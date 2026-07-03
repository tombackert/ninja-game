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
        client.send_input_state((left_held, right_held), ["jump"])
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
TICK_LEAD = 2  # how many ticks the client runs ahead of the server
TICK_HARD_RESYNC = 30  # snap local tick if drift exceeds this
ACTION_RESEND_WINDOW = 30  # re-send unacked actions for this many ticks


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
        self._level = 0

        # Tick tracking
        self._server_tick = 0
        self._local_tick = 0

        # Snapshot storage
        self._snapshot_buffer = SnapshotBuffer(max_size=20)
        self._last_full_snapshot: SimulationSnapshot | None = None

        # Input tracking (state + events model)
        # History of what was input each local tick: {tick: (move, actions)}
        self._input_history: Dict[int, Tuple[Tuple[bool, bool], List[str]]] = {}
        # One-shot actions not yet acknowledged: [(seq, name, tick)]
        self._pending_actions: List[Tuple[int, str, int]] = []
        self._action_seq = 0
        # Newest of our input ticks the server confirmed applying
        self._input_ack_tick = 0

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

    @property
    def input_ack_tick(self) -> int:
        """Newest of our input ticks the server confirmed applying."""
        return self._input_ack_tick

    @property
    def level(self) -> int:
        """Level the server is running (valid once connected)."""
        return self._level

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

    def send_input_state(self, move: Tuple[bool, bool], actions: List[str]) -> None:
        """Send this frame's input state to the server.

        Movement is sent as held-key state every frame (drift/loss tolerant).
        One-shot actions get sequence numbers and are re-sent in every packet
        until acknowledged, so a lost packet cannot swallow a jump.

        Args:
            move: (left_held, right_held)
            actions: New one-shot actions triggered this frame
        """
        if self._state != ConnectionState.CONNECTED:
            return

        tick = self._local_tick
        for name in actions:
            self._action_seq += 1
            self._pending_actions.append((self._action_seq, name, tick))

        msg = Message(
            type="input",
            payload={
                "tick": tick,
                "move": [bool(move[0]), bool(move[1])],
                "actions": [[seq, name] for seq, name, _ in self._pending_actions],
            },
        )
        self.transport.send(msg, self._server_addr)
        self._input_history[tick] = ((bool(move[0]), bool(move[1])), list(actions))

    # --- Snapshot access ---

    def get_latest_snapshot(self) -> SimulationSnapshot | None:
        return self._last_full_snapshot

    def get_snapshot_buffer(self) -> SnapshotBuffer:
        return self._snapshot_buffer

    # --- Prediction support ---

    def get_unacknowledged_inputs(
        self, since_tick: int | None = None
    ) -> Dict[int, Tuple[Tuple[bool, bool], List[str]]]:
        """Get inputs the server has not confirmed applying yet.

        Args:
            since_tick: Return inputs for ticks > since_tick.
                Defaults to the server's input ack tick.

        Returns:
            Dict mapping tick -> (move, actions) for unacknowledged ticks
        """
        cutoff = self._input_ack_tick if since_tick is None else since_tick
        return {t: inp for t, inp in self._input_history.items() if t > cutoff}

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
        self._level = payload.get("level", 0)
        self._local_tick = self._server_tick + TICK_LEAD
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

        # Input acknowledgement for prediction reconciliation
        acks = payload.get("acks", {})
        if self._player_id is not None:
            ack = acks.get(str(self._player_id))
            if ack is not None:
                self._input_ack_tick = max(self._input_ack_tick, int(ack))

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
        self._resync_local_tick()

    def _resync_local_tick(self) -> None:
        """Keep the local tick slightly ahead of the server tick.

        The client frame clock and the server tick clock drift apart over
        time (they are independent 60 Hz loops). Without correction the
        input ticks would wander arbitrarily far from the server timeline.
        Large divergence snaps; small divergence is nudged one tick at a
        time to avoid visible input timing jumps.
        """
        target = self._server_tick + TICK_LEAD
        drift = self._local_tick - target
        if abs(drift) > TICK_HARD_RESYNC:
            self._local_tick = target
        elif drift > TICK_LEAD:
            self._local_tick -= 1
        elif drift < -TICK_LEAD:
            self._local_tick += 1

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
        """Drop acknowledged/stale input history and pending actions."""
        cutoff = max(self._input_ack_tick - 5, self._local_tick - 120)
        old_ticks = [t for t in self._input_history if t < cutoff]
        for t in old_ticks:
            del self._input_history[t]
        # Stop re-sending actions once acked or too old to matter
        action_cutoff = self._local_tick - ACTION_RESEND_WINDOW
        self._pending_actions = [
            (seq, name, tick)
            for seq, name, tick in self._pending_actions
            if tick > self._input_ack_tick and tick > action_cutoff
        ]

    # --- Context manager ---

    def __enter__(self) -> GameClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.is_connected:
            self.disconnect()
        self.close()


__all__ = ["GameClient"]
