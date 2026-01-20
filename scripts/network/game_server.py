"""Game Server Implementation (MP-04).

Authoritative game server that manages multiplayer simulation.
Receives inputs from clients, runs the game loop, and broadcasts state.

Usage:
    server = GameServer(port=7777)
    server.start()

    # In game loop:
    while running:
        server.update()

    server.shutdown()
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.network.client_state import ClientManager, ClientState, ConnectionState
from scripts.network.delta import compute_delta
from scripts.network.messages import (
    ConnectionAccept,
    ConnectionReject,
    ConnectionRequest,
    Heartbeat,
    HeartbeatAck,
    Message,
    PlayerJoined,
    PlayerLeft,
)
from scripts.network.udp_transport import UDPTransport
from scripts.snapshot import SimulationSnapshot, SnapshotService

# Type alias
Address = Tuple[str, int]


class GameServer:
    """Authoritative multiplayer game server.

    The server:
    - Accepts client connections and assigns player IDs
    - Receives and buffers client inputs by tick
    - Runs the authoritative game simulation
    - Broadcasts state snapshots to all clients

    Attributes:
        transport: UDP transport for network communication
        clients: Manager for connected clients
        game: The game instance (set via set_game or start)
        tick: Current simulation tick
    """

    # Broadcast snapshot every N ticks (~20 Hz at 60 fps)
    SNAPSHOT_INTERVAL = 3

    # How many ticks in the future to accept inputs
    INPUT_FUTURE_WINDOW = 30

    # How many ticks in the past to accept inputs
    INPUT_PAST_WINDOW = 10

    # Client timeout in seconds
    CLIENT_TIMEOUT = 10.0

    def __init__(
        self,
        port: int = 7777,
        max_clients: int = 4,
        game: Any = None,
    ):
        """Initialize game server.

        Args:
            port: Port to listen on
            max_clients: Maximum number of clients
            game: Optional game instance to use
        """
        self.transport = UDPTransport("0.0.0.0", port)
        self.clients = ClientManager(max_clients=max_clients)
        self.game = game
        self._last_snapshot_tick = 0
        self._last_full_snapshot: Optional[SimulationSnapshot] = None
        self._running = False

        # Callbacks for game events
        self._on_player_join: Optional[Callable[[int, str], None]] = None
        self._on_player_leave: Optional[Callable[[int, str], None]] = None

    @property
    def port(self) -> int:
        """Get the server port."""
        return self.transport.port

    @property
    def tick(self) -> int:
        """Get current game tick."""
        return getattr(self.game, "tick", 0) if self.game else 0

    def set_game(self, game: Any) -> None:
        """Set the game instance.

        Args:
            game: Game instance with tick, players, enemies attributes
        """
        self.game = game

    def on_player_join(self, callback: Callable[[int, str], None]) -> None:
        """Register callback for player join events.

        Args:
            callback: Function(player_id, player_name) called when player joins
        """
        self._on_player_join = callback

    def on_player_leave(self, callback: Callable[[int, str], None]) -> None:
        """Register callback for player leave events.

        Args:
            callback: Function(player_id, reason) called when player leaves
        """
        self._on_player_leave = callback

    def update(self) -> None:
        """Run one server update cycle.

        This should be called once per game tick (60 Hz).
        Processes incoming messages, applies inputs, and broadcasts snapshots.
        """
        # 1. Process all incoming messages
        self._process_incoming_messages()

        # 2. Check for timed out clients
        self._check_timeouts()

        # 3. Apply buffered inputs for this tick
        if self.game:
            self._apply_client_inputs()

        # 4. Broadcast snapshot if interval reached
        if self.game and self.tick - self._last_snapshot_tick >= self.SNAPSHOT_INTERVAL:
            self._broadcast_snapshot()
            self._last_snapshot_tick = self.tick

    def _process_incoming_messages(self) -> None:
        """Process all pending incoming messages."""
        while True:
            result = self.transport.receive()
            if result is None:
                break

            message, addr, header = result
            self._handle_message(message, addr)

    def _handle_message(self, message: Message, addr: Address) -> None:
        """Handle a single incoming message.

        Args:
            message: The received message
            addr: Sender's address
        """
        msg_type = message.type
        payload = message.payload

        if msg_type == "connect_request":
            self._handle_connect_request(payload, addr)
        elif msg_type == "input":
            self._handle_input(payload, addr)
        elif msg_type == "heartbeat":
            self._handle_heartbeat(payload, addr)
        elif msg_type == "disconnect":
            self._handle_disconnect(addr)

    def _handle_connect_request(self, payload: Dict[str, Any], addr: Address) -> None:
        """Handle connection request from new client."""
        player_name = payload.get("player_name", "Player")

        # Check if already connected
        existing = self.clients.get_client(addr)
        if existing:
            # Re-send accept (client may not have received it)
            self._send_connection_accept(existing, addr)
            return

        # Check if server is full
        if self.clients.is_full:
            self._send_connection_reject("Server is full", addr)
            return

        # Accept connection
        try:
            client = self.clients.add_client(addr, player_name)
            self._send_connection_accept(client, addr)

            # Notify other clients
            self._broadcast_player_joined(client)

            # Trigger callback
            if self._on_player_join:
                self._on_player_join(client.player_id, client.player_name)

        except ValueError as e:
            self._send_connection_reject(str(e), addr)

    def _send_connection_accept(self, client: ClientState, addr: Address) -> None:
        """Send connection acceptance to client."""
        msg = Message(
            type="connect_accept",
            payload={
                "player_id": client.player_id,
                "server_tick": self.tick,
            },
        )
        self.transport.send(msg, addr)

    def _send_connection_reject(self, reason: str, addr: Address) -> None:
        """Send connection rejection to client."""
        msg = Message(
            type="connect_reject",
            payload={"reason": reason},
        )
        self.transport.send(msg, addr)

    def _broadcast_player_joined(self, new_client: ClientState) -> None:
        """Broadcast player joined message to all other clients."""
        msg = Message(
            type="player_joined",
            payload={
                "player_id": new_client.player_id,
                "player_name": new_client.player_name,
            },
        )
        for client in self.clients.get_all_clients():
            if client.address != new_client.address:
                self.transport.send(msg, client.address)

    def _handle_input(self, payload: Dict[str, Any], addr: Address) -> None:
        """Handle input message from client."""
        client = self.clients.get_client(addr)
        if not client:
            return  # Unknown client

        tick = payload.get("tick", 0)
        inputs = payload.get("inputs", [])

        # Validate tick is within acceptable window
        if not self._is_valid_input_tick(tick):
            return  # Ignore out-of-range inputs

        # Buffer the inputs
        client.buffer_input(tick, inputs)

    def _is_valid_input_tick(self, input_tick: int) -> bool:
        """Check if input tick is within acceptable range."""
        current = self.tick
        return (current - self.INPUT_PAST_WINDOW <= input_tick <=
                current + self.INPUT_FUTURE_WINDOW)

    def _handle_heartbeat(self, payload: Dict[str, Any], addr: Address) -> None:
        """Handle heartbeat from client."""
        client = self.clients.get_client(addr)
        if not client:
            return

        client_time = payload.get("client_time", 0.0)
        server_time = time.time()

        # Update client activity
        client.last_activity = server_time

        # Send heartbeat response
        msg = Message(
            type="heartbeat_ack",
            payload={
                "client_time": client_time,
                "server_time": server_time,
            },
        )
        self.transport.send(msg, addr)

    def _handle_disconnect(self, addr: Address) -> None:
        """Handle disconnect message from client."""
        self._remove_client(addr, "disconnected")

    def _check_timeouts(self) -> None:
        """Check for and remove timed out clients."""
        timed_out = self.clients.get_timed_out_clients(self.CLIENT_TIMEOUT)
        for client in timed_out:
            self._remove_client(client.address, "timeout")

    def _remove_client(self, addr: Address, reason: str) -> None:
        """Remove a client and notify others."""
        client = self.clients.remove_client(addr)
        if not client:
            return

        # Notify other clients
        msg = Message(
            type="player_left",
            payload={
                "player_id": client.player_id,
                "reason": reason,
            },
        )
        for other in self.clients.get_all_clients():
            self.transport.send(msg, other.address)

        # Trigger callback
        if self._on_player_leave:
            self._on_player_leave(client.player_id, reason)

    def _apply_client_inputs(self) -> None:
        """Apply buffered inputs for the current tick."""
        if not self.game:
            return

        current_tick = self.tick

        for client in self.clients.get_all_clients():
            inputs = client.get_inputs(current_tick)
            if inputs:
                self._apply_inputs_to_player(client.player_id, inputs)

        # Cleanup old inputs periodically
        if current_tick % 60 == 0:
            self.clients.cleanup_all_old_inputs(current_tick)

    def _apply_inputs_to_player(self, player_id: int, inputs: List[str]) -> None:
        """Apply input actions to a player entity.

        Args:
            player_id: The player's ID
            inputs: List of input actions (e.g., ["left", "jump"])
        """
        if not self.game or not hasattr(self.game, "players"):
            return

        # Find player by ID
        player = None
        for p in self.game.players:
            if getattr(p, "id", None) == player_id:
                player = p
                break

        if not player:
            return

        # Apply movement inputs
        # This maps to how the game processes inputs
        movement = [False, False]  # [left, right]

        for action in inputs:
            if action == "left":
                movement[0] = True
            elif action == "right":
                movement[1] = True
            elif action == "jump":
                player.jump()
            elif action == "dash":
                player.dash()
            elif action == "shoot":
                if hasattr(player, "shoot"):
                    player.shoot()

        # Apply movement to player
        # The actual movement vector is computed from left/right
        player_movement = (movement[1] - movement[0], 0)
        if hasattr(player, "update"):
            # Movement will be applied during entity update
            # Store it for the game loop to use
            if hasattr(self.game, "_pending_inputs"):
                self.game._pending_inputs[player_id] = player_movement

    def _broadcast_snapshot(self) -> None:
        """Broadcast game state snapshot to all clients."""
        if not self.game:
            return

        # Capture current state
        snapshot = SnapshotService.capture(self.game)

        # Compute delta if we have a previous snapshot
        if self._last_full_snapshot:
            delta = compute_delta(self._last_full_snapshot, snapshot)
            msg = Message(
                type="snapshot",
                payload={
                    "tick": snapshot.tick,
                    "is_delta": True,
                    "data": delta,
                },
            )
        else:
            # Send full snapshot
            msg = Message(
                type="snapshot",
                payload={
                    "tick": snapshot.tick,
                    "is_delta": False,
                    "data": SnapshotService.serialize(snapshot),
                },
            )

        # Broadcast to all clients
        for client in self.clients.get_all_clients():
            self.transport.send(msg, client.address)

        self._last_full_snapshot = snapshot

    def get_client_count(self) -> int:
        """Get number of connected clients."""
        return self.clients.client_count

    def get_client_info(self) -> List[Dict[str, Any]]:
        """Get info about all connected clients."""
        return [
            {
                "player_id": c.player_id,
                "player_name": c.player_name,
                "address": c.address,
                "rtt": c.rtt_estimate,
            }
            for c in self.clients.get_all_clients()
        ]

    def shutdown(self) -> None:
        """Shutdown the server."""
        self._running = False

        # Notify all clients
        msg = Message(
            type="server_shutdown",
            payload={"reason": "Server shutting down"},
        )
        for client in self.clients.get_all_clients():
            self.transport.send(msg, client.address)

        self.transport.close()

    def __enter__(self) -> GameServer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()


__all__ = ["GameServer"]
