"""Pixel art generator for the store's weapons and gear.

Player skins are drawn by tools/gen_skins.py.

The checkpoint banner (tiles/collectables/checkpoint, furled and hoisted)
is drawn the same way. `--only checkpoint` writes just those.

Weapons and gear (data/images/weapons, data/images/gear, star.png) are
hand-authored pixel grids with a dark outline so they read against every
background at the ninja's 14x18 scale. The sword slash (weapons/slash) is
computed: a crescent that sweeps from top to bottom over 4 frames.
scripts/item_fx.py draws them on the ninja, in a level and in the store.
Pure black (0,0,0) is the transparency colorkey used by AssetManager, so
sprites avoid it except for intentionally transparent pixels.

Usage:
    python tools/gen_pixel_art.py [--preview /path/to/montage.png]
"""

from __future__ import annotations

import argparse
import math
import os

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(REPO, "data", "images")

# --- Weapon / effect sprites -------------------------------------------------
# Grid legend: '.' = transparent (black colorkey), letters = palette entries.
SPRITE_COLORS = {
    "Y": (214, 168, 44),  # gold finial
    "W": (245, 248, 252),  # banner emblem
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

SPRITES: dict = {}


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

# --- Weapons and gear --------------------------------------------------------
# Own palette: a dark outline (O) around shaded metal, wood, lacquer and gold.
ITEM_COLORS = {
    "O": (26, 22, 38),  # outline
    "K": (62, 66, 84),  # steel, shadow
    "G": (112, 120, 140),  # steel
    "S": (176, 186, 206),  # steel, lit
    "W": (244, 248, 255),  # gleam
    "B": (92, 54, 30),  # wood, shadow
    "b": (150, 96, 52),  # wood
    "Y": (240, 190, 60),  # gold
    "y": (170, 116, 30),  # gold, shadow
    "M": (255, 238, 150),  # gold, lit
    "R": (200, 40, 52),  # lacquer red
    "r": (120, 20, 36),  # lacquer red, shadow
    "N": (80, 190, 255),  # energy blue
    "n": (40, 96, 190),  # deep blue
    "C": (150, 232, 255),  # cyan glow
    "c": (64, 150, 222),  # cyan, shadow
    "L": (226, 222, 255),  # moon silver
    "l": (160, 152, 214),  # moon silver, shadow
    "h": (110, 150, 70),  # crate green
    "g": (70, 100, 48),  # crate green, shadow
    "w": (244, 232, 204),  # target cream
}

ITEM_SPRITES = {
    # Pistol, held at the grip (x2, y4)
    "weapons/pistol.png": [
        ".OOOOOOOO.",
        "OSWWWSSSSO",
        "OGGGGGGGKO",
        "OKKbKOOOO.",
        ".ObbOKO...",
        ".OBbOO....",
        ".OBBO.....",
        "..OO......",
    ],
    # Rifle: scope, long barrel, wooden stock against the shoulder
    "weapons/rifle.png": [
        ".......OOOOOO.....",
        "......ONWSSSKO....",
        "OO.....OOKKOO.....",
        "ObOO..OOOOOOOOOOOO",
        "ObbbOOGSWWSSSSSSWO",
        "ObbbbbGGGGGGGGGGKO",
        "OBBbbbKKKKOKKOOOOO",
        "OBBBOOOKbOOOKO....",
        "OOOO..OBbO.OO.....",
        "......OBO.........",
        "......OO..........",
    ],
    # Katana: red-wrapped hilt, gold guard, blade with a gleaming edge
    "weapons/katana.png": [
        ".....OO..........",
        ".OOOOYOOOOOOOOO..",
        "ORrRrYOWSSSSSSSWO",
        "OrRrRYOGGGGGGGOO.",
        ".OOOOYOOOOOOOO...",
        ".....OO..........",
    ],
    # Grappling hook pointing forward: gold rope ring, three prongs
    "weapons/hook.png": [
        "......OO...",
        ".....OWSO..",
        "......OOSO.",
        "OOOOOOOOOSO",
        "OYOGSSSSSWO",
        "OOOOOOOOOSO",
        "......OOSO.",
        ".....OGKO..",
        "......OO...",
    ],
    # Shuriken (players and throwing enemies); spins in flight
    "star.png": [
        "....O....",
        "...OWO...",
        "...OSO...",
        ".OOOSGOO.",
        "OWSSOGGKO",
        ".OOGGKOO.",
        "...OKO...",
        "...OKO...",
        "....O....",
    ],
    # Ammo crate (store card)
    "weapons/ammo.png": [
        ".OWO.OWO.OWO.",
        ".OYO.OYO.OYO.",
        "OOyOOOyOOOyOO",
        "OhhhhhhhhhhgO",
        "OhOOOOOOOOOgO",
        "OhOWWWWWWWOgO",
        "OhOOOOOOOOOgO",
        "OhhhhhhhhhhgO",
        "OgggggggggggO",
        "OOOOOOOOOOOOO",
    ],
    # Straw target the store's weapon cards shoot at
    "weapons/target.png": [
        "..OOOO..",
        ".OwwwwO.",
        "OwRRRRwO",
        "OwRwwRwO",
        "OwRwwRwO",
        "OwRRRRwO",
        ".OwwwwO.",
        "..OOOO..",
        "...ObO..",
        "...ObO..",
        "...ObO..",
        "...OBO..",
        "...ObO..",
        "..OBbBO.",
        ".OBBBBBO",
    ],
    # Shield crest (store icon; in a level it is a bubble)
    "gear/shield.png": [
        "OOOOOOOOO",
        "OWWCCCCcO",
        "OWCNNNNcO",
        "OCNNWNNcO",
        "OCNWWWNcO",
        "OCNNWNNcO",
        ".OcNNNcO.",
        ".OccNccO.",
        "..OcncO..",
        "...OcO...",
        "....O....",
    ],
    # Moon boot: silver with a blue cuff, a gold crescent and a glowing sole
    "gear/moon_boots.png": [
        ".OOOOOO...",
        ".OnnnnO...",
        ".OLLYlO...",
        ".OLYLlO...",
        ".OLYLlO...",
        ".OLLYlOOO.",
        ".OLLLLLLlO",
        ".OLLLLLLlO",
        ".OCCCCCCCO",
        "..OOOOOOO.",
    ],
    # Horseshoe magnet with silver poles
    "gear/magnet.png": [
        "..OOOOO..",
        ".ORRRRRO.",
        "ORRWrrRRO",
        "ORrOOOrRO",
        "ORRO.ORRO",
        "ORRO.ORRO",
        "OSSO.OSSO",
        "OWSO.OWSO",
        "OOOO.OOOO",
    ],
    # Omamori: a red lucky charm pouch with a gold knot and emblem
    "gear/omamori.png": [
        "..OOOO..",
        ".OY..YO.",
        ".OYOOYO.",
        "..OYYO..",
        ".OOYYOO.",
        ".ORRRRO.",
        "ORWRRRrO",
        "ORRYYRrO",
        "ORYMMYrO",
        "ORRYYRrO",
        "ORRRRRrO",
        "OrrrrrrO",
        ".OOOOOO.",
    ],
    # Heart the charm sends up when it grants its extra life
    "gear/heart.png": [
        ".OO.OO.",
        "ORWORRO",
        "ORRRRrO",
        ".ORRrO.",
        "..ORO..",
        "...O...",
    ],
}


# Glyphs drawn as white pixels and outlined automatically
GLYPHS = {
    # "+1" next to the charm's heart
    "gear/plus_one.png": [
        "....W.",
        ".W.WW.",
        "WWW.W.",
        ".W..W.",
        "...WWW",
    ],
}


def _outlined(mask) -> list:
    """Pad a glyph by one pixel and ring its white pixels with the outline."""
    w, h = max(len(r) for r in mask) + 2, len(mask) + 2
    on = {(x + 1, y + 1) for y, row in enumerate(mask) for x, ch in enumerate(row) if ch == "W"}
    near = {(x + dx, y + dy) for x, y in on for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    return ["".join("W" if (x, y) in on else "O" if (x, y) in near else "." for x in range(w)) for y in range(h)]


def _slash_frames() -> list:
    """Sword slash: a crescent sweeping from above to below the blade, then
    fading (4 frames, 13x22, drawn facing right)."""
    w, h = 13, 22
    cx, cy, radius, squash = -4.0, h / 2, 16.0, 0.7
    sweeps = [(-70, -15, 255), (-70, 30, 255), (-70, 70, 255), (-70, 70, 140)]
    frames = []
    for start, end, alpha in sweeps:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(h):
            for x in range(w):
                dx, dy = x + 0.5 - cx, (y + 0.5 - cy) / squash
                r = math.hypot(dx, dy)
                ang = math.degrees(math.atan2(dy, dx))
                if not start <= ang <= end:
                    continue
                # thick in the middle of the swing, thin at its ends
                thick = 1.2 + 3.8 * math.cos(math.radians(ang / 70 * 90))
                depth = radius - r
                if not 0 <= depth <= thick:
                    continue
                lead = end - ang < 14 and alpha == 255
                if depth < 1.1 or lead:
                    col = (255, 255, 255)
                elif depth < thick * 0.6:
                    col = (170, 232, 255)
                else:
                    col = (90, 170, 240)
                a = alpha if depth < thick * 0.6 else alpha * 3 // 4
                img.putpixel((x, y), col + (a,))
        frames.append(img)
    return frames


def _grid_image(grid, colors) -> Image.Image:
    w = max(len(r) for r in grid)
    img = Image.new("RGBA", (w, len(grid)), (0, 0, 0, 0))
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ".":
                img.putpixel((x, y), colors[ch] + (255,))
    return img


def _save(name: str, img: Image.Image) -> None:
    os.makedirs(os.path.dirname(os.path.join(IMG_DIR, name)), exist_ok=True)
    img.save(os.path.join(IMG_DIR, name))
    print(f"sprite '{name}' ({img.width}x{img.height}) generated")


def generate_sprites(only=None) -> None:
    for name, grid in SPRITES.items():
        if only is None or name in only:
            _save(name, _grid_image(grid, SPRITE_COLORS))
    if only is not None:
        return
    for name, grid in ITEM_SPRITES.items():
        _save(name, _grid_image(grid, ITEM_COLORS))
    for name, mask in GLYPHS.items():
        _save(name, _grid_image(_outlined(mask), ITEM_COLORS))
    for i, img in enumerate(_slash_frames()):
        _save(f"weapons/slash/{i}.png", img)


def make_preview(path: str, scale: int = 8) -> None:
    """Montage of all sprites."""
    cells = []
    for name in [*SPRITES, *ITEM_SPRITES, *GLYPHS, *(f"weapons/slash/{i}.png" for i in range(4))]:
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
