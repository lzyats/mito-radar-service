# AGENTS.md

这是一个围绕 77G 雷达服务整理出来的精简接管仓库，和 MITO 项目有关，但不是完整的 MITO 上游代码库。  
This is a trimmed handoff repository centered on a 77G radar service. It is related to MITO, but it is not the full upstream MITO codebase.

## 项目目标 / Project Intent

这个仓库主要用于：  
This repository is mainly used to:

- 维护和扩展雷达点云采集流程  
  Maintain and extend the radar point-cloud capture workflow
- 持续完善 FastAPI 服务，支持样本采集和保存  
  Continue improving the FastAPI service for sample capture and storage
- 保留 MITO 分类测试接口作为兼容能力，而不是当前主线  
  Keep the MITO classifier test endpoint as a compatibility path rather than the primary product path

不要默认把这个仓库当成完整的 `MITO_Codebase`。  
Do not assume this repository is the full `MITO_Codebase`.

## 当前代码现状 / Current Code Reality

当前服务已经实现这些接口：  
The current service implements these routes:

- `GET /`
- `GET /health`
- `POST /classifier/test`
- `GET /jobs/{job_id}`
- `GET /radar/health`
- `POST /radar/capture`
- `GET /radar/latest`
- `POST /radar/record`
- `GET /radar/records`
- `GET /radar/labels`

原始交接文档仍然有价值，但凡是涉及实际接口行为、字段结构、保存路径，优先以 `src/service/app.py` 为准。  
The original handoff guide is still useful, but for actual route behavior, field structures, and storage paths, prefer `src/service/app.py`.

## 关键文件 / Important Files

- `src/service/app.py`：当前 FastAPI 服务  
  Current FastAPI service
- `radar_capture.py`：原始串口采集  
  Raw serial capture
- `radar_hex_reader_v2.py`：主用雷达帧/点解析脚本  
  Main radar frame/point parser
- `radar_hex_debug.py`：字段布局调试脚本  
  Field-layout debugging script
- `MITO_77G_Codex_Dev_Guide.md`：历史背景、部署过程和路线说明  
  Historical background, deployment process, and roadmap notes

## 环境假设 / Environment Assumptions

原始运行环境来自项目说明：  
The original runtime assumptions from the project guide are:

- Ubuntu VM
- CPU-only
- Python 虚拟环境目录为 `mmwave_venv`  
  Python virtual environment at `mmwave_venv`
- 真实雷达串口设备通常为 `/dev/ttyACM0`  
  Physical radar serial device usually at `/dev/ttyACM0`

当前这个 Windows 工作区主要用于编辑、评审和准备提交。涉及真实硬件的验证，通常还是要回到 Ubuntu VM 完成。  
This Windows workspace is mainly for editing, review, and preparing changes. Real hardware validation usually still needs to happen on the Ubuntu VM.

## 开发规则 / Development Rules

- 硬件串口、协议解析相关逻辑尽量集中在 `radar_hex_reader_v2.py`。  
  Keep serial and protocol parsing logic centralized in `radar_hex_reader_v2.py`.
- API 编排和响应结构尽量集中在 `src/service/app.py`。  
  Keep API orchestration and response structure in `src/service/app.py`.
- 不要把点云解析逻辑零散复制到 Web 层。  
  Do not scatter duplicated point-cloud parsing logic into the web layer.
- 除非任务明确要求，否则不要主动改 MITO 原始训练逻辑。  
  Do not modify original MITO training logic unless the task clearly requires it.
- 运行期数据、数据集、模型权重、虚拟环境都视为外部状态，不视为源码。  
  Treat runtime data, datasets, model weights, and virtual environments as external state rather than source code.

## Git 约束 / Git Hygiene

这些路径和文件类型应该继续避免提交：  
These paths and file types should remain out of Git:

- `mmwave_venv/`
- `MITO_Dataset/`
- `runtime/`
- `src/classification/checkpoints/`
- `*.bin`
- `*.jsonl`
- `*.log`

## 推荐下一步 / Recommended Next Steps

1. 在 Ubuntu VM 上对当前雷达接口做真实硬件验证。  
   Validate the current radar endpoints on the Ubuntu VM with the real device.
2. 补齐下游训练需要的运行时元数据规范。  
   Standardize runtime metadata needed by downstream training.
3. 增加样本特征提取脚本。  
   Add a sample feature extraction script.
4. 增加适合 CPU 的轻量分类模型。  
   Add a lightweight CPU-friendly classifier.

## 验证建议 / Verification Guidance

对于当前仓库里的代码改动，至少执行：  
For code changes in this repository, at minimum run:

```bash
python -m py_compile radar_hex_reader_v2.py src/service/app.py
```

涉及雷达行为时，默认按两步走：  
For radar behavior, the default workflow is:

1. 在这里改代码和评审  
   Edit and review here
2. 回 Ubuntu VM 连真实设备验证  
   Validate with the real device on the Ubuntu VM
