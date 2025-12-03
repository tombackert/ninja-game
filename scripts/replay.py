"""Replay and ghost playback system.

Refactored to perform true deterministic re-simulation of the ghost entity
using recorded inputs and snapshots. Snapshot frequency is increased to
minimize correction drift/teleporting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import pygame

from scripts.settings import settings as global_settings
from scripts.snapshot import SnapshotService
from scripts.entities import Player

REPLAY_VERSION = 2


@dataclass(slots=True)
class FrameSample:
    """Single frame of replay data (Legacy Visual Ghost)."""

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
    inputs: List[Dict[str, Any]] = field(default_factory=list)  # [{"tick": N, "inputs": ["left", ...]}, ...]
    snapshots: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # tick -> serialized snapshot

    # Kept for legacy load compatibility
    visual_frames: List[Any] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "version": REPLAY_VERSION,
            "level": self.level,
            "skin": self.skin,
            "seed": self.seed,
            "duration_frames": self.duration_frames,
            "inputs": self.inputs,
            "snapshots": self.snapshots,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ReplayData":
        return cls(
            level=str(data.get("level", "0")),
            skin=str(data.get("skin", "default")),
            seed=int(data.get("seed", 0)),
            duration_frames=int(data.get("duration_frames", 0)),
            inputs=data.get("inputs", []),
            snapshots=data.get("snapshots", {}),
            visual_frames=data.get("visual_frames", []),
        )


class ReplayRecording:
    """Active recording session."""

    def __init__(self, level: str, skin: str, seed: int):
        self.data = ReplayData(level=level, skin=skin, seed=seed, duration_frames=0)

    def capture_frame(
        self, tick: int, player: Any, inputs: List[str], snapshot: Optional[Any] = None, optimized: bool = True
    ):
        # Capture Inputs
        self.data.inputs.append({"tick": tick, "inputs": inputs})

        # Capture Snapshot
        # Logic: If `snapshot` object is passed, it's assumed to be already captured.
        # However, the caller (ReplayManager.update) calls SnapshotService.capture().
        # We should move the capture call inside here OR update ReplayManager to pass the flag.
        # ReplayManager calls capture() then calls capture_frame().
        # To avoid double capture or refactoring caller too much:
        # If the snapshot passed is ALREADY optimized (by the caller knowing), we just serialize.
        # But currently ReplayManager calls capture() without args.

        # Wait, `ReplayManager.update` calls `SnapshotService.capture(self.game)`.
        # It does NOT pass `optimized`.
        # So we receive a FULL snapshot.
        # We should strip it here? No, the user asked to PUSH logic into SnapshotService.
        # This means ReplayManager should call `capture(optimized=True)`.

        if snapshot:
            serialized = SnapshotService.serialize(snapshot)
            # If we received a full snapshot but want optimized, we could strip here,
            # BUT the goal is performance, so we should have captured it optimized in the first place.
            # See ReplayManager.update below.

            # Legacy strip logic removal (handled by upstream capture)
            self.data.snapshots[str(tick)] = serialized

        self.data.duration_frames += 1


class GhostPlayer(Player):
    """A player entity that doesn't spawn effects but simulates movement."""

    def __init__(self, game, pos, size, id, skin_idx=0):
        # Initialize base Player but suppress heavy init if needed
        # We need it to behave exactly like Player for physics
        # lives=1, respawn_pos=pos provided to satisfy Player.__init__ signature
        super().__init__(game, pos, size, id, lives=1, respawn_pos=list(pos))
        self.skin = skin_idx
        # Persistent input state flags
        self.input_left = False
        self.input_right = False

    def update_inputs(self, inputs: List[str]):
        for inp in inputs:
            if inp == "left":
                self.input_left = True
            if inp == "stop_left":
                self.input_left = False
            if inp == "right":
                self.input_right = True
            if inp == "stop_right":
                self.input_right = False

    def render(self, surf, offset=(0, 0)):
        # Ghost specific render override handled by wrapper
        super().render(surf, offset)


