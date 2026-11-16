"""Element library: parametrized elements, each measured once on its own.

docs/level-building-process-brainstorm.md, 3.1. The windows model
(tools/worlds/windows.py) rates an element on its own when it starts settled,
standing on a ledge with the dash ready, and `first_clear` only combines
per-element numbers. So an element measured here in isolation rates the same
in a level, as long as it joins the rest at settled ledges and nothing near it
offers another way (the composer checks that against the full assessment).

An element type is a function that stamps rock into a `builder.Level` at an
entry ledge and adds its route waypoints. It gets the column `x` where the
entry ledge ends (the ledge covers columns < x) and the ledge's floor row `y`
(the row the player stands on), and returns an `Exit`: where the exit ledge
starts, or that the element's last waypoint is its own exit.

`measure(kind, **params)` builds the smallest level around one element (a
13-tile entry ledge with the spawn on it, the element, a 6-tile exit ledge,
all over a void) and rates it with `windows.profile_built`. The result per
parameter point: narrowest window, played-safe seconds, the presses with
their windows and fatal shares, presses of 4 frames or less, exposed presses,
dashes and trick element (the dash wall climb), and the program itself.
`grid(kind, points)` measures many points at once; results are cached in
tools/worlds/library/<kind>.json under the model's version.

    python -m tools.worlds.library gap --grid gap=7,8,9 dh=-1,0,1,2 --jobs 7
    python -m tools.worlds.library chimney --grid width=1,2,3 height=6,9 --jobs 7
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from dataclasses import dataclass

from tools.worlds.builder import Level

FLOOR = 40  # floor row of the test level's entry ledge
ENTRY = 13  # entry ledge length (tiles)
EXIT = 6  # exit ledge length
LEDGE = 3  # ledge thickness (rows)
SPAWN_BACK = 3  # the spawn stands this many tiles before the entry ledge's edge

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library")


@dataclass
class Exit:
    x: int | None  # exit ledge's first column (None: the element ends on its own last waypoint)
    y: int | None = None  # its floor row
    measured_from: int = 0  # first waypoint (of the element's own) the measured part starts at


KINDS: dict = {}


def kind(name: str):
    def register(fn):
        KINDS[name] = fn
        return fn

    return register


# --- element types ---------------------------------------------------------------------


@kind("gap")
def gap(lv: Level, x: int, y: int, gap: int = 5, dh: int = 0, ceiling: int | None = None) -> Exit:
    """A jump over a void: `gap` open columns, the landing `dh` rows higher
    (negative: lower); with `ceiling`, a ceiling that many open rows over the
    takeoff floor, from 4 tiles before the edge to 2 past the landing's start."""
    x1 = x + gap
    if ceiling is not None:
        lv.rect(x - 4, y - ceiling - 1, x1 + 2, y - ceiling - 1)
    return Exit(x1, y - dh)


@kind("chimney")
def chimney(lv: Level, x: int, y: int, width: int = 2, height: int = 8, reach: int = 1) -> Exit:
    """A chimney hanging over the void, climbed wall to wall: its west wall
    hangs over the end of the entry ledge with one open row under it, so the
    player walks to the ledge's end and jumps up into the shaft (`width` open
    columns, `reach` columns past the ledge's end); the east wall reaches down
    past the ledge into the void. The exit ledge is on top of the east wall,
    `height` rows over the entry floor. A miss falls out of the shaft's open
    bottom into the void."""
    west = x - 1 + reach - 1  # the west wall's column: over the ledge's last column(s)
    east = west + width + 1
    top = y - height
    lv.rect(west, top - 2, west, y - 2)  # hangs down to two rows over the floor: one open row under it
    lv.rect(west - 1, top - 2, west, top - 2)  # a cap over its west face: the climb is inside
    lv.rect(east, top, east, y + 4)
    lv.wp(west + 1, top - 3, east - 1, top - 1, label="shaft top")
    return Exit(east, top)


