"""Pixel art generator for the desert and Mars worlds.

Writes two new autotile sets in the layout of `tiles/grass` and
`tiles/stone` (variants 0-8, see `AUTOTILE_MAP` in scripts/tilemap.py):

- `tiles/sand`: wind-rippled dune sand on layered sandstone (desert)
- `tiles/mars`: rust-red regolith dust on cracked basalt (Mars)

plus decor sprites for both worlds (appended to `tiles/decor` and
`tiles/large_decor`) and one background per world. Everything is drawn
from small hand-authored pixel grids and a seeded RNG, so a re-run
reproduces the same files.

Pure black (0, 0, 0) is the transparency colorkey used by AssetManager:
the tiles keep the existing format (RGB, black = transparent).

Usage:
    python tools/gen_world_tiles.py [--preview /path/to/montage.png]
"""

from __future__ import annotations

import argparse
import math
import os
import random

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(REPO, "data", "images")
TILE_DIR = os.path.join(IMG_DIR, "tiles")

T = 16  # tile size
TRANSPARENT = (0, 0, 0)

# Which sides of a tile are open (no neighbor of the same type) per variant
# 0 TL, 1 top, 2 TR, 3 right, 4 BR, 5 bottom, 6 BL, 7 left, 8 center
OPEN_SIDES = {
    0: {"top", "left"},
    1: {"top"},
    2: {"top", "right"},
    3: {"right"},
    4: {"right", "bottom"},
    5: {"bottom"},
    6: {"left", "bottom"},
    7: {"left"},
    8: set(),
}

# Rounded outer corners, as in grass/stone: these pixels stay transparent
CORNER_CUTS = {
    0: [(0, 0), (1, 0), (0, 1)],
    2: [(15, 0), (14, 0), (15, 1)],
    4: [(15, 15), (14, 15), (15, 14)],
    6: [(0, 15), (1, 15), (0, 14)],
}


# --- Tile sets ----------------------------------------------------------------
# Each set: a top band (16 x 8, tiles seamlessly in x), a right edge strip
# (5 x 16, tiles seamlessly in y; mirrored for the left edge) and a body color.

SAND = {
    "palette": {
        "W": (250, 234, 172),  # sun-lit crest
        "S": (238, 204, 124),  # sand
        "T": (216, 168, 92),  # ripple shade
        "U": (182, 126, 70),  # drift shadow
        "B": (130, 82, 48),  # sandstone body
        "D": (112, 68, 42),  # strata seam
        "L": (166, 110, 62),  # lit sandstone
    },
    "top": [
        "WWSWWWWWSSWWWWWS",
        "SWWSSWWSSWWSSWWS",
        "SSSTSSSSSSTTSSSS",
        "TSSSTTSSSSSSTTSS",
        "STTSSSTTTSSSSSTT",
        "UTTUTTUUTTUTTUUT",
        "BUUBUUBBUUBUUBBU",
        "BBBBBBBBBBBBBBBB",
    ],
    "edge": [
        "BLLSL",
        "BDLLS",
        "BLLLS",
        "DLLSL",
        "BBLLL",
        "BLLDL",
        "BLLLS",
        "BDDLL",
        "BLLLL",
        "DLLSL",
        "BLLLS",
        "BBLLL",
        "BLDLL",
        "BLLLS",
        "DLLSL",
        "BBLLL",
    ],
    # Sandstone strata: (row, x0, x1) dashes of the seam color in the body
    "strata": [(5, 2, 7), (12, 9, 14)],
    "strata_color": "D",
    "body": "B",
}

