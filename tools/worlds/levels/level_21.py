"""Level 21 - Coral Lagoon (reef, lagoon sky).

The first water level teaches swimming: wading off the beach into a
shallow lagoon between islets, a dive under a rock arch and a leap out on
the far side, a pillar hop where a miss only means a swim, a reef tunnel
under a rock shelf with one breathing hole halfway, and a climb from the
water up the lighthouse rock to the flag.
"""

from tools.worlds.builder import Level, chimney, pillar_run

SEA = 40  # water surface row
BOTTOM = 72


def build() -> Level:
    lv = Level(21, "reef", background="background-lagoon.png")
    lv.water(21, SEA, 200, BOTTOM)

    # --- Beach ------------------------------------------------------------------
    lv.rect(0, 36, 22, BOTTOM)
    lv.spawn(3, 35)
    lv.decor(7, 35, 10)
    lv.decor(14, 35, 8)
    lv.enemy(17, 35)
    lv.coins(5, 33, 13, 2)
    lv.wp(19, 35, 22, 35, ground=True, label="beach edge")

    # --- Shallow lagoon with two islets ----------------------------------------------
    lv.rect(23, 45, 64, BOTTOM)  # sea floor, 5 rows of water over it
    lv.rect(33, SEA - 1, 35, 44)  # islet 1
    lv.rect(46, SEA - 2, 48, 44)  # islet 2, a stroke higher
    lv.wp(33, SEA - 2, 35, SEA - 2, ground=True, label="islet 1")
    lv.wp(46, SEA - 3, 48, SEA - 3, ground=True, label="islet 2")
    lv.coins(25, 43, 31, 2)
    lv.coins(38, 43, 44, 2)
    lv.coins(51, 43, 57, 2)
    lv.decor(28, 44, 9)
    lv.decor(41, 44, 8)
    lv.decor(54, 44, 11)
    lv.decor(60, 44, 9)
    lv.enemy(34, SEA - 2)

    # --- The arch: a rock wall to dive under -------------------------------------------
    lv.rect(65, 30, 69, 47)  # wall, its foot 4 rows over the deep floor
    lv.rect(64, 52, 90, BOTTOM)  # deep pool floor
    lv.carve(64, 45, 64, 51)  # the lagoon floor drops into the pool
    lv.wp(60, SEA, 63, SEA + 3, label="lagoon end")
    lv.wp(64, 48, 66, 51, label="under the arch")
    lv.wp(70, 47, 73, 51, label="arch exit")
    lv.coins(64, 50, 70, 2)
    lv.big_decor(78, 51, 7)
    lv.decor(73, 51, 8)
    lv.wp(71, SEA, 74, SEA + 2, label="arch surface")
    # Far side: a low ledge to leap out on
    lv.rect(76, SEA - 1, 104, 51)
    lv.wp(76, SEA - 2, 79, SEA - 2, ground=True, label="arch ledge")
    for x in (86, 95):
        lv.enemy(x, SEA - 2)
    lv.big_decor(91, SEA - 2, 9)
    lv.coins(82, SEA - 4, 100, 3)

    # --- Pillar hop over open water -------------------------------------------------
    lv.rect(91, 56, 150, BOTTOM)  # floor of the bay, on under the ledge
    pillar_run(lv, [(108, SEA - 2), (112, SEA - 3), (116, SEA - 1), (120, SEA - 3), (124, SEA - 2)], 55)
    lv.rect(128, SEA - 2, 133, 55)  # reef table
    lv.wp(128, SEA - 3, 131, SEA - 3, ground=True, label="reef table")
    lv.decor(132, SEA - 3, 10)
    lv.coins(110, 50, 124, 2)  # under the pillars, for whoever falls in

    # --- Reef tunnel under a rock shelf, one breathing hole halfway ---------------------
    lv.rect(137, 30, 172, SEA + 1)  # the shelf, its underside 2 rows under the surface
    lv.rect(134, 50, 172, 55)  # tunnel floor, the shaft down to it at 134-136
    lv.rect(150, 56, 172, BOTTOM)
    lv.carve(152, 30, 154, SEA + 1)  # breathing hole
    lv.drain(152, 30, 154, SEA - 1)
    lv.wp(134, SEA + 3, 138, 49, label="tunnel mouth")
    lv.coins(140, 47, 150, 2)
    lv.decor(144, 49, 9)
    lv.decor(149, 49, 11)
    lv.wp(152, SEA - 2, 154, SEA, label="breathing hole")
    lv.coins(156, 47, 168, 2)
    lv.decor(160, 49, 8)
    lv.decor(166, 49, 9)
    lv.enemy(158, 49)
    lv.wp(170, SEA + 2, 172, 49, label="tunnel end")

    # --- Out of the water and up the lighthouse rock -------------------------------------
    lv.rect(173, 50, 200, BOTTOM)
    lv.rect(176, SEA - 1, 179, 49)  # step out of the water
    lv.wp(176, SEA - 2, 179, SEA - 2, ground=True, label="step")
    chimney(lv, 181, 3, SEA - 1, 14)
    lv.rect(185, SEA - 1, 200, 49)
    lv.carve(182, SEA - 14, 184, SEA - 1)
    lv.rect(184, SEA - 8, 184, SEA - 8)  # a rest halfway up: this is the intro level
    lv.wp(182, SEA - 4, 184, SEA - 2, label="chimney")
    lv.rect(186, SEA - 15, 196, SEA - 1)  # the rock
    lv.wp(186, SEA - 16, 188, SEA - 16, ground=True, label="lighthouse rock")
    lv.coins(183, SEA - 10, 183)
    lv.coins(189, SEA - 18, 193, 2)
    lv.flag(194, SEA - 16)
    lv.wp(194, SEA - 16, label="flag")
    return lv
