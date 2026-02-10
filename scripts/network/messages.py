from dataclasses import dataclass, asdict
from typing import Any, Dict
import json


@dataclass
class Message:
    type: str
    payload: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(json_str: str) -> "Message":
        data = json.loads(json_str)
        return Message(type=data["type"], payload=data["payload"])


# Connection protocol messages
@dataclass
class ConnectionRequest:
    """Client requests to join the game."""
    player_name: str = "Player"


@dataclass
class ConnectionAccept:
    """Server accepts the connection."""
    player_id: int
    server_tick: int


@dataclass
class ConnectionReject:
    """Server rejects the connection."""
    reason: str


@dataclass
class PlayerJoined:
    """Broadcast when a new player joins."""
    player_id: int
    player_name: str


@dataclass
class PlayerLeft:
    """Broadcast when a player leaves."""
    player_id: int
    reason: str = "disconnected"


@dataclass
class Heartbeat:
    """Keep-alive message."""
    client_time: float


@dataclass
class HeartbeatAck:
    """Server response to heartbeat."""
    client_time: float
    server_time: float
