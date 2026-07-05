"""Tests for Game Server (MP-04).

Tests the GameServer class including:
- Server initialization and port binding
- Client connection handling
- Input buffering and validation
- Snapshot broadcasting
"""

import time
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List

from scripts.network.game_server import GameServer
from scripts.network.messages import Message
from scripts.network.udp_transport import UDPTransport


@dataclass
class MockPlayer:
    """Mock player for testing."""
    id: int
    pos: List[float] = field(default_factory=lambda: [0.0, 0.0])
    velocity: List[float] = field(default_factory=lambda: [0.0, 0.0])
    flip: bool = False
    action: str = "idle"
    lives: int = 3
    air_time: int = 0
    jumps: int = 2
    wall_slide: bool = False
    dashing: int = 0
    shoot_cooldown: int = 0
    _jumped: bool = False
    _dashed: bool = False

    def jump(self) -> None:
        self._jumped = True

    def dash(self) -> None:
        self._dashed = True

    def set_action(self, action: str) -> None:
        self.action = action


@dataclass
class MockCollectableManager:
    """Mock collectable manager."""
    coins: int = 0


@dataclass
class MockGame:
    """Mock game for testing server without pygame."""
    tick: int = 0
    dead: int = 0
    transition: int = 0
    players: List[MockPlayer] = field(default_factory=list)
    enemies: List[Any] = field(default_factory=list)
    cm: MockCollectableManager = field(default_factory=MockCollectableManager)
    _pending_inputs: Dict[int, tuple] = field(default_factory=dict)


class TestGameServerInit(unittest.TestCase):
    """Tests for server initialization."""

    def test_server_starts_on_port(self):
        """Server should bind to specified port."""
        server = GameServer(port=18001)
        try:
            self.assertEqual(server.port, 18001)
        finally:
            server.shutdown()

    def test_server_with_default_port(self):
        """Server should use default port 7777."""
        # Note: Can't test default port easily as it may be in use
        server = GameServer(port=18002)
        try:
            self.assertIsNotNone(server.transport)
        finally:
            server.shutdown()

    def test_server_context_manager(self):
        """Server should work as context manager."""
        with GameServer(port=18003) as server:
            self.assertEqual(server.port, 18003)


class TestClientConnection(unittest.TestCase):
    """Tests for client connection handling."""

    def test_server_accepts_client(self):
        """Server should accept connection request."""
        server = GameServer(port=18004)
        client = UDPTransport(port=0)

        try:
            # Send connection request
            msg = Message(
                type="connect_request",
                payload={"player_name": "TestPlayer"},
            )
            client.send(msg, ("127.0.0.1", 18004))

            time.sleep(0.02)  # Allow packet to arrive

            # Process on server
            server.update()

            # Check client was registered
            self.assertEqual(server.get_client_count(), 1)

            # Check client received accept
            time.sleep(0.02)
            result = client.receive()
            self.assertIsNotNone(result)
            response, _, _ = result
            self.assertEqual(response.type, "connect_accept")
            self.assertEqual(response.payload["player_id"], 1)

        finally:
            server.shutdown()
            client.close()

    def test_server_rejects_when_full(self):
        """Server should reject connection when at max capacity."""
        server = GameServer(port=18005, max_clients=1)
        client1 = UDPTransport(port=0)
        client2 = UDPTransport(port=0)

        try:
            # First client connects
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client1.send(msg, ("127.0.0.1", 18005))
            time.sleep(0.02)
            server.update()

            # Second client tries to connect
            msg = Message(type="connect_request", payload={"player_name": "P2"})
            client2.send(msg, ("127.0.0.1", 18005))
            time.sleep(0.02)
            server.update()

            # Should still be 1 client
            self.assertEqual(server.get_client_count(), 1)

            # Second client should get rejection
            time.sleep(0.02)
            result = client2.receive()
            self.assertIsNotNone(result)
            response, _, _ = result
            self.assertEqual(response.type, "connect_reject")

        finally:
            server.shutdown()
            client1.close()
            client2.close()

    def test_player_join_callback(self):
        """Server should call on_player_join callback."""
        server = GameServer(port=18006)
        client = UDPTransport(port=0)
        joined_players = []

        server.on_player_join(lambda pid, name: joined_players.append((pid, name)))

        try:
            msg = Message(type="connect_request", payload={"player_name": "Ninja"})
            client.send(msg, ("127.0.0.1", 18006))
            time.sleep(0.02)
            server.update()

            self.assertEqual(len(joined_players), 1)
            self.assertEqual(joined_players[0], (1, "Ninja"))

        finally:
            server.shutdown()
            client.close()


