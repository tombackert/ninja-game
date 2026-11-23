"""The calibration course: graded elements, played by a person, to refit the rating.

docs/level-building-process-brainstorm.md, 5.1 ("The calibration course").
A short test map outside the campaign. It holds element families from the
library (tools/worlds/library.py) at graded windows, each over the void, so a
miss is a death, with a checkpoint banner in front of every element, so a
death costs only that element. The death log (scripts/death_log.py) then
gives attempts and deaths per element: a death after banner k is a miss of
element k, and reaching banner k + 1 (or the flag) is a pass.

`fit` turns the counts into the model's parameters. Per element the model
gives the chance that an attempt (one that ends in a pass or a death; a
non-fatal miss is only a retry and leaves no line in the log) ends in a
death: die / (hit + die) from `windows.element_odds`. The timing error sigma
and the lapse rate are fitted by maximum likelihood over all elements, then
per element family; a likelihood-ratio test says whether the families need
parameters of their own. The table per window class answers the question
decision D2 put: does the window matter between 2 and 13 frames?

    python -m tools.worlds.course measure [--jobs 7]   # the library points it picks from
    python -m tools.worlds.course build                # write data/maps/calibration.json and its plan
    python app.py --map calibration                    # play it (the death log is on)
    python -m tools.worlds.course fit                  # deaths per element and the refit
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass

from tools.worlds import library as L

WINDOWS = (2, 4, 8, 13)  # the window classes the course grades each family at
FLOOR = 30  # floor row of the spawn ledge

# Library points the course picks from, per family (measured once: `measure`).
CANDIDATES = {
    "gap": [{"gap": g, "dh": dh} for g in (6, 7, 8, 9) for dh in (-1, 0, 1, 2)],
    "chimney": [{"width": w, "height": h} for w in (1, 2, 3) for h in (6, 8, 10)],
    "hook": [{"drop": d, "gap": g} for d in (2, 3, 4) for g in (1, 2, 3, 4)],
    "pillars": [{"count": 3, "spacing": s, "width": 1, "dh": dh} for s in (3, 4, 5, 6) for dh in (0, 1)],
}


# --- choosing and building --------------------------------------------------------------------


def measure(jobs: int = 1) -> dict:
    """Measure every candidate point (cached in the library)."""
    return {kind: L.grid(kind, points, jobs) for kind, points in CANDIDATES.items()}


def pick(results: dict, windows=WINDOWS) -> list[dict]:
    """Per family and window class, the measured point whose narrowest window is
    closest to it (each point once, trick elements left out); in the course's
    order: families one after another, easiest first."""
    out = []
    for kind, rs in results.items():
        ok = [r for r in rs if r.get("ok") and not r.get("trick")]
        used = set()
        for w in windows:
            best = min(
                (r for r in ok if L._point_key(r["params"]) not in used),
                key=lambda r: (abs(r["narrowest"] - w), -r["exposed"], r["seconds"]),
                default=None,
            )
            if best is None or abs(best["narrowest"] - w) > max(2, w // 2):
                continue
            used.add(L._point_key(best["params"]))
            out.append({"kind": kind, **best["params"], "label": f"{kind} {len(used)}", "_window": best["narrowest"]})
    order = {k: i for i, k in enumerate(results)}
    out.sort(key=lambda sp: (order[sp["kind"]], -sp["_window"]))
    return out


def outline(picks: list[dict], map_id: int) -> dict:
    """The course as a composer outline: a banner and a walk before every element."""
    elements = []
    for sp in picks:
        elements.append({"banner": True, "back": 5, "gate": True})
        elements.append({k: v for k, v in sp.items() if not k.startswith("_")})
    return {"level": map_id, "elements": elements}


def build(map_id: int, picks: list[dict]):
    """The course as a builder.Level: a spawn ledge, then per element a banner on
    the ledge before it (in a low gate, so it cannot be jumped over), the element
    over the void and a ledge after it; the flag at the end."""
    from tools.worlds.builder import Level
    from tools.worlds.compose import stamp

    lv = Level(map_id, "stone")
    lv.rect(0, FLOOR, 9, FLOOR + L.LEDGE)
    lv.spawn(3, FLOOR - 1)
    x, y = stamp(lv, outline(picks, map_id)["elements"], 10, FLOOR, ledge=10)
    lv.rect(x, y, x + 5, y + L.LEDGE)
    lv.flag(x + 3, y - 1)
    lv.wp(x + 3, y - 1, label="flag")
    return lv


# --- the death log against the course ------------------------------------------------------------


@dataclass
class Count:
    element: int
    label: str
    deaths: int = 0
    passes: int = 0

    @property
    def attempts(self) -> int:
        return self.deaths + self.passes


def counts(lines: list[dict], n_elements: int, labels=None, map_hash: str | None = None, banner_xs=None) -> list[Count]:
    """Deaths and passes per element from a death log: element k lies between
    banner k and banner k + 1 (the flag, for the last). A death there is a miss
    of element k; getting beyond banner k + 1 in a run is a pass of k. A run ends
    with a clear, a quit or a restart (no life left).

    With `banner_xs` (px, west to east) the place decides: the element a line
    belongs to is the last banner west of its position. That holds even when a
    player jumped past a banner without touching it. Without it, the furthest
    banner touched decides."""
    out = [Count(k, labels[k] if labels else str(k)) for k in range(n_elements)]
    run_max = -1

    def where(ln) -> list:
        """Banners (indices) the line's place lies beyond."""
        if banner_xs is None:
            return ln.get("checkpoints") or []
        x = ln["pos"][0]
        return [k for k, bx in enumerate(banner_xs) if bx <= x + 16]

    def close(cleared: bool):
        top = n_elements if cleared else run_max
        for k in range(min(top, n_elements)):
            out[k].passes += 1

    session = None
    for ln in lines:
        if map_hash is not None and ln.get("map") != map_hash:
            continue
        if ln.get("session") != session:
            if session is not None:
                close(False)
            session, run_max = ln.get("session"), -1
        reached = where(ln)
        if ln["event"] == "death":
            k = max(reached) if reached else None  # before the first banner: off the spawn ledge
            if k is not None and k < n_elements:
                out[k].deaths += 1
            run_max = max(run_max, max(reached, default=-1))
            if ln.get("restart"):
                close(False)
                run_max = -1
        elif ln["event"] in ("clear", "quit"):
            run_max = max(run_max, max(reached, default=-1))
            close(ln["event"] == "clear")
            run_max = -1
    return out


