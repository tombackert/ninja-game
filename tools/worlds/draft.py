"""A first route for a map that has none, and small edits of a map's route.

The draft is what every map has to offer: the spawn, the checkpoints and the
flag. It runs from the spawn over each checkpoint (a ground box on the tile
the checkpoint respawns on, in the order an air path from the spawn reaches
them) to the flag (its tile, as the built levels end). The planner
(`python -m tools.worlds.build <id>`) then shows where it gets stuck: a
waypoint it reports UNREACHED needs stops before it, put in with `insert`,
until the route is OK. The route lives in the map (map_data.route,
tools/worlds/mapfile.py); nothing else of the map is changed.

Usage:
    python -m tools.worlds.draft draft <id> [--force]     # write the draft route into data/maps/<id>.json
    python -m tools.worlds.draft list <id>                 # the route, numbered
    python -m tools.worlds.draft insert <id> <index> x0 y0 [x1 y1] [--ground] [--label L] [--guide]
    python -m tools.worlds.draft delete <id> <index>
"""

from __future__ import annotations

import argparse
import sys
from collections import deque

from tools.worlds.mapfile import MapLevel
from tools.worlds.planner import Waypoint

AIR_MARGIN = 8  # tiles of open air around the map the path search may use


def air_steps(ml: MapLevel, start: tuple) -> dict:
    """Steps from `start` to every air tile 4-connected to it (within the map's
    bounds widened by AIR_MARGIN): a rough order along the level."""
    xs = [x for x, _ in ml.solid] or [start[0]]
    ys = [y for _, y in ml.solid] or [start[1]]
    x_lo, x_hi = min(xs) - AIR_MARGIN, max(xs) + AIR_MARGIN
    y_lo, y_hi = min(ys) - AIR_MARGIN, max(ys) + AIR_MARGIN
    dist = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in dist or ml.is_solid(nx, ny) or not (x_lo <= nx <= x_hi and y_lo <= ny <= y_hi):
                continue
            dist[(nx, ny)] = dist[(x, y)] + 1
            queue.append((nx, ny))
    return dist


def draft_route(ml: MapLevel) -> list[Waypoint]:
    """Spawn -> checkpoints -> flag as waypoints (the spawn is where the plan starts)."""
    if ml.spawn_tile is None:
        raise ValueError(f"map {ml.map_id}: no player spawner")
    if ml.flag_tile is None:
        raise ValueError(f"map {ml.map_id}: no flag")
    steps = air_steps(ml, ml.spawn_tile)
    far = len(steps) + 1
    route = []
    checkpoints = sorted(ml.checkpoint_tiles, key=lambda t: (steps.get(t, far), t))
    for i, (x, y) in enumerate(checkpoints, start=1):
        route.append(Waypoint(x - 1, y, x + 1, y, True, f"checkpoint {i}" if len(checkpoints) > 1 else "checkpoint"))
    fx, fy = ml.flag_tile
    route.append(Waypoint(fx, fy, fx, fy, False, "flag"))
    return route


def describe(i: int, w: Waypoint) -> str:
    box = f"{w.x0},{w.y0}" if (w.x0, w.y0) == (w.x1, w.y1) else f"{w.x0},{w.y0}..{w.x1},{w.y1}"
    flags = "".join((" ground" if w.ground else "", " guide" if w.guide else ""))
    return f"{i:3d}  {box:<20} {w.label}{flags}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("draft", help="write the draft route into the map")
    p.add_argument("map_id")
    p.add_argument("--force", action="store_true", help="replace a route the map already has")
    p = sub.add_parser("list", help="print the map's route")
    p.add_argument("map_id")
    p = sub.add_parser("insert", help="put a waypoint in before <index> (the route's length: at the end)")
    p.add_argument("map_id")
    p.add_argument("index", type=int)
    p.add_argument("box", type=float, nargs="+", help="x0 y0 [x1 y1], tiles, inclusive")
    p.add_argument("--ground", action="store_true", help="the player must stand in the box")
    p.add_argument("--label", default="")
    p.add_argument("--guide", action="store_true", help="only there so the planner gets through")
    p = sub.add_parser("delete", help="take out waypoint <index>")
    p.add_argument("map_id")
    p.add_argument("index", type=int)
    args = ap.parse_args(argv)

    ml = MapLevel.load(args.map_id)
    route = list(ml.route)
    if args.command == "list":
        for i, w in enumerate(route):
            print(describe(i, w))
        return 0
    if args.command == "draft":
        if route and not args.force:
            print(f"map {args.map_id} has a route of {len(route)} waypoints already (--force replaces it)")
            return 1
        route = draft_route(ml)
    elif args.command == "insert":
        if len(args.box) not in (2, 4):
            ap.error("box: x0 y0 or x0 y0 x1 y1")
        x0, y0, x1, y1 = args.box if len(args.box) == 4 else args.box * 2
        x0, y0, x1, y1 = (int(v) if float(v).is_integer() else v for v in (x0, y0, x1, y1))
        if not 0 <= args.index <= len(route):
            ap.error(f"index: 0..{len(route)}")
        route.insert(args.index, Waypoint(x0, y0, x1, y1, args.ground, args.label, args.guide))
    elif args.command == "delete":
        if not 0 <= args.index < len(route):
            ap.error(f"index: 0..{len(route) - 1}")
        del route[args.index]
    ml.set_route(route)
    print(f"{ml.save()}: {len(route)} waypoints")
    for i, w in enumerate(route):
        print(describe(i, w))
    return 0


if __name__ == "__main__":
    sys.exit(main())
