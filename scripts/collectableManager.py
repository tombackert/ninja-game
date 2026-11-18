import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

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


@dataclass(frozen=True)
class SkinDef:
    name: str  # item name (store, ownership, equip lists)
    path: str  # folder under data/images/entities/player
    title: str  # full name shown in the menus
    description: str
    attr: str = ""  # ownership counter in collectables.json ("" = always owned)
    price: int = 0


# Store order = equip index (settings.selected_skin), so new skins go last.
# The save keys (attr) are those of the skins each one replaced, so players
# keep what they bought: Red Ninja -> Homura, ..., Berserker -> Oni.
SKIN_DEFS: List[SkinDef] = [
    SkinDef("Default", "default", "Ninja (Default)", "The classic ninja with the red headband."),
    SkinDef(
        "Homura",
        "homura",
        "Homura (Flame Ninja)",
        "His hair is on fire. Sparks rise and the ends of his headband glow.",
        "red_ninja",
        1000,
    ),
    SkinDef(
        "Shogun",
        "shogun",
        "Shogun (Golden Samurai)",
        "Lacquered helmet with a golden crest, lamellar armor and a banner on his back. "
        "A shine sweeps over the gold.",
        "gold_ninja",
        2000,
    ),
    SkinDef(
        "Chrome",
        "chrome",
        "Chrome (Cyber Ninja)",
        "Polished steel with a scanning visor, a blinking antenna and energy ribbons. " "Thrusters fire when he jumps.",
        "platinum_ninja",
        3000,
    ),
    SkinDef(
        "Crystal",
        "crystal",
        "Crystal (Diamond Ninja)",
        "Cut from diamond: a crystal crown, a shard on the shoulder and a sparkle that wanders over the body.",
        "diamond_ninja",
        5000,
    ),
    SkinDef(
        "Shadow",
        "shadow",
        "Shadow (Assassin)",
        "Under the hood only a red eye glows. The tattered cloak flies behind him when he runs.",
        "assassin",
        7000,
    ),
    SkinDef(
        "Oni",
        "oni",
        "Oni (Demon)",
        "Red demon mask with horns and fangs, a wild white mane and a tiger-skin loincloth.",
        "berserker",
        10000,
    ),
    SkinDef(
        "Kitsune",
        "kitsune",
        "Kitsune (Fox Spirit)",
        "White fox mask, pointed ears and two fluffy tails that stream behind her when she runs.",
        "kitsune",
        12000,
    ),
]

# What each weapon and gear item does (store and accessories cards)
ITEM_DESCRIPTIONS = {
    "Default": "Your dash. Dash into enemies to defeat them.",
    "Gun": "Shoots straight ahead. Each shot uses one bullet.",
    "Ammo": "25 bullets for the gun and the rifle.",
    "Rifle": "Fast, far-reaching shots. Uses 2 bullets per shot and reloads slowly.",
    "Ninja Stars": "20 throwing stars. They fly in an arc and pierce every enemy in their path.",
    "Sword": "Close-range slash that defeats enemies and cuts their bullets out of the air.",
    "Grapple Hook": "Hooks onto walls and ceilings and pulls you there. Deals no damage.",
    "None": "No gear equipped.",
    "Shield": "One charge blocks one hit. Re-arms after 10 seconds while charges are left.",
    "Moon Boots": "One extra jump in the air.",
    "Coin Magnet": "Pulls nearby coins to you.",
    "Lucky Charm": "One extra life at the start of each level.",
}

# Small sprite shown on an item's card (path under data/images)
ITEM_ICONS = {
    "Gun": "gun.png",
    "Ammo": "projectile.png",
    "Rifle": "rifle.png",
    "Ninja Stars": "star.png",
    "Sword": "sword.png",
    "Grapple Hook": "hook.png",
    "Coin Magnet": "collectables/coin/0.png",
}

# Folder names of the skins replaced by the ones above (old replays name them)
LEGACY_SKIN_PATHS = {
    "red": "homura",
    "gold": "shogun",
    "platinum": "chrome",
    "diamond": "crystal",
    "assassin": "shadow",
    "berserker": "oni",
}


