"""Level 31 - Rift Bridge (mars rock, Mars sky).

A rift splits the Martian crust, too wide to see across and too deep to
see the bottom. A natural bridge of rock spans it, but crags too tall to
climb stand on its back, so the crossing goes underneath: down through a
hole in the bridge on to the foot of a stalactite, then from hook to hook
along the claws that hang from its underside (step off a foot, drop past
it, dash beneath the claw and jump up on to the next foot, each one lower
over the abyss), and up again wall to wall in a hanging basket, out
through the next hole and across the bridge's back to the next crag. Six
times; twice (right after the spawn and right after the banner) the last
swing ends in a shaft open to the abyss instead of a basket, caught only
with a wall jump. The checkpoint banner stands on the crown of the bridge,
halfway. On the far side the last basket leads up a long chimney between
a needle of rock and the east cliff to the rim with the flag.
"""

import math

from tools.worlds.builder import Level
from tools.worlds.kits.mars import arch, hook, tooth

TOP = 28  # the bridge's top row
BOTTOM = 74  # the rift walls reach down to here; below them the abyss
WEST, EAST = 22, 314  # the cliff faces: the bridge spans WEST..EAST-1
RIM = 12  # top row of the east cliff
FIRST = 39  # row of the first foot under each hole


def under(x: int) -> int:
    """Underside of the bridge: thin under the middle, curving down into the cliffs."""
    d = min(x - WEST, EAST - 1 - x)
    springer = 16 * max(0.0, 1 - d / 14) ** 2
    return 33 + round(springer + 0.8 * math.sin(x / 4.3))


def underpass(lv: Level, x: int, gaps, name: str, rests=(), drop: int = 3, chimney=False, rim=None, guides=()) -> int:
    """Down through a hole in the bridge at columns x..x+2 on to the foot of a
    hook, a hop to the next hook's foot (`gaps[0]` open columns before it), then
    under one hanging hook after the other on to the next foot, each `drop`
    rows lower (`gaps[1:]`: the open columns between a hook and the next foot).
    The last swing ends in a hanging basket (a cup between a stem and a wall,
    the stem ending three rows over its floor) or, with `chimney`, in a shaft
    open below between the last hook's stem and a hanging wall. Either is climbed
    wall to wall (`rests`: (side, row) ledges) and left through the bridge
    again, or with `rim` (the east cliff's top row) on up between a needle and
    the cliff. `guides`: the drops (by number) the planner needs a waypoint at,
    under the foot it drops off. Returns the shaft's first column.

    For the shortcut checker the crossing is an obstacle: from the stop before
    the hole to the way out, nothing on the bridge's back may lead past the crag."""
    before = lv.route[-1].label
    lv.carve(x, TOP, x + 2, under(x + 1))
    f0, f1 = hook(lv, x - 2, under(x - 2), FIRST, foot=4, east=True)
    lv.wp(f0, FIRST - 1, f1, FIRST - 1, ground=True, label=f"{name} landing")
    lv.coin(f1, FIRST - 2)
    sx, row = f1 + 4, FIRST
    h0 = None
    hooks = len(gaps) if chimney else len(gaps) - 1
    for i, g in enumerate(gaps):
        sx += g
        if h0 is not None and i in guides:  # drop off the west end of the foot before, to swing under it
            lv.wp(h0 - 1, row + 2, h0 - 1, row + 3, label=f"{name} drop {i}", guide=True)
        row += drop
        if i == hooks:
            break
        h0, h1 = hook(lv, sx, under(sx), row, taper=not (chimney and i == hooks - 1))
        lv.wp(h0, row - 1, h1, row - 1, ground=True, label=f"{name} hook {i + 1}")
        lv.coin(h0, row - 2)
        sx += 4
    if chimney:
        cx = sx - 2
        lv.rect(cx + 3, under(cx + 3), cx + 3, row + 5)
        if hooks in guides:
            lv.wp(h0 - 1, row + 2, h0 - 1, row + 3, label=f"{name} drop {hooks}", guide=True)
    else:
        lv.rect(sx - 2, row, sx + 5, row)
        lv.rect(sx, under(sx), sx + 1, row - 3)
        lv.rect(sx + 5, under(sx + 5), sx + 5, row - 1)
        lv.wp(sx - 2, row - 1, sx - 1, row - 1, ground=True, label=f"{name} basket door")
        cx = sx + 2
        lv.wp(cx, row - 1, cx + 2, row - 1, ground=True, label=f"{name} basket")
    lv.carve(cx, TOP, cx + 2, under(cx + 1))
    for side, r in rests:
        rx = cx if side < 0 else cx + 2
        lv.rect(rx, r, rx, r)
        lv.wp(rx, r - 1, ground=True, label=f"{name} rest {r}")
        lv.coin(cx + 1, r - 3)
    if rim is None:
        lv.wp(cx - 1, TOP - 1, cx + 4, TOP - 1, ground=True, label=f"{name} out")
        lv.obstacle(
            f"{name} crag", x, TOP - 2, x + 2, TOP, before, f"{name} out", area=(x - 6, TOP - 16, cx + 6, TOP - 1)
        )
    else:
        lv.rect(cx - 2, rim + 1, cx - 1, TOP - 1)  # the needle
        lv.rect(cx - 2, rim, cx - 2, rim)
        lv.wp(cx + 3, rim - 1, cx + 6, rim - 1, ground=True, label="east rim")
        lv.obstacle(f"{name} crag", x, TOP - 2, x + 2, TOP, before, "east rim", area=(x - 6, rim - 6, cx + 8, TOP - 1))
    return cx


