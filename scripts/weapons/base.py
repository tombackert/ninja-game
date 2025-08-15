from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class FireResult:
    spawned: bool
    ammo_used: int = 0


class Weapon:
    """Base weapon interface.

    Subclasses override `can_fire` and `fire` to implement behavior.
    Stateless by default; stateful weapons can keep cooldowns etc.
    """

    name: str = "weapon"

    def can_fire(self, player) -> bool:  # pragma: no cover - trivial
        return False

    def fire(self, player) -> Optional[FireResult]:  # pragma: no cover - default
        return None


class NoneWeapon(Weapon):
    name = "none"

    def can_fire(self, player) -> bool:  # always false
        return False

    def fire(self, player):  # returns explicit result for clarity
        return FireResult(spawned=False, ammo_used=0)
