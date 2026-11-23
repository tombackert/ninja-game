"""Playtests from the death log against the rating's predictions.

docs/level-building-process-brainstorm.md, 5.1: "check the refitted model
against playtests: the first clear per level and the deaths from the death
log". For every level with a death log (data/deaths/<level>.jsonl, read only)
this takes the player's first clear: the time from the first entry into the
level to the first clear, the deaths and the bullet hits before it, and
whether the manual checkpoint P was used. Next to it stands what the model
expects for both profiles, with P only if the player used it.

The deaths over all levels then say how far the lapse rate is off: with the
timing error sigma kept, `fit_lapse` finds the lapse at which the model
expects as many deaths as were seen (deaths are Poisson-like: the interval
is the lapse range whose expected deaths the observed count is within 95 %
of). A handful of playtests pins nothing else.

    python -m tools.worlds.playtests [levels] [--jobs 4]

Levels are rated with the check's exact element cache, so a second run is quick.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass

from scripts import death_log


@dataclass
class Observed:
    level: str
    cleared: bool
    seconds: float  # from the first entry into the level to the first clear (or to the last line)
    deaths: int
    hits: int
    saves: int  # uses of the manual checkpoint P
    entries: int  # times the level was entered up to the clear
    stale: int  # lines of another version of the map (still counted)


def observed(level, lines: list | None = None, map_hash: str | None = None) -> Observed | None:
    """The player's first clear of a level from its death log. `tick` counts from
    each entry into the level (a new Game), on through respawns."""
    lines = death_log.read(level) if lines is None else lines
    if not lines:
        return None
    total = 0.0
    last_tick = 0
    deaths = hits = saves = 0
    entries = 1
    stale = sum(1 for ln in lines if map_hash and ln.get("map") != map_hash)
    for ln in lines:
        if ln["tick"] < last_tick:  # ticks start over: the level was entered again
            total += last_tick
            entries += 1
        last_tick = ln["tick"]
        kind = ln["event"]
        if kind == "death":
            deaths += 1
        elif kind == "hit":
            hits += 1
        elif kind == "save":
            saves += 1
        elif kind == "clear":
            return Observed(str(level), True, (total + last_tick) / 60, deaths, hits, saves, entries, stale)
    return Observed(str(level), False, (total + last_tick) / 60, deaths, hits, saves, entries, stale)


def map_hash(level) -> str | None:
    import hashlib

    try:
        with open(f"data/maps/{level}.json", "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:12]
    except OSError:
        return None


def rated(level) -> tuple[list, list]:
    """(elements, banner cuts) of a level, rated with the check's element cache.
    Banners the rating's programs pass by are placed by the designed route."""
    from tools.worlds import physics as ph
    from tools.worlds import windows as W
    from tools.worlds.assess import _map_data, checkpoint_boxes, checkpoint_frames, load_map
    from tools.worlds.cache import element_store
    from tools.worlds.check import route_cuts
    from tools.worlds.route import load_plan

    solids, _tiles = load_map(level)
    plan = load_plan(level)
    els = W.analyse_route(
        solids, plan["spawn"], plan["waypoints"], plan["frame_list"], plan["segments"], cache=element_store()
    )
    boxes = checkpoint_boxes(_map_data(level))
    cuts = W.checkpoint_cuts(els, boxes, solids) if boxes else []
    if len(cuts) < len(boxes):
        s = ph.spawn_state(*plan["spawn"])
        states = [s]
        for m, j, d in plan["frame_list"]:
            s = ph.apply_frame(s, m, j, d, solids)[0]
            states.append(s)
        arrivals = [a + n for a, n in plan["segments"]]
        cuts = set(route_cuts(els, checkpoint_frames(states, boxes), arrivals))
        if len(cuts) < len(boxes):
            # banners the route passes by too (the calibration course's gates): by place, west to
            # east: each stands before the first element that ends east of it
            for x0, _y0, _x1, _y1 in boxes:
                k = next((i for i, e in enumerate(els) if plan["waypoints"][e.last].x0 * 16 >= x0), None)
                if k:
                    cuts.add(k)
        cuts = sorted(cuts)
    return els, cuts


def _rated_job(level):
    els, cuts = rated(level)
    slim = [(e.label, round(e.seconds, 3), [w.width for w in e.windows], list(e.fatal)) for e in els]
    return level, slim, cuts


def _elements(slim: list) -> list:
    from tools.worlds.compose import Composed, Press

    return [Composed(label, s, [Press(w) for w in ws], f) for label, s, ws, f in slim]


