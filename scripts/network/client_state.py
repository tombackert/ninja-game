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

    Attributes:
        player_id: Unique ID assigned to this player
        player_name: Display name for the player
        address: Network address (host, port)
        state: Current connection state
        input_buffer: Inputs keyed by tick number
        last_ack_tick: Last tick the client acknowledged
        last_activity: Timestamp of last received message
        rtt_estimate: Estimated round-trip time in seconds
        pending_heartbeat: Timestamp of sent heartbeat awaiting response
    """
    player_id: int
    player_name: str
    address: Address
    state: ConnectionState = ConnectionState.CONNECTED
    input_buffer: Dict[int, List[str]] = field(default_factory=dict)
    last_ack_tick: int = 0
    last_activity: float = field(default_factory=time.time)
    rtt_estimate: float = 0.0
    pending_heartbeat: float = 0.0

    def buffer_input(self, tick: int, inputs: List[str]) -> bool:
        """Buffer inputs for a specific tick.

        Args:
            tick: The simulation tick these inputs are for
            inputs: List of input actions

        Returns:
            True if inputs were buffered, False if tick is too old
        """
        self.last_activity = time.time()
        self.input_buffer[tick] = inputs
        return True

    def get_inputs(self, tick: int) -> List[str]:
        """Get and remove buffered inputs up to and including the given tick.

        Merges all buffered inputs from past ticks to handle clock drift
        between client and server.

        Args:
            tick: The simulation tick (inclusive upper bound)

        Returns:
            Combined list of input actions, empty if none buffered
        """
        merged: List[str] = []
        consumed = [t for t in self.input_buffer if t <= tick]
        for t in sorted(consumed):
            merged.extend(self.input_buffer.pop(t))
        return merged

    def has_inputs_for_tick(self, tick: int) -> bool:
        """Check if inputs are buffered for a specific tick."""
        return tick in self.input_buffer

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

    def cleanup_old_inputs(self, current_tick: int, max_age: int = 60) -> int:
        """Remove inputs older than max_age ticks.

        Args:
            current_tick: Current simulation tick
            max_age: Maximum tick age to keep

        Returns:
            Number of inputs removed
        """
        old_ticks = [t for t in self.input_buffer if t < current_tick - max_age]
        for tick in old_ticks:
            del self.input_buffer[tick]
        return len(old_ticks)


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

    def cleanup_all_old_inputs(self, current_tick: int) -> int:
        """Cleanup old inputs for all clients."""
        total = 0
        for client in self.clients.values():
            total += client.cleanup_old_inputs(current_tick)
        return total

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
