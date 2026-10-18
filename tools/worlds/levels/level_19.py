"""Level 19 - Mars Caverns (mars rock, Mars sky).

Down a crater shaft into a lava cavern crossed on stalagmites, a holed
chimney standing free in the cavern up to a gallery, a large tube
labyrinth, a crawlway over lava pits and a zigzag shaft up to the base
station with the flag.
"""

from tools.worlds.builder import Level, Maze, holed_chimney, pillar_run, zigzag

BOTTOM = 84


def build() -> Level:
    lv = Level(19, "mars", background="background-mars.png")
    lv.rect(0, 12, 210, BOTTOM)  # the massif

    # --- Surface and the crater shaft ------------------------------------------
    lv.spawn(3, 11)
    lv.big_decor(8, 11, 5)
    lv.decor(12, 11, 7)
    for x in (15, 21):
        lv.enemy(x, 11)
    lv.coins(5, 9, 13, 2)
    lv.rect(24, 11, 24, 11)  # crater rim
    lv.rect(29, 11, 29, 11)
    lv.carve(25, 12, 28, 23)  # shaft (4 wide) into the cavern
    lv.wp(21, 11, 23, 11, ground=True, label="crater rim")

    # --- Lava cavern: stalagmites over a bottomless lake ----------------------
    lv.carve(20, 24, 96, 46)
    lv.carve(30, 47, 92, BOTTOM + 4)  # the lake: no floor
    lv.rect(20, 47, 29, 50)  # landing shelf under the shaft
    lv.wp(24, 46, 28, 46, ground=True, label="cavern shelf")
    for x in (22, 27):
        lv.enemy(x, 46)
    stalagmites = [(32, 46), (36, 45), (41, 45), (45, 43), (49, 44), (54, 44), (58, 42)]
    pillar_run(lv, stalagmites, BOTTOM, label="stalagmite")
    for x in (40, 52, 64, 88):  # stalactites
        lv.rect(x, 24, x, 30)
    lv.rect(62, 41, 70, 42)  # rock island in the lake
    lv.wp(62, 40, 64, 40, ground=True, label="lake island")
    for x in (66, 69):
        lv.enemy(x, 40)
    lv.coins(63, 38, 69, 2)

    # --- Free-standing holed chimney up to the north gallery -----------------
    lv.rect(71, 42, 80, 42)  # chimney foot
    holed_chimney(lv, 73, 3, 25, 42, rests=[(1, 34)], label="cavern chimney")
    lv.carve(72, 18, 130, 23)  # north gallery above the cavern
    lv.rect(79, 24, 96, 24)  # its floor over the cavern
    lv.wp(79, 23, 82, 23, ground=True, label="north gallery")
    for x in (88, 96, 104, 112, 120):
        lv.enemy(x, 23)
    lv.coins(84, 21, 126, 3)

    # --- Tube labyrinth --------------------------------------------------------
    mz = Maze(lv, 132, 20, 9, 5, seed=1909, dx=5, dy=5, cw=3, ch=3, border=0, extra_edges=4, start=(0, 0))
    lv.carve(130, 20, 132, 23)
    mz.route((0, 0), (8, 4))
    for c, r in mz.dead_ends():
        if (c, r) not in ((0, 0), (8, 4)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    placed = 0
    for c in range(1, 9):
        for r in range(5):
            x, y = mz.cell_xy(c, r)
            if (c + r) % 2 == 1 and lv.is_solid(x + 1, y + 3) and placed < 16:
                lv.enemy(x + 1, y + 2)
                placed += 1

    # --- Crawlway east over lava pits -----------------------------------------
    ex, ey = mz.cell_xy(8, 4)
    cy = ey + 9  # crawlway air rows cy-1..cy, floor cy+1
    lv.carve(ex, ey + 3, ex + 2, cy)
    lv.carve(ex, cy - 1, 203, cy)
    lv.wp(ex, cy - 1, ex + 2, cy, ground=True, label="crawlway west")
    for px in (178, 186, 194):
        lv.carve(px, cy + 1, px + 3, BOTTOM + 4)
        lv.coin(px + 1, cy - 1)
        lv.wp(px + 4, cy - 1, px + 6, cy, ground=True, label=f"lava pit {px}")
    for x in (176, 184, 192, 199):
        lv.enemy(x, cy)

    # --- Zigzag shaft up to the base station -------------------------------------
    zigzag(lv, 201, cy, sections=7, height=5, inner=3, offset=2, label="exit zigzag")
    for i in range(7):
        lv.coin(202 + (2 if i % 2 else 0), cy - 3 - 5 * i)
    lv.carve(201, 12, 203, cy - 35)  # out through the surface
    lv.wp(196, 11, 200, 11, ground=True, label="base station")
    lv.decor(190, 11, 6)
    lv.rect(186, 11, 187, 11)
    for x in (184, 193):
        lv.enemy(x, 11)
    lv.coins(185, 8, 199, 2)
    lv.rect(205, 10, 207, 11)  # landing pad
    lv.flag(206, 9)
    lv.wp(206, 9, label="flag")
    return lv
