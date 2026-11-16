"""Level 36 - Tide Pools (reef and sand, lagoon sky).

Low tide on the headland: the sea has drawn back and left its water in
pools all over the rock, and the crabs have come out on the rims. Off the
beach over the gully, ten wide, where the surf still runs in (a jump and
a dash; a miss is a climb back out of the surf), over the flats and their
pools, boulder to boulder through the rock garden (a miss is a swim back
to its start), along the comb, a row of knife-edge ridges standing out of
a deep channel (a miss is a swim back to the comb's start), and wall to
wall up between a sea needle and the terrace's face, with one rest ledge.
Up the terrace steps, pools whose rims the waves have undercut so that
only a leap from the right spot clears the lip, and down the last, deep
pool into the sea cave under the cliff, where the ebb runs back out
against the swimmer. It comes up in the grotto at the foot of the cleft:
the checkpoint banner stands on its ledge. Up the cleft, a crack in the
cliff climbed wall to wall with two rest ledges, over the high pools,
down a hole into the blowhole's cave and up the blowhole on to the upper
terrace, across the sea stacks standing in the upper lagoon (a miss falls
in and the way out is back at its start), and up the crown's pools to the
cairn with the flag.
"""

import math

from tools.worlds.builder import LEFT, UP, Level, holed_chimney
from tools.worlds.kits.water import (
    ANCHOR,
    ANEMONE,
    CORAL,
    FAN_CORAL,
    KELP,
    SEAWEED,
    STARFISH,
    basin,
    dress,
    pocket,
    shift,
)

BOTTOM = 72
SEA = 58  # the sea's surface row


def undercut_pool(lv: Level, x: int, surface: int, w: int, rise: int, lip: int, rim_w: int, depth=4, label="pool"):
    """A pool `w` wide cut into the rock east of column x, its far rim `rise`
    rows over the surface and undercut: the rim's top row hangs `lip` tiles
    out over the water, so a leap only clears it from out in the pool. The
    rock is stamped down to BOTTOM. Returns (x after the rim, rim top row)."""
    rim = surface - rise
    lv.rect(x, surface + depth, x + w - 1, BOTTOM)
    lv.rect(x + w, rim, x + w + rim_w - 1, BOTTOM)
    lv.carve(x, surface - 2, x + w - 1, surface + depth - 1)
    lv.water(x, surface, x + w - 1, surface + depth - 1)
    lv.rect(x + w - lip, rim, x + w - 1, rim)  # the lip
    lv.wp(x, surface, x + w - 1 - lip, surface + depth - 1, label=f"{label} water")
    lv.wp(x + w - lip, rim - 1, x + w + rim_w - 1, rim - 1, ground=True, label=f"{label} rim")
    lv.decor(x + 1, surface + depth - 1, SEAWEED)
    lv.decor(x + w - lip - 1, surface + depth - 1, ANEMONE)
    return x + w + rim_w, rim


def knife_ridges(lv: Level, x0: int, x1: int, surface: int, ridges, label="ridge"):
    """A deep channel x0..x1 (water from `surface`, 6 deep) with knife-edge
    ridges (x, top) standing out of it, too high over the water to climb from
    it: a miss is a swim back to the step at the channel's west end."""
    lv.rect(x0, surface + 6, x1, BOTTOM)
    lv.carve(x0, surface - 6, x1, surface + 5)
    lv.water(x0, surface, x1, surface + 5)
    lv.rect(x0, surface - 1, x0 + 1, surface + 5)  # the step back out
    for x, top in ridges:
        lv.rect(x, top, x, surface + 5)
        lv.coin(x, top - 2)
        lv.wp(x, top - 1, ground=True, label=f"{label} {x}")
    dress(lv, range(x0 + 3, x1, 3), surface, (SEAWEED, CORAL, ANEMONE, STARFISH), seed=x0)


