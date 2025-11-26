"""Replay and ghost playback system (Issue 30).

Provides lightweight recording of the local player's trajectory together
with a translucent ghost playback for subsequent runs. Records are stored
per-level so that best runs can be surfaced later (e.g. speedrunning, QA).

Design goals:
    * Zero runtime overhead when unused (graceful fallbacks if assets missing)
    * Deterministic playback tied to recorded frame samples (position, flip, anim)
    * Persistence of best runs while keeping most recent run in-memory for
      immediate ghost comparison after a restart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pygame

from scripts.settings import settings as global_settings

REPLAY_VERSION = 1


@dataclass(slots=True)
class FrameSample:
    """Single frame of replay data."""

    x: float
    y: float
    flip: bool
    action: str
    anim_frame: int

    def to_dict(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "flip": self.flip,
            "action": self.action,
            "anim": self.anim_frame,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "FrameSample":
        return cls(
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            flip=bool(payload.get("flip", False)),
            action=str(payload.get("action", "idle")),
            anim_frame=int(payload.get("anim", 0)),
        )


class ReplayRecording:
    """In-memory representation of a single run."""

    def __init__(self, level: str, skin_path: str, *, duration_ms: int = 0) -> None:
        self.level = level
        self.skin_path = skin_path
        self.duration_ms = duration_ms
        self.frames: List[FrameSample] = []

    def append_player(self, player) -> None:
        action = getattr(player, "action", "idle") or "idle"
        animation = getattr(player, "animation", None)
        frame_value = int(getattr(animation, "frame", 0)) if animation else 0
        self.frames.append(
            FrameSample(
                x=float(player.pos[0]),
                y=float(player.pos[1]),
                flip=bool(getattr(player, "flip", False)),
                action=action,
                anim_frame=frame_value,
            )
        )

    # Serialization helpers -------------------------------------------------
    def to_json(self) -> dict:
        return {
            "version": REPLAY_VERSION,
            "level": self.level,
            "skin": self.skin_path,
            "duration_ms": int(self.duration_ms),
            "frames": [sample.to_dict() for sample in self.frames],
        }

    @classmethod
    def from_json(cls, payload: dict) -> "ReplayRecording":
        level = str(payload.get("level", "0"))
        skin = str(payload.get("skin", "default"))
        rec = cls(level, skin, duration_ms=int(payload.get("duration_ms", 0)))
        frames = payload.get("frames", [])
        for item in frames:
            rec.frames.append(FrameSample.from_dict(item))
        return rec

    def clone(self) -> "ReplayRecording":
        dup = ReplayRecording(self.level, self.skin_path, duration_ms=self.duration_ms)
        dup.frames = [FrameSample(f.x, f.y, f.flip, f.action, f.anim_frame) for f in self.frames]
        return dup


class ReplayGhost:
    """Ghost entity backed by recorded frame samples."""

    _TINT_COLOR = (100, 220, 255, 180)

    def __init__(self, recording: ReplayRecording, assets: Dict[str, object] | None) -> None:
        self.recording = recording
        self._assets = assets or {}
        self._index = 0
        self._tint_cache: Dict[tuple[str, int], pygame.Surface] = {}
        self._base_frame_cache: Dict[str, tuple[List[pygame.Surface], int]] = {}
        if self.recording.frames:
            self._prepare_animation_cache()

    # Public helpers --------------------------------------------------------
    def reset(self) -> None:
        self._index = 0

    def step_and_render(self, surface: pygame.Surface, offset: tuple[int, int]) -> None:
        if not self.recording.frames:
            return
        frame = self.recording.frames[min(self._index, len(self.recording.frames) - 1)]
        img = self._frame_image(frame)
        if img is None:
            fallback = pygame.Surface((14, 22), pygame.SRCALPHA)
            pygame.draw.ellipse(fallback, (120, 220, 255, 140), fallback.get_rect())
            surface.blit(fallback, (frame.x - offset[0], frame.y - offset[1]))
        else:
            surface.blit(img, (frame.x - offset[0], frame.y - offset[1]))
        if self._index < len(self.recording.frames) - 1:
            self._index += 1

    def current_frame(self) -> Optional[FrameSample]:
        if not self.recording.frames:
            return None
        return self.recording.frames[min(self._index, len(self.recording.frames) - 1)]

    # Internal helpers ------------------------------------------------------
    def _prepare_animation_cache(self) -> None:
        unique_actions = {frame.action for frame in self.recording.frames}
        base_prefix = f"player/{self.recording.skin_path}/"
        for action in unique_actions:
            key = base_prefix + action
            asset = self._assets.get(key)
            if asset is None:
                continue
            images = getattr(asset, "images", None)
            img_dur = getattr(asset, "img_duration", 1)
            if images and isinstance(images, Iterable):
                self._base_frame_cache[action] = (list(images), int(max(1, img_dur)))

    def _frame_image(self, frame: FrameSample) -> Optional[pygame.Surface]:
        cache_entry = self._base_frame_cache.get(frame.action)
        if not cache_entry:
            return None
        frames, img_dur = cache_entry
        if not frames:
            return None
        idx = max(0, min(len(frames) - 1, frame.anim_frame // img_dur))
        tint_key = (frame.action, idx)
        tinted = self._tint_cache.get(tint_key)
        if tinted is None:
            base = frames[idx]
            tinted = base.copy()
            tint_surface = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
            tint_surface.fill(self._TINT_COLOR)
            tinted.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            tinted.set_alpha(self._TINT_COLOR[3])
            self._tint_cache[tint_key] = tinted
        if frame.flip:
            flip_key = (frame.action, idx, "flip")
            flipped = self._tint_cache.get(flip_key)
            if flipped is None:
                flipped = pygame.transform.flip(tinted, True, False)
                self._tint_cache[flip_key] = flipped
            return flipped
        return tinted

    # Debug helpers ---------------------------------------------------------
    def debug_index(self) -> int:
        return self._index


class ReplayManager:
    """Coordinates recording and ghost playback for the active Game instance."""

    def __init__(self, game, storage_dir: str | Path | None = None, settings_obj=None) -> None:
        self.game = game
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/replays")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.last_runs_dir = self.storage_dir / "last_runs"
        self.last_runs_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings_obj or global_settings
        self.current_level: Optional[str] = None
        self.recording: Optional[ReplayRecording] = None
        self.best_recording: Optional[ReplayRecording] = None
        self.last_recording: Optional[ReplayRecording] = None
        self._pending_playback: Optional[ReplayRecording] = None
        self.ghost: Optional[ReplayGhost] = None

    # Level lifecycle ------------------------------------------------------
    def on_level_load(self, level: int | str, player) -> None:
        self.current_level = str(level)
        self.recording = None
        self.best_recording = None
        self.last_recording = None
        playback_source = None
        self.ghost = None
        if not self._ghosts_enabled():
            self._pending_playback = None
            return

        skin_path = self._skin_path_for_player(player)
        self.recording = ReplayRecording(self.current_level, skin_path)
        self.best_recording = self._load_from_disk(self.current_level, kind="best")
        self.last_recording = self._load_from_disk(self.current_level, kind="last")
        if self._pending_playback and self._pending_playback.level == self.current_level:
            playback_source = self._pending_playback
        elif self.best_recording and self.best_recording.level == self.current_level:
            playback_source = self.best_recording
        elif self.last_recording and self.last_recording.level == self.current_level:
            playback_source = self.last_recording
        self._pending_playback = None
        if playback_source and playback_source.frames:
            self.ghost = ReplayGhost(playback_source.clone(), getattr(self.game, "assets", {}))
            self.ghost.reset()

    def abort_current_run(self) -> None:
        if self.recording:
            self.recording = ReplayRecording(self.recording.level, self.recording.skin_path)

    # Frame sampling -------------------------------------------------------
    def capture_player(self, player) -> None:
        if not self._ghosts_enabled() or not self.recording or not self.recording.level:
            return
        if getattr(self.game, "dead", 0):
            return
        self.recording.append_player(player)

    # Completion -----------------------------------------------------------
    def commit_run(self, *, duration_ms: int, new_best: bool) -> None:
        if not self._ghosts_enabled() or not self.recording or not self.recording.frames:
            return
        self.recording.duration_ms = duration_ms
        committed = self.recording.clone()
        self._pending_playback = committed.clone()
        self.last_recording = committed.clone()
        self._save_to_disk(committed, kind="last")
        if new_best:
            self._save_to_disk(committed, kind="best")
            self.best_recording = committed.clone()
        # Prepare for next run (maintain same skin)
        self.recording = ReplayRecording(self.current_level or "0", committed.skin_path)

    # Rendering ------------------------------------------------------------
    def advance_and_render(self, render_surface: pygame.Surface, offset: tuple[int, int]) -> None:
        if not self._ghosts_enabled() or not self.ghost:
            return
        self.ghost.step_and_render(render_surface, offset)

    # Persistence ----------------------------------------------------------
    def _replay_path(self, level: str, *, kind: str = "best") -> Path:
        if kind == "best":
            return self.storage_dir / f"{level}.json"
        return self.last_runs_dir / f"{level}.json"

    def _save_to_disk(self, recording: ReplayRecording, *, kind: str = "best") -> None:
        path = self._replay_path(recording.level, kind=kind)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(recording.to_json(), fh, indent=2)

    def _load_from_disk(self, level: str, *, kind: str = "best") -> Optional[ReplayRecording]:
        path = self._replay_path(level, kind=kind)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return ReplayRecording.from_json(data)
        except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
            return None

    # Utility --------------------------------------------------------------
    def _skin_path_for_player(self, player) -> str:
        try:
            from scripts.collectableManager import CollectableManager as CM

            skins = CM.SKIN_PATHS
            idx = int(getattr(player, "skin", 0))
            if 0 <= idx < len(skins):
                return skins[idx]
        except Exception:  # pragma: no cover - fallback
            pass
        return "default"

    # Test helpers ---------------------------------------------------------
    def ghost_current_frame(self) -> Optional[FrameSample]:
        if not self.ghost:
            return None
        return self.ghost.current_frame()

    def ghost_index(self) -> int:
        if not self.ghost:
            return 0
        return self.ghost.debug_index()

    def has_ghost(self) -> bool:
        return self._ghosts_enabled() and self.ghost is not None

    def _ghosts_enabled(self) -> bool:
        try:
            return bool(getattr(self.settings, "ghost_enabled", True))
        except Exception:  # pragma: no cover - defensive
            return True


__all__ = ["ReplayManager", "ReplayRecording", "ReplayGhost", "FrameSample"]
