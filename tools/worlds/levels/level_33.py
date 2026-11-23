"""Level 33 - The Monolith Field (mars rock, alien stone, Mars sky).

Nobody knows who set them up. On a plain cut by chasms stand hundreds of
black slabs, smooth as glass, some on the ground, some hovering a body's
height above it, as if they had forgotten to come down. The way across
leads between them and over them: in under the first hovering slab and wall
to wall up between it and its neighbour, over the tops of a row of slabs
above a chasm, in through the window in a great slab and out of its far
side, down into the valley of the sleepers (the banner stands there),
under the tallest hovering slab and the long climb between it and its twin,
across the fragments of a broken slab that drift over the deepest chasm,
and up inside the gate, two slabs and a lintel, to the flag on top of it.
"""

from tools.worlds.builder import Level

BOTTOM = 84
G = 60  # the plain
SLAB = "stone"


def slab(lv: Level, x0: int, x1: int, top: int, bottom: int):
    lv.rect(x0, top, x1, bottom, SLAB)


def rests(lv: Level, x0: int, x1: int, spec, label: str):
    for side, row in spec:
        rx = x0 if side < 0 else x1
        lv.rect(rx, row, rx, row, SLAB)
        lv.wp(rx, row - 1, ground=True, label=f"{label} rest {row}")
        lv.coin((x0 + x1) // 2, row - 3)


def chasm(lv: Level, x0: int, x1: int):
    lv.carve(x0, G, x1, BOTTOM)


def build() -> Level:
    lv = Level(33, "mars", background="background-mars.png")
    lv.rect(-28, G, 150, BOTTOM)

    # --- The edge of the field ----------------------------------------------------------------------------
    lv.spawn(-24, G - 1)
    lv.decor(-20, G - 1, 3)
    lv.big_decor(-14, G - 1, 5)
    lv.coins(-18, G - 3, 0, 3)
    lv.enemy(-6, G - 1)
    lv.flamejet(-11, G, "up", on=40, phase=110)  # fumaroles in the plain
    lv.wp(0, G - 1, 3, G - 1, ground=True, label="the field's edge")

    # --- Under the first hovering slab, up between it and its neighbour -----------------------------------------
    slab(lv, 5, 7, 30, G - 4)  # hovering
    slab(lv, 12, 14, 38, G - 1)
    lv.wp(8, G - 3, 11, G - 1, label="under the first slab")
    rests(lv, 8, 11, [(1, 54), (-1, 48), (1, 43)], "first pair")
    lv.wp(12, 37, 14, 37, ground=True, label="first slab top")

    # --- Over the row of slabs above the chasm -------------------------------------------------------------------
    chasm(lv, 15, 43)
    for i, (x0, x1, top) in enumerate(((18, 19, 39), (23, 25, 37), (30, 31, 38))):
        slab(lv, x0, x1, top, BOTTOM)
        lv.wp(x0, top - 1, x1, top - 1, ground=True, label=f"row slab {i}")
        lv.coin(x0, top - 3)
    lv.enemy(24, 36)

    # --- In through the window of the great slab --------------------------------------------------------------------
    slab(lv, 34, 40, 24, BOTTOM)
    lv.carve(34, 36, 40, 37)  # the window
    lv.wp(36, 37, 38, 37, ground=True, label="the window")
    lv.coins(35, 37, 39, 2)
    slab(lv, 44, 46, 42, BOTTOM)
    lv.wp(44, 41, 46, 41, ground=True, label="below the window")

    # --- The valley of the sleepers ---------------------------------------------------------------------------------
    for i, (x0, x1) in enumerate(((49, 51), (55, 56))):  # slabs lying on their sides
        slab(lv, x0, x1, G - 1, G - 1)
    lv.wp(52, G - 1, 54, G - 1, ground=True, label="the valley")
    lv.checkpoint(53, G - 1)
    lv.enemy(58, G - 1)
    lv.decor(48, G - 1, 3)
    lv.flamejet(47, G, "up", on=40)

    # --- Up between the tallest hovering slab and its twin ----------------------------------------------------------
    slab(lv, 61, 63, 12, G - 4)  # hovering
    slab(lv, 68, 70, 20, G - 1)
    lv.wp(64, G - 3, 67, G - 1, label="under the tall slab")
    rests(lv, 64, 67, [(1, 54), (-1, 48), (1, 42), (-1, 36), (1, 30), (-1, 25)], "twins")
    lv.wp(68, 19, 70, 19, ground=True, label="twin top")

    # --- The fragments over the deepest chasm -----------------------------------------------------------------------
    chasm(lv, 71, 118)
    frags = ((75, 20, 2), (80, 19, 2), (86, 21, 3), (93, 20, 1), (98, 18, 2), (104, 19, 3), (111, 18, 2))
    for i, (x, top, w) in enumerate(frags):
        slab(lv, x, x + w - 1, top, top)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"fragment {i}")
        lv.coin(x + w // 2, top - 2)
    lv.enemy(105, 18)

    # --- The gate: up inside it on to the lintel --------------------------------------------------------------------
    lv.rect(119, G - 1, 150, G - 1)
    lv.rect(115, 18, 117, BOTTOM, SLAB)  # a landing slab
    lv.wp(115, 17, 117, 17, ground=True, label="before the gate")
    slab(lv, 121, 123, 4, G - 1)  # the west pillar
    slab(lv, 128, 130, 4, G - 1)  # the east pillar
    lv.carve(121, 18, 123, 20)  # a door through the west pillar
    lv.rect(119, 21, 123, 21, SLAB)
    lv.wp(124, 18, 127, 20, label="inside the gate")
    rests(lv, 124, 127, [(1, 15), (-1, 10)], "gate")
    lv.rect(120, 2, 131, 3, SLAB)  # the lintel
    lv.carve(124, 2, 127, 3)  # cracked through
    lv.wp(128, 1, 130, 1, ground=True, label="the lintel")
    lv.coins(121, 0, 130, 3)
    lv.flag(131, 1)
    lv.wp(131, 1, label="flag")
    return lv
