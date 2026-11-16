"""Shortcut checker: ways past a level's design that are shorter than its route.

docs/level-building-process-brainstorm.md, 3.3. Three probes, from cheap to
expensive. Each finding is **proven** (a way was found, with its time and
place), **refuted** (the search ran out of states: within its moves there is
none) or **not proven** (its node budget ran out first).

1. **Climb scan** (static, milliseconds). With the dash wall climb (kept in
   the game, decision D1 = A) a player climbs any sheer wall: a face of rock
   with open air beside it all the way up and nothing overhanging the air at
   its top. The scan lists each such wall at least TRICK_ROWS tall whose air
   is near the route early on and whose top is near it much later: climbing
   it would save at least MIN_GAIN frames, counting CLIMB_FRAMES per row. Each
   one is then probed: the planner, with the game's full physics, from the
   route's state where it passes the wall's foot to where it passes its top.
2. **Skip probes** (about 25 CPU minutes per level: two probes of up to 30,000 nodes per waypoint). From the route's
   arrival at waypoint i straight to waypoint i+2 and i+3, with the skipped
   waypoints' boxes (a tile wider) walled off and SKIP_NODES nodes: a way that
   is shorter than the designed one by SHORTER and MIN_GAIN frames is proven.
3. **Obstacle probes**, for the obstacles a level file declares
   (`Level.obstacle`): the designed route's trail between the waypoints
   before and after the obstacle is made deadly (a tile wider, not near
   either end), and so is everything outside the obstacle's box widened by
   its margin, so the search has to find another way within the box. The box
   keeps the search small enough to run out: refuted.

    python -m tools.worlds.shortcuts 27 28 31 [--jobs 7] [--json out.json] [--no-skip]

Nothing is written but the --json report.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field

from tools.worlds import physics as ph
from tools.worlds.planner import SegmentSearch, Waypoint

TS = ph.TS
TRICK_ROWS = 5  # a sheer wall this tall is only climbed with the dash wall climb (wall jumps alone: 4.5 rows)
NEAR = 3  # tiles: a place this close to the route's trail is on the route
MIN_GAIN = 90  # frames (1.5 s) a way round must save to count as a shortcut
SHORTER = 0.8  # ... and it must take at most this share of the designed time
CLIMB_FRAMES = 17  # frames per row the planner's dash climb takes (12 rows in 3.3 s)
SKIP_NODES = 30000
CLIMB_NODES = 15000
OBSTACLE_NODES = 60000
PROBE = {"weight": 5.0, "field": True, "water_key": True, "wait": True}  # the route's fixed search

PROVEN, REFUTED, NOT_PROVEN = "proven", "refuted", "not proven"


@dataclass
class Finding:
    probe: str  # "climb", "skip" or "obstacle"
    label: str
    verdict: str
    where: tuple = ()  # tile
    designed_s: float | None = None  # the route's time for the stretch
    found_s: float | None = None  # the way found
    nodes: int = 0
    detail: str = ""
    seconds: float = 0.0

    @property
    def saved_s(self) -> float | None:
        if self.designed_s is None or self.found_s is None:
            return None
        return round(self.designed_s - self.found_s, 1)


# --- a level and its route ------------------------------------------------------------------


@dataclass
class Route:
    level: int
    solids: object
    waypoints: list
    states: list  # state after every frame of the plan (states[0]: the spawn)
    arrivals: list  # frame of the arrival at each waypoint
    obstacles: list = field(default_factory=list)

    def tile(self, i: int) -> tuple:
        s = self.states[i]
        return int((s[ph.X] + ph.PW / 2) // TS), int((s[ph.Y] + ph.PH / 2) // TS)


_ROUTES: dict = {}


def load(level: int) -> Route:
    """A level built from its file, with its saved plan played in the replica (cached per process)."""
    if level in _ROUTES:
        return _ROUTES[level]
    from tools.worlds.build import build_level
    from tools.worlds.route import load_plan

    lv = build_level(level)
    solids = lv.solids()
    plan = load_plan(level)
    s = ph.spawn_state(*plan["spawn"])
    states = [s]
    for m, j, d in plan["frame_list"]:
        s = ph.apply_frame(s, m, j, d, solids)[0]
        states.append(s)
    arrivals = [a + n for a, n in plan["segments"]]
    r = Route(level, solids, plan["waypoints"], states, arrivals, list(lv.obstacles))
    _ROUTES[level] = r
    return r


def from_level(lv, level: int | None = None) -> Route:
    """The Route of a builder.Level in memory, its route planned now."""
    from tools.worlds.route import plan_route

    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * TS, lv.spawn_tile[1] * TS)
    res = plan_route(solids, spawn, lv.route, solids.kill_y, verbose=False)
    if not res.ok:
        raise ValueError(f"the route fails at {lv.route[res.failed_at].label!r}")
    s = ph.spawn_state(*spawn)
    states = [s]
    for m, j, d in res.frames:
        s = ph.apply_frame(s, m, j, d, solids)[0]
        states.append(s)
    arrivals = [a + n for _label, a, n, _e in res.segments]
    return Route(
        level if level is not None else lv.map_id, solids, list(lv.route), states, arrivals, list(lv.obstacles)
    )


def _center_tile(s: tuple) -> tuple:
    return int((s[ph.X] + ph.PW / 2) // TS), int((s[ph.Y] + ph.PH / 2) // TS)


def tile_path(start, goal, solids, blocked_tiles=frozenset(), area=None) -> bool:
    """Whether open tiles connect the start's tile to the goal box at all: steps
    to the four neighbours, and diagonal ones past a corner with one of the two
    tiles beside it open. The hitbox (8 x 15 px) is smaller than a tile, so every
    way the player can take is such a path: none means no way (refuted)."""
    from collections import deque

    def free(t):
        if t in solids or t in blocked_tiles:
            return False
        return area is None or (area[0] <= t[0] <= area[2] and area[1] <= t[1] <= area[3])

    s0 = _center_tile(start)
    goal_tiles = {(x, y) for x in range(int(goal.x0), int(goal.x1) + 1) for y in range(int(goal.y0), int(goal.y1) + 1)}
    seen, todo = {s0}, deque([s0])
    while todo:
        x, y = todo.popleft()
        if (x, y) in goal_tiles:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            t = (x + dx, y + dy)
            if t in seen or not free(t):
                continue
            if dx and dy and not (free((x + dx, y)) or free((x, y + dy))):
                continue
            seen.add(t)
            todo.append(t)
    return False


def _search(start, goal, solids, blocked, nodes) -> tuple:
    """(verdict, frames or None, nodes spent) of one probe search."""
    search = SegmentSearch(
        start, goal, solids, kill_y=getattr(solids, "kill_y", None), max_expand=nodes, blocked=blocked, **PROBE
    )
    res = search.next_arrival()
    if res is not None:
        return PROVEN, res.frames, search.expanded
    return (REFUTED if search.exhausted else NOT_PROVEN), None, search.expanded


# --- 1. the climb scan -------------------------------------------------------------------------


def climbable_faces(solids, min_rows: int = TRICK_ROWS) -> list:
    """Sheer faces a player can climb with the dash wall climb and get over:
    (x, side, y_top, y_bottom): column x is rock from y_top to y_bottom with open
    air in column x + side beside every row and two rows over the top, and the
    top (x, y_top - 1) open to stand on."""
    cols: dict = {}
    for x, y in solids:
        cols.setdefault(x, []).append(y)
    out = []

    def flush(x, side, run):
        if len(run) < min_rows:
            return
        top, bottom = run[0], run[-1]
        if (x, top - 1) not in solids and (x + side, top - 1) not in solids and (x + side, top - 2) not in solids:
            out.append((x, side, top, bottom))

    for x, ys in cols.items():
        for side in (-1, 1):
            run: list = []
            for y in sorted(ys):
                if (x + side, y) in solids:  # no air beside this row: not a face
                    flush(x, side, run)
                    run = []
                    continue
                if run and y != run[-1] + 1:
                    flush(x, side, run)
                    run = []
                run.append(y)
            flush(x, side, run)
    return out


def _near_frames(route: Route) -> dict:
    """{tile: (first frame, last frame)} the trail passes within NEAR tiles of it."""
    near: dict = {}
    for i in range(0, len(route.states), 2):
        cx, cy = route.tile(i)
        for dx in range(-NEAR, NEAR + 1):
            for dy in range(-NEAR, NEAR + 1):
                t = (cx + dx, cy + dy)
                a = near.get(t)
                near[t] = (i, i) if a is None else (a[0], i)
    return near


def climb_scan(route: Route) -> list[dict]:
    """Walls whose climb (with the trick) would skip MIN_GAIN frames or more of the route."""
    near = _near_frames(route)
    out = []
    for x, side, top, bottom in climbable_faces(route.solids):
        lane = x + side
        tops = [near[t][1] for t in ((x, top - 1), (x - side, top - 1), (x, top - 2)) if t in near]
        if not tops:
            continue
        late = max(tops)
        best = None
        for y in range(top + TRICK_ROWS - 1, bottom + 1):  # caught lower down: a climb wall jumps alone cannot make
            seen = near.get((lane, y))
            if seen is None:
                continue
            rows = y - top + 1
            gain = late - seen[0] - rows * CLIMB_FRAMES
            if best is None or gain > best[0]:
                best = (gain, seen[0], y, rows)
        if best is not None and best[0] >= MIN_GAIN:
            gain, at, y, rows = best
            out.append(
                {
                    "x": x,
                    "side": side,
                    "top": top,
                    "bottom": bottom,
                    "catch": y,
                    "rows": rows,
                    "from_frame": at,
                    "to_frame": late,
                    "gain": gain,
                }
            )
    out.sort(key=lambda c: -c["gain"])
    return out


def probe_climb(route: Route, c: dict, nodes: int = CLIMB_NODES) -> Finding:
    t0 = time.time()
    start = route.states[c["from_frame"]]
    tx, ty = route.tile(c["to_frame"])
    goal = Waypoint(tx - 1, ty - 1, tx + 1, ty + 1, label="the route further on")
    verdict, frames, spent = _search(start, goal, route.solids, None, nodes)
    designed = (c["to_frame"] - c["from_frame"]) / 60
    found = len(frames) / 60 if frames is not None else None
    if verdict == PROVEN and not _shorter(found, designed):
        verdict, detail = REFUTED, "the way found is no shorter than the route"
    else:
        detail = f"wall at column {c['x']} rows {c['top']}..{c['bottom']}, climbed {c['rows']} rows"
    return Finding(
        "climb",
        f"wall x={c['x']}",
        verdict,
        (c["x"], c["top"]),
        round(designed, 1),
        None if found is None else round(found, 1),
        spent,
        detail,
        round(time.time() - t0, 1),
    )


def _shorter(found: float | None, designed: float) -> bool:
    return found is not None and found <= designed * SHORTER and designed - found >= MIN_GAIN / 60


# --- 2. skip probes ------------------------------------------------------------------------------


def _box_blocker(boxes: list, goal) -> callable:
    def blocked(s):
        cx, cy = _center_tile(s)
        for x0, y0, x1, y1 in boxes:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return not goal.contains(s, True)
        return False

    return blocked


def probe_skip(route: Route, i: int, skip: int, nodes: int = SKIP_NODES) -> Finding | None:
    """From the arrival at waypoint i straight to waypoint i + skip + 1, walled off
    from the skipped waypoints' boxes."""
    j = i + skip + 1
    if j >= len(route.waypoints):
        return None
    t0 = time.time()
    a = route.arrivals[i] if i >= 0 else 0
    start = route.states[a]
    goal = route.waypoints[j]
    skipped = route.waypoints[i + 1 : j]
    sx, sy = _center_tile(start)
    boxes = []
    for w in skipped:
        b = (int(w.x0) - 1, int(w.y0) - 1, int(w.x1) + 1, int(w.y1) + 1)
        if b[0] <= sx <= b[2] and b[1] <= sy <= b[3]:
            b = (int(w.x0), int(w.y0), int(w.x1), int(w.y1))
            if b[0] <= sx <= b[2] and b[1] <= sy <= b[3]:
                return None  # the start is in the box it should skip
        boxes.append(b)
    goal_tiles = {(x, y) for x in range(int(goal.x0), int(goal.x1) + 1) for y in range(int(goal.y0), int(goal.y1) + 1)}
    walled = frozenset(
        (x, y) for b in boxes for x in range(b[0], b[2] + 1) for y in range(b[1], b[3] + 1) if (x, y) not in goal_tiles
    )
    if not tile_path(start, goal, route.solids, walled):
        verdict, frames, spent = REFUTED, None, 0
    else:
        verdict, frames, spent = _search(start, goal, route.solids, _box_blocker(boxes, goal), nodes)
    designed = (route.arrivals[j] - a) / 60
    found = len(frames) / 60 if frames is not None else None
    label = f"{route.waypoints[i].label if i >= 0 else 'spawn'} -> {goal.label}"
    detail = "past " + ", ".join(w.label for w in skipped)
    if verdict == PROVEN and not _shorter(found, designed):
        verdict, detail = "detour", detail + ": another way, not shorter"
    return Finding(
        "skip",
        label,
        verdict,
        _center_tile(start),
        round(designed, 1),
        None if found is None else round(found, 1),
        spent,
        detail,
        round(time.time() - t0, 1),
    )


