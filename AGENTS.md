# AGENTS.md

This repository is a trimmed handoff workspace for a 77G radar service related to the MITO project.

## Project Intent

Use this repository to:

- maintain and extend the radar point-cloud capture workflow
- evolve the FastAPI service toward labeled sample collection
- keep MITO-specific classifier test support only as a secondary compatibility path

Do not assume this repository is the full upstream MITO codebase.

## Current Code Reality

The handoff guide documents a radar API, but the checked-in service currently implements only:

- `GET /health`
- `POST /classifier/test`
- `GET /jobs/{job_id}`

Before making product decisions, verify whether you are working from:

- documented target behavior in `MITO_77G_Codex_Dev_Guide.md`
- actual current behavior in `src/service/app.py`

Call out any mismatch explicitly in commits, reviews, or status updates.

## Important Files

- `src/service/app.py`: current FastAPI service
- `radar_capture.py`: raw UART capture
- `radar_hex_reader_v2.py`: main radar frame and point parser
- `radar_hex_debug.py`: field-layout debugging helper
- `MITO_77G_Codex_Dev_Guide.md`: historical setup and roadmap context

## Environment Assumptions

Primary runtime from the original project notes:

- Ubuntu VM
- CPU-only
- Python virtual environment at `mmwave_venv`
- physical radar serial device typically at `/dev/ttyACM0`

This Windows checkout is mainly for editing and review. Hardware validation usually has to happen on the Ubuntu VM.

## Development Rules

- Keep hardware-specific serial and protocol logic isolated from API orchestration code.
- Prefer evolving `radar_hex_reader_v2.py` for protocol parsing instead of scattering parsing logic into the web layer.
- Keep API glue in `src/service/app.py`.
- Avoid modifying MITO training code unless the task clearly requires it.
- Treat runtime data, datasets, model weights, and virtualenv contents as external state, not source code.

## Git Hygiene

These paths should remain out of Git:

- `mmwave_venv/`
- `MITO_Dataset/`
- `runtime/`
- `src/classification/checkpoints/`
- `*.bin`
- `*.jsonl`
- `*.log`

## Recommended Next Steps

1. Implement the documented radar endpoints in `src/service/app.py`.
2. Standardize runtime output paths for latest captures and labeled recordings.
3. Add a feature extraction script for stored radar records.
4. Add a lightweight CPU-friendly classifier for collected point-cloud samples.

## Verification Guidance

For code-only changes in this repository, prefer at least:

```bash
python -m py_compile radar_hex_reader_v2.py src/service/app.py
```

For radar behavior, expect a two-step workflow:

1. edit and review here
2. validate against the real radar on the Ubuntu VM
