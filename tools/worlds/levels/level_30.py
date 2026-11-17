"""Level 30 - The Colossus (city stone, desert sky). Finale of the desert.

At the end of the caravan road a king sits on his throne, carved out of a
mountain, and looks west over the sand he once ruled. The way to his crown
leads over him. Across his forecourt and the cleft before his feet, over
his toes on to the foot, and in under the scepter's foot into the gap
between the scepter and his shin: wall to wall up to the knee, which hangs
out over the gap, so the climb has to cross to the scepter's side to
squeeze up past it. On the knee the first banner. Along the thigh, over his
fingers on to the fist, under the scepter where he holds it loosely, and up
the long gap between the scepter and his upper arm to the shoulder, with
the second banner. Then in under the lappet of his headdress, up between
it and his cheek to where the crown's band has broken away, through the
break and up the crown's spikes to the flag on the highest of them.
"""

from tools.worlds.builder import Level
from tools.worlds.kits.desert import CITY, ROCK

BOTTOM = 160
G = 150  # the desert floor


def rests(lv: Level, x0: int, x1: int, spec, label: str):
    """One-tile rest ledges in a gap x0..x1: (side, row), side -1 the west wall."""
    for side, row in spec:
        rx = x0 if side < 0 else x1
        lv.rect(rx, row, rx, row, CITY)
        lv.wp(rx, row - 1, ground=True, label=f"{label} rest {row}")
        lv.coin((x0 + x1) // 2, row - 3)


def build() -> Level:
    lv = Level(30, CITY, background="background-desert.png")

    # --- The forecourt ----------------------------------------------------------------------------
    lv.rect(-64, G, 120, BOTTOM, ROCK)
    lv.spawn(-60, G - 1)
    lv.big_decor(-56, G - 1, 2)
    lv.decor(-52, G - 1, 3)
    for i, (x, h, w) in enumerate(((-48, 2, 2), (-40, 4, 3), (-30, 2, 2), (-22, 5, 2), (-12, 3, 3))):
        lv.rect(x, G - h, x + w - 1, G - 1, CITY)  # toppled statues and broken walls
        lv.wp(x, G - h - 1, x + w - 1, G - h - 1, ground=True, label=f"forecourt {i}")
        lv.coin(x + w // 2, G - h - 3)
    lv.carve(-36, G, -33, BOTTOM)  # a crack in the court
    lv.carve(-18, G, -15, BOTTOM)
    lv.enemy(-26, G - 1)
    lv.enemy(-4, G - 1)
    lv.decor(4, G - 1, 3)
    lv.wp(8, G - 1, 12, G - 1, ground=True, label="before the cleft")

    # --- The cleft, the toes, the foot -------------------------------------------------------------------
    lv.carve(13, G, 16, BOTTOM)
    lv.rect(17, 148, 18, G - 1)
    lv.rect(19, 146, 20, G - 1)
    lv.rect(21, 144, 36, G - 1)
    lv.wp(19, 145, 20, 145, ground=True, label="toes")

    # --- The shin, the scepter's foot and the knee --------------------------------------------------------
    lv.rect(27, 106, 33, 143)  # the shin
    lv.rect(21, 92, 21, 140)  # the scepter, its foot on the king's foot (a gap under it)
    lv.rect(20, 90, 22, 91)  # its head
    lv.wp(22, 141, 26, 143, label="under the scepter")
    rests(lv, 22, 26, [(1, 138), (-1, 132), (1, 126), (-1, 120), (1, 114)], "shin")
    lv.rect(25, 98, 35, 105)  # the knee, out over the gap
    rests(lv, 22, 24, [(-1, 104)], "knee")
    lv.wp(26, 97, 29, 97, ground=True, label="the knee")
    lv.checkpoint(30, 97)

    # --- The thigh, the fingers, the fist --------------------------------------------------------------------
    lv.rect(34, 98, 92, BOTTOM - 10)  # thigh, seat and throne
    lv.carve(34, 109, 45, 143)  # the shadow under the thigh, behind the calf
    lv.rect(34, 120, 35, 143)  # the calf
    lv.rect(36, 128, 36, 143)
    lv.decor(40, 143, 3)
    lv.big_decor(43, 143, 2)
    lv.enemy(36, 97)
    lv.coins(31, 95, 38, 2)
    lv.rect(40, 96, 41, 97)  # fingers
    lv.rect(42, 94, 43, 97)
    lv.wp(42, 93, 43, 93, ground=True, label="fingers")
    lv.rect(44, 92, 50, 97)  # the fist
    lv.wp(44, 91, 47, 91, ground=True, label="the fist")
    lv.rect(49, 30, 50, 88)  # the scepter he holds (loosely: a gap over the fist)
    lv.rect(47, 26, 52, 29)  # its crest
    lv.rect(48, 25, 51, 25)

    # --- The arm: up between the scepter and the upper arm ------------------------------------------------------
    lv.rect(51, 93, 62, 97)  # the forearm on the thigh
    lv.rect(55, 63, 59, 92)  # the upper arm
    lv.wp(51, 92, 54, 92, ground=True, label="forearm")
    rests(lv, 51, 54, [(1, 87), (-1, 81), (1, 75), (-1, 69), (1, 65)], "arm")
    lv.rect(55, 62, 92, 97)  # shoulder and chest
    lv.wp(55, 61, 58, 61, ground=True, label="the shoulder")
    lv.checkpoint(57, 61)
    lv.enemy(61, 61)
    lv.coins(56, 59, 62, 2)

    # --- The head: up between the lappet and the cheek, through the broken crown -----------------------------------
    lv.rect(70, 34, 86, 61)  # the head
    lv.carve(72, 42, 73, 43)  # an eye
    lv.rect(69, 45, 69, 48)  # the nose
    lv.rect(64, 34, 65, 58)  # the lappet of the headdress
    lv.wp(66, 59, 69, 61, label="under the lappet")
    rests(lv, 66, 68, [(1, 54), (-1, 48), (1, 42), (-1, 37)], "cheek")
    lv.rect(62, 30, 88, 33)  # the crown's band
    lv.carve(66, 30, 69, 33)  # broken away
    lv.wp(70, 29, 72, 29, ground=True, label="the crown")
    for i, (x, top) in enumerate(((74, 27), (78, 25), (82, 23))):
        lv.rect(x, top, x + 1, 29)
        lv.wp(x, top - 1, x + 1, top - 1, ground=True, label=f"spike {i}")
        lv.coin(x, top - 3)
    lv.rect(62, 27, 63, 29)  # the front spike
    lv.rect(86, 26, 87, 29)
    lv.rect(86, 34, 94, G - 1)  # the throne's back
    lv.flag(82, 22)
    lv.wp(82, 22, label="flag")
    return lv
