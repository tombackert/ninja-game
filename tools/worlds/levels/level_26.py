"""Level 26 - The Buried City (stone city, sand dunes, desert sky).

A city the desert swallowed: only roofs, towers and the palace still stand
out of the sand. Over the roofs of half-buried houses and in through the
west gate of the covered bazaar: its floor sank into the sand, so the way
through the long hall is from stall to stall under the vaults, ducking
the beams the vaults spring from. Out of its east gate, a row of tower
houses whose rooms are only reached by dashing through a window high in
the west wall (the streets between them are quicksand). Up the alley
between two houses, wall to wall, across the high roofs, inside the bell
tower from beam to beam, down on to the palace dome. The great hall bars
the way over the roofs, so down the courtyard well into the cistern under
the palace: from column to column over the dark, under its vaults, and up
the narrow well at its far end into the court between the two minarets,
up between them to the flag. The checkpoint banner stands halfway, on the
roof at the top of the alley.
"""

from tools.worlds.builder import Level, dunes, perforate

BOTTOM = 80
CITY = "stone"


def windows(lv: Level, x0: int, x1: int, row: int, every: int = 3):
    """Dark windows (enclosed 1x2 holes) in a facade, one tile in from its sides."""
    for x in range(x0 + 1, x1, every):
        if x < x1:
            lv.carve(x, row, x, row + 1)


def tower_house(lv: Level, tx: int, floor: int, top: int, wy: int, w: int = 9, slit: int = 2, crown=True):
    """A tower house `w` wide with walls two tiles thick: a window `slit` rows
    tall through the west wall whose bottom row is `wy` rows over the room's
    floor row, a room 5 rows high, a door through the east wall at floor level
    and the tower's body above."""
    lv.rect(tx, top, tx + w - 1, BOTTOM)
    lv.carve(tx + 2, floor - 5, tx + w - 3, floor - 1)  # the room
    wb = floor - 1 + wy
    lv.carve(tx, wb - slit + 1, tx + 1, wb)  # window
    lv.carve(tx + w - 2, floor - 3, tx + w - 1, floor - 1)  # door
    if floor - 9 > top + 1:
        windows(lv, tx + 1, tx + w - 2, floor - 9, every=2)
    if crown:
        for x in range(tx, tx + w, 2):
            lv.rect(x, top - 1, x, top - 1, CITY)


def dome(lv: Level, cx: int, base: int, radius: int):
    """A dome on roof row `base` (its lowest row is base - 1), centered on column cx."""
    for dy in range(radius):
        half = round((radius * radius - dy * dy) ** 0.5)
        lv.rect(cx - half, base - 1 - dy, cx + half, base - 1 - dy, CITY)


def vault(lv: Level, x0: int, x1: int, ceiling: int, rise: int = 2):
    """Carve a vault up into a flat ceiling (its lowest row of rock `ceiling`)
    over columns x0..x1: highest in the middle, springing at the ends."""
    mid = (x0 + x1) / 2
    half = (x1 - x0) / 2 + 0.5
    for x in range(x0, x1 + 1):
        d = abs(x - mid) / half
        up = round(rise * (1 - d * d) ** 0.5)
        if up > 0:
            lv.carve(x, ceiling - up + 1, x, ceiling)


