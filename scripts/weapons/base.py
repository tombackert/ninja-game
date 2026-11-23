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


# --- Who holds which weapon -------------------------------------------------
# Single player: the weapon equipped in the store (settings.selected_weapon)
# and the inventory of the saved game (game.cm). Multiplayer: each player
# carries a Loadout (scripts/weapons/loadout.py) with their own weapon and
# ammo, as several players share one game on the server.


def equipped_weapon(player) -> str:
    """Display name of the weapon `player` holds (CollectableManager.WEAPONS)."""
    loadout = getattr(player, "loadout", None)
    if loadout is not None:
        return loadout.weapon
    from scripts.collectableManager import CollectableManager as cm
    from scripts.settings import settings

    try:
        return cm.WEAPONS[settings.selected_weapon]
    except (IndexError, TypeError):  # pragma: no cover - defensive
        return "Default"


def inventory(player):
    """What `player`'s weapons own and spend (ammo, stars, ownership counts)."""
    loadout = getattr(player, "loadout", None)
    return loadout if loadout is not None else player.game.cm


def spawn_kwargs(player) -> dict:
    """Extra projectile spawn arguments: in multiplayer the shooter's ID
    (PvP hits and kill credit; single-player shots have no owner)."""
    if getattr(player, "loadout", None) is None:
        return {}
    return {"owner_id": player.id}
