from __future__ import annotations

from scripts.collectableManager import CollectableManager as cm
from scripts.constants import STAR_COOLDOWN_FRAMES, STAR_GRAVITY, STAR_SPEED_X, STAR_SPEED_Y
from scripts.settings import settings

from .base import FireResult, Weapon


class NinjaStarWeapon(Weapon):
    """Thrown shuriken: gravity arc, pierces enemies, consumes a star per throw."""

    name = "stars"

    def can_fire(self, player) -> bool:
        try:
            stars_index = cm.WEAPONS.index("Ninja Stars")
        except ValueError:  # pragma: no cover
            stars_index = 3
        return player.game.cm.ninja_stars > 0 and player.shoot_cooldown == 0 and settings.selected_weapon == stars_index

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
        )
        player.game.cm.ninja_stars -= 1
        player.shoot_cooldown = STAR_COOLDOWN_FRAMES
        return FireResult(spawned=True, ammo_used=1)
