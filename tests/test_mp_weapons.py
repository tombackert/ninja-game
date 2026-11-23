"""Multiplayer weapons: every player brings the weapon equipped in single
player, if they own it (scripts/weapons/loadout.py)."""

from __future__ import annotations

import os

import pygame
import pytest

os.environ["NINJA_GAME_TESTING"] = "1"

from scripts.collectableManager import CollectableManager  # noqa: E402
from scripts.constants import RIFLE_AMMO_COST  # noqa: E402
from scripts.entities import Enemy  # noqa: E402
from scripts.network.delta import apply_delta, compute_delta  # noqa: E402
from scripts.network.headless_game import HeadlessGame  # noqa: E402
from scripts.settings import settings  # noqa: E402
from scripts.snapshot import SnapshotService  # noqa: E402
from scripts.weapons.loadout import brought_weapon  # noqa: E402


@pytest.fixture(autouse=True)
def init_pygame():
    pygame.init()
    yield


@pytest.fixture()
def selected_weapon():
    old = settings.selected_weapon

    def select(name: str) -> None:
        settings.selected_weapon = CollectableManager.WEAPONS.index(name)

    yield select
    settings.selected_weapon = old


class _Inventory:
    gun = 0
    rifle = 0
    ninja_stars = 0
    sword = 0
    grapple_hook = 0


def _game(*weapons: str) -> HeadlessGame:
    hg = HeadlessGame(level=0)
    hg.collectables = {}
    hg.enemies = []
    for i, weapon in enumerate(weapons, start=1):
        p = hg.add_player(i, weapon=weapon)
        p.shoot_cooldown = 0
        p.pos = [100.0 + 40 * i, p.pos[1]]
    return hg


# --- What a player brings ----------------------------------------------------------------


def test_a_player_brings_the_equipped_weapon_they_own(selected_weapon):
    inv = _Inventory()
    inv.rifle = 1
    selected_weapon("Rifle")
    assert brought_weapon(inv) == "Rifle"


def test_an_equipped_weapon_not_owned_is_left_at_home(selected_weapon):
    selected_weapon("Sword")
    assert brought_weapon(_Inventory()) == "Default"


def test_no_weapon_equipped_brings_none(selected_weapon):
    inv = _Inventory()
    inv.gun = 1
    selected_weapon("Default")
    assert brought_weapon(inv) == "Default"


# --- The server fires each player's own weapon -------------------------------------------


def test_without_a_weapon_nobody_shoots():
    hg = _game("Default")
    p = hg.players[0]
    assert not hg.player_shoot(p)
    assert len(hg.projectiles) == 0 and p.mp_ammo == HeadlessGame.MP_START_AMMO


def test_the_gun_shoots_with_the_players_ammo_and_id():
    hg = _game("Gun")
    p = hg.players[0]
    assert hg.player_shoot(p)
    (proj,) = list(hg.projectiles)
    assert proj["owner_id"] == p.id
    assert p.mp_ammo == HeadlessGame.MP_START_AMMO - 1


def test_the_rifle_costs_its_ammo():
    hg = _game("Rifle")
    p = hg.players[0]
    assert hg.player_shoot(p)
    assert p.mp_ammo == HeadlessGame.MP_START_AMMO - RIFLE_AMMO_COST


def test_stars_are_thrown_from_the_ammo():
    hg = _game("Ninja Stars")
    p = hg.players[0]
    assert hg.player_shoot(p)
    (proj,) = list(hg.projectiles)
    assert proj["kind"] == "star" and proj["owner_id"] == p.id
    assert p.mp_ammo == HeadlessGame.MP_START_AMMO - 1


def test_weapons_do_not_follow_the_hosts_settings(selected_weapon):
    selected_weapon("Gun")
    hg = _game("Sword")
    assert hg.player_shoot(hg.players[0])
    assert len(hg.projectiles) == 0  # slashed, not shot


def test_the_sword_kills_enemies_and_hits_players_in_reach():
    hg = _game("Sword", "Default")
    a, b = hg.players
    b.pos = [a.pos[0] + 10, a.pos[1]]
    a.flip = False
    e = Enemy(hg, (a.pos[0] + 6, a.pos[1]), (8, 15), 999, kind="patrol")
    hg.enemies = [e]
    lives = b.lives
    assert hg.player_shoot(a)
    assert e not in hg.enemies and a.mp_coins == 1
    assert b.lives == lives - 1


def test_the_grapple_hooks_into_a_wall():
    hg = _game("Grapple Hook")
    p = hg.players[0]
    weapon_hits = []
    for flip in (False, True):
        p.flip = flip
        p.shoot_cooldown = 0
        p.grapple_point = None
        hg.player_shoot(p)
        weapon_hits.append(p.grapple_point)
    # level 0 has a wall within reach on at least one side of the spawn
    assert any(point is not None for point in weapon_hits)


# --- Clients learn who holds what --------------------------------------------------------


def test_snapshots_carry_the_weapon_and_the_grapple():
    hg = _game("Grapple Hook", "Default")
    before = SnapshotService.capture(hg, include_rng=False)
    hg.players[0].grapple_point = [10.0, 20.0]
    hg.players[0].grapple_frames = 3
    after = SnapshotService.capture(hg, include_rng=False)
    assert [p.weapon for p in after.players] == ["Grapple Hook", ""]
    rebuilt = apply_delta(before, compute_delta(before, after))
    assert rebuilt.players[0].grapple_point == [10.0, 20.0]
    assert rebuilt.players[0].grapple_frames == 3
    assert rebuilt.players[0].weapon == "Grapple Hook"
