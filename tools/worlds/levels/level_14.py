"""Level 14 - Desert (sand, desert sky).

Dunes with quicksand pits, a canyon crossed on sandstone pillars and up a
crack, a great stepped pyramid whose 4-tile steps can only be climbed via
single stone blocks (or a chimney behind a free-standing post), a tomb
labyrinth inside it and an oasis with the flag.
"""

import math

from tools.worlds.builder import Level, Maze, box, perforate, pillar

BOTTOM = 74  # sand reaches down to here (below: the void)


def dunes(lv: Level, x0: int, x1: int, base: int, amp: float, period: float, phase: float = 0.0):
    """Rolling sand surface from x0 to x1; returns {x: surface row}."""
    tops = {}
    for x in range(x0, x1 + 1):
        top = base - round(amp * (math.sin((x + phase) / period) + 0.5 * math.sin((x + phase) / (period * 0.37))))
        lv.rect(x, top, x, BOTTOM)
        tops[x] = top
    return tops


def quicksand(lv: Level, tops: dict, pits):
    """Carve deadly pits into a dune field, with coins over them and route points around."""
    for px, w in pits:
        lv.carve(px, 0, px + w - 1, BOTTOM)
        lv.coins(px, min(tops[px - 1], tops[px + w]) - 3, px + w - 1)
        lv.wp(px - 3, tops[px - 3] - 2, px - 1, tops[px - 1] - 1, ground=True, label=f"before pit {px}")
        lv.wp(px + w, tops[px + w] - 2, px + w + 2, tops[px + w] - 1, ground=True, label=f"after pit {px}")


