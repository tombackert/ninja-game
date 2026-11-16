"""Composer: a level's difficulty and length on paper, from the element library.

docs/level-building-process-brainstorm.md, 3.1 and step 7 of 5.1. A level
outline lists its elements with their parameters, the walks between them and
its banners. Each element's numbers come from the library
(tools/worlds/library.py: measured once, on its own, by the same windows
model as the check), and `windows.first_clear` combines them exactly as it
combines a built level's elements. So the composer predicts the first clear
per profile, the deaths, the exposed presses and the tight elements per half
before anything is built.

Length and difficulty are the two parameters to balance (decision D2):
- **length** is the played-safe time (free elements and walks cost about their
  seconds times the profile's pace);
- **difficulty** is what the presses add: retries (a miss that only costs
  another try) and restarts (a death that sends the player back to the last
  checkpoint).
The report splits the predicted time into those parts, and `balance` says
how far the target is in either currency: seconds of played-safe length at
this difficulty, or exposed presses of a given window at this length.

An outline (JSON, tools/worlds/outlines/<id>.json):

    {"level": 29, "targets": [4.0, 5.0, 0.8, 8],
     "elements": [{"kind": "gap", "gap": 8, "dh": 1, "label": "first chasm"},
                  {"walk": 3.0},
                  {"banner": true},
                  {"kind": "chimney", "width": 2, "height": 9, "repeat": 2}]}

`stamp(lv, outline_elements, x, y)` builds the outline's elements one after
another into a Level (flat ledges for the walks, a banner where it says so;
`"back"` tiles before the ledge's end, with `"gate"` under a lintel so that it
cannot be jumped over):
the calibration course is built this way, and a level can be.

    python -m tools.worlds.compose tools/worlds/outlines/29.json [--measure --jobs 7]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from tools.worlds import library as L

WALK_SPEED = 60.0  # px per second a player walks a ledge (the run speed: 1 px per frame)
OFF = 0.15  # an element of the built level this far off its library seconds is a context effect
TOLERANCE_MIN = 0.10  # the composer's prediction against the check: within 10 %


@dataclass
class Press:
    width: int


@dataclass
class Composed:
    """An element as `windows.first_clear` reads it (label, seconds, windows, fatal)."""

    label: str
    seconds: float
    windows: list = field(default_factory=list)
    fatal: list = field(default_factory=list)
    kind: str = "walk"
    params: dict = field(default_factory=dict)
    trick: bool = False

    def presses(self):
        return [(w.width, f) for w, f in zip(self.windows, self.fatal)]

    @property
    def narrowest(self) -> int:
        from tools.worlds.windows import FREE

        return min((w.width for w in self.windows), default=FREE)


def _params(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k not in ("kind", "label", "repeat", "banner", "walk")}


def elements_of(outline: dict, measure: bool = False, jobs: int = 1) -> tuple[list, list]:
    """(composed elements, banner cuts) of an outline. Library points not yet
    measured are measured now with `measure`, else they are an error."""
    specs = outline["elements"]
    if measure:
        by_kind: dict = {}
        for sp in specs:
            if "kind" in sp:
                by_kind.setdefault(sp["kind"], []).append(_params(sp))
        for kind, points in by_kind.items():
            uniq = [json.loads(p) for p in sorted({json.dumps(p, sort_keys=True) for p in points})]
            L.grid(kind, uniq, jobs)
    out, cuts = [], []
    for sp in specs:
        if sp.get("banner"):
            cuts.append(len(out))
            continue
        if "walk" in sp:
            out.append(Composed(sp.get("label", "walk"), float(sp["walk"])))
            continue
        known = L.load(sp["kind"]).get(L._point_key(_params(sp)))
        if known is None:
            raise KeyError(f"{sp['kind']} {_params(sp)} is not in the library yet (run with --measure)")
        if not known.get("ok"):
            raise ValueError(f"{sp['kind']} {_params(sp)} cannot be played: {known.get('why')}")
        for r in range(sp.get("repeat", 1)):
            for k, e in enumerate(known["elements"]):
                label = sp.get("label", f"{sp['kind']} {' '.join(f'{a}={b}' for a, b in _params(sp).items())}")
                if len(known["elements"]) > 1:
                    label += f" {k + 1}"
                if sp.get("repeat", 1) > 1:
                    label += f" #{r + 1}"
                out.append(
                    Composed(
                        label,
                        e["seconds"],
                        [Press(w) for w in e["widths"]],
                        list(e["fatal"]),
                        sp["kind"],
                        _params(sp),
                        e.get("trick", False),
                    )
                )
    return out, cuts


def predict(elements: list, cuts: list, profiles=None) -> dict:
    """First clear per profile with its parts (played safe x pace, retries,
    restarts), exposed presses and tight elements per half."""
    from tools.worlds import windows as W

    profiles = profiles or W.PROFILES
    out = {"elements": len(elements), "played_safe_s": round(sum(e.seconds for e in elements), 1)}
    for name, prof in profiles.items():
        fc = W.first_clear(elements, prof, cuts)
        costs, _passes, _deaths = W.element_costs(elements, prof)
        clean = sum(e.seconds for e in elements) * prof["pace"]
        tries = sum(costs)
        out[name] = {
            **fc,
            "parts_s": {
                "played_safe_x_pace": round(clean, 1),
                "retries": round(tries - clean, 1),
                "restarts": round(fc["minutes"] * 60 - tries, 1),
            },
        }
    c = cuts[0] if cuts else len(elements)
    hs = [elements[:c], elements[c:]] if cuts else [elements]
    out["exposed_per_half"] = [W.exposed_presses(h) for h in hs]
    out["le4_per_half"] = [sum(1 for e in h if e.narrowest <= 4) for h in hs]
    out["trick_elements"] = [e.label for e in elements if e.trick]
    return out


def _with(elements: list, cuts: list, extra_s: float = 0.0, k: int = 0, window: int = 8) -> tuple[list, list]:
    """The elements with `extra_s` seconds of free length spread evenly between
    them, and `k` exposed presses of `window` frames at the end of each stretch
    between banners. Returns (elements, cuts)."""
    n = len(elements)
    edges = [0, *sorted(c for c in cuts if 0 < c < n), n]
    out, new_cuts = [], []
    per = extra_s / n if n else 0.0
    for a, b in zip(edges, edges[1:]):
        if a:
            new_cuts.append(len(out))
        for e in elements[a:b]:
            out.append(e)
            if per:
                out.append(Composed("filler", per))
        out += [Composed("press", 0.0, [Press(window)], [1.0]) for _ in range(k)]
    return out, new_cuts


def balance(elements: list, cuts: list, target_min: float, profile: str = "expert", window: int = 8) -> dict:
    """How far the target is, in either currency: seconds of played-safe length
    (free, spread through the level) at this difficulty, or exposed presses of
    `window` frames per stretch between banners at this length."""
    from tools.worlds import windows as W

    prof = W.PROFILES[profile]

    def minutes(extra_s=0.0, k=0):
        els, cs = _with(elements, cuts, extra_s, k, window)
        return W.first_clear(els, prof, cs)["minutes"]

    now = minutes()
    out = {"profile": profile, "minutes": now, "target": target_min, "length_s": 0.0, "presses_per_half": 0}
    if now >= target_min:
        return out
    lo, hi = 0.0, 3000.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if minutes(mid) < target_min else (lo, mid)
    out["length_s"] = round(hi, 0)
    k = 0
    while k < 200 and minutes(k=k) < target_min:
        k += 1
    out["presses_per_half"] = k if k < 200 else None
    return out


def stamp(lv, specs: list, x: int, y: int, ledge: int = 6) -> tuple[int, int]:
    """Build the outline elements into `lv` one after another from an entry
    ledge ending at column x, floor row y: each element, then a `ledge`-tile
    ledge (longer for a walk), a banner where the outline says. Returns where
    the last ledge ends (column, floor row)."""
    for sp in specs:
        if sp.get("banner"):
            bx = x - sp.get("back", 2)  # this many tiles before the ledge's end
            lv.checkpoint(bx, y - 1)
            if sp.get("gate"):  # a lintel over it: nobody jumps over the banner
                lv.rect(bx - 1, y - 3, bx + 1, y - 3)
            continue
        if "walk" in sp:
            n = max(2, round(float(sp["walk"]) * WALK_SPEED / 16))
            lv.rect(x, y, x + n - 1, y + L.LEDGE)
            lv.wp(x + n - 3, y - 1, x + n - 1, y - 1, ground=True, label=sp.get("label", "walk"))
            x += n
            continue
        for _r in range(sp.get("repeat", 1)):
            first = len(lv.route)
            ex = L.KINDS[sp["kind"]](lv, x, y, **_params(sp))
            for w in lv.route[first:]:
                w.label = f"{sp.get('label', sp['kind'])} {w.label}".strip()
            if ex.x is None:  # it ends on its own last waypoint: a ledge to the east of it
                last = lv.route[-1]
                x, y = int(last.x1) + 3, int(last.y1) + 1
                lv.rect(x, y, x + ledge - 1, y + L.LEDGE)
            else:
                x, y = ex.x, ex.y
                lv.rect(x, y, x + ledge - 1, y + L.LEDGE)
            lv.wp(x + 1, y - 1, x + ledge - 1, y - 1, ground=True, label=f"{sp.get('label', sp['kind'])} out")
            x += ledge
    return x, y


def versus_check(outline: dict, els: list, summ: dict) -> str:
    """One line for the check: the composer's prediction against the built level."""
    try:
        comp, cuts = elements_of(outline)
    except (KeyError, ValueError) as exc:
        return f"vs composer -    {exc}"
    pred = predict(comp, cuts)["expert"]["minutes"]
    checked = summ["first_clear"]["expert"]["minutes"]
    off = []
    for c in comp:
        if c.kind == "walk":
            continue
        match = [e for e in els if e.label.endswith(c.label) or c.label in e.label]
        if not match:
            continue
        e = match[0]
        if abs(e.seconds - c.seconds) > OFF * max(c.seconds, 0.5) or (e.narrowest < c.narrowest) != (
            c.narrowest < e.narrowest
        ):
            if e.narrowest != c.narrowest:
                how = "narrower" if e.narrowest < c.narrowest else "wider"
            else:
                how = "longer" if e.seconds > c.seconds else "shorter"
            off.append(f"{c.label} ({how})")
    pct = (checked - pred) / pred * 100 if pred else 0.0
    flag = "OK  " if abs(pct) <= TOLERANCE_MIN * 100 and len(off) * 10 <= max(1, len(comp)) else "OFF "
    return (
        f"vs composer {flag}{checked - pred:+.1f} min ({pct:+.0f} %); {len(off)} elements off by >{round(OFF * 100)} %"
        f"{': ' + ', '.join(off[:3]) if off else ''}"
    )


