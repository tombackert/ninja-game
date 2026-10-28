"""Pixel art generator for the water world.

Writes, in the house style of tools/gen_world_tiles.py (same autotile
layout, small hand-authored pixel grids, seeded RNG, so a re-run
reproduces the same files):

- `tiles/reef`: pale wet sand with coral pebbles on slate-blue rock
- `tiles/wreck`: mossy ship planks with nails (the sunken ship)
- `tiles/water`: one icon per water flow (still, right, left, up, down)
  for the editor and the level previews
- `water/surface`, `water/current`, `water/bubbles`: the animated overlays
  the game draws over a level's water (wave crest, current streaks, the
  bubble columns of up-currents)
- `particles/bubble`: the bubbles a swimmer breathes out
- `breath.png`, `breath-low.png`: the breath meter's bubble icons
- `entities/player/<skin>/swim`: a 4-frame swim cycle for every skin,
  drawn for the default skin and recolored per skin the way the skins
  are (palette swaps of default)
- sea decor appended to `tiles/decor` and `tiles/large_decor`
- `background-lagoon.png` (above the sea) and `background-deep.png`
  (under it)

Pure black (0, 0, 0) is the transparency colorkey used by AssetManager.

Usage:
    python tools/gen_water_world.py [--preview /path/to/montage.png]
"""

from __future__ import annotations

import argparse
import math
import os
import random
from collections import Counter

from PIL import Image

from gen_world_tiles import IMG_DIR, TILE_DIR, TRANSPARENT, T, _disc, _lerp, _sky, build_tile

PLAYER_DIR = os.path.join(IMG_DIR, "entities", "player")
WATER_DIR = os.path.join(IMG_DIR, "water")

# --- Tile sets ------------------------------------------------------------------

REEF = {
    "palette": {
        "W": (238, 228, 196),  # sun-bleached sand
        "S": (214, 198, 156),  # wet sand
        "T": (184, 166, 122),  # sand shade
        "P": (240, 128, 136),  # coral pebble
        "U": (104, 120, 130),  # wet shadow
        "B": (62, 84, 104),  # slate rock body
        "D": (44, 60, 80),  # crack
        "L": (90, 114, 134),  # lit rock
        "G": (104, 168, 120),  # algae
    },
    "top": [
        "WSWWWSWWSWWWWSWW",
        "SWSSWSSPSSWSSWSS",
        "SSTSSSSSSSTSSSPS",
        "TSSPTSSSTSSSTSST",
        "UTTSUTTSUUTTSUTT",
        "BUUTBUUUBBUUUBUU",
        "BBUBBBBUBBBBUBBB",
        "BBBBBBBBBBBBBBBB",
    ],
    "edge": [
        "BLLLG",
        "BDLLL",
        "BLLGL",
        "DLLLL",
        "BBLLG",
        "BLLDL",
        "BLLLL",
        "BDLLG",
        "BLLLL",
        "DLGLL",
        "BLLLL",
        "BBLLG",
        "BLDLL",
        "BLLLL",
        "DLLGL",
        "BBLLL",
    ],
    "strata": [(4, 3, 6), (10, 9, 13), (13, 2, 3)],
    "strata_color": "D",
    "body": "B",
}

# Planks: seams every 5 rows, butt joints staggered between them
_PLANK_SEAMS = [(3, 0, 15), (8, 0, 15), (13, 0, 15)]
_PLANK_JOINTS = [(r, 5, 5) for r in range(0, 3)] + [(r, 11, 11) for r in range(4, 8)]
_PLANK_JOINTS += [(r, 3, 3) for r in range(9, 13)] + [(r, 9, 9) for r in range(14, 16)]

