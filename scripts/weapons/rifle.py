from __future__ import annotations

from scripts.constants import RIFLE_AMMO_COST, RIFLE_COOLDOWN_FRAMES, RIFLE_PROJECTILE_SPEED

from .base import FireResult, Weapon, equipped_weapon, inventory, spawn_kwargs


class RifleWeapon(Weapon):
    """Long-range rifle: fast bullet, 2 ammo per shot, slow fire rate."""

    name = "rifle"

    def can_fire(self, player) -> bool:
        inv = inventory(player)
        return (
            inv.rifle > 0
            and inv.ammo >= RIFLE_AMMO_COST
            and player.shoot_cooldown == 0
            and equipped_weapon(player) == "Rifle"
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
            **spawn_kwargs(player),
        )
        inventory(player).ammo -= RIFLE_AMMO_COST
        player.shoot_cooldown = RIFLE_COOLDOWN_FRAMES
        return FireResult(spawned=True, ammo_used=RIFLE_AMMO_COST)
