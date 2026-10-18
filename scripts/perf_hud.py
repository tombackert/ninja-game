"""Performance HUD metrics collection.

This module isolates *timing* concerns (work segment, full frame, smoothed
average) from the visual rendering of the overlay. Rendering of the text/UI
remains delegated to `UI.perf_overlay` so we do not further bloat the
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
    overlay = hud.overlay()  # surface to place on screen, or None

`begin_frame` sets both the *full* frame and *work* start markers.  The caller
must explicitly signal the end of the work portion (everything up to but NOT
including presenting) so the HUD can display both numbers, aiding diagnosis of
how much time is spent in simulation / composition versus present / vsync.
"""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Any

# A frame-to-frame interval above this missed at least one 60 Hz frame
HITCH_MS = 25.0
# Window for the worst interval (frames, ~1 s at 60 FPS)
WORST_WINDOW = 60

_task_info = None  # macOS: (task_info, own task port, mach_task_basic_info struct type)


def current_rss_mb() -> float | None:
    """Resident set size of this process right now, in MB (None where unknown).

    getrusage() only has the peak (ru_maxrss), which never goes down.
    """
    try:
        if sys.platform == "darwin":
            return _mach_resident_bytes() / (1024 * 1024)
        if sys.platform.startswith("linux"):
            with open("/proc/self/statm") as f:
                return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except Exception:
        pass
    return None


