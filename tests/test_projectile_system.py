import os
import pygame

from scripts.projectile_system import ProjectileSystem
from scripts.constants import PROJECTILE_LIFETIME_FRAMES


class DummyTilemap:
    def __init__(self, solid_positions=None):
        self.solid_positions = set(tuple(p) for p in (solid_positions or []))

    def solid_check(self, pos):
        # Simple point block collision
        key = tuple(int(round(c)) for c in pos)
        return key in self.solid_positions


def make_game_with_assets():
    class G:
        pass

    g = G()
    # Minimal assets required by projectile + spark spawning utilities
    surf = pygame.Surface((4, 4))
    g.assets = {
        "projectile": surf,
        "particle/particle": type(
            "Anim",
            (),
            {
                "copy": lambda self=surf: self,
                "img": lambda self=surf: surf,
                "update": lambda self=surf: None,
            },
        )(),
    }

    class Aud:
        def play(self, name, loops=0):
            return None

    g.audio = Aud()
    g.cm = type("C", (), {"coins": 0})()
    g.screenshake = 0
    g.sparks = []
    g.particles = []
    return g


def test_projectile_lifetime_expires(monkeypatch):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    game = make_game_with_assets()
    ps = ProjectileSystem(game)
    ps.spawn(0, 0, 1, "player")
    tm = DummyTilemap()
    # Advance just over lifetime
    for _ in range(PROJECTILE_LIFETIME_FRAMES + 1):
        ps.update(tm, players=[], enemies=[])
    assert len(list(ps)) == 0


def test_projectile_hits_enemy(monkeypatch):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    game = make_game_with_assets()
    ps = ProjectileSystem(game)
    ps.spawn(0, 0, 0, "player")  # stationary projectile centered on enemy

    class Enemy:
        def rect(self):
            return pygame.Rect(0, 0, 10, 10)

    summary = ps.update(DummyTilemap(), players=[], enemies=[Enemy()])
    assert summary["hits_enemy"] == 1
    assert len(list(ps)) == 0
    assert game.cm.coins == 1


def test_enemy_projectile_hits_player(monkeypatch):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    game = make_game_with_assets()
    ps = ProjectileSystem(game)
    ps.spawn(0, 0, 0, "enemy")

    class Player:
        def __init__(self):
            self._lives = 3
            self.dashing = 0

        def rect(self):
            return pygame.Rect(0, 0, 10, 10)

        @property
        def lives(self):
            return self._lives

        @lives.setter
        def lives(self, v):
            self._lives = v

    p = Player()
    summary = ps.update(DummyTilemap(), players=[p], enemies=[])
    assert summary["hits_player"] == 1
    assert p.lives == 2
    assert len(list(ps)) == 0