def build() -> Level:
    lv = Level(14, "sand", background="background-desert.png")

    # --- Dunes with quicksand pits ----------------------------------------------
    tops = dunes(lv, 0, 50, 60, 1.6, 5.0)
    lv.spawn(3, tops[3] - 1)
    quicksand(lv, tops, [(17, 4), (30, 5), (42, 4)])
    for x, v in [(6, 4), (11, 5), (24, 4), (38, 5), (47, 4)]:
        lv.decor(x, tops[x] - 1, v)
    lv.big_decor(14, tops[14] - 1, 3)
    lv.big_decor(27, tops[27] - 1, 4)
    lv.big_decor(36, tops[36] - 1, 3)
    for x in (8, 13, 23, 26, 36, 39, 48):
        lv.enemy(x, tops[x] - 1)
    lv.coins(5, tops[5] - 3, 9, 2)

    # --- Canyon: pillars, a crack chimney, a dash to the plateau ----------------
    rim = tops[50]
    for x, top in [(53, rim + 1), (58, rim - 1), (62, rim), (66, rim - 2)]:
        pillar(lv, x, top, BOTTOM)
        lv.coin(x, top - 2)
        lv.wp(x, top - 1, ground=True, label=f"canyon pillar {x}")
    # crack: two sandstone towers with a 3-wide gap and two rest ledges
    lv.rect(69, rim + 2, 72, BOTTOM)  # ledge block at the foot
    lv.rect(73, 40, 74, BOTTOM)  # left tower
    lv.rect(78, 36, 81, BOTTOM)  # right tower
    lv.carve(73, rim - 2, 74, rim + 1)  # opening into the crack
    lv.rect(75, rim + 2, 77, BOTTOM)  # crack floor
    lv.rect(75, 52, 75, 52)  # rest ledges
    lv.rect(77, 44, 77, 44)
    # upper crack: thin, holed walls
    lv.carve(73, 40, 73, 50)
    perforate(lv, 74, 41, 50, solid=2, gap=1)
    lv.carve(79, 37, 81, 43)
    perforate(lv, 78, 37, 43, solid=2, gap=1)
    lv.enemy(76, rim + 1)
    lv.wp(70, rim + 1, 72, rim + 1, ground=True, label="crack ledge")
    lv.wp(75, rim - 1, 77, rim + 1, ground=True, label="crack floor")
    lv.wp(75, 51, 75, 51, ground=True, label="crack rest 1")
    lv.wp(77, 43, 77, 43, ground=True, label="crack rest 2")
    lv.wp(78, 35, 81, 35, ground=True, label="right tower top")
    lv.coins(76, 56, 76)
    lv.coins(76, 48, 76)
    lv.coins(76, 40, 76)

    # --- Plateau, a 7-tile dash away, and the great pyramid -----------------------
    plateau = 40
    lv.rect(89, plateau, 204, BOTTOM)
    lv.wp(89, plateau - 1, 92, plateau - 1, ground=True, label="plateau edge")
    lv.coins(83, 34, 87, 2)
    for x in (92, 94):
        lv.decor(x, plateau - 1, 5 if x == 92 else 4)
    lv.enemy(91, plateau - 1)
    lv.enemy(94, plateau - 1)

    px0, steps, sw, sh = 96, 8, 5, 4
    for k in range(steps):
        lv.rect(px0 + sw * k, plateau - sh * (k + 1), 196 - sw * k, plateau - 1 - sh * k)
    apex_y = plateau - sh * steps
    aids = ["detached", "far", "chimney", "far", "detached", "chimney", "far", "detached"]
    for k, kind in enumerate(aids):
        face = px0 + sw * k
        foot = plateau - sh * k  # row the face stands on
        if kind == "attached":
            box(lv, face - 1, foot - 2, 1, 1)
        elif kind == "detached":
            box(lv, face - 2, foot - 2, 1, 1)
        elif kind == "far":
            box(lv, face - 3, foot - 2, 1, 1)
        elif kind == "chimney":
            pillar(lv, face - 4, foot - 7, foot - 3)  # post: crawl under, climb behind it
        lv.wp(face, foot - sh - 1, face + 1, foot - sh - 1, ground=True, label=f"pyramid step {k} ({kind})")
        if k in (1, 2, 3, 4, 6):
            lv.enemy(face + 4, foot - sh - 1)

    for k in range(steps):  # coins over the steps, once every block stands
        lv.coins(px0 + sw * k + 1, plateau - sh * (k + 1) - 3, px0 + sw * k + 3)

    # --- Tomb labyrinth inside the pyramid --------------------------------------
    mz = Maze(lv, 121, 25, 10, 3, seed=1402, dx=5, dy=5, cw=3, ch=3, border=0, extra_edges=2, start=(4, 2))
    shaft_x, low_y = mz.cell_xy(4, 2)
    lv.carve(shaft_x, apex_y, shaft_x + 2, low_y - 1)  # drop from the apex to the lowest gallery
    lv.wp(shaft_x, apex_y - 1, shaft_x + 2, apex_y - 1, label="pyramid apex")
    # climb back up through the galleries to the east door at the top
    mz.route((4, 2), (9, 0))
    ex, ey = mz.cell_xy(9, 0)
    lv.carve(ex + 3, ey, 196, ey + 2)  # east door, out on to step 2
    lv.wp(179, ey, 183, ey + 2, ground=True, label="east door")
    for c, r in mz.dead_ends():
        if (c, r) not in ((4, 2), (9, 0)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    placed = 0
    for c in range(10):
        for r in range(3):
            x, y = mz.cell_xy(c, r)
            if (c + r) % 2 == 1 and lv.is_solid(x + 1, y + 3) and placed < 18:
                lv.enemy(x + 1, y + 2)
                placed += 1

    # --- Oasis: sandstone pillars across wide quicksand --------------------------
    otops = dunes(lv, 205, 244, 50, 1.2, 4.0, phase=2.0)
    for px0, px1, pillars in [(213, 226, [(216, -1), (220, 1), (224, -1)]), (233, 244, [(236, 0), (240, -2)])]:
        lv.carve(px0, 0, px1, BOTTOM)
        base = otops[px0 - 1]
        lv.wp(px0 - 3, otops[px0 - 3] - 2, px0 - 1, otops[px0 - 1] - 1, ground=True, label=f"before quicksand {px0}")
        for x, dy in pillars:
            pillar(lv, x, base + dy, BOTTOM)
            lv.coin(x, base + dy - 2)
            lv.wp(x, base + dy - 1, ground=True, label=f"oasis pillar {x}")
    for x, v in [(207, 4), (229, 5)]:
        lv.decor(x, otops[x] - 1, v)
    for x in (210, 231):
        lv.big_decor(x, otops[x] - 1, 2)
    for x in (206, 208, 211, 228, 230, 231):
        lv.enemy(x, otops[x] - 1)
    lv.coins(206, otops[206] - 3, 212, 2)
    lv.coins(227, otops[227] - 3, 231, 2)

    # --- Obelisk chimney up to the flag mesa ----------------------------------------
    g = 50  # ground row from x 245 on
    lv.rect(245, g, 266, BOTTOM)
    lv.wp(245, g - 1, 246, g - 1, ground=True, label="obelisk foot")
    mesa = 18
    lv.rect(247, mesa, 247, g - 4)  # left obelisk (crawl under it)
    lv.rect(252, mesa, 252, g - 1)  # right obelisk
    perforate(lv, 247, mesa + 1, g - 7, solid=2, gap=1)
    perforate(lv, 252, mesa + 1, g - 7, solid=2, gap=1)
    lv.rect(248, 39, 248, 39)  # rest ledges
    lv.rect(251, 29, 251, 29)
    lv.wp(248, g - 3, 251, g - 1, ground=True, label="obelisk chimney base")
    lv.wp(248, 38, 248, 38, ground=True, label="obelisk rest 1")
    lv.wp(251, 28, 251, 28, ground=True, label="obelisk rest 2")
    lv.wp(247, mesa - 1, 252, mesa - 1, label="obelisk tops")
    lv.coins(249, 44, 250)
    lv.coins(249, 34, 250)
    lv.coins(249, 23, 250)
    lv.rect(255, mesa, 266, BOTTOM)  # flag mesa, two tiles off the right obelisk
    lv.wp(255, mesa - 1, 257, mesa - 1, ground=True, label="flag mesa")
    for x in (261, 263):  # not where the obelisk jump lands
        lv.enemy(x, mesa - 1)
    lv.decor(256, mesa - 1, 4)
    lv.big_decor(260, mesa - 1, 3)
    lv.coins(256, mesa - 4, 262, 2)
    lv.flag(264, mesa - 1)
    lv.wp(264, mesa - 1, label="flag")
    return lv
