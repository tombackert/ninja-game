import os
import json
from scripts.collectables import Collectables
from scripts.utils import load_image
from scripts import settings

COIN_IMAGE_PATH = "collectables/coin.png"
DATA_FILE = "data/collectables.json"


class CollectableManager:

    PURCHASEABLES = {
        "Default",
        "Gun",
        "Ammo",
        "Red Ninja",
    }

    NOT_PURCHASEABLES = {
        "Shield",
        "Moon Boots",
        "Ninja Stars",
        "Red Ninja",
        "Gold Ninja",
        "Platinum Ninja",
        "Diamond Ninja",
        "Assassin",
        "Berserker",
    }

    SKINS = [
        "Default",
        "Red Ninja",
        "Gold Ninja",
        "Platinum Ninja",
        "Diamond Ninja",
        "Assassin",
        "Berserker",
    ]
    SKIN_PATHS = [
        "default",
        "red",
        "gold",
        "platinum",
        "diamond",
        "assassin",
        "berserker",
    ]

    WEAPONS = [
        "Default",
        "Gun",
        "Shield",
        "Rifle",
        "Moon Boots",
        "Ninja Stars",
        "Grapple Hook",
        "Sword",
    ]

    # Unified item price mapping (corrected 'Berserker' spelling)
    ITEMS = {
        "Gun": 500,
        "Ammo": 50,
        "Shield": 100,
        "Rifle": 2000,
        "Moon Boots": 2500,
        "Ninja Stars": 500,
        "Sword": 1000,
        "Grapple Hook": 5000,
        "Red Ninja": 1000,
        "Gold Ninja": 2000,
        "Platinum Ninja": 3000,
        "Diamond Ninja": 5000,
        "Assassin": 7000,
        "Berserker": 10000,
    }

    def __init__(self, game):
        self.coin_list = []
        self.game = game
        # Unified state fields persisted to JSON
        self.coins = 0
        self.gun = 0
        self.ammo = 0
        self.shield = 0
        self.moon_boots = 0
        self.ninja_stars = 0
        self.sword = 0
        self.grapple_hook = 0
        self.red_ninja = 0
        self.gold_ninja = 0
        self.platinum_ninja = 0
        self.diamond_ninja = 0
        self.assassin = 0
        self.berserker = 0
        # Load persisted values
        self.load_collectables()

        # Deprecated coin_count access removed (Issue 5 cleanup)

    def load_collectables_from_tilemap(self, tilemap):
        self.coin_list = []
        self.ammo_pickups = []

        coin_tiles = tilemap.extract([("coin", 0)], keep=False)
        for tile in coin_tiles:
            self.coin_list.append(
                Collectables(self.game, tile["pos"], self.game.assets["coin"])
            )

        ammo_tiles = tilemap.extract([("ammo", 0)], keep=False)
        for tile in ammo_tiles:
            self.ammo_pickups.append(
                Collectables(self.game, tile["pos"], self.game.assets["ammo"])
            )

    def update(self, player_rect):
        for coin in self.coin_list[:]:
            if coin.update(player_rect):
                self.coin_list.remove(coin)
                self.coins += 1
                self.game.sfx["collect"].play()

        for ammo in self.ammo_pickups[:]:
            if ammo.update(player_rect):
                self.ammo_pickups.remove(ammo)
                self.ammo += 5
                self.game.sfx["collect"].play()

    def render(self, surf, offset=(0, 0)):
        for coin in self.coin_list:
            coin.render(surf, offset=offset)

    def load_collectables(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                # Backward compatibility: coin_count -> coins
                self.coins = data.get("coins", data.get("coin_count", 0))
                self.gun = data.get("gun", 0)
                self.ammo = data.get("ammo", 0)
                self.shield = data.get("shield", 0)
                self.moon_boots = data.get("moon_boots", 0)
                self.ninja_stars = data.get("ninja_stars", 0)
                self.sword = data.get("sword", 0)
                self.grapple_hook = data.get("grapple_hook", 0)
                self.red_ninja = data.get("red_ninja", 0)
                self.gold_ninja = data.get("gold_ninja", 0)
                self.platinum_ninja = data.get("platinum_ninja", 0)
                self.diamond_ninja = data.get("diamond_ninja", 0)
                self.assassin = data.get("assassin", 0)
                # Accept both spellings for migration
                self.berserker = data.get("berserker", data.get("berzerker", 0))
            except (json.JSONDecodeError, IOError):
                # Ignore load errors; start with defaults
                pass

    def save_collectables(self):
        data = {
            "coins": self.coins,
            "gun": self.gun,
            "ammo": self.ammo,
            "shield": self.shield,
            "moon_boots": self.moon_boots,
            "ninja_stars": self.ninja_stars,
            "sword": self.sword,
            "grapple_hook": self.grapple_hook,
            "red_ninja": self.red_ninja,
            "gold_ninja": self.gold_ninja,
            "platinum_ninja": self.platinum_ninja,
            "diamond_ninja": self.diamond_ninja,
            "assassin": self.assassin,
            "berserker": self.berserker,
        }
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except IOError:
            pass

    def is_purchaseable(self, item):
        return item in self.PURCHASEABLES

    def buy_collectable(self, item):
        if self.is_purchaseable(item):
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
                elif item == "Gold Ninja":
                    self.gold_ninja += 1
                elif item == "Platinum Ninja":
                    self.platinum_ninja += 1
                elif item == "Diamond Ninja":
                    self.diamond_ninja += 1
                elif item == "Assassin":
                    self.assassin += 1
                elif item == "Berserker":
                    self.berserker += 1

                self.coins -= self.ITEMS[item]
                self.save_collectables()
                return "success"
            else:
                return "not enough coins"
        else:
            return "not purchaseable"

    def get_price(self, item):
        return self.ITEMS[item]

    def get_amount(self, item):
        mapping = {
            "Default": 1,
            "Gun": self.gun,
            "Ammo": self.ammo,
            "Shield": self.shield,
            "Moon Boots": self.moon_boots,
            "Ninja Stars": self.ninja_stars,
            "Sword": self.sword,
            "Grapple Hook": self.grapple_hook,
            "Red Ninja": self.red_ninja,
            "Gold Ninja": self.gold_ninja,
            "Platinum Ninja": self.platinum_ninja,
            "Diamond Ninja": self.diamond_ninja,
            "Assassin": self.assassin,
            "Berserker": self.berserker,
        }
        return mapping.get(item, 0)
