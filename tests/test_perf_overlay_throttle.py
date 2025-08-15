import pygame
from scripts.ui import UI


def test_perf_overlay_throttling(monkeypatch):
    pygame.display.init()
    pygame.font.init()
    # Monkeypatch get_font to avoid relying on external font file in test env
    UI.get_font = staticmethod(lambda size: pygame.font.SysFont(None, size))  # type: ignore
    surf = pygame.Surface((200, 150))
    # Ensure clean cache state
    if hasattr(UI, "_perf_overlay_frame"):
        delattr(UI, "_perf_overlay_frame")
    if hasattr(UI, "_perf_overlay_cache"):
        delattr(UI, "_perf_overlay_cache")

    # Draw several times with update_every=5
    prev_id = None
    rebuilds = 0
    for i in range(1, 16):
        UI.render_perf_overlay(
            surf,
            work_ms=4.2,
            frame_full_ms=8.4,
            avg_work_ms=4.0,
            fps=60.0,
            theor_fps=238.0,
            update_every=5,
        )
        cache = getattr(UI, "_perf_overlay_cache")
        cid = id(cache)
        if cid != prev_id:
            rebuilds += 1
            prev_id = cid
    # For 15 frames with update_every=5 we expect 3 rebuilds (frames 1,6,11)
    assert rebuilds == 3, f"Expected 3 rebuilds, got {rebuilds}"