# --- the fit ---------------------------------------------------------------------------------------

SIGMAS = [round(0.1 + 0.05 * i, 2) for i in range(39)]  # 0.1 .. 2.0 frames
LAPSES = [round(0.005 * i, 3) for i in range(41)]  # 0 .. 0.2 per press


def death_chance(presses: list, sigma: float, lapse: float) -> float:
    """Chance that an attempt at an element (one ending in a pass or a death) ends in a death."""
    from tools.worlds.windows import element_odds

    hit, die = element_odds(presses, sigma, lapse)
    return die / (hit + die) if hit + die > 0 else 0.0


def log_likelihood(data: list, sigma: float, lapse: float) -> float:
    """data: [(presses, deaths, passes)] per element."""
    ll = 0.0
    for presses, d, p in data:
        q = min(max(death_chance(presses, sigma, lapse), 1e-9), 1 - 1e-9)
        ll += d * math.log(q) + p * math.log(1 - q)
    return ll


def fit_grid(data: list) -> dict:
    """Maximum likelihood sigma and lapse on the grid, with the 95 % region
    (log-likelihood within 1.92 of the best)."""
    table = {(s, lp): log_likelihood(data, s, lp) for s in SIGMAS for lp in LAPSES}
    (s, lp), best = max(table.items(), key=lambda kv: kv[1])
    near = [k for k, v in table.items() if best - v <= 1.92]
    return {
        "sigma": s,
        "lapse": lp,
        "ll": round(best, 3),
        "sigma_range": [min(k[0] for k in near), max(k[0] for k in near)],
        "lapse_range": [min(k[1] for k in near), max(k[1] for k in near)],
    }


