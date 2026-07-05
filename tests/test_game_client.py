"""Tests for Game Client (MP-05).

Tests the GameClient class including:
- Connection lifecycle (connect, reject, retry, timeout)
- Input sending and history
- Snapshot reception (full and delta)
- Heartbeat and RTT measurement
- Disconnection (graceful, server shutdown, timeout)
- Player join/leave events
"""

import time
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List

from scripts.network.client_state import ConnectionState
from scripts.network.delta import compute_delta
from scripts.network.game_client import (
    CONNECT_RETRY_INTERVAL,
    HEARTBEAT_INTERVAL,
    MAX_CONNECT_ATTEMPTS,
    SERVER_TIMEOUT,
    GameClient,
)
from scripts.network.game_server import GameServer
from scripts.network.messages import Message
from scripts.network.udp_transport import UDPTransport
from scripts.snapshot import EntitySnapshot, SimulationSnapshot, SnapshotService


# --- Mock objects (reuse pattern from test_game_server.py) ---


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
    """Mock game for testing without pygame."""

    tick: int = 0
    dead: int = 0
    transition: int = 0
    players: List[MockPlayer] = field(default_factory=list)
    enemies: List[Any] = field(default_factory=list)
    cm: MockCollectableManager = field(default_factory=MockCollectableManager)
    _pending_inputs: Dict[int, tuple] = field(default_factory=dict)


# --- Helper ---


def _connect_client_to_server(
    client: GameClient, server: GameServer, sleep: float = 0.02
) -> None:
    """Helper: drive a client through the connect handshake."""
    client.connect()
    time.sleep(sleep)
    server.update()
    time.sleep(sleep)
    client.update()


# --- Test classes ---


class TestClientInit(unittest.TestCase):
    """Tests for client initialization."""

    def test_client_starts_disconnected(self):
        """Client should start in DISCONNECTED state."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
            self.assertFalse(client.is_connected)
            self.assertIsNone(client.player_id)
        finally:
            client.close()

    def test_client_defaults(self):
        """Client should have sensible defaults."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            self.assertEqual(client.server_tick, 0)
            self.assertEqual(client.local_tick, 0)
            self.assertEqual(client.rtt, 0.0)
        finally:
            client.close()


