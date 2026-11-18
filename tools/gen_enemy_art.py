"""Pixel art and animations for the enemy kinds (scripts/enemy_kinds.py).

The gunner keeps the original red ninja (entities/enemy/idle, run). Every
other kind is its own character with its own animations, drawn here from
hand-made pixel grids and per-frame poses:

    patrol   amber ashigaru: wide straw hat, lacquered armor, upright spear,
             banner on its back.
             idle   banner flutters, glances at the viewer, blinks, taps
                    the spear on the ground (a puff of dust)
             run    an 8-step march, spear swaying forward on each stride,
                    banner snapping in the wind
    turret   steel sentry automaton on treads: dome head, one visor lens,
             antenna beacon, hazard stripe, gun mount.
             idle   the dim lens sweeps the visor, antenna wobbles, beacon
                    blinks, a vent puffs steam now and then
             alert  (player in sight) lens locked on and charging up from
                    dull to white-hot, stripe lights chasing, beacon racing
             shoot  recoil, lens flash, steam bursting from both vents
             run    treads rolling
    chaser   purple oni: horns, wild mane, tiger-skin loincloth, claws.
             idle   asleep: slow deep breaths, snoring mouth, a "z" rising
             alert  (awake but held up) glowing eyes flickering, snarling,
                    claws flexing, steam snorting from its nose, mane
                    bristling
             run    a hunched sprint: claws reaching in turn, mane flowing,
                    jaws open
    jumper   green frog ninja: bulging eyes, red headband, pale belly.
             idle   timed to its 50 frames on the ground: landing squash,
                    throat puffing, a blink, a tongue flick, then a crouch
                    winding up the next hop
             run    (in the air) one hop, 52 frames: launch stretch, legs
                    trailing, tucked at the top, legs reaching for the
                    landing; played once, holding the landing pose on a
                    longer fall
    thrower  teal hooded ninja: masked face, headband tails, shuriken sash.
             idle   twirls a star in its hand, tails drifting, blinks
             run    paces with the arm raised (Enemy.render puts the star in
                    that hand), tails streaming, sash end flapping
             shoot  the throw: release, follow-through, recover (its 24
                    frames of THROW_PAUSE)

Frames are 14x18 like the original, facing right, the 8x15 hitbox at
(3, 3) (Enemy anim_offset), feet on the bottom row. Enemy.update picks
run (moving), shoot (just fired), alert (awake) or idle; a kind without one
of them falls back to its idle. game.py loads them with these timings:

    idle  img_dur 6     run   img_dur 4 (jumper: once, no loop)
    alert img_dur 6     shoot img_dur 6, once

Each kind's spawner tile (tiles/spawners/<variant>.png, 6x15, for the
editor) is the hitbox column of its first idle frame.

Pure black (0, 0, 0) is the transparency colorkey (AssetManager).

Usage:
    python tools/gen_enemy_art.py [--preview /path/to/montage.png]
"""

from __future__ import annotations

import argparse
import os

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(REPO, "data", "images")
ENEMY_DIR = os.path.join(IMG_DIR, "entities", "enemy")

W, H = 14, 18
CLEAR = (0, 0, 0)

# Shared colors (the player's / original enemy's palette)
INK = (20, 16, 32)
NAVY = (38, 36, 58)
WHITE = (219, 224, 231)
SILVER = (163, 172, 190)
RED = (196, 44, 54)
DARK_RED = (120, 31, 44)
STEAM = (196, 200, 214)
STEAM_FAINT = (128, 134, 152)

SPAWNER_VARIANT = {"patrol": 2, "turret": 3, "chaser": 4, "jumper": 5, "thrower": 6}

# Idle: the original enemy's breathing rhythm (frames 5-6 and 12-13 dip)
IDLE_BOB = [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0]


def blank() -> Image.Image:
    return Image.new("RGB", (W, H), CLEAR)


def stamp(img: Image.Image, grid: list[str], palette: dict, dx: int = 0, dy: int = 0) -> None:
    """Draw a character grid onto img; '.' and ' ' are transparent."""
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch in ". ":
                continue
            px, py = x + dx, y + dy
            if 0 <= px < W and 0 <= py < H:
                img.putpixel((px, py), palette[ch])


def put(img: Image.Image, points, color) -> None:
    for x, y in points:
        if 0 <= x < W and 0 <= y < H:
            img.putpixel((x, y), color)


# ------------------------------------------------------------ walk cycle
# Rows 14-17 of a two-legged walker facing right: n near leg, f far leg,
# N / F their feet. A: near leg in front; B: the far one.

