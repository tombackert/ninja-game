"""Level 24 - Undertow Caves (reef, deep water).

Breath is what counts here: a dry cave down into a flooded labyrinth
where only a few cells hold air under their roof, a half-flooded tunnel
whose floor drains pull swimmers down into dead-end pits (hop or dash
over them), and a geyser up a long shaft to the exit cave.
"""

from tools.worlds.builder import DOWN, UP, Level, Maze, maze_path

BOTTOM = 52


def build() -> Level:
    lv = Level(24, "reef", background="background-deep.png", clouds=False)
    lv.rect(0, 4, 168, BOTTOM)  # everything is inside the rock

    # --- Dry cave ------------------------------------------------------------------------
    lv.carve(1, 9, 40, 14)
    lv.spawn(3, 14)
    lv.decor(8, 14, 11)
    for x in (16, 28):
        lv.enemy(x, 14)
    lv.coins(5, 12, 35, 3)
    lv.big_decor(22, 14, 7)
    lv.wp(36, 14, 40, 14, ground=True, label="cave end")

    # --- Down into the flooded labyrinth --------------------------------------------------
    lv.carve(41, 9, 44, 23)
    lv.water(41, 17, 44, 23)
    lv.wp(41, 18, 44, 21, label="pool")
    mz = Maze(lv, 47, 19, 6, 4, seed=2404, dx=7, dy=6, cw=3, ch=3, border=0, extra_edges=2, start=(0, 0))
    x0, y0, x1, y1 = mz.bounds
    lv.carve(45, 19, 46, 21)  # from the pool into the first cell
    lv.water(45, 19, x1, y1)
    path = maze_path(mz.edges, (0, 0), (5, 3))
    mz.route((0, 0), (5, 3))
    # Air under the roof of every third cell on the way, and in the dead ends
    for i, (c, r) in enumerate(path):
        if i % 3 == 2:
            cx, cy = mz.cell_xy(c, r)
            lv.drain(cx, cy, cx + 2, cy)
    for c, r in mz.dead_ends():
        if (c, r) not in path:
            cx, cy = mz.cell_xy(c, r)
            lv.drain(cx, cy, cx + 2, cy)
            lv.coins(cx, cy + 2, cx + 2)
    for c, r in ((2, 1), (4, 2)):
        cx, cy = mz.cell_xy(c, r)
        if lv.is_solid(cx + 1, cy + 3):
            lv.enemy(cx + 1, cy + 2)
    ex, ey = mz.cell_xy(5, 3)
    mz.open_to(5, 3, "right")

    # --- Half-flooded tunnel with drains in its floor --------------------------------------
    t0, t1 = x1 + 1, x1 + 56
    top = ey - 3  # three rows of air over the water
    lv.carve(t0, top, t1, ey + 2)
    lv.water(t0, ey, t1, ey + 2)
    lv.wp(t0, ey - 2, t0 + 3, ey + 2, label="tunnel")
    drains = (t0 + 8, t0 + 18, t0 + 28, t0 + 38)
    for i, x in enumerate(drains):
        lv.carve(x, ey + 3, x + 2, ey + 12)  # pit under the drain
        lv.water(x, ey, x + 2, ey + 12, DOWN)
        lv.coins(x, ey - 2, x + 2)
        lv.wp(x + 4, ey - 2, x + 6, ey + 2, label=f"past drain {i + 1}")
    lv.coins(t0 + 44, ey + 1, t0 + 50, 2)
    lv.wp(t1 - 4, ey - 2, t1 - 1, ey + 2, label="tunnel end")

    # --- Geyser up to the exit cave -----------------------------------------------------------
    gx = t1 + 1
    exit_floor = top - 18
    lv.carve(gx, exit_floor - 1, gx + 3, ey + 2)
    lv.water(gx, exit_floor, gx + 3, ey + 2, UP)
    lv.wp(gx, top, gx + 3, ey, label="geyser")
    lv.carve(gx + 4, exit_floor - 5, gx + 24, exit_floor - 1)  # exit cave
    lv.wp(gx + 4, exit_floor - 1, gx + 7, exit_floor - 1, ground=True, label="exit cave")
    lv.enemy(gx + 14, exit_floor - 1)
    lv.coins(gx + 8, exit_floor - 3, gx + 18, 2)
    lv.decor(gx + 11, exit_floor - 1, 8)
    lv.flag(gx + 22, exit_floor - 1)
    lv.wp(gx + 22, exit_floor - 1, label="flag")
    return lv
