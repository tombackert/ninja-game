"""A first route for a map that has none, and small edits of a map's route.

The draft is what every map has to offer: the spawn, the checkpoints and the
flag. It runs from the spawn over each checkpoint (a ground box on the tile
the checkpoint respawns on, in the order an air path from the spawn reaches
them) to the flag (its tile, as the built levels end). The planner
(`python -m tools.worlds.build <id>`) then shows where it gets stuck: a
waypoint it reports UNREACHED needs stops before it, put in with `insert`,
until the route is OK. The route lives in the map (map_data.route,
tools/worlds/mapfile.py); nothing else of the map is changed.

A route can also come from a replay (scripts/replay.py, data/replays/<id>.json:
a snapshot every 10 ticks): every REPLAY_STEP tiles of the run, the next
place the player stands on becomes a ground waypoint. After a death the stops
past the respawn point are dropped, as the run went on from there.

Usage:
    python -m tools.worlds.draft draft <id> [--force]     # write the draft route into data/maps/<id>.json
    python -m tools.worlds.draft replay <id> [--file PATH] [--step N] [--force]   # route from a replay
    python -m tools.worlds.draft list <id>                 # the route, numbered
    python -m tools.worlds.draft insert <id> <index> x0 y0 [x1 y1] [--ground] [--label L] [--guide]
    python -m tools.worlds.draft delete <id> <index>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

from tools.worlds.mapfile import MapLevel
from tools.worlds.physics import PH, PW, TS
from tools.worlds.planner import Waypoint

AIR_MARGIN = 8  # tiles of open air around the map the path search may use
REPLAY_STEP = 6  # tiles of the run between two stops taken from a replay
REPLAY_DIR = os.path.join("data", "replays")


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


def stand_box(ml: MapLevel, x: int, y: int, reach: int = 1) -> Waypoint:
    """A ground waypoint on stand tile (x, y), as wide as the floor there allows
    within `reach` tiles to each side."""
    x0 = x1 = x
    while x0 > x - reach and ml.is_solid(x0 - 1, y + 1) and not ml.is_solid(x0 - 1, y):
        x0 -= 1
    while x1 < x + reach and ml.is_solid(x1 + 1, y + 1) and not ml.is_solid(x1 + 1, y):
        x1 += 1
    return Waypoint(x0, y, x1, y, True, "")


def standing_tile(ml: MapLevel, x: float, y: float) -> tuple | None:
    """The air tile a player whose hitbox's top left is at (x, y) px stands on,
    or None in the air: the feet on a tile's top, rock under the middle."""
    bottom = y + PH
    row = round(bottom / TS)
    if abs(bottom - row * TS) > 1:
        return None
    tx = int((x + PW / 2) // TS)
    if ml.is_solid(tx, row) and not ml.is_solid(tx, row - 1):
        return tx, row - 1
    return None


def replay_positions(replay: dict) -> list[tuple]:
    """(tick, x, y, deaths) of the first player in each snapshot, in tick order."""
    out = []
    for tick in sorted(replay.get("snapshots", {}), key=int):
        snap = replay["snapshots"][tick]
        players = snap.get("players") or []
        if players:
            x, y = players[0]["pos"]
            out.append((int(tick), float(x), float(y), int(snap.get("dead_count", 0))))
    return out


def replay_route(ml: MapLevel, replay: dict, step: int = REPLAY_STEP) -> list[Waypoint]:
    """Stops along a recorded run, then the flag. A stop is a place the player
    stood on once the run had gone `step` tiles (either way) from the last one;
    after a death the stops beyond the one nearest the respawn are dropped."""
    if ml.flag_tile is None:
        raise ValueError(f"map {ml.map_id}: no flag")
    stops: list[tuple] = []
    last = ml.spawn_tile
    respawns = [t for t in [ml.spawn_tile, *ml.checkpoint_tiles] if t is not None]
    deaths = 0
    died_at = None  # the player's tile when the last death was counted, until the respawn
    pos = None
    for tick, x, y, dead in replay_positions(replay):
        here = (int((x + PW / 2) // TS), int((y + PH / 2) // TS))
        if dead > deaths:
            deaths, died_at = dead, pos or here
            continue
        pos = here
        cell = standing_tile(ml, x, y)
        if cell is None:
            continue
        if died_at is not None:
            # still where it died (the death plays out there), unless that is a respawn point
            at_respawn = any(max(abs(cell[0] - r[0]), abs(cell[1] - r[1])) <= 2 for r in respawns)
            if not at_respawn and max(abs(cell[0] - died_at[0]), abs(cell[1] - died_at[1])) <= 2:
                continue
            # the run goes on from here: forget what came after it
            died_at = None
            near = [max(abs(cell[0] - s[0]), abs(cell[1] - s[1])) for s in stops]
            keep = near.index(min(near)) + 1 if near and min(near) < step else 0
            stops = stops[:keep]
            last = stops[-1] if stops else cell
            continue
        if last is None or max(abs(cell[0] - last[0]), abs(cell[1] - last[1])) >= step:
            stops.append(cell)
            last = cell
    fx, fy = ml.flag_tile
    route = []
    for i, (x, y) in enumerate(stops, start=1):
        if max(abs(x - fx), abs(y - fy)) < 2:
            break  # at the flag already
        w = stand_box(ml, x, y)
        w.label = f"replay {i}"
        route.append(w)
    route.append(Waypoint(fx, fy, fx, fy, False, "flag"))
    return route


def load_replay(map_id, path: str | None = None) -> dict:
    with open(path or os.path.join(REPLAY_DIR, f"{map_id}.json")) as f:
        return json.load(f)


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
    p = sub.add_parser("replay", help="write a route taken from a replay into the map")
    p.add_argument("map_id")
    p.add_argument("--file", help="the replay (default: data/replays/<id>.json, the best run)")
    p.add_argument("--step", type=int, default=REPLAY_STEP, help="tiles of the run between two stops")
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
    if args.command in ("draft", "replay"):
        if route and not args.force:
            print(f"map {args.map_id} has a route of {len(route)} waypoints already (--force replaces it)")
            return 1
        if args.command == "draft":
            route = draft_route(ml)
        else:
            route = replay_route(ml, load_replay(args.map_id, args.file), args.step)
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
