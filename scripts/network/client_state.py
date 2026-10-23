"""Client State Tracking (MP-04).

Tracks per-client state for the game server including:
- Player identity and network address
- Input buffer for tick-based input processing
- Connection health metrics (RTT, last activity)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

# Type alias for network address
Address = Tuple[str, int]

# One physics step per client input (see ClientState)
MAX_STEPS_PER_TICK = 2  # a backlog (a burst after a delay) catches up this fast
HOLE_WAIT_TICKS = 3  # ticks to wait for a missing input before filling it in
MAX_INPUT_BACKLOG = 60  # inputs (1 s); a longer backlog is skipped
MAX_INPUT_AHEAD = 600  # inputs this far beyond the last one that ran are ignored


class ConnectionState(Enum):
    """Connection state machine states."""

    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    DISCONNECTED = auto()


def _new_tick_counts() -> Dict[str, int]:
    return {
        "ticks": 0,
        "starved": 0,
        "burst": 0,
        "no_step": 0,
        "multi_step": 0,
        "filled": 0,
        "dropped": 0,
        "late_actions": 0,
    }


@dataclass
class ClientState:
    """Tracks state for a connected client.

    Input model: one physics step per client input.
    - Every client tick is one input: the held movement state ([left,
      right]) plus the one-shot actions (jump/dash/shoot) pressed in it.
      The server runs the player one physics step per input, in input
      order, so its trajectory matches the client's prediction step for
      step no matter when the packets arrive (the way the Source engine
      runs player commands). ``take_steps()`` hands out the next inputs
      once per server tick: none if none has arrived (the player waits),
      up to MAX_STEPS_PER_TICK to catch up after a burst.
    - Packets carry the previous few movement states too (``history``),
      so a lost packet leaves no hole; a hole that stays is filled with
      the last movement after HOLE_WAIT_TICKS.
    - Actions carry a sequence number and their client tick, are re-sent
      until the server has run that tick, and are deduplicated by
      ``last_action_seq``. An action whose tick has already run (it only
      arrived after its step was filled in) runs with the next step.
    - The ack for prediction is ``ack_tick``: the newest input that has
      run, so the snapshot state is exactly the client's state after it.

    Attributes:
        player_id: Unique ID assigned to this player
        player_name: Display name for the player
        address: Network address (host, port)
        state: Current connection state
        movement: Newest received held movement state [left, right]
        last_action_seq: Highest action sequence number received
        last_input_tick: Client tick of the newest input packet received
        last_activity: Timestamp of last received message
        rtt_estimate: Estimated round-trip time in seconds
        pending_heartbeat: Timestamp of sent heartbeat awaiting response
        last_input_arrival: Arrival time (wall clock) of the newest input packet
        new_inputs_this_tick: Newer input packets received since the last server tick
        input_queue: Received inputs that have not run yet: tick -> (movement, arrival)
        queued_actions: Actions waiting for their tick to run: tick -> names
        late_actions: Actions whose tick already ran; they run with the next step
        last_processed_tick: Newest input tick that has run (None before the first input)
        last_processed_arrival: Arrival time of that input (0 if it was filled in)
        last_step_move: Movement of the newest input that ran (fills holes)
        hole_wait: Ticks spent waiting for a missing input
        tick_counts: Per report window: server ticks; ticks without a new
            input arriving (starved) and with 2+ (burst); ticks in which the
            player made no step (no_step) and 2+ steps (multi_step); inputs
            filled in, dropped from an overlong backlog, and late actions
        report: The client's own netcode summary (sent with its heartbeats)
        server_view: Compact link summary for this client, echoed in heartbeat acks
    """

    player_id: int
    player_name: str
    address: Address
    state: ConnectionState = ConnectionState.CONNECTED
    movement: List[bool] = field(default_factory=lambda: [False, False])
    last_action_seq: int = 0
    last_input_tick: int = 0
    last_activity: float = field(default_factory=time.time)
    rtt_estimate: float = 0.0
    pending_heartbeat: float = 0.0
    last_input_arrival: float = 0.0
    new_inputs_this_tick: int = 0
    input_queue: Dict[int, Tuple[List[bool], float]] = field(default_factory=dict)
    queued_actions: Dict[int, List[str]] = field(default_factory=dict)
    late_actions: List[str] = field(default_factory=list)
    last_processed_tick: Optional[int] = None
    last_processed_arrival: float = 0.0
    last_step_move: List[bool] = field(default_factory=lambda: [False, False])
    hole_wait: int = 0
    tick_counts: Dict[str, int] = field(default_factory=_new_tick_counts)
    report: Dict[str, Any] = field(default_factory=dict)
    server_view: Dict[str, Any] = field(default_factory=dict)

    @property
    def ack_tick(self) -> int:
        """Newest input tick that has run (0 before the first one)."""
        return self.last_processed_tick if self.last_processed_tick is not None else 0

    def receive_input(
        self,
        tick: int,
        move: List[bool],
        actions: List[List],
        arrival: float = 0.0,
        history: Optional[List[List[bool]]] = None,
    ) -> None:
        """Ingest an input packet from the client.

        Args:
            tick: Client tick of this input
            move: Held movement state [left, right] in that tick
            actions: [seq, name, tick] lists (re-sent until their tick ran);
                [seq, name] means this packet's tick
            arrival: Packet arrival time (wall clock), 0 if unknown
            history: Movement states of the ticks just before, oldest first
        """
        self.last_activity = time.time()
        moves = list(history or []) + [move]
        first = tick - len(moves) + 1
        if self.last_processed_tick is None:
            self.last_processed_tick = first - 1
        if tick > self.last_processed_tick + MAX_INPUT_AHEAD:
            return  # garbage, or a client that restarted its ticks
        if tick > self.last_input_tick:
            self.new_inputs_this_tick += 1
        if tick >= self.last_input_tick:
            self.last_input_tick = tick
            self.movement = [bool(move[0]), bool(move[1])]
            if arrival:
                self.last_input_arrival = arrival
        for i, mv in enumerate(moves):
            t = first + i
            if t > self.last_processed_tick and t not in self.input_queue:
                self.input_queue[t] = ([bool(mv[0]), bool(mv[1])], arrival)
        for action in sorted(actions, key=lambda a: int(a[0])):
            seq, name = int(action[0]), str(action[1])
            if seq <= self.last_action_seq:
                continue
            self.last_action_seq = seq
            action_tick = int(action[2]) if len(action) > 2 else tick
            if action_tick > self.last_processed_tick:
                self.queued_actions.setdefault(action_tick, []).append(name)
            else:
                self.late_actions.append(name)
                self.tick_counts["late_actions"] += 1

    def take_steps(self, max_steps: int = MAX_STEPS_PER_TICK) -> List[Tuple[int, List[bool], List[str]]]:
        """The inputs to run this server tick, in order: (tick, movement, actions).

        Call once per server tick. Empty while the next input has not
        arrived; a missing input with later ones already here is filled in
        with the last movement after HOLE_WAIT_TICKS.
        """
        if self.last_processed_tick is None:
            return []
        if len(self.input_queue) > MAX_INPUT_BACKLOG:
            # Far behind (the client sent faster than we run, or we stalled):
            # skip ahead rather than replay a long past
            keep = sorted(self.input_queue)[-MAX_INPUT_BACKLOG:]
            skipped = keep[0] - 1 - self.last_processed_tick
            self.input_queue = {t: self.input_queue[t] for t in keep}
            for t in [t for t in self.queued_actions if t < keep[0]]:
                self.late_actions.extend(self.queued_actions.pop(t))
            self.last_processed_tick = keep[0] - 1
            self.tick_counts["dropped"] += skipped
        steps: List[Tuple[int, List[bool], List[str]]] = []
        while len(steps) < max_steps:
            nxt = self.last_processed_tick + 1
            entry = self.input_queue.pop(nxt, None)
            if entry is None:
                if not self.input_queue:
                    break  # nothing has arrived yet: the player waits
                if self.hole_wait < HOLE_WAIT_TICKS:
                    self.hole_wait += 1
                    break  # it may still arrive
                entry = (self.last_step_move, 0.0)
                self.tick_counts["filled"] += 1
            self.hole_wait = 0
            move, arrival = entry
            actions = self.late_actions + self.queued_actions.pop(nxt, [])
            self.late_actions = []
            self.last_processed_tick = nxt
            self.last_processed_arrival = arrival
            self.last_step_move = move
            steps.append((nxt, move, actions))
        if self.last_input_arrival:
            if not steps:
                self.tick_counts["no_step"] += 1
            elif len(steps) >= 2:
                self.tick_counts["multi_step"] += 1
        return steps

    def count_tick_inputs(self) -> None:
        """Classify this server tick by how many new inputs arrived (call once per tick)."""
        n = self.new_inputs_this_tick
        self.new_inputs_this_tick = 0
        if not self.last_input_arrival:
            return  # no input yet (just connected)
        self.tick_counts["ticks"] += 1
        if n == 0:
            self.tick_counts["starved"] += 1
        elif n >= 2:
            self.tick_counts["burst"] += 1

    def take_tick_counts(self) -> Dict[str, int]:
        """Return this window's tick classification and start a new window."""
        counts = self.tick_counts
        self.tick_counts = _new_tick_counts()
        return counts

    def update_rtt(self, client_time: float, server_time: float) -> None:
        """Update RTT estimate from heartbeat response.

        Args:
            client_time: Original timestamp from client's heartbeat
            server_time: Current server time
        """
        if self.pending_heartbeat > 0:
            rtt = server_time - self.pending_heartbeat
            # Exponential moving average
            if self.rtt_estimate == 0:
                self.rtt_estimate = rtt
            else:
                self.rtt_estimate = 0.9 * self.rtt_estimate + 0.1 * rtt
            self.pending_heartbeat = 0.0

    def is_timed_out(self, timeout: float = 10.0) -> bool:
        """Check if client has timed out.

        Args:
            timeout: Seconds without activity before timeout

        Returns:
            True if client has exceeded timeout
        """
        return time.time() - self.last_activity > timeout


