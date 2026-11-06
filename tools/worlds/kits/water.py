"""Building blocks of the second water world (levels 36-40): tide pools,
whirlpool rings, kelp lanes, reef vaults and bone arcs.

Everything takes tile coordinates (y grows downward) and stamps into a
`tools.worlds.builder.Level`. Water has to stay held (rock or water beside
and under every water tile), so the helpers that flood something also
leave or build the rock that holds it; the builder refuses a level that
leaks.
"""

from __future__ import annotations

import math
import random

from tools.worlds.builder import DOWN, LEFT, RIGHT, STILL, UP, Level

# Small decor (tiles/decor): seaweed, coral, starfish and shell, anemone
SEAWEED, CORAL, STARFISH, ANEMONE = 8, 9, 10, 11
# Large decor (tiles/large_decor): kelp, fan coral, anchor, treasure chest
KELP, FAN_CORAL, ANCHOR, CHEST = 6, 7, 8, 9
SEA_DECOR = (SEAWEED, CORAL, STARFISH, ANEMONE)


# --- water --------------------------------------------------------------------------


def basin(lv: Level, x0: int, x1: int, surface: int, bottom: int, flow: int = STILL, air: int = 0):
    """Carve x0..x1 from `air` rows over `surface` down to `bottom` and flood
    surface..bottom: a pool cut into rock (the rock around it holds it)."""
    lv.carve(x0, surface - air, x1, bottom)
    lv.water(x0, surface, x1, bottom, flow)


def pocket(lv: Level, x0: int, y0: int, x1: int, y1: int):
    """Air trapped under rock: carve x0..x1, y0..y1 and take the water out
    (it needs rock over and beside it and water under it)."""
    lv.carve(x0, y0, x1, y1)
    lv.drain(x0, y0, x1, y1)


def flow_of(dx: float, dy: float, clockwise: bool = True) -> int:
    """Current of a whirl at offset (dx, dy) from its centre (y down): along the
    tangent, by its stronger axis. Clockwise on screen: right along the top,
    down the east side, left along the bottom, up the west side."""
    tx, ty = (-dy, dx) if clockwise else (dy, -dx)
    if abs(tx) >= abs(ty):
        return RIGHT if tx > 0 else LEFT
    return DOWN if ty > 0 else UP


def ellipse_in(x: int, y: int, cx: float, cy: float, rx: float, ry: float) -> bool:
    """Whether tile (x, y)'s centre lies inside the ellipse."""
    return ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0


def ring_flow(x: int, y: int, box: tuple, lane: int, clockwise: bool = True) -> int:
    """Current of tile (x, y) in a ring `lane` tiles wide round the inside of
    `box` (x0, y0, x1, y1): along the lane it is in. In a corner it turns into
    the next lane only next to the outer wall, a tile past the core's corner,
    so a swimmer (wider than nothing) is never pinned against the core.
    Clockwise on screen: right along the top, down the east side, left along
    the bottom, up the west side."""
    x0, y0, x1, y1 = box
    west, east = x < x0 + lane, x > x1 - lane
    top, bottom = y < y0 + lane, y > y1 - lane
    if clockwise:
        if top and west:
            return RIGHT if y < y0 + lane - 1 else UP
        if top and east:
            return DOWN if x > x1 - lane + 1 else RIGHT
        if bottom and east:
            return LEFT if y > y1 - lane + 1 else DOWN
        if bottom and west:
            return UP if x < x0 + lane - 1 else LEFT
        return RIGHT if top else LEFT if bottom else UP if west else DOWN
    if top and east:
        return LEFT if y < y0 + lane - 1 else UP
    if top and west:
        return DOWN if x < x0 + lane - 1 else LEFT
    if bottom and west:
        return RIGHT if y > y1 - lane + 1 else DOWN
    if bottom and east:
        return UP if x > x1 - lane + 1 else RIGHT
    return LEFT if top else RIGHT if bottom else UP if east else DOWN


def ring(lv: Level, box: tuple, lane: int, clockwise: bool = True, round_r: float = 0.0, t=None, stamp=True):
    """A whirl: a ring of water `lane` tiles wide round a core of rock, inside
    rock `box` (x0, y0, x1, y1, the ring's outer edge; the rock round it is
    stamped two tiles thick unless `stamp` is off), its current turning round
    the core (see `ring_flow`). The outer and the core's corners are rounded
    with radius `round_r` (tiles). Returns the ring's tiles."""
    x0, y0, x1, y1 = box
    if stamp:
        lv.rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2, t)

    def cut(x, y, bx0, by0, bx1, by1, r):
        """Whether tile (x, y) is outside the rounded corners of the box."""
        if r <= 0:
            return False
        for cx, cy, sx, sy in (
            (bx0 + r, by0 + r, -1, -1),
            (bx1 + 1 - r, by0 + r, 1, -1),
            (bx0 + r, by1 + 1 - r, -1, 1),
            (bx1 + 1 - r, by1 + 1 - r, 1, 1),
        ):
            px, py = x + 0.5, y + 0.5
            if (px - cx) * sx > 0 and (py - cy) * sy > 0 and math.hypot(px - cx, py - cy) > r:
                return True
        return False

    tiles = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if cut(x, y, x0, y0, x1, y1, round_r):
                continue
            inner = x0 + lane <= x <= x1 - lane and y0 + lane <= y <= y1 - lane
            if inner and not cut(x, y, x0 + lane, y0 + lane, x1 - lane, y1 - lane, max(0.0, round_r - lane)):
                continue
            tiles.append((x, y))
    for x, y in tiles:
        lv.solid.pop((x, y), None)
        lv.water_tiles[(x, y)] = ring_flow(x, y, box, lane, clockwise)
    return tiles


