"""Tests for the store expansion: new weapons, gear and skins.

Covers purchase flow, weapon physics (rifle, ninja stars, sword, grapple)
and passive gear effects (shield, moon boots, coin magnet, lucky charm).
"""

import os

import pygame
import pytest

import scripts.collectableManager as cm_module
from game import Game
from scripts.collectableManager import CollectableManager
from scripts.collectables import Collectables
from scripts.constants import (
    AIR_JUMP_VELOCITY,
    GRAPPLE_PULL_SPEED,
    RIFLE_AMMO_COST,
    RIFLE_PROJECTILE_SPEED,
    STAR_GRAVITY,
    STAR_SPEED_X,
)
from scripts.entities import Enemy
from scripts.settings import settings

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


@pytest.fixture()
def game(tmp_path, monkeypatch):
    # Never touch the real save file from tests
    monkeypatch.setattr(cm_module, "DATA_FILE", str(tmp_path / "collectables.json"))
    g = Game()
    g.load_level(0)
    # Reset equip state and restore it afterwards
    old = (settings.selected_weapon, settings.selected_gear, settings.selected_skin)
    settings.selected_weapon = 0
    settings.selected_gear = 0
    settings.selected_skin = 0
    yield g
    settings.selected_weapon, settings.selected_gear, settings.selected_skin = old


def equip_weapon(name: str) -> None:
    settings.selected_weapon = CollectableManager.WEAPONS.index(name)


def equip_gear(name: str) -> None:
    settings.selected_gear = CollectableManager.GEAR.index(name)


# ---------------------------------------------------------------------------
# Store / registry
# ---------------------------------------------------------------------------


def test_all_items_purchaseable(game):
    cm = game.cm
    for name in cm._ITEM_DEFS:
        assert cm.is_purchaseable(name), f"{name} must be purchaseable in the store"


def test_buy_every_item_succeeds_and_persists(game):
    cm = game.cm
    for name, idef in cm._ITEM_DEFS.items():
        cm.coins = idef.price
        before = getattr(cm, idef.attr)
        assert cm.buy_collectable(name) == "success"
        assert getattr(cm, idef.attr) == before + idef.increment
        assert cm.coins == 0
    # Reload from (patched) disk file
    fresh = CollectableManager(None)
    assert fresh.rifle >= 1
    assert fresh.coin_magnet >= 1
    assert fresh.lucky_charm >= 1
    assert fresh.ninja_stars >= 20


def test_buy_without_coins_fails(game):
    cm = game.cm
    cm.coins = 0
    for name in ("Rifle", "Sword", "Grapple Hook", "Coin Magnet", "Berserker"):
        assert cm.buy_collectable(name) == "not enough coins"


def test_weapon_and_gear_lists_are_disjoint():
    assert set(CollectableManager.WEAPONS) & set(CollectableManager.GEAR) == set()
    # All non-default entries must exist in the item registry
    for entry in CollectableManager.WEAPONS[1:] + CollectableManager.GEAR[1:]:
        assert entry in CollectableManager._ITEM_DEFS


# ---------------------------------------------------------------------------
# Rifle
# ---------------------------------------------------------------------------


def test_rifle_consumes_two_ammo_and_spawns_fast_projectile(game):
    p = game.player
    game.cm.rifle = 1
    game.cm.ammo = 5
    p.shoot_cooldown = 0
    p.flip = False
    equip_weapon("Rifle")
    result = p.shoot()
    assert result is not None and result.spawned
    assert result.ammo_used == RIFLE_AMMO_COST
    assert game.cm.ammo == 5 - RIFLE_AMMO_COST
    projs = list(game.projectiles)
    assert len(projs) == 1
    assert projs[0]["vel"][0] == RIFLE_PROJECTILE_SPEED
    # Cooldown prevents immediate refire
    assert p.shoot_cooldown > 0
    assert p.shoot() is None


def test_rifle_requires_two_ammo(game):
    p = game.player
    game.cm.rifle = 1
    game.cm.ammo = 1  # not enough for one rifle shot
    p.shoot_cooldown = 0
    equip_weapon("Rifle")
    assert p.shoot() is None


# ---------------------------------------------------------------------------
# Ninja stars
# ---------------------------------------------------------------------------


