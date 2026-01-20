"""Network Synchronization Service (MP-03).

Manages network communication for multiplayer games.
Supports both loopback (testing) and UDP (real network) transports.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from scripts.network.messages import Message


class LocalLoopbackTransport:
    """Simulates network by placing messages in a local queue."""

    def __init__(self) -> None:
        self.queue: List[Message] = []

    def send(self, message: Message) -> None:
        """Send message to own queue (simulates roundtrip)."""
        serialized = message.to_json()
        self.queue.append(Message.from_json(serialized))

    def receive(self) -> Optional[Message]:
        """Receive message from queue."""
        if self.queue:
            return self.queue.pop(0)
        return None


class NetSyncService:
    """Manages network synchronization for multiplayer games."""

    def __init__(self, transport: Any) -> None:
        self.transport = transport

    def send_input(self, tick: int, inputs: List[str]) -> None:
        """Send player input."""
        msg = Message(type="input", payload={"tick": tick, "inputs": inputs})
        self.transport.send(msg)

    def send_snapshot(self, tick: int, snapshot_data: Dict[str, Any]) -> None:
        """Send game state snapshot."""
        msg = Message(type="snapshot", payload={"tick": tick, "snapshot_data": snapshot_data})
        self.transport.send(msg)

    def send_ack(self, tick: int) -> None:
        """Send acknowledgment."""
        msg = Message(type="ack", payload={"tick": tick, "received_ts": time.time()})
        self.transport.send(msg)

    def process_messages(self) -> List[Message]:
        """Process all pending incoming messages."""
        messages: List[Message] = []
        while True:
            result = self.transport.receive()
            if not result:
                break
            # Handle both Message (loopback) and tuple (UDP) returns
            if isinstance(result, Message):
                messages.append(result)
            elif isinstance(result, tuple):
                messages.append(result[0])
        return messages
