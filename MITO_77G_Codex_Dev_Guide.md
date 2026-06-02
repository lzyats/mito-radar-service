# MITO + 77G 雷达点云项目开发说明（Codex 接入版）

> 项目目录：`/www/wwwroot/MITO/MITO_Codebase`  
> 运行环境：Ubuntu VM，CPU-only，无 GPU/CUDA  
> 当前目标：先完成 **77G 雷达点云采集 API + 文件存储**，方便采集训练样本；后续再做点云分类模型。  
> 注意：当前硬件实时数据是 **77G 雷达点云数据**，不是 MITO 官方数据格式，不能直接使用 MITO 的 `final_weights.h5` 识别物品。

---

## 1. 当前项目总体状态

### 1.1 已完成

当前已经完成以下工作：

```text
MITO_Codebase 仓库拉取               OK
Python 3.10.12                       OK
CPU-only 虚拟环境 mmwave_venv         OK
PyTorch CPU 2.4.1+cpu                OK
CUDA / nvcc / GPU                    不使用
MITO_Dataset                         已下载
MITO 分类器权重 final_weights.h5      已下载
MITO test_classifier.py              已跑通
MITO FastAPI 初始接口                 已跑通
77G 雷达 CH343 USB 串口               已识别
77G 雷达固件                          3.5G_20fps_64pc_hex
雷达启动命令                          scan start -1 stream_on
雷达停止命令                          scan stop
HEX 点云协议解析                      已基本跑通
点云 JSONL / BIN 文件保存             OK
```

MITO 官方测试结果曾成功跑出：

```text
test_all acc:  0.8529
test_los acc:  0.8889
test_nlos acc: 0.8125
```

77G 雷达点云采集已经成功输出：

```text
frames ≈ 200
non_empty_frames 可根据目标变化
空场景 point_count 基本为 0
有小物体时 point_count 明显增加
```

---

## 2. 项目目录结构

当前重要路径如下：

```text
/www/wwwroot/MITO/MITO_Codebase/
├── README.md
├── setup.py
├── requirements.txt
├── requirements_cpu.txt                 # CPU-only 依赖文件，后续建议保留
├── mmwave_venv/                         # Python 虚拟环境，不提交 Git
├── MITO_Dataset/                        # MITO 官方数据集，不提交 Git
├── pretrained_weights.zip               # 权重压缩包，不提交 Git
├── src/
│   ├── classification/
│   │   ├── test_classifier.py
│   │   └── checkpoints/                 # MITO 权重目录，不提交 Git
│   ├── simulation/
│   │   └── cpp/
│   │       └── simulation.cpython-310-x86_64-linux-gnu.so
│   ├── data_processing/
│   │   └── cpp/
│   │       └── imaging.cpython-310-x86_64-linux-gnu.so
│   └── service/
│       └── app.py                       # FastAPI 服务入口
├── radar_capture.py                     # 雷达原始数据采集脚本
├── radar_hex_debug.py                   # HEX 字段调试脚本
├── radar_hex_reader_v2.py               # 当前正式雷达 HEX 解析脚本
├── runtime/                             # 运行时数据，不提交 Git
│   ├── radar_latest.bin
│   ├── radar_latest.jsonl
│   ├── radar_latest.json
│   ├── jobs/
│   └── radar_records/
│       ├── empty/
│       ├── udisk/
│       ├── box/
│       └── small_object/
└── AGENTS.md                            # 建议新增，给 Codex 的项目说明
```

---

## 3. 部署过程回顾

### 3.1 拉取仓库

仓库源：

```text
https://github.com/signalkinetics/MITO_Codebase.git
```

部署目录：

```bash
mkdir -p /www/wwwroot/MITO
cd /www/wwwroot/MITO
git clone https://github.com/signalkinetics/MITO_Codebase.git
cd /www/wwwroot/MITO/MITO_Codebase
```

---

### 3.2 安装系统依赖

```bash
sudo apt update
sudo apt install -y \
  build-essential make gcc g++ \
  python3.10 python3.10-venv python3.10-dev python3-dev \
  libboost-system-dev libboost-thread-dev \
  git git-lfs wget curl unzip
```

确认：

```bash
python3.10 -V
python3-config --extension-suffix
```

如果没有 `python3-config`，但有 `python3.10-config`：

