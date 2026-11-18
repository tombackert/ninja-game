"""Pixel art generator for the store expansion (weapon sprites).

Player skins are drawn by tools/gen_skins.py.

The checkpoint banner (tiles/collectables/checkpoint, furled and hoisted)
is drawn the same way. `--only checkpoint` writes just those.

Weapon sprites are small hand-authored pixel grids in the scale of the
existing `gun.png` (5x3) / `projectile.png` (6x4). Pure black (0,0,0) is
the transparency colorkey used by AssetManager, so sprites avoid it except
for intentionally transparent pixels.

Usage:
    python tools/gen_pixel_art.py [--preview /path/to/montage.png]
"""

from __future__ import annotations

import argparse
import os

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(REPO, "data", "images")

# --- Weapon / effect sprites -------------------------------------------------
# Grid legend: '.' = transparent (black colorkey), letters = palette entries.
SPRITE_COLORS = {
    "K": (75, 78, 90),  # gun metal dark
    "G": (120, 124, 138),  # gun metal light
    "B": (110, 70, 35),  # wood
    "S": (200, 205, 215),  # steel / blade
    "W": (245, 248, 252),  # white tip / gleam
    "H": (140, 96, 40),  # hilt
    "Y": (214, 168, 44),  # gold guard
    "C": (170, 220, 250),  # slash cyan
    "D": (16, 40, 64),  # dark blue-ish (visible on black via colorkey offset)
    "P": (92, 62, 38),  # pole wood, shadow side
    "Q": (150, 108, 62),  # pole wood, lit side
    "R": (78, 80, 94),  # stone base, dark
    "T": (126, 128, 142),  # stone base, light
    "A": (118, 114, 126),  # furled cloth
    "a": (80, 76, 90),  # furled cloth, folds
    "E": (40, 184, 158),  # banner teal
    "e": (22, 118, 104),  # banner teal, shade
    "L": (148, 236, 212),  # banner teal, light
}

SPRITES = {
    # Long barrel + angled stock; reads as a rifle beside the 14x18 ninja.
    "rifle.png": [
        ".KGGGGGGGGG",
        "BBKKKKKGG..",
        "BB.........",
    ],
    # Katana held forward: brown hilt, gold guard, steel blade, white tip.
    "sword.png": [
        "...........W",
        "..YSSSSSSSW.",
        "HHY.........",
    ],
    # Crescent slash VFX (rendered ~6 frames after a swing).
    "slash.png": [
        ".....CC.",
        "...CCWC.",
        "..CWWC..",
        ".CWWC...",
        ".CWC....",
        ".CWC....",
        ".CWWC...",
        "..CWWC..",
        "...CCWC.",
        ".....CC.",
    ],
    # 4-point shuriken; rotated at render time while flying.
    "star.png": [
        "...W...",
        "...S...",
        "...S...",
        "WSSKSSW",
        "...S...",
        "...S...",
        "...W...",
    ],
    # Grapple hook claw (rope is drawn as a line in code).
    "hook.png": [
        ".S...S.",
        ".S...S.",
        ".SS.SS.",
        "..SSS..",
        "...S...",
        "...K...",
    ],
}


_POLE = "....QP.........."
_BASE = ["...RTTR.........", "..RTTTTR........", "..RRRRRR........"]
# Checkpoint banner (16x32, drawn from its top-left; the lower half stands
# on the ground): 0 furled at the foot of the pole, 1 hoisted once touched.
CHECKPOINT = {
    "tiles/collectables/checkpoint/0.png": [
        "....aa..........",
        "....aa..........",
    ]
    + [_POLE] * 17
    + [
        "....QPAa........",
        "....QPAAa.......",
        "....QPAaAa......",
        "....QPAAaA......",
        "....QPaAAa......",
        "....QPAaAa......",
        "....QPAAa.......",
        "....QPAa........",
        "....QPa.........",
        _POLE,
    ]
    + _BASE,
    "tiles/collectables/checkpoint/1.png": [
        "....YY..........",
        "....YY..........",
        "....QPLEEEEEEEe.",
        "....QPLEEEEEEEe.",
        "....QPLEEWWEEEe.",
        "....QPLEWLLWEEe.",
        "....QPLEWLLWEEe.",
        "....QPLEEWWEEEe.",
        "....QPLEEEEEEEe.",
        "....QPLEEEEEEEe.",
        "....QPLEEEeEEEe.",
        "....QPLEEe.eEEe.",
        "....QPLEe...eEe.",
        "....QPLe.....ee.",
    ]
    + [_POLE] * 15
    + _BASE,
}
SPRITES.update(CHECKPOINT)


def generate_sprites(only=None) -> None:
    for name, grid in SPRITES.items():
        if only is not None and name not in only:
            continue
        w = max(len(r) for r in grid)
        h = len(grid)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch == ".":
                    continue
                img.putpixel((x, y), SPRITE_COLORS[ch] + (255,))
        os.makedirs(os.path.dirname(os.path.join(IMG_DIR, name)), exist_ok=True)
        img.save(os.path.join(IMG_DIR, name))
        print(f"sprite '{name}' ({w}x{h}) generated")


def make_preview(path: str, scale: int = 8) -> None:
    """Montage of all weapon sprites."""
    cells = []
    for name in SPRITES:
        cells.append((name, Image.open(os.path.join(IMG_DIR, name)).convert("RGBA")))

    cell_w = max(im.width for _, im in cells) + 2
    cell_h = max(im.height for _, im in cells) + 2
    cols = 7
    rows = (len(cells) + cols - 1) // cols
    canvas = Image.new("RGBA", (cols * cell_w, rows * cell_h), (40, 44, 52, 255))
    for i, (_, im) in enumerate(cells):
        x = (i % cols) * cell_w + 1
        y = (i // cols) * cell_h + 1
        canvas.paste(im, (x, y), im)
    canvas = canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)
    canvas.save(path)
    print(f"preview saved: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None, help="optional montage output path")
    ap.add_argument("--only", choices=["checkpoint"], default=None, help="write only these sprites")
    args = ap.parse_args()
    if args.only == "checkpoint":
        generate_sprites(only=CHECKPOINT)
    else:
        generate_sprites()
    if args.preview:
        make_preview(args.preview)
