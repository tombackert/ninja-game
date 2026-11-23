"""Hand-designed player skins, drawn on top of the default animation.

Every skin keeps the default ninja's motion (same frame counts and poses for
idle/run/jump/slide/wall_slide/swim) but gets its own silhouette, materials
and animated details: helmets, horns, hats, hoods, capes, tails, banners,
glowing eyes, sparkles, flames.

How it works: each default frame is read as a grid of its five colors and
split into body parts (head top, headband, mask/eye row, face, torso, belt,
legs, trailing scarf). Anchors found per frame (headband row, head span,
belt row) let a design restyle each part and add pieces relative to the
head or torso, so the additions follow the pose in every frame.

Frames are 20x22: the original 14x18 box sits at (3, 4), leaving room for
horns, crests, capes and hats. The renderer centers wider frames on the
14-wide box and aligns them at its bottom.

The `default` skin is the template and is not touched. Its swim cycle
comes from tools/gen_water_world.py, so after changing that, run this
again to carry the change over to every skin.

Usage:
    python tools/gen_skins.py [--out DIR] [--only NAME ...]
"""

from __future__ import annotations

import argparse
import os
import zlib

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_DIR = os.path.join(REPO, "data", "images", "entities", "player")

ACTIONS = ["idle", "run", "jump", "slide", "wall_slide", "swim"]
W, H = 20, 22
PAD_X, PAD_TOP = 3, 4

_DEFAULT = {
    (38, 36, 58): "B",
    (20, 16, 32): "S",
    (219, 224, 231): "H",
    (163, 172, 190): "A",
    (196, 44, 54): "R",
}

# How hard the wind pulls trailing cloth per animation (capes, hair, tails)
DRAG = {"idle": 0, "run": 2, "jump": 1, "slide": 3, "wall_slide": 0, "swim": 2}


def nz(*a) -> int:
    return zlib.crc32(repr(a).encode()) & 0xFFFF


def load_grid(path: str) -> list[str]:
    im = Image.open(path).convert("RGBA")
    rows = []
    for y in range(im.height):
        row = ""
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            row += _DEFAULT.get((r, g, b), ".") if a else "."
        rows.append(row)
    return rows


class Frame:
    """One default frame split into body parts, with its anchors."""

    def __init__(self, grid: list[str], anim: str, i: int, n: int):
        self.grid, self.anim, self.i, self.n = grid, anim, i, n
        self.drag = DRAG[anim]
        self.hb = next(y for y, r in enumerate(grid) if r.count("R") >= 5)
        self.x1 = max(x for x, c in enumerate(grid[self.hb]) if c == "R")
        self.x0 = self.x1 - 5
        self.belt = next(
            y
            for y in range(self.hb + 4, len(grid))
            if any(grid[y][x] == "A" and grid[y][x + 1] == "H" for x in range(len(grid[y]) - 1))
        )
        self.labels: dict = {}
        for y, row in enumerate(grid):
            for x, c in enumerate(row):
                if c == ".":
                    continue
                self.labels[(x, y)] = self._label(x, y, c)
        self.eye = next((p for p, lab in self.labels.items() if lab == "eye"), (self.x0 + 4, self.hb + 1))
        self.torso_top = self.hb + 4
        legs = [p for p, lab in self.labels.items() if lab in ("legf", "legb")]
        self.bottom = max(y for _, y in legs) if legs else self.belt + 3
        # Lowest pixel of each leg per column: the feet
        low: dict = {}
        for (x, y), lab in self.labels.items():
            if lab in ("legf", "legb") and y > low.get((x, lab), -1):
                low[(x, lab)] = y
        self.feet = {(x, y) for (x, lab), y in low.items() if y >= self.bottom - 1}

    def _label(self, x, y, c):
        hb = self.hb
        if c == "R":
            return "band" if y == hb and self.x0 <= x <= self.x1 else "tail"
        if y < hb:
            return "top"
        if y == hb + 1:
            return {"A": "mask", "S": "eye"}.get(c, "face")
        if y <= hb + 3:
            return "face"
        if y < self.belt:
            if c == "A":
                return "collar" if y == hb + 4 else "strap"
            return "arm" if c == "S" else "torso"
        if y == self.belt:
            return {"H": "belt", "A": "buckle", "S": "arm"}.get(c, "torso")
        return "legb" if c == "S" else "legf"

    # -- geometry helpers --------------------------------------------------
    def head(self, hx, hy):
        return (self.x0 + hx, self.hb + hy)

    def span(self, y, parts=("torso", "arm", "strap", "collar", "belt", "buckle")):
        xs = [x for (x, yy), lab in self.labels.items() if yy == y and lab in parts]
        return (min(xs), max(xs)) if xs else None

    def pixels(self, *parts):
        return [(p, lab) for p, lab in sorted(self.labels.items()) if lab in parts]

    @property
    def upright(self):
        return self.anim not in ("slide",)


