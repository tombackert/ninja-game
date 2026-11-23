"""Game over (last life gone) and Restart in the pause menu."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402
import pytest  # noqa: E402

from scripts import death_log  # noqa: E402
from scripts.constants import AIR_TIME_FATAL, RESPAWN_DEAD_THRESHOLD  # noqa: E402
from scripts.input_router import InputRouter  # noqa: E402
from scripts.settings import settings  # noqa: E402
from scripts.state_manager import (  # noqa: E402
    GameOverState,
    GameState,
    MenuState,
    PauseState,
    StateManager,
    fresh_game_state,
)
import test_death_log as _dl  # noqa: E402

# The death log tests' scratch map, log folder and save redirection
MAP_ID = _dl.MAP_ID
maps = _dl.maps
deaths = _dl.deaths
scratch_saves = _dl.scratch_saves

DEATH_FRAMES = AIR_TIME_FATAL + 2 * RESPAWN_DEAD_THRESHOLD + 60


@pytest.fixture(autouse=True)
def campaign_level(monkeypatch):
    """Select the test map as the campaign level without writing data/settings.json."""
    monkeypatch.setattr(settings, "flush", lambda *a, **k: None)
    before = settings.selected_level
    settings.selected_level = MAP_ID
    yield
    settings._selected_level = before


def _running(sm: StateManager) -> GameState:
    pygame.init()
    sm.set(GameState())
    gs = sm.current
    assert isinstance(gs, GameState) and gs.game.level == MAP_ID
    for _ in range(5):
        gs.update(1 / 60)
    return gs


def _lose_last_life(sm: StateManager, gs: GameState) -> None:
    g = gs.game
    g.player.lives = 1
    g.player.pos = [12 * 16.0, 17 * 16.0]  # over the pit
    g.player.velocity = [0, 0]
    for _ in range(DEATH_FRAMES):
        if sm.current is not gs:
            return
        sm.update(1 / 60)
        if g.dead and g.player.lives > 0:
            g.player.lives = 0  # the fall takes the last life, as a bullet would
    raise AssertionError("no game over")


def _press(sm, router, key):
    actions = router.process([pygame.event.Event(pygame.KEYDOWN, {"key": key})], sm.current.name)
    sm.handle_actions(actions)
    sm.update(1 / 60)


def test_the_last_life_lost_shows_the_game_over_screen(maps, deaths):
    sm = StateManager()
    gs = _running(sm)
    _lose_last_life(sm, gs)
    over = sm.current
    assert isinstance(over, GameOverState) and over.level == MAP_ID
    # the death ends the attempt; leaving the game adds no "quit" line
    events = [line["event"] for line in death_log.read(MAP_ID, str(deaths))]
    assert events == ["death"]
    assert death_log.read(MAP_ID, str(deaths))[0]["restart"] is True
    over.render(pygame.Surface((1280, 720)))


def test_game_over_ignores_input_at_first_then_try_again_starts_over(maps, deaths):
    sm = StateManager()
    router = InputRouter()
    _lose_last_life(sm, _running(sm))
    over = sm.current
    _press(sm, router, pygame.K_RETURN)  # still holding keys from play
    assert sm.current is over
    over._age = GameOverState.INPUT_DELAY
    _press(sm, router, pygame.K_RETURN)  # "Try Again" is selected first
    fresh = sm.current
    assert isinstance(fresh, GameState) and fresh.game.level == MAP_ID
    assert fresh.game.player.lives == 3


def test_game_over_to_menu(maps, deaths):
    sm = StateManager()
    router = InputRouter()
    _lose_last_life(sm, _running(sm))
    sm.current._age = GameOverState.INPUT_DELAY
    _press(sm, router, pygame.K_DOWN)
    _press(sm, router, pygame.K_RETURN)
    assert isinstance(sm.current, MenuState)


def test_restart_in_the_pause_menu_starts_the_level_over(maps, deaths):
    sm = StateManager()
    router = InputRouter()
    gs = _running(sm)
    gs.game.player.lives = 1
    sm.push(PauseState())
    pause = sm.current
    assert pause.options_keys == ["menu.resume", "menu.restart", "level_complete.menu"]
    _press(sm, router, pygame.K_DOWN)
    _press(sm, router, pygame.K_RETURN)
    assert pause.closed and pause.restart_requested and not pause.return_to_menu
    # what app.py does with it
    sm.pop()
    sm.set(fresh_game_state(sm.current.game.level))
    assert sm.current is not gs and sm.current.game.player.lives == 3


def test_r_restarts_from_the_pause_menu(maps):
    sm = StateManager()
    _running(sm)
    sm.push(PauseState())
    _press(sm, InputRouter(), pygame.K_r)
    assert sm.current.closed and sm.current.restart_requested


def test_a_multiplayer_pause_offers_no_restart():
    class _Multiplayer:
        def network_idle_update(self):
            pass

    pygame.init()
    pause = PauseState()
    pause.on_enter(_Multiplayer())
    assert "menu.restart" not in pause.options_keys
    pause.handle_actions(["pause_restart"])
    assert not pause.restart_requested and not pause.closed


def test_a_named_map_restarts_by_name(maps, monkeypatch):
    seen = []
    monkeypatch.setattr(GameState, "__init__", lambda self, level=None: seen.append(level))
    fresh_game_state("calibration")
    assert seen == ["calibration"]


def test_the_game_over_backdrop_has_no_alpha_to_lose():
    """On macOS the window is ARGB: a backdrop in its format ended up with alpha 0
    under the red veil, and every outlined text showed its whole box."""
    pygame.init()
    over = GameOverState(level=MAP_ID)
    screen = pygame.Surface((1280, 720), pygame.SRCALPHA)  # the window's ARGB format
    over.render(screen)
    # (the headless display is not ARGB, so the buffer's own format is checked)
    assert over._backdrop.get_bitsize() == 24 and over._backdrop.get_masks()[3] == 0
    assert screen.get_at((100, 600)).a == 255
