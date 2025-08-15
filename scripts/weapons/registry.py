from __future__ import annotations
from typing import Dict, Optional
from .base import Weapon

_registry: Dict[str, Weapon] = {}


def register_weapon(name: str, weapon: Weapon) -> None:
    _registry[name] = weapon


def get_weapon(name: str) -> Optional[Weapon]:
    return _registry.get(name, _registry.get("none"))


def list_weapons():  # pragma: no cover - simple passthrough
    return list(_registry.keys())
