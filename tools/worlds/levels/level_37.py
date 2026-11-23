"""Level 37 - The Whirlpool (reef and wreck, deep water).

Off the outer reef two tides meet, and the sea turns in a whirlpool that
never stops: eddy under eddy down into the reef, and everything it ever
caught circles in it. Wall to wall up a crack from the waterline on to the
reef, over the wreckage piled up on its edge and two rifts, into the outer
eddy, whose top still runs at the surface (a breath every round). Out of
it at the foot of its east side, dashing against the water that flows
back in, into the second eddy, which turns the other way under the reef:
ride it round and up its east side into the capsized hull stuck in the
rock, its air trapped under the keel. Out through the hull's breach over
the bay, mast to mast (a miss is a swim back to the bay's west end), and
down the funnel into three eddies that mesh like gears: where two touch
both run the same way, and only who keeps to the far side there is taken
on into the next; air waits over the second junction. Out of the third
into the bell, a pocket of air in the reef (the checkpoint banner stands
on its ledge). Then the bell's own eddy, its top under the bell's air,
the eddy below it and the great eddy round the eye: air only in the eye
inside its core, reached through a gap on the way up its west side and
left through another into its east side, and out of the eddy at the foot
of that side against its outflow. It spits the swimmer into the
graveyard of ships, a cave of air where the wrecks it swallowed came to
rest: over a capsized boat and the masts, wall to wall between two hulls
standing on end, up a crack in the cave's roof and over the reef's rifts
to the flag.
"""

from tools.worlds.builder import LEFT, Level, holed_chimney, perforate
from tools.worlds.kits.water import (
    ANCHOR,
    ANEMONE,
    CHEST,
    CORAL,
    KELP,
    SEAWEED,
    STARFISH,
    basin,
    dress,
    gears,
    pocket,
    ring,
    shift,
)

BOTTOM = 84
SURF = 22  # the sea's surface over the outer eddy


