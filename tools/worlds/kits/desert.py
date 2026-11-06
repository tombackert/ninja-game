"""Desert world kit (levels 26-30): rock shapes shared by the desert levels.

Hoodoos (caps on stems), balanced rocks and notched stems for Hoodoo Valley,
and the small helpers the other desert levels build their landmarks from.
All take tile coordinates, like tools/worlds/builder.py.
"""

from __future__ import annotations

from tools.worlds.builder import Level, perforate

ROCK = "sand"  # sandstone
CITY = "stone"  # dark blue brick: buildings, statues


def hoodoo(lv: Level, x0: int, x1: int, top: int, stem: tuple, bottom: int, cap_h: int = 2, t: str = ROCK):
    """A hoodoo: a cap from column x0 to x1, `cap_h` rows thick from row `top`
    (its lowest row worn one tile shorter at both ends when it is wide), on a
    stem over columns stem[0]..stem[1] down to row `bottom`."""
    for r in range(cap_h):
        trim = 1 if (r == cap_h - 1 and cap_h > 1 and x1 - x0 >= 5) else 0
        lv.rect(x0 + trim, top + r, x1 - trim, top + r, t)
    lv.rect(stem[0], top + cap_h, stem[1], bottom, t)


def balanced_rock(lv: Level, x: int, top: int, bottom: int, w: int = 2, h: int = 2, t: str = ROCK):
    """A boulder `w` x `h` with its top-left tile at (x, top), balanced on a
    needle one tile wide under it down to row `bottom`."""
    lv.rect(x, top, x + w - 1, top + h - 1, t)
    nx = x + (w - 1) // 2
    lv.rect(nx, top + h, nx, bottom, t)


def notch(lv: Level, x: int, y_top: int, y_bottom: int, solid: int = 2, gap: int = 1):
    """Erosion notches up a stem's face column: `solid` rows of rock, then
    `gap` rows worn through, from y_bottom up (builder.perforate)."""
    perforate(lv, x, y_top, y_bottom, solid=solid, gap=gap)


def dome(lv: Level, cx: int, base: int, radius: int, t: str = CITY):
    """A dome standing on row `base` (its lowest row is base - 1), centered on column cx."""
    for dy in range(radius):
        half = round((radius * radius - dy * dy) ** 0.5)
        lv.rect(cx - half, base - 1 - dy, cx + half, base - 1 - dy, t)