class TestInputHandling(unittest.TestCase):
    """Tests for the state+event input protocol."""

    def test_server_applies_movement_state_and_actions(self):
        """Server should store movement state and apply queued actions."""
        server = GameServer(port=18007)
        player = MockPlayer(id=1)
        game = MockGame(tick=10, players=[player])
        server.set_game(game)
        client = UDPTransport(port=0)

        try:
            # Connect client
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client.send(msg, ("127.0.0.1", 18007))
            time.sleep(0.02)
            server.update()

            # Send input: holding left + a jump action (seq 1)
            input_msg = Message(
                type="input",
                payload={"tick": 15, "move": [True, False], "actions": [[1, "jump"]]},
            )
            client.send(input_msg, ("127.0.0.1", 18007))
            time.sleep(0.02)
            server.update()

            client_state = server.clients.get_all_clients()[0]
            self.assertEqual(client_state.movement, [True, False])
            self.assertEqual(client_state.last_input_tick, 15)
            # Action was applied to the player and drained
            self.assertTrue(player._jumped)
            self.assertEqual(client_state.pending_actions, [])
            # Movement translated into a pending input vector
            self.assertEqual(game._pending_inputs[1], (-1, 0))

        finally:
            server.shutdown()
            client.close()

    def test_server_deduplicates_resent_actions(self):
        """Re-sent actions (same seq) must only be applied once."""
        server = GameServer(port=18008)
        player = MockPlayer(id=1)
        game = MockGame(tick=100, players=[player])
        server.set_game(game)
        client = UDPTransport(port=0)

        try:
            # Connect client
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client.send(msg, ("127.0.0.1", 18008))
            time.sleep(0.02)
            server.update()

            # Same action (seq 1) arrives in two consecutive packets
            for tick in (50, 51):
                input_msg = Message(
                    type="input",
                    payload={"tick": tick, "move": [False, False], "actions": [[1, "dash"]]},
                )
                client.send(input_msg, ("127.0.0.1", 18008))
            time.sleep(0.02)
            server.update()

            client_state = server.clients.get_all_clients()[0]
            self.assertEqual(client_state.last_action_seq, 1)
            self.assertTrue(player._dashed)
            # Reset and re-send the same seq: must not fire again
            player._dashed = False
            input_msg = Message(
                type="input",
                payload={"tick": 52, "move": [False, False], "actions": [[1, "dash"]]},
            )
            client.send(input_msg, ("127.0.0.1", 18008))
            time.sleep(0.02)
            server.update()
            self.assertFalse(player._dashed)

        finally:
            server.shutdown()
            client.close()

    def test_stale_packet_does_not_overwrite_movement(self):
        """An out-of-order older packet must not overwrite newer movement."""
        server = GameServer(port=18018)
        player = MockPlayer(id=1)
        game = MockGame(tick=10, players=[player])
        server.set_game(game)
        client = UDPTransport(port=0)

        try:
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client.send(msg, ("127.0.0.1", 18018))
            time.sleep(0.02)
            server.update()

            client_state = server.clients.get_all_clients()[0]
            # Newer packet first
            client_state.receive_input(20, [False, True], [])
            # Stale packet afterwards (simulated reorder)
            client_state.receive_input(19, [True, False], [])

            self.assertEqual(client_state.movement, [False, True])
            self.assertEqual(client_state.last_input_tick, 20)

        finally:
            server.shutdown()
            client.close()


class TestSnapshotBroadcast(unittest.TestCase):
    """Tests for snapshot broadcasting."""

    def test_server_broadcasts_snapshots(self):
        """Server should broadcast snapshots at regular intervals."""
        server = GameServer(port=18009)
        player = MockPlayer(id=1, pos=[100.0, 200.0])
        game = MockGame(tick=0, players=[player])
        server.set_game(game)
        client = UDPTransport(port=0)

        try:
            # Connect client
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client.send(msg, ("127.0.0.1", 18009))
            time.sleep(0.02)
            server.update()

            # Clear any pending messages
            while client.receive():
                pass

            # Run enough updates to trigger broadcast
            for _ in range(server.SNAPSHOT_INTERVAL + 1):
                game.tick += 1
                server.update()

            time.sleep(0.02)

            # Client should receive a snapshot (skip stragglers such as a
            # late-arriving connect_accept — UDP gives no ordering guarantee)
            snapshot_msg = None
            deadline = time.time() + 1.0
            while time.time() < deadline:
                result = client.receive()
                if result is None:
                    time.sleep(0.01)
                    continue
                msg, _, _ = result
                if msg.type == "snapshot":
                    snapshot_msg = msg
                    break
            self.assertIsNotNone(snapshot_msg)
            self.assertIn("tick", snapshot_msg.payload)

        finally:
            server.shutdown()
            client.close()


