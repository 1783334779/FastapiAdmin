"""滑块拼图验证码：品牌化出题器。

背景使用产品页面截图，图块使用品牌 Logo；缺口横坐标只保存在服务端 Redis，
前端拖动到正确位置后由服务端校验。
"""

from __future__ import annotations

import base64
import random
from pathlib import Path

WIDTH = 320
HEIGHT = 160
PIECE = 48
KNOB = 7
PIECE_WIDTH = PIECE + KNOB
RADIUS = 8

_ASSET_DIR = Path(__file__).parent / "assets"


def _read_asset_data_uri(name: str, mime: str) -> str:
    path = _ASSET_DIR / name
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


BG_IMAGE = _read_asset_data_uri("page-bg.png", "image/png")
LOGO_IMAGE = _read_asset_data_uri("logo.svg", "image/svg+xml")


def _svg_data(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()


def _fallback_background() -> str:
    return '<rect width="320" height="160" fill="#1b2140"/><circle cx="250" cy="50" r="70" fill="#4f6bff" opacity="0.3"/><circle cx="80" cy="120" r="60" fill="#6d5bff" opacity="0.28"/>'


def build_puzzle(key: str) -> dict:
    """返回背景、图块与缺口坐标；target_x 写入 Redis，不下发前端。"""
    rnd = random.Random(key)
    target_x = rnd.randint(80, WIDTH - PIECE_WIDTH - 16)
    target_y = rnd.randint(12, HEIGHT - PIECE - 12)

    background = f'<image href="{BG_IMAGE}" x="0" y="0" width="{WIDTH}" height="{HEIGHT}" preserveAspectRatio="xMidYMid slice"/>' if BG_IMAGE else _fallback_background()

    bg_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}">'
        f"{background}"
        '<rect width="320" height="160" fill="#0b0d12" opacity="0.28"/>'
        f'<rect x="{target_x}" y="{target_y}" width="{PIECE}" height="{PIECE}" '
        f'rx="{RADIUS}" fill="#080a10" opacity="0.72"/>'
        f'<circle cx="{target_x + PIECE}" cy="{target_y + PIECE // 2}" r="{KNOB}" '
        f'fill="#080a10" opacity="0.72"/>'
        f'<rect x="{target_x}" y="{target_y}" width="{PIECE}" height="{PIECE}" '
        f'rx="{RADIUS}" fill="none" stroke="#ffffff" stroke-opacity="0.55"/>'
        f'<circle cx="{target_x + PIECE}" cy="{target_y + PIECE // 2}" r="{KNOB}" '
        f'fill="none" stroke="#ffffff" stroke-opacity="0.55"/>'
        "</svg>"
    )

    piece_content = (
        f'<image href="{LOGO_IMAGE}" x="4" y="4" width="{PIECE - 8}" height="{PIECE - 8}" preserveAspectRatio="xMidYMid meet"/>' if LOGO_IMAGE else '<rect width="48" height="48" fill="#4f6bff"/>'
    )
    piece_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PIECE_WIDTH}" height="{PIECE}" '
        f'viewBox="0 0 {PIECE_WIDTH} {PIECE}">'
        "<defs>"
        '<clipPath id="piece">'
        f'<rect width="{PIECE}" height="{PIECE}" rx="{RADIUS}"/>'
        f'<circle cx="{PIECE}" cy="{PIECE // 2}" r="{KNOB}"/>'
        "</clipPath>"
        "</defs>"
        '<g clip-path="url(#piece)">'
        '<rect width="48" height="48" fill="#141824"/>'
        f"{piece_content}"
        "</g>"
        f'<rect x="0.5" y="0.5" width="{PIECE - 1}" height="{PIECE - 1}" rx="{RADIUS}" '
        'fill="none" stroke="#ffffff" stroke-opacity="0.85"/>'
        f'<circle cx="{PIECE}" cy="{PIECE // 2}" r="{KNOB}" fill="none" '
        'stroke="#ffffff" stroke-opacity="0.85"/>'
        "</svg>"
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
