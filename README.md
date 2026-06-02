# mito-radar-service

This repository is a lightweight handoff workspace for a 77G radar point-cloud capture service built alongside the MITO research codebase.

It is not the full upstream `MITO_Codebase`. Instead, it contains:

- a minimal FastAPI service entrypoint
- 77G radar capture and HEX parsing scripts
- a project handoff guide for the original Ubuntu VM environment

## What This Repo Is For

The current development goal is to support:

- 77G radar point-cloud capture
- labeled sample storage for later training
- lightweight CPU-only model experimentation on collected point-cloud data

The MITO classifier and weights are kept here mainly as:

- environment validation
- reference code
- a known-good baseline for the original MITO setup

The current 77G radar point-cloud data is not directly compatible with MITO's original `final_weights.h5`.

## Current State

The repository currently includes:

- [src/service/app.py](E:\Go\mito-radar-service\src\service\app.py): minimal FastAPI service
- [radar_capture.py](E:\Go\mito-radar-service\radar_capture.py): raw serial capture script
- [radar_hex_reader_v2.py](E:\Go\mito-radar-service\radar_hex_reader_v2.py): point-cloud parser
- [radar_hex_debug.py](E:\Go\mito-radar-service\radar_hex_debug.py): protocol debugging helper
- [MITO_77G_Codex_Dev_Guide.md](E:\Go\mito-radar-service\MITO_77G_Codex_Dev_Guide.md): original project handoff guide

## Important Reality Check

The handoff guide describes a target radar API with routes such as:

- `GET /radar/health`
- `POST /radar/capture`
- `POST /radar/record`
- `GET /radar/latest`

But the current checked-in FastAPI code does not provide those routes yet.

Today, [src/service/app.py](E:\Go\mito-radar-service\src\service\app.py) only exposes:

- `GET /health`
- `POST /classifier/test`
- `GET /jobs/{job_id}`

So the repository is currently between two stages:

- documented target state: radar capture service
- actual code state: MITO classifier test job service plus radar scripts

## Repository Layout

```text
.
|-- MITO_77G_Codex_Dev_Guide.md
|-- README.md
|-- AGENTS.md
|-- radar_capture.py
|-- radar_hex_debug.py
|-- radar_hex_reader_v2.py
`-- src/
    `-- service/
        `-- app.py
```

## FastAPI Service Today

The checked-in service is aimed at running a background MITO classifier test job against a prepared Ubuntu VM environment.

It expects paths like:

- `mmwave_venv/`
- `MITO_Dataset/`
- `src/classification/checkpoints/.../final_weights.h5`

Those directories are described in the handoff guide but are not part of this trimmed repository.

## Radar Scripts

### `radar_capture.py`

Captures raw bytes from the radar serial port and saves:

- `.bin`
- `.hex.txt`

### `radar_hex_reader_v2.py`

Parses captured radar data into frames and points, including:

- `range_m`
- `velocity_mps`
- `azimuth_deg`
- `elevation_deg`
- `x_m`
- `y_m`
- `z_m`

It assumes the radar angle and velocity fields are 15-bit offset-coded values:

```text
real = (raw15 - 0x4000) / 100
```

### `radar_hex_debug.py`

Helps inspect raw 20-byte point records and compare alternate field interpretations while validating the protocol.

## Expected Runtime Environment

The original target environment from the handoff guide is:

- Ubuntu VM
- CPU-only
- no CUDA
- physical radar attached there, typically `/dev/ttyACM0`

This local Windows workspace is best treated as a development mirror. Real radar verification is expected to happen on the Ubuntu VM.

## Suggested Near-Term Roadmap

1. Align the FastAPI service with the documented radar endpoints.
2. Keep hardware-specific logic isolated in `radar_hex_reader_v2.py`.
3. Add runtime output conventions for latest capture and labeled records.
4. Add feature extraction and a lightweight classifier trained on collected point-cloud samples.

## Development Notes

- Do not commit runtime capture data.
- Do not commit virtual environments, datasets, or pretrained weights.
- Do not assume the full MITO source tree is present in this repository.
- Treat `MITO_77G_Codex_Dev_Guide.md` as historical and target-state context, not as a perfect description of checked-in code.
