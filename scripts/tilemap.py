class Tilemap:
    def __init__(self, game, tile_size=16):
        self.game = game
        self.tile_size = tile_size
        self.tilemap = {}
        self.offgrid_tiles = []

        for i in range(10):
            self.tilemap[str(3 + i) + ';10'] = {'type': 'grass', 
                                                'variant': 1, 
                                                'pos': (3 + i, 10)}
            self.tilemap[';10' + str(i + 5)] = {'type': 'stone', 
                                                'variant': 1, 
                                                'pos': (10, 5 + i)}


    def render(self, surf):
        for tile in self.offgrid_tiles:
            surf.blit(self.game.assets[tile['type']][tile['variant']], tile['pos'])

        for loc in self.tilemap:
            tile = self.tilemap[loc]
            surf.blit(self.game.assets[tile['type']][tile['variant']], 
                      (tile['pos'][0] * self.tile_size, 
                       tile['pos'][1] * self.tile_size))
        
        