"""Frame pacing at an exact frame rate.

`pygame.time.Clock.tick(60)` works in whole milliseconds, so it waits
17 ms (58.8 FPS) and `tick_busy_loop(60)` waits 16 ms (62.5 FPS). On a
60 Hz display either one shows a repeated or skipped frame every
0.4-0.9 s, which reads as a regular micro-stutter.

`FramePacer` instead advances a deadline by exactly 1/fps per frame. It
sleeps most of the way and spins for the last bit, because `time.sleep`
can overshoot by a fraction of a millisecond.

VSync is not used: on macOS it paced the same window at 60 Hz on one
display and 120 Hz on another (both report 60 Hz). The simulation
advances one step per frame, so the game would run at double speed.
"""

from __future__ import annotations

import time
from typing import Callable

# Sleep until this much before the deadline, then spin (seconds)
SPIN_MARGIN = 0.0015
# Further behind than this (a hitch, a level load) restarts the schedule
# instead of rushing several frames out to catch up (seconds)
MAX_LAG = 0.05


class FramePacer:
    def __init__(
        self,
        fps: float = 60.0,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.period = 1.0 / fps
        self._clock = clock
        self._sleep = sleep
        self._deadline: float | None = None
        self._last: float | None = None

    def tick(self) -> float:
        """Wait for the next frame deadline; return seconds since the last tick."""
        now = self._clock()
        if self._deadline is None:
            self._deadline = now
        else:
            self._deadline += self.period
            if now > self._deadline + MAX_LAG:
                self._deadline = now
            else:
                if self._deadline - now > SPIN_MARGIN:
                    self._sleep(self._deadline - now - SPIN_MARGIN)
                while self._clock() < self._deadline:
                    pass
        now = self._clock()
        dt = 0.0 if self._last is None else now - self._last
        self._last = now
        return dt