def build() -> Level:
    lv = Level(36, "reef", background="background-lagoon.png")

    # --- The beach --------------------------------------------------------------------------------
    lv.rect(-7, 46, -4, BOTTOM)  # a sea stack off the beach
    lv.rect(-5, 44, -4, 45)
    lv.water(-3, SEA, 10, SEA + 7)  # the sea, out at low tide
    lv.rect(-3, SEA + 8, 10, BOTTOM)
    for x in range(11, 26):
        t = SEA - 1 - (x - 11) // 4
        lv.rect(x, t + 4, x, BOTTOM)
        lv.rect(x, t, x, t + 3, "sand")
    beach = SEA - 4  # its top at the gully
    lv.spawn(14, SEA - 2)
    lv.big_decor(19, SEA - 4, ANCHOR)  # washed up
    lv.decor(17, SEA - 3, STARFISH)
    lv.decor(23, SEA - 5, STARFISH)
    lv.coins(15, SEA - 6, 23, 2)
    lv.wp(20, beach - 1, 23, beach - 1, ground=True, label="beach")

    # --- The gully: ten wide, the surf still runs in ------------------------------------------------------
    g0, g1 = 26, 35
    flats = beach
    lv.rect(g0, beach + 1, g1 + 40, BOTTOM)
    lv.rect(25, beach - 1, 25, beach - 1)  # raised rims
    lv.rect(g1 + 1, flats - 1, g1 + 1, flats - 1)
    basin(lv, g0 + 1, g1, SEA - 1, SEA + 3, air=4)  # the surf
    lv.carve(g0, beach + 1, g0, SEA - 2)
    lv.rect(g0, SEA - 3, g0, SEA + 3)  # a step back out of it
    lv.coins(g0 + 1, beach - 4, g1 - 1, 2)
    lv.wp(g1 + 2, flats - 1, g1 + 4, flats - 1, ground=True, label="over the gully")
    lv.decor(g0 + 3, SEA + 3, SEAWEED)
    lv.decor(g1 - 1, SEA + 3, CORAL)

    # --- The flats: three pools, the first crabs ----------------------------------------------------------
    f0 = g1 + 1
    lv.rect(f0, flats, f0 + 35, BOTTOM)
    for i, (p0, p1, d) in enumerate(((6, 11, 3), (16, 22, 4), (27, 31, 5))):
        basin(lv, f0 + p0, f0 + p1, flats + 1, flats + d, air=1)
        if i < 2:  # into the last pool the planner finds its own way
            lv.wp(f0 + p0, flats + 1, f0 + p1, flats + d, label=f"flats pool {i}")
        lv.wp(f0 + p1 + 1, flats - 1, f0 + p1 + 3, flats - 1, ground=True, label=f"flats {i}")
        dress(lv, (f0 + p0 + 1, f0 + p1 - 1), flats, (SEAWEED, ANEMONE, CORAL), seed=36 + i)
        lv.coins(f0 + p0 + 1, flats - 2, f0 + p1 - 1, 2)
    for x in (f0 + 4, f0 + 14, f0 + 25):
        lv.enemy(x, flats - 1)
    lv.decor(f0 + 2, flats - 1, STARFISH)

    # --- The rock garden: boulders standing in a shallow pool ---------------------------------------------
    r0 = f0 + 36
    c0 = r0 + 26
    lv.rect(r0, flats + 4, c0 - 1, BOTTOM)
    lv.carve(r0, flats - 8, c0 - 4, flats + 3)
    lv.water(r0, flats + 1, c0 - 4, flats + 3)
    lv.rect(c0 - 3, flats - 1, c0 - 1, flats + 3)  # the bank at its east end
    for i, (dx, w, h) in enumerate(((3, 2, 2), (7, 3, 3), (13, 2, 2), (17, 2, 4), (22, 1, 3))):
        bx, btop = r0 + dx, flats - h
        lv.rect(bx, btop, bx + w - 1, flats + 3)
        lv.wp(bx, btop - 1, bx + w - 1, btop - 1, ground=True, label=f"boulder {i}")
        lv.coin(bx + w // 2, btop - 2)
        if i in (1, 3):
            lv.enemy(bx + w - 1, btop - 1)
    lv.wp(c0 - 3, flats - 2, c0 - 1, flats - 2, ground=True, label="garden bank")
    dress(lv, range(r0 + 1, c0 - 4, 2), flats, (SEAWEED, ANEMONE, STARFISH, CORAL), seed=365)

    # --- The comb: knife-edge ridges out of a deep channel ------------------------------------------------
    surf = flats + 2
    hops = [(6, 1), (4, 2), (4, 1), (6, 2), (3, 3), (4, 4), (6, 4), (4, 5), (4, 4), (7, 5), (3, 6), (4, 5), (6, 6)]
    ridges, x = [], c0 - 2
    for dx, up in hops:
        x += dx
        ridges.append((x, flats - up))
    c1 = x + 3
    knife_ridges(lv, c0, c1, surf, ridges)
    for kx in range(c0 + 7, c1 - 2, 12):
        lv.big_decor(kx, surf + 5, KELP)
    bank = flats - 7
    lv.rect(c1 + 1, bank, c1 + 12, BOTTOM)
    lv.wp(c1 + 1, bank - 1, c1 + 3, bank - 1, ground=True, label="comb bank")

    # --- The needle: wall to wall up between a sea needle and the terrace's face ---------------------------
    face = c1 + 12  # the face's column, five off the needle
    top_t = bank - 16
    holed_chimney(lv, c1 + 6, 5, bank - 14, bank, rests=[(1, bank - 8)], label="needle", top=False)
    lv.rect(face + 1, top_t, face + 4, BOTTOM)
    lv.wp(face + 1, top_t - 1, face + 3, top_t - 1, ground=True, label="terrace top")
    lv.coins(c1 + 8, bank - 5, c1 + 10)
    face += 1
    lv.decor(c1 + 4, bank - 1, STARFISH)
    lv.coins(c1 + 2, bank - 3, c1 + 5, 1)

    # --- The terrace steps: undercut pools ---------------------------------------------------------------
    x, rim = face + 4, top_t
    steps = [(6, 2, 2, 3), (6, 2, 2, 3), (5, 2, 3, 3), (7, 2, 2, 3), (6, 2, 3, 3), (5, 2, 2, 3), (7, 2, 3, 4)]
    for i, (w, rise, lip, rim_w) in enumerate(steps):
        x, rim = undercut_pool(lv, x, rim + 1, w, rise, lip, rim_w, label=f"step {i}")
        lv.coins(x - rim_w - lip - 2, rim - 2, x - rim_w - 1)
        if i in (1, 4):
            lv.enemy(x - 2, rim - 1)
    lv.big_decor(x - 1, rim - 1, FAN_CORAL)

    # --- The deep pool and the sea cave: the ebb runs out against the swimmer ------------------------------
    dp = x  # the deep pool, three wide, at the foot of the cliff
    top = rim  # the last step's rim
    cl_top = top - 20  # the cliff's top row
    lv.rect(dp, top + 13, dp + 2, BOTTOM)
    lv.rect(dp + 3, cl_top, dp + 64, BOTTOM)  # the cliff
    lv.rect(dp + 1, cl_top, dp + 2, cl_top + 2)  # its brow, hanging over the deep pool
    for k, x in enumerate(range(dp + 1, dp + 27)):  # its crown, weathered
        h = round(1.2 + 1.2 * math.sin(k / 2.3) + 0.6 * math.sin(k / 0.9))
        if h > 0:
            lv.rect(x, cl_top - h, x, cl_top - 1)
    lv.water(dp, top + 1, dp + 2, top + 12)
    cave_y = top + 9  # the cave under the cliff: rows cave_y..cave_y+3
    cv1 = dp + 24
    basin(lv, dp + 3, cv1, cave_y, cave_y + 3)
    lv.water(dp + 8, cave_y, dp + 18, cave_y + 3, LEFT)  # the ebb
    lv.wp(dp + 10, cave_y, dp + 12, cave_y + 3, label="the ebb")
    lv.wp(dp + 20, cave_y, dp + 22, cave_y + 3, label="past the ebb")
    dress(lv, range(dp + 4, cv1, 3), cave_y, (ANEMONE, CORAL, STARFISH), seed=363)
    lv.coins(dp + 9, cave_y + 2, dp + 17, 2)
    # Up into the grotto inside the cliff, at the foot of the cleft
    gw = top + 4  # the grotto pool's surface
    g0, n0 = cv1 - 2, cv1 + 7  # the grotto's west end; the cleft's west wall
    basin(lv, cv1 - 2, cv1, gw + 2, cave_y - 1)  # the rise from the cave
    basin(lv, g0, n0 - 1, gw, gw + 1)
    pocket(lv, g0, gw - 4, n0 - 1, gw - 1)
    ledge = gw - 1
    lv.wp(n0 + 1, ledge - 1, n0 + 3, ledge - 1, ground=True, label="grotto ledge")
    lv.decor(g0 + 1, gw + 1, ANEMONE)

    # --- The cleft: a crack up the cliff, wall to wall -----------------------------------------------------
    lv.carve(n0, cl_top, n0 + 5, ledge - 1)
    holed_chimney(lv, n0, 4, cl_top + 2, ledge, rests=[(1, ledge - 9), (-1, ledge - 17)], label="cleft")
    lv.checkpoint(n0 + 2, ledge - 1)  # halfway
    lv.decor(n0 + 4, ledge - 1, STARFISH)
    lv.wp(n0 + 6, cl_top - 1, n0 + 8, cl_top - 1, ground=True, label="cliff top")
    lv.coins(n0 + 7, cl_top - 3, n0 + 9)

    # --- The high pools, then down the blowhole's cave and up the blowhole ----------------------------------
    x, rim = n0 + 10, cl_top
    for i, (w, lip, rim_w) in enumerate(((6, 2, 3), (6, 3, 3), (5, 2, 3), (7, 3, 3), (6, 3, 3))):
        x, rim = undercut_pool(lv, x, rim + 1, w, 2, lip, rim_w, label=f"high pool {i}")
        lv.coins(x - rim_w - lip - 2, rim - 2, x - rim_w - 1)
        if i in (1, 4):
            lv.enemy(x - 1, rim - 1)
    hole = x + 1  # a hole in the rock, down into the blowhole's cave
    up = rim - 7  # the upper terrace, over a wall too high to climb
    lv.rect(hole - 1, rim, hole + 30, BOTTOM)
    lv.rect(hole + 4, up, hole + 30, rim - 1)
    basin(lv, hole, hole + 2, rim + 1, rim + 12, air=1)
    basin(lv, hole + 3, hole + 12, rim + 9, rim + 12)  # the cave
    bh = hole + 13  # the blowhole, two wide
    basin(lv, bh, bh + 1, up, rim + 12, UP)
    lv.carve(bh, up - 3, bh + 1, up - 1)
    lv.wp(hole + 7, rim + 9, hole + 9, rim + 12, label="blowhole cave")
    lv.wp(bh + 2, up - 1, bh + 4, up - 1, ground=True, label="upper terrace")
    dress(lv, range(hole + 4, hole + 12, 3), rim + 9, (ANEMONE, SEAWEED, CORAL), seed=364)
    lv.coins(bh, up - 2, bh + 1)
    lv.coins(hole + 5, rim + 11, hole + 10, 1)

    # --- The upper lagoon and its sea stacks --------------------------------------------------------------
    lg0 = bh + 7
    lv.rect(bh + 2, up, lg0 - 1, BOTTOM)
    rim = up
    lg1, lsurf = lg0 + 54, rim + 3
    lv.rect(lg0, lsurf + 5, lg1, BOTTOM)
    lv.carve(lg0, lsurf - 6, lg1, lsurf + 4)
    lv.water(lg0, lsurf, lg1, lsurf + 4)
    lv.rect(lg0, lsurf - 1, lg0 + 1, lsurf + 4)  # the step back out
    stacks = [(6, -1, 1), (6, -1, 1), (5, 0, 2), (6, -1, 1), (5, -3, 1), (7, -2, 2), (6, -3, 1), (6, -4, 1)]
    sx = lg0
    for dx, dy, sw in stacks:
        sx += dx
        stop = rim + dy
        lv.rect(sx, stop, sx + sw - 1, lsurf + 4)
        lv.coin(sx, stop - 2)
        lv.wp(sx, stop - 1, sx + sw - 1, stop - 1, ground=True, label=f"stack {sx}")
        sx += sw - 1
    crown_foot = rim - 5
    lv.rect(lg1 + 1, crown_foot, lg1 + 40, BOTTOM)
    lv.wp(lg1 + 1, crown_foot - 1, lg1 + 3, crown_foot - 1, ground=True, label="crown foot")
    dress(lv, range(lg0 + 3, lg1, 4), lsurf, (SEAWEED, CORAL, ANEMONE), seed=362)
    for kx in (lg0 + 8, lg0 + 23, lg0 + 37):
        lv.big_decor(kx, lsurf + 4, KELP)
    lv.enemy(lg1 + 2, crown_foot - 1)

    # --- The crown: its pools up to the cairn -------------------------------------------------------------
    x, rim = lg1 + 5, crown_foot
    for i, (w, lip, rim_w) in enumerate(((5, 2, 2), (6, 3, 3), (6, 3, 2), (5, 2, 3), (7, 3, 3))):
        x, rim = undercut_pool(lv, x, rim + 1, w, 2, lip, rim_w, label=f"crown pool {i}")
        lv.coins(x - rim_w - lip - 2, rim - 2, x - rim_w - 1)
        if i == 2:
            lv.enemy(x - 1, rim - 1)
    lv.enemy(x - 1, rim - 1)
    lv.rect(x, rim - 2, x + 8, BOTTOM)  # the crown
    lv.wp(x, rim - 3, x + 2, rim - 3, ground=True, label="crown")
    lv.rect(x + 4, rim - 3, x + 5, rim - 3)  # the cairn
    lv.rect(x + 4, rim - 4, x + 4, rim - 4)
    lv.coins(x, rim - 5, x + 3, 1)
    lv.flag(x + 7, rim - 3)
    lv.wp(x + 7, rim - 3, label="flag")
    lv.decor(x + 1, rim - 3, STARFISH)
    shift(lv, 0, 16)  # keep every row on the positive side
    return lv
