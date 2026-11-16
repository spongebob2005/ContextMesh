"""Render X (Twitter) ready brand assets from the SVG logo sources.

Outputs:
  brand/x_post_1600x900.png   — 16:9 post image, logo lockup centered
  brand/x_profile_400x400.png — square profile picture
  brand/logo_1024.png         — transparent-background lockup, social/OG use

Run:  python -m scripts.render_brand_assets
"""
from __future__ import annotations

import io
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"

W, H = 1600, 900
BG = (11, 15, 20)
GRID = (14, 19, 26)
ACCENT = (55, 210, 170)


def svg_png(name: str, width: int) -> Image.Image:
    png = cairosvg.svg2png(
        url=str(BRAND / name), output_width=width, background_color=None
    )
    assert png is not None
    return Image.open(io.BytesIO(png)).convert("RGBA")


def compose_post() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 64):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 64):
        d.line([(0, y), (W, y)], fill=GRID, width=1)

    # soft accent glow behind the lockup (very subtle)
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)
    glow = np.clip(1 - dist / 620.0, 0, 1) ** 2 * 26
    layer = np.zeros((H, W, 3), dtype=np.float32)
    for c, v in enumerate(ACCENT):
        layer[..., c] = v
    base = np.asarray(img).astype(np.float32)
    alpha = (glow / 255.0)[..., None]
    img = Image.fromarray(
        np.clip(base * (1 - alpha) + layer * alpha, 0, 255).astype(np.uint8)
    )

    lockup = svg_png("contextmesh_lockup.svg", 1400)
    lockup = lockup.crop(lockup.getbbox() or (0, 0, *lockup.size))  # trim padding
    ratio = 1000 / lockup.size[0]
    lockup = lockup.resize((1000, round(lockup.size[1] * ratio)), Image.LANCZOS)
    lw, lh = lockup.size
    img.paste(lockup, ((W - lw) // 2, (H - lh) // 2), lockup)
    return img


def compose_profile() -> Image.Image:
    # the mark carries its own dark badge; flatten onto the brand background
    mark = svg_png("contextmesh_mark.svg", 400)
    flat = Image.new("RGB", (400, 400), BG)
    flat.paste(mark, (0, 0), mark)
    return flat


def main() -> int:
    post = compose_post()
    post.save(BRAND / "x_post_1600x900.png", optimize=True)

    profile = compose_profile()
    profile.save(BRAND / "x_profile_400x400.png", optimize=True)

    lockup = svg_png("contextmesh_lockup.svg", 1024)
    lockup.save(BRAND / "logo_1024.png", optimize=True)

    for name in ("x_post_1600x900.png", "x_profile_400x400.png", "logo_1024.png"):
        p = BRAND / name
        with Image.open(p) as im:
            print(f"  {name:<26} {im.size[0]}x{im.size[1]}  {p.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
