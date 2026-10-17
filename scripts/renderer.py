"""Unified rendering pipeline (Issue 14).

This module centralizes frame composition order so that *all* entry
points (legacy `Game.run` and new `GameState.render`) follow the same
deterministic layering. This is a transitional orchestrator; future
iterations (Issues 15–18) will replace direct asset / effect access
with dedicated systems (AssetManager, ParticleSystem, etc.).

Layer Order (bottom -> top):
1. Clear primary off-screen buffers (game.display)
2. Clear display_2 (the background image is composed in step 8, unshifted)
3. World & entities (tiles, player, enemies, projectiles, particles) via UI helper
4. Transition / full-screen visual effects pre-compose (optional)
5. Compose game.display onto display_2
6. HUD / UI overlay (timer, level info, lives, coins, ammo, perf metrics),
   on its own layer so it does not move with the camera
7. Screen shake / post effects applied just before blitting to window
8. Upscale to the window, shifted by the camera's sub-pixel remainder

Design Notes:
- Keeps all mutation of game surfaces in one place.
- Optional `capture_sequence` parameter records executed high-level steps
  for tests (avoids brittle pixel sampling with live artwork).
- Avoids importing heavy modules at top-level when possible to reduce
  import side-effects during test collection.
"""

from __future__ import annotations