class Canvas:
    def __init__(self):
        self.back: dict = {}
        self.body: dict = {}
        self.front: dict = {}

    def image(self) -> Image.Image:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for layer in (self.back, self.body, self.front):
            for (x, y), c in layer.items():
                px, py = x + PAD_X, y + PAD_TOP
                if 0 <= px < W and 0 <= py < H and c is not None:
                    assert c != (0, 0, 0), "pure black is the transparency colorkey"
                    im.putpixel((px, py), tuple(c) + (255,))
        return im


def stamp(layer: dict, f: Frame, rows: list[str], origin: tuple, pal: dict, hx=0, hy=0):
    """Draw `rows` with the char at `origin` (col, row) placed on head (hx, hy)."""
    ox, oy = origin
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == "." or ch == " ":
                continue
            p = f.head(hx + c - ox, hy + r - oy)
            if ch == "_":
                layer.pop(p, None)
            else:
                layer[p] = pal[ch]


def stamp_at(layer: dict, ax: int, ay: int, rows: list[str], origin: tuple, pal: dict):
    """Like stamp, but anchored at a template pixel instead of the head."""
    ox, oy = origin
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in ". ":
                continue
            layer[(ax + c - ox, ay + r - oy)] = pal[ch]


def base(cv: Canvas, f: Frame, pal: dict, skip=()):
    """Recolor the default body by part. pal: part -> color.

    Extra keys: torso_hi / torso_lo (front / back edge of each torso row),
    foot (lowest pixel of each leg column).
    """
    for (x, y), lab in f.labels.items():
        if lab in skip:
            continue
        key = lab
        if lab in ("legf", "legb") and (x, y) in f.feet and "foot" in pal:
            key = "foot"
        elif lab == "torso":
            sp = f.span(y)
            if sp and x == sp[1] and "torso_hi" in pal:
                key = "torso_hi"
            elif sp and x == sp[0] and "torso_lo" in pal:
                key = "torso_lo"
        c = pal.get(key, pal.get(lab))
        if callable(c):
            c = c(x, y)
        if c is not None:
            cv.body[(x, y)] = c


def lerp(a, b, t):
    return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


# =============================================================================
# Designs
# =============================================================================
DESIGNS: dict = {}


def design(key):
    """Register a design; `key` is its folder under entities/player."""

    def deco(fn):
        DESIGNS[key] = fn
        return fn

    return deco


