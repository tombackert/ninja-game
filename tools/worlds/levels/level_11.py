"""Level 11 - Sky Ruins (grass islands, stone ruins).

Pillar run over the void, a 7-tile dash chasm, a 4-wide wall-jump chimney
up a ruined tower, floating box stairs, a ruin labyrinth whose low
corridors cap every jump, a 5-wide chimney between two sky spires and a
fortress gauntlet before the flag island.
"""

from tools.worlds.builder import Level, Maze, box, perforate, pillar


def island(lv: Level, x0: int, x1: int, top: int, depth: int = 4, t="grass"):
    """Floating island: flat top, tapering underside."""
    for i in range(depth + 3):
        inset = max(0, i - depth + 2) * 2
        if x0 + inset > x1 - inset:
            break
        lv.rect(x0 + inset, top + i, x1 - inset, top + i, t)


def build() -> Level:
    lv = Level(11, "stone")

    # --- Start island and pillar run -----------------------------------
    island(lv, 2, 16, 90)
    lv.spawn(5, 89)
    lv.decor(3, 89, 0)
    lv.decor(10, 89, 2)
    lv.big_decor(13, 89, 2)
    lv.coins(8, 88, 11)
    lv.wp(13, 89, 15, 89, ground=True, label="start edge")

    # gaps of 3 and 4 tiles (a 4-gap needs a late jump off the edge), steps up to 2
    tops = [(20, 89), (24, 88), (29, 88), (33, 86), (37, 87), (42, 87), (46, 85)]
    for x, top in tops:
        pillar(lv, x, top, 97)
        lv.coin(x, top - 2)
        lv.coin(x + 2, top - 4)
        lv.wp(x, top - 1, ground=True, label=f"pillar {x}")

    # --- Island A, 7-tile dash chasm, island B -------------------------
    island(lv, 50, 56, 84)
    lv.enemy(53, 83)
    lv.coins(51, 82, 52)
    lv.wp(54, 83, 56, 83, ground=True, label="island A edge")
    lv.coins(58, 79, 63)

    island(lv, 65, 100, 84, depth=5)
    lv.wp(65, 83, 67, 83, ground=True, label="dash chasm landing")
    for x in (69, 72, 76, 79, 83, 88, 93):
        lv.enemy(x, 83)
    lv.coins(67, 81, 85, 2)
    lv.decor(72, 83, 1)
    lv.decor(77, 83, 0)
    lv.big_decor(81, 83, 2)
    lv.big_decor(66, 83, 1)

    # --- Ruined tower: 4-wide chimney (x 91..94) from y=83 up to y=56 ---
    # Both walls are 1 thick and full of holes above the rest ledge
    lv.rect(86, 50, 90, 80)  # left block, door below it (rows 81..83)
    lv.rect(95, 56, 97, 83)  # right block
    lv.rect(94, 70, 94, 70)  # rest ledge
    lv.carve(86, 50, 89, 68)
    lv.carve(96, 56, 97, 68)
    perforate(lv, 90, 52, 68, solid=2, gap=1)
    perforate(lv, 95, 58, 68, solid=2, gap=1)
    lv.coins(92, 76, 93)
    lv.coins(92, 62, 93)
    lv.wp(91, 81, 94, 83, label="chimney bottom")
    lv.wp(93, 67, 94, 69, ground=True, label="chimney rest ledge")
    lv.wp(95, 55, 97, 55, ground=True, label="tower top")

    # --- Bridge and floating box stairs (rise 2 / gap 3 over the void) ---
    lv.rect(98, 56, 106, 56)
    lv.enemy(101, 55)
    lv.enemy(104, 55)
    lv.wp(104, 55, 106, 55, ground=True, label="bridge end")
    # mostly single crates: 3-tile gaps, rising up to 2 per jump
    stairs = [(110, 54, 2), (115, 52, 1), (119, 51, 1), (123, 49, 1), (127, 49, 1), (131, 47, 2), (136, 45, 1)]
    for bx, by, w in stairs:
        box(lv, bx, by, w, 2)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, bx + w - 1, by - 1, ground=True, label=f"crate {bx}")

    # --- Ruin labyrinth: 9x5 cells, 3-tall corridors, climbing shafts ---
    mz = Maze(lv, 142, 22, 9, 5, seed=1107, dx=5, dy=5, cw=3, ch=3, extra_edges=4, start=(0, 4))
    entry_y = mz.floor_y(0, 4)
    # Stairs land on a stone porch in front of the entry
    lv.rect(139, entry_y, 141, entry_y + 1)
    mz.open_to(0, 4, "left")
    lv.wp(139, entry_y - 1, 141, entry_y - 1, ground=True, label="maze porch")
    mz.route((0, 4), (8, 0))
    mz.open_to(8, 0, "right")
    for c, r in mz.dead_ends():
        if (c, r) in ((0, 4), (8, 0)):
            continue
        x, y = mz.cell_xy(c, r)
        lv.coins(x, y + 2, x + 2)
    enemies = 0
    for c in range(9):
        for r in range(5):
            x, y = mz.cell_xy(c, r)
            if (c + r) % 2 == 1 and c > 0 and lv.is_solid(x + 1, y + 3) and enemies < 20:
                lv.enemy(x + 1, y + 2)
                enemies += 1

    # --- Spire section: drop to island C, 5-wide chimney between spires --
    ex = mz.bounds[2] + 1
    ey = mz.floor_y(8, 0)
    lv.rect(ex, ey, ex + 4, ey + 1)
    lv.wp(ex + 2, ey - 1, ex + 4, ey - 1, ground=True, label="maze exit ledge")
    cx0 = ex + 11  # island C, lower, reached with a falling dash
    island(lv, cx0, cx0 + 20, ey + 12, depth=4)
    lv.wp(cx0, ey + 11, cx0 + 3, ey + 11, ground=True, label="island C landing")
    for x in (cx0 + 5, cx0 + 8, cx0 + 11, cx0 + 17):
        lv.enemy(x, ey + 11)
    lv.coins(cx0 + 4, ey + 9, cx0 + 12, 2)
    lv.big_decor(cx0 + 2, ey + 11, 1)
    # Spires stand on island C: inner shaft 5 wide, 24 tall, door on the left
    sx = cx0 + 14
    lv.rect(sx, ey - 16, sx + 1, ey + 8)  # left spire
    lv.rect(sx + 7, ey - 12, sx + 8, ey + 11)  # right spire
    lv.carve(sx, ey + 9, sx + 1, ey + 11)
    lv.rect(sx + 2, ey - 2, sx + 2, ey - 2)  # rest ledge
    lv.carve(sx + 8, ey - 11, sx + 8, ey - 3)  # right spire 1 thick above the ledge
    perforate(lv, sx + 7, ey - 11, ey - 3, solid=2, gap=1)
    lv.coins(sx + 3, ey + 2, sx + 5, 2)
    lv.coins(sx + 3, ey - 8, sx + 5, 2)
    lv.wp(sx + 2, ey + 9, sx + 6, ey + 11, label="spire chimney bottom")
    lv.wp(sx + 2, ey - 3, sx + 3, ey - 3, ground=True, label="spire rest ledge")
    lv.wp(sx + 7, ey - 13, sx + 8, ey - 13, ground=True, label="right spire top")

    # --- Fortress gauntlet: low corridor with enemies, then the flag ----
    fx = sx + 9
    fy = ey - 12  # corridor floor
    lv.rect(fx, fy, fx + 26, fy + 2)  # floor
    lv.rect(fx + 3, fy - 4, fx + 26, fy - 3)  # ceiling (corridor 2 tall)
    lv.rect(fx + 26, fy - 4, fx + 26, fy - 1)
    lv.carve(fx + 26, fy - 2, fx + 26, fy - 1)  # exit
    for x in (fx + 7, fx + 11, fx + 15, fx + 19, fx + 23):
        lv.enemy(x, fy - 1)
    lv.coins(fx + 5, fy - 1, fx + 24, 4)
    lv.wp(fx + 22, fy - 2, fx + 25, fy - 1, ground=True, label="gauntlet end")
    # Single crates with 4-tile gaps (late jumps or dashes), then the flag island
    crates = [(fx + 30, fy + 1), (fx + 35, fy + 2), (fx + 40, fy + 1), (fx + 45, fy + 3), (fx + 50, fy + 2)]
    for bx, by in crates:
        box(lv, bx, by, 1, 1)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, ground=True, label=f"sky crate {bx}")
    gx = fx + 55
    island(lv, gx, gx + 14, fy + 4, depth=4)
    lv.wp(gx, fy + 3, gx + 2, fy + 3, ground=True, label="flag island")
    for x in (gx + 4, gx + 7, gx + 10):
        lv.enemy(x, fy + 3)
    lv.coins(gx + 1, fy + 1, gx + 13, 2)
    lv.big_decor(gx + 6, fy + 3, 2)
    lv.decor(gx + 2, fy + 3, 2)
    lv.flag(gx + 12, fy + 3)
    lv.wp(gx + 12, fy + 3, label="flag")
    return lv
