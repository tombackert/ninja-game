"""Level 22 - Kelp Currents (reef, lagoon sky).

Currents: a kelp sea under rock islands, a long cave channel whose current
carries the swimmer east with one air pocket halfway, a geyser that
shoots up a shaft on to the plateau, a drain that pulls down into a
flooded cave, a short swim against the current to the cave's air pocket
and a last geyser up to the flag.
"""

from tools.worlds.builder import DOWN, LEFT, RIGHT, UP, Level

SEA = 30
BOTTOM = 80


def build() -> Level:
    lv = Level(22, "reef", background="background-lagoon.png")

    # --- Start cliff and the kelp sea --------------------------------------------------
    lv.rect(0, 25, 16, BOTTOM)
    lv.spawn(3, 24)
    lv.decor(7, 24, 8)
    lv.enemy(11, 24)
    lv.coins(4, 22, 12, 2)
    lv.wp(13, 24, 16, 24, ground=True, label="cliff edge")
    lv.water(17, SEA, 69, BOTTOM)
    lv.rect(17, 44, 69, BOTTOM)  # sea floor, 14 rows down
    lv.rect(27, SEA - 1, 30, 43)  # rock island 1
    lv.rect(41, SEA - 1, 47, 43)  # rock island 2
    lv.enemy(45, SEA - 2)
    lv.rect(57, SEA - 1, 60, 43)  # rock island 3
    lv.wp(27, SEA - 2, 30, SEA - 2, ground=True, label="island 1")
    lv.wp(41, SEA - 2, 43, SEA - 2, ground=True, label="island 2")
    lv.wp(57, SEA - 2, 60, SEA - 2, ground=True, label="island 3")
    for x in (20, 24, 34, 38, 51, 54, 65):
        lv.big_decor(x, 43, 6)  # kelp
    for x, v in ((22, 8), (36, 9), (49, 11), (63, 9)):
        lv.decor(x, 43, v)
    lv.coins(20, 40, 25, 1)
    lv.coins(33, 38, 38, 1)
    lv.coins(50, 40, 55, 1)

    # --- The channel: a current carries the swimmer east through the rock -------------
    lv.rect(70, 24, 124, BOTTOM)  # the big island the channel runs through
    lv.carve(70, 36, 120, 39)
    lv.water(70, 36, 120, 39, RIGHT)
    lv.carve(64, SEA, 69, 39)  # the sea floor dips to the channel mouth
    lv.wp(64, 34, 69, 39, label="channel mouth")
    lv.coins(72, 38, 90, 3)
    lv.wp(84, 36, 87, 39, label="channel")
    lv.carve(93, 33, 96, 35)  # air pocket in the channel roof
    lv.wp(93, 34, 96, 35, label="air pocket")
    lv.coins(99, 38, 117, 3)
    lv.wp(108, 36, 111, 39, label="channel end")

    # --- Geyser up to the plateau -------------------------------------------------------
    lv.carve(121, 20, 124, 39)  # open to the sky: the water spouts out at the top
    lv.water(121, 25, 124, 39, UP)
    lv.wp(121, 30, 124, 34, label="geyser")
    lv.coins(122, 32, 123)
    lv.wp(125, 23, 128, 23, ground=True, label="plateau")
    lv.rect(125, 24, 160, BOTTOM)
    for x in (110, 116):
        lv.enemy(x, 23)
    lv.coins(100, 21, 118, 3)
    for x in (133, 141):
        lv.enemy(x, 23)
    lv.big_decor(137, 23, 7)
    lv.coins(129, 21, 145, 2)

    # --- Drain into the flooded cave ------------------------------------------------------
    lv.rect(152, 14, 172, BOTTOM)  # cliff over the cave, too high to climb: the way is under it
    lv.rect(173, 57, 176, BOTTOM)  # under the last geyser
    lv.carve(148, 20, 151, 50)  # pool on the plateau, then the drain shaft
    lv.water(148, 21, 151, 23)
    lv.water(148, 24, 151, 50, DOWN)
    lv.wp(146, 23, 147, 23, ground=True, label="pool edge")
    lv.wp(148, 30, 151, 36, label="drain")
    lv.carve(140, 51, 175, 56)  # the flooded cave
    lv.water(140, 51, 175, 56)
    lv.wp(148, 52, 151, 56, label="cave floor")
    lv.coins(141, 55, 146, 1)  # a little side bay
    # Against the current to the cave's air pocket
    lv.water(156, 51, 166, 56, LEFT)
    lv.wp(160, 51, 162, 56, label="against the current")
    lv.carve(168, 47, 172, 50)  # air pocket over the cave's far end
    lv.wp(168, 49, 172, 50, label="cave air")
    lv.coins(157, 53, 165, 2)

    # --- Last geyser up to the flag ----------------------------------------------------------
    lv.carve(173, 16, 176, 56)
    lv.water(173, 17, 176, 56, UP)
    lv.drain(173, 16, 176, 16)
    lv.wp(173, 30, 176, 40, label="last geyser")
    lv.rect(177, 16, 195, BOTTOM)  # flag rock
    lv.wp(177, 15, 180, 15, ground=True, label="flag rock")
    lv.coins(181, 13, 188, 2)
    lv.decor(183, 15, 8)
    lv.flag(190, 15)
    lv.wp(190, 15, label="flag")
    return lv