# --- 3. obstacle probes ----------------------------------------------------------------------------


def probe_obstacle(route: Route, ob: dict, nodes: int = OBSTACLE_NODES) -> Finding:
    t0 = time.time()
    labels = [w.label for w in route.waypoints]
    i, j = labels.index(ob["before"]), labels.index(ob["after"])
    a, b = route.arrivals[i], route.arrivals[j]
    start, goal = route.states[a], route.waypoints[j]
    sx, sy = _center_tile(start)
    x0, y0, x1, y1 = ob["box"]
    mg = ob.get("margin", 6)
    area = ob.get("area") or (min(x0, sx) - mg, min(y0, sy) - mg, max(x1, goal.x1) + mg, max(y1, goal.y1) + mg)
    trail = set()
    for f in range(a, b + 1):
        cx, cy = route.tile(f)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    trail.add((cx + dx, cy + dy))
    trail = {t for t in trail if max(abs(t[0] - sx), abs(t[1] - sy)) > 2}

    def blocked(s):
        c = _center_tile(s)
        if not (area[0] <= c[0] <= area[2] and area[1] <= c[1] <= area[3]):
            return True
        return c in trail and not goal.contains(s, True)

    goal_tiles = {(x, y) for x in range(int(goal.x0), int(goal.x1) + 1) for y in range(int(goal.y0), int(goal.y1) + 1)}
    if not tile_path(start, goal, route.solids, frozenset(trail - goal_tiles), area):
        verdict, frames, spent = REFUTED, None, 0  # no open tiles round the blocked trail at all
    else:
        verdict, frames, spent = _search(start, goal, route.solids, blocked, nodes)
    designed = (b - a) / 60
    found = len(frames) / 60 if frames is not None else None
    detail = f"{ob['before']} -> {ob['after']}, the trail through tiles {ob['box']} blocked"
    return Finding(
        "obstacle",
        ob["label"],
        verdict,
        (x0, y0),
        round(designed, 1),
        None if found is None else round(found, 1),
        spent,
        detail,
        round(time.time() - t0, 1),
    )


