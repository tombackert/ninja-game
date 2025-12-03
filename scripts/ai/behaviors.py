import math
from typing import Any, Dict

from scripts.ai.core import Policy
from scripts.constants import (
    ENEMY_DIRECTION_BASE,
    ENEMY_DIRECTION_SCALE_LOG,
)
from scripts.rng_service import RNGService
from scripts.settings import settings


class ScriptedEnemyPolicy(Policy):
    """Replicates the legacy random walk and shoot behavior."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        game = entity.game
        rng = RNGService.get()

        result = {"movement": (0, 0), "shoot": False, "shoot_direction": 0}

        if entity.walking:
            tilemap = game.tilemap

            # Solid check ahead
            check_x = entity.rect().centerx + (-7 if entity.flip else 7)
            check_y = entity.pos[1] + 23

            if tilemap.solid_check((check_x, check_y)):
                # Wall collision check
                if entity.collisions["right"] or entity.collisions["left"]:
                    entity.flip = not entity.flip
                else:
                    # Move
                    direction = ENEMY_DIRECTION_BASE * (
                        1 + ENEMY_DIRECTION_SCALE_LOG * math.log(settings.selected_level + 1)
                    )
                    move_x = -direction if entity.flip else direction
                    result["movement"] = (move_x, 0)
            else:
                # Cliff edge, turn around
                entity.flip = not entity.flip

            entity.walking = max(0, entity.walking - 1)

            if not entity.walking:
                self._check_shoot(entity, game, result)

        elif rng.random() < 0.01:
            entity.walking = rng.randint(30, 120)

        return result

    def _check_shoot(self, entity, game, result):
        dis = (
            game.player.pos[0] - entity.pos[0],
            game.player.pos[1] - entity.pos[1],
        )
        if abs(dis[1]) < 15:  # Y distance small
            if entity.flip and dis[0] < 0:  # Facing left, player to left
                result["shoot"] = True
                result["shoot_direction"] = -1
            if not entity.flip and dis[0] > 0:  # Facing right, player to right
                result["shoot"] = True
                result["shoot_direction"] = 1


class PatrolPolicy(Policy):
    """Walks back and forth continuously without shooting."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        game = entity.game
        tilemap = game.tilemap
        result = {"movement": (0, 0), "shoot": False}

        # Ensure walking timer is active or just ignore it and force move?
        # To keep consistent with physics/anim, we command movement.

        check_x = entity.rect().centerx + (-7 if entity.flip else 7)
        check_y = entity.pos[1] + 23

        if tilemap.solid_check((check_x, check_y)):
            if entity.collisions["right"] or entity.collisions["left"]:
                entity.flip = not entity.flip
            else:
                direction = ENEMY_DIRECTION_BASE * (
                    1 + ENEMY_DIRECTION_SCALE_LOG * math.log(settings.selected_level + 1)
                )
                move_x = -direction if entity.flip else direction
                result["movement"] = (move_x, 0)
        else:
            entity.flip = not entity.flip

        return result


class ShooterPolicy(Policy):
    """Stationary turret that tracks and shoots at the player."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        game = entity.game
        rng = RNGService.get()
        result = {"movement": (0, 0), "shoot": False, "shoot_direction": 0}

        # Always face player
        diff_x = game.player.pos[0] - entity.pos[0]
        if diff_x > 0:
            entity.flip = False
        else:
            entity.flip = True

        # Shoot check
        # Simple cooldown implemented via RNG for now (or could use entity state)
        if rng.random() < 0.02:  # 2% chance per frame ~ 1 shot per second at 60fps
            dis = (
                game.player.pos[0] - entity.pos[0],
                game.player.pos[1] - entity.pos[1],
            )
            # Range check
            if abs(dis[0]) < 200 and abs(dis[1]) < 30:
                result["shoot"] = True
                result["shoot_direction"] = 1 if diff_x > 0 else -1

        return result
