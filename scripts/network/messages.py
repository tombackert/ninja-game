from dataclasses import dataclass, asdict
from typing import Any, Dict, List
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


@dataclass
class InputMessage:
    tick: int
    inputs: List[str]


@dataclass
class SnapshotMessage:
    tick: int
    snapshot_data: Dict[str, Any]  # Serialized SimulationSnapshot


@dataclass
class AckMessage:
    tick: int
    received_ts: float
