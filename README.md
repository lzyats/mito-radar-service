# mito-radar-service

这是一个围绕 77G 雷达点云采集服务整理出来的轻量接管仓库，和 MITO 研究代码有关联，但并不是完整的上游 `MITO_Codebase`。

当前仓库主要包含：

- 一个最小可运行的 FastAPI 服务入口
- 77G 雷达串口采集与 HEX 点云解析脚本
- 一份原始项目交接说明文档

## 仓库用途

当前阶段的主要目标是：

- 支持 77G 雷达点云采集
- 支持带标签的样本保存
- 为后续基于点云数据做 CPU-only 轻量模型训练打基础

MITO 相关分类器和权重在这里更多是作为：

- 环境验证参考
- 原始训练流程参考
- 历史兼容能力保留

需要特别注意的是：当前 77G 雷达输出的点云数据，不能直接拿去使用 MITO 原始的 `final_weights.h5`。

## 当前仓库状态

当前仓库中最重要的文件有：

- [src/service/app.py](E:\Go\mito-radar-service\src\service\app.py)：当前 FastAPI 服务入口
- [radar_capture.py](E:\Go\mito-radar-service\radar_capture.py)：原始串口采集脚本
- [radar_hex_reader_v2.py](E:\Go\mito-radar-service\radar_hex_reader_v2.py)：当前主用点云解析脚本
- [radar_hex_debug.py](E:\Go\mito-radar-service\radar_hex_debug.py)：协议字段调试脚本
- [MITO_77G_Codex_Dev_Guide.md](E:\Go\mito-radar-service\MITO_77G_Codex_Dev_Guide.md)：原始项目说明与交接文档

## 当前 API

现在服务已经同时包含“MITO 分类测试接口”和“雷达采集接口”两部分：

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

## 目录结构

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

## FastAPI 服务说明

当前服务支持两条能力线：

- MITO 分类测试任务
- 77G 雷达采集、最近一次样本保存、带标签样本保存

其中分类测试接口仍然依赖这些目录存在：

- `mmwave_venv/`
- `MITO_Dataset/`
- `src/classification/checkpoints/.../final_weights.h5`

这些目录和文件在原始说明文档中有定义，但不在当前这个精简仓库里。

雷达接口依赖：

- `fastapi`
- `uvicorn`
- `pyserial`

如果环境里还没有安装 `pyserial`，服务本身仍然可以启动，但 `/radar/health` 会明确返回雷达依赖导入失败的信息。

## 雷达脚本说明

### `radar_capture.py`

负责从雷达串口读取原始字节流，并保存：

- `.bin`
- `.hex.txt`

### `radar_hex_reader_v2.py`

负责把原始采集数据解析为帧和点，包括这些字段：

- `range_m`
- `velocity_mps`
- `azimuth_deg`
- `elevation_deg`
- `x_m`
- `y_m`
- `z_m`

当前解析假设速度和角度字段采用 15-bit 偏移码：

```text
real = (raw15 - 0x4000) / 100
```

### `radar_hex_debug.py`

用于检查原始 20 字节点记录，辅助验证字段布局和不同解析方式是否合理。

## 运行环境假设

原始项目说明里的目标运行环境是：

- Ubuntu VM
- CPU-only
- 无 CUDA
- 真实雷达设备通常挂在 `/dev/ttyACM0`

当前这个 Windows 工作区更适合作为开发镜像使用。真正的雷达联调和采集验证，仍然建议在 Ubuntu VM 上进行。

## 当前运行时输出

临时采集输出会保存到：

- `runtime/radar_latest.bin`
- `runtime/radar_latest.jsonl`
- `runtime/radar_latest.json`

带标签采集输出会保存到：

- `runtime/radar_records/<label>/<label>_<timestamp>.bin`
- `runtime/radar_records/<label>/<label>_<timestamp>.jsonl`
- `runtime/radar_records/<label>/<label>_<timestamp>.meta.json`

## 近期建议路线

1. 保持硬件相关解析逻辑继续集中在 `radar_hex_reader_v2.py`。
2. 在 Ubuntu VM 上对新补齐的雷达接口做真实设备验证。
3. 增加点云样本特征提取脚本。
4. 基于采集结果补轻量分类模型与预测接口。

## 开发注意事项

- 不要提交运行期采集数据。
- 不要提交虚拟环境、数据集和模型权重。
- 不要默认假设当前仓库包含完整 MITO 源码。
- `MITO_77G_Codex_Dev_Guide.md` 更适合作为背景说明和目标说明，实际行为请以代码为准。