```bash
sudo ln -sf /usr/bin/python3.10-config /usr/local/bin/python3-config
```

---

### 3.3 创建 CPU-only 虚拟环境

```bash
cd /www/wwwroot/MITO/MITO_Codebase

python3.10 -m venv mmwave_venv
source mmwave_venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
```

---

### 3.4 修改 MITO 参数为 CPU-only

文件：

```text
src/utils/params.json
```

关键配置：

```json
{
  "processing": {
    "use_cuda": false,
    "use_simulation": false,
    "use_segmentation": false
  }
}
```

曾使用命令：

```bash
python - <<'PY'
import json
from pathlib import Path

p = Path("src/utils/params.json")
data = json.loads(p.read_text())

data["processing"]["use_cuda"] = False
data["processing"]["use_simulation"] = False
data["processing"]["use_segmentation"] = False

p.write_text(json.dumps(data, indent=4))
print(json.dumps(data["processing"], indent=4))
PY
```

---

### 3.5 创建 CPU-only requirements

原始 `requirements.txt` 里包含：

```text
pycuda==2024.1
torch
torchvision==0.19.1
```

当前 VM 没有 GPU / CUDA / nvcc，所以不要直接安装原始 requirements。

创建 CPU 版本：

```bash
grep -v -E '^(pycuda==|torch$|torchvision==)' requirements.txt > requirements_cpu.txt
```

安装 CPU PyTorch：

```bash
pip install --index-url https://download.pytorch.org/whl/cpu \
  torch==2.4.1 torchvision==0.19.1
```

安装其他依赖：

```bash
pip install -r requirements_cpu.txt
pip install opencv-python-headless==4.8.1.78
pip install numpy==1.24.3
```

验证：

```bash
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.cuda.is_available())
PY
```

期望：

```text
torch: 2.4.1+cpu
cuda: False
```

---

### 3.6 编译 C++ 扩展

```bash
cd /www/wwwroot/MITO/MITO_Codebase
source mmwave_venv/bin/activate

make -C src/simulation/cpp
make -C src/data_processing/cpp
```

确认 `.so`：

```bash
find src/simulation/cpp -name "*.so" -o -name "*.cpython*"
find src/data_processing/cpp -name "*.so" -o -name "*.cpython*"
```

期望：

```text
src/simulation/cpp/simulation.cpython-310-x86_64-linux-gnu.so
src/data_processing/cpp/imaging.cpython-310-x86_64-linux-gnu.so
```

测试 import：

```bash
python - <<'PY'
import sys

sys.path.append("src/simulation/cpp")
import simulation
print("simulation import OK")

sys.path.append("src/data_processing/cpp")
import imaging
print("imaging import OK")
PY
```

---

### 3.7 下载 MITO_Dataset

由于服务器无法稳定访问 `huggingface.co`，最终使用了 `hfd.sh` / 镜像方式下载。

最终数据集路径：

```text
/www/wwwroot/MITO/MITO_Codebase/MITO_Dataset
```

验证：

```bash
ls -lah MITO_Dataset
du -sh MITO_Dataset
```

---

### 3.8 下载 MITO 分类器权重

Google Drive 文件名原始为：

```text
MITO_Classifier_Weights.zip
```

上传到服务器后改名：

```text
/www/wwwroot/MITO/MITO_Codebase/pretrained_weights.zip
```

解压：

```bash
mkdir -p src/classification/checkpoints
unzip -o pretrained_weights.zip -d src/classification/checkpoints
```

最终路径：

```text
src/classification/checkpoints/1103c_final_all/models/final_weights.h5
```

验证：

```bash
find src/classification/checkpoints -name "final_weights.h5" -print
```

---

### 3.9 测试 MITO 分类器

```bash
cd /www/wwwroot/MITO/MITO_Codebase/src/classification
source ../../mmwave_venv/bin/activate

python3 test_classifier.py --use_cpu True
```

成功结果：

```text
test_all acc:  0.8529
test_los acc:  0.8889
test_nlos acc: 0.8125
```

---

## 4. 77G 雷达硬件接入说明

### 4.1 硬件状态

当前使用：

```text
77G 雷达模块
CH343 USB 串口板
Ubuntu VM
串口设备：/dev/ttyACM0
Windows COM 口：COM6
固件：SDK示例点云固件/3.5G_20fps_64pc_hex
```

