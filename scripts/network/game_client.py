"""Game Client Implementation (MP-05).

Client-side counterpart to GameServer. Connects to a server, sends inputs,
receives snapshots, and provides building blocks for client-side prediction.

Pure networking logic — no Game/Player imports, no physics, no UI.

Usage:
    client = GameClient(server_host="127.0.0.1", server_port=7777, player_name="Ninja")
    client.connect()

    # In game loop:
    while running:
        client.update()
        client.send_inputs(client.local_tick, ["left", "jump"])
        snapshot = client.get_latest_snapshot()

    client.disconnect()
    client.close()
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.network.client_state import ConnectionState
from scripts.network.delta import apply_delta
from scripts.network.interpolation import SnapshotBuffer
from scripts.network.messages import Message
from scripts.network.udp_transport import UDPTransport
from scripts.snapshot import SimulationSnapshot, SnapshotService

# Type alias
Address = Tuple[str, int]

# Constants
CONNECT_RETRY_INTERVAL = 1.0  # seconds between connect retries
MAX_CONNECT_ATTEMPTS = 5  # give up after this many
HEARTBEAT_INTERVAL = 1.0  # seconds between heartbeats
SERVER_TIMEOUT = 10.0  # disconnect if no messages for this long


class GameClient:
    """Client-side networking for multiplayer.

    Mirrors the GameServer's message protocol. Handles:
    - Connection lifecycle (connect, disconnect, timeout)
    - Sending player inputs to the server
    - Receiving and reconstructing state snapshots
    - Heartbeat and RTT measurement
    - Player join/leave event callbacks
    """

    def __init__(
        self,
        server_host: str = "127.0.0.1",
        server_port: int = 7777,
        player_name: str = "Player",
        transport: UDPTransport | None = None,
    ):
        self.transport = transport if transport is not None else UDPTransport(port=0)
        self._server_addr: Address = (server_host, server_port)
        self._player_name = player_name

        # Connection state
        self._state = ConnectionState.DISCONNECTED
        self._player_id: int | None = None

        # Tick tracking
        self._server_tick = 0
        self._local_tick = 0

        # Snapshot storage
        self._snapshot_buffer = SnapshotBuffer(max_size=20)
        self._last_full_snapshot: SimulationSnapshot | None = None

        # Input history for reconciliation
        self._input_history: Dict[int, List[str]] = {}

        # RTT measurement
        self._rtt_estimate = 0.0
        self._pending_heartbeat_time = 0.0

        # Timing
        self._last_heartbeat_time = 0.0
        self._last_server_message_time = 0.0
        self._connect_attempt_count = 0
        self._last_connect_attempt_time = 0.0

        # Callbacks
        self._on_connected: Optional[Callable[[int], None]] = None
        self._on_disconnected: Optional[Callable[[str], None]] = None
        self._on_player_joined: Optional[Callable[[int, str], None]] = None
        self._on_player_left: Optional[Callable[[int, str], None]] = None

    # --- Properties ---

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def player_id(self) -> int | None:
        return self._player_id

    @property
    def server_tick(self) -> int:
        return self._server_tick

    @property
    def local_tick(self) -> int:
        return self._local_tick

    @property
    def rtt(self) -> float:
        return self._rtt_estimate

    # --- Lifecycle ---

    def connect(self) -> None:
        """Initiate connection to the server."""
        if self._state != ConnectionState.DISCONNECTED:
            return
        self._state = ConnectionState.CONNECTING
        self._connect_attempt_count = 0
        self._last_connect_attempt_time = 0.0
        self._send_connect_request()

    def disconnect(self) -> None:
        """Gracefully disconnect from the server."""
        if self._state == ConnectionState.DISCONNECTED:
            return
        msg = Message(type="disconnect", payload={})
        self.transport.send(msg, self._server_addr)
        self._state = ConnectionState.DISCONNECTED
        if self._on_disconnected:
            self._on_disconnected("client_disconnect")

    def update(self) -> None:
        """Process one frame of networking. Call once per game tick."""
        now = time.time()

        # Retry connect if in CONNECTING state
        if self._state == ConnectionState.CONNECTING:
            self._update_connecting(now)

        # Process all incoming messages
        self._process_incoming_messages()

        # Connected state updates
        if self._state == ConnectionState.CONNECTED:
            self._local_tick += 1
            self._update_heartbeat(now)
            self._check_server_timeout(now)
            self._prune_input_history()

    def close(self) -> None:
        """Release transport resources."""
        self.transport.close()

    # --- Input ---

    def send_inputs(self, tick: int, inputs: List[str]) -> None:
        """Send input actions to the server and store in history.

        Args:
            tick: The simulation tick these inputs are for
            inputs: List of input actions (e.g., ["left", "jump"])
        """
        if self._state != ConnectionState.CONNECTED:
            return
        msg = Message(
            type="input",
            payload={"tick": tick, "inputs": inputs},
        )
        self.transport.send(msg, self._server_addr)
        self._input_history[tick] = inputs

    # --- Snapshot access ---

    def get_latest_snapshot(self) -> SimulationSnapshot | None:
        return self._last_full_snapshot

    def get_snapshot_buffer(self) -> SnapshotBuffer:
        return self._snapshot_buffer

    # --- Prediction support ---

    def get_unacknowledged_inputs(self, since_tick: int) -> Dict[int, List[str]]:
        """Get inputs sent but not yet confirmed by the server.

        Args:
            since_tick: Return inputs for ticks > since_tick

        Returns:
            Dict mapping tick -> inputs for unacknowledged ticks
        """
        return {t: inputs for t, inputs in self._input_history.items() if t > since_tick}

    # --- Callbacks ---

    def on_connected(self, callback: Callable[[int], None]) -> None:
        self._on_connected = callback

    def on_disconnected(self, callback: Callable[[str], None]) -> None:
        self._on_disconnected = callback

    def on_player_joined(self, callback: Callable[[int, str], None]) -> None:
        self._on_player_joined = callback

    def on_player_left(self, callback: Callable[[int, str], None]) -> None:
        self._on_player_left = callback

    # --- Internal: connection ---

    def _send_connect_request(self) -> None:
        """Send a connect_request message and track the attempt."""
        msg = Message(
            type="connect_request",
            payload={"player_name": self._player_name},
        )
        self.transport.send(msg, self._server_addr)
        self._connect_attempt_count += 1
        self._last_connect_attempt_time = time.time()

    def _update_connecting(self, now: float) -> None:
        """Handle retry logic while in CONNECTING state."""
        if self._connect_attempt_count >= MAX_CONNECT_ATTEMPTS:
            self._state = ConnectionState.DISCONNECTED
            if self._on_disconnected:
                self._on_disconnected("max_retries")
            return
        if now - self._last_connect_attempt_time >= CONNECT_RETRY_INTERVAL:
            self._send_connect_request()

    # --- Internal: message processing ---

    def _process_incoming_messages(self) -> None:
        """Process all pending incoming messages."""
        while True:
            result = self.transport.receive()
            if result is None:
                break
            message, addr, header = result
            self._handle_message(message)

    def _handle_message(self, message: Message) -> None:
        """Dispatch a single incoming message by type."""
        msg_type = message.type
        payload = message.payload

        if msg_type == "connect_accept":
            self._handle_connect_accept(payload)
        elif msg_type == "connect_reject":
            self._handle_connect_reject(payload)
        elif msg_type == "snapshot":
            self._handle_snapshot(payload)
        elif msg_type == "heartbeat_ack":
            self._handle_heartbeat_ack(payload)
        elif msg_type == "player_joined":
            self._handle_player_joined(payload)
        elif msg_type == "player_left":
            self._handle_player_left(payload)
        elif msg_type == "server_shutdown":
            self._handle_server_shutdown(payload)

    def _handle_connect_accept(self, payload: Dict[str, Any]) -> None:
        """Handle connection acceptance from server."""
        if self._state != ConnectionState.CONNECTING:
            return
        self._player_id = payload["player_id"]
        self._server_tick = payload["server_tick"]
        self._local_tick = self._server_tick
        self._state = ConnectionState.CONNECTED
        self._last_server_message_time = time.time()
        self._last_heartbeat_time = time.time()
        if self._on_connected and self._player_id is not None:
            self._on_connected(self._player_id)

    def _handle_connect_reject(self, payload: Dict[str, Any]) -> None:
        """Handle connection rejection from server."""
        reason = payload.get("reason", "rejected")
        self._state = ConnectionState.DISCONNECTED
        if self._on_disconnected:
            self._on_disconnected(reason)

    def _handle_snapshot(self, payload: Dict[str, Any]) -> None:
        """Handle snapshot message (full or delta)."""
        self._last_server_message_time = time.time()
        tick = payload["tick"]
        is_delta = payload.get("is_delta", False)
        data = payload["data"]

        if is_delta:
            if self._last_full_snapshot is None:
                return  # No base to apply delta to; wait for full
            try:
                snapshot = apply_delta(self._last_full_snapshot, data)
            except Exception:
                self._last_full_snapshot = None  # Reset; wait for next full
                return
        else:
            snapshot = SnapshotService.deserialize(data)

        self._last_full_snapshot = snapshot
        self._server_tick = tick
        self._snapshot_buffer.push(tick, snapshot)

    def _handle_heartbeat_ack(self, payload: Dict[str, Any]) -> None:
        """Handle heartbeat acknowledgement and compute RTT."""
        self._last_server_message_time = time.time()
        if self._pending_heartbeat_time > 0:
            rtt = time.time() - self._pending_heartbeat_time
            if self._rtt_estimate == 0:
                self._rtt_estimate = rtt
            else:
                self._rtt_estimate = 0.9 * self._rtt_estimate + 0.1 * rtt
            self._pending_heartbeat_time = 0.0

    def _handle_player_joined(self, payload: Dict[str, Any]) -> None:
        """Handle player joined broadcast."""
        self._last_server_message_time = time.time()
        if self._on_player_joined:
            self._on_player_joined(payload["player_id"], payload["player_name"])

    def _handle_player_left(self, payload: Dict[str, Any]) -> None:
        """Handle player left broadcast."""
        self._last_server_message_time = time.time()
        if self._on_player_left:
            self._on_player_left(payload["player_id"], payload.get("reason", "disconnected"))

    def _handle_server_shutdown(self, payload: Dict[str, Any]) -> None:
        """Handle server shutdown notification."""
        self._state = ConnectionState.DISCONNECTED
        if self._on_disconnected:
            self._on_disconnected("server_shutdown")

    # --- Internal: heartbeat ---

    def _update_heartbeat(self, now: float) -> None:
        """Send heartbeat if interval elapsed."""
        if now - self._last_heartbeat_time >= HEARTBEAT_INTERVAL:
            self._pending_heartbeat_time = now
            msg = Message(
                type="heartbeat",
                payload={"client_time": now},
            )
            self.transport.send(msg, self._server_addr)
            self._last_heartbeat_time = now

    def _check_server_timeout(self, now: float) -> None:
        """Disconnect if server has been silent too long."""
        if now - self._last_server_message_time >= SERVER_TIMEOUT:
            self._state = ConnectionState.DISCONNECTED
            if self._on_disconnected:
                self._on_disconnected("server_timeout")

    # --- Internal: cleanup ---

    def _prune_input_history(self) -> None:
        """Remove inputs older than 60 ticks behind server_tick."""
        cutoff = self._server_tick - 60
        old_ticks = [t for t in self._input_history if t < cutoff]
        for t in old_ticks:
            del self._input_history[t]

    # --- Context manager ---

    def __enter__(self) -> GameClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.is_connected:
            self.disconnect()
        self.close()


__all__ = ["GameClient"]
