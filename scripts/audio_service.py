"""AudioService (Issue 16)

Central abstraction over pygame.mixer for SFX and music playback.

Goals:
- Uniform interface for playing sounds by id without exposing raw mixer objects.
- Central volume management synced with settings (music_volume, sound_volume).
- Future: channel pooling, concurrency limits, ducking, 3D positional audio.

Design:
- Singleton-style via get().
- Registers & caches Sound objects using AssetManager's get_sound for consistency.
- Music control wraps pygame.mixer.music.* functions.
"""

from __future__ import annotations

import os
import random
from array import array
from typing import Dict, List

import pygame

from scripts.asset_manager import AssetManager
from scripts.settings import settings

# Every effect in data/sfx, loaded at start (more load lazily on first play)
SFX_NAMES = [
    "jump", "dash", "hit", "shoot", "ambience", "collect",
    # tools/gen_audio.py
    "land", "wall_jump", "double_jump", "swim", "splash", "stomp", "coin", "heart",
    "checkpoint", "death", "level_clear", "menu_move", "menu_select", "menu_back", "breath_low",
    "crumble",
]  # fmt: skip

# Loudness of each effect relative to the sound volume setting. Measured,
# not guessed: `python tools/gen_audio.py balance` computes them from each
# file's A-weighted loudness and the mix in its TARGET_DB (dash and kills
# above a jump; coins, stomps, swim strokes and menus below).
BASE_VOLUME = {
    "ambience": 0.2,
    "jump": 0.7,
    "wall_jump": 0.715,
    "double_jump": 0.129,
    "land": 0.533,
    "dash": 0.23,
    "hit": 0.739,
    "stomp": 0.256,
    "shoot": 0.296,
    "coin": 0.07,
    "collect": 0.55,
    "heart": 0.111,
    "checkpoint": 0.168,
    "death": 0.2,
    "level_clear": 0.189,
    "splash": 0.252,
    "swim": 0.113,
    "crumble": 0.565,
    "breath_low": 0.056,
    "menu_move": 0.049,
    "menu_select": 0.041,
    "menu_back": 0.036,
}

# Short effects heard over and over get a slightly different pitch each
# time (one of these playback-rate factors), so they do not sound canned
PITCH_VARIANTS = (0.93, 0.965, 1.035, 1.07)
VARIED = {"jump", "land", "wall_jump", "double_jump", "swim", "stomp", "coin", "hit", "dash", "crumble"}

# Mixer channels: enough that a burst of effects never cuts one off
CHANNELS = 24

# Music by the level's sky: each world has its own loop (tools/gen_audio.py);
# the sky islands and caves keep the original track
DEFAULT_MUSIC = "data/music/music_0.wav"
WORLD_MUSIC = {
    "background-desert.png": "data/music/music_desert.wav",
    "background-mars.png": "data/music/music_mars.wav",
    "background-lagoon.png": "data/music/music_sea.wav",
    "background-deep.png": "data/music/music_sea.wav",
}


def music_for(meta_data: dict) -> str:
    """The track of a level: its own "music" if it names another than the
    default, else the one of its world (WORLD_MUSIC)."""
    own = meta_data.get("music")
    if own and own != DEFAULT_MUSIC:
        return own
    return WORLD_MUSIC.get(meta_data.get("background"), DEFAULT_MUSIC)


def _resampled(snd: "pygame.mixer.Sound", factor: float) -> "pygame.mixer.Sound | None":
    """`snd` played `factor` times as fast (higher and shorter), or None if
    the mixer format is not one this handles. Nearest-sample resampling is
    enough for a few percent."""
    init = pygame.mixer.get_init()
    if not init:
        return None
    _, size, channels = init
    code = {-16: "h", 16: "H", 32: "f", -8: "b", 8: "B"}.get(size)
    if code is None:
        return None
    src = array(code)
    src.frombytes(snd.get_raw())
    frames = len(src) // channels
    count = int(frames / factor)
    if count < 2:
        return None
    if channels == 1:
        out = array(code, [src[int(i * factor)] for i in range(count)])
    else:
        out = array(code, [src[int(i * factor) * channels + c] for i in range(count) for c in range(channels)])
    return pygame.mixer.Sound(buffer=out.tobytes())


