"""Level 15 - Mars (mars rock, Mars sky).

A crater field crossed by dash jumps, a 5-wide chimney up a mesa, single
floating rocks over a chasm, lava tubes (a crawlway over pits and a tube
labyrinth) and a zigzag shaft up to the launch pad with the flag.
"""

from tools.worlds.builder import Level, Maze, box, perforate, zigzag

BOTTOM = 62


def build() -> Level:
    lv = Level(15, "mars", background="background-mars.png")
    ground = 50

    # --- Landing site and crater field (dash across each crater) ---------------
    lv.rect(0, ground, 81, BOTTOM)
    lv.spawn(3, ground - 1)
    lv.big_decor(8, ground - 1, 5)
    lv.decor(12, ground - 1, 6)
    lv.decor(15, ground - 1, 7)
    for x in (11, 18, 24):
        lv.enemy(x, ground - 1)
    lv.coins(5, ground - 3, 13, 2)
    craters = [(30, 8), (46, 8), (62, 9)]  # 9 needs a late jump plus the dash
    for cx, w in craters:
        lv.carve(cx, ground, cx + w - 1, BOTTOM)
        lv.rect(cx - 1, ground - 1, cx - 1, ground - 1)  # raised rims
        lv.rect(cx + w, ground - 1, cx + w, ground - 1)
        lv.coins(cx + 1, ground - 4, cx + w - 2, 2)
        lv.wp(cx - 4, ground - 1, cx - 2, ground - 1, ground=True, label=f"crater {cx} rim")
        lv.wp(cx + w + 1, ground - 1, cx + w + 3, ground - 1, ground=True, label=f"crater {cx} far rim")
    for x in (42, 59, 76):  # one per stretch, away from the landing spots
        lv.enemy(x, ground - 1)
    lv.decor(42, ground - 1, 7)
    lv.decor(58, ground - 1, 6)
    lv.big_decor(75, ground - 1, 5)

    # --- Mesa: 5-wide chimney between a rock needle and the mesa face ----------
    lv.rect(82, 16, 84, ground - 4)  # needle (crawl under it)
    lv.carve(82, 17, 83, 38)  # its upper part: 1 thick and holed
    perforate(lv, 84, 18, 38, solid=2, gap=1)
    lv.rect(82, ground, 89, BOTTOM)
    lv.rect(90, 18, 110, BOTTOM)  # mesa
    lv.rect(89, 40, 89, 40)  # rest ledges
    lv.rect(85, 30, 85, 30)
    lv.wp(85, ground - 3, 89, ground - 1, ground=True, label="chimney base")
    lv.wp(89, 39, 89, 39, ground=True, label="chimney rest 1")
    lv.wp(85, 29, 85, 29, ground=True, label="chimney rest 2")
    lv.wp(90, 17, 93, 17, ground=True, label="mesa top")
    lv.coins(87, 44, 87)
    lv.coins(87, 35, 87)
    lv.coins(87, 24, 87)
    for x in (102, 107):  # not right at the chimney exit
        lv.enemy(x, 17)
    lv.big_decor(101, 17, 5)

    # --- Floating rocks over the chasm ------------------------------------------
    rocks = [(114, 19), (118, 18), (123, 20), (127, 19), (132, 21)]  # gaps of 3 and 4
    for bx, by in rocks:
        box(lv, bx, by, 1, 1)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, ground=True, label=f"rock {bx}")
    box(lv, 138, 22, 2, 1)  # dash
    lv.wp(138, 21, 139, 21, ground=True, label="rock ledge 138")
    for bx, by in [(143, 21), (147, 23)]:
        box(lv, bx, by, 1, 1)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, ground=True, label=f"rock {bx}")
    lv.coins(133, 18, 136)
    lv.coins(150, 22, 154)

    # --- Plateau over the lava tubes --------------------------------------------
    top = 26
    lv.rect(156, top, 282, BOTTOM)
    lv.wp(156, top - 1, 159, top - 1, ground=True, label="plateau edge (dash)")
    for x in (161, 165, 170, 174):
        lv.enemy(x, top - 1)
    lv.decor(158, top - 1, 7)
    lv.big_decor(176, top - 1, 5)
    lv.coins(160, top - 3, 172, 3)

    # Crawlway (2 tall, rows 33..34) over pits into a lower tube
    lv.carve(178, top, 180, 34)  # way down
    lv.wp(178, 32, 180, 34, label="tube entrance")
    lv.carve(178, 33, 214, 34)
    for px in (186, 195, 204):
        lv.carve(px, 35, px + 4, 41)
        lv.coin(px + 2, 33)
    lv.carve(176, 42, 214, 44)  # lower tube (floor row 45)
    lv.carve(176, 33, 177, 44)  # back up to the crawlway start (2-wide chimney)
    for x in (183, 192, 201, 210):
        lv.enemy(x, 34)
    lv.coins(180, 43, 212, 4)
    lv.wp(191, 33, 194, 34, ground=True, label="crawl 1")
    lv.wp(200, 33, 203, 34, ground=True, label="crawl 2")
    lv.wp(209, 33, 213, 34, ground=True, label="crawl 3")

    # Tube labyrinth
    cols = 10
    mz = Maze(lv, 217, 38, cols, 3, seed=1606, dx=5, dy=5, cw=3, ch=3, border=0, extra_edges=3, start=(0, 0))
    lv.carve(214, 33, 219, 37)
    lv.wp(217, 38, 219, 40, label="labyrinth entrance")
    mz.route((0, 0), (cols - 1, 2))
    for c, r in mz.dead_ends():
        if (c, r) not in ((0, 0), (cols - 1, 2)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    placed = 0
    for c in range(1, cols):
        for r in range(3):
            x, y = mz.cell_xy(c, r)
            if (c + r) % 2 == 0 and lv.is_solid(x + 1, y + 3) and placed < 18:
                lv.enemy(x + 1, y + 2)
                placed += 1

    # Zigzag shaft from the last cell up to the launch pad
    ex, ey = mz.cell_xy(cols - 1, 2)
    zx = ex + 6
    lv.carve(ex + 3, ey, zx + 2, ey + 2)
    zigzag(lv, zx, ey + 2, sections=5, height=5, inner=3, offset=2)
    # two steps in the top piece: out of the shaft with plain jumps
    lv.rect(zx + 2, top + 3, zx + 2, top + 3)
    lv.rect(zx, top + 1, zx, top + 1)
    for i in range(5):
        lv.coin(zx + 1 + (2 if i % 2 else 0), ey - 1 - 5 * i)
    lv.wp(zx - 3, top - 1, zx - 1, top - 1, ground=True, label="launch pad")

    # Launch pad
    lv.rect(zx - 7, top - 1, zx - 6, top - 1)
    lv.decor(zx - 10, top - 1, 7)
    for x in (zx - 12, zx - 9):  # away from the shaft exit
        lv.enemy(x, top - 1)
    lv.coins(zx - 1, top - 4, zx + 5, 2)
    lv.rect(zx + 7, top - 1, zx + 9, top - 1)  # flag pedestal
    lv.flag(zx + 8, top - 2)
    lv.wp(zx + 8, top - 2, label="flag")
    return lv