# --- 1. Homura: flame ninja ------------------------------------------------
@design("homura")
def homura(f: Frame) -> Canvas:
    cv = Canvas()
    crim, crim_hi, crim_lo = (176, 30, 38), (226, 66, 54), (104, 16, 26)
    dark = (30, 20, 26)
    gold = (236, 186, 64)
    base(
        cv,
        f,
        {
            "band": dark,
            "tail": dark,
            "mask": crim,
            "eye": (255, 226, 96),
            "face": crim_lo,
            "collar": (236, 222, 206),
            "strap": gold,
            "torso": crim,
            "torso_hi": crim_hi,
            "torso_lo": crim_lo,
            "arm": crim_lo,
            "belt": dark,
            "buckle": (255, 140, 40),
            "legf": crim,
            "legb": (92, 14, 24),
            "foot": dark,
        },
        skip=("top",),
    )
    # Gold plate on the headband
    cv.body[f.head(3, 0)] = gold
    cv.body[f.head(4, 0)] = (255, 232, 140)
    # Burning tail ends: the farthest tail pixels glow
    tails = sorted(p for p, lab in f.labels.items() if lab == "tail")
    for k, p in enumerate(tails[:2]):
        cv.body[p] = [(255, 150, 40), (220, 60, 30)][k]
    # Flame hair: columns of fire over the head, flickering per frame
    heights = [2, 4, 5, 4, 3, 2]
    fire = [(214, 48, 30), (246, 102, 32), (255, 150, 40), (255, 206, 74), (255, 240, 170)]
    lean = 0 if f.drag == 0 else 1
    for hx, hgt in enumerate(heights):
        hgt += (nz("homura", f.anim, f.i, hx) % 3) - 1
        hgt = max(1, hgt)
        for k in range(hgt):
            t = k / max(1, hgt - 1)
            col = fire[min(len(fire) - 1, int(t * (len(fire) - 1) + 0.5))]
            shift = -(k * lean) // 2
            cv.front[f.head(hx + shift, -1 - k)] = col
    # Embers drifting up in idle
    if f.anim == "idle":
        e = nz("ember", f.i // 3) % 6
        cv.front[f.head(e - 1, -7 - (f.i % 3))] = (255, 120, 40) if f.i % 3 < 2 else (170, 50, 30)
    return cv


# --- 2. Shogun: golden samurai -------------------------------------------
@design("shogun")
def shogun(f: Frame) -> Canvas:
    cv = Canvas()
    G, D, Y, Wt = (218, 166, 44), (150, 100, 22), (255, 226, 120), (255, 250, 220)
    K, k = (40, 30, 36), (76, 60, 66)
    red = (186, 34, 40)
    menpo = (184, 54, 46)

    def lamellar(x, y):
        return G if (y - f.torso_top) % 2 == 0 else D

    base(
        cv,
        f,
        {
            "mask": K,
            "eye": Wt,
            "face": menpo,
            "collar": G,
            "strap": red,
            "torso": lamellar,
            "arm": D,
            "belt": red,
            "buckle": Y,
            "legf": (58, 42, 70),
            "legb": (34, 24, 42),
            "foot": K,
        },
        skip=("top", "band", "tail"),
    )
    pal = {"G": G, "D": D, "Y": Y, "K": K, "k": k, "W": Wt, "r": red, "m": menpo}
    # Helmet: crescent crest, lacquered dome, gold rim, flared neck guard
    stamp(
        cv.front,
        f,
        [
            "..Y....Y.",
            "...G..G..",
            "....YY...",
            "..kKKKKk.",
            ".GGGGGGGG",
            "DK.......",
            "KD.......",
        ],
        (2, 4),
        pal,
    )
    cv.front[f.head(5, 2)] = Y  # gold moustache on the menpo
    # Shoulder plates (sode) one pixel wider than the torso
    for y in (f.torso_top + 1, f.torso_top + 2):
        sp = f.span(y)
        if sp and f.upright:
            cv.front[(sp[0] - 1, y)] = D if y % 2 else G
            cv.front[(sp[1] + 1, y)] = G if y % 2 else Y
    # Sashimono banner on the back
    if f.anim not in ("slide", "swim"):
        px = f.x0 - 2
        for y in range(f.hb - 6, f.torso_top + 2):
            cv.back[(px, y)] = K
        flutter = (f.i // 2) % 2 if f.drag else (f.i // 11) % 2
        for r in range(4):
            for c in range(3):
                x = px - 1 - c
                y = f.hb - 6 + r + (1 if c == 2 and r == 3 and flutter else 0)
                cv.back[(x, y)] = Wt if (c, r) not in ((1, 1), (1, 2)) else red
        cv.back[(px, f.hb - 7)] = Y
    # Gold shine sweeping over the armor in idle
    if f.anim == "idle" and f.i < 10:
        k_line = f.i * 2 - 2
        for p, c in list(cv.body.items()) + list(cv.front.items()):
            x, y = p
            if (x - f.x0) + (y - f.hb) - 4 in (k_line, k_line + 1) and c in (G, D, Y):
                (cv.front if p in cv.front else cv.body)[p] = Wt if c == Y else Y
    return cv


# --- 3. Cyber: chrome ninja ----------------------------------------------
@design("chrome")
def cyber(f: Frame) -> Canvas:
    cv = Canvas()
    S, L, g, V = (176, 186, 200), (236, 242, 250), (86, 94, 112), (26, 30, 44)
    C, c, b = (90, 236, 255), (40, 150, 200), (40, 72, 160)
    base(
        cv,
        f,
        {
            "top": S,
            "band": S,
            "mask": V,
            "eye": C,
            "face": S,
            "collar": g,
            "strap": S,
            "torso": S,
            "torso_hi": L,
            "torso_lo": g,
            "arm": g,
            "belt": V,
            "buckle": V,
            "legf": S,
            "legb": g,
            "foot": V,
        },
    )
    pal = {"S": S, "L": L, "g": g, "V": V}
    # Dome highlight, fin with LED, visor wraps the front
    stamp(cv.front, f, [".g....", ".g....", "..SLLS", "SSSSLS", "gVVVVV", "SSSggg", ".gggg."], (0, 2), pal)
    led = (255, 70, 70) if (f.i // 4) % 2 else (120, 30, 40)
    cv.front[f.head(1, -3)] = led
    # Visor scanner: a glowing slit that sweeps in idle, locks forward in motion
    if f.anim == "idle":
        pos = [1, 2, 3, 4, 5, 4, 3, 2][(f.i // 2) % 8]
    else:
        pos = 4
    for hx in range(1, 6):
        d = abs(hx - pos)
        cv.front[f.head(hx, 1)] = C if d == 0 else (c if d == 1 else V)
    # Energy ribbons instead of the cloth scarf
    tails = sorted(p for p, lab in f.labels.items() if lab == "tail")
    for k, p in enumerate(reversed(tails)):
        cv.body[p] = [C, c, b][min(2, k)] if (k + f.i) % 4 else L
    # Panel seam across the chest, glowing core
    if f.upright:
        mid = f.torso_top + 2
        sp = f.span(mid)
        if sp:
            for x in range(sp[0], sp[1]):
                cv.front[(x, mid)] = g
        sp = f.span(f.torso_top + 1)
        if sp:
            pulse = [C, (170, 250, 255), L, (170, 250, 255), C, c][(f.i // 2) % 6]
            cv.front[(sp[1] - 2, f.torso_top + 1)] = pulse
    # Running lights on the belt
    belt = sorted(p for p, lab in f.labels.items() if lab in ("belt", "buckle"))
    for k, p in enumerate(belt):
        cv.front[p] = C if (k + f.i // 2) % 3 == 0 else V
    # Thrusters when airborne
    if f.anim == "jump":
        for p in f.feet:
            cv.front[(p[0], p[1] + 1)] = c
    return cv


# --- 4. Crystal: diamond ninja ---------------------------------------------
@design("crystal")
def crystal(f: Frame) -> Canvas:
    cv = Canvas()
    B, Sd, Hl, A = (64, 180, 216), (18, 80, 110), (215, 248, 255), (140, 226, 244)
    M = (98, 204, 232)
    P, Pl = (148, 84, 204), (196, 140, 244)
    Wt = (255, 255, 255)

    def facet(x, y):
        return A if (x - y) % 5 == 0 else B

    base(
        cv,
        f,
        {
            "top": A,
            "band": P,
            "tail": lambda x, y: Pl if (x + y) % 2 else P,
            "mask": Sd,
            "eye": (206, 120, 255),
            "face": Hl,
            "collar": A,
            "strap": Hl,
            "torso": facet,
            "torso_hi": Hl,
            "torso_lo": Sd,
            "arm": Sd,
            "belt": P,
            "buckle": Hl,
            "legf": facet,
            "legb": Sd,
            "foot": Sd,
        },
    )
    pal = {"A": A, "B": B, "D": Sd, "H": Hl, "W": Wt, "M": M}
    # Crystal crown: three shards with lit left / shaded right facets
    stamp(cv.front, f, ["..W...", "H.HM.H", "A.AM.A", "MAHHAM"], (0, 4), pal)
    cv.body[f.head(0, 0)] = Hl  # gem at the scarf knot
    # Shard growing from the back shoulder
    if f.upright:
        sp = f.span(f.torso_top)
        if sp:
            x = sp[0]
            cv.back[(x - 1, f.torso_top - 1)] = Hl
            cv.back[(x - 1, f.torso_top)] = A
            cv.back[(x - 2, f.torso_top - 2)] = Wt
            cv.back[(x, f.torso_top - 1)] = M
    # Twinkles: a four-point star that blooms and fades at changing spots
    spots = [f.head(4, -4), f.head(-2, f.belt - f.hb), f.head(6, 4), f.head(-1, 2)]
    cycle = f.n if f.anim == "idle" else 8
    phase = f.i % max(1, cycle // 2)
    spot = spots[(f.i // max(1, cycle // 2)) % len(spots)] if f.anim == "idle" else spots[0]
    if phase == 1 or (f.anim != "idle" and f.i % 4 == 0):
        cv.front[spot] = Wt
    elif phase == 2:
        x, y = spot
        cv.front[spot] = Wt
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cv.front[(x + dx, y + dy)] = Hl
    elif phase == 3:
        cv.front[spot] = Hl
    return cv


# --- 5. Shadow assassin ----------------------------------------------------
@design("shadow")
def shade(f: Frame) -> Canvas:
    cv = Canvas()
    K, k, X = (40, 38, 50), (70, 68, 84), (16, 14, 22)
    m = (58, 56, 70)
    red, eye = (176, 22, 34), (255, 64, 56)
    leather, silver = (104, 66, 42), (206, 210, 222)
    base(
        cv,
        f,
        {
            "collar": m,
            "strap": K,
            "torso": K,
            "torso_hi": k,
            "arm": X,
            "belt": red,
            "buckle": red,
            "legf": K,
            "legb": X,
            "foot": X,
        },
        skip=("top", "band", "tail", "mask", "eye", "face"),
    )
    pal = {"K": K, "k": k, "X": X, "m": m}
    # Hood: peak trailing back, front brim, face lost in shadow, cloth mask
    stamp(
        cv.front,
        f,
        [
            "kk.....",
            ".kKkkk.",
            ".KKKKKK",
            ".KKXXXK",
            ".KXXmmm",
            "..mmmm.",
        ],
        (1, 2),
        pal,
    )
    blink = f.anim == "idle" and f.i in (17, 18)
    if not blink:
        cv.front[f.head(4, 1)] = eye
        if f.anim == "idle" and f.i % 11 < 5:
            cv.front[f.head(3, 1)] = (120, 20, 26)
    # Leather strap across the chest with a buckle
    if f.upright:
        for y in range(f.torso_top, f.belt):
            sp = f.span(y)
            if not sp:
                continue
            x = sp[1] - (y - f.torso_top)
            if sp[0] <= x <= sp[1]:
                cv.front[(x, y)] = silver if y == f.torso_top + 2 else leather
    # Dagger hilt at the front of the belt
    sp = f.span(f.belt)
    if sp:
        cv.front[(sp[1], f.belt)] = silver
        cv.front[(sp[1] + 1, f.belt - 1)] = (150, 154, 168)
    # Cloak hanging from the shoulders, pulled back by the wind
    top = f.torso_top
    bottom = min(f.bottom - 1, f.belt + 3)
    for y in range(top, bottom + 1):
        sp = f.span(y, parts=("torso", "arm", "strap", "collar", "belt", "buckle", "legf", "legb"))
        if not sp:
            continue
        t = (y - top) / max(1, bottom - top)
        w = 1 + int(t * (1 + f.drag * 1.4) + 0.5)
        if f.drag:
            w += nz("cloak", f.anim, f.i, y) % 2
        elif f.anim == "idle" and y == bottom and (f.i // 6) % 2:
            w += 1
        for x in range(sp[0] - w, sp[0] + 2):
            if y == bottom and (x + f.i) % 2 and x < sp[0]:
                continue
            cv.back[(x, y)] = X if x == sp[0] - w else K
        cv.back[(sp[0] - w + 1, y)] = red if y >= bottom - 1 else K
    return cv


# --- 6. Kitsune: fox spirit ---------------------------------------------------
@design("kitsune")
def kitsune(f: Frame) -> Canvas:
    cv = Canvas()
    Wt, ws = (240, 236, 230), (196, 190, 204)
    red, red_d = (206, 40, 50), (140, 24, 36)
    fox, fox_d, tip = (236, 130, 44), (186, 84, 30), (252, 248, 240)
    gold = (250, 204, 70)
    base(
        cv,
        f,
        {
            "top": Wt,
            "band": Wt,
            "tail": lambda x, y: red if (x + y) % 2 else red_d,
            "mask": Wt,
            "eye": gold,
            "face": Wt,
            "collar": red,
            "strap": ws,
            "torso": Wt,
            "torso_lo": ws,
            "arm": ws,
            "belt": red,
            "buckle": gold,
            "legf": red,
            "legb": red_d,
            "foot": (60, 40, 50),
        },
    )
    pal = {"W": Wt, "w": ws, "r": red, "p": (244, 150, 160)}
    # Fox ears and mask markings
    stamp(cv.front, f, ["W...W.", "Wp.Wp.", "WWWWWW"], (0, 2), pal)
    cv.front[f.head(3, 1)] = red
    cv.front[f.head(5, 1)] = red
    cv.front[f.head(5, 2)] = (60, 40, 50)  # nose
    cv.front[f.head(2, 2)] = red
    # Two fluffy fox tails behind the hips: curled up at rest, streaming in motion
    sp = f.span(f.belt)
    if sp:
        tpal = {"F": fox, "d": fox_d, "W": tip}
        ax, ay = sp[0], f.belt
        if f.drag == 0:
            lean = 1 if f.anim == "idle" and (f.i // 6) % 2 else 0
            back_tail = ["Wdd..", ".dddd"]
            main = [".WW...", "WWWF..", "WFFF..", ".FFd..", "..FFd.", "...dFF"]
            if lean:
                main = [" " + r[:-1] for r in main[:3]] + main[3:]
            stamp_at(cv.back, ax - 1, ay + 1, back_tail, (4, 1), {"W": tip, "d": fox_d})
            stamp_at(cv.back, ax, ay, main, (5, 5), tpal)
        else:
            flick = (f.i // 2) % 2
            main = ["WW.....", "WWFFF..", ".WFFFFd", "..ddFFF"]
            if flick:
                main = [".WW....", "WWFFF..", "WWFFFFd", "..ddFFF"]
            stamp_at(cv.back, ax - 1, ay + 1, ["Wddd."], (4, 0), {"W": tip, "d": fox_d})
            stamp_at(cv.back, ax, ay, main, (6, 3), tpal)
    return cv


# --- 7. Oni: demon ----------------------------------------------------------
@design("oni")
def oni(f: Frame) -> Canvas:
    cv = Canvas()
    red, red_d, red_l = (198, 44, 40), (130, 24, 28), (236, 90, 70)
    horn, horn_d = (244, 214, 120), (190, 150, 70)
    hair, hair_d = (236, 236, 240), (180, 180, 196)
    arm, arm_l = (40, 36, 48), (82, 76, 96)
    tig, tig_s = (232, 168, 40), (44, 30, 26)

    def tiger(x, y):
        return tig_s if (x + 2 * y) % 4 == 0 else tig

    base(
        cv,
        f,
        {
            "top": hair,
            "band": red,
            "tail": lambda x, y: hair if (x + y + f.i // 3) % 3 else hair_d,
            "mask": red,
            "eye": (255, 236, 80),
            "face": red,
            "collar": arm_l,
            "strap": arm_l,
            "torso": arm,
            "torso_hi": arm_l,
            "arm": red_d,
            "belt": tiger,
            "buckle": tiger,
            "legf": lambda x, y: tiger(x, y) if y <= f.belt + 2 else red,
            "legb": lambda x, y: tiger(x, y) if y <= f.belt + 1 else red_d,
            "foot": arm,
        },
    )
    pal = {"h": horn, "j": horn_d, "w": hair, "v": hair_d, "R": red, "r": red_d, "L": red_l, "F": (250, 250, 244)}
    # Horns, wild mane at the back, brow ridge, fangs
    stamp(
        cv.front,
        f,
        [
            "....h.h..",
            "....h.h..",
            "...wjwj..",
            ".wwwwRR..",
            "wvwwRLRR.",
            ".vw......",
        ],
        (2, 3),
        pal,
    )
    cv.front[f.head(5, 3)] = (250, 250, 244)
    cv.front[f.head(3, 3)] = (250, 250, 244)
    cv.front[f.head(5, 1)] = red_l
    # Eye glow flickers
    if f.anim == "idle" and f.i % 8 in (0, 1):
        cv.front[f.head(4, 1)] = (255, 200, 60)
    return cv


# =============================================================================
def template_frames():
    for anim in ACTIONS:
        d = os.path.join(PLAYER_DIR, "default", anim)
        names = sorted(n for n in os.listdir(d) if n.endswith(".png"))
        for i, name in enumerate(names):
            yield anim, name, Frame(load_grid(os.path.join(d, name)), anim, i, len(names))


def render_design(key: str) -> dict:
    """{(anim, frame name): image} for one design."""
    fn = DESIGNS[key]
    return {(anim, name): fn(f).image() for anim, name, f in template_frames()}


def write_design(key: str, out_dir: str) -> None:
    for (anim, name), im in render_design(key).items():
        d = os.path.join(out_dir, anim)
        os.makedirs(d, exist_ok=True)
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        bg.alpha_composite(im)
        bg.convert("RGB").save(os.path.join(d, name))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=PLAYER_DIR, help="parent folder (default: the game's player art)")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    for key in args.only or DESIGNS:
        write_design(key, os.path.join(args.out, key))
        print(f"{key}: written")
