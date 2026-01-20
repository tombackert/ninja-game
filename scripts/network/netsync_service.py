"""Network Synchronization Service (MP-03).

Manages network communication for multiplayer games.
Supports both loopback (testing) and UDP (real network) transports.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, Union

from scripts.network.messages import Message

# Type alias for address tuple
Address = Tuple[str, int]


class LocalLoopbackTransport:
    """Simulates network by placing messages in a local queue."""

    def __init__(self) -> None:
        self.queue: List[Message] = []

    def send(self, message: Message, address: Optional[Address] = None) -> None:
        """Send message to own queue (simulates roundtrip)."""
        serialized = message.to_json()
        self.queue.append(Message.from_json(serialized))

    def receive(self) -> Optional[Message]:
        """Receive message from queue."""
        if self.queue:
            return self.queue.pop(0)
        return None

    def close(self) -> None:
        """Close transport (no-op for loopback)."""
        self.queue.clear()


class NetSyncService:
    """Manages network synchronization for multiplayer games.

    Works with both LocalLoopbackTransport (testing) and UDPTransport (real network).
    When using UDP, a default_address must be provided for send operations.
    """

    def __init__(
        self,
        transport: Any,
        default_address: Optional[Address] = None,
    ) -> None:
        self.transport = transport
        self.default_address = default_address
        # Detect if this is a UDP-style transport (returns tuples with addresses)
        self._is_udp = hasattr(transport, 'local_addr')

    def _send(self, message: Message, address: Optional[Address] = None) -> None:
        """Internal send that handles both transport types."""
        target = address or self.default_address
        if self._is_udp:
            if target is None:
                raise ValueError("UDP transport requires an address")
            self.transport.send(message, target)
        else:
            self.transport.send(message)

    def send_input(self, tick: int, inputs: List[str], address: Optional[Address] = None) -> None:
        """Send player input."""
        msg = Message(type="input", payload={"tick": tick, "inputs": inputs})
        self._send(msg, address)

    def send_snapshot(
        self, tick: int, snapshot_data: Dict[str, Any], address: Optional[Address] = None
    ) -> None:
        """Send game state snapshot."""
        msg = Message(type="snapshot", payload={"tick": tick, "snapshot_data": snapshot_data})
        self._send(msg, address)

    def send_ack(self, tick: int, address: Optional[Address] = None) -> None:
        """Send acknowledgment."""
        msg = Message(type="ack", payload={"tick": tick, "received_ts": time.time()})
        self._send(msg, address)

    def process_messages(self) -> Union[List[Message], List[Tuple[Message, Address]]]:
        """Process all pending incoming messages.

        Returns:
            For loopback transport: List[Message]
            For UDP transport: List[Tuple[Message, Address]] where Address is (host, port)
        """
        messages: List[Any] = []
        while True:
            result = self.transport.receive()
            if not result:
                break
            # Handle both Message (loopback) and tuple (UDP) returns
            if isinstance(result, Message):
                messages.append(result)
            elif isinstance(result, tuple):
                # UDP returns (message, addr, header) - extract message and addr
                message = result[0]
                addr = result[1]
                messages.append((message, addr))
        return messages

    def close(self) -> None:
        """Close the transport and release resources."""
        if hasattr(self.transport, 'close'):
            self.transport.close()
