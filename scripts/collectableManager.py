import os
import json
from scripts.collectables import Collectables
from scripts.utils import load_image
from scripts import settings

COIN_IMAGE_PATH = 'collectables/coin.png'
DATA_FILE = 'data/collectables.json'


class CollectableManager:

    PURCHASEABLES = {
        "Gun", 
        "Ammo"
    }
    NOT_PURCHASEABLES = {
        "Shield", 
        "Moon Boots", 
        "Ninja Stars", 
        "Sword", 
        "Grapple Hook", 
        "Red Ninja", 
        "Blue Ninja", 
        "Green Ninja"
    }


    ITEMS = {
        "Gun": 2500,
        "Ammo": 100,
        "Shield": 100,
        "Moon Boots": 5000,
        "Ninja Stars": 500,
        "Sword": 1000,
        "Grapple Hook": 5000,
        "Red Ninja": 1000,
        "Gold Ninja": 2000,
        "Platinum Ninja": 3000,
        "Diamond Ninja": 5000,
        "Assassin": 7000,
        "Berzerker": 10000,
    }

    def __init__(self, game):
        self.coin_list = []
        self.game = game
        self.coin_count = self.load_collectable_count()
        self.coins = 0
        self.gun = 0
        self.ammo = 0
        self.shield = 0
        self.moon_boots = 0
        self.ninja_stars = 0
        self.sword = 0
        self.grapple_hook = 0
        self.red_ninja = 0
        self.blue_ninja = 0
        self.green_ninja = 0

    ### DEPRECATED ###
    def load_collectable_count(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return data.get('coin_count', 0)
        else:
            with open(DATA_FILE, 'w') as f:
                json.dump({"coin_count": 0}, f, indent=4)
            return 0

    ### DEPRECATED ###
    def save_collectable_count(self):
        with open(DATA_FILE, 'w') as f:
            json.dump({"coin_count": self.coin_count}, f, indent=4)

    def load_collectables_from_tilemap(self, tilemap):
        self.coin_list = []
        self.ammo_pickups = []
        
        coin_tiles = tilemap.extract([('coin', 0)], keep=False)
        for tile in coin_tiles:
            self.coin_list.append(Collectables(self.game, tile['pos'], self.game.assets['coin']))
        
        ammo_tiles = tilemap.extract([('ammo', 0)], keep=False)
        for tile in ammo_tiles:
            self.ammo_pickups.append(Collectables(self.game, tile['pos'], self.game.assets['ammo']))

    def update(self, player_rect):
        for coin in self.coin_list[:]:
            if coin.update(player_rect):
                self.coin_list.remove(coin)
                self.coin_count += 1
                self.coins += 1
                self.game.sfx['collect'].play()
        
        for ammo in self.ammo_pickups[:]:
            if ammo.update(player_rect):
                self.ammo_pickups.remove(ammo)
                self.ammo += 5
                self.game.sfx['collect'].play()

    def render(self, surf, offset=(0,0)):
        for coin in self.coin_list:
            coin.render(surf, offset=offset)


    def load_collectables(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                    self.coins = data.get("coin_count", 0)
                    self.gun = data.get("gun", 0)
                    self.ammo = data.get("ammo", 0)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading collectable: {e}")
    
    def save_collectables(self):
        data = {
            "coin_count": self.coins,
            "gun": self.gun,
            "ammo": self.ammo
        }
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Error saving collectable: {e}")

    def is_purchaseable(self, item):
        return item in self.PURCHASEABLES
    
    def buy_collectable(self, item):

        if self.is_purchaseable(item):
            self.load_collectables()
            if self.coins >= self.ITEMS[item]:
                if item == "Gun":
                    self.gun += 1
                elif item == "Ammo":
                    self.ammo += 25
                elif item == "Shield":
                    self.shield += 1
                elif item == "Moon Boots":
                    self.moon_boots += 1
                elif item == "Ninja Stars":
                    self.ninja_stars += 3
                elif item == "Sword":
                    self.sword += 1
                elif item == "Grapple Hook":
                    self.grapple_hook += 1
                elif item == "Red Ninja":
                    self.red_ninja += 1
                elif item == "Blue Ninja":
                    self.blue_ninja += 1
                elif item == "Green Ninja":
                    self.green_ninja += 1
                
                self.coins -= self.ITEMS[item]
                self.save_collectables()
                return "success"
            else:
                print("Not enough coins!")
                return "not enough coins"
        else:
            print(f"{item} is not purchaseable!")
            return "not purchaseable"

    def get_price(self, item):
        return self.ITEMS[item]
    
    def get_amount(self, item):
        if item == "Gun":
            return self.gun
        elif item == "Ammo":
            return self.ammo
        elif item == "Shield":
            return self.shield
        elif item == "Moon Boots":
            return self.moon_boots
        elif item == "Ninja Stars":
            return self.ninja_stars
        elif item == "Sword":
            return self.sword
        elif item == "Grapple Hook":
            return self.grapple_hook
        elif item == "Red Ninja":
            return self.red_ninja
        elif item == "Blue Ninja":
            return self.blue_ninja
        elif item == "Green Ninja":
            return self.green_ninja
        else:
            return 0