def print_report(outline: dict, comp: list, cuts: list) -> None:
    p = predict(comp, cuts)
    tgt = outline.get("targets")
    print(f"outline {outline.get('level', '?')}: {p['elements']} elements, played safe {p['played_safe_s']} s")
    for name in ("expert", "average"):
        fc = p[name]
        parts = fc["parts_s"]
        print(
            f"  {name:7s} {fc['minutes']:5.1f} min / {fc['deaths']:.1f} deaths  = played safe x pace "
            f"{parts['played_safe_x_pace']:.0f} s + retries {parts['retries']:.0f} s "
            f"+ restarts {parts['restarts']:.0f} s"
            f"  (first try {round(100 * fc['first_try'])} %)"
        )
    print(f"  exposed presses per half {p['exposed_per_half']}, elements <= 4 frames per half {p['le4_per_half']}")
    if p["trick_elements"]:
        print(f"  trick elements: {', '.join(p['trick_elements'])}")
    if tgt:
        mid = (tgt[0] + tgt[1]) / 2
        b = balance(comp, cuts, mid)
        print(
            f"  target {tgt[0]:g}-{tgt[1]:g} min / <= {tgt[2]:g} deaths, <= {tgt[3]} exposed per half: to reach "
            f"{mid:g} min add {b['length_s']:.0f} s of played-safe length, or {b['presses_per_half']} exposed "
            f"8-frame presses per half"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outline")
    ap.add_argument("--measure", action="store_true", help="measure library points that are missing")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()
    with open(args.outline) as f:
        outline = json.load(f)
    comp, cuts = elements_of(outline, args.measure, args.jobs)
    print_report(outline, comp, cuts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
