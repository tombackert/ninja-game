from __future__ import annotations

from scripts.collectableManager import CollectableManager as cm
from scripts.constants import (
    GRAPPLE_COOLDOWN_FRAMES,
    GRAPPLE_RANGE,
    GRAPPLE_RAY_STEP,
    GRAPPLE_WHIFF_COOLDOWN_FRAMES,
)
from scripts.settings import settings

from .base import FireResult, Weapon


class GrappleWeapon(Weapon):
    """Grapple hook: pulls the player to the first solid tile in facing direction.

    Pure mobility — no damage. The pull physics live in Player.update.
    """

    name = "grapple"

    def can_fire(self, player) -> bool:
        try:
            grapple_index = cm.WEAPONS.index("Grapple Hook")
        except ValueError:  # pragma: no cover
            grapple_index = 5
        return (
            player.game.cm.grapple_hook > 0
            and player.shoot_cooldown == 0
            and player.grapple_point is None
            and settings.selected_weapon == grapple_index
        )

    def find_anchor(self, player):
        """Sample a horizontal ray in facing direction; return anchor pos or None."""
        tilemap = player.game.tilemap
        cx, cy = player.rect().center
        direction = -1 if player.flip else 1
        for dist in range(GRAPPLE_RAY_STEP, GRAPPLE_RANGE + 1, GRAPPLE_RAY_STEP):
            probe = (cx + direction * dist, cy)
            if tilemap.solid_check(probe):
                return [probe[0], probe[1]]
        return None

    def fire(self, player):
        if not self.can_fire(player):
            return None
        anchor = self.find_anchor(player)
        if anchor is None:
            player.shoot_cooldown = GRAPPLE_WHIFF_COOLDOWN_FRAMES
            return FireResult(spawned=False, ammo_used=0)
        if player.services:
            player.services.play("dash")
        else:
            player.game.audio.play("dash")
        player.grapple_point = anchor
        player.grapple_frames = 0
        player.shoot_cooldown = GRAPPLE_COOLDOWN_FRAMES
        return FireResult(spawned=True, ammo_used=0)
