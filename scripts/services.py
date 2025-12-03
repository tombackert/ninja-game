"""Service interfaces & simple adapter implementations (Issue 19).

Entities will depend on narrow protocol-style interfaces instead of the
entire Game object. This improves testability and reduces coupling.

Current scope (minimal extraction):
- AudioPort           -> wraps AudioService.play
- ProjectilePort      -> wraps ProjectileSystem.spawn
- ParticlePort        -> wraps ParticleSystem.spawn_particle / spawn_spark
- CollectablePort     -> limited coin/ammo/gun access used by entities

Game will create a ServiceContainer exposing these ports and pass it to
entities instead of raw `game` reference. During migration we still keep
`entity.game` for backwards compatibility but new code should use
`entity.services`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple


# ---- Protocols ----
class AudioPort(Protocol):
    def play(self, name: str, loops: int = 0) -> None: ...  # noqa: D401


class ProjectilePort(Protocol):
    def spawn(self, x: float, y: float, vx: float, owner: str): ...


class ParticlePort(Protocol):
    def spawn_particle(self, p_type: str, pos: Tuple[float, float], velocity=(0, 0), frame: int = 0): ...
    def spawn_spark(self, pos: Tuple[float, float], angle: float, speed: float): ...


class CollectablePort(Protocol):
    @property
    def coins(self) -> int: ...
    @coins.setter
    def coins(self, v: int) -> None: ...
    @property
    def ammo(self) -> int: ...
    @ammo.setter
    def ammo(self, v: int) -> None: ...
    @property
    def gun(self) -> bool: ...


@dataclass
class ServiceContainer:
    audio: AudioPort
    projectiles: ProjectilePort
    particles: ParticlePort | None
    collectables: CollectablePort

    # Convenience helpers (thin proxies) for readability inside entities
    def play(self, name: str, loops: int = 0) -> None:  # pragma: no cover - simple
        self.audio.play(name, loops=loops)

    def spawn_projectile(self, x: float, y: float, vx: float, owner: str):  # pragma: no cover
        self.projectiles.spawn(x, y, vx, owner)

    def emit_particle(self, p_type: str, pos: Tuple[float, float], velocity=(0, 0), frame: int = 0):  # pragma: no cover
        if self.particles:
            self.particles.spawn_particle(p_type, pos, velocity=velocity, frame=frame)

    def emit_spark(self, pos: Tuple[float, float], angle: float, speed: float):  # pragma: no cover
        if self.particles:
            self.particles.spawn_spark(pos, angle, speed)


__all__ = [
    "AudioPort",
    "ProjectilePort",
    "ParticlePort",
    "CollectablePort",
    "ServiceContainer",
    "build_services",
]


def build_services(game) -> ServiceContainer:
    """Factory building a ServiceContainer from a game instance.

    Safe to call early; particle system may not exist yet.
    """
    particles = getattr(game, "particle_system", None)
    return ServiceContainer(
        audio=game.audio,
        projectiles=game.projectiles,
        particles=particles,
        collectables=game.cm,
    )