class TestClientConnection(unittest.TestCase):
    """Tests for connection lifecycle."""

    def test_client_connects_to_server(self):
        """Client should transition DISCONNECTED -> CONNECTING -> CONNECTED."""
        server = GameServer(port=19001)
        client = GameClient(
            server_host="127.0.0.1",
            server_port=19001,
            player_name="TestNinja",
            transport=UDPTransport(port=0),
        )

        try:
            # Before connect
            self.assertEqual(client.state, ConnectionState.DISCONNECTED)

            # Start connecting
            client.connect()
            self.assertEqual(client.state, ConnectionState.CONNECTING)

            # Server processes connect_request
            time.sleep(0.02)
            server.update()

            # Client processes connect_accept
            time.sleep(0.02)
            client.update()

            self.assertEqual(client.state, ConnectionState.CONNECTED)
            self.assertTrue(client.is_connected)
            self.assertEqual(client.player_id, 1)
        finally:
            server.shutdown()
            client.close()

    def test_client_gets_player_id(self):
        """Client should receive correct player_id from server."""
        server = GameServer(port=19002)
        game = MockGame(tick=42)
        server.set_game(game)

        client = GameClient(
            server_port=19002,
            player_name="Ninja1",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)
            self.assertEqual(client.player_id, 1)
            self.assertEqual(client.server_tick, 42)
        finally:
            server.shutdown()
            client.close()

    def test_client_handles_rejection(self):
        """Client should handle server rejection (server full)."""
        server = GameServer(port=19003, max_clients=1)

        # First client fills the server
        first = UDPTransport(port=0)
        msg = Message(type="connect_request", payload={"player_name": "P1"})
        first.send(msg, ("127.0.0.1", 19003))
        time.sleep(0.02)
        server.update()

        # Second client tries to connect
        client = GameClient(
            server_port=19003,
            player_name="P2",
            transport=UDPTransport(port=0),
        )
        disconnected_reasons: List[str] = []
        client.on_disconnected(lambda reason: disconnected_reasons.append(reason))

        try:
            client.connect()
            time.sleep(0.02)
            server.update()
            time.sleep(0.02)
            client.update()

            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
            self.assertFalse(client.is_connected)
            self.assertEqual(len(disconnected_reasons), 1)
            self.assertIn("full", disconnected_reasons[0].lower())
        finally:
            server.shutdown()
            first.close()
            client.close()

    def test_client_retries_connect(self):
        """Client should retry connection attempts."""
        # No server listening — client will retry
        client = GameClient(
            server_port=19004,
            player_name="Retry",
            transport=UDPTransport(port=0),
        )

        try:
            client.connect()
            self.assertEqual(client.state, ConnectionState.CONNECTING)

            # First attempt already sent in connect()
            self.assertEqual(client._connect_attempt_count, 1)

            # Simulate time passing and update
            client._last_connect_attempt_time = time.time() - CONNECT_RETRY_INTERVAL - 0.1
            client.update()
            self.assertEqual(client._connect_attempt_count, 2)
        finally:
            client.close()

    def test_client_gives_up_after_max_retries(self):
        """Client should give up after MAX_CONNECT_ATTEMPTS."""
        client = GameClient(
            server_port=19005,
            player_name="GiveUp",
            transport=UDPTransport(port=0),
        )
        disconnected_reasons: List[str] = []
        client.on_disconnected(lambda reason: disconnected_reasons.append(reason))

        try:
            client.connect()

            # Simulate reaching max attempts
            client._connect_attempt_count = MAX_CONNECT_ATTEMPTS
            client.update()

            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
            self.assertEqual(disconnected_reasons, ["max_retries"])
        finally:
            client.close()

    def test_on_connected_callback(self):
        """on_connected callback should fire with player_id."""
        server = GameServer(port=19006)
        client = GameClient(
            server_port=19006,
            player_name="Callback",
            transport=UDPTransport(port=0),
        )
        connected_ids: List[int] = []
        client.on_connected(lambda pid: connected_ids.append(pid))

        try:
            _connect_client_to_server(client, server)
            self.assertEqual(connected_ids, [1])
        finally:
            server.shutdown()
            client.close()

    def test_on_disconnected_callback(self):
        """on_disconnected callback should fire on disconnect."""
        server = GameServer(port=19007)
        client = GameClient(
            server_port=19007,
            player_name="DiscoTest",
            transport=UDPTransport(port=0),
        )
        reasons: List[str] = []
        client.on_disconnected(lambda r: reasons.append(r))

        try:
            _connect_client_to_server(client, server)
            client.disconnect()
            self.assertEqual(reasons, ["client_disconnect"])
        finally:
            server.shutdown()
            client.close()


