#!/usr/bin/env python3
"""One benchmark session: play the game headless and write what it measured.

Started by `python -m tools.bench` in a fresh process per session:

    python tools/bench/session.py --root <game root> --out result.json [--quick]

The game root is a sandbox of the working tree (or a checkout of an older
commit), so the session starts from a fresh install and never touches the
repo's data/ (best times, coins, replays and settings live there).

The core is a campaign played the way a player meets the game: start-up,
menu, Play, then levels 0-6 one after another through the level-complete
screen. Each level is played to its finish by a real best run from
tools/trailer_replays/ (inputs rebuilt by tools/trailer.py's `Run`). Level
2 is replayed once against the ghost of the run just finished, and level 3
is paused for a moment. Every frame is timed (update, render, flip) and
labelled with what the player sees, so start, finish and respawn stalls
are told apart from smooth gameplay.

Isolated scenarios then cover what the campaign does not reach: the start
and respawn of every level, the cost of the F1 performance HUD, saving and
loading a replay, and the headless simulation the training env runs.

The game's frame loop is app.py's, without the frame pacer (frames run
back to back, so a frame's time is its cost). Older versions of the game
lack some of the pieces; a scenario that fails is reported in "errors" and
the others still run.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import os
import platform
import random
import resource
import shutil
import sys
import time
import traceback

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.dirname(BENCH_DIR)
REPLAYS = os.path.join(TOOLS_DIR, "trailer_replays")

WINDOW = (1280, 720)  # app.py's window
DT = 1 / 60
BUDGET_MS = 1000 / 60  # a frame slower than this misses a 60 Hz refresh
HITCH_MS = 25.0  # the perf HUD's hitch: a missed 60 Hz frame (scripts/perf_hud.py)

# The campaign: (level, replay that drives the player). A new level is
# reached through the level-complete screen's "next level", a repeated one
# through "replay", raced against the ghost of the run just finished.
CAMPAIGN = [(0, "best"), (1, "best"), (2, "best"), (2, "last"), (3, "best"), (4, "best"), (5, "best"), (6, "best")]
QUICK_CAMPAIGN = CAMPAIGN[:4]
PAUSE = (3, 600, 90)  # level, frame it is paused at, frames it stays paused
MENU_FRAMES = 60  # the player looks at the menu for a second
COMPLETE_FRAMES = 60  # ... and at each level-complete screen
FINISH_SLACK = 300  # frames past the replay's end before a level counts as not finished
LEVEL_REPEATS = 3  # starts and respawns per level in the level sweep (median)
# The machine slept when wall-clock time ran this much further than perf_counter
# (which stops in sleep). Frames run slow for a while after a wake, so the
# WAKE_FRAMES frames from there on are left out of the statistics.
SLEEP_GAP_S = 0.5
WAKE_FRAMES = 300

clock = time.perf_counter  # system-wide on macOS and Linux, so comparable with the parent's BENCH_T0


def load_run_class():
    """tools/trailer.py's `Run`, imported by path (it is not a package).

    trailer.py puts its repo root first on sys.path; that would shadow the
    game under test when it is an older checkout, so sys.path is restored.
    """
    saved = list(sys.path)
    spec = importlib.util.spec_from_file_location("bench_trailer", os.path.join(TOOLS_DIR, "trailer.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    sys.path[:] = saved
    return module.Run


class Session:
    def __init__(self, quick: bool):
        self.quick = quick
        self.frames: list[dict] = []  # every timed frame of the campaign
        self.metrics: dict = {}
        self.detail: dict = {}
        self.fingerprint: dict = {}
        self.errors: dict = {}
        self.gc_pauses: list[float] = []
        self._gc_start = 0.0
        self.wakes = 0  # times the machine slept during the session
        self._wake_until = -1  # frames up to this index ran right after a wake
        self._clocks = (time.time(), clock())

    # --- harness ---------------------------------------------------------
    def scenario(self, name, fn, *args):
        try:
            fn(*args)
        except BaseException as e:  # noqa: BLE001 - one broken scenario must not end the session
            if isinstance(e, KeyboardInterrupt):
                raise
            self.errors[name] = "".join(traceback.format_exception_only(type(e), e)).strip()[-500:]
            self.detail.setdefault("tracebacks", {})[name] = traceback.format_exc()[-3000:]

    def boot(self, t0: float) -> None:
        """Start-up as app.py does it, up to the first menu frame on screen."""
        t_import = clock()
        import pygame

        from scripts import state_manager

        self.pg = pygame
        self.sm_mod = state_manager
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW)
        from scripts.settings import settings

        self.settings = settings
        self.Run = load_run_class()
        self.sm = state_manager.StateManager()
        self.sm.set(state_manager.MenuState())
        self.step()
        now = clock()
        self.metrics["startup.to_menu_ms"] = (now - t0) * 1000
        self.metrics["startup.import_init_ms"] = (now - t_import) * 1000

    def step(self, actions=(), kind=None, level=None) -> dict:
        """One iteration of app.py's loop, timed (without the frame pacer's wait)."""
        sm = self.sm
        t0 = clock()
        sm.handle_actions(list(actions))
        self.app_transitions()
        sm.update(DT)
        t2 = clock()
        sm.render(self.screen)
        t3 = clock()
        self.pg.display.flip()
        t4 = clock()
        frame = {
            "kind": kind,
            "level": level,
            "ms": (t4 - t0) * 1000,
            "update": (t2 - t0) * 1000,  # actions and state changes count as update work
            "render": (t3 - t2) * 1000,
            "flip": (t4 - t3) * 1000,
        }
        wall, perf = time.time(), clock()
        if (wall - self._clocks[0]) - (perf - self._clocks[1]) > SLEEP_GAP_S:
            self.wakes += 1
            self._wake_until = len(self.frames) + WAKE_FRAMES
        self._clocks = (wall, perf)
        if len(self.frames) <= self._wake_until:
            frame["wake"] = True
        if kind:
            self.frames.append(frame)
        return frame

    def app_transitions(self) -> None:
        """The state changes app.py's loop makes between input and update."""
        sm, m = self.sm, self.sm_mod
        cur = sm.current
        if isinstance(cur, m.MenuState) and getattr(cur, "start_game", False):
            sm.set(m.GameState())
        elif isinstance(cur, m.GameState) and getattr(cur, "request_pause", False):
            sm.push(m.PauseState())
        elif isinstance(cur, m.PauseState) and cur.closed:
            sm.pop()

    def seed(self, level: int) -> None:
        """Seed the gameplay RNG and `random` per level, so each level replays
        the same however the levels before it went."""
        try:
            from scripts.rng_service import RNGService

            RNGService.get().seed(level)
        except ImportError:
            pass
        random.seed(level)

    def game_state(self):
        """The GameState on top of the stack or under the pause screen."""
        for state in reversed(self.sm._stack):
            if isinstance(state, self.sm_mod.GameState):
                return state
        return None

    # --- campaign --------------------------------------------------------
    def campaign(self) -> None:
        m = self.sm_mod
        for _ in range(MENU_FRAMES):
            self.step(kind="menu")
        plan = QUICK_CAMPAIGN if self.quick else CAMPAIGN
        prev = None
        for i, (level, kind) in enumerate(plan):
            self.seed(level)
            # The frame that builds the GameState is the level start stall
            if i == 0:
                self.settings.selected_level = level
                self.step(["menu_select"], kind="menu")  # Play: the menu asks app.py for a game
                frame = self.step(kind="start", level=level)
            else:
                frame = self.choose_on_complete_screen(level, replay=(level == prev))
            gs = self.sm.current
            assert isinstance(gs, m.GameState), f"level {level} did not start ({type(gs).__name__})"
            frame["render_first"] = frame["render"]
            self.play(gs, level, kind, label=f"L{level}" + ("-ghost" if level == prev else ""))
            prev = level
            for _ in range(COMPLETE_FRAMES):
                self.step(kind="complete", level=level)

    def choose_on_complete_screen(self, level: int, replay: bool) -> dict:
        """Pick "replay" or "next level" like a player, one key per frame.

        Returns the frame that started the level.
        """
        cur = self.sm.current
        want = "level_complete.replay" if replay else "level_complete.next_level"
        keys = getattr(cur, "options_keys", [])
        if want in keys and (replay or getattr(cur, "next_level", None) == level):
            for _ in range(keys.index(want)):
                self.step(["menu_down"], kind="complete", level=level)
            return self.step(["menu_select"], kind="start", level=level)
        # Older level-complete screens: start the level directly
        self.settings.selected_level = level
        t0 = clock()
        self.sm.set(self.sm_mod.GameState())
        built = (clock() - t0) * 1000
        frame = self.step(kind="start", level=level)
        frame["ms"] += built
        frame["update"] += built
        return frame

    def play(self, gs, level: int, kind: str, label: str) -> None:
        """Play a level with a recorded run until it is finished."""
        g = gs.game
        run = self.Run(level, kind)
        run.place(g.player)
        g.movement = list(run.held)
        # The router's actions as recorded: GameState hands them to the
        # replay recorder, as in live play
        recorded = {
            e["tick"]: [a for a in e["inputs"] if a not in ("pause_toggle", "debug_toggle")] for e in run.data["inputs"]
        }
        coins0 = g.cm.coins
        limit = run.data["duration_frames"] + FINISH_SLACK
        pause_at = PAUSE[1] if (PAUSE[0] == level and kind == "best" and not self.quick) else None
        tick = 0
        finished = False
        world = None  # md5 of the world picture halfway (the end fades to black)
        for n in range(limit):
            if tick == run.data["duration_frames"] // 2 and world is None and n:
                # Without the HUD layer: its timer runs on wall-clock time
                world = hashlib.md5(self.pg.image.tobytes(g.display_2, "RGBA")).hexdigest()[:12]
            kind_now = "play"
            extra = []
            if n == pause_at:
                self.pause(level)
                kind_now, extra = "resume", ["pause_close"]  # Esc again: this frame is a game tick
            actions = []
            if not g.dead:
                run.feed(tick, g.player, g.movement, g.audio)
                actions = recorded.get(tick, [])
                tick += 1
            frame = self.step(actions + extra, kind=kind_now, level=label)
            if self.sm.current is not gs:
                frame["kind"] = "finish"  # replay saved, best time saved, level-complete screen built
                finished = True
                break
        p = g.player
        self.fingerprint[label] = {
            "finished": finished,
            "ticks": tick,
            "pos": [round(p.pos[0], 3), round(p.pos[1], 3)],
            "coins": g.cm.coins - coins0,
            "enemies": len(g.enemies),
            "world": world,
        }

    def pause(self, level: int) -> None:
        """Pause (Esc) and stay on the pause screen; the caller resumes."""
        self.step(["pause_toggle"], kind="pause_first", level=level)
        for _ in range(PAUSE[2]):
            self.step(kind="pause", level=level)

    # --- isolated scenarios ------------------------------------------------
    def levels(self) -> None:
        """Start and respawn of every level as a first visit (assets are loaded by now).

        Each is the median of LEVEL_REPEATS, so the worst level is not one noisy sample.
        """
        from scripts.level_cache import list_levels

        start, respawn = {}, {}
        for level in list_levels():
            starts, respawns = [], []
            for _ in range(LEVEL_REPEATS):
                self.forget_runs(level)
                self.seed(level)
                self.settings.selected_level = level
                t0 = clock()
                self.sm.set(self.sm_mod.GameState())
                self.step()
                starts.append((clock() - t0) * 1000)
                g = self.sm.current.game
                lives = getattr(g.player, "lives", 3)
                t0 = clock()
                g.load_level(level, lives, respawn=True)
                respawns.append((clock() - t0) * 1000)
            start[str(level)] = pct(starts, 0.5)
            respawn[str(level)] = pct(respawns, 0.5)
        self.detail["level_start_ms"] = start
        self.detail["respawn_ms"] = respawn

    def hud(self) -> None:
        """Level 1 played twice, without and with the F1 performance HUD."""
        p50 = {}
        cache = {}
        for on in (False, True):
            self.forget_runs(1)
            self.seed(1)
            self.settings.selected_level = 1
            self.sm.set(self.sm_mod.GameState())
            gs = self.sm.current
            gs.perf_enabled = on
            before = text_cache_stats()
            n0 = len(self.frames)
            self.play(gs, 1, "best", label="hud" if on else "nohud")
            ms = [f["ms"] for f in self.frames[n0:] if f["kind"] == "play"]
            del self.frames[n0:]  # not part of the campaign
            p50[on] = pct(ms, 0.5)
            cache[on] = hit_rate(before, text_cache_stats())
        self.metrics["hud.frame_p50_ms"] = p50[True]
        self.metrics["hud.overhead_ms"] = p50[True] - p50[False]
        if cache[True] is not None:
            self.metrics["hud.text_cache_hit_pct"] = cache[True]

    def replay_files(self) -> None:
        """Save and load the longest replay (level 5's best run, ~4900 ticks)."""
        from scripts.replay import ReplayData, ReplayManager

        tmp = os.path.abspath("bench-replays")
        rm = ReplayManager(self.game_state().game if self.game_state() else None, storage_dir=tmp)
        with open(os.path.join(REPLAYS, "5-best.json")) as f:
            data = ReplayData.from_json(json.load(f))
        save, load = [], []
        for _ in range(5):
            t0 = clock()
            rm._save(data, "best")
            save.append((clock() - t0) * 1000)
            t0 = clock()
            rm._load(data.level, "best")
            load.append((clock() - t0) * 1000)
        shutil.rmtree(tmp, ignore_errors=True)
        self.metrics["replay.save_ms"] = pct(save, 0.5)
        self.metrics["replay.load_ms"] = pct(load, 0.5)

    def training(self) -> None:
        """Steps per second of the headless training env (random actions, level 0)."""
        from scripts.training_env import TrainingEnv

        env = TrainingEnv(seed=42, level_id=0)
        env.reset()
        rng = random.Random(0)
        steps, spent = 0, 0.0
        while steps < (1000 if self.quick else 3000):
            action = rng.randrange(8)
            t0 = clock()
            _, _, done, _ = env.step(action)
            spent += clock() - t0
            steps += 1
            if done:
                env.reset()
        self.metrics["sim.steps_per_s"] = steps / spent

    def forget_runs(self, level: int) -> None:
        """Drop a level's saved replays, so no ghost appears and the level plays as a first try."""
        for path in (f"data/replays/{level}.json", f"data/replays/last_runs/{level}.json"):
            if os.path.exists(path):
                os.remove(path)

    # --- results -----------------------------------------------------------
    def summarize(self) -> None:
        m, d = self.metrics, self.detail
        frames = [f for f in self.frames if not f.get("wake")]
        by_kind: dict[str, list[dict]] = {}
        for f in frames:
            by_kind.setdefault(f["kind"], []).append(f)
        play = by_kind.get("play", [])
        if play:
            ms = [f["ms"] for f in play]
            m["frame.p50_ms"] = pct(ms, 0.5)
            m["frame.p95_ms"] = pct(ms, 0.95)
            m["frame.p99_ms"] = pct(ms, 0.99)
            m["frame.max_ms"] = max(ms)
            m["update.p50_ms"] = pct([f["update"] for f in play], 0.5)
            m["update.p99_ms"] = pct([f["update"] for f in play], 0.99)
            m["render.p50_ms"] = pct([f["render"] for f in play], 0.5)
            m["render.p99_ms"] = pct([f["render"] for f in play], 0.99)
            m["frame.budget_pct"] = 100 * pct(ms, 0.5) / BUDGET_MS
            m["frames.played"] = len(play)
            # Every frame the player sees in the campaign (stalls included)
            shown = [f["ms"] for f in frames]
            m["frames.over_budget"] = sum(x > BUDGET_MS for x in shown)
            m["frames.hitches"] = sum(x > HITCH_MS for x in shown)
            per_level: dict[str, dict] = {}
            for f in play:
                per_level.setdefault(str(f["level"]), []).append(f["ms"])  # type: ignore[arg-type]
            d["campaign_frame_ms"] = {
                k: {"p50": pct(v, 0.5), "p99": pct(v, 0.99), "max": max(v), "frames": len(v)}
                for k, v in per_level.items()
            }
        starts = by_kind.get("start", [])
        if starts:
            d["campaign_start_ms"] = {str(f["level"]): f["ms"] for f in starts}
            m["level_start.first_ms"] = starts[0]["ms"]  # the first level of a session loads every asset
            m["level_start.p50_ms"] = pct([f["ms"] for f in starts[1:]] or [starts[0]["ms"]], 0.5)
            m["level_start.max_ms"] = max(f["ms"] for f in starts[1:]) if len(starts) > 1 else starts[0]["ms"]
            m["first_frame.render_p50_ms"] = pct([f["render_first"] for f in starts], 0.5)
        finishes = by_kind.get("finish", [])
        if finishes:
            d["campaign_finish_ms"] = {str(f["level"]): f["ms"] for f in finishes}
            m["level_finish.p50_ms"] = pct([f["ms"] for f in finishes], 0.5)
            m["level_finish.max_ms"] = max(f["ms"] for f in finishes)
        for kind, name in (("menu", "menu"), ("complete", "complete_screen"), ("pause", "pause")):
            if by_kind.get(kind):
                m[f"{name}.frame_p50_ms"] = pct([f["ms"] for f in by_kind[kind]], 0.5)
        if by_kind.get("pause_first"):
            m["pause.first_ms"] = by_kind["pause_first"][0]["ms"]
        if by_kind.get("resume"):
            m["pause.resume_ms"] = by_kind["resume"][0]["ms"]
        if frames:
            m["campaign.wall_s"] = sum(f["ms"] for f in frames) / 1000
        if d.get("level_start_ms"):
            vals = list(d["level_start_ms"].values())
            m["levels.start_max_ms"] = max(vals)
            m["levels.respawn_max_ms"] = max(d["respawn_ms"].values())
            m["levels.respawn_p50_ms"] = pct(list(d["respawn_ms"].values()), 0.5)
        if self.gc_pauses:
            m["gc.max_pause_ms"] = max(self.gc_pauses)
            m["gc.collections"] = len(self.gc_pauses)

    def caches(self, before) -> None:
        """Hit rates of the UI caches over the campaign, and what is loaded."""
        after = text_cache_stats()
        rate = hit_rate(before, after)
        if rate is not None:
            self.metrics["cache.text_hit_pct"] = rate
            self.metrics["cache.text_evictions"] = after["evictions"] - before["evictions"]
        try:
            from scripts.ui import UI

            img = UI.get_image_cache_stats()
            if img["hits"] + img["misses"]:
                self.metrics["cache.image_hit_pct"] = 100 * img["hits"] / (img["hits"] + img["misses"])
            self.metrics["cache.fonts"] = len(getattr(UI, "_font_cache", {}))
        except Exception:
            pass
        try:
            from scripts.asset_manager import AssetManager

            self.metrics["assets.images"] = len(AssetManager.get()._images)
        except Exception:
            pass

    def watch_gc(self) -> None:
        def callback(phase, info):
            if phase == "start":
                self._gc_start = clock()
            else:
                self.gc_pauses.append((clock() - self._gc_start) * 1000)

        gc.callbacks.append(callback)
        self._gc_callback = callback

    def unwatch_gc(self) -> None:
        if getattr(self, "_gc_callback", None) in gc.callbacks:
            gc.callbacks.remove(self._gc_callback)


