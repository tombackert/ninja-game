"""Level 40 - The Leviathan's Bones (reef and bone, deep water). Finale of the water world.

Sailors tell of a sea monster longer than a fleet. It died long ago, and
its bones lie in the trench under the reef, the spine against the reef's
underside, the ribs reaching down to the sea floor like the bars of a cage.
The tide runs through the cage, up between some ribs, down between others,
and the only air is what is caught under the spine between two ribs, and in
the skull. Off the cliff and down into the trench, in under the reef past
the tail into the cup of the pelvis, then through the ribcage, rib after
rib, each broken through high or low: breathe under the spine, ride the
tide down, through the break, up the next bay. At the heart a great bubble
lies under the breastbone (the first banner). On through the second half of
the cage, where a rib fell across the bays, into the skull through the hole
at its back and up into its air (the second banner), down the throat into
the mouth, out between the teeth, and up the geyser in front of the jaws to
the sea stack with the flag.
"""

import math

from tools.worlds.builder import DOWN, LEFT, STILL, UP, Level
from tools.worlds.kits.water import ANEMONE, CORAL, KELP, SEAWEED, STARFISH, dress, pocket

BOTTOM = 80
SURF = 24  # the sea's surface where it is open
CEIL = 39  # the reef's underside
FLOOR = 70  # the sea floor: its first row of rock
BONE = "sand"
SPINE = 40  # the spine: rows SPINE..SPINE+2 under the reef


def rib(lv: Level, x: int, gap: tuple, w: int = 1):
    """A rib from under the spine to the sea floor, straight at the top and
    bowed a little to the east below, broken through at rows gap[0]..gap[1]."""
    for y in range(SPINE + 3, FLOOR):
        if gap[0] <= y <= gap[1]:
            continue
        dx = round(1.5 * math.sin(math.pi * max(0, y - SPINE - 11) / (FLOOR - SPINE - 11)))
        lv.rect(x + dx, y, x + dx + w - 1, y, BONE)