def gears(lv: Level, boxes, lane: int, round_r: float = 0.0, t=None):
    """Whirls side by side that mesh like gears: boxes (x0, y0, x1, y1) left to
    right, each next to the one before (x0 = the last x1 + 1), turning
    alternately clockwise and the other way, so that where two touch both run
    the same way (down, then up, ...) in one shared lane twice as wide. Where
    it ends, each turns back into its own ring: which one a swimmer follows
    depends on the side of the shared lane it is on. Returns the tiles."""
    for x0, y0, x1, y1 in boxes:
        lv.rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2, t)
    tiles = []
    for i, box in enumerate(boxes):
        tiles += ring(lv, box, lane, i % 2 == 0, round_r, t, stamp=False)
    return tiles


def shift(lv: Level, dx: int, dy: int = 0):
    """Move everything stamped into `lv` so far by (dx, dy) tiles: rock, water,
    objects, offgrid decor and banners, the spawn and the route (levels are
    drawn from x 0 on; a level designed round a negative x is moved over)."""
    from tools.worlds.planner import Waypoint

    lv.solid = {(x + dx, y + dy): t for (x, y), t in lv.solid.items()}
    lv.water_tiles = {(x + dx, y + dy): f for (x, y), f in lv.water_tiles.items()}
    lv.objects = {(x + dx, y + dy): o for (x, y), o in lv.objects.items()}
    for o in lv.offgrid:
        o["pos"] = [o["pos"][0] + dx * 16, o["pos"][1] + dy * 16]
    if lv.spawn_tile:
        lv.spawn_tile = (lv.spawn_tile[0] + dx, lv.spawn_tile[1] + dy)
    lv.route = [Waypoint(w.x0 + dx, w.y0 + dy, w.x1 + dx, w.y1 + dy, w.ground, w.label) for w in lv.route]


# --- rock shapes ------------------------------------------------------------------------


def blob(lv: Level, cx: float, cy: float, rx: float, ry: float, t=None):
    """Fill an ellipse of rock."""
    for y in range(math.floor(cy - ry) - 1, math.ceil(cy + ry) + 1):
        for x in range(math.floor(cx - rx) - 1, math.ceil(cx + rx) + 1):
            if ellipse_in(x, y, cx, cy, rx, ry):
                lv.solid[(x, y)] = t or lv.tile


def hollow(lv: Level, cx: float, cy: float, rx: float, ry: float):
    """Carve an ellipse out of the rock."""
    for y in range(math.floor(cy - ry) - 1, math.ceil(cy + ry) + 1):
        for x in range(math.floor(cx - rx) - 1, math.ceil(cx + rx) + 1):
            if ellipse_in(x, y, cx, cy, rx, ry):
                lv.solid.pop((x, y), None)


def arc(lv: Level, cx: float, cy: float, r: float, a0: float, a1: float, thick: float = 1.0, t=None, ry=None):
    """A band of rock `thick` tiles wide along an arc (an ellipse with radii r,
    ry) from angle a0 to a1 (degrees, 0 = east, 90 = north/up on screen).
    Returns its tiles."""
    ry = r if ry is None else ry
    tiles = set()
    lo, hi = min(a0, a1), max(a0, a1)
    for y in range(math.floor(cy - ry - thick) - 1, math.ceil(cy + ry + thick) + 1):
        for x in range(math.floor(cx - r - thick) - 1, math.ceil(cx + r + thick) + 1):
            dx, dy = x + 0.5 - cx, cy - (y + 0.5)
            ang = math.degrees(math.atan2(dy / ry, dx / r)) % 360
            if not any(lo <= a <= hi for a in (ang, ang - 360, ang + 360)):
                continue
            # distance from the ellipse along the radius, in tiles
            k = math.hypot(dx / r, dy / ry)
            rad = math.hypot(dx, dy)
            d = abs(rad - rad / k) if k else rad
            if d <= thick / 2:
                tiles.add((x, y))
    for p in tiles:
        lv.solid[p] = t or lv.tile
    return tiles


# --- decor --------------------------------------------------------------------------------


def floor_at(lv: Level, x: int, y_from: int, y_to: int = 400):
    """Row of the first solid tile at or below `y_from` in column x (None if none)."""
    for y in range(y_from, y_to):
        if lv.is_solid(x, y):
            return y
    return None


def free(lv: Level, x: int, y: int) -> bool:
    return not lv.is_solid(x, y) and (x, y) not in lv.objects


def dress(lv: Level, xs, y_from: int, variants=SEA_DECOR, seed: int = 0):
    """Small decor on the floor under row `y_from` at each column of `xs`
    (where the tile over the floor is free)."""
    rng = random.Random(seed)
    for x in xs:
        fy = floor_at(lv, x, y_from)
        if fy is not None and free(lv, x, fy - 1):
            lv.decor(x, fy - 1, rng.choice(variants))


def kelp(lv: Level, xs, y_from: int):
    """Kelp (large decor) on the floor under row `y_from` at each column of `xs`."""
    for x in xs:
        fy = floor_at(lv, x, y_from)
        if fy is not None and free(lv, x, fy - 1):
            lv.big_decor(x, fy - 1, KELP)


__all__ = [
    "ANCHOR",
    "ANEMONE",
    "CHEST",
    "CORAL",
    "DOWN",
    "FAN_CORAL",
    "KELP",
    "LEFT",
    "RIGHT",
    "SEAWEED",
    "SEA_DECOR",
    "STARFISH",
    "STILL",
    "UP",
    "arc",
    "basin",
    "blob",
    "dress",
    "ellipse_in",
    "floor_at",
    "flow_of",
    "free",
    "gears",
    "hollow",
    "kelp",
    "pocket",
    "ring",
    "ring_flow",
    "shift",
]
