"""Exact, fast replica of the player's movement physics.

Mirrors `PhysicsEntity.update` + `Player.update` / `jump` / `dash` in
scripts/entities.py operation for operation (same float arithmetic, same
pygame.Rect truncation, same collision order), without particles,
animations or audio. `tools/worlds/check_physics.py` verifies it frame by
frame against the real `Player` on real maps.

Only movement matters here: enemies and projectiles never push the player,
so the trajectory depends on the inputs alone.

State is an immutable tuple so the route planner can hash and branch it:
    (x, y, vx, vy, air_time, jumps, wall_slide, dashing, flip, last_m)
"""

from __future__ import annotations

from scripts.constants import (
    AIR_TIME_FATAL,
    DASH_DECEL_TRIGGER_FRAME,
    DASH_DURATION_FRAMES,
    DASH_MIN_ACTIVE_ABS,
    DASH_SPEED,
    GRAVITY_ACCEL,
    HORIZONTAL_FRICTION,
    JUMP_VELOCITY,
    MAX_FALL_SPEED,
    WALL_JUMP_HORIZONTAL_VEL,
    WALL_JUMP_VERTICAL_VEL,
    WALL_SLIDE_MAX_SPEED,
)
from scripts.tilemap import NEIGHBOR_OFFSET, PHYSICS_TILES

TS = 16
PW, PH = 8, 15  # player hitbox

X, Y, VX, VY, AIR, JUMPS, WALL, DASH, FLIP, LASTM = range(10)


def solids_from_map(tilemap: dict) -> set:
    """Set of (tx, ty) for every physics tile of a map's `tilemap` dict."""
    out = set()
    for tile in tilemap.values():
        if tile["type"] in PHYSICS_TILES:
            out.add((tile["pos"][0], tile["pos"][1]))
    return out


def spawn_state(px: float, py: float) -> tuple:
    """State of a freshly spawned player (Player.__init__ defaults)."""
    return (px, py, 0, 0, 0, 1, False, 0, False, 0)


def _trunc(v: float) -> int:
    return int(v)  # pygame.Rect truncates toward zero


def press_jump(s: tuple) -> tuple:
    """Player.jump() (no grapple, no moon boots). Returns the new state."""
    x, y, vx, vy, air, jumps, wall, dashing, flip, lastm = s
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
            )
        return s
    if jumps:
        return (x, y, vx, JUMP_VELOCITY, 5, jumps - 1, wall, dashing, flip, lastm)
    return s


def can_jump(s: tuple) -> bool:
    return press_jump(s) is not s


def press_dash(s: tuple) -> tuple:
    if s[DASH]:
        return s
    d = -DASH_DURATION_FRAMES if s[FLIP] else DASH_DURATION_FRAMES
    return s[:DASH] + (d,) + s[DASH + 1 :]


def step(s: tuple, m: int, solids: set) -> tuple:
    """One `Player.update(tilemap, (m, 0))`. Returns (state, down, dead)."""
    x, y, vx, vy, air, jumps, wall, dashing, flip, lastm = s
    down = up = right = left = False

    # Horizontal
    fmx = m + vx
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
    fmy = vy
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
    vy = min(MAX_FALL_SPEED, vy + GRAVITY_ACCEL)
    if down or up:
        vy = 0

    air += 1
    dead = air > AIR_TIME_FATAL
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
        vx = abs(dashing) / dashing * DASH_SPEED
        if abs(dashing) == DASH_DECEL_TRIGGER_FRAME:
            vx *= 0.1

    if vx > 0:
        vx = max(vx - HORIZONTAL_FRICTION, 0)
    else:
        vx = min(vx + HORIZONTAL_FRICTION, 0)

    return (x, y, vx, vy, air, jumps, wall, dashing, flip, lastm), down, dead


def apply_frame(s: tuple, m: int, jump: bool, dash: bool, solids: set) -> tuple:
    """Inputs of one frame in the game's order: key presses, then the update."""
    if jump:
        s = press_jump(s)
    if dash:
        s = press_dash(s)
    return step(s, m, solids)
