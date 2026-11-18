"""Looks of the weapons and gear (scripts/item_fx.py) and their store scenes
(scripts/item_showcase.py)."""

import os

import pygame
import pytest

import scripts.collectableManager as cm_module
from game import Game
from scripts import item_fx
from scripts.collectableManager import ITEM_ICONS, CollectableManager
from scripts.item_showcase import SCENES, scene_for
from scripts.settings import settings
from scripts.skin_preview import STAGE, SkinPreview

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()


def test_every_weapon_and_gear_has_an_icon_and_a_scene():
    items = [n for n, d in CollectableManager._ITEM_DEFS.items() if d.category in ("weapon", "gear")]
    for name in items:
        assert os.path.exists(os.path.join("data/images", ITEM_ICONS[name])), name
        assert name in SCENES, name
    for name in item_fx.HELD.values():
        assert os.path.exists(os.path.join("data/images", name[0]))


@pytest.mark.parametrize("name", sorted(SCENES))
def test_scene_plays_its_whole_loop(name):
    preview = SkinPreview()
    preview.set_skin("default", showcase=False)
    scene = scene_for(name)
    surf = pygame.Surface(STAGE)
    seen = set()
    for t in range(0, scene.cycle * 2, 3):
        preview.ticks = float(t)
        preview.render_stage(surf, surf.get_rect(), scene=scene)
        seen.add(pygame.image.tobytes(surf, "RGB"))
    assert len(seen) > 3, f"{name} should animate"


def test_moon_boots_recolor_only_the_feet():
    frame = SkinPreview()
    frame.set_skin("default", showcase=False)
    img = frame.anim_frame("idle", 0)
    boots = item_fx.boots_overlay(img)
    painted = [(x, y) for x in range(img.get_width()) for y in range(img.get_height()) if boots.get_at((x, y)).a]
    assert painted, "the boots must show"
    assert min(y for _, y in painted) >= img.get_height() - 5
    assert {tuple(boots.get_at(p))[:3] for p in painted} <= set(item_fx.BOOT.values())


@pytest.fixture()
def game(tmp_path, monkeypatch):
    monkeypatch.setattr(cm_module, "DATA_FILE", str(tmp_path / "collectables.json"))
    g = Game()
    g.load_level(0)
    for attr in ("gun", "rifle", "sword", "grapple_hook", "shield", "moon_boots", "coin_magnet", "lucky_charm"):
        setattr(g.cm, attr, 1)
    g.cm.ammo = g.cm.ninja_stars = 10
    old = (settings.selected_weapon, settings.selected_gear)
    yield g
    settings.selected_weapon, settings.selected_gear = old


def _drawn(game):
    surf = pygame.Surface((game.BASE_W, game.BASE_H), pygame.SRCALPHA)
    game.player.render(surf, offset=game.scroll)
    return pygame.image.tobytes(surf, "RGBA")


@pytest.mark.parametrize("gear", CollectableManager.GEAR[1:])
def test_equipped_gear_shows_on_the_ninja(game, gear):
    settings.selected_weapon = 0
    settings.selected_gear = 0
    game.player.fx_tick = 500  # past the lucky charm's level-start heart
    bare = _drawn(game)
    settings.selected_gear = CollectableManager.GEAR.index(gear)
    game.step()  # arms the shield
    game.player.fx_tick = 500
    assert _drawn(game) != bare, gear


@pytest.mark.parametrize("weapon", [w for w in CollectableManager.WEAPONS if w != "Default"])
def test_firing_plays_the_weapon_animation(game, weapon):
    settings.selected_weapon = CollectableManager.WEAPONS.index(weapon)
    settings.selected_gear = 0
    p = game.player
    p.shoot_cooldown = 0
    rest = _drawn(game)
    assert p.shoot() is not None
    assert p.fire_fx_kind == weapon and p.fire_fx == item_fx.FIRE_FRAMES[weapon]
    game.step()
    assert _drawn(game) != rest, weapon
    for _ in range(item_fx.FIRE_FRAMES[weapon]):
        game.step()
    assert p.fire_fx == 0


def test_rendering_leaves_the_simulation_alone(game):
    settings.selected_weapon = CollectableManager.WEAPONS.index("Sword")
    settings.selected_gear = CollectableManager.GEAR.index("Coin Magnet")
    p = game.player
    before = (list(p.pos), list(p.velocity), p.fx_tick, [list(c.pos) for c in game.cm.coin_list])
    for _ in range(5):
        _drawn(game)
    assert before == (list(p.pos), list(p.velocity), p.fx_tick, [list(c.pos) for c in game.cm.coin_list])


def test_moon_jump_burst_keeps_the_rng_draws_of_the_old_particles(game):
    from scripts.rng_service import RNGService

    settings.selected_gear = CollectableManager.GEAR.index("Moon Boots")
    p = game.player
    p.jumps = 0
    p.air_jumps = 1
    p.wall_slide = False
    rng = RNGService.get()
    rng.seed(7)
    particles = len(game.particles)
    assert p.jump()
    after_jump = rng.random()
    rng.seed(7)
    for _ in range(10):
        rng.random(), rng.random(), rng.randint(0, 7)
    assert rng.random() == after_jump  # replays recorded before stay in step
    assert len(game.particles) == particles
    assert p.moon_fx == item_fx.MOON_JUMP_FRAMES
