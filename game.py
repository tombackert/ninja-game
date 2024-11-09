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

class Game:
    def __init__(self, level=0):
        
        pygame.init()

        # screen
        pygame.display.set_caption('Ninja Game')
        self.screen = pygame.display.set_mode((640, 480))
        self.display = pygame.Surface((320, 240), pygame.SRCALPHA)
        self.display_2 = pygame.Surface((320, 240))
        
        # clock
        self.clock = pygame.time.Clock()
        
        # movement
        self.movement = [False, False]

        # assets
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
            'jump': pygame.mixer.Sound('data/sfx/jump.wav'),
            'dash': pygame.mixer.Sound('data/sfx/dash.wav'),
            'hit': pygame.mixer.Sound('data/sfx/hit.wav'),
            'shoot': pygame.mixer.Sound('data/sfx/shoot.wav'),
            'ambience': pygame.mixer.Sound('data/sfx/ambience.wav'),
        }

        self.sfx['ambience'].set_volume(0.2)
        self.sfx['shoot'].set_volume(0.4)
        self.sfx['hit'].set_volume(0.8)
        self.sfx['dash'].set_volume(0.1)
        self.sfx['jump'].set_volume(0.7)

        # entities
        self.clouds = Clouds(self.assets['clouds'], count=16)
        self.player = Player(self, (100, 100), (8, 15))
        self.tilemap = Tilemap(self, tile_size=16)
        
        # global variables
        self.level = level
        self.screenshake = 0
        self.saves = 0
        self.reaspawn_pos = []
        self.timer = Timer(self.level)

        # load first level
        self.load_level(self.level)

    def load_level(self, map_id, lifes=3, respawn=False):
        self.timer.reset()
        self.tilemap.load('data/maps/' + str(map_id) + '.json')

        self.leaf_spawners = []
        for tree in self.tilemap.extract([('large_decor', 2)], keep=True):
            self.leaf_spawners.append(pygame.Rect(4 + tree['pos'][0], 4 + tree['pos'][1], 23, 13))

        if respawn: 
            self.enemies = []
            enemy_id = 0
            self.player.pos = self.respawn_pos
            respawn_pos = [self.respawn_pos[0], self.respawn_pos[1]]
            self.player.air_time = 0
            for spawner in self.tilemap.extract([('spawners', 0),('spawners', 1)]):
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
            for spawner in self.tilemap.extract([('spawners', 0),('spawners', 1)]):
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

        # music
        pygame.mixer.music.load('data/music.wav')
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)
        self.sfx['ambience'].play(-1)

        # main loop
        running = True
        while running:

            self.timer.update(self.level)
            
            self.display.fill((0, 0, 0, 0))

            self.display_2.blit(self.assets['background'], (0, 0))

            self.screenshake = max(0, self.screenshake - 1)

            if not len(self.enemies):
                self.transition += 1
                if self.transition > 30:
                    #self.timer.update_best_time_for_level()
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

            # leaf particles
            for rect in self.leaf_spawners:
                if random.random() * 49999 < rect.width * rect.height:
                    pos = (rect.x + random.random() * rect.width, rect.y + random.random() * rect.height)
                    self.particles.append(Particle(self, 'leaf', pos, velocity=[-0.1, 0.3], frame=random.randint(0, 20)))

            # rendering
            self.clouds.update()
            self.clouds.render(self.display_2, offset=render_scroll)
            self.tilemap.render(self.display, offset=render_scroll)

            # handling enemies
            for enemy in self.enemies.copy():
                kill = enemy.update(self.tilemap, (0, 0))
                enemy.render(self.display, offset=render_scroll)
                if kill:
                    self.enemies.remove(enemy)
                    self.killed_enemies.append(enemy.id)

            if not self.dead:
                self.player.update(self.tilemap, (self.movement[1] - self.movement[0], 0))
                self.player.render(self.display, offset=render_scroll)


            # handling projectiles [[x, y], direction, timer]
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
                            self.particles.append(Particle(self, 'particle', self.player.rect().center, velocity=[math.cos(angle + math.pi) * speed * 0.5, math.sin(angle + math.pi) * speed * 0.5], frame=random.randint(0, 7)))

            # handling sparks
            for spark in self.sparks.copy():
                kill = spark.update()
                spark.render(self.display, offset=render_scroll)
                if kill:
                    self.sparks.remove(spark)

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

            # handling player movement
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                
                # movement keys
                if event.type == pygame.KEYDOWN:

                    if event.key == pygame.K_ESCAPE:
                        running = False
                    
                    # w, a, s, d
                    if event.key == pygame.K_a:
                        self.movement[0] = True
                    if event.key == pygame.K_d:
                        self.movement[1] = True
                    if event.key == pygame.K_w:
                        if self.player.jump():
                            self.sfx['jump'].play()

                    # arrow keys
                    if event.key == pygame.K_LEFT:
                        self.movement[0] = True
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = True
                    if event.key == pygame.K_UP:
                        if self.player.jump():
                            self.sfx['jump'].play()
                    
                    # space
                    if event.key == pygame.K_SPACE:
                        self.player.dash()

                    # respwan
                    if event.key == pygame.K_r:
                        self.dead += 1
                        self.lifes -= 1
                        print(self.dead)

                    # safe position
                    if event.key == pygame.K_p:
                        if self.saves > 0:
                            self.saves -= 1
                            self.respawn_pos = [self.player.pos[0], self.player.pos[1]]
                            print('saved respawn pos: ', self.respawn_pos)
                
                # stop movement
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_a:
                        self.movement[0] = False
                    if event.key == pygame.K_d:
                        self.movement[1] = False

                    if event.key == pygame.K_LEFT:
                        self.movement[0] = False
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = False

            # level transition
            if self.transition:
                transition_surf = pygame.Surface(self.display.get_size())
                pygame.draw.circle(transition_surf, (255, 255, 255), (self.display.get_width() // 2, self.display.get_height() // 2), (30 - abs(self.transition)) * 8)
                transition_surf.set_colorkey((255, 255, 255))
                self.display.blit(transition_surf, (0, 0))
            self.display_2.blit(self.display, (0, 0))

            # info display
            def get_font(size): 
                return pygame.font.Font("data/font.ttf", size)

            # display player position
            position = str(int(self.player.pos[0])) + ', ' + str(int(self.player.pos[1]))
            POSITION_TEXT = get_font(10).render(position, True, "black")
            POSITION_RECT = POSITION_TEXT.get_rect(center=(270, 10))
            #self.display_2.blit(POSITION_TEXT, POSITION_RECT)

            # display respawn position
            position = str(int(self.respawn_pos[0])) + ', ' + str(int(self.respawn_pos[1]))
            RESPAWN_TEXT = get_font(10).render(position, True, "black")
            RESPAWN_RECT = RESPAWN_TEXT.get_rect(center=(270, 25))
            #self.display_2.blit(RESPAWN_TEXT, RESPAWN_RECT)

            # display timer
            timer = self.timer.text
            TIMER_TEXT = get_font(10).render(timer, True, "black")
            TIMER_RECT = TIMER_TEXT.get_rect(center=(270, 10))
            self.display_2.blit(TIMER_TEXT, TIMER_RECT)

            # display best time
            best_time = self.timer.load_best_time_for_level()
            best_time = self.timer.format_time(best_time)
            BEST_TIME_TEXT = get_font(10).render(best_time, True, "black")
            BEST_TIME_RECT = BEST_TIME_TEXT.get_rect(center=(270, 25))
            self.display_2.blit(BEST_TIME_TEXT, BEST_TIME_RECT)
            
            # display lifes
            lifes = 'LIFES:' + str(self.lifes)
            LIFE_TEXT = get_font(10).render(lifes, True, "black")
            LIFE_RECT = LIFE_TEXT.get_rect(center=(45, 10))
            self.display_2.blit(LIFE_TEXT, LIFE_RECT)

            # display level
            level = 'LEVEL:' + str(self.level)
            LEVEL_TEXT = get_font(10).render(level, True, "black")
            LEVEL_RECT = LEVEL_TEXT.get_rect(center=(165, 10))
            self.display_2.blit(LEVEL_TEXT, LEVEL_RECT)
            
            # screen shake
            screenshake_offset = (random.random() * self.screenshake - self.screenshake / 2, random.random() * self.screenshake - self.screenshake / 2)
            self.screen.blit(pygame.transform.scale(self.display_2, self.screen.get_size()), screenshake_offset)

            # clock
            pygame.display.update()
            self.clock.tick(60) # 60fps

if __name__ == "__main__":
    Game().run()