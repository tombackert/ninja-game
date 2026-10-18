"""Level 20 - Olympus Mons (mars rock, Mars sky). The finale.

A vertical climb inside the volcano, switching back and forth: a holed
chimney, a chain of floating rocks, a wall-bounce ladder against the
crater wall, a zigzag shaft through an outcrop, a rock ladder, a holed
chimney entered from the right and a chain of dashes over the caldera to
the flag. A fall is not deadly, but it lands far below.
"""

from tools.worlds.builder import Level, crate_chain, holed_chimney, perforate, zigzag

LEFT, RIGHT, GROUND = 1, 69, 141


def build() -> Level:
    lv = Level(20, "mars", background="background-mars.png")
    lv.rect(LEFT - 1, 16, LEFT, GROUND + 3)  # crater walls
    lv.rect(RIGHT, 16, RIGHT + 1, GROUND + 3)
    lv.rect(LEFT - 1, GROUND, RIGHT + 1, GROUND + 3)

    # --- Floor of the crater and a holed chimney on the right -------------------
    lv.spawn(4, GROUND - 1)
    lv.big_decor(10, GROUND - 1, 5)
    lv.decor(20, GROUND - 1, 7)
    lv.decor(33, GROUND - 1, 6)
    for x in (12, 16, 22, 26, 32, 36, 42, 46):
        lv.enemy(x, GROUND - 1)
    lv.coins(6, GROUND - 3, 50, 4)
    holed_chimney(lv, 58, 4, 118, GROUND, rests=[(1, 131), (-1, 124)], label="floor chimney")
    lv.rect(66, 118, RIGHT - 1, 118)  # ledge L1, two tiles off the chimney
    lv.wp(66, 117, 68, 117, ground=True, label="L1")

    # --- Floating rocks leading west to L2 ----------------------------------------
    rocks = [(55, 115, 1), (51, 113, 1), (46, 112, 1), (42, 110, 1), (37, 109, 1), (33, 107, 1), (28, 106, 1)]
    rocks += [(24, 105, 1)]
    crate_chain(lv, rocks, label="rock")
    lv.rect(LEFT + 1, 104, 19, 104)  # L2
    lv.wp(15, 103, 19, 103, ground=True, label="L2")
    for x in (5, 14, 17):
        lv.enemy(x, 103)

    # --- Wall-bounce ladder against the crater wall --------------------------------
    w = 11
    lv.rect(w, 84, w, 98)  # free-standing bounce wall (pass under it on L2)
    for i, row in enumerate([101, 98, 95, 92, 89, 86]):
        lv.rect(LEFT + 1, row, w - 3, row)
        lv.wp(LEFT + 1, row - 1, w - 3, row - 1, ground=True, label=f"bounce ledge {i}")
        lv.coin(w - 1, row - 1)
    lv.wp(w, 83, ground=True, label="bounce wall top")

    # --- Zigzag shaft through the outcrop -----------------------------------------
    lv.rect(14, 60, 52, 90)
    lv.carve(14, 81, 16, 83)  # door in the outcrop's west face
    zigzag(lv, 17, 83, sections=4, height=6, inner=3, offset=2, label="outcrop zigzag")
    lv.carve(17, 60, 19, 61)
    for i in range(4):
        lv.coin(18 + (2 if i % 2 else 0), 80 - 6 * i)
    lv.wp(20, 59, 23, 59, ground=True, label="outcrop top")
    for x in (27, 32, 38, 43, 48):
        lv.enemy(x, 59)
    lv.coins(26, 57, 50, 3)

    # --- Rock ladder up the east side ---------------------------------------------
    ladder = [(56, 58, 1), (60, 56, 1), (64, 54, 1), (60, 52, 1), (56, 50, 1)]
    crate_chain(lv, ladder, label="ladder rock")

    # --- Holed chimney on L5, entered from the right --------------------------------
    lv.rect(42, 48, 52, 48)  # L5
    lv.wp(51, 47, 52, 47, ground=True, label="L5")
    lv.enemy(43, 47)
    lv.rect(50, 26, 50, 44)  # right wall: crawl under it, westwards
    lv.rect(45, 26, 45, 47)  # left wall
    perforate(lv, 50, 27, 42, solid=2, gap=1)
    perforate(lv, 45, 27, 42, solid=2, gap=1)
    lv.rect(46, 37, 46, 37)  # rest ledge
    lv.wp(46, 45, 49, 47, ground=True, label="summit chimney base")
    lv.wp(46, 36, ground=True, label="summit chimney rest")
    lv.wp(45, 25, 50, 25, label="summit chimney top")
    lv.coins(47, 41, 48)
    lv.coins(47, 31, 48)

    # --- Caldera rim and a chain of dashes to the flag ------------------------------
    lv.rect(53, 24, RIGHT - 1, 25)  # east rim, two tiles off the chimney
    lv.wp(53, 23, 55, 23, ground=True, label="east rim")
    for x in (61, 64, 67):  # not where the summit chimney ends
        lv.enemy(x, 23)
    lv.coins(56, 21, 66, 2)
    crate_chain(lv, [(46, 23, 1), (38, 23, 1), (30, 22, 1), (22, 23, 1)], label="caldera rock")
    lv.rect(LEFT + 1, 22, 16, 23)  # west rim
    lv.wp(13, 21, 16, 21, ground=True, label="west rim")
    lv.enemy(7, 21)
    lv.coins(5, 19, 14, 3)
    lv.decor(9, 21, 7)
    lv.flag(3, 21)
    lv.wp(3, 21, label="flag")
    return lv
