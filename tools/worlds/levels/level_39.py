"""Level 39 - The Drowned City (city stone and reef, deep water).

The city in the desert was not the only one the earth swallowed. On the
coast a whole town sank into a cave under the sea floor, and the sea came
after it. Its houses still stand, roof against the cave's ceiling, and in
each attic a little air is trapped. Off the quay into the harbour and in
under the ceiling: house to house, a breath in every attic, through the
doors and down the streets between them, where the tide runs up one alley
and down the next. Through the arcade under the town hall against the ebb,
up into the hall's attics, down the alley into the palace, whose great hall
still holds its air (the banner stands on its floor). On through the
market, where a wrong door leads only down, and into the bell tower, up its
flooded shaft to the water's surface inside it, then wall to wall up the
belfry and out on to its roof, high over the sea, with the flag.
"""

from tools.worlds.builder import DOWN, LEFT, STILL, UP, Level
from tools.worlds.kits.water import ANEMONE, CHEST, CORAL, SEAWEED, STARFISH, dress, pocket

BOTTOM = 80
CEIL = 35  # the cave's ceiling: its lowest row of rock
FLOOR = 66  # the sea floor the town stands on
HOUSE = "stone"


def house(lv: Level, x0: int, x1: int, attic: int = 2, flow: int = STILL, plates=(), doors=(), label="house"):
    """A house from the ceiling to the sea floor, walls one thick (x0 and x1):
    `attic` rows of air under the ceiling, water below it flowing `flow`.
    `plates` are (row, hole x0, hole x1) floors with a hole; `doors` are
    (side, row0, row1) gaps in the west (-1) or east (+1) wall."""
    lv.rect(x0, CEIL + 1, x0, FLOOR - 1, HOUSE)
    lv.rect(x1, CEIL + 1, x1, FLOOR - 1, HOUSE)
    lv.carve(x0 + 1, CEIL + 1, x1 - 1, FLOOR - 1)
    lv.water(x0 + 1, CEIL + 1, x1 - 1, FLOOR - 1, flow)
    pocket(lv, x0 + 1, CEIL + 1, x1 - 1, CEIL + attic)
    for row, h0, h1 in plates:
        lv.rect(x0 + 1, row, x1 - 1, row, HOUSE)
        lv.carve(h0, row, h1, row)
        lv.water(h0, row, h1, row, flow)
    for side, r0, r1 in doors:
        x = x0 if side < 0 else x1
        lv.carve(x, r0, x, r1)
        lv.water(x, r0, x, r1, STILL)
    lv.decor(x0 + 2, FLOOR - 1, CORAL)


def alley(lv: Level, x0: int, x1: int, flow: int, top: int = CEIL + 1):
    lv.water(x0, top, x1, FLOOR - 1, flow)