WRECK = {
    "palette": {
        "W": (156, 196, 124),  # moss highlight
        "S": (110, 152, 96),  # moss
        "T": (80, 118, 76),  # moss shade
        "U": (88, 60, 40),  # wood shadow
        "B": (124, 86, 54),  # plank
        "D": (74, 50, 32),  # seam
        "L": (156, 112, 70),  # lit plank edge
        "N": (186, 182, 168),  # nail head
    },
    "top": [
        "WSWWSWWWSWWSWWSW",
        "SSWSSSSWSSSWSSSS",
        "TSSTSSTSSTSSSTST",
        "UTTUTTUTUUTTUTTU",
        "LLLLLLLLLLLLLLLL",
        "BBNBBBBBBBBBNBBB",
        "BBBBBBBBBBBBBBBB",
        "DDDDDDDDDDDDDDDD",
    ],
    "edge": [
        "BBLLU",
        "BBLLU",
        "BBLNU",
        "DDDDU",
        "BBLLU",
        "BBLLU",
        "BBLLU",
        "BBLNU",
        "DDDDU",
        "BBLLU",
        "BBLLU",
        "BBLLU",
        "BBLNU",
        "DDDDU",
        "BBLLU",
        "BBLLU",
    ],
    "strata": _PLANK_SEAMS + _PLANK_JOINTS,
    "strata_color": "D",
    "body": "B",
}

TILESETS = {"reef": REEF, "wreck": WRECK}


def generate_tiles() -> None:
    for name, spec in TILESETS.items():
        out = os.path.join(TILE_DIR, name)
        os.makedirs(out, exist_ok=True)
        for v in range(9):
            build_tile(spec, v).save(os.path.join(out, f"{v}.png"))
        print(f"tile set '{name}' generated (9 variants)")


# --- Pixel grids -------------------------------------------------------------------
# '.' = transparent; letters index COLORS.
COLORS = {
    # sea life
    "G": (70, 150, 96),  # seaweed
    "g": (40, 104, 72),  # seaweed shade
    "h": (140, 206, 130),  # seaweed highlight
    "K": (96, 128, 52),  # kelp
    "k": (64, 92, 40),  # kelp shade
    "l": (150, 178, 80),  # kelp highlight
    "c": (240, 118, 142),  # coral
    "C": (196, 74, 110),  # coral shade
    "q": (255, 180, 196),  # coral tip
    "o": (248, 150, 70),  # starfish / anemone orange
    "O": (206, 100, 44),  # orange shade
    "y": (252, 214, 140),  # shell
    "Y": (214, 168, 100),  # shell shade
    "m": (150, 96, 196),  # anemone purple
    "M": (104, 62, 150),  # anemone shade
    # metal and wood
    "i": (120, 132, 140),  # iron
    "I": (76, 86, 96),  # iron shade
    "j": (176, 186, 190),  # iron highlight
    "r": (150, 92, 60),  # rust
    "w": (132, 88, 52),  # chest wood
    "W": (92, 60, 36),  # chest wood shade
    "u": (232, 196, 80),  # gold
    "U": (176, 132, 40),  # gold shade
    "z": (255, 246, 190),  # gold gleam
    # water and bubbles
    "f": (226, 244, 255),  # foam
    "s": (160, 214, 244),  # crest
    "d": (98, 172, 222),  # crest shade
    "a": (150, 206, 236),  # streak
    "b": (178, 226, 250),  # bubble rim
    "B": (238, 250, 255),  # bubble gleam
    "e": (232, 92, 84),  # low breath
    "E": (255, 196, 186),  # low breath gleam
}


def grid_image(grid: list[str]) -> Image.Image:
    w = max(len(r) for r in grid)
    img = Image.new("RGB", (w, len(grid)), TRANSPARENT)
    px = img.load()
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch in COLORS:
                px[x, y] = COLORS[ch]
    return img


