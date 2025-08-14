"""Effects utilities (Issue 7: Projectile hit / spark utility).

Consolidates duplicated spark + particle spawning patterns so gameplay
code (entities, ui) can call a single helper ensuring consistent counts
and tuning usage.
"""

from __future__ import annotations
import math
import random
from typing import Tuple

from scripts.spark import Spark
from scripts.particle import Particle
from scripts.constants import (
    SPARK_COUNT_ENEMY_HIT,
    SPARK_PARTICLE_SPEED_MAX,
    SPARK_COUNT_PROJECTILE,
)


def spawn_hit_sparks(game, center: Tuple[float, float], count: int | None = None):
    """Spawn generic circular hit sparks and particles.

    Args:
        game: Game instance with .sparks and .particles lists.
        center: (x, y) position for emission center.
        count: Optional override; if None uses SPARK_COUNT_ENEMY_HIT.
    """
    total = count if count is not None else SPARK_COUNT_ENEMY_HIT
    for _ in range(total):
        angle = random.random() * math.pi * 2
        speed = random.random() * SPARK_PARTICLE_SPEED_MAX
        game.sparks.append(Spark(center, angle, 2 + random.random()))
        game.particles.append(
            Particle(
                game,
                "particle",
                center,
                velocity=[
                    math.cos(angle + math.pi) * speed * 0.5,
                    math.sin(angle + math.pi) * speed * 0.5,
                ],
                frame=random.randint(0, 7),
            )
        )


def spawn_projectile_sparks(game, pos: Tuple[float, float], direction: float):
    """Projectile muzzle / impact sparks using existing count constant."""
    for _ in range(SPARK_COUNT_PROJECTILE):
        game.sparks.append(
            Spark(
                pos,
                random.random() - 0.5 + (math.pi if direction < 0 else 0),
                2 + random.random(),
            )
        )


__all__ = ["spawn_hit_sparks", "spawn_projectile_sparks"]
