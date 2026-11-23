"""Mars kit: building blocks shared by the Mars levels (31-35).

All coordinates are tiles; "row" is the solid row a player stands on unless
said otherwise.
"""

from __future__ import annotations

from tools.worlds.builder import Level


def arch(lv: Level, x0: int, x1: int, top: int, under, t=None) -> dict:
    """A rock span from column x0 to x1: solid from row `top` down to row
    `under(x)` in each column. Returns {x: underside row}."""
    rows = {}
    for x in range(x0, x1 + 1):
        rows[x] = under(x)
        lv.rect(x, top, x, rows[x], t)
    return rows


def tooth(lv: Level, x: int, base: int, h: int, w: int = 2, t=None, cap: int = 0):
    """A crag standing on row `base` (its foot), `h` rows tall: too tall to jump.
    Height alone does not block (the dash wall climb takes any sheer face), so
    with `cap` its two top rows overhang that many tiles to the west, the side
    it is come at from: a wall jump off the face under the cap does not rise
    past it."""
    lv.rect(x, base - h, x + w - 1, base - 1, t)
    if cap:
        lv.rect(x - cap, base - h - 1, x + w - 1, base - h, t)
    elif w > 2:
        lv.rect(x, base - h - 1, x + w - 2, base - h - 1, t)


def hook(lv: Level, x: int, top: int, row: int, foot: int = 2, stem: int = 2, east: bool = False, taper=True, t=None):
    """A hanging hook: a stalactite `stem` wide (columns x..x+stem-1) from row
    `top` down to row `row`, where its foot bends out `foot` tiles to the west
    (or to the east): the foot's top is a ledge on `row`, the stem a wall at its
    end. Its upper half is a tile wider on the side away from the foot (unless
    not `taper`). Returns the foot's columns (x0, x1)."""
    lv.rect(x, top, x + stem - 1, row, t)
    if taper and stem > 1 and row - top > 3:
        lv.rect(x - 1 if east else x + stem, top, x - 1 if east else x + stem, top + (row - top) // 2, t)
    x0, x1 = (x + stem, x + stem + foot - 1) if east else (x - foot, x - 1)
    lv.rect(x0, row, x1, row, t)
    return x0, x1