@kind("hook")
def hook_swing(lv: Level, x: int, y: int, drop: int = 3, gap: int = 2, foot: int = 2, hang: int = 8) -> Exit:
    """The Mars hook swing (level 31): from the foot of a hook hanging from
    above, drop off its west end, pass under it and its claw, and jump up on to
    the next hook's foot `drop` rows lower, `gap` open columns east of the first
    hook's stem. The first foot is a free hop from the entry ledge; the
    measured part is the swing. The element ends on the second foot."""
    from tools.worlds.kits.mars import hook

    s1 = x + 2 + foot  # first stem's column (two wide)
    f0, f1 = hook(lv, s1, y - hang, y, foot=foot)
    lv.wp(f0, y - 1, f1, y - 1, ground=True, label="first foot")
    s2 = s1 + 2 + gap + foot
    g0, g1 = hook(lv, s2, y - hang, y + drop, foot=foot)
    lv.wp(g0, y + drop - 1, g1, y + drop - 1, ground=True, label="next foot")
    return Exit(None, measured_from=1)


@kind("pillars")
def pillars(lv: Level, x: int, y: int, count: int = 4, spacing: int = 3, width: int = 1, dh: int = 0) -> Exit:
    """A run of `count` pillars `width` wide over the void, `spacing` open
    columns apart, each `dh` rows higher than the one before; a stop on each."""
    px = x + spacing
    row = y
    for i in range(count):
        row -= dh
        lv.rect(px, row, px + width - 1, row + 8)
        lv.wp(px, row - 1, px + width - 1, row - 1, ground=True, label=f"pillar {i + 1}")
        px += width + spacing
    return Exit(px, row - dh)


# --- the measuring harness ----------------------------------------------------------------


def test_level(kind_name: str, **params) -> Level:
    """The smallest level around one element: entry ledge, element, exit ledge, a void under all."""
    lv = Level(900, "stone")
    lv.rect(0, FLOOR, ENTRY - 1, FLOOR + LEDGE)
    lv.spawn(ENTRY - SPAWN_BACK, FLOOR - 1)
    first = len(lv.route)
    ex = KINDS[kind_name](lv, ENTRY, FLOOR, **params)
    if ex.x is not None:
        lv.rect(ex.x, ex.y, ex.x + EXIT - 1, ex.y + LEDGE)
        lv.wp(ex.x, ex.y - 1, ex.x + EXIT - 1, ex.y - 1, ground=True, label="exit")
    lv._measured_from = first + ex.measured_from  # route index the measured part starts at
    return lv


def model_version() -> str:
    """A hash of the code the numbers come from: physics, planner and rating."""
    from tools.worlds.cache import code_version

    return code_version("physics.py", "planner.py", "route.py", "windows.py", "library.py")


def _point_key(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


def measure(kind_name: str, **params) -> dict:
    """Rate one parameter point of an element type (see the module doc)."""
    from tools.worlds import windows as W
    from tools.worlds.assess import checkpoint_boxes
    from tools.worlds.planner import dash_climbs
    from tools.worlds.route import plan_route

    t0 = time.time()
    lv = test_level(kind_name, **params)
    out = {"kind": kind_name, "params": params}
    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * 16, lv.spawn_tile[1] * 16)
    res = plan_route(solids, spawn, lv.route, solids.kill_y, verbose=False)
    if not res.ok:
        out.update(ok=False, why=f"route fails at {lv.route[res.failed_at].label!r}", seconds_cpu=time.time() - t0)
        return out
    segments = [(start, n) for _label, start, n, _exp in res.segments]
    els = W.analyse_route(solids, spawn, lv.route, res.frames, segments)
    first = lv._measured_from
    own = [e for e in els if e.last >= first]
    walk = [e for e in els if e not in own]
    presses = [(w.width, round(f, 3)) for e in own for w, f in zip(e.windows, e.fatal)]
    out.update(
        ok=True,
        elements=[
            {
                "label": e.label,
                "narrowest": e.narrowest,
                "seconds": round(e.seconds, 3),
                "widths": [w.width for w in e.windows],
                "fatal": [round(f, 3) for f in e.fatal],
                "trick": e.trick,
                "dashes": sum(1 for f in e.frames if f[2]),
                "dash_climbs": dash_climbs(e.start, e.frames, solids),
                "settled": e.settled,
                "frames": [list(f) for f in e.frames],
            }
            for e in own
        ],
        narrowest=min((e.narrowest for e in own), default=W.FREE),
        seconds=round(sum(e.seconds for e in own), 3),
        walk_seconds=round(sum(e.seconds for e in walk), 3),
        presses=presses,
        presses_le4=sum(1 for w, _f in presses if w <= 4),
        exposed=sum(1 for w, f in presses if f >= 0.5 and w < W.FREE),
        trick=any(e.trick for e in own),
        checkpoints=checkpoint_boxes({"tilemap": {}, "offgrid": lv.offgrid}),
        seconds_cpu=round(time.time() - t0, 1),
    )
    return out


