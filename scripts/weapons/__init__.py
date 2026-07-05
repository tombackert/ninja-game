"""Weapon system package (Issue 23).

Provides abstraction for weapon behaviors so Player and enemies call
polymorphic objects instead of hard-coded branching on selected_weapon.
"""

from .base import FireResult, NoneWeapon, Weapon
from .grapple import GrappleWeapon
from .gun import GunWeapon
from .registry import get_weapon, list_weapons, register_weapon
from .rifle import RifleWeapon
from .stars import NinjaStarWeapon
from .sword import SwordWeapon

# Register built-ins on import
register_weapon("none", NoneWeapon())  # no-op default
register_weapon("gun", GunWeapon())
register_weapon("rifle", RifleWeapon())
register_weapon("stars", NinjaStarWeapon())
register_weapon("sword", SwordWeapon())
register_weapon("grapple", GrappleWeapon())

# Maps CollectableManager.WEAPONS display names to registry keys.
WEAPON_KEYS = {
    "Default": "none",
    "Gun": "gun",
    "Rifle": "rifle",
    "Ninja Stars": "stars",
    "Sword": "sword",
    "Grapple Hook": "grapple",
}

__all__ = [
    "Weapon",
    "FireResult",
    "get_weapon",
    "register_weapon",
    "list_weapons",
    "GunWeapon",
    "RifleWeapon",
    "NinjaStarWeapon",
    "SwordWeapon",
    "GrappleWeapon",
    "WEAPON_KEYS",
]