def crags(lv: Level, x0: int, spec):
    """Low crags on the bridge's top: (offset, height, width) each, hopped over."""
    for dx, h, w in spec:
        lv.rect(x0 + dx, TOP - h, x0 + dx + w - 1, TOP - 1)


def build() -> Level:
    lv = Level(31, "mars", background="background-mars.png")
    lv.rect(0, TOP, WEST - 1, BOTTOM)  # the west cliff
    lv.rect(EAST, RIM, EAST + 18, BOTTOM)  # the east cliff, higher
    arch(lv, WEST, EAST - 1, TOP, under)

    # --- The west end of the bridge -----------------------------------------------------
    lv.spawn(4, TOP - 1)
    lv.decor(2, TOP - 1, 3)
    lv.decor(7, TOP - 1, 3)
    lv.decor(10, TOP - 1, 6)
    lv.big_decor(14, TOP - 1, 5)
    lv.coins(6, TOP - 3, 26, 3)
    crags(lv, 0, [(19, 1, 2)])
    lv.wp(26, TOP - 1, 28, TOP - 1, ground=True, label="bridge")
    tooth(lv, 34, TOP, 5, cap=4)

    # --- U1: two swings and a third into an open hanging chimney (the first highlight) --------
    c = underpass(lv, 30, (1, 3, 3), "u1", rests=((1, 44), (-1, 37)), chimney=True, guides=(3,))

    # --- T1 ------------------------------------------------------------------------------
    x = c + 5
    crags(lv, x, [(4, 2, 2), (11, 1, 3), (17, 2, 2)])
    lv.enemy(x + 9, TOP - 1)
    lv.decor(x + 14, TOP - 1, 6)
    lv.coins(x, TOP - 4, x + 20, 2)
    lv.wp(x + 6, TOP - 1, x + 8, TOP - 1, ground=True, label="span 1 a")
    lv.wp(x + 14, TOP - 1, x + 16, TOP - 1, ground=True, label="span 1 b")
    lv.wp(x + 20, TOP - 1, x + 22, TOP - 1, ground=True, label="span 1 c")
    tooth(lv, x + 27, TOP, 6, w=3, cap=4)

    # --- U2: one swing into a basket --------------------------------------------------------
    c = underpass(lv, x + 23, (1, 3), "u2", rests=((-1, 40), (1, 34)))

    # --- T2 ------------------------------------------------------------------------------
    x = c + 5
    crags(lv, x, [(5, 2, 2), (12, 2, 2)])
    lv.enemy(x + 9, TOP - 1)
    lv.big_decor(x + 17, TOP - 1, 5)
    lv.coins(x, TOP - 4, x + 18, 2)
    lv.wp(x + 7, TOP - 1, x + 10, TOP - 1, ground=True, label="span 2 a")
    lv.wp(x + 15, TOP - 1, x + 17, TOP - 1, ground=True, label="span 2 b")
    tooth(lv, x + 24, TOP, 6, cap=4)

    # --- U3: two swings into a basket -------------------------------------------------------
    c = underpass(lv, x + 20, (1, 3, 3), "u3", rests=((1, 43), (-1, 38), (1, 33)))

    # --- The crown of the bridge (banner) ----------------------------------------------
    x = c + 5
    lv.checkpoint(x + 2, TOP - 1)
    lv.decor(x + 6, TOP - 1, 7)
    lv.decor(x + 7, TOP - 1, 7)
    lv.big_decor(x + 10, TOP - 1, 0)
    crags(lv, x, [(13, 2, 3), (20, 1, 2)])
    lv.enemy(x + 18, TOP - 1)
    lv.coins(x + 4, TOP - 4, x + 24, 2)
    lv.wp(x + 16, TOP - 1, x + 19, TOP - 1, ground=True, label="crown")
    lv.wp(x + 23, TOP - 1, x + 25, TOP - 1, ground=True, label="crown east")
    tooth(lv, x + 30, TOP, 7, w=3, cap=4)

    # --- U4: right after the banner, swings into an open chimney (the second highlight) ------
    c = underpass(lv, x + 26, (1, 4, 3), "u4", rests=((1, 44), (-1, 37)), chimney=True, guides=(2,))

    # --- T4 ------------------------------------------------------------------------------
    x = c + 5
    crags(lv, x, [(4, 1, 2), (10, 2, 3), (17, 1, 2)])
    lv.enemy(x + 13, TOP - 1)
    lv.decor(x + 8, TOP - 1, 5)
    lv.coins(x, TOP - 4, x + 20, 2)
    lv.wp(x + 6, TOP - 1, x + 8, TOP - 1, ground=True, label="span 4 a")
    lv.wp(x + 14, TOP - 1, x + 16, TOP - 1, ground=True, label="span 4 b")
    lv.wp(x + 20, TOP - 1, x + 22, TOP - 1, ground=True, label="span 4 c")
    tooth(lv, x + 27, TOP, 6, w=3, cap=4)

    # --- U5: one long swing into a basket ---------------------------------------------------
    c = underpass(lv, x + 23, (1, 4), "u5", rests=((1, 40), (-1, 34)))

    # --- T5: the last span, up to the needle ------------------------------------------------
    x = c + 5
    gaps6 = (1, 3, 3)
    x6 = EAST - 12 - sum(gaps6) - 4 * (len(gaps6) - 1)
    crags(lv, x, [(5, 2, 2), (12, 1, 2)])
    lv.enemy(x + 9, TOP - 1)
    lv.decor(x + 15, TOP - 1, 6)
    lv.coins(x, TOP - 4, x6 - 5, 2)
    lv.wp(x + 7, TOP - 1, x + 10, TOP - 1, ground=True, label="span 5 a")
    lv.wp(x6 - 5, TOP - 1, x6 - 3, TOP - 1, ground=True, label="span 5 b")
    tooth(lv, x6 + 4, TOP, 6, cap=4)

    # --- U6: two swings, then the long climb between the needle and the east cliff ----------
    rests = ((1, 43), (-1, 38), (1, 33), (-1, 28), (1, 23), (-1, 18))
    underpass(lv, x6, gaps6, "u6", rests=rests, rim=RIM)
    lv.big_decor(EAST + 9, RIM - 1, 5)
    lv.decor(EAST + 13, RIM - 1, 6)
    lv.flag(EAST + 11, RIM - 1)
    lv.wp(EAST + 11, RIM - 1, label="flag")
    return lv
