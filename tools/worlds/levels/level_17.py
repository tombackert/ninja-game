"""Level 17 - Sandstone Canyons (sand, desert sky).

A pillar run down into a canyon, a holed chimney back out, a wall-bounce
staircase (wall jump off a free-standing wall back on to a ledge too high
to reach otherwise, twice), a cave labyrinth inside the plateau, a pillar
run across the next canyon, a dash to the last mesa and a holed chimney
up to the flag.
"""

from tools.worlds.builder import Level, Maze, crate_chain, holed_chimney, pillar_run

BOTTOM = 80


def build() -> Level:
    lv = Level(17, "sand", background="background-desert.png")

    # --- Start mesa and a pillar run down into the canyon ----------------------
    lv.rect(0, 40, 18, BOTTOM)
    lv.spawn(3, 39)
    lv.decor(7, 39, 4)
    lv.big_decor(12, 39, 3)
    for x in (10, 15):
        lv.enemy(x, 39)
    lv.coins(4, 37, 8, 2)
    lv.wp(15, 39, 18, 39, ground=True, label="mesa edge")
    pillar_run(lv, [(22, 42), (26, 44), (31, 45), (35, 47), (39, 49), (44, 50), (48, 52)], BOTTOM, label="down pillar")

    # --- Canyon ledge and a holed chimney back up --------------------------------
    lv.rect(52, 54, 72, BOTTOM)
    lv.wp(52, 53, 54, 53, ground=True, label="canyon ledge")
    for x in (56, 60, 63):
        lv.enemy(x, 53)
    lv.decor(58, 53, 5)
    lv.coins(55, 51, 63, 2)
    holed_chimney(lv, 66, 4, 24, 54, rests=[(1, 44), (-1, 34)], label="canyon chimney")

    # --- Plateau B and the wall-bounce staircase -------------------------------
    lv.rect(74, 24, 100, BOTTOM)  # two tiles off the chimney's right wall
    lv.wp(74, 23, 76, 23, ground=True, label="plateau B")
    for x in (80, 85, 90, 95):
        lv.enemy(x, 23)
    lv.big_decor(83, 23, 4)
    lv.decor(93, 23, 4)
    lv.coins(78, 21, 98, 2)
    # Plateau C's west face is the bounce wall; neither ledge can be reached
    # by a plain jump (4 rows up), only by a wall jump off the opposite wall
    lv.rect(104, 15, 150, BOTTOM)  # plateau C
    lv.rect(99, 20, 101, 20)  # ledge L1 over the plateau B edge
    lv.rect(96, 6, 96, 17)  # free-standing wall W2
    lv.rect(100, 17, 103, 17)  # ledge L2 on plateau C's face (48 px over L1: > a jump)
    lv.wp(97, 23, 100, 23, ground=True, label="plateau B edge")
    lv.wp(99, 19, 101, 19, ground=True, label="bounce ledge 1")
    lv.wp(100, 16, 103, 16, ground=True, label="bounce ledge 2")
    lv.wp(104, 14, 107, 14, ground=True, label="plateau C")
    lv.coins(102, 21, 103)
    lv.coins(97, 17, 98)
    lv.coins(101, 14, 103)
    for x in (110, 118, 126, 134):
        lv.enemy(x, 14)
    lv.decor(122, 14, 5)
    lv.big_decor(130, 14, 3)
    lv.coins(116, 12, 140, 3)
    mz = Maze(lv, 112, 17, 7, 4, seed=1707, dx=5, dy=5, cw=3, ch=3, border=0, extra_edges=3, start=(0, 0))
    lv.carve(112, 15, 114, 16)  # shaft down into cell (0,0)
    lv.wp(112, 15, 114, 16, label="cave shaft")
    mz.route((0, 0), (6, 3))
    for c, r in mz.dead_ends():
        if (c, r) not in ((0, 0), (6, 3)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    placed = 0
    for c in range(1, 7):
        for r in range(4):
            x, y = mz.cell_xy(c, r)
            if (c + r) % 2 == 1 and lv.is_solid(x + 1, y + 3) and placed < 12:
                lv.enemy(x + 1, y + 2)
                placed += 1
    ex, ey = mz.cell_xy(6, 3)
    lv.carve(ex + 3, ey, 150, ey + 2)  # door in the cliff
    lv.wp(147, ey, 150, ey + 2, ground=True, label="cliff door")

    # --- Canyon D: pillars, then a dash to the last mesa --------------------------
    floor = ey + 3
    pillar_run(
        lv,
        [(154, floor + 1), (158, floor), (163, floor + 2), (167, floor + 1), (172, floor + 3), (176, floor + 2)],
        BOTTOM,
        label="canyon pillar",
    )
    crate_chain(lv, [(180, floor + 4, 1)], label="last rock")

    # --- Wall-bounce ladder up cliff F (dash under the wall on to the first ledge) ---
    cliff = 192
    wall = cliff - 7
    first = floor + 3
    ledges = [first - 3 * i for i in range(6)]
    lv.rect(wall, ledges[-1] - 6, wall, first - 2)
    for i, row in enumerate(ledges):
        lv.rect(wall + 3, row, cliff - 1, row)
        lv.wp(wall + 3, row - 1, cliff - 1, row - 1, ground=True, label=f"bounce ledge {i}")
        if i:
            lv.coin(wall + 1, row - 1)
    top = ledges[-1] - 2
    lv.rect(cliff, top, 230, BOTTOM)
    lv.wp(cliff, top - 1, cliff + 2, top - 1, ground=True, label="cliff F")
    for x in (199, 203, 206):  # not where the bounce ladder ends
        lv.enemy(x, top - 1)
    lv.decor(198, top - 1, 5)
    lv.big_decor(202, top - 1, 3)
    lv.coins(194, top - 3, 204, 2)

    # --- Holed chimney up to the flag -----------------------------------------------
    holed_chimney(lv, 208, 3, top - 16, top, rests=[(1, top - 8)], label="flag chimney")
    slab = top - 16
    lv.rect(215, slab, 222, slab + 1)  # flag slab, two tiles off the chimney
    lv.wp(215, slab - 1, 217, slab - 1, ground=True, label="flag slab")
    lv.coins(216, slab - 3, 220, 2)
    lv.flag(221, slab - 1)
    lv.wp(221, slab - 1, label="flag")
    return lv
