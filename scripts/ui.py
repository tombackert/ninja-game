import pygame
import random
from collections import OrderedDict
from scripts.particle import Particle


class UI:

    COLOR = "#137547"
    GAME_UI_COLOR = "#2C8C99"
    PM_COLOR = "#449DD1"
    SELECTOR_COLOR = "#DD6E42"
    # LOCK_IMG = pygame.image.load("data/images/gun.png")

    # Simple in-memory LRU cache for UI images (Issue 4 + optional enhancements)
    _image_cache: "OrderedDict[tuple[str, float], pygame.Surface]" = OrderedDict()
    _cache_capacity: int = 64
    _cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
    # Text outline cache (Issue 24)
    _text_cache: "OrderedDict[tuple[str, int, str, tuple[int,int,int], tuple[int,int,int]], pygame.Surface]" = (OrderedDict())
    _text_cache_capacity: int = 256
    _text_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    @staticmethod
    def clear_image_cache():
        """Clear cached UI images and text outline cache (for tests or memory reset)."""
        UI._image_cache.clear()
        UI._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
        UI._text_cache.clear()
        UI._text_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    @staticmethod
    def configure_image_cache(capacity: int | None = None, clear: bool = False):
        """Configure cache capacity or clear contents.

        Args:
            capacity: New max number of cached (path, scale) variants.
            clear: Whether to clear all cached entries & reset stats.
        """
        if capacity is not None and capacity > 0:
            UI._cache_capacity = capacity
            # If shrinking capacity, evict oldest until within limit
            while len(UI._image_cache) > UI._cache_capacity:
                UI._image_cache.popitem(last=False)
                UI._cache_stats["evictions"] += 1
        if clear:
            UI.clear_image_cache()

    @staticmethod
    def get_image_cache_stats():
        """Return a shallow copy of current cache statistics."""
        return dict(
            UI._cache_stats
            | {"size": len(UI._image_cache), "capacity": UI._cache_capacity}
        )

    @staticmethod
    def get_text_cache_stats():
        return dict(
            UI._text_cache_stats
            | {"size": len(UI._text_cache), "capacity": UI._text_cache_capacity}
        )

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
        text_color=(255, 255, 255),
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
            surf = pygame.Surface(
                (w + outline_pad * 2, h + outline_pad * 2), pygame.SRCALPHA
            )
            for ox, oy in offsets:
                outline_surf = font.render(text, True, outline_color)
                surf.blit(
                    outline_surf,
                    (ox + outline_pad, oy + outline_pad),
                )
            surf.blit(base, (outline_pad, outline_pad))
            text_surf = surf
            if len(UI._text_cache) >= UI._text_cache_capacity:
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
        for rect in game.leaf_spawners:
            if random.random() * 49999 < rect.width * rect.height:
                pos = (
                    rect.x + random.random() * rect.width,
                    rect.y + random.random() * rect.height,
                )
                game.particles.append(
                    Particle(
                        game,
                        "leaf",
                        pos,
                        velocity=[-0.1, 0.3],
                        frame=random.randint(0, 20),
                    )
                )

        # Clouds
        game.clouds.update()
        game.clouds.render(game.display_2, offset=render_scroll)
        game.tilemap.render(game.display, offset=render_scroll)

        # Enemies
        for enemy in game.enemies.copy():
            kill = enemy.update(game.tilemap, (0, 0))
            enemy.render(game.display, offset=render_scroll)
            if kill:
                game.enemies.remove(enemy)

        if not game.dead:
            for player in game.players:
                if player.id == game.playerID:
                    player.update(
                        game.tilemap, (game.movement[1] - game.movement[0], 0)
                    )
                else:
                    player.update(game.tilemap, (0, 0))
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
            game.particle_system.update()
            draw_refs = game.particle_system.get_draw_commands()
            for spark in draw_refs["sparks"]:
                spark.render(game.display, offset=render_scroll)
            for particle in draw_refs["particles"]:
                particle.render(game.display, offset=render_scroll)
        else:
            # Legacy path (should be phased out)
            for spark in game.sparks.copy():
                kill = spark.update()
                spark.render(game.display, offset=render_scroll)
                if kill:
                    game.sparks.remove(spark)

        # Collectables update & render
        game.cm.update(game.player.rect())
        game.cm.render(game.display, offset=render_scroll)

        # Display sillhouette
        display_mask = pygame.mask.from_surface(game.display)
        display_sillhouette = display_mask.to_surface(
            setcolor=(0, 0, 0, 180), unsetcolor=(0, 0, 0, 0)
        )
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
    def render_menu_msg(screen, msg, x, y):
        font_15 = UI.get_font(30)
        UI.draw_text_with_outline(
            surface=screen,
            font=font_15,
            text=msg,
            x=x,
            y=y,
            text_color=UI.GAME_UI_COLOR,
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
        UI.draw_img_outline(
            display, img, x - img.get_width() / 2, y - img.get_height() / 2
        )
