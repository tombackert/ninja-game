"""Level 32 - The Geode (mars rock, crystal, Mars sky).

Under the red plain a lava bubble cooled millions of years ago into a hollow
as round as a ball, and water that seeped in for ages lined it with crystal.
A lava tube leads into it at the bottom; the only way out is the hole at its
top, where the crystal chandelier hangs. The climb winds round the inside of
the ball: east along its floor among the crystals that grew up out of it,
wall to wall up the east side between the rock and a column of crystal,
back west across the middle from shard to shard (the long gaps need a dash),
up the west side between the wall and a second column, and east again under
the dome to the chandelier. Between its two longest crystals up to the hole
and out on to the plain, where the flag stands.
"""

from tools.worlds.builder import Level

BOTTOM = 112
CX, CY, RX, RY = 64, 60, 46, 44  # the geode: an ellipse
CRYSTAL = "reef"
SURFACE = 10  # the plain above


def inside(x: int, y: int, shrink: float = 0.0) -> bool:
    return ((x + 0.5 - CX) / (RX - shrink)) ** 2 + ((y + 0.5 - CY) / (RY - shrink)) ** 2 <= 1.0


def shards(lv: Level, spec, label: str):
    """Floating crystal shards (x0, top, width), a route stop and a coin on each."""
    for i, (x, top, w) in enumerate(spec):
        lv.rect(x, top, x + w - 1, top + (1 if w > 1 else 0), CRYSTAL)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"{label} {i}")
        lv.coin(x + w // 2, top - 2)


def slab(lv: Level, x0: int, y0: int, x1: int, y1: int):
    """A slab of crystal grown on the geode's wall: fills x0..x1, y0..y1 where it
    is hollow, so the wall there is flat."""
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if inside(x, y):
                lv.solid[(x, y)] = CRYSTAL


def rests(lv: Level, x0: int, x1: int, spec, label: str):
    for side, row in spec:
        rx = x0 if side < 0 else x1
        lv.rect(rx, row, rx, row, CRYSTAL)
        lv.wp(rx, row - 1, ground=True, label=f"{label} rest {row}")
        lv.coin((x0 + x1) // 2, row - 3)


def build() -> Level:
    lv = Level(32, "mars", background="background-mars.png")
    lv.rect(-20, SURFACE, 130, BOTTOM)

    # --- The geode: rock lined with crystal --------------------------------------------------------
    for y in range(CY - RY - 2, CY + RY + 3):
        for x in range(CX - RX - 2, CX + RX + 3):
            if inside(x, y):
                lv.solid.pop((x, y), None)
            elif inside(x, y, -1.6):
                lv.solid[(x, y)] = CRYSTAL
    lv.rect(CX - RX, 88, CX + RX, CY + RY + 2)  # the floor: crystal rubble on rock
    lv.rect(CX - RX, 88, CX + RX, 88, CRYSTAL)

    # --- The lava tube and the floor: east among the crystals -------------------------------------------------
    lv.carve(-20, 84, 30, 87)
    lv.rect(-20, 88, 30, 88)
    lv.spawn(-16, 87)
    lv.decor(-12, 87, 3)
    lv.coins(-10, 85, 20, 3)
    lv.enemy(10, 87)
    lv.wp(24, 87, 28, 87, ground=True, label="the tube's mouth")
    for i, (x, h) in enumerate(((40, 2), (48, 1), (55, 2), (64, 2), (72, 1), (80, 2))):
        lv.rect(x, 88 - h, x + 1, 87, CRYSTAL)
        lv.wp(x, 87 - h, x + 1, 87 - h, ground=True, label=f"floor crystal {i}")
        lv.coin(x, 85 - h)
    lv.enemy(60, 87)
    lv.enemy(76, 87)
    for x in (35, 52, 68, 85):  # small crystals between
        lv.decor(x, 87, 0)

    # --- The east side: between the rock and a crystal column ------------------------------------------------------
    slab(lv, 100, 46, 112, 87)  # a slab of crystal on the wall
    lv.rect(95, 56, 95, 84, CRYSTAL)  # the column, a gap under it
    lv.rect(94, 56, 96, 57, CRYSTAL)
    lv.wp(96, 85, 99, 87, label="east column foot")
    rests(lv, 96, 99, [(1, 81), (-1, 75), (1, 69), (-1, 63), (1, 59)], "east")
    lv.wp(94, 55, 96, 55, ground=True, label="east column top")

    # --- Across the middle, west from shard to shard ---------------------------------------------------------------
    shards(lv, [(88, 55, 2), (82, 54, 2), (75, 54, 3), (68, 53, 1), (61, 53, 2)], "middle shard")
    lv.rect(51, 52, 56, 53, CRYSTAL)
    lv.wp(51, 51, 56, 51, ground=True, label="the wide shard")
    lv.enemy(54, 51)
    shards(lv, [(45, 52, 1)], "last middle shard")

    # --- The west side: between the wall and a second column --------------------------------------------------------
    slab(lv, 14, 30, 28, 53)  # a slab of crystal on the wall
    lv.rect(29, 52, 39, 53, CRYSTAL)  # a shelf grown out of the wall
    lv.wp(36, 51, 39, 51, ground=True, label="west shelf")
    lv.rect(34, 32, 34, 47, CRYSTAL)  # the column, a gap under it
    lv.rect(33, 32, 35, 33, CRYSTAL)
    rests(lv, 29, 33, [(-1, 46), (1, 41), (-1, 36)], "west")
    lv.wp(33, 31, 35, 31, ground=True, label="west column top")
    lv.checkpoint(29, 51)  # halfway

    # --- Under the dome, east to the chandelier ---------------------------------------------------------------------
    shards(lv, [(40, 31, 2), (46, 30, 2), (52, 30, 3), (58, 29, 1)], "dome shard")
    lv.rect(60, 29, 67, 29, CRYSTAL)  # under the chandelier
    lv.wp(62, 28, 65, 28, label="under the chandelier")
    lv.rect(61, 12, 61, 25, CRYSTAL)  # its two longest crystals
    lv.rect(66, 12, 66, 25, CRYSTAL)
    for x, bottom in ((56, 20), (58, 22), (70, 22), (72, 19)):  # and the shorter ones
        lv.rect(x, 12, x, bottom, CRYSTAL)
    lv.carve(62, SURFACE, 65, 17)  # the hole at the top
    rests(lv, 62, 65, [(-1, 22), (1, 18)], "chandelier")

    # --- The plain --------------------------------------------------------------------------------------------------
    lv.wp(66, SURFACE - 1, 69, SURFACE - 1, ground=True, label="the plain")
    lv.rect(76, SURFACE - 2, 77, SURFACE - 1)
    lv.enemy(82, SURFACE - 1)
    lv.decor(72, SURFACE - 1, 3)
    lv.big_decor(92, SURFACE - 1, 5)
    lv.coins(68, SURFACE - 3, 84, 2)
    lv.flag(88, SURFACE - 1)
    lv.wp(88, SURFACE - 1, label="flag")
    return lv
