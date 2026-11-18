"""Pixel art for the enemy kinds and the level hazards.

Enemy kinds (scripts/enemy_kinds.py) are palette swaps of the red default
enemy, the same technique tools/gen_pixel_art.py uses for the player skins,
so each kind reads at a glance by its color:

    gunner  red (the original)   patrol  amber   turret  steel
    chaser  purple               jumper  green   thrower teal

Their spawner tiles (tiles/spawners/<variant>.png, for the editor) are the
same swaps of spawner 1.

Hazards (scripts/hazards.py), 16x16 tiles in the palette of the stone tiles:

    tiles/spikes/0-3.png    spikes pointing up, down, left, right
    tiles/crumble/0-1.png   crumbling block, whole and cracked
    tiles/flamejet/0-3.png  flame jet nozzle opening up, down, left, right

Pure black (0, 0, 0) is the transparency colorkey (AssetManager).

Usage:
    python tools/gen_hazard_art.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(REPO, "data", "images")

RED = (196, 44, 54)
DARK_RED = (120, 31, 44)

# kind -> (main color, shade) replacing the default enemy's red and dark red
ENEMY_PALETTES = {
    "patrol": ((214, 140, 46), (128, 76, 30)),
    "turret": ((128, 138, 156), (70, 76, 94)),
    "chaser": ((150, 62, 196), (84, 34, 114)),
    "jumper": ((70, 168, 78), (34, 96, 46)),
    "thrower": ((44, 170, 180), (22, 96, 108)),
}
SPAWNER_VARIANT = {"patrol": 2, "turret": 3, "chaser": 4, "jumper": 5, "thrower": 6}

OUTLINE = (20, 16, 32)
STEEL = (219, 224, 231)
STEEL_SHADE = (163, 172, 190)
STONE = (57, 58, 86)
STONE_DARK = (38, 36, 58)
STONE_LIGHT = (103, 112, 139)
CLAY = (150, 104, 66)
CLAY_DARK = (96, 62, 40)
CLAY_LIGHT = (196, 150, 98)
EMBER = (232, 106, 36)


def swap(img: Image.Image, mapping: dict) -> Image.Image:
    img = img.convert("RGB")
    img.putdata([mapping.get(p, p) for p in img.getdata()])
    return img


def enemy_kinds() -> list[str]:
    written = []
    base = os.path.join(IMG_DIR, "entities", "enemy")
    spawner = Image.open(os.path.join(IMG_DIR, "tiles", "spawners", "1.png"))
    for kind, (main, shade) in ENEMY_PALETTES.items():
        mapping = {RED: main, DARK_RED: shade}
        for action in ("idle", "run"):
            src = os.path.join(base, action)
            dst = os.path.join(base, kind, action)
            os.makedirs(dst, exist_ok=True)
            for name in sorted(os.listdir(src)):
                if name.endswith(".png"):
                    swap(Image.open(os.path.join(src, name)), mapping).save(os.path.join(dst, name))
                    written.append(os.path.join(dst, name))
        out = os.path.join(IMG_DIR, "tiles", "spawners", f"{SPAWNER_VARIANT[kind]}.png")
        swap(spawner, mapping).save(out)
        written.append(out)
    return written


def _rotations(up: Image.Image) -> list[Image.Image]:
    """The up-facing tile and its down, left, right turns (variant order)."""
    return [
        up,
        up.transpose(Image.Transpose.ROTATE_180),
        up.transpose(Image.Transpose.ROTATE_90),
        up.transpose(Image.Transpose.ROTATE_270),
    ]


def spikes() -> Image.Image:
    """Four steel spikes on a base plate, points up, in the lower half."""
    img = Image.new("RGB", (16, 16), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 14, 15, 15), fill=STONE_DARK)
    d.line((0, 14, 15, 14), fill=STONE_LIGHT)
    for i in range(4):
        x = i * 4
        d.line((x + 1, 7, x + 1, 13), fill=STEEL)  # lit side, up to the tip
        d.line((x + 2, 9, x + 2, 13), fill=STEEL_SHADE)
        d.line((x, 11, x, 13), fill=STEEL_SHADE)
        d.line((x + 3, 12, x + 3, 13), fill=OUTLINE)
    return img


def crumble(cracked: bool) -> Image.Image:
    """A block of loose clay bricks; cracked: split wide open, about to fall."""
    img = Image.new("RGB", (16, 16), CLAY)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 15, 15), outline=CLAY_DARK)
    d.line((1, 1, 14, 1), fill=CLAY_LIGHT)
    for y in (5, 10):
        d.line((1, y, 14, y), fill=CLAY_DARK)
    for x, y0, y1 in ((7, 1, 4), (4, 6, 9), (11, 6, 9), (7, 11, 14)):
        d.line((x, y0, x, y1), fill=CLAY_DARK)
    if cracked:
        crack = [(3, 0), (5, 3), (4, 6), (7, 8), (6, 11), (9, 13), (8, 15)]
        d.line(crack, fill=OUTLINE)
        d.line([(12, 0), (11, 4), (13, 7)], fill=OUTLINE)
        d.line([(1, 9), (3, 12)], fill=OUTLINE)
    return img


def flamejet() -> Image.Image:
    """A stone block with a soot-black nozzle opening up and a glowing mouth."""
    img = Image.new("RGB", (16, 16), STONE)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 15, 15), outline=STONE_DARK)
    d.rectangle((1, 4, 14, 14), fill=STONE_DARK)
    d.line((1, 4, 14, 4), fill=STONE_LIGHT)
    d.rectangle((5, 0, 10, 3), fill=STONE_LIGHT)
    d.rectangle((6, 0, 9, 2), fill=OUTLINE)
    d.line((7, 0, 8, 0), fill=EMBER)
    for x in (3, 12):
        d.point((x, 9), fill=STONE_LIGHT)  # rivets
    return img


def hazards() -> list[str]:
    written = []
    sets = {
        "spikes": _rotations(spikes()),
        "crumble": [crumble(False), crumble(True)],
        "flamejet": _rotations(flamejet()),
    }
    for name, images in sets.items():
        folder = os.path.join(IMG_DIR, "tiles", name)
        os.makedirs(folder, exist_ok=True)
        for i, img in enumerate(images):
            path = os.path.join(folder, f"{i}.png")
            img.save(path)
            written.append(path)
    return written


def main() -> None:
    written = enemy_kinds() + hazards()
    print(f"wrote {len(written)} images")


if __name__ == "__main__":
    main()
