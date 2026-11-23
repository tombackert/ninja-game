"""Route planner: finds frame-exact inputs that carry the player along a route.

A route is a list of waypoint boxes (tile coordinates). Between two
waypoints a weighted best-first search over short input macros (hold a
direction for k frames, optionally starting with a jump and/or a dash)
runs the exact physics replica until the player's hitbox center lies in
the next box. The concatenated per-frame inputs are a plan the real game
reproduces exactly, since only inputs move the player.

Moving hazards (enemy bullets in flight) can be passed in as a hit test;
the real-game bot uses that to plan around shots.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field

from tools.worlds import physics as ph

TS = ph.TS


@dataclass
class Waypoint:
    """Target box in tile coordinates (inclusive), center of the hitbox must be inside."""

    x0: float
    y0: float
    x1: float
    y1: float
    ground: bool = False  # also require standing on the ground
    label: str = ""
    guide: bool = False  # only there so the planner gets through: not a stop of the level's design

    def contains(self, s: tuple, down: bool) -> bool:
        cx = s[ph.X] + ph.PW / 2
        cy = s[ph.Y] + ph.PH / 2
        inside = self.x0 * TS <= cx <= (self.x1 + 1) * TS and self.y0 * TS <= cy <= (self.y1 + 1) * TS
        return inside and (down or not self.ground)

    def distance(self, s: tuple) -> float:
        """Rough frames to the box: run at 1 px/frame, rise ~1.5, fall ~3."""
        cx = s[ph.X] + ph.PW / 2
        cy = s[ph.Y] + ph.PH / 2
        dx = max(self.x0 * TS - cx, 0, cx - (self.x1 + 1) * TS)
        up = max(cy - (self.y1 + 1) * TS, 0)
        down = max(self.y0 * TS - cy, 0)
        return dx + up / 1.5 + down / 3.0


@dataclass
class SegmentResult:
    ok: bool
    frames: list = field(default_factory=list)  # [(m, jump, dash), ...]
    end: tuple | None = None
    expanded: int = 0


def _key(s: tuple, down: bool) -> tuple:
    d = s[ph.DASH]
    ad = abs(d)
    dash_bucket = 0 if d == 0 else (ad if ad > 48 else 100 + ad // 16)
    return (
        round(s[ph.X]),
        round(s[ph.Y]),
        round(s[ph.VX] * 4),
        round(s[ph.VY] * 4),
        min(s[ph.AIR], 6),
        s[ph.JUMPS],
        s[ph.WALL],
        dash_bucket,
        s[ph.FLIP],
        s[ph.LASTM],
        s[ph.BREATH] // 60,
        s[ph.SWIM],
        down,
    )


def key_water(s: tuple, down: bool) -> tuple:
    """F2: `_key` with a coarser water part once breath or the swim cooldown
    are in play: breath in 3-second buckets, the swim cooldown in 4-frame ones,
    so the same place at the same speed is not a new state every second and
    after every stroke."""
    k = _key(s, down)
    if s[ph.BREATH] == ph.BREATH_FRAMES and s[ph.SWIM] == 0:
        return k
    return k[:10] + (s[ph.BREATH] // 180, s[ph.SWIM] // 4, down)


# --- F1: a heuristic that sees the walls ---------------------------------------

FIELD_MARGIN = 12  # tiles of open air the field reaches beyond the level's rock, sideways and up
FIELD_REACH = (48, 32)  # tiles the field reaches from its goal box, sideways and up/down: it reads only those
AIR_COST = {(1, 0): 16.0, (-1, 0): 16.0, (0, -1): 16 / 1.5, (0, 1): 16 / 3.0}  # frames per tile
SWIM_SPEED = {(1, 0): 0.7, (-1, 0): 0.7, (0, -1): 1.0, (0, 1): 0.8}  # px per frame, still water


def _water_cost(flow: int, move: tuple) -> float:
    """Frames to swim one tile in direction `move` through water of `flow`: the
    swim speed plus the current along the move (at least 0.1 px per frame)."""
    from scripts.constants import WATER_CURRENTS

    px, py = WATER_CURRENTS[flow]
    speed = SWIM_SPEED[move] + px * move[0] + py * move[1]
    return TS / max(speed, 0.1)


def _bounds(solids) -> tuple:
    cache = getattr(solids, "__dict__", None)
    if cache is not None and "_field_bounds" in cache:
        return cache["_field_bounds"]
    xs = [x for x, _ in solids]
    ys = [y for _, y in solids]
    b = (min(xs) - FIELD_MARGIN, max(xs) + FIELD_MARGIN, min(ys) - FIELD_MARGIN, max(ys) + 5)
    if cache is not None:
        cache["_field_bounds"] = b
    return b


PROBES: list = []  # active tools.worlds.cache.Probe objects: told the tile box each field reads


def field_bounds(goal: Waypoint, solids) -> tuple:
    """(x_lo, x_hi, y_lo, y_hi): the tiles a goal's distance field covers, its
    goal box widened by FIELD_REACH, within the level (and its open air)."""
    x_lo, x_hi, y_lo, y_hi = _bounds(solids)
    rx, ry = FIELD_REACH
    return (
        max(x_lo, int(goal.x0) - rx),
        min(x_hi, int(goal.x1) + rx),
        max(y_lo, int(goal.y0) - ry),
        min(y_hi, int(goal.y1) + ry),
    )


def distance_field(goal: Waypoint, solids) -> dict:
    """Frames from each open tile to the goal box, by a Dijkstra over the tiles
    that are not solid: air costs 16 frames a tile sideways, 10.7 up and 5.3
    down (the straight-line heuristic's speeds), water 16 over the swim speed
    with the tile's current along the move. It covers `field_bounds` (beyond
    them the heuristic is the straight line). Cached per goal box on the terrain."""
    x_lo, x_hi, y_lo, y_hi = field_bounds(goal, solids)
    for probe in PROBES:
        probe.read(x_lo, y_lo, x_hi, y_hi)
    cache = getattr(solids, "__dict__", None)
    store = None
    box = (goal.x0, goal.y0, goal.x1, goal.y1)
    if cache is not None:
        store = cache.setdefault("_fields", {})
        if box in store:
            return store[box]
    water = getattr(solids, "water", None) or {}
    dist: dict = {}
    pq = []
    for x in range(int(goal.x0), int(goal.x1) + 1):
        for y in range(int(goal.y0), int(goal.y1) + 1):
            if (x, y) not in solids:
                dist[(x, y)] = 0.0
                pq.append((0.0, x, y))
    heapq.heapify(pq)
    while pq:
        d, bx, by = heapq.heappop(pq)
        if d > dist.get((bx, by), 1e18):
            continue
        for move in AIR_COST:
            ax, ay = bx - move[0], by - move[1]  # A moves `move` into B
            if (ax, ay) in solids or not (x_lo <= ax <= x_hi and y_lo <= ay <= y_hi):
                continue
            flow = water.get((ax, ay))
            nd = d + (AIR_COST[move] if flow is None else _water_cost(flow, move))
            if nd < dist.get((ax, ay), 1e18):
                dist[(ax, ay)] = nd
                heapq.heappush(pq, (nd, ax, ay))
    if store is not None:
        store[box] = dist
    return dist


class FieldGoal:
    """A waypoint whose distance follows the air round the rock (F1): the larger of
    the straight line and the distance field less one tile (in open air the two
    agree)."""

    UNREACHABLE = 2000.0

    def __init__(self, wp: Waypoint, solids):
        self.wp = wp
        self.field = distance_field(wp, solids)

    def __getattr__(self, name):
        return getattr(self.wp, name)

    def contains(self, s: tuple, down: bool) -> bool:
        return self.wp.contains(s, down)

    def distance(self, s: tuple) -> float:
        d0 = self.wp.distance(s)
        f = self.field.get((int((s[ph.X] + ph.PW / 2) // TS), int((s[ph.Y] + ph.PH / 2) // TS)))
        if f is None:
            return d0 + self.UNREACHABLE
        return max(d0, f - TS)


# --- F4: arrivals that can still land ----------------------------------------------

REACT = 10  # frames until a correction takes effect


def can_land(s: tuple, solids, *, floor: float | None = None, frames: int = 240, dash: bool = False) -> bool:
    """Whether a player at `s` can still land somewhere: steer either way or not
    at all, jump once or not (after REACT frames, until then keep on), and with
    `dash` also dash once then. With `floor` (px), only a landing no lower than
    that counts. A swimmer still alive in the water at the end counts too: it
    can swim on. (windows.saved is this without the dash.)"""
    water = getattr(solids, "water", None)
    for m in (-1, 0, 1):
        for jump_at in (None, 0, 8, 16):
            for dash_now in (False, True) if dash else (False,):
                cur, at = s, jump_at
                dead = False
                for f in range(frames):
                    mm = m if f >= REACT else cur[ph.LASTM]
                    jump = at is not None and f >= REACT + at and ph.can_jump(cur, solids)
                    if jump:
                        at = None
                    cur, down, dead = ph.apply_frame(cur, mm, jump, dash_now and f == REACT, solids)
                    if dead:
                        break
                    if down:
                        if floor is None or cur[ph.Y] + ph.PH <= floor:
                            return True
                        dead = True
                        break
                if not dead and water and ph.water_at(cur[ph.X], cur[ph.Y], water)[0] is not None:
                    return True
    return False


# --- the dash wall climb ---------------------------------------------------------


def dash_climb_press(s: tuple, dash: bool, solids) -> bool:
    """Whether a jump pressed at `s` (with `dash` pressed in the same frame) is the
    dash wall climb: a wall jump while a dash is active, so the dash cancels the
    push-off (docs/level-building-findings.md, section 4). A dash pressed in the
    same frame is active from that frame's update on, so it counts too."""
    if not s[ph.WALL]:
        return False
    if abs(s[ph.DASH]) <= ph.DASH_MIN_ACTIVE_ABS and not (dash and s[ph.DASH] == 0):
        return False
    t = ph.press_jump(s, solids)
    return t is not s and t[ph.VY] == ph.WALL_JUMP_VERTICAL_VEL and t[ph.SWIM] == s[ph.SWIM]


