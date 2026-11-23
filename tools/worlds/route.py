"""Plan a level's intended route with the physics replica.

Runs the planner waypoint by waypoint from the player spawn and returns
the frame-exact input plan (the real-game bot replays it). A waypoint the
planner cannot reach is reported with its label and position, which is how
the level design is iterated until every route segment is playable.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from tools.worlds import physics as ph
from tools.worlds.planner import SegmentResult, SegmentSearch, Waypoint, _arrival_key

PLANS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans")


@dataclass
class SegmentStat:
    label: str
    tries: list  # (try name, nodes spent, found) per try made, in order
    seconds: float
    arrival: int  # which of the segment's distinct arrivals the route goes on from (F5), from 0

    @property
    def expanded(self) -> int:
        return sum(n for _name, n, _ok in self.tries)

    @property
    def at_limit(self) -> bool:
        """A try ran out of its node budget before the one that found the way."""
        return any(not ok and n >= TRY_LIMITS[name] for name, n, ok in self.tries)


@dataclass
class RouteResult:
    ok: bool
    frames: list = field(default_factory=list)
    segments: list = field(default_factory=list)  # (label, start_frame, n_frames, expanded)
    failed_at: int | None = None
    end: tuple | None = None
    seconds: float = 0.0
    stats: list = field(default_factory=list)  # SegmentStat per planned segment

    @property
    def expanded(self) -> int:
        return sum(st.expanded for st in self.stats)

    def summary(self) -> str:
        used: dict = {}
        for st in self.stats:
            name = next((n for n, _e, ok in st.tries if ok), "none")
            used[name] = used.get(name, 0) + 1
        limit = sum(1 for st in self.stats if st.at_limit)
        later = sum(1 for st in self.stats if st.arrival)
        tries = ", ".join(f"{n} {k}" for n, k in used.items())
        return (
            f"{len(self.stats)} segments, {self.expanded:,} nodes ({tries}); {limit} with a try at its node limit, "
            f"{later} gone on from a later arrival"
        )


# Idle frames before the first input: the game steps once before the bot's
# first key event reaches it (and again after each reload), so a plan
# starts by standing still for a moment, as a player watching the fade-in.
LEAD_IN = 30

# The tries per segment (docs/level-building-process-brainstorm.md 3.2): the
# search the routes were first planned with comes first, so easy moves stay as
# they were; then the fixed search (F1 distance field, F2 water key, F3 wait
# for the dash, F4 safe arrival) at weight 5 and 2; the old weight-2 search is
# the last resort.
FIXES = {"field": True, "water_key": True, "wait": True, "safe": True}
TRIES = (
    ("plain w5", {"weight": 5.0, "max_expand": 20000}),
    ("field w5", {"weight": 5.0, "max_expand": 20000, **FIXES}),
    ("field w2", {"weight": 2.0, "max_expand": 120000, **FIXES}),
    ("plain w2", {"weight": 2.0, "max_expand": 120000}),
)
TRY_LIMITS = {name: kw["max_expand"] for name, kw in TRIES}
ARRIVALS = 4  # distinct arrivals per waypoint the next segment may start from (F5)


class _Segment:
    """The searches of one segment, kept so a later arrival can be asked for."""

    def __init__(self, start: tuple, wp: Waypoint, solids, kill_y: float, tries=TRIES):
        self.start, self.wp, self.solids, self.kill_y = start, wp, solids, kill_y
        self.tries = list(tries)
        self.k = 0  # current try
        self.search: SegmentSearch | None = None
        self.log: list = []  # (name, nodes, found)
        self.arrivals = 0
        self.seen: set = set()
        self.t = 0.0

    def next(self):
        """The next distinct arrival (a SegmentResult), or None."""
        t0 = time.time()
        try:
            while self.k < len(self.tries):
                name, kw = self.tries[self.k]
                if self.search is None:
                    self.search = SegmentSearch(self.start, self.wp, self.solids, kill_y=self.kill_y, **kw)
                    self.log.append([name, 0, False])
                res = self.search.next_arrival()
                self.log[-1][1] = self.search.expanded
                if res is None:  # this try is spent: the next one
                    self.k += 1
                    self.search = None
                    continue
                key = _arrival_key(res.end)
                if key in self.seen:  # an earlier try arrived alike
                    continue
                self.seen.add(key)
                self.log[-1][2] = True
                self.arrivals += 1
                return res
            return None
        finally:
            self.t += time.time() - t0

    def stat(self, arrival: int) -> SegmentStat:
        return SegmentStat(self.wp.label, [tuple(x) for x in self.log], round(self.t, 2), arrival)


class _Cached(_Segment):
    """A segment whose first arrival came from the cache (tools/worlds/cache.py):
    asked for another one, it searches afresh and passes over the first."""

    def __init__(self, start, wp, solids, kill_y, tries, log):
        super().__init__(start, wp, solids, kill_y, tries)
        self.log = [list(x) for x in log]
        self.arrivals = 1
        self._fresh = None

    def next(self):
        if self._fresh is None:
            self._fresh = _Segment(self.start, self.wp, self.solids, self.kill_y, self.tries)
            self._fresh.next()  # the cached arrival
        res = self._fresh.next()
        self.log, self.t = self._fresh.log, self._fresh.t
        if res is not None:
            self.arrivals += 1
        return res


def _first_arrival(s, wp, solids, kill_y, tries, cache):
    """The segment's search and its first arrival, from the cache when it holds them."""
    if cache is None:
        seg = _Segment(s, wp, solids, kill_y, tries)
        return seg, seg.next()
    from tools.worlds.cache import Probe, input_key

    key = input_key("segment", s, (wp.x0, wp.y0, wp.x1, wp.y1, wp.ground), kill_y, repr(tries))
    hit = cache.get(key, solids)
    if hit is not None:
        frames, end, expanded, log = hit
        seg = _Cached(s, wp, solids, kill_y, tries, log)
        return seg, SegmentResult(True, frames, end, expanded)
    seg = _Segment(s, wp, solids, kill_y, tries)
    with Probe() as probe:
        res = seg.next()
    if res is not None:
        cache.put(key, solids, probe.box(), (res.frames, res.end, res.expanded, [tuple(x) for x in seg.log]))
    return seg, res


