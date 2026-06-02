# AGENTS.md

这是一个围绕 77G 雷达服务整理出来的精简接管仓库，和 MITO 项目有关，但不是完整的 MITO 上游代码库。

## 项目目标

这个仓库主要用于：

- 维护和扩展雷达点云采集流程
- 持续完善 FastAPI 服务，支持样本采集和保存
- 保留 MITO 分类测试接口作为兼容能力，而不是当前主线

不要默认把这个仓库当成完整的 `MITO_Codebase`。

## 当前代码现状

当前服务已经实现这些接口：

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

## 关键文件

- `src/service/app.py`：当前 FastAPI 服务
- `radar_capture.py`：原始串口采集
- `radar_hex_reader_v2.py`：主用雷达帧/点解析脚本
- `radar_hex_debug.py`：字段布局调试脚本
- `MITO_77G_Codex_Dev_Guide.md`：历史背景、部署过程和路线说明

## 环境假设

原始运行环境来自项目说明：

- Ubuntu VM
- CPU-only
- Python 虚拟环境目录为 `mmwave_venv`
- 真实雷达串口设备通常为 `/dev/ttyACM0`

当前这个 Windows 工作区主要用于编辑、评审和准备提交。涉及真实硬件的验证，通常还是要回到 Ubuntu VM 完成。

## 开发规则

- 硬件串口、协议解析相关逻辑尽量集中在 `radar_hex_reader_v2.py`。
- API 编排和响应结构尽量集中在 `src/service/app.py`。
- 不要把点云解析逻辑零散复制到 Web 层。
- 除非任务明确要求，否则不要主动改 MITO 原始训练逻辑。
- 运行期数据、数据集、模型权重、虚拟环境都视为外部状态，不视为源码。

## Git 约束

这些路径和文件类型应该继续避免提交：

- `mmwave_venv/`
- `MITO_Dataset/`
- `runtime/`
- `src/classification/checkpoints/`
- `*.bin`
- `*.jsonl`
- `*.log`

## 推荐下一步

1. 在 Ubuntu VM 上对当前雷达接口做真实硬件验证。
2. 补齐下游训练需要的运行时元数据规范。
3. 增加样本特征提取脚本。
4. 增加适合 CPU 的轻量分类模型。

## 验证建议

对于当前仓库里的代码改动，至少执行：

```bash
python -m py_compile radar_hex_reader_v2.py src/service/app.py
```

涉及雷达行为时，默认按两步走：

1. 在这里改代码和评审
2. 回 Ubuntu VM 连真实设备验证
