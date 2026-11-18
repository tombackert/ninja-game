"""Level 35 - The Beacon (mars rock, old stone, Mars sky). Finale of Mars.

On the shore of a sea that dried up a billion years ago stands a tower
built by someone who was here before us: a lighthouse for ships nobody has
seen. Its lamp still holds a crystal as big as a house. Over the dry canal
and in through its gate; up the hall, through the hatch by a crack-riddled
wall; west through the machine room over the holes in its floor; east under
the hanging cables and out of a window on to the balcony (the first
banner). The storey above is sealed, so the climb goes outside, wall to
wall between the tower and its antenna mast, and back in through a window
into the gallery of lenses. Up into the storey whose floor fell in (the
second banner), from floe to floe, under the great crystal of the lamp
and out through the roof hatch on to the top of the tower, up the cupola
to the flag.
"""

from tools.worlds.builder import Level, holed_chimney

BOTTOM = 182
G = 170  # the dry seabed
X0, X1 = 40, 66  # the tower's outer faces (walls two thick)
TOWER = "stone"
GLASS = "reef"


def top(k: int) -> int:
    """Top row of plate k (plate 0 is the ground floor, plate 7 the roof)."""
    return G - 15 * k


def hatch(lv: Level, k: int, west: bool, hang: int = 10, rest: int = 6):
    """The hatch through plate k at the west or east end of the storey under it,
    and a wall hanging from the plate beside it `hang` rows down: the gap
    between it and the tower's wall is climbed wall to wall."""
    t = top(k)
    if west:
        lv.carve(X0 + 2, t, X0 + 5, t + 1)
        lv.rect(X0 + 6, t + 2, X0 + 6, t + 1 + hang, TOWER)
        lv.wp(X0 + 2, t + 2 + hang, X0 + 5, t + 4 + hang, label=f"hatch {k} foot")
        rests(lv, X0 + 2, X0 + 5, [(1, top(k - 1) - 1 - rest)], f"hatch {k}")
        lv.wp(X0 + 6, t - 1, X0 + 9, t - 1, ground=True, label=f"through hatch {k}")
    else:
        lv.carve(X1 - 5, t, X1 - 2, t + 1)
        lv.rect(X1 - 6, t + 2, X1 - 6, t + 1 + hang, TOWER)
        lv.wp(X1 - 5, t + 2 + hang, X1 - 2, t + 4 + hang, label=f"hatch {k} foot")
        rests(lv, X1 - 5, X1 - 2, [(-1, top(k - 1) - 1 - rest)], f"hatch {k}")
        lv.wp(X1 - 9, t - 1, X1 - 6, t - 1, ground=True, label=f"through hatch {k}")


