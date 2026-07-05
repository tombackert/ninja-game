"""Pixel art generator for the store expansion (new skins & weapon sprites).

Skins are palette swaps of the `default` player animation set — the same
technique used for the existing `red` skin — so they match the art style
and animation frame counts exactly.

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
PLAYER_DIR = os.path.join(REPO, "data", "images", "entities", "player")
IMG_DIR = os.path.join(REPO, "data", "images")

# Exact palette of the default skin (verified over all 33 frames).
BODY = (38, 36, 58)  # suit main
SHADOW = (20, 16, 32)  # outline / shadow
HIGHLIGHT = (219, 224, 231)  # face / highlights
ACCENT = (163, 172, 190)  # armor accents
SCARF = (196, 44, 54)  # scarf

# skin name -> {default color: replacement}
SKIN_PALETTES = {
    "gold": {
        BODY: (196, 148, 32),
        SHADOW: (94, 60, 8),
        HIGHLIGHT: (255, 224, 120),
        ACCENT: (232, 190, 70),
        SCARF: (235, 235, 240),
    },
    "platinum": {
        BODY: (150, 160, 172),
        SHADOW: (62, 70, 82),
        HIGHLIGHT: (236, 241, 246),
        ACCENT: (198, 206, 216),
        SCARF: (52, 96, 168),
    },
    "diamond": {
        BODY: (64, 180, 216),
        SHADOW: (18, 80, 110),
        HIGHLIGHT: (215, 248, 255),
        ACCENT: (140, 226, 244),
        SCARF: (148, 84, 204),
    },
    "assassin": {
        BODY: (30, 30, 36),
        SHADOW: (8, 8, 12),
        HIGHLIGHT: (96, 96, 108),
        ACCENT: (58, 58, 68),
        SCARF: (168, 22, 32),
    },
    "berserker": {
        BODY: (122, 44, 32),
        SHADOW: (56, 16, 12),
        HIGHLIGHT: (232, 146, 58),
        ACCENT: (178, 84, 44),
        SCARF: (28, 22, 22),
    },
}

ACTIONS = ["idle", "run", "jump", "slide", "wall_slide"]


def swap_palette(img: Image.Image, mapping: dict) -> Image.Image:
    src = img.convert("RGBA")
    out = Image.new("RGBA", src.size)
    data = []
    for px in src.getdata():
        rgb, a = px[:3], px[3]
        data.append(mapping.get(rgb, rgb) + (a,))
    out.putdata(data)
    return out


def generate_skins() -> None:
    for skin, mapping in SKIN_PALETTES.items():
        for action in ACTIONS:
            src_dir = os.path.join(PLAYER_DIR, "default", action)
            dst_dir = os.path.join(PLAYER_DIR, skin, action)
            os.makedirs(dst_dir, exist_ok=True)
            for name in sorted(os.listdir(src_dir)):
                if not name.endswith(".png"):
                    continue
                img = Image.open(os.path.join(src_dir, name))
                swap_palette(img, mapping).save(os.path.join(dst_dir, name))
        print(f"skin '{skin}' generated")


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


def generate_sprites() -> None:
    for name, grid in SPRITES.items():
        w = max(len(r) for r in grid)
        h = len(grid)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch == ".":
                    continue
                img.putpixel((x, y), SPRITE_COLORS[ch] + (255,))
        img.save(os.path.join(IMG_DIR, name))
        print(f"sprite '{name}' ({w}x{h}) generated")


def make_preview(path: str, scale: int = 8) -> None:
    """Montage: one idle/run frame per skin plus all weapon sprites."""
    cells = []
    for skin in ["default", "red", *SKIN_PALETTES.keys()]:
        for action, frame in [("idle", None), ("run", None)]:
            d = os.path.join(PLAYER_DIR, skin, action)
            name = sorted(os.listdir(d))[0]
            cells.append((f"{skin}/{action}", Image.open(os.path.join(d, name)).convert("RGBA")))
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
    args = ap.parse_args()
    generate_skins()
    generate_sprites()
    if args.preview:
        make_preview(args.preview)