def test_star_throw_consumes_star_and_arcs(game):
    p = game.player
    game.cm.ninja_stars = 2
    p.shoot_cooldown = 0
    p.flip = False
    equip_weapon("Ninja Stars")
    result = p.shoot()
    assert result is not None and result.spawned
    assert game.cm.ninja_stars == 1
    proj = list(game.projectiles)[0]
    assert proj["kind"] == "star"
    assert proj["pierce"] is True
    assert proj["vel"][0] == STAR_SPEED_X
    vy0 = proj["vel"][1]
    game.projectiles.update(game.tilemap, [], [])
    assert proj["vel"][1] == pytest.approx(vy0 + STAR_GRAVITY)


def test_star_pierces_enemies(game):
    p = game.player
    # Two enemies in a row far from tiles: spawn star directly between them
    e1 = Enemy(game, (p.pos[0] + 20, p.pos[1]), (8, 15), id=901)
    e2 = Enemy(game, (p.pos[0] + 30, p.pos[1]), (8, 15), id=902)
    game.enemies = [e1, e2]
    proj = game.projectiles.spawn(
        p.pos[0] + 15, p.pos[1] + 7, 3.0, "player", vy=0.0, gravity=0.0, kind="star", pierce=True
    )
    summary = game.projectiles.update(game.tilemap, [], game.enemies)
    assert summary["hits_enemy"] >= 1
    assert proj in list(game.projectiles), "piercing star must survive enemy hits"


def test_no_stars_no_throw(game):
    p = game.player
    game.cm.ninja_stars = 0
    p.shoot_cooldown = 0
    equip_weapon("Ninja Stars")
    assert p.shoot() is None


# ---------------------------------------------------------------------------
# Sword
# ---------------------------------------------------------------------------


def test_sword_kills_enemy_in_reach(game):
    p = game.player
    game.cm.sword = 1
    p.shoot_cooldown = 0
    p.flip = False
    equip_weapon("Sword")
    enemy = Enemy(game, (p.rect().right + 4, p.pos[1]), (8, 15), id=903)
    game.enemies = [enemy]
    coins_before = game.cm.coins
    result = p.shoot()
    assert result is not None and result.spawned
    assert game.enemies == []
    assert game.cm.coins == coins_before + 1
    assert result.ammo_used == 0
    assert p.slash_timer > 0  # VFX active


def test_sword_misses_enemy_behind(game):
    p = game.player
    game.cm.sword = 1
    p.shoot_cooldown = 0
    p.flip = False  # facing right
    equip_weapon("Sword")
    enemy = Enemy(game, (p.rect().left - 30, p.pos[1]), (8, 15), id=904)
    game.enemies = [enemy]
    p.shoot()
    assert game.enemies == [enemy], "enemy behind the player must survive"


def test_sword_destroys_enemy_projectiles(game):
    p = game.player
    game.cm.sword = 1
    p.shoot_cooldown = 0
    p.flip = False
    equip_weapon("Sword")
    game.projectiles.clear()
    game.projectiles.spawn(p.rect().right + 5, p.rect().centery, -1.0, "enemy")
    assert len(game.projectiles) == 1
    p.shoot()
    assert len(game.projectiles) == 0, "slash must parry enemy projectiles"


# ---------------------------------------------------------------------------
# Grapple hook
# ---------------------------------------------------------------------------


def _place_solid_tile(game, tile_x, tile_y):
    game.tilemap.tilemap[f"{tile_x};{tile_y}"] = {
        "type": "stone",
        "variant": 0,
        "pos": [tile_x, tile_y],
    }


