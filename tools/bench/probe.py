#!/usr/bin/env python3
"""Black-box frame timing of any version of the game, back to the first commit.

Started by `python -m tools.bench` (`--probe`, and for every commit of `history`):

    python tools/bench/probe.py --root <checkout> --out result.json

The version's own entry point (app.py, else menu.py, else game.py) runs
unchanged. Hooks into pygame make it measurable and let it play itself:

- pygame.display.flip / update mark the frames. Clock.tick,
  pygame.time.wait / delay and the FramePacer return at once, so a frame's
  time is what it costs to make.
- Enter is pressed every half second until a level map is loaded (the
  menu's "Play"; the very first menu only took clicks, so after a while
  the top button is clicked), then tools/frame_pacing.py's script runs,
  jumps and turns.
- After GAMEPLAY_FRAMES frames of play the probe stops the game.

Every version has loaded its levels with Tilemap.load, so timing that call
finds the level start and the map load. Maps, window size and features are
whatever the commit had: the numbers say what that version cost to run,
not how fast the same work got.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import resource
import runpy
import sys
import time
import traceback

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.dirname(BENCH_DIR)

GAMEPLAY_FRAMES = 600  # 10 s of play at 60 FPS
MAX_FRAMES = 1500  # gives up when no level has started by then
ENTER_EVERY = 30
CLICK_AFTER = 300  # frames of Enter before clicking the top button instead
CLICK_AT = (0.5, 0.21)  # the first menu's "Play" button, relative to the window
BUDGET_MS = 1000 / 60
HITCH_MS = 25.0  # the perf HUD's hitch (scripts/perf_hud.py)
ENTRY_POINTS = ("app.py", "menu.py", "game.py")

clock = time.perf_counter


class Stop(BaseException):
    """Raised from inside the game loop to end it (games catch Exception, not this)."""


class FastClock:
    """pygame.time.Clock that measures but never waits."""

    def __init__(self) -> None:
        self._last = clock()
        self._ms = 0.0

    def tick(self, framerate=0) -> int:
        now = clock()
        self._ms = (now - self._last) * 1000
        self._last = now
        return int(self._ms)

    tick_busy_loop = tick

    def get_time(self) -> int:
        return int(self._ms)

    get_rawtime = get_time

    def get_fps(self) -> float:
        return 1000 / self._ms if self._ms else 0.0


def frame_pacing_script():
    """(frame, event type, key) of tools/frame_pacing.py's scripted run, imported by path."""
    saved = list(sys.path)  # frame_pacing.py puts its repo root first on sys.path
    spec = importlib.util.spec_from_file_location("bench_frame_pacing", os.path.join(TOOLS_DIR, "frame_pacing.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path[:] = saved
    return module.scripted_input()


class Probe:
    def __init__(self, t0: float) -> None:
        self.t0 = t0
        self.flips: list[float] = []
        self.play_from: int | None = None  # index of the first frame of play
        self.loads: list[tuple[int, str, float]] = []  # (frame, map path, ms)
        self.script: dict[int, list] = {}
        self.release: list = []  # keys to let go of on the next frame

    def install(self, pygame) -> None:
        self.pg = pygame
        for name in ("flip", "update"):
            original = getattr(pygame.display, name)

            def hooked(*args, _original=original, **kwargs):
                result = _original(*args, **kwargs)
                self.frame()
                return result

            setattr(pygame.display, name, hooked)
        pygame.time.Clock = FastClock
        pygame.time.wait = pygame.time.delay = lambda *args: 0
        try:
            from scripts.frame_pacer import FramePacer

            FramePacer.tick = lambda self: 1 / 60
        except ImportError:
            pass
        try:
            from scripts.tilemap import Tilemap

            load = Tilemap.load
        except (ImportError, AttributeError):  # the first commits had no level files: everything is play
            self.play_from = 0
        else:

            def timed_load(tilemap, path, *args, **kwargs):
                t0 = clock()
                result = load(tilemap, path, *args, **kwargs)
                self.loads.append((len(self.flips), str(path), (clock() - t0) * 1000))
                if self.play_from is None and "menu" not in str(path):
                    self.play_from = len(self.flips)  # the next frame shows the level
                return result

            Tilemap.load = timed_load
        for f, typ, key in frame_pacing_script():
            self.script.setdefault(f, []).append((typ, key))

    def press(self, typ, key) -> None:
        self.pg.event.post(self.pg.event.Event(typ, key=key, mod=0, unicode="", scancode=0))

    def frame(self) -> None:
        pg = self.pg
        self.flips.append(clock())
        for key in self.release:
            self.press(pg.KEYUP, key)
        self.release = []
        n = len(self.flips)
        if self.play_from is None:
            if n >= MAX_FRAMES:
                raise Stop
            if n % ENTER_EVERY == 0 and n < CLICK_AFTER:
                self.press(pg.KEYDOWN, pg.K_RETURN)
                self.release.append(pg.K_RETURN)
            elif n % ENTER_EVERY == 0:
                w, h = pg.display.get_surface().get_size()
                pos = (int(w * CLICK_AT[0]), int(h * CLICK_AT[1]))
                pg.mouse.get_pos = lambda: pos  # the menu reads the pointer, not the event
                pg.event.post(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=pos))
            return
        played = n - self.play_from
        if played >= GAMEPLAY_FRAMES:
            raise Stop
        for typ, key in self.script.get(played, ()):
            self.press(typ, key)

    def results(self) -> dict:
        f = self.flips
        out: dict = {"frames": len(f)}
        if f:
            out["startup_ms"] = (f[0] - self.t0) * 1000
        p = self.play_from
        if p is not None and len(f) > p + 10:
            iv = [(b - a) * 1000 for a, b in zip(f, f[1:])]  # iv[i]: frame i shown -> frame i+1 shown
            if p > 0:
                out["level_start_ms"] = iv[p - 1]  # last menu frame to the level's first frame
            play = iv[p:]
            out["frame_p50_ms"] = pct(play, 0.5)
            out["frame_p95_ms"] = pct(play, 0.95)
            out["frame_p99_ms"] = pct(play, 0.99)
            out["frame_max_ms"] = max(play)
            out["over_budget"] = sum(x > BUDGET_MS for x in play)
            out["hitches"] = sum(x > HITCH_MS for x in play)
            out["fps_uncapped"] = 1000 * len(play) / sum(play)
            out["frames_played"] = len(play)
        level_loads = [ms for _, path, ms in self.loads if "menu" not in path]
        if level_loads:
            out["map_load_ms"] = level_loads[0]
            out["map"] = next(path for _, path, _ in self.loads if "menu" not in path)
        surface = self.pg.display.get_surface() if self.pg.display.get_init() else None
        if surface:
            out["window"] = list(surface.get_size())
        ui = sys.modules.get("scripts.ui")
        stats = getattr(getattr(ui, "UI", None), "get_text_cache_stats", None)
        if stats:
            s = stats()
            if s["hits"] + s["misses"]:
                out["text_cache_hit_pct"] = 100 * s["hits"] / (s["hits"] + s["misses"])
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        out["peak_rss_mb"] = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
        return out


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def entry_point() -> str | None:
    """The first of app.py / menu.py / game.py that starts the game when run."""
    for name in ENTRY_POINTS:
        if os.path.exists(name):
            with open(name) as f:
                src = f.read()
            if "__main__" in src or ").run()" in src:
                return name
    return None


def main() -> None:
    t0 = float(os.environ.get("BENCH_T0") or clock())
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, help="game root to run in (a sandbox or a checkout)")
    ap.add_argument("--out", required=True, help="where to write the JSON result")
    args = ap.parse_args()
    out = os.path.abspath(args.out)

    os.chdir(args.root)
    sys.path[0] = os.path.abspath(args.root)  # replaces this script's directory
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("NINJA_LOG_LEVEL", "WARN")
    random.seed(0)

    result: dict = {}
    entry = entry_point()
    probe = Probe(t0)
    wall0, perf0 = time.time(), clock()
    if entry is None:
        result["error"] = "no entry point"
    else:
        result["entry"] = entry
        sys.argv = [entry]
        try:
            import pygame

            probe.install(pygame)
            runpy.run_path(entry, run_name="__main__")
            result["ended"] = "returned"
        except Stop:
            result["ended"] = "stopped"
        except SystemExit:
            result["ended"] = "exited"
        except BaseException as e:  # noqa: BLE001 - an old version may crash; that is a result too
            result["ended"] = "crashed"
            result["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()[-500:]
        if hasattr(probe, "pg"):
            result.update(probe.results())
        # perf_counter stops while the machine sleeps; frames after a wake run slow
        result["slept"] = (time.time() - wall0) - (clock() - perf0) > 0.5
    with open(out, "w") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
