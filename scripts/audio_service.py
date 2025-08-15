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
from typing import Dict
import pygame
from scripts.asset_manager import AssetManager
from scripts.settings import settings


class AudioService:
    _instance: "AudioService | None" = None

    def __init__(self) -> None:
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
        pygame.mixer.music.set_volume(music_v)

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
        snd.play(loops)

    # Music ---------------------------------------------------------------
    def play_music(self, track: str = "data/music.wav", loops: int = -1) -> None:
        pygame.mixer.music.load(track)
        pygame.mixer.music.play(loops)
        self.apply_volumes()

    def stop_music(self) -> None:
        pygame.mixer.music.stop()

    def set_music_volume(self, v: float) -> None:
        settings.music_volume = v
        self.apply_volumes()

    def set_sound_volume(self, v: float) -> None:
        settings.sound_volume = v
        self.apply_volumes()


__all__ = ["AudioService"]
