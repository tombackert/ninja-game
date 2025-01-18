import pygame
import math
import random
from scripts.particle import Particle
from scripts.spark import Spark
from scripts.button import Button
from scripts.settings import Settings

class UI:

    COLOR = "#137547"
    GAME_UI_COLOR = "#2C8C99"
    PM_COLOR = "#449DD1"
    SELECTOR_COLOR = "#DD6E42"

    @staticmethod
    def get_font(size):
        return pygame.font.Font("data/font.ttf", size)

    @staticmethod
    def draw_text_with_outline(surface, font, text, x, y,
                               text_color=(255,255,255),
                               outline_color=(0,0,0),
                               center=False):

        text_surf = font.render(text, True, text_color)

        if center:
            text_rect = text_surf.get_rect(center=(x, y))
            x, y = text_rect.x, text_rect.y

        offsets = [
            (-1, -1), (-1, 0), (-1, 1),
            (0,  -1),           (0,  1),
            (1,  -1),  (1,  0),  (1,  1)
        ]
        for ox, oy in offsets:
            outline_surf = font.render(text, True, outline_color)
            surface.blit(outline_surf, (x + ox, y + oy))

        surface.blit(text_surf, (x, y))

    @staticmethod
    def render_game_elements(game, render_scroll):
        # Leaf particles
        for rect in game.leaf_spawners:
            if random.random() * 49999 < rect.width * rect.height:
                pos = (rect.x + random.random() * rect.width, rect.y + random.random() * rect.height)
                game.particles.append(Particle(game, 'leaf', pos, velocity=[-0.1, 0.3], frame=random.randint(0, 20)))

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
                player.update(game.tilemap, (game.movement[1] - game.movement[0], 0))
                player.render(game.display, offset=render_scroll)

        # Projectiles
        for projectile in game.projectiles.copy():
            projectile[0][0] += projectile[1]
            projectile[2] += 1
            img = game.assets['projectile']
            game.display.blit(img, (projectile[0][0] - img.get_width() / 2 - render_scroll[0], projectile[0][1] - img.get_height() / 2 - render_scroll[1]))
            if game.tilemap.solid_check(projectile[0]):
                game.projectiles.remove(projectile)
                for i in range(4):
                    game.sparks.append(Spark(projectile[0], random.random() - 0.5 + (math.pi if projectile[1] > 0 else 0), 2 + random.random()))
            elif projectile[2] > 360:
                game.projectiles.remove(projectile)
            elif abs(game.player.dashing) < 50:
                if game.player.rect().collidepoint(projectile[0]):
                    game.projectiles.remove(projectile)
                    game.player.lifes -= 1
                    game.sfx['hit'].play()
                    game.screenshake = max(16, game.screenshake)
                    for i in range(30):
                        angle = random.random() * math.pi * 2
                        speed = random.random() * 5
                        game.sparks.append(Spark(game.player.rect().center, angle, 2 + random.random()))
                        game.particles.append(Particle(
                            game, 'particle', game.player.rect().center,
                            velocity=[
                                math.cos(angle + math.pi) * speed * 0.5,
                                math.sin(angle + math.pi) * speed * 0.5
                            ],
                            frame=random.randint(0, 7)
                        ))

        # Sparks
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
        display_sillhouette = display_mask.to_surface(setcolor=(0, 0, 0, 180), unsetcolor=(0, 0, 0, 0))
        for offset_o in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            game.display_2.blit(display_sillhouette, offset_o)

        # Particles
        for particle in game.particles.copy():
            kill = particle.update()
            particle.render(game.display, offset=render_scroll)
            if particle.type == 'leaf':
                particle.pos[0] += math.sin(particle.animation.frame * 0.035) * 0.3
            if kill:
                game.particles.remove(particle)
            
    @staticmethod
    def render_o_box(screen, options, selected_option, x, y, spacing):
        
        option_rects = []
        font_30 = UI.get_font(30)

        for i, option in enumerate(options):
            if i == selected_option:
                button_color = UI.SELECTOR_COLOR
            else:
                button_color = UI.PM_COLOR
            
            button_text = f"{option}"
            UI.draw_text_with_outline(
                surface=screen,
                font=font_30,
                text=button_text,
                x=x,
                y=y + i * spacing,
                text_color=button_color,
                center=True
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
                center=True
            )
    
    @staticmethod
    def render_menu_title(screen, title, x, y):
        font_40 = UI.get_font(40)
        UI.draw_text_with_outline(
            surface=screen,
            font=font_40,
            text=title,
            x=x,
            y=y,
            text_color=UI.PM_COLOR,
            center=True
        )

    @staticmethod
    def render_menu_bg(screen, display, bg):
        display.blit(bg, (0, 0))
        scaled_display = pygame.transform.scale(display, screen.get_size())
        screen.blit(scaled_display, (0, 0))

    @staticmethod
    def render_menu_msg(screen, msg, x, y):
        font_15 = UI.get_font(15)
        UI.draw_text_with_outline(
            surface=screen,
            font=font_15,
            text=msg,
            x=x,
            y=y,
            text_color=UI.SELECTOR_COLOR,
            center=True
        )

    @staticmethod
    def render_game_ui_element(display, text, x, y, align='left'):
        font_8 = UI.get_font(8)
        if align == 'right':
            text_surface = font_8.render(text, True, UI.GAME_UI_COLOR)
            x = x - text_surface.get_width()
        UI.draw_text_with_outline(
            surface=display,
            font=font_8,
            text=text,
            x=x,
            y=y,
            text_color=UI.GAME_UI_COLOR,
        )
