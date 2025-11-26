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
from typing import Dict

import pygame

from scripts.asset_manager import AssetManager
from scripts.settings import settings


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
        self._sfx: Dict[str, pygame.mixer.Sound] = {}
        self._am = AssetManager.get()
        # Pre-register known sounds (can lazily add later)
        for name in ["jump", "dash", "hit", "shoot", "ambience", "collect"]:
            self._sfx[name] = self._am.get_sound(f"{name}.wav")
        self.apply_volumes()

    @classmethod
    def get(cls) -> "AudioService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # Volume management --------------------------------------------------
    def apply_volumes(self) -> None:
        music_v = settings.music_volume
        sound_v = settings.sound_volume
        for k, snd in self._sfx.items():
            base = 1.0
            if k == "ambience":
                base = 0.2
            elif k == "shoot":
                base = 0.4
            elif k == "hit":
                base = 0.8
            elif k == "dash":
                base = 0.1
            elif k == "jump":
                base = 0.7
            elif k == "collect":
                base = 0.4
            snd.set_volume(sound_v * base)
        try:
            pygame.mixer.music.set_volume(music_v)
        except Exception:
            pass

    # SFX ----------------------------------------------------------------
    def play(self, name: str, loops: int = 0) -> None:
        snd = self._sfx.get(name)
        if snd is None:  # lazy load unknown
            try:
                snd = self._am.get_sound(f"{name}.wav")
                self._sfx[name] = snd
            except Exception:
                return
            self.apply_volumes()
        try:
            snd.play(loops)
        except Exception:
            pass

    # Music ---------------------------------------------------------------
    def play_music(self, track: str = "data/music.wav", loops: int = -1) -> None:
        try:
            pygame.mixer.music.load(track)
            pygame.mixer.music.play(loops)
            self.apply_volumes()
        except Exception:
            pass

    def stop_music(self) -> None:
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


__all__ = ["AudioService"]
