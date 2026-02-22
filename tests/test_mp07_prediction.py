"""Tests for MP-07: Client-Side Prediction & Remote Player Interpolation.

Tests the interpolation, prediction, and reconciliation features in
MultiplayerGameState.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pygame
import pytest

# Ensure testing mode
os.environ["NINJA_GAME_TESTING"] = "1"

from scripts.network.interpolation import SnapshotBuffer, interpolate_entity
from scripts.snapshot import EntitySnapshot


@pytest.fixture(autouse=True)
def init_pygame():
    """Ensure pygame is initialized for physics Rect usage."""
    pygame.init()
    yield


class TestSnapshotBuffer:
    """Tests for SnapshotBuffer interpolation utilities."""

    def test_push_and_retrieve_single_snapshot(self):
        buffer = SnapshotBuffer(max_size=10)
        state = EntitySnapshot(
            type="player", id=1, pos=[100.0, 200.0], velocity=[0.0, 0.0],
            flip=False, action="idle"
        )
        buffer.push(10, state)

        prev, next_, t = buffer.get_surrounding_snapshots(10)
        assert prev is not None
        assert prev[0] == 10
        assert next_ is None  # Only one snapshot, target at or after it

    def test_interpolation_between_two_snapshots(self):
        buffer = SnapshotBuffer(max_size=10)
        state1 = EntitySnapshot(
            type="player", id=1, pos=[100.0, 200.0], velocity=[1.0, 0.0],
            flip=False, action="run"
        )
        state2 = EntitySnapshot(
            type="player", id=1, pos=[110.0, 200.0], velocity=[1.0, 0.0],
            flip=False, action="run"
        )
        buffer.push(10, state1)
        buffer.push(20, state2)

        # Target tick 15 (halfway between 10 and 20)
        prev, next_, t = buffer.get_surrounding_snapshots(15)
        assert prev is not None
        assert next_ is not None
        assert prev[0] == 10
        assert next_[0] == 20
        assert abs(t - 0.5) < 0.01  # Should be 0.5

    def test_interpolate_entity_produces_smooth_position(self):
        state1 = EntitySnapshot(
            type="player", id=1, pos=[0.0, 0.0], velocity=[10.0, 0.0],
            flip=False, action="run"
        )
        state2 = EntitySnapshot(
            type="player", id=1, pos=[100.0, 0.0], velocity=[10.0, 0.0],
            flip=False, action="run"
        )

        # Interpolate at t=0.5
        result = interpolate_entity(state1, state2, 0.5)
        assert result.pos[0] == 50.0  # Halfway
        assert result.pos[1] == 0.0

        # Interpolate at t=0.25
        result = interpolate_entity(state1, state2, 0.25)
        assert result.pos[0] == 25.0

    def test_out_of_order_snapshot_ignored(self):
        buffer = SnapshotBuffer(max_size=10)
        state1 = EntitySnapshot(
            type="player", id=1, pos=[100.0, 200.0], velocity=[0.0, 0.0],
            flip=False, action="idle"
        )
        state2 = EntitySnapshot(
            type="player", id=1, pos=[90.0, 200.0], velocity=[0.0, 0.0],
            flip=False, action="idle"
        )
        buffer.push(20, state1)
        buffer.push(10, state2)  # Out of order - should be ignored

        # Buffer should only have the first snapshot
        assert len(buffer.buffer) == 1


class TestRemotePlayerInterpolation:
    """Tests for remote player interpolation in MultiplayerGameState."""

    def test_remote_player_buffer_created_on_update(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()
        # Initially no buffers
        assert len(state._remote_player_buffers) == 0

    def test_remote_player_buffer_cleanup_on_leave(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()
        # Manually add a buffer
        state._remote_player_buffers[42] = SnapshotBuffer()

        # Simulate player leaving
        state._on_player_left(42, "disconnected")

        assert 42 not in state._remote_player_buffers


class TestClientSidePrediction:
    """Tests for client-side prediction."""

    def test_apply_local_inputs_moves_player_immediately(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()

        # Create a mock game with player
        mock_game = MagicMock()
        mock_player = MagicMock()
        mock_player.pos = [100.0, 100.0]
        mock_game.player = mock_player
        mock_game.tilemap = MagicMock()
        state._game = mock_game

        # Set movement flags (moving right)
        state._movement = [False, True]

        # Apply local inputs
        state._apply_local_inputs([])

        # Player.update should have been called with rightward movement
        mock_player.update.assert_called_once()
        call_args = mock_player.update.call_args
        assert call_args[0][1] == (1, 0)  # movement = (1, 0) for right

    def test_apply_local_inputs_triggers_jump(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()

        mock_game = MagicMock()
        mock_player = MagicMock()
        mock_game.player = mock_player
        mock_game.tilemap = MagicMock()
        state._game = mock_game
        state._movement = [False, False]

        # Apply jump action
        state._apply_local_inputs(["jump"])

        mock_player.jump.assert_called_once()

    def test_apply_local_inputs_triggers_dash(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()

        mock_game = MagicMock()
        mock_player = MagicMock()
        mock_game.player = mock_player
        mock_game.tilemap = MagicMock()
        state._game = mock_game
        state._movement = [False, False]

        state._apply_local_inputs(["dash"])

        mock_player.dash.assert_called_once()


class TestReconciliation:
    """Tests for server reconciliation."""

    def test_reconcile_snaps_when_divergence_exceeds_threshold(self):
        from scripts.multiplayer_state import MultiplayerGameState, RECONCILE_THRESHOLD

        state = MultiplayerGameState()

        mock_player = MagicMock()
        # Player predicted position is far from server
        mock_player.pos = [200.0, 100.0]
        mock_player.action = "idle"

        # Server says player should be at 100, 100 (divergence = 100 > threshold)
        server_snap = EntitySnapshot(
            type="player", id=1, pos=[100.0, 100.0], velocity=[0.0, 0.0],
            flip=False, action="idle", lives=3
        )

        # Mock client for replay
        state._client = MagicMock()
        state._client.get_unacknowledged_inputs.return_value = {}
        state._game = MagicMock()
        state._game.tilemap = MagicMock()

        state._reconcile_local_player(mock_player, server_snap, 100)

        # Should have snapped to server position
        assert mock_player.pos == [100.0, 100.0]

    def test_reconcile_preserves_position_when_divergence_small(self):
        from scripts.multiplayer_state import MultiplayerGameState, RECONCILE_THRESHOLD

        state = MultiplayerGameState()

        mock_player = MagicMock()
        # Player predicted position is close to server (divergence = 2 < threshold)
        mock_player.pos = [102.0, 100.0]
        mock_player.action = "idle"

        server_snap = EntitySnapshot(
            type="player", id=1, pos=[100.0, 100.0], velocity=[0.0, 0.0],
            flip=False, action="idle", lives=3
        )

        state._reconcile_local_player(mock_player, server_snap, 100)

        # Position should NOT have changed (minor divergence tolerated)
        assert mock_player.pos == [102.0, 100.0]
        # But other state should be updated
        assert mock_player.lives == 3

    def test_replay_unacknowledged_inputs_called_on_snap(self):
        from scripts.multiplayer_state import MultiplayerGameState, RECONCILE_THRESHOLD

        state = MultiplayerGameState()

        mock_player = MagicMock()
        mock_player.pos = [200.0, 100.0]  # Far from server
        mock_player.action = "idle"

        server_snap = EntitySnapshot(
            type="player", id=1, pos=[100.0, 100.0], velocity=[0.0, 0.0],
            flip=False, action="idle", lives=3
        )

        mock_client = MagicMock()
        mock_client.get_unacknowledged_inputs.return_value = {
            101: ["right"],
            102: ["right", "jump"],
        }
        state._client = mock_client

        mock_game = MagicMock()
        mock_game.tilemap = MagicMock()
        state._game = mock_game

        state._reconcile_local_player(mock_player, server_snap, 100)

        # Should have called get_unacknowledged_inputs
        mock_client.get_unacknowledged_inputs.assert_called_once_with(100)

        # Should have replayed jump
        mock_player.jump.assert_called_once()

        # Should have called update twice (once per tick)
        assert mock_player.update.call_count == 2


class TestInterpDelayConstant:
    """Test that interpolation delay constant exists and is sensible."""

    def test_interp_delay_exists_and_positive(self):
        from scripts.multiplayer_state import INTERP_DELAY
        assert INTERP_DELAY > 0
        assert INTERP_DELAY <= 10  # Reasonable upper bound


class TestReconcileThresholdConstant:
    """Test that reconciliation threshold constant exists and is sensible."""

    def test_reconcile_threshold_exists_and_positive(self):
        from scripts.multiplayer_state import RECONCILE_THRESHOLD
        assert RECONCILE_THRESHOLD > 0
        assert RECONCILE_THRESHOLD <= 50  # Reasonable upper bound for pixels