Windows GUI 已验证：

```text
PCGUI 能显示点云
硬件正常
固件正常
串口正常
```

---

### 4.2 USB 串口识别

Ubuntu 中：

```bash
lsusb
ls /dev/ttyACM* 2>/dev/null
ls /dev/ttyUSB* 2>/dev/null
```

当前识别结果：

```text
ID 1a86:55d3 QinHeng Electronics USB Single Serial
/dev/ttyACM0
```

---

### 4.3 固件烧录

使用 Windows 的烧录工具，COM 口使用：

```text
COM6
```

烧录模式：

```text
SOP2 → 3V3
```

烧录完成后必须：

```text
拔 USB 断电
断开 SOP2 和 3V3
SOP2 悬空
重新上电
```

正常工作模式：

```text
SOP2 悬空
```

VIO 建议：

```text
VIO → 3V3
雷达 VCC 仍然使用 5V
```

---

### 4.4 雷达命令

当前已确认命令：

```text
启动：scan start -1 stream_on
停止：scan stop
```

命令发现过程：

```text
help 命令输出中显示 scan 指令
scan start -1 stream_on 可以触发大量 HEX 点云输出
```

---

## 5. 点云解析说明

当前正式解析脚本：

```text
radar_hex_reader_v2.py
```

主要功能：

```text
打开 /dev/ttyACM0
发送 scan start -1 stream_on
读取 HEX 原始数据
解析帧头
解析点云包
解析 range / velocity / azimuth / elevation / snr
转换 x/y/z
保存 .bin 和 .jsonl
发送 scan stop
```

---

### 5.1 HEX 包头

实测数据中出现：

```text
dcffeeff
d3ffeeff
cbfeddff
c4feddff
```

含义：

```text
dcffeeff  = 0xFFEEFFDC 小端
d3ffeeff  = 0xFFEEFFD3 小端
cbfeddff  = 0xFFDDFECB 小端
c4feddff  = 0xFFDDFEC4 小端
```

---

### 5.2 点字段解析校准

初版误把速度/角度按二补码解析，得到异常值：

```text
vel=-163.84m/s
azi=160°
ele=-130°
```

后来通过 raw 20 字节诊断确认：

```text
速度 / 方位角 / 俯仰角是 15bit 偏移码
0x4000 表示 0
真实值 = (raw15 - 0x4000) / 100
```

修正后输出正常：

```text
range=0.45m~0.65m
velocity≈0
azimuth 在合理角度范围
elevation 在合理角度范围
x/y/z 正常
```

---

### 5.3 点云坐标转换

公式：

```text
X = range * cos(elevation) * sin(azimuth)
Y = range * cos(elevation) * cos(azimuth)
Z = range * sin(elevation)
```

当前 `radar_hex_reader_v2.py` 已实现。

---

## 6. 当前 FastAPI 基础版

当前目标不是完整业务系统，而是先方便采集训练数据。

基础版 API 文件：

```text
src/service/app.py
```

依赖：

```bash
pip install fastapi "uvicorn[standard]"
pip install pyserial
```

启动：

```bash
cd /www/wwwroot/MITO/MITO_Codebase/src
source ../mmwave_venv/bin/activate

uvicorn service.app:app --host 0.0.0.0 --port 8000
```

---

### 6.1 API 路由

```text
GET  /
GET  /radar/health
POST /radar/capture
GET  /radar/latest
POST /radar/record?label=empty
GET  /radar/records
GET  /radar/labels
```

---

### 6.2 雷达健康检查

```bash
curl http://127.0.0.1:8000/radar/health
```

期望：

```json
{
  "ok": true,
  "port": "/dev/ttyACM0",
  "port_exists": true,
  "reader_exists": true,
  "start_command": "scan start -1 stream_on",
  "stop_command": "scan stop"
}
```

---

### 6.3 临时采集

```bash
curl -X POST "http://127.0.0.1:8000/radar/capture?seconds=3&min_range=0.2&max_range=3.0"
```

输出包括：

```text
summary
sample_points
bin_path
jsonl_path
```

保存路径：

```text
runtime/radar_latest.bin
runtime/radar_latest.jsonl
runtime/radar_latest.json
```

查看最近一次：

```bash
curl http://127.0.0.1:8000/radar/latest
```

