"""Level 18 - Sky Fortress (stone castle on a grass island, sky).

A crate bridge over the moat into the gate, a low gatehouse gallery over
bottomless murder holes (dash them), a holed chimney up the outer wall,
the battlement walk with pits and merlons, a zigzag shaft inside the west
tower and a long sky bridge of single crates to the floating keep with
the flag.
"""

from tools.worlds.builder import Level, crate_chain, holed_chimney, zigzag

BOTTOM = 92


def build() -> Level:
    lv = Level(18, "stone")

    # --- Start island and the crate bridge to the gate -------------------------
    for i in range(6):
        lv.rect(0 + i, 70 + i, 14 - i, 70 + i, "grass")
    lv.spawn(3, 69)
    lv.decor(6, 69, 0)
    lv.big_decor(10, 69, 2)
    for x in (7, 11):
        lv.enemy(x, 69)
    lv.coins(4, 67, 10, 2)
    lv.wp(12, 69, 14, 69, ground=True, label="island edge")
    crate_chain(lv, [(18, 70, 2), (23, 69, 1), (27, 69, 1), (32, 68, 1), (36, 67, 2)], label="moat crate")

    # --- Castle body: floor slab, outer wall with gate, inner block ----------
    lv.rect(40, 67, 115, 70)
    for i in range(1, 7):
        lv.rect(40 + 3 * i, 70 + i, 115 - 3 * i, 70 + i, "grass")
    lv.rect(40, 31, 43, 66)  # west wall
    lv.carve(40, 64, 43, 66)  # gate
    lv.rect(44, 30, 103, 63)  # inner block; its top is the battlement walk
    lv.wp(40, 64, 43, 66, ground=True, label="gate")

    # --- Gatehouse gallery (3 tall) over bottomless murder holes ---------------
    for px in (52, 62, 72, 82, 92):
        lv.carve(px, 67, px + 3, BOTTOM + 4)
        lv.coin(px + 1, 65)
        lv.wp(px - 4, 64, px - 1, 66, ground=True, label=f"murder hole {px}")
    for x in (46, 49, 57, 60, 67, 77, 80, 87, 97, 101):
        lv.enemy(x, 66)
    lv.wp(99, 64, 103, 66, ground=True, label="gallery end")

    # --- East balcony and a holed chimney up the outer wall ---------------------
    lv.enemy(105, 66)
    lv.coins(104, 64, 106)
    holed_chimney(lv, 107, 3, 30, 67, rests=[(1, 56), (-1, 45)], label="outer wall chimney")

    # --- Battlement walk (row 30) heading west: pits and merlons ---------------
    lv.wp(100, 29, 103, 29, ground=True, label="battlements east")
    for px in (92, 80, 68, 56):
        lv.carve(px, 30, px + 2, 35)  # 6 deep pits, climb out if you fall in
        lv.rect(px + 5, 28, px + 6, 29)  # merlon right after each pit
        lv.coin(px + 1, 28)
        lv.wp(px - 3, 29, px - 1, 29, ground=True, label=f"battlement pit {px}")
    for x in (100, 89, 84, 77, 65, 64, 53, 49):
        lv.enemy(x, 29)
    lv.coins(46, 27, 100, 4)

    # --- West tower: zigzag shaft to the top --------------------------------------
    lv.rect(34, 2, 47, 29)
    lv.carve(44, 27, 47, 29)  # door from the battlements
    zigzag(lv, 41, 29, sections=5, height=5, inner=3, offset=2, label="tower zigzag")
    lv.carve(41, 2, 43, 4)  # out on to the roof
    for i in range(5):
        lv.coin(42 + (2 if i % 2 else 0), 27 - 5 * i)
    lv.wp(44, 1, 47, 1, ground=True, label="tower roof")
    lv.enemy(36, 1)

    # --- Sky bridge of single crates to the floating keep -------------------------
    bridge = [
        (51, 3, 1),
        (55, 4, 1),
        (60, 4, 1),
        (64, 5, 2),
        (70, 5, 1),
        (75, 6, 1),
        (79, 5, 1),
        (84, 7, 2),
        (90, 6, 1),
        (95, 7, 1),
        (100, 8, 1),
        (104, 7, 1),
    ]
    crate_chain(lv, bridge, label="sky crate")
    keep_x = 113
    lv.rect(keep_x, 10, keep_x + 13, 12)
    for i in range(1, 5):
        lv.rect(keep_x + i * 2, 12 + i, keep_x + 13 - i * 2, 12 + i)
    lv.wp(keep_x, 9, keep_x + 2, 9, ground=True, label="keep")
    for x in (keep_x + 6, keep_x + 9):  # not where the sky bridge lands
        lv.enemy(x, 9)
    lv.coins(keep_x + 1, 7, keep_x + 11, 2)
    lv.big_decor(keep_x + 6, 9, 2)
    lv.flag(keep_x + 12, 9)
    lv.wp(keep_x + 12, 9, label="flag")
    return lv
