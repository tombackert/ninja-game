"""FramePacer keeps an exact frame rate (no whole-millisecond rounding)."""

from scripts.frame_pacer import FramePacer


class FakeTime:
    """Clock that advances on every read, and a sleep that overshoots."""

    def __init__(self, overshoot=0.0004):
        self.now = 100.0
        self.overshoot = overshoot

    def clock(self):
        self.now += 0.00001  # each read costs a little, so spinning terminates
        return self.now

    def sleep(self, s):
        self.now += s + self.overshoot


def _run(frames, work):
    t = FakeTime()
    pacer = FramePacer(60, clock=t.clock, sleep=t.sleep)
    stamps = []
    for i in range(frames):
        pacer.tick()
        stamps.append(t.now)
        t.now += work(i)
    return stamps


def test_average_rate_is_exactly_60():
    stamps = _run(601, lambda i: 0.005)
    assert abs((stamps[-1] - stamps[0]) / 600 - 1 / 60) < 1e-6


def test_each_frame_is_one_period_despite_sleep_overshoot():
    stamps = _run(120, lambda i: 0.005)
    intervals = [b - a for a, b in zip(stamps, stamps[1:])]
    assert max(abs(iv - 1 / 60) for iv in intervals) < 0.0001


def test_hitch_restarts_schedule_instead_of_rushing():
    # One 200 ms stall (e.g. a level load), then normal frames
    stamps = _run(10, lambda i: 0.2 if i == 3 else 0.005)
    after = [b - a for a, b in zip(stamps[4:], stamps[5:])]
    assert all(abs(iv - 1 / 60) < 0.0001 for iv in after)


def test_tick_returns_elapsed_seconds():
    t = FakeTime()
    pacer = FramePacer(60, clock=t.clock, sleep=t.sleep)
    assert pacer.tick() == 0.0
    dt = pacer.tick()
    assert abs(dt - 1 / 60) < 0.0001