def build() -> Level:
    lv = Level(40, "reef", background="background-deep.png", clouds=False)
    lv.rect(-34, 20, 236, BOTTOM)
    lv.carve(-34, 0, 236, 19)

    # --- The cliff and the open water over the trench ------------------------------------------------------------
    lv.carve(-34, 20, 10, 23)
    lv.spawn(-30, 23)
    lv.decor(-26, 23, STARFISH)
    lv.coins(-24, 21, 6, 3)
    lv.wp(4, 23, 8, 23, ground=True, label="the cliff's edge")
    lv.carve(11, 20, 30, FLOOR - 1)
    lv.water(11, SURF, 30, FLOOR - 1)
    lv.water(18, SURF + 4, 26, FLOOR - 4, DOWN)  # a downwelling into the trench
    lv.wp(16, SURF, 24, SURF + 3, label="the dive")
    x0, pitch = 46, 8  # the first rib, the ribs' spacing
    sx = x0 + pitch * 12 + 2  # the skull's back
    s1 = sx + 30  # its front
    m0, m1 = s1 - 5, s1 + 16  # the mouth
    lv.carve(31, CEIL + 1, m1, FLOOR - 1)  # the trench under the reef
    lv.water(31, CEIL + 1, m1, FLOOR - 1)

    # --- The tail and the pelvis ------------------------------------------------------------------------------------
    for x, y in ((21, 68), (24, 67), (27, 66), (30, 65)):  # the tail's last vertebrae
        lv.rect(x, y, x + 1, y + 1, BONE)
    lv.rect(33, 52, 42, 53, BONE)  # the pelvis, a cup upside down
    lv.rect(33, 54, 33, 56, BONE)
    lv.rect(42, 54, 42, 56, BONE)
    pocket(lv, 34, 54, 41, 55)
    lv.wp(34, 54, 41, 55, label="the pelvis")
    lv.coins(36, 55, 40, 2)

    # --- The ribcage: the spine under the reef, ribs broken high or low ---------------------------------------------
    lv.rect(x0 - 4, SPINE, sx, SPINE + 2, BONE)  # the spine
    hi, lo, mid = (SPINE + 6, SPINE + 9), (FLOOR - 6, FLOOR - 3), (SPINE + 10, SPINE + 13)
    # (gap of the rib, flow of the bay east of it, air under the spine there)
    cage = [
        (lo, UP, True),
        (hi, DOWN, False),
        (lo, UP, True),
        (hi, DOWN, False),
        (lo, UP, True),
        (mid, STILL, False),  # the heart
        (mid, DOWN, False),
        (lo, UP, True),
        (hi, DOWN, False),
        (lo, UP, True),
        (hi, DOWN, False),
        (lo, STILL, True),
    ]
    heart = 5
    for k, (gap, flow, air) in enumerate(cage):
        x = x0 + pitch * k
        w = 2 if k in (heart, heart + 1) else 1
        rib(lv, x, gap, w)
        lv.wp(x + 1, gap[0], x + 2, gap[1], label=f"rib {k}")
        b0, b1 = x + w, x + pitch - 1
        lv.water(b0, SPINE + 3, b1, FLOOR - 1, flow)
        if flow == UP:  # still water under the spine: the tide turns there
            lv.water(b0, SPINE + 3, b1, SPINE + 10, STILL)
        if air:
            pocket(lv, b0, SPINE + 3, b1, SPINE + 4)
            lv.wp(b0 + 1, SPINE + 3, b1 - 1, SPINE + 4, label=f"air in bay {k}")
            lv.coin(b0 + 2, SPINE + 7)
        lv.coin(b0 + 3, (gap[0] + gap[1]) // 2)
        if k == heart:  # a great bubble under the breastbone
            pocket(lv, x + 2, SPINE + 3, x + pitch - 1, SPINE + 9)
            lv.rect(x + 3, SPINE + 10, x + 6, SPINE + 10, BONE)  # the breastbone
            lv.wp(x + 3, SPINE + 9, x + 6, SPINE + 9, ground=True, label="the heart")
            lv.checkpoint(x + 5, SPINE + 9)
    # hydrothermal vents in the trench floor of two bays where the tide runs down
    for k in (3, 8):
        lv.flamejet(x0 + pitch * k + 4, FLOOR, "up", on=40, phase=60 * (k % 2))
    # a rib fallen across two bays (a gap left at its west end), the undertow along the floor
    fx = x0 + pitch * 7
    lv.rect(fx + 3, SPINE + 14, fx + pitch + 5, SPINE + 14, BONE)
    lv.water(fx, FLOOR - 2, x0 + pitch * 12 - 1, FLOOR - 1, LEFT)

    # --- The skull: through the last rib into the hole at its back, up into its air ---------------------------------
    back = (SPINE + 14, SPINE + 17)
    rib(lv, x0 + pitch * 12, back)
    lv.rect(sx, CEIL + 1, s1, FLOOR - 1, BONE)
    lv.carve(sx + 3, SPINE + 3, s1 - 6, SPINE + 18)  # the brain case
    lv.water(sx + 3, SPINE + 3, s1 - 6, SPINE + 18)
    pocket(lv, sx + 3, SPINE + 3, s1 - 6, SPINE + 10)
    lv.rect(sx + 9, SPINE + 11, sx + 17, SPINE + 11, BONE)  # a shelf of bone inside
    lv.carve(sx, back[0], sx + 2, back[1])  # the hole at its back
    lv.water(sx - 1, back[0], sx + 2, back[1])
    lv.wp(sx, back[0], sx + 2, back[1], label="into the skull")
    lv.wp(sx + 9, SPINE + 10, sx + 12, SPINE + 10, ground=True, label="inside the skull")
    lv.checkpoint(sx + 14, SPINE + 10)
    lv.enemy(sx + 16, SPINE + 10)

    # --- The throat, the mouth, the teeth ---------------------------------------------------------------------------
    mt, mb = SPINE + 20, FLOOR - 3  # the mouth's rows between the jaws
    lv.carve(s1 - 8, SPINE + 19, s1 - 6, mt - 1)  # the throat
    lv.water(s1 - 8, SPINE + 19, s1 - 6, mt - 1)
    lv.rect(s1 + 1, CEIL + 1, m1, mt - 1, BONE)  # the upper jaw
    lv.rect(s1 + 1, mb + 1, m1, FLOOR - 1, BONE)  # the lower jaw
    lv.carve(s1 - 8, mt, m1 - 1, mb)
    lv.water(s1 - 8, mt, m1 - 1, mb)
    lv.wp(s1 - 8, mt - 3, s1 - 6, mt, label="the throat")
    lv.wp(s1 - 4, mt + 3, s1, mb, label="the mouth", guide=True)
    pocket(lv, m0 + 9, mt - 3, m0 + 13, mt - 2)  # a bubble caught in the palate
    lv.carve(m0 + 9, mt - 1, m0 + 13, mt - 1)
    lv.water(m0 + 9, mt - 1, m0 + 13, mt - 1)
    lv.wp(m0 + 9, mt - 3, m0 + 13, mt - 2, label="the palate")
    for i, x in enumerate(range(m0 + 6, m1 - 1, 3)):
        if i % 2 == 0:
            lv.rect(x, mt, x, mt + 3, BONE)  # an upper tooth
        else:
            lv.rect(x, mb - 3, x, mb, BONE)  # a lower tooth
    lv.carve(m1, mt, m1, mb)  # the jaws stand open
    lv.water(m1, mt, m1, mb)
    lv.wp(m1, mt, m1, mb, label="between the front teeth")

    # --- The geyser and the sea stack -------------------------------------------------------------------------------
    g0, g1 = m1 + 1, m1 + 6
    lv.carve(g0, 20, 232, FLOOR - 1)
    lv.water(g0, SURF, 232, FLOOR - 1)
    lv.water(g0, SURF + 3, g1, FLOOR - 1, UP)
    lv.wp(g0, SURF, g1, SURF + 2, label="the geyser")
    st = g1 + 4  # the sea stack
    lv.rect(st, SURF - 4, st + 9, FLOOR - 1)
    lv.rect(st - 2, SURF - 2, st - 1, SURF + 1)
    lv.wp(st - 2, SURF - 3, st - 1, SURF - 3, ground=True, label="a foothold")
    lv.wp(st, SURF - 5, st + 3, SURF - 5, ground=True, label="the sea stack")
    lv.coins(st + 1, SURF - 7, st + 8, 2)
    lv.flag(st + 7, SURF - 5)
    lv.wp(st + 7, SURF - 5, label="flag")

    dress(lv, range(32, m0, 3), CEIL + 2, (SEAWEED, ANEMONE, CORAL, STARFISH), seed=40)
    for x in (13, 29, 222, 228):
        if lv.is_solid(x, FLOOR) and not lv.is_solid(x, FLOOR - 1) and (x, FLOOR - 1) not in lv.objects:
            lv.big_decor(x, FLOOR - 1, KELP)
    return lv
