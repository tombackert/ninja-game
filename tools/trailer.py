#!/usr/bin/env python3
"""Render the game trailer: an MP4 with sound and a GIF for the README.

Usage (from the repo root):
    python tools/trailer.py              # docs/media/trailer.mp4, trailer.gif, social-preview.png
    python tools/trailer.py --sheet      # three stills per shot in one image, a quick check
    python tools/trailer.py --no-gif

Needs ffmpeg on PATH. Nothing in data/ is written: settings changes stay
in memory and the runs are never recorded or saved.

Every gameplay shot is a real best run from tools/trailer_replays/ (copies
of data/replays/), re-simulated headless through GameState.update() like
live play. The camera frames 480x270 instead of the game's 640x360, a bit
closer on the action, scaled 4x to 1920x1080 with the renderer's sub-pixel
glide. Captions use the game's pixel font on the same pixel grid.

Replays store the input router's actions, not what KeyboardManager did:
Space is recorded as "jump" but dashes, and mouse dashes are not recorded
at all. `Run` recovers the real inputs from the snapshots stored every 10
ticks, so the runs replay exactly as they were played.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPLAYS = os.path.join(ROOT, "tools", "trailer_replays")
OUT_DIR = os.path.join(ROOT, "docs", "media")

VIEW_W, VIEW_H = 480, 270  # world framing in game pixels
SCALE = 4  # -> 1920x1080
FPS = 60
GIF_W, GIF_FPS = 960, 20  # 20 = every third 60 Hz frame, even cadence
SOCIAL_VIEW = (640, 320)  # GitHub social preview, scaled 2x to 1280x640

INK = (22, 24, 48)  # outline / shadow colour of all trailer text
ACCENT = (232, 110, 60)  # the menus' highlight orange


@dataclass
class Shot:
    """`frames` frames of a level's replay, from replay tick `start` on."""

    level: int
    start: int
    frames: int
    caption: str = ""
    run: str = "best"  # replay that drives the player: "best" or "last"
    ghost: str | None = None  # replay raced as the ghost
    rival: str | None = None  # replay of a second ninja (the multiplayer shot)
    skin: int = 0
    skins: tuple[int, ...] = ()  # cycle through these skins
    weapon: str = "Default"
    seed: int = 0  # gameplay RNG, i.e. what the enemies do


@dataclass
class Card:
    kind: str  # "title" or "end"
    frames: int


# The cut. Ticks are 60 Hz frames into each replay.
TIMELINE: list[Shot | Card] = [
    Shot(level=0, start=0, frames=150),
    Card("title", 120),
    Shot(level=1, start=150, frames=100, caption="DASH THROUGH ENEMIES"),
    Shot(level=5, start=3830, frames=90, caption="DASH THROUGH ENEMIES"),
    Shot(level=4, start=2330, frames=140, caption="WALL-SLIDE. WALL-JUMP."),
    Shot(level=2, start=30, frames=180, caption="RACE YOUR BEST RUN", run="last", ghost="best"),
    Shot(level=3, start=400, frames=120, caption="6 SKINS TO UNLOCK", skins=(1, 2, 3, 4, 5, 6)),
    Shot(level=21, start=32, frames=115, caption="PLAY WITH FRIENDS", rival="last", skin=2, weapon="Gun"),
    Shot(level=4, start=1570, frames=45, caption="12 HAND-BUILT LEVELS"),
    Shot(level=6, start=825, frames=45, caption="12 HAND-BUILT LEVELS"),
    Shot(level=5, start=2070, frames=45, caption="12 HAND-BUILT LEVELS"),
    Shot(level=3, start=500, frames=45, caption="12 HAND-BUILT LEVELS"),
    Card("end", 200),
]


def boot():
    """Start pygame headless in the repo root (assets load relative to it)."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["NINJA_GAME_TESTING"] = "1"
    os.chdir(ROOT)
    import pygame

    pygame.init()
    pygame.display.set_mode((VIEW_W * SCALE, VIEW_H * SCALE))

    from scripts.settings import settings

    settings.flush = lambda: None  # keep data/settings.json untouched
    settings.camera_style = "classic"
    settings.selected_gear = 0
    return pygame


class Run:
    """A replay's inputs, rebuilt into what the player actually did."""

    def __init__(self, level: int, kind: str = "best"):
        with open(os.path.join(REPLAYS, f"{level}-{kind}.json")) as f:
            self.data = json.load(f)
        self.snaps = {int(t): s["players"][0] for t, s in self.data["snapshots"].items() if s.get("players")}
        self.events = self._events(self.data["inputs"])
        self.held = self._held(self.data["inputs"])

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
        """Put the player in the state the recording starts with."""
        s = self.snaps[0]
        player.pos = list(s["pos"])
        player.velocity = list(s["velocity"])
        for name in ("air_time", "jumps", "wall_slide", "dashing", "flip"):
            setattr(player, name, s[name])

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
    """Stands in for the ReplayManager: draws ghost and rival, never records or saves."""

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

    puppet = (Rival if rival else ReplayGhost)(game, ReplayData.from_json(run.data))
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


