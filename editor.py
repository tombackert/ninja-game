import sys

import pygame
import pygame.font

from scripts.displayManager import DisplayManager
from scripts.entities import Enemy, Player
from scripts.settings import settings
from scripts.tilemap import Tilemap
from scripts.utils import load_image, load_images

MAP_NAME = "20"  # Default target map (may not exist). Will fallback to first available.
CURRENT_MAP = "data/maps/" + str(MAP_NAME) + ".json"


class Editor:
    def __init__(self):
        pygame.init()
        dm = DisplayManager()
        self.BASE_W = dm.BASE_W
        self.BASE_H = dm.BASE_H
        self.WIN_W = dm.WIN_W
        self.WIN_H = dm.WIN_H

        self.scale_x = self.WIN_W / self.BASE_W
        self.scale_y = self.WIN_H / self.BASE_H

        pygame.display.set_caption("editor")
        self.screen = pygame.display.set_mode((self.WIN_W, self.WIN_H))
        self.display = pygame.Surface((self.BASE_W, self.BASE_H), pygame.SRCALPHA)

        self.clock = pygame.time.Clock()

        self.assets = {
            "grass": load_images("tiles/grass"),
            "stone": load_images("tiles/stone"),
            "spawners": load_images("tiles/spawners"),
            "large_decor": load_images("tiles/large_decor"),
            "decor": load_images("tiles/decor"),
            "coin": load_images("tiles/collectables/coin"),
            "flag": load_images("tiles/collectables/flag"),
        }

        self.background = load_image("background.png")

        self.movement = [False, False, False, False]

        self.tilemap = Tilemap(self, tile_size=16)

        # Attempt to load requested map; if not present, fallback to first available.
        import os

        if os.path.exists(CURRENT_MAP):
            self.tilemap.load(CURRENT_MAP, load_entities=False)
        else:
            map_dir = "data/maps"
            try:
                candidates = [f for f in os.listdir(map_dir) if f.endswith(".json")]
            except FileNotFoundError:
                candidates = []
            numeric = []
            for f in candidates:
                try:
                    numeric.append(int(f.split(".")[0]))
                except Exception:
                    continue
            if numeric:
                numeric.sort()
                fallback = numeric[0]
                fallback_path = f"{map_dir}/{fallback}.json"
                self.tilemap.load(fallback_path, load_entities=False)
                settings.set_editor_level(int(fallback))
            # else: start with empty tilemap (new map creation scenario)

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
        # Optional frame cap for automated testing / CI (set EDITOR_MAX_FRAMES)
        import os

        max_frames_env = os.environ.get("EDITOR_MAX_FRAMES")
        max_frames = int(max_frames_env) if max_frames_env and max_frames_env.isdigit() else None
        frame_counter = 0

        while True:
            self.display.fill((255, 255, 255))
            # self.display.blit(self.background, (0, 0))

            self.scroll[0] += (self.movement[1] - self.movement[0]) * 5
            self.scroll[1] += (self.movement[3] - self.movement[2]) * 5
            render_scroll = (int(self.scroll[0]), int(self.scroll[1]))

            self.tilemap.render(self.display, offset=render_scroll)

            current_tile_img = self.assets[self.tile_list[self.tile_group]][self.tile_variant].copy()
            current_tile_img.set_alpha(180)

            mpos = pygame.mouse.get_pos()
            mpos = (
                mpos[0] / self.scale_x,  # X-Koordinate mit horizontalem Skalierungsfaktor
                mpos[1] / self.scale_y,  # Y-Koordinate mit vertikalem Skalierungsfaktor
            )
            tile_pos = (
                int((mpos[0] + render_scroll[0]) // self.tilemap.tile_size),
                int((mpos[1] + render_scroll[1]) // self.tilemap.tile_size),
            )

            if self.ongrid:
                if not self.multi_tile:
                    render_pos = (
                        tile_pos[0] * self.tilemap.tile_size - render_scroll[0],
                        tile_pos[1] * self.tilemap.tile_size - render_scroll[1],
                    )
                    self.display.blit(current_tile_img, render_pos)
                elif self.multi_tile:
                    for x in range(-self.m_offset, self.m_offset + 1):
                        for y in range(-self.m_offset, self.m_offset + 1):
                            pos = (tile_pos[0] + x, tile_pos[1] + y)
                            self.display.blit(
                                current_tile_img,
                                (
                                    pos[0] * self.tilemap.tile_size - render_scroll[0],
                                    pos[1] * self.tilemap.tile_size - render_scroll[1],
                                ),
                            )
            elif not self.ongrid:
                self.display.blit(current_tile_img, mpos)

            # Object placement
            if self.clicking:
                if self.ongrid:
                    if not self.multi_tile:
                        tile_type = self.tile_list[self.tile_group]
                        variant = self.tile_variant
                        pos = tile_pos
                        self.tilemap.tilemap[str(pos[0]) + ";" + str(pos[1])] = {
                            "type": tile_type,
                            "variant": variant,
                            "pos": pos,
                        }
                    elif self.multi_tile:
                        for x in range(-self.m_offset, self.m_offset + 1):
                            for y in range(-self.m_offset, self.m_offset + 1):
                                pos = (tile_pos[0] + x, tile_pos[1] + y)
                                self.tilemap.tilemap[f"{pos[0]};{pos[1]}"] = {
                                    "type": self.tile_list[self.tile_group],
                                    "variant": self.tile_variant,
                                    "pos": pos,
                                }
                elif not self.ongrid:
                    if not self.multi_tile:
                        self.tilemap.offgrid_tiles.append(
                            {
                                "type": self.tile_list[self.tile_group],
                                "variant": self.tile_variant,
                                "pos": (
                                    mpos[0] + self.scroll[0],
                                    mpos[1] + self.scroll[1],
                                ),
                            }
                        )

                if self.tile_group == 2 and self.tile_variant == 0:
                    if self.tilemap.players == []:
                        self.tilemap.players.append(
                            Player(
                                self,
                                [tile_pos[0], tile_pos[1]],
                                (8, 15),
                                self.tilemap.get_player_count(),
                                lifes=3,
                                respawn_pos=(tile_pos[0], tile_pos[1]),
                            )
                        )
                        print("-----------------")
                        print(self.tilemap.players)
                        for player in self.tilemap.players:
                            print(f"id: {player.id} at pos: {player.pos}")
                        print("-----------------")
                    else:
                        if not any(
                            player.pos[0] == tile_pos[0] and player.pos[1] == tile_pos[1]
                            for player in self.tilemap.players
                        ):
                            self.tilemap.players.append(
                                Player(
                                    self,
                                    [tile_pos[0], tile_pos[1]],
                                    (8, 15),
                                    self.tilemap.get_player_count(),
                                    lifes=3,
                                    respawn_pos=(tile_pos[0], tile_pos[1]),
                                )
                            )
                            print("-----------------")
                            print(self.tilemap.players)
                            for player in self.tilemap.players:
                                print(f"id: {player.id} at pos: {player.pos}")
                            print("-----------------")

                if self.tile_group == 2 and self.tile_variant == 1:
                    if self.tilemap.enemies == []:
                        self.tilemap.enemies.append(
                            Enemy(
                                self,
                                [tile_pos[0], tile_pos[1]],
                                (8, 15),
                                self.tilemap.get_enemy_count(),
                            )
                        )
                        print("-----------------")
                        print(self.tilemap.enemies)
                        for enemy in self.tilemap.enemies:
                            print(f"id: {enemy.id} at pos: {enemy.pos}")
                        print("-----------------")
                    else:
                        if not any(
                            enemy.pos[0] == tile_pos[0] and enemy.pos[1] == tile_pos[1]
                            for enemy in self.tilemap.enemies
                        ):
                            self.tilemap.enemies.append(
                                Enemy(
                                    self,
                                    [tile_pos[0], tile_pos[1]],
                                    (8, 15),
                                    self.tilemap.get_enemy_count(),
                                )
                            )
                            print("-----------------")
                            print(self.tilemap.enemies)
                            for enemy in self.tilemap.enemies:
                                print(f"id: {enemy.id} at pos: {enemy.pos}")
                            print("-----------------")

            # Tile removal
            if self.right_clicking:
                tile_loc = str(tile_pos[0]) + ";" + str(tile_pos[1])
                if tile_loc in self.tilemap.tilemap:
                    tile = self.tilemap.tilemap[tile_loc]
                    del self.tilemap.tilemap[tile_loc]

                for tile in self.tilemap.offgrid_tiles.copy():
                    tile_img = self.assets[tile["type"]][tile["variant"]]
                    tile_r = pygame.Rect(
                        tile["pos"][0] - self.scroll[0],
                        tile["pos"][1] - self.scroll[1],
                        tile_img.get_width(),
                        tile_img.get_height(),
                    )
                    if tile_r.collidepoint(mpos):
                        self.tilemap.offgrid_tiles.remove(tile)

                if self.multi_tile:
                    for x in range(-self.m_offset, self.m_offset + 1):
                        for y in range(-self.m_offset, self.m_offset + 1):
                            pos = (tile_pos[0] + x, tile_pos[1] + y)
                            tile_loc = f"{pos[0]};{pos[1]}"
                            if tile_loc in self.tilemap.tilemap:
                                del self.tilemap.tilemap[tile_loc]

                # Entity removal

                for player in self.tilemap.players:
                    if player.pos[0] == tile_pos[0] and player.pos[1] == tile_pos[1]:
                        self.tilemap.players.remove(player)

                        print("-----------------")
                        print(self.tilemap.players)
                        for player in self.tilemap.players:
                            print(f"id: {player.id} at pos: {player.pos}")
                        print("-----------------")

                for enemy in self.tilemap.enemies:
                    if enemy.pos[0] == tile_pos[0] and enemy.pos[1] == tile_pos[1]:
                        self.tilemap.enemies.remove(enemy)

                        print("-----------------")
                        print(self.tilemap.enemies)
                        for enemy in self.tilemap.enemies:
                            print(f"id: {enemy.id} at pos: {enemy.pos}")
                        print("-----------------")

            # update entity ids
            for i, player in enumerate(self.tilemap.players):
                player.id = i

            for i, enemy in enumerate(self.tilemap.enemies):
                enemy.id = i

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
                            self.tile_variant = (self.tile_variant - 1) % len(
                                self.assets[self.tile_list[self.tile_group]]
                            )
                        if event.button == 5:
                            self.tile_variant = (self.tile_variant + 1) % len(
                                self.assets[self.tile_list[self.tile_group]]
                            )
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

            position = str(int(self.scroll[0])) + ", " + str(int(self.scroll[1]))
            position_surface = self.font.render(position, True, (0, 0, 0))
            self.display.blit(
                position_surface,
                (self.display.get_width() - position_surface.get_width() - 10, 10),
            )

            t_pos = str(tile_pos[0]) + ", " + str(tile_pos[1])
            t_pos_surface = self.font.render(t_pos, True, (0, 0, 0))
            self.display.blit(
                t_pos_surface,
                (self.display.get_width() - t_pos_surface.get_width() - 10, 20),
            )

            # NOTE: Must provide destination tuple to blit; previous code caused TypeError
            self.screen.blit(pygame.transform.scale(self.display, (self.WIN_W, self.WIN_H)), (0, 0))
            pygame.display.update()
            self.clock.tick(60)  # 60fps

            if max_frames is not None:
                frame_counter += 1
                if frame_counter >= max_frames:
                    # Auto-exit for test harness usage
                    break


Editor().run()
