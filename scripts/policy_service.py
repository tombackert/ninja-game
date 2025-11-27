from abc import ABC, abstractmethod
from typing import Any, Dict, Callable
import math
import random
from scripts.rng_service import RNGService
from scripts.settings import settings
from scripts.constants import (
    ENEMY_DIRECTION_BASE,
    ENEMY_DIRECTION_SCALE_LOG,
)


class Policy(ABC):
    """Abstract base class for entity behavior policies."""

    @abstractmethod
    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        """Decide on an action based on the entity and context (game state).

        Returns:
            Dict containing action intentions (e.g. {'movement': (1,0), 'shoot': True})
        """
        pass


class PolicyService:
    """Registry for behavioral policies."""

    _policies: Dict[str, Policy] = {}

    @classmethod
    def register(cls, name: str, policy: Policy) -> None:
        cls._policies[name] = policy

    @classmethod
    def get(cls, name: str) -> Policy:
        if name not in cls._policies:
            # Fallback or raise? For now, raise to ensure correctness
            raise ValueError(f"Policy '{name}' not found in registry.")
        return cls._policies[name]


# --- Standard Policies ---


class ScriptedEnemyPolicy(Policy):
    """Replicates the legacy random walk and shoot behavior."""

    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        # context is expected to be the 'Game' instance or 'Tilemap'
        # depending on what's needed. The entity (Enemy) holds references too.
        # But we should prefer passed context for purity.
        # entity.game is available.

        game = entity.game
        rng = RNGService.get()

        result = {"movement": (0, 0), "shoot": False, "shoot_direction": 0}

        # Walking logic (updating internal state of entity is a side effect,
        # ideally policy is pure, but for migration we might read/write entity state)
        # The original code updated 'walking' timer inside update.

        if entity.walking:
            # Check for solid ground ahead
            # We need the tilemap. Assuming it's accessible via game or context.
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

            # Decrement walking (Side effect on entity!)
            entity.walking = max(0, entity.walking - 1)

            # Shooting logic inside walking state?
            # Original code: `if not self.walking: ...` logic was ONLY when NOT walking?
            # Wait, original code structure:
            # if self.walking:
            #    ... movement ...
            #    self.walking -= 1
            #    if not self.walking:
            #       ... shoot checks ...

            # So shooting happens exactly on the frame walking finishes?
            # Or is it "if we ARE walking, do walk stuff. Once we finish (walking becomes 0), try to shoot immediately"?
            # Let's look at the indentation in original code.

            if not entity.walking:
                # Just finished walking, check shoot
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
                result["shoot_direction"] = -1  # simplified, magnitude handled by caller/constants
            if not entity.flip and dis[0] > 0:  # Facing right, player to right
                result["shoot"] = True
                result["shoot_direction"] = 1


# Register default
PolicyService.register("scripted_enemy", ScriptedEnemyPolicy())
