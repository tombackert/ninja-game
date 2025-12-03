import pygame
import pytest

from game import Game
from scripts.renderer import Renderer


@pytest.fixture(scope="module")
def pygame_init():
    pygame.init()
    yield
    pygame.quit()


def test_renderer_layer_order(pygame_init):
    g = Game()
    r = Renderer(show_perf=False)
    surface = pygame.Surface((g.BASE_W, g.BASE_H))
    seq = []
    # Minimal preparation consistent with Game.run partial logic
    g.cm.load_collectables()
    g.timer.update(g.level)
    # Execute render
    r.render(g, surface, capture_sequence=seq)
    # Expected ordering sequence subsequence (perf optional when disabled)
    expected = [
        "clear",
        "background",
        "world",
        # transition maybe absent if not active, so skip asserting it
        "compose",
        "hud",
        # perf omitted since show_perf False
        "effects_post",
        "blit",
    ]
    # Filter seq for those in expected to allow optional steps
    filtered = [s for s in seq if s in expected]
    assert filtered == expected, seq
