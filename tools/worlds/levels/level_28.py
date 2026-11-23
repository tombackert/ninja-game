"""Level 28 - The Sinkhole (sandstone, desert sky). The first level going down.

One night the desert floor fell in. The caravan road now ends at the lip of
a hole as deep as a mountain is high: a narrow throat that opens into a
bell-shaped cavern, its walls hanging over the dark at the bottom. There is
no climbing down an overhanging wall: the way down is from ledge to ledge,
each tucked in under the rock above it. Drop off the lip, slide down the
face of the overhang and tuck in under it; across the throat from side to
side; then out into the bell, where only a dash at the right moment of the
fall reaches the swallows' cave in its wall. Down the hanging stair of
ledges under the cave, across the rubble pillars over the dark to the old
river's tunnel, along the riverbed past the sinks in its floor and up the
dry spring's shaft to the oasis on the far side, with the flag.
"""

from tools.worlds.builder import Level, perforate
from tools.worlds.kits.desert import ROCK

BOTTOM = 172


def pocket(
    lv: Level, side: str, face: int, floor: int, depth: int = 3, height: int = 3, lip: int = 1, lip_rows: int = 3
):
    """A pocket carved into a shaft wall (`side` 'W' or 'E', its face column `face`):
    `height` rows of air over floor row `floor`, `depth` columns deep, and the
    rock over its mouth sticking out `lip` columns into the shaft for `lip_rows`
    rows: a ledge under an overhang. Returns its floor columns (x0, x1)."""
    if side == "E":
        x0, x1 = face, face + depth - 1
        lv.carve(x0, floor - height, x1, floor - 1)
        if lip:
            lv.rect(face - lip, floor - height - lip_rows, face - 1, floor - height - 1)
    else:
        x0, x1 = face - depth + 1, face
        lv.carve(x0, floor - height, x1, floor - 1)
        if lip:
            lv.rect(face + 1, floor - height - lip_rows, face + lip, floor - height - 1)
    return x0, x1


