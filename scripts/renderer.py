"""Unified rendering pipeline (Issue 14).

This module centralizes frame composition order so that *all* entry
points (legacy `Game.run` and new `GameState.render`) follow the same
deterministic layering. This is a transitional orchestrator; future
iterations (Issues 15–18) will replace direct asset / effect access
with dedicated systems (AssetManager, ParticleSystem, etc.).

Layer Order (bottom -> top):
1. Clear primary off-screen buffers (game.display)
2. Background image -> display_2
3. World & entities (tiles, player, enemies, projectiles, particles) via UI helper
4. Transition / full-screen visual effects pre-compose (optional)
5. Compose game.display onto display_2
6. HUD / UI overlay (timer, level info, lives, coins, ammo, perf metrics)
7. Screen shake / post effects applied just before blitting to window

Design Notes:
- Keeps all mutation of game surfaces in one place.
- Optional `capture_sequence` parameter records executed high-level steps
  for tests (avoids brittle pixel sampling with live artwork).
- Avoids importing heavy modules at top-level when possible to reduce
  import side-effects during test collection.
"""

from __future__ import annotations

from typing import List, Optional

import pygame

try:  # Local logger (not mandatory for tests)
    from scripts.logger import get_logger  # type: ignore
except Exception:  # pragma: no cover - fallback when logger absent

    def get_logger(name: str):  # type: ignore
        class _Nop:
            def debug(self, *a, **k):
                pass

        return _Nop()


_log = get_logger("renderer")


class Renderer:
    """High-level frame orchestrator.

    Usage:
        r = Renderer(show_perf=True)
        r.render(game, window_surface)
    """

    def __init__(self, show_perf: bool = True) -> None:
        import os
        from scripts.perf_hud import PerformanceHUD  # local import

        log_file = os.environ.get("PERF_LOG_FILE")
        self.perf_hud = PerformanceHUD(enabled=show_perf, log_path=log_file)

    @property
    def last_frame_ms(self) -> float:
        return self.perf_hud.last_full_frame_ms

    def render(
        self,
        game,  # legacy Game object
        target_surface: pygame.Surface,
        capture_sequence: Optional[List[str]] = None,
    ) -> None:
        seq = capture_sequence
        # Start timing via HUD abstraction
        self.perf_hud.begin_frame()
        # 1. Clear primary off-screen buffer
        game.display.fill((0, 0, 0, 0))
        if seq is not None:
            seq.append("clear")

        # 2. Background
        game.display_2.blit(game.assets["background"], (0, 0))
        if seq is not None:
            seq.append("background")

        # 3. World & entities
        from scripts.ui import UI  # local import avoids cycles

        game.scroll[0] += (game.player.rect().centerx - game.display.get_width() / 2 - game.scroll[0]) / 30
        game.scroll[1] += (game.player.rect().centery - game.display.get_height() / 2 - game.scroll[1]) / 30
        render_scroll = (int(game.scroll[0]), int(game.scroll[1]))
        # Render ghost before world to keep player on top
        replay_mgr = getattr(game, "replay", None)
        if replay_mgr:
            try:
                replay_mgr.render_ghost(game.display, render_scroll)
            except Exception:
                pass
        UI.render_game_elements(game, render_scroll)
        if seq is not None:
            seq.append("world")

        # 4. Transition
        from scripts.effects import Effects

        if game.transition:
            Effects.transition(game)
            if seq is not None:
                seq.append("effects_transition")

        # 5. Compose
        game.display_2.blit(game.display, (0, 0))
        if seq is not None:
            seq.append("compose")

        # 6. HUD:
        game_counts = {
            "players": len(getattr(game, "players", [])),
            "enemies": len(getattr(game, "enemies", [])),
            "projectiles": len(getattr(game, "projectiles", [])),
            "particles": len(getattr(game, "particles", [])),
            "sparks": len(getattr(game, "sparks", [])),
        }
        self._render_hud(game, game_counts=game_counts)
        if seq is not None:
            seq.append("hud")
        # Mark end of work segment (work portion excludes optional perf overlay drawing)
        self.perf_hud.end_work_segment()
        state_ref = getattr(game, "state_ref", None)
        if getattr(state_ref, "perf_enabled", False):
            # Add tile type counts (throttled via overlay rebuild) without heavy per-frame cost
            try:
                if hasattr(game, "tilemap") and hasattr(game.tilemap, "get_type_counts"):
                    self.perf_hud._game_counts = {
                        **getattr(self.perf_hud, "_game_counts", {}),  # existing entity counts
                        **{f"tile:{k}": v for k, v in game.tilemap.get_type_counts().items()},
                    }
                if hasattr(game, "cm") and hasattr(game.cm, "get_collectable_counts"):
                    self.perf_hud._game_counts = {
                        **getattr(self.perf_hud, "_game_counts", {}),
                        **game.cm.get_collectable_counts(),
                    }
            except Exception:
                pass
            # Render performance overlay (timings + counts incl. tiles)
            self.perf_hud.render(game.display_2, x=5, y=game.BASE_H - 170)
            if seq is not None and self.perf_hud.last_sample:
                seq.append("perf")

        # 7. Post effects (screenshake) then present
        Effects.screenshake(game)
        if seq is not None:
            seq.append("effects_post")

        if game.display_2.get_size() != target_surface.get_size():
            scaled = pygame.transform.scale(game.display_2, target_surface.get_size())
            target_surface.blit(scaled, (0, 0))
        else:
            target_surface.blit(game.display_2, (0, 0))
        if seq is not None:
            seq.append("blit")
        # Finalize full frame timing (sample available next frame)
        self.perf_hud.end_frame(clock=getattr(game, "clock", None))

    # Full frame time available next frame via self._last_frame_ms

    def _render_hud(self, game, game_counts=None) -> None:
        from scripts.ui import UI

        UI.render_game_ui_element(game.display_2, f"{game.timer.text}", game.BASE_W - 70, 5)
        UI.render_game_ui_element(game.display_2, f"{game.timer.best_time_text}", game.BASE_W - 70, 15)
        UI.render_game_ui_element(game.display_2, f"Level: {game.level}", game.BASE_W // 2 - 40, 5)
        if getattr(game, "player", None):
            lives = getattr(game.player, "lives", getattr(game.player, "lifes", 0))
            UI.render_game_ui_element(game.display_2, f"Lives: {lives}", 5, 5)
        UI.render_game_ui_element(game.display_2, f"${game.cm.coins}", 5, 15)
        UI.render_game_ui_element(game.display_2, f"Ammo:  {game.cm.ammo}", 5, 25)
        # Pass counts to performance HUD via perf_hud.render call later
        if game_counts is not None:
            try:
                # Attach for perf overlay rendering (perf_hud.render uses UI.render_perf_overlay)
                self.perf_hud._game_counts = game_counts  # type: ignore[attr-defined]
            except Exception:
                pass


__all__ = ["Renderer"]