def build() -> Level:
    lv = Level(39, "reef", background="background-deep.png", clouds=False)
    lv.rect(-36, 20, 140, BOTTOM)  # rock: the sea floor over the cave, the cave's floor
    lv.carve(-36, 0, 140, 19)

    # --- The quay and the harbour ---------------------------------------------------------------------------
    lv.carve(-36, 20, -5, 29)
    lv.spawn(-32, 29)
    lv.decor(-28, 29, STARFISH)
    lv.big_decor(-24, 29, 8)  # an anchor on the quay
    lv.coins(-26, 27, -8, 3)
    lv.enemy(-14, 29)
    lv.wp(-9, 29, -6, 29, ground=True, label="the quay's edge")
    lv.carve(-4, 20, 5, 40)
    lv.water(-4, 30, 5, 40)
    lv.carve(6, CEIL + 1, 9, 40)  # the street in under the ceiling
    lv.water(6, CEIL + 1, 9, 40)
    lv.wp(0, 36, 5, 40, label="the harbour")

    # --- The first houses and their alleys -----------------------------------------------------------------------
    lv.carve(10, CEIL + 1, 122, FLOOR - 1)  # the cave
    lv.water(10, CEIL + 1, 122, FLOOR - 1)
    house(lv, 10, 18, plates=[(48, 16, 17)], doors=[(-1, 38, 40), (1, 57, 60)], label="the harbourmaster's house")
    lv.wp(11, CEIL + 1, 17, CEIL + 2, label="first attic")
    lv.wp(16, 48, 17, 48, label="first house's floor")
    lv.wp(18, 57, 18, 60, label="first house's door")
    alley(lv, 19, 22, UP)
    house(lv, 23, 31, flow=DOWN, doors=[(-1, 38, 41), (1, 60, 63)], label="the leaning house")
    lv.wp(24, CEIL + 1, 30, CEIL + 2, label="second attic")
    lv.wp(31, 60, 31, 63, label="second house's door")
    lv.coins(20, 50, 20, 1)
    lv.coins(27, 45, 27, 1)

    # --- The arcade under the town hall, against the ebb ------------------------------------------------------------
    hall0, hall1, arcade = 32, 56, 50
    lv.rect(hall0, CEIL + 1, hall1, arcade - 1, HOUSE)
    lv.water(38, arcade, 40, FLOOR - 1, LEFT)  # the ebb runs through the arcade
    for x in (39, 48, 53):
        lv.rect(x, arcade, x, arcade + 1, HOUSE)  # the arches' keystones
    for i, (a0, a1) in enumerate(((34, 37), (42, 45))):  # two attics reached from below
        lv.carve(a0, CEIL + 1, a1, arcade - 1)
        pocket(lv, a0, CEIL + 1, a1, CEIL + 3)
        lv.wp(a0, arcade, a1, arcade + 3, label=f"under town hall attic {i}")
        lv.wp(a0, CEIL + 1, a1, CEIL + 3, label=f"town hall attic {i}")
        lv.wp(a0, arcade, a1, arcade + 3, label=f"back under town hall attic {i}")
        lv.coin(a0 + 2, arcade - 5)

    # --- Down the alley into the palace -----------------------------------------------------------------------------
    alley(lv, 57, 60, DOWN, top=CEIL + 1)
    lv.water(57, 50, 60, 54, STILL)
    lv.wp(57, 51, 60, 54, label="the alley")
    p0, p1 = 61, 92
    lv.rect(p0, CEIL + 1, p0, FLOOR - 1, HOUSE)
    lv.rect(p1, CEIL + 1, p1, FLOOR - 1, HOUSE)
    lv.carve(p0, 51, p0, 54)  # its gate
    pocket(lv, p0 + 1, CEIL + 1, p1 - 1, 49)  # the great hall's air
    lv.rect(p0 + 9, 50, p1 - 9, 51, HOUSE)  # its floor
    lv.wp(p0 + 2, 50, p0 + 7, 54, label="under the great hall")
    lv.wp(p0 + 9, 49, p0 + 12, 49, ground=True, label="the great hall")
    lv.checkpoint(p0 + 13, 49)
    lv.enemy(p0 + 17, 49)
    lv.big_decor(p0 + 20, 49, CHEST)
    lv.coins(p0 + 10, 46, p1 - 10, 3)
    lv.wp(p1 - 8, 50, p1 - 2, 54, label="the great hall's east pool")
    lv.carve(p1, 56, p1, 59)  # out into the market
    lv.wp(p1, 56, p1, 59, label="the palace's back door")

    # --- The market: alleys and houses, a wrong door leads only down ------------------------------------------------
    alley(lv, 93, 96, UP)
    house(lv, 97, 105, flow=STILL, plates=[(46, 98, 99)], doors=[(-1, 38, 40), (1, 49, 52)], label="the baker's")
    lv.wp(98, CEIL + 1, 104, CEIL + 2, label="baker's attic")
    lv.wp(98, 46, 99, 46, label="baker's floor")
    lv.wp(105, 49, 105, 52, label="baker's door")
    alley(lv, 106, 109, DOWN)
    house(lv, 110, 118, flow=UP, doors=[(-1, 50, 54), (1, 38, 40)], label="the weaver's")
    lv.water(111, CEIL + 3, 117, 44, STILL)  # still water under its attic
    lv.wp(110, 50, 110, 54, label="weaver's door")
    lv.wp(111, CEIL + 1, 117, CEIL + 2, label="weaver's attic")
    lv.wp(118, 38, 118, 40, label="weaver's upper door")
    alley(lv, 119, 122, STILL)
    lv.coins(107, 45, 107, 1)
    lv.coins(114, 50, 114, 1)

    # --- The bell tower: up the flooded shaft, wall to wall up the belfry -------------------------------------------
    t0, t1 = 123, 128
    lv.rect(t0, 4, t0, FLOOR - 1, HOUSE)
    lv.rect(t1, 4, t1, FLOOR - 1, HOUSE)
    lv.carve(t0 + 1, 4, t1 - 1, FLOOR - 1)
    lv.carve(t0, 37, t0, 40)  # its door
    lv.water(t0, 37, t0, 40)
    lv.wp(t0, 37, t0, 40, label="the tower door")
    surf = 24  # the water's surface inside the tower
    lv.water(t0 + 1, surf, t1 - 1, FLOOR - 1, UP)
    lv.wp(t0 + 1, surf, t1 - 1, surf + 1, label="the tower's water")
    lv.rect(t0 + 1, surf - 2, t0 + 1, surf - 2, HOUSE)
    lv.wp(t0 + 1, surf - 3, ground=True, label="tower ledge")
    for i, row in enumerate((surf - 7, surf - 12, surf - 17)):
        x = t1 - 1 if i % 2 == 0 else t0 + 1
        lv.rect(x, row, x, row, HOUSE)
        lv.wp(x, row - 1, ground=True, label=f"belfry rest {i}")
        lv.coin((t0 + t1) // 2, row - 3)
    lv.rect(t0 - 2, 2, t1 + 4, 3, HOUSE)  # the roof
    lv.carve(t0 + 1, 2, t1 - 1, 3)
    lv.rect(t0 - 2, 0, t0 - 2, 1, HOUSE)
    lv.wp(t1, 1, t1 + 2, 1, ground=True, label="the tower roof")
    lv.coins(t0 - 1, -1, t1 + 3, 2)
    lv.flag(t1 + 3, 1)
    lv.wp(t1 + 3, 1, label="flag")

    dress(lv, range(12, 120, 3), CEIL + 2, (SEAWEED, ANEMONE, CORAL, STARFISH), seed=39)
    return lv
