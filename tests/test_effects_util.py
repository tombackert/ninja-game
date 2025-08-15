import pygame
import os
from scripts.effects_util import spawn_hit_sparks, spawn_projectile_sparks
from game import Game

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


def test_spawn_hit_sparks_counts():
    g = Game()
    before_sparks = len(g.sparks)
    before_particles = len(g.particles)
    spawn_hit_sparks(g, (100, 100), count=10)
    after_sparks = len(g.sparks)
    after_particles = len(g.particles)
    assert after_sparks - before_sparks == 10
    assert after_particles - before_particles == 10


def test_spawn_projectile_sparks_direction():
    g = Game()
    before = len(g.sparks)
    spawn_projectile_sparks(g, (50, 50), direction=3.5)
    assert len(g.sparks) > before
