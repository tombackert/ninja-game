
import pygame
import math
import random
from scripts.particle import Particle
from scripts.spark import Spark 
from scripts.button import Button
from scripts.settings import Settings

class UI:

    COLOR = "#172A3A"

    def get_font(size):
        return pygame.font.Font("data/font.ttf", size)
    
    def render_game_ui(game):
        # Current time
        timer = game.timer.text
        TIMER_TEXT = game.get_font(10).render(f"{timer}", True, UI.COLOR)
        TIMER_RECT = TIMER_TEXT.get_rect(center=(270, 10))
        game.display_2.blit(TIMER_TEXT, TIMER_RECT)

        # Best time
        best_time = game.timer.best_time_text
        BEST_TIME_TEXT = game.get_font(10).render(f"{best_time}", True, UI.COLOR)
        BEST_TIME_RECT = BEST_TIME_TEXT.get_rect(center=(270, 25))
        #game.display_2.blit(BEST_TIME_TEXT, BEST_TIME_RECT)

        # Display lifes
        lifes = 'LIFES:' + str(game.player.lifes)
        LIFE_TEXT = game.get_font(10).render(lifes, True, UI.COLOR)
        LIFE_RECT = LIFE_TEXT.get_rect(center=(45, 10))
        game.display_2.blit(LIFE_TEXT, LIFE_RECT)

        # Display level
        level = 'LEVEL:' + str(game.level)
        LEVEL_TEXT = game.get_font(10).render(level, True, UI.COLOR)
        LEVEL_RECT = LEVEL_TEXT.get_rect(center=(165, 10))
        game.display_2.blit(LEVEL_TEXT, LEVEL_RECT)

        # Coins
        coins_str = 'COINS:' + str(game.collectable_manager.coin_count)
        COIN_TEXT = game.get_font(10).render(coins_str, True, UI.COLOR)
        COIN_RECT = COIN_TEXT.get_rect(center=(50, 25))
        #game.display_2.blit(COIN_TEXT, COIN_RECT)

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
                            velocity=[math.cos(angle + math.pi) * speed * 0.5, math.sin(angle + math.pi) * speed * 0.5],
                            frame=random.randint(0, 7)
                        ))

        # Sparks
        for spark in game.sparks.copy():
            kill = spark.update()
            spark.render(game.display, offset=render_scroll)
            if kill:
                game.sparks.remove(spark)
        
        # Collectables updaten & rendern
        game.collectable_manager.update(game.player.rect())
        game.collectable_manager.render(game.display, offset=render_scroll)

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