class ClientManager:
    """Manages all connected clients.

    Handles client lifecycle: connection, tracking, disconnection.
    Assigns unique player IDs.
    """

    def __init__(self, max_clients: int = 4):
        """Initialize client manager.

        Args:
            max_clients: Maximum number of simultaneous clients
        """
        self.clients: Dict[Address, ClientState] = {}
        self.max_clients = max_clients
        self._next_player_id = 1

    def add_client(self, address: Address, player_name: str = "Player") -> ClientState:
        """Add a new client.

        Args:
            address: Client's network address
            player_name: Display name for the player

        Returns:
            The new ClientState

        Raises:
            ValueError: If server is full or client already connected
        """
        if address in self.clients:
            raise ValueError(f"Client already connected: {address}")
        if len(self.clients) >= self.max_clients:
            raise ValueError("Server is full")

        player_id = self._next_player_id
        self._next_player_id += 1

        client = ClientState(
            player_id=player_id,
            player_name=player_name,
            address=address,
        )
        self.clients[address] = client
        return client

    def remove_client(self, address: Address) -> ClientState | None:
        """Remove a client.

        Args:
            address: Client's network address

        Returns:
            The removed ClientState, or None if not found
        """
        return self.clients.pop(address, None)

    def get_client(self, address: Address) -> ClientState | None:
        """Get client by address."""
        return self.clients.get(address)

    def get_client_by_id(self, player_id: int) -> ClientState | None:
        """Get client by player ID."""
        for client in self.clients.values():
            if client.player_id == player_id:
                return client
        return None

    def get_all_clients(self) -> List[ClientState]:
        """Get all connected clients."""
        return list(self.clients.values())

    def get_timed_out_clients(self, timeout: float = 10.0) -> List[ClientState]:
        """Get clients that have timed out."""
        return [c for c in self.clients.values() if c.is_timed_out(timeout)]

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self.clients)

    @property
    def is_full(self) -> bool:
        """Check if server is at capacity."""
        return len(self.clients) >= self.max_clients


__all__ = [
    "ConnectionState",
    "ClientState",
    "ClientManager",
]
