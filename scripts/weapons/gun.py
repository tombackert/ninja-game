from __future__ import annotations

from scripts.constants import PROJECTILE_SPEED

from .base import FireResult, Weapon, equipped_weapon, inventory, spawn_kwargs


class GunWeapon(Weapon):
    name = "gun"

    def can_fire(self, player) -> bool:
        inv = inventory(player)
        return inv.gun and inv.ammo > 0 and player.shoot_cooldown == 0 and equipped_weapon(player) == "Gun"

    def fire(self, player):
        if not self.can_fire(player):
            return None
        if player.services:
            player.services.play("shoot")
        else:
            player.game.audio.play("shoot")
        direction = -PROJECTILE_SPEED if player.flip else PROJECTILE_SPEED
        (player.services.projectiles.spawn if player.services else player.game.projectiles.spawn)(
            player.rect().centerx + (7 * (-1 if player.flip else 1)),
            player.rect().centery,
            direction,
            "player",
            **spawn_kwargs(player),
        )
        inventory(player).ammo -= 1
        player.shoot_cooldown = 10
        return FireResult(spawned=True, ammo_used=1)
