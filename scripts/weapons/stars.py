from __future__ import annotations

from scripts.constants import STAR_COOLDOWN_FRAMES, STAR_GRAVITY, STAR_SPEED_X, STAR_SPEED_Y

from .base import FireResult, Weapon, equipped_weapon, inventory, spawn_kwargs


class NinjaStarWeapon(Weapon):
    """Thrown shuriken: gravity arc, pierces enemies, consumes a star per throw."""

    name = "stars"

    def can_fire(self, player) -> bool:
        return (
            inventory(player).ninja_stars > 0
            and player.shoot_cooldown == 0
            and equipped_weapon(player) == "Ninja Stars"
        )

    def fire(self, player):
        if not self.can_fire(player):
            return None
        if player.services:
            player.services.play("shoot")
        else:
            player.game.audio.play("shoot")
        vx = -STAR_SPEED_X if player.flip else STAR_SPEED_X
        (player.services.projectiles.spawn if player.services else player.game.projectiles.spawn)(
            player.rect().centerx + (7 * (-1 if player.flip else 1)),
            player.rect().centery - 2,
            vx,
            "player",
            vy=STAR_SPEED_Y,
            gravity=STAR_GRAVITY,
            kind="star",
            pierce=True,
            **spawn_kwargs(player),
        )
        inventory(player).ninja_stars -= 1
        player.shoot_cooldown = STAR_COOLDOWN_FRAMES
        return FireResult(spawned=True, ammo_used=1)