import math
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
        # HUD layer: drawn on top of the world without the camera's sub-pixel shift
        self._hud: Optional[pygame.Surface] = None
        self._hud_dirty: Optional[pygame.Rect] = None
        # Background scaled to the window (rebuilt if the source or size changes)
        self._bg: Optional[pygame.Surface] = None
        self._bg_src: Optional[pygame.Surface] = None
        # Window-sized opaque buffer the final frame is composed in
        self._frame: Optional[pygame.Surface] = None

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

        # 2. Background: composed in step 8 so it does not move with the
        # camera's sub-pixel shift; display_2 starts transparent
        game.display_2.fill((0, 0, 0, 0))
        if seq is not None:
            seq.append("background")

        # 3. World & entities, at whole pixels (floor of the camera). The
        # remaining fraction is applied when upscaling (step 8).
        from scripts.ui import UI  # local import avoids cycles

        render_scroll = (math.floor(game.scroll[0]), math.floor(game.scroll[1]))
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

        # 6. HUD, on its own layer so it does not move with the camera:
        hud = self._hud_layer(game)
        game_counts = {
            "players": len(getattr(game, "players", [])),
            "enemies": len(getattr(game, "enemies", [])),
            "projectiles": len(getattr(game, "projectiles", [])),
            "particles": len(getattr(game, "particles", [])),
            "sparks": len(getattr(game, "sparks", [])),
        }
        hud_area = self._render_hud(game, hud, game_counts=game_counts)
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
            hud_area = _union(hud_area, self.perf_hud.render(hud, x=5, y=game.BASE_H - 170))
            if seq is not None and self.perf_hud.last_sample:
                seq.append("perf")
        if hud_area:
            hud_area = hud_area.clip(hud.get_rect())
        self._hud_dirty = hud_area

        # 7. Compute screenshake offset
        import random

        screenshake_offset = (0, 0)
        if getattr(game, "screenshake", 0):
            screenshake_offset = (
                random.random() * game.screenshake - game.screenshake / 2,
                random.random() * game.screenshake - game.screenshake / 2,
            )
        if seq is not None:
            seq.append("effects_post")

        # 8. Scale + blit to target surface with screenshake
        self._present(game, target_surface, render_scroll, hud, hud_area, screenshake_offset)
        if seq is not None:
            seq.append("blit")
        # Finalize full frame timing (sample available next frame)
        self.perf_hud.end_frame(clock=getattr(game, "clock", None))

    # Full frame time available next frame via self._last_frame_ms

    def _background(self, game, size) -> pygame.Surface:
        """Background image (its top-left screen-sized part) scaled to `size`."""
        src = game.assets["background"]
        if self._bg is None or self._bg_src is not src or self._bg.get_size() != size:
            view = src.subsurface((0, 0, min(src.get_width(), game.BASE_W), min(src.get_height(), game.BASE_H)))
            self._bg = pygame.Surface(size)  # opaque, so blitting it is a plain copy
            self._bg.blit(pygame.transform.scale(view, size), (0, 0))
            self._bg_src = src
        return self._bg

    def _hud_layer(self, game) -> pygame.Surface:
        size = (game.BASE_W, game.BASE_H)
        if self._hud is None or self._hud.get_size() != size:
            self._hud = pygame.Surface(size, pygame.SRCALPHA)
        elif self._hud_dirty:
            self._hud.fill((0, 0, 0, 0), self._hud_dirty)
        return self._hud

    def _present(self, game, target_surface, render_scroll, hud, hud_area, shake) -> None:
        size = target_surface.get_size()
        sx, sy = size[0] / game.BASE_W, size[1] / game.BASE_H
        # Compose background (static), world (camera-shifted) and HUD (static)
        # in an opaque buffer. Alpha blits straight onto the window would be
        # wrong: on macOS its surface has alpha 0, which turns them black.
        if self._frame is None or self._frame.get_size() != size:
            self._frame = pygame.Surface(size)
        frame = self._frame
        frame.blit(self._background(game, size), (0, 0))
        # Sub-pixel camera: the world was drawn at floor(scroll). Shifting the
        # upscaled image by the rest (in window pixels) makes the camera glide
        # instead of stepping by whole upscaled game pixels.
        ox = -round((game.scroll[0] - render_scroll[0]) * sx)
        oy = -round((game.scroll[1] - render_scroll[1]) * sy)
        world = game.display_2
        if (sx, sy) != (1, 1):
            w, h = world.get_size()
            world = pygame.transform.scale(world, (round(w * sx), round(h * sy)))
        frame.blit(world, (ox, oy))
        if hud_area:
            # Only the area the HUD drew on is scaled (a full-screen alpha
            # layer costs ~1 ms per frame)
            part = hud.subsurface(hud_area)
            if (sx, sy) != (1, 1):
                part = pygame.transform.scale(part, (round(hud_area.w * sx), round(hud_area.h * sy)))
            frame.blit(part, (round(hud_area.x * sx), round(hud_area.y * sy)))
        target_surface.blit(frame, shake)

    def _render_hud(self, game, surface, game_counts=None) -> Optional[pygame.Rect]:
        """Draw the HUD text onto `surface`; return the area drawn on."""
        from scripts.ui import UI

        drawn = [
            UI.render_game_ui_element(surface, f"{game.timer.text}", game.BASE_W - 70, 5),
            UI.render_game_ui_element(surface, f"{game.timer.best_time_text}", game.BASE_W - 70, 15),
            UI.render_game_ui_element(surface, f"Level: {game.level}", game.BASE_W // 2 - 40, 5),
        ]
        if getattr(game, "player", None):
            lives = getattr(game.player, "lives", getattr(game.player, "lifes", 0))
            drawn.append(UI.render_game_ui_element(surface, f"Lives: {lives}", 5, 5))
        drawn.append(UI.render_game_ui_element(surface, f"${game.cm.coins}", 5, 15))
        drawn.append(UI.render_game_ui_element(surface, f"Ammo:  {game.cm.ammo}", 5, 25))
        # Contextual HUD lines for new store items (only when relevant)
        y = 35
        try:
            from scripts.collectableManager import CollectableManager as CM
            from scripts.settings import settings as _settings

            if (
                0 <= _settings.selected_weapon < len(CM.WEAPONS)
                and CM.WEAPONS[_settings.selected_weapon] == "Ninja Stars"
            ):
                drawn.append(UI.render_game_ui_element(surface, f"Stars: {game.cm.ninja_stars}", 5, y))
                y += 10
            if 0 <= _settings.selected_gear < len(CM.GEAR) and CM.GEAR[_settings.selected_gear] == "Shield":
                drawn.append(UI.render_game_ui_element(surface, f"Shield: {game.cm.shield}", 5, y))
                y += 10
        except Exception:  # pragma: no cover - HUD is best-effort
            pass
        # Pass counts to performance HUD via perf_hud.render call later
        if game_counts is not None:
            try:
                # Attach for perf overlay rendering (perf_hud.render uses UI.render_perf_overlay)
                self.perf_hud._game_counts = game_counts  # type: ignore[attr-defined]
            except Exception:
                pass
        area = None
        for rect in drawn:
            area = _union(area, rect)
        return area


def _union(a: Optional[pygame.Rect], b: Optional[pygame.Rect]) -> Optional[pygame.Rect]:
    if not b:
        return a
    return b.copy() if not a else a.union(b)


__all__ = ["Renderer"]
