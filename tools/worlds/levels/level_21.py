"""Level 21 - Jungle Temple (grass and stone, sky).

Vine pillars over a swamp, a stepped temple climbed via single blocks, a
labyrinth inside it, a crate chain over the gorge and a wall-bounce
ladder up the far cliff: six wall jumps off a free-standing wall, each
landing on a ledge three rows higher than a jump can reach.
"""

from tools.worlds.builder import Level, Maze, box, crate_chain, holed_chimney, pillar, pillar_run

BOTTOM = 84


def build() -> Level:
    lv = Level(21, "stone")

    # --- Jungle floor and vine pillars over the swamp --------------------------
    lv.rect(0, 60, 30, 63, "grass")
    lv.rect(0, 64, 30, BOTTOM)
    lv.spawn(3, 59)
    for x, v in [(6, 0), (14, 1), (22, 2)]:
        lv.decor(x, 59, v)
    for x in (9, 18, 26):
        lv.big_decor(x, 59, 2)
    for x in (12, 20, 27):
        lv.enemy(x, 59)
    lv.coins(4, 57, 28, 3)
    lv.wp(27, 59, 30, 59, ground=True, label="swamp edge")
    vines = [(34, 59), (38, 57), (43, 58), (47, 56), (52, 57), (56, 55)]  # gaps 3-4, steps up to 2
    pillar_run(lv, vines, BOTTOM, t="grass", label="vine")
    # rest island in the swamp, then a second vine run with 4-tile gaps
    for i in range(5):
        lv.rect(60 + i, 55 + i, 72 - i, 55 + i, "grass")
    lv.wp(60, 54, 62, 54, ground=True, label="swamp island")
    for x in (64, 67, 70):
        lv.enemy(x, 54)
    lv.big_decor(66, 54, 2)
    lv.coins(61, 52, 71, 2)
    # Giant tree: a holed chimney between two trunks, then crates through the canopy
    lv.rect(73, 55, 80, 58, "grass")
    holed_chimney(lv, 74, 4, 32, 55, rests=[(1, 46), (-1, 39)], t="grass", label="giant tree")
    canopy = [(84, 33, 1), (88, 34, 1), (93, 36, 1), (97, 38, 1), (102, 40, 1), (106, 42, 1)]
    crate_chain(lv, canopy, t="grass", label="canopy crate")
    lv.big_decor(76, 31, 2)

    # --- Stepped temple, climbed via single blocks ------------------------------
    base, x0, x1, steps, sw, sh = 56, 98, 176, 7, 5, 4
    lv.rect(x0, base, x1, BOTTOM)
    for k in range(steps):
        lv.rect(x0 + sw * k, base - sh * (k + 1), x1 - sw * k, base - 1 - sh * k)
    apex = base - sh * steps
    aids = ["far", "detached", "post", "far", "detached", "post"]
    lv.wp(108, 43, 110, 43, ground=True, label="temple step 2 (from the canopy)")
    for k, kind in enumerate(aids, start=1):
        face = x0 + sw * k
        foot = base - sh * k
        if kind == "detached":
            box(lv, face - 2, foot - 2, 1, 1)
        elif kind == "far":
            box(lv, face - 3, foot - 2, 1, 1)
        elif kind == "post":
            pillar(lv, face - 4, foot - 7, foot - 3)
        if k >= 3:
            lv.wp(face, foot - sh - 1, face + 1, foot - sh - 1, ground=True, label=f"temple step {k} ({kind})")
        if k in (1, 2, 4, 5):
            lv.enemy(face + 3, foot - sh - 1)
    for k in range(1, steps):  # coins over the steps, once every block stands
        lv.coins(x0 + sw * k + 1, base - sh * (k + 1) - 3, x0 + sw * k + 2)
    lv.big_decor(x0 + sw * steps + 4, apex - 1, 1)

    # --- Labyrinth inside the temple --------------------------------------------
    mz = Maze(lv, 118, 40, 8, 3, seed=2121, dx=5, dy=5, cw=3, ch=3, border=0, extra_edges=2, start=(4, 0))
    sx, sy = mz.cell_xy(4, 0)
    lv.carve(sx, apex, sx + 2, sy - 1)
    lv.wp(sx, apex - 1, sx + 2, apex - 1, label="temple apex")
    mz.route((4, 0), (7, 2))
    for c, r in mz.dead_ends():
        if (c, r) not in ((4, 0), (7, 2)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    placed = 0
    for c in range(8):
        for r in range(3):
            x, y = mz.cell_xy(c, r)
            if (c + r) % 2 == 1 and lv.is_solid(x + 1, y + 3) and placed < 10:
                lv.enemy(x + 1, y + 2)
                placed += 1
    ex, ey = mz.cell_xy(7, 2)
    lv.carve(ex + 3, ey, x1, ey + 2)  # east door
    lv.wp(x1 - 3, ey, x1, ey + 2, ground=True, label="east door")

    # --- Crate chain over the gorge ----------------------------------------------
    floor = ey + 3
    g0 = x1 + 4
    crates = [(g0, floor, 1), (g0 + 5, floor - 1, 1), (g0 + 10, floor - 1, 1), (g0 + 15, floor - 2, 2)]
    crates += [(g0 + 22, floor - 2, 1), (g0 + 27, floor - 3, 1), (g0 + 32, floor - 4, 1)]  # 4-tile gaps
    crate_chain(lv, crates, label="gorge crate")

    # --- Wall-bounce ladder up the far cliff --------------------------------------
    cliff = g0 + 44
    wall = cliff - 7
    lv.rect(wall, floor - 27, wall, floor - 7)  # free-standing bounce wall (pass under it)
    first = floor - 5
    ledges = [first - 3 * i for i in range(6)]
    for i, row in enumerate(ledges):
        lv.rect(wall + 3, row, cliff - 1, row)
        lv.wp(wall + 3, row - 1, cliff - 1, row - 1, ground=True, label=f"bounce ledge {i}")
        if i:
            lv.coin(wall + 1, row - 1)
    top = ledges[-1] - 2
    lv.rect(cliff, top, cliff + 31, BOTTOM)
    lv.wp(cliff, top - 1, cliff + 2, top - 1, ground=True, label="cliff top")
    for x in (8, 11, 14):  # not where the bounce ladder ends
        lv.enemy(cliff + x, top - 1)
    lv.coins(cliff + 4, top - 3, cliff + 14, 2)
    lv.decor(cliff + 7, top - 1, 2)

    # --- Holed chimney up to the high altar ------------------------------------------
    holed_chimney(lv, cliff + 16, 3, top - 16, top, rests=[(1, top - 8)], label="altar chimney")
    altar = top - 16
    lv.rect(cliff + 23, altar, cliff + 30, altar + 1)  # altar slab, two tiles off the chimney
    lv.wp(cliff + 23, altar - 1, cliff + 25, altar - 1, ground=True, label="altar")
    lv.big_decor(cliff + 27, altar - 1, 2)
    lv.coins(cliff + 24, altar - 3, cliff + 28, 2)
    lv.flag(cliff + 29, altar - 1)
    lv.wp(cliff + 29, altar - 1, label="flag")
    return lv
