"""Play levels in the real game, the way a user does: window, menu, keyboard.

The orchestrator builds a throwaway data sandbox per run (assets linked,
save files fresh, so your own progress, best times and replays stay
untouched) and launches the real `app.main()` in a separate process with a
normal window and the real 60 Hz frame pacing. Inside that process the bot
only injects keyboard events into pygame's event queue:

1. Main menu -> Levels -> picks the level -> back -> Play
2. In the level it presses the keys of the planned route
   (tools/worlds/plans/<id>.json) frame by frame: A/D to run, W to jump,
   Space to dash. Enemies are live and random; if they take all lives the
   level restarts and the bot starts the route over, as a player would.
3. Success = the game shows its level-complete screen.

Each run writes report.json, screenshots and (with --video) an mp4 of the
playthrough to the output directory.

Usage:
    python -m tools.worlds.play 11 [12 13 14 16] [--out DIR] [--attempts 3] [--video]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMLINKS = ["images", "maps", "music", "sfx", "font.ttf", "music.wav"]
COPIES = ["strings.json", "menu.json"]
FRAME_BUDGET = 60 * 60 * 12  # 12 game minutes per run


# --- orchestrator ----------------------------------------------------------------


def build_sandbox(root: str, level: int) -> None:
    data = os.path.join(root, "data")
    os.makedirs(data)
    for name in SYMLINKS:
        src = os.path.join(REPO, "data", name)
        if os.path.exists(src):
            os.symlink(src, os.path.join(data, name))
    for name in COPIES:
        shutil.copy(os.path.join(REPO, "data", name), os.path.join(data, name))
    for name in ("saves", "replays"):
        os.makedirs(os.path.join(data, name))
    with open(os.path.join(data, "collectables.json"), "w") as f:
        json.dump({"coins": 0}, f)
    with open(os.path.join(data, "best_times.json"), "w") as f:
        json.dump({}, f)
    # A player who has unlocked the level; sound off for unattended runs
    settings = {
        "music_volume": 0.0,
        "sound_volume": 0.0,
        "selected_level": 0,
        "selected_editor_level": 0,
        "selected_skin": 0,
        "selected_weapon": 0,
        "selected_gear": 0,
        "playable_levels": {"0": True, str(level): True},
        "show_perf_overlay": False,
        "ghost_enabled": False,
        "ghost_mode": "best",
        "camera_style": "classic",
    }
    with open(os.path.join(data, "settings.json"), "w") as f:
        json.dump(settings, f)


def run_level(level: int, out_dir: str, attempts: int, video: bool) -> dict:
    plan = os.path.join(REPO, "tools", "worlds", "plans", f"{level}.json")
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO
    report: dict = {}
    for attempt in range(1, attempts + 1):
        sandbox = tempfile.mkdtemp(prefix=f"ninja_play_{level}_")
        build_sandbox(sandbox, level)
        run_out = os.path.join(out_dir, f"level_{level}", f"attempt_{attempt}")
        os.makedirs(run_out, exist_ok=True)
        print(f"[play] level {level} attempt {attempt}: real game window, sandbox {sandbox}")
        cmd = [sys.executable, os.path.abspath(__file__), "--bot", str(level), "--plan", plan, "--out", run_out]
        if video:
            cmd.append("--video")
        proc = subprocess.run(cmd, cwd=sandbox, env=env, timeout=FRAME_BUDGET / 60 + 300)
        shutil.rmtree(sandbox, ignore_errors=True)
        with open(os.path.join(run_out, "report.json")) as f:
            report = json.load(f)
        report["attempt"] = attempt
        print(f"[play] level {level}: {'COMPLETED' if report.get('completed') else 'FAILED'} {json.dumps(report)}")
        if proc.returncode == 0 and report.get("completed"):
            break
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--out", default=None)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--bot", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--plan", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.bot is not None:
        return bot_main(args.bot, args.plan, args.out, args.video)

    out = os.path.abspath(args.out or tempfile.mkdtemp(prefix="ninja_play_out_"))
    summary = {}
    for level in args.levels:
        summary[level] = run_level(level, out, args.attempts, args.video)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[play] results in {out}")
    done = sum(1 for r in summary.values() if r.get("completed"))
    print(f"[play] {done}/{len(summary)} levels completed in the real game")
    return 0 if done == len(summary) else 1


# --- bot (runs inside the real game process) ------------------------------------


class Bot:
    MENU_DELAY = 12  # frames between menu key presses

    def __init__(self, level: int, plan: list, out: str, video: bool):
        self.level = level
        self.plan = plan
        self.out = out
        self.video = video
        self.sm = None
        self.frame = 0
        self.wait = 30
        self.phase = "menu"
        self.held: set = set()
        self.updates = 0  # player updates since the last level (re)load
        self.loads = 0
        self.report = {
            "level": level,
            "completed": False,
            "lives_lost": 0,
            "restarts": 0,
            "plan_frames": len(plan),
            "desyncs": 0,
            "dodges": 0,
            "reflexes": 0,
            "replans": 0,
            "checkpoint_restarts": 0,
            "recoveries": 0,
        }
        self.queue: list = []
        self.predicted = None
        self.on_track = True
        self.queue_reaches = False
        self.seg = 0
        self.cooldown = 0
        self.dodge_cooldown = 0
        self.failures = 0
        self.expected = None
        self.last_lives = None
        self.game_frames = 0
        self.t_start = None
        self.done_frames = 0
        self.video_index = 0
        self.select_presses = 0

    # pygame event helpers
    def _key(self, kind, key):
        import pygame

        pygame.event.post(pygame.event.Event(kind, {"key": key, "mod": 0, "unicode": "", "scancode": 0}))

    def tap(self, key):
        import pygame

        self._key(pygame.KEYDOWN, key)
        self._key(pygame.KEYUP, key)

    def hold(self, keys: set):
        import pygame

        for k in self.held - keys:
            self._key(pygame.KEYUP, k)
        for k in keys - self.held:
            self._key(pygame.KEYDOWN, k)
        self.held = set(keys)

    def screenshot(self, name):
        import pygame

        surf = pygame.display.get_surface()
        if surf is not None:
            # The window surface's alpha is 0 on macOS: keep only RGB
            rgb = pygame.image.frombytes(pygame.image.tobytes(surf, "RGB"), surf.get_size(), "RGB")
            pygame.image.save(rgb, os.path.join(self.out, f"{name}.png"))

    def on_frame(self):
        """Called once per game loop iteration, before the game reads events."""
        import pygame

        self.frame += 1
        cur = self.sm.current if self.sm else None
        name = getattr(cur, "name", "")
        if self.frame > FRAME_BUDGET:
            self.finish(False, "frame budget exhausted")
            return
        if self.wait > 0:
            self.wait -= 1
            return
        if name == "MenuState":
            self.menu_main(cur)
        elif name == "LevelsState":
            self.menu_levels(cur)
        elif name == "GameState":
            self.play(cur)
        elif name == "PauseState":
            self.tap(pygame.K_ESCAPE)
            self.wait = self.MENU_DELAY
        elif name == "LevelCompleteState":
            if not self.report["completed"]:
                self.hold(set())
                self.report["completed"] = True
                self.report["game_frames"] = self.game_frames
                self.report["wall_seconds"] = round(time.time() - self.t_start, 1)
                self.report["time_shown"] = cur.time_str
                self.wait = 45
                return
            self.screenshot("99_level_complete")
            self.finish(True, "level complete screen reached")

    def menu_main(self, cur):
        import pygame

        from scripts.settings import settings

        target = 0 if settings.selected_level == self.level else 2  # Play / Levels
        idx = cur.list_widget.selected_index
        if idx < target:
            self.tap(pygame.K_DOWN)
        elif idx > target:
            self.tap(pygame.K_UP)
        else:
            if target == 0:
                self.screenshot("00_menu")
            self.tap(pygame.K_RETURN)
        self.wait = self.MENU_DELAY

    def menu_levels(self, cur):
        import pygame

        from scripts.settings import settings

        if settings.selected_level == self.level:
            self.screenshot("01_level_selected")
            self.tap(pygame.K_BACKSPACE)
        else:
            target = cur.levels.index(self.level)
            idx = cur.widget.selected_index
            if idx < target:
                self.tap(pygame.K_DOWN)
            elif idx > target:
                self.tap(pygame.K_UP)
            elif self.select_presses >= 3:
                self.screenshot("01_level_locked")
                self.finish(False, f"level shows as locked in the menu ({cur.message})")
                return
            else:
                self.select_presses += 1
                self.tap(pygame.K_RETURN)
        self.wait = self.MENU_DELAY

    def play(self, cur):
        import pygame

        g = cur.game
        p = getattr(g, "player", None)
        if p is None:
            return
        if self.t_start is None:
            self.t_start = time.time()
            self.report["map_loaded"] = g.tilemap.loaded_path
        self.game_frames += 1
        if self.last_lives is not None and p.lives < self.last_lives:
            self.report["lives_lost"] += self.last_lives - p.lives
        self.last_lives = p.lives
        if self.game_frames % 600 == 1:
            self.screenshot(f"10_play_{self.game_frames // 60:04d}s")
        if self.video and self.game_frames % 3 == 0:
            surf = pygame.display.get_surface()
            small = pygame.transform.smoothscale(surf, (640, 360))
            pygame.image.save(small, os.path.join(self.out, "frames", f"{self.video_index:05d}.jpg"))
            self.video_index += 1
        if g.dead:
            self.hold(set())
            self.queue = []
            self.predicted = None
            return

        m, jump, dash = self.decide(g, p)
        keys = set()
        if m < 0:
            keys.add(pygame.K_a)
        elif m > 0:
            keys.add(pygame.K_d)
        self.hold(keys)
        if jump:
            self.tap(pygame.K_w)
        if dash:
            self.tap(pygame.K_SPACE)

    # --- decisions ---------------------------------------------------------
    HORIZON = 45  # frames of bullet flight the bot looks ahead

    def decide(self, g, p):
        """Inputs for the next frame: follow the route, dodge what is flying at us."""
        from tools.worlds import physics as ph
        from tools.worlds.planner import plan_segment

        s = (
            p.pos[0],
            p.pos[1],
            p.velocity[0],
            p.velocity[1],
            p.air_time,
            p.jumps,
            p.wall_slide,
            p.dashing,
            p.flip,
            p.last_movement[0],
        )
        down = p.collisions["down"]
        u = self.updates
        if self.predicted is not None and s != self.predicted:
            self.report["desyncs"] += 1
            self.queue = []
            self.on_track = False
        self.predicted = None

        # On the precomputed route while nothing pushed us off it (also right
        # after a level restart: the route starts with idle frames)
        if u < len(self.pre_states) and s == self.pre_states[u] and (self.on_track or u <= 30):
            self.on_track = True
            self.seg = self.seg_of[u] if u < len(self.seg_of) else len(self.route)
            self.queue = (
                list(self.plan[u : self.seg_end[self.seg]]) if self.seg < len(self.route) else list(self.plan[u:])
            )
        else:
            self.on_track = False

        if self.cooldown > 0:  # just failed to find a way on: catch breath
            self.cooldown -= 1
            return 0, False, False
        hazard = self.hazards(g)
        if not self.queue and self.seg < len(self.route):
            while self.seg < len(self.route) and self.route[self.seg].contains(s, down):
                self.seg += 1
            if self.seg < len(self.route):
                wp = self.route[self.seg]
                res = plan_segment(
                    s, wp, self.solids, weight=5.0, max_expand=12000, kill_y=self.kill_y, start_down=down
                )
                if not res.ok:
                    res = plan_segment(
                        s, wp, self.solids, weight=2.0, max_expand=30000, kill_y=self.kill_y, start_down=down
                    )
                self.report["replans"] += 1
                self.queue = res.frames if res.ok else []
                self.queue_reaches = res.ok
                if not res.ok:
                    return self.stuck(s, down)
                self.failures = 0
        if self.dodge_cooldown > 0:
            self.dodge_cooldown -= 1
        elif (
            hazard is not None and self.queue and self.seg < len(self.route) and self.threatened(s, self.queue, hazard)
        ):
            # A bullet would hit us on the way: a quick look for a way round,
            # else the first reflex that gets out of its line (dash, jump, wait, back off)
            res = plan_segment(
                s,
                self.route[self.seg],
                self.solids,
                weight=5.0,
                max_expand=1500,
                kill_y=self.kill_y,
                start_down=down,
                hazard=hazard,
            )
            if res.ok:
                self.queue = res.frames
                self.queue_reaches = True
                self.report["dodges"] += 1
            else:
                reflex = self.reflex(s, hazard)
                if reflex is not None:
                    self.queue = reflex
                    self.queue_reaches = False
                    self.report["reflexes"] += 1
                self.dodge_cooldown = 8
            self.on_track = False
        if not self.queue:
            return 0, False, False
        frame = self.queue.pop(0)
        self.predicted, _d, _dead = ph.apply_frame(s, frame[0], frame[1], frame[2], self.solids)
        if not self.queue and not self.on_track and self.queue_reaches:
            self.seg += 1
        return frame

    def reflex(self, s, hazard):
        """First quick evasion that no bullet in flight hits, or None."""
        from tools.worlds import physics as ph

        m = -1 if s[ph.FLIP] else 1
        options = []
        if s[ph.DASH] == 0:
            options.append([(m, False, True)] + [(m, False, False)] * 10)
        if ph.can_jump(s):
            options.append([(m, True, False)] + [(m, False, False)] * 14)
            options.append([(0, True, False)] + [(0, False, False)] * 14)
        options.append([(0, False, False)] * 12)
        options.append([(-m, False, False)] * 12)
        for frames in options:
            if not self.threatened(s, frames, hazard) and not self.falls(s, frames):
                return list(frames)
        return None

    def falls(self, s, frames) -> bool:
        from tools.worlds import physics as ph

        cur = s
        for m, j, d in frames:
            cur, _down, dead = ph.apply_frame(cur, m, j, d, self.solids)
            if dead or cur[ph.Y] > self.kill_y:
                return True
        return False

    def stuck(self, s, down):
        """No way to the next waypoint from here (after a fall, say): go back to
        the latest earlier one that can be reached and take the route again,
        as a player would. Only if none can: wait, and after a few tries restart
        from the checkpoint (R)."""
        import pygame

        from tools.worlds import physics as ph
        from tools.worlds.planner import plan_segment

        self.report.setdefault("stuck_at", []).append(
            [self.route[self.seg].label, round(s[ph.X] / 16, 1), round(s[ph.Y] / 16, 1)]
        )
        for back in range(1, 9):
            k = self.seg - back
            if k < 0:
                break
            res = plan_segment(
                s, self.route[k], self.solids, weight=5.0, max_expand=6000, kill_y=self.kill_y, start_down=down
            )
            if res.ok:
                self.seg = k
                self.queue = res.frames
                self.queue_reaches = True
                self.report["recoveries"] += 1
                return self.queue.pop(0) if self.queue else (0, False, False)
        self.failures += 1
        self.cooldown = 20
        if self.failures >= 3:
            self.failures = 0
            self.report["checkpoint_restarts"] += 1
            self.tap(pygame.K_r)
        return 0, False, False

    def hazards(self, g):
        """Hit test for the enemy bullets in flight, or None if there are none."""
        from tools.worlds import physics as ph

        trajectories = []
        for proj in g.projectiles:
            if proj.get("owner") != "enemy":
                continue
            x, y = proj["pos"]
            vx, vy = proj["vel"]
            grav = proj.get("gravity", 0.0)
            age = proj["age"]
            pts = []
            for _ in range(self.HORIZON):
                vy += grav
                x += vx
                y += vy
                age += 1
                if (int(x // 16), int(y // 16)) in self.solids or age > 360:
                    break
                pts.append((int(x), int(y)))
            if pts:
                trajectories.append(pts)
        if not trajectories:
            return None

        def hit(t, st):
            if abs(st[ph.DASH]) >= 50:
                return False
            rx, ry = int(st[ph.X]), int(st[ph.Y])
            for pts in trajectories:
                if t < len(pts):
                    bx, by = pts[t]
                    if rx < bx + 4 and bx < rx + 8 and ry < by + 4 and by < ry + 15:
                        return True
            return False

        return hit

    def threatened(self, s, queue, hazard) -> bool:
        from tools.worlds import physics as ph

        cur = s
        for t, (m, j, d) in enumerate(queue[: self.HORIZON]):
            if hazard(t, ph.press_dash(cur) if d else cur):
                return True
            cur, _down, _dead = ph.apply_frame(cur, m, j, d, self.solids)
        return False

    def finish(self, ok: bool, reason: str):
        import pygame

        self.report["reason"] = reason
        with open(os.path.join(self.out, "report.json"), "w") as f:
            json.dump(self.report, f, indent=2)
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.phase = "done"


def bot_main(level: int, plan_path: str, out: str, video: bool) -> int:
    sys.path.insert(0, REPO)
    import pygame

    import app
    import game as game_mod
    from scripts import state_manager as smod
    from scripts.entities import Player
    from tools.worlds import physics as ph
    from tools.worlds.route import load_plan

    data = load_plan(level)
    plan = data["frame_list"]
    if video:
        os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    bot = Bot(level, plan, out, video)

    # Precomputed route: state after every update, segment of every frame
    with open(os.path.join("data", "maps", f"{level}.json")) as f:
        solids = ph.solids_from_map(json.load(f)["map_data"]["tilemap"])
    s = ph.spawn_state(*data["spawn"])
    pre_states = [s]
    for m, j, d in plan:
        s, _down, _dead = ph.apply_frame(s, m, j, d, solids)
        pre_states.append(s)
    seg_end = [start + n for start, n in data["segments"]]
    seg_of = []
    k = 0
    for i in range(len(plan)):
        while k < len(seg_end) and i >= seg_end[k]:
            k += 1
        seg_of.append(k)
    bot.solids = solids
    bot.pre_states = pre_states
    bot.seg_end = seg_end
    bot.seg_of = seg_of
    bot.route = data["waypoints"]
    bot.kill_y = (max(y for _, y in solids) + 4) * 16

    # Instrumentation only: find the state manager, count player updates
    orig_sm_init = smod.StateManager.__init__

    def sm_init(self):
        orig_sm_init(self)
        bot.sm = self

    smod.StateManager.__init__ = sm_init

    orig_load = game_mod.Game.load_level

    def load_level(self, *a, **k):
        orig_load(self, *a, **k)
        if bot.loads:
            bot.report["restarts"] += 1
        bot.loads += 1
        bot.updates = 0

    game_mod.Game.load_level = load_level

    orig_update = Player.update

    def player_update(self, tilemap, movement=(0, 0)):
        result = orig_update(self, tilemap, movement)
        if self is getattr(self.game, "player", None):
            bot.updates += 1
        return result

    Player.update = player_update

    real_get = pygame.event.get

    def event_get(*a, **k):
        if bot.phase != "done":
            bot.on_frame()
        return real_get(*a, **k)

    pygame.event.get = event_get
    sys.argv = [sys.argv[0]]
    try:
        app.main()
    except SystemExit:  # the game quits this way from inside a level
        pass
    finally:
        if not os.path.exists(os.path.join(out, "report.json")):
            bot.report["reason"] = "game exited"
            with open(os.path.join(out, "report.json"), "w") as f:
                json.dump(bot.report, f, indent=2)
    if video and bot.video_index:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                "20",
                "-i",
                os.path.join(out, "frames", "%05d.jpg"),
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "scale=640:360",
                os.path.join(out, f"level_{level}.mp4"),
            ],
            check=False,
        )
        shutil.rmtree(os.path.join(out, "frames"), ignore_errors=True)
    return 0 if bot.report["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
