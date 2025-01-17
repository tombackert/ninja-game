import pygame
import math
import random
from scripts.particle import Particle
from scripts.spark import Spark
from scripts.button import Button
from scripts.settings import Settings

class UI:

    COLOR = "#137547"
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
    def render_game_ui(game):
        font_10 = UI.get_font(10)

        # Timer
        timer_text = f"{game.timer.text}"
        UI.draw_text_with_outline(
            surface=game.display_2,
            font=font_10,
            text=timer_text,
            x=220,
            y=5,
            text_color=UI.COLOR,
            outline_color="black",
        )

        # Best time
        """
        best_time = f"{game.timer.best_time_text}"
        UI.draw_text_with_outline(
            surface=game.display_2,
            font=font_10,
            text=best_time,
            x=270,
            y=25,
            text_color=UI.COLOR,
            outline_color="black",
            center=True
        )
        """

        # Display lifes
        lifes = f"Lives: {game.player.lifes}"
        UI.draw_text_with_outline(
            surface=game.display_2,
            font=font_10,
            text=lifes,
            x=5,
            y=5,
            text_color=UI.COLOR,
            outline_color="black",
        )

        # Display level
        level_text = f"Level: {game.level}"
        UI.draw_text_with_outline(
            surface=game.display_2,
            font=font_10,
            text=level_text,
            x=115,
            y=5,
            text_color=UI.COLOR,
            outline_color="black",
        )

        # Coins
        coin_text = f"Coins: {game.cm.coins}"
        UI.draw_text_with_outline(
            surface=game.display_2,
            font=font_10,
            text=coin_text,
            x=5,
            y=20,
            text_color=UI.COLOR,
            outline_color="black",
        )

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

    # Display pause menu
    @staticmethod
    def render_pm_ui(game, options, selected_option, O_START_Y, O_SPACING):
        
        current_time = game.timer.text
        best_time = game.timer.best_time_text

        START_Y = 100
        SPACING = 20

        O_START_Y = O_START_Y
        O_SPACING = O_SPACING

        options = options
        selected_option = selected_option

        # Render the background
        game.display_3.blit(game.assets['background'], (0, 0))
        scaled_display = pygame.transform.scale(game.display_3, game.screen.get_size())
        game.screen.blit(scaled_display, (0, 0))

        # Title
        font_40 = UI.get_font(40)
        UI.draw_text_with_outline(
            surface=game.screen,
            font=font_40,
            text="Pause Menu",
            x=320,
            y=50,
            text_color=UI.PM_COLOR,
            outline_color="black",
            center=True
        )

        # Level info
        font_15 = UI.get_font(15)
        info_text = f"Level: {game.level}"
        UI.draw_text_with_outline(
            surface=game.screen,
            font=font_15,
            text=info_text,
            x=320,
            y=START_Y + SPACING * 0,
            text_color=UI.PM_COLOR,
            center=True
        )

        # Timer
        timer_text = f"Time: {current_time}"
        UI.draw_text_with_outline(
            surface=game.screen,
            font=font_15,
            text=timer_text,
            x=320,
            y=START_Y + SPACING * 1,
            text_color=UI.PM_COLOR,
            center=True
        )

        # Best time
        best_time_text = f"Best time: {best_time}"
        UI.draw_text_with_outline(
            surface=game.screen,
            font=font_15,
            text=best_time_text,
            x=320,
            y=START_Y + SPACING * 2,
            text_color=UI.PM_COLOR,
            center=True
        )

        # Coins
        coin_text = f"Coins: {game.cm.coins}"
        UI.draw_text_with_outline(
            surface=game.screen,
            font=font_15,
            text=coin_text,
            x=320,
            y=START_Y + SPACING * 3,
            text_color=UI.PM_COLOR,
            center=True
        )


        # Render pause menu box
        option_rects = UI.render_options_box(game, options, selected_option, O_START_Y, O_SPACING)
        
        return option_rects

            
    @staticmethod
    def render_options_box(game, options, selected_option, START_Y, SPACING):
        
        option_rects = []
        START_Y = START_Y
        SPACING = SPACING
        font_30 = UI.get_font(30)

        for i, option in enumerate(options):
            temp_rect = pygame.Rect(320 - 100, START_Y + i * SPACING - 15, 200, 30)
            if i == selected_option:
                button_color = UI.SELECTOR_COLOR
            else:
                button_color = UI.PM_COLOR
            
            button_text = f"{option}"
            UI.draw_text_with_outline(
                surface=game.screen,
                font=font_30,
                text=button_text,
                x=320,
                y=START_Y + i * SPACING,
                text_color=button_color,
                center=True
            )

        return option_rects