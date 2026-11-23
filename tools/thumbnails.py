#!/usr/bin/env python3
"""Render the level menu's preview thumbnails (data/thumbnails/levels/<id>.png).

A thumbnail is one frame of the real game, headless and without HUD (the
trailer's Studio), framed 320x180 around the ninja: what a player sees of
the level, so it is recognisable in the menu.

Which frame, without giving the level away:
- Only the opening of the run is looked at: the first SPOILER_SHARE of the
  route. The finale, the flag and the level's big set piece stay unseen;
  the opening still shows the world, its backdrop and its kind of terrain.
- In that window a frame is taken every STEP ticks and scored by how much
  there is to see (tile edges and decor, colour variety), with the ninja
  alive, well inside the frame and no fade on screen. The best one wins.
- PICKS overrides the choice per level (a replay tick), for openings where
  the score picks a dull or misleading frame.

What drives the ninja, first that exists: the route plan
(tools/worlds/plans/<id>.json, levels 11-40), the trailer's best run
(tools/trailer_replays/<id>-best.json), the local best run
(data/replays/<id>.json), else the ninja just stands at the spawn.

Usage (from the repo root):
    python tools/thumbnails.py                 # all levels
    python tools/thumbnails.py 14 21 --sheet   # also a contact sheet of the candidates in out/thumbnails/
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import trailer as tr  # noqa: E402

VIEW = (320, 180)
SPOILER_SHARE = 0.3  # look no further than this share of the run
MIN_WINDOW = 600  # ticks: short runs still get ten seconds to pick from
STEP = 10  # ticks between candidates
OUT_DIR = os.path.join(ROOT, "data", "thumbnails", "levels")
SHEET_DIR = os.path.join(ROOT, "out", "thumbnails")

# Hand-picked frames (run tick) where the score picks a dull one.
PICKS: dict[int, int] = {
    22: 640,  # Kelp Currents: under the surface between the rock islands, not on the dry start rock
    30: 750,  # The Colossus: the dark steps of his foot; the score's pick looked like The Hourglass
}


def source(level: int) -> tuple[str, "tr.Run | None", int]:
    """What drives the ninja on `level`: (label, run, run length in ticks)."""
    if os.path.exists(os.path.join(ROOT, "tools", "worlds", "plans", f"{level}.json")):
        run = tr.Run(level, "plan")
    elif os.path.exists(os.path.join(tr.REPLAYS, f"{level}-best.json")):
        run = tr.Run(level, "best")
    elif os.path.exists(os.path.join(ROOT, "data", "replays", f"{level}.json")):
        run = tr.Run(level, "best", path=os.path.join(ROOT, "data", "replays", f"{level}.json"))
    else:
        return "spawn", None, 0
    total = max((e["tick"] for e in run.data["inputs"]), default=0)
    label = "plan" if not run.snaps else "replay"
    return label, run, total


def score(pg, frame) -> float:
    """How much there is to see: edge detail times colour variety."""
    import numpy as np

    px = pg.surfarray.array3d(frame).astype(np.int16)  # (w, h, 3)
    lum = px[..., 0] * 3 + px[..., 1] * 6 + px[..., 2]
    detail = float(np.mean(np.abs(np.diff(lum, axis=0)) > 40) + np.mean(np.abs(np.diff(lum, axis=1)) > 40))
    q = (px >> 5).reshape(-1, 3)
    colours = len(np.unique(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]))
    return detail * np.log1p(colours)


def framed(g) -> bool:
    """The ninja is alive, in the middle of the frame, and the scene is calm:
    no fade, no hit sparks or screenshake, no dash smoke (leaves may fall)."""
    if g.dead or g.transition or g.sparks or g.screenshake:
        return False
    if any(p.type != "leaf" for p in g.particles):
        return False
    r = g.player.rect()
    x, y = r.centerx - g.scroll[0], r.centery - g.scroll[1]
    w, h = g.BASE_W, g.BASE_H
    return w * 0.2 < x < w * 0.8 and h * 0.2 < y < h * 0.8


def render_level(studio, level: int, sheet: bool = False) -> str:
    pg = studio.pg
    label, run, total = source(level)
    window = max(MIN_WINDOW, int(total * SPOILER_SHARE)) if run else 60
    pick = PICKS.get(level)
    if pick is not None:
        window = pick + 1

    gs = studio.stage(level, 0, "Default", VIEW)
    g = gs.game
    if run:
        run.place(g.player)
        g.movement = list(run.held)
    studio.frame_camera(g)
    frame = pg.Surface(VIEW)
    best = None  # (score, tick, surface)
    shots = []
    for tick in range(window):
        if run and not g.dead:
            run.feed(tick, g.player, g.movement, g.audio)
        gs.update(1 / tr.FPS)
        if pick is not None and tick != pick:
            continue
        if pick is None and (tick < 30 or tick % STEP or not framed(g)):
            continue
        studio.renderer.render(g, frame)
        s = score(pg, frame)
        if sheet:
            shots.append((s, tick, frame.copy()))
        if best is None or s > best[0]:
            best = (s, tick, frame.copy())
    if best is None:  # never framed (e.g. died at once): take the last frame
        studio.renderer.render(g, frame)
        best = (score(pg, frame), window - 1, frame.copy())

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{level}.png")
    pg.image.save(best[2], path)
    print(
        f"level {level:2}: {label:6} tick {best[1]:5} of {total:5} (score {best[0]:.2f})",
        "->",
        os.path.relpath(path, ROOT),
    )
    if sheet and shots:
        write_sheet(studio, level, shots, best[1])
    return path


def write_sheet(studio, level, shots, chosen) -> None:
    pg = studio.pg
    shots = shots[:: max(1, len(shots) // 24)][:24]
    cols, (w, h), gap = 4, VIEW, 4
    rows = (len(shots) + cols - 1) // cols
    sheet = pg.Surface((cols * (w + gap), rows * (h + gap + 10)))
    sheet.fill((20, 20, 28))
    font = studio.font[8]
    for k, (s, tick, surf) in enumerate(shots):
        x, y = (k % cols) * (w + gap), (k // cols) * (h + gap + 10)
        sheet.blit(surf, (x, y + 10))
        colour = (255, 200, 60) if tick == chosen else (220, 220, 220)
        sheet.blit(font.render(f"t{tick} {s:.2f}", False, colour), (x, y))
    os.makedirs(SHEET_DIR, exist_ok=True)
    pg.image.save(sheet, os.path.join(SHEET_DIR, f"{level}.png"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--sheet", action="store_true", help="contact sheet of the candidates in out/thumbnails/")
    args = ap.parse_args()
    studio = tr.Studio()
    from scripts.level_cache import list_levels

    for level in args.levels or list_levels():
        render_level(studio, level, args.sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
