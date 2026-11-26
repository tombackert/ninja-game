"""In-game stills along a level's route plan, as one contact sheet.

The level is played by the real game, headless (the trailer's Studio:
GameState, live enemies, the real renderer, no HUD), with the inputs of its
route plan (tools/worlds/plans/<id>.json), and a frame is taken at `n`
evenly spaced moments of the route. That is how the level looks to a
player: backgrounds, autotiled edges, water, decor and enemies, which the
overview from `build --preview` does not show.

The plan is played straight, without dodging: an enemy shot can still end
the run early (the summary line says so; `play` is the playthrough check).

Usage:
    python -m tools.worlds.stills 26 [27 ...] [--n 12] [--out DIR] [--cols 3]
"""

from __future__ import annotations

import argparse
import os
import sys


def contact_sheet(level: int, n: int, out_dir: str, cols: int = 3, view=(640, 360)) -> str:
    from tools import trailer as tr

    studio = tr.Studio()
    pg = studio.pg
    from scripts.constants import TRANSITION_MAX
    from tools.worlds.route import load_plan

    total = len(load_plan(level)["frame_list"])
    ticks = [int(40 + (total - 60) * k / max(1, n - 1)) for k in range(n)]
    gs = studio.stage(level, 0, "Default", view)
    g = gs.game
    run = tr.Run(level, "plan")
    run.place(g.player)
    g.movement = list(run.held)
    frame = pg.Surface(view)
    shots = []
    tick = deaths = 0
    was_dead = False
    for _ in range(total + 600):
        if not g.dead and not g.hitstop:  # a hit-stop frame runs no tick (Game.hitstop)
            run.feed(tick, g.player, g.movement, g.audio)
            tick += 1
        deaths += bool(g.dead) and not was_dead
        was_dead = bool(g.dead)
        gs.update(1 / 60)
        if ticks and tick >= ticks[0]:
            ticks.pop(0)
            studio.renderer.render(g, frame)
            shots.append(frame.copy())
        if g.endpoint and g.transition >= TRANSITION_MAX:
            break
    w, h = view
    rows = (len(shots) + cols - 1) // cols
    sheet = pg.Surface((cols * (w + 6) - 6, rows * (h + 6) - 6))
    sheet.fill((20, 20, 28))
    for k, surf in enumerate(shots):
        sheet.blit(surf, ((k % cols) * (w + 6), (k // cols) * (h + 6)))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"level_{level}_stills.png")
    pg.image.save(sheet, path)
    end = "reached the flag" if g.endpoint else f"stopped at route frame {tick} of {total}"
    print(f"level {level}: {len(shots)} stills -> {path}; the plan played straight {end}, {deaths} deaths")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="+", type=int)
    ap.add_argument("--n", type=int, default=12, help="stills per level")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    for level in args.levels:
        contact_sheet(level, args.n, out, args.cols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
