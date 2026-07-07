"""Store-items E2E bot (real game instance).

Runs the real state machine (MenuState -> StoreState -> AccessoriesState ->
GameState) with the production InputRouter and drives it exclusively through
synthetic pygame keyboard events — the same code paths a human player hits.

Verifies:
- every new store item can be bought with coins in the real store UI
- weapons/gear/skins can be equipped through the real accessories UI
- in-game physics of every new element (rifle, stars, sword, grapple,
  moon boots, shield, coin magnet, lucky charm)
- rendering: screenshots + pixel-level checks on the live frame buffer

Must be launched by tools/items_e2e.py inside an isolated data sandbox
(cwd contains a disposable copy of data/). Writes report.json + PNGs to --out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

CHECKS: list[dict] = []
OUT_DIR = "."


def check(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


def screenshot(name: str) -> None:
    surf = pygame.display.get_surface()
    if surf is not None:
        pygame.image.save(surf, os.path.join(OUT_DIR, f"{name}.png"))


class Driver:
    """Replicates app.py's main-loop wiring (single event poll, router,
    state transitions) so states behave exactly as in production."""

    def __init__(self):
        from scripts.input_router import InputRouter
        from scripts.state_manager import (
            AccessoriesState,
            GameState,
            LevelsState,
            MenuState,
            OptionsState,
            PauseState,
            StateManager,
            StoreState,
        )

        self._states = {
            "Levels": LevelsState,
            "Store": StoreState,
            "Accessories": AccessoriesState,
            "Options": OptionsState,
        }
        self._MenuState = MenuState
        self._GameState = GameState
        self._PauseState = PauseState
        self.sm = StateManager()
        self.router = InputRouter()
        self.sm.set(MenuState())

    @property
    def cur(self):
        return self.sm.current

    def step(self, frames: int = 1) -> None:
        from scripts.state_manager import GameState, MenuState, PauseState

        for _ in range(frames):
            events = pygame.event.get()
            actions = self.router.process(events, self.cur.name if self.cur else "")
            self.sm.handle_actions(actions)
            self.sm.handle(events)

            cur = self.cur
            if isinstance(cur, MenuState):
                if getattr(cur, "start_game", False):
                    cur.start_game = False
                    self.sm.set(GameState())
                elif getattr(cur, "next_state", None):
                    nxt = cur.next_state
                    cur.next_state = None
                    if nxt in self._states:
                        self.sm.set(self._states[nxt]())
                cur = self.cur
            if cur is not None and getattr(cur, "request_back", False):
                cur.request_back = False
                self.sm.set(self._MenuState())
                cur = self.cur
            if isinstance(cur, GameState) and getattr(cur, "request_pause", False):
                self.sm.push(PauseState())
                cur = self.cur
            if isinstance(cur, PauseState) and cur.closed:
                self.sm.pop()

            self.sm.update(1 / 60)
            screen = pygame.display.get_surface()
            if screen is not None:
                self.sm.render(screen)

    def press(self, key: int, frames_after: int = 2) -> None:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": key}))
        self.step()
        pygame.event.post(pygame.event.Event(pygame.KEYUP, {"key": key}))
        self.step(frames_after)


def region_pixels(surf: pygame.Surface, cx: int, cy: int, radius: int) -> list[tuple]:
    pixels = []
    for x in range(max(0, cx - radius), min(surf.get_width(), cx + radius)):
        for y in range(max(0, cy - radius), min(surf.get_height(), cy + radius)):
            pixels.append(surf.get_at((x, y))[:3])
    return pixels


def color_near(surf, cx, cy, radius, color, tol=12) -> bool:
    for px in region_pixels(surf, cx, cy, radius):
        if all(abs(px[i] - color[i]) <= tol for i in range(3)):
            return True
    return False


def player_screen_pos(g):
    ox, oy = int(g.scroll[0]), int(g.scroll[1])
    r = g.player.rect()
    return r.centerx - ox, r.centery - oy


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def phase_store(d: Driver) -> None:
    from scripts.state_manager import MenuState, StoreState

    check("boot.menu", isinstance(d.cur, MenuState), f"state={d.cur.name}")
    screenshot("01_menu")

    # Navigate to the store entry with real key presses
    menu = d.cur
    target = menu.options_keys.index("menu.store")
    for _ in range(target):
        d.press(pygame.K_DOWN)
    d.press(pygame.K_RETURN, frames_after=3)
    check("menu.opens_store", isinstance(d.cur, StoreState), f"state={d.cur.name}")
    screenshot("02_store")

    store = d.cur
    cm = store.cm
    start_coins = cm.coins
    bought = {}
    # Buy every item once (list order == store display order)
    for idx, name in enumerate(store.options_raw):
        cur_idx = store.widget.selected_index
        key = pygame.K_DOWN if idx > cur_idx else pygame.K_UP
        for _ in range(abs(idx - cur_idx)):
            d.press(key)
        before = cm.get_amount(name)
        d.press(pygame.K_RETURN, frames_after=3)
        after = cm.get_amount(name)
        idef = cm.get_item_def(name)
        bought[name] = after
        check(
            f"store.buy.{name.replace(' ', '_')}",
            after == before + idef.increment,
            f"amount {before}->{after} (price {idef.price})",
        )
    # Two extra shield charges + one extra ammo pack for the gameplay phase
    for extra, presses in (("Shield", 2), ("Ammo", 1)):
        idx = store.options_raw.index(extra)
        cur_idx = store.widget.selected_index
        key = pygame.K_DOWN if idx > cur_idx else pygame.K_UP
        for _ in range(abs(idx - cur_idx)):
            d.press(key)
        for _ in range(presses):
            d.press(pygame.K_RETURN, frames_after=3)
    total_price = sum(cm.get_item_def(n).price for n in store.options_raw)
    total_price += cm.get_item_def("Shield").price * 2 + cm.get_item_def("Ammo").price
    check(
        "store.coins_deducted",
        cm.coins == start_coins - total_price,
        f"{start_coins} - {total_price} = {cm.coins}",
    )
    screenshot("03_store_after_buys")

    # Persistence: a fresh manager must see the purchases
    from scripts.collectableManager import CollectableManager

    fresh = CollectableManager(None)
    check(
        "store.persisted",
        fresh.rifle == 1 and fresh.sword == 1 and fresh.grapple_hook == 1 and fresh.berserker == 1,
        f"rifle={fresh.rifle} sword={fresh.sword} grapple={fresh.grapple_hook} berserker={fresh.berserker}",
    )
    d.press(pygame.K_ESCAPE, frames_after=3)  # back to menu


def phase_accessories(d: Driver) -> None:
    from scripts.settings import settings
    from scripts.state_manager import AccessoriesState, MenuState

    menu = d.cur
    check("back_to_menu", isinstance(menu, MenuState), f"state={menu.name}")
    target = menu.options_keys.index("menu.accessories")
    for _ in range(target):
        d.press(pygame.K_DOWN)
    d.press(pygame.K_RETURN, frames_after=3)
    acc = d.cur
    check("menu.opens_accessories", isinstance(acc, AccessoriesState), f"state={acc.name}")

    # Panel 0: equip Sword via real keys
    sword_idx = acc.weapons.index("Sword")
    for _ in range(sword_idx):
        d.press(pygame.K_DOWN)
    d.press(pygame.K_RETURN, frames_after=3)
    check(
        "accessories.equip_sword", settings.selected_weapon == sword_idx, f"selected_weapon={settings.selected_weapon}"
    )

    # TAB -> gear panel: equip Shield
    d.press(pygame.K_TAB)
    shield_idx = acc.gear.index("Shield")
    for _ in range(shield_idx):
        d.press(pygame.K_DOWN)
    d.press(pygame.K_RETURN, frames_after=3)
    check("accessories.equip_shield", settings.selected_gear == shield_idx, f"selected_gear={settings.selected_gear}")

    # TAB -> skins panel: equip Gold Ninja
    d.press(pygame.K_TAB)
    gold_idx = acc.skins.index("Gold Ninja")
    for _ in range(gold_idx):
        d.press(pygame.K_DOWN)
    d.press(pygame.K_RETURN, frames_after=3)
    check("accessories.equip_gold_skin", settings.selected_skin == gold_idx, f"selected_skin={settings.selected_skin}")
    screenshot("04_accessories")
    d.press(pygame.K_ESCAPE, frames_after=3)


def _find_grapple_spot(g):
    """Find a solid tile with free tiles to its left (player stands there facing right)."""
    ts = g.tilemap.tile_size
    for key, tile in g.tilemap.tilemap.items():
        if tile["type"] not in ("grass", "stone"):
            continue
        tx, ty = tile["pos"]
        left_free = all(f"{tx - i};{ty}" not in g.tilemap.tilemap for i in range(1, 6))
        below_left = f"{tx - 3};{ty + 1}" in g.tilemap.tilemap
        if left_free and below_left:
            return (tx - 3) * ts, ty * ts
    return None


def phase_gameplay(d: Driver) -> None:
    from scripts.collectableManager import CollectableManager as CM
    from scripts.collectables import Collectables
    from scripts.constants import AIR_JUMP_VELOCITY, RIFLE_AMMO_COST, RIFLE_PROJECTILE_SPEED
    from scripts.entities import Enemy
    from scripts.settings import settings
    from scripts.state_manager import GameState, MenuState

    menu = d.cur
    check("menu_before_play", isinstance(menu, MenuState), f"state={menu.name}")
    # menu.play is the first entry (selection resets in a fresh MenuState)
    d.press(pygame.K_RETURN, frames_after=5)
    check("menu.starts_game", isinstance(d.cur, GameState), f"state={d.cur.name}")
    g = d.cur.game
    # Remove map enemies: they shoot at the player and would make the
    # long-running deterministic checks flaky. Weapon tests spawn their own.
    g.enemies.clear()
    d.step(30)  # settle spawn / camera

    def settle_grounded(max_frames=90) -> bool:
        """Teleport the player to spawn and wait until standing on ground."""
        g.player.pos = list(g.player.respawn_pos)
        g.player.velocity = [0.0, 0.0]
        g.player.grapple_point = None
        g.player.dashing = 0
        for _ in range(max_frames):
            d.step(1)
            if g.player.collisions["down"]:
                return True
        return False

    settle_grounded()
    # Neutral loadout so pixel checks see the bare skin (no held weapon,
    # no shield bubble from the accessories phase)
    settings.selected_weapon = 0
    settings.selected_gear = 0

    # --- Skins render with correct palettes -------------------------------
    skin_body = {
        "default": (38, 36, 58),
        "red": (245, 65, 84),
        "gold": (196, 148, 32),
        "platinum": (150, 160, 172),
        "diamond": (64, 180, 216),
        "assassin": (30, 30, 36),
        "berserker": (122, 44, 32),
    }
    for idx, path in enumerate(CM.SKIN_PATHS):
        g.player.skin = idx
        g.player.action = ""
        g.player.set_action("idle")
        d.step(3)
        px, py = player_screen_pos(g)
        ok = color_near(g.display, px, py, 14, skin_body[path], tol=10)
        check(f"render.skin.{path}", ok, f"body color {skin_body[path]} near player")
        screenshot(f"05_skin_{idx}_{path}")
    g.player.skin = 0
    g.player.action = ""
    g.player.set_action("idle")

    # --- Gun ---------------------------------------------------------------
    settings.selected_weapon = CM.WEAPONS.index("Gun")
    settings.selected_gear = 0
    g.player.shoot_cooldown = 0
    ammo0 = g.cm.ammo
    n0 = len(g.projectiles)
    d.press(pygame.K_x, frames_after=1)
    check("gun.fires", len(g.projectiles) == n0 + 1 and g.cm.ammo == ammo0 - 1, f"ammo {ammo0}->{g.cm.ammo}")
    screenshot("06_gun_shot")
    d.step(30)

    # --- Rifle ---------------------------------------------------------------
    settings.selected_weapon = CM.WEAPONS.index("Rifle")
    g.player.shoot_cooldown = 0
    g.projectiles.clear()
    ammo0 = g.cm.ammo
    d.press(pygame.K_x, frames_after=1)
    projs = list(g.projectiles)
    ok = len(projs) == 1 and abs(projs[0]["vel"][0]) == RIFLE_PROJECTILE_SPEED and g.cm.ammo == ammo0 - RIFLE_AMMO_COST
    check("rifle.fires_fast_2ammo", ok, f"ammo {ammo0}->{g.cm.ammo}, vel={projs[0]['vel'][0] if projs else None}")
    screenshot("07_rifle_shot")
    d.step(30)

    # --- Ninja stars ---------------------------------------------------------
    settings.selected_weapon = CM.WEAPONS.index("Ninja Stars")
    g.player.shoot_cooldown = 0
    g.projectiles.clear()
    stars0 = g.cm.ninja_stars
    d.press(pygame.K_x, frames_after=1)
    projs = list(g.projectiles)
    ok = len(projs) == 1 and projs[0]["kind"] == "star" and projs[0]["pierce"] and g.cm.ninja_stars == stars0 - 1
    check("stars.throw", ok, f"stars {stars0}->{g.cm.ninja_stars}")
    if projs:
        vy0 = projs[0]["vel"][1]
        d.step(6)
        arc_ok = projs[0] not in g.projectiles or projs[0]["vel"][1] > vy0
        check("stars.arc_gravity", arc_ok, f"vy {vy0} -> {projs[0]['vel'][1]}")
        if projs[0] in list(g.projectiles):
            sx = int(projs[0]["pos"][0] - g.scroll[0])
            sy = int(projs[0]["pos"][1] - g.scroll[1])
            # Dark hub color (75,78,90) cannot be confused with sky/clouds
            check(
                "render.star_sprite",
                color_near(g.display, sx, sy, 6, (75, 78, 90), tol=10),
                "star hub pixels at star pos",
            )
    screenshot("08_star_flight")
    d.step(40)

    # --- Sword ---------------------------------------------------------------
    settings.selected_weapon = CM.WEAPONS.index("Sword")
    settle_grounded()
    g.player.flip = False

    # Swing in empty air first: slash VFX must be visible undisturbed
    g.player.shoot_cooldown = 0
    d.press(pygame.K_x, frames_after=1)
    px, py = player_screen_pos(g)
    check(
        "render.slash_vfx",
        color_near(g.display, px + 12, py, 12, (170, 220, 250), tol=20),
        "slash cyan in front of player",
    )
    screenshot("09a_sword_swing")
    d.step(30)

    # Kill: enemy directly in reach
    g.player.shoot_cooldown = 0
    prect = g.player.rect()
    enemy = Enemy(g, (prect.right + 6, prect.top), (8, 15), id=990)
    g.enemies.append(enemy)
    coins0 = g.cm.coins
    n_enemies = len(g.enemies)
    d.press(pygame.K_x, frames_after=1)
    check(
        "sword.kills_enemy",
        len(g.enemies) == n_enemies - 1 and g.cm.coins == coins0 + 1,
        f"enemies {n_enemies}->{len(g.enemies)}, coins {coins0}->{g.cm.coins}",
    )
    screenshot("09b_sword_kill")
    d.step(30)

    # Sword parry: destroy an incoming enemy projectile
    g.player.shoot_cooldown = 0
    g.projectiles.clear()
    g.projectiles.spawn(g.player.rect().right + 8, g.player.rect().centery, -0.5, "enemy")
    d.press(pygame.K_x, frames_after=1)
    check("sword.parries_projectile", len(g.projectiles) == 0, f"projectiles={len(g.projectiles)}")
    d.step(20)

    # --- Grapple hook ----------------------------------------------------------
    settings.selected_weapon = CM.WEAPONS.index("Grapple Hook")
    spot = _find_grapple_spot(g)
    if spot is None:
        check("grapple.spot_found", False, "no wall with free approach found in level")
    else:
        g.player.pos = [float(spot[0]), float(spot[1])]
        g.player.velocity = [0.0, 0.0]
        g.player.flip = False
        g.player.shoot_cooldown = 0
        d.step(3)  # settle
        g.player.pos = [float(spot[0]), float(spot[1])]
        x0 = g.player.pos[0]
        d.press(pygame.K_x, frames_after=1)
        attached = g.player.grapple_point is not None
        check("grapple.attaches", attached, f"anchor={g.player.grapple_point}")
        if attached:
            px, py = player_screen_pos(g)
            ax = int(g.player.grapple_point[0] - g.scroll[0])
            mid = ((px + ax) // 2, py)
            check(
                "render.grapple_rope",
                color_near(g.display, mid[0], mid[1], 6, (200, 205, 215), tol=20),
                "rope pixels between player and anchor",
            )
            screenshot("10_grapple_pull")
            d.step(4)
            check("grapple.pulls_player", g.player.pos[0] > x0, f"x {x0} -> {g.player.pos[0]}")
            d.step(60)
            check("grapple.releases", g.player.grapple_point is None, "anchor cleared")
    d.step(30)

    # --- Moon boots (double jump) ----------------------------------------------
    settings.selected_weapon = 0
    settings.selected_gear = CM.GEAR.index("Moon Boots")
    check("moonboots.grounded", settle_grounded(), f"pos={g.player.pos}")
    d.press(pygame.K_w, frames_after=6)
    airborne = not g.player.collisions["down"] and not g.player.wall_slide
    aj0 = g.player.air_jumps
    d.press(pygame.K_w, frames_after=0)
    vy = g.player.velocity[1]
    check(
        "moonboots.double_jump",
        airborne and aj0 == 1 and g.player.air_jumps == 0 and abs(vy - AIR_JUMP_VELOCITY) < 0.15,
        f"airborne={airborne} air_jumps {aj0}->{g.player.air_jumps} vy={vy:.2f}",
    )
    d.step(60)

    # --- Shield ------------------------------------------------------------------
    settings.selected_gear = CM.GEAR.index("Shield")
    settle_grounded()
    d.step(2)  # arm
    check("shield.arms", g.player.shield_ready, f"charges={g.cm.shield}")
    px, py = player_screen_pos(g)
    with_bubble = region_pixels(g.display, px, py, 16)
    g.player.shield_ready = False
    d.step(1)
    without_bubble = region_pixels(g.display, px, py, 16)
    g.player.shield_ready = True
    d.step(1)
    check("render.shield_bubble", with_bubble != without_bubble, "bubble changes player region pixels")
    screenshot("11_shield_bubble")
    lives0 = g.player.lives
    charges0 = g.cm.shield
    g.projectiles.clear()
    # Spawn overlapping the player: guaranteed hit on next projectile update
    g.projectiles.spawn(g.player.rect().centerx - 2, g.player.rect().centery, 0.8, "enemy")
    d.step(5)
    check(
        "shield.absorbs_hit",
        g.player.lives == lives0 and g.cm.shield == charges0 - 1,
        f"lives {lives0}->{g.player.lives}, charges {charges0}->{g.cm.shield}",
    )
    d.step(10)

    # --- Coin magnet ---------------------------------------------------------------
    settings.selected_gear = CM.GEAR.index("Coin Magnet")
    settle_grounded()
    coin = Collectables(g, (g.player.rect().centerx + 34, g.player.rect().centery), g.assets["coin"])
    g.cm.coin_list.append(coin)
    x0 = coin.pos[0]
    d.step(2)
    moved = coin not in g.cm.coin_list or coin.pos[0] < x0
    check("magnet.pulls_coin", moved, f"coin x {x0} -> {coin.pos[0]}")
    coins0 = g.cm.coins
    d.step(60)
    check("magnet.coin_collected", coin not in g.cm.coin_list and g.cm.coins > coins0, f"coins {coins0}->{g.cm.coins}")

    # --- Lucky charm -----------------------------------------------------------------
    settings.selected_gear = CM.GEAR.index("Lucky Charm")
    g.load_level(g.level)
    check("charm.extra_life", g.player.lives == 4, f"lives={g.player.lives}")
    settings.selected_gear = 0
    g.load_level(g.level)
    check("charm.baseline_without", g.player.lives == 3, f"lives={g.player.lives}")

    # --- HUD with stars + shield equipped ---------------------------------------------
    settings.selected_weapon = CM.WEAPONS.index("Ninja Stars")
    settings.selected_gear = CM.GEAR.index("Shield")
    d.step(3)
    screenshot("12_hud_stars_shield")

    # Persistence on exit
    d.cur.on_exit(None)
    from scripts.collectableManager import CollectableManager

    fresh = CollectableManager(None)
    check(
        "exit.persists_consumables",
        fresh.ammo == g.cm.ammo and fresh.shield == g.cm.shield,
        f"ammo={fresh.ammo} shield={fresh.shield}",
    )


def main() -> int:
    global OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    OUT_DIR = args.out
    os.makedirs(OUT_DIR, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((1280, 720))

    d = Driver()
    d.step(5)
    phase_store(d)
    phase_accessories(d)
    phase_gameplay(d)

    failed = [c for c in CHECKS if not c["ok"]]
    report = {"checks": CHECKS, "passed": len(CHECKS) - len(failed), "failed": len(failed)}
    with open(os.path.join(OUT_DIR, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n{report['passed']}/{len(CHECKS)} checks passed")
    pygame.quit()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