DECOR = {
    # Seaweed fronds (16x16, stands on the tile below like the flowers)
    "decor/8.png": [
        "................",
        "................",
        "................",
        "........h.......",
        ".......hG.......",
        "...h...hG.......",
        "...hG...Gg......",
        "....Gg..hG...h..",
        "....hG.hGg..hG..",
        "...hGg.hG...Gg..",
        "...hG...Gg.hG...",
        "....Gg..hG.hGg..",
        "....hG.hGg..hG..",
        "...hGg.hG..hGg..",
        "...hG..hGg.hG...",
        "...gG..gGg.gGg..",
    ],
    # Branching pink coral
    "decor/9.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "......q.....q...",
        "..q...c...q.c...",
        "..c..qc...c.C...",
        "..cC.cC.q.cC....",
        "...cCcC.c.c..q..",
        "....ccC.cCc..c..",
        ".....cCcCc..cC..",
        "......ccCcccC...",
        ".......cCcC.....",
        ".......cCC......",
        "......CCCCC.....",
    ],
    # Starfish and a shell
    "decor/10.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "....o...........",
        "....o......yyy..",
        "..oooOo...yYyYy.",
        "...oOo....yYyYy.",
        "...o.o....YyYyY.",
        "..o...o....YYY..",
        "................",
    ],
    # Sea anemone
    "decor/11.png": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "....o..o.o..o...",
        ".....o.o.o.o....",
        "...o.oOoOoOo.o..",
        "....oOoOoOoOo...",
        ".....mmmmmmm....",
        "......mMmMm.....",
        "......mmMmm.....",
        ".....mMmMmMm....",
        ".....MMMMMMM....",
    ],
}

LARGE_DECOR = {
    # Tall kelp (offgrid decor)
    "large_decor/6.png": [
        ".....l.......",
        "....lK.......",
        "....lKk......",
        ".....Kk..l...",
        ".....lKk.lK..",
        "......lK.Kk..",
        "......lKkK...",
        ".l....lKk....",
        ".lK...Kk.....",
        "..Kk.lKk.....",
        "..lK.lK......",
        "...KklKk.....",
        "....lKk......",
        "....lKk..l...",
        ".....lKk.lK..",
        "......lK.Kk..",
        "......lKkK...",
        "......lKk....",
        ".....lKk.....",
        "..l..lK......",
        "..lK.lKk.....",
        "...KklKk.....",
        "....lKk......",
        "....lKk......",
        ".....lKk..l..",
        "......lK.lK..",
        "......lKkKk..",
        "......lKk....",
        ".....lKk.....",
        ".l...lK......",
        ".lK..lKk.....",
        "..KkllKk.....",
        "...lKKk......",
        "....lKk......",
        ".....lKk.....",
        "......lK.....",
        "......lKk....",
        ".....lKk.....",
        ".....lK......",
        ".....lKk.....",
        "......lK.....",
        ".....kKKk....",
    ],
    # Fan coral
    "large_decor/7.png": [
        "........q.q.q.....q.......",
        ".....q.qcqcqc.q..qcq......",
        "....qcqcccccccqcqccc..q...",
        "...qcccCccCccccccCccq.cq..",
        "..qccCcccCcccCccCccccqcc..",
        "..ccCccCccCccCccCcccCccc..",
        "...ccCcCccCcCccCcCcCccc...",
        "....cCcCcCcCcCcCcCcCcc....",
        ".....ccCcCcCcCcCcCcc......",
        "......cCcCcCcCcCcc.....q..",
        ".......ccCcCcCccc.....qc..",
        "........ccCcCcc......qcC..",
        ".........cCcCc......qcC...",
        "..........cCc.....qccC....",
        "..........cCc...qccC......",
        "..........cCccccCC........",
        ".........CcCCCCC..........",
        "........CCCCCCCC..........",
    ],
    # Half-buried anchor
    "large_decor/8.png": [
        ".......jii.......",
        "......jI.Ii......",
        "......ji.ji......",
        ".......jii.......",
        "...jiiiiiiiiii...",
        "...IIIIjiIIIII...",
        ".......jir.......",
        ".......jiI.......",
        ".......jiI.......",
        ".......jrI.......",
        ".......jiI.......",
        ".......jiI.......",
        ".......jiI.......",
        ".......jir.......",
        ".j.....jiI.....j.",
        ".ji....jiI....ji.",
        ".jiI...jiI...jiI.",
        "..jiI..jiI..jiI..",
        "...jiiijiIiiiI...",
        "....IIrjiIrII....",
        ".YyYyYyYyYyYyYyY.",
        "YyYyYyYyYyYyYyYyY",
    ],
    # Treasure chest spilling gold
    "large_decor/9.png": [
        "...wwwwwwwwwwww...",
        "..wwWwwwwwwwWwww..",
        ".wwwWwwwwwwwWwwww.",
        ".UUUUUUUUUUUUUUUU.",
        ".wwwWwwwuUwwWwwww.",
        ".wwwWwwwUUwwWwwww.",
        ".UUUUUUUUUUUUUUUU.",
        ".wwwWwwwwwwwWwwww.",
        ".wwwWwwwwwwwWwwwwz",
        ".WWWWWWWWWWWWWWWuu",
        "...............uUu",
        "..............uzuUu",
        "............uuUuUuU",
    ],
}