def build() -> Level:
    lv = Level(37, "reef", background="background-deep.png", clouds=False)
    lv.rect(-46, SURF, 330, BOTTOM)  # the reef
    lv.rect(26, 4, 47, SURF - 1)  # the reef wall over the second eddy

    # --- The reef's edge: wreckage piled up ----------------------------------------------------------
    # --- Up the crack from the waterline on to the reef ------------------------------------------------------
    lv.carve(-40, SURF, -36, SURF + 12)
    holed_chimney(lv, -41, 5, SURF, SURF + 13, rests=[(1, SURF + 5)], label="crack", top=False)
    lv.route = [w for w in lv.route if w.label != "crack base"]
    lv.carve(-44, SURF + 10, -41, SURF + 12)  # a hollow at its foot
    lv.rect(-46, SURF + 13, -36, SURF + 13)
    lv.spawn(-39, SURF + 12)
    lv.decor(-37, SURF + 12, STARFISH)
    lv.coins(-38, SURF + 7, -37)
    lv.decor(-28, SURF - 1, STARFISH)
    lv.rect(-26, SURF - 3, -24, SURF - 1, "wreck")  # a crate stack
    lv.rect(-25, SURF - 5, -24, SURF - 4, "wreck")
    lv.crumble(-25, SURF - 5, -24)  # the top crate has rotted
    lv.wp(-25, SURF - 6, -24, SURF - 6, ground=True, label="crate stack")
    lv.carve(-21, SURF, -16, SURF + 6)  # a rift in the reef, the sea down in it
    lv.water(-21, SURF + 2, -16, SURF + 6)
    lv.rect(-18, SURF - 2, -18, SURF + 6, "wreck")  # a spar stuck in it
    lv.wp(-18, SURF - 3, ground=True, label="spar")
    lv.wp(-15, SURF - 1, -13, SURF - 1, ground=True, label="past the rift")
    lv.enemy(-11, SURF - 1)
    lv.rect(-9, SURF - 2, -6, SURF - 1, "wreck")  # an upturned boat
    lv.rect(-8, SURF - 3, -7, SURF - 3, "wreck")
    lv.wp(-8, SURF - 4, -7, SURF - 4, ground=True, label="upturned boat")
    lv.carve(-4, SURF, 0, SURF + 5)  # a second rift
    lv.water(-4, SURF + 2, 0, SURF + 5)
    lv.wp(1, SURF - 1, 2, SURF - 1, ground=True, label="past the second rift")
    lv.coins(-27, SURF - 8, -15, 3)
    lv.decor(2, SURF - 1, STARFISH)
    lv.rect(4, SURF - 2, 5, SURF - 1, "wreck")  # crates
    lv.spikes(6, SURF - 1, 7)  # broken iron sticking out of the wreckage
    lv.rect(9, SURF - 4, 9, SURF - 1, "wreck")  # a broken mast
    lv.coins(2, SURF - 4, 8, 2)
    lv.wp(9, SURF - 5, ground=True, label="broken mast")
    lv.wp(12, SURF - 1, 13, SURF - 1, ground=True, label="reef edge")

    # --- The outer eddy and the second eddy -----------------------------------------------------------
    a_box = (14, SURF, 23, SURF + 15)  # its top at the surface
    b_box = (28, SURF + 4, 39, SURF + 19)  # under the reef, the other way round
    ring(lv, a_box, 3, clockwise=True, round_r=2.5)
    ring(lv, b_box, 3, clockwise=False, round_r=2.5)
    lv.carve(12, SURF - 6, 23, SURF - 1)  # the bay over the outer eddy
    lv.rect(24, SURF - 2, 25, SURF - 1)
    lv.coins(16, SURF + 1, 20, 2)
    lv.wp(18, SURF, 20, SURF + 2, label="outer eddy")
    ex_a = SURF + 11  # out at the foot of its east side
    basin(lv, 24, 27, ex_a, ex_a + 1, LEFT)  # it flows back in: dash out against it
    lv.wp(24, ex_a, 27, ex_a + 1, label="out of the outer eddy")
    lv.wp(32, SURF + 17, 35, SURF + 19, label="second eddy bottom")
    lv.coins(31, SURF + 18, 36, 1)

    # --- The capsized hull ----------------------------------------------------------------------------------
    hull_y = SURF - 4  # the row its water and decks are on (the keel above)
    h0, h1 = 30, 44
    lv.rect(h0, hull_y - 7, h1, hull_y + 1, "wreck")
    pocket(lv, h0 + 1, hull_y - 5, h1 - 1, hull_y - 1)
    basin(lv, 36, 39, hull_y, hull_y)
    basin(lv, 37, 38, hull_y + 1, SURF + 3)  # the shaft up from the second eddy
    lv.wp(40, hull_y - 1, 42, hull_y - 1, ground=True, label="hull deck")
    lv.big_decor(32, hull_y - 1, CHEST)
    lv.coins(40, hull_y - 3, 43, 1)
    # The breach, out over the bay
    lv.carve(h1, hull_y - 2, h1 + 3, hull_y - 1)
    lv.rect(h1 + 1, hull_y, h1 + 3, hull_y + 2)

    # --- The bay: mast to mast over its water ------------------------------------------------------------
    b0, b1 = h1 + 4, h1 + 68  # the bay's water
    bs = SURF + 1  # its surface
    lv.carve(b0, 0, b1, bs - 1)
    basin(lv, b0, b1, bs, bs + 5)
    lv.rect(b0 + 1, bs - 1, b0 + 1, bs + 5)  # the steps back out at its west end
    lv.rect(b0, bs - 3, b0, bs + 5)
    lv.rect(h1 + 1, hull_y, b0 - 1, BOTTOM)
    lv.wp(h1 + 1, hull_y - 1, h1 + 3, hull_y - 1, ground=True, label="the breach")
    masts = [(5, -3), (5, -4), (6, -3), (4, -5), (5, -4), (6, -5), (4, -6), (5, -5), (5, -4), (6, -6), (5, -4), (5, -5)]
    mx = h1 + 3
    for i, (dx, top) in enumerate(masts):
        mx += dx
        lv.rect(mx, hull_y + top + 3, mx, bs + 5, "wreck")
        if i in (4, 9):  # rotten mast tops
            lv.crumble(mx, hull_y + top + 3)
        lv.wp(mx, hull_y + top + 2, ground=True, label=f"mast {i}")
        lv.coin(mx, hull_y + top + 1)
    for kx in range(b0 + 3, b1 - 2, 6):
        lv.big_decor(kx, bs + 5, KELP)
    dress(lv, range(b0 + 4, b1, 4), bs, (SEAWEED, CORAL, ANEMONE), seed=371)
    isl = b1 + 1  # a rock island at the funnel
    lv.rect(isl, hull_y + 1, isl + 5, BOTTOM)
    lv.wp(isl, hull_y, isl + 2, hull_y, ground=True, label="funnel rock")
    lv.decor(isl + 1, hull_y, STARFISH)

    # --- The triplet eddies: down the funnel, keep east where they mesh ------------------------------------
    d0 = isl + 7
    boxes = [(d0 + 10 * k, SURF + 5, d0 + 10 * k + 9, SURF + 24) for k in range(3)]
    gears(lv, boxes, 3, round_r=2.5)
    lv.carve(isl + 6, 0, d0 + 4, hull_y)
    basin(lv, isl + 6, d0 + 1, hull_y + 1, SURF + 4)  # the funnel down into the first
    lv.rect(d0 + 2, 4, 330, SURF - 1)  # the reef wall from here on, too high to climb
    # air over the top of the second junction, where both run up
    j = d0 + 17  # its west column (x j..j+5)
    for x in range(j, j + 6):
        for y in (SURF + 5, SURF + 6):
            k = 1 if x < d0 + 20 else 2
            from tools.worlds.kits.water import ring_flow

            lv.solid.pop((x, y), None)
            lv.water_tiles[(x, y)] = ring_flow(x, y, boxes[k], 3, k % 2 == 0)
    pocket(lv, j + 1, SURF + 2, j + 4, SURF + 4)
    lv.wp(d0 + 3, SURF + 5, d0 + 6, SURF + 7, label="first eddy top")
    lv.wp(d0 + 13, SURF + 22, d0 + 16, SURF + 24, label="second eddy bottom")
    lv.wp(j + 1, SURF + 3, j + 4, SURF + 4, label="the air over the second junction")
    lv.wp(d0 + 23, SURF + 5, d0 + 26, SURF + 7, label="third eddy top")
    lv.coins(d0 + 10, SURF + 12, d0 + 10, 1)
    lv.coins(d0 + 13, SURF + 23, d0 + 16, 1)
    lv.coins(j + 2, SURF + 3, j + 3, 1)
    # Out of the third eddy's east side into the bell
    bx = d0 + 32
    by = SURF + 16  # the bell's water row; its ledge east of it
    basin(lv, d0 + 30, bx + 3, by, by + 1)
    lv.water(d0 + 30, by, d0 + 31, by + 1, LEFT)  # it flows back into the eddy
    pocket(lv, bx, by - 5, bx + 9, by - 1)
    lv.rect(bx + 4, by, bx + 9, by + 1)
    lv.wp(bx + 5, by - 1, bx + 7, by - 1, ground=True, label="the bell")
    lv.checkpoint(bx + 6, by - 1)  # halfway
    lv.decor(bx + 8, by - 1, ANEMONE)

    # --- Down the bell's eddy and the one under it into the great eddy round the eye --------------------------
    s1 = (bx + 11, by, bx + 20, by + 13)  # its top runs under the bell's air
    s2 = (bx + 25, by + 10, bx + 34, by + 24)
    cx0 = bx + 40  # the great eddy's west side
    c_box = (cx0, SURF + 18, cx0 + 17, SURF + 45)
    for box in (s1, s2):
        ring(lv, box, 3, clockwise=True, round_r=2.5)
    ring(lv, c_box, 3, clockwise=True, round_r=3)
    gy = SURF + 40  # the graveyard pool's surface
    pocket(lv, bx + 10, by - 3, bx + 20, by - 1)
    lv.wp(bx + 13, by, bx + 16, by + 2, label="the bell's eddy")
    basin(lv, bx + 21, bx + 24, by + 10, by + 11, LEFT)  # out against its outflow
    lv.wp(bx + 22, by + 10, bx + 24, by + 11, label="out of the bell's eddy")
    lv.wp(bx + 28, by + 10, bx + 31, by + 12, label="lower eddy top")
    basin(lv, bx + 35, cx0 - 1, by + 20, by + 21)
    lv.wp(bx + 35, by + 20, bx + 37, by + 21, label="out of the lower eddy")
    lv.coins(bx + 14, by + 1, bx + 18, 2)
    lv.coins(bx + 27, by + 11, bx + 31, 2)
    e0, e1 = cx0 + 6, cx0 + 11
    ey = SURF + 30  # the eye's water surface
    basin(lv, e0, e1, ey, ey + 4)
    pocket(lv, e0, ey - 5, e1, ey - 1)
    basin(lv, cx0 + 3, e0 - 1, ey + 3, ey + 4)  # the gap from the west side
    basin(lv, e1 + 1, cx0 + 14, ey + 3, ey + 4)  # and on into the east side
    lv.wp(cx0 + 3, ey + 3, cx0 + 5, ey + 4, label="the gap into the eye")
    lv.wp(e0, ey - 2, e1, ey - 1, label="the eye")
    lv.coins(e0 + 1, ey - 2, e1 - 1, 2)
    lv.decor(e0 + 1, ey + 4, ANEMONE)
    lv.decor(e1 - 1, ey + 4, CORAL)

    # --- The graveyard of ships ----------------------------------------------------------------------------
    gx = cx0 + 21  # the cave's west wall
    basin(lv, cx0 + 18, gx - 1, gy, gy + 1, LEFT)  # out of the great eddy, against its outflow
    lv.wp(cx0 + 18, gy, gx - 1, gy + 1, label="out of the great eddy")
    roof = SURF + 10  # the cave's first row of air
    g1 = gx + 66  # its east wall
    lv.carve(gx, roof, g1, gy + 3)
    lv.water(gx, gy, g1, gy + 3)
    # A hull on its side to climb out on to, a capsized boat, masts sticking up out of the water
    lv.rect(gx + 5, gy - 2, gx + 12, gy + 3, "wreck")
    lv.wp(gx + 5, gy - 3, gx + 8, gy - 3, ground=True, label="first wreck")
    lv.big_decor(gx + 11, gy - 3, ANCHOR)
    lv.spikes(gx + 9, gy - 3, gx + 10)  # its broken ribs
    lv.rect(gx + 17, gy - 3, gx + 21, gy - 1, "wreck")
    lv.rect(gx + 18, gy, gx + 20, gy + 3, "wreck")
    lv.wp(gx + 17, gy - 4, gx + 19, gy - 4, ground=True, label="capsized boat")
    lv.enemy(gx + 21, gy - 4)
    for i, (mx, mt) in enumerate(
        ((gx + 26, gy - 5), (gx + 31, gy - 7), (gx + 36, gy - 5), (gx + 41, gy - 8), (gx + 46, gy - 6))
    ):
        lv.rect(mx, mt, mx, gy + 3, "wreck")
        lv.wp(mx, mt - 1, ground=True, label=f"graveyard mast {i}")
        lv.coin(mx, mt - 2)
    lv.rect(gx + 50, gy - 7, gx + 52, gy - 7, "wreck")  # a yard hanging off the last mast
    lv.rect(gx + 51, gy - 6, gx + 51, gy + 3, "wreck")
    lv.wp(gx + 50, gy - 8, gx + 52, gy - 8, ground=True, label="the yard")
    # Two hulls standing on end: wall to wall up between them, on up a crack in the cave's roof
    w0 = gx + 57  # the first hull's east side; the second's west side is w0 + 5
    lv.rect(w0 - 2, gy - 4, w0, gy + 3, "wreck")  # the first hull, broken open
    lv.rect(w0 - 2, roof + 6, w0, gy - 9, "wreck")
    lv.rect(w0 + 5, roof + 3, w0 + 8, gy + 3, "wreck")  # the second hull
    lv.wp(w0 - 2, gy - 5, w0, gy - 5, ground=True, label="hull foot")
    lv.crumble(w0 + 4, gy - 13)  # a rotten plank to rest on
    lv.wp(w0 + 4, gy - 14, ground=True, label="hull rest")
    lv.wp(w0 - 2, roof + 5, w0, roof + 5, ground=True, label="first hull top")
    lv.coins(w0 + 2, gy - 10, w0 + 3)
    lv.coins(w0 + 2, gy - 19, w0 + 3)
    top = roof - 12  # the reef's top over the graveyard
    lv.carve(gx - 4, 0, 330, top - 1)
    lv.carve(w0 + 1, top, w0 + 4, roof - 1)  # the crack
    perforate(lv, w0, top + 1, roof - 2, solid=2, gap=1)
    perforate(lv, w0 + 5, top + 1, roof - 2, solid=2, gap=1)
    lv.rect(w0 + 4, roof - 7, w0 + 4, roof - 7)
    lv.wp(w0 + 4, roof - 8, ground=True, label="crack rest")
    lv.wp(w0 + 5, top - 1, w0 + 7, top - 1, ground=True, label="the reef")
    lv.coins(w0 + 2, roof - 4, w0 + 3)
    # Over the reef to the flag: two rifts, a crab, a stranded mast
    for i, (r0, r1) in enumerate(((w0 + 12, w0 + 17), (w0 + 27, w0 + 33))):
        lv.carve(r0, top, r1, top + 5)
        lv.water(r0, top + 2, r1, top + 5)
        lv.wp(r1 + 1, top - 1, r1 + 3, top - 1, ground=True, label=f"over rift {i}")
        lv.coins(r0 + 1, top - 3, r1 - 1, 2)
    lv.rect(w0 + 30, top - 1, w0 + 30, top + 5, "wreck")
    lv.enemy(w0 + 22, top - 1)
    lv.decor(w0 + 10, top - 1, STARFISH)
    lv.decor(w0 + 24, top - 1, CORAL)
    lv.flag(w0 + 40, top - 1)
    lv.wp(w0 + 40, top - 1, label="flag")
    dress(lv, range(gx + 2, g1, 3), gy, (SEAWEED, ANEMONE, CORAL, STARFISH), seed=37)
    shift(lv, 46)
    return lv