WALK = {
    "stand": [
        "....ff.nn.....",
        "....ff.nn.....",
        "....ff.nn.....",
        "...FFF.NNN....",
    ],
    "a_contact": [
        "....ffnn......",
        "...ff..nn.....",
        "..ff....nn....",
        ".FF......NNN..",
    ],
    "a_down": [
        "....ffnn......",
        "...ff..nn.....",
        ".FFf...nn.....",
        "........NNN...",
    ],
    "a_pass": [
        "....fnnf......",
        ".....nnff.....",
        ".....nn.FF....",
        ".....NNN......",
    ],
    "a_up": [
        "....fnn.......",
        "....nnfff.....",
        "...nn....FF...",
        "..NN..........",
    ],
}
for _a, _b in (("a_contact", "b_contact"), ("a_down", "b_down"), ("a_pass", "b_pass"), ("a_up", "b_up")):
    WALK[_b] = [row.translate(str.maketrans("nfNF", "fnFN")) for row in WALK[_a]]
WALK_CYCLE = ["a_contact", "a_down", "a_pass", "a_up", "b_contact", "b_down", "b_pass", "b_up"]
WALK_BOB = [0, 1, 0, 0, 0, 1, 0, 0]


def walk_legs(img: Image.Image, pose: str, colors: dict, claws=None) -> None:
    """Legs of a walk pose in the kind's colors {n, f, N, F}; claws: a color
    for the front pixel of each foot."""
    grid = WALK[pose]
    stamp(img, grid, colors, dy=14)
    if claws:
        foot = grid[3]
        for x, ch in enumerate(foot):
            if ch in "NF" and (x + 1 >= len(foot) or foot[x + 1] != ch):
                put(img, [(x, 17)], claws)


# ---------------------------------------------------------------- patrol
# Amber ashigaru spearman: jingasa hat, lacquered do with lacing, spear in
# the front hand, sashimono banner on the back.

PATROL = {
    "H": (214, 140, 46),  # hat / armor amber
    "h": (128, 76, 30),  # amber shade
    "L": (244, 196, 112),  # amber light
    "k": (72, 40, 24),  # lacing, hat cord
    "f": WHITE,  # face
    "s": SILVER,  # face shade
    "b": (232, 228, 214),  # banner cloth
    "r": RED,  # banner emblem
}
PATROL_LEGS = {"n": NAVY, "f": (28, 24, 42), "N": (120, 84, 52), "F": (84, 56, 34)}
SHAFT = (146, 100, 60)
SHAFT_SHADE = (96, 62, 40)
POLE = (96, 62, 40)

PATROL_UPPER = [
    # 0123456789ABCD
    "..............",  # 0-3 banner, drawn per frame
    "..............",
    "..............",
    "..............",
    "....LHh.......",  # 4 hat
    "...LHHHHh.....",  # 5
    ".LHHHHHHHhh...",  # 6 brim
    ".hhhkkkhhh....",  # 7 brim underside
    "....sffff.....",  # 8 face (eye per frame)
    "....sfffs.....",  # 9
    "...hHHHHHH....",  # 10 pauldron, arm (hand per frame)
    "...hkkkkk.....",  # 11 lacing
    "...hHHHHH.....",  # 12
    "...kkkkkk.....",  # 13 belt
]
PATROL_SKIRT = ["...hHhHh......"]
# banner beside the pole (cols 0-1, rows 0-3), waving
BANNERS = [
    ["bb", "rb", "rr", "bb"],
    ["b.", "br", "rr", "bb"],
    ["bb", "rr", "rb", ".b"],
    [".b", "rb", "rr", "b."],
]


def draw_spear(img: Image.Image, top: int, tilt: int) -> None:
    """Leaf blade over a shaft in the front hand, butt on the ground; tilt
    leans the upper part one pixel forward."""
    x = 11
    for y in range(top + 4, H):
        sx = x + (tilt if y < top + 7 else 0)
        put(img, [(sx, y)], SHAFT if y < 15 else SHAFT_SHADE)
    bx = x + tilt
    put(img, [(bx, top), (bx - 1, top + 1), (bx + 1, top + 1), (bx - 1, top + 2), (bx + 1, top + 2)], WHITE)
    put(img, [(bx, top + 1), (bx, top + 2), (bx, top + 3)], SILVER)


def patrol_frame(legs, bob=0, banner=0, eye="fwd", tap=0, tilt=0, dust=False) -> Image.Image:
    img = blank()
    walk_legs(img, legs, PATROL_LEGS)
    stamp(img, PATROL_SKIRT, PATROL, dy=14 + bob)
    put(img, [(2, y + bob) for y in range(0, 10)], POLE)
    stamp(img, BANNERS[banner], PATROL, dy=bob)
    stamp(img, PATROL_UPPER, PATROL, dy=bob)
    if eye == "fwd":
        put(img, [(7, 8 + bob)], INK)
    elif eye == "viewer":  # glancing at the camera
        put(img, [(6, 8 + bob)], INK)
    else:  # blink
        put(img, [(6, 8 + bob), (7, 8 + bob)], SILVER)
    draw_spear(img, bob + tap, tilt)
    put(img, [(10, 10 + bob), (11, 10 + bob)], NAVY)  # hand on the shaft
    if dust:
        put(img, [(10, 17), (12, 17)], STEAM_FAINT)
        put(img, [(9, 16), (13, 16)], STEAM_FAINT)
    return img


