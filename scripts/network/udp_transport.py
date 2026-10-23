"""UDP Transport Layer (MP-03).

Implements real UDP networking for multiplayer communication.
Replaces the loopback-only transport with actual socket operations.

Features:
- Non-blocking send/receive operations
- Packet sequencing for ordering (per peer, so receivers can count loss)
- Basic reliability layer (ack tracking)
- Graceful handling of malformed packets
- Per-peer link statistics (loss, jitter, bytes) with kernel arrival
  timestamps where the platform provides them

Usage:
    # Server
    server = UDPTransport(port=7777)

    # Client (ephemeral port)
    client = UDPTransport()
    client.send(msg, ("127.0.0.1", 7777))

    # Receive
    result = server.receive()
    if result:
        message, sender_addr = result
"""

from __future__ import annotations

import json
import socket
import struct
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple

from .messages import Message
from .netstats import LinkStats


# Maximum UDP packet size
MAX_PACKET_SIZE = 65535

# Default timeout for blocking operations (not used in non-blocking mode)
DEFAULT_TIMEOUT = 0.0

# Kernel receive timestamps (SO_TIMESTAMP): when a packet arrived, not when
# the game loop got around to reading it (up to a tick/frame later). Python
# does not export the constants on every platform (macOS), so fall back to
# the platform values.
_SO_TIMESTAMP = getattr(socket, "SO_TIMESTAMP", {"darwin": 0x0400, "linux": 29}.get(sys.platform))
_SCM_TIMESTAMP = getattr(socket, "SCM_TIMESTAMP", {"darwin": 0x02, "linux": 29}.get(sys.platform))
# struct timeval: 64-bit seconds, then microseconds (int32 on macOS, long on
# Linux); 16 bytes either way, padding included
_TIMEVAL = struct.Struct("@qi" if sys.platform == "darwin" else "@qq")
_TIMEVAL_BYTES = 16


@dataclass
class PacketHeader:
    """Header for packet sequencing and reliability.

    Attributes:
        sequence: Packet sequence number (monotonically increasing per peer)
        ack: Last received sequence number from peer
        ack_bitfield: Bitfield of 32 most recent acks (bit 0 = ack-1, bit 1 = ack-2, etc.)
        time: Sender wall-clock time at send (for jitter; 0 = unknown)
    """

    sequence: int = 0
    ack: int = 0
    ack_bitfield: int = 0
    time: float = 0.0


@dataclass
class Packet:
    """Network packet with header and message payload.

    Attributes:
        header: Packet sequencing and reliability info
        message: The actual message being sent
    """

    header: PacketHeader
    message: Message

    def to_bytes(self) -> bytes:
        """Serialize packet to bytes for transmission."""
        data = {
            "header": asdict(self.header),
            "message": {
                "type": self.message.type,
                "payload": self.message.payload,
            },
        }
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def from_bytes(data: bytes) -> Optional[Packet]:
        """Deserialize packet from bytes. Returns None if malformed."""
        try:
            parsed = json.loads(data.decode("utf-8"))
            header = PacketHeader(**parsed["header"])
            message = Message(
                type=parsed["message"]["type"],
                payload=parsed["message"]["payload"],
            )
            return Packet(header=header, message=message)
        except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError):
            return None


