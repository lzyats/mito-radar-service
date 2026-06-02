from fastapi import FastAPI, HTTPException
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import threading
import uuid
import sys
import os
import json
import re

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "mmwave_venv" / "bin" / "python"
JOB_DIR = ROOT / "runtime" / "jobs"
DATASET_DIR = ROOT / "MITO_Dataset"
WEIGHTS_PATH = ROOT / "src" / "classification" / "checkpoints" / "1103c_final_all" / "models" / "final_weights.h5"

JOB_DIR.mkdir(parents=True, exist_ok=True)

# Allow the service to import MITO local modules and compiled C++ extensions.
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "src"))
sys.path.append(str(ROOT / "src" / "simulation" / "cpp"))
sys.path.append(str(ROOT / "src" / "data_processing" / "cpp"))

app = FastAPI(title="MITO CPU Service", version="1.1.0")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def log_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.log"


def pid_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.pid"


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def extract_metrics(log_text: str) -> dict:
    metrics = {}
    for name, value in re.findall(r"(test_(?:all|los|nlos)) acc:\s*([0-9.]+)", log_text):
        metrics[name] = float(value)
    return metrics


@app.get("/health")
def health():
    result = {
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
    except Exception as e:
        result["ok"] = False
        result["torch_error"] = str(e)

    try:
        from src.utils import utilities
        result["processing"] = utilities.load_param_json()["processing"]
    except Exception as e:
        result["ok"] = False
        result["params_error"] = str(e)

    try:
        import simulation
        result["simulation_import"] = True
    except Exception as e:
        result["ok"] = False
        result["simulation_import"] = False
        result["simulation_error"] = str(e)

    try:
        import imaging
        result["imaging_import"] = True
    except Exception as e:
        result["ok"] = False
        result["imaging_import"] = False
        result["imaging_error"] = str(e)

    if not DATASET_DIR.exists():
        result["ok"] = False

    if not WEIGHTS_PATH.exists():
        result["ok"] = False

    return result


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

    pp.write_text(str(proc.pid))

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
            text = lp.read_text(errors="replace")
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

    log_text = lp.read_text(errors="replace")
    status["metrics"] = extract_metrics(log_text)
    status["log_tail"] = log_text[-12000:]
    return status
