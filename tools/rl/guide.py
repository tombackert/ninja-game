"""The guide: the planner's next move from states around a stretch's route.

The route of a stretch is planned once, frame-exact from its start. A player
who dodges, waits or slips is off it, and a frame-exact plan does not carry
over to a state a pixel or a frame away. Planning again from there costs the
planner milliseconds to seconds, too slow for a step of training (the
simulation takes microseconds a frame).

So the planning is done ahead, once per stretch (cached in tools/rl/cache/):
the planner plans in the agent's own decisions (a move held for 4 or 8
frames, jump and dash pressed on the first frame, no dash wall climb) from
many states around the route: the route's own states at every decision, and
from each a few that a player gets into by leaving it (a few random moves:
standing, turning back, jumping, dashing). Every state along each plan is
stored with that frame's input and the waypoint it heads for (one per
rounding of a state the planner tells apart). The route action asks it every
frame for the input of the nearest state it has seen (same waypoint, ground,
wall, jumps left and dash; position and speed within RADIUS): off the route
it still knows the way on.

Flame jets burn on a beat, and the way past one depends on where in its beat
a player arrives. Near a jet (NEAR px from its nozzle) the guide also holds
plans made with the beat (the planner's `hazard`), one set per BEAT frames of
it, from the route's states there (and a state off each) at every beat:
there the route action follows the plan made nearest to where in the beat
the player is (the beat's difference counts in the distance, MARGIN frames
of it fit), as a player who has watched the jet a cycle times the way past it.
Only beats in which the route, arriving then, runs into the burning jet get
plans of their own (`Flames.burns`); in the others the route's way is fine.

Rounds of refinement (tools/rl/segment_env.py, stretch_guide) then plan from
the states the route action met but the guide did not know. Most of them are
a few pixels off the route: their plans end where they reach it (an anchor,
see _Reach), which costs a tenth of planning on to the waypoint. A plan may
not end on another such plan: answers near the end of one plan and the
middle of another can go round in a loop.

The lookup searches only the states in the 3 x 3 cells of RADIUS px around
the player's position, which gives the same answer as a search of all.
"""

from __future__ import annotations

import contextlib
import json
import multiprocessing as mp
import os
import random

import numpy as np

from tools.worlds import physics as ph
from tools.worlds.planner import FieldGoal, _key, dash_climb_press, plan_segment

DECISION = 4  # frames per agent decision
DURATIONS = (4, 8)  # the planner's moves: one or two decisions
VERSION = 7
BEAT = 10  # frames of a flame jet's beat whose plans are searched together
NEAR = 8 * 16  # px from a jet's nozzle within which the beat counts
MARGIN = 2  # frames a flame counts as burning before and after it does
TIME = 3.0  # px per frame of beat difference, in the lookup's distance (MARGIN frames fit in RADIUS)
TIMED_BUDGET = {"weight": 3.0, "max_expand": 6000, "field": True, "wait": True, "water_key": True}
MISS_EXPAND = 1500  # node budget of a plan from a state the guide did not know (many lead nowhere)
TIMED_STOP = False  # plans made with the beat end at an anchor too (out of the flames' reach)
RADIUS = 6.0  # px: how far from a state the guide has seen it still answers
SPEED = 8.0  # px per (px per frame) of speed difference, in that distance
PERTURB = 3  # states off the route per decision of the route
PERTURB_MOVES = 6  # random decisions (at most) that lead off it
BUDGET = {"weight": 3.0, "max_expand": 3000, "field": True, "wait": True, "water_key": True}
MISS_EXPAND = 1500  # node budget of a plan from a state the guide did not know (many lead nowhere)
MOVES = [(0, False, False), (-1, False, False), (1, False, False), (0, True, False)]
MOVES += [(-1, True, False), (1, True, False), (-1, False, True), (1, False, True)]


def key(s: tuple, down: bool, wp: int) -> tuple:
    """The guide's key: the planner's state key and the waypoint headed for."""
    return _key(s, down) + (wp,)


KEY_LEN = len(key(ph.spawn_state(0, 0), True, 0))  # of an untimed key (a timed one adds the beat)


def decision(s: tuple, down: bool, move: tuple, solids, kill_y) -> tuple | None:
    """One decision of `move` (jump and dash on its first frame), as the
    environment plays it; None if the player dies."""
    m, jump, dash = move
    if jump and dash_climb_press(s, dash, solids):
        jump = False
    for i in range(DECISION):
        s, down, dead = ph.apply_frame(s, m, jump and i == 0, dash and i == 0, solids)
        if dead or (kill_y is not None and s[ph.Y] > kill_y):
            return None
    return s, down


