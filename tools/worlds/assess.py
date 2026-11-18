"""Difficulty profile of a level, comparable across levels.

The route of levels 11-20 is the designed one (tools/worlds/plans). For the
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
hardest route sections; on levels with water also the least breath left
anywhere on the route.

--sections adds up the failures per section of a designed route (its
waypoint labels, numbers left out: "bounce ledge 0..5" is one section), so
it shows which elements make a level hard.

--playtime estimates the time a player needs to beat the level for the
first time, deaths included, for two skill profiles (PROFILES): a miss that
no quick correction saves (steering or one jump, after a reaction time)
is a death; it costs the rest of the fall and the fade, and sends the
player back to the last checkpoint passed (the level's banners, plus the
manual one, P, placed where it saves the most). It sees no enemies and no breath, and
the designed route is the fastest, not the safest way, so the minutes are
rough (+-50 % against a tester's first clears); comparisons between levels
and the sections where players die (death hotspots) are what it is for.

`profile_level(lv)` measures a Level that only exists in memory (an element
built on its own to see how hard it is), planning its route first.

--windows is the headline measure now (tools/worlds/windows.py): the
timing window of every key press on the most forgiving way through each
element of the route, and the time to the first clear from it, calibrated
on playtests (--calibrate, tools/worlds/calibrate.py). The noise model above
stays for comparison and for tools/report.

Usage:
    python -m tools.worlds.assess 8 9 10 11 12 13 14 15 [--sigma 2] [--json out.json]
    python -m tools.worlds.assess 26 --sections --playtime
    python -m tools.worlds.assess 26 --windows
    python -m tools.worlds.assess 26 27 28 --windows --jobs 8 [--dash-climb]
    python -m tools.worlds.assess --calibrate [levels] [--jobs 8]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict

from scripts.constants import AIR_TIME_FATAL, RESPAWN_DEAD_THRESHOLD
from tools.worlds import physics as ph
from tools.worlds.planner import Waypoint, plan_segment
from tools.worlds.route import LEAD_IN, PLANS_DIR, load_plan

TOLERANCE = 10  # px

# Skill profiles for --playtime: (timing error of a key press in frames, 1 sd;
# pace: play time over the designed route's time). "expert" fits a tester's
# first clears of levels 13-20 (2026-11-03: 1.6-5 min a level, deaths and
# menus included; best runs 1.4-2.3x the route's time). "average" is a guess.
PROFILES = {"expert": (1.0, 1.6), "average": (2.0, 2.0)}
REACT = 10  # frames until a correction after a miss takes effect
PLAYTIME_SAMPLES = 60


def _map_data(map_id: int) -> dict:
    with open(f"data/maps/{map_id}.json") as f:
        return json.load(f)["map_data"]


def load_map(map_id: int):
    map_data = _map_data(map_id)
    return ph.terrain_from_map(map_data), list(map_data["tilemap"].values())


def checkpoint_boxes(map_data: dict) -> list:
    """Banners (x0, y0, x1, y1 in px) of a map's checkpoints, as scripts/checkpoints.py
    reads them: grid tiles in tile units, offgrid ones in px, drawn from there down."""
    from scripts.checkpoints import BANNER_H, BANNER_W, CHECKPOINT

    ts = map_data.get("tile_size", 16)
    corners = [(t["pos"][0] * ts, t["pos"][1] * ts) for t in map_data["tilemap"].values() if t["type"] == CHECKPOINT]
    corners += [tuple(t["pos"]) for t in map_data.get("offgrid", []) if t["type"] == CHECKPOINT]
    return [(x, y, x + BANNER_W, y + BANNER_H) for x, y in corners]


def checkpoint_frames(states: list, boxes: list) -> list:
    """Route frames at which the planned run touches each checkpoint first, in order."""
    out = []
    for x0, y0, x1, y1 in boxes:
        for i, s in enumerate(states):
            rx, ry = int(s[ph.X]), int(s[ph.Y])
            if rx < x1 and x0 < rx + ph.PW and ry < y1 and y0 < ry + ph.PH:
                out.append(i)
                break
    return sorted(out)


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
            jump = pending_jump > 0 and ph.can_jump(s, solids)
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


def _lands(s: tuple, m: int, jump_at, solids, kill_y: float, frames: int = 240) -> bool:
    """Hold `m` after REACT frames (until then the last direction), jump once at
    REACT + `jump_at` if possible: True if that ends standing on something."""
    for f in range(frames):
        mm = m if f >= REACT else s[ph.LASTM]
        jump = jump_at is not None and f >= REACT + jump_at and ph.can_jump(s, solids)
        if jump:
            jump_at = None
        s, down, dead = ph.apply_frame(s, mm, jump, False, solids)
        if dead or s[ph.Y] > kill_y:
            return False
        if down:
            return True
    return False


def _fall_frames(s: tuple, solids, kill_y: float) -> int:
    """Frames until a player falling from `s` without input is dead."""
    for f in range(AIR_TIME_FATAL + 1):
        s, _down, dead = ph.apply_frame(s, 0, False, False, solids)
        if dead or s[ph.Y] > kill_y:
            return f + 1
    return AIR_TIME_FATAL


def piece_outcomes(states, frames, a, b, solids, kill_y, rng, sigma, samples) -> tuple:
    """(share that gets to the planned position at b, share that dies, mean
    frames a death costs on top of the piece: the rest of the fall and the
    fade before the respawn) of noisy replays of frames[a:b]. A miss is a death
    only if no quick correction (steer either way or not at all, jump once or
    not) lands it."""
    tx, ty = states[b][ph.X], states[b][ph.Y]
    horizon = min(len(frames), b + 8)
    hits = deaths = 0
    death_frames = 0
    for _ in range(samples):
        inputs = _noisy(frames[a:horizon], rng, sigma)
        s = states[a]
        hit = dead = False
        pending_jump = 0
        for i, (m, j, d) in enumerate(inputs):
            if j:
                pending_jump = 6
            jump = pending_jump > 0 and ph.can_jump(s, solids)
            if jump:
                pending_jump = 0
            elif pending_jump:
                pending_jump -= 1
            s, _down, dd = ph.apply_frame(s, m, jump, d, solids)
            if dd or s[ph.Y] > kill_y:
                dead = True
                break
            if a + i + 1 >= b - 4 and abs(s[ph.X] - tx) <= TOLERANCE and abs(s[ph.Y] - ty) <= TOLERANCE:
                hit = True
                break
        if dead:
            death_frames += RESPAWN_DEAD_THRESHOLD
        elif not hit and not any(_lands(s, m, at, solids, kill_y) for m in (-1, 0, 1) for at in (None, 0, 8, 16)):
            dead = True
            death_frames += _fall_frames(s, solids, kill_y) + RESPAWN_DEAD_THRESHOLD
        hits += hit
        deaths += dead
    return hits / samples, deaths / samples, death_frames / deaths if deaths else 0.0


def time_to_beat(costs: list, passes: list) -> float:
    """Expected time through consecutive pieces when a death starts them over
    from the first: a run costs A on average and gets through with chance Q,
    so the time is A / Q (Wald). `costs[i]`: time spent in piece i per arrival,
    `passes[i]`: chance to get through it without dying."""
    total, reach = 0.0, 1.0
    for cost, q in zip(costs, passes):
        total += reach * cost
        reach *= q
    return total / reach if reach > 0 else float("inf")


def section_name(label: str) -> str:
    """A waypoint label without its numbers: the section of the route it belongs to."""
    return re.sub(r"\s+", " ", re.sub(r"-?\d+(\s*,\s*-?\d+)*", "", label)).strip() or label


def piece_sections(segments, waypoints, starts) -> list:
    """Section of the route each piece (by start frame) lies in."""
    bounds = [(start, start + n) for start, n in segments]
    out = []
    for a in starts:
        k = next((i for i, (s0, s1) in enumerate(bounds) if s0 <= a < s1), len(waypoints) - 1)
        out.append(section_name(waypoints[k].label))
    return out


def playtime(
    states, frames, solids, kill_y, seed, sigma, pace, chunk, sections=None, checkpoints=(), samples=PLAYTIME_SAMPLES
):
    """Expected first-clear time (minutes) and deaths: a death sends the player
    back to the last of the level's `checkpoints` (route frames) passed; with
    the manual checkpoint (P) put where it saves the most, as a tester does
    (the calibrated estimate), and without it. Plus the sections with the
    most deaths."""
    rng = random.Random(seed)
    costs, passes, deaths, starts = [], [], [], []
    for a in range(LEAD_IN, len(frames) - 1, chunk):
        b = min(a + chunk, len(frames))
        hit, die, extra = piece_outcomes(states, frames, a, b, solids, kill_y, rng, sigma, samples)
        hit = max(hit, 1e-3)
        costs.append(((b - a) * pace / 60 + die * extra / 60) / (hit + die))  # tries until through or dead
        passes.append(hit / (hit + die))
        deaths.append(die / (hit + die))
        starts.append(a)
    lead = LEAD_IN * pace / 60
    fixed = sorted({next((k for k, a in enumerate(starts) if a >= f), len(starts)) for f in checkpoints} - {0})

    def stretches(cuts):
        edges = [0, *sorted(set(cuts)), len(costs)]
        return [(e0, e1) for e0, e1 in zip(edges, edges[1:]) if e1 > e0]

    def minutes(cuts):
        return (lead + sum(time_to_beat(costs[e0:e1], passes[e0:e1]) for e0, e1 in stretches(cuts))) / 60

    def deaths_for(cuts):
        total = 0.0
        for e0, e1 in stretches(cuts):
            reach = 1.0
            for q in passes[e0:e1]:
                reach *= q
            total += 1 / reach - 1 if reach > 0 else float("inf")
        return total

    best_p = min(range(1, len(costs)), key=lambda k: minutes([*fixed, k])) if len(costs) > 1 else 0
    hot: dict = defaultdict(float)
    for name, d in zip(sections or ["route"] * len(deaths), deaths):
        hot[name] += d
    return {
        "sigma": sigma,
        "pace": pace,
        "checkpoints": len(fixed),
        "minutes": round(minutes([*fixed, best_p]), 1),
        "deaths": round(deaths_for([*fixed, best_p]), 1),
        "p_checkpoint_second": round(starts[best_p] / 60, 1) if starts else 0.0,
        "minutes_without_p": round(minutes(fixed), 1),
        "deaths_without_p": round(deaths_for(fixed), 1),
        "death_hotspots": [[k, round(v, 2)] for k, v in sorted(hot.items(), key=lambda kv: -kv[1])[:4] if v >= 0.05],
    }


def _measure(
    map_id, solids, tiles, spawn, frames, source, teleports, sigma, chunk, samples, labels, sections, times, boxes=()
):
    kill_y = (max(y for _, y in solids) + 4) * 16
    states = [ph.spawn_state(*spawn)]
    jumps = walljumps = dashes = 0
    for i, (m, j, d) in enumerate(frames):
        s = teleports.get(i, states[-1])
        states[-1] = s
        if j and ph.can_jump(s, solids):
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
    row = {
        "level": map_id,
        "source": source,
        "size": [max(xs) - min(xs) + 1, max(ys) - min(ys) + 1],
        "enemies": sum(1 for t in tiles if t["type"] == "spawners" and t["variant"] != 0),
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
    if getattr(solids, "water", None):
        row["breath_min_s"] = round(min(s[ph.BREATH] for s in states) / 60, 1)
    names = None
    if labels is not None:
        segs, wps = labels
        names = piece_sections(segs, wps, [a for _r, a in rates])
    if sections and names:
        per: dict = defaultdict(float)
        for (r, _a), name in zip(rates, names):
            per[name] += r
        row["sections"] = [[k, round(v, 2)] for k, v in sorted(per.items(), key=lambda kv: -kv[1])]
    if times:
        row["playtime"] = {
            name: playtime(
                states, frames, solids, kill_y, map_id, sg, pace, chunk, names, checkpoint_frames(states, boxes)
            )
            for name, (sg, pace) in PROFILES.items()
        }
    return row


def profile(
    map_id: int,
    sigma: float,
    chunk: int,
    samples: int,
    resample: bool = False,
    sections: bool = False,
    times: bool = False,
) -> dict:
    solids, tiles = load_map(map_id)
    spawn, route, frames, source, teleports = load_route(map_id, solids, resample)
    labels = None
    if source == "designed route":
        plan = load_plan(map_id)
        labels = (plan["segments"], plan["waypoints"])
    boxes = checkpoint_boxes(_map_data(map_id))
    return _measure(
        map_id, solids, tiles, spawn, frames, source, teleports, sigma, chunk, samples, labels, sections, times, boxes
    )


def profile_level(lv, sigma: float = 2.0, chunk: int = 24, samples: int = 30, times: bool = True) -> dict | None:
    """Profile of a tools.worlds.builder.Level that is not saved: plans its route
    (None if a waypoint cannot be reached) and measures it, sections included."""
    from tools.worlds.route import plan_route

    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
    kill_y = (max(y for _, y in solids) + 4) * 16
    res = plan_route(solids, spawn, lv.route, kill_y, verbose=False)
    if not res.ok:
        return None
    tiles = [{"type": k, "variant": v} for k, v in lv.objects.values()]
    boxes = checkpoint_boxes({"tilemap": {}, "offgrid": lv.offgrid})
    segments = [(start, n) for _label, start, n, _exp in res.segments]
    return _measure(
        lv.map_id,
        solids,
        tiles,
        spawn,
        res.frames,
        "designed route",
        {},
        sigma,
        chunk,
        samples,
        (segments, lv.route),
        True,
        times,
        boxes,
    )


def print_details(r: dict) -> None:
    """Sections and play time of a profile, as readable lines."""
    if "breath_min_s" in r:
        print(f"  level {r['level']}: least breath left on the route {r['breath_min_s']} s")
    if "sections" in r:
        print(f"  level {r['level']} sections (fails per run):")
        for name, v in r["sections"]:
            if v >= 0.05:
                print(f"    {v:5.2f}  {name}")
    for name, t in r.get("playtime", {}).items():
        hot = ", ".join(f"{k} {v}" for k, v in t["death_hotspots"])
        print(
            f"  level {r['level']} {name} (sigma {t['sigma']}, pace {t['pace']}): ~{t['minutes']} min to clear, "
            f"~{t['deaths']} deaths ({t['checkpoints']} checkpoints on the route, P at {t['p_checkpoint_second']} s; "
            f"without P {t['minutes_without_p']} min); dies most at: {hot or '-'}"
        )


def _windows_job(item) -> tuple:
    """Worker: one level's window profile, with its element lines as text."""
    import contextlib
    import io

    from tools.worlds.windows import profile_map

    lvl, climb = item
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"level {lvl}: elements (most forgiving way, narrowest window in frames):")
        timing = profile_map(lvl, verbose=True, dash_climb=climb)
    return lvl, buf.getvalue(), timing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--sigma", type=float, default=2.0, help="timing error of a key press (frames, 1 sd)")
    ap.add_argument("--chunk", type=int, default=24, help="frames a player cannot correct (reaction time)")
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--resample", action="store_true", help="treat designed routes like replays (fair comparison)")
    ap.add_argument("--sections", action="store_true", help="failures per section of a designed route")
    ap.add_argument("--playtime", action="store_true", help="estimated first-clear time per skill profile (old model)")
    ap.add_argument(
        "--windows", action="store_true", help="timing windows of the elements and the calibrated time to clear"
    )
    ap.add_argument(
        "--calibrate", action="store_true", help="fit the skill profiles to the playtests in data/ (read only)"
    )
    ap.add_argument("--json", default=None)
    ap.add_argument("--jobs", type=int, default=1, help="levels rated at once (--windows, --calibrate)")
    ap.add_argument(
        "--dash-climb", action="store_true", help="let the rating's search use the dash wall climb (for comparison)"
    )
    args = ap.parse_args()
    climb = True if args.dash_climb else None
    if args.calibrate:
        from tools.worlds.calibrate import calibrate, print_calibration

        cal = calibrate(args.levels or range(11, 27), workers=args.jobs if args.jobs > 1 else None, dash_climb=climb)
        print_calibration(cal)
        if args.json:
            with open(args.json, "w") as f:
                json.dump(cal, f, indent=2)
        return 0
    if not args.levels:
        ap.error("level ids are needed (or --calibrate)")
    rows = []
    timings = {}
    if args.windows and args.jobs > 1 and len(args.levels) > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(min(args.jobs, len(args.levels))) as pool:
            for lvl, text, timing in pool.map(_windows_job, [(lvl, climb) for lvl in args.levels]):
                print(text, end="", flush=True)
                timings[lvl] = timing
    for lvl in args.levels:
        r = profile(lvl, args.sigma, args.chunk, args.samples, args.resample, args.sections, args.playtime)
        if args.windows:
            if lvl in timings:
                r["timing"] = timings[lvl]
            else:
                from tools.worlds.windows import profile_map

                print(f"level {lvl}: elements (most forgiving way, narrowest window in frames):", flush=True)
                r["timing"] = profile_map(lvl, verbose=True, dash_climb=climb)
        rows.append(r)
        print(json.dumps(r), flush=True)
    if args.windows:
        from tools.worlds.windows import print_summary

        print("Difficulty from timing windows (calibrated on playtests, see docs/difficulty-rating-brainstorm.md):")
        for r in rows:
            print_summary(r["timing"])
        print("Previous metric (noise on the fastest route; kept for comparison):")
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
    for r in rows:
        print_details(r)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
