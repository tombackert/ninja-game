#!/usr/bin/env python3
"""Render the game trailer: an MP4 with sound and a GIF for the README.

Usage (from the repo root):
    python tools/trailer.py              # docs/media/trailer.mp4, trailer.gif, social-preview.png, levels.png
    python tools/trailer.py --sheet      # three stills per shot in one image, a quick check
    python tools/trailer.py --sheet 12-20  # ... of the timeline's items 12 to 20 only
    python tools/trailer.py --levels     # only levels.png, the README's level matrix
    python tools/trailer.py --no-gif

Needs ffmpeg on PATH and numpy (the sound mix). Nothing in data/ is
written: settings changes stay in memory and the runs are never recorded
or saved.

Every gameplay shot is a real run, re-simulated headless through
GameState.update() like live play:

- runs played by hand, from tools/trailer_replays/<level>-<name>.json
  (copied from data/replays/ of a dev checkout or of the desktop app; the
  "evening" runs were played on the evening of the multiplayer session the
  trailer shows), and
- the route plans of the built levels 11-40 (tools/worlds/plans/,
  Shot.run = "plan"), the frame-exact routes the level tools check.

A replay stores the player's inputs and, every 10 ticks, where the player
was; it does not store the gameplay RNG, so the enemies of a re-simulation
do not move exactly as they did. A hit that never happened would throw the
run off its course, so the player is put back on it at every stored
snapshot (Run.resync). A plan's snapshots come from playing it once
without enemies. The shots are picked where no correction is needed, so
what is on screen is what the run did.

Weapons and gear are not in any run: the weapon shots add the presses
(Shot.fire, Shot.press). The cut runs on the music's beat (160 BPM, 22.5
frames a beat): every item lasts a whole number of beats and the music is
arranged from whole bars of the game's track (MUSIC). The camera frames
`Shot.view` game pixels (480x270 by default, closer or wider per shot),
scaled to 1920x1080 by the renderer with its sub-pixel glide; the overlays
(captions, lower thirds, name tags) use the game's pixel font on a
480x270 grid.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPLAYS = os.path.join(ROOT, "tools", "trailer_replays")
OUT_DIR = os.path.join(ROOT, "docs", "media")

OUT_W, OUT_H = 1920, 1080
VIEW_W, VIEW_H = 480, 270  # default world framing and the overlay grid, in game pixels
SCALE = OUT_W // VIEW_W  # overlay grid -> output
FPS = 60
BEAT = 0.375  # s: 160 BPM
PHASE = 0.36  # s: the first beat of the music
GIF_W, GIF_FPS = 640, 15  # 15 = every fourth 60 Hz frame, even cadence; the whole trailer stays small
SOCIAL_VIEW = (640, 320)  # GitHub social preview, scaled 2x to 1280x640
GRID_VIEW, GRID_SCALE = (320, 180), 2  # a cell of the level matrix: small on the page, so framed closer
GRID_GAP = 8

INK = (22, 24, 48)  # outline / shadow colour of all trailer text
ACCENT = (232, 110, 60)  # the menus' highlight orange
GHOST_TINT = (100, 220, 255)  # ReplayGhost's tint
WHITE = (255, 255, 255)

# Close-ups, the default and wide shots: whole multiples of the 1920x1080 frame
CLOSE, MID, WIDE = (384, 216), (480, 270), (640, 360)


@dataclass
class Shot:
    """`beats` beats of a level's run, from run tick `start` on."""

    level: int
    start: int
    beats: int
    run: str = "best"  # tools/trailer_replays/<level>-<run>.json, or "plan" (the route plan)
    view: tuple[int, int] = MID
    seed: int = 0  # gameplay RNG, i.e. what the enemies do
    # Overlays
    caption: str = ""  # big line at the bottom; runs on across shots that share it
    kicker: str = ""  # lower third: small orange line (the chapter) ...
    title: str = ""  # ... over the white line (the level)
    heading: str = ""  # big line in the middle (a section)
    tag: str = ""  # name tag over the player
    callouts: tuple[str, ...] = ()  # enemy kinds to name on screen
    race: bool = False  # race HUD: timer, YOU and BEST RUN tags
    flash: bool = False  # white flash on the cut
    # The ninja
    skin: int = 0
    weapon: str = "Default"
    gear: str = "None"
    fire: tuple[int, ...] = ()  # frames into the shot at which the ninja uses the weapon
    press: tuple[tuple[int, str], ...] = ()  # extra inputs: (frame into the shot, action)
    sync_until: int | None = None  # frame into the shot from which the run is no longer resynced
    # Others
    ghost: str | None = None  # run raced as the ghost
    rivals: tuple[tuple[str, int, int, str], ...] = ()  # (run, skin, tick offset, tag): other ninjas
    pan: tuple[tuple[float, float], tuple[float, float]] | None = None  # camera centre from, to (world px)
    mute: bool = False


@dataclass
class Card:
    """A full-screen moment: the title, a menu of the game, the end."""

    kind: str  # "title", "end", "levels" or "store"
    beats: int
    bg: Shot | None = None  # gameplay behind it, dimmed
    heading: str = ""
    caption: str = ""


Item = Shot | Card

# The music: (first bar of the game's track, bars) in order. A bar is 4 beats,
# 1.5 s. Bars 0-31 run as they are, 8-31 again, then the quiet bars 32-39
# under the end card, faded out.
MUSIC = [(0, 32), (8, 24), (32, 8)]


def item_frames(timeline: list[Item]) -> list[int]:
    """Frames of each item: cuts fall on the frame nearest to their beat."""

    def at(beat: int) -> int:
        return 0 if beat == 0 else round((PHASE + beat * BEAT) * FPS)

    out, beat = [], 0
    for item in timeline:
        out.append(at(beat + item.beats) - at(beat))
        beat += item.beats
    return out


# --- the cut --------------------------------------------------------------
# Filled in below the engine (TIMELINE), so the engine reads top to bottom.


def still(level: int, tick: int, run: str = "best", seed: int = 0) -> Shot:
    return Shot(level=level, start=tick, beats=0, run=run, seed=seed)


# The README's level matrix, row by row: three frames of real runs per world,
# mixed so that no world sits next to itself and it looks like many levels.
LEVEL_GRID: list[list[Shot]] = [
    [still(0, 150), still(14, 300, seed=1), still(12, 450, "plan"), still(20, 300), still(25, 1232, "plan")],
    [still(18, 2250), still(3, 300), still(21, 460, "plan"), still(16, 2850, "plan"), still(3, 2850)],
    [
        still(12, 1500, "plan"),
        still(23, 1050, "plan"),
        still(16, 1650, "plan"),
        still(7, 150, "dev"),
        still(15, 300, "plan"),
    ],
]


