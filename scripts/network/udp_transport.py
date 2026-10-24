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
- Dual stack: bound to ``::``, one socket talks IPv4 and IPv6 (peers are
  plain ``(host, port)`` tuples either way; IPv4 never shows up as
  ``::ffff:a.b.c.d``)
- Non-game packets (STUN answers) go to ``raw_handler``

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
from typing import Callable, Dict, Optional, Tuple

from .messages import Message
from .netstats import LinkStats
from .stun import is_stun


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
        raw_handler: Called with (data, addr) for STUN packets instead of
            dropping them as malformed
    """

    def __init__(self, host: str = "::", port: int = 0):
        """Initialize UDP transport.

        Args:
            host: Host address to bind to. Default "::" binds to all
                interfaces, IPv6 and IPv4 (falls back to IPv4 only where
                the system has no IPv6).
            port: Port to bind to. Default 0 lets OS assign an ephemeral port.
        """
        self._socket = _bind(host, port)
        self._socket.setblocking(False)
        self.ipv6 = self._socket.family == socket.AF_INET6
        self.local_addr: Tuple[str, int] = normalize_address(self._socket.getsockname())
        self._rx_timestamps = self._enable_rx_timestamps()
        self.raw_handler: Optional[Callable[[bytes, Tuple[str, int]], object]] = None

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
            self._socket.sendto(data, self._sockaddr(address))
            self._sequences[address] = sequence + 1
            self.last_send_bytes = len(data)
            self.link(address).on_send(len(data))
            return True
        except (OSError, socket.error):
            return False

    def send_raw(self, data: bytes, address: Tuple[str, int]) -> bool:
        """Send bytes as they are (STUN), outside the game protocol."""
        try:
            self._socket.sendto(data, self._sockaddr(address))
            return True
        except (OSError, socket.error, ValueError):
            return False

    def _sockaddr(self, address: Tuple[str, int]) -> Tuple:
        """The socket address for a peer: IPv4 is v4-mapped on the dual-stack socket."""
        host, port = address[0], address[1]
        if not self.ipv6:
            return (host, port)
        if ":" in host:
            return (host, port, 0, 0)
        return ("::ffff:" + host, port, 0, 0)

    def receive(self) -> Optional[Tuple[Message, Tuple[str, int], PacketHeader]]:
        """Receive a message if one is available.

        Non-blocking: returns None immediately if no message is waiting.
        STUN packets go to ``raw_handler`` and are skipped.

        Returns:
            Tuple of (message, sender_address, header) if a message was received,
            None if no message available or packet was malformed.
        """
        while True:
            try:
                if self._rx_timestamps:
                    data, ancdata, _flags, sockaddr = self._socket.recvmsg(
                        MAX_PACKET_SIZE, socket.CMSG_SPACE(_TIMEVAL_BYTES)
                    )
                    arrival = _kernel_arrival(ancdata)
                else:
                    data, sockaddr = self._socket.recvfrom(MAX_PACKET_SIZE)
                    arrival = 0.0
            except BlockingIOError:
                return None  # No data available
            except (OSError, socket.error):
                return None  # Socket error
            addr = normalize_address(sockaddr)
            if is_stun(data):
                if self.raw_handler is not None:
                    self.raw_handler(data, addr)
                continue
            return self._accept(data, addr, arrival)

    def _accept(
        self, data: bytes, addr: Tuple[str, int], arrival: float
    ) -> Optional[Tuple[Message, Tuple[str, int], PacketHeader]]:
        """Parse a game packet and update the peer's ack tracking and link statistics."""
        packet = Packet.from_bytes(data)
        if packet is None:
            return None  # Malformed packet

        # Update ack tracking and link statistics for this peer
        self._update_ack_tracking(addr, packet.header.sequence)
        self.last_arrival = arrival or time.time()
        self.link(addr).on_receive(packet.header.sequence, len(data), self.last_arrival, packet.header.time)

        return (packet.message, addr, packet.header)

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


def _bind(host: str, port: int) -> socket.socket:
    """A UDP socket bound to host:port; "::" is dual stack, IPv4 only without IPv6."""
    if ":" in host and socket.has_ipv6:
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            try:
                if host == "::":
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                sock.bind((host, port))
                return sock
            except OSError:
                sock.close()
                if host != "::":
                    raise
        except OSError:
            if host != "::":
                raise
        host = "0.0.0.0"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    return sock


def normalize_address(sockaddr: Tuple) -> Tuple[str, int]:
    """(host, port) for any socket address: v4-mapped IPv6 becomes plain IPv4,
    IPv6 is written in its canonical (compressed, lower case) form."""
    host, port = sockaddr[0], sockaddr[1]
    if host.startswith("::ffff:") and "." in host:
        return host[7:], port
    if ":" in host and "%" not in host:
        try:
            host = socket.inet_ntop(socket.AF_INET6, socket.inet_pton(socket.AF_INET6, host))
        except OSError:
            pass
    return host, port


def resolve_address(host: str, port: int) -> Tuple[str, int]:
    """A peer address as receive() will report it: numeric and normalized.

    Host names are resolved once (blocking DNS); an unresolvable name is
    returned as it is, so sending to it simply fails.
    """
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_DGRAM)
    except (OSError, UnicodeError):
        return host, port
    # Prefer IPv4 for names like "localhost" that resolve to both
    infos.sort(key=lambda info: info[0] != socket.AF_INET)
    return normalize_address(infos[0][4])


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
