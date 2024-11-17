import pygame
import json
from scripts.entities import Enemy, Player
from settings import settings

AUTOTILE_MAP = {
    tuple(sorted([(1, 0), (0, 1)]))                     : 0,
    tuple(sorted([(1, 0), (0, 1), (-1, 0)]))            : 1,
    tuple(sorted([(-1, 0), (0, 1)]))                    : 2,
    tuple(sorted([(-1, 0), (0, -1), (0, 1)]))           : 3,
    tuple(sorted([(-1, 0), (0, -1)]))                   : 4,
    tuple(sorted([(-1, 0), (0, -1), (1, 0)]))           : 5,
    tuple(sorted([(1, 0), (0, -1)]))                    : 6,
    tuple(sorted([(1, 0), (0, -1), (0, 1)]))            : 7,
    tuple(sorted([(1, 0), (-1, 0), (0, 1), (0, -1)]))   : 8,
}

NEIGHBOR_OFFSET = [(-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (0, 0), (-1, 1), (0, 1), (1, 1)]
PHYSICS_TILES = {'grass', 'stone'} # things an entity can colid with
AUTOTILE_TILES = {'grass', 'stone'}


class Tilemap:
    def __init__(self, game, tile_size=16):
        self.game = game
        self.level = settings.get_selected_editor_level()
        self.tile_size = tile_size
        self.tilemap = {}
        self.offgrid_tiles = []
        self.enemies = []
        self.players = []

    def extract(self, id_pairs, keep=False):
        matches = []
        for tile in self.offgrid_tiles.copy():
            if (tile['type'], tile['variant']) in id_pairs:
                matches.append(tile.copy())
                if not keep:
                    self.offgrid_tiles.remove(tile)

        for loc in self.tilemap.copy():
            tile = self.tilemap[loc]
            if (tile['type'], tile['variant']) in id_pairs:
                matches.append(tile.copy())
                matches[-1]['pos'] = matches[-1]['pos'].copy()
                matches[-1]['pos'][0] *= self.tile_size
                matches[-1]['pos'][1] *= self.tile_size
                if not keep:
                    del self.tilemap[loc]
        
        return matches

    def tiles_around(self, pos):
        tiles = []
        tile_loc = (int(pos[0] // self.tile_size), int(pos[1] // self.tile_size))
        for offset in NEIGHBOR_OFFSET:
            check_loc = str(tile_loc[0] + offset[0]) + ';' + str(tile_loc[1] + offset[1])
            if check_loc in self.tilemap:
                tiles.append(self.tilemap[check_loc])
        return tiles

    def save(self, path):
        #print(f"Players: {self.players}")
        #print("-"*50)
        #print(f"Enemies: {self.enemies}")
        game_state = {}
        
        # Meta data
        meta_data = {
            'map': self.level,
            'timer': {
                'current_time': "00:00:00",
                'start_time': "00:00:00",
            }
        }

        entity_data = {
            'players': self.players,
            'enemies': self.enemies
        }
        
        # Map data
        tilemap_data = {
            'tilemap': self.tilemap,
            'tile_size': self.tile_size,
            'offgrid': self.offgrid_tiles
        }

        # Game data
        game_state['meta_data'] = meta_data
        game_state['entities_data'] = entity_data
        game_state['map_data'] = tilemap_data
        try:
            with open(path, 'w') as f:
                json.dump(game_state, f, indent=4)
            print(f"Tilemap saved under {path}")
        except Exception as e:
            print(f"Error saving tilemap: {e}")

    def load(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            map_data = data.get('map_data', data)  # Unterstützt alte und neue Formate
            self.tilemap = map_data['tilemap']
            self.tile_size = map_data['tile_size']
            self.offgrid_tiles = map_data['offgrid']

            # Load entities
            entities_data = data.get('entities_data', {})
            self.players = []
            self.enemies = []

            for player_data in entities_data.get('players', []):
                player = Player(self.game, player_data['pos'], (8, 15), id=player_data['id'])
                player.velocity = player_data['velocity']
                player.air_time = player_data['air_time']
                player.action = player_data['action']
                player.flip = player_data['flip']
                player.alive = player_data['alive']
                player.lifes = player_data['lifes']
                player.respawn_pos = player_data['respawn_pos']
                self.players.append(player)

            for enemy_data in entities_data.get('enemies', []):
                enemy = Enemy(self.game, enemy_data['pos'], (8, 15), id=enemy_data['id'])
                enemy.velocity = enemy_data['velocity']
                enemy.alive = enemy_data['alive']
                self.enemies.append(enemy)

            print(f"Tilemap geladen von {path}")
        except Exception as e:
            print(f"Fehler beim Laden der Tilemap: {e}")

    def solid_check(self, pos):
        tile_loc = str(int(pos[0] // self.tile_size)) + ';' + str(int(pos[1] // self.tile_size))
        if tile_loc in self.tilemap:
            if self.tilemap[tile_loc]['type'] in PHYSICS_TILES:
                return self.tilemap[tile_loc]

    def physics_rects_around(self, pos):
        rects = []
        for tile in self.tiles_around(pos):
            if tile['type'] in PHYSICS_TILES:
                rects.append(pygame.Rect(tile['pos'][0] * self.tile_size, 
                                         tile['pos'][1] * self.tile_size,
                                         self.tile_size, 
                                         self.tile_size))
        return rects

    def autotile(self):
        for loc in self.tilemap:
            tile = self.tilemap[loc]
            neighbors = set()
            for shift in [(1, 0), (-1, 0), (0, -1), (0, 1)]:
                check_loc = str(tile['pos'][0] + shift[0]) + ';' + str(tile['pos'][1] + shift[1])
                if check_loc in self.tilemap:
                    if self.tilemap[check_loc]['type'] == tile['type']:
                        neighbors.add(shift)
            neighbors = tuple(sorted(neighbors))
            if tile['type'] in AUTOTILE_TILES and neighbors in AUTOTILE_MAP:
                tile['variant'] = AUTOTILE_MAP[neighbors]

    def render(self, surf, offset=(0, 0)):
        for tile in self.offgrid_tiles:
            surf.blit(self.game.assets[tile['type']][tile['variant']], 
                      (tile['pos'][0] - offset[0], 
                       tile['pos'][1] - offset[1])) 

        for x in range(int(offset[0] // self.tile_size), int((offset[0] + surf.get_width()) // self.tile_size) + 1):
            for y in range(int(offset[1] // self.tile_size), int((offset[1] + surf.get_height()) // self.tile_size) + 1):
                loc = str(x) + ';' + str(y)
                if loc in self.tilemap:
                    tile = self.tilemap[loc]
                    surf.blit(self.game.assets[tile['type']][tile['variant']], 
                              (tile['pos'][0] * self.tile_size - offset[0], 
                               tile['pos'][1] * self.tile_size - offset[1]))