def boot():
    """Start pygame headless in the repo root (assets load relative to it)."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["NINJA_GAME_TESTING"] = "1"
    os.chdir(ROOT)
    import pygame

    pygame.init()
    pygame.display.set_mode((OUT_W, OUT_H))

    from scripts.settings import settings
    from scripts.timer import Timer

    settings.flush = lambda: None  # keep data/settings.json untouched
    Timer.save_best_times = lambda self: None  # and data/best_times.json, should a run reach the flag
    settings.camera_style = "classic"
    settings.selected_gear = 0
    return pygame


def plan_replay(level: int) -> dict:
    """A level's route plan as replay data, its inputs as they are.

    No snapshots: from a played run's, `Run` would take swim strokes for
    jumps that failed and drop them.
    """
    from tools.worlds.route import load_plan

    keys = {-1: "left", 1: "right"}
    inputs, held = [], 0
    for tick, (move, jump, dash) in enumerate(load_plan(level)["frame_list"]):
        actions = []
        if move != held:
            if held:
                actions.append("stop_" + keys[held])
            if move:
                actions.append(keys[move])
            held = move
        if jump:
            actions.append("jump")
        if dash:
            actions.append("dash")
        inputs.append({"tick": tick, "inputs": actions})
    return {"inputs": inputs, "snapshots": {}}


def replay_path(level: int, kind: str) -> str:
    return kind if os.path.isabs(kind) else os.path.join(REPLAYS, f"{level}-{kind}.json")


class Run:
    """A replay's inputs, rebuilt into what the player actually did."""

    def __init__(self, level: int, kind: str = "best"):
        if kind == "plan":
            self.data = plan_replay(level)
        else:
            with open(replay_path(level, kind)) as f:
                self.data = json.load(f)
        self.snaps = {int(t): s["players"][0] for t, s in self.data["snapshots"].items() if s.get("players")}
        self.events = self._events(self.data["inputs"])
        self.held = self._held(self.data["inputs"])
        # Where the player really was, every 10 ticks: a played run's own
        # snapshots; a plan's come from playing it without enemies (Studio.plan_sync)
        self.sync = dict(self.snaps)

    def _dash_starts(self) -> set[int]:
        # A dash counts from +-60 towards 0 once per tick, so a snapshot
        # taken during one tells when it started - unless the snapshot ten
        # ticks earlier already saw the same dash.
        starts = set()
        for t, s in self.snaps.items():
            d = s["dashing"]
            prev = self.snaps.get(t - 10, {}).get("dashing", 0)
            if d and prev != d + (10 if d > 0 else -10):
                starts.add(t - (60 - abs(d)))
        return starts

    def _jumped(self, t: int) -> bool:
        """Whether a jump at tick t took off (a jump sets air_time to 5)."""
        nxt = next((u for u in range(t + 1, t + 11) if u in self.snaps), None)
        return nxt is None or self.snaps[nxt]["air_time"] == nxt - t + 5

    def _events(self, inputs) -> dict[int, list[str]]:
        starts = self._dash_starts()
        events: dict[int, list[str]] = {}
        for entry in inputs:
            t = entry["tick"]
            for action in entry["inputs"]:
                if action == "jump":
                    # Space dashes and Up/W jump, both recorded as "jump"
                    if t in starts:
                        starts.discard(t)
                        events.setdefault(t, []).append("dash")
                    if not self._jumped(t):
                        continue
                events.setdefault(t, []).append(action)
        for t in starts:  # mouse dashes: no input recorded at all
            if t >= 0:
                events.setdefault(t, []).insert(0, "dash")
        return events

    @staticmethod
    def _held(inputs) -> list[bool]:
        """Keys already held when the recording started (first seen released)."""
        held: dict[int, bool] = {}
        for entry in inputs:
            for action in entry["inputs"]:
                for i, key in enumerate(("left", "right")):
                    if i not in held and action in (key, "stop_" + key):
                        held[i] = action == "stop_" + key
        return [held.get(0, False), held.get(1, False)]

    def place(self, player) -> None:
        """Put the player in the state the recording starts with (a plan: the spawn)."""
        if 0 not in self.snaps:
            return
        s = self.snaps[0]
        player.pos = list(s["pos"])
        player.velocity = list(s["velocity"])
        for name in ("air_time", "jumps", "wall_slide", "dashing", "flip"):
            setattr(player, name, s[name])

    def resync(self, tick: int, player) -> float:
        """Put the player back on the recorded run at a snapshot tick.

        Returns how far (px) the player was off; the shots are picked where
        that stays 0.
        """
        s = self.sync.get(tick)
        if s is None:
            return 0.0
        off = abs(s["pos"][0] - player.pos[0]) + abs(s["pos"][1] - player.pos[1])
        if off < 0.01:
            return 0.0
        player.pos = list(s["pos"])
        player.velocity = list(s["velocity"])
        for name in ("air_time", "jumps", "wall_slide", "dashing", "flip", "breath", "swim_cooldown"):
            if name in s:
                setattr(player, name, s[name])
        return off

    def feed(self, tick: int, player, movement: list[bool], audio) -> None:
        """Apply one tick's inputs the way KeyboardManager does."""
        for action in self.events.get(tick, ()):
            if action in ("left", "right"):
                movement[action == "right"] = True
            elif action in ("stop_left", "stop_right"):
                movement[action == "stop_right"] = False
            elif action == "jump":
                if player.jump():
                    audio.play("jump")
            elif action == "dash":
                player.dash()
            elif action == "shoot":
                player.shoot()


class Extras:
    """Stands in for the ReplayManager: draws ghost and rivals, never records or saves."""

    def __init__(self, *puppets):
        self.puppets = [p for p in puppets if p]

    def on_level_load(self, *args):
        pass

    def update(self, *args):
        pass

    def commit_run(self, *args, **kwargs):
        pass

    def abort_current_run(self):
        pass

    def render_ghost(self, surface, offset):
        for puppet in self.puppets:
            puppet.step_and_render(surface, offset)


def make_puppet(game, run: Run, rival: bool, skin: int):
    """A ReplayGhost driven by the rebuilt inputs; a rival is drawn untinted."""
    from scripts.replay import ReplayData, ReplayGhost

    class Rival(ReplayGhost):
        def _render_tinted(self, surface, offset):
            self.entity.render(surface, offset)

    puppet = (Rival if rival else ReplayGhost)(
        game, ReplayData.from_json({"level": "0", "skin": "default", **run.data})
    )
    puppet.data.snapshots = (
        {str(t): {"players": [s]} for t, s in run.sync.items()} if not run.snaps else puppet.data.snapshots
    )
    puppet.input_map = run.events
    run.place(puppet.entity)
    puppet.entity.input_left, puppet.entity.input_right = run.held
    set_skin(puppet.entity, skin)
    return puppet


def set_skin(player, skin: int) -> None:
    """Swap the skin without restarting the current animation."""
    player.skin = skin
    action = player.action
    frame = player.animation.frame if player.animation else 0
    player.action = None
    player.set_action(action or "idle")
    player.animation.frame = frame


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


