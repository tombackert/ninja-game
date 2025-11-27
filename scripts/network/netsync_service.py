from typing import Callable, List, Optional
import time
from scripts.network.messages import Message, InputMessage, SnapshotMessage, AckMessage


class Transport:
    """Abstract transport layer."""

    def send(self, message: Message):
        raise NotImplementedError

    def receive(self) -> Optional[Message]:
        raise NotImplementedError


class LocalLoopbackTransport(Transport):
    """Simulates network by placing messages in a local queue."""

    def __init__(self):
        self.queue: List[Message] = []

    def send(self, message: Message):
        # Simulate serialization/deserialization overhead/integrity
        serialized = message.to_json()
        self.queue.append(Message.from_json(serialized))

    def receive(self) -> Optional[Message]:
        if self.queue:
            return self.queue.pop(0)
        return None


class NetSyncService:
    """Manages network synchronization."""

    def __init__(self, transport: Transport):
        self.transport = transport
        self.peer_transport: Optional[Transport] = None  # For loopback connecting

    def send_input(self, tick: int, inputs: List[str]):
        msg = Message(type='input', payload={'tick': tick, 'inputs': inputs})
        self.transport.send(msg)

    def send_snapshot(self, tick: int, snapshot_data: dict):
        msg = Message(type='snapshot', payload={'tick': tick, 'snapshot_data': snapshot_data})
        self.transport.send(msg)

    def send_ack(self, tick: int):
        msg = Message(type='ack', payload={'tick': tick, 'received_ts': time.time()})
        self.transport.send(msg)

    def process_messages(self) -> List[Message]:
        messages = []
        while True:
            msg = self.transport.receive()
            if not msg:
                break
            messages.append(msg)
        return messages
