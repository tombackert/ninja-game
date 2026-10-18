"""Build the hand-designed worlds, verify their routes and save maps + plans.

For each level: build the geometry (tools/worlds/levels/level_<id>.py),
write data/maps/<id>.json, plan the intended route with the exact physics
replica (fails loudly at the first unreachable waypoint) and save the
input plan to tools/worlds/plans/<id>.json for the real-game bot.

Usage:
    python -m tools.worlds.build [ids, default: all in tools/worlds/levels] [--preview DIR] [--no-plan]
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys

from tools.worlds import physics as ph
from tools.worlds.planner import simulate
from tools.worlds.route import plan_route, save_plan

LEVELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "levels")
LEVELS = sorted(int(f[6:-3]) for f in os.listdir(LEVELS_DIR) if f.startswith("level_") and f.endswith(".py"))


def build_level(map_id: int):
    mod = importlib.import_module(f"tools.worlds.levels.level_{map_id}")
    return mod.build()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int, default=LEVELS)
    ap.add_argument("--preview", default=None, help="directory for overview PNGs")
    ap.add_argument("--no-plan", action="store_true")
    ap.add_argument("--scale", type=float, default=0.5)
    args = ap.parse_args()

    failures = 0
    for map_id in args.levels:
        lv = build_level(map_id)
        path = lv.save()
        st = lv.stats()
        print(
            f"level {map_id}: {path} size {st['size']} tiles {st['tiles']} enemies {st['enemies']} "
            f"coins {st['coins']} waypoints {st['waypoints']}"
        )
        trail = None
        res = None
        if not args.no_plan:
            solids = lv.solids()
            spawn_px = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
            kill_y = (max(y for _, y in solids) + 4) * 16
            res = plan_route(solids, spawn_px, lv.route, kill_y)
            trail = [spawn_px] + [
                (s[ph.X], s[ph.Y]) for _i, s, _d, _dead in simulate(ph.spawn_state(*spawn_px), res.frames, solids)
            ]
            jumps = sum(1 for f in res.frames if f[1])
            dashes = sum(1 for f in res.frames if f[2])
            status = "OK" if res.ok else f"FAILED at waypoint {res.failed_at}"
            print(
                f"  route {status}: {len(res.frames)} frames ({len(res.frames) / 60:.1f} s), {jumps} jumps, "
                f"{dashes} dashes, planned in {res.seconds:.1f} s"
            )
            if res.ok:
                save_plan(map_id, spawn_px, res.frames, lv.route, res.segments)
            else:
                failures += 1
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            from tools.worlds.preview import render

            render(path, os.path.join(args.preview, f"level_{map_id}.png"), args.scale, lv.route, trail)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
