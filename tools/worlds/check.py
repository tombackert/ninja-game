"""Every check a level needs, in one command, on one screen.

docs/level-building-process-brainstorm.md, 3.4. Builds and saves the level,
plans its route, checks the physics replica against the game along it, the
banner on the route, the shortcut probes and the breath, and rates it with
the timing-window model (as players play: no dash wall climb). Prints at
most about 15 lines; the details go to out/check/<id>/report.json and
elements.txt.

The route's segments and the elements' ratings are cached exactly
(tools/worlds/cache.py): after a local change only what the change can reach
is planned and rated again.

    python -m tools.worlds.check 38 [--jobs 7] [--skips] [--stills] [--play] [--no-shortcuts] [--fresh]

The shortcut check runs the climb scan and the declared obstacles; `--skips`
adds the skip probes, which take minutes per level (about 25 CPU minutes).

`--stills` adds the contact sheet of the real game (tools/worlds/stills.py),
`--play` the route bot in the real game window (tools/worlds/play.py): both
slow, for the end of a level's work.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

from tools.worlds import physics as ph  # noqa: E402

OUT_DIR = os.path.join("out", "check")
BREATH_MIN = 2.0  # seconds of breath the closest call on the route should leave
PHYSICS_FRAMES = 20000

# Targets for the expert profile (docs/difficulty-rating-brainstorm.md, section 9):
# (minutes low, high, deaths at most, exposed presses per half at most). Under
# decision D2 they are the model's view until the calibration has checked it;
# an outline (tools/worlds/outlines/<id>.json, "targets") overrides them.
FINALES = {30, 35, 40}
TARGETS = {n: (15.0, 20.0, 1.5, 15) if n in FINALES else (4.0, 6.0, 0.8, 8) for n in range(26, 41)}


def level_title(map_id: int) -> str:
    mod = importlib.import_module(f"tools.worlds.levels.level_{map_id}")
    first = (mod.__doc__ or "").strip().splitlines()[0] if mod.__doc__ else f"Level {map_id}"
    return first.rstrip(".").replace(" - ", " ", 1)


def _history(map_id: int) -> int:
    path = os.path.join(OUT_DIR, str(map_id), "history.json")
    runs = []
    if os.path.exists(path):
        with open(path) as f:
            runs = json.load(f)
    runs.append(time.strftime("%Y-%m-%d %H:%M:%S"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(runs, f)
    return len(runs)


def physics_check(map_id: int) -> tuple[bool, str]:
    """The replica against the real game along the route (check_physics --route)."""
    from game import Game
    from tools.worlds.check_physics import check_map

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        game = Game(fullscreen=False)
        bad = check_map(game, map_id, PHYSICS_FRAMES, 1, route=True)
    text = buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else ""
    return bad == 0, text


def breath_check(states: list, arrivals: list, route: list) -> tuple[float, str]:
    """(least breath left on the route in seconds, the waypoint it comes before)."""
    i = min(range(len(states)), key=lambda k: states[k][ph.BREATH])
    k = next((q for q, a in enumerate(arrivals) if a >= i), len(route) - 1)
    return states[i][ph.BREATH] / 60, route[k].label


def halves(elements: list, cuts: list) -> list:
    """The elements before and after the (first) banner."""
    if not cuts:
        return [elements]
    c = cuts[0]
    return [elements[:c], elements[c:]]


def route_cuts(els: list, touched: list, arrivals: list) -> list:
    """The element each banner stands before, from the frames the designed route
    touches it at: the element whose stretch of the route holds the frame (the
    next one, if it comes in that stretch's second half)."""
    cuts = []
    for f in touched:
        for k, e in enumerate(els):
            a = arrivals[e.first - 1] if e.first > 0 else 0
            b = arrivals[e.last]
            if a <= f <= b:
                cuts.append(k if f - a < (b - a) / 2 else k + 1)
                break
    return sorted(c for c in cuts if 0 < c < len(els))


def outline_for(map_id: int) -> dict | None:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outlines", f"{map_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def run_check(
    map_id: int, jobs: int = 1, shortcuts: bool = True, fresh: bool = False, stills=False, play=False, skips=False
):
    from tools.worlds import windows as W
    from tools.worlds.assess import checkpoint_boxes, checkpoint_frames
    from tools.worlds.build import build_level
    from tools.worlds.cache import element_store, route_store
    from tools.worlds.route import plan_route, save_plan

    t_all = time.time()
    lines: list = []
    report: dict = {"level": map_id}
    n_check = _history(map_id)
    head = f"level {map_id} {level_title(map_id).split(' ', 2)[-1]}"
    lines.append(f"{head[:58]:58s} check {n_check} of this level")

    # build and plan
    lv = build_level(map_id)
    lv.save()
    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * ph.TS, lv.spawn_tile[1] * ph.TS)
    rstore = None if fresh else route_store()
    t0 = time.time()
    res = plan_route(solids, spawn, lv.route, solids.kill_y, verbose=False, cache=rstore)
    plan_s = time.time() - t0
    guides = sum(1 for w in lv.route if w.guide)
    cached = f" ({rstore.stats()} segments)" if rstore else ""
    if not res.ok:
        wp = lv.route[res.failed_at]
        lines.append(f"route      FAIL waypoint {res.failed_at} {wp.label!r} {(wp.x0, wp.y0, wp.x1, wp.y1)} unreached")
        report["route"] = {"ok": False, "failed_at": res.failed_at, "label": wp.label}
        return _finish(map_id, lines, report, [])
    save_plan(map_id, spawn, res.frames, lv.route, res.segments)
    limit = sum(1 for st in res.stats if st.at_limit)
    lines.append(
        f"route      OK   {len(lv.route)} waypoints, {guides} guides, {len(res.frames) / 60:.1f} s, planned in "
        f"{plan_s:.0f} s{cached}{f', {limit} segments at a node limit' if limit else ''}"
    )
    report["route"] = {
        "ok": True,
        "frames": len(res.frames),
        "guides": guides,
        "seconds": round(plan_s, 1),
        "nodes": res.expanded,
        "at_limit": limit,
        "summary": res.summary(),
    }

    s = ph.spawn_state(*spawn)
    states = [s]
    for m, j, d in res.frames:
        s = ph.apply_frame(s, m, j, d, solids)[0]
        states.append(s)
    arrivals = [a + n for _l, a, n, _e in res.segments]

    # physics
    ok, text = physics_check(map_id)
    lines.append(f"physics    {'OK  ' if ok else 'FAIL'} {text.split(': ', 1)[-1] if text else ''} along the route")
    report["physics"] = {"ok": ok, "text": text}

    # banner (the element it stands before comes with the rating)
    boxes = checkpoint_boxes({"tilemap": {}, "offgrid": lv.offgrid})
    touched = checkpoint_frames(states, boxes)
    banner_ok = len(touched) == len(boxes)

    # shortcuts
    if shortcuts:
        from tools.worlds import shortcuts as SC

        SC._ROUTES[map_id] = SC.Route(map_id, solids, list(lv.route), states, arrivals, list(lv.obstacles))
        t0 = time.time()
        sc = SC.check([map_id], jobs, skips=skips)[map_id]
        proven = [f for f in sc["findings"] if f["verdict"] == SC.PROVEN]
        open_obs = [f for f in sc["findings"] if f["probe"] == "obstacle" and f["verdict"] == SC.NOT_PROVEN]
        tag = "FAIL" if proven else ("OPEN" if open_obs else "OK  ")
        lines.append(f"shortcuts  {tag} {SC.summary(sc)} ({time.time() - t0:.0f} s)")
        for f in proven[:3]:
            lines.append(f"             {f['probe']} {f['label']}: {f['found_s']} s instead of {f['designed_s']} s")
        report["shortcuts"] = sc
    else:
        lines.append("shortcuts  -    not run (--no-shortcuts)")

    # breath
    if getattr(solids, "water", None):
        least, where = breath_check(states, arrivals, lv.route)
        lines.append(
            f"breath     {'OK  ' if least >= BREATH_MIN else 'LOW '} least {least:.1f} s left (before {where})"
        )
        report["breath"] = {"least_s": round(least, 2), "where": where}

    # rating
    estore = None if fresh else element_store()
    t0 = time.time()
    segments = [(a, n) for _l, a, n, _e in res.segments]
    els = W.analyse_route(solids, spawn, lv.route, res.frames, segments, cache=estore)
    rate_s = time.time() - t0
    summ = W.summary(map_id, els, len(res.frames), boxes, solids)
    cuts = summ["checkpoints"]
    by_route = False
    if boxes and banner_ok and len(cuts) < len(boxes):
        # the most forgiving programs pass the banner by (a jump over it): place it by the route
        cuts = route_cuts(els, touched, arrivals)
        by_route = True
        summ["checkpoints"] = cuts
        summ["first_clear"] = {name: W.first_clear(els, prof, cuts) for name, prof in W.PROFILES.items()}
    if boxes:
        at = f"at element {cuts[0] + 1} of {len(els)}" if cuts else "but at no element"
        at += " (by the route: the rating's programs pass it by)" if by_route else ""
        lines.insert(
            3,
            f"banner     {'OK  ' if banner_ok and cuts else 'FAIL'} "
            f"{'on the route' if banner_ok else 'NOT on the route'} {at}",
        )
    fc = summ["first_clear"]
    outline = outline_for(map_id)
    tgt = tuple(outline["targets"]) if outline and outline.get("targets") else TARGETS.get(map_id)
    target = f"    target {tgt[0]:g}-{tgt[1]:g} / <={tgt[2]:g}" if tgt else ""
    lines.append(
        f"rating          expert {fc['expert']['minutes']:.1f} min / {fc['expert']['deaths']:.1f} deaths   "
        f"average {fc['average']['minutes']:.1f} min / {fc['average']['deaths']:.1f}{target}"
    )
    hs = halves(els, cuts)
    exposed = [W.exposed_presses(h) for h in hs]
    tight = [sum(1 for e in h if e.narrowest <= 4) for h in hs]
    lines.append(
        f"                played safe {summ['forgiving_seconds']:.0f} s, exposed {' + '.join(map(str, exposed))} "
        f"per half, <=4 frames: {' + '.join(map(str, tight))}, trick elements {len(summ['trick_elements'])}"
    )
    hard = ", ".join(f"{label} {n}" for label, n, _f in summ["hardest"][:3] if n < W.FREE) or "none below 25"
    lines.append(f"                hardest: {hard}")
    cache_note = f" ({estore.stats()} elements)" if estore else ""
    lines.append(f"                rated in {rate_s:.0f} s{cache_note}")
    report["rating"] = summ
    report["halves"] = {"exposed": exposed, "le4": tight}

    if outline:
        from tools.worlds import compose

        lines.append(compose.versus_check(outline, els, summ))

    if stills:
        from tools.worlds.stills import contact_sheet

        sheet = contact_sheet(map_id, 12, os.path.join(OUT_DIR, str(map_id)))
        lines.append(f"stills          {sheet}")
    if play:
        import subprocess

        out = os.path.join(OUT_DIR, str(map_id), "play")
        proc = subprocess.run(
            [sys.executable, "-m", "tools.worlds.play", str(map_id), "--out", out, "--attempts", "2"],
            capture_output=True,
            text=True,
        )
        last = [ln for ln in proc.stdout.splitlines() if "COMPLETED" in ln or "FAILED" in ln]
        lines.append(f"play       {'OK  ' if proc.returncode == 0 else 'FAIL'} {(last[-1] if last else '')[:90]}")
    report["seconds"] = round(time.time() - t_all, 1)
    return _finish(map_id, lines, report, els)


def _finish(map_id: int, lines: list, report: dict, els: list):
    d = os.path.join(OUT_DIR, str(map_id))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    with open(os.path.join(d, "elements.txt"), "w") as f:
        for e in els:
            f.write(
                f"{e.label[:50]:50s} {e.seconds:5.1f} s  narrowest {e.narrowest:2d}  presses "
                f"{[w.width for w in e.windows]}  fatal {[round(x, 2) for x in e.fatal]}"
                f"{'  TRICK' if e.trick else ''}\n"
            )
    lines.append(f"details    {d}/report.json, {d}/elements.txt")
    return lines, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="+", type=int)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--no-shortcuts", action="store_true")
    ap.add_argument("--skips", action="store_true", help="also the skip probes (minutes per level)")
    ap.add_argument("--fresh", action="store_true", help="ignore the caches")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--play", action="store_true")
    args = ap.parse_args()
    bad = 0
    for n in args.levels:
        lines, report = run_check(n, args.jobs, not args.no_shortcuts, args.fresh, args.stills, args.play, args.skips)
        print("\n".join(lines), flush=True)
        bad += any(ln[11:15] == "FAIL" for ln in lines)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
