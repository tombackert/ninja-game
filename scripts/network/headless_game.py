"""Headless Game Simulation (MP-06).

Server-side game simulation that runs the full world — players, enemies,
projectiles and collectables — without pygame display or assets. Uses stub
classes for rendering/audio dependencies so entity physics and the Tilemap
work correctly without a display.

Multiplayer rules implemented here (server-authoritative):
- Per-player coins/ammo (``player.mp_coins`` / ``player.mp_ammo``), captured
  into snapshots by SnapshotService.
- Per-player death & respawn: fatal falls and projectile hits cost a life
  and respawn the player at their spawn point; at 0 lives the player
  respawns with full lives (arena style).
- Collectables (coins/ammo pickups) are tracked by stable IDs derived from
  tilemap extraction order — identical on client and server because both
  load the same level JSON. Picked-up IDs accumulate in ``collected_ids``.
- Enemy AI targets the nearest player.

Usage:
    game = HeadlessGame(level=0)
    game.add_player(player_id=1)
    game.simulate_tick()
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pygame

from scripts.constants import AIR_TIME_FATAL, DASH_MIN_ACTIVE_ABS, PROJECTILE_SPEED
from scripts.entities import Enemy, Player
from scripts.entity_id import EntityIDGenerator
from scripts.projectile_system import ProjectileSystem
from scripts.tilemap import Tilemap


class StubAnimation:
    """Minimal animation stub that satisfies PhysicsEntity.set_action()."""

    done = False
    frame = 0

    def copy(self) -> StubAnimation:
        return StubAnimation()

    def update(self) -> None:
        pass

    def img(self) -> None:
        return None


class StubAssets(dict):
    """Dict subclass that auto-creates StubAnimation for any missing key."""

    def __missing__(self, key: str) -> StubAnimation:
        anim = StubAnimation()
        self[key] = anim
        return anim


class StubAudio:
    """No-op audio service for headless mode."""

    def play(self, *args: Any, **kwargs: Any) -> None:
        pass

    def trigger_ducking(self, **kwargs: Any) -> None:
        pass

    def play_music(self, *args: Any, **kwargs: Any) -> None:
        pass

    def update(self) -> None:
        pass


class StubCM:
    """Minimal CollectableManager stub for headless mode."""

    coins: int = 0
    gun: bool = False
    ammo: int = 0


class HeadlessGame:
    """Server-side game that loads levels and runs the full world simulation.

    Provides the same interface that entities, ProjectileSystem and Tilemap
    expect from a game object, but with stubs for rendering/audio/UI systems.
    """

    MP_START_LIVES = 3
    MP_START_AMMO = 15
    AMMO_PICKUP_AMOUNT = 5

    def __init__(self, level: int = 0) -> None:
        self.assets: Any = StubAssets()
        self.audio: Any = StubAudio()
        self.particles: List[Any] = []
        self.sparks: List[Any] = []
        self.screenshake: int = 0
        self.dead: int = 0
        self.transition: int = 0
        self.tick: int = 0
        self.cm: Any = StubCM()
        self.running: bool = True
        self.level: int = level

        # Pending inputs from clients: {player_id: (dx, dy)}
        self._pending_inputs: Dict[int, Tuple[float, float]] = {}

        # Initialize tilemap and load level
        self.tilemap = Tilemap(self)
        self._load_level(level)

    def _load_level(self, level: int) -> None:
        """Load level JSON, spawn enemies and register collectables."""
        path = f"data/maps/{level}.json"
        self.tilemap.load(path, load_entities=False)

        # Entity ID generator (enemies + projectiles share it; players get
        # their IDs from the server's ClientManager)
        self._id_gen = EntityIDGenerator.get()
        self._id_gen.reset(0)

        # Entity lists
        self.players: List[Player] = []
        self.enemies: List[Enemy] = []

        # Extract spawn points (variant 0) and enemies (variant 1)
        self._spawn_points: List[List[float]] = []
        self._spawn_index: int = 0
        for spawner in self.tilemap.extract([("spawners", 0), ("spawners", 1)], keep=False):
            if spawner["variant"] == 0:
                self._spawn_points.append(list(spawner["pos"]))
            else:
                self.enemies.append(Enemy(self, spawner["pos"], (8, 15), self._id_gen.next_id()))

        # Collectables with stable IDs (extraction order: coins, then ammo —
        # must mirror CollectableManager.load_collectables_from_tilemap)
        self.collectables: Dict[int, Dict[str, Any]] = {}
        self.collected_ids: List[int] = []
        next_cid = 0
        for kind, tile_key in (("coin", "coin"), ("ammo", "ammo")):
            for tile in self.tilemap.extract([(tile_key, 0)], keep=False):
                rect = pygame.Rect(tile["pos"][0], tile["pos"][1], 16, 16)
                self.collectables[next_cid] = {"kind": kind, "rect": rect}
                next_cid += 1

        # Projectile system (server-authoritative)
        self.projectiles = ProjectileSystem(self)

    def add_player(self, player_id: int) -> Player:
        """Create a new player at the next available spawn point."""
        if self._spawn_points:
            pos = list(self._spawn_points[self._spawn_index % len(self._spawn_points)])
            self._spawn_index += 1
        else:
            pos = [50.0, 50.0]  # fallback

        player = Player(
            self,
            pos,
            (8, 15),
            player_id,
            lives=self.MP_START_LIVES,
            respawn_pos=list(pos),
        )
        player.skin = 0
        player.air_time = 0
        player.mp_coins = 0
        player.mp_ammo = self.MP_START_AMMO
        self.players.append(player)

        # Keep self.player pointing at a valid entity (enemy AI + snapshot
        # compatibility); it is re-targeted per enemy during simulate_tick.
        if len(self.players) == 1:
            self.player = player

        return player

    def remove_player(self, player_id: int) -> Optional[Player]:
        """Remove a player by their network ID."""
        for i, p in enumerate(self.players):
            if p.id == player_id:
                removed = self.players.pop(i)
                if self.players:
                    self.player = self.players[0]
                return removed
        return None

    def player_shoot(self, player: Player) -> bool:
        """Multiplayer shoot: per-player ammo, no settings dependency."""
        if player.shoot_cooldown > 0 or getattr(player, "mp_ammo", 0) <= 0:
            return False
        direction = -PROJECTILE_SPEED if player.flip else PROJECTILE_SPEED
        self.projectiles.spawn(
            player.rect().centerx + (7 * (-1 if player.flip else 1)),
            player.rect().centery,
            direction,
            "player",
            owner_id=player.id,
        )
        player.mp_ammo -= 1
        player.shoot_cooldown = 10
        return True

    def award_coin(self, player_id: Optional[int], amount: int = 1) -> None:
        """Credit coins to a specific player (kill rewards)."""
        if player_id is None:
            return
        for p in self.players:
            if p.id == player_id:
                p.mp_coins += amount
                return

    def _respawn(self, player: Player, lose_life: bool) -> None:
        """Reset a player to their spawn point."""
        if lose_life:
            player.lives -= 1
        if player.lives < 1:
            player.lives = self.MP_START_LIVES  # arena style: always back in
        player.pos = list(player.respawn_pos)
        player.velocity = [0, 0]
        player.air_time = 0
        player.dashing = 0
        player.jumps = 1

    def _nearest_player(self, enemy: Enemy) -> Optional[Player]:
        """Find the player closest to an enemy (AI targeting)."""
        best = None
        best_dist = float("inf")
        for p in self.players:
            d = abs(p.pos[0] - enemy.pos[0]) + abs(p.pos[1] - enemy.pos[1])
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def simulate_tick(self) -> None:
        """Run one authoritative simulation tick (players, enemies,
        projectiles, collectables, deaths/respawns)."""
        self.tick += 1

        # --- Players: physics + fatal fall handling ---
        for player in self.players:
            movement = self._pending_inputs.get(player.id, (0, 0))
            player.update(self.tilemap, movement)
            if player.air_time > AIR_TIME_FATAL:
                self._respawn(player, lose_life=True)
        self._pending_inputs.clear()
        # The global death counter is meaningless with per-player respawn.
        self.dead = 0

        # --- Enemies: AI targets nearest player; dash kills for everyone ---
        # (idle until at least one player is connected — Enemy.update and its
        # policy dereference game.player)
        for enemy in self.enemies.copy() if self.players else []:
            target = self._nearest_player(enemy)
            if target is not None:
                self.player = target
            kill = enemy.update(self.tilemap, (0, 0))
            if kill:
                # Enemy.update credited the dash kill via award_coin
                self.enemies.remove(enemy)
                continue
            # Dash kills by players other than the AI target
            for p in self.players:
                if p is target:
                    continue
                if abs(p.dashing) >= DASH_MIN_ACTIVE_ABS and enemy.rect().colliderect(p.rect()):
                    self.award_coin(p.id)
                    self.enemies.remove(enemy)
                    break

        # --- Projectiles (handles enemy hits, PvP hits, tile impacts) ---
        self.projectiles.update(self.tilemap, self.players, self.enemies)

        # --- Respawn players killed by projectiles ---
        for player in self.players:
            if player.lives < 1:
                self._respawn(player, lose_life=False)

        # --- Collectable pickups (first player to touch wins) ---
        for cid, item in list(self.collectables.items()):
            for p in self.players:
                if item["rect"].colliderect(p.rect()):
                    if item["kind"] == "coin":
                        p.mp_coins += 1
                    else:
                        p.mp_ammo += self.AMMO_PICKUP_AMOUNT
                    del self.collectables[cid]
                    self.collected_ids.append(cid)
                    break

        # --- Per-frame cleanup (visual-only state has no server meaning) ---
        self.particles = []
        self.sparks = []
        self.screenshake = max(0, self.screenshake - 1)


__all__ = ["HeadlessGame"]