class UDPTransport:
    """UDP socket transport for network communication.

    Implements the Transport interface with real UDP sockets.
    All operations are non-blocking.

    Attributes:
        socket: The underlying UDP socket
        local_addr: The (host, port) this transport is bound to
        sequence: Next outgoing packet sequence number for each peer
        remote_sequence: Last received sequence from each peer
        ack_bitfields: Ack bitfields for each peer
        links: Link statistics for each peer
        last_arrival: Arrival time (wall clock) of the packet receive() returned last
        last_send_bytes: Size of the datagram send() sent last
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 0):
        """Initialize UDP transport.

        Args:
            host: Host address to bind to. Default "0.0.0.0" binds to all interfaces.
            port: Port to bind to. Default 0 lets OS assign an ephemeral port.
        """
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind((host, port))
        self.local_addr: Tuple[str, int] = self._socket.getsockname()
        self._rx_timestamps = self._enable_rx_timestamps()

        # Packet sequencing (per peer: a receiver sees a gap-free stream
        # unless packets are lost, which is what loss counting relies on)
        self._sequences: Dict[Tuple[str, int], int] = {}
        self._remote_sequences: Dict[Tuple[str, int], int] = {}
        self._ack_bitfields: Dict[Tuple[str, int], int] = {}

        # Link statistics
        self.links: Dict[Tuple[str, int], LinkStats] = {}
        self.last_arrival = 0.0
        self.last_send_bytes = 0

    def _enable_rx_timestamps(self) -> bool:
        if _SO_TIMESTAMP is None or _SCM_TIMESTAMP is None or not hasattr(self._socket, "recvmsg"):
            return False
        try:
            self._socket.setsockopt(socket.SOL_SOCKET, _SO_TIMESTAMP, 1)
        except OSError:
            return False
        return True

    @property
    def port(self) -> int:
        """Get the port this transport is bound to."""
        return self.local_addr[1]

    def send(self, message: Message, address: Tuple[str, int]) -> bool:
        """Send a message to the specified address.

        Args:
            message: The message to send
            address: Destination (host, port) tuple

        Returns:
            True if send succeeded, False otherwise
        """
        # Build packet with header
        sequence = self._sequences.get(address, 0)
        header = PacketHeader(
            sequence=sequence,
            ack=self._remote_sequences.get(address, 0),
            ack_bitfield=self._ack_bitfields.get(address, 0),
            time=round(time.time(), 4),
        )
        packet = Packet(header=header, message=message)

        try:
            data = packet.to_bytes()
            if len(data) > MAX_PACKET_SIZE:
                return False  # Packet too large
            self._socket.sendto(data, address)
            self._sequences[address] = sequence + 1
            self.last_send_bytes = len(data)
            self.link(address).on_send(len(data))
            return True
        except (OSError, socket.error):
            return False

    def receive(self) -> Optional[Tuple[Message, Tuple[str, int], PacketHeader]]:
        """Receive a message if one is available.

        Non-blocking: returns None immediately if no message is waiting.

        Returns:
            Tuple of (message, sender_address, header) if a message was received,
            None if no message available or packet was malformed.
        """
        try:
            if self._rx_timestamps:
                data, ancdata, _flags, addr = self._socket.recvmsg(MAX_PACKET_SIZE, socket.CMSG_SPACE(_TIMEVAL_BYTES))
                arrival = _kernel_arrival(ancdata)
            else:
                data, addr = self._socket.recvfrom(MAX_PACKET_SIZE)
                arrival = 0.0
            packet = Packet.from_bytes(data)

            if packet is None:
                return None  # Malformed packet

            # Update ack tracking and link statistics for this peer
            self._update_ack_tracking(addr, packet.header.sequence)
            self.last_arrival = arrival or time.time()
            self.link(addr).on_receive(packet.header.sequence, len(data), self.last_arrival, packet.header.time)

            return (packet.message, addr, packet.header)

        except BlockingIOError:
            return None  # No data available
        except (OSError, socket.error):
            return None  # Socket error

    def _update_ack_tracking(self, addr: Tuple[str, int], sequence: int) -> None:
        """Update ack tracking when a packet is received from a peer."""
        prev_seq = self._remote_sequences.get(addr, -1)

        if sequence > prev_seq:
            # New highest sequence - shift bitfield
            if prev_seq >= 0:
                shift = sequence - prev_seq
                old_bitfield = self._ack_bitfields.get(addr, 0)
                # Shift and set bit for previous sequence
                new_bitfield = (old_bitfield << shift) | (1 << (shift - 1))
                # Keep only 32 bits
                self._ack_bitfields[addr] = new_bitfield & 0xFFFFFFFF
            self._remote_sequences[addr] = sequence
        elif sequence < prev_seq:
            # Out of order packet - set appropriate bit
            diff = prev_seq - sequence
            if diff <= 32:
                self._ack_bitfields[addr] = self._ack_bitfields.get(addr, 0) | (1 << (diff - 1))

    def link(self, address: Tuple[str, int]) -> LinkStats:
        """Link statistics for a peer (created on first use)."""
        stats = self.links.get(address)
        if stats is None:
            stats = self.links[address] = LinkStats()
        return stats

    def forget(self, address: Tuple[str, int]) -> None:
        """Drop all per-peer state (sequences, acks, link statistics)."""
        for table in (self._sequences, self._remote_sequences, self._ack_bitfields, self.links):
            table.pop(address, None)

    def get_ack_status(self, address: Tuple[str, int]) -> Tuple[int, int]:
        """Get the current ack status for a peer.

        Args:
            address: The peer address

        Returns:
            Tuple of (last_acked_sequence, ack_bitfield)
        """
        return (
            self._remote_sequences.get(address, 0),
            self._ack_bitfields.get(address, 0),
        )

    def was_packet_acked(self, address: Tuple[str, int], sequence: int) -> bool:
        """Check if a specific packet sequence was acknowledged by a peer.

        Args:
            address: The peer address
            sequence: The sequence number to check

        Returns:
            True if the packet was acknowledged
        """
        last_ack = self._remote_sequences.get(address, -1)
        if sequence == last_ack:
            return True
        if sequence < last_ack:
            diff = last_ack - sequence
            if diff <= 32:
                bitfield = self._ack_bitfields.get(address, 0)
                return bool(bitfield & (1 << (diff - 1)))
        return False

    def close(self) -> None:
        """Close the transport and release resources."""
        try:
            self._socket.close()
        except (OSError, socket.error):
            pass

    def __enter__(self) -> UDPTransport:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _kernel_arrival(ancdata) -> float:
    """Arrival time from an SCM_TIMESTAMP control message (0.0 if absent)."""
    for level, kind, data in ancdata:
        if level == socket.SOL_SOCKET and kind == _SCM_TIMESTAMP and len(data) >= _TIMEVAL.size:
            sec, usec = _TIMEVAL.unpack_from(data)
            return sec + usec / 1e6
    return 0.0


class UDPClient:
    """Convenience wrapper for client-side UDP communication.

    Maintains connection to a single server address.
    """

    def __init__(self, server_host: str, server_port: int, local_port: int = 0):
        """Initialize client.

        Args:
            server_host: Server hostname or IP
            server_port: Server port
            local_port: Local port to bind to (0 for ephemeral)
        """
        self.transport = UDPTransport(port=local_port)
        self.server_addr = (server_host, server_port)

    def send(self, message: Message) -> bool:
        """Send message to server."""
        return self.transport.send(message, self.server_addr)

    def receive(self) -> Optional[Tuple[Message, PacketHeader]]:
        """Receive message from server."""
        result = self.transport.receive()
        if result is None:
            return None
        message, addr, header = result
        # Only accept messages from our server
        if addr == self.server_addr:
            return (message, header)
        return None

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> UDPClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class UDPServer:
    """Convenience wrapper for server-side UDP communication.

    Handles multiple clients and tracks their addresses.
    """

    def __init__(self, port: int, host: str = "0.0.0.0"):
        """Initialize server.

        Args:
            port: Port to listen on
            host: Host address to bind to
        """
        self.transport = UDPTransport(host=host, port=port)
        self.clients: Dict[Tuple[str, int], float] = {}  # addr -> last_seen timestamp

    def send(self, message: Message, client_addr: Tuple[str, int]) -> bool:
        """Send message to a specific client."""
        return self.transport.send(message, client_addr)

    def broadcast(self, message: Message) -> int:
        """Send message to all known clients.

        Returns:
            Number of clients the message was sent to
        """
        count = 0
        for addr in self.clients:
            if self.transport.send(message, addr):
                count += 1
        return count

    def receive(self) -> Optional[Tuple[Message, Tuple[str, int], PacketHeader]]:
        """Receive message from any client."""
        result = self.transport.receive()
        if result:
            message, addr, header = result
            import time

            self.clients[addr] = time.time()
        return result

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> UDPServer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


__all__ = [
    "PacketHeader",
    "Packet",
    "UDPTransport",
    "UDPClient",
    "UDPServer",
    "MAX_PACKET_SIZE",
]
