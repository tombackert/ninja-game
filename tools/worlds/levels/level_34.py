"""Level 34 - The Polar Layers (mars dust, ice, Mars sky).

At the Martian pole every winter lays down a sheet of ice and every summer a
sheet of dust on top of it, and the cap has grown that way for a million
years: plate on plate, with hollow storeys between them where the ice sank
away. Where a plate cracked, a gap leads up into the storey above, but the
cracks never sit over each other: each storey has to be crossed end to end
to reach the next one. In at the cap's foot, east past the stalagmites, up
through the first crack, back west over the crevasses, east again under the
icicles, west over the thin ice (the banner stands where it starts), east
past the frost-guards behind their ice walls, west across the storey whose
floor fell in from one floating floe to the next, and up the last crack out
on to the cap, where the flag stands at the edge of the summer ice.
"""

from tools.worlds.builder import Level

BOTTOM = 112
FLOOR = 100  # the cap's foot
W, E = 0, 38  # the cap's outer walls (the storeys are x 1..37)
ICE = "reef"


def top(k: int) -> int:
    """Top row of plate k (plate 0 is the ground under the cap)."""
    return FLOOR - 9 * k


def build() -> Level:
    lv = Level(34, "mars", background="background-mars.png")
    lv.rect(-24, FLOOR, 70, BOTTOM)
    lv.rect(W - 6, top(6), E, FLOOR - 1)
    for k in range(1, 7):  # hollow storeys between plates, ice and dust in turn
        lv.carve(W + 1, top(k) + 2, E - 1, top(k - 1) - 1)
        if k % 2 == 0:
            lv.rect(W + 1, top(k), E - 1, top(k) + 1, ICE)

    def crack(k: int):
        """The crack through plate k: at the east end for odd k, the west end for
        even; the rock of the storey's ceiling hangs four rows down beside it."""
        t = top(k)
        if k % 2:
            lv.carve(E - 3, t, E - 1, t + 1)
            lv.rect(E - 4, t + 2, E - 4, t + 5, ICE if k % 2 == 0 else "mars")
            lv.wp(E - 3, t + 6, E - 1, t + 8, label=f"crack {k}")
            lv.wp(E - 7, t - 1, E - 4, t - 1, ground=True, label=f"storey {k + 1}")
        else:
            lv.carve(W + 1, t, W + 3, t + 1)
            lv.rect(W + 4, t + 2, W + 4, t + 5, ICE)
            lv.wp(W + 1, t + 6, W + 3, t + 8, label=f"crack {k}")
            lv.wp(W + 4, t - 1, W + 7, t - 1, ground=True, label=f"storey {k + 1}")

    # --- The foot of the cap; storey 1: stalagmites ----------------------------------------------------------
    lv.spawn(-20, FLOOR - 1)
    lv.decor(-16, FLOOR - 1, 3)
    lv.big_decor(-10, FLOOR - 1, 5)
    lv.coins(-14, FLOOR - 3, -2, 3)
    lv.carve(W - 6, FLOOR - 4, W, FLOOR - 1)  # the way in
    f = FLOOR - 1
    for i, (x, h) in enumerate(((9, 2), (17, 2), (25, 1), (30, 2))):
        lv.rect(x, f - h + 1, x + 1, f, ICE)
        lv.wp(x, f - h, x + 1, f - h, ground=True, label=f"stalagmite {i}")
        lv.coin(x, f - h - 2)
    lv.enemy(13, f)
    lv.enemy(22, f)
    crack(1)

    # --- Storey 2: crevasses (a fall is a storey back down) --------------------------------------------------------
    f = top(1) - 1
    for i, (x0, x1) in enumerate(((27, 30), (19, 23), (10, 13))):
        lv.carve(x0, top(1), x1, top(1) + 1)
        lv.wp(x0 - 3, f, x0 - 1, f, ground=True, label=f"past crevasse {i}")
        lv.coins(x0, f - 2, x1, 2)
    lv.enemy(16, f)
    lv.crumble(18, top(1))  # the dust at a crevasse's lip is loose
    crack(2)

    # --- Storey 3: icicles hanging to three rows over the floor, ice blocks between ---------------------------------
    f = top(2) - 1
    for x in (9, 15, 21, 27):
        lv.rect(x, top(3) + 2, x, f - 3, ICE)
    for i, x in enumerate((12, 18, 24)):
        lv.rect(x, f - 1, x, f, ICE)
        lv.wp(x, f - 2, ground=True, label=f"ice block {i}")
        lv.coin(x + 1, f - 1)
    crack(3)

    # --- Storey 4: thin ice (the banner where it starts) ------------------------------------------------------------
    f = top(3) - 1
    lv.checkpoint(E - 6, f)
    for x0, x1 in ((28, 30), (23, 25), (17, 20), (12, 14), (7, 9)):
        lv.carve(x0, top(3), x1, top(3) + 1)
    for x in (26, 21):  # the thinnest bits of the floor give way
        lv.crumble(x, top(3), x + 1)
        lv.crumble(x, top(3) + 1, x + 1)
    for i, x in enumerate((26, 21, 15)):
        lv.wp(x - 1, f, x, f, ground=True, label=f"thin ice {i}")
        lv.coin(x, f - 2)
    crack(4)

    # --- Storey 5: frost-guards behind their ice walls, a crevasse --------------------------------------------------
    f = top(4) - 1
    for i, (x, guard) in enumerate(((10, 13), (21, 24), (31, 34))):
        lv.rect(x, f - 1, x, f, ICE)
        lv.wp(x, f - 2, ground=True, label=f"ice wall {i}")
        lv.enemy(guard, f)
    lv.carve(15, top(4), 18, top(4) + 1)
    lv.coins(15, f - 3, 18, 1)
    crack(5)

    # --- Storey 6: the floor fell in; from floe to floe -------------------------------------------------------------
    f = top(5) - 1
    lv.carve(6, top(5), E - 5, top(5) + 1)
    floes = ((28, f + 1, 2), (22, f, 2), (16, f + 1, 1), (10, f, 2))
    for i, (x, row, w) in enumerate(floes):
        lv.rect(x, row, x + w - 1, row, ICE)
        lv.wp(x, row - 1, x + w - 1, row - 1, ground=True, label=f"floe {i}")
        lv.coin(x, row - 2)
    crack(6)

    # --- On the cap -------------------------------------------------------------------------------------------------
    t = top(6)
    lv.rect(E + 1, t, 70, FLOOR - 1)
    lv.rect(W + 1, t, 70, t, ICE)
    for k in range(2, 6, 2):  # the layers show in the cap's flanks
        lv.rect(W - 6, top(k), W, top(k) + 1, ICE)
        lv.rect(E, top(k), 70, top(k) + 1, ICE)
    for x in range(W - 6, W):
        lv.rect(x, t - (1 if x % 3 else 2), x, t - 1, ICE)
    lv.carve(W + 1, t, W + 3, t + 1)
    for x, h in ((14, 1), (22, 2), (34, 1), (48, 2)):
        lv.rect(x, t - h, x + 1, t - 1, ICE)
    lv.enemy(28, t - 1)
    lv.enemy(52, t - 1)
    lv.decor(42, t - 1, 3)
    lv.big_decor(60, t - 1, 5)
    lv.coins(10, t - 4, 56, 4)
    lv.flag(64, t - 1)
    lv.wp(64, t - 1, label="flag")
    return lv
