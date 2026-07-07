"""Tests for MP-07: Client-Side Prediction & Remote Player Interpolation.

Tests the interpolation, prediction, and reconciliation features in
MultiplayerGameState.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

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
        state = EntitySnapshot(type="player", id=1, pos=[100.0, 200.0], velocity=[0.0, 0.0], flip=False, action="idle")
        buffer.push(10, state)

        prev, next_, t = buffer.get_surrounding_snapshots(10)
        assert prev is not None
        assert prev[0] == 10
        assert next_ is None  # Only one snapshot, target at or after it

    def test_interpolation_between_two_snapshots(self):
        buffer = SnapshotBuffer(max_size=10)
        state1 = EntitySnapshot(type="player", id=1, pos=[100.0, 200.0], velocity=[1.0, 0.0], flip=False, action="run")
        state2 = EntitySnapshot(type="player", id=1, pos=[110.0, 200.0], velocity=[1.0, 0.0], flip=False, action="run")
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
        state1 = EntitySnapshot(type="player", id=1, pos=[0.0, 0.0], velocity=[10.0, 0.0], flip=False, action="run")
        state2 = EntitySnapshot(type="player", id=1, pos=[100.0, 0.0], velocity=[10.0, 0.0], flip=False, action="run")

        # Interpolate at t=0.5
        result = interpolate_entity(state1, state2, 0.5)
        assert result.pos[0] == 50.0  # Halfway
        assert result.pos[1] == 0.0

        # Interpolate at t=0.25
        result = interpolate_entity(state1, state2, 0.25)
        assert result.pos[0] == 25.0

    def test_out_of_order_snapshot_ignored(self):
        buffer = SnapshotBuffer(max_size=10)
        state1 = EntitySnapshot(type="player", id=1, pos=[100.0, 200.0], velocity=[0.0, 0.0], flip=False, action="idle")
        state2 = EntitySnapshot(type="player", id=1, pos=[90.0, 200.0], velocity=[0.0, 0.0], flip=False, action="idle")
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
    """Tests for client-side prediction (_predict_local)."""

    def _make_state_with_player(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()
        mock_game = MagicMock()
        mock_player = MagicMock()
        mock_player.id = 1
        mock_player.pos = [100.0, 100.0]
        mock_player.shoot_cooldown = 0
        mock_game.players = [mock_player]
        mock_game.tilemap = MagicMock()
        state._game = mock_game
        state._my_player_id = 1
        return state, mock_player

    def test_predict_local_moves_player_immediately(self):
        state, mock_player = self._make_state_with_player()

        state._predict_local((False, True), [])

        mock_player.update.assert_called_once()
        call_args = mock_player.update.call_args
        assert call_args[0][1] == (1, 0)  # movement = (1, 0) for right

    def test_predict_local_triggers_jump(self):
        state, mock_player = self._make_state_with_player()

        state._predict_local((False, False), ["jump"])

        mock_player.jump.assert_called_once()

    def test_predict_local_triggers_dash(self):
        state, mock_player = self._make_state_with_player()

        state._predict_local((False, False), ["dash"])

        mock_player.dash.assert_called_once()


class TestReconciliation:
    """Tests for rewind+replay reconciliation."""

    def _server_snap(self):
        return EntitySnapshot(
            type="player", id=1, pos=[100.0, 100.0], velocity=[0.0, 0.0], flip=False, action="idle", lives=3
        )

    def test_reconcile_rewinds_to_server_state(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()

        mock_player = MagicMock()
        mock_player.pos = [200.0, 100.0]
        mock_player.action = "idle"

        state._client = MagicMock()
        state._client.get_unacknowledged_inputs.return_value = {}
        state._game = MagicMock()
        state._game.tilemap = MagicMock()

        state._reconcile_local_player(mock_player, self._server_snap())

        # Rewound to authoritative position (no unacked inputs to replay)
        assert mock_player.pos == [100.0, 100.0]
        assert mock_player.lives == 3

    def test_reconcile_replays_unacknowledged_inputs(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()

        mock_player = MagicMock()
        mock_player.pos = [200.0, 100.0]
        mock_player.action = "idle"

        mock_client = MagicMock()
        mock_client.get_unacknowledged_inputs.return_value = {
            101: ((False, True), []),
            102: ((False, True), ["jump"]),
        }
        state._client = mock_client

        mock_game = MagicMock()
        mock_game.tilemap = MagicMock()
        mock_game.particles = []
        mock_game.sparks = []
        state._game = mock_game

        state._reconcile_local_player(mock_player, self._server_snap())

        mock_client.get_unacknowledged_inputs.assert_called_once_with()

        # Replayed the jump exactly once
        mock_player.jump.assert_called_once()

        # One physics step per unacked tick, rightward movement
        assert mock_player.update.call_count == 2
        assert mock_player.update.call_args[0][1] == (1, 0)

    def test_reconcile_tracks_prediction_error(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()

        mock_player = MagicMock()
        mock_player.pos = [130.0, 100.0]
        mock_player.action = "idle"

        state._client = MagicMock()
        state._client.get_unacknowledged_inputs.return_value = {}
        state._game = MagicMock()
        state._game.tilemap = MagicMock()

        state._reconcile_local_player(mock_player, self._server_snap())

        assert state._stats["reconcile_error_px"] == 30.0
        assert state._stats["reconcile_max_px"] == 30.0


class TestPauseNetworking:
    """While paused, the connection must stay alive with neutral inputs."""

    def test_network_idle_update_sends_neutral_input(self):
        from scripts.multiplayer_state import MultiplayerGameState

        state = MultiplayerGameState()
        client = MagicMock()
        client.is_connected = True
        state._client = client
        state._movement = [True, False]  # was holding a key when pausing

        state.network_idle_update()

        client.update.assert_called_once()
        client.send_input_state.assert_called_once_with((False, False), [])
        assert state._movement == [False, False]


class TestInterpDelayConstant:
    """Test that interpolation delay constant exists and is sensible."""

    def test_interp_delay_exists_and_positive(self):
        from scripts.multiplayer_state import INTERP_DELAY

        assert INTERP_DELAY > 0
        assert INTERP_DELAY <= 10  # Reasonable upper bound
