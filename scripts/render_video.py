"""Render the ContextMesh walkthrough as a real MP4.

Motion graphics drawn with PIL (no browser, no recording needed), encoded
with the imageio-ffmpeg bundled binary.

Run:  python -m scripts.render_video
Out:  brand/contextmesh_walkthrough.mp4
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 12
OUT = Path(__file__).resolve().parents[1] / "brand" / "contextmesh_walkthrough.mp4"

INK = (219, 231, 244)
DIM = (138, 160, 184)
PANEL = (17, 24, 35)
LINE = (34, 48, 66)
ACCENT = (55, 210, 170)
BLUE = (90, 162, 255)
PURP = (199, 146, 234)
WARN = (255, 180, 84)
BAD = (255, 107, 122)
BG = (11, 15, 20)

FDIR = "/usr/share/fonts/truetype/dejavu/"
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def F(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _font_cache:
        name = {"b": "DejaVuSans-Bold.ttf", "m": "DejaVuSansMono.ttf",
                "mb": "DejaVuSansMono-Bold.ttf", "r": "DejaVuSans.ttf"}[weight]
        _font_cache[key] = ImageFont.truetype(FDIR + name, size)
    return _font_cache[key]


def ease(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def pop(p: float) -> float:
    """0..1 with a small overshoot."""
    p = min(max(p, 0.0), 1.0)
    if p >= 1:
        return 1.0
    return 1 - math.cos(p * math.pi * 1.16) * (1 - p) ** 2


def base_frame() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # faint grid
    for x in range(0, W, 64):
        d.line([(x, 0), (x, H)], fill=(14, 19, 26), width=1)
    for y in range(0, H, 64):
        d.line([(0, y), (W, y)], fill=(14, 19, 26), width=1)
    return img


def fade_in(img: Image.Image, p: float) -> Image.Image:
    if p >= 1:
        return img
    black = Image.new("RGB", img.size, BG)
    return Image.blend(black, img, ease(p))


def txt(d: ImageDraw.ImageDraw, xy, s, font, fill=INK, anchor="la"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


def chip(d, box, label, font, border=LINE, fill=PANEL, tcolor=INK, width=2):
    d.rounded_rectangle(box, radius=10, fill=fill, outline=border, width=width)
    x0, y0, x1, y1 = box
    txt(d, ((x0 + x1) / 2, (y0 + y1) / 2 + 1), label, font, tcolor, anchor="mm")


# ---------------------------------------------------------------- mesh mark

MESH_OUT = [(0.19, 0.21), (0.81, 0.18), (0.50, 0.125), (0.156, 0.68), (0.84, 0.65)]
MESH_CENTER = (0.50, 0.50)


def draw_mesh(d, cx, cy, s, reveal: float, lit: bool = False):
    """Graph mark. reveal 0..1 staggers: outer nodes -> edges -> center."""
    outer = [(cx + (mx - 0.5) * s, cy + (my - 0.5) * s * 0.86) for mx, my in MESH_OUT]
    c = (cx + (MESH_CENTER[0] - 0.5) * s, cy + (MESH_CENTER[1] - 0.5) * s * 0.86)
    n = len(outer)
    for i, (mx, my) in enumerate(MESH_OUT):
        p = ease((reveal - i * 0.07) / 0.35)
        if p <= 0:
            continue
        r = 10 * s / 240 * pop(p)
        ox, oy = outer[i]
        d.ellipse([ox - r, oy - r, ox + r, oy + r],
                  fill=(BLUE if i != 2 else LINE))
    for i, (mx, my) in enumerate(MESH_OUT):
        p = ease((reveal - 0.25 - i * 0.05) / 0.35)
        if p <= 0:
            continue
        ox, oy = outer[i]
        ex, ey = ox + (c[0] - ox) * p, oy + (c[1] - oy) * p
        d.line([ox, oy, ex, ey], fill=(58, 79, 107), width=max(2, int(s / 90)))
    if lit:
        d.line([outer[0], outer[1]], fill=LINE, width=2)
        d.line([outer[3], outer[4]], fill=LINE, width=2)
    p = ease((reveal - 0.55) / 0.4)
    if p > 0:
        rr = 26 * s / 240 * p
        glow = tuple(int(v * 0.35) for v in ACCENT)
        d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], fill=glow)
        r0 = 16 * s / 240 * pop(p)
        d.ellipse([c[0] - r0, c[1] - r0, c[0] + r0, c[1] + r0], fill=ACCENT)


# ------------------------------------------------------------------ scenes

def sc_intro(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    p = t / 6.0
    draw_mesh(d, W / 2, H * 0.40, 300, p * 1.6, lit=True)
    a = ease((t - 3.2) / 0.8)
    if a > 0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        f_title = F("b", 64)
        w_c = od.textlength("Context", font=f_title)
        w_m = od.textlength("Mesh", font=f_title)
        x0 = W / 2 - (w_c + w_m) / 2
        od.text((x0, H * 0.66), "Context", font=f_title,
                fill=INK + (int(255 * a),), anchor="lm")
        od.text((x0 + w_c, H * 0.66), "Mesh", font=f_title,
                fill=ACCENT + (int(255 * a),), anchor="lm")
        od.text((W / 2, H * 0.75), "agent memory, as a graph — built on HydraDB",
                font=F("m", 20), fill=DIM + (int(255 * a),), anchor="mm")
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    return fade_in(img, min(1, t / 0.6))


TOOLS_WALL = ["get_ci_status", "list_recent_commits", "create_issue", "get_pod_status",
              "get_events", "restart_deployment", "scale_deployment", "get_slow_queries",
              "get_replication_lag", "run_readonly_query", "get_metric_series",
              "get_dashboard", "get_incidents", "get_oncall", "acknowledge_incident",
              "lookup_entity"]


def sc_problem(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    txt(d, (70, 54), "Today: brute-force context", F("b", 40))
    txt(d, (70, 106), "every tool, in every window, on every step", F("r", 20), DIM)
    # scrolling tool wall
    px0, py0, px1, py1 = 70, 150, 700, 620
    d.rounded_rectangle([px0, py0, px1, py1], radius=14, fill=(13, 20, 32), outline=LINE)
    scroll = (t * 55) % 60
    f = F("m", 15)
    cols = 2
    for row in range(9):
        for col in range(cols):
            idx = (row * cols + col) % len(TOOLS_WALL)
            x = px0 + 24 + col * 300
            y = py0 + 20 + row * 56 - scroll
            if py0 + 6 < y < py1 - 30:
                chip(d, [x, y, x + 272, y + 40], f"tool: {TOOLS_WALL[idx]}  {{…schema}}",
                     f, border=(24, 34, 48), tcolor=DIM)
    a = ease((t - 1.2) / 0.7)
    if a > 0:
        txt(d, (760, 200), "16 tools × every step", F("b", 30), BAD)
        txt(d, (760, 250), "— paid again on every turn", F("r", 20), DIM)
    b = ease((t - 2.4) / 0.7)
    if b > 0:
        txt(d, (760, 350), '"checkout" → ???', F("mb", 26), WARN)
        txt(d, (760, 400), "N mentions → N resolver calls", F("r", 20), DIM)
        txt(d, (760, 440), "…and the model may simply skip them", F("r", 18), DIM)
    return fade_in(img, min(1, t / 0.5))


GRAPH_NODES = [
    ("agent-0", 0.50, 0.16, LINE, INK),
    ("incident-triage", 0.22, 0.36, BLUE, INK),
    ("db-health-check", 0.50, 0.36, BLUE, INK),
    ("escalation-oncall", 0.78, 0.36, BLUE, INK),
    ("get_pod_status", 0.09, 0.60, ACCENT, INK),
    ("get_metric_series", 0.295, 0.60, ACCENT, INK),
    ("get_slow_queries", 0.50, 0.60, ACCENT, INK),
    ("get_oncall", 0.705, 0.60, ACCENT, INK),
    ("create_issue", 0.91, 0.60, ACCENT, INK),
    ("github", 0.35, 0.84, WARN, INK),
    ("k8s", 0.55, 0.84, WARN, INK),
    ("pagerduty", 0.78, 0.84, WARN, INK),
]
GRAPH_EDGES = [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (2, 6), (3, 7), (3, 8),
               (5, 9), (4, 10), (7, 11)]


def sc_graph(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    txt(d, (70, 54), "The alternative: knowledge as a graph", F("b", 38))
    txt(d, (70, 104), "durable in HydraDB — object-store native, snapshot-consistent", F("r", 19), DIM)
    fx0, fy0, fx1, fy1 = 120, 160, 830, 650
    pts = []
    for _, mx, my, _, _ in GRAPH_NODES:
        pts.append((fx0 + (fx1 - fx0) * mx, fy0 + (fy1 - fy0) * my))
    for i, (a, b) in enumerate(GRAPH_EDGES):
        p = ease((t - 0.7 - i * 0.22) / 0.5)
        if p <= 0:
            continue
        x0, y0 = pts[a]
        x1, y1 = pts[b]
        d.line([x0, y0, x0 + (x1 - x0) * p, y0 + (y1 - y0) * p], fill=(58, 79, 107), width=3)
    for i, (label, _, _, border, color) in enumerate(GRAPH_NODES):
        p = ease((t - i * 0.14) / 0.5)
        if p <= 0:
            continue
        x, y = pts[i]
        s = pop(p)
        f_node = F("m", 14)
        w2 = (d.textlength(label, font=f_node) + 18) / 2 * s
        h2 = 21 * s
        d.rounded_rectangle([x - w2, y - h2, x + w2, y + h2], radius=9,
                            fill=PANEL, outline=border, width=2)
        txt(d, (x, y + 1), label, f_node, color, anchor="mm")
    c = ease((t - 2.6) / 0.7)
    if c > 0:
        d.rounded_rectangle([880, 300, 1210, 470], radius=14, fill=(13, 20, 32), outline=LINE)
        txt(d, (905, 330), '(:Alias)-[:RESOLVES_TO]', F("m", 16), PURP)
        txt(d, (905, 362), '  ->(:Entity)', F("m", 16), PURP)
        txt(d, (905, 402), '"checkout" → checkout-api', F("m", 15), DIM)
        txt(d, (905, 430), '"prod"     → prod-us', F("m", 15), DIM)
    return fade_in(img, min(1, t / 0.5))


def sc_plan(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    txt(d, (70, 54), "One call before the model sees anything", F("b", 38))
    d.rounded_rectangle([70, 130, 780, 600], radius=14, fill=(13, 20, 32), outline=LINE)
    query = 'plan("why is checkout failing in prod")'
    shown = query[: int(len(query) * min(1, t / 1.6))]
    txt(d, (100, 165), "» ", F("mb", 22), ACCENT)
    txt(d, (134, 165), shown, F("mb", 22), INK)
    rows = [
        ("skill ", "incident-triage", ACCENT),
        ("tools ", "5 bound (of 16)", ACCENT),
        ("entity", 'checkout → checkout-api', PURP),
        ("entity", "prod → prod-us", PURP),
        ("trips ", "2 round-trips · ~4 ms", WARN),
    ]
    for i, (k, v, color) in enumerate(rows):
        p = ease((t - 2.2 - i * 0.55) / 0.5)
        if p <= 0:
            continue
        a = int(255 * p)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        y = 230 + i * 56
        od.text((100, y), k, font=F("m", 20), fill=DIM + (a,))
        od.text((210, y), v, font=F("mb", 20), fill=color + (a,))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(img)
    p = ease((t - 2.4) / 1.0)
    if p > 0:
        val = int(round(2 * p))
        d.text((1010, 270), str(val), font=F("b", 130), fill=ACCENT, anchor="mm")
        txt(d, (1010, 380), "graph round-trips", F("r", 22), DIM, anchor="mm")
        txt(d, (1010, 430), "before the first LLM call", F("r", 18), DIM, anchor="mm")
    return fade_in(img, min(1, t / 0.5))


def sc_learn(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    txt(d, (70, 54), "Every session writes back", F("b", 38))
    txt(d, (70, 104), "the graph gets sharper the more it is used", F("r", 19), DIM)
    p = ease(t / 0.8)
    if p > 0:
        s = pop(p)
        label = "(:Session) {task}"
        lw = d.textlength(label, font=F("mb", 18))
        x0, y0 = 70, 190
        chip(d, [x0, y0, x0 + (lw + 44) * s, y0 + 60],
             label, F("mb", 18), border=BLUE)
    tools = ["get_ci_status", "get_pod_status", "get_metric_series"]
    for i, name in enumerate(tools):
        q = ease((t - 0.9 - i * 0.25) / 0.5)
        if q <= 0:
            continue
        x0, y0 = 235, 220
        x1, y1 = 200 + i * 240, 340
        d.line([x0, y0, x0 + (x1 - x0) * q, y0 + (y1 - y0) * q], fill=(58, 79, 107), width=3)
        s = pop(q)
        chip(d, [x1 - 100 * (1 - s), y1, x1 + 190 * s, y1 + 46], name, F("m", 16),
             border=ACCENT)
        u = ease((t - 2.0 - i * 0.2) / 0.6)
        if u > 0:
            txt(d, (x1 + 95, y1 + 64), f"uses {8 + i} → {9 + i}", F("m", 15), WARN, anchor="mm")
    a = ease((t - 3.4) / 0.8)
    if a > 0:
        s = pop(a)
        chip(d, [70, 470, 70 + 420 * s, 524], 'learned: "db" → orders-db', F("mb", 19),
             border=PURP, tcolor=PURP)
        txt(d, (510, 497), "— next task resolves it for free", F("r", 18), DIM)
    b = ease((t - 4.6) / 0.7)
    if b > 0:
        txt(d, (70, 580), "durable in SlateDB — restarts lose nothing", F("m", 18), DIM)
    return fade_in(img, min(1, t / 0.5))


def sc_results(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    txt(d, (70, 54), "Same tasks. Same model.", F("b", 38))
    txt(d, (70, 104), "graph context vs all-tools-in-window (5 ops tasks)", F("r", 19), DIM)
    maxw = 850.0
    for row, (label, val, color, y) in enumerate([
        ("baseline  15,276 prompt tokens", 15276, BAD, 190),
        ("hydra       8,195 prompt tokens", 8195, ACCENT, 262),
    ]):
        p = ease((t - 0.6 - row * 0.45) / 1.0)
        if p <= 0:
            continue
        txt(d, (70, y), label.split()[0], F("mb", 24), color)
        w = int(maxw * (val / 15276.0) * p)
        d.rounded_rectangle([260, y - 4, 260 + w, y + 30], radius=8, fill=color)
        txt(d, (276 + w, y + 2), f"{val:,}", F("mb", 20), INK) if w > 220 else None
    txt(d, (260, 320), "prompt tokens (lower is better)", F("r", 17), DIM)
    rows2 = [("correct", "4 / 5", ACCENT, "0 / 5", BAD), ]
    p = ease((t - 2.0) / 0.8)
    if p > 0:
        txt(d, (70, 380), "tool + entity correctness", F("mb", 24), INK)
        txt(d, (70, 425), "hydra", F("r", 20), DIM)
        txt(d, (200, 425), "4 / 5", F("b", 30), ACCENT)
        txt(d, (340, 425), "baseline", F("r", 20), DIM)
        txt(d, (500, 425), "0 / 5", F("b", 30), BAD)
    q = ease((t - 3.0) / 0.8)
    if q > 0:
        txt(d, (70, 500), "load: 128 concurrent sessions · 0 errors", F("mb", 24), INK)
        txt(d, (70, 545), "plan p50 37 ms · p95 76 ms at 16-way concurrency", F("r", 19), DIM)
    r = ease((t - 4.0) / 0.8)
    if r > 0:
        txt(d, (70, 615), "durability: reboot → graph intact from object storage", F("m", 19), WARN)
    return fade_in(img, min(1, t / 0.5))


def sc_outro(t: float) -> Image.Image:
    img = base_frame()
    d = ImageDraw.Draw(img)
    draw_mesh(d, W / 2, H * 0.36, 260, min(1.6, t / 4.0 * 1.6), lit=True)
    a = ease((t - 2.0) / 0.8)
    if a > 0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        f_title = F("b", 56)
        w_c = od.textlength("Context", font=f_title)
        w_m = od.textlength("Mesh", font=f_title)
        x0 = W / 2 - (w_c + w_m) / 2
        od.text((x0, H * 0.60), "Context", font=f_title,
                fill=INK + (int(255 * a),), anchor="lm")
        od.text((x0 + w_c, H * 0.60), "Mesh", font=f_title,
                fill=ACCENT + (int(255 * a),), anchor="lm")
        od.text((W / 2, H * 0.68), "The context layer for agent fleets.", font=F("r", 24),
                fill=DIM + (int(255 * a),), anchor="mm")
        od.text((W / 2, H * 0.78), "built on HydraDB", font=F("m", 18),
                fill=DIM + (int(200 * a),), anchor="mm")
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    return fade_in(img, min(1, t / 0.6))


SCENES = [
    ("intro", sc_intro, 6.0),
    ("problem", sc_problem, 6.5),
    ("graph", sc_graph, 6.0),
    ("plan", sc_plan, 6.5),
    ("learn", sc_learn, 6.5),
    ("results", sc_results, 6.5),
    ("outro", sc_outro, 5.0),
]


def main() -> int:
    import numpy as np
    import imageio.v2 as imageio

    frames_path = Path("/tmp/opencode/cm_frames")
    frames_path.mkdir(parents=True, exist_ok=True)
    n_total = sum(int(dur * FPS) for _, _, dur in SCENES)
    print(f"rendering {n_total} frames at {FPS} fps ({W}x{H}) …")
    i = 0
    with imageio.get_writer(OUT, fps=FPS, quality=8, macro_block_size=16) as w:
        for name, fn, dur in SCENES:
            n = int(dur * FPS)
            for k in range(n):
                frame = fn(k / FPS)
                w.append_data(np.asarray(frame))
                if k % 12 == 0:
                    frame.save(frames_path / f"{name}_{k:03d}.png")
                i += 1
            print(f"  {name}: {n} frames done ({i}/{n_total})")
    print(f"saved -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