---

### 6.4 采集训练样本

空场景：

```bash
curl -X POST "http://127.0.0.1:8000/radar/record?label=empty&seconds=8&min_range=0.2&max_range=3.0"
```

U 盘：

```bash
curl -X POST "http://127.0.0.1:8000/radar/record?label=udisk&seconds=8&min_range=0.2&max_range=3.0"
```

盒子：

```bash
curl -X POST "http://127.0.0.1:8000/radar/record?label=box&seconds=8&min_range=0.2&max_range=3.0"
```

小物体：

```bash
curl -X POST "http://127.0.0.1:8000/radar/record?label=small_object&seconds=8&min_range=0.2&max_range=3.0"
```

---

### 6.5 样本保存结构

每次 `/radar/record` 保存：

```text
runtime/radar_records/<label>/<label>_<timestamp>.bin
runtime/radar_records/<label>/<label>_<timestamp>.jsonl
runtime/radar_records/<label>/<label>_<timestamp>.meta.json
```

示例：

```text
runtime/radar_records/udisk/udisk_20260528_083000.bin
runtime/radar_records/udisk/udisk_20260528_083000.jsonl
runtime/radar_records/udisk/udisk_20260528_083000.meta.json
```

---

### 6.6 查看样本数量

```bash
curl http://127.0.0.1:8000/radar/labels
```

查看采集记录：

```bash
curl http://127.0.0.1:8000/radar/records
```

---

## 7. 当前数据性质

当前从硬件读出的数据是：

```text
77G 雷达点云数据
```

不是 MITO 官方数据。

点云字段：

```text
range_m
velocity_mps
azimuth_deg
elevation_deg
snr
x_m
y_m
z_m
```

MITO 官方数据是：

```text
MITO_Dataset 中的 mmWave / SAR 图像数据
processed_image.pkl
mask
```

当前点云数据不能直接喂给 MITO 的 `final_weights.h5`。

---

## 8. 后期和 MITO 的关系

### 8.1 当前阶段

当前阶段 MITO 主要作为：

```text
环境验证
代码参考
分类训练流程参考
```

实时硬件数据走的是独立点云链路。

---

### 8.2 后期路线 A：推荐

基于当前 77G 点云重新训练模型：

```text
runtime/radar_records/*
    ↓
提取点云统计特征
    ↓
训练 RandomForest / SVM / MLP
    ↓
/radar/predict
```

优点：

```text
适合当前硬件
CPU 可训练
开发快
容易调试
```

---

### 8.3 后期路线 B：MITO-like 转换

后期可做转换：

```text
点云 JSONL
    ↓
投影成 range-azimuth / xy / xz 图像
    ↓
生成 MITO-like 数据集
    ↓
重新训练 MITO 风格模型
```

不建议当前阶段做，因为 MITO 预训练权重不能直接识别当前硬件点云。

---

## 9. 训练数据采集建议

每个类别建议至少：

```text
20~50 组样本
每组 5~10 秒
```

优先标签：

```text
empty
udisk
box
can
phone
small_object
```

每个物体要换姿态：

```text
正前方 0.4m
正前方 0.6m
正前方 0.8m
左偏
右偏
横放
竖放
```

空场景也要采不同环境：

```text
桌面空
地面空
有背景墙
不同距离
```

---

## 10. Git / Codex 接入建议

Codex 无法直接访问 Ubuntu VM 上的真实雷达串口 `/dev/ttyACM0`。因此工作方式应为：

```text
Codex 修改代码
    ↓
提交到 GitHub
    ↓
Ubuntu VM git pull
    ↓
本机真实雷达测试
    ↓
把日志反馈给 Codex
```

---

### 10.1 建议提交的文件

```text
src/service/app.py
radar_hex_reader_v2.py
radar_capture.py
radar_hex_debug.py
requirements_cpu.txt
AGENTS.md
.gitignore
```

---

### 10.2 不要提交的文件

```text
mmwave_venv/
MITO_Dataset/
runtime/
pretrained_weights.zip
src/classification/checkpoints/
*.bin
*.jsonl
*.log
```

---

### 10.3 .gitignore 建议