def generate_decor() -> None:
    for rel, grid in {**DECOR, **LARGE_DECOR}.items():
        grid_image(grid).save(os.path.join(TILE_DIR, rel))
        print(f"decor '{rel}' generated")


# --- Water ---------------------------------------------------------------------------
# The game draws water as a translucent blue layer over the level (see
# scripts/water.py); these overlays add the moving parts, each frame shifted
# by 4 px so 4 frames make a seamless 16 px cycle.

SURFACE = [  # wave crest, 16 px period
    "...ff......fff..",
    "ffssffsf..ffssff",
    "ssddssdsssssddss",
    "d..d.dd.d..d.dd.",
]

CURRENT = [  # flow to the right: streaks of different lengths
    "................",
    "...aaaa.........",
    "................",
    "................",
    "..........aaaaa.",
    "................",
    "................",
    "aa..............",
    "...........aaa..",
    "................",
    "....aaaaa.......",
    "................",
    "................",
    ".............aaa",
    "aaa.............",
    "................",
]

BUBBLES = [  # up-current: rising bubbles, 16 px period
    "................",
    "....b...........",
    "...bBb......b...",
    "....b......bBb..",
    "............b...",
    "................",
    "......b.........",
    "................",
    "..........bb....",
    ".b.......bBBb...",
    "bBb......bBBb...",
    ".b........bb....",
    "................",
    ".....b..........",
    "....bBb.........",
    ".....b..........",
]


def _shift(grid: list[str], dx: int, dy: int) -> list[str]:
    h, w = len(grid), len(grid[0])
    return ["".join(grid[(y - dy) % h][(x - dx) % w] for x in range(w)) for y in range(h)]


def generate_water() -> None:
    for sub, grid, step in (("surface", SURFACE, (4, 0)), ("current", CURRENT, (4, 0)), ("bubbles", BUBBLES, (0, -4))):
        out = os.path.join(WATER_DIR, sub)
        os.makedirs(out, exist_ok=True)
        for f in range(4):
            grid_image(_shift(grid, step[0] * f, step[1] * f)).save(os.path.join(out, f"{f}.png"))
    print("water overlays generated (surface, current, bubbles: 4 frames each)")

    # Icons per flow for the editor and previews: water body with a marker
    out = os.path.join(TILE_DIR, "water")
    os.makedirs(out, exist_ok=True)
    body, deep, mark = (52, 128, 196), (40, 104, 170), (190, 230, 250)
    arrow_right = [(4, 7), (5, 7), (6, 7), (7, 7), (8, 7), (9, 7), (10, 7), (9, 6), (8, 5), (9, 8), (8, 9)]
    for flow in range(5):
        img = Image.new("RGB", (T, T), body)
        px = img.load()
        for y in range(T):
            for x in range(T):
                if (x + y) % 8 == 0:
                    px[x, y] = deep
        if flow:
            for x, y in arrow_right:
                pt = {1: (x, y), 2: (15 - x, y), 3: (y, 15 - x), 4: (y, x)}[flow]
                px[pt] = mark
        img.save(os.path.join(out, f"{flow}.png"))
    print("water icons generated (5 flows)")


BUBBLE_FRAMES = [
    ["...", ".B.", "..."],
    ["....", ".bB.", ".bb.", "...."],
    [".....", "..b..", ".bBb.", "..b..", "....."],
    [".....", ".bbb.", "bB..b", "b...b", ".bbb."],
    ["......", ".bbbb.", "bB...b", "b....b", "b....b", ".bbbb."],
    ["......", "B....B", "..b...", "...b..", "B....B", "......"],
]

