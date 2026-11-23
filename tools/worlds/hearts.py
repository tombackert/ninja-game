"""Hearts along a level's route, placed by the danger on the way.

A heart gives a lost life back (scripts/collectableManager.py). Where the
level is dangerous they come close together, where it is calm there are
none: walking the planned route frame by frame, every frame adds the hits a
player is expected to take there, and each time BUDGET expected hits have
passed, a heart goes on the next ground waypoint of the route (not the last,
by the flag). Counting starts again from that waypoint.

The danger of a frame is what is near the player there:
- enemies within ENEMY_NEAR (as tools/rl/segment_env.py's segment_threats),
- hazard tiles within HAZARD_NEAR: spikes, flame jets and crumbling blocks.
A crumbling block costs no life (falls do not), but it is counted as asked
for the test; with K_HAZARD it adds what a hazard tile adds.

The rates come from the death log (`fit`, below): hits per minute of play
per enemy (or hazard tile) near the route, on FIT_LEVELS. A player takes
PACE times the route's time (the testers: 1.4-2.3x).

    python -m tools.worlds.hearts fit          # rates from the death log
    python -m tools.worlds.hearts show 11 15   # where the hearts would go

`python -m tools.worlds.build` places them for the levels in HEART_LEVELS.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

from scripts.hazards import CRUMBLE, FLAMEJET, SPIKES, flame_cells
from tools.worlds import physics as ph

HEART_LEVELS = (11, 15)  # the test; more once playtests show what hearts do
BUDGET = 0.75  # expected hits between two hearts
PACE = 1.5  # a player's time over the route's time

# Hits per minute of play per enemy / hazard tile near the route: `fit` on the
# death log of 2026-11-23, levels 11-20 (the fight levels hearts are for; all
# map versions): 36 hits from enemies and 9 from hazards in 29.7 minutes. The
# calm levels after them have long logs with almost no hits, which would
# pull the rates down (all levels with a plan: 0.77 and 1.00).
FIT_LEVELS = tuple(range(11, 21))
K_ENEMY = 0.94
K_HAZARD = 1.86

ENEMY_NEAR = (12 * 16, 6 * 16)  # px from the player's middle, x and y
HAZARD_NEAR = (3 * 16, 3 * 16)
ENEMY_CAUSES = ("bullet", "star", "enemy")
HAZARD_CAUSES = ("spikes", "flame")


def danger_sites(lv) -> tuple[list, list]:
    """Middles (px) of the enemies and of the hazard tiles of a builder Level."""
    enemies = [(x * 16 + 8, y * 16 + 8) for (x, y), (k, v) in lv.objects.items() if k == "spawners" and v != 0]
    hazards = [(x * 16 + 8, y * 16 + 8) for (x, y), (k, _v) in lv.objects.items() if k == SPIKES]
    hazards += [(x * 16 + 8, y * 16 + 8) for (x, y), t in lv.solid.items() if t in (CRUMBLE, FLAMEJET)]
    return enemies, hazards


def nearby(states: list, sites: list, reach: tuple) -> list[int]:
    """Per state: how many sites lie within `reach` (x, y px) of the player's middle."""
    rx, ry = reach
    out = []
    for s in states:
        cx, cy = s[ph.X] + ph.PW / 2, s[ph.Y] + ph.PH / 2
        out.append(sum(1 for x, y in sites if abs(x - cx) <= rx and abs(y - cy) <= ry))
    return out


def expected_hits(states: list, enemies: list, hazards: list) -> list[float]:
    """Hits a player is expected to take in each route frame."""
    per_frame = PACE / 3600  # minutes of play per route frame
    ne = nearby(states, enemies, ENEMY_NEAR)
    nh = nearby(states, hazards, HAZARD_NEAR)
    return [(K_ENEMY * e + K_HAZARD * h) * per_frame for e, h in zip(ne, nh)]


def _flamed(lv) -> set:
    """Air tiles a flame jet's flame reaches."""
    out: set = set()
    for (x, y), fields in lv.fixed.items():
        if lv.solid.get((x, y)) == FLAMEJET:
            out.update(map(tuple, flame_cells(x, y, fields["variant"], lv.is_solid)))
    return out


def heart_cell(lv, wp, flamed: set) -> tuple | None:
    """A tile for a heart on ground waypoint `wp`: air with ground under it,
    out of any flame, free or a coin (the heart takes its place); the one
    nearest the waypoint's middle. None if there is none."""
    row = int(wp.y1)
    mid = (wp.x0 + wp.x1) / 2
    for x in sorted(range(int(wp.x0), int(wp.x1) + 1), key=lambda x: (abs(x - mid), x)):
        if lv.is_solid(x, row) or not lv.is_solid(x, row + 1) or (x, row) in flamed:
            continue
        if lv.objects.get((x, row), ("coin", 0))[0] == "coin":
            return x, row
    return None


