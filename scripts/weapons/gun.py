from __future__ import annotations
from .base import Weapon, FireResult
from scripts.constants import PROJECTILE_SPEED
from scripts.settings import settings
from scripts.collectableManager import CollectableManager as cm


class GunWeapon(Weapon):
    name = "gun"

    def can_fire(self, player) -> bool:
        try:
            gun_index = cm.WEAPONS.index("Gun")
        except ValueError:  # pragma: no cover
            gun_index = 1
        return (
            player.game.cm.gun
            and player.game.cm.ammo > 0
            and player.shoot_cooldown == 0
            and settings.selected_weapon == gun_index
        )

    def fire(self, player):
        if not self.can_fire(player):
            return None
        if player.services:
            player.services.play("shoot")
        else:
            player.game.audio.play("shoot")
        direction = -PROJECTILE_SPEED if player.flip else PROJECTILE_SPEED
        (
            player.services.projectiles.spawn
            if player.services
            else player.game.projectiles.spawn
        )(
            player.rect().centerx + (7 * (-1 if player.flip else 1)),
            player.rect().centery,
            direction,
            "player",
        )
        player.game.cm.ammo -= 1
        player.shoot_cooldown = 10
        return FireResult(spawned=True, ammo_used=1)
