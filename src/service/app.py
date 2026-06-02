from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import re
import subprocess
import sys
import threading
import uuid

from fastapi import FastAPI, HTTPException, Query

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "mmwave_venv" / "bin" / "python"
RUNTIME_DIR = ROOT / "runtime"
JOB_DIR = RUNTIME_DIR / "jobs"
RADAR_RECORDS_DIR = RUNTIME_DIR / "radar_records"
RADAR_LATEST_BIN = RUNTIME_DIR / "radar_latest.bin"
RADAR_LATEST_JSONL = RUNTIME_DIR / "radar_latest.jsonl"
RADAR_LATEST_JSON = RUNTIME_DIR / "radar_latest.json"
DATASET_DIR = ROOT / "MITO_Dataset"
WEIGHTS_PATH = ROOT / "src" / "classification" / "checkpoints" / "1103c_final_all" / "models" / "final_weights.h5"
DEFAULT_RADAR_PORT = os.environ.get("RADAR_PORT", "/dev/ttyACM0")
DEFAULT_RADAR_BAUD = int(os.environ.get("RADAR_BAUD", "3000000"))
ALLOWED_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

JOB_DIR.mkdir(parents=True, exist_ok=True)
RADAR_RECORDS_DIR.mkdir(parents=True, exist_ok=True)

# Allow the service to import local modules and compiled C++ extensions when present.
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "src"))
sys.path.append(str(ROOT / "src" / "simulation" / "cpp"))
sys.path.append(str(ROOT / "src" / "data_processing" / "cpp"))

app = FastAPI(title="MITO Radar Service", version="1.2.0")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def status_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def log_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.log"


def pid_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.pid"


