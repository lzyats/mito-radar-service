#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_hex_reader_v2.py
77G 雷达 HEX 点云解析脚本 v2。

修正点：
- 帧头/点云包头解析沿用 v1。
- 速度、方位角、俯仰角字段改为“15bit 偏移码”解析：
    real = (raw15 - 0x4000) / 100
  这是根据实测数据校准得到的：
    0x4000 附近代表 0，而不是二补码的 -163.84。
- 距离字段仍然按 uint32 / 100 解析。
- SNR 保留原始相对值，协议说明它不是绝对值。

用法：
    python radar_hex_reader_v2.py live --port /dev/ttyACM0 --seconds 10
    python radar_hex_reader_v2.py live --port /dev/ttyACM0 --seconds 10 --jsonl runtime/radar_points_v2.jsonl
    python radar_hex_reader_v2.py parse --input runtime/radar_live.bin --jsonl runtime/radar_points_v2.jsonl
"""

from __future__ import annotations

import argparse
import binascii
import json
import math
import struct
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import serial


FRAME_HEAD = bytes.fromhex("dcffeeff")   # 0xFFEEFFDC little-endian
FRAME_END = bytes.fromhex("d3ffeeff")    # 0xFFEEFFD3 little-endian
POINT_HEAD = bytes.fromhex("cbfeddff")   # 0xFFDDFECB little-endian
POINT_END = bytes.fromhex("c4feddff")    # 0xFFDDFEC4 little-endian
TAIL_1 = bytes.fromhex("bafdccff")
TAIL_2 = bytes.fromhex("b5fdccff")

START_CMD = b"scan start -1 stream_on\r\n"
STOP_CMD = b"scan stop\r\n"

POINT_RECORD_SIZE = 20
SIGNED15_BIAS = 0x4000


@dataclass
class RadarPoint:
    frame_id: int
    point_index: int
    snr: int
    range_m: float
    velocity_mps: float
    azimuth_deg: float
    elevation_deg: float
    x_m: float
    y_m: float
    z_m: float
    reserved: int


@dataclass
class RadarFrame:
    offset: int
    frame_id: int
    point_count: int
    track_output_number: int
    raw_number: int
    checksum: int
    points: list[RadarPoint]


def decode_signed15_offset(raw15: int) -> float:
    """
    实测固件中，速度/角度字段的 15bit 值不是常规二补码，
    而是以 0x4000 为 0 点的偏移码。
    """
    return (raw15 - SIGNED15_BIAS) / 100.0


def xyz_from_spherical(range_m: float, azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    azi = math.radians(azimuth_deg)
    ele = math.radians(elevation_deg)
    x = range_m * math.cos(ele) * math.sin(azi)
    y = range_m * math.cos(ele) * math.cos(azi)
    z = range_m * math.sin(ele)
    return x, y, z


def parse_point(record: bytes, frame_id: int) -> RadarPoint:
    if len(record) != POINT_RECORD_SIZE:
        raise ValueError(f"point record length must be {POINT_RECORD_SIZE}, got {len(record)}")

    word0, range100, word2, word3, reserved = struct.unpack("<IIIII", record)

    point_index = word0 & 0x03FF
    snr = (word0 >> 10) & 0x7FFF

    range_m = range100 / 100.0

    velocity_raw = word2 & 0x7FFF
    azimuth_raw = (word2 >> 15) & 0x7FFF
    elevation_raw = word3 & 0x7FFF

    velocity_mps = decode_signed15_offset(velocity_raw)
    azimuth_deg = decode_signed15_offset(azimuth_raw)
    elevation_deg = decode_signed15_offset(elevation_raw)

    x, y, z = xyz_from_spherical(range_m, azimuth_deg, elevation_deg)

    return RadarPoint(
        frame_id=frame_id,
        point_index=point_index,
        snr=snr,
        range_m=range_m,
        velocity_mps=velocity_mps,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        x_m=x,
        y_m=y,
        z_m=z,
        reserved=reserved,
    )


def parse_frames(raw: bytes, max_frames: int | None = None) -> list[RadarFrame]:
    frames: list[RadarFrame] = []
    pos = 0

    while True:
        start = raw.find(FRAME_HEAD, pos)
        if start < 0:
            break

        header_end = start + 28
        if len(raw) < header_end:
            break

        if raw[start + 24:start + 28] != FRAME_END:
            pos = start + 1
            continue

        frame_id = struct.unpack_from("<I", raw, start + 8)[0]
        packed = struct.unpack_from("<I", raw, start + 12)[0]
        checksum = struct.unpack_from("<I", raw, start + 20)[0]

        point_count = packed & 0x03FF
        track_output_number = (packed >> 10) & 0x03FF
        raw_number = (packed >> 20) & 0x03FF

        cur = header_end
        points: list[RadarPoint] = []

        if point_count > 0:
            if raw[cur:cur + 4] != POINT_HEAD:
                pos = start + 1
                continue
            cur += 4

            need = point_count * POINT_RECORD_SIZE
            if len(raw) < cur + need + 8:
                break

            for i in range(point_count):
                record = raw[cur + i * POINT_RECORD_SIZE:cur + (i + 1) * POINT_RECORD_SIZE]
                try:
                    points.append(parse_point(record, frame_id=frame_id))
                except Exception:
                    pass

            cur += need

            # 点云包 checksum
            cur += 4

            if raw[cur:cur + 4] == POINT_END:
                cur += 4
            else:
                pos = start + 1
                continue

        if raw[cur:cur + 4] == TAIL_1:
            cur += 4
        if raw[cur:cur + 4] == TAIL_2:
            cur += 4

        frames.append(
            RadarFrame(
                offset=start,
                frame_id=frame_id,
                point_count=point_count,
                track_output_number=track_output_number,
                raw_number=raw_number,
                checksum=checksum,
                points=points,
            )
        )

        pos = cur

        if max_frames is not None and len(frames) >= max_frames:
            break

    return frames


def capture_live(port: str, baud: int, seconds: int) -> bytes:
    print(f"[OPEN] {port} @ {baud}")
    ser = serial.Serial(port, baud, timeout=0.2)
    chunks: list[bytes] = []

    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        print(f"[SEND] {START_CMD!r}")
        ser.write(START_CMD)
        ser.flush()

        start_time = time.time()
        total = 0
        print(f"[READ] {seconds}s ...")

        while time.time() - start_time < seconds:
            data = ser.read(8192)
            if data:
                chunks.append(data)
                total += len(data)
                if total <= 32768:
                    print(f"[DATA] chunk={len(data)} total={total} hex={binascii.hexlify(data[:80]).decode()}")

        print(f"[DONE] total bytes={total}")

    finally:
        try:
            print(f"[SEND] {STOP_CMD!r}")
            ser.write(STOP_CMD)
            ser.flush()
        except Exception as exc:
            print(f"[WARN] failed to stop radar: {exc}")
        ser.close()

    return b"".join(chunks)


def print_summary(frames: list[RadarFrame], limit_frames: int = 10, limit_points: int = 8, min_range: float = 0.0) -> None:
    all_points = [p for f in frames for p in f.points if p.range_m >= min_range]
    non_empty = sum(1 for f in frames if f.points)
    print(f"[SUMMARY] frames={len(frames)}, non_empty_frames={non_empty}, points={len(all_points)}")

    printed = 0
    for f in frames:
        show_points = [p for p in f.points if p.range_m >= min_range]
        if not show_points and printed >= limit_frames:
            continue

        print(
            f"\n[FRAME] offset={f.offset} frame_id={f.frame_id} "
            f"point_count={f.point_count} parsed_points={len(f.points)} "
            f"track={f.track_output_number} raw={f.raw_number}"
        )

        for p in show_points[:limit_points]:
            print(
                f"  idx={p.point_index:03d} snr={p.snr:5d} "
                f"range={p.range_m:6.2f}m vel={p.velocity_mps:7.2f}m/s "
                f"azi={p.azimuth_deg:8.2f}° ele={p.elevation_deg:8.2f}° "
                f"x={p.x_m:7.2f} y={p.y_m:7.2f} z={p.z_m:7.2f}"
            )

        printed += 1
        if printed >= limit_frames:
            break


def write_jsonl(frames: list[RadarFrame], jsonl_path: str) -> None:
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for frame in frames:
            item = asdict(frame)
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[SAVE] jsonl={path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and parse 77G radar HEX point cloud data.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    live = sub.add_parser("live", help="Capture from serial and parse")
    live.add_argument("--port", default="/dev/ttyACM0")
    live.add_argument("--baud", type=int, default=3000000)
    live.add_argument("--seconds", type=int, default=10)
    live.add_argument("--save-bin", default="")
    live.add_argument("--jsonl", default="")
    live.add_argument("--min-range", type=float, default=0.0)

    parse = sub.add_parser("parse", help="Parse existing .bin file")
    parse.add_argument("--input", required=True)
    parse.add_argument("--jsonl", default="")
    parse.add_argument("--min-range", type=float, default=0.0)

    args = parser.parse_args()

    if args.cmd == "live":
        raw = capture_live(args.port, args.baud, args.seconds)
        if args.save_bin:
            p = Path(args.save_bin)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            print(f"[SAVE] bin={p}")
    else:
        raw = Path(args.input).read_bytes()
        print(f"[LOAD] {args.input} bytes={len(raw)}")

    frames = parse_frames(raw)
    print_summary(frames, min_range=args.min_range)

    if getattr(args, "jsonl", ""):
        write_jsonl(frames, args.jsonl)


if __name__ == "__main__":
    main()
