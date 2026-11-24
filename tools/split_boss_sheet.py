"""Boss_smash.png를 몸통 / 왼팔 / 오른팔 레이어로 나눈다 (한 번 돌리는 도구).

시트: 3840×2160, 6×6칸, 칸 640×360, 36프레임. 골렘의 두 팔이 몸통과 떨어져 떠 있어서
프레임마다 연결 요소(불투명 픽셀 덩어리)로 나눌 수 있다.
  - 가장 큰 덩어리 = 몸통(다리 포함)
  - 남은 큰 덩어리 중 가장 오른쪽 = 금속 팔 (원본에서 항상 오른쪽에 가만히 있다)
  - 나머지 = 돌 팔 (내리찍기를 하는 팔)
  - 작은 부스러기는 가장 가까운 덩어리에 붙이고, 아주 작으면 버린다

부위 파괴 명세상 내려찍기는 화면 오른쪽 팔(arm_r)이므로 결과를 좌우 반전한다.
  반전 후: arm_r = 돌 팔(내려찍기), arm_l = 금속 팔.

출력 (프로젝트 폴더):
  boss_body.png, boss_arm_l.png, boss_arm_r.png — 원본과 같은 칸 배치, 좌우 반전
  boss_layers.json — 프레임별 레이어 경계 상자, 핵(붉은 빛) 위치, 발 위치 (칸 좌표, 반전 후)

사용: .venv/Scripts/python.exe tools/split_boss_sheet.py
"""

import ctypes
import json
import os
from collections import deque

import sdl2
import sdl2.sdlimage as sdlimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "Boss_smash.png")
COLUMNS, ROWS = 6, 6
CELL_W, CELL_H = 640, 360
ALPHA_MIN = 16
SPECK_MAX = 60  # 반 해상도 픽셀 수가 이보다 작으면 부스러기
DROP_MAX = 6  # 이보다 작은 부스러기는 버린다
SPECK_REACH = 10  # 부스러기가 이보다 멀면(반 해상도 px) 어느 덩어리에도 붙이지 않는다


def load_rgba(path):
    surface = sdlimage.IMG_Load(path.encode("utf-8"))
    rgba = sdl2.SDL_ConvertSurfaceFormat(surface, sdl2.SDL_PIXELFORMAT_ABGR8888, 0)
    width, height, pitch = rgba.contents.w, rgba.contents.h, rgba.contents.pitch
    data = bytearray(ctypes.string_at(rgba.contents.pixels, pitch * height))
    return data, width, height, pitch


def label_cell(data, pitch, cx, cy):
    """반 해상도(2×2 중 하나라도 불투명) 마스크에서 연결 요소를 찾는다."""
    hw, hh = CELL_W // 2, CELL_H // 2
    mask = bytearray(hw * hh)
    for y in range(hh):
        r0 = (cy + 2 * y) * pitch
        r1 = r0 + pitch
        for x in range(hw):
            o = (cx + 2 * x) * 4 + 3
            if data[r0 + o] > ALPHA_MIN or data[r0 + o + 4] > ALPHA_MIN or data[r1 + o] > ALPHA_MIN or data[r1 + o + 4] > ALPHA_MIN:
                mask[y * hw + x] = 1
    labels = [0] * (hw * hh)
    comps = []
    for start in range(hw * hh):
        if not mask[start] or labels[start]:
            continue
        lab = len(comps) + 1
        labels[start] = lab
        queue = deque([start])
        count = sx = sy = 0
        minx, miny, maxx, maxy = hw, hh, 0, 0
        while queue:
            i = queue.popleft()
            x, y = i % hw, i // hw
            count += 1; sx += x; sy += y
            minx = min(minx, x); maxx = max(maxx, x); miny = min(miny, y); maxy = max(maxy, y)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < hw and 0 <= ny < hh:
                    j = ny * hw + nx
                    if mask[j] and not labels[j]:
                        labels[j] = lab
                        queue.append(j)
        comps.append({"label": lab, "count": count, "cx": sx / count, "cy": sy / count,
                      "box": (minx, miny, maxx, maxy)})
    return labels, comps, hw


