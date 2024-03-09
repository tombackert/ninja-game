# Setup Python ----------------------------------------------- #
import pygame
import sys
import random
import math
import os
import pygame.font

from game import Game
from scripts.entities import PhysicsEntity, Player, Enemy
from scripts.utils import load_image, load_images, Animation
from scripts.tilemap import Tilemap
from scripts.clouds import Clouds
from scripts.particle import Particle
from scripts.spark import Spark
from pygame.locals import *
 
# Setup pygame/window ---------------------------------------- #

class Menu:
    def __init__(self):
        pygame.init()
        
        
        self.clock = pygame.time.Clock()

        self.text_size = 50

        self.font = pygame.font.SysFont(None, self.text_size)
   
        self.click = False

        pygame.display.set_caption('ninja game')
        self.screen = pygame.display.set_mode((640, 480))
        self.display = pygame.Surface((320, 240), pygame.SRCALPHA)
        self.display_2 = pygame.Surface((320, 240))

        self.clock = pygame.time.Clock()

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

        # sound effects
        self.sfx = {
            'ambience': pygame.mixer.Sound('data/sfx/ambience.wav'),
        }

        self.sfx['ambience'].set_volume(0.2)

        self.clouds = Clouds(self.assets['clouds'], count=16)

        self.player = Player(self, (100, 100), (8, 15))

        self.tilemap = Tilemap(self, tile_size=16)
        
        self.level = 'menu'
        
        self.load_level(self.level)

        self.screenshake = 0



    def load_level(self, map_id):
        self.tilemap.load('data/' + str(map_id) + '.json')

        self.leaf_spawners = []
        for tree in self.tilemap.extract([('large_decor', 2)], keep=True):
            self.leaf_spawners.append(pygame.Rect(4 + tree['pos'][0], 4 + tree['pos'][1], 23, 13))

        self.enemies = []
        enemy_id = 0
        for spawner in self.tilemap.extract([('spawners', 0),('spawners', 1)]):
            if spawner['variant'] == 0:
                self.player.pos = spawner['pos']
                self.player.air_time = 0
            else:
                self.enemies.append(Enemy(self, spawner['pos'], (8, 15), enemy_id))
                enemy_id += 1

        self.projectiles = []
        self.particles = []
        self.sparks = []
        

        self.scroll = [0, 0]
        self.dead = 0
        self.transition = -30

        


    def draw_text(self, text, font, color, surface, x, y):
        self.textobj = self.font.render(text, 1, color)
        self.textrect = self.textobj.get_rect()
        self.textrect.topleft = (x, y)
        self.screen.blit(self.textobj, self.textrect)
    
    def run(self):

        pygame.mixer.music.load('data/music.wav')
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)

        self.sfx['ambience'].play(-1)

        while True:
            self.display.fill((0, 0, 0, 0))
            self.display_2.blit(self.assets['background'], (0, 0)) # for outline effect

            self.screenshake = max(0, self.screenshake - 1)
            

            self.scroll[0] += (self.player.rect().centerx - self.display.get_width() / 2 - self.scroll[0]) / 30
            self.scroll[1] += (self.player.rect().centery - self.display.get_height() / 2 - self.scroll[1]) / 30
            render_scroll = (int(self.scroll[0]), int(self.scroll[1]))

            for rect in self.leaf_spawners:
                if random.random() * 49999 < rect.width * rect.height:
                    pos = (rect.x + random.random() * rect.width, rect.y + random.random() * rect.height)
                    self.particles.append(Particle(self, 'leaf', pos, velocity=[-0.1, 0.3], frame=random.randint(0, 20)))


            self.clouds.update()
            self.clouds.render(self.display_2, offset=render_scroll)

            self.tilemap.render(self.display, offset=render_scroll)

            display_mask = pygame.mask.from_surface(self.display)
            display_sillhouette = display_mask.to_surface(setcolor=(0, 0, 0, 180), unsetcolor=(0, 0, 0, 0))
            for offset in [(-1,0), (1,0), (0,-1), (0,1)]:
                self.display_2.blit(display_sillhouette, offset)
            
            # handling particles
            for particle in self.particles.copy():
                kill = particle.update()
                particle.render(self.display, offset=render_scroll)
                if particle.type == 'leaf':
                    particle.pos[0] += math.sin(particle.animation.frame * 0.035) * 0.3
                if kill:
                    self.particles.remove(particle)

            





            self.click = False

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                if event.type == MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.click = True

            self.display_2.blit(self.display, (0, 0))
    
            
            screenshake_offset = (0, 0)
            self.screen.blit(pygame.transform.scale(self.display_2, self.screen.get_size()), screenshake_offset)

            ####

            self.draw_text('Menu', self.font, (0, 0, 0), self.screen, 260, 20)
    
            self.mx, self.my = pygame.mouse.get_pos()

            box_size = 32
    
            self.button_1 = pygame.Rect(640/2-125, 66, 250, 2*box_size + 4)
            self.button_2 = pygame.Rect(640/2-125, 66+96, 250, 2*box_size + 4)
            self.button_3 = pygame.Rect(640/2-125, 66+2*96, 250, 2*box_size + 4)
            self.button_4 = pygame.Rect(640/2-125, 66+3*96, 250, 2*box_size + 4)

            

            if self.button_1.collidepoint((self.mx, self.my)):
                if self.click:
                    Game().run()
            if self.button_2.collidepoint((self.mx, self.my)):
                if self.click:
                    self.options()
            
            pygame.draw.rect(self.display, (0, 0, 0, 128), self.button_1)
            pygame.draw.rect(self.display, (0, 0, 0, 128), self.button_2)
            pygame.draw.rect(self.display, (0, 0, 0, 128), self.button_3)
            pygame.draw.rect(self.display, (0, 0, 0, 128), self.button_4)

            self.text_offset = 20

            self.draw_text('Play', self.font, (0, 0, 0), self.screen, 640/2-125, 66 + self.text_offset)
            self.draw_text('Levels', self.font, (0, 0, 0), self.screen, 640/2-125, 66+96 + self.text_offset)
            self.draw_text('Shop', self.font, (0, 0, 0), self.screen, 640/2-125, 66+2*96 + self.text_offset)
            self.draw_text('Settings', self.font, (0, 0, 0), self.screen, 640/2-125, 66+3*96 + self.text_offset)

            ###



            pygame.display.update()
            self.clock.tick(60) # 60fps
    
    def options(self):
        running = True
        while running:
            self.screen.fill((0,0,0))
    
            self.draw_text('options', self.font, (255, 255, 255), self.screen, 20, 20)
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        running = False
            
            pygame.display.update()
            self.clock.tick(60)
 
Menu().run()