def column(lv: Level, x: int, top: int, w: int = 3):
    """A cistern column: a capital `w` wide on a 1-wide shaft down into the dark."""
    lv.rect(x, top, x + w - 1, top, CITY)
    lv.rect(x + w // 2, top + 1, x + w // 2, BOTTOM, CITY)


def build() -> Level:
    lv = Level(26, CITY, background="background-desert.png")

    # --- The outskirts ----------------------------------------------------------------
    tops = dunes(lv, 0, 22, 58, 1.0, 4.5, BOTTOM, t="sand")
    lv.spawn(3, tops[3] - 1)
    lv.decor(7, tops[7] - 1, 4)
    lv.big_decor(13, tops[13] - 1, 3)
    lv.decor(18, tops[18] - 1, 5)
    for x in (10, 16):
        lv.enemy(x, tops[x] - 1)
    lv.coins(4, tops[4] - 3, 12, 2)
    lv.wp(19, tops[19] - 1, 22, tops[22] - 1, ground=True, label="outskirts")

    # --- Half-buried houses over the quicksand streets -----------------------------------
    houses = [(26, 31, 56), (35, 40, 54), (45, 49, 55), (53, 59, 52), (63, 67, 54)]
    for i, (x0, x1, roof) in enumerate(houses):
        lv.rect(x0, roof + 1, x1, BOTTOM, CITY)
        lv.rect(x0, roof, x1, roof, "sand")  # the dunes drifted over the roofs
        windows(lv, x0, x1, roof + 3)
        lv.wp(x0, roof - 1, x1, roof - 1, ground=True, label=f"house {i}")
        lv.coin((x0 + x1) // 2, roof - 3)
    for x, roof in ((38, 54), (55, 52)):
        lv.enemy(x, roof - 1)
    lv.decor(66, 53, 4)  # a cactus took root on the roof
    lv.decor(28, 55, 5)

    # --- The aqueduct: across the broken spans to the tower quarter -----------------------------
    # The city's aqueduct still crosses the quicksand on its arches, but its deck
    # broke in places; one stretch of its channel is still covered.
    a0, a1, deck = 72, 113, 50  # piers 2 wide every 8 columns, the deck two rows thick
    lv.rect(69, 52, 70, BOTTOM, CITY)  # rubble of the west abutment
    lv.wp(69, 51, 70, 51, ground=True, label="aqueduct rubble")
    lv.rect(a0, deck, a1, deck + 1, CITY)
    for px in range(a0, a1, 8):
        lv.rect(px, deck + 2, px + 1, BOTTOM, CITY)
        if px + 9 <= a1:  # the arch between this pier and the next springs from both
            lv.rect(px + 2, deck + 2, px + 3, deck + 2, CITY)
            lv.rect(px + 6, deck + 2, px + 7, deck + 2, CITY)
            lv.rect(px + 2, deck + 3, px + 2, deck + 3, CITY)
            lv.rect(px + 7, deck + 3, px + 7, deck + 3, CITY)
    lv.wp(a0, deck - 1, a0 + 3, deck - 1, ground=True, label="aqueduct deck")
    lv.coins(a0 + 2, deck - 2, a0 + 8, 2)
    # first break: eight columns of deck gone
    lv.carve(83, deck, 90, deck + 3)
    lv.carve(88, deck + 4, 89, deck + 6)  # its pier broke lower
    lv.wp(91, deck - 1, 93, deck - 1, ground=True, label="aqueduct break 1")
    lv.coins(84, deck - 3, 88)
    # the covered channel: its cover slabs still lie on the deck, a hole under them
    lv.rect(92, deck - 3, 103, deck - 3, CITY)
    lv.carve(98, deck, 101, deck + 3)
    lv.wp(102, deck - 1, 103, deck - 1, ground=True, label="covered channel")
    lv.coins(93, deck - 1, 97)
    lv.enemy(79, deck - 1)
    # the last span fell, its pier broke lower: a long dash to the broken pier
    lv.carve(106, deck, a1, deck + 3)
    lv.carve(a1 - 1, deck + 4, a1, deck + 4)
    lv.carve(a1 - 1, deck + 5, a1 - 1, deck + 7)  # only a sliver of it stands
    lv.wp(a1, deck + 4, ground=True, label="broken pier")
    lv.coins(107, deck - 2, 110)
    lv.decor(a0 + 5, deck - 1, 4)
    lv.decor(94, deck - 4, 5)

    # --- Tower houses: dash in through the window -------------------------------------------
    # (gap from the last edge, floor change, window bottom over the floor, tower height)
    specs = [
        (6, 0, -2, 12),
        (7, 1, -3, 14),
        (7, 0, -3, 11),
        (7, 0, -3, 15),
        (7, 1, -3, 12),
        (7, 1, -3, 13),
        (8, 0, -2, 14),
        (7, 1, -3, 26),
    ]
    x, floor = a1, deck + 5
    for i, (gap, dr, wy, h) in enumerate(specs):
        tx = x + gap + 1
        floor += dr
        last = i == len(specs) - 1
        tower_house(lv, tx, floor, floor - h, wy, crown=not last)
        lv.wp(tx + 1, floor - 1, tx + 3, floor - 1, ground=True, label=f"tower room {i}")
        lv.coins(tx + 3, floor - 2, tx + 5, 2)
        lv.coin(tx - gap // 2, floor - 4 + wy)  # over the street, on the way to the window
        if i in (1, 3, 6):
            lv.enemy(tx + 5, floor - 1)
        x = tx + 8
    alley_floor, t5_top = floor, floor - specs[-1][3]

    # --- The alley: wall to wall up between two houses -------------------------------------------
    ax = x + 1  # alley columns ax..ax+2, the last tower's east wall on its left
    roof_q = alley_floor - 22
    lv.rect(ax, alley_floor, ax + 2, BOTTOM, CITY)
    lv.rect(ax + 3, roof_q, ax + 16, BOTTOM, CITY)  # house Q
    perforate(lv, x, t5_top + 1, alley_floor - 6, solid=2, gap=1)
    perforate(lv, ax + 3, roof_q + 1, alley_floor - 6, solid=2, gap=1)
    lv.rect(ax + 2, alley_floor - 11, ax + 2, alley_floor - 11, CITY)  # a balcony to rest on
    lv.wp(ax, alley_floor - 3, ax + 2, alley_floor - 1, ground=True, label="alley")
    lv.wp(ax + 2, alley_floor - 12, ground=True, label="balcony")
    lv.coin(ax + 1, alley_floor - 7)
    lv.coin(ax + 1, alley_floor - 16)
    lv.wp(ax + 3, roof_q - 1, ax + 5, roof_q - 1, ground=True, label="roof of house Q")
    lv.checkpoint(ax + 4, roof_q - 1)  # halfway: up the alley, before the high roofs

    # --- High roofs ---------------------------------------------------------------------------
    q = ax + 3
    windows(lv, q, q + 13, roof_q + 3)
    for xe in (q + 6, q + 11):
        lv.enemy(xe, roof_q - 1)
    lv.decor(q + 9, roof_q - 1, 3)
    lv.big_decor(q + 3, roof_q - 1, 2)  # a roof garden
    lv.coins(q + 2, roof_q - 3, q + 12, 2)
    r2, r3 = roof_q - 2, roof_q + 1
    lv.rect(q + 19, r2, q + 25, BOTTOM, CITY)
    lv.wp(q + 19, r2 - 1, q + 21, r2 - 1, ground=True, label="high roof 2")
    windows(lv, q + 19, q + 25, r2 + 3)
    lv.enemy(q + 23, r2 - 1)
    lv.rect(q + 29, r3, q + 38, BOTTOM, CITY)
    lv.wp(q + 29, r3 - 1, q + 31, r3 - 1, ground=True, label="high roof 3")
    windows(lv, q + 29, q + 38, r3 + 3)
    lv.coins(q + 30, r3 - 3, q + 36, 3)
    lv.decor(q + 35, r3 - 1, 3)
    lv.big_decor(q + 33, r3 - 1, 1)

    # --- Inside the bell tower, from beam to beam ---------------------------------------------------
    bl = q + 39  # outer west wall; walls two thick, inside bl+2 .. bl+6
    beams = 8
    roof_b = r3 - 3 * beams - 6
    lv.rect(bl, roof_b, bl + 8, BOTTOM, CITY)
    lv.carve(bl + 2, roof_b + 2, bl + 6, r3 - 1)
    lv.carve(bl, r3 - 3, bl + 1, r3 - 1)  # door from the roofs
    lv.wp(bl + 2, r3 - 1, bl + 6, r3 - 1, ground=True, label="bell tower floor")
    for i in range(beams):
        row = r3 - 3 * (i + 1)
        xs = (bl + 6, bl + 6) if i % 2 == 0 else (bl + 2, bl + 2)  # one-tile beams
        lv.rect(xs[0], row, xs[1], row, CITY)
        lv.wp(xs[0], row - 1, xs[1], row - 1, ground=True, label=f"beam {i}")
        lv.coin(bl + 4, row - 1)
    for k in range(1, beams, 2):  # slits in the outer walls
        lv.carve(bl, r3 - 3 * k - 2, bl, r3 - 3 * k - 1)
        lv.carve(bl + 8, r3 - 3 * k - 3, bl + 8, r3 - 3 * k - 2)
    belfry = r3 - 3 * beams  # top beam row
    lv.carve(bl + 7, belfry - 4, bl + 8, belfry - 2)  # the belfry's arch, out to the east
    lv.rect(bl + 2, roof_b - 3, bl + 6, roof_b - 1, CITY)  # the spire
    lv.rect(bl + 3, roof_b - 5, bl + 5, roof_b - 4, CITY)
    lv.rect(bl + 4, roof_b - 7, bl + 4, roof_b - 6, CITY)
    lv.wp(bl + 7, belfry - 4, bl + 8, belfry - 2, label="belfry arch")

    # --- The palace: its dome and roof ------------------------------------------------------------
    p0, p1, proof = bl + 16, bl + 118, r3 + 2
    lv.rect(p0, proof, p1, BOTTOM, CITY)
    windows(lv, p0, p1, proof + 3, every=4)
    dome_c, radius = p0 + 12, 7
    dome(lv, dome_c, proof, radius)
    lv.rect(dome_c, proof - radius - 3, dome_c, proof - radius - 1, CITY)  # the finial
    lv.wp(dome_c - 3, proof - radius - 2, dome_c + 3, proof - 2, ground=True, label="dome")
    lv.wp(dome_c + 9, proof - 1, dome_c + 11, proof - 1, ground=True, label="palace roof")
    for xe in (dome_c + 13, dome_c + 16):
        lv.enemy(xe, proof - 1)
    lv.coins(dome_c + 8, proof - 3, dome_c + 16, 2)
    lv.big_decor(dome_c - 10, proof - 1, 2)

    # --- The great hall bars the roofs: down the courtyard well ------------------------------------
    w1 = dome_c + 19  # the courtyard well, w1..w1+2
    m = p1 - 9  # the west minaret: m-1..m; the east one: m+5..m+6
    gh0, gh1 = w1 + 6, m - 2  # the great hall, ten rows over the palace roof
    lv.rect(gh0, proof - 10, gh1, proof, CITY)
    windows(lv, gh0, gh1, proof - 6, every=3)
    dome(lv, (gh0 + gh1) // 2, proof - 10, 5)
    for x in range(gh0, gh1 + 1, 2):
        lv.rect(x, proof - 11, x, proof - 11, CITY)
    lv.rect(w1 - 1, proof - 1, w1 - 1, proof - 1, CITY)  # the well's curb
    lv.rect(w1 + 3, proof - 1, w1 + 3, proof - 1, CITY)
    lv.big_decor(w1 - 4, proof - 1, 2)

    # --- The cistern under the palace: column to column over the dark ----------------------------
    ceil_c = proof + 5  # the cistern's ceiling (lowest rock row)
    c0, c1 = w1 - 3, m + 6
    lv.carve(c0, ceil_c + 1, c1, BOTTOM)
    lv.carve(w1, proof, w1 + 2, ceil_c)  # the courtyard well
    # (x, capital row, width): two or three rows under the springers, the vaults' crowns over the gaps
    cols = [
        (w1 - 1, ceil_c + 5, 5),
        (w1 + 10, ceil_c + 3, 2),
        (w1 + 18, ceil_c + 3, 2),
        (w1 + 26, ceil_c + 4, 2),
        (w1 + 34, ceil_c + 3, 2),
        (w1 + 42, ceil_c + 3, 2),
        (w1 + 50, ceil_c + 3, 2),
    ]
    shafts = []
    for i, (x, top, w) in enumerate(cols):
        column(lv, x, top, w)
        shafts.append(x + w // 2)
        lv.wp(x, top - 1, x + w - 1, top - 1, ground=True, label=f"cistern column {i}")
        if i:
            lv.coin(x + w // 2, top - 2)
    # the far well head: a ledge under the narrow well up into the court
    wl = m + 1  # the narrow well, wl..wl+1, along the west minaret
    lv.rect(wl - 5, ceil_c + 3, c1, ceil_c + 3, CITY)
    lv.rect(c1 - 1, ceil_c + 4, c1 - 1, BOTTOM, CITY)
    shafts.append(wl - 5)
    for sa, sb in zip(shafts, shafts[1:]):  # a vault from column to column
        vault(lv, sa + 1, sb - 1, ceil_c, rise=2)
    lv.wp(wl - 1, ceil_c + 2, wl + 1, ceil_c + 2, ground=True, label="well head")
    lv.carve(wl, proof, wl + 1, ceil_c)
    perforate(lv, wl - 1, proof + 1, ceil_c, solid=2, gap=1)  # worn steps in its walls
    perforate(lv, wl + 2, proof + 1, ceil_c - 1, solid=2, gap=1)
    lv.coin(wl, ceil_c - 2)
    lv.coin(wl + 1, proof + 1)
    lv.decor(wl + 3, ceil_c + 2, 5)

    # --- Up between the minarets to the flag -----------------------------------------------------
    mtop = proof - 24
    lv.rect(m - 1, mtop, m, proof - 1, CITY)
    lv.rect(m + 5, mtop, m + 6, proof - 1, CITY)
    perforate(lv, m, mtop + 1, proof - 6, solid=2, gap=1)  # notches on the inner faces
    perforate(lv, m + 5, mtop + 1, proof - 6, solid=2, gap=1)
    lv.rect(m + 4, proof - 13, m + 4, proof - 13, CITY)  # a balcony
    lv.wp(m + 3, proof - 3, m + 4, proof - 1, ground=True, label="between the minarets")
    lv.wp(m + 4, proof - 14, ground=True, label="minaret balcony")
    lv.coin(m + 2, proof - 8)
    lv.coin(m + 2, proof - 18)
    lv.rect(m + 4, mtop - 1, m + 7, mtop - 1, CITY)  # the east minaret's gallery
    lv.rect(m - 2, mtop - 1, m + 1, mtop - 1, CITY)  # and the west one's
    lv.rect(m + 5, mtop - 3, m + 6, mtop - 2, CITY)  # its cupola
    lv.rect(m - 1, mtop - 3, m, mtop - 2, CITY)
    lv.wp(m - 2, mtop - 2, m + 7, mtop - 2, label="minaret tops")
    lv.flag(m + 7, mtop - 2)
    lv.wp(m + 7, mtop - 2, label="flag")
    lv.big_decor(p1 - 2, proof - 1, 2)
    return lv
