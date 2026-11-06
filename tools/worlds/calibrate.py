"""Real playtests, re-played in the physics replica, to calibrate tools/worlds/windows.

A replay (data/replays/<id>.json, data/replays/last_runs/<id>.json) holds the
recorded key events of a run (one tick per frame) and the player's state
every 10 frames. The recording starts over at every respawn, so a replay is
the last life of a run: from the spawn (or a checkpoint) to the flag.

Two ambiguities are resolved against the snapshots: Space (dash) and Up/W
(jump) are both recorded as "jump", and a mouse dash is not recorded at all.
Every 10 frames all readings of the presses in between (jump, dash, both,
nothing) are tried and the one that ends in the next snapshot's state is
kept; a dash started without any key event (the mouse) is put where the
snapshot's dash counter says it began. Moon Boots (gear: one weaker air
jump, recharged on landing) are replayed too, as the replica has no gear.
`HumanRun.fidelity` counts snapshots met exactly; all of levels 11-26 are.

Then the run is laid over a level's elements (tools/worlds/windows): where
it reached each element's waypoints, how long it took and the timing
window of every press the player made there (the same measure as for the
most forgiving program, so the two compare).

`--calibrate` (python -m tools.worlds.assess --calibrate) fits the skill
profiles to these runs and the times between first clears in
data/best_times.json (`calibrate`, `print_calibration`); the data is only read.
"""

from __future__ import annotations

import itertools
import json
import math
import os
from dataclasses import dataclass, field

from scripts.constants import AIR_JUMP_VELOCITY
from tools.worlds import physics as ph

REPLAYS = "data/replays"
CHOICES = ("jump", "dash", "both", "none")


def _snap_state(p: dict, lastm: int) -> tuple:
    return (
        p["pos"][0],
        p["pos"][1],
        p["velocity"][0],
        p["velocity"][1],
        p["air_time"],
        p["jumps"],
        p["wall_slide"],
        p["dashing"],
        p["flip"],
        lastm,
        p.get("breath", ph.spawn_state(0, 0)[ph.BREATH]),
        p.get("swim_cooldown", 0),
    )


def moon_frame(s: tuple, air_jumps: int, m: int, jump: bool, dash: bool, solids) -> tuple:
    """`physics.apply_frame` with Moon Boots: a jump with none left, off any wall
    and out of the water, is an air jump (AIR_JUMP_VELOCITY), once until the
    player lands or dives. Returns (state, air jumps left, down, dead, air jumped)."""
    used = False
    if jump:
        s2 = ph.press_jump(s, solids)
        if s2 is s and air_jumps > 0 and not s[ph.WALL]:
            flow, _wet = ph.water_at(s[ph.X], s[ph.Y], solids.water)
            if flow is None:
                s2 = s[: ph.VY] + (AIR_JUMP_VELOCITY, 5) + s[ph.AIR + 1 :]
                air_jumps -= 1
                used = True
        s = s2
    if dash:
        s = ph.press_dash(s)
    _flow, wet = ph.water_at(s[ph.X], s[ph.Y], solids.water)
    s, down, dead = ph.step(s, m, solids)
    if down or wet:
        air_jumps = 1
    return s, air_jumps, down, dead, used


@dataclass
class HumanRun:
    level: int
    path: str
    frames: list = field(default_factory=list)  # (m, jump, dash) per frame, effective presses only
    states: list = field(default_factory=list)  # state before each frame (len(frames) + 1)
    downs: list = field(default_factory=list)  # standing after each frame
    air_jumps: list = field(default_factory=list)  # frames with a Moon Boots air jump
    fidelity: tuple = (0, 0)  # (snapshots met exactly, snapshots compared)
    lives: tuple = (0, 0)  # at the start and the end of the recording
    start_tick: int = 0

    @property
    def seconds(self) -> float:
        return len(self.frames) / 60


def replay_path(level: int, kind: str = "last") -> str:
    if kind == "best":
        return os.path.join(REPLAYS, f"{level}.json")
    return os.path.join(REPLAYS, "last_runs", f"{level}.json")