class Studio:
    """Boots the game headless and turns the timeline into frames and sound cues."""

    def __init__(self):
        self.pg = pygame = boot()
        from scripts.audio_service import AudioService
        from scripts.renderer import Renderer

        self.renderer = Renderer(show_perf=False)
        self.renderer._render_hud = lambda *args, **kwargs: None  # clean frames, no HUD
        self.out = pygame.Surface((OUT_W, OUT_H))
        self.font = {size: pygame.font.Font(os.path.join(ROOT, "data", "font.ttf"), size) for size in (8, 16, 32)}
        self.frame_no = 0  # output frames so far
        self.cues: list[tuple[int, str]] = []  # (output frame, sound)
        self.listening = False
        self._sync_cache: dict = {}
        audio = AudioService.get()
        audio.play = self._cue
        audio.play_music = lambda *args, **kwargs: None
        # Filled per frame by a shot: what the overlays point at
        self.view = MID
        self.scroll = (0.0, 0.0)
        self.game = None
        self.run_tick = 0

    def _cue(self, name, loops=0):
        if self.listening and not loops:
            self.cues.append((self.frame_no, name))

    # --- world -----------------------------------------------------------
    def stage(self, level: int, seed: int, weapon: str = "Default", view=MID, gear: str = "None"):
        """A fresh GameState on `level`, framed to `view`."""
        pygame = self.pg
        from scripts.collectableManager import CollectableManager
        from scripts.rng_service import RNGService
        from scripts.settings import settings
        from scripts.state_manager import GameState

        RNGService.get().seed(seed)
        random.seed(seed)  # screenshake
        settings.selected_level = level
        settings.selected_skin = 0
        settings.selected_weapon = CollectableManager.WEAPONS.index(weapon)
        settings.selected_gear = CollectableManager.GEAR.index(gear)
        settings.ghost_enabled = False
        gs = GameState()
        g = gs.game
        g.players = [g.player]  # one ninja; levels with a second spawn would show it idle
        g.replay = Extras()
        # The weapon and gear on show are owned (and loaded)
        for name in {weapon, gear} - {"Default", "None"}:
            item = CollectableManager._ITEM_DEFS[name]
            setattr(g.cm, item.attr, max(getattr(g.cm, item.attr), item.increment))
        g.cm.ammo = max(g.cm.ammo, 50)
        g.player.lives = 99  # a hit the run never took must not end it
        g.BASE_W, g.BASE_H = view
        g.display = pygame.Surface((view[0] + 1, view[1] + 1), pygame.SRCALPHA)
        g.display_2 = pygame.Surface((view[0] + 1, view[1] + 1), pygame.SRCALPHA)
        return gs

    def plan_sync(self, level: int, run: Run) -> None:
        """Snapshots of a route plan played without enemies: the route as planned."""
        key = ("plan", level)
        if key not in self._sync_cache:
            from scripts.snapshot import SnapshotService

            gs = self.stage(level, 0)
            g = gs.game
            g.enemies.clear()
            plan = Run(level, "plan")
            g.movement = list(plan.held)
            sync = {}
            listening, self.listening = self.listening, False
            for tick in range(len(plan.data["inputs"])):
                if g.dead or g.endpoint:
                    break
                if tick % 10 == 0:
                    snap = SnapshotService.serialize(SnapshotService.capture(g, optimized=True))
                    sync[tick] = snap["players"][0]
                plan.feed(tick, g.player, g.movement, g.audio)
                gs.update(1 / FPS)
                while g.hitstop:  # let a hit-stop run out: one tick per recorded input
                    gs.update(1 / FPS)
            self.listening = listening
            self._sync_cache[key] = sync
        run.sync = self._sync_cache[key]

    def load_run(self, level: int, kind: str) -> Run:
        run = Run(level, kind)
        if kind == "plan":
            self.plan_sync(level, run)
        return run

    def frame_camera(self, g) -> None:
        g.scroll = [g.player.rect().centerx - g.BASE_W / 2, g.player.rect().centery - g.BASE_H / 2]

    def shot(self, shot: Shot, frames: int, out=None, render=True):
        """Yield the frames of a gameplay shot, rendered into `out`."""
        from scripts.constants import TRANSITION_MAX

        out = out or self.out
        gs = self.stage(shot.level, shot.seed, shot.weapon, shot.view, shot.gear)
        g = gs.game
        run = self.load_run(shot.level, shot.run)
        extra: dict[int, list[str]] = {}
        for f in shot.fire:
            extra.setdefault(f, []).append("shoot")
        for f, action in shot.press:
            extra.setdefault(f, []).append(action)
        run.place(g.player)
        g.movement = list(run.held)
        set_skin(g.player, shot.skin)
        puppets = []
        if shot.ghost:
            puppets.append(make_puppet(g, self.load_run(shot.level, shot.ghost), rival=False, skin=0))
        for kind, skin, offset, _tag in shot.rivals:
            puppet = make_puppet(g, self.load_run(shot.level, kind), rival=True, skin=skin)
            for _ in range(offset):  # starts `offset` ticks further into its run
                puppet.step()
            puppets.append(puppet)
        g.replay = Extras(*puppets)
        self.puppets = puppets
        self.frame_camera(g)
        scratch = self.pg.Surface((g.BASE_W + 1, g.BASE_H + 1), self.pg.SRCALPHA)
        self.view, self.game = shot.view, g

        tick = 0
        for i in range(shot.start + frames):
            live = i >= shot.start
            f = i - shot.start
            if not g.dead and not g.hitstop:  # a hit-stop frame runs no tick (Game.hitstop)
                if shot.sync_until is None or f < shot.sync_until:
                    run.resync(tick, g.player)
                run.feed(tick, g.player, g.movement, g.audio)
                for action in extra.get(f, ()):
                    if action == "shoot":
                        g.player.shoot()
                    elif action == "jump" and g.player.jump():
                        g.audio.play("jump")
                    elif action == "dash":
                        g.player.dash()
                tick += 1
            self.run_tick = tick
            self.listening = live and not shot.mute
            gs.update(1 / FPS)
            if g.endpoint and g.transition >= TRANSITION_MAX:
                raise SystemExit(f"shot on level {shot.level} runs past the level end")
            if shot.pan:
                k = (i - shot.start) / max(1, frames - 1) if live else 0.0
                k = k * k * (3 - 2 * k)
                (x0, y0), (x1, y1) = shot.pan
                g.scroll = [x0 + (x1 - x0) * k - g.BASE_W / 2, y0 + (y1 - y0) * k - g.BASE_H / 2]
            if live:
                self.scroll = tuple(g.scroll)
                if render:
                    self.renderer.render(g, out)
                yield out
            else:
                g.replay.render_ghost(scratch, (0, 0))  # keep ghost and rivals in step
            if not live and i == shot.start - 1 and not shot.pan:
                self.frame_camera(g)  # cut in with a settled camera
        self.listening = False

    def to_grid(self, x: float, y: float) -> tuple[float, float]:
        """World px -> the overlay grid (480x270) of the frame being drawn."""
        k = VIEW_W / self.view[0]
        return (x - self.scroll[0]) * k, (y - self.scroll[1]) * k

    # --- overlays --------------------------------------------------------
    def layer(self):
        return self.pg.Surface((VIEW_W, VIEW_H), self.pg.SRCALPHA)

    def text(self, layer, text, size, center, color=WHITE, shadow=ACCENT, alpha=255, anchor="center"):
        """Pixel text with a 1px outline and a drop shadow, placed at `center`."""
        pygame = self.pg
        font = self.font[size]
        glyphs = font.render(text, False, color)
        ink = font.render(text, False, INK)
        d = max(1, size // 8)
        w, h = glyphs.get_size()
        surf = pygame.Surface((w + 4 * d, h + 4 * d), pygame.SRCALPHA)
        if shadow:  # sticks out one step below-right of the outline
            surf.blit(font.render(text, False, shadow), (d * 3, d * 3))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            surf.blit(ink, (d + dx * d, d + dy * d))
        surf.blit(glyphs, (d, d))
        surf.set_alpha(alpha)
        x = center[0] - (surf.get_width() / 2 if anchor == "center" else 0)
        layer.blit(surf, (round(x), round(center[1] - surf.get_height() / 2)))
        return surf.get_width()

    def caption(self, layer, text, age, left, y=VIEW_H - 34):
        """Big line at the bottom: slides up when it appears, fades before it leaves."""
        rise = max(0, 6 - age)
        alpha = min(255, age * 40, left * 40)
        self.text(layer, text, 16, (VIEW_W / 2, y + rise), alpha=alpha)

    def lower_third(self, layer, kicker, title, age, left, title_age):
        """Chapter and level, bottom left: an orange bar grows, the lines slide in."""
        pygame = self.pg
        out = min(1.0, left / 8)
        x, base = 18, VIEW_H - 22
        bar_h = round(30 * ease_out(age / 8) * out)
        if bar_h:
            pygame.draw.rect(layer, ACCENT, (x, base - bar_h, 3, bar_h))

        def slid(a):
            return round(10 * (1 - ease_out((a - 3) / 10))), round(255 * min(1.0, max(0, a - 3) / 6) * out)

        if kicker:
            slide, alpha = slid(age)
            self.text(
                layer, kicker, 8, (x + 8 - slide, base - 26), color=ACCENT, shadow=None, alpha=alpha, anchor="left"
            )
        if title:
            slide, alpha = slid(title_age)
            self.text(layer, title, 16, (x + 7 - slide, base - 9), alpha=alpha, anchor="left")

    def heading(self, layer, text, age, left):
        """A section's name in the middle: punches in, a line runs out under it."""
        pygame = self.pg
        alpha = round(255 * min(1.0, age / 3, left / 6))
        if age < 6:  # overshoot: big, then settles
            k = 1 + 0.35 * (1 - ease_out(age / 6))
            tmp = self.layer()
            self.text(tmp, text, 32, (VIEW_W / 2, VIEW_H / 2 - 8), alpha=alpha)
            big = pygame.transform.scale_by(tmp, k)
            layer.blit(big, (VIEW_W / 2 - big.get_width() / 2, VIEW_H / 2 - big.get_height() / 2))
        else:
            self.text(layer, text, 32, (VIEW_W / 2, VIEW_H / 2 - 8), alpha=alpha)
        w = round(150 * ease_out((age - 3) / 10) * min(1.0, left / 6))
        if w > 0:
            pygame.draw.rect(layer, ACCENT, (VIEW_W / 2 - w, VIEW_H / 2 + 14, 2 * w, 2))

    def tag(self, layer, text, at, color=WHITE, alpha=255):
        """A name tag pointing down at `at` (grid px)."""
        pygame = self.pg
        font = self.font[8]
        glyphs = font.render(text, False, color)
        w, h = glyphs.get_width() + 6, glyphs.get_height() + 3
        x = round(min(max(at[0] - w / 2, 2), VIEW_W - w - 2))
        y = round(at[1] - h - 4)
        box = pygame.Surface((w, h + 3), pygame.SRCALPHA)
        pygame.draw.rect(box, (*INK, 215), (0, 0, w, h))
        pygame.draw.rect(box, (*color, 255), (0, h - 1, w, 1))
        tip = round(at[0]) - x
        if 2 <= tip <= w - 3:
            pygame.draw.polygon(box, (*INK, 215), [(tip - 2, h), (tip + 2, h), (tip, h + 2)])
        box.blit(glyphs, (3, 1))
        box.set_alpha(alpha)
        layer.blit(box, (x, y))

    def entity_top(self, entity) -> tuple[float, float]:
        r = entity.rect()
        return self.to_grid(r.centerx, r.top - 2)

    def callout(self, layer, kind, age):
        """Name the enemy of this kind nearest the middle of the picture."""
        g = self.game
        cx, cy = self.scroll[0] + self.view[0] / 2, self.scroll[1] + self.view[1] / 2
        near = [e for e in g.enemies if e.kind.name == kind]
        if not near:
            return
        e = min(near, key=lambda e: (e.pos[0] - cx) ** 2 + (e.pos[1] - cy) ** 2)
        x, y = self.entity_top(e)
        if -10 < x < VIEW_W + 10 and 0 < y < VIEW_H + 20:
            self.tag(layer, kind.upper(), (x, y), color=ACCENT, alpha=min(255, age * 50))

    def race_hud(self, layer, puppets):
        t = self.run_tick / FPS
        self.text(layer, f"{int(t // 60):02}:{t % 60:05.2f}", 16, (VIEW_W / 2, 18), shadow=None)
        you = self.entity_top(self.game.player)
        self.tag(layer, "YOU", you)
        for p in puppets:
            x, y = self.entity_top(p.entity)
            if abs(x - you[0]) < 40 and abs(y - you[1]) < 14:  # stacked over YOU, not on it
                y = min(y, you[1]) - 13
            self.tag(layer, "BEST RUN", (x, y), color=GHOST_TINT)

    def letterbox(self, layer, k):
        h = round(32 * k)
        if h:
            layer.fill((0, 0, 0, 255), (0, 0, VIEW_W, h))
            layer.fill((0, 0, 0, 255), (0, VIEW_H - h, VIEW_W, h))

    # --- cards -----------------------------------------------------------
    def card(self, card: Card, frames: int):
        """Yield the background frames of a card (a dimmed shot or level)."""
        pygame = self.pg
        dim = pygame.Surface((OUT_W, OUT_H), pygame.SRCALPHA)
        dim.fill((*INK, 150 if card.kind != "end" else 170))
        if card.bg:
            bg = Shot(**{**card.bg.__dict__, "mute": True})
            source = self.shot(bg, frames)
        else:
            gs = self.stage(0, 0)
            g = gs.game
            g.transition = 0
            g.players = []
            g.scroll = [260 - VIEW_W / 2, 150 - VIEW_H / 2]

            def still_level():
                for _ in range(frames):
                    g.step()
                    self.renderer.render(g, self.out)
                    yield self.out

            source = still_level()
        for frame in source:
            frame.blit(dim, (0, 0))
            yield frame

    def idle_anims(self, g):
        from scripts.collectableManager import CollectableManager

        return [g.assets[f"player/{p}/idle"].copy() for p in CollectableManager.SKIN_PATHS]

    def run_anims(self, g):
        from scripts.collectableManager import CollectableManager

        return [g.assets[f"player/{p}/run"].copy() for p in CollectableManager.SKIN_PATHS]

    def title_layer(self, layer, i, anims):
        drop = max(0.0, 1 - i / 10)
        y = 108 - round(70 * drop * drop) + (3 if 10 <= i < 14 else 0)
        self.text(layer, "NINJA GAME", 32, (VIEW_W / 2, y))
        if i >= 18:
            alpha = min(255, (i - 18) * 32)
            self.text(layer, "A FAST PIXEL-ART PLATFORMER", 8, (VIEW_W / 2, 148), shadow=None, alpha=alpha)
        if i >= 26:
            alpha = min(255, (i - 26) * 32)
            self.text(
                layer,
                "41 LEVELS  -  7 WORLDS  -  ONLINE MULTIPLAYER",
                8,
                (VIEW_W / 2, 164),
                color=ACCENT,
                shadow=None,
                alpha=alpha,
            )
        if i >= 10:
            img = self.pg.transform.scale_by(anims[0].img(), 3)
            layer.blit(img, (VIEW_W / 2 - img.get_width() / 2, 190))

    def end_layer(self, layer, i, anims):
        drop = max(0.0, 1 - i / 10)
        self.text(layer, "NINJA GAME", 32, (VIEW_W / 2, 46 - round(40 * drop * drop)))
        n = len(anims)
        for k, anim in enumerate(anims):
            if i < 8 + k * 4:
                continue
            img = self.pg.transform.scale_by(anim.img(), 3)
            x = VIEW_W / 2 + (k - (n - 1) / 2) * 50
            pop = 1 - ease_out((i - 8 - k * 4) / 8)
            layer.blit(img, (round(x - img.get_width() / 2), 80 - round(12 * pop)))
        if i >= 50:
            alpha = min(255, (i - 50) * 32)
            self.text(layer, "FREE & OPEN SOURCE", 16, (VIEW_W / 2, 160), alpha=alpha)
            self.text(
                layer, "WINDOWS  -  MACOS  -  LINUX", 8, (VIEW_W / 2, 184), color=ACCENT, shadow=None, alpha=alpha
            )
        if i >= 70:
            alpha = min(255, (i - 70) * 32)
            self.text(layer, "github.com/tombackert/ninja-game", 8, (VIEW_W / 2, 206), shadow=None, alpha=alpha)
        if i >= 95:
            alpha = min(255, (i - 95) * 32)
            self.text(layer, "PLAY IT. MOD IT. STAR IT.", 8, (VIEW_W / 2, 234), color=ACCENT, shadow=None, alpha=alpha)

    def menu_panel(self, kind: str):
        """A menu of the game as it looks in the window, 1280x720, and a step function."""
        pygame = self.pg
        from scripts.progress_tracker import get_progress_tracker
        from scripts.settings import settings

        tracker = get_progress_tracker()
        for lvl in list(tracker.levels):
            try:
                tracker.unlock(lvl)
            except Exception:
                pass
        surface = pygame.Surface((1280, 720))
        if kind == "levels":
            from scripts.state_manager import LevelsState

            settings.selected_level = 11
            state = LevelsState()
            state.best_times = {}

            def step(i):
                if i and i % 23 == 0:
                    state.widget.move_down()

        else:
            from scripts.state_manager import StoreState

            state = StoreState()
            state.cm.coins = 9999
            state.handle_actions(["menu_select"])  # the weapons page
            state.update(1 / FPS)

            def step(i):
                if i and i % 23 == 0:
                    state.handle_actions(["menu_down"])

        def frame(i):
            step(i)
            state.update(1 / FPS)
            state.render(surface)
            return surface

        return frame

    def ui_card(self, card: Card, frames: int):
        """A menu shown floating over the dimmed game, scaling in."""
        pygame = self.pg
        panel = self.menu_panel(card.kind)
        shadow = pygame.Surface((1280 + 40, 720 + 40), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 0))
        pygame.draw.rect(shadow, (0, 0, 0, 120), shadow.get_rect(), border_radius=18)
        for i, frame in enumerate(self.card(card, frames)):
            surf = panel(i)
            k = 0.86 + 0.08 * ease_out(i / 18)
            w, h = round(1280 * k), round(720 * k)
            img = pygame.transform.smoothscale(surf, (w, h))
            x, y = (OUT_W - w) // 2, (OUT_H - h) // 2 - 70
            frame.blit(pygame.transform.smoothscale(shadow, (w + 40, h + 40)), (x - 20, y - 6))
            pygame.draw.rect(frame, ACCENT, (x - 4, y - 4, w + 8, h + 8), border_radius=6)
            frame.blit(img, (x, y))
            yield frame

    # --- timeline --------------------------------------------------------
    def frames(self, timeline, first: int = 0, last: int | None = None):
        """Yield every output frame of the timeline (of its items first to last)."""
        pygame = self.pg
        lengths = item_frames(timeline)
        # Overlays that run on across items sharing them: (key, text) -> frames left
        spans: list[dict] = []
        for k, item in enumerate(timeline):
            span = {}
            for key in ("caption", "kicker", "heading"):
                text = getattr(item, key, "")
                if not text:
                    continue
                total = 0
                for nxt, n in zip(timeline[k:], lengths[k:]):
                    if getattr(nxt, key, "") != text:
                        break
                    total += n
                span[key] = total
            spans.append(span)
        ages: dict = {}
        # Up to the title the picture is letterboxed, the captions sit in the bar
        opening = next((k for k, it in enumerate(timeline) if getattr(it, "kind", "") == "title"), 0)
        for k, item in enumerate(timeline):
            if k < first or (last is not None and k > last):
                continue
            n = lengths[k]
            prev = timeline[k - 1] if k else None
            # An overlay starts over unless the item before shares it
            for key in ("caption", "kicker", "heading", "title"):
                text = getattr(item, key, "")
                if not text or getattr(prev, key, None) != text or k == first:
                    ages[key] = (0, spans[k].get(key, n))
            if isinstance(item, Shot):
                source = self.shot(item, n)
                anims = None
            elif item.kind in ("levels", "store"):
                source = self.ui_card(item, n)
            else:
                source = self.card(item, n)
                g0 = self.stage(0, 0).game
                anims = self.run_anims(g0) if item.kind == "end" else self.idle_anims(g0)
            for i, frame in enumerate(source):
                layer = self.layer()
                if isinstance(item, Shot):
                    if item.callouts:
                        for kind in item.callouts:
                            self.callout(layer, kind, i)
                    if item.tag:
                        self.tag(layer, item.tag, self.entity_top(self.game.player), alpha=min(255, i * 40))
                    for puppet, (_, _, _, tag) in zip(self.puppets[1 if item.ghost else 0 :], item.rivals):
                        if tag:
                            self.tag(layer, tag, self.entity_top(puppet.entity), color=ACCENT, alpha=min(255, i * 40))
                    if item.race:
                        self.race_hud(layer, self.puppets[:1])
                elif item.kind == "title":
                    self.letterbox(layer, 1 - ease_out(i / 20))
                    self.title_layer(layer, i, anims)
                    for a in anims:
                        a.update()
                elif item.kind == "end":
                    self.end_layer(layer, i, anims)
                    for a in anims:
                        a.update()
                if k < opening:
                    self.letterbox(layer, 1.0)
                for key, draw in (("caption", self.caption), ("heading", self.heading)):
                    text = getattr(item, key, "")
                    if text:
                        age, left = ages[key]
                        if key == "caption" and k < opening:
                            self.caption(layer, text, age, left, y=VIEW_H - 17)
                        else:
                            draw(layer, text, age, left)
                        ages[key] = (age + 1, left - 1)
                if getattr(item, "kicker", "") or getattr(item, "title", ""):
                    # The bar stays while the chapter does; a new level's name slides in anew
                    bar_age, left = ages.get("kicker") or ages["title"]
                    title_age, _ = ages.get("title", (bar_age, left))
                    self.lower_third(layer, item.kicker, item.title, bar_age, left, title_age)
                    for key in ("kicker", "title"):
                        if key in ages:
                            ages[key] = (ages[key][0] + 1, ages[key][1] - 1)
                frame.blit(pygame.transform.scale_by(layer, SCALE), (0, 0))
                if k == 0 and i < 40:
                    fade = pygame.Surface((OUT_W, OUT_H), pygame.SRCALPHA)
                    fade.fill((0, 0, 0, round(255 * (1 - i / 40))))
                    frame.blit(fade, (0, 0))
                # A white flash on the title and where a new section starts
                strength = 0
                if getattr(item, "flash", False) or getattr(item, "kind", "") == "title":
                    strength = 210
                elif k > opening and getattr(item, "kicker", "") and getattr(prev, "kicker", "") != item.kicker:
                    strength = 110
                if strength and i < 8:
                    flash = pygame.Surface((OUT_W, OUT_H), pygame.SRCALPHA)
                    flash.fill((255, 255, 255, round(strength * (1 - i / 8))))
                    frame.blit(flash, (0, 0))
                yield frame
                self.frame_no += 1

    def social(self):
        """1280x640 card for the repo's social preview."""
        pygame = self.pg
        gs = self.stage(1, 0, view=SOCIAL_VIEW)
        g = gs.game
        g.transition = 0
        g.players = []
        g.scroll = [200 - SOCIAL_VIEW[0] / 2, 60 - SOCIAL_VIEW[1] / 2]
        for _ in range(60):
            g.step()
        out = pygame.Surface((SOCIAL_VIEW[0] * 2, SOCIAL_VIEW[1] * 2))
        self.renderer.render(g, out)
        layer = pygame.Surface(SOCIAL_VIEW, pygame.SRCALPHA)
        layer.fill((*INK, 130))
        cx = SOCIAL_VIEW[0] / 2
        self.text(layer, "NINJA GAME", 32, (cx, 118))
        self.text(layer, "A FAST PIXEL-ART PLATFORMER IN PURE PYTHON", 8, (cx, 160), shadow=None)
        self.text(layer, "GHOST REPLAYS - MULTIPLAYER - LEVEL EDITOR - RL ENV", 8, (cx, 178), shadow=None)
        anims = self.idle_anims(g)
        for k, anim in enumerate(anims):
            img = pygame.transform.scale_by(anim.img(), 2)
            x = cx + (k - (len(anims) - 1) / 2) * 34 - img.get_width() / 2
            layer.blit(img, (round(x), 214))
        out.blit(pygame.transform.scale_by(layer, 2), (0, 0))
        return out

    def level_grid(self):
        """The README's level matrix, LEVEL_GRID's rows on a dark ground."""
        pygame = self.pg
        w, h = GRID_VIEW[0] * GRID_SCALE, GRID_VIEW[1] * GRID_SCALE
        rows, cols = len(LEVEL_GRID), len(LEVEL_GRID[0])
        grid = pygame.Surface((cols * (w + GRID_GAP) - GRID_GAP, rows * (h + GRID_GAP) - GRID_GAP))
        grid.fill(INK)
        cell = pygame.Surface((w, h))
        for r, row in enumerate(LEVEL_GRID):
            for c, shot in enumerate(row):
                shot = Shot(**{**shot.__dict__, "view": GRID_VIEW})
                for frame in self.shot(shot, 1, cell):
                    grid.blit(frame, (c * (w + GRID_GAP), r * (h + GRID_GAP)))
        return grid