def write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_metrics(log_text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for name, value in re.findall(r"(test_(?:all|los|nlos)) acc:\s*([0-9.]+)", log_text):
        metrics[name] = float(value)
    return metrics


def load_radar_helpers():
    try:
        from radar_hex_reader_v2 import START_CMD, STOP_CMD, capture_live, parse_frames, write_jsonl
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Radar helper import failed: {exc}") from exc
    return {
        "START_CMD": START_CMD,
        "STOP_CMD": STOP_CMD,
        "capture_live": capture_live,
        "parse_frames": parse_frames,
        "write_jsonl": write_jsonl,
    }


def extract_filtered_points(frames, min_range: float, max_range: float | None) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for frame in frames:
        for point in frame.points:
            if point.range_m < min_range:
                continue
            if max_range is not None and point.range_m > max_range:
                continue
            points.append(asdict(point))
    return points


def summarize_points(points: list[dict[str, Any]], frames) -> dict[str, Any]:
    non_empty_frames = sum(1 for frame in frames if frame.points)
    summary: dict[str, Any] = {
        "frames": len(frames),
        "non_empty_frames": non_empty_frames,
        "point_count": len(points),
    }

    if not frames:
        return summary

    summary["frame_ids"] = {
        "first": frames[0].frame_id,
        "last": frames[-1].frame_id,
    }

    if not points:
        return summary

    ranges = [point["range_m"] for point in points]
    snrs = [point["snr"] for point in points]
    velocities = [point["velocity_mps"] for point in points]
    xs = [point["x_m"] for point in points]
    ys = [point["y_m"] for point in points]
    zs = [point["z_m"] for point in points]

    summary.update(
        {
            "avg_range_m": round(sum(ranges) / len(ranges), 4),
            "min_range_m": round(min(ranges), 4),
            "max_range_m": round(max(ranges), 4),
            "avg_snr": round(sum(snrs) / len(snrs), 4),
            "max_snr": max(snrs),
            "avg_velocity_mps": round(sum(velocities) / len(velocities), 4),
            "bbox": {
                "x": [round(min(xs), 4), round(max(xs), 4)],
                "y": [round(min(ys), 4), round(max(ys), 4)],
                "z": [round(min(zs), 4), round(max(zs), 4)],
            },
        }
    )
    return summary


def build_capture_payload(
    *,
    raw: bytes,
    frames,
    min_range: float,
    max_range: float | None,
    sample_points_limit: int = 12,
) -> dict[str, Any]:
    points = extract_filtered_points(frames, min_range=min_range, max_range=max_range)
    summary = summarize_points(points, frames)
    return {
        "captured_at": utc_now(),
        "raw_bytes": len(raw),
        "min_range": min_range,
        "max_range": max_range,
        "summary": summary,
        "sample_points": points[:sample_points_limit],
    }


def ensure_valid_label(label: str) -> str:
    if not ALLOWED_LABEL_RE.fullmatch(label):
        raise HTTPException(status_code=400, detail="Invalid label")
    return label


def resolve_port_exists(port: str) -> bool:
    try:
        return Path(port).exists()
    except Exception:
        return False


def save_capture_artifacts(
    *,
    raw: bytes,
    frames,
    meta: dict[str, Any],
    bin_path: Path,
    jsonl_path: Path,
    meta_path: Path,
) -> dict[str, Any]:
    helpers = load_radar_helpers()
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(raw)
    helpers["write_jsonl"](frames, str(jsonl_path))
    write_json(meta_path, meta)
    return {
        "bin_path": str(bin_path),
        "jsonl_path": str(jsonl_path),
        "meta_path": str(meta_path),
    }


def capture_radar_once(
    *,
    port: str,
    baud: int,
    seconds: int,
    min_range: float,
    max_range: float | None,
) -> tuple[bytes, list[Any], dict[str, Any]]:
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be > 0")
    if min_range < 0:
        raise HTTPException(status_code=400, detail="min_range must be >= 0")
    if max_range is not None and max_range <= min_range:
        raise HTTPException(status_code=400, detail="max_range must be greater than min_range")

    helpers = load_radar_helpers()
    try:
        raw = helpers["capture_live"](port=port, baud=baud, seconds=seconds)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Radar capture failed: {exc}") from exc

    frames = helpers["parse_frames"](raw)
    payload = build_capture_payload(raw=raw, frames=frames, min_range=min_range, max_range=max_range)
    return raw, frames, payload


def list_record_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not RADAR_RECORDS_DIR.exists():
        return items

    for meta_path in sorted(RADAR_RECORDS_DIR.glob("*/*.meta.json"), reverse=True):
        try:
            meta = read_json(meta_path)
        except Exception:
            continue
        meta["meta_path"] = str(meta_path)
        items.append(meta)
    return items


@app.get("/")
def root():
    return {
        "service": "mito-radar-service",
        "version": app.version,
        "routes": [
            "/health",
            "/classifier/test",
            "/jobs/{job_id}",
            "/radar/health",
            "/radar/capture",
            "/radar/latest",
            "/radar/record",
            "/radar/records",
            "/radar/labels",
        ],
    }


@app.get("/health")
def health():
    result: dict[str, Any] = {
        "ok": True,
        "root": str(ROOT),
        "python": str(PYTHON),
        "dataset_exists": DATASET_DIR.exists(),
        "weights_exists": WEIGHTS_PATH.exists(),
        "weights_path": str(WEIGHTS_PATH),
    }

    try:
        import torch

        result["torch"] = torch.__version__
        result["cuda_available"] = torch.cuda.is_available()
    except Exception as exc:
        result["ok"] = False
        result["torch_error"] = str(exc)

    try:
        from src.utils import utilities

        result["processing"] = utilities.load_param_json()["processing"]
    except Exception as exc:
        result["ok"] = False
        result["params_error"] = str(exc)

    try:
        import simulation

        result["simulation_import"] = True
    except Exception as exc:
        result["ok"] = False
        result["simulation_import"] = False
        result["simulation_error"] = str(exc)

    try:
        import imaging

        result["imaging_import"] = True
    except Exception as exc:
        result["ok"] = False
        result["imaging_import"] = False
        result["imaging_error"] = str(exc)

    if not DATASET_DIR.exists():
        result["ok"] = False

    if not WEIGHTS_PATH.exists():
        result["ok"] = False

    return result


@app.get("/radar/health")
def radar_health(
    port: str = Query(DEFAULT_RADAR_PORT),
    baud: int = Query(DEFAULT_RADAR_BAUD),
):
    helper_error = None
    start_command = "scan start -1 stream_on"
    stop_command = "scan stop"
    try:
        helpers = load_radar_helpers()
        start_command = helpers["START_CMD"].decode("utf-8", errors="replace").strip()
        stop_command = helpers["STOP_CMD"].decode("utf-8", errors="replace").strip()
    except HTTPException as exc:
        helper_error = exc.detail

    return {
        "ok": helper_error is None,
        "port": port,
        "baud": baud,
        "port_exists": resolve_port_exists(port),
        "reader_exists": (ROOT / "radar_hex_reader_v2.py").exists(),
        "helper_import_ok": helper_error is None,
        "helper_error": helper_error,
        "runtime_dir": str(RUNTIME_DIR),
        "start_command": start_command,
        "stop_command": stop_command,
    }


@app.post("/classifier/test")
def run_classifier_test():
    """
    Starts a background job equivalent to:
      cd src/classification && python3 test_classifier.py --use_cpu True
    """
    if not DATASET_DIR.exists():
        raise HTTPException(status_code=400, detail="MITO_Dataset not found")

    if not WEIGHTS_PATH.exists():
        raise HTTPException(status_code=400, detail="final_weights.h5 not found")

    job_id = uuid.uuid4().hex
    lp = log_path(job_id)
    pp = pid_path(job_id)
    sp = status_path(job_id)

    cmd = [
        str(PYTHON),
        "test_classifier.py",
        "--use_cpu",
        "True",
    ]

    with open(lp, "wb") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT / "src" / "classification"),
            stdout=log,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
            },
        )

    pp.write_text(str(proc.pid), encoding="utf-8")

    initial_status = {
        "job_id": job_id,
        "pid": proc.pid,
        "running": True,
        "exit_code": None,
        "started_at": utc_now(),
        "finished_at": None,
        "command": " ".join(cmd),
        "log_path": str(lp),
    }
    write_json(sp, initial_status)

    def wait_and_record():
        exit_code = proc.wait()
        try:
            current = read_json(sp)
        except Exception:
            current = initial_status
        current["running"] = False
        current["exit_code"] = exit_code
        current["finished_at"] = utc_now()
        try:
            text = lp.read_text(errors="replace", encoding="utf-8")
            current["metrics"] = extract_metrics(text)
        except Exception:
            current["metrics"] = {}
        write_json(sp, current)

    threading.Thread(target=wait_and_record, daemon=True).start()

    return {
        "job_id": job_id,
        "pid": proc.pid,
        "log_path": str(lp),
        "status_url": f"/jobs/{job_id}",
    }


