"""Network Synchronization Service (MP-03).

Manages network communication for multiplayer games.
Supports both loopback (testing) and UDP (real network) transports.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from scripts.network.messages import Message

# Type alias for address tuple
Address = Tuple[str, int]

# Sentinel address for loopback transport
LOOPBACK_ADDRESS: Address = ("127.0.0.1", 0)


class LocalLoopbackTransport:
    """Simulates network by placing messages in a local queue."""

    def __init__(self) -> None:
        self.queue: List[Tuple[Message, Address]] = []

    def send(self, message: Message, address: Address = LOOPBACK_ADDRESS) -> None:
        """Send message to own queue (simulates roundtrip)."""
        serialized = message.to_json()
        self.queue.append((Message.from_json(serialized), address))

    def receive(self) -> Optional[Tuple[Message, Address]]:
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
    Both transports return tuples from receive(), enabling uniform message processing.
    """

    def __init__(
        self,
        transport: Any,
        default_address: Address = LOOPBACK_ADDRESS,
    ) -> None:
        self.transport = transport
        self.default_address = default_address

    def _send(self, message: Message, address: Optional[Address] = None) -> None:
        """Internal send that handles both transport types."""
        self.transport.send(message, address or self.default_address)

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

    def process_messages(self) -> List[Tuple[Message, Address]]:
        """Process all pending incoming messages.

        Returns:
            List[Tuple[Message, Address]] — uniform for both loopback and UDP transports.
        """
        messages: List[Tuple[Message, Address]] = []
        while True:
            result = self.transport.receive()
            if not result:
                break
            # Both transports return tuples; extract message and address (index 0, 1)
            messages.append((result[0], result[1]))
        return messages

    def close(self) -> None:
        """Close the transport and release resources."""
        if hasattr(self.transport, 'close'):
            self.transport.close()
