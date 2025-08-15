"""Weapon system package (Issue 23).

Provides abstraction for weapon behaviors so Player and enemies call
polymorphic objects instead of hard-coded branching on selected_weapon.
"""

from .base import Weapon, FireResult, NoneWeapon
from .registry import get_weapon, register_weapon, list_weapons
from .gun import GunWeapon

# Register built-ins on import
register_weapon("none", NoneWeapon())  # no-op default
register_weapon("gun", GunWeapon())

__all__ = [
    "Weapon",
    "FireResult",
    "get_weapon",
    "register_weapon",
    "list_weapons",
    "GunWeapon",
]
