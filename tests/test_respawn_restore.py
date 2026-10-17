"""A respawn restores the level from memory, exactly as re-reading the map would."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from game import Game  # noqa: E402

LEVEL = 3  # coins, enemies and offgrid decor


def _state(g):
    return (
        sorted((loc, t["type"], t["variant"], tuple(t["pos"])) for loc, t in g.tilemap.tilemap.items()),
        [(t["type"], t["variant"], tuple(t["pos"])) for t in g.tilemap.offgrid_tiles],
        [(e.id, list(e.pos)) for e in g.enemies],
        [list(c.pos) for c in g.cm.coin_list],
        [list(p.pos) for p in g.players],
    )


def _play(g):
    """Change what a run changes: defeat an enemy, collect a coin, move."""
    g.enemies.pop(0)
    g.cm.coin_list.pop(0)
    g.player.pos = [0.0, 0.0]


def test_respawn_restores_the_level_without_reading_the_map(monkeypatch):
    pygame.init()
    g = Game()
    g.load_level(LEVEL)
    assert g.enemies and g.cm.coin_list

    _play(g)
    g.tilemap.loaded_path = None  # previous behaviour: parse the map file again
    g.load_level(LEVEL, lives=2, respawn=True)
    reloaded = _state(g)

    _play(g)
    loads = []
    monkeypatch.setattr(g.tilemap, "load", lambda *a, **k: loads.append(a))
    g.load_level(LEVEL, lives=2, respawn=True)

    assert loads == []
    assert _state(g) == reloaded


def test_other_level_is_read_from_its_file():
    pygame.init()
    g = Game()
    g.load_level(LEVEL)
    g.load_level(0, respawn=True)

    assert g.tilemap.loaded_path == "data/maps/0.json"
