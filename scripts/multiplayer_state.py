"""Multiplayer Game State (MP-07).

Client-side state for multiplayer gameplay. Connects to a dedicated server,
sends inputs, receives snapshots, and renders the game world with all
remote players visible.

Features:
- Client-side prediction: local player responds immediately to inputs
- Remote player interpolation: smooth movement between server snapshots
- Server reconciliation: corrects prediction errors when divergence detected
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import pygame

from scripts.network.interpolation import SnapshotBuffer, interpolate_entity
from scripts.snapshot import EntitySnapshot
from scripts.state_manager import State

# Tuning constants
INTERP_DELAY = 3  # Ticks behind server for remote interpolation
RECONCILE_THRESHOLD = 5.0  # Pixels divergence before snap to server


class MultiplayerGameState(State):
    """State subclass for multiplayer client experience."""

    name = "MultiplayerGameState"

    def __init__(self, host: str = "127.0.0.1", port: int = 7777, player_name: str = "Player") -> None:
        self._host = host
        self._port = port
        self._player_name = player_name
        self._game: Any = None
        self._client: Any = None
        self._my_player_id: int | None = None
        self._movement = [False, False]  # [left, right]
        self._action_buffer: List[str] = []
        self._connected = False
        self._disconnected = False
        self._disconnect_reason = ""
        self.request_pause = False
        # Remote player interpolation buffers (keyed by player_id)
        self._remote_player_buffers: Dict[int, SnapshotBuffer] = {}
        # Track last processed server tick for reconciliation
        self._last_server_tick = 0

    def on_enter(self, previous: State | None) -> None:
        from game import Game

        from scripts.network.game_client import GameClient

        # Create full rendering game instance
        self._game = Game(fullscreen=False)
        self._game.load_level(0)
        # Skip the fade-in transition (TRANSITION_START = -30 would stay
        # black forever since MultiplayerGameState doesn't tick it).
        self._game.transition = 0

        # Clear auto-spawned players — server is authoritative
        self._game.players = []

        # Create network client
        self._client = GameClient(
            server_host=self._host,
            server_port=self._port,
            player_name=self._player_name,
        )

        # Register callbacks
        self._client.on_connected(self._on_connected)
        self._client.on_disconnected(self._on_disconnected)
        self._client.on_player_left(self._on_player_left)

        # Initiate connection
        self._client.connect()

    def on_exit(self, next_state: State | None) -> None:
        if self._client:
            if self._client.is_connected:
                self._client.disconnect()
            self._client.close()

    def _on_connected(self, player_id: int) -> None:
        self._my_player_id = player_id
        self._connected = True
        print(f"Connected as player {player_id}")

    def _on_disconnected(self, reason: str) -> None:
        self._disconnected = True
        self._disconnect_reason = reason
        print(f"Disconnected: {reason}")

    def _on_player_left(self, player_id: int, reason: str) -> None:
        # Clean up interpolation buffer for departing player
        self._remote_player_buffers.pop(player_id, None)

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
        self._action_buffer = []
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

    def _apply_local_inputs(self, actions: List[str]) -> None:
        """Apply inputs locally for immediate response (client-side prediction).

        This runs local physics for the local player so movement feels instant
        instead of waiting for the server round-trip.
        """
        g = self._game
        if not g or not hasattr(g, "player") or g.player is None:
            return

        player = g.player

        # Build movement tuple from flags
        movement = (0, 0)
        if self._movement[0] and not self._movement[1]:
            movement = (-1, 0)
        elif self._movement[1] and not self._movement[0]:
            movement = (1, 0)

        # Apply actions
        for action in actions:
            if action == "jump":
                player.jump()
            elif action == "dash":
                player.dash()
            elif action == "shoot":
                player.shoot()

        # Run local physics update
        if hasattr(g, "tilemap") and g.tilemap:
            player.update(g.tilemap, movement)

    def update(self, dt: float) -> None:
        if not self._client:
            return

        # Build input list from movement flags + actions
        inputs: List[str] = []
        if self._movement[0]:
            inputs.append("left")
        if self._movement[1]:
            inputs.append("right")
        inputs.extend(self._action_buffer)
        # Keep a copy of actions for local prediction
        current_actions = list(self._action_buffer)
        self._action_buffer = []

        # Send inputs to server
        if self._client.is_connected and inputs:
            self._client.send_inputs(self._client.local_tick, inputs)

        # Apply inputs locally for immediate response (client-side prediction)
        self._apply_local_inputs(current_actions)

        # Process network messages
        self._client.update()

        # Apply latest snapshot to game entities (with reconciliation)
        self._apply_snapshot()

        # Local cosmetic updates (not authoritative, just visual)
        g = self._game
        if hasattr(g, "clouds"):
            g.clouds.update()
        if hasattr(g, "particle_system"):
            g.particle_system.update()
        g.screenshake = max(0, g.screenshake - 1)

        # Advance player animations locally (server sets action via snapshot,
        # but animation.update() must be ticked to advance frames)
        for player in g.players:
            if hasattr(player, "animation") and player.animation:
                player.animation.update()

        # Update camera to follow local player
        g = self._game
        if hasattr(g, "player") and g.player and g.players:
            g.scroll[0] += (g.player.rect().centerx - g.display.get_width() / 2 - g.scroll[0]) / 30
            g.scroll[1] += (g.player.rect().centery - g.display.get_height() / 2 - g.scroll[1]) / 30

        g.clock.tick()

        # Return to menu if disconnected
        if self._disconnected and self.manager:
            from scripts.state_manager import MenuState

            self.manager.set(MenuState())

    def _apply_snapshot(self) -> None:
        """Apply the latest server snapshot to local game entities.

        Local player: reconciliation (snap if divergence > threshold)
        Remote players: interpolation for smooth movement
        """
        if not self._client:
            return

        snapshot = self._client.get_latest_snapshot()
        if snapshot is None:
            return

        server_tick = snapshot.tick
        self._last_server_tick = server_tick
        g = self._game
        from scripts.entities import Player

        # Build lookup of existing local players by ID
        existing: Dict[int, Any] = {p.id: p for p in g.players}

        # Update or create players from snapshot
        new_players: List[Any] = []
        for p_snap in snapshot.players:
            player = existing.get(p_snap.id)
            if player is None:
                # Create new player entity
                player = Player(
                    g,
                    list(p_snap.pos),
                    (8, 15),
                    p_snap.id,
                    lives=p_snap.lives,
                    respawn_pos=list(p_snap.pos),
                )
                player.skin = 0

            # Split handling: local player vs remote players
            if p_snap.id == self._my_player_id:
                # Local player: reconciliation
                self._reconcile_local_player(player, p_snap, server_tick)
            else:
                # Remote player: interpolation
                self._update_remote_player(player, p_snap, server_tick)

            new_players.append(player)

        g.players = new_players

        # Set local player reference
        if self._my_player_id is not None:
            for p in g.players:
                if p.id == self._my_player_id:
                    g.player = p
                    break

        # Update game tick
        g.tick = snapshot.tick

    def _update_remote_player(self, player: Any, p_snap: EntitySnapshot, server_tick: int) -> None:
        """Update remote player using interpolation for smooth movement."""
        player_id = p_snap.id

        # Get or create buffer for this player
        if player_id not in self._remote_player_buffers:
            self._remote_player_buffers[player_id] = SnapshotBuffer(max_size=20)

        buffer = self._remote_player_buffers[player_id]
        buffer.push(server_tick, p_snap)

        # Calculate render tick (delayed behind server for interpolation)
        render_tick = server_tick - INTERP_DELAY

        # Get surrounding snapshots for interpolation
        prev_snap, next_snap, t = buffer.get_surrounding_snapshots(render_tick)

        if prev_snap is not None and next_snap is not None:
            # Interpolate between two snapshots
            _, prev_state = prev_snap
            _, next_state = next_snap
            interp = interpolate_entity(prev_state, next_state, t)
            player.pos = list(interp.pos)
            player.velocity = list(interp.velocity)
            player.flip = interp.flip
            if player.action != interp.action:
                player.set_action(interp.action)
        elif prev_snap is not None:
            # Only have one snapshot - use it directly (extrapolation case)
            _, state = prev_snap
            player.pos = list(state.pos)
            player.velocity = list(state.velocity)
            player.flip = state.flip
            if player.action != state.action:
                player.set_action(state.action)
        else:
            # No interpolation data - snap to latest
            self._snap_player_to_state(player, p_snap)

        # Always update non-interpolated fields from latest snapshot
        player.lives = p_snap.lives
        player.air_time = p_snap.air_time
        player.jumps = p_snap.jumps
        player.wall_slide = p_snap.wall_slide
        player.dashing = p_snap.dashing
        player.shoot_cooldown = p_snap.shoot_cooldown

    def _snap_player_to_state(self, player: Any, p_snap: EntitySnapshot) -> None:
        """Snap player to exact snapshot state (no interpolation)."""
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

    def _reconcile_local_player(self, player: Any, p_snap: EntitySnapshot, server_tick: int) -> None:
        """Reconcile local player with server state.

        If predicted position diverges too far from server, snap to server state
        and replay unacknowledged inputs.
        """
        # Calculate position divergence
        dx = abs(player.pos[0] - p_snap.pos[0])
        dy = abs(player.pos[1] - p_snap.pos[1])
        divergence = max(dx, dy)

        if divergence > RECONCILE_THRESHOLD:
            # Snap to server state
            self._snap_player_to_state(player, p_snap)
            # Replay unacknowledged inputs for smoother correction
            self._replay_unacknowledged_inputs(player, server_tick)
        else:
            # Minor divergence - update non-position state only
            player.lives = p_snap.lives
            player.air_time = p_snap.air_time
            player.jumps = p_snap.jumps
            player.wall_slide = p_snap.wall_slide
            player.dashing = p_snap.dashing
            player.shoot_cooldown = p_snap.shoot_cooldown
            if player.action != p_snap.action:
                player.set_action(p_snap.action)

    def _replay_unacknowledged_inputs(self, player: Any, server_tick: int) -> None:
        """Replay inputs that server hasn't acknowledged yet.

        After snapping to server state, we re-apply any inputs we sent that
        the server hasn't confirmed yet. This smooths out the correction.
        """
        if not self._client or not self._game:
            return

        g = self._game
        if not hasattr(g, "tilemap") or g.tilemap is None:
            return

        # Get all inputs since the server tick
        unacked = self._client.get_unacknowledged_inputs(server_tick)

        # Replay each set of inputs in tick order
        for tick in sorted(unacked.keys()):
            inputs = unacked[tick]

            # Build movement from inputs
            movement = (0, 0)
            has_left = "left" in inputs
            has_right = "right" in inputs
            if has_left and not has_right:
                movement = (-1, 0)
            elif has_right and not has_left:
                movement = (1, 0)

            # Apply actions (skip shoot during replay to avoid duplicate projectiles)
            for inp in inputs:
                if inp == "jump":
                    player.jump()
                elif inp == "dash":
                    player.dash()

            # Run physics for this tick
            player.update(g.tilemap, movement)

    def render(self, surface: pygame.Surface) -> None:
        if not self._game:
            return

        g = self._game

        # Use the existing Renderer for the full render pipeline
        from scripts.renderer import Renderer

        if not hasattr(self, "_renderer"):
            self._renderer = Renderer(show_perf=False)
        self._renderer.render(g, surface)

        # Draw multiplayer HUD overlay
        self._render_mp_hud(surface)

    def _render_mp_hud(self, surface: pygame.Surface) -> None:
        """Render minimal multiplayer HUD info."""
        font = pygame.font.SysFont(None, 24)

        # Connection status
        if self._connected and self._client:
            status = f"Players: {len(self._game.players)} | RTT: {self._client.rtt * 1000:.0f}ms"
        else:
            status = "Connecting..."

        text_surf = font.render(status, True, (255, 255, 255))
        surface.blit(text_surf, (10, surface.get_height() - 30))

        # Player name
        name_surf = font.render(self._player_name, True, (200, 200, 200))
        surface.blit(name_surf, (10, surface.get_height() - 50))


__all__ = ["MultiplayerGameState"]