def classify(comps):
    big = sorted((c for c in comps if c["count"] >= SPECK_MAX), key=lambda c: -c["count"])
    body = big[0]
    others = big[1:]
    metal = max(others, key=lambda c: c["cx"])
    stone = max((c for c in others if c is not metal), key=lambda c: c["count"])
    role = {body["label"]: "body", metal["label"]: "metal", stone["label"]: "stone"}
    # 나머지(큰 잡티 포함)는 아래 부스러기 규칙으로 — 가까우면 붙이고 멀면 버린다
    anchors = [body, metal, stone]
    for c in comps:
        if c["label"] in role:
            continue
        if c["count"] < DROP_MAX:
            role[c["label"]] = None
            continue

        def box_gap(a):
            ax0, ay0, ax1, ay1 = a["box"]
            dx = max(ax0 - c["cx"], 0, c["cx"] - ax1)
            dy = max(ay0 - c["cy"], 0, c["cy"] - ay1)
            return (dx * dx + dy * dy) ** 0.5

        nearest = min(anchors, key=box_gap)
        # 덩어리에서 멀리 떨어진 부스러기(칸 끝의 잡티)는 버린다
        role[c["label"]] = role[nearest["label"]] if box_gap(nearest) <= SPECK_REACH else None
    return role


def main():
    data, width, height, pitch = load_rgba(SOURCE)
    layers = {name: bytearray(len(data)) for name in ("body", "arm_l", "arm_r")}
    # 반전 후 화면 기준 이름: 돌 팔 → arm_r, 금속 팔 → arm_l
    rename = {"body": "body", "stone": "arm_r", "metal": "arm_l"}
    meta = {"cell": [CELL_W, CELL_H], "columns": COLUMNS, "frames": []}
    for frame in range(COLUMNS * ROWS):
        col, row = frame % COLUMNS, frame // COLUMNS
        cx, cy = col * CELL_W, row * CELL_H
        labels, comps, hw = label_cell(data, pitch, cx, cy)
        if not comps:
            break
        role = classify(comps)
        boxes = {}
        red_sum = []
        for y in range(CELL_H):
            src_row = (cy + y) * pitch
            lrow = (y // 2) * hw
            for x in range(CELL_W):
                o = src_row + (cx + x) * 4
                if data[o + 3] <= ALPHA_MIN:
                    continue
                lab = labels[lrow + x // 2]
                name = rename.get(role.get(lab)) if lab else None
                if name is None:
                    continue
                mx = CELL_W - 1 - x  # 좌우 반전
                d = src_row + (cx + mx) * 4
                layers[name][d:d + 4] = data[o:o + 4]
                b = boxes.setdefault(name, [mx, y, mx, y])
                b[0] = min(b[0], mx); b[1] = min(b[1], y); b[2] = max(b[2], mx); b[3] = max(b[3], y)
                if name == "body":
                    r, g, bl = data[o], data[o + 1], data[o + 2]
                    if r > 120 and r > g + 30 and r > bl + 30:  # 붉은 빛 (핵·혈관)
                        red_sum.append((mx, y))
        # 핵: 몸통 위쪽 가운데 축 근처의 붉은 픽셀 중심 (혈관은 몸통 아래·옆으로 퍼져 있다)
        bx0, by0, bx1, by1 = boxes["body"]
        axis = (bx0 + bx1) / 2
        near = [(x, y) for x, y in red_sum if abs(x - axis) < 40 and y < by0 + 90]
        core = [sum(x for x, _ in near) / len(near), sum(y for _, y in near) / len(near)] if near else None
        meta["frames"].append({"boxes": boxes, "core": core})
        print(frame, {k: tuple(v) for k, v in boxes.items()}, "core", core and [round(v) for v in core])
    # 발: 몸통 경계 상자 아래 가운데의 평균 (모든 프레임에서 거의 같다)
    bottoms = [f["boxes"]["body"][3] for f in meta["frames"]]
    centers = [(f["boxes"]["body"][0] + f["boxes"]["body"][2]) / 2 for f in meta["frames"]]
    meta["foot"] = [sum(centers) / len(centers), max(bottoms)]
    with open(os.path.join(ROOT, "boss_layers.json"), "w", encoding="utf-8") as fp:
        json.dump(meta, fp, indent=1)
    for name, buf in layers.items():
        surf = sdl2.SDL_CreateRGBSurfaceWithFormatFrom(
            (ctypes.c_ubyte * len(buf)).from_buffer(buf), width, height, 32, pitch,
            sdl2.SDL_PIXELFORMAT_ABGR8888,
        )
        sdlimage.IMG_SavePNG(surf, os.path.join(ROOT, f"boss_{name}.png").encode("utf-8"))
    print("foot", meta["foot"])


if __name__ == "__main__":
    main()
