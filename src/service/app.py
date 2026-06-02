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
from fastapi.responses import HTMLResponse

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


DASHBOARD_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MITO Radar Console</title>
  <style>
    :root {
      --bg: #f5f7f2;
      --panel: #ffffff;
      --ink: #17211b;
      --muted: #66736a;
      --line: #dfe6dc;
      --accent: #20775a;
      --accent-strong: #135b44;
      --warn: #b45f06;
      --bad: #a73030;
      --good: #1f7a4d;
      --shadow: 0 18px 45px rgba(32, 56, 42, 0.12);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(135deg, rgba(32,119,90,0.10), transparent 34%),
        linear-gradient(180deg, #fbfcf8 0%, var(--bg) 100%);
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    }

    .shell {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 42px;
    }

    header {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-end;
      padding: 8px 0 24px;
    }

    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 48px);
      line-height: 1;
      letter-spacing: 0;
    }

    .subtitle {
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 15px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 8px 13px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255,255,255,0.72);
      font-size: 14px;
      white-space: nowrap;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--warn);
    }

    .dot.good { background: var(--good); }
    .dot.bad { background: var(--bad); }

    .grid {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 18px;
      align-items: start;
    }

    .panel {
      background: rgba(255,255,255,0.88);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .panel-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
    }

    .panel-title {
      margin: 0;
      font-size: 17px;
      font-weight: 700;
    }

    .panel-body { padding: 18px; }

    .controls {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }

    input {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      color: var(--ink);
      background: #fff;
      font: inherit;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }

    button {
      min-height: 40px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 13px;
      color: #fff;
      background: var(--accent);
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }

    button.secondary {
      color: var(--accent-strong);
      background: #fff;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.55;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 16px;
    }

    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcf8;
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }

    .metric strong {
      display: block;
      margin-top: 6px;
      font-size: 22px;
    }

    .split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-top: 18px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }

    th, td {
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    pre {
      min-height: 180px;
      max-height: 420px;
      margin: 0;
      padding: 14px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #111a15;
      color: #d7f6e7;
      font-size: 12px;
      line-height: 1.5;
    }

    .empty {
      color: var(--muted);
      padding: 14px 0;
      font-size: 14px;
    }

    @media (max-width: 860px) {
      header, .grid, .split { grid-template-columns: 1fr; display: grid; }
      header { align-items: start; }
      .controls, .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 520px) {
      .shell { width: min(100% - 22px, 1180px); padding-top: 18px; }
      .controls, .metrics { grid-template-columns: 1fr; }
      .panel-head { align-items: flex-start; flex-direction: column; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>MITO Radar Console</h1>
        <p class="subtitle">77G 雷达点云采集、样本保存和标签统计</p>
      </div>
      <div class="status-pill"><span id="healthDot" class="dot"></span><span id="healthText">等待检查</span></div>
    </header>

    <section class="grid">
      <div class="panel">
        <div class="panel-head">
          <h2 class="panel-title">采集控制</h2>
          <button class="secondary" id="refreshHealth">刷新状态</button>
        </div>
        <div class="panel-body">
          <div class="controls">
            <label>采集秒数<input id="seconds" type="number" min="1" max="300" value="3"></label>
            <label>最小距离 m<input id="minRange" type="number" min="0" step="0.01" value="0.0"></label>
            <label>最大距离 m<input id="maxRange" type="number" min="0.1" step="0.1" value="3.0"></label>
            <label>样本标签<input id="label" value="empty" placeholder="empty / udisk / box"></label>
          </div>
          <div class="actions">
            <button id="captureBtn">临时采集</button>
            <button id="recordBtn">保存为训练样本</button>
            <button class="secondary" id="latestBtn">查看最近一次</button>
            <button class="secondary" id="refreshData">刷新标签和记录</button>
          </div>

          <div class="metrics">
            <div class="metric"><span>有效点数</span><strong id="validPoints">-</strong></div>
            <div class="metric"><span>是否有目标</span><strong id="hasTarget">-</strong></div>
            <div class="metric"><span>非空帧</span><strong id="frames">-</strong></div>
            <div class="metric"><span>最近距离</span><strong id="nearest">-</strong></div>
          </div>

          <div class="split">
            <div>
              <h3 class="panel-title">标签统计</h3>
              <div id="labelsBox" class="empty">暂无标签</div>
            </div>
            <div>
              <h3 class="panel-title">最近记录</h3>
              <div id="recordsBox" class="empty">暂无记录</div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2 class="panel-title">接口输出</h2>
          <span id="busyText" class="subtitle"></span>
        </div>
        <div class="panel-body">
          <pre id="output">等待操作...</pre>
        </div>
      </div>
    </section>
  </main>

  <script>
    const el = (id) => document.getElementById(id);
    const buttons = ["captureBtn", "recordBtn", "latestBtn", "refreshData", "refreshHealth"].map(el);

    function setBusy(isBusy, text = "") {
      buttons.forEach((button) => button.disabled = isBusy);
      el("busyText").textContent = text;
    }

    function show(data) {
      el("output").textContent = JSON.stringify(data, null, 2);
      updateMetrics(data.summary || data);
    }

    function updateMetrics(summary) {
      if (!summary) return;
      el("validPoints").textContent = summary.valid_point_count ?? "-";
      el("hasTarget").textContent = summary.has_target === true ? "是" : summary.has_target === false ? "否" : "-";
      const frames = summary.non_empty_frames !== undefined && summary.frames !== undefined
        ? `${summary.non_empty_frames}/${summary.frames}`
        : "-";
      el("frames").textContent = frames;
      const nearest = summary.nearest_point || summary.raw_nearest_point;
      el("nearest").textContent = nearest ? `${nearest.range_m} m` : "-";
    }

    async function api(path, options = {}) {
      setBusy(true, "请求中...");
      try {
        const res = await fetch(path, options);
        const data = await res.json();
        show(data);
        return data;
      } catch (error) {
        const data = { error: String(error) };
        show(data);
        return data;
      } finally {
        setBusy(false);
      }
    }

    function params(includeLabel = false) {
      const query = new URLSearchParams({
        seconds: el("seconds").value || "3",
        min_range: el("minRange").value || "0.0",
        max_range: el("maxRange").value || "3.0",
      });
      if (includeLabel) query.set("label", el("label").value || "empty");
      return query.toString();
    }

    async function refreshHealth() {
      const data = await api("/radar/health");
      const dot = el("healthDot");
      dot.className = data.ok ? "dot good" : "dot bad";
      el("healthText").textContent = data.ok
        ? `雷达已连接 ${data.port}`
        : `雷达未就绪 ${data.port || ""}`;
    }

    async function refreshLabels() {
      const data = await fetch("/radar/labels").then((r) => r.json());
      if (!data.labels || !data.labels.length) {
        el("labelsBox").innerHTML = '<div class="empty">暂无标签</div>';
        return data;
      }
      const rows = data.labels.map((item) =>
        `<tr><td>${item.label}</td><td>${item.sample_count ?? item.count}</td></tr>`
      ).join("");
      el("labelsBox").innerHTML = `<table><thead><tr><th>标签</th><th>样本数</th></tr></thead><tbody>${rows}</tbody></table>`;
      return data;
    }

    async function refreshRecords() {
      const data = await fetch("/radar/records?limit=8").then((r) => r.json());
      if (!data.records || !data.records.length) {
        el("recordsBox").innerHTML = '<div class="empty">暂无记录</div>';
        return data;
      }
      const rows = data.records.map((item) =>
        `<tr><td>${item.label || "-"}</td><td>${item.captured_at || "-"}</td><td>${item.summary?.valid_point_count ?? "-"}</td></tr>`
      ).join("");
      el("recordsBox").innerHTML = `<table><thead><tr><th>标签</th><th>时间</th><th>点数</th></tr></thead><tbody>${rows}</tbody></table>`;
      return data;
    }

    async function refreshData() {
      setBusy(true, "刷新中...");
      try {
        const [labels, records] = await Promise.all([refreshLabels(), refreshRecords()]);
        show({ labels, records });
      } finally {
        setBusy(false);
      }
    }

    el("refreshHealth").addEventListener("click", refreshHealth);
    el("refreshData").addEventListener("click", refreshData);
    el("latestBtn").addEventListener("click", () => api("/radar/latest"));
    el("captureBtn").addEventListener("click", () => api(`/radar/capture?${params(false)}`, { method: "POST" }));
    el("recordBtn").addEventListener("click", async () => {
      const data = await api(`/radar/record?${params(true)}`, { method: "POST" });
      if (!data.detail && !data.error) await refreshData();
    });

    refreshHealth();
    refreshData();
  </script>
</body>
</html>
"""


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


def compact_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_id": point["frame_id"],
        "point_index": point["point_index"],
        "range_m": round(point["range_m"], 4),
        "velocity_mps": round(point["velocity_mps"], 4),
        "azimuth_deg": round(point["azimuth_deg"], 4),
        "elevation_deg": round(point["elevation_deg"], 4),
        "snr": point["snr"],
        "x_m": round(point["x_m"], 4),
        "y_m": round(point["y_m"], 4),
        "z_m": round(point["z_m"], 4),
    }


def summarize_points(points: list[dict[str, Any]], frames) -> dict[str, Any]:
    non_empty_frames = sum(1 for frame in frames if frame.points)
    summary: dict[str, Any] = {
        "frames": len(frames),
        "non_empty_frames": non_empty_frames,
        "non_empty_frame_ratio": round(non_empty_frames / len(frames), 4) if frames else 0.0,
        "point_count": len(points),
        "valid_point_count": len(points),
        "has_target": len(points) > 0,
    }

    if not frames:
        summary["center"] = None
        summary["nearest_point"] = None
        return summary

    summary["frame_ids"] = {
        "first": frames[0].frame_id,
        "last": frames[-1].frame_id,
    }

    if not points:
        summary["center"] = None
        summary["nearest_point"] = None
        return summary

    ranges = [point["range_m"] for point in points]
    snrs = [point["snr"] for point in points]
    velocities = [point["velocity_mps"] for point in points]
    xs = [point["x_m"] for point in points]
    ys = [point["y_m"] for point in points]
    zs = [point["z_m"] for point in points]
    nearest_point = min(points, key=lambda point: point["range_m"])

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
            "center": {
                "x_m": round(sum(xs) / len(xs), 4),
                "y_m": round(sum(ys) / len(ys), 4),
                "z_m": round(sum(zs) / len(zs), 4),
                "range_m": round(sum(ranges) / len(ranges), 4),
            },
            "nearest_point": compact_point(nearest_point),
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
    raw_points = extract_filtered_points(frames, min_range=0.0, max_range=None)
    points = extract_filtered_points(frames, min_range=min_range, max_range=max_range)
    summary = summarize_points(points, frames)
    raw_nearest_point = min(raw_points, key=lambda point: point["range_m"]) if raw_points else None
    summary["raw_point_count"] = len(raw_points)
    summary["filtered_out_by_range"] = max(len(raw_points) - len(points), 0)
    summary["raw_nearest_point"] = compact_point(raw_nearest_point) if raw_nearest_point else None
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


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(DASHBOARD_HTML)


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
    port_exists = resolve_port_exists(port)
    start_command = "scan start -1 stream_on"
    stop_command = "scan stop"
    try:
        helpers = load_radar_helpers()
        start_command = helpers["START_CMD"].decode("utf-8", errors="replace").strip()
        stop_command = helpers["STOP_CMD"].decode("utf-8", errors="replace").strip()
    except HTTPException as exc:
        helper_error = exc.detail

    return {
        "ok": helper_error is None and port_exists,
        "port": port,
        "baud": baud,
        "port_exists": port_exists,
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
        sample_count = len(meta_files)
        labels.append(
            {
                "label": label_dir.name,
                "sample_count": sample_count,
                "count": sample_count,
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