# --- audio ---------------------------------------------------------------
RATE = 44100
MUSIC_GAIN = 0.9
SFX_GAIN = {"jump": 0.35, "dash": 0.2, "hit": 0.5, "shoot": 0.3, "collect": 0.15}


def read_wav(path):
    """A 16-bit WAV as float stereo samples, shape (n, 2)."""
    import numpy as np

    with wave.open(path) as w:
        assert w.getframerate() == RATE and w.getsampwidth() == 2, path
        channels = w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    samples = samples.reshape(-1, channels)
    return np.repeat(samples, 2, axis=1) if channels == 1 else samples


def arrange_music(n: int):
    """The track's bars in MUSIC's order, joined with short crossfades, n samples long."""
    import numpy as np

    track = read_wav(os.path.join(ROOT, "data", "music", "music_0.wav"))
    bar = 4 * BEAT * RATE
    xf = int(0.012 * RATE)
    out = np.zeros((n, 2))
    pos = 0
    for k, (first, bars) in enumerate(MUSIC):
        a = 0 if k == 0 else int(round(PHASE * RATE + first * bar))
        b = int(round(PHASE * RATE + (first + bars) * bar)) if k < len(MUSIC) - 1 else len(track)
        piece = track[a : b + xf].copy()
        if k:  # fade in over the previous piece's tail
            ramp = np.linspace(0, 1, xf)[:, None]
            piece[:xf] *= ramp
            out[pos : pos + xf] *= 1 - ramp[: max(0, min(xf, n - pos))]
        end = min(n, pos + len(piece))
        out[pos:end] += piece[: end - pos]
        pos += b - a
        if pos >= n:
            break
    return out