# --- running it -------------------------------------------------------------------------------------


def jobs_for(level: int, skips: bool = True, climbs: bool = True) -> list[tuple]:
    route = load(level)
    out = []
    if climbs:
        out += [("climb", level, c) for c in climb_scan(route)]
    out += [("obstacle", level, ob) for ob in route.obstacles]
    if skips:
        out += [("skip", level, (i, k)) for i in range(-1, len(route.waypoints) - 2) for k in (1, 2)]
    return out


def run_job(job: tuple) -> tuple:
    kind, level, arg = job
    route = load(level)
    if kind == "climb":
        f = probe_climb(route, arg)
    elif kind == "obstacle":
        f = probe_obstacle(route, arg)
    else:
        f = probe_skip(route, *arg)
    return level, None if f is None else asdict(f)


def check(levels, jobs: int = 1, skips: bool = True, climbs: bool = True) -> dict:
    """{level: {"walls": climb scan rows, "findings": [Finding dicts]}}."""
    out = {n: {"walls": climb_scan(load(n)), "findings": []} for n in levels}
    work = [j for n in levels for j in jobs_for(n, skips, climbs)]
    if jobs > 1 and len(work) > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(min(jobs, len(work))) as pool:
            results = list(pool.map(run_job, work, chunksize=4))
    else:
        results = [run_job(j) for j in work]
    for level, f in results:
        if f is not None:
            out[level]["findings"].append(f)
    return out


