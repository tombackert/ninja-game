"""Level 23 - Sunken Galleon (wreck and reef, deep water).

A shipwreck on the sea floor, its stern castle still out of the water:
debris to hop on at the surface, a hatch in the main deck down into the
flooded upper hold, air trapped behind the bulkhead beams, a hatch further
down into the cargo hold between crates and treasure, back up into the
half-flooded stern cabin and out of its door, and a wall-jump climb between
the stern tower and a notched rock pillar up to the flag on the guarded
tower top.
"""

from tools.worlds.builder import Level, box, crate_chain, perforate

SEA = 16
BOTTOM = 60
FLOOR = 40  # sea floor row


def build() -> Level:
    lv = Level(23, "reef", background="background-deep.png", clouds=False)
    lv.water(11, SEA, 140, BOTTOM)

    # --- Start rock and the debris at the surface ------------------------------------
    lv.rect(0, 14, 10, BOTTOM)
    lv.rect(141, SEA - 3, 144, BOTTOM)  # the cliff at the far end of the sea
    lv.spawn(3, 13)
    lv.decor(7, 13, 10)
    lv.coins(4, 11, 8, 2)
    lv.wp(8, 13, 10, 13, ground=True, label="start rock")
    lv.rect(11, FLOOR, 140, BOTTOM)
    crate_chain(lv, [(14, SEA - 1, 2), (20, SEA - 1, 2), (26, SEA - 1, 3)], t="wreck", label="debris")
    lv.big_decor(18, FLOOR - 1, 6)
    lv.big_decor(25, FLOOR - 1, 6)
    lv.big_decor(31, FLOOR - 1, 8)  # the galleon's anchor
    lv.decor(22, FLOOR - 1, 9)

    # --- The hull ------------------------------------------------------------------------
    lv.rect(36, 22, 118, 39, "wreck")
    lv.carve(38, 24, 116, 30)  # upper hold
    lv.carve(38, 33, 116, 37)  # cargo hold
    for x in (54, 84, 108):  # bulkhead beams: air stays trapped behind them
        lv.rect(x, 24, x, 26, "wreck")
    lv.coins(40, 20, 52, 3)
    lv.enemy(60, 21)
    lv.enemy(92, 21)

    # Hatch in the main deck, room A (flooded)
    lv.carve(44, 22, 46, 23)
    lv.wp(44, 18, 46, 21, label="deck hatch")
    lv.wp(44, 24, 46, 27, label="upper hold")
    lv.coins(40, 29, 52, 3)
    lv.enemy(50, 30)
    # Room B, behind the first beam: air under the deck
    lv.drain(55, 24, 83, 25)
    lv.wp(56, 28, 60, 30, label="under the beam")
    lv.wp(58, 25, 62, 26, label="trapped air")
    lv.coins(64, 28, 80, 4)

    # Hatch down into the cargo hold
    lv.carve(76, 31, 78, 32)
    lv.wp(76, 31, 78, 33, label="cargo hatch")
    for x, y, w, h in ((66, 36, 2, 2), (70, 35, 2, 3), (86, 36, 3, 2), (92, 34, 2, 4), (100, 36, 2, 2)):
        box(lv, x, y, w, h, t="wreck")  # crates
    lv.big_decor(81, 37, 9)  # treasure
    lv.coins(80, 35, 84, 2)
    lv.coins(95, 35, 99, 2)
    lv.enemy(97, 37)
    lv.enemy(75, 37)
    lv.wp(96, 33, 99, 37, label="cargo hold")

    # Room C, between the second and third beam: air again (past the third beam
    # the hatch up into the stern cabin lets it out), then up into the cabin
    lv.drain(85, 24, 107, 25)
    lv.carve(104, 31, 106, 32)
    lv.wp(104, 31, 106, 32, label="hatch up")
    lv.wp(103, 25, 107, 26, label="room C air")
    lv.wp(109, 27, 112, 30, label="under the third beam")
    lv.enemy(114, 30)

    # --- The stern castle, its cabin half out of the water --------------------------------
    lv.rect(102, 10, 118, 21, "wreck")
    lv.carve(104, 12, 116, 21)  # cabin
    lv.carve(110, 22, 112, 23)  # hatch from room C
    lv.drain(104, 12, 116, SEA - 1)
    lv.wp(110, 20, 112, 23, label="cabin hatch")
    lv.rect(113, SEA - 1, 116, SEA - 1, "wreck")  # ledge in the cabin
    lv.wp(113, SEA - 2, 116, SEA - 2, ground=True, label="cabin ledge")
    lv.coins(105, 13, 109, 2)
    lv.carve(117, 12, 118, SEA - 2)  # stern door
    lv.wp(117, 12, 118, SEA - 2, label="stern door")

    # --- Climb between the stern tower and a notched rock pillar ---------------------------
    lv.rect(108, -4, 118, 9, "wreck")  # stern tower on the castle
    lv.rect(122, -8, 124, FLOOR)  # rock pillar; the stern is the other wall
    perforate(lv, 122, -7, SEA - 2, solid=2, gap=1)  # notches break the wall slides
    lv.wp(119, 2, 121, 5, label="climb")
    lv.coins(120, 7, 120)
    lv.coins(120, -1, 120)
    lv.wp(119, -7, 121, -5, label="over the tower")
    lv.wp(112, -5, 117, -5, ground=True, label="tower top")
    lv.enemy(113, -5)
    lv.enemy(110, -5)
    lv.coins(109, -7, 116, 2)
    lv.coins(103, 8, 106, 1)  # on the castle roof below
    lv.flag(108, -5)
    lv.wp(108, -5, label="flag")
    return lv