class ReplayGhost:
    """Renders a ghost by re-simulating inputs."""

    _TINT_COLOR = (100, 220, 255, 180)

    def __init__(self, game_instance, data: ReplayData):
        self.game = game_instance
        self.data = data
        self.tick = 0

        start_pos = (0, 0)
        start_snap = self.data.snapshots.get("0")
        if start_snap:
            snap = SnapshotService.deserialize(start_snap)
            if snap.players:
                start_pos = snap.players[0].pos

        try:
            from scripts.collectableManager import CollectableManager as CM

            skin_idx = CM.SKIN_PATHS.index(data.skin)
        except ValueError:
            skin_idx = 0

        self.entity = GhostPlayer(self.game, start_pos, (8, 15), 999, skin_idx)
        self.input_map = {entry["tick"]: entry["inputs"] for entry in self.data.inputs}
        self._tint_cache: Dict[tuple, pygame.Surface] = {}

    def step_and_render(self, surface: pygame.Surface, offset: tuple[int, int]):
        if self.tick >= self.data.duration_frames:
            return

        # print(f"[DEBUG] Ghost Tick {self.tick} Pos {self.entity.pos}")

        # 1. Apply Snapshot Correction (Sync)
        if str(self.tick) in self.data.snapshots:
            snap_data = self.data.snapshots[str(self.tick)]
            snap = SnapshotService.deserialize(snap_data)
            if snap.players:
                p_snap = snap.players[0]
                self.entity.pos = list(p_snap.pos)
                self.entity.velocity = list(p_snap.velocity)
                self.entity.flip = p_snap.flip
                self.entity.set_action(p_snap.action)
                self.entity.lives = p_snap.lives
                self.entity.air_time = p_snap.air_time
                self.entity.jumps = p_snap.jumps
                self.entity.wall_slide = p_snap.wall_slide
                self.entity.dashing = p_snap.dashing

        # 2. Apply Inputs (Persistent State)
        inputs = self.input_map.get(self.tick, [])
        self.entity.update_inputs(inputs)

        # Map persistent state to frame movement
        movement = [self.entity.input_left, self.entity.input_right]

        # Triggers are instant
        jump = False
        dash = False
        for inp in inputs:
            if inp == "jump":
                jump = True
            if inp == "dash":
                dash = True

        if jump:
            self.entity.jump()
        if dash:
            self.entity.dash()

        # 3. Run Physics Update
        frame_movement = (movement[1] - movement[0], 0)
        self.entity.update(self.game.tilemap, frame_movement)

        # 4. Render
        self._render_tinted(surface, offset)

        self.tick += 1

    def _render_tinted(self, surface: pygame.Surface, offset: tuple[int, int]):
        if not self.entity.animation:
            return

        base_img = self.entity.animation.img()
        if not base_img:
            return

        anim_key = (self.entity.action, int(self.entity.animation.frame), self.entity.flip)

        tinted = self._tint_cache.get(anim_key)
        if not tinted:
            tinted = base_img.copy()
            if self.entity.flip:
                tinted = pygame.transform.flip(tinted, True, False)

            tint_surf = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
            tint_surf.fill(self._TINT_COLOR)
            tinted.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            tinted.set_alpha(self._TINT_COLOR[3])

            self._tint_cache[anim_key] = tinted

        surface.blit(
            tinted,
            (
                self.entity.pos[0] - offset[0] + self.entity.anim_offset[0],
                self.entity.pos[1] - offset[1] + self.entity.anim_offset[1],
            ),
        )

    def reset(self):
        self.tick = 0


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
        seed = 0
        try:
            pass

            # Capture seed if possible
        except Exception:
            pass

        skin = self._get_skin(player)

        if self._ghosts_enabled():
            self.recording = ReplayRecording(level_str, skin, seed)
            self.tick_counter = 0

            self.best_data = self._load(level_str, "best")
            self.last_data = self._load(level_str, "last")

            source = None
            mode = getattr(global_settings, "ghost_mode", "best")

            # Prioritize based on mode
            if mode == "best":
                if self.best_data and self.best_data.level == level_str:
                    source = self.best_data
                elif self.last_data and self.last_data.level == level_str:
                    source = self.last_data
            else:  # mode == "last"
                if self.last_data and self.last_data.level == level_str:
                    source = self.last_data
                elif self.best_data and self.best_data.level == level_str:
                    source = self.best_data

            if source:
                self.ghost = ReplayGhost(self.game, source)
                self.ghost.reset()

    def update(self, player: Any, inputs: List[str]):
        """Called every frame to capture state."""
        if not self.recording:
            return
        if getattr(self.game, "dead", 0):
            return

        # Snapshot every 10 frames (approx 6 times/sec at 60fps)
        # Good balance between smoothness (catching drift early) and performance
        snap = None
        if self.tick_counter % 10 == 0:
            try:
                # Pushed filtering into capture service for performance
                snap = SnapshotService.capture(self.game, optimized=True)
            except Exception:
                pass

        self.recording.capture_frame(self.tick_counter, player, inputs, snap, optimized=True)
        self.tick_counter += 1

    def commit_run(self, new_best: bool):
        if not self.recording or self.recording.data.duration_frames < 10:
            return
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
        if not path.exists():
            return None
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
        except Exception:
            return "default"


__all__ = ["ReplayManager", "ReplayRecording", "ReplayGhost", "ReplayData", "FrameSample"]
