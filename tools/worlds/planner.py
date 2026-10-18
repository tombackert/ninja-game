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
        down,
    )


def plan_segment(
    start: tuple,
    goal: Waypoint,
    solids: set,
    *,
    max_expand: int = 60000,
    weight: float = 2.0,
    durations: tuple = (1, 3, 8),
    allow_dash: bool = True,
    kill_y: float | None = None,
    start_down: bool = True,
    hazard=None,
) -> SegmentResult:
    """Best-first search from `start` until the hitbox center is in `goal`.

    `hazard(t, state)` (optional) is True if the player in `state` gets hit
    during simulation frame t (frames from now), e.g. by a flying bullet;
    such states count as dead and the search plans around them.
    """
    if goal.contains(start, start_down):
        return SegmentResult(True, [], start, 0)
    durs = sorted(durations)
    counter = itertools.count()
    # node: (f, tiebreak, g, state, down, parent_id, action)
    nodes = [(start, start_down, -1, None)]  # id -> (state, down, parent, action)
    heap = [(weight * goal.distance(start), next(counter), 0, 0)]
    seen = {_key(start, start_down)}
    expanded = 0
    while heap and expanded < max_expand:
        _f, _t, g, nid = heapq.heappop(heap)
        s, down, _parent, _act = nodes[nid]
        expanded += 1
        jumps = (False, True) if ph.can_jump(s) else (False,)
        dashes = (False, True) if (allow_dash and s[ph.DASH] == 0) else (False,)
        for m in (1, -1, 0):
            for jump in jumps:
                for dash in dashes:
                    for k in durs:
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
                            if goal.contains(cur, cur_down):
                                reached = True
                                break
                        if dead:
                            continue
                        child = len(nodes)
                        nodes.append((cur, cur_down, nid, tuple(frames)))
                        if reached:
                            return SegmentResult(True, _unwind(nodes, child), cur, expanded)
                        g2 = g + len(frames)
                        key = _key(cur, cur_down)
                        if hazard is not None:
                            key = key + (g2 // 3,)  # hazards move: same place, other time
                        if key in seen:
                            continue
                        seen.add(key)
                        heapq.heappush(heap, (g2 + weight * goal.distance(cur), next(counter), g2, child))
    return SegmentResult(False, [], None, expanded)


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
