"""The start of a level is safe: no enemy attacks a player standing there.

A start zone covers the platform under a player spawner, up to SAFE_RADIUS
tiles to either side of the spawn and SAFE_HEIGHT tiles above the floor
(a jump on the spot stays inside). While a player is in it:

- no enemy fires or throws at them, and turrets and throwers do not wind up;
  chasers hold still instead of running at them,
- enemy bullets and stars vanish where they enter the zone,
- touching an enemy costs nothing.

Enemies never walk or hop into a zone (scripts/ai/behaviors.py); one that
spawns inside one may walk out. Landing on an enemy still kills it.
"""

from __future__ import annotations

from typing import Any, Iterable, List

import pygame

SAFE_RADIUS = 4  # tiles to either side of the spawn tile
SAFE_HEIGHT = 4  # tiles above the floor (a jump rises about 3)
FLOOR_SEARCH = 12  # tiles below the spawn a floor is looked for


def _solid(tilemap: Any, tx: int, ty: int) -> bool:
    return tilemap.solid_type(tx, ty) is not None


def start_zone(tilemap: Any, spawn_pos: Iterable[float]) -> pygame.Rect:
    """The safe zone of a player spawned at `spawn_pos` (px, top-left of an
    8x15 player): the walkable floor under it (open above, no further than
    SAFE_RADIUS tiles from the spawn) and SAFE_HEIGHT tiles of air above."""
    ts = tilemap.tile_size
    x, y = spawn_pos
    tx = int(x + 4) // ts
    ty = int(y + 15) // ts
    for _ in range(FLOOR_SEARCH):
        if _solid(tilemap, tx, ty):
            break
        ty += 1
    else:  # in the air: a box around the spawn
        return pygame.Rect(
            (tx - SAFE_RADIUS) * ts, int(y) - SAFE_HEIGHT * ts, (2 * SAFE_RADIUS + 1) * ts, (SAFE_HEIGHT + 1) * ts
        )
    left = right = tx
    while tx - left < SAFE_RADIUS and _solid(tilemap, left - 1, ty) and not _solid(tilemap, left - 1, ty - 1):
        left -= 1
    while right - tx < SAFE_RADIUS and _solid(tilemap, right + 1, ty) and not _solid(tilemap, right + 1, ty - 1):
        right += 1
    return pygame.Rect(left * ts, (ty - SAFE_HEIGHT) * ts, (right - left + 1) * ts, SAFE_HEIGHT * ts)


def start_zones(tilemap: Any, spawn_positions: Iterable[Iterable[float]]) -> List[pygame.Rect]:
    return [start_zone(tilemap, pos) for pos in spawn_positions]


def in_safe_zone(game: Any, point: Iterable[float]) -> bool:
    """True if `point` (px) lies in one of the game's start zones."""
    zones = getattr(game, "safe_zones", None)
    if not isinstance(zones, list):
        return False
    px, py = point
    return any(zone.collidepoint(px, py) for zone in zones)


def player_safe(game: Any, player: Any) -> bool:
    """True if `player` stands (or jumps) in a start zone."""
    return player is not None and in_safe_zone(game, player.rect().center)