class Flames:
    """The flame jets of a level, as plain data (sent to the planning
    processes): their deadly boxes and beats."""

    def __init__(self, jets: list):
        self.jets = jets  # [(boxes [(x, y, w, h)], period, on, phase, nozzle x, nozzle y)]

    @classmethod
    def from_hazards(cls, hz) -> "Flames":
        from scripts.hazards import flame_box

        jets = []
        for jet in getattr(hz, "jets", None) or []:
            boxes = [tuple(flame_box(c, jet.facing, hz.ts)) for c in jet.cells]
            cx, cy = (jet.pos[0] + 0.5) * hz.ts, (jet.pos[1] + 0.5) * hz.ts
            jets.append((boxes, jet.period, jet.on, jet.phase, cx, cy))
        return cls(jets)

    def near(self, s: tuple) -> int | None:
        """The jet whose nozzle is nearest the player in `s`, if within NEAR."""
        x, y = s[ph.X] + ph.PW / 2, s[ph.Y] + ph.PH / 2
        best, best_d = None, NEAR * NEAR
        for i, (_b, _p, _o, _ph, cx, cy) in enumerate(self.jets):
            d = (cx - x) ** 2 + (cy - y) ** 2
            if d <= best_d:
                best, best_d = i, d
        return best

    def beat(self, jet: int, tick: int) -> int:
        """Where in its beat `jet` is at `tick` (0 .. period - 1)."""
        _b, period, _on, phase, _x, _y = self.jets[jet]
        return (tick + phase) % period

    def period(self, jet: int) -> int:
        return self.jets[jet][1]

    def tick_for(self, jet: int, beat: int) -> int:
        """A tick in the middle of `beat` of `jet`."""
        _b, period, _on, phase, _x, _y = self.jets[jet]
        return (beat * BEAT + BEAT // 2 - phase) % period

    def beats(self, jet: int) -> int:
        return -(-self.jets[jet][1] // BEAT)

    def burns(self, states: list, f: int, tick: int, horizon: int = 120) -> bool:
        """Whether the states from `f` on, the one at `f` at `tick`, run into
        a burning jet before they are out of every jet's reach (at most
        `horizon` frames)."""
        for k in range(1, min(horizon, len(states) - f)):
            st = states[f + k]
            if self.near(st) is None:
                return False
            if self.lethal(st, tick + k):
                return True
        return False

    def lethal(self, s: tuple, tick: int) -> bool:
        x0, y0 = int(s[ph.X]), int(s[ph.Y])
        x1, y1 = x0 + ph.PW, y0 + ph.PH
        for boxes, period, on, phase, _x, _y in self.jets:
            t = (tick + phase) % period
            if MARGIN <= t - on < period - on - MARGIN:
                continue  # out, with the margin on both sides
            for bx, by, bw, bh in boxes:
                if bx < x1 and x0 < bx + bw and by < y1 and y0 < by + bh:
                    return True
        return False


def _label(table: dict, s: tuple, down: bool, wp: int, frames: list, solids, flames=None, tick=0) -> tuple:
    """Store the input of every frame of `frames`, played from `s`: the plan
    is in decisions, but the agent's decisions need not fall on its grid. A
    plan made with the beat (`flames`, starting at `tick`) is stored with the
    beat of each state near a jet (states away from jets are left out), the
    jet's index and its period. Returns the state the plan ends in and the
    keys of an untimed plan's states."""
    keys = []
    for move in frames:
        if flames is None:
            keys.append(key(s, down, wp))
            table.setdefault(keys[-1], (s, down, wp, move, None))
        else:
            jet = flames.near(s)
            if jet is not None:
                b = flames.beat(jet, tick)
                table.setdefault(key(s, down, wp) + (jet, b), (s, down, wp, move, (jet, b)))
        s, down, _dead = ph.apply_frame(s, *move, solids)
        tick += 1
    return s, down, keys


class _Reach(FieldGoal):
    """The waypoint a plan heads for, or an anchor: a state of the route or
    of a plan that reached the waypoint (`anchors`: their guide keys), from
    where the guide knows a whole way on, so planning further adds nothing.
    A plan made with the beat stops only at an anchor out of the flames'
    reach, where the way on does not depend on the beat. A plan that ended at
    an anchor is no anchor itself: chains of such plans would add up the
    guide's rounding into loops."""

    def __init__(self, goal: FieldGoal, wp: int, anchors, flames=None):
        self.wp = goal.wp
        self.field = goal.field
        self.index = wp
        self.anchors = anchors
        self.flames = flames

    def contains(self, s: tuple, down: bool) -> bool:
        if self.wp.contains(s, down):
            return True
        if not any(key(s, down, self.index) in a for a in self.anchors):
            return False
        return self.flames is None or self.flames.near(s) is None


STATS = {"plans": 0, "ok": 0, "nodes": 0}  # of the last plan_from call


def _plan(
    table: dict,
    s: tuple,
    down: bool,
    wp: int,
    solids,
    waypoints,
    flames=None,
    tick=0,
    anchors=(),
    stats=None,
    stop: bool = True,
    max_expand: int | None = None,
) -> None:
    """Plan from `s` to waypoint `wp` (or, if `stop`, an anchor) and label the
    way. The states of a plan that reached the waypoint join `anchors[-1]`."""
    hazard = None if flames is None else (lambda t, st: flames.lethal(st, tick + t))
    budget = dict(BUDGET if flames is None else TIMED_BUDGET)
    if max_expand is not None:
        budget["max_expand"] = max_expand
    goal = waypoints[wp]
    if budget.pop("field", False) and anchors and stop and (flames is None or TIMED_STOP):
        goal = _Reach(FieldGoal(goal, solids), wp, anchors, flames)
    else:
        budget["field"] = True
    res = plan_segment(
        s,
        goal,
        solids,
        kill_y=solids.kill_y,
        start_down=down,
        no_dash_climb=True,
        durations=DURATIONS,
        hazard=hazard,
        **budget,
    )
    if stats is not None:
        stats["plans"] += 1
        stats["ok"] += res.ok
        stats["nodes"] += res.expanded
    if res.ok:
        end, end_down, keys = _label(table, s, down, wp, res.frames, solids, flames, tick)
        if anchors and waypoints[wp].contains(end, end_down):
            anchors[-1].update(keys)


def _plans(job: tuple) -> tuple[dict, dict, set]:
    """Plans from the states around the route's decisions in `seeds` (or,
    with `perturb` 0, from those states themselves). With `flames`, a seed
    carries the tick it is at, and the plans are made with the beat. A plan
    ends at an anchor (`known`, or one of its own plans) if `stop`. Returns
    the labels, counts and the new anchors."""
    solids, waypoints, seeds, seed, perturb, flames, known, stop, max_expand = job
    if solids is None:  # a worker of `planners`
        solids, waypoints = _WORLD["solids"], _WORLD["waypoints"]
    rng = random.Random(seed)
    kill_y = solids.kill_y
    table: dict = {}
    stats = {"plans": 0, "ok": 0, "nodes": 0}
    anchors = (known, set()) if known is not None else ()
    known = known or frozenset()
    for s0, down0, wp0, tick0 in seeds:
        if not perturb:
            _plan(table, s0, down0, wp0, solids, waypoints, flames, tick0, anchors, stats, stop, max_expand)
            continue
        for _ in range(perturb):
            s, down, wp, tick = s0, down0, wp0, tick0
            for _ in range(rng.randint(1, PERTURB_MOVES)):
                nxt = decision(s, down, rng.choice(MOVES), solids, kill_y)
                if nxt is None:
                    break
                s, down = nxt
                tick += DECISION
                while wp < len(waypoints) and waypoints[wp].contains(s, down):
                    wp += 1
            else:
                k = key(s, down, wp)
                if wp >= len(waypoints) or (flames is None and (k in table or k in known)):
                    continue
                _plan(table, s, down, wp, solids, waypoints, flames, tick, anchors, stats, stop, max_expand)
    return table, stats, anchors[1] if anchors else set()


_WORLD: dict = {}  # the terrain and waypoints of `planners` (in its workers too)
JOBS_PER_PROC = 4


def _init_world(solids, waypoints) -> None:
    _WORLD.update(solids=solids, waypoints=waypoints)


@contextlib.contextmanager
def planners(solids, waypoints: list, procs: int = 0):
    """One pool of planning processes for a whole build: they get the
    terrain and waypoints once (plan_from with the same ones uses it)."""
    procs = procs or (os.cpu_count() or 1)
    with mp.get_context("spawn").Pool(procs, initializer=_init_world, initargs=(solids, waypoints)) as pool:
        _WORLD.update(solids=solids, waypoints=waypoints, pool=pool)
        try:
            yield pool
        finally:
            _WORLD.clear()


def plan_from(
    solids,
    waypoints: list,
    starts: list,
    perturb: int = 0,
    procs: int = 0,
    flames: Flames | None = None,
    anchors: set | None = None,
    stop: bool = True,
    max_expand: int | None = None,
) -> dict:
    """Plans from `starts` [(state, down, waypoint index, tick)] (or from
    `perturb` states off each), in `procs` processes; with `flames`, made with
    their beat. With `anchors` (guide keys, see _Reach), the states of the
    plans that reached their waypoint are added to it, and (`stop`) a plan
    ends at the first anchor it reaches. `max_expand`: the node budget per
    plan, if not the default's. Counts in STATS."""
    procs = procs or (os.cpu_count() or 1)
    known = frozenset(anchors) if anchors is not None else None
    stop = stop and anchors is not None
    world = _WORLD.get("pool") is not None and _WORLD["solids"] is solids and _WORLD["waypoints"] is waypoints
    # Small jobs, several per process: plans differ a lot in cost
    n = max(1, min(len(starts), procs * JOBS_PER_PROC if world else procs))
    jobs = [(None, None, starts[i::n], i, perturb, flames, known, stop, max_expand) for i in range(n) if starts[i::n]]
    if world:
        parts = _WORLD["pool"].map(_plans, jobs, chunksize=1)
    else:
        jobs = [(solids, waypoints) + j[2:] for j in jobs]
        if len(jobs) > 1:
            with mp.get_context("spawn").Pool(len(jobs)) as pool:
                parts = pool.map(_plans, jobs)
        else:
            parts = [_plans(j) for j in jobs]
    table: dict = {}
    STATS.update(plans=0, ok=0, nodes=0)
    for part, stats, new in parts:
        for k, v in part.items():
            table.setdefault(k, v)
        for k in STATS:
            STATS[k] += stats[k]
        if anchors is not None:
            anchors.update(new)
    return table


def build(
    solids,
    waypoints: list,
    start: tuple,
    route_frames: list,
    wp_frames: list,
    flames: Flames | None = None,
    procs: int = 0,
    log=print,
    anchors: set | None = None,
    spine: set | None = None,
) -> dict:
    """The guide of a stretch: `route_frames` played from `start` reach the
    stretch's waypoints at `wp_frames`. The route's own decisions come first
    (a key seen twice keeps its first move). `anchors` (a set, filled here:
    the route's states and those of plans that reached their waypoint) lets
    later plans end where the guide knows a whole way on (see _Reach).
    `spine` (a set) gets the keys of the route's own states."""
    anchors = set() if anchors is None else anchors
    table: dict = {}
    states = [(start, True)]  # before each frame of the route
    for move in route_frames:
        s, down, _dead = ph.apply_frame(states[-1][0], *move, solids)
        states.append((s, down))
    route = [st for st, _d in states]
    seeds, timed = [], []
    skipped = 0
    begin = 0
    for wp, end in enumerate(wp_frames):
        for f in range(begin, end):
            s, down = states[f]
            table.setdefault(key(s, down, wp), (s, down, wp, route_frames[f], None))
            if (f - begin) % DECISION == 0:
                seeds.append((s, down, wp, 0))
                jet = flames.near(s) if flames is not None else None
                if jet is not None and (f - begin) % (2 * DECISION) == 0:
                    for b in range(flames.beats(jet)):
                        tick = flames.tick_for(jet, b)
                        # only where the route, arriving in this beat, burns
                        if any(flames.burns(route, f, tick + dt) for dt in (-BEAT // 2, 0, BEAT // 2 - 1)):
                            timed.append((s, down, wp, tick))
                        else:
                            skipped += 1
        begin = end
    anchors.update(table)
    if spine is not None:
        spine.update(table)
    # Whole plans from off the route: ways round it, not only back onto it
    for k, v in plan_from(solids, waypoints, seeds, PERTURB, procs, anchors=anchors, stop=False).items():
        table.setdefault(k, v)
    if timed:
        log(
            f"[guide] {len(table):,} states; planning past the flames from {len(timed):,} states and beats"
            f" ({skipped:,} where the route does not burn left out)"
        )
        for perturb in (0, 1):
            for k, v in plan_from(solids, waypoints, timed, perturb, procs, flames, anchors).items():
                table.setdefault(k, v)
    return table


class Guide:
    """The stored states, grouped for a nearest-neighbour lookup. A state by a
    flame (`beat` (jet, where in its beat)) is grouped by the BEAT frames of
    the beat it is in, and the lookup also weighs the beat's difference."""

    def __init__(self, rows: list, flames: Flames | None = None):
        groups: dict = {}
        for st, down, wp, move, beat in rows:
            groups.setdefault(self._group(st, down, wp, beat), []).append((st, move, beat))
        self.groups = {}
        for g, items in groups.items():
            points = np.array([self._point(st) for st, _m, _b in items], np.float32)
            # The states by RADIUS-sized cells of their position: the nearest
            # one within RADIUS is in the 3 x 3 cells around a state
            cells: dict = {}
            for i, (x, y) in enumerate(zip((points[:, 0] // RADIUS).astype(int), (points[:, 1] // RADIUS).astype(int))):
                cells.setdefault((x, y), []).append(i)
            self.groups[g] = (
                points,
                [m for _st, m, _b in items],
                np.array([b[1] if b is not None else 0 for _st, _m, b in items], np.float32),
                {c: np.array(ix, np.int64) for c, ix in cells.items()},
            )
        self.rows = rows
        self.flames = flames

    @staticmethod
    def _near(group: tuple, q: np.ndarray):
        """The indices of the group's states in the 3 x 3 cells around `q`."""
        cells = group[3]
        cx, cy = int(q[0] // RADIUS), int(q[1] // RADIUS)
        parts = [cells[c] for c in ((cx + i, cy + j) for i in (-1, 0, 1) for j in (-1, 0, 1)) if c in cells]
        if not parts:
            return None
        return np.sort(np.concatenate(parts)) if len(parts) > 1 else parts[0]

    def __len__(self) -> int:
        return len(self.rows)

    @staticmethod
    def _group(s: tuple, down: bool, wp: int, beat) -> tuple:
        window = None if beat is None else (beat[0], beat[1] // BEAT)
        return (wp, bool(down), bool(s[ph.WALL]), s[ph.JUMPS], s[ph.DASH] != 0, window)

    @staticmethod
    def _point(s: tuple) -> tuple:
        return (s[ph.X], s[ph.Y], SPEED * s[ph.VX], SPEED * s[ph.VY])

    def beat(self, s: tuple, tick: int):
        """(jet, where in its beat) of the jet the player in `s` is near, or None."""
        if self.flames is None:
            return None
        jet = self.flames.near(s)
        return None if jet is None else (jet, self.flames.beat(jet, tick))

    def move(self, s: tuple, down: bool, wp: int, beat=None) -> tuple | None:
        """The input of the nearest state the guide has seen: of a plan made
        with the beat, if `beat` is given (None if there is none near)."""
        q = np.array(self._point(s), np.float32)
        if beat is None:
            group = self.groups.get(self._group(s, down, wp, None))
            ix = None if group is None else self._near(group, q)
            if ix is None:
                return None
            d = ((group[0][ix] - q) ** 2).sum(1)
            i = int(d.argmin())
            return group[1][ix[i]] if d[i] <= RADIUS * RADIUS else None
        jet, t = beat
        period = self.flames.period(jet)
        windows = -(-period // BEAT)
        best, best_d = None, RADIUS * RADIUS
        for w in {(t // BEAT + k) % windows for k in (-1, 0, 1)}:
            group = self.groups.get(self._group(s, down, wp, (jet, w * BEAT)))
            ix = None if group is None else self._near(group, q)
            if ix is None:
                continue
            points, moves, beats, _cells = group
            dt = np.abs(beats[ix] - t)
            dt = np.minimum(dt, period - dt)
            d = ((points[ix] - q) ** 2).sum(1) + (TIME * dt) ** 2
            i = int(d.argmin())
            if d[i] <= best_d:
                best, best_d = moves[ix[i]], d[i]
        return best


def save(path: str, cache_key: str, table: dict, flames: Flames | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = [
        [list(st), bool(down), wp, [m, int(j), int(d)], None if b is None else list(b)]
        for st, down, wp, (m, j, d), b in table.values()
    ]
    jets = [] if flames is None else flames.jets
    with open(path, "w") as f:
        json.dump({"key": cache_key, "version": VERSION, "rows": rows, "flames": jets}, f)


def load(path: str, cache_key: str) -> Guide | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get("key") != cache_key or data.get("version") != VERSION:
        return None
    rows = [
        (tuple(st), down, wp, (m, bool(j), bool(d)), None if b is None else tuple(b))
        for st, down, wp, (m, j, d), b in data["rows"]
    ]
    jets = [([tuple(b) for b in boxes], *rest) for boxes, *rest in data["flames"]]
    return Guide(rows, Flames(jets) if jets else None)
