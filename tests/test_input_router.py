import os
import pygame
from scripts.input_router import InputRouter

os.environ["NINJA_GAME_TESTING"] = "1"


def test_menu_navigation_actions():
    pygame.init()
    router = InputRouter()
    events = [
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_UP}),
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN}),
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}),
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}),
    ]
    actions = router.process(events, "MenuState")
    # Order preserved, duplicates avoided
    assert actions == ["menu_up", "menu_down", "menu_select", "menu_quit"]


def test_game_pause_action():
    pygame.init()
    router = InputRouter()
    events = [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})]
    actions = router.process(events, "GameState")
    assert actions == ["pause_toggle"]


def test_pause_menu_actions():
    pygame.init()
    router = InputRouter()
    events = [
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}),
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_m}),
    ]
    actions = router.process(events, "PauseState")
    # First ESC closes, M would request menu; ensure both captured
    assert actions == ["pause_close", "pause_menu"]
