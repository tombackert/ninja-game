import pygame

from scripts.ui import UI


def test_perf_overlay_throttling(monkeypatch):
    pygame.display.init()
    pygame.font.init()
    # Monkeypatch get_font to avoid relying on external font file in test env
    UI.get_font = staticmethod(lambda size: pygame.font.SysFont(None, size))  # type: ignore
    # Ensure clean cache state
    UI._perf_overlay_frame = 0
    UI._perf_overlay_cache = None

    # Build several times with update_every=5
    prev_id = None
    rebuilds = 0
    for i in range(1, 16):
        overlay = UI.perf_overlay(
            work_ms=4.2,
            frame_full_ms=8.4,
            avg_work_ms=4.0,
            fps=60.0,
            theor_fps=238.0,
            update_every=5,
        )
        assert overlay is UI._perf_overlay_cache
        cid = id(overlay)
        if cid != prev_id:
            rebuilds += 1
            prev_id = cid
    # For 15 frames with update_every=5 we expect 3 rebuilds (frames 1,6,11)
    assert rebuilds == 3, f"Expected 3 rebuilds, got {rebuilds}"