def dash_climbs(start: tuple, frames: list, solids) -> int:
    """How many presses of a program are the dash wall climb."""
    n = 0
    s = start
    for m, j, d in frames:
        if j and dash_climb_press(s, d, solids):
            n += 1
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
    return n


def _arrival_key(s: tuple) -> tuple:
    """Arrivals this alike would fail the next segment alike (F5 keeps others)."""
    d = abs(s[ph.DASH])
    return (
        round(s[ph.X] / 4),
        round(s[ph.Y] / 4),
        0 if d == 0 else (1 if d > ph.DASH_MIN_ACTIVE_ABS else 2 + d // 16),
        s[ph.JUMPS],
        s[ph.WALL],
        min(s[ph.AIR], 6) > 4,
        round(s[ph.VY]),
    )


class SegmentSearch:
    """The best-first search of `plan_segment`, kept alive to hand out further
    distinct arrivals (F5): `next_arrival()` goes on from where the last one was
    found. `expanded` counts the nodes spent so far, `hit_limit` whether the node
    budget ran out."""

    def __init__(
        self,
        start: tuple,
        goal,
        solids: set,
        *,
        max_expand: int = 60000,
        weight: float = 2.0,
        durations: tuple = (1, 3, 8),
        allow_dash: bool = True,
        kill_y: float | None = None,
        start_down: bool = True,
        hazard=None,
        field: bool = False,
        wait: bool = False,
        water_key: bool = False,
        safe: bool = False,
        no_dash_climb: bool = False,
        blocked=None,
    ):
        if field and not isinstance(goal, FieldGoal):
            goal = FieldGoal(goal, solids)
        self.goal = goal
        self.expanded = 0
        self.hit_limit = False
        self.exhausted = False
        self._gen = self._run(
            start,
            goal,
            solids,
            max_expand,
            weight,
            durations,
            allow_dash,
            kill_y,
            start_down,
            hazard,
            wait,
            key_water if water_key else _key,
            safe and not getattr(goal, "ground", False),
            no_dash_climb,
            blocked,
        )

    def next_arrival(self) -> SegmentResult | None:
        return next(self._gen, None)

    def _run(
        self,
        start,
        goal,
        solids,
        max_expand,
        weight,
        durations,
        allow_dash,
        kill_y,
        start_down,
        hazard,
        wait,
        key,
        safe,
        no_dash_climb,
        blocked,
    ):
        if goal.contains(start, start_down):
            yield SegmentResult(True, [], start, 0)
            return
        durs = sorted(durations)
        counter = itertools.count()
        nodes = [(start, start_down, -1, None)]  # id -> (state, down, parent, action)
        heap = [(weight * goal.distance(start), next(counter), 0, 0)]
        seen = {key(start, start_down)}
        arrived: set = set()
        held: list = []  # arrivals that cannot land (F4): handed out only once the search is spent
        expanded = 0
        while heap and expanded < max_expand:
            _f, _t, g, nid = heapq.heappop(heap)
            s, down, _parent, _act = nodes[nid]
            expanded += 1
            self.expanded = expanded
            jumps = (False, True) if ph.can_jump(s, solids) else (False,)
            dashes = (False, True) if (allow_dash and s[ph.DASH] == 0) else (False,)
            ks = durs
            if wait and 0 < abs(s[ph.DASH]) <= ph.DASH_MIN_ACTIVE_ABS and abs(s[ph.DASH]) not in durs:
                ks = durs + [abs(s[ph.DASH])]  # F3: hold on until the dash is ready
            for m in (1, -1, 0):
                for jump in jumps:
                    for dash in dashes:
                        if no_dash_climb and jump and dash_climb_press(s, dash, solids):
                            continue
                        for k in ks:
                            cur = s
                            cur_down = down
                            frames = []
                            dead = False
                            reached = False
                            for i in range(k):
                                j = jump and i == 0
                                d = dash and i == 0
                                # Bullets move before the player within a step, but a dash
                                # pressed this frame already grants its i-frames
                                if hazard is not None and hazard(g + i, ph.press_dash(cur) if d else cur):
                                    dead = True
                                    break
                                cur, cur_down, dead = ph.apply_frame(cur, m, j, d, solids)
                                frames.append((m, j, d))
                                if dead or (kill_y is not None and cur[ph.Y] > kill_y):
                                    dead = True
                                    break
                                if blocked is not None and blocked(cur):
                                    dead = True
                                    break
                                if goal.contains(cur, cur_down):
                                    reached = True
                                    break
                            if dead:
                                continue
                            child = len(nodes)
                            nodes.append((cur, cur_down, nid, tuple(frames)))
                            if reached:
                                ak = _arrival_key(cur)
                                if ak in arrived:
                                    continue
                                arrived.add(ak)
                                res = SegmentResult(True, _unwind(nodes, child), cur, expanded)
                                if safe and not can_land(cur, solids, dash=True):
                                    held.append(res)
                                    continue
                                yield res
                                continue
                            g2 = g + len(frames)
                            kk = key(cur, cur_down)
                            if hazard is not None:
                                kk = kk + (g2 // 3,)  # hazards move: same place, other time
                            if kk in seen:
                                continue
                            seen.add(kk)
                            heapq.heappush(heap, (g2 + weight * goal.distance(cur), next(counter), g2, child))
        self.hit_limit = expanded >= max_expand
        self.exhausted = not heap  # every state was tried: within its moves there is no way
        for res in held:
            yield res


def plan_segment(
    start: tuple,
    goal,
    solids: set,
    *,
    max_expand: int = 60000,
    weight: float = 2.0,
    durations: tuple = (1, 3, 8),
    allow_dash: bool = True,
    kill_y: float | None = None,
    start_down: bool = True,
    hazard=None,
    field: bool = False,
    wait: bool = False,
    water_key: bool = False,
    safe: bool = False,
    no_dash_climb: bool = False,
    blocked=None,
) -> SegmentResult:
    """Best-first search from `start` until the hitbox center is in `goal`.

    `hazard(t, state)` (optional) is True if the player in `state` gets hit
    during simulation frame t (frames from now), e.g. by a flying bullet;
    such states count as dead and the search plans around them.

    The fixes of docs/level-building-process-brainstorm.md (3.2), all off by
    default (then this is the search the routes were first planned with, node
    for node): `field` (F1) the distance field as heuristic, `water_key` (F2) the
    coarser key in water, `wait` (F3) a macro that holds on until the dash is
    ready, `safe` (F4) an air waypoint counts as reached first by a state that can
    still land (`can_land`; others only once the search is spent).

    `no_dash_climb` leaves out the dash wall climb (`dash_climb_press`), as the
    difficulty rating plays it (players almost never use it). `blocked(state)`:
    states it is True for count as dead (the shortcut checker's walls).
    """
    search = SegmentSearch(
        start,
        goal,
        solids,
        max_expand=max_expand,
        weight=weight,
        durations=durations,
        allow_dash=allow_dash,
        kill_y=kill_y,
        start_down=start_down,
        hazard=hazard,
        field=field,
        wait=wait,
        water_key=water_key,
        safe=safe,
        no_dash_climb=no_dash_climb,
        blocked=blocked,
    )
    res = search.next_arrival()
    if res is None:
        return SegmentResult(False, [], None, search.expanded)
    return res


def _unwind(nodes: list, nid: int) -> list:
    out = []
    while nid > 0:
        _s, _d, parent, act = nodes[nid]
        out.extend(reversed(act))
        nid = parent
    out.reverse()
    return out


def simulate(start: tuple, frames: list, solids: set):
    """Replay per-frame inputs; yields (frame_index, state, down, dead)."""
    s = start
    for i, (m, j, d) in enumerate(frames):
        s, down, dead = ph.apply_frame(s, m, j, d, solids)
        yield i, s, down, dead
