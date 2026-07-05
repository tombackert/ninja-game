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
    id: int (unique projectile ID for network sync, MP-02)
    pos: [x: float, y: float]
    vel: [vx: float, vy: float] (currently only horizontal)
    age: int (frames since spawn)
    owner: str ("player" | "enemy") for future friendly-fire logic
    owner_id: int | None (player ID who fired, for multiplayer)

Public API:
    spawn(x, y, vx, owner, owner_id=None): -> projectile dict
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

from typing import Any, Dict, Iterator, List, Optional

import pygame

from .constants import DASH_MIN_ACTIVE_ABS, PROJECTILE_LIFETIME_FRAMES
from .effects_util import spawn_hit_sparks, spawn_projectile_sparks
from .entity_id import EntityIDGenerator


class ProjectileSystem:
    def __init__(self, game):
        self.game = game
        self._projectiles: List[Dict[str, Any]] = []
        self._id_gen = EntityIDGenerator.get()

    # --- Collection Protocol -------------------------------------------------
    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._projectiles)

    def __iter__(self) -> Iterator[Dict[str, Any]]:  # pragma: no cover - trivial
        return iter(self._projectiles)

    # --- API -----------------------------------------------------------------
    def spawn(
        self,
        x: float,
        y: float,
        vx: float,
        owner: str,
        owner_id: Optional[int] = None,
        vy: float = 0.0,
        gravity: float = 0.0,
        kind: str = "bullet",
        pierce: bool = False,
    ):
        proj = {
            "id": self._id_gen.next_id(),
            "pos": [x, y],
            "vel": [vx, vy],
            "age": 0,
            "owner": owner,
            "owner_id": owner_id,
            "gravity": gravity,
            "kind": kind,
            "pierce": pierce,
        }
        self._projectiles.append(proj)
        spawn_projectile_sparks(self.game, proj["pos"], vx)
        return proj

    def destroy_in_rect(self, rect: pygame.Rect, owner: str = "enemy") -> int:
        """Remove projectiles of `owner` overlapping `rect` (sword parry).

        Returns the number of destroyed projectiles.
        """
        destroyed = 0
        for proj in self._projectiles.copy():
            if proj["owner"] != owner:
                continue
            if rect.collidepoint(proj["pos"][0], proj["pos"][1]):
                self._projectiles.remove(proj)
                spawn_projectile_sparks(self.game, proj["pos"], proj["vel"][0])
                destroyed += 1
        return destroyed

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
            # Movement (vy/gravity used by arcing projectiles like ninja stars)
            proj["vel"][1] += proj.get("gravity", 0.0)
            proj["pos"][0] += proj["vel"][0]
            proj["pos"][1] += proj["vel"][1]
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
                hit_something = False
                for enemy in enemies.copy():
                    if enemy.rect().colliderect(rect):
                        pierce = proj.get("pierce", False)
                        if not pierce and proj in self._projectiles:
                            self._projectiles.remove(proj)
                            removed += 1
                        self.game.screenshake = max(16, self.game.screenshake)
                        self.game.audio.play("hit")
                        # Multiplayer servers credit the shooter; single player
                        # falls back to the global coin counter.
                        award = getattr(self.game, "award_coin", None)
                        if award:
                            award(proj.get("owner_id"))
                        else:
                            self.game.cm.coins += 1
                        spawn_hit_sparks(self.game, enemy.rect().center)
                        hits_enemy += 1
                        hit_something = not pierce
                        # Mark and remove enemy immediately for clarity
                        if hasattr(enemy, "alive"):
                            enemy.alive = False
                        try:
                            enemies.remove(enemy)
                        except ValueError:
                            pass
                        if not pierce:
                            break
                # PvP: player projectiles hit other players (multiplayer only —
                # single-player spawns have owner_id None, so this never fires)
                if not hit_something and proj.get("owner_id") is not None:
                    for player in players:
                        if getattr(player, "id", None) == proj.get("owner_id"):
                            continue  # never hit the shooter
                        if abs(player.dashing) < DASH_MIN_ACTIVE_ABS and player.rect().colliderect(rect):
                            if proj in self._projectiles:
                                self._projectiles.remove(proj)
                                if not self._try_absorb(player):
                                    player.lives -= 1
                                self.game.audio.play("hit")
                                self.game.screenshake = max(16, self.game.screenshake)
                                spawn_hit_sparks(self.game, player.rect().center)
                                hits_player += 1
                                removed += 1
                            break
            else:  # enemy owned
                # Player damage (skip if heavily dashing similar to old logic)
                rect = pygame.Rect(proj["pos"][0], proj["pos"][1], 4, 4)
                for player in players:
                    if abs(player.dashing) < DASH_MIN_ACTIVE_ABS and player.rect().colliderect(rect):
                        if proj in self._projectiles:
                            self._projectiles.remove(proj)
                            if not self._try_absorb(player):
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

    @staticmethod
    def _try_absorb(player) -> bool:
        """Let an armed shield absorb the hit instead of costing a life."""
        absorb = getattr(player, "absorb_hit", None)
        return bool(absorb and absorb())

    # --- Rendering Data ------------------------------------------------------
    def get_draw_commands(self):
        """Yield tuples (image, draw_x, draw_y) for active projectiles.

        Keeps renderer/UI unaware of internal structure details.
        """
        for proj in self._projectiles:
            if proj.get("kind") == "star":
                base = self.game.assets.get("star") if hasattr(self.game.assets, "get") else None
                if base is None:
                    base = self.game.assets["projectile"]
                # Spin while flying
                img = pygame.transform.rotate(base, (proj["age"] * 20) % 360)
            else:
                img = self.game.assets["projectile"]
            yield img, proj["pos"][0] - img.get_width() / 2, proj["pos"][1] - img.get_height() / 2


__all__ = ["ProjectileSystem"]
