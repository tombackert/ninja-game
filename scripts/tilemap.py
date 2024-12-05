import pygame
import json
from scripts.entities import Enemy, Player
from settings import settings
from scripts.utils import Animation

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
        self.meta_data = {}

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
        game_state = {}

        meta_data = self.meta_data.copy()
        if not meta_data:
            meta_data = {
                'map': self.level,
                'timer': {
                    'current_time': "00:00:00",
                    'start_time': "00:00:00",
                }
            }

        entity_data = {
            'players': [{
                'id': player.id,
                'pos': player.pos,
                'velocity': player.velocity,
                'air_time': player.air_time,
                'action': player.action,
                'flip': player.flip,
                'alive': player.alive,
                'lifes': player.lifes,
                'respawn_pos': player.respawn_pos,
            } for player in self.players],
            'enemies': [{
                'id': enemy.id,
                'pos': enemy.pos,
                'velocity': enemy.velocity,
                'alive': enemy.alive
            } for enemy in self.enemies]
        }

        tilemap_data = {
            'tilemap': self.tilemap,
            'tile_size': self.tile_size,
            'offgrid': self.offgrid_tiles
        }

        game_state['meta_data'] = meta_data
        game_state['entities_data'] = entity_data
        game_state['map_data'] = tilemap_data

        try:
            with open(path, 'w') as f:
                json.dump(game_state, f, indent=4)
            print(f"Game saved under {path}")
            return True
        except Exception as e:
            print(f"Error saving tilemap: {e}")
            return False

    def load(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            self.meta_data = data.get('meta_data', {})
            self.level = self.meta_data.get('map', self.level)

            entities_data = data.get('entities_data', {})
            self.players = []
            self.enemies = []

            for player_data in entities_data.get('players', []):
                player = Player(self.game, player_data['pos'], (8, 15), e_id=player_data['id'],
                                lifes=player_data['lifes'], respawn_pos=player_data['respawn_pos'])
                player.velocity = player_data['velocity']
                player.air_time = player_data['air_time']
                player.action = player_data['action']
                player.flip = player_data['flip']
                player.alive = player_data['alive']
                player.respawn_pos = player_data['respawn_pos']
                self.players.append(player)

            for enemy_data in entities_data.get('enemies', []):
                enemy = Enemy(self.game, enemy_data['pos'], (8, 15), e_id=enemy_data['id'])
                enemy.velocity = enemy_data['velocity']
                enemy.alive = enemy_data['alive']
                self.enemies.append(enemy)

            map_data = data.get('map_data', data)
            self.tilemap = map_data['tilemap']
            self.tile_size = map_data['tile_size']
            self.offgrid_tiles = map_data['offgrid']

            print(f"Tilemap loaded from {path}")
        except Exception as e:
            print(f"Error while loading Tilemap: {e}")

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
            image = self.get_image(tile)
            if image:
                surf.blit(image, 
                        (tile['pos'][0] - offset[0], 
                        tile['pos'][1] - offset[1])) 

        for x in range(int(offset[0] // self.tile_size), int((offset[0] + surf.get_width()) // self.tile_size) + 1):
            for y in range(int(offset[1] // self.tile_size), int((offset[1] + surf.get_height()) // self.tile_size) + 1):
                loc = str(x) + ';' + str(y)
                if loc in self.tilemap:
                    tile = self.tilemap[loc]
                    image = self.get_image(tile)
                    if image:
                        surf.blit(image, 
                                (tile['pos'][0] * self.tile_size - offset[0], 
                                tile['pos'][1] * self.tile_size - offset[1]))

    def get_image(self, tile):
        asset = self.game.assets.get(tile['type'])
        if asset is None:
            print(f"Warning: Asset for tile type '{tile['type']}' not found.")
            return None
        
        if isinstance(asset, list):
            if 0 <= tile['variant'] < len(asset):
                return asset[tile['variant']]
            else:
                print(f"Warning: Variant index {tile['variant']} out of bounds for tile type '{tile['type']}'.")
                return None
        elif isinstance(asset, pygame.Surface):
            return asset
        elif isinstance(asset, Animation):
            frame = asset.get_current_frame()
            if isinstance(frame, pygame.Surface):
                return frame
            else:
                print(f"Warning: Animation frame is not a Surface for tile type '{tile['type']}'.")
                return None
        else:
            print(f"Warning: Unexpected asset type for tile type '{tile['type']}': {type(asset)}")
            return None

    