BREATH = [".bbb.", "bBB.b", "bB..b", "b...b", ".bbb."]


def generate_bubbles() -> None:
    out = os.path.join(IMG_DIR, "particles", "bubble")
    os.makedirs(out, exist_ok=True)
    for i, grid in enumerate(BUBBLE_FRAMES):
        frame = Image.new("RGB", (7, 7), TRANSPARENT)  # centered like the other particles
        g = grid_image(grid)
        frame.paste(g, ((7 - g.width) // 2, (7 - g.height) // 2))
        frame.save(os.path.join(out, f"{i}.png"))
    grid_image(BREATH).save(os.path.join(IMG_DIR, "breath.png"))
    low = [r.replace("b", "e").replace("B", "E") for r in BREATH]
    grid_image(low).save(os.path.join(IMG_DIR, "breath-low.png"))
    print("bubble particle (6 frames) and breath icons generated")


# --- Swim cycle -----------------------------------------------------------------------
# Default skin colors: B suit, S shadow, H face/highlights, A armor, R scarf.
NINJA = {
    "B": (38, 36, 58),
    "S": (20, 16, 32),
    "H": (219, 224, 231),
    "A": (163, 172, 190),
    "R": (196, 44, 54),
}

_HEAD = [
    "..............",
    "..............",
    ".....HHHH.....",
    "....RRRRRR....",
]

SWIM = [
    # Arm reaching forward, legs scissored wide, scarf streaming back
    _HEAD
    + [
        "..RRAAAASA....",
        "....HHHHHH....",
        ".....HHHH.....",
        ".....BAAB.....",
        "....BBBABBBB..",
        "...BBBBBBB.B..",
        "....BBBBBB....",
        "....SBBBBS....",
        "....AHHHHA....",
        "....BBBBSS....",
        "...BBBB.SSS...",
        "..BBB....SSS..",
        ".BB.......SS..",
        "..............",
    ],
    # Arm sweeping down, legs closing
    _HEAD
    + [
        "...RAAAASA....",
        "..R.HHHHHH....",
        ".....HHHH.....",
        ".....BAAB.....",
        "....BBBABB....",
        "....BBBBBBB...",
        "....BBBBBB.B..",
        "....SBBBBS....",
        "....AHHHHA....",
        "....BBBBSS....",
        "....BBB.SS....",
        "...BBB..SSS...",
        "...BB....SS...",
        "..............",
    ],
    # Arm pulled back, legs crossed
    _HEAD
    + [
        "..RRAAAASA....",
        "....HHHHHH....",
        ".....HHHH.....",
        ".....BAAB.....",
        "..BBBBBABB....",
        "...B.BBBBB....",
        "....BBBBBB....",
        "....SBBBBS....",
        "....AHHHHA....",
        "....BBBBSS....",
        "....BBSSSS....",
        "....BSSBBB....",
        "....SS..BBB...",
        "..............",
    ],
    # Arm coming forward again, legs opening
    _HEAD
    + [
        "...RAAAASA....",
        "..R.HHHHHH....",
        ".....HHHH.....",
        ".....BAAB.....",
        "....BBBABB....",
        "...BBBBBBBB...",
        "....BBBBBB....",
        "....SBBBBS....",
        "....AHHHHA....",
        "....BBBBSS....",
        "....BBB.SSS...",
        "...BBB...SS...",
        "..BB......S...",
        "..............",
    ],
]


def _skin_palette(skin: str) -> dict:
    """Default color -> this skin's color, read off the skin's own frames.

    Most skins are exact palette swaps of default; for the hand-drawn ones
    the most common counterpart of each color wins.
    """
    votes: dict = {c: Counter() for c in NINJA.values()}
    for anim in ("idle", "run", "jump"):
        d_dir = os.path.join(PLAYER_DIR, "default", anim)
        s_dir = os.path.join(PLAYER_DIR, skin, anim)
        for name in sorted(os.listdir(d_dir)):
            d = Image.open(os.path.join(d_dir, name)).convert("RGB").load()
            s_img = Image.open(os.path.join(s_dir, name)).convert("RGB")
            if s_img.size != (14, 18):  # cropped differently (red's run): not aligned
                continue
            s = s_img.load()
            for y in range(18):
                for x in range(14):
                    if d[x, y] in votes:
                        votes[d[x, y]][s[x, y]] += 1
    return {c: v.most_common(1)[0][0] for c, v in votes.items()}


def generate_swim() -> None:
    skins = sorted(d for d in os.listdir(PLAYER_DIR) if os.path.isdir(os.path.join(PLAYER_DIR, d)))
    for skin in skins:
        palette = {k: c for k, c in NINJA.items()}
        if skin != "default":
            mapping = _skin_palette(skin)
            palette = {k: mapping[c] for k, c in NINJA.items()}
        out = os.path.join(PLAYER_DIR, skin, "swim")
        os.makedirs(out, exist_ok=True)
        for i, grid in enumerate(SWIM):
            img = Image.new("RGBA", (14, 18), (0, 0, 0, 255))
            px = img.load()
            for y, row in enumerate(grid):
                for x, ch in enumerate(row):
                    if ch in palette:
                        px[x, y] = palette[ch] + (255,)
            img.save(os.path.join(out, f"{i}.png"))
    print(f"swim cycle generated for {len(skins)} skins (4 frames)")


# --- Backgrounds -------------------------------------------------------------------------
# 640x480 like the other skies (the renderer shows the top 640x360).


def _rays(img: Image.Image, color, seed: int, count: int, fade_to: int) -> None:
    """Slanted shafts of sunlight from the top, fading out by row `fade_to`."""
    px = img.load()
    rng = random.Random(seed)
    for _ in range(count):
        x0 = rng.randint(-120, 600)
        width = rng.randint(14, 40)
        slope = rng.uniform(0.35, 0.55)
        strength = rng.uniform(0.10, 0.20)
        for y in range(min(fade_to, img.height)):
            t = strength * (1 - y / fade_to)
            xc = x0 + slope * y
            for x in range(int(xc), int(xc + width)):
                if 0 <= x < img.width:
                    px[x, y] = _lerp(px[x, y], color, t)


def _silhouette(img: Image.Image, base_y: int, amp: int, color, seed: int, period: float, spikes: int = 0) -> None:
    """Rolling rock ridge, optionally with kelp-like spikes standing on it."""
    px = img.load()
    rng = random.Random(seed)
    phase = rng.uniform(0, math.tau)
    tops = []
    for x in range(img.width):
        top = base_y - int(amp * (0.6 * math.sin(x / period + phase) + 0.4 * math.sin(x / (period * 0.37) + phase)))
        tops.append(top)
        for y in range(max(0, top), img.height):
            px[x, y] = color
    for _ in range(spikes):
        x = rng.randint(0, img.width - 3)
        h = rng.randint(30, 90)
        sway = rng.uniform(4, 9)
        for dy in range(h):
            xx = x + int(sway * math.sin(dy / 14))
            for w in range(3 if dy < h * 0.7 else 2):
                if 0 <= xx + w < img.width and tops[x] - dy >= 0:
                    px[xx + w, tops[x] - dy] = color


def generate_backgrounds() -> None:
    # Lagoon: tropical sky, sun, a reef island and the open sea on the horizon
    lagoon = _sky(top=(70, 176, 226), bottom=(190, 236, 244), streak=(240, 252, 252), seed=17)
    _disc(lagoon, 470, 74, 24, (255, 250, 220), rim=(255, 236, 170))
    _silhouette(lagoon, 312, 10, (98, 170, 140), seed=19, period=60)
    px = lagoon.load()
    for y in range(318, 480):  # sea in flat bands, lighter at the horizon
        col = _lerp((84, 186, 210), (36, 120, 176), min(1.0, (y - 318) / 60))
        for x in range(lagoon.width):
            px[x, y] = col
    rng = random.Random(23)
    for _ in range(140):  # glints on the water
        x, y = rng.randint(0, 637), rng.randint(320, 360)
        for dx in range(rng.randint(2, 4)):
            px[x + dx, y] = (210, 244, 250)
    lagoon.save(os.path.join(IMG_DIR, "background-lagoon.png"))
    # Deep: sunlit water fading into the dark, light shafts, reef ridges
    deep = _sky(top=(52, 150, 196), bottom=(10, 40, 84), streak=(90, 176, 214), seed=29)
    _rays(deep, (200, 240, 250), seed=31, count=7, fade_to=300)
    _silhouette(deep, 318, 16, (22, 74, 110), seed=37, period=40, spikes=9)
    _silhouette(deep, 344, 10, (12, 48, 82), seed=41, period=25, spikes=6)
    rng = random.Random(43)
    px = deep.load()
    for _ in range(36):  # drifting bubbles
        x, y, r = rng.randint(4, 634), rng.randint(20, 300), rng.choice((1, 1, 2))
        for a in range(0, 360, 30):
            px[x + round(r * math.cos(math.radians(a))), y + round(r * math.sin(math.radians(a)))] = (150, 210, 236)
    deep.save(os.path.join(IMG_DIR, "background-deep.png"))
    print("backgrounds 'background-lagoon.png', 'background-deep.png' generated")


def make_preview(path: str, scale: int = 6) -> None:
    """Montage: both tile sets as islands under water, decor, overlays, swim cycles."""
    blue = (40, 44, 52)
    parts = []
    for name in TILESETS:
        tiles = [Image.open(os.path.join(TILE_DIR, name, f"{v}.png")) for v in range(9)]
        layout = [[0, 1, 1, 1, 2], [7, 8, 8, 8, 3], [6, 5, 5, 5, 4]]
        island = Image.new("RGB", (5 * T, 3 * T), blue)
        for y, r in enumerate(layout):
            for x, v in enumerate(r):
                island.paste(tiles[v], (x * T, y * T), tiles[v].convert("L").point(lambda p: 255 if p else 0))
        parts.append(island)
    for rel in {**DECOR, **LARGE_DECOR}:
        parts.append(Image.open(os.path.join(TILE_DIR, rel)))
    for v in range(5):
        parts.append(Image.open(os.path.join(TILE_DIR, "water", f"{v}.png")))
    for sub in ("surface", "current", "bubbles"):
        parts.append(Image.open(os.path.join(WATER_DIR, sub, "0.png")))
    for i in range(6):
        parts.append(Image.open(os.path.join(IMG_DIR, "particles", "bubble", f"{i}.png")))
    parts.append(Image.open(os.path.join(IMG_DIR, "breath.png")))
    parts.append(Image.open(os.path.join(IMG_DIR, "breath-low.png")))
    for skin in sorted(d for d in os.listdir(PLAYER_DIR) if os.path.isdir(os.path.join(PLAYER_DIR, d))):
        for i in range(4):
            parts.append(Image.open(os.path.join(PLAYER_DIR, skin, "swim", f"{i}.png")).convert("RGB"))
    w = 0
    rows, row, x = [], [], 0
    for p in parts:
        if x + p.width > 300:
            rows.append(row)
            row, x = [], 0
        row.append(p)
        x += p.width + 3
    rows.append(row)
    w = 300
    h = sum(max(p.height for p in r) + 3 for r in rows)
    canvas = Image.new("RGB", (w, h), (34, 96, 150))
    y = 0
    for r in rows:
        x = 0
        for p in r:
            canvas.paste(p, (x, y), p.convert("L").point(lambda v: 255 if v else 0))
            x += p.width + 3
        y += max(q.height for q in r) + 3
    canvas = canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)
    canvas.save(path)
    print(f"preview saved: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None, help="optional montage output path")
    args = ap.parse_args()
    generate_tiles()
    generate_decor()
    generate_water()
    generate_bubbles()
    generate_swim()
    generate_backgrounds()
    if args.preview:
        make_preview(args.preview)
