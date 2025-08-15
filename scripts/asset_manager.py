"""AssetManager (Issue 15)

Centralized lazy loading and caching for images, animations and sounds.
Replaces scattered `load_image`, `load_images`, and direct `pygame.mixer.Sound`
usage across the codebase. Provides a single import side-effect location
for Pygame resource I/O to simplify future headless / asset pipeline changes.

Design:
- Singleton-style access via `AssetManager.get()` 
  (lightweight; thread-safety not required now).
- Image cache keyed by relative path under data/images/ *without* leading slash.
- Animation builder caches underlying frame lists; 
  each `get_animation` returns a *fresh* Animation copy so per-entity state (frame index) is not shared.
- Sound cache keyed by relative path under data/sfx/.
- Background preloading minimal; other assets load on first request.

Future Extensions (Roadmap):
- Async / threaded preloading (issue later for startup latency hiding).
- Reference counting & unloading for large texture sets.
- Pack file / atlas support.
"""

from __future__ import annotations
from typing import Dict, List
import os
import pygame
from scripts.utils import Animation, BASE_IMG_PATH

IMG_ROOT = BASE_IMG_PATH  # 'data/images/'
SFX_ROOT = "data/sfx/"


class AssetManager:
    _instance: "AssetManager | None" = None

    def __init__(self) -> None:
        self._images: Dict[str, pygame.Surface] = {}
        self._image_frames: Dict[str, List[pygame.Surface]] = {}
        self._animations: Dict[str, List[pygame.Surface]] = {}
        self._sounds: Dict[str, pygame.mixer.Sound] = {}

    # Singleton accessor -------------------------------------------------
    @classmethod
    def get(cls) -> "AssetManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # Image helpers ------------------------------------------------------
    def get_image(self, rel_path: str) -> pygame.Surface:
        surf = self._images.get(rel_path)
        if surf is None:
            full = os.path.join(IMG_ROOT, rel_path)
            raw = pygame.image.load(full)
            # When no display mode set (headless tests), convert() raises error.
            if pygame.display.get_init() and pygame.display.get_surface():
                try:
                    raw = raw.convert()
                except pygame.error:
                    pass
            else:  # keep original format
                try:
                    raw = raw.convert_alpha()
                except pygame.error:
                    pass
            raw.set_colorkey((0, 0, 0))
            surf = raw
            self._images[rel_path] = surf
        return surf

    def get_image_frames(self, rel_dir: str) -> List[pygame.Surface]:
        frames = self._image_frames.get(rel_dir)
        if frames is None:
            full_dir = os.path.join(IMG_ROOT, rel_dir)
            frames = []
            for img_name in sorted(os.listdir(full_dir)):
                frames.append(self.get_image(os.path.join(rel_dir, img_name)))
            self._image_frames[rel_dir] = frames
        return frames

    # Animations ---------------------------------------------------------
    def get_animation(
        self, rel_dir: str, img_dur: int = 5, loop: bool = True
    ) -> Animation:
        # Cache raw frames; always return a new Animation wrapper
        frames = self.get_image_frames(rel_dir)
        return Animation(frames, img_dur, loop)

    # Sounds -------------------------------------------------------------
    def get_sound(self, rel_path: str) -> pygame.mixer.Sound:
        snd = self._sounds.get(rel_path)
        if snd is None:
            full = os.path.join(SFX_ROOT, rel_path)
            snd = pygame.mixer.Sound(full)
            self._sounds[rel_path] = snd
        return snd


__all__ = ["AssetManager"]
