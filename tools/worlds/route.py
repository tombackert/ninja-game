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
from tools.worlds.planner import Waypoint, plan_segment

PLANS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans")


@dataclass
class RouteResult:
    ok: bool
    frames: list = field(default_factory=list)
    segments: list = field(default_factory=list)  # (label, start_frame, n_frames, expanded)
    failed_at: int | None = None
    end: tuple | None = None
    seconds: float = 0.0


# Idle frames before the first input: the game steps once before the bot's
# first key event reaches it (and again after each reload), so a plan
# starts by standing still for a moment, as a player watching the fade-in.
LEAD_IN = 30


def plan_route(solids: set, spawn_px: tuple, route: list[Waypoint], kill_y: float, verbose=True) -> RouteResult:
    t0 = time.time()
    s = ph.spawn_state(*spawn_px)
    frames: list = [(0, False, False)] * LEAD_IN
    for _ in range(LEAD_IN):
        s, _down, _dead = ph.step(s, 0, solids)
    segments = []
    for i, wp in enumerate(route):
        res = plan_segment(s, wp, solids, weight=5.0, max_expand=20000, kill_y=kill_y)
        if not res.ok:
            res = plan_segment(s, wp, solids, weight=2.0, max_expand=120000, kill_y=kill_y)
        if not res.ok:
            if verbose:
                print(
                    f"  waypoint {i} '{wp.label}' {(wp.x0, wp.y0, wp.x1, wp.y1)} UNREACHED "
                    f"from px {(round(s[0]), round(s[1]))}"
                )
            return RouteResult(False, frames, segments, i, s, time.time() - t0)
        segments.append((wp.label, len(frames), len(res.frames), res.expanded))
        frames += res.frames
        s = res.end
    return RouteResult(True, frames, segments, None, s, time.time() - t0)


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
                "route": [[w.x0, w.y0, w.x1, w.y1, w.ground, w.label] for w in route],
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