@app.post("/radar/capture")
def radar_capture(
    seconds: int = Query(3, ge=1, le=120),
    min_range: float = Query(0.0, ge=0.0),
    max_range: float | None = Query(None),
    port: str = Query(DEFAULT_RADAR_PORT),
    baud: int = Query(DEFAULT_RADAR_BAUD, ge=1),
):
    raw, frames, payload = capture_radar_once(
        port=port,
        baud=baud,
        seconds=seconds,
        min_range=min_range,
        max_range=max_range,
    )

    meta = {
        **payload,
        "port": port,
        "baud": baud,
        "seconds": seconds,
        "saved_as": "latest",
    }
    artifact_paths = save_capture_artifacts(
        raw=raw,
        frames=frames,
        meta=meta,
        bin_path=RADAR_LATEST_BIN,
        jsonl_path=RADAR_LATEST_JSONL,
        meta_path=RADAR_LATEST_JSON,
    )

    return {
        **meta,
        **artifact_paths,
    }


@app.get("/radar/latest")
def radar_latest():
    if not RADAR_LATEST_JSON.exists():
        raise HTTPException(status_code=404, detail="No latest radar capture found")
    return read_json(RADAR_LATEST_JSON)


@app.post("/radar/record")
def radar_record(
    label: str = Query(..., min_length=1),
    seconds: int = Query(8, ge=1, le=300),
    min_range: float = Query(0.0, ge=0.0),
    max_range: float | None = Query(None),
    port: str = Query(DEFAULT_RADAR_PORT),
    baud: int = Query(DEFAULT_RADAR_BAUD, ge=1),
):
    label = ensure_valid_label(label)
    raw, frames, payload = capture_radar_once(
        port=port,
        baud=baud,
        seconds=seconds,
        min_range=min_range,
        max_range=max_range,
    )

    tag = now_tag()
    record_dir = RADAR_RECORDS_DIR / label
    base_name = f"{label}_{tag}"
    bin_path = record_dir / f"{base_name}.bin"
    jsonl_path = record_dir / f"{base_name}.jsonl"
    meta_path = record_dir / f"{base_name}.meta.json"

    meta = {
        **payload,
        "label": label,
        "port": port,
        "baud": baud,
        "seconds": seconds,
    }
    artifact_paths = save_capture_artifacts(
        raw=raw,
        frames=frames,
        meta=meta,
        bin_path=bin_path,
        jsonl_path=jsonl_path,
        meta_path=meta_path,
    )

    return {
        **meta,
        **artifact_paths,
    }


@app.get("/radar/records")
def radar_records(limit: int = Query(100, ge=1, le=1000)):
    items = list_record_items()[:limit]
    return {
        "count": len(items),
        "records": items,
    }


@app.get("/radar/labels")
def radar_labels():
    labels: list[dict[str, Any]] = []
    for label_dir in sorted(RADAR_RECORDS_DIR.iterdir()) if RADAR_RECORDS_DIR.exists() else []:
        if not label_dir.is_dir():
            continue
        meta_files = list(label_dir.glob("*.meta.json"))
        labels.append(
            {
                "label": label_dir.name,
                "count": len(meta_files),
            }
        )
    return {
        "count": len(labels),
        "labels": labels,
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if not job_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid job_id")

    lp = log_path(job_id)
    sp = status_path(job_id)

    if not lp.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    if sp.exists():
        status = read_json(sp)
    else:
        # Compatibility with older jobs created by app.py v1.0.
        status = {
            "job_id": job_id,
            "pid": None,
            "running": False,
            "exit_code": None,
            "started_at": None,
            "finished_at": None,
            "log_path": str(lp),
        }

    log_text = lp.read_text(errors="replace", encoding="utf-8")
    status["metrics"] = extract_metrics(log_text)
    status["log_tail"] = log_text[-12000:]
    return status