class TestInputSending(unittest.TestCase):
    """Tests for the state+event input protocol (client side)."""

    def test_send_input_state_transmits_to_server(self):
        """send_input_state should reach the server and apply actions."""
        server = GameServer(port=19010)
        player = MockPlayer(id=1)
        game = MockGame(tick=10, players=[player])
        server.set_game(game)

        client = GameClient(
            server_port=19010,
            player_name="Input",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)

            client.send_input_state((True, False), ["jump"])
            time.sleep(0.02)
            server.update()

            client_state = server.clients.get_all_clients()[0]
            self.assertEqual(client_state.movement, [True, False])
            self.assertTrue(player._jumped)
        finally:
            server.shutdown()
            client.close()

    def test_inputs_stored_in_history(self):
        """send_input_state should record per-tick history for replay."""
        server = GameServer(port=19011)
        client = GameClient(
            server_port=19011,
            player_name="History",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)
            tick1 = client.local_tick
            client.send_input_state((True, False), [])
            client.update()
            tick2 = client.local_tick
            client.send_input_state((False, True), ["jump"])

            self.assertEqual(client._input_history[tick1], ((True, False), []))
            self.assertEqual(client._input_history[tick2], ((False, True), ["jump"]))
        finally:
            server.shutdown()
            client.close()

    def test_actions_resent_until_acknowledged(self):
        """Unacked actions must be re-sent in subsequent packets."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            client._state = ConnectionState.CONNECTED
            client._local_tick = 100
            client.send_input_state((False, False), ["jump"])
            client._local_tick = 101
            client.send_input_state((False, False), ["dash"])
            # Both actions still pending (no ack received)
            self.assertEqual(
                [(seq, name) for seq, name, _ in client._pending_actions],
                [(1, "jump"), (2, "dash")],
            )
            # Ack tick 100 → jump pruned, dash kept
            client._input_ack_tick = 100
            client._prune_input_history()
            self.assertEqual(
                [(seq, name) for seq, name, _ in client._pending_actions],
                [(2, "dash")],
            )
        finally:
            client.close()

    def test_old_inputs_pruned(self):
        """Acknowledged input history should be pruned."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            client._input_history = {
                10: ((True, False), []),
                20: ((False, False), []),
                90: ((False, True), ["jump"]),
            }
            client._input_ack_tick = 88
            client._local_tick = 95

            client._prune_input_history()

            # Everything older than ack-5 is gone; recent history kept
            self.assertNotIn(10, client._input_history)
            self.assertNotIn(20, client._input_history)
            self.assertIn(90, client._input_history)
        finally:
            client.close()

    def test_send_input_state_ignored_when_disconnected(self):
        """send_input_state should do nothing when not connected."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            client.send_input_state((True, False), ["jump"])
            self.assertEqual(client._input_history, {})
            self.assertEqual(client._pending_actions, [])
        finally:
            client.close()

    def test_get_unacknowledged_inputs(self):
        """get_unacknowledged_inputs should return inputs after ack tick."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            client._input_history = {
                5: ((True, False), []),
                10: ((False, False), ["jump"]),
                15: ((False, True), []),
            }
            client._input_ack_tick = 8
            result = client.get_unacknowledged_inputs()
            self.assertEqual(sorted(result.keys()), [10, 15])
        finally:
            client.close()

    def test_snapshot_ack_updates_input_ack_tick(self):
        """Snapshot 'acks' payload should update the client's ack tick."""
        client = GameClient(transport=UDPTransport(port=0))
        try:
            client._player_id = 3
            client._handle_snapshot(
                {
                    "tick": 50,
                    "is_delta": False,
                    "acks": {"3": 47},
                    "data": {"tick": 50, "rng_state": []},
                }
            )
            self.assertEqual(client.input_ack_tick, 47)
        finally:
            client.close()


class TestSnapshotReception(unittest.TestCase):
    """Tests for receiving snapshots."""

    def test_client_receives_full_snapshot(self):
        """Client should receive and store full snapshot."""
        server = GameServer(port=19020)
        player = MockPlayer(id=1, pos=[100.0, 200.0])
        game = MockGame(tick=0, players=[player])
        server.set_game(game)

        client = GameClient(
            server_port=19020,
            player_name="Snap",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)

            # Advance ticks to trigger snapshot broadcast
            for _ in range(server.SNAPSHOT_INTERVAL + 1):
                game.tick += 1
                server.update()

            time.sleep(0.02)
            client.update()

            snapshot = client.get_latest_snapshot()
            self.assertIsNotNone(snapshot)
            self.assertEqual(len(snapshot.players), 1)
            self.assertEqual(snapshot.players[0].pos, [100.0, 200.0])
        finally:
            server.shutdown()
            client.close()

    def test_client_receives_delta_snapshot(self):
        """Client should reconstruct state from delta snapshots."""
        server = GameServer(port=19021)
        player = MockPlayer(id=1, pos=[10.0, 20.0])
        game = MockGame(tick=0, players=[player])
        server.set_game(game)

        client = GameClient(
            server_port=19021,
            player_name="Delta",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)

            # First snapshot (full)
            for _ in range(server.SNAPSHOT_INTERVAL + 1):
                game.tick += 1
                server.update()
            time.sleep(0.02)
            client.update()

            first_snap = client.get_latest_snapshot()
            self.assertIsNotNone(first_snap)

            # Move player and trigger second snapshot (delta)
            player.pos = [50.0, 60.0]
            for _ in range(server.SNAPSHOT_INTERVAL):
                game.tick += 1
                server.update()
            time.sleep(0.02)
            client.update()

            second_snap = client.get_latest_snapshot()
            self.assertIsNotNone(second_snap)
            self.assertEqual(second_snap.players[0].pos, [50.0, 60.0])
        finally:
            server.shutdown()
            client.close()

    def test_snapshots_stored_in_buffer(self):
        """Received snapshots should be stored in the snapshot buffer."""
        server = GameServer(port=19022)
        player = MockPlayer(id=1)
        game = MockGame(tick=0, players=[player])
        server.set_game(game)

        client = GameClient(
            server_port=19022,
            player_name="Buf",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)

            for _ in range(server.SNAPSHOT_INTERVAL + 1):
                game.tick += 1
                server.update()
            time.sleep(0.02)
            client.update()

            buf = client.get_snapshot_buffer()
            self.assertTrue(len(buf.buffer) > 0)
        finally:
            server.shutdown()
            client.close()

    def test_server_tick_updated_on_snapshot(self):
        """server_tick should update when snapshot is received."""
        server = GameServer(port=19023)
        player = MockPlayer(id=1)
        game = MockGame(tick=0, players=[player])
        server.set_game(game)

        client = GameClient(
            server_port=19023,
            player_name="Tick",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)
            initial_tick = client.server_tick

            for _ in range(server.SNAPSHOT_INTERVAL + 1):
                game.tick += 1
                server.update()
            time.sleep(0.02)
            client.update()

            self.assertGreater(client.server_tick, initial_tick)
        finally:
            server.shutdown()
            client.close()


