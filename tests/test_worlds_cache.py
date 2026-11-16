"""The exact caches of the level checks (tools/worlds/cache.py)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

from tools.worlds import cache as C  # noqa: E402
from tools.worlds import physics as ph  # noqa: E402
from tools.worlds import windows as W  # noqa: E402
from tools.worlds.planner import FieldGoal, Waypoint  # noqa: E402
from tools.worlds.route import plan_route  # noqa: E402


def _terrain(extra=()):
    """Two ledges with a 3-tile gap; far to the east an unrelated island; deep rock sets the kill line."""
    s = {(x, y) for x in range(0, 12) for y in (20, 21)}
    s |= {(x, y) for x in range(15, 30) for y in (20, 21)}
    s |= {(x, 18) for x in range(200, 205)}
    s |= {(100, 40)}
    s |= set(extra)
    return ph.Terrain(s)


GOAL = Waypoint(17, 19, 19, 19, ground=True, label="far side")


def test_a_probe_boxes_the_steps_and_the_fields_read():
    solids = _terrain()
    s = ph.spawn_state(5 * 16, 19 * 16)
    with C.Probe() as probe:
        for _ in range(30):
            s, _d, _x = ph.apply_frame(s, 1, False, False, solids)
    x0, y0, x1, y1 = probe.box()
    assert x0 <= 5 - C.MARGIN and x1 >= int(s[ph.X] // 16) + C.MARGIN
    assert y0 <= 19 - C.MARGIN <= y1
    with C.Probe() as probe:
        FieldGoal(GOAL, solids)
    assert probe.fields and probe.box()[0] < 17 < probe.box()[2]
    assert probe.box()[2] < 200  # the island is beyond the field's reach


def test_a_hit_needs_the_same_tiles_in_the_box(tmp_path):
    solids = _terrain()
    store = C.Store("t", "v1", str(tmp_path))
    store.put("k", solids, (10, 15, 20, 25), "value")
    assert store.get("k", solids) == "value"
    assert store.get("k", _terrain(extra=[(203, 10)])) == "value"  # outside the box
    assert store.get("k", _terrain(extra=[(13, 18)])) is None  # inside it
    assert store.get("k", _terrain(extra=[(50, 60)])) is None  # a lower kill line
    assert C.Store("t", "v2", str(tmp_path)).get("k", solids) is None  # other code
    assert store.hits == 2 and store.misses == 2


def test_a_cached_route_plans_the_same_and_survives_a_change_far_away(tmp_path):
    store = C.Store("route", "v", str(tmp_path))
    spawn = (5 * 16, 19 * 16)
    route = [GOAL, Waypoint(25, 19, 27, 19, ground=True, label="end")]
    fresh = plan_route(_terrain(), spawn, route, _terrain().kill_y, verbose=False)
    first = plan_route(_terrain(), spawn, route, _terrain().kill_y, verbose=False, cache=store)
    assert first.frames == fresh.frames and store.hits == 0
    again = plan_route(_terrain(extra=[(203, 10)]), spawn, route, _terrain().kill_y, verbose=False, cache=store)
    assert again.frames == fresh.frames and store.hits == 2
    near = _terrain(extra=[(13, 17)])  # a block over the gap
    changed = plan_route(near, spawn, route, near.kill_y, verbose=False, cache=store)
    assert changed.frames == plan_route(near, spawn, route, near.kill_y, verbose=False).frames
    assert store.misses >= 3


def test_cached_ratings_equal_fresh_ones(tmp_path):
    solids = _terrain()
    spawn = (8 * 16, 19 * 16)
    route = [GOAL]
    res = plan_route(solids, spawn, route, solids.kill_y, verbose=False)
    segs = [(a, n) for _l, a, n, _e in res.segments]
    fresh = W.analyse_route(solids, spawn, route, res.frames, segs)
    store = C.Store("element", "v", str(tmp_path))
    first = W.analyse_route(solids, spawn, route, res.frames, segs, cache=store)
    second = W.analyse_route(_terrain(extra=[(203, 10)]), spawn, route, res.frames, segs, cache=store)
    for a, b, c in zip(fresh, first, second):
        assert a.frames == b.frames == c.frames
        assert [w.width for w in a.windows] == [w.width for w in c.windows]
        assert a.fatal == c.fatal
    assert store.hits == len(fresh)