def synth(kind: str):
    """Trailer sound design: an impact for the title and the end, a whoosh for sections."""
    import numpy as np

    rng = np.random.default_rng(7)
    if kind == "boom":
        t = np.arange(int(1.6 * RATE)) / RATE
        freq = 38 + 70 * np.exp(-t * 18)
        body = np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 3.2)
        click = rng.normal(0, 1, len(t)) * np.exp(-t * 60) * 0.35
        x = (body + click) * 0.9
    elif kind == "whoosh":
        n = int(0.55 * RATE)
        t = np.arange(n) / RATE
        noise = rng.normal(0, 1, n)
        # a band sweeping up: noise through a moving one-pole low-pass
        cut = 0.02 + 0.25 * (t / t[-1]) ** 2
        y, acc = np.zeros(n), 0.0
        for i in range(n):
            acc += cut[i] * (noise[i] - acc)
            y[i] = acc
        env = np.sin(np.pi * np.clip(t / t[-1], 0, 1)) ** 2
        x = y * env * 1.6
    elif kind == "riser":
        n = int(1.5 * RATE)
        t = np.arange(n) / RATE
        x = rng.normal(0, 1, n) * (t / t[-1]) ** 3 * 0.25
        x += np.sin(2 * np.pi * (200 * t + 300 * t**2)) * (t / t[-1]) ** 2 * 0.15
    else:
        raise ValueError(kind)
    x = x / (np.abs(x).max() or 1) * 32767 * 0.8
    return np.stack([x, x], axis=1)