def text_cache_stats():
    try:
        from scripts.ui import UI

        return UI.get_text_cache_stats()
    except Exception:
        return None


def hit_rate(before, after):
    if not before or not after:
        return None
    hits = after["hits"] - before["hits"]
    misses = after["misses"] - before["misses"]
    return 100 * hits / (hits + misses) if hits + misses else None


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def environment(pg) -> dict:
    return {
        "python": platform.python_version(),
        "pygame": getattr(pg.version, "ver", "?"),
        "sdl": ".".join(map(str, pg.get_sdl_version())),
        "platform": platform.platform(terse=True),
        "machine": platform.machine(),
    }


def main() -> None:
    t0 = float(os.environ.get("BENCH_T0") or clock())
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, help="game root to run in (a sandbox or a checkout)")
    ap.add_argument("--out", required=True, help="where to write the JSON result")
    ap.add_argument("--quick", action="store_true", help="a shorter campaign and fewer steps")
    args = ap.parse_args()
    out = os.path.abspath(args.out)

    os.chdir(args.root)  # the game loads data/ relative to its root
    sys.path[0] = os.path.abspath(args.root)  # replaces this script's directory
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["NINJA_GAME_TESTING"] = "0"  # as app.py: music and ambience play
    os.environ.setdefault("NINJA_LOG_LEVEL", "WARN")

    s = Session(quick=args.quick)
    s.scenario("startup", s.boot, t0)
    env = environment(s.pg) if hasattr(s, "pg") else {}
    if "startup" not in s.errors:
        before = text_cache_stats()
        s.watch_gc()
        s.scenario("campaign", s.campaign)
        s.unwatch_gc()
        s.caches(before)
        s.metrics["memory.campaign_peak_mb"] = peak_rss_mb()  # what a player's session peaks at
        s.summarize()
        s.scenario("levels", s.levels)
        s.summarize()  # adds the level sweep
        s.scenario("hud", s.hud)
        s.scenario("replay_files", s.replay_files)
        s.scenario("training", s.training)  # last: the env opens a fullscreen display
    with open(out, "w") as f:
        json.dump(
            {
                "metrics": s.metrics,
                "detail": s.detail,
                "fingerprint": s.fingerprint,
                "errors": s.errors,
                "env": env,
                "quick": args.quick,
                "wakes": s.wakes,
            },
            f,
            indent=1,
        )


if __name__ == "__main__":
    main()
