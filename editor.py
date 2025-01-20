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
MAP_NAME = '15'
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
            'coin': load_images('tiles/collectables/coin'),
            'flag': load_images('tiles/collectables/flag'),
        }

        self.background = load_image('background.png')

        self.movement = [False, False, False, False]

        self.tilemap = Tilemap(self, tile_size=16)

        try:
            self.tilemap.load(CURRENT_MAP, load_entities=False)
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
        self.space = False
        self.multi_tile = False

        self.multi_tile_size = 3
        self.m_offset = self.multi_tile_size // 2

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
                if not self.multi_tile:
                    self.display.blit(current_tile_img, (tile_pos[0] * self.tilemap.tile_size - self.scroll[0], tile_pos[1] * self.tilemap.tile_size - self.scroll[1]))
                elif self.multi_tile:
                    for x in range(-self.m_offset, self.m_offset + 1):
                        for y in range(-self.m_offset, self.m_offset + 1):
                            pos = (tile_pos[0] + x, tile_pos[1] + y)
                            self.display.blit(current_tile_img, (
                                pos[0] * self.tilemap.tile_size - self.scroll[0],
                                pos[1] * self.tilemap.tile_size - self.scroll[1]
                            ))
            elif not self.ongrid:
                self.display.blit(current_tile_img, mpos)

            # Object placement
            if self.clicking:
                if self.ongrid:
                    if not self.multi_tile:
                        tile_type = self.tile_list[self.tile_group]
                        variant = self.tile_variant
                        pos = tile_pos
                        self.tilemap.tilemap[str(pos[0]) + ';' + str(pos[1])] = {
                            'type': tile_type, 
                            'variant': variant, 
                            'pos': pos
                        }
                    elif self.multi_tile:
                        for x in range(-self.m_offset, self.m_offset + 1):
                            for y in range(-self.m_offset, self.m_offset + 1):
                                pos = (tile_pos[0] + x, tile_pos[1] + y)
                                self.tilemap.tilemap[f"{pos[0]};{pos[1]}"] = {
                                    'type': self.tile_list[self.tile_group],
                                    'variant': self.tile_variant,
                                    'pos': pos
                                }
                elif not self.ongrid:
                    if not self.multi_tile:
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
                    del self.tilemap.tilemap[tile_loc]
                    
                for tile in self.tilemap.offgrid_tiles.copy():
                    tile_img = self.assets[tile['type']][tile['variant']]
                    tile_r = pygame.Rect(tile['pos'][0] - self.scroll[0], tile['pos'][1] - self.scroll[1], tile_img.get_width(), tile_img.get_height())
                    if tile_r.collidepoint(mpos):
                        self.tilemap.offgrid_tiles.remove(tile)

                if self.multi_tile:
                    for x in range(-self.m_offset, self.m_offset + 1):
                        for y in range(-self.m_offset, self.m_offset + 1):
                            pos = (tile_pos[0] + x, tile_pos[1] + y)
                            tile_loc = f"{pos[0]};{pos[1]}"
                            if tile_loc in self.tilemap.tilemap:
                                del self.tilemap.tilemap[tile_loc]


            self.display.blit(current_tile_img, (5, 5))
            tile_name = f"{self.tile_list[self.tile_group]}/{self.tile_variant}"
            name_surface = self.font.render(tile_name, True, (0, 0, 0))
            self.display.blit(name_surface, (30, 5))

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
                    elif self.space and self.multi_tile:
                        if event.button == 4:
                            self.multi_tile_size = max(1, self.multi_tile_size - 1)
                            self.m_offset = self.multi_tile_size // 2
                        if event.button == 5:
                            self.multi_tile_size += 1
                            self.m_offset = self.multi_tile_size // 2
                    elif not self.shift:
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
                    if event.key == pygame.K_m:
                        self.multi_tile = not self.multi_tile
                    if event.key == pygame.K_SPACE:
                        self.space = True
                
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
                    if event.key == pygame.K_SPACE:
                        self.space = False

            position = str(int(self.scroll[0])) + ', ' + str(int(self.scroll[1]))
            position_surface = self.font.render(position, True, (0, 0, 0))
            self.display.blit(position_surface, (self.display.get_width() - position_surface.get_width() - 10, 10))

            self.screen.blit(pygame.transform.scale(self.display, self.screen.get_size()), (0, 0))
            pygame.display.update()
            self.clock.tick(60)  # 60fps

Editor().run()