SYNTH_GAIN = {"boom": 0.9, "whoosh": 0.35, "riser": 0.4}


def mix(cues, total_frames, path) -> None:
    """Music, the cued sound effects and the trailer's own, as a 16-bit stereo WAV."""
    import numpy as np

    n = int(total_frames / FPS * RATE)
    out = arrange_music(n) * MUSIC_GAIN
    sfx = {name: read_wav(os.path.join(ROOT, "data", "sfx", f"{name}.wav")) for name in SFX_GAIN}
    made = {}
    for frame, name in cues:
        if name in sfx:
            clip, gain = sfx[name], SFX_GAIN[name]
        elif name in SYNTH_GAIN:
            clip, gain = made.setdefault(name, synth(name)), SYNTH_GAIN[name]
        else:
            continue
        start = int(frame / FPS * RATE)
        if name == "riser":  # ends on the cue
            start -= len(clip)
        a = max(0, start)
        end = min(n, start + len(clip))
        if end > a:
            out[a:end] += clip[a - start : end - start] * gain
    fade_out = int(3.0 * RATE)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    out *= min(1.0, 0.89 * 32767 / (np.abs(out).max() or 1))  # peak at -1 dBFS at most
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(np.round(out).astype(np.int16).tobytes())


def sound_design(timeline) -> list[tuple[int, str]]:
    """The trailer's own cues: a riser into and an impact on the title, a whoosh
    where a new section (lower third's kicker, a menu) starts, an impact on the end card."""
    cues = []
    at, prev = 0, None
    for item, n in zip(timeline, item_frames(timeline)):
        kind = getattr(item, "kind", "")
        section = getattr(item, "kicker", "") or kind
        if kind == "title":
            cues += [(at, "riser"), (at, "boom")]
        elif kind == "end":
            cues.append((at, "boom"))
        elif section and section != prev:
            cues.append((at, "whoosh"))
        prev = section
        at += n
    return cues


# --- main ----------------------------------------------------------------
def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def parse_range(text: str | None, n: int) -> range:
    if not text:
        return range(n)
    a, _, b = text.partition("-")
    return range(int(a), int(b or a) + 1)


def render_segment(studio, items: range, out: str) -> None:
    """Items `items` of the timeline as a lossless video, their sound cues beside it."""
    pygame = studio.pg
    raw = f"-f rawvideo -pix_fmt rgb24 -s {OUT_W}x{OUT_H} -r {FPS} -i -".split()
    lossless = "-c:v libx264rgb -qp 0 -preset ultrafast".split()
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", *raw, *lossless, out], stdin=subprocess.PIPE)
    assert enc.stdin
    for frame in studio.frames(TIMELINE, first=items.start, last=items.stop - 1):
        enc.stdin.write(pygame.image.tobytes(frame, "RGB"))
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg failed to encode a segment")
    with open(out + ".json", "w") as f:
        json.dump({"frames": studio.frame_no, "cues": studio.cues}, f)