def rests(lv: Level, x0: int, x1: int, spec, label: str, t=TOWER):
    for side, row in spec:
        rx = x0 if side < 0 else x1
        lv.rect(rx, row, rx, row, t)
        lv.wp(rx, row - 1, ground=True, label=f"{label} rest {row}")
        lv.coin((x0 + x1) // 2, row - 3)


def build() -> Level:
    lv = Level(35, "mars", background="background-mars.png")
    lv.rect(-44, G, 100, BOTTOM)

    # --- The tower ------------------------------------------------------------------------------------------
    lv.rect(X0, top(7), X1, G - 1, TOWER)
    for k in (1, 2, 3, 5, 6, 7):  # hollow storeys (storey 4 is sealed)
        lv.carve(X0 + 2, top(k) + 2, X1 - 2, top(k - 1) - 1)
    for k in range(1, 8):  # cornices
        lv.rect(X0 - 1, top(k), X0 - 1, top(k), TOWER)
        lv.rect(X1 + 1, top(k), X1 + 1, top(k), TOWER)
        lv.carve(X0, top(k) + 6, X0, top(k) + 8)  # slit windows
        lv.carve(X1, top(k) + 6, X1, top(k) + 8)

    # --- The dry canal before the tower ---------------------------------------------------------------------
    lv.spawn(-40, G - 1)
    lv.decor(-36, G - 1, 3)
    lv.big_decor(-31, G - 1, 5)
    lv.coins(-34, G - 3, -26, 2)
    lv.carve(-24, G, -14, BOTTOM)  # the canal
    lv.rect(-20, G - 1, -19, BOTTOM, TOWER)  # a pier of the old bridge
    lv.crumble(-20, G - 1, -19)  # its top is loose
    lv.wp(-20, G - 2, -19, G - 2, ground=True, label="bridge pier")
    lv.wp(-13, G - 1, -10, G - 1, ground=True, label="past the canal")
    lv.enemy(-4, G - 1)
    for x, h in ((-8, 2), (4, 1), (12, 2), (26, 3)):
        lv.rect(x, G - h, x + 1, G - 1, TOWER)  # fallen blocks
    lv.rect(24, G - 2, 25, G - 1, TOWER)
    lv.coins(0, G - 4, 30, 3)
    lv.enemy(18, G - 1)
    lv.carve(X0, G - 5, X0 + 1, G - 1)  # the gate
    lv.wp(34, G - 1, 37, G - 1, ground=True, label="the gate")

    # --- Storey 1: the hall, the crack-riddled wall ----------------------------------------------------------------
    f = G - 1
    for x in (46, 53):
        lv.rect(x, f - 1, x + 1, f, TOWER)
    lv.enemy(50, f)
    lv.enemy(57, f)
    holed_chimney(
        lv, X1 - 6, 4, top(1) + 2, G, rests=[(1, f - 5), (-1, f - 9)], label="cracked wall", t=TOWER, top=False
    )
    lv.crumble(X1 - 2, f - 5)  # the crack runs through the lower rest
    lv.carve(X1 - 5, top(1), X1 - 2, top(1) + 1)
    lv.wp(X1 - 9, top(1) - 1, X1 - 6, top(1) - 1, ground=True, label="through hatch 1")

    # --- Storey 2: the machine room, holes in its floor -------------------------------------------------------------
    f = top(1) - 1
    for x0, x1 in ((53, 56), (46, 48)):
        lv.carve(x0, top(1), x1, top(1) + 1)
        lv.wp(x0 - 2, f, x0 - 1, f, ground=True, label=f"past hole {x0}")
        lv.coins(x0, f - 2, x1, 2)
    lv.rect(50, f - 4, 51, f - 4, TOWER)  # a cog wheel's axle
    lv.flamejet(51, top(1), "up", on=40, phase=8)  # the machines still vent
    lv.decor(58, f, 6)
    hatch(lv, 2, west=True)

    # --- Storey 3: under the hanging cables, out on to the balcony --------------------------------------------------
    f = top(2) - 1
    for x in (49, 55, 61):
        lv.rect(x, top(3) + 2, x, f - 3, TOWER)
    for i, x in enumerate((52, 58)):
        lv.rect(x, f - 1, x, f, TOWER)
        lv.wp(x, f - 2, ground=True, label=f"cable block {i}")
    lv.enemy(46, f)
    lv.carve(X1 - 1, f - 3, X1, f)  # the window
    lv.rect(X1 + 1, top(2), X1 + 4, top(2) + 1, TOWER)  # the balcony
    lv.wp(X1 + 1, f, X1 + 4, f, ground=True, label="the balcony")
    lv.checkpoint(X1 + 2, f)

    # --- Outside: between the tower and the antenna mast ------------------------------------------------------------
    mast = X1 + 5
    lv.rect(mast, top(5) + 1, mast, G - 1, TOWER)
    lv.rect(mast - 1, top(5) - 1, mast + 1, top(5), GLASS)  # its beacon
    rests(lv, X1 + 1, mast - 1, [(1, f - 6), (-1, f - 12), (1, f - 18), (-1, f - 24)], "mast")
    w5 = top(4) - 1  # storey 5's floor row
    lv.carve(X1 - 1, w5 - 3, X1, w5)  # the window back in
    lv.wp(X1 - 4, w5, X1 - 2, w5, ground=True, label="the gallery of lenses")

    # --- Storey 5: the gallery of lenses ----------------------------------------------------------------------------
    f = w5
    for i, (x, h) in enumerate(((57, 2), (51, 2), (47, 1))):
        lv.rect(x, f - h + 1, x + 2, f, GLASS)
        lv.wp(x, f - h, x + 2, f - h, ground=True, label=f"lens {i}")
        lv.coin(x + 1, f - h - 2)
    lv.enemy(55, f)
    lv.enemy(50, f)
    hatch(lv, 5, west=True)

    # --- Storey 6: the floor fell in; from floe to floe -------------------------------------------------------------
    f = top(5) - 1
    lv.checkpoint(X0 + 8, f)
    lv.carve(X0 + 10, top(5), X1 - 7, top(5) + 1)
    for i, (x, row, w) in enumerate(((52, f + 1, 2), (57, f, 1))):
        lv.rect(x, row, x + w - 1, row, TOWER)
        if i == 1:  # it breaks off
            lv.crumble(x, row)
        lv.wp(x, row - 1, x + w - 1, row - 1, ground=True, label=f"floe {i}")
        lv.coin(x, row - 2)
    hatch(lv, 6, west=False)

    # --- Storey 7: the lamp room ------------------------------------------------------------------------------------
    f = top(6) - 1
    lv.rect(49, top(7) + 2, 57, top(7) + 7, GLASS)  # the great crystal, hanging from the roof
    lv.rect(51, top(7) + 8, 55, top(7) + 8, GLASS)
    lv.enemy(53, f)
    lv.coins(46, f - 2, 60, 2)
    hatch(lv, 7, west=True, hang=8)

    # --- The roof and the cupola ------------------------------------------------------------------------------------
    r = top(7) - 1
    lv.enemy(64, r)
    for i, (x0, x1, row) in enumerate(((51, 61, r - 1), (53, 59, r - 3), (55, 57, r - 5))):
        lv.rect(x0, row, x1, r, TOWER)
        lv.wp(x0, row - 1, x0 + 1, row - 1, ground=True, label=f"cupola {i}")
    lv.rect(56, r - 8, 56, r - 6, GLASS)  # the spire
    lv.coins(X0 + 8, r - 2, 50, 2)
    lv.flag(55, r - 6)
    lv.wp(55, r - 6, label="flag")
    return lv
