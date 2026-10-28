"""Exact, fast replica of the player's movement physics.

Mirrors `PhysicsEntity.update` + `Player.update` / `jump` / `dash` in
scripts/entities.py operation for operation (same float arithmetic, same
pygame.Rect truncation, same collision order), without particles,
animations or audio. `tools/worlds/check_physics.py` verifies it frame by
frame against the real `Player` on real maps.

Only movement matters here: enemies and projectiles never push the player,
so the trajectory depends on the inputs alone.

The level is a `Terrain`: the set of solid tiles, carrying the level's
water layer ({(tx, ty): flow}, see scripts/water.py) along.

State is an immutable tuple so the route planner can hash and branch it:
    (x, y, vx, vy, air_time, jumps, wall_slide, dashing, flip, last_m,
     breath, swim_cooldown)
"""

from __future__ import annotations

from scripts.constants import (
    AIR_TIME_FATAL,
    BREATH_FRAMES,
    DASH_DECEL_TRIGGER_FRAME,
    DASH_DURATION_FRAMES,
    DASH_MIN_ACTIVE_ABS,
    DASH_SPEED,
    GRAVITY_ACCEL,
    HORIZONTAL_FRICTION,
    JUMP_VELOCITY,
    MAX_FALL_SPEED,
    SWIM_STROKE_COOLDOWN,
    SWIM_STROKE_VELOCITY,
    WALL_JUMP_HORIZONTAL_VEL,
    WALL_JUMP_VERTICAL_VEL,
    WALL_SLIDE_MAX_SPEED,
    WATER_CURRENTS,
    WATER_DASH_SPEED,
    WATER_DRAG,
    WATER_GRAVITY,
    WATER_MAX_SINK,
    WATER_MOVE_SCALE,
)
from scripts.tilemap import NEIGHBOR_OFFSET, PHYSICS_TILES

TS = 16
PW, PH = 8, 15  # player hitbox

X, Y, VX, VY, AIR, JUMPS, WALL, DASH, FLIP, LASTM, BREATH, SWIM = range(12)

_DRY: dict = {}


class Terrain(set):
    """Solid tiles {(tx, ty)} of a level, with its water layer as `.water`."""

    def __init__(self, solids=(), water=None):
        super().__init__(solids)
        self.water = water or _DRY


def solids_from_map(tilemap: dict, water_rows=None) -> Terrain:
    """Terrain of a map: every physics tile of its `tilemap` dict, and its
    water layer from the map's `water` runs."""
    from scripts.water import water_from_rows

    out = Terrain(water=water_from_rows(water_rows or []))
    for tile in tilemap.values():
        if tile["type"] in PHYSICS_TILES:
            out.add((tile["pos"][0], tile["pos"][1]))
    return out


def terrain_from_map(map_data: dict) -> Terrain:
    return solids_from_map(map_data["tilemap"], map_data.get("water"))


def spawn_state(px: float, py: float) -> tuple:
    """State of a freshly spawned player (Player.__init__ defaults)."""
    return (px, py, 0, 0, 0, 1, False, 0, False, 0, BREATH_FRAMES, 0)


