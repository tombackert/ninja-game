from collections import OrderedDict

import pygame

from scripts.particle import Particle
from scripts.rng_service import RNGService


class UI:
    COLOR = "#137547"
    GAME_UI_COLOR = "#2C8C99"
    PM_COLOR = "#449DD1"
    SELECTOR_COLOR = "#DD6E42"
    # Simple in-memory LRU cache for UI images
    _image_cache: "OrderedDict[tuple[str, float], pygame.Surface]" = OrderedDict()
    _cache_capacity: int = 64
    _cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
    # Text outline cache
    _text_cache: "OrderedDict[tuple[str, int, str, tuple[int,int,int], tuple[int,int,int]], pygame.Surface]" = (
        OrderedDict()
    )
    _text_cache_capacity: int = 256
    _text_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    # ---------- Cache management helpers (restored) ----------
    @staticmethod
    def clear_image_cache():
        UI._image_cache.clear()
        UI._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
        UI._text_cache.clear()
        UI._text_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    @staticmethod
    def configure_image_cache(capacity: int | None = None, clear: bool = False):
        if capacity is not None and capacity > 0:
            UI._cache_capacity = capacity
            while len(UI._image_cache) > UI._cache_capacity:
                UI._image_cache.popitem(last=False)
                UI._cache_stats["evictions"] += 1
        if clear:
            UI.clear_image_cache()

    @staticmethod
    def get_image_cache_stats():
        return dict(UI._cache_stats | {"size": len(UI._image_cache), "capacity": UI._cache_capacity})

    @staticmethod
    def get_text_cache_stats():
        return dict(UI._text_cache_stats | {"size": len(UI._text_cache), "capacity": UI._text_cache_capacity})

    @staticmethod
    def render_perf_overlay(
        surface,
        *,
        work_ms: float,
        frame_full_ms: float | None = None,
        avg_work_ms: float | None = None,
        fps: float | None = None,
        theor_fps: float | None = None,
        x: int = 5,
        y: int = 5,
        update_every: int = 10,
        min_width: int = 190,
        game_counts: dict | None = None,
    ):
        """Render (throttled) performance HUD.

        Note:
            Earlier refactor misinterpreted `y` as an internal first-line offset
            while always blitting the overlay at (0,0). Passing a large `y`
            (e.g. bottom anchoring with BASE_H - 120) then caused all text to be
            drawn outside the 120px-tall overlay, yielding an effectively empty
            transparent surface (HUD appeared missing). We now treat (x,y) as the
            on-screen anchor; internal text always starts at a small fixed inset.
        """
        if not hasattr(UI, "_perf_overlay_frame"):
            UI._perf_overlay_frame = 0  # type: ignore[attr-defined]
            UI._perf_overlay_cache = None  # type: ignore[attr-defined]
        UI._perf_overlay_frame += 1  # type: ignore[attr-defined]
        rebuild = (
            UI._perf_overlay_cache is None or (UI._perf_overlay_frame % update_every) == 1  # type: ignore[attr-defined]
        )
        if not rebuild and UI._perf_overlay_cache is not None:  # type: ignore[attr-defined]
            # If caller now requests a wider overlay than cached, force rebuild.
            try:  # pragma: no cover - defensive
                if UI._perf_overlay_cache.get_width() < min_width:  # type: ignore[attr-defined]
                    rebuild = True
            except Exception:
                rebuild = True
            if not rebuild:
                surface.blit(UI._perf_overlay_cache, (x, y))  # type: ignore[attr-defined]
                return
        font = UI.get_font(8)
        # We'll size width dynamically based on measured text so large values fit.
        # Fallback height remains fixed (120) for layout stability.
        # Build rows first (existing logic continues below) then compute width.
        # (Overlay surface created later after measuring text.)

        # Build rows first so we can size columns dynamically (prevents overlap).
        rows: list[tuple[str, str]] = []
        section_breaks: list[int] = []  # indices where a visual gap inserted
        if frame_full_ms is not None:
            rows.append(("Frame:", f"{frame_full_ms:.2f}ms"))
        rows.append(("Work:", f"{work_ms:.2f}ms"))
        if avg_work_ms is not None:
            rows.append(("AvgWork:", f"{avg_work_ms:.2f}ms"))
        if fps is not None:
            rows.append(("FPS:", f"{fps:.1f}"))
        if theor_fps is not None:
            rows.append(("FPS:", f"{theor_fps:.0f}"))
        section_breaks.append(len(rows))  # end of perf section
        img = UI.get_image_cache_stats()
        txt = UI.get_text_cache_stats()

        def ratio(stats: dict):
            total = stats.get("hits", 0) + stats.get("misses", 0)
            return (stats.get("hits", 0) / total * 100.0) if total else 0.0

        rows.append(("ImgCache:", f"{img['size']}/{img['capacity']} {ratio(img):.0f}%"))
        rows.append(("TxtCache:", f"{txt['size']}/{txt['capacity']} {ratio(txt):.0f}%"))
        rows.append(("Txt h/m/e:", f"{txt['hits']}/{txt['misses']}/{txt['evictions']}"))
        section_breaks.append(len(rows))  # end of cache section
        if game_counts:
            rows.extend((f"{k.capitalize()}:", str(game_counts[k])) for k in sorted(game_counts.keys()))
            section_breaks.append(len(rows))

        # Determine max label width for alignment (use fixed inner padding 5).
        inner_x = 5
        label_w = 0
        for lbl, _ in rows:
            w = font.render(lbl, True, UI.GAME_UI_COLOR).get_width()
            if w > label_w:
                label_w = w
        value_x = inner_x + label_w + 4

        # Compute dynamic column widths (labels already measured above) and max value width
        value_w = 0
        for _, val in rows:
            wv = font.render(val, True, UI.GAME_UI_COLOR).get_width()
            if wv > value_w:
                value_w = wv
        # Reserve space for optional icon (approx 22px) + padding
        icon_pad = 24
        dynamic_width = inner_x + label_w + 4 + value_w + 6 + icon_pad
        overlay_w = max(min_width, dynamic_width)

        gaps = max(0, len(section_breaks) - 1)
        dyn_height = 5 + len(rows) * 8 + gaps * 3 + 5
        overlay_h = max(120, dyn_height)  # maintain minimum for layout stability
        overlay = pygame.Surface((overlay_w, overlay_h), pygame.SRCALPHA)

        line = 5
        for idx, (lbl, val) in enumerate(rows):
            UI.draw_text_with_outline(
                surface=overlay,
                font=font,
                text=lbl,
                x=inner_x,
                y=line,
                text_color=UI.GAME_UI_COLOR,
            )
            UI.draw_text_with_outline(
                surface=overlay,
                font=font,
                text=val,
                x=value_x,
                y=line,
                text_color=UI.GAME_UI_COLOR,
            )
            line += 8
            if idx + 1 in section_breaks and idx + 1 != len(rows):
                line += 3  # small gap between sections
        # Small icon to exercise image cache in overlay path.
        try:  # pragma: no cover - depends on asset existing
            icon = UI.load_image_cached("data/images/projectile.png", scale=0.4)
            overlay.blit(icon, (overlay.get_width() - icon.get_width() - 2, 2))
        except Exception:  # pragma: no cover
            pass
        # Cache composed overlay for fast reuse.
        UI._perf_overlay_cache = overlay  # type: ignore[attr-defined]
        surface.blit(overlay, (x, y))

    @staticmethod
    def load_image_cached(path, scale=1):
        """Load and scale an image with caching.

        Cache key includes the path and scale factor so repeated calls avoid
        disk IO and redundant scaling work.
        """
        key = (path, scale)
        img = UI._image_cache.get(key)
        if img is not None:
            # LRU touch: move to end
            UI._image_cache.move_to_end(key)
            UI._cache_stats["hits"] += 1
            return img

        UI._cache_stats["misses"] += 1
        base = pygame.image.load(path)
        if scale != 1:
            base = pygame.transform.scale(
                base,
                (
                    int(base.get_width() * scale),
                    int(base.get_height() * scale),
                ),
            )

        # Evict if at capacity (before adding new)
        if len(UI._image_cache) >= UI._cache_capacity:
            UI._image_cache.popitem(last=False)
            UI._cache_stats["evictions"] += 1
        UI._image_cache[key] = base
        return base

    @staticmethod
    def get_font(size):
        return pygame.font.Font("data/font.ttf", size)

    @staticmethod
    def draw_text_with_outline(
        surface,
        font,
        text,
        x,
        y,
        text_color=PM_COLOR,
        outline_color=(0, 0, 0),
        center=False,
        scale=1,
    ):
        # Cache key uses font id (size via font.get_height()), text, colors
        font_size = font.get_height()
        key = (
            text,
            font_size,
            f"{text_color}-{outline_color}-{scale}-{center}",
            tuple(text_color),
            tuple(outline_color),
        )
        cached = UI._text_cache.get(key)
        if cached is not None:
            UI._text_cache.move_to_end(key)
            UI._text_cache_stats["hits"] += 1
            text_surf = cached
        else:
            UI._text_cache_stats["misses"] += 1
            base = font.render(text, True, text_color)
            offsets = [
                (-1 * scale, -1 * scale),
                (-1 * scale, 0),
                (-1 * scale, 1 * scale),
                (0 * scale, -1 * scale),
                (0 * scale, 1 * scale),
                (1 * scale, -1 * scale),
                (1 * scale, 0),
                (1 * scale, 1 * scale),
            ]
            # Create surface large enough for outlines
            w, h = base.get_width(), base.get_height()
            outline_pad = scale + 1
            surf = pygame.Surface((w + outline_pad * 2, h + outline_pad * 2), pygame.SRCALPHA)
            for ox, oy in offsets:
                outline_surf = font.render(text, True, outline_color)
                surf.blit(
                    outline_surf,
                    (ox + outline_pad, oy + outline_pad),
                )
            surf.blit(base, (outline_pad, outline_pad))
            text_surf = surf
            # Enforce capacity strictly (handles runtime capacity shrink)
            while len(UI._text_cache) >= UI._text_cache_capacity:
                UI._text_cache.popitem(last=False)
                UI._text_cache_stats["evictions"] += 1
            UI._text_cache[key] = text_surf

        draw_x, draw_y = x, y
        if center:
            rect = text_surf.get_rect(center=(x, y))
            draw_x, draw_y = rect.topleft
        surface.blit(text_surf, (draw_x, draw_y))

    @staticmethod
    def render_game_elements(game, render_scroll):
        # Leaf particles
        rng = RNGService.get()
        for rect in game.leaf_spawners:
            if rng.random() * 49999 < rect.width * rect.height:
                pos = (
                    rect.x + rng.random() * rect.width,
                    rect.y + rng.random() * rect.height,
                )
                game.particles.append(
                    Particle(
                        game,
                        "leaf",
                        pos,
                        velocity=[-0.1, 0.3],
                        frame=rng.randint(0, 20),
                    )
                )

        # Clouds
        game.clouds.render(game.display_2, offset=render_scroll)
        game.tilemap.render(game.display, offset=render_scroll)

        # Enemies
        for enemy in game.enemies:
            enemy.render(game.display, offset=render_scroll)

        if not game.dead:
            for player in game.players:
                if player.lives > 0:
                    player.render(game.display, offset=render_scroll)

        # Projectiles (render only; simulation handled by ProjectileSystem)
        for img, dx, dy in game.projectiles.get_draw_commands():
            game.display.blit(
                img,
                (
                    dx - render_scroll[0],
                    dy - render_scroll[1],
                ),
            )

        # Update & render sparks / particles via central system if present
        if hasattr(game, "particle_system"):
            draw_refs = game.particle_system.get_draw_commands()
            for spark in draw_refs["sparks"]:
                spark.render(game.display, offset=render_scroll)
            for particle in draw_refs["particles"]:
                particle.render(game.display, offset=render_scroll)
        else:
            # Legacy path (should be phased out)
            for spark in game.sparks.copy():
                spark.render(game.display, offset=render_scroll)

        # Collectables update & render
        game.cm.render(game.display, offset=render_scroll)

        # Display sillhouette
        display_mask = pygame.mask.from_surface(game.display)
        display_sillhouette = display_mask.to_surface(setcolor=(0, 0, 0, 180), unsetcolor=(0, 0, 0, 0))
        for offset_o in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            game.display_2.blit(display_sillhouette, offset_o)

    # Particle update now handled above when particle_system present.

    @staticmethod
    def render_o_box(screen, options, selected_option, x, y, spacing, font_size=30):
        option_rects = []
        font = UI.get_font(font_size)

        for i, option in enumerate(options):
            if i == selected_option:
                button_color = UI.SELECTOR_COLOR
            else:
                button_color = UI.PM_COLOR

            button_text = f"{option}"
            UI.draw_text_with_outline(
                surface=screen,
                font=font,
                text=button_text,
                x=x,
                y=y + i * spacing,
                text_color=button_color,
                center=True,
                scale=3,
            )

        return option_rects

    @staticmethod
    def render_info_box(screen, info, y, spacing):
        font_15 = UI.get_font(15)
        for i, text in enumerate(info):
            UI.draw_text_with_outline(
                surface=screen,
                font=font_15,
                text=text,
                x=320,
                y=y + i * spacing,
                text_color=UI.PM_COLOR,
                center=True,
                scale=3,
            )

    @staticmethod
    def render_menu_title(screen, title, x, y):
        font = UI.get_font(50)
        UI.draw_text_with_outline(
            surface=screen,
            font=font,
            text=title,
            x=x,
            y=y,
            text_color=UI.PM_COLOR,
            center=True,
            scale=3,
        )

    @staticmethod
    def render_menu_subtitle(screen, subtitle, x, y):
        font = UI.get_font(40)
        UI.draw_text_with_outline(
            surface=screen,
            font=font,
            text=subtitle,
            x=x,
            y=y,
            text_color=UI.PM_COLOR,
            center=True,
            scale=3,
        )

    @staticmethod
    def render_menu_bg(screen, display, bg):
        display.blit(bg, (0, 0))
        scaled_display = pygame.transform.scale(display, screen.get_size())
        screen.blit(scaled_display, (0, 0))

    @staticmethod
    def render_menu_msg(screen, msg, x, y, color=None):
        if color is None:
            color = UI.GAME_UI_COLOR
        font_15 = UI.get_font(30)
        UI.draw_text_with_outline(
            surface=screen,
            font=font_15,
            text=msg,
            x=x,
            y=y,
            text_color=color,
            center=True,
            scale=3,
        )

    @staticmethod
    def render_menu_ui_element(display, text, x, y, align="left"):
        font = UI.get_font(15)
        if align == "right":
            text_surface = font.render(text, True, UI.GAME_UI_COLOR)
            x = x - text_surface.get_width()
        UI.draw_text_with_outline(
            surface=display,
            font=font,
            text=text,
            x=x,
            y=y,
            text_color=UI.GAME_UI_COLOR,
            scale=2,
        )

    @staticmethod
    def render_game_ui_element(display, text, x, y, align="left"):
        font = UI.get_font(8)
        if align == "right":
            text_surface = font.render(text, True, UI.GAME_UI_COLOR)
            x = x - text_surface.get_width()
        UI.draw_text_with_outline(
            surface=display,
            font=font,
            text=text,
            x=x,
            y=y,
            text_color=UI.GAME_UI_COLOR,
        )

    @staticmethod
    def draw_img_outline(surface, img, x, y, outline_color=(0, 0, 0), scale=2):
        mask = pygame.mask.from_surface(img)
        outline_surf = mask.to_surface(setcolor=outline_color, unsetcolor=(0, 0, 0, 0))

        offsets = [
            (-1 * scale, -1 * scale),
            (-1 * scale, 0),
            (-1 * scale, 1 * scale),
            (0 * scale, -1 * scale),
            (0 * scale, 1 * scale),
            (1 * scale, -1 * scale),
            (1 * scale, 0),
            (1 * scale, 1 * scale),
        ]
        for ox, oy in offsets:
            surface.blit(outline_surf, (x + ox, y + oy))

        surface.blit(img, (x, y))

    @staticmethod
    def render_ui_img(display, p, x, y, scale=1):
        img = UI.load_image_cached(p, scale=scale)
        display.blit(img, (x - img.get_width() / 2, y - img.get_height() / 2))
        UI.draw_img_outline(display, img, x - img.get_width() / 2, y - img.get_height() / 2)
