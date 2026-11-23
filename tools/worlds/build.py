"""Build the hand-designed worlds, verify their routes and save maps + plans.

For each level: build the geometry (tools/worlds/levels/level_<id>.py),
write data/maps/<id>.json, plan the intended route with the exact physics
replica (fails loudly at the first unreachable waypoint), check it against
the flame jets' beat and the crumbling blocks (tools/worlds/hazard_check.py)
and save the input plan to tools/worlds/plans/<id>.json for the real-game bot.
The levels in tools/worlds/hearts.py's HEART_LEVELS then get their hearts
along that route, and the map is saved with them.

With --assess, each level's difficulty is measured right after its route is
planned: the timing windows of its elements and the calibrated time to the
first clear (tools/worlds/windows), then the previous noise metric
(tools/worlds/assess), which is the loop for balancing a level.

Usage:
    python -m tools.worlds.build [ids, default: all in tools/worlds/levels] [--preview DIR] [--no-plan] [--assess]
        [--jobs N]
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import sys

from tools.worlds import physics as ph
from tools.worlds.hearts import HEART_LEVELS
from tools.worlds.planner import simulate
from tools.worlds.route import plan_route, save_plan

LEVELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "levels")
LEVELS = sorted(int(f[6:-3]) for f in os.listdir(LEVELS_DIR) if f.startswith("level_") and f.endswith(".py"))


def build_level(map_id: int):
    mod = importlib.import_module(f"tools.worlds.levels.level_{map_id}")
    return mod.build()


def _hearts(lv, frames: list, segments: list) -> None:
    """Place the hearts along the planned route (tools/worlds/hearts.py) and save the map again."""
    from tools.worlds.hearts import place

    spots = place(lv, frames, segments)
    lv.save()
    print(f"  hearts: {len(spots)} at {spots}")


def process_level(map_id: int, args) -> int:
    """Build, save, plan (and optionally assess / preview) one level; prints its
    report. Returns 1 if its route fails, else 0."""
    lv = build_level(map_id)
    path = lv.save()
    st = lv.stats()
    guides = sum(1 for w in lv.route if w.guide)
    print(
        f"level {map_id}: {path} size {st['size']} tiles {st['tiles']} enemies {st['enemies']} "
        f"coins {st['coins']} waypoints {st['waypoints']} ({guides} guides)"
    )
    trail = None
    res = None
    failed = 0
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
        print(f"  planner: {res.summary()}")
        if res.ok:
            from tools.worlds.hazard_check import check_route

            problems = check_route(lv.to_json()["map_data"]["tilemap"], spawn_px, res.frames, solids)
            for line in problems:
                print(f"  hazard {line}")
            if problems:
                failed = 1
        if res.ok:
            save_plan(map_id, spawn_px, res.frames, lv.route, res.segments)
            if map_id in HEART_LEVELS:
                _hearts(lv, res.frames, [(start, n) for _label, start, n, _exp in res.segments])
            if args.assess:
                from tools.worlds.assess import print_details, profile
                from tools.worlds.windows import print_summary, profile_map

                print("  elements (most forgiving way, narrowest window in frames):")
                print_summary(profile_map(map_id, verbose=True))
                r = profile(map_id, 2.0, 24, 30, sections=True, times=True)
                print(f"  previous metric: {r['fails_per_run']} fails per run (assess, sigma 2)")
                print_details(r)
        else:
            failed = 1
    elif map_id in HEART_LEVELS:  # no new plan: the hearts follow the saved one
        from tools.worlds.route import load_plan

        plan = load_plan(map_id)
        _hearts(lv, plan["frame_list"], plan["segments"])
    if args.preview:
        os.makedirs(args.preview, exist_ok=True)
        from tools.worlds.preview import render

        render(path, os.path.join(args.preview, f"level_{map_id}.png"), args.scale, lv.route, trail)
    return failed


def _job(item) -> tuple:
    map_id, args = item
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        failed = process_level(map_id, args)
    return map_id, failed, buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int, default=LEVELS)
    ap.add_argument("--preview", default=None, help="directory for overview PNGs")
    ap.add_argument("--no-plan", action="store_true")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--assess", action="store_true", help="measure difficulty and play time after planning")
    ap.add_argument("--jobs", type=int, default=1, help="levels built and planned at once (processes)")
    args = ap.parse_args()

    if args.jobs <= 1 or len(args.levels) <= 1:
        return 1 if sum(process_level(map_id, args) for map_id in args.levels) else 0
    from concurrent.futures import ProcessPoolExecutor

    failures = 0
    with ProcessPoolExecutor(max_workers=min(args.jobs, len(args.levels))) as pool:
        for _map_id, failed, text in pool.map(_job, [(m, args) for m in args.levels]):
            print(text, end="", flush=True)
            failures += failed
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