class CollectableManager:
    SKINS = [d.name for d in SKIN_DEFS]
    SKIN_PATHS = [d.path for d in SKIN_DEFS]
    SKIN_INFO = {d.name: d for d in SKIN_DEFS}

    @classmethod
    def skin_index(cls, path: str) -> int:
        """Equip index of a skin folder name (also the replaced skins' names); 0 if unknown."""
        path = LEGACY_SKIN_PATHS.get(path, path)
        return cls.SKIN_PATHS.index(path) if path in cls.SKIN_PATHS else 0

    @classmethod
    def display_name(cls, item: str) -> str:
        info = cls.SKIN_INFO.get(item)
        return info.title if info else item

    # Active weapons (single equip slot, index = settings.selected_weapon)
    WEAPONS = [
        "Default",
        "Gun",
        "Rifle",
        "Ninja Stars",
        "Sword",
        "Grapple Hook",
    ]

    # Passive gear (single equip slot, index = settings.selected_gear)
    GEAR = [
        "None",
        "Shield",
        "Moon Boots",
        "Coin Magnet",
        "Lucky Charm",
    ]

    # Centralized item registry (Issue 6 refinement)
    _ITEM_DEFS: Dict[str, ItemDef] = {
        # Weapons
        "Gun": ItemDef("Gun", "gun", 500, "weapon", True, 1),
        "Ammo": ItemDef("Ammo", "ammo", 50, "weapon", True, 25),
        "Rifle": ItemDef("Rifle", "rifle", 2000, "weapon", True, 1),
        "Ninja Stars": ItemDef("Ninja Stars", "ninja_stars", 300, "weapon", True, 20),
        "Sword": ItemDef("Sword", "sword", 1000, "weapon", True, 1),
        "Grapple Hook": ItemDef("Grapple Hook", "grapple_hook", 5000, "weapon", True, 1),
        # Gear (passive)
        "Shield": ItemDef("Shield", "shield", 100, "gear", True, 1),
        "Moon Boots": ItemDef("Moon Boots", "moon_boots", 2500, "gear", True, 1),
        "Coin Magnet": ItemDef("Coin Magnet", "coin_magnet", 1500, "gear", True, 1),
        "Lucky Charm": ItemDef("Lucky Charm", "lucky_charm", 3000, "gear", True, 1),
        # Skins
        **{d.name: ItemDef(d.name, d.attr, d.price, "skin", True, 1) for d in SKIN_DEFS if d.attr},
    }

    # Legacy sets kept for backward compatibility (derived from registry)
    PURCHASEABLES = {name for name, idef in _ITEM_DEFS.items() if idef.purchaseable}
    NOT_PURCHASEABLES = {name for name, idef in _ITEM_DEFS.items() if not idef.purchaseable}

    # Derived price mapping kept for backward compatibility (tests & menu store)
    ITEMS = {name: idef.price for name, idef in _ITEM_DEFS.items()}

    def __init__(self, game):
        self.coin_list = []
        self.game = game
        # Unified state fields persisted to JSON
        self.coins = 0
        self.gun = 0
        self.ammo = 0
        self.rifle = 0
        self.shield = 0
        self.moon_boots = 0
        self.coin_magnet = 0
        self.lucky_charm = 0
        self.ninja_stars = 0
        self.sword = 0
        self.grapple_hook = 0
        self.red_ninja = 0
        self.gold_ninja = 0
        self.platinum_ninja = 0
        self.diamond_ninja = 0
        self.assassin = 0
        self.berserker = 0
        self.kitsune = 0
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
        self._apply_coin_magnet(player_rect)
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

    def _apply_coin_magnet(self, player_rect):
        """Pull nearby coins toward the player when Coin Magnet gear is equipped."""
        from scripts.constants import MAGNET_PULL_SPEED, MAGNET_RADIUS
        from scripts.settings import settings  # lazy import (no circular at module load)

        try:
            gear_name = self.GEAR[settings.selected_gear]
        except (IndexError, AttributeError):
            return
        if gear_name != "Coin Magnet" or self.coin_magnet <= 0:
            return
        px, py = player_rect.centerx, player_rect.centery
        for coin in self.coin_list:
            cx = coin.pos[0] + coin.size[0] / 2
            cy = coin.pos[1] + coin.size[1] / 2
            dx, dy = px - cx, py - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if 0 < dist <= MAGNET_RADIUS:
                step = min(MAGNET_PULL_SPEED, dist)
                coin.pos[0] += dx / dist * step
                coin.pos[1] += dy / dist * step
                coin.rect.topleft = (coin.pos[0], coin.pos[1])

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
                self.rifle = data.get("rifle", 0)
                self.shield = data.get("shield", 0)
                self.moon_boots = data.get("moon_boots", 0)
                self.coin_magnet = data.get("coin_magnet", 0)
                self.lucky_charm = data.get("lucky_charm", 0)
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
                self.kitsune = data.get("kitsune", 0)
            except (json.JSONDecodeError, IOError):
                # Ignore load errors; start with defaults
                pass

    def save_collectables(self):
        data = {
            "coins": self.coins,
            "gun": self.gun,
            "ammo": self.ammo,
            "rifle": self.rifle,
            "shield": self.shield,
            "moon_boots": self.moon_boots,
            "coin_magnet": self.coin_magnet,
            "lucky_charm": self.lucky_charm,
            "ninja_stars": self.ninja_stars,
            "sword": self.sword,
            "grapple_hook": self.grapple_hook,
            "red_ninja": self.red_ninja,
            "gold_ninja": self.gold_ninja,
            "platinum_ninja": self.platinum_ninja,
            "diamond_ninja": self.diamond_ninja,
            "assassin": self.assassin,
            "berserker": self.berserker,
            "kitsune": self.kitsune,
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
        if idef.category == "skin" and getattr(self, idef.attr, 0) > 0:
            return "already owned"
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
        if item in ("Default", "None"):
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
            if w in self._ITEM_DEFS:
                idef = self._ITEM_DEFS[w]
                if getattr(self, idef.attr, 0) > 0:
                    owned.append(w)
        return owned

    def list_owned_gear(self) -> List[str]:
        owned = ["None"]
        for g in self.GEAR:
            if g == "None":
                continue
            if g in self._ITEM_DEFS and self.get_amount(g) > 0:
                owned.append(g)
        return owned