class TestHeartbeat(unittest.TestCase):
    """Tests for heartbeat/keep-alive."""

    def test_server_responds_to_heartbeat(self):
        """Server should respond to heartbeat with ack."""
        server = GameServer(port=18010)
        client = UDPTransport(port=0)

        try:
            # Connect client
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client.send(msg, ("127.0.0.1", 18010))
            time.sleep(0.02)
            server.update()

            # Clear all pending messages
            time.sleep(0.02)
            while client.receive():
                pass

            # Send heartbeat
            client_time = time.time()
            heartbeat = Message(
                type="heartbeat",
                payload={"client_time": client_time},
            )
            client.send(heartbeat, ("127.0.0.1", 18010))
            time.sleep(0.02)
            server.update()

            # Should receive heartbeat_ack
            time.sleep(0.02)
            result = client.receive()
            self.assertIsNotNone(result)
            ack_msg, _, _ = result
            self.assertEqual(ack_msg.type, "heartbeat_ack")
            self.assertEqual(ack_msg.payload["client_time"], client_time)

        finally:
            server.shutdown()
            client.close()


class TestClientDisconnection(unittest.TestCase):
    """Tests for client disconnection."""

    def test_server_handles_graceful_disconnect(self):
        """Server should handle graceful disconnect."""
        server = GameServer(port=18011)
        client = UDPTransport(port=0)
        left_players = []

        server.on_player_leave(lambda pid, reason: left_players.append((pid, reason)))

        try:
            # Connect client
            msg = Message(type="connect_request", payload={"player_name": "P1"})
            client.send(msg, ("127.0.0.1", 18011))
            time.sleep(0.02)
            server.update()

            self.assertEqual(server.get_client_count(), 1)

            # Send disconnect
            disconnect = Message(type="disconnect", payload={})
            client.send(disconnect, ("127.0.0.1", 18011))
            time.sleep(0.02)
            server.update()

            # Client should be removed
            self.assertEqual(server.get_client_count(), 0)
            self.assertEqual(len(left_players), 1)
            self.assertEqual(left_players[0][1], "disconnected")

        finally:
            server.shutdown()
            client.close()


class TestClientState(unittest.TestCase):
    """Tests for ClientState and ClientManager."""

    def test_client_state_input_model(self):
        """ClientState should track movement state and dedupe actions."""
        from scripts.network.client_state import ClientState

        client = ClientState(
            player_id=1,
            player_name="Test",
            address=("127.0.0.1", 12345),
        )

        client.receive_input(10, [True, False], [[1, "jump"]])
        client.receive_input(11, [True, False], [[1, "jump"], [2, "dash"]])

        self.assertEqual(client.movement, [True, False])
        self.assertEqual(client.last_input_tick, 11)
        # jump (seq 1) only queued once despite being re-sent
        self.assertEqual(client.drain_actions(), ["jump", "dash"])
        self.assertEqual(client.drain_actions(), [])

    def test_client_manager_add_remove(self):
        """ClientManager should add and remove clients."""
        from scripts.network.client_state import ClientManager

        manager = ClientManager(max_clients=2)
        addr1 = ("127.0.0.1", 10001)
        addr2 = ("127.0.0.1", 10002)

        # Add clients
        c1 = manager.add_client(addr1, "Player1")
        c2 = manager.add_client(addr2, "Player2")

        self.assertEqual(manager.client_count, 2)
        self.assertEqual(c1.player_id, 1)
        self.assertEqual(c2.player_id, 2)

        # Remove client
        removed = manager.remove_client(addr1)
        self.assertEqual(removed.player_name, "Player1")
        self.assertEqual(manager.client_count, 1)


if __name__ == "__main__":
    unittest.main()
