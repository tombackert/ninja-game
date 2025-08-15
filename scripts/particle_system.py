"""Central ParticleSystem (Issue 18).

Unifies ad-hoc management of particles (``game.particles`` list) and
sparks (``game.sparks`` list) behind an update + spawn API similar to
``ProjectileSystem`` introduced in Issue 17. This provides:

* Central per–frame update & render draw-command building
* Consistent lifetime / cleanup handling
* Backward compatibility: the raw lists are still exposed so legacy
  code mutating ``game.particles`` / ``game.sparks`` continues to work
  during the migration. New code should call the spawn helpers.

Design notes:
* We keep Particle & Spark classes unchanged (no behavior change).
* Leaf spawning and special dash trail logic will still append directly
  for now; later passes can migrate those call sites if desired.
* Minimal public API: ``spawn_particle(...)`` / ``spawn_spark(...)`` and
  ``update()`` plus ``get_draw_commands()`` for UI render path.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List, Tuple
from scripts.particle import Particle
from scripts.spark import Spark


@dataclass
class ParticleDrawCommand:
    img: object  # pygame.Surface (kept generic for tests without pygame init)
    x: float
    y: float


class ParticleSystem:
    def __init__(self, game):
        self.game = game
        # Underlying storage (authoritative). Exposed as attributes for
        # backward compatibility with legacy loops / tests.
        self.particles: List[Particle] = []
        self.sparks: List[Spark] = []

    # ---- Spawn helpers ----
    def spawn_particle(
        self,
        p_type: str,
        pos: Tuple[float, float],
        velocity=(0, 0),
        frame: int = 0,
    ) -> Particle:
        p = Particle(self.game, p_type, pos, velocity=list(velocity), frame=frame)
        self.particles.append(p)
        return p

    def spawn_spark(self, pos: Tuple[float, float], angle: float, speed: float) -> Spark:
        s = Spark(pos, angle, speed)
        self.sparks.append(s)
        return s

    # Bulk add helpers (used by effects_util migration)
    def extend_particles(self, items: Iterable[Particle]):
        self.particles.extend(items)

    def extend_sparks(self, items: Iterable[Spark]):
        self.sparks.extend(items)

    # ---- Update & draw collection ----
    def update(self):
        # Sparks
        for s in self.sparks.copy():
            if s.update():  # True => dead
                self.sparks.remove(s)
        # Particles
        for p in self.particles.copy():
            dead = p.update()
            if p.type == "leaf":  # preserve existing sway effect (ui.py duplicated)
                import math

                p.pos[0] += math.sin(p.animation.frame * 0.035) * 0.3
            if dead:
                self.particles.remove(p)

    def get_draw_commands(self):
        return {"sparks": list(self.sparks), "particles": list(self.particles)}

    def clear(self):  # pragma: no cover
        self.particles.clear()
        self.sparks.clear()


__all__ = ["ParticleSystem", "ParticleDrawCommand"]
