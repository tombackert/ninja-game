"""The camera glides in window pixels; background and HUD do not move with it."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from game import Game  # noqa: E402
from scripts.renderer import Renderer  # noqa: E402


def _setup():
    pygame.init()
    g = Game()
    g.load_level(0)
    g.replay.ghost = None
    g.screenshake = 0
    g.transition = 0  # no level-start iris (it covers the world in black)
    return g, Renderer(show_perf=False)


def _frame(g, r, scroll):
    """Render at `scroll` on a 2x window.

    Also returns the world layer (tiles, entities) and the camera-shifted
    layer (world plus parallax clouds) as drawn at base resolution.
    """
    g.scroll = list(scroll)
    target = pygame.Surface((g.BASE_W * 2, g.BASE_H * 2))
    r.render(g, target)
    return target, g.display.copy(), g.display_2.copy()


def _points(g):
    # Below the HUD, away from the window edges
    return [(x, y) for y in range(80, g.BASE_H * 2 - 2, 7) for x in range(2, g.BASE_W * 2 - 2, 11)]


def _check_world_shift(g, a, world_a, b, dx):
    """Opaque world pixels of b equal those of a moved by dx window pixels.

    Clouds are left out: they move by parallax, not with the world.
    """
    checked = moved = 0
    for x, y in _points(g):
        if world_a.get_at(((x - dx) // 2, y // 2)).a == 255:
            assert b.get_at((x, y)) == a.get_at((x - dx, y)), (x, y)
            checked += 1
            moved += b.get_at((x, y)) != a.get_at((x, y))
    assert checked > 100 and moved > 10


def test_half_pixel_scroll_shifts_world_by_one_window_pixel():
    g, r = _setup()
    a, world_a, _ = _frame(g, r, (100.0, 40.0))
    b, _, _ = _frame(g, r, (100.5, 40.0))
    _check_world_shift(g, a, world_a, b, -1)


def test_negative_scroll_uses_floor():
    g, r = _setup()
    a, world_a, _ = _frame(g, r, (-20.0, -10.0))
    b, _, _ = _frame(g, r, (-20.5, -10.0))
    _check_world_shift(g, a, world_a, b, 1)


def test_background_and_hud_stay_put_while_camera_moves():
    g, r = _setup()
    a, _, layer_a = _frame(g, r, (100.0, 40.0))
    hud = r._hud.copy()
    b, _, layer_b = _frame(g, r, (100.5, 40.5))
    # Background: pixels with no world or cloud in either frame are unchanged
    sky = [
        (x, y)
        for x, y in _points(g)
        if layer_a.get_at((x // 2, y // 2)).a == 0 and layer_b.get_at(((x + 1) // 2, (y + 1) // 2)).a == 0
    ]
    assert len(sky) > 100
    for p in sky:
        assert a.get_at(p) == b.get_at(p), p
    # HUD: its opaque pixels land on the same window pixels
    text = [(x, y) for x in range(g.BASE_W) for y in range(40) if hud.get_at((x, y)).a == 255]
    assert text, "HUD drew nothing"
    for x, y in text:
        assert a.get_at((2 * x, 2 * y)) == b.get_at((2 * x, 2 * y)), (x, y)
