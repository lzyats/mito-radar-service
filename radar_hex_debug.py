#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_hex_debug.py
用于诊断 77G 雷达 HEX 点云协议字段位置。

用法:
    python radar_hex_debug.py --input runtime/radar_live.bin --frames 5 --points 10

它会输出:
- 帧头位置
- 每帧 point_count
- 每个点的原始 20 字节
- uint16 / int16 / uint32 拆分
- 多种候选解析方式

目的:
当前已经确认帧解析成功，但速度/角度解析明显异常。
此脚本用于对照 Windows GUI 或协议文档，确定正确字段布局。
"""

from __future__ import annotations

import argparse
import struct
import math
from pathlib import Path


FRAME_HEAD = bytes.fromhex("dcffeeff")
FRAME_END = bytes.fromhex("d3ffeeff")
POINT_HEAD = bytes.fromhex("cbfeddff")
POINT_END = bytes.fromhex("c4feddff")

POINT_RECORD_SIZE = 20


def i16(x: int) -> int:
    return x - 65536 if x >= 32768 else x


def sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    mask = (1 << bits) - 1
    value &= mask
    return value - (1 << bits) if value & sign_bit else value


def parse_frame_headers(raw: bytes):
    pos = 0
    while True:
        start = raw.find(FRAME_HEAD, pos)
        if start < 0:
            break
        if len(raw) < start + 28:
            break
        if raw[start + 24:start + 28] != FRAME_END:
            pos = start + 1
            continue

        w1 = struct.unpack_from("<I", raw, start + 4)[0]
        frame_id = struct.unpack_from("<I", raw, start + 8)[0]
        packed = struct.unpack_from("<I", raw, start + 12)[0]
        w4 = struct.unpack_from("<I", raw, start + 16)[0]
        checksum = struct.unpack_from("<I", raw, start + 20)[0]

        point_count = packed & 0x03FF
        track_count = (packed >> 10) & 0x03FF
        raw_count = (packed >> 20) & 0x03FF

        yield {
            "offset": start,
            "w1": w1,
            "frame_id": frame_id,
            "packed": packed,
            "point_count": point_count,
            "track_count": track_count,
            "raw_count": raw_count,
            "w4": w4,
            "checksum": checksum,
            "point_data_offset": start + 28,
        }

        # 粗略跳过本帧
        cur = start + 28
        if point_count > 0 and raw[cur:cur+4] == POINT_HEAD:
            cur += 4 + point_count * POINT_RECORD_SIZE + 8
        pos = max(cur, start + 1)


def print_record_candidates(rec: bytes):
    u16 = struct.unpack("<10H", rec)
    s16 = tuple(i16(x) for x in u16)
    u32 = struct.unpack("<5I", rec)
    s32 = struct.unpack("<5i", rec)

    print("    raw20 :", rec.hex())
    print("    u16   :", " ".join(f"{x:5d}" for x in u16))
    print("    s16   :", " ".join(f"{x:6d}" for x in s16))
    print("    u32   :", " ".join(f"0x{x:08x}" for x in u32))

    # 候选 1：当前脚本假设
    word0, range100, word2, word3, reserved = u32
    idx_a = word0 & 0x03FF
    snr_a = (word0 >> 10) & 0x7FFF
    vel_a = sign_extend(word2 & 0x7FFF, 15) / 100.0
    azi_a = sign_extend((word2 >> 15) & 0x7FFF, 15) / 100.0
    ele_a = sign_extend(word3 & 0x7FFF, 15) / 100.0
    print(f"    candA packed32: idx={idx_a} snr={snr_a} range={range100/100:.2f} vel={vel_a:.2f} azi={azi_a:.2f} ele={ele_a:.2f}")

    # 候选 2：按 int16 顺序理解，寻找 range=第3个u16, vel=第4个s16, azi=第5个s16, ele=第6个s16
    # 很多嵌入式协议会采用 16-bit 字段，这里列出所有 /100 后的候选，便于肉眼对照。
    scaled = [x / 100.0 for x in s16]
    print("    s16/100:", " ".join(f"{x:8.2f}" for x in scaled))

    # 候选 3：把 u16 当作无符号 /100，看哪些像距离/SNR
    uscaled = [x / 100.0 for x in u16]
    print("    u16/100:", " ".join(f"{x:8.2f}" for x in uscaled))

    # 候选 4：某些角度可能是 int16 的补码，但出现 -163.84 通常说明 0xC000 是标志位/字段边界，需要看二进制
    print("    u16hex :", " ".join(f"{x:04x}" for x in u16))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--frames", type=int, default=5)
    ap.add_argument("--points", type=int, default=10)
    args = ap.parse_args()

    raw = Path(args.input).read_bytes()
    print(f"[LOAD] {args.input} bytes={len(raw)}")

    shown = 0
    for fh in parse_frame_headers(raw):
        if shown >= args.frames:
            break
        print("\n" + "=" * 80)
        print(
            f"[FRAME] offset={fh['offset']} frame_id={fh['frame_id']} "
            f"point_count={fh['point_count']} track={fh['track_count']} raw={fh['raw_count']} "
            f"packed=0x{fh['packed']:08x}"
        )

        cur = fh["point_data_offset"]
        if fh["point_count"] <= 0:
            print("  empty frame")
            shown += 1
            continue

        if raw[cur:cur+4] != POINT_HEAD:
            print("  no POINT_HEAD at expected position")
            print("  next bytes:", raw[cur:cur+32].hex())
            shown += 1
            continue

        print(f"  POINT_HEAD at {cur}: {raw[cur:cur+4].hex()}")
        cur += 4

        for i in range(min(fh["point_count"], args.points)):
            rec = raw[cur + i * POINT_RECORD_SIZE:cur + (i + 1) * POINT_RECORD_SIZE]
            print(f"\n  [POINT {i}]")
            print_record_candidates(rec)

        shown += 1


if __name__ == "__main__":
    main()
