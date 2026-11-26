"""Build the hand-designed worlds, verify their routes and save maps + plans.

One flow for every map, built or drawn in the editor:

    level script or editor -> data/maps/<id>.json (tiles + route) -> planner -> plans/<id>.json

For a built level (tools/worlds/levels/level_<id>.py) the geometry is built
and data/maps/<id>.json written first, its route (`lv.wp`) included. An
editor map (levels 0-10) is read as it is and never rewritten, except for
hearts asked for with --hearts. Then, from the map file alone: plan the
route in map_data.route with the exact physics replica (fails loudly at the
first unreachable waypoint), check it against the flame jets' beat and the
crumbling blocks (tools/worlds/hazard_check.py) and save the input plan to
tools/worlds/plans/<id>.json for the real-game bot. The built levels in
tools/worlds/hearts.py's HEART_LEVELS then get their hearts along that route,
and the map is saved with them.

With --assess, each level's difficulty is measured right after its route is
planned: the timing windows of its elements and the calibrated time to the
first clear (tools/worlds/windows), then the previous noise metric
(tools/worlds/assess), which is the loop for balancing a level.

Usage:
    python -m tools.worlds.build [ids, default: every built level and every map with a route]
        [--preview DIR] [--no-plan] [--assess] [--jobs N] [--hearts]
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import sys
from dataclasses import dataclass

from tools.worlds import physics as ph
from tools.worlds.hearts import HEART_LEVELS
from tools.worlds.mapfile import MAPS_DIR, MapLevel, map_path
from tools.worlds.planner import simulate
from tools.worlds.route import RouteResult, plan_route, save_plan

LEVELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "levels")
LEVELS = sorted(int(f[6:-3]) for f in os.listdir(LEVELS_DIR) if f.startswith("level_") and f.endswith(".py"))


def build_level(map_id: int):
    mod = importlib.import_module(f"tools.worlds.levels.level_{map_id}")
    return mod.build()


def routed_maps(maps_dir: str = MAPS_DIR) -> list[int]:
    """The numbered maps whose file holds a route (built levels and routed editor maps)."""
    out = []
    for name in os.listdir(maps_dir):
        stem, ext = os.path.splitext(name)
        if ext != ".json" or not stem.lstrip("-").isdigit():
            continue
        with open(os.path.join(maps_dir, name)) as f:
            if json.load(f)["map_data"].get("route"):
                out.append(int(stem))
    return sorted(out)


@dataclass
class Planned:
    """A map's route planned from its file: the plan, the path of the player's
    hitbox (top left, px, from the spawn) and what the hazard check found."""

    res: RouteResult
    trail: list
    problems: list


def plan_map(ml: MapLevel, verbose: bool = True, cache=None) -> Planned:
    """Plan `ml`'s route with the physics replica and check it against the flame
    jets' beat and the crumbling blocks (tools/worlds/hazard_check.py). Saves
    nothing: build.py and the editor's route mode save the plan themselves."""
    solids = ml.solids()
    spawn_px = ml.spawn_px
    res = plan_route(solids, spawn_px, ml.route, ml.kill_y(), verbose=verbose, cache=cache)
    trail = [spawn_px] + [
        (s[ph.X], s[ph.Y]) for _i, s, _d, _dead in simulate(ph.spawn_state(*spawn_px), res.frames, solids)
    ]
    problems: list = []
    if res.ok:
        from tools.worlds.hazard_check import check_route

        problems = check_route(ml.tilemap, spawn_px, res.frames, solids)
    return Planned(res, trail, problems)


def _hearts(ml: MapLevel, frames: list, segments: list) -> None:
    """Place the hearts along the planned route (tools/worlds/hearts.py) and save the map again."""
    from tools.worlds.hearts import place

    spots = place(ml, frames, segments)
    ml.save()
    print(f"  hearts: {len(spots)} at {spots}")


def process_level(map_id: int, args) -> int:
    """Build and save (a built level), then plan from the map file (and optionally
    assess / preview) one level; prints its report. Returns 1 if its route fails, else 0."""
    built = map_id in LEVELS
    if built:
        lv = build_level(map_id)
        path = lv.save()
        st = lv.stats()
        guides = sum(1 for w in lv.route if w.guide)
        print(
            f"level {map_id}: {path} size {st['size']} tiles {st['tiles']} enemies {st['enemies']} "
            f"coins {st['coins']} waypoints {st['waypoints']} ({guides} guides)"
        )
    else:
        path = map_path(map_id)
    ml = MapLevel.load(map_id)  # from here on only the map file counts
    if not built:
        guides = sum(1 for w in ml.route if w.guide)
        print(f"level {map_id}: {path} (editor map) waypoints {len(ml.route)} ({guides} guides)")
    if not ml.route:
        print("  no route in map_data.route (tools/worlds/draft.py makes a first one)")
        return 1
    if ml.spawn_tile is None:
        print("  no player spawner in the map")
        return 1
    # Hearts are written into the map: always for the built HEART_LEVELS (rebuilt
    # without any), for an editor map only when asked (it replaces its hearts)
    hearts = (built and map_id in HEART_LEVELS) or (not built and args.hearts)
    if hearts and not built:
        gone = ml.remove_hearts()
        if gone:
            print(f"  hearts: took out the {len(gone)} there were at {gone}")
    trail = None
    res = None
    failed = 0
    if not args.no_plan:
        spawn_px = ml.spawn_px
        planned = plan_map(ml)
        res, trail = planned.res, planned.trail
        jumps = sum(1 for f in res.frames if f[1])
        dashes = sum(1 for f in res.frames if f[2])
        status = "OK" if res.ok else f"FAILED at waypoint {res.failed_at}"
        print(
            f"  route {status}: {len(res.frames)} frames ({len(res.frames) / 60:.1f} s), {jumps} jumps, "
            f"{dashes} dashes, planned in {res.seconds:.1f} s"
        )
        print(f"  planner: {res.summary()}")
        for line in planned.problems:
            print(f"  hazard {line}")
        if planned.problems:
            failed = 1
        if res.ok:
            save_plan(map_id, spawn_px, res.frames, ml.route, res.segments)
            if hearts:
                _hearts(ml, res.frames, [(start, n) for _label, start, n, _exp in res.segments])
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
    elif hearts:  # no new plan: the hearts follow the saved one
        from tools.worlds.route import load_plan

        plan = load_plan(map_id)
        _hearts(ml, plan["frame_list"], plan["segments"])
    if args.preview:
        os.makedirs(args.preview, exist_ok=True)
        from tools.worlds.preview import render

        render(path, os.path.join(args.preview, f"level_{map_id}.png"), args.scale, ml.route, trail)
    return failed


def _job(item) -> tuple:
    map_id, args = item
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        failed = process_level(map_id, args)
    return map_id, failed, buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--preview", default=None, help="directory for overview PNGs")
    ap.add_argument("--no-plan", action="store_true")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--assess", action="store_true", help="measure difficulty and play time after planning")
    ap.add_argument("--jobs", type=int, default=1, help="levels built and planned at once (processes)")
    ap.add_argument(
        "--hearts", action="store_true", help="also place hearts on the editor maps given (replaces their hearts)"
    )
    args = ap.parse_args()
    if not args.levels:
        args.levels = sorted(set(LEVELS) | set(routed_maps()))

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
