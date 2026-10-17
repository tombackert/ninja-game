"""The pause screen composes a frozen game once; a live multiplayer world keeps drawing."""

import os
import types

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from scripts.perf_hud import PerformanceHUD  # noqa: E402
from scripts.state_manager import PauseState  # noqa: E402

GAME_COLOR = (200, 60, 40)


class _Game:
    def __init__(self):
        self.renders = 0

    def render(self, surface):
        self.renders += 1
        surface.fill(GAME_COLOR)


class _MultiplayerGame(_Game):
    def network_idle_update(self):
        pass


def _pause(underlying):
    pygame.init()
    pause = PauseState()
    pause.on_enter(underlying)
    return pause


def test_paused_game_is_rendered_once():
    game = _Game()
    pause = _pause(game)
    surface = pygame.Surface((320, 180))

    for _ in range(5):
        pause.render(surface)

    assert game.renders == 1
    # The game is still shown underneath, darkened
    r, g, b, _ = surface.get_at((2, 2))
    assert 0 < r < GAME_COLOR[0] and r > g


def test_live_multiplayer_world_keeps_rendering():
    game = _MultiplayerGame()
    pause = _pause(game)
    surface = pygame.Surface((320, 180))

    for _ in range(5):
        pause.render(surface)

    assert game.renders == 5


def test_pause_frames_count_as_shown_frames_in_the_hud():
    hud = PerformanceHUD(enabled=True)
    game = _Game()
    game._renderer = types.SimpleNamespace(perf_hud=hud)
    real_render = game.render

    def render(surface):  # like GameState.render: the renderer times the frame
        hud.begin_frame()
        real_render(surface)

    game.render = render
    pause = _pause(game)
    surface = pygame.Surface((320, 180))

    hud.begin_frame()  # last game frame
    for _ in range(3):  # composes once (renders the game), then reuses
        pause.render(surface)
    hud.begin_frame()  # first frame after resuming

    assert game.renders == 1
    assert len(hud._intervals) == 4  # one per frame shown, no gap over the pause
    assert hud.hitches == 0