MARS = {
    "palette": {
        "W": (240, 150, 98),  # dust highlight
        "S": (214, 110, 66),  # regolith dust
        "T": (182, 80, 50),  # dust shade
        "P": (110, 52, 46),  # dark pebble
        "U": (146, 56, 40),  # dust shadow
        "B": (104, 38, 32),  # basalt body
        "D": (80, 26, 28),  # crack
        "L": (140, 58, 42),  # lit rock
    },
    "top": [
        "WSWWSSWWWSWSSWWW",
        "SSSWSPSSSSSWSSPS",
        "STSSSSSTSSSSTSSS",
        "TSSTTSSSTTSPSSTT",
        "UTTUTTUTTUTTUTTU",
        "BUUBBUBUUBBUUBBU",
        "BBBBBBBBBBBBBBBB",
        "BBBBBBBBBBBBBBBB",
    ],
    "edge": [
        "BDLLL",
        "BDLWL",
        "BDLLS",
        "BBDLL",
        "BDLLL",
        "DLLSL",
        "DLWLL",
        "BDLLS",
        "BDDLL",
        "BBDLL",
        "BDLLW",
        "BDLLL",
        "DLLSL",
        "DLLLL",
        "BDLLS",
        "BBDDL",
    ],
    # Basalt cracks: (row, x0, x1) dashes in the body
    "strata": [(4, 3, 5), (5, 5, 6), (11, 10, 12), (12, 12, 13)],
    "strata_color": "D",
    "body": "B",
}

TILESETS = {"sand": SAND, "mars": MARS}


def build_tile(spec: dict, variant: int) -> Image.Image:
    pal = spec["palette"]
    body = pal[spec["body"]]
    open_sides = OPEN_SIDES[variant]
    img = Image.new("RGB", (T, T), body)
    px = img.load()

    # Body texture (strata / cracks), skipped where the edges are drawn
    for row, x0, x1 in spec["strata"]:
        for x in range(x0, x1 + 1):
            px[x, row] = pal[spec["strata_color"]]

    top_rows = len(spec["top"])
    # Side edges first; the top band is drawn over them at the corners
    if "right" in open_sides or "left" in open_sides:
        for y in range(T):
            row = spec["edge"][y]
            for i, ch in enumerate(row):
                if "right" in open_sides:
                    px[T - len(row) + i, y] = pal[ch]
                if "left" in open_sides:
                    px[len(row) - 1 - i, y] = pal[ch]
    if "top" in open_sides:
        for y in range(top_rows):
            for x in range(T):
                ch = spec["top"][y][x]
                # Below the sand/dust line the edge strip stays visible
                if ch == spec["body"] and (("right" in open_sides and x >= T - 5) or ("left" in open_sides and x < 5)):
                    continue
                px[x, y] = pal[ch]
    if "bottom" in open_sides:
        # Shadowed underside: one darker row, as rock seen from below
        dark = pal[spec["strata_color"]]
        for x in range(T):
            if x % 5 != 2:
                px[x, T - 1] = dark
    for x, y in CORNER_CUTS.get(variant, []):
        px[x, y] = TRANSPARENT
    return img


def generate_tiles() -> None:
    for name, spec in TILESETS.items():
        out = os.path.join(TILE_DIR, name)
        os.makedirs(out, exist_ok=True)
        for v in range(9):
            build_tile(spec, v).save(os.path.join(out, f"{v}.png"))
        print(f"tile set '{name}' generated (9 variants)")


# --- Decor ----------------------------------------------------------------------
# '.' = transparent; letters index DECOR_COLORS.
DECOR_COLORS = {
    "G": (88, 150, 70),  # cactus green
    "g": (54, 104, 58),  # cactus shade
    "h": (150, 200, 110),  # cactus highlight
    "p": (236, 120, 160),  # cactus flower
    "w": (236, 228, 208),  # bone
    "v": (176, 166, 146),  # bone shade
    "y": (150, 120, 70),  # dry brush
    "z": (110, 84, 52),  # dry brush shade
    "R": (168, 72, 50),  # mars rock
    "r": (116, 46, 38),  # mars rock shade
    "o": (206, 108, 70),  # mars rock light
    "c": (120, 220, 230),  # crystal
    "C": (60, 150, 180),  # crystal shade
    "q": (230, 255, 255),  # crystal gleam
}

