# game.py
import pygame
import sys
import random
import math
import os
import pygame.font

from scripts.entities import PhysicsEntity, Player, Enemy
from scripts.utils import load_image, load_images, Animation
from scripts.tilemap import Tilemap
from scripts.clouds import Clouds
from scripts.particle import Particle
from scripts.spark import Spark 
from scripts.button import Button
from scripts.timer import Timer
from settings import settings

class Game:
    def __init__(self):
        pygame.init()

        # Screen setup
        pygame.display.set_caption('Ninja Game')
        self.screen = pygame.display.set_mode((640, 480))
        self.display = pygame.Surface((320, 240), pygame.SRCALPHA)
        self.display_2 = pygame.Surface((320, 240))

        # Clock
        self.clock = pygame.time.Clock()

        # Movement flags
        self.movement = [False, False]

        # Load assets
        self.assets = {
            'decor': load_images('tiles/decor'),
            'grass': load_images('tiles/grass'),
            'large_decor': load_images('tiles/large_decor'),
            'stone': load_images('tiles/stone'),
            'player': load_image('entities/player.png'),
            'background': load_image('background.png'),
            'clouds': load_images('clouds'),
            'enemy/idle': Animation(load_images('entities/enemy/idle'), img_dur=6),
            'enemy/run': Animation(load_images('entities/enemy/run'), img_dur=4),
            'player/idle': Animation(load_images('entities/player/idle'), img_dur=6),
            'player/run': Animation(load_images('entities/player/run'), img_dur=4),
            'player/jump': Animation(load_images('entities/player/jump')),
            'player/slide': Animation(load_images('entities/player/slide')),
            'player/wall_slide': Animation(load_images('entities/player/wall_slide')),
            'particle/leaf': Animation(load_images('particles/leaf'), img_dur=20, loop=False),
            'particle/particle': Animation(load_images('particles/particle'), img_dur=6, loop=False),
            'gun': load_image('gun.png'),
            'projectile': load_image('projectile.png'),
        }

        # Load sound effects and set volume based on settings
        self.sfx = {
            'jump': pygame.mixer.Sound('data/sfx/jump.wav'),
            'dash': pygame.mixer.Sound('data/sfx/dash.wav'),
            'hit': pygame.mixer.Sound('data/sfx/hit.wav'),
            'shoot': pygame.mixer.Sound('data/sfx/shoot.wav'),
            'ambience': pygame.mixer.Sound('data/sfx/ambience.wav'),
        }

        # Set sound volumes based on settings
        self.update_sound_volumes()

        # Entities
        self.clouds = Clouds(self.assets['clouds'], count=16)
        self.player = Player(self, (100, 100), (8, 15))
        self.tilemap = Tilemap(self, tile_size=16)

        # Global variables
        self.level = settings.selected_level
        self.screenshake = 0
        self.saves = 0
        self.respawn_pos = []
        self.timer = Timer(self.level)

        # Load the selected level
        self.load_level(self.level)

    # Update sound volumes based on settings
    def update_sound_volumes(self):
        """Update sound effect volumes based on settings."""
        self.sfx['ambience'].set_volume(settings.sound_volume * 0.2)
        self.sfx['shoot'].set_volume(settings.sound_volume * 0.4)
        self.sfx['hit'].set_volume(settings.sound_volume * 0.8)
        self.sfx['dash'].set_volume(settings.sound_volume * 0.1)
        self.sfx['jump'].set_volume(settings.sound_volume * 0.7)   

    def load_level(self, map_id, lifes=3, respawn=False):
        self.timer.reset()
        self.tilemap.load(f'data/maps/{map_id}.json')

        self.leaf_spawners = []
        for tree in self.tilemap.extract([('large_decor', 2)], keep=True):
            self.leaf_spawners.append(pygame.Rect(4 + tree['pos'][0], 4 + tree['pos'][1], 23, 13))

        if respawn: 
            self.enemies = []
            enemy_id = 0
            self.player.pos = self.respawn_pos
            respawn_pos = [self.respawn_pos[0], self.respawn_pos[1]]
            self.player.air_time = 0
            for spawner in self.tilemap.extract([('spawners', 0), ('spawners', 1)]):
                if spawner['variant'] == 1:
                    self.enemies.append(Enemy(self, spawner['pos'], (8, 15), enemy_id))
                    if enemy_id in self.killed_enemies:
                        self.enemies.remove(self.enemies[-1])
                    enemy_id += 1
                if spawner['variant'] == 0:
                    self.player.pos = spawner['pos']
                    self.respawn_pos = [self.player.pos[0], self.player.pos[1]]
        else:
            self.enemies = []
            enemy_id = 0
            for spawner in self.tilemap.extract([('spawners', 0), ('spawners', 1)]):
                if spawner['variant'] == 0:
                    self.player.pos = spawner['pos']
                    self.respawn_pos = [self.player.pos[0], self.player.pos[1]]
                    self.player.air_time = 0
                else:
                    self.enemies.append(Enemy(self, spawner['pos'], (8, 15), enemy_id))
                    enemy_id += 1
            self.saves = 1

        self.projectiles = []
        self.particles = []
        self.sparks = []
        self.killed_enemies = []

        self.scroll = [0, 0]
        self.dead = 0
        self.lifes = lifes
        self.transition = -30

        print('loaded level:', map_id)
        print('respawn pos:', self.respawn_pos)

    def run(self):
        # Music setup
        pygame.mixer.music.load('data/music.wav')
        pygame.mixer.music.set_volume(settings.music_volume)
        pygame.mixer.music.play(-1)
        self.sfx['ambience'].play(-1)

        # Flags for game state
        running = True
        paused = False

        # Main loop
        while running:
            self.timer.update(self.level)
            
            self.display.fill((0, 0, 0, 0))

            self.display_2.blit(self.assets['background'], (0, 0))

            self.screenshake = max(0, self.screenshake - 1)

            if not len(self.enemies):
                self.transition += 1
                if self.transition > 30:
                    # self.timer.update_best_time_for_level()
                    self.level = min(self.level + 1, len(os.listdir('data/maps')) - 1)
                    self.load_level(self.level)                

            if self.transition < 0:
                self.transition += 1

            if self.lifes < 1:
                self.dead += 1

            if self.dead:
                self.dead += 1
                if self.dead >= 10:
                    self.transition = min(30, self.transition + 1)
                if self.dead > 40 and self.lifes >= 1:
                    self.load_level(self.level, self.lifes, respawn=True)        
                if self.dead > 40 and self.lifes < 1:   
                    self.load_level(self.level)

            self.scroll[0] += (self.player.rect().centerx - self.display.get_width() / 2 - self.scroll[0]) / 30
            self.scroll[1] += (self.player.rect().centery - self.display.get_height() / 2 - self.scroll[1]) / 30
            render_scroll = (int(self.scroll[0]), int(self.scroll[1]))

            # Leaf particles
            for rect in self.leaf_spawners:
                if random.random() * 49999 < rect.width * rect.height:
                    pos = (rect.x + random.random() * rect.width, rect.y + random.random() * rect.height)
                    self.particles.append(Particle(self, 'leaf', pos, velocity=[-0.1, 0.3], frame=random.randint(0, 20)))

            # Rendering
            self.clouds.update()
            self.clouds.render(self.display_2, offset=render_scroll)
            self.tilemap.render(self.display, offset=render_scroll)

            # Handling enemies
            for enemy in self.enemies.copy():
                kill = enemy.update(self.tilemap, (0, 0))
                enemy.render(self.display, offset=render_scroll)
                if kill:
                    self.enemies.remove(enemy)
                    self.killed_enemies.append(enemy.id)

            if not self.dead:
                self.player.update(self.tilemap, (self.movement[1] - self.movement[0], 0))
                self.player.render(self.display, offset=render_scroll)

            # Handling projectiles [[x, y], direction, timer]
            for projectile in self.projectiles.copy():
                projectile[0][0] += projectile[1]
                projectile[2] += 1
                img = self.assets['projectile']
                self.display.blit(img, (projectile[0][0] - img.get_width() / 2 - render_scroll[0], projectile[0][1] - img.get_height() / 2 - render_scroll[1]))
                if self.tilemap.solid_check(projectile[0]):
                    self.projectiles.remove(projectile)
                    for i in range(4):
                        self.sparks.append(Spark(projectile[0], random.random() - 0.5 + (math.pi if projectile[1] > 0 else 0), 2 + random.random()))
                elif projectile[2] > 360:
                    self.projectiles.remove(projectile)
                elif abs(self.player.dashing) < 50:
                    if self.player.rect().collidepoint(projectile[0]):
                        self.projectiles.remove(projectile)
                        self.lifes -= 1
                        self.sfx['hit'].play()
                        self.screenshake = max(16, self.screenshake)
                        for i in range(30):
                            angle = random.random() * math.pi * 2
                            speed = random.random() * 5
                            self.sparks.append(Spark(self.player.rect().center, angle, 2 + random.random()))
                            self.particles.append(Particle(
                                self, 'particle', self.player.rect().center, 
                                velocity=[math.cos(angle + math.pi) * speed * 0.5, math.sin(angle + math.pi) * speed * 0.5],
                                frame=random.randint(0, 7)
                            ))

            # Handling sparks
            for spark in self.sparks.copy():
                kill = spark.update()
                spark.render(self.display, offset=render_scroll)
                if kill:
                    self.sparks.remove(spark)

            display_mask = pygame.mask.from_surface(self.display)
            display_sillhouette = display_mask.to_surface(setcolor=(0, 0, 0, 180), unsetcolor=(0, 0, 0, 0))
            for offset in [(-1,0), (1,0), (0,-1), (0,1)]:
                self.display_2.blit(display_sillhouette, offset)
            
            # Handling particles
            for particle in self.particles.copy():
                kill = particle.update()
                particle.render(self.display, offset=render_scroll)
                if particle.type == 'leaf':
                    particle.pos[0] += math.sin(particle.animation.frame * 0.035) * 0.3
                if kill:
                    self.particles.remove(particle)

            # Handling player movement
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                
                # Movement keys
                if event.type == pygame.KEYDOWN:

                    if event.key == pygame.K_ESCAPE:
                        paused = True
                        # Capture the current game display for blurring
                        current_game_display = self.display_2.copy()
                        # Get current time and best time from the timer
                        current_time = self.timer.text
                        best_time = self.timer.load_best_time_for_level()
                        best_time = self.timer.format_time(best_time)
                        # Call the pause menu
                        action = self.pause_menu(current_game_display, self.level, current_time, best_time)
                        if action == "continue":
                            paused = False
                        elif action == "menu":
                            # Exit to main menu
                            pygame.quit()
                            sys.exit()
                    
                    # W, A, S, D
                    if event.key == pygame.K_a:
                        self.movement[0] = True
                    if event.key == pygame.K_d:
                        self.movement[1] = True
                    if event.key == pygame.K_w:
                        if self.player.jump():
                            self.sfx['jump'].play()

                    # Arrow keys
                    if event.key == pygame.K_LEFT:
                        self.movement[0] = True
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = True
                    if event.key == pygame.K_UP:
                        if self.player.jump():
                            self.sfx['jump'].play()
                    
                    # Space
                    if event.key == pygame.K_SPACE:
                        self.player.dash()

                    # Respawn
                    if event.key == pygame.K_r:
                        self.dead += 1
                        self.lifes -= 1
                        print(self.dead)

                    # Save position
                    if event.key == pygame.K_p:
                        if self.saves > 0:
                            self.saves -= 1
                            self.respawn_pos = [self.player.pos[0], self.player.pos[1]]
                            print('saved respawn pos: ', self.respawn_pos)
                
                # Stop movement
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_a:
                        self.movement[0] = False
                    if event.key == pygame.K_d:
                        self.movement[1] = False

                    if event.key == pygame.K_LEFT:
                        self.movement[0] = False
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = False

            if not paused:
                # Level transition
                if self.transition:
                    transition_surf = pygame.Surface(self.display.get_size())
                    pygame.draw.circle(
                        transition_surf, (255, 255, 255),
                        (self.display.get_width() // 2, self.display.get_height() // 2),
                        (30 - abs(self.transition)) * 8
                    )
                    transition_surf.set_colorkey((255, 255, 255))
                    self.display.blit(transition_surf, (0, 0))
                self.display_2.blit(self.display, (0, 0))

                # Info display
                def get_font(size): 
                    return pygame.font.Font("data/font.ttf", size)

                # Display timer
                timer = self.timer.text
                TIMER_TEXT = get_font(10).render(timer, True, "black")
                TIMER_RECT = TIMER_TEXT.get_rect(center=(270, 10))
                self.display_2.blit(TIMER_TEXT, TIMER_RECT)

                # Display best time
                best_time = self.timer.load_best_time_for_level()
                best_time = self.timer.format_time(best_time)
                BEST_TIME_TEXT = get_font(10).render(best_time, True, "black")
                BEST_TIME_RECT = BEST_TIME_TEXT.get_rect(center=(270, 25))
                self.display_2.blit(BEST_TIME_TEXT, BEST_TIME_RECT)
                
                # Display lives
                lifes = 'LIFES:' + str(self.lifes)
                LIFE_TEXT = get_font(10).render(lifes, True, "black")
                LIFE_RECT = LIFE_TEXT.get_rect(center=(45, 10))
                self.display_2.blit(LIFE_TEXT, LIFE_RECT)

                # Display current level
                level_display = 'LEVEL:' + str(self.level)
                LEVEL_TEXT = get_font(10).render(level_display, True, "black")
                LEVEL_RECT = LEVEL_TEXT.get_rect(center=(165, 10))
                self.display_2.blit(LEVEL_TEXT, LEVEL_RECT)
                
                # Screen shake effect
                screenshake_offset = (
                    random.random() * self.screenshake - self.screenshake / 2,
                    random.random() * self.screenshake - self.screenshake / 2
                )
                self.screen.blit(pygame.transform.scale(self.display_2, self.screen.get_size()), screenshake_offset)

            # Update display and tick
            pygame.display.update()
            self.clock.tick(60) # 60fps

    def pause_menu(self, game_display, level, current_time, best_time):
        options = ["Continue", "Save Game", "Menu"]
        selected_option = 0


        def get_font(size): 
            return pygame.font.Font("data/font.ttf", size)

        while True:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_LEFT):
                        pass  # Do not exit the pause menu
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        selected_option = (selected_option - 1) % len(options)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected_option = (selected_option + 1) % len(options)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if options[selected_option] == "Continue":
                            return "continue"
                        elif options[selected_option] == "Save Game":
                            print("Save Game feature not implemented yet.")
                        elif options[selected_option] == "Menu":
                            from menu import Menu
                            Menu()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_pos = pygame.mouse.get_pos()
                        for i, rect in enumerate(option_rects):
                            if rect.collidepoint(mouse_pos):
                                if options[i] == "Continue":
                                    return "continue"
                                elif options[i] == "Save Game":
                                    print("Save Game feature not implemented yet.")
                                elif options[i] == "Menu":
                                    from menu import Menu
                                    Menu()

            # Get mouse position for highlighting
            mouse_pos = pygame.mouse.get_pos()

            # Render the blurred game display
            blurred_display = pygame.transform.smoothscale(game_display, (80, 60))
            blurred_display = pygame.transform.scale(blurred_display, (320, 240))
            self.screen.blit(blurred_display, (0, 0))

            # Overlay semi-transparent layer for better visibility
            overlay = pygame.Surface((640, 480), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))  # Black with alpha=100
            self.screen.blit(overlay, (0, 0))

            # Draw pause menu box
            pause_box = pygame.Surface((300, 200), pygame.SRCALPHA)
            pause_box.fill((50, 50, 50, 200))  # Dark gray with some transparency
            pause_rect = pause_box.get_rect(center=(320, 240))
            self.screen.blit(pause_box, pause_rect)

            # Draw Pause Title
            title_text = get_font(40).render("Paused", True, "White")
            title_rect = title_text.get_rect(center=(320, 170))
            self.screen.blit(title_text, title_rect)

            # Display current level, current time, and best time
            info_text = f"Level: {level}"
            info_surface = get_font(25).render(info_text, True, "White")
            info_rect = info_surface.get_rect(center=(320, 200))
            self.screen.blit(info_surface, info_rect)

            info_text = f"Current Time: {current_time}"
            info_surface = get_font(25).render(info_text, True, "White")
            info_rect = info_surface.get_rect(center=(320, 230))
            self.screen.blit(info_surface, info_rect)

            info_text = f"Best Time: {best_time}"
            info_surface = get_font(25).render(info_text, True, "White")
            info_rect = info_surface.get_rect(center=(320, 260))
            self.screen.blit(info_surface, info_rect)

            # Menu options
            option_rects = []
            start_y = 300
            spacing = 40

            for i, option in enumerate(options):
                if i == selected_option:
                    base_color = "Yellow"
                else:
                    base_color = "White"

                option_surface = get_font(30).render(option, True, base_color)
                option_rect = option_surface.get_rect(center=(320, start_y + i * spacing))
                self.screen.blit(option_surface, option_rect)
                option_rects.append(option_rect)

                # Highlighting with mouse hover
                if option_rect.collidepoint(mouse_pos):
                    selected_option = i

            pygame.display.update()
            self.clock.tick(60) 

# Run the main game if this file is executed directly
if __name__ == "__main__":
    Game().run()
