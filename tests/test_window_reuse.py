"""Starting a level keeps the open window instead of recreating it."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from game import Game  # noqa: E402


def test_new_game_keeps_the_open_window(monkeypatch):
    pygame.init()
    first = Game(fullscreen=False)
    calls = []
    real_set_mode = pygame.display.set_mode
    monkeypatch.setattr(pygame.display, "set_mode", lambda *a, **k: calls.append(a) or real_set_mode(*a, **k))

    second = Game(fullscreen=False)

    assert calls == []
    assert second.screen is pygame.display.get_surface()
    assert second.screen.get_size() == first.screen.get_size()


def test_new_game_opens_a_window_when_none_is_open():
    pygame.init()
    pygame.display.quit()
    pygame.display.init()
    assert pygame.display.get_surface() is None

    g = Game(fullscreen=False)

    assert g.screen is pygame.display.get_surface()
    assert g.screen.get_size() == (g.WIN_W, g.WIN_H)
