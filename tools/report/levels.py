"""Planner run over every built level, and the difficulty of each.

Plans each level from scratch the way tools.worlds.build does, without
writing a map or a plan, and compares the result with the checked-in plan:
equal frames mean the plan in the repository can be regenerated from the
level's source. The search effort per route segment is only known during
planning, so it is recorded here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict

from tools.worlds import physics as ph
from tools.worlds.build import LEVELS, build_level
from tools.worlds.route import load_plan, plan_route

# Levels with a best-time replay of a human: difficulty reference for the built ones
REFERENCE_LEVELS = [8, 9, 10]


def plan_level(map_id: int) -> Dict[str, Any]:
    lv = build_level(map_id)
    solids = lv.solids()
    spawn_px = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
    kill_y = (max(y for _, y in solids) + 4) * 16
    res = plan_route(solids, spawn_px, lv.route, kill_y, verbose=False)
    stored = load_plan(map_id)["frame_list"]
    st = lv.stats()
    return {
        "level": map_id,
        "ok": res.ok,
        "size": list(st["size"]),
        "tiles": st["tiles"],
        "enemies": st["enemies"],
        "coins": st["coins"],
        "waypoints": st["waypoints"],
        "frames": len(res.frames),
        "seconds_of_play": round(len(res.frames) / 60, 1),
        "jumps": sum(1 for f in res.frames if f[1]),
        "dashes": sum(1 for f in res.frames if f[2]),
        "plan_seconds": round(res.seconds, 2),
        "expanded": sum(seg[3] for seg in res.segments),
        "segments": [{"label": s[0], "start": s[1], "frames": s[2], "expanded": s[3]} for s in res.segments],
        "matches_stored_plan": [tuple(f) for f in res.frames] == [tuple(f) for f in stored],
    }


def collect() -> Dict[str, Any]:
    rows = []
    for map_id in LEVELS:
        row = plan_level(map_id)
        rows.append(row)
        print(
            f"level {map_id}: {row['frames']} frames, {row['expanded']} expanded, "
            f"{row['plan_seconds']} s, stored plan {'matches' if row['matches_stored_plan'] else 'DIFFERS'}",
            flush=True,
        )
    return {"replica_steps_per_s": replica_speed(), "levels": rows}


def replica_speed(steps: int = 200000) -> int:
    """Steps per second of the physics replica along a real planned route."""
    import time

    map_id = LEVELS[-1]
    with open(f"data/maps/{map_id}.json") as f:
        solids = ph.terrain_from_map(json.load(f)["map_data"])
    plan = load_plan(map_id)
    frames = plan["frame_list"]
    s = ph.spawn_state(*plan["spawn"])
    t0 = time.perf_counter()
    done = 0
    while done < steps:
        s = ph.spawn_state(*plan["spawn"])
        for m, j, d in frames:
            s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
        done += len(frames)
    return round(done / (time.perf_counter() - t0))


def play_results(play_dir: str) -> Dict[str, Any]:
    """Reduce the summary of a tools.worlds.play run."""
    with open(os.path.join(play_dir, "summary.json")) as f:
        summary = json.load(f)
    keys = ("completed", "attempt", "lives_lost", "restarts", "dodges", "replans", "desyncs")
    rows = [{"level": int(level), **{k: report.get(k) for k in keys}} for level, report in summary.items()]
    return {"completed": sum(1 for r in rows if r["completed"]), "total": len(rows), "levels": rows}


def difficulty(out_dir: str) -> Dict[str, Any]:
    """tools.worlds.assess with --resample: built and human routes measured the same way."""
    path = os.path.join(out_dir, "difficulty-rows.json")
    ids = [str(i) for i in [*REFERENCE_LEVELS, *LEVELS]]
    subprocess.run(
        [sys.executable, "-m", "tools.worlds.assess", *ids, "--resample", "--json", path],
        check=True,
    )
    with open(path) as f:
        rows = json.load(f)
    os.remove(path)
    return {"reference_levels": REFERENCE_LEVELS, "levels": rows}