```gitignore
# virtual env
mmwave_venv/
__pycache__/
*.pyc

# MITO data and weights
MITO_Dataset/
pretrained_weights.zip
src/classification/checkpoints/

# runtime radar data
runtime/
*.bin
*.jsonl
*.log

# OS/editor
.DS_Store
.vscode/
.idea/
```

---

## 11. AGENTS.md 建议内容

建议在仓库根目录增加 `AGENTS.md`：

```markdown
# AGENTS.md

This project combines the MITO research codebase with a local 77G radar point-cloud capture service.

## Environment

Production/test path:

/www/wwwroot/MITO/MITO_Codebase

Python virtual environment:

mmwave_venv

This project runs CPU-only. Do not assume CUDA, nvcc, or GPU is available.

## Hardware

The physical radar is attached only on the user's Ubuntu VM:

/dev/ttyACM0

Firmware:

3.5G_20fps_64pc_hex

Start command:

scan start -1 stream_on

Stop command:

scan stop

Codex cannot directly test radar capture because /dev/ttyACM0 exists only on the user's VM.

## Important files

Radar parser:

radar_hex_reader_v2.py

FastAPI service:

src/service/app.py

Runtime training data:

runtime/radar_records/

Do not commit runtime data.

## Run service

cd /www/wwwroot/MITO/MITO_Codebase/src
source ../mmwave_venv/bin/activate
uvicorn service.app:app --host 0.0.0.0 --port 8000

## Basic syntax test

python -m py_compile radar_hex_reader_v2.py src/service/app.py

## API endpoints

GET /radar/health
POST /radar/capture
GET /radar/latest
POST /radar/record?label=empty
GET /radar/records
GET /radar/labels

## Development rule

Keep hardware-specific operations isolated in radar_hex_reader_v2.py.
Keep API logic in src/service/app.py.
Do not modify MITO original training code unless explicitly requested.
```

---

## 12. 常用命令

### 启动 API

```bash
cd /www/wwwroot/MITO/MITO_Codebase/src
source ../mmwave_venv/bin/activate
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

### 停止 API

```bash
sudo pkill -f "uvicorn service.app:app" || true
```

### 健康检查

```bash
curl http://127.0.0.1:8000/radar/health
```

### 采集空场景

```bash
curl -X POST "http://127.0.0.1:8000/radar/record?label=empty&seconds=8&min_range=0.2&max_range=3.0"
```

### 采集 U 盘

```bash
curl -X POST "http://127.0.0.1:8000/radar/record?label=udisk&seconds=8&min_range=0.2&max_range=3.0"
```

### 查看标签

```bash
curl http://127.0.0.1:8000/radar/labels
```

### 检查语法

```bash
cd /www/wwwroot/MITO/MITO_Codebase
source mmwave_venv/bin/activate

python -m py_compile radar_hex_reader_v2.py src/service/app.py
```

---

## 13. 下一阶段计划

### 阶段 1：采集数据

目标：

```text
empty 20~50 组
udisk 20~50 组
box 20~50 组
can 20~50 组
phone 20~50 组
```

---

### 阶段 2：特征提取

新增脚本：

```text
extract_radar_features.py
```

输出每组样本的特征：

```text
valid_point_count
non_empty_frame_ratio
avg_range_m
min_range_m
max_snr
avg_snr
x/y/z bbox
velocity mean/std
range histogram
azimuth histogram
elevation histogram
```

---

### 阶段 3：训练分类模型

新增脚本：

```text
train_radar_classifier.py
```

第一版模型：

```text
RandomForestClassifier
```

输出：

```text
models/radar_classifier_v1.pkl
models/radar_classifier_v1.metrics.json
```

---

### 阶段 4：预测接口

新增接口：

```text
POST /radar/predict?seconds=3
```

返回：

```json
{
  "label": "udisk",
  "confidence": 0.86,
  "summary": {}
}
```

---

### 阶段 5：系统化

后期再引入：

```text
MySQL
Go 管理后台
模型版本管理
样本审核
批量采集任务
```

---

## 14. 当前结论

当前项目已从 MITO 官方数据集测试，扩展到本地 77G 雷达点云采集。

现在应优先完成：

```text
FastAPI + 文件存储
带标签点云样本采集
样本数量统计
训练数据规范化
```

暂时不要把点云强行接入 MITO 官方 `final_weights.h5`。后续应先基于点云训练自己的轻量分类模型，再考虑 MITO-like 转换。
