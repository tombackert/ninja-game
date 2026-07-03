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
from typing import Dict, List, Tuple

# Type alias for network address
Address = Tuple[str, int]


class ConnectionState(Enum):
    """Connection state machine states."""

    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    DISCONNECTED = auto()


@dataclass
class ClientState:
    """Tracks state for a connected client.

    Input model (state + events):
    - ``movement`` holds the most recently received held-key state
      ([left, right]). The server applies it every tick, so clock drift
      between client and server never drops movement.
    - ``pending_actions`` queues one-shot actions (jump/dash/shoot).
      Clients send each action with a monotonically increasing sequence
      number and re-send unacknowledged actions in every packet;
      ``last_action_seq`` deduplicates them here.

    Attributes:
        player_id: Unique ID assigned to this player
        player_name: Display name for the player
        address: Network address (host, port)
        state: Current connection state
        movement: Latest held movement state [left, right]
        pending_actions: One-shot actions awaiting application this tick
        last_action_seq: Highest action sequence number processed
        last_input_tick: Client tick of the newest input packet (echoed as ack)
        last_activity: Timestamp of last received message
        rtt_estimate: Estimated round-trip time in seconds
        pending_heartbeat: Timestamp of sent heartbeat awaiting response
    """

    player_id: int
    player_name: str
    address: Address
    state: ConnectionState = ConnectionState.CONNECTED
    movement: List[bool] = field(default_factory=lambda: [False, False])
    pending_actions: List[str] = field(default_factory=list)
    last_action_seq: int = 0
    last_input_tick: int = 0
    last_activity: float = field(default_factory=time.time)
    rtt_estimate: float = 0.0
    pending_heartbeat: float = 0.0

    def receive_input(self, tick: int, move: List[bool], actions: List[List]) -> None:
        """Ingest an input packet from the client.

        Args:
            tick: Client tick the packet was generated at
            move: Held movement state [left, right]
            actions: List of [seq, name] pairs (includes re-sent unacked ones)
        """
        self.last_activity = time.time()
        # Movement is last-writer-wins; ignore stale (out-of-order) packets.
        if tick >= self.last_input_tick:
            self.last_input_tick = tick
            self.movement = [bool(move[0]), bool(move[1])]
        # Actions are deduplicated by sequence number.
        new_actions = sorted((int(seq), str(name)) for seq, name in actions if int(seq) > self.last_action_seq)
        for seq, name in new_actions:
            self.pending_actions.append(name)
            self.last_action_seq = seq

    def drain_actions(self) -> List[str]:
        """Return and clear the queued one-shot actions."""
        actions = self.pending_actions
        self.pending_actions = []
        return actions

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
