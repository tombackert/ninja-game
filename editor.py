import pygame
import pygame.font
import sys
from scripts.utils import load_images, load_image
from scripts.tilemap import Tilemap
from scripts.entities import Player
from scripts.entities import Enemy
from scripts.collectables import Collectables
from scripts.settings import settings

RENDER_SCALE = 2.0
MAP_NAME = '8'
CURRENT_MAP = 'data/maps/' + str(MAP_NAME) + '.json'

class Editor:
    def __init__(self):
        pygame.init()

        pygame.display.set_caption('editor')
        self.screen = pygame.display.set_mode((640, 480))
        self.display = pygame.Surface((320, 240))

        self.clock = pygame.time.Clock()

        self.assets = {
            'decor': load_images('tiles/decor'),
            'grass': load_images('tiles/grass'),
            'large_decor': load_images('tiles/large_decor'),
            'stone': load_images('tiles/stone'),
            'spawners': load_images('tiles/spawners'),
            'player/idle': load_images('tiles/large_decor'),
            'enemy/idle': load_images('tiles/large_decor'),
            'coin': load_images('collectables/coin'),
        }

        self.background = load_image('background.png')

        self.movement = [False, False, False, False]

        self.tilemap = Tilemap(self, tile_size=16)

        try:
            self.tilemap.load(CURRENT_MAP)
        except FileNotFoundError:
            pass

        self.scroll = [0, 0]

        self.tile_list = list(self.assets)
        self.tile_group = 0
        self.tile_variant = 0

        self.clicking = False
        self.right_clicking = False
        self.shift = False
        self.ongrid = True

        settings.load_settings()
        settings.set_editor_level(int(MAP_NAME))
        settings.save_settings()

        self.font = pygame.font.Font(None, 10)

    def run(self):
        while True:
            self.display.blit(self.background, (0, 0))

            self.scroll[0] += (self.movement[1] - self.movement[0]) * 5
            self.scroll[1] += (self.movement[3] - self.movement[2]) * 5
            render_scroll = (int(self.scroll[0]), int(self.scroll[1]))

            self.tilemap.render(self.display, offset=render_scroll)

            current_tile_img = self.assets[self.tile_list[self.tile_group]][self.tile_variant].copy()
            current_tile_img.set_alpha(180)

            mpos = pygame.mouse.get_pos()
            mpos = (mpos[0] / RENDER_SCALE, mpos[1] / RENDER_SCALE)
            tile_pos = (int((mpos[0] + self.scroll[0]) // self.tilemap.tile_size), 
                        int((mpos[1] + self.scroll[1]) // self.tilemap.tile_size))

            if self.ongrid:
                self.display.blit(current_tile_img, (tile_pos[0] * self.tilemap.tile_size - self.scroll[0], tile_pos[1] * self.tilemap.tile_size - self.scroll[1]))
            else:
                self.display.blit(current_tile_img, mpos)

            # Object placement
            if self.clicking and self.ongrid:
                tile_type = self.tile_list[self.tile_group]
                variant = self.tile_variant
                pos = tile_pos
                
                self.tilemap.tilemap[str(pos[0]) + ';' + str(pos[1])] = {
                    'type': tile_type, 
                    'variant': variant, 
                    'pos': pos
                }
                
                # Entities
                if tile_type == 'spawners':
                    # Player
                    if variant == 0:
                        if not any([p.pos == [pos[0] * self.tilemap.tile_size, pos[1] * self.tilemap.tile_size] for p in self.tilemap.players]):
                            self.tilemap.players.append(
                                Player(
                                    game=self, 
                                    pos=[pos[0] * self.tilemap.tile_size, pos[1] * self.tilemap.tile_size], 
                                    size=(8, 15), 
                                    e_id=len(self.tilemap.players),
                                    lifes=3,
                                    respawn_pos=[pos[0] * self.tilemap.tile_size, pos[1] * self.tilemap.tile_size]
                                )
                            )
                            print('Player added')
                            print(self.tilemap.players)
                    # Enemy
                    elif variant == 1:
                        if not any([e.pos == [pos[0] * self.tilemap.tile_size, pos[1] * self.tilemap.tile_size] for e in self.tilemap.enemies]):
                            self.tilemap.enemies.append(
                                Enemy(
                                    game=self, 
                                    pos=[pos[0] * self.tilemap.tile_size, pos[1] * self.tilemap.tile_size], 
                                    size=(8, 15), 
                                    e_id=len(self.tilemap.enemies),
                                )
                            )
                            print('Enemy added')
                            print(self.tilemap.enemies)
            # Offgrid tiles
            elif self.clicking and not self.ongrid:
                self.tilemap.offgrid_tiles.append({
                    'type': self.tile_list[self.tile_group], 
                    'variant': self.tile_variant, 
                    'pos': (mpos[0] + self.scroll[0], mpos[1] + self.scroll[1])
                })

            # Tile removal
            if self.right_clicking:
                tile_loc = str(tile_pos[0]) + ';' + str(tile_pos[1])
                if tile_loc in self.tilemap.tilemap:
                    tile = self.tilemap.tilemap[tile_loc]
                    if tile['type'] == 'spawners':
                        if tile['variant'] == 0:
                            # Player removal
                            self.tilemap.players = [p for p in self.tilemap.players if p.pos != [tile_pos[0] * self.tilemap.tile_size, tile_pos[1] * self.tilemap.tile_size]]
                        elif tile['variant'] == 1:
                            # Enemy removal
                            self.tilemap.enemies = [e for e in self.tilemap.enemies if e.pos != [tile_pos[0] * self.tilemap.tile_size, tile_pos[1] * self.tilemap.tile_size]]
                    del self.tilemap.tilemap[tile_loc]
                for tile in self.tilemap.offgrid_tiles.copy():
                    tile_img = self.assets[tile['type']][tile['variant']]
                    tile_r = pygame.Rect(tile['pos'][0] - self.scroll[0], tile['pos'][1] - self.scroll[1], tile_img.get_width(), tile_img.get_height())
                    if tile_r.collidepoint(mpos):
                        self.tilemap.offgrid_tiles.remove(tile)
            self.display.blit(current_tile_img, (5, 5))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                # Object placement
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.clicking = True
                    if event.button == 3:
                        self.right_clicking = True
                    if self.shift:
                        if event.button == 4:
                            self.tile_variant = (self.tile_variant - 1) % len(self.assets[self.tile_list[self.tile_group]])
                        if event.button == 5:
                            self.tile_variant = (self.tile_variant + 1) % len(self.assets[self.tile_list[self.tile_group]])
                    else:
                        if event.button == 4:
                            self.tile_group = (self.tile_group - 1) % len(self.tile_list)
                            self.tile_variant = 0
                        if event.button == 5:
                            self.tile_group = (self.tile_group + 1) % len(self.tile_list)
                            self.tile_variant = 0

                if event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self.clicking = False
                    if event.button == 3:
                        self.right_clicking = False

                # Movement and other controls
                if event.type == pygame.KEYDOWN:
                    # w, a, s, d
                    if event.key == pygame.K_a:
                        self.movement[0] = True
                    if event.key == pygame.K_d:
                        self.movement[1] = True
                    if event.key == pygame.K_w:
                        self.movement[2] = True
                    if event.key == pygame.K_s:
                        self.movement[3] = True
                   
                    if event.key == pygame.K_LEFT:
                        self.movement[0] = True
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = True
                    if event.key == pygame.K_UP:
                        self.movement[2] = True
                    if event.key == pygame.K_DOWN:
                        self.movement[3] = True

                    if event.key == pygame.K_g:
                        self.ongrid = not self.ongrid
                    if event.key == pygame.K_LSHIFT:
                        self.shift = True
                    if event.key == pygame.K_o:
                        self.tilemap.save(CURRENT_MAP)
                    if event.key == pygame.K_t:
                        self.tilemap.autotile()
                
                    if event.key == pygame.K_ESCAPE:
                        self.tilemap.save(CURRENT_MAP)
                        pygame.quit()
                        sys.exit()

                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_a:
                        self.movement[0] = False
                    if event.key == pygame.K_d:
                        self.movement[1] = False
                    if event.key == pygame.K_w:
                        self.movement[2] = False
                    if event.key == pygame.K_s:
                        self.movement[3] = False

                    if event.key == pygame.K_LEFT:
                        self.movement[0] = False
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = False
                    if event.key == pygame.K_UP:
                        self.movement[2] = False
                    if event.key == pygame.K_DOWN:
                        self.movement[3] = False

                    if event.key == pygame.K_LSHIFT:
                        self.shift = False

            position = str(int(self.scroll[0])) + ', ' + str(int(self.scroll[1]))
            position_surface = self.font.render(position, True, (0, 0, 0))
            self.display.blit(position_surface, (self.display.get_width() - position_surface.get_width() - 10, 10))

            self.screen.blit(pygame.transform.scale(self.display, self.screen.get_size()), (0, 0))
            pygame.display.update()
            self.clock.tick(60)  # 60fps

Editor().run()