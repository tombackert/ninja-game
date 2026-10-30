"""The benchmark's water run: tools/trailer_replays/25-best.json against its route plan."""

from tools.bench.metrics import METRICS
from tools.bench.session import WATER_LEVEL, load_run_class
from tools.worlds.route import load_plan


def _ticks(run, action):
    return {tick for tick, events in run.events.items() if action in events}


def test_run_rebuilds_every_jump_and_dash_of_the_plan():
    """A swim stroke `Run` drops leaves the player in the water, far from the flag."""
    run = load_run_class()(WATER_LEVEL)
    frames = load_plan(WATER_LEVEL)["frame_list"]
    # The game steps once before tick 0, so tick t plays frame t + 1
    assert _ticks(run, "jump") == {tick for tick, frame in enumerate(frames[1:]) if frame[1]}
    assert _ticks(run, "dash") == {tick for tick, frame in enumerate(frames[1:]) if frame[2]}


def test_water_metrics_stay_out_of_the_score():
    water = [m for m in METRICS if m.group == "water"]
    assert [m.key for m in water] == ["water.frame_p50_ms", "water.frame_p99_ms", "water.frames_over_budget"]
    assert not any(m.score for m in water)
