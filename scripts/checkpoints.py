"""Checkpoints: banners a level puts at the start of its sections.

A checkpoint is a tile of type "checkpoint", on the grid or offgrid. Its
16x32 banner is drawn from the tile's position down, so the banner's lower
half stands in the air tile right above the ground; variant 0 is furled,
1 hoisted. A player who touches it respawns there, in its lower tile, after
a death: it moves the player's respawn point the first time this player
touches it (touching an earlier one again later does not move it back) and
hoists the banner.

The banner's state lives in the tilemap's own tile, so it stays hoisted
through respawns (Game.load_level keeps the tiles) and is furled again
when the level is loaded anew (game over, next start). Each player keeps
the checkpoints they reached (`player.checkpoints_reached`), so in
multiplayer everyone respawns at their own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

CHECKPOINT = "checkpoint"
FURLED, HOISTED = 0, 1
BANNER_W, BANNER_H = 16, 32


@dataclass
class Checkpoint:
    tile: dict  # the tilemap's own tile: its variant is the banner's state
    rect: pygame.Rect  # the banner: touching it reaches the checkpoint
    respawn: tuple  # px: where a player who reached it comes back

    @property
    def hoisted(self) -> bool:
        return self.tile["variant"] == HOISTED


def find_checkpoints(tilemap) -> list:
    """The checkpoints of a loaded tilemap, west to east."""
    ts = tilemap.tile_size
    found = []
    for tile in tilemap.offgrid_tiles:
        if tile["type"] == CHECKPOINT:
            found.append((tile, tile["pos"][0], tile["pos"][1]))
    for tile in tilemap.tilemap.values():
        if tile["type"] == CHECKPOINT:
            found.append((tile, tile["pos"][0] * ts, tile["pos"][1] * ts))
    found.sort(key=lambda f: (f[1], f[2]))
    return [
        Checkpoint(tile, pygame.Rect(int(x), int(y), BANNER_W, BANNER_H), (x, y + BANNER_H - ts))
        for tile, x, y in found
    ]


def touch(checkpoints: list, player):
    """Hoist and take the checkpoint `player` touches for the first time: its
    respawn point moves there. Returns that checkpoint, or None."""
    reached = getattr(player, "checkpoints_reached", None)
    if reached is None:
        reached = player.checkpoints_reached = set()
    rect = player.rect()
    for i, cp in enumerate(checkpoints):
        if i not in reached and rect.colliderect(cp.rect):
            reached.add(i)
            cp.tile["variant"] = HOISTED
            player.respawn_pos = list(cp.respawn)
            return cp
    return None


def celebrate(game, cp) -> None:
    """Sparks off the hoisted banner (fixed angles: no gameplay RNG drawn) and a chime."""
    from scripts.spark import Spark

    center = (cp.rect.x + 10, cp.rect.y + 7)
    for k in range(12):
        game.sparks.append(Spark(center, k * math.pi / 6, 1.5 + (k % 3) * 0.5))
    game.audio.play("checkpoint")


__all__ = ["CHECKPOINT", "FURLED", "HOISTED", "Checkpoint", "find_checkpoints", "touch", "celebrate"]
