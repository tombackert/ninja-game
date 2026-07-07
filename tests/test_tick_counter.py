"""Tests for the global tick counter (MP-01).

The tick counter is critical for multiplayer synchronization - all network
messages, snapshots, and reconciliation depend on a shared tick reference.
"""

import os


# Set testing environment before imports
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

from game import Game
from scripts.snapshot import SimulationSnapshot, SnapshotService


class TestTickCounterInitialization:
    """Tests for tick counter initialization."""

    def test_game_tick_starts_at_zero(self):
        """Verify that a new Game instance has tick initialized to 0."""
        game = Game()
        assert hasattr(game, "tick"), "Game should have a 'tick' attribute"
        assert game.tick == 0, "Game tick should start at 0"


class TestSnapshotTickCapture:
    """Tests for tick capture in snapshots."""

    def test_snapshot_captures_game_tick(self):
        """Verify that SnapshotService.capture() uses the actual game tick."""
        game = Game()
        game.load_level(0)

        # Set tick to a known value
        game.tick = 42

        snapshot = SnapshotService.capture(game)

        assert snapshot.tick == 42, "Snapshot should capture the game's tick value"

    def test_snapshot_captures_zero_tick_for_new_game(self):
        """Verify that a new game's snapshot has tick=0."""
        game = Game()
        game.load_level(0)

        snapshot = SnapshotService.capture(game)

        assert snapshot.tick == 0, "New game snapshot should have tick=0"


class TestSnapshotTickRestore:
    """Tests for tick restoration from snapshots."""

    def test_snapshot_restore_sets_tick(self):
        """Verify that SnapshotService.restore() restores the tick value."""
        game = Game()
        game.load_level(0)

        # Create a snapshot with a specific tick
        game.tick = 100
        snapshot = SnapshotService.capture(game)

        # Mutate the tick
        game.tick = 999

        # Restore
        SnapshotService.restore(game, snapshot)

        assert game.tick == 100, "Restore should set tick to snapshot value"

    def test_snapshot_roundtrip_preserves_tick(self):
        """Verify tick is preserved through capture/restore cycle."""
        game = Game()
        game.load_level(0)

        game.tick = 12345

        # Capture
        snapshot = SnapshotService.capture(game)

        # Mutate
        game.tick = 0

        # Restore
        SnapshotService.restore(game, snapshot)

        assert game.tick == 12345, "Tick should survive roundtrip"


class TestSnapshotTickSerialization:
    """Tests for tick serialization/deserialization."""

    def test_serialize_includes_tick(self):
        """Verify that serialized snapshot includes the tick field."""
        snapshot = SimulationSnapshot(
            tick=500,
            rng_state=(),
            players=[],
            enemies=[],
            projectiles=[],
            score=0,
            dead_count=0,
            transition=0,
        )

        serialized = SnapshotService.serialize(snapshot)

        assert "tick" in serialized, "Serialized snapshot should include tick"
        assert serialized["tick"] == 500, "Serialized tick should match"

    def test_deserialize_restores_tick(self):
        """Verify that deserialization restores the tick field."""
        data = {
            "tick": 750,
            "rng_state": [],
            "players": [],
            "enemies": [],
            "projectiles": [],
            "score": 0,
            "dead_count": 0,
            "transition": 0,
        }

        snapshot = SnapshotService.deserialize(data)

        assert snapshot.tick == 750, "Deserialized tick should match"

    def test_deserialize_defaults_tick_to_zero(self):
        """Verify that deserialization defaults tick to 0 if missing."""
        data = {
            "rng_state": [],
            "players": [],
            "enemies": [],
            "projectiles": [],
            "score": 0,
            "dead_count": 0,
            "transition": 0,
        }

        snapshot = SnapshotService.deserialize(data)

        assert snapshot.tick == 0, "Missing tick should default to 0"


class TestTickIncrementInGameState:
    """Tests for tick increment during GameState.update()."""

    def test_tick_increments_each_update(self):
        """Verify that tick increments exactly once per GameState.update() call."""
        from scripts.state_manager import GameState, StateManager

        sm = StateManager()
        gs = GameState()
        sm.push(gs)

        initial_tick = gs.game.tick
        assert initial_tick == 0, "Initial tick should be 0"

        # First update
        gs.update(dt=1 / 60)
        assert gs.game.tick == initial_tick + 1, "Tick should increment by 1"

        # Second update
        gs.update(dt=1 / 60)
        assert gs.game.tick == initial_tick + 2, "Tick should increment again"

        # Third update
        gs.update(dt=1 / 60)
        assert gs.game.tick == initial_tick + 3, "Tick should continue incrementing"

    def test_tick_does_not_increment_when_paused(self):
        """Verify that tick does NOT increment when game is paused."""
        from scripts.state_manager import GameState, StateManager

        sm = StateManager()
        gs = GameState()
        sm.push(gs)

        # Run a few updates to advance tick
        for _ in range(5):
            gs.update(dt=1 / 60)

        tick_before_pause = gs.game.tick
        assert tick_before_pause == 5, "Should have 5 ticks"

        # Simulate pause freeze (this is how PauseState prevents updates)
        gs.game._paused_freeze = True

        # Update while paused
        gs.update(dt=1 / 60)
        gs.update(dt=1 / 60)

        assert gs.game.tick == tick_before_pause, "Tick should not increment when paused"

        # Unpause
        gs.game._paused_freeze = False

        # Update after unpause
        gs.update(dt=1 / 60)

        assert gs.game.tick == tick_before_pause + 1, "Tick should resume after unpause"
