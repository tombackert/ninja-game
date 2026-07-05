from __future__ import annotations

import math

import pygame

from scripts.collectableManager import CollectableManager as cm
from scripts.constants import (
    SWORD_COOLDOWN_FRAMES,
    SWORD_HITBOX_HEIGHT,
    SWORD_REACH,
    SWORD_SLASH_VFX_FRAMES,
)
from scripts.effects_util import spawn_hit_sparks
from scripts.settings import settings
from scripts.spark import Spark

from .base import FireResult, Weapon


class SwordWeapon(Weapon):
    """Melee slash: kills enemies in reach and destroys enemy projectiles.

    No ammo cost — balanced by melee range against shooting enemies.
    """

    name = "sword"

    def can_fire(self, player) -> bool:
        try:
            sword_index = cm.WEAPONS.index("Sword")
        except ValueError:  # pragma: no cover
            sword_index = 4
        return (
            player.game.cm.sword > 0
            and player.shoot_cooldown == 0
            and settings.selected_weapon == sword_index
        )

    def slash_rect(self, player) -> pygame.Rect:
        prect = player.rect()
        x = prect.left - SWORD_REACH if player.flip else prect.right
        y = prect.centery - SWORD_HITBOX_HEIGHT // 2
        return pygame.Rect(x, y, SWORD_REACH, SWORD_HITBOX_HEIGHT)

    def fire(self, player):
        if not self.can_fire(player):
            return None
        game = player.game
        if player.services:
            player.services.play("dash")  # swing whoosh
        else:
            game.audio.play("dash")
        player.shoot_cooldown = SWORD_COOLDOWN_FRAMES
        player.slash_timer = SWORD_SLASH_VFX_FRAMES

        hit_rect = self.slash_rect(player)
        kills = 0
        for enemy in game.enemies.copy():
            if enemy.rect().colliderect(hit_rect):
                game.screenshake = max(16, game.screenshake)
                if player.services:
                    player.services.play("hit")
                else:
                    game.audio.play("hit")
                award = getattr(game, "award_coin", None)
                if award:
                    award(getattr(player, "id", None))
                else:
                    game.cm.coins += 1
                spawn_hit_sparks(game, enemy.rect().center)
                game.sparks.append(Spark(enemy.rect().center, 0, 5))
                game.sparks.append(Spark(enemy.rect().center, math.pi, 5))
                if hasattr(enemy, "alive"):
                    enemy.alive = False
                try:
                    game.enemies.remove(enemy)
                except ValueError:  # pragma: no cover - defensive
                    pass
                kills += 1

        # Parry: destroy enemy projectiles inside the slash arc
        destroy = getattr(game.projectiles, "destroy_in_rect", None)
        if destroy:
            destroy(hit_rect, owner="enemy")

        return FireResult(spawned=kills > 0, ammo_used=0)
