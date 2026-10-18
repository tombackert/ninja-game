"""Level 12 - Deep Caverns (stone).

A drop shaft with a side exit (miss it and climb back up), a crawlway only
two tiles high over pits that have to be dashed, a zigzag chimney, a large
labyrinth with low corridors, an enemy gauntlet and a box-climbing hall
up to the flag.
"""

from tools.worlds.builder import Level, Maze, box, perforate, zigzag


def build() -> Level:
    lv = Level(12, "stone")
    lv.rect(0, 10, 44, 72)  # western rock under the surface
    lv.rect(45, -5, 172, 72)  # mountain massif
    lv.rect(0, 10, 44, 11, "grass")

    # --- Surface start -------------------------------------------------------
    lv.spawn(4, 9)
    lv.decor(2, 9, 0)
    lv.decor(9, 9, 1)
    lv.big_decor(12, 9, 2)
    lv.big_decor(20, 9, 0)
    lv.coins(6, 7, 12, 2)
    for x in (14, 19, 24, 28):
        lv.enemy(x, 9)
    lv.coins(26, 7, 30)

    # --- Drop shaft with a side exit -------------------------------------------
    lv.carve(34, 10, 36, 42)  # shaft; misses fall on to the chamber below
    lv.carve(30, 38, 40, 42)  # bottom chamber (floor row 43)
    lv.carve(37, 19, 40, 21)  # side exit in the right wall (floor row 22)
    lv.coins(35, 14, 35)
    lv.coins(35, 17, 35)
    lv.wp(31, 9, 33, 9, ground=True, label="shaft rim")
    lv.wp(38, 19, 40, 21, ground=True, label="side exit")

    # --- Crawlway (2 tall) over pits that need a dash ------------------------
    cy = 21  # air rows 20..21, floor row 22
    lv.carve(40, cy - 1, 96, cy)
    for px, w in [(46, 4), (54, 4), (63, 5), (71, 4), (81, 5)]:
        lv.carve(px, cy + 1, px + w - 1, 37)  # pit into the lower tunnel
        lv.coin(px + w // 2, cy - 1)
    lv.carve(38, 33, 96, 37)  # lower tunnel (floor row 38) back to the chamber
    for x in (44, 51, 60, 69, 77, 87, 93):
        lv.enemy(x, cy)
    lv.coins(42, 37, 52, 2)
    lv.coins(60, 37, 70, 2)
    lv.wp(51, cy - 1, 53, cy, ground=True, label="crawl 1")
    lv.wp(59, cy - 1, 62, cy, ground=True, label="crawl 2")
    lv.wp(67, cy - 1, 70, cy, ground=True, label="crawl 3")
    lv.wp(76, cy - 1, 80, cy, ground=True, label="crawl 4")
    lv.wp(86, cy - 1, 90, cy, ground=True, label="crawl 5")

    # --- Zigzag chimney up to the labyrinth ----------------------------------
    zigzag(lv, 97, cy, sections=4, height=6, inner=3, offset=2)
    for i in range(4):
        lv.coin(98 + (2 if i % 2 else 0), cy - 3 - 6 * i)

    # --- Labyrinth: 7x5 cells, low corridors, climbing shafts ---------------
    mz = Maze(lv, 104, -1, 8, 6, seed=1203, dx=6, dy=6, cw=3, ch=3, border=0, extra_edges=4, start=(0, 0))
    lv.carve(99, -1, 103, 1)  # gallery from the zigzag top into cell (0,0)
    lv.wp(102, -1, 103, 1, ground=True, label="labyrinth gate")
    mz.route((0, 0), (7, 5))
    for c, r in mz.dead_ends():
        if (c, r) not in ((0, 0), (7, 5)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    placed = 0
    for c in range(8):
        for r in range(6):
            x, y = mz.cell_xy(c, r)
            if (c * 3 + r) % 3 == 1 and lv.is_solid(x + 1, y + 3) and placed < 18:
                lv.enemy(x + 1, y + 2)
                placed += 1

    # --- Drop out of the last cell into the gauntlet (3 tall, heading west) ---
    ex, ey = mz.cell_xy(7, 5)
    gy = 52  # gauntlet floor row, air rows 49..51
    lv.carve(ex, ey + 3, ex + 2, gy - 1)
    lv.carve(29, gy - 3, ex + 2, gy - 1)
    lv.wp(ex - 3, gy - 3, ex - 1, gy - 1, ground=True, label="gauntlet start")
    # bottomless pits in the 3-tall tunnel: too low to jump them, dash
    for px in (124, 110, 96, 82, 68, 54):
        lv.carve(px, gy, px + 3, 80)
        lv.coin(px + 1, gy - 2)
        lv.wp(px - 4, gy - 3, px - 1, gy - 1, ground=True, label=f"tunnel pit {px}")
    for x in (40, 48, 61, 75, 89, 103, 117, 131, 138):
        lv.enemy(x, gy - 1)
    lv.coins(36, gy - 2, 136, 6)
    lv.wp(30, gy - 3, 33, gy - 1, ground=True, label="gauntlet end")

    # --- Box-climbing hall (x 4..28) up to the flag ------------------------
    lv.carve(4, 24, 28, gy - 1)
    # single floating crates: 3-tile gaps, up to 2 rows per jump
    for bx, by in [(25, gy - 2), (21, gy - 4), (17, gy - 5), (13, gy - 7), (10, gy - 9)]:
        box(lv, bx, by, 1, 1)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, ground=True, label=f"crate {bx}")
    # box tower against the west wall: crawl under it, climb the gap behind it
    lv.rect(7, 30, 7, gy - 11)
    perforate(lv, 7, 31, gy - 13, solid=2, gap=1)
    lv.wp(4, gy - 10, 6, gy - 9, label="tower base")
    lv.wp(7, 29, 8, 29, ground=True, label="tower top")
    lv.coins(5, 34, 5)
    lv.coins(5, 38, 5)
    for bx, by in [(12, 29), (16, 28)]:
        box(lv, bx, by, 1, 1)
        lv.wp(bx, by - 1, ground=True, label=f"crate {bx}")
    lv.rect(21, 27, 28, 28)  # flag ledge
    lv.enemy(23, 26)
    for x in (12, 18):
        lv.enemy(x, gy - 1)
    lv.coins(22, 24, 26, 2)
    lv.flag(27, 26)
    lv.wp(27, 26, label="flag")
    return lv
