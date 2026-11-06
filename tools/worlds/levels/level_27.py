"""Level 27 - Hoodoo Valley (sandstone hoodoos over quicksand, desert sky).

Wind and rain carved this valley into hoodoos: thin stems of soft sandstone
wearing wide caps of harder rock, balanced boulders on needles, all standing
in quicksand. The caps are easy to hop; what takes skill is getting from
one level of caps to the next: up the slot between two stems, wall to wall
on their worn, notched faces, and out past the cap that overhangs the slot.

Down from the valley rim over the low caps to the Twin Stems: through the
tunnel in the rock they stand on, up the slot between them and out round
the east one's cap. Across the balanced rocks, over the natural arch and
the tall caps to the Anvil, where the banner stands. Then through the
Needle's Eye (a hole worn through a stone needle) into the slot behind it,
with nothing under it but quicksand, up to the top of the Chimney Rock.
Down over the toadstools, along the Fallen Giant (a hoodoo that toppled
and broke), through the rock under the Organ Pipes and up between them,
across the pins (pebbles balanced on the thinnest needles) to the foot of
the Sentinel, the tallest hoodoo of the valley, up between it and the
Watchman spire and round its great cap to the flag.
"""

from tools.worlds.builder import Level
from tools.worlds.kits.desert import ROCK, balanced_rock, hoodoo, notch

BOTTOM = 90


def caps_run(lv: Level, caps, label: str, coins=True):
    """Hoodoos to hop: (x0, x1, top, stem) each, a route stop on the east end of every cap."""
    for i, (x0, x1, top, stem) in enumerate(caps):
        hoodoo(lv, x0, x1, top, stem, BOTTOM)
        lv.wp(max(x0, x1 - 3), top - 1, x1, top - 1, ground=True, label=f"{label} {i}")
        if coins:
            lv.coin((x0 + x1) // 2, top - 3)


def rocks_run(lv: Level, rocks, label: str, w: int = 2):
    """Balanced rocks (x, top) `w` wide to hop, a coin over each gap."""
    for i, (x, top) in enumerate(rocks):
        balanced_rock(lv, x, top, BOTTOM, w=w, h=2 if w > 1 else 1)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"{label} {i}")
        lv.coin(x - 2, top - 3)