class Studio:
    """Boots the game headless and turns the timeline into frames and sound cues."""

    def __init__(self):
        self.pg = pygame = boot()
        from scripts.audio_service import AudioService
        from scripts.renderer import Renderer

        self.renderer = Renderer(show_perf=False)
        self.renderer._render_hud = lambda *args, **kwargs: None  # clean frames, no HUD
        self.out = pygame.Surface((VIEW_W * SCALE, VIEW_H * SCALE))
        self.font = {size: pygame.font.Font(os.path.join(ROOT, "data", "font.ttf"), size) for size in (8, 16, 32)}
        self.frame_no = 0  # output frames so far
        self.cues: list[tuple[int, str]] = []  # (output frame, sound)
        self.listening = False
        audio = AudioService.get()
        audio.play = self._cue
        audio.play_music = lambda *args, **kwargs: None

    def _cue(self, name, loops=0):
        if self.listening and not loops:
            self.cues.append((self.frame_no, name))

    # --- world -----------------------------------------------------------
    def stage(self, level: int, seed: int, weapon: str = "Default", view=(VIEW_W, VIEW_H)):
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
        settings.ghost_enabled = False
        gs = GameState()
        g = gs.game
        g.players = [g.player]  # one ninja; levels with a second spawn would show it idle
        g.replay = Extras()
        g.cm.gun = max(g.cm.gun, 1)  # the multiplayer shot shows everyone with a gun
        g.BASE_W, g.BASE_H = view
        g.display = pygame.Surface((view[0] + 1, view[1] + 1), pygame.SRCALPHA)
        g.display_2 = pygame.Surface((view[0] + 1, view[1] + 1), pygame.SRCALPHA)
        return gs

    def frame_camera(self, g) -> None:
        g.scroll = [g.player.rect().centerx - g.BASE_W / 2, g.player.rect().centery - g.BASE_H / 2]

    def shot(self, shot: Shot):
        """Yield the frames of a gameplay shot."""
        from scripts.constants import TRANSITION_MAX

        gs = self.stage(shot.level, shot.seed, shot.weapon)
        g = gs.game
        run = Run(shot.level, shot.run)
        run.place(g.player)
        g.movement = list(run.held)
        set_skin(g.player, shot.skins[0] if shot.skins else shot.skin)
        g.replay = Extras(
            shot.ghost and make_puppet(g, Run(shot.level, shot.ghost), rival=False, skin=0),
            shot.rival and make_puppet(g, Run(shot.level, shot.rival), rival=True, skin=0),
        )
        self.frame_camera(g)
        scratch = self.pg.Surface((g.BASE_W + 1, g.BASE_H + 1), self.pg.SRCALPHA)

        tick = 0
        for i in range(shot.start + shot.frames):
            live = i >= shot.start
            if not g.dead:
                run.feed(tick, g.player, g.movement, g.audio)
                tick += 1
            if live and shot.skins and i > shot.start and (i - shot.start) % 20 == 0:
                set_skin(g.player, shot.skins[(i - shot.start) // 20 % len(shot.skins)])
                self.puff(g, g.player.rect().center)
            self.listening = live
            gs.update(1 / FPS)
            if g.endpoint and g.transition >= TRANSITION_MAX:
                raise SystemExit(f"shot on level {shot.level} runs past the level end")
            if live:
                self.renderer.render(g, self.out)
                yield self.out
            else:
                g.replay.render_ghost(scratch, (0, 0))  # keep ghost / rival in step
            if not live and i == shot.start - 1:
                self.frame_camera(g)  # cut in with a settled camera
        self.listening = False

    def puff(self, g, pos) -> None:
        from scripts.particle import Particle

        for _ in range(16):
            angle = random.random() * math.pi * 2
            speed = random.random() * 0.6 + 0.4
            vel = [math.cos(angle) * speed, math.sin(angle) * speed]
            g.particles.append(Particle(g, "particle", pos, velocity=vel, frame=random.randint(0, 7)))

    # --- cards -----------------------------------------------------------
    def card(self, card: Card):
        """Yield the frames of a title or end card over a dimmed level."""
        pygame = self.pg
        gs = self.stage(0, 0)
        g = gs.game
        g.transition = 0
        g.players = []  # off stage: the card has its own ninjas
        g.scroll = [260 - VIEW_W / 2, 150 - VIEW_H / 2]
        dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        dim.fill((*INK, 150))
        anims = self.idle_anims(g)
        for i in range(card.frames):
            g.step()
            self.renderer.render(g, self.out)
            layer = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
            layer.blit(dim, (0, 0))
            if card.kind == "title":
                self.title_layer(layer, i, anims)
            else:
                self.end_layer(layer, i, anims)
            for a in anims:
                a.update()
            self.out.blit(pygame.transform.scale_by(layer, SCALE), (0, 0))
            yield self.out

    def idle_anims(self, g):
        from scripts.collectableManager import CollectableManager

        return [g.assets[f"player/{p}/idle"].copy() for p in CollectableManager.SKIN_PATHS]

    def text(self, layer, text, size, center, color=(255, 255, 255), shadow=ACCENT, alpha=255):
        """Pixel text with a 1px outline and a drop shadow, centred on `center`."""
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
        layer.blit(surf, (round(center[0] - surf.get_width() / 2), round(center[1] - surf.get_height() / 2)))

    def title_layer(self, layer, i, anims):
        drop = max(0.0, 1 - i / 14)
        y = 112 - round(60 * drop * drop) + (2 if 14 <= i < 18 else 0)
        self.text(layer, "NINJA GAME", 32, (VIEW_W / 2, y))
        if i >= 22:
            alpha = min(255, (i - 22) * 32)
            self.text(layer, "A FAST PIXEL-ART PLATFORMER", 8, (VIEW_W / 2, 152), shadow=None, alpha=alpha)
            self.text(layer, "WRITTEN IN PURE PYTHON", 8, (VIEW_W / 2, 166), shadow=None, alpha=alpha)
        img = anims[0].img()
        big = self.pg.transform.scale_by(img, 3)
        if i >= 8:
            layer.blit(big, (VIEW_W / 2 - big.get_width() / 2, 196))

    def end_layer(self, layer, i, anims):
        self.text(layer, "NINJA GAME", 32, (VIEW_W / 2, 64))
        n = len(anims)
        for k, anim in enumerate(anims):
            if i < 10 + k * 5:
                continue
            img = self.pg.transform.scale_by(anim.img(), 2)
            x = VIEW_W / 2 + (k - (n - 1) / 2) * 34 - img.get_width() / 2
            layer.blit(img, (round(x), 104))
        if i >= 50:
            alpha = min(255, (i - 50) * 32)
            self.text(layer, "FREE & OPEN SOURCE", 8, (VIEW_W / 2, 170), shadow=None, alpha=alpha)
            self.text(layer, "github.com/tombackert/ninja-game", 8, (VIEW_W / 2, 190), shadow=None, alpha=alpha)
        if i >= 80:
            alpha = min(255, (i - 80) * 32)
            self.text(layer, "PLAY IT. MOD IT. STAR IT.", 8, (VIEW_W / 2, 226), color=ACCENT, shadow=None, alpha=alpha)

    def caption(self, text, age, left):
        """Caption layer: slides up when it appears, fades before it leaves."""
        pygame = self.pg
        layer = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        rise = max(0, 6 - age)
        alpha = min(255, age * 40, left * 40)
        self.text(layer, text, 16, (VIEW_W / 2, VIEW_H - 34 + rise), alpha=alpha)
        return pygame.transform.scale_by(layer, SCALE)

    # --- timeline --------------------------------------------------------
    def frames(self, timeline):
        """Yield every output frame of the trailer."""
        caption, age = None, 0
        for k, item in enumerate(timeline):
            frames = self.shot(item) if isinstance(item, Shot) else self.card(item)
            text = getattr(item, "caption", "")
            # A caption runs on across shots that share it (montages)
            span = 0
            for nxt in timeline[k:]:
                if getattr(nxt, "caption", "") != text or not text:
                    break
                span += nxt.frames
            if text != caption:
                caption, age = text, 0
                left = span
            for frame in frames:
                if caption:
                    frame.blit(self.caption(caption, age, left), (0, 0))
                    age += 1
                    left -= 1
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


# --- audio ---------------------------------------------------------------
RATE = 44100
MUSIC_GAIN = 0.8
SFX_GAIN = {"jump": 0.5, "dash": 0.25, "hit": 0.7, "shoot": 0.35, "collect": 0.3}


def read_wav(path) -> array:
    """A 16-bit WAV as interleaved stereo samples."""
    with wave.open(path) as w:
        assert w.getframerate() == RATE and w.getsampwidth() == 2, path
        channels = w.getnchannels()
        samples = array("h", w.readframes(w.getnframes()))
    if channels == 1:
        stereo = array("h", bytes(len(samples) * 4))
        stereo[0::2] = samples
        stereo[1::2] = samples
        return stereo
    return samples


def mix(cues, total_frames, path) -> None:
    """Music bed plus the cued sound effects, written as a 16-bit stereo WAV."""
    n = int(total_frames / FPS * RATE) * 2
    music = read_wav(os.path.join(ROOT, "data", "music", "music_0.wav"))
    out = [s * MUSIC_GAIN for s in music[:n]]
    out += [0.0] * (n - len(out))
    sfx = {name: read_wav(os.path.join(ROOT, "data", "sfx", f"{name}.wav")) for name in SFX_GAIN}
    for frame, name in cues:
        if name not in sfx:
            continue
        start = int(frame / FPS * RATE) * 2
        gain = SFX_GAIN[name]
        for k, s in enumerate(sfx[name][: n - start]):
            out[start + k] += s * gain
    fade_in, fade_out = int(0.05 * RATE) * 2, int(1.5 * RATE) * 2
    for k in range(fade_in):
        out[k] *= k / fade_in
    for k in range(fade_out):
        out[n - fade_out + k] *= 1 - k / fade_out
    gain = min(1.0, 0.89 * 32767 / (max(map(abs, out)) or 1))  # peak at -1 dBFS at most
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(array("h", (round(s * gain) for s in out)).tobytes())


# --- main ----------------------------------------------------------------
def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def render(args) -> None:
    studio = Studio()
    pygame = studio.pg
    os.makedirs(OUT_DIR, exist_ok=True)
    w, h = VIEW_W * SCALE, VIEW_H * SCALE

    if args.sheet:
        thumbs = []
        for item in TIMELINE:
            picks = {0, item.frames // 2, item.frames - 1}
            for k, frame in enumerate(studio.frames([item])):
                if k in picks:
                    thumbs.append(pygame.transform.smoothscale(frame, (w // 4, h // 4)))
        sheet = pygame.Surface((w // 4 * 3, h // 4 * len(TIMELINE)))
        for k, t in enumerate(thumbs):
            sheet.blit(t, (k % 3 * w // 4, k // 3 * h // 4))
        path = os.path.join(tempfile.gettempdir(), "trailer-sheet.png")
        pygame.image.save(sheet, path)
        print(path)
        return

    tmp = tempfile.mkdtemp(prefix="ninja-trailer-")
    try:
        master = os.path.join(tmp, "master.mkv")
        raw = f"-f rawvideo -pix_fmt rgb24 -s {w}x{h} -r {FPS} -i -".split()
        lossless = "-c:v libx264rgb -qp 0 -preset ultrafast".split()
        enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", *raw, *lossless, master], stdin=subprocess.PIPE)
        assert enc.stdin
        for frame in studio.frames(TIMELINE):
            enc.stdin.write(pygame.image.tobytes(frame, "RGB"))
            if studio.frame_no % 300 == 0:
                print(f"  {studio.frame_no / FPS:5.1f}s rendered", flush=True)
        enc.stdin.close()
        if enc.wait():
            raise SystemExit("ffmpeg failed to encode the master")
        total = studio.frame_no
        print(f"{total} frames ({total / FPS:.1f}s), {len(studio.cues)} sound cues")

        audio = os.path.join(tmp, "audio.wav")
        mix(studio.cues, total, audio)
        mp4 = os.path.join(OUT_DIR, "trailer.mp4")
        video = "-c:v libx264 -preset slow -crf 16 -tune animation -pix_fmt yuv420p".split()
        sound = "-af loudnorm=I=-16:TP=-1.5 -c:a aac -ar 48000 -b:a 192k".split()
        ffmpeg("-i", master, "-i", audio, *video, *sound, "-movflags", "+faststart", "-shortest", mp4)
        print(mp4)

        if not args.no_gif:
            gif = os.path.join(OUT_DIR, "trailer.gif")
            # Pixel art has few colours: one palette for the whole clip, no dithering
            palette = "split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none"
            ffmpeg("-i", master, "-filter_complex", f"fps={GIF_FPS},scale={GIF_W}:-1:flags=neighbor,{palette}", gif)
            print(gif)

        social = os.path.join(OUT_DIR, "social-preview.png")
        pygame.image.save(studio.social(), social)
        print(social)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", action="store_true", help="only render a contact sheet of the shots")
    parser.add_argument("--no-gif", action="store_true", help="skip the README GIF")
    render(parser.parse_args())


if __name__ == "__main__":
    main()
