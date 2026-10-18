"""Level 13 - Crate Tower (stone, vertical).

Six storeys inside a tower, each a different box climb that ends in a
wall-jump chimney through a hole in the floor above: box stairs, a dash
over a broken floor, single floating crates over a hole, a labyrinth
storey, dash pits under fire, a zigzag chimney and floating crates up to
the roof hole. A fall lands on the storey below.
"""

from tools.worlds.builder import Level, Maze, box

L, R = 0, 61  # tower walls (inner x 1..60)
FLOORS = [118, 96, 74, 52, 30]  # floor slab top rows (2 thick), ground = 141, roof = 8


def build() -> Level:
    lv = Level(13, "stone")
    lv.rect(L - 1, 8, L, 143)
    lv.rect(R, 8, R + 1, 143)
    lv.rect(L - 1, 141, R + 1, 143, "grass")
    for f in FLOORS:
        lv.rect(L + 1, f, R - 1, f + 1)
    lv.rect(L - 1, 8, R + 1, 9)  # roof

    # --- Storey 1: box stairs to a 4-wide chimney --------------------------------
    lv.spawn(3, 140)
    lv.decor(2, 140, 0)
    lv.big_decor(10, 140, 1)
    for bx, by in [(7, 139), (12, 137), (17, 135), (22, 133), (27, 131)]:
        box(lv, bx, by)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, bx + 1, by - 1, ground=True, label=f"s1 box {bx}")
    lv.rect(32, 132, 37, 133)  # chimney base
    lv.rect(32, 120, 32, 128)  # left wall (crawl under it)
    lv.rect(37, 120, 37, 131)  # right wall
    lv.carve(33, 118, 36, 119)  # hole in floor 1
    lv.wp(33, 129, 36, 131, ground=True, label="s1 chimney base")
    lv.wp(33, 115, 36, 117, label="s1 hole")
    for x in (20, 26, 42, 48, 54):
        lv.enemy(x, 140)
    lv.coins(40, 138, 58, 2)

    # --- Storey 2: broken floor (dash), chimney at the west wall ------------
    lv.carve(12, 118, 20, 119)  # 9-wide break in floor 1
    lv.wp(21, 117, 24, 117, ground=True, label="s2 break edge")
    lv.wp(7, 117, 11, 117, ground=True, label="s2 across the break")
    lv.rect(5, 98, 5, 112)  # chimney pillar, inner x 1..4
    lv.carve(1, 96, 4, 97)  # hole in floor 2
    lv.rect(5, 105, 5, 105)
    lv.wp(1, 113, 4, 117, ground=True, label="s2 chimney base")
    lv.wp(1, 93, 4, 95, label="s2 hole")
    for x in (8, 30, 38, 46, 54):
        lv.enemy(x, 117)
    lv.coins(13, 114, 19)
    lv.coins(2, 108, 3)
    lv.coins(28, 115, 56, 2)

    # --- Storey 3: single crates over a hole, 5-wide chimney --------------------
    lv.carve(9, 96, 45, 97)  # hole in floor 2 under the crates
    crates = [(13, 94), (17, 93), (21, 94), (25, 92), (29, 93), (33, 91), (37, 92), (41, 91)]
    for bx, by in crates:
        box(lv, bx, by, 1, 1)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, ground=True, label=f"s3 crate {bx}")
    lv.wp(46, 95, 50, 95, ground=True, label="s3 landing")
    lv.rect(55, 76, 55, 90)  # chimney pillar, inner x 56..60
    lv.carve(56, 74, 60, 75)  # hole in floor 3
    lv.wp(56, 91, 60, 95, ground=True, label="s3 chimney base")
    lv.wp(56, 71, 60, 73, label="s3 hole")
    for x in (47, 50, 53):
        lv.enemy(x, 95)
    for x in (3, 6):
        lv.enemy(x, 95)
    lv.coins(46, 93, 53)
    lv.coins(57, 86, 59)
    lv.coins(57, 80, 59)

    # --- Storey 4: labyrinth, out through its top into floor 4 ------------------
    mz = Maze(lv, 8, 59, 8, 3, seed=1304, dx=6, dy=6, cw=3, ch=3, border=2, extra_edges=3, start=(7, 2))
    lv.rect(6, 54, 54, 56)  # rock up to floor 4
    mz.open_to(7, 2, "right")
    lv.wp(53, 71, 55, 73, ground=True, label="labyrinth entry")
    mz.route((7, 2), (0, 0))
    lv.carve(8, 52, 10, 58)  # shaft from cell (0,0) up through floor 4
    lv.wp(8, 49, 10, 51, label="s4 exit")
    for c, r in mz.dead_ends():
        if (c, r) not in ((7, 2), (0, 0)):
            x, y = mz.cell_xy(c, r)
            lv.coins(x, y + 2, x + 2)
    for c, r in [(5, 2), (3, 2), (1, 2), (6, 1), (4, 1), (2, 1), (5, 0), (3, 0)]:
        x, y = mz.cell_xy(c, r)
        if lv.is_solid(x + 1, y + 3):
            lv.enemy(x + 1, y + 2)

    # --- Storey 5: dash pits under fire (a fall drops into the labyrinth) -------
    for px in (14, 26, 38):  # each pit opens above a labyrinth cell
        lv.carve(px, 52, px + 5, 58)
    for x in (11, 23, 35, 47):
        lv.enemy(x, 51)
    lv.coins(15, 48, 18)
    lv.coins(27, 48, 30)
    lv.coins(39, 48, 42)
    lv.wp(21, 51, 24, 51, ground=True, label="s5 pit 1")
    lv.wp(33, 51, 36, 51, ground=True, label="s5 pit 2")
    lv.wp(45, 51, 48, 51, ground=True, label="s5 pit 3")
    # zigzag chimney: x 56..60 (pillar x 55), then x 54..58 (walls 53/59), floor 5 hole
    lv.rect(55, 40, 55, 47)
    lv.rect(53, 32, 53, 39)
    lv.rect(59, 32, 59, 39)
    lv.carve(54, 30, 58, 31)
    lv.wp(56, 48, 60, 51, ground=True, label="s5 chimney base")
    lv.wp(54, 35, 58, 38, label="s5 zigzag")
    lv.wp(54, 27, 58, 29, label="s5 hole")

    # --- Storey 6: floating crates to the roof chimney -----------------------
    for bx, by in [(50, 28), (45, 26), (40, 24), (35, 23), (30, 24), (25, 22), (21, 23)]:
        box(lv, bx, by)
        lv.coin(bx, by - 2)
        lv.wp(bx, by - 1, bx + 1, by - 1, ground=True, label=f"s6 box {bx}")
    box(lv, 14, 21, 2, 1)
    lv.wp(14, 20, 15, 20, ground=True, label="s6 under the roof")
    lv.rect(12, 10, 12, 17)  # roof chimney, inner x 13..16
    lv.rect(17, 10, 17, 17)
    lv.carve(13, 8, 16, 9)  # roof hole
    for x in (46, 40, 33, 26):
        lv.enemy(x, 29)
    lv.coins(24, 28, 48, 2)
    lv.wp(13, 5, 16, 7, label="roof")

    # --- Roof --------------------------------------------------------------------
    for x in (28, 37, 46):
        lv.enemy(x, 7)
    lv.coins(20, 5, 54, 3)
    lv.big_decor(24, 7, 2)
    lv.decor(50, 7, 2)
    lv.flag(58, 7)
    lv.wp(58, 7, label="flag")
    return lv
