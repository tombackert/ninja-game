"""The route planner's fixes F1-F5 (docs/level-building-process-brainstorm.md, 3.2)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

from tools.worlds import physics as ph  # noqa: E402
from tools.worlds import route  # noqa: E402
from tools.worlds.planner import (  # noqa: E402
    FieldGoal,
    SegmentResult,
    Waypoint,
    _key,
    can_land,
    distance_field,
    key_water,
    plan_segment,
)


def _standing(solids, tx, ty=19):
    s = ph.spawn_state(tx * 16, ty * 16 + 1)
    for _ in range(60):
        s, _down, _dead = ph.step(s, 0, solids)
    return s


def _floor(x0=-10, x1=60, y=20):
    return {(x, yy) for x in range(x0, x1) for yy in (y, y + 1)}


def _slab():
    """A floor with a slab two rows over it; the goal is on top of the slab."""
    solids = _floor()
    solids |= {(x, 17) for x in range(10, 30)}
    return ph.Terrain(solids), Waypoint(18, 16, 21, 16, ground=True)


def test_the_distance_field_goes_round_the_rock():
    solids, goal = _slab()
    field = distance_field(goal, solids)
    under = (20, 19)  # right under the goal, but the slab is in the way
    assert field[(20, 16)] == 0
    straight = 3 * 16 / 1.5  # three rows up
    assert field[under] > 10 * 16 > straight  # out from under the slab and back on top
    assert (20, 17) not in field  # rock


def test_the_field_heuristic_finds_the_way_out_from_under_a_slab():
    solids, goal = _slab()
    start = _standing(solids, 20)
    plain = plan_segment(start, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y)
    fixed = plan_segment(start, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y, field=True)
    assert not plain.ok and plain.expanded == 20000
    assert fixed.ok and fixed.expanded < 2000


def test_in_open_air_the_field_agrees_with_the_straight_line():
    solids = ph.Terrain(_floor())
    goal = Waypoint(30, 19, 31, 19, ground=True)
    fg = FieldGoal(goal, solids)
    s = _standing(solids, 10)
    assert fg.distance(s) == goal.distance(s)
    assert fg.ground and fg.label == ""


def test_the_water_key_is_the_old_key_until_breath_or_strokes_count():
    s = ph.spawn_state(100, 100)
    assert key_water(s, True) == _key(s, True)
    wet = s[: ph.BREATH] + (ph.BREATH_FRAMES - 70, 7)
    wetter = s[: ph.BREATH] + (ph.BREATH_FRAMES - 130, 5)
    assert _key(wet, False) != _key(wetter, False)
    assert key_water(wet, False) == key_water(wetter, False)  # same 3 s bucket, same 4-frame stroke bucket


def _gap():
    """Two ledges with a 5-tile void between: a dash is needed."""
    solids = {(x, y) for x in range(-10, 12) for y in (20, 21)}
    solids |= {(x, y) for x in range(17, 40) for y in (20, 21)}
    return ph.Terrain(solids), Waypoint(18, 19, 22, 19, ground=True)


def test_the_wait_macro_waits_for_the_dash():
    solids, goal = _gap()
    s = _standing(solids, 9)
    cooling = s[: ph.DASH] + (40,) + s[ph.DASH + 1 :]
    plain = plan_segment(cooling, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y)
    waits = plan_segment(cooling, goal, solids, weight=5.0, max_expand=20000, kill_y=solids.kill_y, wait=True)
    assert plain.ok and waits.ok
    assert waits.expanded * 5 < plain.expanded


def test_can_land_knows_a_doomed_fall_and_a_dash_that_saves_it():
    solids, _goal = _gap()
    falling = ph.spawn_state(13 * 16, 18 * 16)
    falling = falling[: ph.JUMPS] + (0,) + falling[ph.JUMPS + 1 :]
    assert not can_land(falling, solids)
    assert can_land(falling, solids, dash=True)
    assert can_land(_standing(solids, 5), solids)


def test_a_safe_arrival_is_preferred_to_a_doomed_one(monkeypatch):
    from tools.worlds import planner

    solids, _goal = _gap()
    box = Waypoint(12, 14, 16, 21)  # the air over the void
    s = _standing(solids, 9)
    first = plan_segment(s, box, solids, weight=5.0, max_expand=5000, kill_y=solids.kill_y)
    assert first.ok
    # say the first arrival is doomed: the search hands out another one first
    monkeypatch.setattr(planner, "can_land", lambda st, *_a, **_k: st != first.end)
    safe = plan_segment(s, box, solids, weight=5.0, max_expand=5000, kill_y=solids.kill_y, safe=True)
    assert safe.ok and safe.end != first.end
    # with no other way in, the doomed arrival comes once the search is spent
    monkeypatch.setattr(planner, "can_land", lambda *_a, **_k: False)
    spent = planner.SegmentSearch(s, box, solids, weight=5.0, max_expand=300, kill_y=solids.kill_y, safe=True)
    res = spent.next_arrival()
    assert res is not None and spent.hit_limit and res.end == first.end
    # ground waypoints are safe by definition
    ground = Waypoint(18, 19, 22, 19, ground=True)
    assert plan_segment(s, ground, solids, weight=5.0, max_expand=5000, kill_y=solids.kill_y, safe=True).ok


class _Stub:
    """A SegmentSearch stand-in: per (waypoint label, start x) the arrivals to hand out."""

    table: dict = {}

    def __init__(self, start, goal, solids, **kw):
        self._left = list(self.table.get((goal.label, start[ph.X]), []))
        self.expanded = 1
        self.hit_limit = False

    def next_arrival(self):
        if not self._left:
            return None
        x = self._left.pop(0)
        end = ph.spawn_state(x, 0)
        return SegmentResult(True, [(1, False, False)] * 3, end, 1)


def test_the_route_goes_on_from_a_later_arrival_when_the_next_segment_fails(monkeypatch):
    lead = ph.spawn_state(0, 0)
    for _ in range(route.LEAD_IN):
        lead, _d, _x = ph.step(lead, 0, ph.Terrain())
    a, b = Waypoint(0, 0, 0, 0, label="a"), Waypoint(0, 0, 0, 0, label="b")
    _Stub.table = {
        ("a", lead[ph.X]): [100.0, 200.0],  # two distinct arrivals at a
        ("b", 200.0): [300.0],  # b only from the second
    }
    monkeypatch.setattr(route, "SegmentSearch", _Stub)
    res = route.plan_route(ph.Terrain({(0, 50)}), (0, 0), [a, b], 10**6, verbose=False, tries=(("t", {}),))
    assert res.ok
    assert [st.arrival for st in res.stats] == [1, 0]
    assert res.end[ph.X] == 300.0
    assert len(res.frames) == route.LEAD_IN + 6


def test_the_route_fails_when_no_arrival_helps(monkeypatch):
    a, b = Waypoint(0, 0, 0, 0, label="a"), Waypoint(0, 0, 0, 0, label="b")
    lead = ph.spawn_state(0, 0)
    for _ in range(route.LEAD_IN):
        lead, _d, _x = ph.step(lead, 0, ph.Terrain())
    _Stub.table = {("a", lead[ph.X]): [100.0, 200.0]}
    monkeypatch.setattr(route, "SegmentSearch", _Stub)
    res = route.plan_route(ph.Terrain({(0, 50)}), (0, 0), [a, b], 10**6, verbose=False, tries=(("t", {}),))
    assert not res.ok and res.failed_at == 1


def test_the_tries_keep_the_old_search_first_and_last():
    names = [name for name, _kw in route.TRIES]
    assert names[0] == "plain w5" and names[-1] == "plain w2"
    assert all(route.TRIES[i][1].get("field") for i in (1, 2))
    assert not route.TRIES[0][1].get("field") and not route.TRIES[-1][1].get("field")


def test_a_real_route_reports_its_tries():
    solids, goal = _slab()
    res = route.plan_route(solids, (12 * 16, 19 * 16), [goal], solids.kill_y, verbose=False)
    assert res.ok
    (st,) = res.stats
    assert [name for name, _n, _ok in st.tries][:2] == ["plain w5", "field w5"]
    assert st.at_limit  # the old search ran out of nodes under the slab
    assert "field w5 1" in res.summary()
