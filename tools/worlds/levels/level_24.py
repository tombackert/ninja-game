"""Level 24 - Undertow Caves (reef, deep water).

Breath is what counts here: a dry cave with a pillar pit, down into a
flooded labyrinth where only a few cells hold air in a dome over them, a
half-flooded tunnel whose floor drains pull swimmers down into dead-end
pits (hop or dash over them), a geyser up a long shaft to the exit cave
and its last pit, and a notched shaft to climb up to the flag.
"""

from tools.worlds.builder import DOWN, UP, Level, Maze, maze_path, perforate, pillar_run

BOTTOM = 52


def build() -> Level:
    lv = Level(24, "reef", background="background-deep.png", clouds=False)
    lv.rect(0, 4, 176, BOTTOM)  # everything is inside the rock

    # --- Dry cave ------------------------------------------------------------------------
    lv.carve(1, 9, 40, 14)
    lv.spawn(3, 14)
    lv.decor(8, 14, 11)
    lv.enemy(12, 14)
    lv.carve(16, 15, 29, 44)  # dry pit in the cave floor
    pillar_run(lv, [(19, 14), (22, 16), (25, 15)], 44, label="cave pillar")
    lv.wp(30, 14, 32, 14, ground=True, label="past the pit")
    lv.enemy(35, 14)
    lv.coins(31, 12, 37, 3)
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

    def dome(c, r, nxt=None):
        """Air trapped in a dome in the rock over cell (c, r), or else over the
        corridor on to the next cell `nxt`; none where a shaft leads up, the air
        would rise out of it. Returns the dome's columns, None if there is none."""
        cx, cy = mz.cell_xy(c, r)
        if frozenset(((c, r - 1), (c, r))) not in mz.edges:
            x0, x1 = cx, cx + 2
        elif nxt and nxt[1] == r:  # the middle of the corridor: no shaft ever leads up from it
            x0 = min(cx, mz.cell_xy(*nxt)[0]) + 4
            x1 = x0 + 1
        else:
            return None
        lv.carve(x0, cy - 2, x1, cy - 1)
        lv.drain(x0, cy - 2, x1, cy - 1)
        return x0, x1

    # Air over every third cell on the way (or the next one it can stay over), and over the dead ends
    due = False
    for i, (c, r) in enumerate(path):
        if due or i % 3 == 2:
            cols = dome(c, r, path[i + 1] if i + 1 < len(path) else None)
            due = cols is None
            if cols:  # into the air after the cell: the route has to breathe there
                cy = mz.cell_xy(c, r)[1]
                lv.wp(cols[0], cy - 1, cols[1], cy - 1, label=f"air over {c},{r}")
                at = next(k for k, w in enumerate(lv.route) if w.label == f"maze {c},{r}")
                lv.route.insert(at + 1, lv.route.pop())
    for c, r in mz.dead_ends():
        if (c, r) not in path:
            dome(c, r)
            cx, cy = mz.cell_xy(c, r)
            lv.coins(cx, cy + 2, cx + 2)
    for c, r in ((1, 2), (2, 1), (3, 0), (4, 2), (5, 1)):
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
    for x in (t0, t1):  # its air ends at rock, not at the water of the maze shaft and the geyser
        lv.rect(x, top, x, ey - 1)
    lv.wp(t0, ey - 2, t0 + 3, ey + 2, label="tunnel")
    drains = (t0 + 8, t0 + 18, t0 + 28, t0 + 38)
    for i, x in enumerate(drains):
        lv.carve(x, ey + 3, x + 3, ey + 12)  # pit under the drain
        lv.water(x, ey, x + 3, ey + 12, DOWN)
        lv.coins(x, ey - 2, x + 3)
        lv.wp(x + 5, ey - 2, x + 7, ey + 2, label=f"past drain {i + 1}")
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
    lv.carve(gx + 9, exit_floor, gx + 18, exit_floor + 12)  # last pit
    pillar_run(lv, [(gx + 12, exit_floor), (gx + 15, exit_floor - 2)], exit_floor + 12, label="exit pillar")
    lv.wp(gx + 19, exit_floor - 1, gx + 20, exit_floor - 1, ground=True, label="past the last pit")
    lv.decor(gx + 7, exit_floor - 1, 8)
    # A notched shaft up to the flag cave
    lv.rect(gx - 2, exit_floor - 30, gx + 34, 4)
    lv.carve(gx + 21, exit_floor - 22, gx + 23, exit_floor - 6)
    for x in (gx + 20, gx + 24):
        perforate(lv, x, exit_floor - 20, exit_floor - 6, solid=2, gap=1)
    lv.wp(gx + 21, exit_floor - 13, gx + 23, exit_floor - 10, label="shaft")
    lv.coins(gx + 22, exit_floor - 8, gx + 22)
    lv.coins(gx + 22, exit_floor - 16, gx + 22)
    lv.carve(gx + 21, exit_floor - 27, gx + 33, exit_floor - 23)  # flag cave
    lv.wp(gx + 25, exit_floor - 23, gx + 27, exit_floor - 23, ground=True, label="flag cave")
    lv.enemy(gx + 28, exit_floor - 23)
    lv.coins(gx + 26, exit_floor - 25, gx + 30, 2)
    lv.flag(gx + 32, exit_floor - 23)
    lv.wp(gx + 32, exit_floor - 23, label="flag")
    return lv