class TestHeartbeat(unittest.TestCase):
    """Tests for heartbeat and RTT measurement."""

    def test_client_sends_heartbeat(self):
        """Client should send heartbeats after interval."""
        server = GameServer(port=19030)
        client = GameClient(
            server_port=19030,
            player_name="Heart",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)

            # Force heartbeat by backdating the last heartbeat time
            client._last_heartbeat_time = time.time() - HEARTBEAT_INTERVAL - 0.1
            client.update()

            # Server should receive and respond to heartbeat
            time.sleep(0.02)
            server.update()

            # Client should process heartbeat_ack
            time.sleep(0.02)
            client.update()

            self.assertGreater(client.rtt, 0.0)
        finally:
            server.shutdown()
            client.close()

    def test_rtt_computed_from_heartbeat(self):
        """RTT should be computed from heartbeat round-trip."""
        server = GameServer(port=19031)
        client = GameClient(
            server_port=19031,
            player_name="RTT",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)
            self.assertEqual(client.rtt, 0.0)

            # Trigger heartbeat
            client._last_heartbeat_time = time.time() - HEARTBEAT_INTERVAL - 0.1
            client.update()
            time.sleep(0.02)
            server.update()
            time.sleep(0.02)
            client.update()

            # RTT should be positive and small (localhost)
            self.assertGreater(client.rtt, 0.0)
            self.assertLess(client.rtt, 1.0)  # Should be well under 1s on localhost
        finally:
            server.shutdown()
            client.close()


