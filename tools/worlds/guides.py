"""Which waypoints of a route are guides the planner no longer needs.

A route's semantic waypoints are the stops where elements start (ground
waypoints, and air ones where a player who lets go of the keys comes to rest:
`windows.stable_waypoints`) and the flag. The other air waypoints were placed
so the planner gets through ("guides"). One pass along the route, planned with
`route`'s tries, asks of each of them in turn: from where the route stands
before it, can the planner go straight to the waypoint after it, and from
there on to the next one? If so the guide is not needed, unless the way
without it is much shorter and misses the guide's box: then it may be a
shortcut past what the guide marks, and the guide is kept and reported.

    python -m tools.worlds.guides 31 37 38 [--jobs 8] [--json out.json]

Nothing is written: the level files are edited by hand from the report.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from tools.worlds import physics as ph

SHORTER = 0.8  # a way without the guide this much shorter, and not through its box, may be a shortcut


def _through(start: tuple, frames: list, wp, solids, margin: int = 1) -> bool:
    """Whether the hitbox center passes within `margin` tiles of `wp`'s box."""
    s = start
    for m, j, d in frames:
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
        cx, cy = (s[ph.X] + ph.PW / 2) / ph.TS, (s[ph.Y] + ph.PH / 2) / ph.TS
        if wp.x0 - margin <= cx < wp.x1 + 1 + margin and wp.y0 - margin <= cy < wp.y1 + 1 + margin:
            return True
    return False


def analyse(map_id: int) -> dict:
    from tools.worlds.build import build_level
    from tools.worlds.route import LEAD_IN, _Segment
    from tools.worlds.windows import settle

    t0 = time.time()
    lv = build_level(map_id)
    solids = lv.solids()
    spawn = (lv.spawn_tile[0] * ph.TS, lv.spawn_tile[1] * ph.TS)
    kill_y = (max(y for _, y in solids) + 4) * 16
    route = lv.route
    s = ph.spawn_state(*spawn)
    for _ in range(LEAD_IN):
        s, _down, _dead = ph.step(s, 0, solids)

    def seg(start, wp):
        return _Segment(start, wp, solids, kill_y).next()

    rows = []
    cache: dict = {}
    i = 0
    while i < len(route):
        wp = route[i]
        stable = wp.ground
        if not stable and i < len(route) - 1:
            # the planner's own arrival here, let go of the keys: does it come to rest?
            r_keep = cache.pop(("keep", i), None) or seg(s, wp)
            stable = r_keep is not None and settle(r_keep.end, wp, solids) is not None
            cache[("keep", i)] = r_keep
        if not stable and i < len(route) - 1:
            nxt = route[i + 1]
            r = seg(s, nxt)
            row = {"index": i, "label": wp.label, "next": nxt.label}
            if r is None:
                row.update(verdict="needed", why="no way to the next waypoint without it")
            else:
                ok2 = i + 2 >= len(route) or seg(r.end, route[i + 2]) is not None
                r_keep = cache.get(("keep", i))
                r_keep2 = seg(r_keep.end, nxt) if r_keep is not None else None
                keep_frames = len(r_keep.frames) + len(r_keep2.frames) if r_keep2 is not None else None
                through = _through(s, r.frames, wp, solids)
                ratio = len(r.frames) / keep_frames if keep_frames else None
                row.update(frames=len(r.frames), with_guide=keep_frames, through=through)
                if not ok2:
                    row.update(verdict="needed", why="the waypoint after the next cannot be planned from there")
                elif ratio is not None and ratio < SHORTER and not through:
                    row.update(verdict="kept", why=f"the way without it is {ratio:.2f}x as long and misses its box")
                else:
                    row.update(verdict="not needed")
                    rows.append(row)
                    cache[("keep", i + 1)] = r  # going on from s straight to the next waypoint
                    i += 1
                    continue
            rows.append(row)
        r = cache.pop(("keep", i), None) or seg(s, wp)
        if r is None:
            return {"level": map_id, "rows": rows, "failed_at": i, "label": wp.label, "seconds": time.time() - t0}
        s = r.end
        i += 1
    return {"level": map_id, "rows": rows, "failed_at": None, "seconds": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="+", type=int)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    if args.jobs > 1 and len(args.levels) > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(min(args.jobs, len(args.levels))) as pool:
            results = list(pool.map(analyse, args.levels))
    else:
        results = [analyse(n) for n in args.levels]
    for r in results:
        rows = r["rows"]
        gone = [x["label"] for x in rows if x["verdict"] == "not needed"]
        print(
            f"level {r['level']}: {len(rows)} guides, {len(gone)} not needed"
            f"{'' if r['failed_at'] is None else ' (route FAILED at ' + str(r['failed_at']) + ')'} ({r['seconds']} s)"
        )
        for x in rows:
            if x["verdict"] != "not needed":
                print(f"  {x['verdict']:6s} {x['label']!r} -> {x['next']!r}: {x['why']}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
