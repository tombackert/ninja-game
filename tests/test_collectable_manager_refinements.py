import pygame
import os
from game import Game
from scripts.collectableManager import CollectableManager

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


def test_unknown_item_validation():
    g = Game()
    cm: CollectableManager = g.cm
    cm.coins = 9999
    assert cm.buy_collectable("Nonexistent") == "unknown item"


def test_owned_lists():
    g = Game()
    cm: CollectableManager = g.cm
    cm.coins = 5000
    assert "Red Ninja" not in cm.list_owned_skins()
    assert cm.buy_collectable("Gun") == "success"
    assert "Gun" in cm.list_owned_weapons()
    assert cm.buy_collectable("Red Ninja") == "success"
    skins = cm.list_owned_skins()
    assert "Red Ninja" in skins
    assert skins[0] == "Default"