def heart_spots(lv, hits: list, segments: list, budget: float = BUDGET) -> list[tuple]:
    """Tiles for the hearts: after every `budget` expected hits (counted along
    the route frames), the next ground waypoint that has a cell for one.
    `segments`: per waypoint (start frame, frames), the route plan's."""
    reached = [start + n for start, n in segments]
    flamed = _flamed(lv)
    last = len(lv.route) - 1
    spots: list[tuple] = []
    acc, f = 0.0, 0
    while f < len(hits):
        acc += hits[f]
        if acc < budget:
            f += 1
            continue
        cell, at = None, None
        for i, wp in enumerate(lv.route[:last]):
            if reached[i] >= f and wp.ground and not wp.guide:
                cell = heart_cell(lv, wp, flamed)
                if cell is not None and cell not in spots:
                    at = reached[i]
                    break
                cell = None
        if cell is None:
            break
        spots.append(cell)
        acc, f = 0.0, at + 1
    return spots


def route_states(lv, frames: list) -> list:
    """The physics state of every frame of the planned route."""
    from tools.worlds.planner import simulate

    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
    return [s for _i, s, _d, _dead in simulate(ph.spawn_state(*spawn), frames, solids)]


def place(lv, frames: list, segments: list, budget: float = BUDGET) -> list[tuple]:
    """Put the hearts into `lv` (builder Level) along its planned route and
    return their tiles. `segments`: (start frame, frames) per waypoint."""
    enemies, hazards = danger_sites(lv)
    hits = expected_hits(route_states(lv, frames), enemies, hazards)
    spots = heart_spots(lv, hits, segments, budget)
    for x, y in spots:
        lv.heart(x, y)
    return spots


def _planned(level: int):
    """(builder Level, route frames, segments) of a level from its saved plan."""
    from tools.worlds.build import build_level
    from tools.worlds.route import load_plan

    plan = load_plan(level)
    return build_level(level), plan["frame_list"], plan["segments"]


# --- the rates, from the death log ------------------------------------------


def logged_play(level, directory: str = os.path.join("data", "deaths")) -> tuple[float, int, int]:
    """(minutes of play, hits from enemies, hits from hazards) in a level's death log."""
    path = os.path.join(directory, f"{level}.jsonl")
    if not os.path.exists(path):
        return 0.0, 0, 0
    ticks: dict = collections.defaultdict(int)
    hits: collections.Counter = collections.Counter()
    with open(path) as f:
        for raw in f:
            line = json.loads(raw)
            key = (line.get("session"), line.get("attempt"))
            ticks[key] = max(ticks[key], line.get("tick", 0))
            if line["event"] == "hit":
                hits[line.get("cause")] += 1
    return (
        sum(ticks.values()) / 3600,
        sum(hits[c] for c in ENEMY_CAUSES),
        sum(hits[c] for c in HAZARD_CAUSES),
    )


def fit(levels: list) -> dict:
    """K_ENEMY and K_HAZARD: logged hits over (minutes played x mean number
    of enemies / hazard tiles near the route) on `levels`."""
    tot = {"minutes": 0.0, "enemy_hits": 0, "hazard_hits": 0, "enemy_exposure": 0.0, "hazard_exposure": 0.0}
    for level in levels:
        minutes, he, hh = logged_play(level)
        if minutes <= 0:
            continue
        lv, frames, _segments = _planned(level)
        states = route_states(lv, frames)
        enemies, hazards = danger_sites(lv)
        ne, nh = nearby(states, enemies, ENEMY_NEAR), nearby(states, hazards, HAZARD_NEAR)
        tot["minutes"] += minutes
        tot["enemy_hits"] += he
        tot["hazard_hits"] += hh
        tot["enemy_exposure"] += minutes * sum(ne) / len(ne)
        tot["hazard_exposure"] += minutes * sum(nh) / len(nh)
    tot["K_ENEMY"] = tot["enemy_hits"] / tot["enemy_exposure"] if tot["enemy_exposure"] else None
    tot["K_HAZARD"] = tot["hazard_hits"] / tot["hazard_exposure"] if tot["hazard_exposure"] else None
    return tot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("fit", "show"))
    ap.add_argument("levels", nargs="*", type=int)
    args = ap.parse_args(argv)
    levels = args.levels or list(FIT_LEVELS if args.command == "fit" else HEART_LEVELS)
    if args.command == "fit":
        r = fit(levels)
        print(f"{r['minutes']:.1f} min of play, {r['enemy_hits']} hits from enemies, {r['hazard_hits']} from hazards")
        print(f"K_ENEMY = {r['K_ENEMY']:.2f}, K_HAZARD = {r['K_HAZARD']:.2f} (hits per minute per one near)")
        return 0
    for level in levels:
        lv, frames, segments = _planned(level)
        enemies, hazards = danger_sites(lv)
        hits = expected_hits(route_states(lv, frames), enemies, hazards)
        spots = heart_spots(lv, hits, segments)
        print(f"level {level}: {sum(hits):.2f} expected hits along the route, {len(spots)} hearts at {spots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
