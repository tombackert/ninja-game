"""The F1 perf overlay is scaled once per rebuild, not with the HUD layer every frame."""

import os
import types

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from game import Game  # noqa: E402
from scripts.renderer import Renderer  # noqa: E402
from scripts.ui import UI  # noqa: E402


def test_perf_overlay_is_scaled_once_per_rebuild_and_drawn_in_place():
    pygame.init()
    g = Game()
    g.load_level(0)
    g.replay.ghost = None
    g.screenshake = 0
    g.transition = 0
    g.state_ref = types.SimpleNamespace(perf_enabled=True)
    r = Renderer(show_perf=True)
    UI._perf_overlay_frame = 0
    UI._perf_overlay_cache = None
    target = pygame.Surface((g.BASE_W * 2, g.BASE_H * 2))

    # Frame 1 has no complete sample yet; frames 2-6 share one overlay build
    scaled = []
    for i in range(6):
        g.scroll = [100.0 + i * 0.5, 40.0]
        r.render(g, target)
        if r._perf is not None:
            scaled.append(r._perf[2])
    assert len(scaled) == 5
    assert all(s is scaled[0] for s in scaled)

    overlay = r._perf[0]
    y0 = g.BASE_H - 170
    if y0 + overlay.get_height() > g.BASE_H:
        y0 = g.BASE_H - overlay.get_height() - 5
    # The HUD layer (scaled every frame) keeps to its text, above the overlay
    assert r._hud_dirty.bottom <= y0
    # Opaque overlay pixels land on the window 2x scaled at (5, y0)
    text = [
        (x, y)
        for x in range(overlay.get_width())
        for y in range(overlay.get_height())
        if overlay.get_at((x, y)).a == 255
    ]
    assert text, "overlay drew nothing"
    for x, y in text:
        assert target.get_at((2 * (5 + x), 2 * (y0 + y))) == overlay.get_at((x, y)), (x, y)