class AudioService:
    _instance: "AudioService | None" = None

    def __init__(self) -> None:
        # Ensure mixer initialized (CI headless may need dummy audio driver)
        if not pygame.get_init():  # Guard in case service used before global init
            pygame.init()
        if not pygame.mixer.get_init():
            # Try normal init first; if it fails (no audio device), fallback to dummy
            try:
                pygame.mixer.init()
            except pygame.error:
                # Attempt fallback to dummy audio driver
                os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
                try:
                    pygame.mixer.init()
                except pygame.error:
                    # As a last resort, create no-op stand-ins; tests that patch sounds will still function.
                    class _NullMusic:
                        def load(self, *a, **kw):
                            pass

                        def play(self, *a, **kw):
                            pass

                        def set_volume(self, *a, **kw):
                            pass

                        def stop(self):
                            pass

                    pygame.mixer.music = _NullMusic()  # type: ignore
        try:
            pygame.mixer.set_num_channels(CHANNELS)
        except Exception:
            pass
        self._sfx: Dict[str, pygame.mixer.Sound] = {}
        self._variants: Dict[str, List[pygame.mixer.Sound]] = {}
        self._am = AssetManager.get()
        # Pitch picks are looks only: never the game's seeded RNG
        self._rand = random.Random()
        self._music_track: str | None = None
        self._loops: Dict[str, "pygame.mixer.Channel | None"] = {}
        # Pre-register known sounds (can lazily add later)
        for name in SFX_NAMES:
            try:
                self._sfx[name] = self._am.get_sound(f"{name}.wav")
            except Exception:
                continue
            if name in VARIED:
                self._variants[name] = self._make_variants(self._sfx[name])
        self._duck_factor = 1.0
        self._duck_target = 1.0
        self._duck_speed = 0.1
        self.apply_volumes()

    @classmethod
    def get(cls) -> "AudioService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _make_variants(snd) -> List["pygame.mixer.Sound"]:
        variants = [snd]
        for factor in PITCH_VARIANTS:
            try:
                v = _resampled(snd, factor)
            except Exception:  # a stand-in sound (tests) or an odd mixer format
                v = None
            if v is not None:
                variants.append(v)
        return variants

    # Ducking ------------------------------------------------------------
    def trigger_ducking(self, duration: float = 0.5, intensity: float = 0.3) -> None:
        """Temporarily lower music volume."""
        self._duck_target = intensity
        # For simplicity, we just set the target.
        # Ideally, we'd have a timer, but a simple 'decay back to 1.0' in update works too.
        # Let's use a simple approach: set target low, and update() slowly raises it back.

    def update(self) -> None:
        """Called every frame to update ducking envelope."""
        # If we have a target lower than current factor, move down towards it
        if self._duck_target < self._duck_factor:
            self._duck_factor = max(self._duck_target, self._duck_factor - 0.1)
            if self._duck_factor <= self._duck_target + 0.01:
                # Reached bottom, reset target to 1.0 so we rise back up next frame
                self._duck_target = 1.0
            self.apply_volumes()
        # Otherwise, if we are below 1.0, rise back up
        elif self._duck_factor < 1.0:
            self._duck_factor = min(1.0, self._duck_factor + 0.05)
            self.apply_volumes()

    # Volume management --------------------------------------------------
    def apply_volumes(self) -> None:
        music_v = settings.music_volume * self._duck_factor
        sound_v = settings.sound_volume
        for k, snd in self._sfx.items():
            v = sound_v * BASE_VOLUME.get(k, 1.0)
            for variant in self._variants.get(k, (snd,)):
                variant.set_volume(v)
        try:
            pygame.mixer.music.set_volume(music_v)
        except Exception:
            pass

    # SFX ----------------------------------------------------------------
    def play(self, name: str, loops: int = 0, volume: float = 1.0) -> None:
        """Play effect `name`; `volume` scales it for this play (e.g. by how hard a landing was)."""
        snd = self._sfx.get(name)
        if snd is None:  # lazy load unknown
            try:
                snd = self._am.get_sound(f"{name}.wav")
                self._sfx[name] = snd
            except Exception:
                return
            self.apply_volumes()
        variants = self._variants.get(name)
        if variants and loops == 0:
            snd = self._rand.choice(variants)
        try:
            channel = snd.play(loops)
            if channel is not None and volume != 1.0:
                channel.set_volume(max(0.0, min(1.0, volume)))
        except Exception:
            pass

    def play_loop(self, name: str) -> None:
        """Loop effect `name` (the ambience) unless it is looping already:
        every level start asks for it, and each extra copy would hold a
        mixer channel for good."""
        channel = self._loops.get(name)
        try:
            if channel is not None and channel.get_busy():
                return
        except Exception:
            pass
        snd = self._sfx.get(name)
        if snd is None:
            self.play(name, loops=-1)
            return
        try:
            self._loops[name] = snd.play(-1)
        except Exception:
            pass

    # Music ---------------------------------------------------------------
    def play_music(self, track: str = "data/music.wav", loops: int = -1) -> None:
        """Start `track`; one that is already playing goes on (the next level
        of the same world keeps its music instead of starting it over)."""
        try:
            if track == self._music_track and pygame.mixer.music.get_busy():
                return
        except Exception:
            pass
        try:
            pygame.mixer.music.load(track)
            pygame.mixer.music.play(loops)
            self._music_track = track
            self.apply_volumes()
        except Exception:
            pass

    def stop_music(self) -> None:
        self._music_track = None
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def set_music_volume(self, v: float) -> None:
        settings.music_volume = v
        self.apply_volumes()

    def set_sound_volume(self, v: float) -> None:
        settings.sound_volume = v
        self.apply_volumes()


def ui_sound(name: str) -> None:
    """A menu sound (move, select, back); silent under the test suite."""
    if os.environ.get("NINJA_GAME_TESTING") == "1":
        return
    try:
        AudioService.get().play(name)
    except Exception:
        pass


__all__ = ["AudioService", "music_for", "ui_sound"]
