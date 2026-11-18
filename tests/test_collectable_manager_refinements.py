import os

import pygame

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
    cm.red_ninja = 0  # the test save is a copy of the player's own
    assert "Homura" not in cm.list_owned_skins()
    assert cm.buy_collectable("Gun") == "success"
    assert "Gun" in cm.list_owned_weapons()
    assert cm.buy_collectable("Homura") == "success"
    skins = cm.list_owned_skins()
    assert "Homura" in skins
    assert skins[0] == "Default"
