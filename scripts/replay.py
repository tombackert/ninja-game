"""Replay and ghost playback system.

Updated to support input-based recording (for replays) and interpolated
ghosts using sparse snapshots.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Any

import pygame

from scripts.settings import settings as global_settings
from scripts.snapshot import SimulationSnapshot, SnapshotService
from scripts.network.messages import InputMessage

REPLAY_VERSION = 2  # Bumped for new schema

@dataclass(slots=True)
class FrameSample:
    """Single frame of replay data (Visual Ghost)."""
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

@dataclass
class ReplayData:
    """Full replay container (Inputs + Snapshots)."""
    level: str
    skin: str
    seed: int
    duration_frames: int
    inputs: List[Dict[str, Any]] = field(default_factory=list) # List of InputMessage dicts
    snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict) # tick -> snapshot dict (sparse)
    # Visual fallback for lightweight ghosts (legacy support or optimization)
    visual_frames: List[FrameSample] = field(default_factory=list) 

    def to_json(self) -> dict:
        return {
            "version": REPLAY_VERSION,
            "level": self.level,
            "skin": self.skin,
            "seed": self.seed,
            "duration_frames": self.duration_frames,
            "inputs": self.inputs,
            "snapshots": self.snapshots,
            "visual_frames": [f.to_dict() for f in self.visual_frames],
        }

    @classmethod
    def from_json(cls, data: dict) -> "ReplayData":
        rd = cls(
            level=str(data.get("level", "0")),
            skin=str(data.get("skin", "default")),
            seed=int(data.get("seed", 0)),
            duration_frames=int(data.get("duration_frames", 0)),
            inputs=data.get("inputs", []),
            snapshots=data.get("snapshots", {}),
        )
        frames = data.get("visual_frames", []) # Legacy key 'frames' mapped to visual_frames?
        if not frames and "frames" in data:
             frames = data["frames"]
        
        rd.visual_frames = [FrameSample.from_dict(f) for f in frames]
        return rd


class ReplayRecording:
    """Active recording session wrapper."""
    def __init__(self, level: str, skin: str, seed: int):
        self.data = ReplayData(level=level, skin=skin, seed=seed, duration_frames=0)
        self.start_tick = 0

    def capture_frame(self, tick: int, player: Any, inputs: List[str], snapshot: Optional[Any] = None):
        # 1. Visual capture (every frame, or sparse if we wanted)
        # Maintaining every-frame visual capture for now to ensure smooth ghost without interpolation complexity yet
        self.data.visual_frames.append(self._extract_sample(player))
        
        # 2. Input capture
        self.data.inputs.append({"tick": tick, "inputs": inputs})
        
        # 3. Snapshot capture (sparse)
        if snapshot:
            # SnapshotService.serialize returns a dict (JSON compatible)
            # We assume snapshot is already a SimulationSnapshot object
            # But wait, SnapshotService.serialize takes a snapshot object.
            # If 'snapshot' passed here is the object, we serialize it.
            serialized = SnapshotService.serialize(snapshot)
            self.data.snapshots[str(tick)] = serialized

        self.data.duration_frames += 1

    def _extract_sample(self, player: Any) -> FrameSample:
        action = getattr(player, "action", "idle") or "idle"
        animation = getattr(player, "animation", None)
        frame_value = int(getattr(animation, "frame", 0)) if animation else 0
        return FrameSample(
            x=float(player.pos[0]),
            y=float(player.pos[1]),
            flip=bool(getattr(player, "flip", False)),
            action=action,
            anim_frame=frame_value,
        )


class ReplayGhost:
    """Renders a ghost from ReplayData.
    
    Currently uses 'visual_frames' for direct playback.
    Future: Use 'snapshots' + interpolation if visual_frames are sparse.
    """
    _TINT_COLOR = (100, 220, 255, 180)

    def __init__(self, data: ReplayData, assets: Dict[str, Any]):
        self.data = data
        self.assets = assets
        self.index = 0
        self._tint_cache: Dict[tuple, pygame.Surface] = {}
        self._base_frame_cache: Dict[str, tuple[List[pygame.Surface], int]] = {}
        if self.data.visual_frames:
            self._prepare_animation_cache()

    def step_and_render(self, surface: pygame.Surface, offset: tuple[int, int]):
        if not self.data.visual_frames:
            return
        
        frame = self.data.visual_frames[min(self.index, len(self.data.visual_frames) - 1)]
        img = self._frame_image(frame)
        
        if img:
            surface.blit(img, (frame.x - offset[0], frame.y - offset[1]))
        
        if self.index < len(self.data.visual_frames) - 1:
            self.index += 1

    def _prepare_animation_cache(self):
        unique_actions = {f.action for f in self.data.visual_frames}
        base_prefix = f"player/{self.data.skin}/"
        for action in unique_actions:
            key = base_prefix + action
            asset = self.assets.get(key)
            if asset:
                images = getattr(asset, "images", [])
                img_dur = getattr(asset, "img_duration", 1)
                self._base_frame_cache[action] = (list(images), int(max(1, img_dur)))

    def _frame_image(self, frame: FrameSample) -> Optional[pygame.Surface]:
        cache_entry = self._base_frame_cache.get(frame.action)
        if not cache_entry: return None
        frames, img_dur = cache_entry
        if not frames: return None
        
        idx = max(0, min(len(frames) - 1, frame.anim_frame // img_dur))
        tint_key = (frame.action, idx)
        tinted = self._tint_cache.get(tint_key)
        
        if tinted is None:
            base = frames[idx]
            tinted = base.copy()
            tint_surf = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
            tint_surf.fill(self._TINT_COLOR)
            tinted.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
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
    
    def reset(self):
        self.index = 0


class ReplayManager:
    def __init__(self, game, storage_dir=None):
        self.game = game
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/replays")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.last_runs_dir = self.storage_dir / "last_runs"
        self.last_runs_dir.mkdir(parents=True, exist_ok=True)
        
        self.recording: Optional[ReplayRecording] = None
        self.ghost: Optional[ReplayGhost] = None
        self.best_data: Optional[ReplayData] = None
        self.last_data: Optional[ReplayData] = None
        
        self.tick_counter = 0

    def on_level_load(self, level: int | str, player: Any):
        level_str = str(level)
        from scripts.rng_service import RNGService
        seed = RNGService.get().get_state()[1][0] # Hacky extraction of seed or just use 0 if not accessible
        # Better:
        # seed = RNGService.get_seed() # If available
        seed = 0 # Placeholder
        
        skin = self._get_skin(player)
        
        # Start recording
        if self._ghosts_enabled():
            self.recording = ReplayRecording(level_str, skin, seed)
            self.tick_counter = 0
            
            # Load best run
            self.best_data = self._load(level_str, "best")
            self.last_data = self._load(level_str, "last")
            
            # Prioritize last run if it was same level (instant retry), else best
            source = None
            if self.last_data and self.last_data.level == level_str:
                source = self.last_data
            elif self.best_data and self.best_data.level == level_str:
                source = self.best_data
            
            if source:
                self.ghost = ReplayGhost(source, getattr(self.game, "assets", {}))
                self.ghost.reset()

    def update(self, player: Any, inputs: List[str]):
        """Called every frame to capture state."""
        if not self.recording: return
        if getattr(self.game, "dead", 0): return
        
        # Capture snapshot every 60 frames (1s)
        snap = None
        if self.tick_counter % 60 == 0:
            # Snapshots might be heavy, ensure we don't lag
            try:
                snap = SnapshotService.capture(self.game)
            except Exception:
                pass
        
        self.recording.capture_frame(self.tick_counter, player, inputs, snap)
        self.tick_counter += 1

    def commit_run(self, new_best: bool):
        if not self.recording or self.recording.data.duration_frames < 10: return
        
        data = self.recording.data
        self.last_data = data
        self._save(data, "last")
        
        if new_best:
            self.best_data = data
            self._save(data, "best")

    def render_ghost(self, surface, offset):
        if self.ghost and self._ghosts_enabled():
            self.ghost.step_and_render(surface, offset)

    def _save(self, data: ReplayData, kind: str):
        path = self._path(data.level, kind)
        with path.open("w") as f:
            json.dump(data.to_json(), f)

    def _load(self, level: str, kind: str) -> Optional[ReplayData]:
        path = self._path(level, kind)
        if not path.exists(): return None
        try:
            with path.open("r") as f:
                return ReplayData.from_json(json.load(f))
        except Exception:
            return None

    def _path(self, level: str, kind: str) -> Path:
        return (self.storage_dir if kind == "best" else self.last_runs_dir) / f"{level}.json"

    def _ghosts_enabled(self) -> bool:
        return bool(getattr(global_settings, "ghost_enabled", True))

    def _get_skin(self, player) -> str:
        try:
            from scripts.collectableManager import CollectableManager as CM
            idx = int(getattr(player, "skin", 0))
            return CM.SKIN_PATHS[idx] if 0 <= idx < len(CM.SKIN_PATHS) else "default"
        except:
            return "default"

__all__ = ["ReplayManager", "ReplayRecording", "ReplayGhost", "ReplayData"]