def chi2_sf(x: float, k: int) -> float:
    """P(chi-square with k degrees of freedom > x), by the regularized gamma series."""
    if x <= 0:
        return 1.0
    a, z = k / 2.0, x / 2.0
    term = total = 1.0 / a
    n = 1
    while term > 1e-12 * total and n < 500:
        term *= z / (a + n)
        total += term
        n += 1
    lower = total * math.exp(-z + a * math.log(z) - math.lgamma(a))
    return max(0.0, 1.0 - lower)


def wilson(d: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = d / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, c - h), min(1.0, c + h))


def fit(elements: list, cs: list[Count], families=None, profile=None) -> dict:
    """Refit sigma and lapse to the counts. `elements`: the course's rated
    elements (windows.Element or compose.Composed), in course order; `families`:
    each element's family (kind). Returns the joint fit, the fits per family
    with the likelihood-ratio test, and the table per window class."""
    from tools.worlds.windows import PROFILES, WINDOW_BANDS

    profile = profile or PROFILES["expert"]
    data = [(e.presses(), c.deaths, c.passes) for e, c in zip(elements, cs) if c.attempts]
    joint = fit_grid(data)
    out = {"attempts": sum(c.attempts for c in cs), "deaths": sum(c.deaths for c in cs), "joint": joint}
    if families:
        fams = {}
        for e, c, f in zip(elements, cs, families):
            if c.attempts:
                fams.setdefault(f, []).append((e.presses(), c.deaths, c.passes))
        per = {f: fit_grid(d) for f, d in fams.items() if len(d) >= 2}
        if len(per) >= 2:
            lr = 2 * (
                sum(p["ll"] for p in per.values())
                - log_likelihood([x for f in per for x in fams[f]], joint["sigma"], joint["lapse"])
            )
            dof = 2 * (len(per) - 1)
            out["families"] = per
            out["family_test"] = {"lr": round(lr, 2), "dof": dof, "p": round(chi2_sf(lr, dof), 4)}
    rows = []
    for e, c in zip(elements, cs):
        q_fit = death_chance(e.presses(), joint["sigma"], joint["lapse"])
        q_now = death_chance(e.presses(), profile["sigma"], profile.get("lapse", 0.0))
        rows.append((e.narrowest, c, q_fit, q_now))
    bands = []
    for lo, hi in zip((0, *WINDOW_BANDS), (*WINDOW_BANDS, 99)):
        rs = [r for r in rows if lo < r[0] <= hi]
        d = sum(r[1].deaths for r in rs)
        n = sum(r[1].attempts for r in rs)
        if not rs:
            continue
        bands.append(
            {
                "windows": f"{lo + 1}-{hi}" if hi < 99 else f">{lo}",
                "elements": len(rs),
                "attempts": n,
                "deaths": d,
                "observed": round(d / n, 3) if n else None,
                "interval": [round(x, 3) for x in wilson(d, n)],
                "fitted": round(sum(r[2] * r[1].attempts for r in rs) / n, 3) if n else None,
                "model_now": round(sum(r[3] * r[1].attempts for r in rs) / n, 3) if n else None,
            }
        )
    out["bands"] = bands
    out["elements"] = [
        {
            "label": r[1].label,
            "narrowest": r[0],
            "attempts": r[1].attempts,
            "deaths": r[1].deaths,
            "fitted": round(r[2], 3),
            "model_now": round(r[3], 3),
        }
        for r in rows
    ]
    return out


def print_fit(res: dict) -> None:
    j = res["joint"]
    print(
        f"{res['attempts']} attempts, {res['deaths']} deaths. Fit: sigma {j['sigma']} frames "
        f"({j['sigma_range'][0]}-{j['sigma_range'][1]}), lapse {j['lapse']} "
        f"({j['lapse_range'][0]}-{j['lapse_range'][1]})"
    )
    if "family_test" in res:
        t = res["family_test"]
        fams = ", ".join(f"{f}: sigma {p['sigma']} lapse {p['lapse']}" for f, p in res["families"].items())
        verdict = (
            "the families need parameters of their own" if t["p"] < 0.05 else "one set of parameters fits all families"
        )
        print(f"per family: {fams}; likelihood ratio {t['lr']} on {t['dof']} dof, p = {t['p']}: {verdict}")
    print(
        f"{'windows':>8} {'elem':>4} {'tries':>5} {'deaths':>6} {'observed':>8} {'95 %':>13} "
        f"{'fitted':>6} {'model now':>9}"
    )
    for b in res["bands"]:
        obs = "-" if b["observed"] is None else f"{b['observed']:.2f}"
        print(
            f"{b['windows']:>8} {b['elements']:>4} {b['attempts']:>5} {b['deaths']:>6} {obs:>8} "
            f"{b['interval'][0]:.2f}-{b['interval'][1]:.2f}  {b['fitted'] or 0:>6.2f} {b['model_now'] or 0:>9.2f}"
        )