def patrol() -> dict:
    idle = []
    for i, b in enumerate(IDLE_BOB):
        eye = "viewer" if 6 <= i <= 9 else "blink" if i == 3 else "fwd"
        tap = 1 if i in (12, 13) else 0  # the spear slides down and thumps the ground
        idle.append(patrol_frame("stand", b, [0, 1, 0, 3][(i // 2) % 4], eye, tap, 0, i in (13, 14)))
    run = []
    for i, leg in enumerate(WALK_CYCLE):
        tilt = 1 if leg.endswith(("contact", "down")) else 0
        run.append(patrol_frame(leg, WALK_BOB[i], (i + 1) % 4, "fwd", 0, tilt))
    return {"idle": idle, "run": run}


# ---------------------------------------------------------------- turret
# Steel sentry on treads: dome head, visor lens, antenna beacon, hazard
# stripe, gun mount on the front shoulder (the gun is Enemy.render's).

TURRET = {
    "S": (150, 160, 178),  # steel
    "s": (98, 106, 126),  # steel shade
    "L": (214, 220, 230),  # steel light
    "k": (52, 54, 72),  # dark plates
    "K": INK,
    "v": (60, 64, 82),  # visor glass
    "o": (70, 74, 96),  # tread
    "O": (120, 128, 146),  # tread wheel
}
ANTENNA = (98, 106, 126)
STRIPE = [(232, 176, 48), (52, 54, 72)]
STRIPE_LIT = (255, 226, 120)
# lens (body, core) by charge: dull, warm, red, hot, flash
LENS = [
    ((96, 38, 46), (130, 56, 58)),
    ((150, 40, 50), (200, 76, 70)),
    (RED, (255, 120, 96)),
    ((255, 84, 72), (255, 214, 190)),
    ((255, 220, 200), (255, 255, 240)),
]
BEACON_OFF = (70, 40, 46)
BEACON_ON = (255, 96, 80)

TURRET_UPPER = [
    # 0123456789ABCD
    "..............",  # 0-1 antenna, beacon per frame
    "..............",
    ".....LSSL.....",  # 2 dome
    "....LSSSSS....",  # 3
    "...LSSvvvvS...",  # 4 visor band
    "...SSvvvvvS...",  # 5
    "...sSSSSSSs...",  # 6
    "...kkkkkkkk...",  # 7 neck
    "..LSSSSSSSSk..",  # 8 shoulders
    "..........Skk.",  # 9 stripe per frame, mount
    "..SSSSSSSSkKk.",  # 10 gun mount (gun at row 10)
    "..sSLSLSLSskk.",  # 11 vents
    "..sssssssssk..",  # 12
    "..kkkkkkkkkk..",  # 13
]
TREADS = [
    "..oooooooooo..",
    ".oO.O.O.O.O.o.",
    ".o.O.O.O.O.Oo.",
    "..oooooooooo..",
]


def turret_frame(
    lens_x=8, charge=0, beacon=False, antenna=0, stripe=0, lit=False, recoil=0, treads=0, steam=()
) -> Image.Image:
    img = blank()
    rows = TREADS[:]
    if treads % 2:
        rows[1], rows[2] = rows[2], rows[1]
    stamp(img, rows, TURRET, dy=14)
    dx = -recoil
    stamp(img, TURRET_UPPER, TURRET, dx=dx)
    # antenna (wobbling tip) and beacon
    put(img, [(6 + dx, 1)], ANTENNA)
    put(img, [(6 + dx + antenna, 0)], BEACON_ON if beacon else BEACON_OFF)
    # hazard stripe across the chest, its lights chasing when lit
    for x in range(2, 10):
        c = STRIPE[(x + stripe) % 2]
        if lit and (x + stripe) % 4 == 0:
            c = STRIPE_LIT
        put(img, [(x + dx, 9)], c)
    # the lens: 2x2, a bright core on its front edge, glow on the glass
    body, core = LENS[charge]
    for x in (lens_x, lens_x + 1):
        put(img, [(x + dx, 4), (x + dx, 5)], body)
    put(img, [(lens_x + 1 + dx, 4)], core)
    if charge >= 2:
        put(img, [(lens_x + 2 + dx, 5)], (110, 50, 64))
    for x, y, c in steam:
        put(img, [(x, y)], c)
    return img


def turret() -> dict:
    sweep = [6, 6, 6, 7, 7, 8, 8, 8, 8, 8, 7, 7, 6, 6, 6, 6]
    wobble = [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, -1, -1, 0, 0]
    puff = {10: [(2, 7, STEAM)], 11: [(1, 6, STEAM)], 12: [(1, 5, STEAM_FAINT)], 13: [(0, 4, STEAM_FAINT)]}
    idle = [turret_frame(sweep[i], 0, i in (0, 1, 8, 9), wobble[i], 0, False, 0, 0, puff.get(i, ())) for i in range(16)]
    # alert: charges over the 12 frames between shots, then holds hot
    ramp = [1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3]
    alert = [turret_frame(8, ramp[i], i % 2 == 0, [0, 1, 0, -1][i % 4] if i >= 8 else 0, i, True) for i in range(16)]
    burst = [
        [(1, 7, STEAM), (0, 6, STEAM), (12, 6, STEAM)],
        [(1, 5, STEAM), (0, 4, STEAM_FAINT), (13, 5, STEAM), (12, 7, STEAM_FAINT)],
        [(0, 3, STEAM_FAINT), (13, 4, STEAM_FAINT)],
        [],
    ]
    shoot = [
        turret_frame(8, 4, True, -1, 0, True, 1, 0, burst[0]),
        turret_frame(8, 3, True, -1, 1, True, 1, 0, burst[1]),
        turret_frame(8, 2, False, 1, 2, False, 0, 0, burst[2]),
        turret_frame(8, 1, False, 0, 3, False, 0, 0, burst[3]),
    ]
    run = [turret_frame(8, 2, i % 2 == 0, 0, i, True, 0, i) for i in range(8)]
    return {"idle": idle, "alert": alert, "shoot": shoot, "run": run}


# ---------------------------------------------------------------- chaser
# Purple oni: bone horns, dark mane, glowing eyes, fangs, tiger-skin
# loincloth, clawed hands and feet. Hunched; leans forward when it runs.

CHASER = {
    "P": (150, 62, 196),  # skin
    "p": (96, 38, 132),  # skin shade
    "l": (196, 128, 232),  # skin light
    "M": (52, 24, 72),  # mane
    "m": (84, 34, 114),  # mane light
    "w": (236, 226, 196),  # horn / fang
    "W": (176, 160, 128),  # horn shade
    "t": (232, 160, 40),  # tiger cloth
    "T": INK,  # tiger stripe
}
CLAW = (236, 226, 196)
EYE_GLOW = (255, 214, 64)
EYE_HOT = (255, 246, 170)
EYE_DIM = (176, 120, 40)
Z = (226, 214, 246)
Z_FAINT = (150, 136, 176)
CHASER_LEGS = {"n": (150, 62, 196), "f": (96, 38, 132), "N": (150, 62, 196), "F": (96, 38, 132)}

CHASER_HEAD = [
    # 0123456789ABCD
    "...W.....w....",  # 0 horn tips
    "...Ww...ww....",  # 1
    "..MMWwmwwM....",  # 2
    ".MMmPPPPPPl...",  # 3
    ".MMPPPPPPPP...",  # 4 eye row
    "MMmPPPPPPPPP..",  # 5 snout
    ".MMpPPPPPPPP..",  # 6 mouth row
    "..MMpPPPPPp...",  # 7
]
CHASER_BODY = [
    # rows 8-13
    ".MMlPPPPPP....",  # 8 shoulders
    "..pPPPlPPP....",  # 9
    "..pPPPPPPp....",  # 10
    "..ptTttTttp...",  # 11 loincloth
    "...tTttTtt....",  # 12
    "....tTttT.....",  # 13
]
# near arm: (arm pixels, claw pixels) from the shoulder at (9, 9)
CHASER_ARMS = {
    "hang": ([(9, 9), (10, 10), (10, 11)], [(10, 12), (11, 12)]),
    "reach": ([(9, 9), (10, 9), (11, 9)], [(12, 9), (12, 10)]),
    "raise": ([(9, 9), (10, 8), (11, 8)], [(12, 7), (12, 8)]),
    "flex": ([(9, 9), (10, 9), (10, 8)], [(11, 7), (11, 8)]),
    "back": ([(8, 10), (8, 11)], [(8, 12)]),
}
# the far arm, seen behind the body
CHASER_FAR_ARMS = {
    "none": ([], []),
    "back": ([(2, 9), (1, 10)], [(0, 11), (1, 11)]),
    "fwd": ([(10, 10), (11, 10)], [(12, 11)]),
}


def chaser_frame(
    legs="stand",
    bob=0,
    eyes="closed",
    lean=0,
    mouth="shut",
    arm="hang",
    far="none",
    zs=(),
    snort=(),
    mane=0,
    walk_bob=0,
) -> Image.Image:
    img = blank()
    y0 = bob + walk_bob
    # far arm first: behind everything
    arm_px, claw_px = CHASER_FAR_ARMS[far]
    put(img, [(x + lean, y + y0) for x, y in arm_px], CHASER["p"])
    put(img, [(x + lean, y + y0) for x, y in claw_px], (176, 160, 128))
    walk_legs(img, legs, CHASER_LEGS, claws=CLAW)
    stamp(img, CHASER_BODY, CHASER, dx=lean, dy=8 + y0)
    stamp(img, CHASER_HEAD, CHASER, dx=lean, dy=y0)
    if mane:  # bristling / flowing back
        put(img, [(0, 3 + y0), (0, 7 + y0)] if mane == 1 else [(0, 4 + y0), (1, 8 + y0)], CHASER["M"])
    ex, ey = 8 + lean, 4 + y0
    if eyes in ("open", "hot"):
        put(img, [(ex, ey), (ex + 2, ey)], EYE_HOT if eyes == "hot" else EYE_GLOW)
        put(img, [(ex - 1, ey - 1), (ex + 1, ey - 1)], CHASER["p"])  # furrowed brow
    elif eyes == "half":
        put(img, [(ex, ey), (ex + 2, ey)], EYE_DIM)
    else:  # asleep
        put(img, [(ex, ey), (ex + 2, ey)], INK)
    my = 6 + y0
    if mouth == "snarl":  # jaws wide, fangs bared
        put(img, [(ex, my), (ex + 1, my), (ex + 2, my), (ex + 1, my + 1)], INK)
        put(img, [(ex, my + 1), (ex + 2, my + 1), (ex + 3, my)], CHASER["w"])
    elif mouth == "snore":  # slack, a little open
        put(img, [(ex + 1, my), (ex + 2, my), (ex + 2, my + 1)], INK)
    else:
        put(img, [(ex, my), (ex + 1, my), (ex + 2, my)], INK)
        put(img, [(ex + 2, my + 1)], CHASER["w"])  # a fang over the lip
    arm_px, claw_px = CHASER_ARMS[arm]
    put(img, [(x + lean, y + y0) for x, y in arm_px], CHASER["P"])
    put(img, [(x + lean, y + y0) for x, y in claw_px], CLAW)
    for x, y, c in zs:
        put(img, [(x, y)], c)
    for x, y, c in snort:
        put(img, [(x + lean, y + y0)], c)
    return img


def z_letter(x: int, y: int, color) -> list:
    return [(x, y, color), (x + 1, y, color), (x + 1, y + 1, color), (x, y + 2, color), (x + 1, y + 2, color)]


def chaser() -> dict:
    # idle: asleep, slow breath, snoring at the top of it, a z drifting up
    breath = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0]
    zpath = {5: (11, 2, Z_FAINT), 6: (11, 2, Z), 7: (11, 2, Z), 8: (12, 1, Z), 9: (12, 1, Z), 10: (12, 0, Z_FAINT)}
    idle = []
    for i, b in enumerate(breath):
        zs = z_letter(*zpath[i]) if i in zpath else ()
        idle.append(chaser_frame("stand", b, "closed", 0, "snore" if 5 <= i <= 10 else "shut", zs=zs))
    # alert: awake, held up (a wall or an edge between it and the player)
    alert = []
    for i in range(16):
        snort = [(12, 5, STEAM)] if i in (2, 3) else [(13, 4, STEAM_FAINT)] if i == 4 else []
        alert.append(
            chaser_frame(
                "stand",
                IDLE_BOB[i],
                "hot" if i % 4 == 0 else "half" if i == 9 else "open",
                1 if i % 8 < 4 else 0,
                "snarl" if i % 4 < 2 else "shut",
                "flex" if i % 4 < 2 else "raise",
                "none",
                snort=snort,
                mane=1 if i % 2 else 2,
            )
        )
    run = []
    for i, leg in enumerate(WALK_CYCLE):
        front = leg.startswith("a")  # near leg forward: far arm reaches, near arm back
        run.append(
            chaser_frame(
                leg,
                0,
                "hot" if i % 2 else "open",
                1,
                "snarl",
                "back" if front else "reach",
                "fwd" if front else "back",
                mane=1 + i % 2,
                walk_bob=WALK_BOB[i],
            )
        )
    return {"idle": idle, "alert": alert, "run": run}


# ---------------------------------------------------------------- jumper
# Green frog ninja: big eyes on top, red headband with tails, wide mouth,
# pale belly, strong hind legs.

JUMPER = {
    "G": (70, 168, 78),  # skin
    "g": (34, 96, 46),  # shade
    "L": (140, 214, 120),  # light
    "b": (214, 230, 170),  # belly
    "B": (168, 196, 128),  # belly shade
    "E": WHITE,  # eyeball
    "e": INK,  # pupil, mouth
    "r": RED,  # headband
    "R": DARK_RED,
    "s": (40, 120, 60),  # spots
}
TONGUE = (232, 112, 132)

JUMPER_HEAD = [
    # 0123456789ABCD
    "......LGG.LGG.",  # +0 eye bumps
    ".....GEEGGEEe.",  # +1 eyes (pupil front)
    "....RrrrrrrrR.",  # +2 headband
    "...gGGGGGGGGG.",  # +3
    "...GGsGGGeeeee",  # +4 mouth
    "...gGGGGbbbbb.",  # +5 throat
]
JUMPER_BODY = {
    "sit": [
        "..gGGGbbbbbG..",  # 9
        "..gGGbbbbbbG..",  # 10
        ".gGsGbbbbbbGL.",  # 11 arm
        ".gGGGbbbbBGGG.",  # 12 hand
        "LgGGGGBbbBgG..",  # 13 knee
        "LgggGGGBBGg...",  # 14 haunch
        "..gGGgGGGGG...",  # 15
        ".GGGG..GGGGG..",  # 16 feet
        "gg.gg..gg.gG..",  # 17 toes
    ],
    "crouch": [
        "..gGGGbbbbbG..",  # 9
        ".gGGGbbbbbbGL.",  # 10
        "LgGsGbbbbbbGG.",  # 11
        "LgGGGGbbbBGGGG",  # 12 hands down
        "LggGGGGBBBgGG.",  # 13
        "LggggGGGGGg...",  # 14
        ".gGGGgGGGGGG..",  # 15
        "GGGGG..GGGGGG.",  # 16 feet spread
        "gg.gg..gg..gG.",  # 17
    ],
    "stretch": [
        "..gGGGbbbbbG..",  # 9
        ".LgGGbbbbbbG..",  # 10 arms swept back
        "L.gGGbbbbbbG..",  # 11
        "...gGGbbbBGG..",  # 12
        "....gGGBBGg...",  # 13
        "....gGG.gG....",  # 14 legs straight down
        "....gG..gG....",  # 15
        "...gG....gG...",  # 16
        "..gg......gg..",  # 17 toes pointed
    ],
    "trail": [
        "..gGGGbbbbbG..",  # 9
        "..gGGbbbbbbGL.",  # 10 arm up
        "..gGsbbbbbbGL.",  # 11
        "..gGGGbbbBGG..",  # 12
        "...gGGGBBGg...",  # 13
        "...gGGGGGgg...",  # 14
        "..gGG...gGG...",  # 15 legs kicked back
        ".gGG.....gG...",  # 16
        "gG........g...",  # 17
    ],
    "tuck": [
        "..gGGGbbbbbGL.",  # 9 arms out
        ".LgGGbbbbbbGL.",  # 10
        "..gGsbbbbbbG..",  # 11
        "..gGGGbbbBGG..",  # 12
        "..LgGGGBBGGg..",  # 13 knees drawn up
        "...ggGGGGgg...",  # 14
        "....gg..gg....",  # 15
        "..............",  # 16
        "..............",  # 17
    ],
    "reach": [
        ".LgGGGbbbbbG..",  # 9 arms up behind
        "L.gGGbbbbbbG..",  # 10
        "..gGsbbbbbbG..",  # 11
        "..gGGGbbbBGG..",  # 12
        "...gGGGBBGGg..",  # 13
        "....gGG..gGG..",  # 14 legs reaching for the ground
        "....gG....gG..",  # 15
        "...gG......gG.",  # 16
        "..gg.......gg.",  # 17
    ],
}


def jumper_frame(pose="sit", dy=0, tails="flutter0", eyes="open", throat=0, tongue=False) -> Image.Image:
    """dy moves the head (squash and stretch); the body stays planted."""
    img = blank()
    stamp(img, JUMPER_BODY[pose], JUMPER, dy=9)
    hy = 3 + dy
    stamp(img, JUMPER_HEAD, JUMPER, dy=hy)
    ty = hy + 2  # headband row
    tail = {
        "flutter0": [(3, ty), (2, ty - 1), (1, ty - 1), (0, ty - 2)],
        "flutter1": [(3, ty), (2, ty), (1, ty + 1), (0, ty + 1)],
        "down": [(3, ty), (2, ty + 1), (2, ty + 2), (1, ty + 3)],  # rising: trailing below
        "up": [(3, ty), (2, ty - 1), (2, ty - 2), (1, ty - 3)],  # falling: streaming above
    }[tails]
    put(img, tail, JUMPER["r"])
    put(img, [tail[2]], JUMPER["R"])
    if eyes == "blink":
        put(img, [(6, hy + 1), (7, hy + 1), (10, hy + 1), (11, hy + 1), (12, hy + 1)], JUMPER["g"])
    elif eyes == "squint":  # lids half down (landing, winding up)
        put(img, [(6, hy), (7, hy), (10, hy), (11, hy)], JUMPER["g"])
    elif eyes == "wide":  # pupil small, white all round
        put(img, [(12, hy + 1)], WHITE)
        put(img, [(11, hy + 1)], INK)
    if throat:  # puffed throat sac
        put(img, [(9, hy + 6), (10, hy + 6), (11, hy + 6), (12, hy + 6)], JUMPER["b"])
        put(img, [(12, hy + 5)], JUMPER["B"])
        if throat > 1:
            put(img, [(13, hy + 6), (12, hy + 7), (13, hy + 5)], JUMPER["b"])
    if tongue:
        put(img, [(13, hy + 4), (13, hy + 5)], TONGUE)
    return img


def jumper() -> dict:
    # idle: one ground stay, 50 frames (8 frames of 6) from landing to the next hop
    idle = [
        jumper_frame("crouch", 2, "up", "squint"),  # landing squash
        jumper_frame("sit", 1, "flutter1"),
        jumper_frame("sit", 0, "flutter0", throat=1),
        jumper_frame("sit", 0, "flutter0", throat=2),
        jumper_frame("sit", 0, "flutter1", "blink"),
        jumper_frame("sit", 0, "flutter1", tongue=True),
        jumper_frame("crouch", 1, "flutter0"),  # winding up
        jumper_frame("crouch", 2, "flutter0", "squint"),
        jumper_frame("crouch", 2, "flutter1", "squint"),
    ]
    # run: one hop, 52 frames in the air (13 frames of 4), played once
    run = [
        jumper_frame("stretch", -1, "down", "wide"),
        jumper_frame("stretch", -1, "down", "wide"),
        jumper_frame("trail", 0, "down"),
        jumper_frame("trail", 0, "down"),
        jumper_frame("trail", 0, "flutter1"),
        jumper_frame("tuck", 0, "flutter0"),
        jumper_frame("tuck", 0, "flutter1"),
        jumper_frame("tuck", 0, "up"),
        jumper_frame("reach", 0, "up"),
        jumper_frame("reach", 0, "up"),
        jumper_frame("reach", 0, "up", "wide"),
        jumper_frame("stretch", 0, "up", "wide"),
        jumper_frame("stretch", 0, "up", "wide"),
    ]
    return {"idle": idle, "run": run}


# ---------------------------------------------------------------- thrower
# Teal hooded ninja: hood and mask (only the eyes show), long headband
# tails, shuriken on the sash.

THROWER = {
    "T": (44, 170, 180),  # gi
    "t": (22, 96, 108),  # gi shade
    "L": (120, 220, 222),  # gi light
    "h": (24, 56, 70),  # hood
    "H": (36, 82, 98),  # hood light
    "m": (16, 36, 48),  # mask
    "f": WHITE,  # eye skin
    "r": RED,  # headband
    "k": INK,  # sash
    "s": SILVER,  # shuriken on the sash
}
THROWER_LEGS = {"n": NAVY, "f": INK, "N": (28, 24, 42), "F": INK}

THROWER_HEAD = [
    # 0123456789ABCD
    "..............",  # 0
    "..............",  # 1
    ".....hHHH.....",  # 2
    "....hhHHHH....",  # 3
    "...rrrrrrrr...",  # 4 headband
    "....hhfffh....",  # 5 eye slit (eye per frame)
    "....hmmmmm....",  # 6 mask
    ".....hmmm.....",  # 7
]
THROWER_BODY = [
    # rows 8-13
    "....tTTLT.....",  # 8
    "...tTTTTLT....",  # 9
    "...tTTTTTT....",  # 10
    "...kkskkkk....",  # 11 sash with a shuriken
    "...tTTTTTt....",  # 12
    "...tTT.TTt....",  # 13
]
# front arm: (sleeve pixels, glove pixels)
THROWER_ARMS = {
    "side": ([(9, 9), (10, 10), (10, 11)], [(11, 12)]),
    "raised": ([(9, 9), (10, 8), (11, 7), (11, 6)], [(12, 5), (12, 6)]),
    "release": ([(9, 9), (10, 8), (11, 8), (12, 7)], [(13, 6), (13, 7)]),
    "forward": ([(9, 9), (10, 9), (11, 9), (12, 9)], [(13, 9), (13, 10)]),
    "low": ([(9, 10), (10, 11), (11, 12)], [(12, 12), (12, 13)]),
    "half": ([(9, 9), (10, 9), (10, 10)], [(11, 11)]),
}
TAILS = [
    [(2, 4), (1, 5), (0, 5), (1, 6), (0, 7)],  # hanging
    [(2, 4), (1, 4), (0, 5), (1, 5), (0, 6)],  # lifting
    [(2, 4), (1, 4), (0, 4), (1, 5), (0, 5)],  # streaming
]
STAR_TWIRL = [
    [(12, 11), (11, 12), (12, 12), (13, 12), (12, 13)],  # +
    [(11, 11), (13, 11), (12, 12), (11, 13), (13, 13)],  # x
]


def thrower_frame(
    legs="stand", bob=0, tails=0, arm="side", eye="fwd", lean=0, star=None, sash=0, streak=False
) -> Image.Image:
    img = blank()
    # the sash end hangs (or flaps) behind the back
    put(img, [(2, 11 + bob), (2, 12 + bob)] if sash == 0 else [(2, 11 + bob), (1, 11 + bob)], INK)
    walk_legs(img, legs, THROWER_LEGS)
    stamp(img, THROWER_BODY, THROWER, dx=lean, dy=8 + bob)
    stamp(img, THROWER_HEAD, THROWER, dx=lean, dy=bob)
    tail = TAILS[tails]
    put(img, [(x + lean, y + bob) for x, y in tail], THROWER["r"])
    put(img, [(tail[2][0] + lean, tail[2][1] + bob)], DARK_RED)
    if eye == "fwd":
        put(img, [(8 + lean, 5 + bob)], INK)
    elif eye == "viewer":
        put(img, [(7 + lean, 5 + bob)], INK)
    else:  # blink
        put(img, [(6 + lean, 5 + bob), (7 + lean, 5 + bob), (8 + lean, 5 + bob)], THROWER["h"])
    sleeve, glove = THROWER_ARMS[arm]
    put(img, [(x + lean, y + bob) for x, y in sleeve], THROWER["T"])
    put(img, [(x + lean, y + bob) for x, y in glove], NAVY)
    if star is not None:  # a shuriken spinning on a finger
        pts = STAR_TWIRL[star]
        put(img, [(x + lean, y + bob) for x, y in pts], SILVER)
        put(img, [(pts[2][0] + lean, pts[2][1] + bob)], WHITE)
    if streak:  # the star just left the hand
        put(img, [(12 + lean, 4 + bob), (13 + lean, 4 + bob)], WHITE)
        put(img, [(11 + lean, 5 + bob)], STEAM_FAINT)
    return img


def thrower() -> dict:
    idle = []
    for i, b in enumerate(IDLE_BOB):
        eye = "blink" if i == 11 else "viewer" if 4 <= i <= 6 else "fwd"
        idle.append(thrower_frame("stand", b, [0, 0, 1, 1][(i // 2) % 4], "side", eye, 0, i % 2, (i // 4) % 2))
    run = [
        thrower_frame(leg, WALK_BOB[i], 1 + i % 2, "raised", "fwd", 0, None, i % 2) for i, leg in enumerate(WALK_CYCLE)
    ]
    # the throw: 24 frames standing (THROW_PAUSE), 4 frames of 6, played once
    shoot = [
        thrower_frame("a_contact", 0, 2, "release", "fwd", 1, None, 1, True),
        thrower_frame("a_contact", 1, 2, "forward", "fwd", 1, None, 1),
        thrower_frame("a_down", 1, 1, "low", "fwd", 1, None, 0),
        thrower_frame("stand", 0, 0, "half", "fwd", 0, None, 0),
    ]
    return {"idle": idle, "run": run, "shoot": shoot}


KINDS = {"patrol": patrol, "turret": turret, "chaser": chaser, "jumper": jumper, "thrower": thrower}
ACTIONS = ("idle", "run", "alert", "shoot")


def frame_name(action: str, i: int) -> str:
    # the original enemy's naming: idle two digits, run one
    return f"{i}.png" if action == "run" else f"{i:02d}.png"


def write_all() -> list[str]:
    written = []
    for kind, make in KINDS.items():
        anims = make()
        for action in ACTIONS:
            folder = os.path.join(ENEMY_DIR, kind, action)
            if os.path.isdir(folder):  # no stale frames from an older set
                for name in os.listdir(folder):
                    if name.endswith(".png"):
                        os.remove(os.path.join(folder, name))
                if action not in anims:
                    os.rmdir(folder)
            if action not in anims:
                continue
            os.makedirs(folder, exist_ok=True)
            for i, img in enumerate(anims[action]):
                path = os.path.join(folder, frame_name(action, i))
                img.save(path)
                written.append(path)
        spawner = anims["idle"][0].crop((4, 3, 10, 18))
        out = os.path.join(IMG_DIR, "tiles", "spawners", f"{SPAWNER_VARIANT[kind]}.png")
        spawner.save(out)
        written.append(out)
    return written


def make_preview(path: str, scale: int = 6) -> None:
    """Every kind's animations, one row per kind and action (gunner first),
    on a mid-gray."""
    gunner = {}
    for a in ("idle", "run"):
        folder = os.path.join(ENEMY_DIR, a)
        gunner[a] = [Image.open(os.path.join(folder, n)).convert("RGB") for n in sorted(os.listdir(folder))]
    sets = [gunner] + [make() for make in KINDS.values()]
    rows = [anims[a] for anims in sets for a in ACTIONS if a in anims]
    cols = max(len(r) for r in rows)
    cw, ch = (W + 2) * scale, (H + 2) * scale
    sheet = Image.new("RGB", (cols * cw, len(rows) * ch), (92, 96, 112))
    for r, frames in enumerate(rows):
        for i, frame in enumerate(frames):
            f = frame.convert("RGBA")
            f.putdata([(0, 0, 0, 0) if p[:3] == CLEAR else p for p in f.getdata()])
            big = f.resize((W * scale, H * scale), Image.NEAREST)
            sheet.paste(big, (i * cw, r * ch), big)
    sheet.save(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preview", default=None, help="write a montage of all frames here instead")
    args = ap.parse_args()
    if args.preview:
        make_preview(args.preview)
        print(f"preview saved: {args.preview}")
        return
    print(f"wrote {len(write_all())} images")


if __name__ == "__main__":
    main()
