"""Effects utilities (Issue 7: Projectile hit / spark utility).

Consolidates duplicated spark + particle spawning patterns so gameplay
code (entities, ui) can call a single helper ensuring consistent counts
and tuning usage.
"""

from __future__ import annotations

import math
from typing import Tuple

from scripts.constants import (
    SPARK_COUNT_ENEMY_HIT,
    SPARK_COUNT_PROJECTILE,
    SPARK_PARTICLE_SPEED_MAX,
)
from scripts.particle import Particle
from scripts.rng_service import RNGService
from scripts.spark import Spark


def spawn_hit_sparks(game, center: Tuple[float, float], count: int | None = None):
    """Spawn generic circular hit sparks and particles.

    Args:
        game: Game instance with .sparks and .particles lists.
        center: (x, y) position for emission center.
        count: Optional override; if None uses SPARK_COUNT_ENEMY_HIT.
    """
    rng = RNGService.get()
    total = count if count is not None else SPARK_COUNT_ENEMY_HIT
    for _ in range(total):
        angle = rng.random() * math.pi * 2
        speed = rng.random() * SPARK_PARTICLE_SPEED_MAX
        game.sparks.append(Spark(center, angle, 2 + rng.random()))
        game.particles.append(
            Particle(
                game,
                "particle",
                center,
                velocity=[
                    math.cos(angle + math.pi) * speed * 0.5,
                    math.sin(angle + math.pi) * speed * 0.5,
                ],
                frame=rng.randint(0, 7),
            )
        )


def spawn_projectile_sparks(game, pos: Tuple[float, float], direction: float):
    """Projectile muzzle / impact sparks using existing count constant."""
    rng = RNGService.get()
    for _ in range(SPARK_COUNT_PROJECTILE):
        game.sparks.append(
            Spark(
                pos,
                rng.random() - 0.5 + (math.pi if direction < 0 else 0),
                2 + rng.random(),
            )
        )


__all__ = ["spawn_hit_sparks", "spawn_projectile_sparks"]