def predicted(els: list, cuts: list, profile: dict, with_p: bool) -> tuple[float, float]:
    """(seconds, deaths) to the first clear the model expects."""
    from tools.worlds.windows import first_clear

    fc = first_clear(els, profile, cuts)
    if with_p:
        return fc["minutes"] * 60, fc["deaths"]
    return fc["minutes_without_p"] * 60, fc["deaths_without_p"]


def fit_lapse(cases: list, profile: dict) -> dict:
    """The lapse rate at which the model expects the deaths that were seen, over
    `cases` [(elements, cuts, with_p, deaths seen)], with the profile's sigma kept."""
    seen = sum(c[3] for c in cases)

    def expected(lapse):
        prof = {**profile, "lapse": lapse}
        return sum(predicted(els, cuts, prof, with_p)[1] for els, cuts, with_p, _d in cases)

    grid = [round(0.0025 * i, 4) for i in range(81)]  # 0 .. 0.2
    table = [(lp, expected(lp)) for lp in grid]
    best = min(table, key=lambda t: abs(t[1] - seen))

    def poisson_ok(mu):  # seen is within the central 95 % of Poisson(mu)
        if mu <= 0:
            return seen == 0
        p, cdf = math.exp(-mu), 0.0
        for k in range(seen):
            cdf += p
            p *= mu / (k + 1)
        return cdf <= 0.975 and cdf + p >= 0.025

    ok = [lp for lp, mu in table if poisson_ok(mu)]
    return {
        "deaths_seen": seen,
        "expected_now": round(expected(profile.get("lapse", 0.0)), 1),
        "lapse": best[0],
        "lapse_range": [min(ok), max(ok)] if ok else None,
    }


def main() -> int:
    from tools.worlds.windows import PROFILES

    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    levels = args.levels or sorted(
        (f[:-6] for f in os.listdir(death_log.DEATHS_DIR) if f.endswith(".jsonl")), key=lambda s: (len(s), s)
    )
    obs = {lv: observed(lv, map_hash=map_hash(lv)) for lv in levels}
    cleared = [lv for lv in levels if obs[lv] is not None and obs[lv].cleared]
    for lv in levels:
        o = obs[lv]
        if o is not None and not o.cleared:
            print(f"level {lv}: not cleared ({o.seconds:.0f} s, {o.deaths} deaths, {o.hits} hits): left out")
    if not cleared:
        return 0
    if args.jobs > 1 and len(cleared) > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(min(args.jobs, len(cleared))) as pool:
            ratings = {lv: (slim, cuts) for lv, slim, cuts in pool.map(_rated_job, cleared)}
    else:
        ratings = {lv: _rated_job(lv)[1:] for lv in cleared}
    print(
        f"{'level':>11} {'seen: min':>9} {'deaths':>6} {'hits':>4} {'P':>2}   "
        f"{'expert: min':>11} {'deaths':>6}   {'average: min':>12} {'deaths':>6}"
    )
    cases = []
    rows = []
    for lv in cleared:
        o = obs[lv]
        els = _elements(ratings[lv][0])
        cuts = ratings[lv][1]
        with_p = o.saves > 0
        e = predicted(els, cuts, PROFILES["expert"], with_p)
        a = predicted(els, cuts, PROFILES["average"], with_p)
        cases.append((els, cuts, with_p, o.deaths))
        rows.append({"level": lv, "seen_s": round(o.seconds, 1), "deaths": o.deaths, "expert": e, "average": a})
        note = f"  ({o.stale} lines of another map version)" if o.stale else ""
        print(
            f"{lv:>11} {o.seconds / 60:>9.1f} {o.deaths:>6} {o.hits:>4} {'y' if with_p else 'n':>2}   "
            f"{e[0] / 60:>11.1f} {e[1]:>6.1f}   {a[0] / 60:>12.1f} {a[1]:>6.1f}{note}"
        )
    seen_s = sum(r["seen_s"] for r in rows)
    for name in ("expert", "average"):
        fit = fit_lapse(cases, PROFILES[name])
        pred_s = sum(r[name][0] for r in rows)
        rng = fit["lapse_range"]
        print(
            f"{name}: {fit['expected_now']} deaths expected, {fit['deaths_seen']} seen; time {pred_s / 60:.1f} min "
            f"expected, {seen_s / 60:.1f} seen. Lapse that fits the deaths (sigma {PROFILES[name]['sigma']} kept): "
            f"{fit['lapse']}" + (f" (95 %: {rng[0]}-{rng[1]})" if rng else "")
        )
    os.makedirs(os.path.join("out", "playtests"), exist_ok=True)
    with open(os.path.join("out", "playtests", "report.json"), "w") as f:
        json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