class TestDisconnection(unittest.TestCase):
    """Tests for disconnection scenarios."""

    def test_graceful_disconnect(self):
        """Graceful disconnect should transition to DISCONNECTED."""
        server = GameServer(port=19040)
        client = GameClient(
            server_port=19040,
            player_name="Grace",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)
            self.assertTrue(client.is_connected)

            client.disconnect()
            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
            self.assertFalse(client.is_connected)
        finally:
            server.shutdown()
            client.close()

    def test_server_removes_disconnected_client(self):
        """Server should remove client after graceful disconnect."""
        server = GameServer(port=19041)
        client = GameClient(
            server_port=19041,
            player_name="Gone",
            transport=UDPTransport(port=0),
        )

        try:
            _connect_client_to_server(client, server)
            self.assertEqual(server.get_client_count(), 1)

            client.disconnect()
            time.sleep(0.02)
            server.update()

            self.assertEqual(server.get_client_count(), 0)
        finally:
            server.shutdown()
            client.close()

    def test_server_shutdown_triggers_disconnect(self):
        """Client should disconnect when receiving server_shutdown."""
        server = GameServer(port=19042)
        client = GameClient(
            server_port=19042,
            player_name="Shut",
            transport=UDPTransport(port=0),
        )
        reasons: List[str] = []
        client.on_disconnected(lambda r: reasons.append(r))

        try:
            _connect_client_to_server(client, server)
            self.assertTrue(client.is_connected)

            # Server shuts down (sends server_shutdown to all clients)
            server.shutdown()
            time.sleep(0.02)
            client.update()

            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
            self.assertEqual(reasons, ["server_shutdown"])
        finally:
            client.close()

    def test_server_timeout_triggers_disconnect(self):
        """Client should disconnect after server timeout."""
        server = GameServer(port=19043)
        client = GameClient(
            server_port=19043,
            player_name="Timeout",
            transport=UDPTransport(port=0),
        )
        reasons: List[str] = []
        client.on_disconnected(lambda r: reasons.append(r))

        try:
            _connect_client_to_server(client, server)

            # Simulate server silence by backdating last message time
            client._last_server_message_time = time.time() - SERVER_TIMEOUT - 1.0
            client.update()

            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
            self.assertEqual(reasons, ["server_timeout"])
        finally:
            server.shutdown()
            client.close()


class TestPlayerEvents(unittest.TestCase):
    """Tests for player join/leave event callbacks."""

    def test_on_player_joined(self):
        """on_player_joined should fire when another client connects."""
        server = GameServer(port=19050)
        client1 = GameClient(
            server_port=19050,
            player_name="First",
            transport=UDPTransport(port=0),
        )
        joined_events: List[tuple] = []
        client1.on_player_joined(lambda pid, name: joined_events.append((pid, name)))

        client2_transport = UDPTransport(port=0)

        try:
            _connect_client_to_server(client1, server)

            # Second player connects via raw transport
            msg = Message(type="connect_request", payload={"player_name": "Second"})
            client2_transport.send(msg, ("127.0.0.1", 19050))
            time.sleep(0.02)
            server.update()

            # Client1 should receive player_joined broadcast
            time.sleep(0.02)
            client1.update()

            self.assertEqual(len(joined_events), 1)
            self.assertEqual(joined_events[0], (2, "Second"))
        finally:
            server.shutdown()
            client1.close()
            client2_transport.close()

    def test_on_player_left(self):
        """on_player_left should fire when another client disconnects."""
        server = GameServer(port=19051)
        client1 = GameClient(
            server_port=19051,
            player_name="Stayer",
            transport=UDPTransport(port=0),
        )
        left_events: List[tuple] = []
        client1.on_player_left(lambda pid, reason: left_events.append((pid, reason)))

        client2_transport = UDPTransport(port=0)

        try:
            _connect_client_to_server(client1, server)

            # Second player connects
            msg = Message(type="connect_request", payload={"player_name": "Leaver"})
            client2_transport.send(msg, ("127.0.0.1", 19051))
            time.sleep(0.02)
            server.update()

            # Drain client1's player_joined message
            time.sleep(0.02)
            client1.update()

            # Second player disconnects
            disconnect_msg = Message(type="disconnect", payload={})
            client2_transport.send(disconnect_msg, ("127.0.0.1", 19051))
            time.sleep(0.02)
            server.update()

            # Client1 should receive player_left broadcast
            time.sleep(0.02)
            client1.update()

            self.assertEqual(len(left_events), 1)
            self.assertEqual(left_events[0][0], 2)  # player_id
            self.assertEqual(left_events[0][1], "disconnected")
        finally:
            server.shutdown()
            client1.close()
            client2_transport.close()


class TestContextManager(unittest.TestCase):
    """Tests for context manager usage."""

    def test_context_manager_cleans_up(self):
        """Context manager should disconnect and close."""
        server = GameServer(port=19060)
        try:
            with GameClient(
                server_port=19060,
                player_name="Ctx",
                transport=UDPTransport(port=0),
            ) as client:
                _connect_client_to_server(client, server)
                self.assertTrue(client.is_connected)

            # After __exit__, should be disconnected
            self.assertEqual(client.state, ConnectionState.DISCONNECTED)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
