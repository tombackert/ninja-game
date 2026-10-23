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
from scripts.network.netstats import NetStats
from scripts.network.udp_transport import UDPTransport
from scripts.snapshot import SimulationSnapshot, SnapshotService

# Type alias
Address = Tuple[str, int]

# Constants
CONNECT_RETRY_INTERVAL = 1.0  # seconds between connect retries
MAX_CONNECT_ATTEMPTS = 5  # give up after this many
HEARTBEAT_INTERVAL = 1.0  # seconds between heartbeats
SERVER_TIMEOUT = 10.0  # disconnect if no messages for this long
TICK_LEAD = 2  # the first local tick: this far ahead of the server's tick at connect
INPUT_REDUNDANCY = 4  # each input packet carries this many ticks of movement
ACTION_RESEND_WINDOW = 30  # re-send unacked actions for this many ticks
STALL_MS = 100.0  # a snapshot gap this long is a visible network stall (3 snapshot intervals)
MAX_RTT_SAMPLE = 5.0  # seconds; anything outside 0..this is a clock step, not a measurement


class GameClient:
    """Client-side networking for multiplayer.

    Mirrors the GameServer's message protocol. Handles:
    - Connection lifecycle (connect, disconnect, timeout)
    - Sending player inputs to the server
    - Receiving and reconstructing state snapshots
    - Heartbeat and RTT measurement
    - Player join/leave event callbacks
    - Netcode health metrics (``netstats``) for the session log and HUD

    RTT is measured from every snapshot: it acks our newest input tick and
    says how long that input waited on the server (``holds``), so
    ``snapshot arrival - input send - hold`` is the network round trip
    without the time packets sit in socket buffers until the next tick or
    frame reads them (arrival times are kernel timestamps where available).
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
        # Snapshots received since the last drain_new_snapshots() call.
        # Bounded so a paused client cannot grow it without limit.
        self._new_snapshots: List[SimulationSnapshot] = []
        self._last_full_request_time = 0.0
        # Recently reconstructed snapshots by tick (delta base lookup) and
        # deltas that arrived before their base (reordered packets).
        self._recent_by_tick: Dict[int, SimulationSnapshot] = {}
        self._pending_deltas: Dict[int, Tuple[int, Any, Optional[int]]] = {}  # base tick -> (tick, data, ack)

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
        self._input_sent_at: Dict[int, float] = {}  # local tick -> wall-clock send time

        # Netcode health (session log, HUD). Arrival times are wall clock.
        self.netstats = NetStats()
        self._last_snap_arrival: Optional[float] = None
        self.newest_snapshot_arrival: Optional[float] = None  # when server_tick's snapshot became usable
        self.server_view: Dict[str, Any] = {}  # how the server receives us (from heartbeat acks)
        self._report: Dict[str, Any] = {}  # our own summary, sent with heartbeats
        self._connect_started = 0.0
        self._joined = False

        # Network health counters (read by metrics logging / diagnostics)
        self.net_stats: Dict[str, int] = {
            "snapshots_recv": 0,
            "fulls_recv": 0,
            "deltas_dropped": 0,
            "deltas_deferred": 0,  # arrived before their base (reordered)
            "deltas_pruned": 0,  # parked delta whose base never arrived (lost)
            "snap_late": 0,  # arrival tick gap > snapshot interval
            "snap_gap_max": 0,
            "snap_bursts": 0,  # >= 2 snapshots processed in one update()
        }
        self._last_snap_recv_tick: int | None = None
        self._snaps_this_update = 0

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
        """Smoothed network round-trip time in seconds (0.0 until measured)."""
        return self._rtt_estimate

    @property
    def server_address(self) -> Address:
        return self._server_addr

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
        # A new session: the server restarts its packet sequence for us
        self.transport.forget(self._server_addr)
        self._connect_started = time.perf_counter()
        self._joined = False
        self._connect_attempt_count = 0
        self._last_connect_attempt_time = 0.0
        self._send_connect_request()

    def disconnect(self) -> None:
        """Gracefully disconnect from the server."""
        if self._state == ConnectionState.DISCONNECTED:
            return
        msg = Message(type="disconnect", payload={})
        self.transport.send(msg, self._server_addr)
        self._set_disconnected("client_disconnect")

    def update(self) -> None:
        """Process one frame of networking. Call once per game tick."""
        now = time.time()

        # Retry connect if in CONNECTING state
        if self._state == ConnectionState.CONNECTING:
            self._update_connecting(now)

        # Process all incoming messages
        self._snaps_this_update = 0
        self._process_incoming_messages()
        if self._snaps_this_update >= 2:
            self.net_stats["snap_bursts"] += 1

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
        """Send this frame's input to the server (call once per local tick).

        Every local tick is one input, and the server runs one physics step
        per input, so ticks must stay contiguous. Movement is held-key
        state; each packet also carries the movement of the previous ticks
        (``history``), so a lost packet leaves no hole. One-shot actions
        get sequence numbers and their tick, and are re-sent in every packet
        until the server has run that tick, so a lost packet cannot swallow
        a jump.

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

        history = []
        for t in range(tick - INPUT_REDUNDANCY + 1, tick):
            if t in self._input_history:
                history.append(list(self._input_history[t][0]))
            else:
                history = []  # only a gap-free run up to this tick
        msg = Message(
            type="input",
            payload={
                "tick": tick,
                "move": [bool(move[0]), bool(move[1])],
                "history": history,
                "actions": [[seq, name, t] for seq, name, t in self._pending_actions],
            },
        )
        self._input_sent_at[tick] = time.time()
        self.transport.send(msg, self._server_addr)
        self._input_history[tick] = ((bool(move[0]), bool(move[1])), list(actions))

    # --- Snapshot access ---

    def get_latest_snapshot(self) -> SimulationSnapshot | None:
        return self._last_full_snapshot

    def drain_new_snapshots(self) -> List[SimulationSnapshot]:
        """Return every snapshot received since the last call (arrival order).

        Under bursty delivery (Wi-Fi aggregation/power-save) several
        snapshots can arrive within one frame; consumers that only read
        get_latest_snapshot() would silently drop interpolation samples.
        """
        out = self._new_snapshots
        self._new_snapshots = []
        return out

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

    # --- Metrics ---

    def set_report(self, report: Dict[str, Any]) -> None:
        """Summary of our netcode health, sent to the server with each heartbeat."""
        self._report = report

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
            self._set_disconnected("max_retries")
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
        self.netstats.event(
            "connected",
            player=self._player_id,
            ms=round((time.perf_counter() - self._connect_started) * 1000.0, 1),
            attempts=self._connect_attempt_count,
        )
        if self._on_connected and self._player_id is not None:
            self._on_connected(self._player_id)

    def _handle_connect_reject(self, payload: Dict[str, Any]) -> None:
        """Handle connection rejection from server."""
        reason = payload.get("reason", "rejected")
        self._set_disconnected(reason)

    def _handle_snapshot(self, payload: Dict[str, Any]) -> None:
        """Handle snapshot message (full or delta)."""
        self._last_server_message_time = time.time()
        arrival = self.transport.last_arrival or time.time()
        tick = payload["tick"]
        is_delta = payload.get("is_delta", False)
        data = payload["data"]

        # Arrival gaps in real time: a long one is a stall the player sees
        if self._last_snap_arrival is not None:
            gap_ms = (arrival - self._last_snap_arrival) * 1000.0
            self.netstats.add("snap_gap_ms", gap_ms)
            if gap_ms >= STALL_MS:
                self.netstats.count("stalls")
                self.netstats.event("net_stall", tick=tick, ms=round(gap_ms, 1))
        self._last_snap_arrival = arrival

        # Arrival-stream diagnostics (gaps = lost/late snapshots)
        self.net_stats["snapshots_recv"] += 1
        self._snaps_this_update += 1
        if not is_delta:
            self.net_stats["fulls_recv"] += 1
        if self._last_snap_recv_tick is not None:
            gap = tick - self._last_snap_recv_tick
            if gap > 2:
                self.net_stats["snap_late"] += 1
            self.net_stats["snap_gap_max"] = max(self.net_stats["snap_gap_max"], gap)
        self._last_snap_recv_tick = tick

        # Input acknowledgement for prediction reconciliation. It belongs to
        # this snapshot's state, so it only counts once the snapshot is
        # accepted as the newest (see _accept_snapshot); the RTT sample is
        # valid for this packet either way.
        ack: Optional[int] = None
        if self._player_id is not None:
            raw_ack = payload.get("acks", {}).get(str(self._player_id))
            if raw_ack is not None:
                ack = int(raw_ack)
                hold_ms = payload.get("holds", {}).get(str(self._player_id))
                sent = self._input_sent_at.get(ack)
                if hold_ms is not None and sent is not None:
                    self._add_rtt_sample(arrival - sent - hold_ms / 1000.0, "rtt_ms")

        if is_delta:
            # Deltas are computed against the server's previous broadcast.
            # Applying one to the wrong base silently corrupts state, so
            # resolve the exact base by tick. A delta whose base has not
            # arrived yet (reordered packet) is parked and re-applied the
            # moment its base is reconstructed.
            base_tick = payload.get("base_tick")
            base = self._resolve_delta_base(base_tick)
            if base is None:
                if base_tick is not None and len(self._pending_deltas) < 8:
                    self._pending_deltas[base_tick] = (tick, data, ack)
                    self.net_stats["deltas_deferred"] += 1
                else:
                    self.net_stats["deltas_dropped"] += 1
                self._request_full_snapshot()
                return
            try:
                snapshot = apply_delta(base, data)
            except Exception:
                self._last_full_snapshot = None  # Reset; wait for next full
                self.net_stats["deltas_dropped"] += 1
                self._request_full_snapshot()
                return
        else:
            snapshot = SnapshotService.deserialize(data)

        self._accept_snapshot(tick, snapshot, ack)

    def _resolve_delta_base(self, base_tick: Any) -> SimulationSnapshot | None:
        """Find the snapshot a delta must be applied to."""
        if base_tick is None:  # server without base_tick support
            return self._last_full_snapshot
        return self._recent_by_tick.get(base_tick)

    def _accept_snapshot(self, tick: int, snapshot: SimulationSnapshot, ack: Optional[int] = None) -> None:
        """Store a reconstructed snapshot and resolve any deltas waiting on it.

        Reordered (older) snapshots still serve as interpolation samples,
        but must not roll back the delta base, the tick clock or the input
        ack: the ack always belongs to the newest snapshot, the one the
        game reconciles against.
        """
        if tick > self._server_tick or self._last_full_snapshot is None:
            self._last_full_snapshot = snapshot
            self._server_tick = tick
            self.newest_snapshot_arrival = self.transport.last_arrival or time.time()
            if ack is not None:
                self._input_ack_tick = max(self._input_ack_tick, ack)
        if not self._joined and self._connect_started:
            self._joined = True
            self.netstats.event(
                "joined", tick=tick, ms=round((time.perf_counter() - self._connect_started) * 1000.0, 1)
            )
        self._snapshot_buffer.push(tick, snapshot)
        self._new_snapshots.append(snapshot)
        if len(self._new_snapshots) > 30:
            self._new_snapshots.pop(0)
        self._recent_by_tick[tick] = snapshot
        while len(self._recent_by_tick) > 32:
            self._recent_by_tick.pop(next(iter(self._recent_by_tick)))

        pending = self._pending_deltas.pop(tick, None)
        if pending is not None:
            p_tick, p_data, p_ack = pending
            try:
                self._accept_snapshot(p_tick, apply_delta(snapshot, p_data), p_ack)
            except Exception:
                self.net_stats["deltas_dropped"] += 1
                self._request_full_snapshot()

    def _request_full_snapshot(self) -> None:
        """Ask the server to reset our delta chain with a full snapshot."""
        now = time.time()
        if now - self._last_full_request_time < 0.1:
            return
        self._last_full_request_time = now
        self.transport.send(Message(type="request_full", payload={}), self._server_addr)

    def _handle_heartbeat_ack(self, payload: Dict[str, Any]) -> None:
        """Handle heartbeat acknowledgement: RTT sample and the server's view of our link."""
        self._last_server_message_time = time.time()
        arrival = self.transport.last_arrival or time.time()
        if self._pending_heartbeat_time > 0:
            hold = payload.get("hold_ms", 0.0) / 1000.0
            self._add_rtt_sample(arrival - self._pending_heartbeat_time - hold, "rtt_hb_ms")
            self._pending_heartbeat_time = 0.0
        link = payload.get("link")
        if isinstance(link, dict):
            self.server_view = link

    def _add_rtt_sample(self, rtt: float, metric: str) -> None:
        """Feed one RTT measurement (seconds) into the metric and the smoothed estimate."""
        if not 0.0 <= rtt < MAX_RTT_SAMPLE:
            return  # wall-clock step, not a measurement
        self.netstats.add(metric, rtt * 1000.0)
        if self._rtt_estimate == 0:
            self._rtt_estimate = rtt
        else:
            self._rtt_estimate = 0.9 * self._rtt_estimate + 0.1 * rtt

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
        self._set_disconnected("server_shutdown")

    # --- Internal: heartbeat ---

    def _update_heartbeat(self, now: float) -> None:
        """Send heartbeat if interval elapsed."""
        if now - self._last_heartbeat_time >= HEARTBEAT_INTERVAL:
            self._pending_heartbeat_time = now
            msg = Message(
                type="heartbeat",
                payload={"client_time": now, "report": self._report},
            )
            self.transport.send(msg, self._server_addr)
            self._last_heartbeat_time = now

    def _check_server_timeout(self, now: float) -> None:
        """Disconnect if server has been silent too long."""
        if now - self._last_server_message_time >= SERVER_TIMEOUT:
            self._set_disconnected("server_timeout")

    def _set_disconnected(self, reason: str) -> None:
        self._state = ConnectionState.DISCONNECTED
        self.netstats.event("disconnected", tick=self._server_tick, reason=reason)
        if self._on_disconnected:
            self._on_disconnected(reason)

    # --- Internal: cleanup ---

    def _prune_input_history(self) -> None:
        """Drop acknowledged/stale input history and pending actions."""
        # Parked deltas whose base never arrived are unrecoverable
        stale = [bt for bt in self._pending_deltas if bt < self._server_tick - 30]
        for bt in stale:
            del self._pending_deltas[bt]
            self.net_stats["deltas_dropped"] += 1
            self.net_stats["deltas_pruned"] += 1
        cutoff = max(self._input_ack_tick - 5, self._local_tick - 120)
        old_ticks = [t for t in self._input_history if t < cutoff]
        for t in old_ticks:
            del self._input_history[t]
        for t in [t for t in self._input_sent_at if t < cutoff]:
            del self._input_sent_at[t]
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
