import os

import pygame

from scripts.input_router import InputRouter
from scripts.state_manager import GameState, MenuState, PauseState, StateManager

os.environ["NINJA_GAME_TESTING"] = "1"


def pump(sm, router, events):
    current_name = sm.current.name if sm.current else ""
    actions = router.process(events, current_name)
    sm.handle_actions(actions)
    sm.update(1 / 60)


def test_menu_to_game_and_pause_cycle(monkeypatch):
    pygame.init()
    # screen = pygame.display.set_mode((320, 180))
    # clock = pygame.time.Clock()

    sm = StateManager()
    router = InputRouter()
    menu = MenuState()
    sm.set(menu)

    # Simulate pressing ENTER to start game
    events = [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})]
    pump(sm, router, events)
    # update will set start_game flag which app loop would react to;
    # simulate that transition manually
    if getattr(sm.current, "start_game", False):
        sm.set(GameState())
    assert isinstance(sm.current, GameState)

    # Request pause via ESC
    events = [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})]
    pump(sm, router, events)
    if getattr(sm.current, "request_pause", False):
        sm.push(PauseState())
    assert isinstance(sm.current, PauseState)

    # Close pause (ESC)
    events = [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})]
    pump(sm, router, events)
    if isinstance(sm.current, PauseState) and sm.current.closed:
        sm.pop()
    assert isinstance(sm.current, GameState)

    # Return to menu by pushing pause again and choosing menu (simulate 'm')
    events = [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})]
    pump(sm, router, events)
    if getattr(sm.current, "request_pause", False):
        sm.push(PauseState())
    events = [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_m})]
    pump(sm, router, events)
    if isinstance(sm.current, PauseState) and sm.current.return_to_menu:
        sm.pop()
        sm.set(MenuState())
    assert isinstance(sm.current, MenuState)

    pygame.quit()
