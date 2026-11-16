"""Level 38 - Kelp Forest (reef, lagoon sky).

Under the cliffs the kelp grows on narrow rock pillars, a forest of trunks
from the sea floor to the overhang above, and the tide runs between them
in lanes, up one, down the next. Off the beach into the forest under the
overhang: down the first lane, under a trunk, up the next and through a
gap in the trunk beside it at the right height, lane after lane east,
past stalks fallen across the lanes, with air only in three hollows in
the overhang (miss a gap on the way up and the
lane pins you under the rock until you swim back over the trunk you came
by). In the clearing the last lane carries up to the light, and two trunks
stand on up out of the water: wall to wall between them, with two rest
ledges, up to the cliff top and the checkpoint banner. Then down the
sinkhole into the deep wood, where an undertow runs back west along the
floor and pushes anyone who sinks to it back: through the lanes again,
past its three hollows of air, and up the last lane into the old sea cave,
then wall to wall up its chimney and out on to the headland with the flag.
"""

from tools.worlds.builder import DOWN, LEFT, STILL, UP, Level, holed_chimney
from tools.worlds.kits.water import ANEMONE, CORAL, FAN_CORAL, KELP, SEAWEED, STARFISH, basin, dress, pocket

BOTTOM = 64
SURF = 31  # the sea's surface at the beach and in the clearing


def trunks(lv: Level, x0: int, top: int, floor: int, spec, label: str):
    """A stand of kelp trunks under rock: water from row `top` to the row over
    `floor`, a trunk (one wide) every four columns from x0 on, the lanes
    between them three wide. `spec` is one (flow of the lane west of the
    trunk, the trunk's open rows) per trunk. Each lane gets kelp on its
    floor. Returns the x of the lane after the last trunk."""
    x = x0
    for i, (flow, gaps) in enumerate(spec):
        lv.water(x, top, x + 2, floor - 1, flow)
        lv.rect(x + 3, top, x + 3, floor - 1)
        for g0, g1 in gaps:
            lv.carve(x + 3, g0, x + 3, g1)
            lv.water(x + 3, g0, x + 3, g1)
        if i % 2 == 0:
            lv.big_decor(x + 1, floor - 1, KELP)
        x += 4
    return x


