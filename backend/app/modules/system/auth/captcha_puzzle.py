"""滑块拼图验证码的 SVG 出题器。

不依赖 Pillow：用随机几何图形拼出背景，再按拼图缺口裁剪出滑块图块。
前端把图块按用户拖动位置覆盖到背景上，服务端只保存缺口横坐标并校验。
"""

from __future__ import annotations

import base64
import random

WIDTH = 320
HEIGHT = 160
PIECE = 48
KNOB = 7
PIECE_WIDTH = PIECE + KNOB
RADIUS = 8

PALETTE = [
    "#4F6BFF",
    "#6D5BFF",
    "#22C55E",
    "#F59E0B",
    "#EC4899",
    "#06B6D4",
    "#A855F7",
    "#F97316",
]


def _svg_data(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()


def _background_shapes(rnd: random.Random) -> str:
    parts = [
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>',
    ]
    for _ in range(14):
        cx = rnd.randint(-20, WIDTH + 20)
        cy = rnd.randint(-20, HEIGHT + 20)
        r = rnd.randint(14, 52)
        color = rnd.choice(PALETTE)
        opacity = round(rnd.uniform(0.18, 0.55), 2)
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" opacity="{opacity}"/>')
    for _ in range(5):
        x = rnd.randint(0, WIDTH - 40)
        y = rnd.randint(0, HEIGHT - 20)
        w = rnd.randint(30, 100)
        h = rnd.randint(8, 26)
        color = rnd.choice(PALETTE)
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{color}" opacity="0.28" transform="rotate({rnd.randint(-18, 18)} {x} {y})"/>')
    parts.append(f'<g stroke="#ffffff" stroke-opacity="0.12"><path d="M0 {HEIGHT * 2 // 3} L{WIDTH} {HEIGHT // 3}"/><path d="M0 {HEIGHT // 3} L{WIDTH} {HEIGHT * 2 // 3}"/></g>')
    return "".join(parts)


def build_puzzle(key: str) -> dict:
    """返回背景、图块、缺口坐标；target_x 由调用方写入 Redis，不下发给前端。"""
    rnd = random.Random(key)
    target_x = rnd.randint(80, WIDTH - PIECE_WIDTH - 16)
    target_y = rnd.randint(12, HEIGHT - PIECE - 12)

    shapes = _background_shapes(rnd)
    defs = (
        "<defs>"
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#1B2140"/>'
        '<stop offset="0.55" stop-color="#2A1F45"/>'
        '<stop offset="1" stop-color="#0E2233"/>'
        "</linearGradient>"
        '<mask id="hole">'
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>'
        f'<rect x="{target_x}" y="{target_y}" width="{PIECE}" height="{PIECE}" rx="{RADIUS}" fill="#000"/>'
        f'<circle cx="{target_x + PIECE}" cy="{target_y + PIECE // 2}" r="{KNOB}" fill="#000"/>'
        "</mask>"
        "</defs>"
    )

    bg_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}">{defs}'
        f'<g mask="url(#hole)">{shapes}</g>'
        f'<rect x="{target_x}" y="{target_y}" width="{PIECE}" height="{PIECE}" '
        f'rx="{RADIUS}" fill="none" stroke="#ffffff" stroke-opacity="0.4"/>'
        f'<circle cx="{target_x + PIECE}" cy="{target_y + PIECE // 2}" r="{KNOB}" '
        f'fill="none" stroke="#ffffff" stroke-opacity="0.4"/>'
        f"</svg>"
    )

    piece_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PIECE_WIDTH}" height="{PIECE}" '
        f'viewBox="0 0 {PIECE_WIDTH} {PIECE}">'
        "<defs>"
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#1B2140"/>'
        '<stop offset="0.55" stop-color="#2A1F45"/>'
        '<stop offset="1" stop-color="#0E2233"/>'
        "</linearGradient>"
        '<clipPath id="piece">'
        f'<rect width="{PIECE}" height="{PIECE}" rx="{RADIUS}"/>'
        f'<circle cx="{PIECE}" cy="{PIECE // 2}" r="{KNOB}"/>'
        "</clipPath>"
        "</defs>"
        f'<g clip-path="url(#piece)"><g transform="translate({-target_x} {-target_y})">'
        f"{shapes}</g></g>"
        f'<rect x="0.5" y="0.5" width="{PIECE - 1}" height="{PIECE - 1}" rx="{RADIUS}" '
        f'fill="none" stroke="#ffffff" stroke-opacity="0.85"/>'
        f'<circle cx="{PIECE}" cy="{PIECE // 2}" r="{KNOB}" fill="none" '
        f'stroke="#ffffff" stroke-opacity="0.85"/>'
        f"</svg>"
    )

    return {
        "target_x": target_x,
        "piece_y": target_y,
        "piece_width": PIECE_WIDTH,
        "piece_height": PIECE,
        "bg_width": WIDTH,
        "bg_height": HEIGHT,
        "img_base": _svg_data(bg_svg),
        "piece_base": _svg_data(piece_svg),
    }