def build() -> Level:
    lv = Level(28, ROCK, background="background-desert.png")

    # --- The desert floor and the caravan road ----------------------------------------------
    lv.rect(-2, 20, 160, BOTTOM)  # the ground the sinkhole is cut into
    lv.rect(32, 14, 74, 19)  # the far rim: a rocky ridge
    lv.rect(36, 12, 66, 13)
    lv.spawn(3, 19)
    lv.big_decor(1, 19, 4)
    lv.decor(7, 19, 3)  # the caravan's lost cargo
    lv.decor(8, 19, 3)
    lv.decor(12, 19, 5)
    lv.big_decor(15, 19, 3)
    lv.enemy(10, 19)
    lv.coins(4, 17, 12, 2)
    lv.wp(16, 19, 19, 19, ground=True, label="the lip")
    lv.big_decor(50, 11, 3)
    lv.decor(42, 11, 5)

    # --- The throat: from side to side, each ledge tucked under the rock above -------------------
    n = 14  # ledges down the throat, six rows apart
    lv.carve(20, 20, 31, 23)  # the mouth
    lv.carve(23, 24, 30, 31 + 6 * n - 4)  # the throat, eight wide
    west, east = 22, 31  # the throat's wall faces
    lv.wp(20, 23, 22, 23, ground=True, label="first shelf")
    for i in range(n):
        side, floor = ("E" if i % 2 == 0 else "W"), 31 + 6 * i
        lip = 1 if i in (0, n - 1) else 2  # how far the rock over its mouth sticks out
        face = east if side == "E" else west
        x0, x1 = pocket(lv, side, face, floor, depth=3 + lip - 1, height=4 - lip, lip=lip)
        lv.wp(x0, floor - 1, x1, floor - 1, ground=True, label=f"throat ledge {i}")
        lv.coin((x0 + x1) // 2, floor - 2)
    b0 = 31 + 6 * n - 3  # the bell's first row
    lv.checkpoint(21, b0 - 4)  # halfway: the last ledge before the bell

    # --- The bell: its walls hang back over the dark -----------------------------------------------
    for r0, r1, x0, x1 in ((0, 6, 18, 35), (7, 14, 16, 37), (15, 22, 14, 39), (23, BOTTOM - b0, 13, 40)):
        lv.carve(x0, b0 + r0, x1, b0 + r1)
    # the swallows' cave: its roof sticks out over the bell, the wall above it hangs far back
    lv.carve(13, b0, 17, b0 + 9)
    lv.rect(13, b0 + 10, 17, b0 + 10)
    lv.carve(13, b0 + 11, 16, b0 + 12)
    lv.wp(13, b0 + 12, 16, b0 + 12, ground=True, label="the swallows' cave")
    lv.decor(13, b0 + 12, 5)
    # the hanging stair under the cave: each ledge one further in
    for i, (row, x0, x1) in enumerate(
        ((17, 14, 16), (22, 14, 14), (27, 13, 14), (32, 13, 13), (37, 13, 14), (42, 13, 13))
    ):
        lv.rect(x0, b0 + row, x1, b0 + row)
        lv.wp(x0, b0 + row - 1, x1, b0 + row - 1, ground=True, label=f"hanging stair {i}")
    # rubble pillars over the dark
    for i, (x0, x1, top) in enumerate(((20, 20, 45), (27, 27, 46), (34, 34, 44))):
        lv.rect(x0, b0 + top, x1, BOTTOM)
        lv.wp(x0, b0 + top - 1, x1, b0 + top - 1, ground=True, label=f"rubble pillar {i}")
        lv.coin(x0, b0 + top - 3)
        if i == 1:  # loose rubble on top
            lv.crumble(x0, b0 + top)

    # --- The old river's tunnel: up the riverbed past the sinks in its floor ----------------------------
    # (first column, floor row, sink width): stretches ten columns long, each two rows higher
    fl = b0 + 46
    sinks = (5, 6, 5, 6, 6, 5, 6, 5)
    x = 41
    for i, w in enumerate(sinks):
        lv.carve(x, fl - 4, x + 9, fl - 1)
        px = x + 3
        lv.carve(px, fl, px + w - 1, BOTTOM)
        if i in (1, 4, 6):  # the floor is still falling in at the sink's edge
            lv.crumble(px - 1, fl)
        lv.wp(px + w, fl - 1, px + w + 1, fl - 1, ground=True, label=f"riverbed sink {i}")
        lv.coin(px + w // 2, fl - 2)
        lv.rect(x + 7, fl - 4, x + 7, fl - 3)  # a stalactite
        if i in (2, 5):
            lv.enemy(x + 9, fl - 1)
        x += 10
        fl -= 2
    lv.carve(x, fl - 4, x + 7, fl - 1)

    # --- Up the dry spring into the wadi, to the oasis ---------------------------------------------------
    sx = x + 5  # the spring's shaft: columns sx..sx+2
    top = fl - 26  # the wadi's floor
    lv.carve(sx, top, sx + 2, fl - 1)
    perforate(lv, sx - 1, top + 1, fl - 2, solid=2, gap=1)
    perforate(lv, sx + 3, top + 1, fl - 2, solid=2, gap=1)
    lv.carve(sx - 3, 20, sx + 30, top - 1)  # the wadi, open to the sky
    lv.rect(sx + 31, 14, sx + 34, BOTTOM)
    lv.wp(sx, fl - 4, sx + 2, fl - 1, label="the spring's foot")
    rest = top + 13
    lv.rect(sx + 2, rest, sx + 2, rest)  # a knob halfway up
    lv.wp(sx + 2, rest - 1, ground=True, label="spring rest")
    lv.coins(sx + 1, rest + 6, sx + 1)
    lv.coins(sx + 1, rest - 5, sx + 1)
    lv.wp(sx + 3, top - 1, sx + 5, top - 1, ground=True, label="the spring")
    # the wadi's floor: quicksand pools between rocks
    for i, (x0, x1, h) in enumerate(((sx + 9, sx + 10, 1), (sx + 14, sx + 15, 2), (sx + 19, sx + 20, 1))):
        lv.carve(x0 - 2, top, x0 - 1, BOTTOM)  # a pool of quicksand before each rock
        lv.rect(x0, top - h, x1, top - 1)
        lv.wp(x0, top - h - 1, x1, top - h - 1, ground=True, label=f"wadi rock {i}")
    lv.big_decor(sx + 5, top - 1, 2)
    lv.big_decor(sx + 23, top - 1, 2)
    lv.decor(sx + 16, top - 1, 1)
    lv.decor(sx + 21, top - 1, 0)
    lv.enemy(sx + 22, top - 1)
    lv.coins(sx + 4, top - 3, sx + 20, 3)
    lv.flag(sx + 25, top - 1)
    lv.wp(sx + 25, top - 1, label="flag")
    return lv