def _measure_job(item):
    kind_name, params = item
    try:
        return measure(kind_name, **params)
    except Exception as exc:  # a point that cannot be built or rated is a result too
        return {"kind": kind_name, "params": params, "ok": False, "why": f"{type(exc).__name__}: {exc}"}


def load(kind_name: str) -> dict:
    """The cached measurements of an element type under the current model: {point key: result}."""
    path = os.path.join(LIB_DIR, f"{kind_name}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get(model_version(), {})


def save(kind_name: str, results: dict) -> str:
    os.makedirs(LIB_DIR, exist_ok=True)
    path = os.path.join(LIB_DIR, f"{kind_name}.json")
    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    version = model_version()
    data = {version: {**data.get(version, {}), **results}}  # older model versions are dropped
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    return path


def grid(kind_name: str, points: list[dict], jobs: int = 1, cache: bool = True) -> list[dict]:
    """Measure every parameter point (cached ones are read back)."""
    known = load(kind_name) if cache else {}
    todo = [p for p in points if _point_key(p) not in known]
    fresh = {}
    if todo:
        items = [(kind_name, p) for p in todo]
        if jobs > 1 and len(items) > 1:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(min(jobs, len(items))) as pool:
                results = list(pool.map(_measure_job, items))
        else:
            results = [_measure_job(it) for it in items]
        fresh = {_point_key(r["params"]): r for r in results}
        if cache:
            save(kind_name, fresh)
    allr = {**known, **fresh}
    return [allr[_point_key(p)] for p in points]


def entry(kind_name: str, **params) -> dict:
    """One measured point (measured now if it is not in the library yet)."""
    return grid(kind_name, [params])[0]


def _parse_grid(specs: list[str]) -> list[dict]:
    axes = []
    for spec in specs:
        name, values = spec.split("=")
        vals = [None if v == "none" else int(v) for v in values.split(",")]
        axes.append([(name, v) for v in vals])
    return [dict(combo) for combo in itertools.product(*axes)]


def describe(r: dict) -> str:
    p = " ".join(f"{k}={v}" for k, v in r["params"].items())
    if not r.get("ok"):
        return f"{r['kind']} {p}: - ({r.get('why', '?')})"
    widths = sorted(w for w, _f in r["presses"])
    tight = [w for w in widths if w < 25]
    return (
        f"{r['kind']} {p}: narrowest {r['narrowest']:2d}, {r['seconds']:.1f} s, presses {tight or '-'} "
        f"(<=4: {r['presses_le4']}, exposed {r['exposed']}){'  TRICK' if r['trick'] else ''}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=sorted(KINDS))
    ap.add_argument("--grid", nargs="*", default=[], help="name=v1,v2,... per parameter")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    points = _parse_grid(args.grid) or [{}]
    for r in grid(args.kind, points, args.jobs, cache=not args.no_cache):
        print(describe(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
