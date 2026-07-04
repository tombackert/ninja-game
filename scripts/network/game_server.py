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
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.network.client_state import ClientManager, ClientState
from scripts.network.delta import compute_delta
from scripts.network.messages import Message
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

    # Broadcast snapshot every N ticks (~30 Hz at 60 fps)
    SNAPSHOT_INTERVAL = 2

    # Every Nth broadcast is a full snapshot to recover from UDP packet loss
    FULL_SNAPSHOT_INTERVAL = 30

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
        self._clients_needing_full: set[Address] = set()
        self._snapshot_broadcast_count = 0
        self._running = False
        # Lightweight performance counters (read by server.py metrics loop)
        self.stats: Dict[str, int] = {
            "snapshots_sent": 0,
            "last_snapshot_bytes": 0,
        }

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

    def process_inputs(self) -> None:
        """Process incoming messages and apply inputs. Call BEFORE simulate_tick."""
        self._process_incoming_messages()
        self._check_timeouts()
        if self.game:
            self._apply_client_inputs()

    def post_tick(self) -> None:
        """Broadcast snapshot if needed. Call AFTER simulate_tick."""
        if self.game and self.tick - self._last_snapshot_tick >= self.SNAPSHOT_INTERVAL:
            self._broadcast_snapshot()
            self._last_snapshot_tick = self.tick

    def update(self) -> None:
        """Run one server update cycle (legacy combined method).

        Prefer using process_inputs() → simulate_tick() → post_tick() instead.
        """
        self.process_inputs()
        self.post_tick()

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
        elif msg_type == "request_full":
            self._handle_request_full(addr)

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
            self._clients_needing_full.add(addr)
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
                "level": getattr(self.game, "level", 0) if self.game else 0,
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
        """Handle input message from client (held movement state + action events)."""
        client = self.clients.get_client(addr)
        if not client:
            return  # Unknown client

        tick = payload.get("tick", 0)
        move = payload.get("move", [False, False])
        actions = payload.get("actions", [])
        client.receive_input(tick, move, actions)

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

    def _handle_request_full(self, addr: Address) -> None:
        """Client detected a broken delta chain; send it a full snapshot."""
        if self.clients.get_client(addr) is not None:
            self._clients_needing_full.add(addr)

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
        """Apply each client's held movement state and queued actions.

        Movement is applied every tick from the latest known state, so
        clock drift or lost packets never freeze or drop movement.
        One-shot actions fire exactly once (deduplicated by sequence).
        """
        if not self.game or not hasattr(self.game, "players"):
            return

        players_by_id = {getattr(p, "id", None): p for p in self.game.players}

        for client in self.clients.get_all_clients():
            player = players_by_id.get(client.player_id)
            if player is None:
                client.drain_actions()
                continue

            for action in client.drain_actions():
                if action == "jump":
                    player.jump()
                elif action == "dash":
                    player.dash()
                elif action == "shoot":
                    # Prefer the game's multiplayer shoot hook (per-player ammo);
                    # fall back to the entity's own shoot.
                    if hasattr(self.game, "player_shoot"):
                        self.game.player_shoot(player)
                    elif hasattr(player, "shoot"):
                        player.shoot()

            movement = (int(client.movement[1]) - int(client.movement[0]), 0)
            if hasattr(self.game, "_pending_inputs"):
                self.game._pending_inputs[client.player_id] = movement

    def _broadcast_snapshot(self) -> None:
        """Broadcast game state snapshot to all clients.

        Sends full snapshots to newly-connected clients and deltas to the rest.
        Periodically forces a full snapshot to all clients to recover from
        UDP packet loss that would otherwise corrupt the delta chain.
        """
        if not self.game:
            return

        # Capture current state (without RNG state: clients never restore it
        # and the Mersenne tuple would add ~5KB of JSON to every snapshot)
        snapshot = SnapshotService.capture(self.game, include_rng=False)

        # Per-player input acknowledgements (client tick of newest applied
        # input) — clients use these for prediction reconciliation.
        acks = {str(c.player_id): c.last_input_tick for c in self.clients.get_all_clients()}

        # Prepare full snapshot message
        full_msg = Message(
            type="snapshot",
            payload={
                "tick": snapshot.tick,
                "is_delta": False,
                "acks": acks,
                "data": SnapshotService.serialize(snapshot),
            },
        )

        # Check if this broadcast should force full snapshots to everyone
        self._snapshot_broadcast_count += 1
        force_full = self._snapshot_broadcast_count % self.FULL_SNAPSHOT_INTERVAL == 0

        self.stats["last_snapshot_bytes"] = len(full_msg.to_json())
        self.stats["snapshots_sent"] += 1

        if force_full:
            # Send full snapshot to all clients to reset delta chain
            for client in self.clients.get_all_clients():
                self.transport.send(full_msg, client.address)
            self._clients_needing_full.clear()
        else:
            # Prepare delta message if we have a previous snapshot
            delta_msg = None
            if self._last_full_snapshot:
                delta = compute_delta(self._last_full_snapshot, snapshot)
                delta_msg = Message(
                    type="snapshot",
                    payload={
                        "tick": snapshot.tick,
                        "is_delta": True,
                        # Clients verify their base matches before applying
                        "base_tick": self._last_full_snapshot.tick,
                        "acks": acks,
                        "data": delta,
                    },
                )
                self.stats["last_delta_bytes"] = len(delta_msg.to_json())

            # Send per-client: full to new clients, delta to established ones
            for client in self.clients.get_all_clients():
                if client.address in self._clients_needing_full or delta_msg is None:
                    self.transport.send(full_msg, client.address)
                    self._clients_needing_full.discard(client.address)
                else:
                    self.transport.send(delta_msg, client.address)

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