def render_master(master: str, tmp: str, jobs: int) -> tuple[int, list]:
    """Render the timeline in `jobs` processes at once and join the pieces."""
    lengths = item_frames(TIMELINE)
    total = sum(lengths)
    # Contiguous runs of items, about the same number of frames each
    bounds, acc, start = [], 0, 0
    for k, n in enumerate(lengths):
        acc += n
        if acc >= total * (len(bounds) + 1) / jobs and k + 1 < len(lengths):
            bounds.append((start, k))
            start = k + 1
    bounds.append((start, len(lengths) - 1))
    procs = []
    for a, b in bounds:
        out = os.path.join(tmp, f"seg-{a:03}.mkv")
        cmd = [sys.executable, os.path.abspath(__file__), "--segment", f"{a}-{b}", "--seg-out", out]
        procs.append((a, b, out, subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
    cues, listing = [], os.path.join(tmp, "segments.txt")
    with open(listing, "w") as f:
        for a, b, out, proc in procs:
            if proc.wait():
                raise SystemExit(f"segment from item {a} failed")
            offset = sum(lengths[:a])
            with open(out + ".json") as g:
                meta = json.load(g)
            if meta["frames"] != sum(lengths[a : b + 1]):
                raise SystemExit(f"segment from item {a} has {meta['frames']} frames")
            cues += [(offset + frame, name) for frame, name in meta["cues"]]
            f.write(f"file '{out}'\n")
    ffmpeg("-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", master)
    return total, cues


def render(args) -> None:
    studio = Studio()
    pygame = studio.pg
    os.makedirs(OUT_DIR, exist_ok=True)
    w, h = OUT_W, OUT_H

    levels = os.path.join(OUT_DIR, "levels.png")
    if args.levels:
        pygame.image.save(studio.level_grid(), levels)
        print(levels)
        return

    if args.sheet is not None:
        picks_of = parse_range(args.sheet, len(TIMELINE))
        lengths = item_frames(TIMELINE)
        thumbs = []
        for k in picks_of:
            n = lengths[k]
            picks = {0, n // 2, n - 1}
            for i, frame in enumerate(studio.frames(TIMELINE, first=k, last=k)):
                if i in picks:
                    thumbs.append(pygame.transform.smoothscale(frame, (w // 4, h // 4)))
        rows = (len(thumbs) + 2) // 3
        sheet = pygame.Surface((w // 4 * 3, h // 4 * rows))
        for k, t in enumerate(thumbs):
            sheet.blit(t, (k % 3 * w // 4, k // 3 * h // 4))
        path = args.out or os.path.join(tempfile.gettempdir(), "trailer-sheet.png")
        pygame.image.save(sheet, path)
        print(path)
        return

    if args.segment:
        render_segment(studio, parse_range(args.segment, len(TIMELINE)), args.seg_out)
        return

    tmp = tempfile.mkdtemp(prefix="ninja-trailer-")
    try:
        master = os.path.join(tmp, "master.mkv")
        total, cues = render_master(master, tmp, args.jobs)
        print(f"{total} frames ({total / FPS:.1f}s), {len(cues)} sound cues")

        audio = os.path.join(tmp, "audio.wav")
        mix(cues + sound_design(TIMELINE), total, audio)
        mp4 = args.out or os.path.join(OUT_DIR, "trailer.mp4")
        video = "-c:v libx264 -preset veryslow -crf 18 -tune animation -pix_fmt yuv420p".split()
        sound = "-af loudnorm=I=-14:TP=-1.0 -c:a aac -ar 48000 -b:a 256k".split()
        ffmpeg("-i", master, "-i", audio, *video, *sound, "-movflags", "+faststart", "-shortest", mp4)
        print(mp4)
        if args.out:
            return

        if not args.no_gif:
            gif = os.path.join(OUT_DIR, "trailer.gif")
            # Pixel art has few colours: one palette for the whole clip, no dithering
            palette = "split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none"
            ffmpeg("-i", master, "-filter_complex", f"fps={GIF_FPS},scale={GIF_W}:-1:flags=neighbor,{palette}", gif)
            print(gif)

        social = os.path.join(OUT_DIR, "social-preview.png")
        pygame.image.save(studio.social(), social)
        print(social)

        pygame.image.save(studio.level_grid(), levels)
        print(levels)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", nargs="?", const="", default=None, help="only render a contact sheet (of items A-B)")
    parser.add_argument("--levels", action="store_true", help="only render the README's level matrix")
    parser.add_argument("--no-gif", action="store_true", help="skip the README GIF")
    parser.add_argument("--out", help="write the sheet / only the MP4 here instead")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="render processes")
    parser.add_argument("--segment", help=argparse.SUPPRESS)
    parser.add_argument("--seg-out", help=argparse.SUPPRESS)
    render(parser.parse_args())


SKY, CAVES, WORLD, SEA, KINGS, MARS, DEEP = (
    "CHAPTER 1 - SKY ISLANDS",
    "CHAPTER 2 - UNDERGROUND",
    "CHAPTER 3 - JOURNEY ACROSS THE WORLD",
    "CHAPTER 4 - THE SEA",
    "CHAPTER 5 - THE DESERT OF KINGS",
    "CHAPTER 6 - ANCIENT MARS",
    "CHAPTER 7 - THE DEEP SEA",
)
MOVES, ENEMIES, TRAPS, HELP = "MOVES", "6 ENEMY KINDS", "TRAPS", "HELP ON THE WAY"
SKINS, WEAPONS, GEAR = "8 SKINS", "5 WEAPONS", "4 GEAR ITEMS"
ONLINE = "PLAY ONLINE WITH FRIENDS"


def kill(level, run, at, beats=2, before=30, view=CLOSE, **kw) -> Shot:
    """A shot whose kill (frame `at` of the run) lands `before` frames in."""
    return Shot(level, at - before, beats, run, view=view, **kw)


# The cut, beat by beat (a beat is 22.5 frames; the comments count bars of 4 beats).
TIMELINE: list[Item] = [
    # Bars 0-4, the intro of the track: the journey in wide shots, letterboxed
    Shot(0, 40, 8, "evening", view=WIDE, caption="FROM THE SKY ISLANDS"),
    Shot(26, 3990, 2, "plan", view=WIDE, caption="ACROSS DESERTS AND MARS"),
    Shot(33, 720, 2, "plan", view=WIDE, caption="ACROSS DESERTS AND MARS"),
    Shot(38, 3960, 2, "plan", view=WIDE, caption="TO THE BOTTOM OF THE SEA"),
    Shot(40, 5040, 2, "plan", view=WIDE, caption="TO THE BOTTOM OF THE SEA"),
    kill(11, "plan", 866, 4, before=60, view=MID),
    # Bar 5: the groove starts
    Card("title", 8, bg=Shot(11, 700, 0, "plan", view=WIDE)),
    # Bars 7-13: skill montage, real runs
    kill(13, "plan", 1632),
    kill(16, "plan", 1444, seed=3),
    kill(20, "best", 93),
    kill(7, "dev", 3411),
    Shot(27, 4235, 2, "plan", view=CLOSE),
    kill(19, "dev", 4722),
    kill(3, "devlast", 547),
    kill(8, "dev", 3027),
    Shot(4, 3775, 2, "evening", view=CLOSE),
    kill(9, "dev", 3710),
    kill(17, "plan", 2118),
    kill(15, "plan", 1669, seed=1),
    kill(23, "plan", 2042),
    Shot(26, 5110, 2, "plan", view=CLOSE),
    # Bars 14-17: the moves
    Shot(2, 60, 4, "evening", view=CLOSE, kicker=MOVES, title="DOUBLE JUMP"),
    Shot(13, 440, 4, "plan", view=CLOSE, kicker=MOVES, title="WALL-JUMP"),
    kill(11, "plan", 866, 4, before=60, kicker=MOVES, title="DASH THROUGH ENEMIES"),
    kill(14, "dev", 6226, 4, before=55, kicker=MOVES, title="STOMP ON THEM"),
    # Bars 18-21: the enemies, each named on screen
    kill(4, "dev", 422, 2, before=35, view=MID, kicker=ENEMIES, title="GUNNER", callouts=("gunner",)),
    kill(7, "dev", 4580, 2, before=35, view=MID, kicker=ENEMIES, title="PATROL", callouts=("patrol",)),
    kill(8, "dev", 5568, 3, before=50, view=MID, kicker=ENEMIES, title="TURRET", callouts=("turret",)),
    kill(19, "dev", 235, 3, before=50, view=MID, kicker=ENEMIES, title="CHASER", callouts=("chaser",)),
    kill(6, "dev", 2341, 3, before=50, view=MID, kicker=ENEMIES, title="JUMPER", callouts=("jumper",)),
    kill(20, "dev", 491, 3, before=50, view=MID, kicker=ENEMIES, title="THROWER", callouts=("thrower",)),
    # Bars 22-24: traps and help
    Shot(12, 2370, 2, "plan", view=CLOSE, kicker=TRAPS, title="SPIKES"),
    Shot(11, 2572, 2, "dev", view=CLOSE, kicker=TRAPS, title="FLAME JETS"),
    Shot(3, 2420, 2, "evening", view=CLOSE, kicker=TRAPS, title="CRUMBLING BLOCKS"),
    Shot(28, 1765, 3, "plan", view=CLOSE, kicker=HELP, title="CHECKPOINTS"),
    Shot(11, 1485, 3, "plan", view=CLOSE, kicker=HELP, title="HEARTS"),
    # Bars 25-32: the seven chapters, then the water
    Shot(4, 3720, 2, "evening", kicker=SKY, title="SKY COURSE"),
    Shot(7, 4500, 2, "dev", kicker=SKY, title="THE ARCH"),
    Shot(9, 7410, 2, "dev", kicker=CAVES, title="ROOT CAVES"),
    Shot(10, 1230, 2, "dev", kicker=CAVES, title="DEEP LABYRINTH"),
    Shot(17, 990, 2, "dev", kicker=WORLD, title="SKY FORTRESS"),
    Shot(20, 420, 2, "dev", kicker=WORLD, title="OLYMPUS MONS"),
    Shot(22, 90, 2, "plan", kicker=SEA, title="KELP CURRENTS"),
    Shot(23, 930, 2, "plan", seed=1, kicker=SEA, title="SUNKEN GALLEON"),
    Shot(26, 3990, 2, "plan", kicker=KINGS, title="THE BURIED CITY"),
    Shot(30, 3090, 2, "dev", kicker=KINGS, title="THE COLOSSUS"),
    Shot(33, 720, 2, "plan", kicker=MARS, title="THE MONOLITH FIELD"),
    Shot(35, 2010, 2, "dev", kicker=MARS, title="THE BEACON"),
    Shot(38, 3960, 2, "plan", kicker=DEEP, title="KELP FOREST"),
    Shot(40, 5040, 2, "plan", kicker=DEEP, title="THE LEVIATHAN'S BONES"),
    Shot(21, 1800, 2, "plan", caption="DIVE IN. HOLD YOUR BREATH."),
    Shot(25, 2010, 2, "plan", caption="DIVE IN. HOLD YOUR BREATH."),
    # Bars 33-34: every level in the menu
    Card("levels", 8, bg=Shot(16, 1380, 0, "plan", view=WIDE), caption="41 LEVELS IN 7 WORLDS"),
    # Bars 35-37: last night's run against the best run
    Shot(4, 1290, 12, "evening", ghost="dev", race=True, caption="RACE YOUR BEST RUN"),
    # Bars 38-41: the skins
    Shot(3, 1500, 2, "evening", view=CLOSE, skin=0, kicker=SKINS, title="NINJA"),
    Shot(5, 3090, 2, "evening", view=CLOSE, skin=1, kicker=SKINS, title="HOMURA - FLAME NINJA"),
    Shot(6, 2280, 2, "dev", view=CLOSE, skin=2, kicker=SKINS, title="SHOGUN - GOLDEN SAMURAI"),
    Shot(16, 1380, 2, "plan", view=CLOSE, skin=3, kicker=SKINS, title="CHROME - CYBER NINJA"),
    Shot(12, 150, 2, "plan", view=CLOSE, skin=4, kicker=SKINS, title="CRYSTAL - DIAMOND NINJA"),
    Shot(18, 270, 2, "plan", view=CLOSE, skin=5, kicker=SKINS, title="SHADOW - ASSASSIN"),
    Shot(27, 4290, 2, "plan", view=CLOSE, skin=6, kicker=SKINS, title="ONI - DEMON"),
    Shot(29, 2400, 2, "plan", view=CLOSE, skin=7, kicker=SKINS, title="KITSUNE - FOX SPIRIT"),
    # Bars 42-46: the store, weapons and gear
    Card("store", 4, bg=Shot(6, 2280, 0, "dev", view=WIDE), caption="UNLOCK THEM IN THE STORE"),
    Shot(12, 269, 2, "dev", view=CLOSE, weapon="Gun", fire=(14,), kicker=WEAPONS, title="GUN"),
    Shot(20, 171, 2, "dev", view=CLOSE, weapon="Rifle", fire=(12,), kicker=WEAPONS, title="RIFLE"),
    Shot(1, 361, 2, "evening", view=CLOSE, weapon="Ninja Stars", fire=(8, 26), kicker=WEAPONS, title="NINJA STARS"),
    Shot(13, 1165, 2, "dev", view=CLOSE, weapon="Sword", fire=(24,), kicker=WEAPONS, title="SWORD"),
    Shot(
        7,
        4670,
        2,
        "dev",
        view=CLOSE,
        weapon="Grapple Hook",
        fire=(12,),
        sync_until=12,
        kicker=WEAPONS,
        title="GRAPPLE HOOK",
    ),
    Shot(12, 3415, 2, "dev", view=CLOSE, gear="Shield", sync_until=40, kicker=GEAR, title="SHIELD"),
    Shot(
        1,
        140,
        2,
        "evening",
        view=CLOSE,
        gear="Moon Boots",
        press=((35, "jump"),),
        sync_until=35,
        kicker=GEAR,
        title="MOON BOOTS",
    ),
    Shot(8, 9270, 2, "dev", view=CLOSE, gear="Coin Magnet", kicker=GEAR, title="COIN MAGNET"),
    Shot(2, 42, 2, "evening", view=CLOSE, gear="Lucky Charm", kicker=GEAR, title="LUCKY CHARM"),
    # Bars 47-51: multiplayer, on the levels of last night's session
    Shot(3, 1230, 8, "dev", skin=7, rivals=(("evening", 6, 210, "P2"),), tag="P1", caption=ONLINE),
    Shot(5, 945, 6, "best", skin=7, rivals=(("evening", 6, 585, "P2"),), tag="P1", caption=ONLINE),
    Shot(
        4,
        1590,
        6,
        "devlast",
        skin=7,
        rivals=(("evening", 6, 60, "P2"),),
        tag="P1",
        caption="HOST. SHARE THE CODE. PLAY.",
    ),
    # Bars 52-55: the climax, a kill on every beat
    kill(20, "best", 2710, 1, before=14),
    kill(8, "dev", 3183, 1, before=14),
    kill(14, "best", 2814, 1, before=14),
    kill(9, "dev", 5393, 1, before=14),
    kill(10, "dev", 6463, 1, before=14),
    kill(12, "plan", 443, 1, before=14),
    kill(9, "dev", 7151, 1, before=14),
    kill(35, "dev", 431, 1, before=14),
    kill(13, "plan", 1632, 1, before=14),
    kill(19, "plan", 3310, 1, before=14, seed=2),
    kill(16, "plan", 1444, 1, before=14, seed=3),
    kill(11, "plan", 866, 1, before=14),
    kill(20, "plan", 94, 1, before=14),
    kill(7, "dev", 4580, 1, before=14),
    # Bar 56: the track's last hit
    Card("end", 16, bg=Shot(0, 40, 0, "evening", view=WIDE)),
]

if __name__ == "__main__":
    main()
