"""Unified rendering pipeline (Issue 14).

This module centralizes frame composition order so that *all* entry
points (legacy `Game.run` and new `GameState.render`) follow the same
deterministic layering. This is a transitional orchestrator; future
iterations (Issues 15–18) will replace direct asset / effect access
with dedicated systems (AssetManager, ParticleSystem, etc.).

Layer Order (bottom -> top):
1. Clear primary off-screen buffers (game.display)
2. Background image -> display_2
3. World & entities (tiles, player, enemies, projectiles, particles) via UI helper
4. Transition / full-screen visual effects pre-compose (optional)
5. Compose game.display onto display_2
6. HUD / UI overlay (timer, level info, lives, coins, ammo, perf metrics)
7. Screen shake / post effects applied just before blitting to window

Design Notes:
- Keeps all mutation of game surfaces in one place.
- Optional `capture_sequence` parameter records executed high-level steps
  for tests (avoids brittle pixel sampling with live artwork).
- Avoids importing heavy modules at top-level when possible to reduce
  import side-effects during test collection.
"""

from __future__ import annotations
from typing import List, Optional
import time
import pygame

try:  # Local logger (not mandatory for tests)
    from scripts.logger import get_logger  # type: ignore
except Exception:  # pragma: no cover - fallback when logger absent

    def get_logger(name: str):  # type: ignore
        class _Nop:
            def debug(self, *a, **k):
                pass

        return _Nop()


_log = get_logger("renderer")


class Renderer:
    """High-level frame orchestrator.

    Usage:
        r = Renderer(show_perf=True)
        r.render(game, window_surface)
    """

    def __init__(self, show_perf: bool = True) -> None:
        # Performance tracking
        self.show_perf = show_perf
        self._last_frame_ms = 0.0
        self._avg_frame_ms: Optional[float] = None  # moving average frame time (ms)
        self._alpha = 0.1  # smoothing factor for EMA

    @property
    def last_frame_ms(self) -> float:
        return self._last_frame_ms

    def render(
        self,
        game,  # legacy Game object
        target_surface: pygame.Surface,
        capture_sequence: Optional[List[str]] = None,
    ) -> None:
        seq = capture_sequence
        # Start timing (full frame). We'll measure 'work' up to just before present.
        t_full_start = time.perf_counter()
        t_work_start = t_full_start
        # 1. Clear primary off-screen buffer
        game.display.fill((0, 0, 0, 0))
        if seq is not None:
            seq.append("clear")

        # 2. Background
        game.display_2.blit(game.assets["background"], (0, 0))
        if seq is not None:
            seq.append("background")

        # 3. World & entities
        from scripts.ui import UI  # local import avoids cycles

        game.scroll[0] += (game.player.rect().centerx - game.display.get_width() / 2 - game.scroll[0]) / 30
        game.scroll[1] += (game.player.rect().centery - game.display.get_height() / 2 - game.scroll[1]) / 30
        render_scroll = (int(game.scroll[0]), int(game.scroll[1]))
        UI.render_game_elements(game, render_scroll)
        if seq is not None:
            seq.append("world")

        # 4. Transition
        from scripts.effects import Effects

        if game.transition:
            Effects.transition(game)
            if seq is not None:
                seq.append("effects_transition")

        # 5. Compose
        game.display_2.blit(game.display, (0, 0))
        if seq is not None:
            seq.append("compose")

        # 6. HUD
        self._render_hud(game)
        if seq is not None:
            seq.append("hud")
        # Performance metrics (work segment ends here, before post effects & present)
        t_work_end = time.perf_counter()
        work_ms = (t_work_end - t_work_start) * 1000.0
        # Update EMA (based on work time for responsiveness insight)
        if self._avg_frame_ms is None:
            self._avg_frame_ms = work_ms
        else:
            self._avg_frame_ms = self._alpha * work_ms + (1 - self._alpha) * self._avg_frame_ms
        if self.show_perf:
            try:
                from scripts.settings import settings as _settings  # type: ignore

                perf_enabled = getattr(_settings, "show_perf_overlay", True)
            except Exception:  # pragma: no cover
                perf_enabled = True
            if perf_enabled:
                from scripts.ui import UI  # local import for cache stats

                fps = game.clock.get_fps()
                theor_fps = 1000.0 / work_ms if work_ms > 0 else None
                # Pass previous full frame time (self._last_frame_ms) so overlay shows last complete frame.
                UI.render_perf_overlay(
                    game.display_2,
                    work_ms=work_ms,
                    frame_full_ms=self._last_frame_ms if self._last_frame_ms else None,
                    avg_work_ms=self._avg_frame_ms,
                    fps=fps,
                    theor_fps=theor_fps,
                    x=5,
                    y=game.BASE_H - 120,
                )
                if seq is not None:
                    seq.append("perf")

        # 7. Post effects (screenshake) then present
        Effects.screenshake(game)
        if seq is not None:
            seq.append("effects_post")

        if game.display_2.get_size() != target_surface.get_size():
            scaled = pygame.transform.scale(game.display_2, target_surface.get_size())
            target_surface.blit(scaled, (0, 0))
        else:
            target_surface.blit(game.display_2, (0, 0))
        if seq is not None:
            seq.append("blit")
        # Now that the frame is presented (blit done), finalize full frame timing.
        t_full_end = time.perf_counter()
        full_ms = (t_full_end - t_full_start) * 1000.0
        self._last_frame_ms = full_ms

    # Full frame time available next frame via self._last_frame_ms

    def _render_hud(self, game) -> None:
        from scripts.ui import UI

        UI.render_game_ui_element(game.display_2, f"{game.timer.text}", game.BASE_W - 70, 5)
        UI.render_game_ui_element(game.display_2, f"{game.timer.best_time_text}", game.BASE_W - 70, 15)
        UI.render_game_ui_element(game.display_2, f"Level: {game.level}", game.BASE_W // 2 - 40, 5)
        if getattr(game, "player", None):
            lives = getattr(game.player, "lives", getattr(game.player, "lifes", 0))
            UI.render_game_ui_element(game.display_2, f"Lives: {lives}", 5, 5)
        UI.render_game_ui_element(game.display_2, f"${game.cm.coins}", 5, 15)
        UI.render_game_ui_element(game.display_2, f"Ammo:  {game.cm.ammo}", 5, 25)


__all__ = ["Renderer"]
