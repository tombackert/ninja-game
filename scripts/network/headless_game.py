"""Headless Game Simulation (MP-06).

Server-side game simulation that runs physics without pygame display or assets.
Uses stub classes for rendering/audio dependencies so Player.update() and
Tilemap work correctly without a display.

Usage:
    game = HeadlessGame(level=0)
    game.add_player(player_id=1)
    game.simulate_tick()
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pygame

from scripts.entities import Player
from scripts.entity_id import EntityIDGenerator
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
    """Server-side game that loads levels and runs physics without rendering.

    Provides the same interface that Player.update() and Tilemap expect
    from a game object, but with stubs for all rendering/audio/UI systems.
    """

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
        """Load level JSON and extract spawn points."""
        path = f"data/maps/{level}.json"
        self.tilemap.load(path, load_entities=False)

        # Extract spawn points (variant 0 = player spawner)
        self._spawn_points: List[List[float]] = []
        self._spawn_index: int = 0

        spawners = self.tilemap.extract([("spawners", 0), ("spawners", 1)], keep=False)
        for spawner in spawners:
            if spawner["variant"] == 0:
                self._spawn_points.append(list(spawner["pos"]))

        # Entity lists
        self.players: List[Player] = []
        self.enemies: List[Any] = []

        # Entity ID generator
        self._id_gen = EntityIDGenerator.get()
        self._id_gen.reset(0)

    def add_player(self, player_id: int) -> Player:
        """Create a new player at the next available spawn point.

        Args:
            player_id: Network player ID to assign

        Returns:
            The created Player entity
        """
        # Pick spawn point (cycle through available ones)
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
            lives=3,
            respawn_pos=list(pos),
        )
        player.skin = 0
        player.air_time = 0
        self.players.append(player)

        # Set self.player to the first player for SnapshotService compatibility
        if len(self.players) == 1:
            self.player = player

        return player

    def remove_player(self, player_id: int) -> Optional[Player]:
        """Remove a player by their network ID.

        Args:
            player_id: Network player ID to remove

        Returns:
            The removed Player, or None if not found
        """
        for i, p in enumerate(self.players):
            if p.id == player_id:
                removed = self.players.pop(i)
                # Update self.player reference
                if self.players:
                    self.player = self.players[0]
                return removed
        return None

    def simulate_tick(self) -> None:
        """Run one simulation tick.

        Applies pending inputs to players, runs physics updates,
        and resets per-frame state.
        """
        self.tick += 1

        # Update each player with their pending movement input
        for player in self.players:
            movement = self._pending_inputs.get(player.id, (0, 0))
            player.update(self.tilemap, movement)

        # Clear pending inputs for this tick
        self._pending_inputs.clear()

        # Reset per-frame state
        self.particles = []
        self.sparks = []
        self.screenshake = max(0, self.screenshake - 1)


__all__ = ["HeadlessGame"]