def plan_route(
    solids: set, spawn_px: tuple, route: list[Waypoint], kill_y: float, verbose=True, tries=TRIES, cache=None
) -> RouteResult:
    """Inputs from the spawn through every waypoint of `route` in order. Each
    segment runs the `tries` until one reaches the waypoint; if the next segment
    cannot be planned from there, it is tried from up to ARRIVALS distinct
    arrivals at this waypoint (F5) before the route fails. `cache`: a
    tools.worlds.cache.Store for the segments' first arrivals."""
    t0 = time.time()
    s = ph.spawn_state(*spawn_px)
    frames: list = [(0, False, False)] * LEAD_IN
    for _ in range(LEAD_IN):
        s, _down, _dead = ph.step(s, 0, solids)
    segments, stats = [], []
    prev: _Segment | None = None  # the segment before, for another arrival
    i = 0
    while i < len(route):
        wp = route[i]
        seg, res = _first_arrival(s, wp, solids, kill_y, tries, cache)
        while res is None and prev is not None and prev.arrivals < ARRIVALS:
            # F5: go on from another arrival at the waypoint before
            alt = prev.next()
            if alt is None:
                break
            _label, start, _n, _exp = segments[-1]
            frames = frames[:start] + alt.frames
            segments[-1] = (prev.wp.label, start, len(alt.frames), alt.expanded)
            stats[-1] = prev.stat(prev.arrivals - 1)
            s = alt.end
            seg, res = _first_arrival(s, wp, solids, kill_y, tries, cache)
        if res is None:
            stats.append(seg.stat(0))
            if verbose:
                print(
                    f"  waypoint {i} '{wp.label}' {(wp.x0, wp.y0, wp.x1, wp.y1)} UNREACHED "
                    f"from px {(round(s[0]), round(s[1]))}"
                )
            return RouteResult(False, frames, segments, i, s, time.time() - t0, stats)
        segments.append((wp.label, len(frames), len(res.frames), res.expanded))
        stats.append(seg.stat(0))
        frames += res.frames
        s = res.end
        prev = seg
        i += 1
    return RouteResult(True, frames, segments, None, s, time.time() - t0, stats)


def save_plan(map_id: int, spawn_px: tuple, frames: list, route: list[Waypoint] = (), segments: list = ()) -> str:
    os.makedirs(PLANS_DIR, exist_ok=True)
    path = os.path.join(PLANS_DIR, f"{map_id}.json")
    # Run-length encoded: [frames, m, jump, dash]
    rle: list = []
    for m, j, d in frames:
        if rle and not j and not d and rle[-1][1] == m:
            rle[-1][0] += 1
        else:
            rle.append([1, m, int(j), int(d)])
    with open(path, "w") as f:
        json.dump(
            {
                "map": map_id,
                "spawn": list(spawn_px),
                "frames": len(frames),
                "inputs": rle,
                "route": [[w.x0, w.y0, w.x1, w.y1, w.ground, w.label] + ([True] if w.guide else []) for w in route],
                "segments": [[start, n] for _label, start, n, _exp in segments],
            },
            f,
        )
    return path


def load_plan(map_id: int) -> dict:
    with open(os.path.join(PLANS_DIR, f"{map_id}.json")) as f:
        data = json.load(f)
    frames = []
    for n, m, j, d in data["inputs"]:
        frames.append((m, bool(j), bool(d)))
        frames.extend([(m, False, False)] * (n - 1))
    data["frame_list"] = frames
    data["waypoints"] = [Waypoint(*w) for w in data.get("route", [])]
    return data
