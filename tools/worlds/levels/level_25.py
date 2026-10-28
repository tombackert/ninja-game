"""Level 25 - The Abyss (reef, deep water).

The finale puts it all together: sea stacks over the open sea, a drain
that drags the swimmer to the bottom of a trench, a long run along its
floor where a current first carries and then pushes back (rocks to
shelter behind, air domes in the roof), a geyser up the whole depth, a
dry climb up a holed sea stack and pillars across the summit to the flag.
"""

from tools.worlds.builder import DOWN, LEFT, RIGHT, UP, Level, holed_chimney, pillar_run

SEA = 14
BOTTOM = 70
SHELF = 26  # sea floor of the shallows
DEEP = 56  # floor of the trench


def build() -> Level:
    lv = Level(25, "reef", background="background-deep.png", clouds=False)
    lv.water(15, SEA, 134, BOTTOM)

    # --- Start cliff and the sea stacks ------------------------------------------------------
    lv.rect(0, 10, 14, BOTTOM)
    lv.spawn(3, 9)
    lv.enemy(10, 9)
    lv.coins(4, 7, 9, 1)
    lv.decor(7, 9, 11)
    lv.wp(11, 9, 14, 9, ground=True, label="cliff edge")
    lv.rect(15, SHELF, 44, BOTTOM)
    pillar_run(
        lv, [(18, SEA - 2), (23, SEA - 3), (28, SEA - 1), (33, SEA - 3), (38, SEA - 2)], SHELF - 1, label="stack"
    )
    lv.coins(20, SHELF - 3, 36, 4)
    for x in (21, 31):
        lv.big_decor(x, SHELF - 1, 6)
    lv.decor(26, SHELF - 1, 9)
    lv.rect(41, SEA - 2, 44, SHELF)  # last stack, the trench's rim
    lv.wp(41, SEA - 3, 44, SEA - 3, ground=True, label="rim")

    # --- Down the drain to the bottom of the trench -----------------------------------------
    lv.rect(45, DEEP, 116, BOTTOM)  # trench floor
    lv.water(45, SEA, 48, DEEP - 6, DOWN)
    lv.wp(45, SEA + 4, 48, SEA + 8, label="drain")
    lv.coins(46, SEA + 12, 47, 1)
    lv.rect(49, SEA - 20, 116, DEEP - 9)  # sea cliff over the trench: no way over or round it
    lv.wp(45, DEEP - 5, 50, DEEP - 1, label="trench bottom")
    lv.carve(51, DEEP - 12, 55, DEEP - 9)  # air dome under the wall
    lv.drain(51, DEEP - 12, 55, DEEP - 10)
    lv.wp(51, DEEP - 10, 55, DEEP - 9, label="first air")
    lv.big_decor(53, DEEP - 1, 8)
    lv.decor(57, DEEP - 1, 11)

    # --- The floor run: carried by the current, then against it ------------------------------
    lv.water(56, DEEP - 8, 85, DEEP - 1, RIGHT)
    lv.coins(60, DEEP - 3, 84, 3)
    for x in (64, 72, 80):
        lv.big_decor(x, DEEP - 1, 6)
    lv.wp(70, DEEP - 6, 73, DEEP - 1, label="carried")
    for x in (68, 82):
        lv.enemy(x, DEEP - 1)
    lv.carve(86, DEEP - 13, 90, DEEP - 9)  # second air dome
    lv.drain(86, DEEP - 13, 90, DEEP - 10)
    lv.wp(86, DEEP - 10, 90, DEEP - 9, label="second air")
    lv.water(91, DEEP - 8, 116, DEEP - 1, LEFT)
    # Rocks on the floor; in their lee, west of them, the water stands still
    for x in (96, 104, 112):
        lv.rect(x, DEEP - 3, x + 1, DEEP - 1)
        lv.water(x - 2, DEEP - 4, x - 1, DEEP - 1)
        lv.coins(x - 2, DEEP - 5, x - 1)
    lv.wp(94, DEEP - 6, 95, DEEP - 1, label="lee 1")
    lv.wp(102, DEEP - 6, 103, DEEP - 1, label="lee 2")
    lv.carve(102, DEEP - 13, 106, DEEP - 9)  # third air dome, over the second rock
    lv.drain(102, DEEP - 13, 106, DEEP - 10)
    lv.wp(102, DEEP - 10, 106, DEEP - 9, label="third air")
    lv.wp(110, DEEP - 6, 111, DEEP - 1, label="lee 3")
    lv.enemy(108, DEEP - 1)
    lv.decor(115, DEEP - 1, 9)
    lv.wp(113, DEEP - 6, 116, DEEP - 1, label="end of the run")

    # --- The geyser up the whole depth ------------------------------------------------------------
    lv.carve(117, SEA - 1, 120, DEEP - 1)
    lv.water(117, SEA, 120, DEEP - 1, UP)
    lv.rect(121, SEA - 1, 124, DEEP - 1)
    lv.wp(117, SEA + 10, 120, SEA + 20, label="geyser")
    lv.coins(118, SEA + 6, 119, 1)

    # --- Up the sea stack to the flag --------------------------------------------------------------
    lv.rect(117, DEEP, 134, BOTTOM)
    lv.rect(125, SEA - 1, 134, BOTTOM)  # ledge at the surface
    lv.wp(125, SEA - 2, 128, SEA - 2, ground=True, label="ledge")
    lv.enemy(131, SEA - 2)
    holed_chimney(lv, 135, 4, SEA - 22, SEA - 1, rests=[(1, SEA - 12)], label="sea stack")
    lv.rect(135, SEA - 1, 167, BOTTOM)
    lv.rect(142, SEA - 22, 146, SEA - 21)  # the summit, then pillars over the drop
    lv.wp(142, SEA - 23, 145, SEA - 23, ground=True, label="summit")
    lv.enemy(145, SEA - 23)
    pillar_run(lv, [(150, SEA - 24), (154, SEA - 21), (158, SEA - 25)], SEA - 18, label="summit pillar")
    lv.rect(162, SEA - 22, 166, SEA - 21)
    lv.coins(163, SEA - 25, 165, 2)
    lv.flag(165, SEA - 23)
    lv.wp(165, SEA - 23, label="flag")
    return lv
