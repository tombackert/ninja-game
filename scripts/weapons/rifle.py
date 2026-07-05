from __future__ import annotations

from scripts.collectableManager import CollectableManager as cm
from scripts.constants import RIFLE_AMMO_COST, RIFLE_COOLDOWN_FRAMES, RIFLE_PROJECTILE_SPEED
from scripts.settings import settings

from .base import FireResult, Weapon


class RifleWeapon(Weapon):
    """Long-range rifle: fast bullet, 2 ammo per shot, slow fire rate."""

    name = "rifle"

    def can_fire(self, player) -> bool:
        try:
            rifle_index = cm.WEAPONS.index("Rifle")
        except ValueError:  # pragma: no cover
            rifle_index = 2
        return (
            player.game.cm.rifle > 0
            and player.game.cm.ammo >= RIFLE_AMMO_COST
            and player.shoot_cooldown == 0
            and settings.selected_weapon == rifle_index
        )

    def fire(self, player):
        if not self.can_fire(player):
            return None
        if player.services:
            player.services.play("shoot")
        else:
            player.game.audio.play("shoot")
        direction = -RIFLE_PROJECTILE_SPEED if player.flip else RIFLE_PROJECTILE_SPEED
        (player.services.projectiles.spawn if player.services else player.game.projectiles.spawn)(
            player.rect().centerx + (9 * (-1 if player.flip else 1)),
            player.rect().centery,
            direction,
            "player",
        )
        player.game.cm.ammo -= RIFLE_AMMO_COST
        player.shoot_cooldown = RIFLE_COOLDOWN_FRAMES
        return FireResult(spawned=True, ammo_used=RIFLE_AMMO_COST)