# --- the command ------------------------------------------------------------------------------------

PICKS = os.path.join(L.LIB_DIR, "course.json")  # the course's elements, once picked
NAME = "calibration"  # a named map: the menu lists only numbered levels, so it stays outside the campaign


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("measure", "build", "fit"))
    ap.add_argument("map_id", nargs="?", default=NAME, help="the map's name (data/maps/<name>.json)")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()
    if args.action == "measure":
        res = measure(args.jobs)
        for rs in res.values():
            for r in rs:
                print(L.describe(r))
        picks = pick(res)
        os.makedirs(L.LIB_DIR, exist_ok=True)
        with open(PICKS, "w") as f:
            json.dump(picks, f, indent=1)
        print(f"picked {len(picks)} elements: " + ", ".join(f"{p['label']} ({p['_window']})" for p in picks))
        return 0
    with open(PICKS) as f:
        picks = json.load(f)
    if args.action == "build":
        from tools.worlds.route import plan_route, save_plan

        lv = build(args.map_id, picks)
        path = lv.save()
        solids = lv.solids()
        spawn = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
        res = plan_route(solids, spawn, lv.route, solids.kill_y, verbose=True)
        if not res.ok:
            return 1
        save_plan(args.map_id, spawn, res.frames, lv.route, res.segments)
        print(f"{path}: {len(picks)} elements, route {len(res.frames) / 60:.0f} s")
        return 0
    # fit
    from scripts import death_log
    from tools.worlds.windows import analyse_map

    from tools.worlds.route import load_plan

    els, _n, boxes, _solids = analyse_map(args.map_id)
    xs = sorted(b[0] for b in boxes)
    per_banner = _elements_per_banner(els, xs, load_plan(args.map_id)["waypoints"])
    with open(f"data/maps/{args.map_id}.json", "rb") as f:
        import hashlib

        sha = hashlib.sha1(f.read()).hexdigest()[:12]
    lines = death_log.read(args.map_id)
    cs = counts(lines, len(per_banner), [e.label for e in per_banner], sha, banner_xs=xs)
    if not sum(c.attempts for c in cs):
        from tools.worlds.windows import PROFILES

        print(f"no attempts of this map version in data/deaths/{args.map_id}.jsonl yet. The model expects:")
        for e, p in zip(per_banner, picks):
            q = [death_chance(e.presses(), pr["sigma"], pr["lapse"]) for pr in PROFILES.values()]
            print(
                f"  {p['label']:11s} narrowest {e.narrowest:2d}, {e.seconds:4.1f} s: deaths per attempt "
                f"{q[0]:.2f} (expert) / {q[1]:.2f} (average)"
            )
        return 0
    print_fit(fit(per_banner, cs, [p["kind"] for p in picks][: len(per_banner)]))
    return 0


def _elements_per_banner(els, banner_xs: list, route: list) -> list:
    """The rated elements merged into one per course element: all whose last
    waypoint lies between a banner and the next (by place: the rating's programs
    may pass a banner by)."""
    from tools.worlds.compose import Composed, Press

    groups: list = [[] for _ in banner_xs]
    for e in els:
        x = route[e.last].x0 * 16
        k = sum(1 for bx in banner_xs if bx <= x) - 1
        if k >= 0:
            groups[k].append(e)
    return [
        Composed(
            group[-1].label if group else "?",
            sum(e.seconds for e in group),
            [Press(w.width) for e in group for w in e.windows],
            [f for e in group for f in e.fatal],
        )
        for group in groups
    ]


if __name__ == "__main__":
    sys.exit(main())
