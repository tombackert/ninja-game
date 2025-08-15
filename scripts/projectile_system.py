"""ProjectileSystem (Issue 17).

Centralizes all projectile lifetime, movement and collision handling that was
previously scattered across `ui.render_game_elements`, `Player.shoot` and
`Enemy.update` loops. This improves testability (headless updates) and clears
the way for future networking / rollback (single source of truth for spawn &
resolve) and weapon extensibility.

Data Model: lightweight dict per projectile to remain flexible while legacy
code still spawns positional lists. A future iteration (Issue 19/23) can swap
to a dataclass once services injection pattern is in place.

Projectile record fields:
    pos: [x: float, y: float]
    vel: [vx: float, vy: float] (currently only horizontal)
    age: int (frames since spawn)
    owner: str ("player" | "enemy") for future friendly-fire logic

Public API:
    spawn(x, y, vx, owner): -> projectile dict
    update(tilemap, players, enemies) -> collisions summary dict
    iter() -> iterator over active projectiles (for rendering)
    clear() -> remove all

Rendering Responsibility:
The system does NOT blit surfaces – the Renderer/UI queries active
projectiles and draws them (preserving separation of simulation & presentation).

Collision Rules (parity with prior logic):
  * Solid tile: remove projectile & spawn impact sparks.
  * Age > PROJECTILE_LIFETIME_FRAMES: remove.
  * Hit enemy (player owned) or player (enemy owned) while player not dashing
    aggressively: remove, apply damage/effects.

Tests (added in `tests/test_projectile_system.py`) cover:
  * Lifetime expiry.
  * Enemy hit removal (coins increment).
  * Player hit decrements lives (and respects dashing small window logic
    equivalently by skipping high dashing magnitude check for simplicity).
"""

from __future__ import annotations

from typing import Iterator, List, Dict, Any

import pygame

from .constants import PROJECTILE_LIFETIME_FRAMES, DASH_MIN_ACTIVE_ABS
from .effects_util import spawn_projectile_sparks, spawn_hit_sparks


class ProjectileSystem:
    def __init__(self, game):
        self.game = game
        self._projectiles: List[Dict[str, Any]] = []

    # --- Collection Protocol -------------------------------------------------
    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._projectiles)

    def __iter__(self) -> Iterator[Dict[str, Any]]:  # pragma: no cover - trivial
        return iter(self._projectiles)

    # --- API -----------------------------------------------------------------
    def spawn(self, x: float, y: float, vx: float, owner: str):
        proj = {"pos": [x, y], "vel": [vx, 0.0], "age": 0, "owner": owner}
        self._projectiles.append(proj)
        spawn_projectile_sparks(self.game, proj["pos"], vx)
        return proj

    def clear(self):  # pragma: no cover - utility
        self._projectiles.clear()

    # --- Simulation ----------------------------------------------------------
    def update(self, tilemap, players, enemies):
        """Advance all projectiles one frame.

        Returns a summary dict for potential instrumentation / tests.
        """
        removed = 0
        hits_player = 0
        hits_enemy = 0
        for proj in self._projectiles.copy():
            # Movement
            proj["pos"][0] += proj["vel"][0]
            proj["age"] += 1

            # Tile collision
            if tilemap.solid_check(proj["pos"]):
                self._projectiles.remove(proj)
                spawn_projectile_sparks(self.game, proj["pos"], proj["vel"][0])
                removed += 1
                continue

            # Lifetime expiry
            if proj["age"] > PROJECTILE_LIFETIME_FRAMES:
                self._projectiles.remove(proj)
                removed += 1
                continue

            # Entity collisions
            if proj["owner"] == "player":
                # Check enemies
                rect = pygame.Rect(proj["pos"][0], proj["pos"][1], 4, 4)
                for enemy in enemies.copy():
                    if enemy.rect().colliderect(rect):
                        self._projectiles.remove(proj)
                        self.game.screenshake = max(16, self.game.screenshake)
                        self.game.audio.play("hit")
                        self.game.cm.coins += 1
                        spawn_hit_sparks(self.game, enemy.rect().center)
                        hits_enemy += 1
                        removed += 1
                        # Enemy removal handled in enemy.update; we just trigger state.
                        break
            else:  # enemy owned
                # Player damage (skip if heavily dashing similar to old logic)
                rect = pygame.Rect(proj["pos"][0], proj["pos"][1], 4, 4)
                for player in players:
                    if abs(
                        player.dashing
                    ) < DASH_MIN_ACTIVE_ABS and player.rect().colliderect(rect):
                        if proj in self._projectiles:
                            self._projectiles.remove(proj)
                            player.lives -= 1
                            self.game.audio.play("hit")
                            self.game.screenshake = max(16, self.game.screenshake)
                            spawn_hit_sparks(self.game, player.rect().center)
                            hits_player += 1
                            removed += 1
                        break

        return {
            "removed": removed,
            "hits_player": hits_player,
            "hits_enemy": hits_enemy,
            "active": len(self._projectiles),
        }

    # --- Rendering Data ------------------------------------------------------
    def get_draw_commands(self):
        """Yield tuples (image, draw_x, draw_y) for active projectiles.

        Keeps renderer/UI unaware of internal structure details.
        """
        img = self.game.assets["projectile"]
        for proj in self._projectiles:
            yield img, proj["pos"][0] - img.get_width() / 2, proj["pos"][
                1
            ] - img.get_height() / 2


__all__ = ["ProjectileSystem"]