DECOR = {
    # Small cactus (16x16, stands on the tile below like the flowers)
    "decor/4.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        ".......hG.......",
        "......hGGg......",
        "......hGGg......",
        "...hG.hGGg......",
        "...hGg.hGGg.hG..",
        "...hGGGhGGg.hGg.",
        "....gggGGGgGGGg.",
        ".......hGGggggg.",
        ".......hGGg.....",
        ".......hGGg.....",
        ".......hGGg.....",
    ],
    # Bleached skull and bone
    "decor/5.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "....wwww........",
        "...wwwwwv.......",
        "...w.ww.v.......",
        "...wwwwwv.......",
        "....wvwv..wv..vw",
        "....v.v...wwwwww",
        "..........wv..vw",
    ],
    # Mars rock cluster
    "decor/6.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "......oR........",
        ".....oRRr.......",
        "....oRRRRr..oR..",
        "...oRRRRRr.oRRr.",
        "..oRRRRRRrroRRRr",
        "..rrrrrrrrrrrrrr",
    ],
    # Mars crystal
    "decor/7.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        ".......q........",
        "......qcC.......",
        "......ccC.......",
        "......ccC..q....",
        "...q..ccC.qcC...",
        "..qcC.ccC.ccC...",
        "..ccC.ccC.ccC...",
        "..ccCcccCcccC...",
        "...rRRRRRRRRr...",
        "..rRRRRRRRRRRr..",
        "................",
    ],
}

LARGE_DECOR = {
    # Tall saguaro cactus (offgrid decor)
    "large_decor/3.png": [
        "........hGG........",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg..p....",
        ".......hGGGg..hG...",
        "..hG...hGGGg..hGg..",
        "..hGg..hGGGg..hGg..",
        "..hGg..hGGGg..hGg..",
        "..hGg..hGGGg..hGg..",
        "..hGg..hGGGgGGhGg..",
        "..hGg..hGGGgGGGGg..",
        "..hGGGGhGGGggggg...",
        "...ggggGGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        ".......hGGGg.......",
        "......yzGGGgzy.....",
    ],
    # Dry desert brush
    "large_decor/4.png": [
        "....y.....y....y.....",
        ".y...z...yz...z...y..",
        "..yz..y.z..y.yz..zy..",
        "...yy.zyy..zyy..yz...",
        ".y..zyyzyyzyzyyzy..y.",
        "..zyyzyyzzyyzzyyzyz..",
        "...zzyzzyzzyzzyzzz...",
    ],
    # Mars boulder formation
    "large_decor/5.png": [
        "..........oo..............",
        "........ooRRr.............",
        ".......oRRRRRr............",
        "......oRRRRRRRr.....oR....",
        ".....oRRRRRRRRRr...oRRr...",
        "....oRRRRRRRRRRRr.oRRRRr..",
        "...oRRRRRrRRRRRRrroRRRRRr.",
        "..oRRRRRrrRRRRRRRroRRRRRRr",
        ".oRRRRRRRRRRRRRRRrRRRRRRRr",
        "rrrrrrrrrrrrrrrrrrrrrrrrrr",
    ],
}


def _grid_image(grid: list[str]) -> Image.Image:
    w = max(len(r) for r in grid)
    img = Image.new("RGB", (w, len(grid)), TRANSPARENT)
    px = img.load()
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch in DECOR_COLORS:
                px[x, y] = DECOR_COLORS[ch]
    return img


def generate_decor() -> None:
    for rel, grid in {**DECOR, **LARGE_DECOR}.items():
        _grid_image(grid).save(os.path.join(TILE_DIR, rel))
        print(f"decor '{rel}' generated")


# --- Backgrounds -----------------------------------------------------------------
# 640x480 like background-big.png (the renderer shows its top 640x360).


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _sky(top, bottom, streak, seed: int) -> Image.Image:
    """Vertical gradient in flat bands plus soft diagonal streaks (house style)."""
    w, h = 640, 480
    img = Image.new("RGB", (w, h))
    px = img.load()
    bands = 9
    for y in range(h):
        t = min(1.0, y / 360)
        band = math.floor(t * bands) / bands
        col = _lerp(top, bottom, band)
        for x in range(w):
            px[x, y] = col
    rng = random.Random(seed)
    for _ in range(3):
        y0 = rng.randint(30, 260)
        slope = rng.uniform(0.12, 0.28) * rng.choice((-1, 1))
        width = rng.randint(3, 7)
        for x in range(w):
            yc = y0 + slope * x
            for dy in range(width):
                y = int(yc + dy)
                if 0 <= y < h:
                    px[x, y] = _lerp(px[x, y], streak, 0.35)
    return img