def water_at(x: float, y: float, water: dict):
    """(flow at the hitbox center or None, eyes under water) for a player at x, y,
    as PhysicsEntity.water_flow and Player.head_in_water read it."""
    if not water:
        return None, False
    cx, ry = _trunc(x) + PW // 2, _trunc(y)
    return water.get((cx // TS, (ry + PH // 2) // TS)), (cx // TS, (ry + 2) // TS) in water


def _trunc(v: float) -> int:
    return int(v)  # pygame.Rect truncates toward zero


def press_jump(s: tuple, solids=_DRY) -> tuple:
    """Player.jump() (no grapple, no moon boots). Returns the new state."""
    x, y, vx, vy, air, jumps, wall, dashing, flip, lastm, breath, swim = s
    flow, head_wet = water_at(x, y, getattr(solids, "water", _DRY))
    if flow is not None and (head_wet or not jumps):
        if swim:
            return s
        return (x, y, vx, SWIM_STROKE_VELOCITY, air, jumps, wall, dashing, flip, lastm, breath, SWIM_STROKE_COOLDOWN)
    if wall:
        if flip and lastm < 0:
            return (
                x,
                y,
                WALL_JUMP_HORIZONTAL_VEL,
                WALL_JUMP_VERTICAL_VEL,
                5,
                max(0, jumps - 1),
                wall,
                dashing,
                flip,
                lastm,
                breath,
                swim,
            )
        if not flip and lastm > 0:
            return (
                x,
                y,
                -WALL_JUMP_HORIZONTAL_VEL,
                WALL_JUMP_VERTICAL_VEL,
                5,
                max(0, jumps - 1),
                wall,
                dashing,
                flip,
                lastm,
                breath,
                swim,
            )
        return s
    if jumps:
        return (x, y, vx, JUMP_VELOCITY, 5, jumps - 1, wall, dashing, flip, lastm, breath, swim)
    return s


def can_jump(s: tuple, solids=_DRY) -> bool:
    return press_jump(s, solids) is not s


def press_dash(s: tuple) -> tuple:
    if s[DASH]:
        return s
    d = -DASH_DURATION_FRAMES if s[FLIP] else DASH_DURATION_FRAMES
    return s[:DASH] + (d,) + s[DASH + 1 :]


def step(s: tuple, m: int, solids: set) -> tuple:
    """One `Player.update(tilemap, (m, 0))`. Returns (state, down, dead)."""
    x, y, vx, vy, air, jumps, wall, dashing, flip, lastm, breath, swim = s
    down = up = right = left = False
    flow, head_wet = water_at(x, y, getattr(solids, "water", _DRY))

    # Horizontal
    if flow is None:
        fmx = m + vx
        fmy = vy
    else:
        push = WATER_CURRENTS[flow]
        fmx = m * WATER_MOVE_SCALE + vx + push[0]
        fmy = vy + push[1]
    x += fmx
    if fmx != 0:
        rx, ry = _trunc(x), _trunc(y)
        tx, ty = int(x // TS), int(y // TS)
        for ox, oy in NEIGHBOR_OFFSET:
            c = (tx + ox, ty + oy)
            if c in solids:
                bx, by = c[0] * TS, c[1] * TS
                if rx < bx + TS and bx < rx + PW and ry < by + TS and by < ry + PH:
                    if fmx > 0:
                        rx = bx - PW
                        right = True
                    else:
                        rx = bx + TS
                        left = True
                    x = rx

    # Vertical
    y += fmy
    if fmy != 0:
        rx, ry = _trunc(x), _trunc(y)
        tx, ty = int(x // TS), int(y // TS)
        for ox, oy in NEIGHBOR_OFFSET:
            c = (tx + ox, ty + oy)
            if c in solids:
                bx, by = c[0] * TS, c[1] * TS
                if rx < bx + TS and bx < rx + PW and ry < by + TS and by < ry + PH:
                    if fmy > 0:
                        ry = by - PH
                        down = True
                    else:
                        ry = by + TS
                        up = True
                    y = ry

    # Orientation
    if m > 0:
        flip = False
    elif m < 0:
        flip = True
    lastm = m

    # Gravity
    if flow is None:
        vy = min(MAX_FALL_SPEED, vy + GRAVITY_ACCEL)
    else:
        vy = min(WATER_MAX_SINK, vy * WATER_DRAG + WATER_GRAVITY)
    if down or up:
        vy = 0

    if swim > 0:
        swim -= 1
    air += 1
    if flow is not None:
        air = 0
        if head_wet:
            jumps = 1
    breath = breath - 1 if head_wet else BREATH_FRAMES
    dead = air > AIR_TIME_FATAL or breath <= 0
    if down:
        air = 0
        jumps = 1

    wall = False
    if (right or left) and air > 4:
        wall = True
        vy = min(vy, WALL_SLIDE_MAX_SPEED)
        flip = not right

    if dashing > 0:
        dashing = max(0, dashing - 1)
    if dashing < 0:
        dashing = min(0, dashing + 1)
    if abs(dashing) > DASH_MIN_ACTIVE_ABS:
        vx = abs(dashing) / dashing * (DASH_SPEED if flow is None else WATER_DASH_SPEED)
        if abs(dashing) == DASH_DECEL_TRIGGER_FRAME:
            vx *= 0.1

    if vx > 0:
        vx = max(vx - HORIZONTAL_FRICTION, 0)
    else:
        vx = min(vx + HORIZONTAL_FRICTION, 0)

    return (x, y, vx, vy, air, jumps, wall, dashing, flip, lastm, breath, swim), down, dead


def apply_frame(s: tuple, m: int, jump: bool, dash: bool, solids: set) -> tuple:
    """Inputs of one frame in the game's order: key presses, then the update."""
    if jump:
        s = press_jump(s, solids)
    if dash:
        s = press_dash(s)
    return step(s, m, solids)
