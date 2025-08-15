import os
import pygame
from scripts.state_manager import StateManager, GameState
from scripts.input_router import InputRouter

os.environ["NINJA_GAME_TESTING"] = "1"


def test_debug_overlay_toggle():
    pygame.init()
    sm = StateManager()
    gs = GameState()
    sm.set(gs)
    router = InputRouter()
    # Simulate F1 key press
    evt = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F1})
    actions = router.process([evt], sm.current.name)
    sm.handle_actions(actions)
    assert gs.debug_overlay is True
    # Press again to toggle off
    actions = router.process([evt], sm.current.name)
    sm.handle_actions(actions)
    assert gs.debug_overlay is False
    pygame.quit()
