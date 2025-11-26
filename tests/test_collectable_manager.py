import json
import os

import pygame

from game import Game
from scripts.collectableManager import DATA_FILE, CollectableManager

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


def setup_module(module):
    # Ensure fresh data file
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)


def test_buy_collectable_success(tmp_path, monkeypatch):
    g = Game()
    cm = g.cm
    cm.coins = 1000  # enough for Gun and Ammo
    result_gun = cm.buy_collectable("Gun")
    assert result_gun == "success"
    assert cm.gun == 1
    assert cm.coins == 1000 - cm.ITEMS["Gun"]

    # Persist and reload
    cm.save_collectables()
    re = CollectableManager(g)
    assert re.gun == 1
    assert re.coins == cm.coins  # coins persisted under 'coins'


def test_buy_collectable_insufficient_funds():
    g = Game()
    cm = g.cm
    cm.coins = 10
    initial_gun = cm.gun
    price = cm.ITEMS["Gun"]
    assert price > cm.coins
    result = cm.buy_collectable("Gun")
    assert result == "not enough coins"
    assert cm.gun == initial_gun  # unchanged


def test_backward_compat_coin_count(monkeypatch, tmp_path):
    # Write legacy file
    legacy = {"coin_count": 42, "gun": 1}
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(legacy, f)
    g = Game()
    cm = g.cm
    assert cm.coins == 42
    assert cm.gun == 1
