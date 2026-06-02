#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_capture.py
读取 77G 雷达 HEX 点云串口数据。

已验证启动命令:
    scan start -1 stream_on

用法:
    python radar_capture.py --port /dev/ttyACM0 --seconds 10
    python radar_capture.py --port /dev/ttyACM0 --baud 3000000 --seconds 30 --out runtime/radar_capture

输出:
    runtime/radar_capture_YYYYmmdd_HHMMSS.bin
    runtime/radar_capture_YYYYmmdd_HHMMSS.hex.txt
"""

from __future__ import annotations

import argparse
import binascii
import time
from datetime import datetime
from pathlib import Path

import serial


START_CMD = b"scan start -1 stream_on\r\n"
STOP_CMD = b"scan stop\r\n"

# 从你读取到的数据看，帧头以小端形式出现：dc ff ee ff
MAGIC = bytes.fromhex("dcffeeff")


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def capture(port: str, baud: int, seconds: int, out_prefix: str, send_stop: bool = True) -> None:
    out_prefix_path = Path(out_prefix)
    out_prefix_path.parent.mkdir(parents=True, exist_ok=True)

    bin_path = out_prefix_path.with_suffix(".bin")
    hex_path = out_prefix_path.with_suffix(".hex.txt")

    print(f"[OPEN] {port} @ {baud}")
    ser = serial.Serial(port, baud, timeout=0.2)

    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        print(f"[SEND] {START_CMD!r}")
        ser.write(START_CMD)
        ser.flush()

        print(f"[READ] {seconds}s ...")
        start_time = time.time()
        total = 0
        chunks: list[bytes] = []

        while time.time() - start_time < seconds:
            data = ser.read(8192)
            if not data:
                continue
            chunks.append(data)
            total += len(data)

            # 实时打印少量信息，避免刷屏
            if total <= 65536 or total % 262144 < len(data):
                sample = binascii.hexlify(data[:80]).decode()
                print(f"[DATA] chunk={len(data)} total={total} sample={sample}")

        raw = b"".join(chunks)
        print(f"[DONE] total bytes: {len(raw)}")

        bin_path.write_bytes(raw)
        hex_path.write_text(binascii.hexlify(raw).decode(), encoding="utf-8")

        print(f"[SAVE] raw: {bin_path}")
        print(f"[SAVE] hex: {hex_path}")

        # 简单统计帧头数量
        magic_count = raw.count(MAGIC)
        print(f"[INFO] magic dcffeeff count: {magic_count}")

        # 打印前几个帧头位置，便于后续解析
        pos = 0
        positions = []
        while len(positions) < 10:
            idx = raw.find(MAGIC, pos)
            if idx < 0:
                break
            positions.append(idx)
            pos = idx + 1

        print(f"[INFO] first magic positions: {positions}")

        if positions:
            for i, idx in enumerate(positions[:3]):
                frame_sample = raw[idx:idx + 160]
                print(f"[FRAME SAMPLE {i}] offset={idx}")
                print(binascii.hexlify(frame_sample).decode())

    finally:
        if send_stop:
            try:
                print(f"[SEND] {STOP_CMD!r}")
                ser.write(STOP_CMD)
                ser.flush()
                time.sleep(0.2)
            except Exception as exc:
                print(f"[WARN] failed to send stop: {exc}")

        ser.close()
        print("[CLOSE]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture raw HEX point cloud data from 77G radar UART.")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=3000000, help="Baud rate")
    parser.add_argument("--seconds", type=int, default=10, help="Capture seconds")
    parser.add_argument(
        "--out",
        default="runtime/radar_capture",
        help="Output prefix. Timestamp will be appended automatically.",
    )
    parser.add_argument("--no-stop", action="store_true", help="Do not send scan stop when finished")
    args = parser.parse_args()

    prefix = f"{args.out}_{now_tag()}"
    capture(
        port=args.port,
        baud=args.baud,
        seconds=args.seconds,
        out_prefix=prefix,
        send_stop=not args.no_stop,
    )


if __name__ == "__main__":
    main()