def summary(res: dict) -> str:
    """One line: static walls | skips proven | obstacles refuted / not proven."""
    fs = res["findings"]
    climbs = [f for f in fs if f["probe"] == "climb"]
    skips = [f for f in fs if f["probe"] == "skip"]
    obs = [f for f in fs if f["probe"] == "obstacle"]

    def n(group, v):
        return sum(1 for f in group if f["verdict"] == v)

    return (
        f"climbs {len(res['walls'])} walls, {n(climbs, PROVEN)} proven | skip {n(skips, PROVEN)} of {len(skips)} "
        f"proven | obstacles {n(obs, REFUTED)} refuted, {n(obs, PROVEN)} proven, {n(obs, NOT_PROVEN)} not proven"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="+", type=int)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--no-skip", action="store_true")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    t0 = time.time()
    res = check(args.levels, args.jobs, skips=not args.no_skip)
    for n in args.levels:
        print(f"level {n}: {summary(res[n])}")
        for f in res[n]["findings"]:
            if f["verdict"] in (PROVEN, NOT_PROVEN) and f["probe"] != "skip" or f["verdict"] == PROVEN:
                saved = "" if f["found_s"] is None else f", {f['found_s']} s instead of {f['designed_s']} s"
                print(f"  {f['probe']:8s} {f['verdict']:10s} {f['label']}{saved} ({f['detail']})")
    print(f"shortcut check in {time.time() - t0:.0f} s")
    if args.json:
        with open(args.json, "w") as f:
            json.dump({str(k): v for k, v in res.items()}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
