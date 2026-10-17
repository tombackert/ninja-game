#!/usr/bin/env python3
"""Measure frame pacing and camera smoothness in the real game window.

Usage (from the repo root):
    python tools/frame_pacing.py                    # scripted run on level 0
    python tools/frame_pacing.py --manual --hud     # you play (F1 HUD on); ESC ends
    python tools/frame_pacing.py --camera calm      # try the calm camera style
    python tools/frame_pacing.py --pacing tick      # old Clock.tick(60), to compare
    python tools/frame_pacing.py --pos 100,1200     # pin the window to a display
    python tools/frame_pacing.py --report a.csv b.csv

Runs the same loop as app.py, but straight into GameState and with a real
window, and logs every frame (timings, camera, player) to a CSV. Scripted
input is posted as real key events, so it goes through the normal input
path; the simulation is deterministic, so scripted runs are comparable.
Settings changes (level, camera style) stay in memory and are not saved.

The report shows:
- pacing: frame rate, frame-to-frame intervals and hitches (> 25 ms, a
  missed 60 Hz frame). A rate off 60 FPS repeats or drops that many
  frames per second on a 60 Hz display.
- cost: update / render / flip time per frame and the time left waiting.
- camera: how often it moves and how far the picture is from an ideal
  continuous camera, in window pixels, as the renderer shows it.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

COLUMNS = ["frame", "t0", "t1", "t2", "t3", "t4", "t5", "sx", "sy", "px", "py", "scale"]


def scripted_input():
    """(frame, event type, key): run, stop, turn and jump, six times over."""
    import pygame

    events = []
    t = 30
    for _ in range(6):
        events.append((t, pygame.KEYDOWN, pygame.K_RIGHT))
        for j in range(t + 20, t + 110, 40):
            events += [(j, pygame.KEYDOWN, pygame.K_UP), (j + 1, pygame.KEYUP, pygame.K_UP)]
        events.append((t + 120, pygame.KEYUP, pygame.K_RIGHT))
        events += [(t + 150, pygame.KEYDOWN, pygame.K_LEFT), (t + 220, pygame.KEYUP, pygame.K_LEFT)]
        t += 240
    return events


def run(args) -> None:
    args.out = os.path.abspath(args.out)
    os.chdir(ROOT)  # the game loads data/ relative to the repo root
    os.environ.setdefault("NINJA_GAME_TESTING", "0")
    if args.pos:
        os.environ["SDL_VIDEO_WINDOW_POS"] = args.pos

    import pygame

    from scripts.frame_pacer import FramePacer
    from scripts.input_router import InputRouter
    from scripts.settings import settings
    from scripts.state_manager import GameState, StateManager

    settings.flush = lambda: None  # keep data/settings.json untouched
    settings.selected_level = args.level
    if args.camera:
        settings.camera_style = args.camera

    pygame.init()
    pygame.display.set_mode((1280, 720))
    sm = StateManager()
    router = InputRouter()
    sm.set(GameState())
    screen = pygame.display.get_surface()
    game = sm.current.game
    print(
        f"window {screen.get_size()} at {pygame.Window.from_display_module().position}, "
        f"display {pygame.display.get_current_refresh_rate()} Hz, pacing {args.pacing}, "
        f"camera {settings.camera_style}"
    )

    if args.pacing == "tick":
        clock = pygame.time.Clock()

        def tick():
            clock.tick(60)

    else:
        tick = FramePacer(60).tick

    scripted: dict[int, list] = {}
    if args.hud:
        scripted.setdefault(2, []).append((pygame.KEYDOWN, pygame.K_F1))
        scripted.setdefault(3, []).append((pygame.KEYUP, pygame.K_F1))
    if not args.manual:
        for f, typ, key in scripted_input():
            scripted.setdefault(f, []).append((typ, key))
        print(f"scripted run, {args.frames} frames")
    else:
        print("play; press ESC or close the window to finish")

    rows = []
    frame = 0
    running = True
    while running and (args.manual or frame < args.frames):
        t0 = time.perf_counter()
        for typ, key in scripted.get(frame, []):
            pygame.event.post(pygame.event.Event(typ, key=key, mod=0, unicode="", scancode=0))
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT or (args.manual and e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
        cur = sm.current
        sm.handle_actions(router.process(events, cur.name if cur else ""))
        sm.handle(events)
        t1 = time.perf_counter()
        tick()
        t2 = time.perf_counter()
        sm.update(1 / 60)
        t3 = time.perf_counter()
        sm.render(screen)
        t4 = time.perf_counter()
        if frame in args.snap:
            # Without alpha: the window surface's alpha channel is 0 on macOS
            rgb = pygame.image.frombytes(pygame.image.tobytes(screen, "RGB"), screen.get_size(), "RGB")
            pygame.image.save(rgb, f"{os.path.splitext(args.out)[0]}_f{frame}.png")
        pygame.display.flip()
        t5 = time.perf_counter()
        game = getattr(sm.current, "game", game)
        p = game.player
        scale = screen.get_width() / game.BASE_W
        rows.append([frame, t0, t1, t2, t3, t4, t5, game.scroll[0], game.scroll[1], p.pos[0], p.pos[1], scale])
        frame += 1
    pygame.quit()

    with open(args.out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"wrote {len(rows)} frames to {args.out}\n")
    report([args.out])


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def _shown(scroll, k):
    """Camera position on screen in window pixels (as Renderer draws it)."""
    f = math.floor(scroll)
    return f * k + round((scroll - f) * k)


def report(paths) -> None:
    for path in paths:
        with open(path) as fh:
            rows = [{key: float(v) for key, v in r.items()} for r in csv.DictReader(fh)]
        rows = rows[10:]  # skip warm-up (window creation, first loads)
        if len(rows) < 3:
            print(f"== {path}: too few frames")
            continue
        flips = [r["t5"] for r in rows]
        iv = [(b - a) * 1000 for a, b in zip(flips, flips[1:])]
        fps = len(iv) / (flips[-1] - flips[0])
        k = rows[0]["scale"]

        def cost(a, b):
            ms = [(r[b] - r[a]) * 1000 for r in rows]
            return f"{_pct(ms, 0.5):.2f}/{_pct(ms, 0.99):.2f}"

        print(f"== {path}")
        print(
            f"  pacing: {fps:.2f} fps ({abs(fps - 60):.2f} frames/s off 60), interval mean "
            f"{statistics.mean(iv):.2f} sd {statistics.pstdev(iv):.2f} p99 {_pct(iv, 0.99):.2f} "
            f"max {max(iv):.2f} ms, hitches (>25 ms) {sum(i > 25 for i in iv)}"
        )
        print(
            f"  cost ms p50/p99: update {cost('t2', 't3')}  render {cost('t3', 't4')}  "
            f"flip {cost('t4', 't5')}  wait {cost('t1', 't2')}"
        )
        for axis in "xy":
            s = [r["s" + axis] for r in rows]
            moving = sum(abs(b - a) > 1e-9 for a, b in zip(s, s[1:]))
            err = [_shown(v, k) - v * k for v in s]
            d_err = [b - a for a, b in zip(err, err[1:])]
            print(
                f"  camera {axis}: moving in {100 * moving / (len(s) - 1):.0f}% of frames, "
                f"off ideal by up to {max(err) - min(err):.1f} px, step jitter sd {statistics.pstdev(d_err):.2f} px"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", nargs="+", metavar="CSV", help="only print the report for saved runs")
    ap.add_argument("--level", type=int, default=0)
    ap.add_argument("--frames", type=int, default=900, help="length of a scripted run")
    ap.add_argument("--manual", action="store_true", help="you play instead of the script")
    ap.add_argument("--hud", action="store_true", help="turn on the F1 performance HUD")
    ap.add_argument("--camera", choices=["classic", "calm"], help="camera style for this run")
    ap.add_argument("--pacing", choices=["pacer", "tick"], default="pacer")
    ap.add_argument("--pos", help="window position 'x,y' (pins the display)")
    ap.add_argument("--snap", type=int, nargs="*", default=[], help="save the window image at these frames")
    ap.add_argument("--out", default=os.path.join(ROOT, "frame_pacing.csv"))
    args = ap.parse_args()
    if args.report:
        report(args.report)
    else:
        run(args)


if __name__ == "__main__":
    main()
