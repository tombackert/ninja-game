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


class ChaserPolicy(Policy):
    """Actively pathfinds/moves towards player within range."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        game = entity.game
        tilemap = game.tilemap
        rng = RNGService.get()
        result = {"movement": (0, 0), "shoot": False, "shoot_direction": 0, "jump": False}

        # Calculate vector to player
        dis_x = game.player.pos[0] - entity.pos[0]
        dis_y = game.player.pos[1] - entity.pos[1]
        dist_sq = dis_x * dis_x + dis_y * dis_y

        # Engage if within ~300px
        if dist_sq < 90000:
            direction = ENEMY_DIRECTION_BASE * (1 + ENEMY_DIRECTION_SCALE_LOG * math.log(settings.selected_level + 1))
            # Basic horizontal seek
            if dis_x > 10:
                entity.flip = False
                move_x = direction
            elif dis_x < -10:
                entity.flip = True
                move_x = -direction
            else:
                move_x = 0

            # Wall/Cliff logic: Jump if blocked, or stop?
            check_x = entity.rect().centerx + (10 if move_x > 0 else -10)
            check_y = entity.pos[1] + 23

            blocked = False
            # Check wall
            if move_x != 0:
                if tilemap.solid_check((check_x, entity.rect().centery)):
                    blocked = True
                if entity.collisions["right"] or entity.collisions["left"]:
                    blocked = True

            # Check cliff
            if not tilemap.solid_check((check_x, check_y)):
                # If cliff, maybe jump if player is above/across?
                # For now, just stop to avoid suicide
                blocked = True
                # Unless we can jump?
                if dis_y < -20:  # Player is above
                    result["jump"] = True

            if not blocked or result["jump"]:
                result["movement"] = (move_x, 0)

            # Jump if player is significantly above
            if dis_y < -40 and rng.random() < 0.02 and entity.collisions["down"]:
                result["jump"] = True

            # Shoot check
            if abs(dis_y) < 30 and abs(dis_x) < 150:
                if rng.random() < 0.05:
                    result["shoot"] = True
                    result["shoot_direction"] = 1 if dis_x > 0 else -1

        return result


class JumperPolicy(Policy):
    """Moves horizontally and jumps frequently to be hard to hit."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        game = entity.game
        tilemap = game.tilemap
        rng = RNGService.get()
        result = {"movement": (0, 0), "shoot": False, "shoot_direction": 0, "jump": False}

        # Patrol logic base
        check_x = entity.rect().centerx + (-7 if entity.flip else 7)
        check_y = entity.pos[1] + 23

        should_turn = False
        if tilemap.solid_check((check_x, check_y)):
            if entity.collisions["right"] or entity.collisions["left"]:
                should_turn = True
            else:
                direction = ENEMY_DIRECTION_BASE * (
                    1 + ENEMY_DIRECTION_SCALE_LOG * math.log(settings.selected_level + 1)
                )
                move_x = -direction if entity.flip else direction
                result["movement"] = (move_x, 0)
        else:
            should_turn = True

        if should_turn:
            # Chance to jump over obstacle instead of turning?
            if rng.random() < 0.5:
                result["jump"] = True
                # Maintain momentum
                move_x = -ENEMY_DIRECTION_BASE if entity.flip else ENEMY_DIRECTION_BASE
                result["movement"] = (move_x, 0)
            else:
                entity.flip = not entity.flip

        # Random jumps
        if rng.random() < 0.02 and entity.collisions["down"]:
            result["jump"] = True

        # Shoot if player aligned
        dis_y = game.player.pos[1] - entity.pos[1]
        if abs(dis_y) < 20 and rng.random() < 0.01:
            result["shoot"] = True
            result["shoot_direction"] = -1 if entity.flip else 1

        return result