def build() -> Level:
    lv = Level(27, ROCK, background="background-desert.png")

    # --- The valley rim -------------------------------------------------------------------
    lv.rect(0, 50, 14, BOTTOM)
    lv.spawn(3, 49)
    lv.big_decor(1, 49, 4)
    lv.decor(6, 49, 4)
    lv.big_decor(9, 49, 3)
    lv.decor(12, 49, 5)
    lv.enemy(11, 49)
    lv.coins(4, 47, 10, 2)
    lv.wp(11, 49, 14, 49, ground=True, label="valley rim")

    # --- Down over the low caps ---------------------------------------------------------------
    caps_run(
        lv,
        [
            (17, 23, 53, (19, 20)),
            (27, 32, 56, (29, 30)),
            (36, 41, 53, (38, 39)),
            (45, 50, 55, (47, 48)),
            (54, 59, 52, (56, 57)),
            (63, 67, 55, (65, 65)),
        ],
        "low cap",
    )
    lv.enemy(30, 55)
    lv.decor(39, 52, 4)
    lv.big_decor(19, 52, 4)

    # --- The Twin Stems: through the rock they stand on, up the slot, out round the cap ------------------
    x = 70  # the rock the twins stand on: x .. x+18
    ped = 58  # its top row
    lv.rect(x, ped, x + 18, BOTTOM)
    lv.carve(x, ped + 1, x + 7, ped + 3)  # a tunnel in from the west, under the slot
    lv.carve(x + 5, ped, x + 7, ped)
    lv.wp(x, ped + 3, x + 2, ped + 3, ground=True, label="twin stems tunnel")
    hoodoo(lv, x - 2, x + 7, 30, (x + 3, x + 4), ped - 1)  # the west twin, tall
    hoodoo(lv, x + 6, x + 14, 41, (x + 8, x + 9), ped - 1)  # the east twin, its cap over the slot
    notch(lv, x + 4, 33, 50)
    notch(lv, x + 8, 44, ped - 2)
    lv.wp(x + 5, 48, x + 7, 51, label="twin stems slot")
    lv.coins(x + 6, ped - 5, x + 6)
    lv.coins(x + 6, 46, x + 6)
    lv.coin(x + 5, 39)
    lv.wp(x + 8, 40, x + 14, 40, ground=True, label="east twin cap")
    lv.big_decor(x + 12, 40, 4)
    lv.decor(x + 1, ped - 1, 5)
    lv.big_decor(x + 15, ped - 1, 3)
    x += 14  # the east twin cap's last column

    # --- The balanced rocks ------------------------------------------------------------------------
    rocks_run(lv, [(x + 5, 41), (x + 12, 40), (x + 19, 42), (x + 26, 40), (x + 33, 41), (x + 40, 39)], "balanced rock")
    x += 41

    # --- The arch: a bridge of rock between two hoodoos ------------------------------------------------
    hoodoo(lv, x + 4, x + 9, 40, (x + 6, x + 7), BOTTOM)
    hoodoo(lv, x + 22, x + 27, 40, (x + 24, x + 25), BOTTOM)
    for dx, row in (
        (10, 39),
        (11, 38),
        (12, 37),
        (13, 37),
        (14, 37),
        (15, 37),
        (16, 37),
        (17, 38),
        (18, 38),
        (19, 39),
        (20, 39),
        (21, 39),
    ):
        lv.rect(x + dx, row, x + dx, row + 1)
    lv.wp(x + 7, 39, x + 9, 39, ground=True, label="arch foot")
    lv.wp(x + 13, 36, x + 16, 36, ground=True, label="arch")
    lv.coins(x + 11, 35, x + 18, 2)
    lv.enemy(x + 14, 36)
    lv.wp(x + 23, 39, x + 27, 39, ground=True, label="arch end")
    x += 27

    # --- The tall caps: too far apart to hop, a dash between each ----------------------------------------
    caps_run(
        lv,
        [
            (x + 8, x + 11, 39, (x + 9, x + 10)),
            (x + 19, x + 22, 38, (x + 20, x + 21)),
            (x + 30, x + 33, 40, (x + 31, x + 32)),
        ],
        "tall cap",
    )
    x += 33

    # --- The Anvil: a broad flat hoodoo, halfway ------------------------------------------------------
    hoodoo(lv, x + 4, x + 15, 41, (x + 8, x + 11), BOTTOM, cap_h=3)
    lv.wp(x + 4, 40, x + 7, 40, ground=True, label="the Anvil")
    lv.checkpoint(x + 6, 40)
    lv.decor(x + 10, 40, 4)
    lv.enemy(x + 13, 40)
    lv.coins(x + 8, 38, x + 14, 2)
    x += 15

    # --- The Needle's Eye: through the needle into the slot behind it, up the Chimney Rock --------------
    nx = x + 2  # the needle: columns nx, nx+1, its east face notched
    lv.rect(nx, 12, nx + 1, BOTTOM)
    lv.carve(nx, 38, nx + 1, 40)  # the eye
    notch(lv, nx + 1, 13, 36)
    hoodoo(lv, nx + 3, nx + 11, 18, (nx + 5, nx + 6), BOTTOM)  # the Chimney Rock, its cap over the slot
    notch(lv, nx + 5, 21, 42)
    lv.wp(nx, 38, nx + 1, 40, ground=True, label="the Needle's Eye")
    lv.wp(nx + 2, 29, nx + 4, 31, label="Chimney Rock slot")
    lv.coins(nx + 3, 35, nx + 3)
    lv.coins(nx + 3, 24, nx + 3)
    lv.wp(nx + 4, 17, nx + 10, 17, ground=True, label="Chimney Rock")
    lv.decor(nx + 9, 17, 5)
    x = nx + 11

    # --- Down over the toadstools ----------------------------------------------------------------------
    caps_run(
        lv,
        [
            (x + 4, x + 9, 22, (x + 6, x + 7)),
            (x + 14, x + 17, 26, (x + 15, x + 16)),
            (x + 23, x + 28, 29, (x + 25, x + 26)),
            (x + 33, x + 37, 32, (x + 35, x + 35)),
        ],
        "toadstool",
    )
    lv.enemy(x + 26, 28)
    lv.big_decor(x + 7, 21, 4)
    x += 37

    # --- The Fallen Giant: a hoodoo that toppled across the quicksand and broke --------------------------
    balanced_rock(lv, x + 5, 36, BOTTOM, w=3, h=2)  # it fell on to two boulders
    balanced_rock(lv, x + 13, 36, BOTTOM, w=3, h=2)
    lv.rect(x + 4, 34, x + 9, 35)  # the stem, broken in two
    lv.rect(x + 13, 34, x + 19, 35)
    lv.rect(x + 20, 32, x + 23, 35)  # and its cap, lying on its side
    lv.rect(x + 21, 31, x + 22, 31)
    lv.wp(x + 7, 33, x + 9, 33, ground=True, label="fallen giant stem")
    lv.wp(x + 13, 33, x + 15, 33, ground=True, label="fallen giant break")
    lv.wp(x + 21, 30, x + 22, 30, ground=True, label="fallen giant cap")
    lv.coins(x + 10, 31, x + 12)
    lv.enemy(x + 17, 33)
    lv.decor(x + 5, 33, 5)
    x += 23

    # --- The Organ Pipes: two worn pipes on a shelf of rock, a tunnel under them into the slot ------------
    lv.rect(x + 3, 36, x + 13, BOTTOM)
    lv.carve(x + 3, 37, x + 9, 39)  # the tunnel, in from the west
    lv.carve(x + 7, 36, x + 9, 36)  # and up into the slot
    lv.wp(x + 3, 39, x + 5, 39, ground=True, label="organ pipes tunnel")
    hoodoo(lv, x + 2, x + 8, 16, (x + 5, x + 6), 35)  # the west pipe, tall
    hoodoo(lv, x + 8, x + 15, 23, (x + 10, x + 11), 35)  # the east pipe, its cap over the slot
    notch(lv, x + 6, 19, 35)
    notch(lv, x + 10, 26, 35)
    lv.wp(x + 7, 30, x + 9, 33, label="organ pipes slot")
    lv.coins(x + 8, 31, x + 8)
    lv.coin(x + 7, 21)
    lv.wp(x + 10, 22, x + 15, 22, ground=True, label="east pipe")
    lv.decor(x + 13, 35, 5)
    lv.big_decor(x + 13, 22, 4)
    x += 15

    # --- The pins: pebbles balanced on the thinnest needles ----------------------------------------------
    pins = [
        (x + 4, 31),
        (x + 9, 29),
        (x + 14, 32),
        (x + 19, 30),
        (x + 24, 32),
        (x + 29, 29),
        (x + 34, 31),
        (x + 39, 30),
    ]
    rocks_run(lv, pins, "pin", w=1)
    x += 39

    # --- The Sentinel and the Watchman: up between them, round the great cap to the flag -------------------
    wx = x + 4  # the Watchman spire: columns wx, wx+1, a hole worn through it low down
    lv.rect(wx, 0, wx + 1, 27)
    lv.rect(wx, 31, wx + 1, BOTTOM)
    notch(lv, wx + 1, 1, 26)
    sx = wx + 6  # the Sentinel's stem: columns sx, sx+1; the slot between is four wide
    hoodoo(lv, sx - 2, sx + 13, 4, (sx, sx + 1), BOTTOM, cap_h=3)
    notch(lv, sx, 8, 29)
    lv.wp(wx, 28, wx + 1, 30, ground=True, label="the Watchman's eye")
    lv.wp(wx + 2, 19, sx - 1, 21, label="Sentinel slot")
    lv.wp(wx + 2, 10, sx - 1, 12, label="Sentinel slot top")
    lv.coins(wx + 3, 25, wx + 3)
    lv.coins(wx + 3, 17, wx + 3)
    lv.coins(wx + 3, 8, wx + 3)
    lv.wp(sx - 1, 3, sx + 2, 3, ground=True, label="the Sentinel")
    lv.coins(sx + 1, 1, sx + 9, 2)
    lv.big_decor(sx + 5, 3, 3)
    lv.flag(sx + 11, 3)
    lv.wp(sx + 11, 3, label="flag")
    return lv
