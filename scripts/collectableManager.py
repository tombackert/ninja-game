import os
import json
from scripts.collectables import Collectables
from scripts.utils import load_image

COIN_IMAGE_PATH = 'collectables/coin.png'
DATA_FILE = 'data/collectables.json'


class CollectableManager:
    def __init__(self, game, coin_image_path=COIN_IMAGE_PATH, data_file=DATA_FILE):
        self.coins = []
        self.game = game
        self.data_file = data_file
        self.coin_image_path = coin_image_path
        self.coin_count = self.load_collectable_count()

    def load_collectable_count(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                return data.get('coin_count', 0)
        else:
            with open(self.data_file, 'w') as f:
                json.dump({"coin_count": 0}, f, indent=4)
            return 0

    def save_collectable_count(self):
        with open(self.data_file, 'w') as f:
            json.dump({"coin_count": self.coin_count}, f, indent=4)

    def load_coins_from_tilemap(self, tilemap, coin_id_pairs=[('coin', 0)]):
        self.coins.clear()
        coin_tiles = tilemap.extract(coin_id_pairs)
        for coin_tile in coin_tiles:
            c = Collectables(self.game, coin_tile['pos'], self.game.assets['coin'])
            self.coins.append(c)

    def update(self, player_rect):
        removed = 0
        for coin in self.coins.copy():
            if coin.update(player_rect):
                self.coins.remove(coin)
                self.coin_count += 1
                removed += 1
        if removed > 0:
            self.game.sfx['collect'].play()
            self.save_collectable_count()

    def render(self, surf, offset=(0,0)):
        for coin in self.coins:
            coin.render(surf, offset=offset)