def human_run(level: int, path: str | None = None, solids=None) -> HumanRun:
    """Re-play a recorded run in the replica (see the module doc)."""
    if solids is None:
        from tools.worlds.assess import load_map

        solids, _tiles = load_map(level)
    path = path or replay_path(level)
    with open(path) as f:
        data = json.load(f)
    snaps = {int(t): s["players"][0] for t, s in data["snapshots"].items() if s.get("players")}
    acts = {e["tick"]: e["inputs"] for e in data["inputs"] if e["inputs"]}
    n = data["duration_frames"]
    held: dict = {}
    for e in data["inputs"]:
        for a in e["inputs"]:
            for i, key in enumerate(("left", "right")):
                if i not in held and a in (key, "stop_" + key):
                    held[i] = a == "stop_" + key  # first seen released: held from the start
    left, right = held.get(0, False), held.get(1, False)
    dash_starts = set()
    for t, p in snaps.items():
        d = p["dashing"]
        prev = snaps.get(t - 10, {}).get("dashing", 0)
        if d and prev != d + (10 if d > 0 else -10):
            dash_starts.add(t - (60 - abs(d)))
    t0 = min(snaps)
    s = _snap_state(snaps[t0], int(right) - int(left))
    air_jumps = 1
    run = HumanRun(level, path, start_tick=t0)
    run.states.append(s)
    run.lives = (snaps[t0]["lives"], snaps[max(snaps)]["lives"])
    exact = compared = 0
    t = t0
    while t < n:
        t1 = min(n, (t // 10 + 1) * 10)
        amb = [u for u in range(t, t1) for a in acts.get(u, ()) if a == "jump"][:5]
        best = None
        for combo in itertools.product(CHOICES, repeat=len(amb)):
            reading: dict = {}
            for u, c in zip(amb, combo):
                reading.setdefault(u, set()).add(c)
            cs, l_, r_, aj = s, left, right, air_jumps
            out = []
            for u in range(t, t1):
                for a in acts.get(u, ()):
                    if a in ("left", "right", "stop_left", "stop_right"):
                        on = not a.startswith("stop_")
                        if a.endswith("left"):
                            l_ = on
                        else:
                            r_ = on
                got = reading.get(u, set())
                jump = bool(got & {"jump", "both"})
                dash = bool(got & {"dash", "both"}) or (u in dash_starts and u not in reading)
                m = int(r_) - int(l_)
                before = cs
                cs, aj, down, dead, used = moon_frame(cs, aj, m, jump, dash, solids)
                out.append((m, jump, dash, before, cs, down, used))
            err = 0.0
            if t1 in snaps:
                p = snaps[t1]
                err = (
                    abs(cs[ph.X] - p["pos"][0])
                    + abs(cs[ph.Y] - p["pos"][1])
                    + abs(cs[ph.VX] - p["velocity"][0])
                    + abs(cs[ph.VY] - p["velocity"][1])
                    + 10 * (cs[ph.DASH] != p["dashing"])
                )
            err += 1e-9 * sum(c != "jump" for c in combo)  # the plainest reading on a tie
            if best is None or err < best[0]:
                best = (err, out, l_, r_, aj)
        err, out, left, right, air_jumps = best
        for m, jump, dash, before, after, down, used in out:
            # keep the presses that did something: a jump that took off, a dash that started
            eff_jump = jump and (used or ph.press_jump(before, solids) is not before)
            eff_dash = dash and before[ph.DASH] == 0
            if used:
                run.air_jumps.append(len(run.frames))
            run.frames.append((m, eff_jump, eff_dash))
            run.states.append(after)
            run.downs.append(down)
        if t1 in snaps:
            compared += 1
            exact += err < 1e-6
            s = _snap_state(snaps[t1], int(right) - int(left))
            if err >= 1e-6:  # off the recording: carry on from the snapshot
                run.states[-1] = s
        else:
            s = out[-1][4] if out else s
        t = t1
    run.fidelity = (exact, compared)
    return run


# --- a run laid over a level's elements ---------------------------------------------


def visits(run: HumanRun, route: list) -> list:
    """Frames played when the run first reached each waypoint (in order; None if
    it never did, e.g. it went past a ledge without standing on it)."""
    out, i = [], 0
    for wp in route:
        found = None
        for j in range(i, len(run.frames)):
            if wp.contains(run.states[j + 1], run.downs[j]):
                found = j + 1
                break
        out.append(found)
        if found is not None:
            i = found
    return out


@dataclass
class HumanElement:
    first: int  # waypoint indices (elements merged where the run missed a waypoint)
    last: int
    label: str
    frames: int  # frames the player spent on it
    windows: list | None  # None: an air jump (Moon Boots) the replica cannot shift
    air_jump: bool = False

    @property
    def narrowest(self) -> int | None:
        from tools.worlds.windows import narrowest

        return None if self.windows is None else narrowest(self.windows)


def human_elements(run: HumanRun, route: list, spans: list, solids) -> list[HumanElement]:
    """The run cut at the same waypoints as the level's elements (`spans`), each
    piece with the timing windows of the presses the player made in it."""
    from tools.worlds.windows import element_label, press_windows

    v = visits(run, route)
    out = []
    begin = 0
    cur = None
    air = set(run.air_jumps)
    for a, b in spans:
        cur = a if cur is None else cur
        if v[b] is None or v[b] <= begin:
            continue
        goals = [route[k] for k in range(cur, b + 1) if v[k] is not None and v[k] > begin]
        program = run.frames[begin : v[b]]
        aj = any(begin <= f < v[b] for f in air)
        ws = None if aj else press_windows(run.states[begin], program, goals, solids)
        out.append(HumanElement(cur, b, element_label(route, cur, b), v[b] - begin, ws, aj))
        begin, cur = v[b], None
    return out


# --- the playtests ---------------------------------------------------------------------

BEST_TIMES = "data/best_times.json"
SESSION_GAP = 15 * 60  # seconds between two clears that still count as one session
OVERHEAD_S = 2.0  # seconds between a clear and the next level's start (level-complete screen)

# What the files cannot tell: who played, and the player's own account.
PLAYERS = {
    "expert": "the main tester (experienced gamer), levels 11-25 in one session on 2026-11-03",
    "average": "the developer (less skilled), level 26 on 2026-11-05: first try, no fall, one life lost to a bullet",
}
PLAYED_BY = {26: "average"}  # levels whose playtest was not the main tester's
FIRST_TRY = {26: True}  # first clears known from the players themselves
BREAKS = {12}  # gaps that hold a break, not attempts (12.3 min for a 1.9 min level)


@dataclass
class Observation:
    level: int
    player: str
    run_s: float  # the clearing run (the last life)
    gap_s: float | None  # since the clear before it in the same session
    first_try: bool | None  # cleared without a death before (wasted time ~0)
    lives_lost: int
    air_jumps: int
    break_: bool = False

    @property
    def minutes(self) -> float | None:
        return None if self.gap_s is None else (self.gap_s - OVERHEAD_S) / 60


def _stamp(s: str) -> float:
    import datetime

    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()


def observations(levels=range(11, 27)) -> list[Observation]:
    """The playtests in data/ (read only): clear times from best_times.json, or the
    last run's file time where the clear was no new best; the runs themselves from
    data/replays/last_runs. A run the replica does not play back exactly (a
    snapshot missed: the map has changed since) is left out."""
    with open(BEST_TIMES) as f:
        best = json.load(f)
    clears, runs = {}, {}
    for lv in levels:
        path = replay_path(lv)
        if not os.path.exists(path):
            continue
        run = human_run(lv)
        if run.fidelity[0] < run.fidelity[1]:
            continue  # recorded on another version of the map
        runs[lv] = run
        mtime = os.path.getmtime(path)
        entry = best.get(str(lv))
        stamp = _stamp(entry["timestamp"]) if entry else None
        clears[lv] = stamp if stamp is not None and abs(stamp - mtime) < 120 else mtime
    order = sorted(clears, key=clears.get)
    out = []
    for i, lv in enumerate(order):
        prev = clears[order[i - 1]] if i else None
        gap = clears[lv] - prev if prev is not None and clears[lv] - prev < SESSION_GAP else None
        player = PLAYED_BY.get(lv, "expert")
        run = runs[lv]
        first = FIRST_TRY.get(lv)
        if first is None and gap is not None and lv not in BREAKS:
            first = gap - run.seconds - OVERHEAD_S < 10
        out.append(
            Observation(
                lv,
                player,
                round(run.seconds, 1),
                None if gap is None else round(gap, 1),
                first,
                run.lives[0] - run.lives[1],
                len(run.air_jumps),
                lv in BREAKS,
            )
        )
    return sorted(out, key=lambda o: o.level)


# --- fitting the skill profiles ------------------------------------------------------


def _analyse(level: int) -> dict:
    """Worker: a level's elements, and the playtest run cut into the same elements."""
    from tools.worlds.assess import _map_data, checkpoint_boxes, load_map
    from tools.worlds.route import load_plan
    from tools.worlds.windows import analyse_route

    solids, _tiles = load_map(level)
    plan = load_plan(level)
    els = analyse_route(solids, plan["spawn"], plan["waypoints"], plan["frame_list"], plan["segments"])
    spans = [(e.first, e.last) for e in els]
    humans = []
    if os.path.exists(replay_path(level)):
        humans = human_elements(human_run(level, solids=solids), plan["waypoints"], spans, solids)
    return {
        "level": level,
        "elements": els,
        "route_frames": len(plan["frame_list"]),
        "boxes": checkpoint_boxes(_map_data(level)),
        "humans": humans,
        "solids": solids,
    }


def analyse_levels(levels, workers: int | None = None) -> dict:
    """`_analyse` for many levels, in parallel."""
    from concurrent.futures import ProcessPoolExecutor

    levels = list(levels)
    if len(levels) == 1 or workers == 1:
        return {lv: _analyse(lv) for lv in levels}
    with ProcessPoolExecutor(max_workers=workers or min(len(levels), os.cpu_count() or 1)) as pool:
        return {r["level"]: r for r in pool.map(_analyse, levels)}


SIGMAS = [round(0.2 + 0.1 * i, 1) for i in range(19)]  # 0.2 .. 2.0 frames
LAPSES = [round(0.01 * i, 2) for i in range(16)]  # 0 .. 0.15 per press
SKILL_GAP = 1.5  # timing error and lapse rate of the "average" profile over the expert's (one playtest cannot fit it)


def _cuts(d: dict) -> list:
    from tools.worlds.windows import checkpoint_cuts

    return checkpoint_cuts(d["elements"], d["boxes"], d["solids"]) if d["boxes"] else []


def fit_precision(data: dict, obs: list, player: str, base: dict) -> dict:
    """Timing error sigma and lapse rate that reproduce the player's session: the
    number of levels cleared without a death before (the sum of the predicted
    chances of a clean first try) and the minutes lost to failed attempts (the
    predicted time to the first clear less a clean run), both over the whole
    session. Matching totals, not level by level: deaths are few and scattered."""
    from tools.worlds.windows import first_clear

    rows = [o for o in obs if o.player == player and o.first_try is not None and not o.break_ and o.level in data]
    if not rows:
        return {}
    cuts = {o.level: _cuts(data[o.level]) for o in rows}
    first_obs = sum(1 for o in rows if o.first_try)
    lost_obs = sum(max(0.0, (o.gap_s or o.run_s) - o.run_s - OVERHEAD_S) for o in rows) / 60
    best = None
    for sigma in SIGMAS:
        for lapse in LAPSES:
            prof = {**base, "sigma": sigma, "lapse": lapse}
            first = lost = 0.0
            for o in rows:
                fc = first_clear(data[o.level]["elements"], prof, cuts[o.level])
                first += fc["first_try"]
                lost += fc["minutes"] - fc["clean_run_minutes"]
            err = ((first - first_obs) / len(rows)) ** 2 + math.log((lost + 0.2) / (lost_obs + 0.2)) ** 2
            if best is None or err < best[0]:
                best = (err, sigma, lapse, first, lost)
    _err, sigma, lapse, first, lost = best
    return {
        "sigma": sigma,
        "lapse": lapse,
        "levels": len(rows),
        "first_tries": [round(first, 1), first_obs],
        "minutes_lost": [round(lost, 1), round(lost_obs, 1)],
    }


def fit_pace(data: dict, obs: list, player: str) -> dict:
    """The player's clearing runs against the most forgiving programs: pace (total
    time over total time) and, by least squares over the elements cut the same
    way in both, the seconds the player adds before a press of PAUSE_WINDOW
    frames or less (it comes out small: the stop before a hard move is already
    in the programs, which start standing still)."""
    from tools.worlds.windows import PAUSE_WINDOW

    run = model = 0.0
    sxx = sxk = skk = sxy = sky = 0.0
    for o in obs:
        if o.player != player or o.level not in data:
            continue
        run += o.run_s
        model += sum(e.seconds for e in data[o.level]["elements"])
        by_span = {(e.first, e.last): e for e in data[o.level]["elements"]}
        for h in data[o.level]["humans"]:
            e = by_span.get((h.first, h.last))
            if e is None:
                continue
            x, k, y = e.seconds, sum(1 for w in e.windows if w.width <= PAUSE_WINDOW), h.frames / 60
            sxx, sxk, skk, sxy, sky = sxx + x * x, sxk + x * k, skk + k * k, sxy + x * y, sky + k * y
    det = sxx * skk - sxk * sxk
    pause = (sxx * sky - sxk * sxy) / det if det > 1e-9 else 0.0
    return {"pace": round(run / model, 2) if model else 1.0, "pause_fit": round(pause, 2)}


def calibrate(levels=range(11, 27), workers: int | None = None, data: dict | None = None) -> dict:
    """Fit the profiles to the playtests and compare predictions with them
    (`data`: analyse_levels output, if already at hand)."""
    from tools.worlds.windows import PROFILES, first_clear, window_profile

    obs = observations(levels)
    data = data or analyse_levels([o.level for o in obs], workers)
    fitted, fits = {}, {}
    expert_pace = fit_pace(data, obs, "expert")
    fits["expert"] = {**expert_pace, **fit_precision(data, obs, "expert", {"pace": expert_pace["pace"]})}
    fitted["expert"] = {k: fits["expert"].get(k, PROFILES["expert"][k]) for k in ("sigma", "pace", "lapse")}
    fitted["expert"]["pause"] = 0.0
    avg_pace = fit_pace(data, obs, "average")
    fits["average"] = {
        **avg_pace,
        "sigma": round(SKILL_GAP * fitted["expert"]["sigma"], 2),
        "lapse": round(SKILL_GAP * fitted["expert"]["lapse"], 3),
    }
    fitted["average"] = {
        "sigma": fits["average"]["sigma"],
        "pace": avg_pace["pace"] if any(o.player == "average" for o in obs) else PROFILES["average"]["pace"],
        "lapse": fits["average"]["lapse"],
        "pause": 0.0,
    }
    rows = []
    for o in obs:
        d = data[o.level]
        els = d["elements"]
        fc = first_clear(els, fitted[o.player], _cuts(d))
        by_span = {(e.first, e.last): e for e in els}
        pairs = [
            (by_span[(h.first, h.last)].narrowest, h.narrowest) for h in d["humans"] if (h.first, h.last) in by_span
        ]
        pairs = [(m, h) for m, h in pairs if h is not None]
        rows.append(
            {
                "level": o.level,
                "player": o.player,
                "elements": len(els),
                "windows": window_profile(els),
                "model_clean_s": round(sum(e.seconds for e in els), 1),
                "run_s": o.run_s,
                "observed_min": None if o.minutes is None or o.break_ else round(o.minutes, 2),
                "first_try": o.first_try,
                "predicted_min": fc["minutes"],
                "predicted_min_without_p": fc["minutes_without_p"],
                "predicted_deaths": fc["deaths"],
                "p_first_try": fc["first_try"],
                "lives_lost": o.lives_lost,
                "air_jumps": o.air_jumps,
                "human_elements": len(d["humans"]),
                "compared": len(pairs),
                "human_wider": sum(1 for m, h in pairs if h > m),
                "model_wider": sum(1 for m, h in pairs if m > h),
                "human_narrowest": min((h for _m, h in pairs), default=None),
                "model_narrowest": min((e.narrowest for e in els), default=None),
                "pairs": pairs,
                "hard_model": [[e.label, e.narrowest] for e in els if e.narrowest <= 4],
                "hard_human": [
                    [h.label, h.narrowest] for h in d["humans"] if h.narrowest is not None and h.narrowest <= 4
                ],
            }
        )
    return {"profiles": fitted, "fits": fits, "rows": rows, "players": PLAYERS}


def print_calibration(cal: dict) -> None:
    for name, p in cal["profiles"].items():
        fit = cal["fits"].get(name, {})
        extra = ""
        if "first_tries" in fit:
            extra = (
                f"; session: clean first tries {fit['first_tries'][0]} predicted / {fit['first_tries'][1]} seen, "
                f"minutes lost to failed attempts {fit['minutes_lost'][0]} / {fit['minutes_lost'][1]}"
            )
        print(
            f"profile {name} ({cal['players'][name]}): sigma {p['sigma']} frames, lapse {p['lapse']}, "
            f"pace {p['pace']} (fitted pause before a tight press {fit.get('pause_fit', '-')} s){extra}"
        )
    print(
        f"{'level':>5} {'who':>7} {'elem':>4} {'<=2':>3} {'<=4':>3} {'<=8':>3} {'run s':>6} {'safe s':>6} "
        f"{'obs min':>7} {'pred min':>8} {'1st try':>7} {'p(1st)':>6} {'deaths':>6}  presses of the run vs the model"
    )
    for r in cal["rows"]:
        w = r["windows"]
        obs = "-" if r["observed_min"] is None else f"{r['observed_min']:.1f}"
        first = {True: "yes", False: "no", None: "?"}[r["first_try"]]
        print(
            f"{r['level']:>5} {r['player']:>7} {r['elements']:>4} {w['le2']:>3} {w['le4']:>3} {w['le8']:>3} "
            f"{r['run_s']:>6.0f} {r['model_clean_s']:>6.0f} {obs:>7} {r['predicted_min']:>8.1f} {first:>7} "
            f"{r['p_first_try']:>6.2f} {r['predicted_deaths']:>6.2f}  "
            f"{r['compared']} elements: run wider {r['human_wider']}, model wider {r['model_wider']}; "
            f"narrowest run {r['human_narrowest']}, model {r['model_narrowest']}"
        )
