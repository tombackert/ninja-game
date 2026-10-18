"""Difficulty profile of a level, comparable across levels.

The route of levels 11+ is the designed one (tools/worlds/plans). For the
reference levels (e.g. 8-10) the planner follows the best-time replay in
data/replays, i.e. the way a human actually went.

Besides size, enemies, coins and the fastest route (seconds, jumps, wall
jumps, dashes), the route is cut into pieces of `chunk` frames (a reaction
time: within it a player cannot correct anything). Each piece is replayed
`samples` times the way a human would press the same keys: every key event
off by a random number of frames (gaussian, `sigma`), and a jump pressed
too early (before touching the ground or a wall) is pressed again. A piece
fails if the player does not get to where the route goes on (+-10 px).
Precise moves fail often, forgiving ones almost never.

Reported: expected failures per run (sum of the piece failure rates), the
number of pieces failing more than 25 % / 50 % of the time and the
hardest route sections.

Usage:
    python -m tools.worlds.assess 8 9 10 11 12 13 14 16 [--sigma 2] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

from tools.worlds import physics as ph
from tools.worlds.planner import Waypoint, plan_segment
from tools.worlds.route import LEAD_IN, PLANS_DIR, load_plan

TOLERANCE = 10  # px


def load_map(map_id: int):
    with open(f"data/maps/{map_id}.json") as f:
        tiles = list(json.load(f)["map_data"]["tilemap"].values())
    solids = {(t["pos"][0], t["pos"][1]) for t in tiles if t["type"] in ph.PHYSICS_TILES}
    return solids, tiles


def route_from_replay(map_id: int, every: int = 45):
    """Spawn position and waypoints along the human best-time replay (last life)."""
    with open(f"data/replays/{map_id}.json") as f:
        snaps = json.load(f)["snapshots"]
    pts = [snaps[k]["players"][0]["pos"] for k in sorted(snaps, key=int)]
    chain = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if abs(b[0] - a[0]) + abs(b[1] - a[1]) > 100:  # respawn: keep the final run
            chain = [b]
        else:
            chain.append(b)
    route = []
    for x, y in chain[every // 10 :: every // 10] + [chain[-1]]:
        cx, cy = (x + 4) / 16, (y + 7.5) / 16
        route.append(Waypoint(cx - 1, cy - 1, cx, cy, label=f"human {round(cx)},{round(cy)}"))
    return tuple(chain[0]), route


def route_from_plan(map_id: int, solids: set, every: int = 45):
    """Waypoints every `every` frames along a designed route, as for the replays.

    Also returns, per waypoint, the designed route's frames up to it and the
    state there: where re-planning gets stuck, the designed piece stands in."""
    data = load_plan(map_id)
    s = ph.spawn_state(*data["spawn"])
    route, fallback = [], []
    last = 0
    for i, (m, j, d) in enumerate(data["frame_list"]):
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
        if (i + 1) % every == 0 or i + 1 == len(data["frame_list"]):
            cx, cy = (s[ph.X] + 4) / 16, (s[ph.Y] + 7.5) / 16
            route.append(Waypoint(cx - 1, cy - 1, cx, cy, label=f"route {round(cx)},{round(cy)}"))
            fallback.append((data["frame_list"][last : i + 1], s))
            last = i + 1
    return tuple(data["spawn"]), route, fallback


def load_route(map_id: int, solids: set, resample: bool = False):
    """(spawn, waypoints, per-frame inputs, source, teleports) of a level's route.

    With `resample`, a designed route is treated exactly like a replay:
    waypoints every 45 frames along it, re-planned from scratch."""
    path = os.path.join(PLANS_DIR, f"{map_id}.json")
    if os.path.exists(path) and not resample:
        data = load_plan(map_id)
        return tuple(data["spawn"]), data["waypoints"], data["frame_list"], "designed route", {}
    fallback = None
    teleports: dict = {}
    if os.path.exists(path):
        spawn, route, fallback = route_from_plan(map_id, solids)
        source = "designed route, resampled like a replay"
    else:
        spawn, route = route_from_replay(map_id)
        source = "human best-time route"
    kill_y = (max(y for _, y in solids) + 4) * 16
    s = ph.spawn_state(*spawn)
    frames = [(0, False, False)] * LEAD_IN
    for _ in range(LEAD_IN):
        s, _d, _dead = ph.step(s, 0, solids)
    for k, wp in enumerate(route):
        res = plan_segment(s, wp, solids, weight=5.0, max_expand=20000, kill_y=kill_y)
        if not res.ok:
            res = plan_segment(s, wp, solids, weight=2.0, max_expand=60000, kill_y=kill_y)
        if res.ok:
            frames += res.frames
            s = res.end
        elif fallback is not None and k > 0:  # the designed piece, from where it starts
            teleports[len(frames)] = fallback[k - 1][1]
            piece, s = fallback[k]
            frames += piece
    return spawn, route, frames, source, teleports


def _noisy(frames: list, rng: random.Random, sigma: float) -> list:
    """The same inputs as a human would press them: each key event a few frames off."""
    n = len(frames)
    m_out = [f[0] for f in frames]
    for i in range(1, n):
        if frames[i][0] != frames[i - 1][0]:
            j = max(1, min(n, i + round(rng.gauss(0, sigma))))
            lo, hi = sorted((i, j))
            fill = frames[i - 1][0] if j > i else frames[i][0]
            for k in range(lo, hi):
                m_out[k] = fill
    out = [[m, False, False] for m in m_out]
    for i, (_m, jmp, dash) in enumerate(frames):
        for idx, on in ((1, jmp), (2, dash)):
            if on:
                k = max(0, i + round(rng.gauss(0, sigma)))
                if k < n:
                    out[k][idx] = True
    return out


def piece_fail_rate(states, frames, a, b, solids, kill_y, rng, sigma, samples) -> float:
    """Share of noisy replays of frames[a:b] that miss the planned position at b."""
    tx, ty = states[b][ph.X], states[b][ph.Y]
    horizon = min(len(frames), b + 8)
    fails = 0
    for _ in range(samples):
        inputs = _noisy(frames[a:horizon], rng, sigma)
        s = states[a]
        hit = False
        pending_jump = 0
        for i, (m, j, d) in enumerate(inputs):
            if j:
                pending_jump = 6  # pressed again for a few frames if it had no effect
            jump = pending_jump > 0 and ph.can_jump(s)
            if jump:
                pending_jump = 0
            elif pending_jump:
                pending_jump -= 1
            s, _down, dead = ph.apply_frame(s, m, jump, d, solids)
            if dead or s[ph.Y] > kill_y:
                break
            if a + i + 1 >= b - 4 and abs(s[ph.X] - tx) <= TOLERANCE and abs(s[ph.Y] - ty) <= TOLERANCE:
                hit = True
                break
        fails += not hit
    return fails / samples


def profile(map_id: int, sigma: float, chunk: int, samples: int, resample: bool = False) -> dict:
    solids, tiles = load_map(map_id)
    kill_y = (max(y for _, y in solids) + 4) * 16
    spawn, route, frames, source, teleports = load_route(map_id, solids, resample)
    states = [ph.spawn_state(*spawn)]
    jumps = walljumps = dashes = 0
    for i, (m, j, d) in enumerate(frames):
        s = teleports.get(i, states[-1])
        states[-1] = s
        if j and ph.can_jump(s):
            if s[ph.WALL]:
                walljumps += 1
            else:
                jumps += 1
        if d and s[ph.DASH] == 0:
            dashes += 1
        states.append(ph.apply_frame(s, m, j, d, solids)[0])
    rng = random.Random(map_id)
    rates = []
    for a in range(LEAD_IN, len(frames) - 1, chunk):
        b = min(a + chunk, len(frames))
        rates.append((piece_fail_rate(states, frames, a, b, solids, kill_y, rng, sigma, samples), a))
    xs = [x for x, _ in solids]
    ys = [y for _, y in solids]
    hardest = sorted(rates, reverse=True)[:5]
    return {
        "level": map_id,
        "source": source,
        "size": [max(xs) - min(xs) + 1, max(ys) - min(ys) + 1],
        "enemies": sum(1 for t in tiles if t["type"] == "spawners" and t["variant"] == 1),
        "coins": sum(1 for t in tiles if t["type"] == "coin"),
        "seconds": round(len(frames) / 60, 1),
        "jumps": jumps,
        "wall_jumps": walljumps,
        "dashes": dashes,
        "pieces": len(rates),
        "fails_per_run": round(sum(r for r, _a in rates), 1),
        "hard_pieces": sum(1 for r, _a in rates if r > 0.25),
        "very_hard_pieces": sum(1 for r, _a in rates if r > 0.5),
        "hardest": [
            {"rate": r, "at_px": [round(states[a][ph.X]), round(states[a][ph.Y])], "second": round(a / 60, 1)}
            for r, a in hardest
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="+", type=int)
    ap.add_argument("--sigma", type=float, default=2.0, help="timing error of a key press (frames, 1 sd)")
    ap.add_argument("--chunk", type=int, default=24, help="frames a player cannot correct (reaction time)")
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--resample", action="store_true", help="treat designed routes like replays (fair comparison)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    rows = []
    for lvl in args.levels:
        r = profile(lvl, args.sigma, args.chunk, args.samples, args.resample)
        rows.append(r)
        print(json.dumps(r), flush=True)
    print(
        f"{'level':>5} {'size':>8} {'enemy':>5} {'coins':>5} {'sec':>4} {'jump':>4} {'wall':>4} {'dash':>4} "
        f"{'fails/run':>9} {'>25%':>5} {'>50%':>5}"
    )
    for r in rows:
        size = f"{r['size'][0]}x{r['size'][1]}"
        print(
            f"{r['level']:>5} {size:>8} {r['enemies']:>5} {r['coins']:>5} {r['seconds']:>4.0f} {r['jumps']:>4} "
            f"{r['wall_jumps']:>4} {r['dashes']:>4} {r['fails_per_run']:>9} {r['hard_pieces']:>5} "
            f"{r['very_hard_pieces']:>5}"
        )
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
