"""Dust puffs where the ninja's feet push off or come down (looks only).

The puffs ride in game.particles like the leaves and the dash trail, but they
draw from Python's `random` (as the screen shake does), never the game's
seeded RNG: recorded runs, route plans and the netcode replay the same with
or without them, and tools that seed `random` (tools/bench) get the same
picture every run.
"""

from __future__ import annotations

import random as _rand

import pygame

DUST_COLOR = (232, 226, 212)
DUST_SHADE = (196, 188, 172)


class Dust:
    """One little cloud that drifts, slows down and shrinks away."""

    type = "dust"

    def __init__(self, pos, velocity, life: int, radius: float, shade: bool = False):
        self.pos = list(pos)
        self.velocity = list(velocity)
        self.life = life
        self.max_life = life
        self.radius = radius
        self.color = DUST_SHADE if shade else DUST_COLOR

    def update(self) -> bool:
        self.pos[0] += self.velocity[0]
        self.pos[1] += self.velocity[1]
        self.velocity[0] *= 0.86
        self.velocity[1] = self.velocity[1] * 0.86 - 0.012  # drifts up a little
        self.life -= 1
        return self.life <= 0

    def render(self, surf, offset=(0, 0)) -> None:
        r = self.radius * (self.life / self.max_life) ** 0.6
        if r < 0.5:
            return
        center = (round(self.pos[0] - offset[0]), round(self.pos[1] - offset[1]))
        pygame.draw.circle(surf, self.color, center, max(1, round(r)))


class Debris:
    """A chip of a broken block: flies off, falls and fades on the last frames."""

    type = "debris"

    def __init__(self, pos, velocity, color, size: int, life: int):
        self.pos = list(pos)
        self.velocity = list(velocity)
        self.color = color
        self.size = size
        self.life = life

    def update(self) -> bool:
        self.velocity[1] = min(4.0, self.velocity[1] + 0.15)
        self.pos[0] += self.velocity[0]
        self.pos[1] += self.velocity[1]
        self.velocity[0] *= 0.97
        self.life -= 1
        return self.life <= 0

    def render(self, surf, offset=(0, 0)) -> None:
        if self.life < 6 and self.life % 2:  # flicker out
            return
        x, y = round(self.pos[0] - offset[0]), round(self.pos[1] - offset[1])
        surf.fill(self.color, (x, y, self.size, self.size))


def _emit(game, items) -> None:
    particles = getattr(game, "particles", None)
    if isinstance(particles, list):
        particles.extend(items)


def landing(game, foot, strength: float) -> None:
    """Puffs out to both sides of the feet; more and wider the harder the landing (0..1)."""
    count = 2 + round(4 * strength)
    items = []
    for i in range(count):
        side = -1 if i % 2 == 0 else 1
        speed = 0.35 + _rand.random() * (0.5 + 0.9 * strength)
        items.append(
            Dust(
                (foot[0] + side * _rand.random() * 3, foot[1] - 1),
                (side * speed, -_rand.random() * 0.25),
                life=12 + _rand.randint(0, 8),
                radius=1.5 + _rand.random() * (1.0 + 1.5 * strength),
                shade=_rand.random() < 0.35,
            )
        )
    _emit(game, items)


def takeoff(game, foot) -> None:
    """A small puff under the feet as they leave the ground."""
    items = [
        Dust(
            (foot[0] + side * 2, foot[1] - 1),
            (side * (0.25 + _rand.random() * 0.35), -0.1 - _rand.random() * 0.2),
            life=10 + _rand.randint(0, 5),
            radius=1.2 + _rand.random() * 1.0,
        )
        for side in (-1, 1)
    ]
    _emit(game, items)


def wall_kick(game, point, away: int) -> None:
    """Grit off the wall the ninja kicks from; `away` is the side they jump to (-1 or 1)."""
    items = [
        Dust(
            (point[0], point[1] + _rand.uniform(-4, 4)),
            (away * (0.4 + _rand.random() * 0.6), _rand.uniform(-0.3, 0.3)),
            life=10 + _rand.randint(0, 6),
            radius=1.2 + _rand.random() * 1.2,
            shade=_rand.random() < 0.4,
        )
        for _ in range(4)
    ]
    _emit(game, items)


def _block_colors(image) -> list:
    """The opaque colors of a tile image (cached per image)."""
    cached = _COLORS.get(id(image))
    if cached is not None:
        return cached
    colorkey = image.get_colorkey()
    colors = []
    for y in range(0, image.get_height(), 2):
        for x in range(0, image.get_width(), 2):
            c = image.get_at((x, y))
            if c.a > 0 and (colorkey is None or tuple(c)[:3] != tuple(colorkey)[:3]):
                colors.append(tuple(c)[:3])
    _COLORS[id(image)] = colors = colors or [DUST_SHADE]
    return colors


_COLORS: dict = {}


def rubble(game, rect, image=None) -> None:
    """A broken block (crumbling tile at `rect`) bursts into chips of its own
    colors that tumble down, plus a puff of dust."""
    colors = _block_colors(image) if image is not None else [DUST_SHADE, DUST_COLOR]
    items = []
    for _ in range(14):
        x = rect.x + _rand.random() * rect.width
        y = rect.y + _rand.random() * rect.height
        away = (x - rect.centerx) / (rect.width / 2)
        items.append(
            Debris(
                (x, y),
                (away * _rand.uniform(0.3, 1.1), _rand.uniform(-1.6, 0.2)),
                _rand.choice(colors),
                size=2 if _rand.random() < 0.55 else 1,
                life=28 + _rand.randint(0, 18),
            )
        )
    for _ in range(5):
        items.append(
            Dust(
                (rect.x + _rand.random() * rect.width, rect.bottom - _rand.random() * 4),
                (_rand.uniform(-0.6, 0.6), _rand.uniform(-0.2, 0.1)),
                life=16 + _rand.randint(0, 8),
                radius=1.5 + _rand.random() * 1.5,
                shade=True,
            )
        )
    _emit(game, items)


__all__ = ["Debris", "Dust", "landing", "rubble", "takeoff", "wall_kick"]
