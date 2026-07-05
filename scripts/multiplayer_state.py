"""Multiplayer Game State (MP-07/MP-08).

Client-side state for multiplayer gameplay. Connects to a dedicated server,
sends inputs, receives snapshots, and renders the full game world:

- Local player: client-side prediction with rewind+replay reconciliation.
  Every authoritative snapshot rewinds the local player to server state and
  re-applies all inputs the server has not acknowledged yet.
- Remote players & enemies: interpolated on a smooth per-frame clock that
  trails the server by INTERP_DELAY ticks (snapshots arrive at ~20 Hz, the
  interpolation clock advances at 60 Hz for fluid motion).
- Projectiles: authoritative from snapshots, extrapolated linearly between
  snapshots.
- Collectables: removed by stable ID as the server reports pickups; own
  coins/ammo are mirrored into the HUD (never persisted).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame

from scripts.constants import DASH_MIN_ACTIVE_ABS
from scripts.entities import Enemy, Player
from scripts.network.interpolation import SnapshotBuffer, interpolate_entity
from scripts.snapshot import EntitySnapshot, SimulationSnapshot
from scripts.state_manager import State

# Tuning constants
INTERP_DELAY = 4  # Minimum ticks the remote-entity clock trails the newest snapshot (~67ms)
INTERP_DELAY_MAX = 24  # Adaptive ceiling under jitter/burst delivery (~400ms)
INTERP_HARD_SNAP = 40  # Snap the interp clock if it drifts further than this
INTERP_HEADROOM_MARGIN = 2.5  # Spare buffered ticks required before shrinking the delay
INTERP_SHRINK_WINDOW = 300  # Frames of sustained headroom before shrinking (~5s)


def _autopilot_input(pattern: str, frame: int) -> Tuple[Tuple[bool, bool], List[str]]:
    """Scripted inputs for automated E2E runs (NINJA_MP_AUTOPILOT)."""
    actions: List[str] = []
    if pattern == "runner":
        phase = (frame // 120) % 2
        move = (False, True) if phase == 0 else (True, False)
        if frame % 90 == 45:
            actions.append("jump")
        if frame % 200 == 100:
            actions.append("dash")
    elif pattern == "shooter":
        move = (False, False)
        if frame % 120 == 60:
            actions.append("jump")
        if frame % 45 == 10:
            actions.append("shoot")
    else:
        move = (False, False)
    return move, actions


class MPPlayer(Player):
    """Player entity for multiplayer rendering.

    Always renders the gun overlay (all players carry guns in multiplayer)
    without depending on the local user's persisted weapon selection.
    """

    def render(self, surf, offset=(0, 0)):
        if abs(self.dashing) <= DASH_MIN_ACTIVE_ABS:
            # Skip Player.render (it checks local settings); use base sprite.
            from scripts.entities import PhysicsEntity

            PhysicsEntity.render(self, surf, offset=offset)
        gun_img = self.game.assets["gun"]
        if self.flip:
            surf.blit(
                pygame.transform.flip(gun_img, True, False),
                (
                    self.rect().centerx - 4 - gun_img.get_width() - offset[0],
                    self.rect().centery - offset[1],
                ),
            )
        else:
            surf.blit(
                gun_img,
                (self.rect().centerx + 4 - offset[0], self.rect().centery - offset[1]),
            )


class _SilentAudio:
    """No-op audio used while replaying inputs during reconciliation."""

    def play(self, *args: Any, **kwargs: Any) -> None:
        pass

    def trigger_ducking(self, **kwargs: Any) -> None:
        pass


class MultiplayerGameState(State):
    """State subclass for multiplayer client experience."""

    name = "MultiplayerGameState"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7777,
        player_name: str = "Player",
        host_process: Any = None,
        host_ip: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._player_name = player_name
        # When we host, we own the dedicated server subprocess.
        self._host_process = host_process
        self._host_ip = host_ip
        self._game: Any = None
        self._client: Any = None
        self._my_player_id: int | None = None
        self._movement = [False, False]  # [left, right]
        self._action_buffer: List[str] = []
        self._connected = False
        self._level_loaded = False
        self._disconnected = False
        self._disconnect_reason = ""
        self.request_pause = False

        # Remote entity interpolation buffers (keyed by entity id)
        self._remote_player_buffers: Dict[int, SnapshotBuffer] = {}
        self._enemy_buffers: Dict[int, SnapshotBuffer] = {}
        self._enemy_entities: Dict[int, Enemy] = {}

        # Smooth interpolation clock for remote entities (fractional ticks).
        # The delay it trails by adapts to measured delivery quality
        # (jitter/bursts on Wi-Fi), AIMD-style: grow fast on starvation,
        # shrink slowly after sustained smooth delivery.
        self._interp_tick = 0.0
        self._interp_delay = float(INTERP_DELAY)
        self._headroom_min = float("inf")
        self._headroom_frames = 0

        # Snapshot bookkeeping
        self._last_applied_tick = -1
        self._known_projectile_ids: set[int] = set()
        self._removed_collectables: set[int] = set()
        self._collectable_registry: List[Tuple[int, str, Any]] = []

        # Perf/diagnostics counters (rendered in HUD, dumped by E2E harness)
        self._stats = {
            "snapshots_applied": 0,
            "reconcile_error_px": 0.0,
            "reconcile_max_px": 0.0,
            "replayed_ticks": 0,
            # Remote-view smoothness (the "laggy picture" symptom)
            "interp_underruns": 0,  # frames where the interp clock passed the newest snapshot
            "remote_frozen_frames": 0,  # remote player rendered motionless while it should move
            "remote_jump_frames": 0,  # remote player teleported > 5px between frames
            "remote_jump_max_px": 0.0,
        }
        self._remote_prev_pos: Dict[int, Tuple[float, float]] = {}
        self._frame_times: List[float] = []
        self._last_frame_t = 0.0

        # E2E hooks: scripted inputs + per-second metrics logging
        self._autopilot = os.environ.get("NINJA_MP_AUTOPILOT", "")
        self._metrics_path = os.environ.get("NINJA_MP_METRICS", "")
        self._metrics_fh: Any = None
        self._frame = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self, previous: State | None) -> None:
        from game import Game

        from scripts.network.game_client import GameClient

        # Create full rendering game instance. Game.__init__ loads the
        # locally selected level; _setup_level reloads to the server's level
        # once connected.
        self._game = Game(fullscreen=False)
        self._game.transition = 0
        self._game.players = []
        self._game.enemies = []

        # Create network client
        self._client = GameClient(
            server_host=self._host,
            server_port=self._port,
            player_name=self._player_name,
        )

        self._client.on_connected(self._on_connected)
        self._client.on_disconnected(self._on_disconnected)
        self._client.on_player_left(self._on_player_left)

        self._client.connect()

    def on_exit(self, next_state: State | None) -> None:
        if self._client:
            if self._client.is_connected:
                self._client.disconnect()
            self._client.close()
        if self._metrics_fh is not None:
            self._metrics_fh.close()
            self._metrics_fh = None
        self._stop_host_process()

    def _stop_host_process(self) -> None:
        if self._host_process is not None:
            try:
                self._host_process.terminate()
                self._host_process.wait(timeout=3)
            except Exception:
                try:
                    self._host_process.kill()
                except Exception:
                    pass
            self._host_process = None

    # ------------------------------------------------------------------
    # Network callbacks
    # ------------------------------------------------------------------

    def _on_connected(self, player_id: int) -> None:
        self._my_player_id = player_id
        self._connected = True

    def _on_disconnected(self, reason: str) -> None:
        self._disconnected = True
        self._disconnect_reason = reason

    def _on_player_left(self, player_id: int, reason: str) -> None:
        self._remote_player_buffers.pop(player_id, None)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def handle(self, events: Sequence[pygame.event.Event]) -> None:
        """Track movement key presses/releases."""
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_LEFT, pygame.K_a):
                    self._movement[0] = True
                elif e.key in (pygame.K_RIGHT, pygame.K_d):
                    self._movement[1] = True
            elif e.type == pygame.KEYUP:
                if e.key in (pygame.K_LEFT, pygame.K_a):
                    self._movement[0] = False
                elif e.key in (pygame.K_RIGHT, pygame.K_d):
                    self._movement[1] = False

    def handle_actions(self, actions: Sequence[str]) -> None:
        """Capture actions from InputRouter."""
        self.request_pause = False
        for act in actions:
            if act == "pause_toggle":
                self.request_pause = True
            elif act == "left":
                self._movement[0] = True
            elif act == "stop_left":
                self._movement[0] = False
            elif act == "right":
                self._movement[1] = True
            elif act == "stop_right":
                self._movement[1] = False
            elif act in ("jump", "dash", "shoot"):
                self._action_buffer.append(act)

    # ------------------------------------------------------------------
    # Level setup (deferred until the server tells us its level)
    # ------------------------------------------------------------------

    def _setup_level(self) -> None:
        g = self._game
        level = self._client.level
        g.level = level
        g.load_level(level)
        g.transition = 0
        g.players = []
        g.enemies = []
        self._enemy_entities = {}
        # Build the collectable registry with the same stable IDs the server
        # derives (extraction order: coins first, then ammo pickups)
        self._collectable_registry = []
        cid = 0
        for coin in g.cm.coin_list:
            self._collectable_registry.append((cid, "coin", coin))
            cid += 1
        for ammo in getattr(g.cm, "ammo_pickups", []):
            self._collectable_registry.append((cid, "ammo", ammo))
            cid += 1
        self._removed_collectables = set()
        self._level_loaded = True

    # ------------------------------------------------------------------
    # Frame update
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        if not self._client:
            return

        # 1. Network: receive messages, advance local tick
        self._client.update()

        if self._disconnected:
            self._return_to_menu()
            return

        if not self._connected:
            self._action_buffer = []
            return

        if not self._level_loaded:
            self._setup_level()

        g = self._game
        self._frame += 1

        # Real frame interval (includes render + flip of the previous frame)
        if self._metrics_path:
            now = time.perf_counter()
            if self._last_frame_t:
                self._frame_times.append((now - self._last_frame_t) * 1000.0)
            self._last_frame_t = now

        # E2E: scripted inputs replace user input when autopilot is active
        if self._autopilot:
            auto_move, auto_actions = _autopilot_input(self._autopilot, self._frame)
            self._movement = list(auto_move)
            self._action_buffer.extend(auto_actions)

        # 2. Apply the newest authoritative snapshot (rewind + replay)
        self._apply_snapshot()

        # 3. Gather and send this frame's input
        actions = self._action_buffer
        self._action_buffer = []
        move = (self._movement[0], self._movement[1])
        self._client.send_input_state(move, actions)

        # 4. Predict local player for this frame
        self._predict_local(move, actions)

        # 5. Advance remote entities on the smooth interpolation clock
        self._interp_tick += 1.0
        self._sync_interp_clock()
        self._update_remote_entities()

        # 6. Extrapolate projectiles between snapshots
        self._extrapolate_projectiles()

        # 7. Cosmetic updates
        if hasattr(g, "clouds"):
            g.clouds.update()
        if hasattr(g, "particle_system"):
            g.particle_system.update()
        g.screenshake = max(0, g.screenshake - 1)
        g.dead = 0  # global death fade is meaningless in multiplayer
        for _, _, obj in self._collectable_registry:
            obj.animation.update()

        # Remote entity animations (local player animates in player.update)
        for player in g.players:
            if self._my_player_id is not None and player.id == self._my_player_id:
                continue
            if getattr(player, "animation", None):
                player.animation.update()
        for enemy in self._enemy_entities.values():
            if getattr(enemy, "animation", None):
                enemy.animation.update()

        # 8. Camera follows local player
        if getattr(g, "player", None) and g.players:
            g.scroll[0] += (g.player.rect().centerx - g.display.get_width() / 2 - g.scroll[0]) / 30
            g.scroll[1] += (g.player.rect().centery - g.display.get_height() / 2 - g.scroll[1]) / 30

        g.clock.tick()
        self._write_metrics()

    def _write_metrics(self) -> None:
        """Append one JSONL metrics sample per second (NINJA_MP_METRICS)."""
        if not self._metrics_path or self._frame % 60 != 0:
            return
        if self._metrics_fh is None:
            self._metrics_fh = open(self._metrics_path, "a")
        g = self._game
        frame_ms = sorted(self._frame_times)
        self._frame_times = []
        sample = {
            "t": time.time(),
            "frame": self._frame,
            "fps": round(g.clock.get_fps(), 2),
            "rtt_ms": round(self._client.rtt * 1000, 2),
            "server_tick": self._client.server_tick,
            "local_tick": self._client.local_tick,
            "ack_lag": self._client.local_tick - self._client.input_ack_tick,
            "snapshots_applied": self._stats["snapshots_applied"],
            "reconcile_error_px": round(self._stats["reconcile_error_px"], 3),
            "reconcile_max_px": round(self._stats["reconcile_max_px"], 3),
            "replayed_ticks": self._stats["replayed_ticks"],
            "players": len(g.players),
            "enemies": len(g.enemies),
            "projectiles": len(getattr(g, "projectiles", [])),
            # Remote-view smoothness (cumulative counters)
            "interp_underruns": self._stats["interp_underruns"],
            "remote_frozen_frames": self._stats["remote_frozen_frames"],
            "remote_jump_frames": self._stats["remote_jump_frames"],
            "remote_jump_max_px": round(self._stats["remote_jump_max_px"], 2),
            "interp_delay": self._current_interp_delay(),
            # Real frame intervals for this window (render + flip included)
            "frame_ms_p50": round(frame_ms[len(frame_ms) // 2], 2) if frame_ms else 0,
            "frame_ms_p95": round(frame_ms[int(len(frame_ms) * 0.95)], 2) if frame_ms else 0,
            "frame_ms_max": round(frame_ms[-1], 2) if frame_ms else 0,
            # Network arrival health (cumulative counters)
            **{f"net_{k}": v for k, v in self._client.net_stats.items()},
        }
        self._metrics_fh.write(json.dumps(sample) + "\n")
        self._metrics_fh.flush()

    def _current_interp_delay(self) -> float:
        """Interpolation delay in ticks the remote view currently trails by."""
        return round(self._interp_delay, 2)

    def network_idle_update(self) -> None:
        """Keep the connection alive while an overlay (pause) is on top.

        Also sends a neutral input state: movement is last-writer-wins on the
        server, so without this a player who paused while holding a key would
        keep running server-side until they resume.
        """
        if self._client and not self._disconnected:
            self._client.update()
            if self._client.is_connected:
                self._movement = [False, False]
                self._client.send_input_state((False, False), [])

    def _return_to_menu(self) -> None:
        if self.manager:
            from scripts.state_manager import MenuState

            self.manager.set(MenuState())

    # ------------------------------------------------------------------
    # Local player prediction
    # ------------------------------------------------------------------

    def _predict_local(self, move: Tuple[bool, bool], actions: List[str]) -> None:
        g = self._game
        player = self._find_local_player()
        if player is None or not getattr(g, "tilemap", None):
            return

        for action in actions:
            if action == "jump":
                player.jump()
            elif action == "dash":
                player.dash()
            elif action == "shoot":
                # Server spawns the projectile; play feedback locally
                if getattr(player, "mp_ammo", 1) > 0 and player.shoot_cooldown == 0:
                    g.audio.play("shoot")

        movement = (int(move[1]) - int(move[0]), 0)
        player.update(g.tilemap, movement)

    def _find_local_player(self) -> Any:
        if self._my_player_id is None:
            return None
        for p in self._game.players:
            if p.id == self._my_player_id:
                return p
        return None

    # ------------------------------------------------------------------
    # Snapshot application
    # ------------------------------------------------------------------

    def _apply_snapshot(self) -> None:
        new_snaps: List[SimulationSnapshot] = self._client.drain_new_snapshots()
        if not new_snaps:
            return

        # Feed EVERY received snapshot into the interpolation buffers.
        # Under bursty delivery (Wi-Fi aggregation/power-save) several
        # snapshots arrive in one frame; buffering only the newest would
        # halve the effective sample rate exactly when jitter is worst.
        newest: Optional[SimulationSnapshot] = None
        for snap in new_snaps:
            if newest is None or snap.tick > newest.tick:
                newest = snap
        for snap in new_snaps:
            if snap is newest:
                continue  # buffered below via the full apply path
            for p_snap in snap.players:
                if p_snap.id != self._my_player_id:
                    self._buffer_remote_player(p_snap, snap.tick)
            for e_snap in snap.enemies:
                if e_snap.id in self._enemy_buffers:
                    self._enemy_buffers[e_snap.id].push(snap.tick, e_snap)

        snapshot = newest
        if snapshot is None or snapshot.tick <= self._last_applied_tick:
            return
        self._last_applied_tick = snapshot.tick
        self._stats["snapshots_applied"] += 1

        g = self._game
        server_tick = snapshot.tick

        # --- Players ---
        existing: Dict[int, Any] = {p.id: p for p in g.players}
        new_players: List[Any] = []
        for p_snap in snapshot.players:
            player = existing.get(p_snap.id)
            if player is None:
                player = MPPlayer(
                    g,
                    list(p_snap.pos),
                    (8, 15),
                    p_snap.id,
                    lives=p_snap.lives,
                    respawn_pos=list(p_snap.pos),
                )
                player.skin = 0
                player.mp_coins = 0
                player.mp_ammo = 0
            if p_snap.id == self._my_player_id:
                self._reconcile_local_player(player, p_snap)
            else:
                self._buffer_remote_player(p_snap, server_tick)
            player.mp_coins = p_snap.coins
            player.mp_ammo = p_snap.ammo
            new_players.append(player)
        g.players = new_players

        # Bind local player reference (camera, HUD)
        local = self._find_local_player()
        if local is not None:
            g.player = local
            # Mirror own score into the HUD (display only, never saved)
            g.cm.coins = local.mp_coins
            g.cm.ammo = local.mp_ammo

        # --- Enemies ---
        self._apply_enemy_snapshots(snapshot.enemies, server_tick)

        # --- Projectiles ---
        self._apply_projectile_snapshots(snapshot.projectiles)

        # --- Collectables ---
        self._apply_collected(snapshot.collected)

        g.tick = snapshot.tick

    # --- Local player reconciliation (rewind + replay) ---

    def _reconcile_local_player(self, player: Any, p_snap: EntitySnapshot) -> None:
        g = self._game
        predicted = list(player.pos)

        # Rewind to authoritative state
        self._snap_player_to_state(player, p_snap)

        # Replay inputs the server has not applied yet
        unacked = self._client.get_unacknowledged_inputs()
        if unacked and getattr(g, "tilemap", None):
            real_audio = g.audio
            real_particles = g.particles
            real_sparks = g.sparks
            g.audio = _SilentAudio()
            g.particles = []
            g.sparks = []
            try:
                for tick in sorted(unacked.keys()):
                    move, actions = unacked[tick]
                    for act in actions:
                        if act == "jump":
                            player.jump()
                        elif act == "dash":
                            player.dash()
                    movement = (int(move[1]) - int(move[0]), 0)
                    player.update(g.tilemap, movement)
                    self._stats["replayed_ticks"] += 1
            finally:
                g.audio = real_audio
                g.particles = real_particles
                g.sparks = real_sparks

        # Diagnostics: how far prediction was off
        err = max(abs(player.pos[0] - predicted[0]), abs(player.pos[1] - predicted[1]))
        self._stats["reconcile_error_px"] = err
        self._stats["reconcile_max_px"] = max(self._stats["reconcile_max_px"], err)

    def _snap_player_to_state(self, player: Any, p_snap: EntitySnapshot) -> None:
        player.pos = list(p_snap.pos)
        player.velocity = list(p_snap.velocity)
        player.flip = p_snap.flip
        player.air_time = p_snap.air_time
        player.jumps = p_snap.jumps
        player.wall_slide = p_snap.wall_slide
        player.dashing = p_snap.dashing
        player.shoot_cooldown = p_snap.shoot_cooldown
        player.lives = p_snap.lives
        if player.action != p_snap.action:
            player.set_action(p_snap.action)

    # --- Remote players ---

    def _buffer_remote_player(self, p_snap: EntitySnapshot, server_tick: int) -> None:
        if p_snap.id not in self._remote_player_buffers:
            self._remote_player_buffers[p_snap.id] = SnapshotBuffer(max_size=20)
        self._remote_player_buffers[p_snap.id].push(server_tick, p_snap)

    def _sync_interp_clock(self) -> None:
        """Keep the interpolation clock trailing the newest snapshot.

        The trailing delay is an adaptive jitter buffer: when the clock
        starves (catches up with the newest snapshot, so remote entities
        would freeze and then jump) the delay grows immediately; after a
        sustained window of comfortable headroom it shrinks again. The
        clock itself is slewed proportionally (max ~±12% playback speed)
        so corrections stay invisible instead of stepping.
        """
        newest = self._client.server_tick
        headroom = newest - self._interp_tick

        # Grow fast on starvation (a freeze is imminent or already visible):
        # cover the observed deficit in one step instead of creeping up,
        # so one bad burst is enough to size the buffer for the next one.
        if headroom < 0.5 and self._interp_delay < INTERP_DELAY_MAX:
            grow = max(1.0, 0.5 - headroom)
            self._interp_delay = min(self._interp_delay + grow, INTERP_DELAY_MAX)
            self._headroom_min = float("inf")
            self._headroom_frames = 0

        # Shrink slowly once delivery has been smooth for a sustained window
        self._headroom_min = min(self._headroom_min, headroom)
        self._headroom_frames += 1
        if self._headroom_frames >= INTERP_SHRINK_WINDOW:
            if self._headroom_min > INTERP_HEADROOM_MARGIN and self._interp_delay > INTERP_DELAY:
                self._interp_delay = max(INTERP_DELAY, self._interp_delay - 0.5)
            self._headroom_min = float("inf")
            self._headroom_frames = 0

        target = newest - self._interp_delay
        drift = self._interp_tick - target
        if abs(drift) > INTERP_HARD_SNAP:
            self._interp_tick = float(target)
        else:
            self._interp_tick += max(-0.12, min(0.12, -drift * 0.05))

    def _update_remote_entities(self) -> None:
        g = self._game
        for player in g.players:
            if self._my_player_id is not None and player.id == self._my_player_id:
                continue
            buffer = self._remote_player_buffers.get(player.id)
            if buffer:
                self._interpolate_onto(player, buffer)
                self._track_remote_motion(player, buffer)

        for enemy_id, enemy in self._enemy_entities.items():
            buffer = self._enemy_buffers.get(enemy_id)
            if buffer:
                self._interpolate_onto(enemy, buffer)

    def _track_remote_motion(self, player: Any, buffer: SnapshotBuffer) -> None:
        """Measure rendered smoothness of a remote player (metrics only)."""
        prev = self._remote_prev_pos.get(player.id)
        self._remote_prev_pos[player.id] = (player.pos[0], player.pos[1])
        if prev is None or not buffer.buffer:
            return
        d = max(abs(player.pos[0] - prev[0]), abs(player.pos[1] - prev[1]))
        _, newest = buffer.buffer[-1]
        should_move = max(abs(newest.velocity[0]), abs(newest.velocity[1])) > 0.3
        if d < 0.01 and should_move:
            self._stats["remote_frozen_frames"] += 1
        elif d > 5.0:
            self._stats["remote_jump_frames"] += 1
            self._stats["remote_jump_max_px"] = max(self._stats["remote_jump_max_px"], d)

    def _interpolate_onto(self, entity: Any, buffer: SnapshotBuffer) -> None:
        prev_snap, next_snap, t = buffer.get_surrounding_snapshots(self._interp_tick)
        if prev_snap is not None and next_snap is None and len(buffer.buffer) >= 2:
            # Interp clock ran past the newest snapshot: entity freezes
            self._stats["interp_underruns"] += 1
        if prev_snap is not None and next_snap is not None:
            _, prev_state = prev_snap
            _, next_state = next_snap
            interp = interpolate_entity(prev_state, next_state, t)
            entity.pos = list(interp.pos)
            entity.velocity = list(interp.velocity)
            entity.flip = interp.flip
            if entity.action != interp.action:
                entity.set_action(interp.action)
        elif prev_snap is not None:
            newest_tick, state = prev_snap
            entity.pos = list(state.pos)
            entity.velocity = list(state.velocity)
            entity.flip = state.flip
            if entity.action != state.action:
                entity.set_action(state.action)
            # Brief starvation: dead-reckon a few ticks past the newest
            # snapshot instead of freezing. Per-tick motion is derived from
            # the last two samples because movement-driven entities carry
            # their speed in position deltas, not in `velocity`.
            if len(buffer.buffer) >= 2:
                prev_tick, prev_state = buffer.buffer[-2]
                span = newest_tick - prev_tick
                ahead = min(self._interp_tick - newest_tick, 4.0)
                if span > 0 and ahead > 0:
                    entity.pos[0] += (state.pos[0] - prev_state.pos[0]) / span * ahead
                    entity.pos[1] += (state.pos[1] - prev_state.pos[1]) / span * ahead

    # --- Enemies ---

    def _apply_enemy_snapshots(self, enemy_snaps: List[EntitySnapshot], server_tick: int) -> None:
        g = self._game
        seen: set[int] = set()
        for e_snap in enemy_snaps:
            seen.add(e_snap.id)
            enemy = self._enemy_entities.get(e_snap.id)
            if enemy is None:
                enemy = Enemy(g, list(e_snap.pos), (8, 15), e_snap.id)
                self._enemy_entities[e_snap.id] = enemy
                self._enemy_buffers[e_snap.id] = SnapshotBuffer(max_size=20)
            self._enemy_buffers[e_snap.id].push(server_tick, e_snap)
            enemy.walking = e_snap.walking

        # Remove enemies the server no longer reports (killed)
        for enemy_id in list(self._enemy_entities.keys()):
            if enemy_id not in seen:
                enemy = self._enemy_entities.pop(enemy_id)
                self._enemy_buffers.pop(enemy_id, None)
                from scripts.effects_util import spawn_hit_sparks

                spawn_hit_sparks(g, enemy.rect().center)
                g.audio.play("hit")

        g.enemies = list(self._enemy_entities.values())

    # --- Projectiles ---

    def _apply_projectile_snapshots(self, proj_snaps: List[Any]) -> None:
        g = self._game
        if not hasattr(g, "projectiles") or not hasattr(g.projectiles, "_projectiles"):
            return
        new_ids = set()
        rebuilt = []
        for p in proj_snaps:
            new_ids.add(p.id)
            rebuilt.append(
                {
                    "id": p.id,
                    "pos": list(p.pos),
                    "vel": [p.velocity, 0.0],
                    "age": p.timer,
                    "owner": p.owner,
                    "owner_id": p.owner_id,
                }
            )
            # Shot feedback for projectiles we did not fire ourselves
            if p.id not in self._known_projectile_ids and p.owner_id != self._my_player_id:
                g.audio.play("shoot")
        g.projectiles._projectiles = rebuilt
        self._known_projectile_ids = new_ids

    def _extrapolate_projectiles(self) -> None:
        g = self._game
        if not hasattr(g, "projectiles") or not hasattr(g.projectiles, "_projectiles"):
            return
        for proj in g.projectiles._projectiles:
            proj["pos"][0] += proj["vel"][0]

    # --- Collectables ---

    def _apply_collected(self, collected: List[int]) -> None:
        g = self._game
        newly = set(collected) - self._removed_collectables
        if not newly:
            return
        for cid, kind, obj in self._collectable_registry:
            if cid in newly:
                if kind == "coin" and obj in g.cm.coin_list:
                    g.cm.coin_list.remove(obj)
                elif kind == "ammo" and obj in getattr(g.cm, "ammo_pickups", []):
                    g.cm.ammo_pickups.remove(obj)
                g.audio.play("collect")
        self._removed_collectables.update(newly)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface) -> None:
        if not self._game:
            return

        g = self._game

        from scripts.renderer import Renderer

        if not hasattr(self, "_renderer"):
            self._renderer = Renderer(show_perf=False)
        self._renderer.render(g, surface)

        self._render_mp_hud(surface)

    def _render_mp_hud(self, surface: pygame.Surface) -> None:
        """Render minimal multiplayer HUD info (game font + outline)."""
        from scripts.ui import UI

        if self._connected and self._client:
            status = (
                f"Players: {len(self._game.players)} | RTT: {self._client.rtt * 1000:.0f}ms"
                f" | FPS: {self._game.clock.get_fps():.0f}"
            )
        elif self._disconnected:
            status = f"Disconnected: {self._disconnect_reason}"
        else:
            status = "Connecting..."

        label = self._player_name
        if self._host_ip:
            label += f" | Hosting on {self._host_ip}:{self._port}"

        font = UI.get_font(14)
        UI.draw_text_with_outline(
            surface=surface,
            font=font,
            text=label,
            x=10,
            y=surface.get_height() - 50,
        )
        UI.draw_text_with_outline(
            surface=surface,
            font=font,
            text=status,
            x=10,
            y=surface.get_height() - 30,
        )


__all__ = ["MultiplayerGameState", "MPPlayer"]
