# mito-radar-service

这是一个围绕 77G 雷达点云采集服务整理出来的轻量接管仓库，和 MITO 研究代码有关联，但并不是完整的上游 `MITO_Codebase`。  
This is a lightweight handoff repository for a 77G radar point-cloud capture service. It is related to the MITO research codebase, but it is not the full upstream `MITO_Codebase`.

当前仓库主要包含：  
This repository mainly contains:

- 一个最小可运行的 FastAPI 服务入口  
  A minimal FastAPI service entrypoint
- 77G 雷达串口采集与 HEX 点云解析脚本  
  77G radar serial capture and HEX point-cloud parsing scripts
- 一份原始项目交接说明文档  
  An original project handoff guide

## 仓库用途 / Purpose

当前阶段的主要目标是：  
The main goals at this stage are:

- 支持 77G 雷达点云采集  
  Support 77G radar point-cloud capture
- 支持带标签的样本保存  
  Support labeled sample storage
- 为后续基于点云数据做 CPU-only 轻量模型训练打基础  
  Prepare for later CPU-only lightweight model training based on point-cloud data

MITO 相关分类器和权重在这里更多是作为：  
MITO-related classifiers and weights are kept here mainly as:

- 环境验证参考  
  Environment validation references
- 原始训练流程参考  
  References for the original training workflow
- 历史兼容能力保留  
  Preserved compatibility with the earlier setup

需要特别注意的是：当前 77G 雷达输出的点云数据，不能直接拿去使用 MITO 原始的 `final_weights.h5`。  
Important: the current 77G radar point-cloud data cannot be directly used with MITO's original `final_weights.h5`.

## 当前仓库状态 / Current State

当前仓库中最重要的文件有：  
The most important files in this repository are:

- [src/service/app.py](E:\Go\mito-radar-service\src\service\app.py)：当前 FastAPI 服务入口  
  Current FastAPI service entrypoint
- [radar_capture.py](E:\Go\mito-radar-service\radar_capture.py)：原始串口采集脚本  
  Raw serial capture script
- [radar_hex_reader_v2.py](E:\Go\mito-radar-service\radar_hex_reader_v2.py)：当前主用点云解析脚本  
  Current main point-cloud parser
- [radar_hex_debug.py](E:\Go\mito-radar-service\radar_hex_debug.py)：协议字段调试脚本  
  Protocol field debugging script
- [MITO_77G_Codex_Dev_Guide.md](E:\Go\mito-radar-service\MITO_77G_Codex_Dev_Guide.md)：原始项目说明与交接文档  
  Original project guide and handoff notes

## 当前 API / Current API

现在服务已经同时包含“MITO 分类测试接口”和“雷达采集接口”两部分：  
The service now includes both the MITO classifier test endpoints and the radar capture endpoints:

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

这意味着仓库已经从“只有说明文档”推进到了“雷达接口已初步落地”的阶段。  
This means the repository has moved from a documentation-only handoff state to an initial working radar-service implementation.

## 目录结构 / Repository Layout

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

## FastAPI 服务说明 / FastAPI Service Notes

当前服务支持两条能力线：  
The service currently supports two tracks:

- MITO 分类测试任务  
  MITO classifier test jobs
- 77G 雷达采集、最近一次样本保存、带标签样本保存  
  77G radar capture, latest-sample storage, and labeled sample storage

其中分类测试接口仍然依赖这些目录存在：  
The classifier test path still depends on these directories:

- `mmwave_venv/`
- `MITO_Dataset/`
- `src/classification/checkpoints/.../final_weights.h5`

这些目录和文件在原始说明文档中有定义，但不在当前这个精简仓库里。  
These directories and files are described in the original guide but are not part of this trimmed repository.

雷达接口依赖：  
Radar endpoints depend on:

- `fastapi`
- `uvicorn`
- `pyserial`

如果环境里还没有安装 `pyserial`，服务本身仍然可以启动，但 `/radar/health` 会明确返回雷达依赖导入失败的信息。  
If `pyserial` is not installed, the service can still start, but `/radar/health` will explicitly report the radar helper import failure.

## 雷达脚本说明 / Radar Scripts

### `radar_capture.py`

负责从雷达串口读取原始字节流，并保存：  
Reads raw bytes from the radar serial port and saves:

- `.bin`
- `.hex.txt`

### `radar_hex_reader_v2.py`

负责把原始采集数据解析为帧和点，包括这些字段：  
Parses raw captured data into frames and points, including:

- `range_m`
- `velocity_mps`
- `azimuth_deg`
- `elevation_deg`
- `x_m`
- `y_m`
- `z_m`

当前解析假设速度和角度字段采用 15-bit 偏移码：  
The current parser assumes velocity and angle fields use 15-bit offset coding:

```text
real = (raw15 - 0x4000) / 100
```

### `radar_hex_debug.py`

用于检查原始 20 字节点记录，辅助验证字段布局和不同解析方式是否合理。  
Used to inspect raw 20-byte point records and validate field layouts and alternate parsing interpretations.

## 运行环境假设 / Environment Assumptions

原始项目说明里的目标运行环境是：  
The target runtime environment described in the original project guide is:

- Ubuntu VM
- CPU-only
- 无 CUDA  
  No CUDA
- 真实雷达设备通常挂在 `/dev/ttyACM0`  
  The physical radar device is usually attached at `/dev/ttyACM0`

当前这个 Windows 工作区更适合作为开发镜像使用。真正的雷达联调和采集验证，仍然建议在 Ubuntu VM 上进行。  
This Windows workspace is best treated as a development mirror. Real radar integration and capture validation should still happen on the Ubuntu VM.

## 当前运行时输出 / Runtime Outputs

临时采集输出会保存到：  
Temporary capture outputs are saved to:

- `runtime/radar_latest.bin`
- `runtime/radar_latest.jsonl`
- `runtime/radar_latest.json`

带标签采集输出会保存到：  
Labeled capture outputs are saved to:

- `runtime/radar_records/<label>/<label>_<timestamp>.bin`
- `runtime/radar_records/<label>/<label>_<timestamp>.jsonl`
- `runtime/radar_records/<label>/<label>_<timestamp>.meta.json`

## 近期建议路线 / Near-Term Roadmap

1. 保持硬件相关解析逻辑继续集中在 `radar_hex_reader_v2.py`。  
   Keep hardware-specific parsing logic centralized in `radar_hex_reader_v2.py`.
2. 在 Ubuntu VM 上对新补齐的雷达接口做真实设备验证。  
   Validate the implemented radar endpoints on the real Ubuntu VM device.
3. 增加点云样本特征提取脚本。  
   Add a point-cloud feature extraction script.
4. 基于采集结果补轻量分类模型与预测接口。  
   Add a lightweight classifier and prediction endpoints based on collected samples.

## 开发注意事项 / Development Notes

- 不要提交运行期采集数据。  
  Do not commit runtime capture data.
- 不要提交虚拟环境、数据集和模型权重。  
  Do not commit virtual environments, datasets, or model weights.
- 不要默认假设当前仓库包含完整 MITO 源码。  
  Do not assume this repository contains the full MITO source tree.
- `MITO_77G_Codex_Dev_Guide.md` 更适合作为背景说明和目标说明，实际行为请以代码为准。  
  Treat `MITO_77G_Codex_Dev_Guide.md` as background and target-state context; actual behavior should be taken from the code.