def _mach_resident_bytes() -> int:
    global _task_info
    import ctypes

    if _task_info is None:

        class MachTaskBasicInfo(ctypes.Structure):
            _pack_ = 4
            _fields_ = [
                ("virtual_size", ctypes.c_uint64),
                ("resident_size", ctypes.c_uint64),
                ("resident_size_max", ctypes.c_uint64),
                ("user_time", ctypes.c_int32 * 2),
                ("system_time", ctypes.c_int32 * 2),
                ("policy", ctypes.c_int32),
                ("suspend_count", ctypes.c_int32),
            ]

        libc = ctypes.CDLL(None)  # libSystem is loaded into every process
        task = ctypes.c_uint32.in_dll(libc, "mach_task_self_").value
        _task_info = (libc.task_info, task, MachTaskBasicInfo)
    task_info, task, info_type = _task_info
    info = info_type()
    count = ctypes.c_uint32(ctypes.sizeof(info_type) // 4)
    if task_info(task, 20, ctypes.byref(info), ctypes.byref(count)) != 0:  # 20: MACH_TASK_BASIC_INFO
        raise OSError("task_info failed")
    return info.resident_size


@dataclass
class PerformanceSample:
    """Snapshot of performance metrics for a single frame.

    Attributes:
        work_ms (float): Time in milliseconds spent on CPU work (logic + render commands).
            Excludes VSync/SwapBuffers time. High values indicate CPU bound.
        full_ms (float | None): Milliseconds from the start of rendering to the final blit.
            Excludes the simulation update, present and the frame wait, so it is not
            the frame time; see interval_ms for that.
        avg_work_ms (float | None): Exponential Moving Average of work_ms for smoothing jitter.
        fps (float | None): Instantaneous Frames Per Second as reported by the game clock.
        theor_fps (float | None): Theoretical maximum FPS possible based solely on work_ms
            (1000 / work_ms). Helps identify potential performance ceiling.
        memory_rss (float | None): Resident Set Size (RSS) memory usage in Megabytes.
            Indicates physical RAM currently used by the process.
        asset_count (int | None): Total count of loaded AssetManager resources (Images + Sounds).
            Useful for tracking asset leaks or loading spikes.
        interval_ms (float | None): Real time since the previous frame started (what the
            player sees; 16.67 ms at 60 FPS).
        worst_interval_ms (float | None): Longest interval over the last WORST_WINDOW frames.
        hitches (int | None): Intervals longer than HITCH_MS since the HUD started.
    """

    work_ms: float
    full_ms: float | None
    avg_work_ms: float | None
    fps: float | None
    theor_fps: float | None
    memory_rss: float | None = None
    asset_count: int | None = None
    interval_ms: float | None = None
    worst_interval_ms: float | None = None
    hitches: int | None = None


@dataclass
class PerformanceHUD:
    """System for collecting and managing performance metrics.

    Separates timing logic from rendering to allow headless profiling and
    cleaner architecture.

    Attributes:
        enabled (bool): Master toggle. If False, overhead is minimized to near zero.
        alpha (float): Smoothing factor (0.0 < alpha <= 1.0) for EMA calculations.
            Lower values = smoother lines but more lag. Default 0.1.
        log_path (Optional[str]): If provided, appends metrics to this CSV file path
            each frame. Useful for session profiling.
    """

    enabled: bool = True
    alpha: float = 0.1  # EMA smoothing factor for work segment
    log_path: Optional[str] = None
    _t_full_start: float = field(default=0.0, init=False, repr=False)
    _t_work_start: float = field(default=0.0, init=False, repr=False)
    _last_full_ms: float = field(default=0.0, init=False)
    _avg_work_ms: Optional[float] = field(default=None, init=False)
    _staging_sample: Optional[PerformanceSample] = field(default=None, init=False)
    _visible_sample: Optional[PerformanceSample] = field(default=None, init=False)
    _csv_file: Optional[Any] = field(default=None, init=False, repr=False)
    _csv_writer: Optional[Any] = field(default=None, init=False, repr=False)
    _t_prev_start: Optional[float] = field(default=None, init=False, repr=False)
    _intervals: deque = field(default_factory=lambda: deque(maxlen=WORST_WINDOW), init=False, repr=False)
    hitches: int = field(default=0, init=False)

    def begin_frame(self) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        self._note_interval(now)
        self._t_full_start = now
        self._t_work_start = now

    def note_frame(self) -> None:
        """Count a frame shown without rendering the game (the pause screen)."""
        if self.enabled:
            self._note_interval(time.perf_counter())

    def _note_interval(self, now: float) -> None:
        if self._t_prev_start is not None:
            interval = (now - self._t_prev_start) * 1000.0
            self._intervals.append(interval)
            if interval > HITCH_MS:
                self.hitches += 1
        self._t_prev_start = now

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
        self._staging_sample = PerformanceSample(
            work_ms=work_ms,
            full_ms=None,
            avg_work_ms=self._avg_work_ms,
            fps=None,
            theor_fps=(1000.0 / work_ms) if work_ms > 0 else None,
            interval_ms=self._intervals[-1] if self._intervals else None,
            worst_interval_ms=max(self._intervals) if self._intervals else None,
            hitches=self.hitches,
        )

    def end_frame(self, clock=None) -> None:  # clock optional to avoid circular imports in tests
        if not self.enabled:
            return
        t_full_end = time.perf_counter()
        full_ms = (t_full_end - self._t_full_start) * 1000.0
        self._last_full_ms = full_ms
        if self._staging_sample:
            # Enrich existing partial sample
            self._staging_sample.full_ms = full_ms
            if clock is not None:
                try:  # pragma: no cover - depends on pygame clock
                    fps = clock.get_fps()
                except Exception:  # pragma: no cover
                    fps = None
            else:
                fps = None
            self._staging_sample.fps = fps

            # Collect system stats (memory, assets)
            mem, assets = self._collect_sys_stats()
            self._staging_sample.memory_rss = mem
            self._staging_sample.asset_count = assets

            if self.log_path:
                self._log_sample()

            # Promote fully completed sample to visible
            self._visible_sample = self._staging_sample

    def _collect_sys_stats(self) -> tuple[float | None, int | None]:
        mem = current_rss_mb()
        assets = None

        try:
            from scripts.asset_manager import AssetManager

            if AssetManager._instance is None:
                assets = 0
            else:
                am = AssetManager.get()
                # Count loaded surfaces and sounds
                assets = len(am._images) + len(am._sounds)
        except Exception:
            pass

        return mem, assets

    def _log_sample(self) -> None:
        if not self._staging_sample or not self.log_path:
            return

        import json

        # Lazy init file
        if self._csv_file is None:
            import csv
            import os

            file_exists = os.path.isfile(self.log_path)
            try:
                self._csv_file = open(self.log_path, "a", newline="")
                self._csv_writer = csv.writer(self._csv_file)
                if not file_exists:
                    self._csv_writer.writerow(["timestamp", "work_ms", "full_ms", "fps", "counts"])
            except Exception:
                # Silently fail if file can't be opened to avoid crashing game
                self.log_path = None
                return

        if self._csv_writer is None:
            return

        import time

        counts = getattr(self, "_game_counts", {})
        try:
            row = [
                time.time(),
                f"{self._staging_sample.work_ms:.3f}",
                f"{self._staging_sample.full_ms:.3f}" if self._staging_sample.full_ms else "",
                f"{self._staging_sample.fps:.2f}" if self._staging_sample.fps else "",
                json.dumps(counts),
            ]
            self._csv_writer.writerow(row)
        except Exception:
            pass

    @property
    def last_sample(self) -> Optional[PerformanceSample]:
        return self._staging_sample

    @property
    def last_full_frame_ms(self) -> float:
        return self._last_full_ms

    def overlay(self):
        """The overlay surface (built by the UI layer) if enabled and a sample exists, else None.

        It is rebuilt only every 10th call and is the same surface in between,
        so a caller can keep a scaled copy until it changes.

        Import is local to avoid creating a hard dependency for pure logic tests.
        """
        # Use visible_sample (from previous frame) so we have full metrics
        if not (self.enabled and self._visible_sample):
            return None
        try:
            from scripts.ui import UI

            game_counts = getattr(self, "_game_counts", None)
            return UI.perf_overlay(
                work_ms=self._visible_sample.work_ms,
                frame_full_ms=self._visible_sample.full_ms,
                avg_work_ms=self._visible_sample.avg_work_ms,
                fps=self._visible_sample.fps,
                theor_fps=self._visible_sample.theor_fps,
                memory_rss=self._visible_sample.memory_rss,
                asset_count=self._visible_sample.asset_count,
                interval_ms=self._visible_sample.interval_ms,
                worst_interval_ms=self._visible_sample.worst_interval_ms,
                hitches=self._visible_sample.hitches,
                game_counts=game_counts,
            )
        except Exception:  # pragma: no cover - overlay optional in headless tests
            return None


__all__ = ["PerformanceHUD", "PerformanceSample"]
