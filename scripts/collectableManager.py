import os
import json
from dataclasses import dataclass
from typing import Dict, Optional, List
from scripts.collectables import Collectables

COIN_IMAGE_PATH = "collectables/coin.png"
DATA_FILE = "data/collectables.json"


@dataclass(frozen=True)
class ItemDef:
    name: str
    attr: str
    price: int
    category: str  # 'weapon' | 'skin' | 'utility'
    purchaseable: bool
    increment: int = 1  # amount to add on successful purchase


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

    # Centralized item registry (Issue 6 refinement)
    _ITEM_DEFS: Dict[str, ItemDef] = {
        # Weapons / utilities
        "Gun": ItemDef("Gun", "gun", 500, "weapon", True, 1),
        "Ammo": ItemDef("Ammo", "ammo", 50, "weapon", True, 25),
        "Shield": ItemDef("Shield", "shield", 100, "weapon", False, 1),
        "Rifle": ItemDef("Rifle", "gun", 2000, "weapon", False, 1),  # shares attr?
        "Moon Boots": ItemDef("Moon Boots", "moon_boots", 2500, "weapon", False, 1),
        "Ninja Stars": ItemDef("Ninja Stars", "ninja_stars", 500, "weapon", False, 3),
        "Sword": ItemDef("Sword", "sword", 1000, "weapon", False, 1),
        "Grapple Hook": ItemDef("Grapple Hook", "grapple_hook", 5000, "weapon", False, 1),
        # Skins
        "Red Ninja": ItemDef("Red Ninja", "red_ninja", 1000, "skin", True, 1),
        "Gold Ninja": ItemDef("Gold Ninja", "gold_ninja", 2000, "skin", False, 1),
        "Platinum Ninja": ItemDef("Platinum Ninja", "platinum_ninja", 3000, "skin", False, 1),
        "Diamond Ninja": ItemDef("Diamond Ninja", "diamond_ninja", 5000, "skin", False, 1),
        "Assassin": ItemDef("Assassin", "assassin", 7000, "skin", False, 1),
        "Berserker": ItemDef("Berserker", "berserker", 10000, "skin", False, 1),
    }

    # Derived price mapping kept for backward compatibility (tests & menu store)
    ITEMS = {name: idef.price for name, idef in _ITEM_DEFS.items()}

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
            self.coin_list.append(Collectables(self.game, tile["pos"], self.game.assets["coin"]))

        ammo_tiles = tilemap.extract([("ammo", 0)], keep=False)
        for tile in ammo_tiles:
            self.ammo_pickups.append(Collectables(self.game, tile["pos"], self.game.assets["ammo"]))

    def update(self, player_rect):
        for coin in self.coin_list[:]:
            if coin.update(player_rect):
                self.coin_list.remove(coin)
                self.coins += 1
                self.game.audio.play("collect")

        for ammo in self.ammo_pickups[:]:
            if ammo.update(player_rect):
                self.ammo_pickups.remove(ammo)
                self.ammo += 5
                self.game.audio.play("collect")

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

    def is_purchaseable(self, item: str) -> bool:
        idef = self._ITEM_DEFS.get(item)
        return bool(idef and idef.purchaseable)

    def validate_item(self, item: str) -> bool:
        return item in self._ITEM_DEFS

    def get_item_def(self, item: str) -> Optional[ItemDef]:
        return self._ITEM_DEFS.get(item)

    def buy_collectable(self, item: str) -> str:
        idef = self.get_item_def(item)
        if not idef:
            return "unknown item"
        if not idef.purchaseable:
            return "not purchaseable"
        if self.coins < idef.price:
            return "not enough coins"
        current_val = getattr(self, idef.attr, 0)
        setattr(self, idef.attr, current_val + idef.increment)
        self.coins -= idef.price
        self.save_collectables()
        return "success"

    def get_price(self, item: str) -> int:
        if item not in self.ITEMS:
            raise KeyError(f"Unknown item '{item}'")
        return self.ITEMS[item]

    def get_amount(self, item: str) -> int:
        if item == "Default":
            return 1
        idef = self.get_item_def(item)
        if not idef:
            return 0
        return int(getattr(self, idef.attr, 0))

    # Ownership listing helpers
    def list_owned_skins(self) -> List[str]:
        owned = ["Default"]
        for skin in self.SKINS:
            if skin == "Default":
                continue
            if self.get_amount(skin) > 0:
                owned.append(skin)
        return owned

    def list_owned_weapons(self) -> List[str]:
        owned = ["Default"]
        for w in self.WEAPONS:
            if w == "Default":
                continue
            # Some weapons share attributes (e.g., Rifle -> gun).
            # If their attr > 0 consider owned.
            if w in self._ITEM_DEFS:
                idef = self._ITEM_DEFS[w]
                if getattr(self, idef.attr, 0) > 0:
                    owned.append(w)
        return owned