def test_grapple_attaches_and_pulls(game):
    p = game.player
    game.cm.grapple_hook = 1
    p.shoot_cooldown = 0
    p.flip = False
    equip_weapon("Grapple Hook")
    # Clear space then place a wall 4 tiles to the right of the player
    tile_size = game.tilemap.tile_size
    tx = int(p.rect().centerx // tile_size) + 4
    ty = int(p.rect().centery // tile_size)
    _place_solid_tile(game, tx, ty)
    result = p.shoot()
    assert result is not None and result.spawned
    assert p.grapple_point is not None
    x_before = p.pos[0]
    p.update(game.tilemap, (0, 0))
    assert p.pos[0] > x_before, "player must be pulled toward the anchor"
    assert abs(p.velocity[0]) <= GRAPPLE_PULL_SPEED + 1e-6


def test_grapple_whiffs_without_target(game):
    p = game.player
    game.cm.grapple_hook = 1
    p.shoot_cooldown = 0
    p.flip = False
    equip_weapon("Grapple Hook")
    # Move player into open air far from tiles
    p.pos = [-4000.0, -4000.0]
    result = p.shoot()
    assert result is not None and not result.spawned
    assert p.grapple_point is None
    assert p.shoot_cooldown > 0  # whiff cooldown applies


def test_grapple_releases_on_jump(game):
    p = game.player
    p.grapple_point = [p.pos[0] + 50, p.pos[1]]
    assert p.jump() is True
    assert p.grapple_point is None
    assert p.velocity[1] == AIR_JUMP_VELOCITY


# ---------------------------------------------------------------------------
# Gear: moon boots, shield, coin magnet, lucky charm
# ---------------------------------------------------------------------------


def test_moon_boots_allow_one_air_jump(game):
    p = game.player
    game.cm.moon_boots = 1
    equip_gear("Moon Boots")
    p.jumps = 0  # already used ground jump
    p.air_jumps = 1
    p.wall_slide = False
    assert p.jump() is True
    assert p.velocity[1] == AIR_JUMP_VELOCITY
    assert p.air_jumps == 0
    assert p.jump() is None or p.jump() is False or not p.jump()


def test_no_air_jump_without_moon_boots(game):
    p = game.player
    game.cm.moon_boots = 0
    equip_gear("None")
    p.jumps = 0
    p.air_jumps = 1
    assert not p.jump()


def test_shield_absorbs_hit_and_consumes_charge(game):
    p = game.player
    game.cm.shield = 1
    equip_gear("Shield")
    p.shield_ready = False
    p.shield_rearm = 0
    p.update(game.tilemap, (0, 0))  # arms the shield
    assert p.shield_ready is True
    lives_before = p.lives
    game.projectiles.clear()
    game.projectiles.spawn(p.rect().centerx, p.rect().centery, 0.5, "enemy")
    summary = game.projectiles.update(game.tilemap, [p], [])
    assert summary["hits_player"] == 1
    assert p.lives == lives_before, "shield must absorb the hit"
    assert game.cm.shield == 0
    assert p.shield_ready is False


def test_hit_without_shield_costs_life(game):
    p = game.player
    game.cm.shield = 0
    equip_gear("None")
    p.shield_ready = False
    lives_before = p.lives
    game.projectiles.clear()
    game.projectiles.spawn(p.rect().centerx, p.rect().centery, 0.5, "enemy")
    game.projectiles.update(game.tilemap, [p], [])
    assert p.lives == lives_before - 1


def test_coin_magnet_pulls_coins(game):
    p = game.player
    game.cm.coin_magnet = 1
    equip_gear("Coin Magnet")
    coin = Collectables(game, (p.rect().centerx + 30, p.rect().centery), game.assets["coin"])
    game.cm.coin_list = [coin]
    x_before = coin.pos[0]
    game.cm.update(p.rect())
    assert coin.pos[0] < x_before, "coin must move toward the player"


def test_coin_magnet_ignores_far_coins(game):
    p = game.player
    game.cm.coin_magnet = 1
    equip_gear("Coin Magnet")
    coin = Collectables(game, (p.rect().centerx + 500, p.rect().centery), game.assets["coin"])
    game.cm.coin_list = [coin]
    x_before = coin.pos[0]
    game.cm.update(p.rect())
    assert coin.pos[0] == x_before


def test_lucky_charm_grants_extra_life(game):
    game.cm.lucky_charm = 1
    equip_gear("Lucky Charm")
    game.load_level(0)
    assert game.player.lives == 4  # 3 default + 1 charm
    equip_gear("None")
    game.load_level(0)
    assert game.player.lives == 3


# ---------------------------------------------------------------------------
# Skins
# ---------------------------------------------------------------------------


def test_all_skin_assets_registered(game):
    for skin_path in CollectableManager.SKIN_PATHS:
        for action in ("idle", "run", "jump", "slide", "wall_slide"):
            assert f"player/{skin_path}/{action}" in game.assets


def test_player_uses_selected_skin_animation(game):
    p = game.player
    for skin_idx in range(len(CollectableManager.SKIN_PATHS)):
        p.skin = skin_idx
        p.action = ""  # force set_action to rebuild animation
        p.set_action("idle")
        assert p.animation is not None


# ---------------------------------------------------------------------------
# Settings migration
# ---------------------------------------------------------------------------


def test_settings_clamp_out_of_range_equips(tmp_path, monkeypatch):
    import json

    from scripts.settings import Settings

    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"selected_weapon": 99, "selected_gear": 42, "selected_skin": -3}))
    monkeypatch.setattr(Settings, "SETTINGS_FILE", str(cfg))
    s = Settings()
    assert s.selected_weapon == 0
    assert s.selected_gear == 0
    assert s.selected_skin == 0
