"""A multiplayer player's weapon (Loadout).

In multiplayer every player brings the weapon they equipped in single
player, if they own it: unlocked weapons carry over, nobody gets one for
free. Several players share one game on the server, so the weapon and its
ammo live on the player (``player.loadout``) instead of in the saved game's
CollectableManager. The weapons (scripts/weapons/) read it through
``inventory(player)``.

Ammo is the per-player multiplayer pool (``player.mp_ammo``: start ammo plus
pickups, never saved); thrown stars draw from it too.
"""

from __future__ import annotations

# Weapon display name -> CollectableManager ownership attribute
WEAPON_ATTRS = {
    "Gun": "gun",
    "Rifle": "rifle",
    "Ninja Stars": "ninja_stars",
    "Sword": "sword",
    "Grapple Hook": "grapple_hook",
}


def owned_weapon(cm, name: str) -> str:
    """`name` if the inventory `cm` owns that weapon, else "Default" (none)."""
    attr = WEAPON_ATTRS.get(name)
    if attr is None or getattr(cm, attr, 0) <= 0:
        return "Default"
    return name


def brought_weapon(cm) -> str:
    """The weapon this player brings into multiplayer: the one equipped in
    single player (settings.selected_weapon), if `cm` (their saved game) owns it."""
    from scripts.collectableManager import CollectableManager
    from scripts.settings import settings

    try:
        name = CollectableManager.WEAPONS[settings.selected_weapon]
    except (IndexError, TypeError):
        return "Default"
    return owned_weapon(cm, name)


class Loadout:
    """One multiplayer player's weapon, shaped like the CollectableManager
    fields the weapons read (gun, rifle, sword, grapple_hook, ninja_stars,
    ammo)."""

    def __init__(self, player, weapon: str) -> None:
        self.player = player
        self.weapon = weapon if weapon in WEAPON_ATTRS else "Default"

    def _owns(self, name: str) -> int:
        return 1 if self.weapon == name else 0

    @property
    def gun(self) -> int:
        return self._owns("Gun")

    @property
    def rifle(self) -> int:
        return self._owns("Rifle")

    @property
    def sword(self) -> int:
        return self._owns("Sword")

    @property
    def grapple_hook(self) -> int:
        return self._owns("Grapple Hook")

    @property
    def ammo(self) -> int:
        return getattr(self.player, "mp_ammo", 0)

    @ammo.setter
    def ammo(self, value: int) -> None:
        self.player.mp_ammo = value

    @property
    def ninja_stars(self) -> int:
        return self.ammo if self.weapon == "Ninja Stars" else 0

    @ninja_stars.setter
    def ninja_stars(self, value: int) -> None:
        if self.weapon == "Ninja Stars":
            self.ammo = value


__all__ = ["Loadout", "WEAPON_ATTRS", "brought_weapon", "owned_weapon"]
