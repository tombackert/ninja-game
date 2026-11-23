"""Level 29 - The Hourglass (sandstone and city stone, desert sky).

Out in the dunes stands the hourglass of the old kings, a monument as tall
as a tower, cut into the shape of the glass it is named after: a wide
chamber at the bottom, a narrow waist, and a wide chamber on top. Its sand
ran out long ago; what was left of it hardened into floating steps of
sandstone. Up the steps at the plinth and in through the door, then up
through the lower chamber from step to step: east along the floor of it,
back west under its vault, on to the stone under the waist and wall to
wall up the waist itself. The banner stands where the waist opens into
the upper chamber. There the steps hang over the empty bowl: up its east
side, from step to step back west, a turn at the west wall and east again
on to the stone under the upper neck, up the neck and out on to the crown
of the hourglass with the flag.
"""

from tools.worlds.builder import Level
from tools.worlds.kits.desert import CITY, ROCK

BOTTOM = 136
G = 120  # the desert floor around the monument


def bulb(lv: Level, x0: int, x1: int, y0: int, y1: int, top_c: int, bot_c: int):
    """Carve a chamber x0..x1, y0..y1 with its corners filled back in at 45
    degrees: `top_c` rows of vault at the top, `bot_c` rows of bowl at the
    bottom (a stair of one column per row)."""
    lv.carve(x0, y0, x1, y1)
    for k in range(top_c):
        lv.rect(x0, y0 + k, x0 + top_c - 1 - k, y0 + k, CITY)
        lv.rect(x1 - top_c + 1 + k, y0 + k, x1, y0 + k, CITY)
    for k in range(bot_c):
        lv.rect(x0, y1 - k, x0 + bot_c - 1 - k, y1 - k, CITY)
        lv.rect(x1 - bot_c + 1 + k, y1 - k, x1, y1 - k, CITY)


def steps(lv: Level, spec, label: str):
    """Floating sandstone steps (x0, top, width), a route stop and a coin on each."""
    for i, (x, top, w) in enumerate(spec):
        lv.rect(x, top, x + w - 1, top, ROCK)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"{label} {i}")
        lv.coin(x + w // 2, top - 2)


def shaft(lv: Level, x: int, y_top: int, y_bottom: int, rests, label: str):
    """A three-wide shaft x..x+2 from y_top to y_bottom, climbed wall to wall,
    with one-tile rest ledges (side, row) and a coin over each."""
    lv.carve(x, y_top, x + 2, y_bottom)
    for side, row in rests:
        rx = x if side < 0 else x + 2
        lv.rect(rx, row, rx, row, ROCK)
        lv.wp(rx, row - 1, ground=True, label=f"{label} rest {row}")
        lv.coin(x + 1, row - 3)


def build() -> Level:
    lv = Level(29, ROCK, background="background-desert.png")

    # --- The dunes before the monument -----------------------------------------------------------
    lv.rect(-80, G, 96, BOTTOM)
    lv.spawn(-76, G - 1)
    lv.decor(-73, G - 1, 1)
    lv.big_decor(-70, G - 1, 2)
    # quicksand between the broken columns of older hourglasses: (pit width, column top, column width)
    x = -66
    for i, (pit, top, w) in enumerate(
        ((4, G - 2, 2), (5, G - 3, 2), (3, G - 1, 1), (6, G - 3, 3), (4, G - 4, 1), (5, G - 2, 2), (7, G - 2, 3))
    ):
        lv.carve(x, G, x + pit - 1, BOTTOM)
        x += pit
        lv.rect(x, top, x + w - 1, BOTTOM, CITY)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"column {i}")
        lv.coin(x + w // 2, top - 3)
        x += w
    lv.enemy(-14, G - 1)
    lv.rect(-5, G - 1, -3, G - 1)  # a dune
    lv.big_decor(-1, G - 1, 2)
    lv.decor(1, G - 1, 1)
    lv.coins(-2, G - 3, 4, 2)

    # --- The monument: plinth, body and crown ---------------------------------------------------------
    lv.rect(14, 38, 66, G - 1, CITY)
    lv.rect(8, 116, 72, G - 1, CITY)  # the plinth
    lv.rect(4, 118, 7, G - 1, CITY)  # a step up to it
    lv.wp(8, 115, 12, 115, ground=True, label="plinth")
    lv.enemy(11, 115)
    for x in range(14, 67, 4):  # battlements on the crown
        if x not in range(36, 48):
            lv.rect(x, 37, x, 37, CITY)
    lv.carve(14, 111, 21, 115)  # the door

    # --- The lower chamber: east along the floor, back west under the vault --------------------------
    bulb(lv, 22, 58, 94, 115, top_c=12, bot_c=0)
    lv.decor(24, 115, 1)
    lv.big_decor(56, 115, 2)
    lv.enemy(40, 115)
    lv.coins(23, 113, 25, 2)
    steps(lv, [(27, 114, 2), (32, 112, 2), (36, 110, 1), (41, 108, 2), (47, 106, 2)], "lower step")
    lv.crumble(36, 110)  # not every step hardened well: some crumble back into sand
    steps(lv, [(50, 104, 3), (44, 102, 3)], "lower turn")
    # the stone under the waist, the waist hanging into the chamber over it
    lv.rect(37, 100, 43, 100, ROCK)
    lv.rect(38, 94, 38, 96, CITY)
    lv.rect(42, 94, 42, 96, CITY)
    lv.wp(39, 99, 41, 99, ground=True, label="under the waist")

    # --- The waist: wall to wall ----------------------------------------------------------------------
    shaft(lv, 39, 75, 96, [(1, 92), (-1, 87), (1, 82), (-1, 78)], "waist")

    # --- The upper chamber: over the empty bowl -----------------------------------------------------------
    bulb(lv, 20, 60, 48, 74, top_c=6, bot_c=10)
    lv.wp(43, 74, 45, 74, ground=True, label="bowl")
    lv.checkpoint(44, 74)  # halfway
    lv.wp(58, 65, 59, 65, ground=True, label="bowl rim")
    steps(lv, [(55, 64, 2), (49, 62, 2), (42, 61, 2), (37, 58, 1), (31, 56, 2)], "upper step")
    lv.crumble(49, 62, 50)
    lv.crumble(37, 58)
    steps(lv, [(28, 53, 3)], "west turn")
    lv.rect(33, 51, 42, 51, ROCK)  # the stone under the upper neck
    lv.wp(36, 50, 40, 50, ground=True, label="under the neck")
    lv.coin(37, 49)
    lv.enemy(41, 50)

    # --- The upper neck and the crown --------------------------------------------------------------------
    shaft(lv, 39, 38, 47, [(-1, 44), (1, 41)], "neck")
    lv.wp(43, 37, 46, 37, ground=True, label="the crown")
    lv.coins(46, 35, 58, 3)
    lv.enemy(52, 37)
    lv.big_decor(64, 37, 2)
    lv.flag(60, 37)
    lv.wp(60, 37, label="flag")
    return lv
