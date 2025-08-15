"""Performance HUD metrics collection.

This module isolates *timing* concerns (work segment, full frame, smoothed
average) from the visual rendering of the overlay. Rendering of the text/UI
remains delegated to `UI.render_perf_overlay` so we do not further bloat the
already large `ui.py` with stateful timing logic.  The split improves testability:

* The numeric smoothing behaviour (EMA) can be unit tested without initializing
  pygame or fonts (see `tests/test_performance_hud.py`).
* Future exporters (e.g. JSON line logs, profiling samples, telemetry) can reuse
  the metrics object without importing UI code.

Typical usage (inside the main renderer):

    hud = PerformanceHUD(enabled=True)
    hud.begin_frame()
    # ... do work ...
    hud.end_work_segment()
    # ... post effects / present ...
    hud.end_frame()
    hud.render(surface, y=game.BASE_H - 120)

`begin_frame` sets both the *full* frame and *work* start markers.  The caller
must explicitly signal the end of the work portion (everything up to but NOT
including presenting) so the HUD can display both numbers, aiding diagnosis of
how much time is spent in simulation / composition versus present / vsync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Optional


@dataclass
class PerformanceSample:
    work_ms: float
    full_ms: float | None
    avg_work_ms: float | None
    fps: float | None
    theor_fps: float | None


@dataclass
class PerformanceHUD:
    enabled: bool = True
    alpha: float = 0.1  # EMA smoothing factor for work segment
    _t_full_start: float = field(default=0.0, init=False, repr=False)
    _t_work_start: float = field(default=0.0, init=False, repr=False)
    _last_full_ms: float = field(default=0.0, init=False)
    _avg_work_ms: Optional[float] = field(default=None, init=False)
    _last_sample: Optional[PerformanceSample] = field(default=None, init=False)

    def begin_frame(self) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        self._t_full_start = now
        self._t_work_start = now

    def end_work_segment(self) -> None:
        """Mark the logical end of the *work* portion of the frame.

        The *work* portion excludes final post-effects and the actual present
        call (which may involve vsync waiting).  This separation helps
        differentiate CPU simulation/composition time from present / swap
        overhead.
        """
        if not self.enabled:
            return
        t_work_end = time.perf_counter()
        work_ms = (t_work_end - self._t_work_start) * 1000.0
        # Update EMA for work segment
        if self._avg_work_ms is None:
            self._avg_work_ms = work_ms
        else:
            self._avg_work_ms = self.alpha * work_ms + (1 - self.alpha) * self._avg_work_ms
        # Temporarily store partial sample (full_ms, fps filled in at end_frame)
        self._last_sample = PerformanceSample(
            work_ms=work_ms,
            full_ms=None,
            avg_work_ms=self._avg_work_ms,
            fps=None,
            theor_fps=(1000.0 / work_ms) if work_ms > 0 else None,
        )

    def end_frame(self, clock=None) -> None:  # clock optional to avoid circular imports in tests
        if not self.enabled:
            return
        t_full_end = time.perf_counter()
        full_ms = (t_full_end - self._t_full_start) * 1000.0
        self._last_full_ms = full_ms
        if self._last_sample:
            # Enrich existing partial sample
            self._last_sample.full_ms = full_ms
            if clock is not None:
                try:  # pragma: no cover - depends on pygame clock
                    fps = clock.get_fps()
                except Exception:  # pragma: no cover
                    fps = None
            else:
                fps = None
            self._last_sample.fps = fps

    @property
    def last_sample(self) -> Optional[PerformanceSample]:
        return self._last_sample

    @property
    def last_full_frame_ms(self) -> float:
        return self._last_full_ms

    def render(self, surface, *, x: int = 5, y: int = 5) -> None:
        """Delegate drawing to UI layer if enabled and a sample exists.

        Import is local to avoid creating a hard dependency for pure logic tests.
        """
        if not (self.enabled and self._last_sample):
            return
        try:
            from scripts.ui import UI

            game_counts = getattr(self, "_game_counts", None)
            UI.render_perf_overlay(
                surface,
                work_ms=self._last_sample.work_ms,
                frame_full_ms=self._last_sample.full_ms,
                avg_work_ms=self._last_sample.avg_work_ms,
                fps=self._last_sample.fps,
                theor_fps=self._last_sample.theor_fps,
                x=x,
                y=y,
                game_counts=game_counts,
            )
        except Exception:  # pragma: no cover - overlay optional in headless tests
            pass


__all__ = ["PerformanceHUD", "PerformanceSample"]
