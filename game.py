import pygame
import sys
import random
import math
import os
import pygame.font
import json
from datetime import datetime
import time

from scripts.displayManager import DisplayManager
from scripts.entities import PhysicsEntity, Player, Enemy
from scripts.utils import load_image, load_images, Animation
from scripts.tilemap import Tilemap
from scripts.clouds import Clouds
from scripts.particle import Particle
from scripts.spark import Spark 
from scripts.button import Button
from scripts.timer import Timer
from scripts.settings import settings
from scripts.collectableManager import CollectableManager
from scripts.ui import UI
from scripts.keyboardManager import KeyboardManager
from scripts.effects import Effects
from menu import Menu

class Game:
    def __init__(self):
        
        pygame.init()

        dm = DisplayManager()
        self.BASE_W = dm.BASE_W
        self.BASE_H = dm.BASE_H
        self.WIN_W = dm.WIN_W
        self.WIN_H = dm.WIN_H

        pygame.display.set_caption("Ninja Game")
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.WIN_W, self.WIN_H = self.screen.get_size()

        self.display = pygame.Surface((self.BASE_W, self.BASE_H), pygame.SRCALPHA)
        self.display_2 = pygame.Surface((self.BASE_W, self.BASE_H))
        self.display_3 = pygame.Surface((self.BASE_W, self.BASE_H))

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
            'background': load_image('background-big.png'),
            'clouds': load_images('clouds'),
            'enemy/idle': Animation(load_images('entities/enemy/idle'), img_dur=6),
            'enemy/run': Animation(load_images('entities/enemy/run'), img_dur=4),
            'player/default/idle': Animation(load_images('entities/player/default/idle'), img_dur=6),
            'player/default/run': Animation(load_images('entities/player/default/run'), img_dur=4),
            'player/default/jump': Animation(load_images('entities/player/default/jump')),
            'player/default/slide': Animation(load_images('entities/player/default/slide')),
            'player/default/wall_slide': Animation(load_images('entities/player/default/wall_slide')),
            'player/red/idle': Animation(load_images('entities/player/red/idle'), img_dur=6),
            'player/red/run': Animation(load_images('entities/player/red/run'), img_dur=4),
            'player/red/jump': Animation(load_images('entities/player/red/jump')),
            'player/red/slide': Animation(load_images('entities/player/red/slide')),
            'player/red/wall_slide': Animation(load_images('entities/player/red/wall_slide')),
            'particle/leaf': Animation(load_images('particles/leaf'), img_dur=20, loop=False),
            'particle/particle': Animation(load_images('particles/particle'), img_dur=6, loop=False),
            'coin': Animation(load_images('collectables/coin'), img_dur=6),
            'flag': load_images('tiles/collectables/flag'),
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
            'collect': pygame.mixer.Sound('data/sfx/collect.wav'),
        }

        self.update_sound_volumes()

        # Entities
        self.clouds = Clouds(self.assets['clouds'], count=16)
        self.tilemap = Tilemap(self, tile_size=16)
        
        # Global variables
        self.level = settings.selected_level
        self.screenshake = 0
        self.timer = Timer(self.level)

        # Collectable Manager
        self.cm = CollectableManager(self)
        self.cm.load_collectables()

        # Keyboard Manager
        self.km = KeyboardManager(self)

        
        
        
        self.playerID = 0
        self.playerSkin = settings.selected_skin

        # Load the selected level
        self.load_level(self.level)
        
        #print(f"id: {self.players[self.playerID].id}")
        #print(f"size: {self.players[self.playerID].size}")
    

        # Game state
        self.running = True
        self.paused = False

    # Update sound volumes based on settings
    def update_sound_volumes(self):
        self.sfx['ambience'].set_volume(settings.sound_volume * 0.2)
        self.sfx['shoot'].set_volume(settings.sound_volume * 0.4)
        self.sfx['hit'].set_volume(settings.sound_volume * 0.8)
        self.sfx['dash'].set_volume(settings.sound_volume * 0.1)
        self.sfx['jump'].set_volume(settings.sound_volume * 0.7)
        self.sfx['collect'].set_volume(settings.sound_volume * 0.4)

    def load_level(self, map_id, lifes=3, respawn=False):
        self.timer.reset()
        self.tilemap.load('data/maps/' + str(map_id) + '.json')
        
        # Extract flags
        self.flags = []
        flag_tiles = self.tilemap.extract([("flag", 0)], keep=True)
        for tile in flag_tiles:
            flag_rect = pygame.Rect(tile['pos'][0], tile['pos'][1], 16, 16)
            self.flags.append(flag_rect)

        self.leaf_spawners = []
        for tree in self.tilemap.extract([('large_decor', 2)], keep=True):
            self.leaf_spawners.append(pygame.Rect(4 + tree['pos'][0], 4 + tree['pos'][1], 23, 13))

        ###### START LOAD LEVEL
        self.enemies = []
        self.players = []

        if respawn:
            enemy_id = 0
            for player in self.players:
                player.pos = player.respawn_pos
                player.air_time = 0
            for spawner in self.tilemap.extract([('spawners', 0), ('spawners', 1)]):
                if spawner['variant'] == 1:
                    self.enemies.append(Enemy(self, spawner['pos'], (8, 15), enemy_id))
                    enemy_id += 1
        else:
            enemy_id = 0
            player_id = 0
            skin = self.playerSkin
            for spawner in self.tilemap.extract([('spawners', 0), ('spawners', 1)]):
                if spawner['variant'] == 0:
                    player = Player(self, spawner['pos'], (8, 15), player_id, lifes=lifes, respawn_pos=list(spawner['pos']))
                    player.skin = skin
                    player.air_time = 0
                    self.players.append(player)
                    player_id += 1
                else:
                    self.enemies.append(Enemy(self, spawner['pos'], (8, 15), enemy_id))
                    enemy_id += 1
            self.saves = 1
            
            # Set the current player if there are any players
            if self.players:
                self.player = self.players[self.playerID]
        ###### END LOAD LEVEL
        
        self.projectiles = []
        self.particles = []
        self.sparks = []

        self.scroll = [0, 0]
        self.dead = 0
        if self.players:
            self.player.lifes = lifes
        self.transition = -30
        self.endpoint = False

        self.cm.load_collectables_from_tilemap(self.tilemap)

    def run(self):
        pygame.mixer.music.load('data/music.wav')
        pygame.mixer.music.set_volume(settings.music_volume)
        pygame.mixer.music.play(-1)
        self.sfx['ambience'].play(-1)


        while self.running:
            self.cm.load_collectables()

            while not self.paused:

                ##### START performance tracking
                start_frame_time = time.perf_counter()

                # Init 
                self.timer.update(self.level)
                self.display.fill((0, 0, 0, 0))
                self.display_2.blit(self.assets['background'], (0, 0))
                self.screenshake = max(0, self.screenshake - 1)

                #### START COMPUTE GAME FLAGS

                for flag_rect in self.flags:
                    if self.player.rect().colliderect(flag_rect):
                        self.endpoint = True

                if self.endpoint:
                    self.transition += 1
                    if self.transition > 30:
                        self.timer.update_best_time()
                        levels = [int(f.split('.')[0]) for f in os.listdir('data/maps') if f.endswith('.json')]
                        levels.sort()
                        current_level_index = levels.index(self.level)
                        if current_level_index == len(levels) - 1:
                            self.load_level(self.level)
                        else:
                            next_level = levels[current_level_index + 1]
                            self.level = next_level
                        settings.set_level_to_playable(self.level)
                        settings.selected_level = self.level
                        self.load_level(self.level)
                if self.transition < 0:
                    self.transition += 1

                if self.player.lifes < 1:
                    self.dead += 1

                if self.dead:
                    self.dead += 1
                    if self.dead >= 10:
                        self.transition = min(30, self.transition + 1)
                    if self.dead > 40 and self.player.lifes >= 1:
                        self.load_level(self.level, self.player.lifes, respawn=True)
                    if self.dead > 40 and self.player.lifes < 1:
                        self.load_level(self.level)

                ##### END COMPUTE GAME FLAGS

                # Rendering?
                self.scroll[0] += (self.player.rect().centerx - self.display.get_width() / 2 - self.scroll[0]) / 30
                self.scroll[1] += (self.player.rect().centery - self.display.get_height() / 2 - self.scroll[1]) / 30
                render_scroll = (int(self.scroll[0]), int(self.scroll[1]))

                #Graphics rendering
                UI.render_game_elements(self, render_scroll)

                # Keyboard events
                self.km.handle_keyboard_input()
                self.km.handle_mouse_input()

                # Level transition
                if self.transition:
                    Effects.transition(self)
                self.display_2.blit(self.display, (0, 0))

                # UI 
                UI.render_game_ui_element(self.display_2, f"{self.timer.text}", self.BASE_W - 70, 5)
                UI.render_game_ui_element(self.display_2, f"{self.timer.best_time_text}", self.BASE_W - 70, 15)
                UI.render_game_ui_element(self.display_2, f"Level: {self.level}", self.BASE_W // 2 - 40, 5)
                UI.render_game_ui_element(self.display_2, f"Lives: {self.player.lifes}", 5, 5)
                UI.render_game_ui_element(self.display_2, f"${self.cm.coins}", 5, 15)
                UI.render_game_ui_element(self.display_2, f"Ammo:  {self.cm.ammo}", 5, 25)

                ######
                end_frame_time = time.perf_counter()
                frame_time_ms = (end_frame_time - start_frame_time) * 1000.0
                fps = self.clock.get_fps()

                UI.render_game_ui_element(self.display_2, f"FPS: {fps:.1f}", 5, self.BASE_H - 20)
                UI.render_game_ui_element(self.display_2, f"{frame_time_ms:.2f} ms", 5, self.BASE_H - 10) 
                ###### END performance tracking
                
                # Screen shake
                Effects.screenshake(self)

                # Clock
                pygame.display.update()
                self.clock.tick(60)  # 60fps

            self.cm.save_collectables()
            Menu.pause_menu(self)

        print("Game Over")

if __name__ == "__main__":
    Game().run()