def build() -> Level:
    lv = Level(38, "reef", background="background-lagoon.png")

    # --- The beach under the cliffs --------------------------------------------------------------------
    lv.rect(-4, SURF, 14, BOTTOM, "sand")
    lv.rect(-4, SURF + 3, 14, BOTTOM)
    lv.spawn(2, SURF - 1)
    lv.decor(5, SURF - 1, STARFISH)
    lv.coins(4, SURF - 3, 10, 2)
    lv.wp(10, SURF - 1, 14, SURF - 1, ground=True, label="beach")
    lv.rect(15, SURF + 15, 100, BOTTOM)  # the sea floor under the forest
    lv.rect(17, 4, 76, SURF - 1)  # the cliff's overhang over the forest
    basin(lv, 15, 16, SURF, SURF + 14)  # the bay at the forest's edge

    # --- The kelp lanes under the overhang -------------------------------------------------------------
    top, floor = SURF, SURF + 15
    t = top
    spec = [
        (DOWN, [(t + 13, t + 14), (t, t + 1)]),  # under it (and back over it after a miss)
        (UP, [(t + 2, t + 3)]),
        (DOWN, [(t + 9, t + 10)]),
        (UP, []),  # air in the overhang over this lane and the next trunk
        (DOWN, [(t + 13, t + 14), (t, t + 1)]),
        (UP, [(t + 4, t + 5)]),
        (STILL, [(t + 11, t + 12)]),
        (UP, []),  # air
        (DOWN, [(t + 13, t + 14), (t, t + 1)]),
        (UP, [(t + 3, t + 4)]),
        (DOWN, [(t + 7, t + 8)]),
        (UP, []),  # air
        (DOWN, [(t + 13, t + 14), (t, t + 1)]),
        (UP, [(t + 2, t + 3)]),
        (DOWN, [(t + 13, t + 14)]),
    ]
    snags = {2: t + 5, 6: t + 6, 10: t + 4, 13: t + 8}  # fallen stalks caught across a lane
    x_end = trunks(lv, 17, top, floor, spec, "lane")
    hollows = {3: "first hollow", 7: "second hollow", 11: "third hollow"}
    for i, row in snags.items():
        lv.rect(17 + 4 * i, row, 17 + 4 * i + 1, row)
    for i in range(len(spec)):
        x = 17 + 4 * i
        if i in hollows:  # the planner finds its own way into a hollow; the stop is over the trunk after it
            pocket(lv, x, top - 3, x + 6, top - 1)
            lv.wp(x + 3, top - 2, x + 3, top - 1, label=f"over trunk {i}")
            continue
        g0, g1 = spec[i][1][0]
        if i != 4:  # a stop in each gap where a swimmer can rest (the planner passes trunk 4 on its own)
            lv.wp(x + 3, g0, x + 3, g1, label=f"trunk {i}")
    for k, x in enumerate(range(18, x_end, 4)):
        lv.coin(x, top + 6 + (3 if k % 2 else -3))
    dress(lv, range(18, x_end, 2), top, (SEAWEED, ANEMONE, CORAL), seed=38)

    # --- The clearing: the last lane up to the light, wall to wall up two trunks -------------------------
    cx = x_end  # the last lane, x cx..cx+3, between trunk cx-1 and trunk cx+4
    cliff = 12
    lv.carve(cx, 0, cx + 3, top - 1)
    lv.water(cx, top, cx + 3, floor - 1, UP)
    lv.rect(cx + 5, cliff, cx + 140, BOTTOM)  # the cliff east of the clearing
    lv.carve(cx, 0, cx + 140, cliff - 1)
    holed_chimney(lv, cx - 1, 4, cliff, top, rests=[(1, top - 8), (-1, top - 14)], label="trunks", top=False)
    lv.rect(cx + 4, cliff, cx + 4, floor - 1)
    lv.route = [w for w in lv.route if w.label != "trunks base"]
    lv.wp(cx + 5, cliff - 1, cx + 7, cliff - 1, ground=True, label="cliff top")
    lv.checkpoint(cx + 7, cliff - 1)  # halfway
    lv.coins(cx + 1, top - 5, cx + 2)
    lv.coins(cx + 1, top - 11, cx + 2)
    lv.big_decor(cx + 11, cliff - 1, FAN_CORAL)
    lv.enemy(cx + 14, cliff - 1)

    # --- Down the sinkhole into the deep wood --------------------------------------------------------------
    sk = cx + 18  # the sinkhole, three wide
    dtop = SURF + 10
    dfloor = dtop + 13
    lv.carve(sk, cliff, sk + 2, dtop - 5)
    basin(lv, sk, sk + 2, dtop - 4, dtop - 1, DOWN)
    d0 = sk
    u = dtop
    dspec = [
        (DOWN, [(u + 9, u + 10), (u, u + 1)]),
        (UP, [(u + 2, u + 3)]),
        (DOWN, [(u + 7, u + 8)]),
        (UP, []),  # air over this lane and the next trunk
        (DOWN, [(u + 11, u + 12), (u, u + 1)]),
        (UP, [(u + 3, u + 4)]),
        (DOWN, [(u + 11, u + 12)]),  # at the floor, against the undertow
        (UP, []),  # air
        (DOWN, [(u + 8, u + 9)]),
        (UP, [(u + 1, u + 2)]),
        (DOWN, [(u + 11, u + 12), (u, u + 1)]),
        (UP, []),  # air
        (DOWN, [(u + 6, u + 7)]),
        (UP, [(u + 2, u + 3)]),
        (DOWN, [(u + 11, u + 12)]),
    ]
    lv.carve(d0, dtop, d0 + 4 * len(dspec) + 2, dfloor - 1)
    xd = trunks(lv, d0, dtop, dfloor, dspec, "deep lane")
    lv.water(d0 + 16, dfloor - 3, xd - 1, dfloor - 1, LEFT)  # the undertow along the floor
    for i in range(len(dspec)):
        x = d0 + 4 * i
        if i in (3, 7, 11):  # as in the lanes above: no stop in the hollow, one over the trunk after it
            pocket(lv, x, dtop - 3, x + 6, dtop - 1)
            if i != 3:
                lv.wp(x + 3, dtop - 2, x + 3, dtop - 1, label=f"over deep trunk {i}")
            continue
        g0, g1 = dspec[i][1][0]
        if i not in (2, 6, 9, 14):  # stops where a swimmer can rest in the gap; the planner passes the others
            lv.wp(x + 3, g0, x + 3, g1, label=f"deep trunk {i}")
    for k, x in enumerate(range(d0 + 1, xd, 4)):
        lv.coin(x, dtop + 6 + (3 if k % 2 else -3))
    dress(lv, range(d0 + 1, xd, 2), dtop, (SEAWEED, ANEMONE, CORAL, STARFISH), seed=381)

    # --- Up the last lane into the old sea cave, up its chimney to the headland -----------------------------
    sc = xd  # the last lane
    cave_floor = dtop - 1
    lv.carve(sc, cave_floor, sc + 2, dfloor - 1)
    lv.water(sc, cave_floor, sc + 2, dfloor - 1, UP)
    lv.carve(sc, cave_floor - 8, sc + 14, cave_floor - 1)
    lv.wp(sc + 3, cave_floor - 1, sc + 5, cave_floor - 1, ground=True, label="sea cave")
    lv.decor(sc + 7, cave_floor - 1, ANEMONE)
    lv.enemy(sc + 9, cave_floor - 1)
    head = cliff - 6  # the headland's top
    ch = sc + 11  # the chimney's west wall
    lv.carve(ch, head, ch + 5, cave_floor - 1)
    lv.rect(ch - 8, head, ch - 1, cave_floor - 9)
    lv.rect(ch + 6, head, ch + 30, cave_floor)
    holed_chimney(
        lv,
        ch,
        4,
        head + 2,
        cave_floor,
        rests=[(1, cave_floor - 9), (-1, cave_floor - 17)],
        label="cave chimney",
        top=False,
    )
    lv.wp(ch + 6, head - 1, ch + 8, head - 1, ground=True, label="headland")
    lv.coins(ch + 2, cave_floor - 6, ch + 3)
    lv.coins(ch + 2, cave_floor - 13, ch + 3)
    lv.enemy(ch + 14, head - 1)
    lv.decor(ch + 11, head - 1, STARFISH)
    lv.coins(ch + 9, head - 3, ch + 17, 2)
    lv.flag(ch + 20, head - 1)
    lv.wp(ch + 20, head - 1, label="flag")
    return lv
