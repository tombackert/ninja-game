"""Integration tests for multiplayer pipeline (MP-06).

Tests the full HeadlessGame + GameServer + GameClient pipeline end-to-end.
Uses ports 20001+ to avoid conflicts with existing tests.
"""

from __future__ import annotations

import os
import time

import pygame
import pytest

# Ensure testing mode
os.environ["NINJA_GAME_TESTING"] = "1"

from scripts.network.game_client import GameClient
from scripts.network.game_server import GameServer
from scripts.network.headless_game import HeadlessGame


@pytest.fixture(autouse=True)
def init_pygame():
    """Ensure pygame is initialized for physics Rect usage."""
    pygame.init()
    yield


def _pump(server: GameServer, clients: list[GameClient], ticks: int = 1) -> None:
    """Run server + client update loops for N ticks."""
    for _ in range(ticks):
        server.update()
        for c in clients:
            c.update()
        time.sleep(0.005)


class TestHeadlessGame:
    """Tests for HeadlessGame in isolation."""

    def test_create_headless_game(self):
        game = HeadlessGame(level=0)
        assert game.tick == 0
        assert game.tilemap is not None
        assert game.players == []

    def test_add_and_remove_player(self):
        game = HeadlessGame(level=0)
        player = game.add_player(player_id=1)
        assert player.id == 1
        assert len(game.players) == 1
        assert game.player == player

        player2 = game.add_player(player_id=2)
        assert len(game.players) == 2

        removed = game.remove_player(1)
        assert removed is not None
        assert removed.id == 1
        assert len(game.players) == 1
        assert game.player == player2

    def test_simulate_tick_increments(self):
        game = HeadlessGame(level=0)
        game.add_player(player_id=1)
        assert game.tick == 0
        game.simulate_tick()
        assert game.tick == 1
        game.simulate_tick()
        assert game.tick == 2

    def test_pending_inputs_applied(self):
        game = HeadlessGame(level=0)
        player = game.add_player(player_id=1)
        initial_pos = list(player.pos)

        # Apply rightward movement for several ticks
        for _ in range(10):
            game._pending_inputs[1] = (1, 0)
            game.simulate_tick()

        # Player should have moved right
        assert player.pos[0] > initial_pos[0]

    def test_remove_nonexistent_player(self):
        game = HeadlessGame(level=0)
        result = game.remove_player(999)
        assert result is None


class TestMultiplayerIntegration:
    """End-to-end tests with HeadlessGame + GameServer + GameClient."""

    def test_client_connects_and_receives_snapshot(self):
        game = HeadlessGame(level=0)
        server = GameServer(port=20001, max_clients=4, game=game)
        server.on_player_join(lambda pid, name: game.add_player(pid))
        server.on_player_leave(lambda pid, reason: game.remove_player(pid))

        client = GameClient(server_host="127.0.0.1", server_port=20001, player_name="Test1")
        client.connect()

        try:
            # Run enough ticks for connection + snapshot broadcast
            _pump(server, [client], ticks=20)

            assert client.is_connected
            assert client.player_id is not None
            assert len(game.players) == 1

            # Run more ticks to get a snapshot
            for _ in range(10):
                game.simulate_tick()
                server.update()
                client.update()
                time.sleep(0.005)

            snapshot = client.get_latest_snapshot()
            assert snapshot is not None
            assert len(snapshot.players) == 1
            assert snapshot.players[0].id == client.player_id
        finally:
            server.shutdown()
            client.close()

    def test_inputs_move_player(self):
        game = HeadlessGame(level=0)
        server = GameServer(port=20002, max_clients=4, game=game)
        server.on_player_join(lambda pid, name: game.add_player(pid))
        server.on_player_leave(lambda pid, reason: game.remove_player(pid))

        client = GameClient(server_host="127.0.0.1", server_port=20002, player_name="Mover")
        client.connect()

        try:
            # Connect
            _pump(server, [client], ticks=20)
            assert client.is_connected

            # Record initial position from snapshot
            for _ in range(10):
                game.simulate_tick()
                server.update()
                client.update()
                time.sleep(0.005)

            initial_snapshot = client.get_latest_snapshot()
            assert initial_snapshot is not None
            initial_x = initial_snapshot.players[0].pos[0]

            # Hold "right" for several ticks
            for i in range(30):
                client.send_input_state((False, True), [])
                server.process_inputs()
                game.simulate_tick()
                server.post_tick()
                client.update()
                time.sleep(0.005)

            final_snapshot = client.get_latest_snapshot()
            assert final_snapshot is not None
            final_x = final_snapshot.players[0].pos[0]

            # Player should have moved right
            assert final_x > initial_x
        finally:
            server.shutdown()
            client.close()

    def test_two_clients_see_each_other(self):
        game = HeadlessGame(level=0)
        server = GameServer(port=20003, max_clients=4, game=game)
        server.on_player_join(lambda pid, name: game.add_player(pid))
        server.on_player_leave(lambda pid, reason: game.remove_player(pid))

        client1 = GameClient(server_host="127.0.0.1", server_port=20003, player_name="P1")
        client2 = GameClient(server_host="127.0.0.1", server_port=20003, player_name="P2")
        client1.connect()

        try:
            # Connect client 1
            _pump(server, [client1], ticks=15)
            assert client1.is_connected

            # Connect client 2
            client2.connect()
            _pump(server, [client1, client2], ticks=15)
            assert client2.is_connected

            assert len(game.players) == 2

            # Run ticks to broadcast snapshot
            for _ in range(15):
                game.simulate_tick()
                server.update()
                client1.update()
                client2.update()
                time.sleep(0.005)

            # Both clients should see 2 players
            snap1 = client1.get_latest_snapshot()
            snap2 = client2.get_latest_snapshot()
            assert snap1 is not None
            assert snap2 is not None
            assert len(snap1.players) == 2
            assert len(snap2.players) == 2
        finally:
            server.shutdown()
            client1.close()
            client2.close()

    def test_disconnect_removes_player(self):
        game = HeadlessGame(level=0)
        server = GameServer(port=20004, max_clients=4, game=game)
        server.on_player_join(lambda pid, name: game.add_player(pid))
        server.on_player_leave(lambda pid, reason: game.remove_player(pid))

        client1 = GameClient(server_host="127.0.0.1", server_port=20004, player_name="Stay")
        client2 = GameClient(server_host="127.0.0.1", server_port=20004, player_name="Leave")
        client1.connect()

        try:
            _pump(server, [client1], ticks=15)
            client2.connect()
            _pump(server, [client1, client2], ticks=15)
            assert len(game.players) == 2

            # Disconnect client 2
            client2.disconnect()
            _pump(server, [client1], ticks=15)

            assert len(game.players) == 1

            # Run more ticks to get updated snapshot
            for _ in range(10):
                game.simulate_tick()
                server.update()
                client1.update()
                time.sleep(0.005)

            snap = client1.get_latest_snapshot()
            assert snap is not None
            assert len(snap.players) == 1
        finally:
            server.shutdown()
            client1.close()
            client2.close()