def _disc(img: Image.Image, cx: int, cy: int, r: int, color, rim=None) -> None:
    px = img.load()
    for y in range(cy - r - 1, cy + r + 2):
        for x in range(cx - r - 1, cx + r + 2):
            d = math.hypot(x - cx, y - cy)
            if d <= r:
                px[x, y] = color
            elif rim is not None and d <= r + 1.2:
                px[x, y] = rim


def _dunes(img: Image.Image, base_y: int, amp: int, color, seed: int, period: float) -> None:
    px = img.load()
    rng = random.Random(seed)
    phase = rng.uniform(0, math.tau)
    for x in range(img.width):
        top = base_y - int(amp * (0.6 * math.sin(x / period + phase) + 0.4 * math.sin(x / (period * 0.43) + phase * 2)))
        for y in range(max(0, top), img.height):
            px[x, y] = color


def generate_backgrounds() -> None:
    # Desert: hot blue sky, white sun, layered dunes on the horizon
    desert = _sky(top=(72, 158, 224), bottom=(176, 222, 240), streak=(236, 248, 252), seed=7)
    _disc(desert, 520, 70, 26, (255, 246, 214), rim=(252, 230, 170))
    _dunes(desert, 330, 18, (232, 206, 150), seed=3, period=70)
    _dunes(desert, 350, 12, (214, 178, 118), seed=5, period=45)
    desert.save(os.path.join(IMG_DIR, "background-desert.png"))
    # Mars: butterscotch sky, two small moons, red mesas on the horizon
    mars = _sky(top=(224, 150, 104), bottom=(240, 190, 140), streak=(252, 214, 170), seed=11)
    _disc(mars, 120, 64, 9, (238, 220, 200), rim=(214, 180, 150))
    _disc(mars, 470, 110, 5, (230, 210, 190), rim=(210, 170, 140))
    _dunes(mars, 330, 22, (196, 116, 84), seed=9, period=30)
    _dunes(mars, 352, 10, (172, 92, 66), seed=13, period=55)
    mars.save(os.path.join(IMG_DIR, "background-mars.png"))
    print("backgrounds 'background-desert.png', 'background-mars.png' generated")


def make_preview(path: str, scale: int = 8) -> None:
    """Montage: each tile set laid out as a small island, plus the decor."""
    rows = []
    for name in TILESETS:
        tiles = [Image.open(os.path.join(TILE_DIR, name, f"{v}.png")) for v in range(9)]
        # 5x3 island using the autotile layout
        layout = [[0, 1, 1, 1, 2], [7, 8, 8, 8, 3], [6, 5, 5, 5, 4]]
        island = Image.new("RGB", (5 * T, 3 * T), (40, 44, 52))
        for y, r in enumerate(layout):
            for x, v in enumerate(r):
                island.paste(tiles[v], (x * T, y * T))
        rows.append(island)
    decor = [Image.open(os.path.join(TILE_DIR, rel)) for rel in {**DECOR, **LARGE_DECOR}]
    w = max(max(r.width for r in rows), sum(d.width + 2 for d in decor))
    h = sum(r.height + 4 for r in rows) + max(d.height for d in decor)
    canvas = Image.new("RGB", (w, h), (40, 44, 52))
    y = 0
    for r in rows:
        canvas.paste(r, (0, y))
        y += r.height + 4
    x = 0
    for d in decor:
        canvas.paste(d, (x, y))
        x += d.width + 2
    canvas = canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)
    canvas.save(path)
    print(f"preview saved: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None, help="optional montage output path")
    args = ap.parse_args()
    generate_tiles()
    generate_decor()
    generate_backgrounds()
    if args.preview:
        make_preview(args.preview)
