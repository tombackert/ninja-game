"""Weapons and gear in action on the store and accessories cards.

Each item gets a little looping scene on the stage of scripts/skin_preview.py:
the gun and the rifle shoot at a straw target, a star arcs through it, the
sword cuts it, the hook bites into a wall and pulls the ninja over, the
shield takes a bullet and re-arms, the moon boots double jump, the magnet
pulls coins, the lucky charm sends up its extra life. All of it is drawn by
scripts/item_fx.py, the same code that draws the items in a level.

Scenes work in stage pixels (STAGE, ground at GROUND_Y) and game ticks.
"""

from __future__ import annotations

import pygame

from scripts import item_fx
from scripts.skin_preview import BOX, GROUND_Y, STAGE, _load_image

TARGET_X = 86  # center of the straw target the weapons hit
TARGET_HIT = 4  # frames the target wobbles after a hit
WALL_X = STAGE[0] - 16  # the grapple scene's wall (its left face)


def _hitbox(fx: float, fy: float) -> pygame.Rect:
    """The ninja's 8x15 hitbox with its feet (bottom center) at fx, fy."""
    return pygame.Rect(round(fx) - 4, round(fy) - 15, 8, 15)


class Scene:
    """One item's loop. `draw` puts the scene and the ninja on the stage."""

    cycle = 120

    def __init__(self, name: str) -> None:
        self.name = name

    # helpers -------------------------------------------------------
    @staticmethod
    def ninja(stage, preview, anim: str, fx: float, fy: float, flip=False, t: float = 0.0, alpha=255):
        img = preview.anim_frame(anim, t)
        if img is None:
            return None
        if flip:
            img = pygame.transform.flip(img, True, False)
        if alpha < 255:
            img = img.copy()
            img.set_alpha(alpha)
        stage.blit(img, (round(fx) - BOX[0] // 2, round(fy) - BOX[1]))
        return img

    @staticmethod
    def target(stage, t_since_hit: float | None):
        img = _load_image("weapons/target.png")
        wobble = 0
        if t_since_hit is not None and 0 <= t_since_hit < TARGET_HIT * 2:
            wobble = (1, -1)[int(t_since_hit) // 2 % 2]
        stage.blit(img, (TARGET_X - img.get_width() // 2 + wobble, GROUND_Y - img.get_height()))
        return (TARGET_X, GROUND_Y - img.get_height() + 4)  # bullseye

    def draw(self, stage, preview, t: float) -> None:
        self.ninja(stage, preview, "idle", STAGE[0] // 2, GROUND_Y, t=t)


class Shooting(Scene):
    """Gun and rifle: aim, fire, the bullet streaks into the target."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.rifle = name == "Rifle"
        self.cycle = 90 if self.rifle else 60
        self.fire_at = 14
        self.speed = 6.5 if self.rifle else 3.5

    def draw(self, stage, preview, t):
        fx = 34
        p = t % self.cycle
        since = p - self.fire_at
        rect = _hitbox(fx, GROUND_Y)
        muzzle_x = item_fx.hand(rect, False)[0] + (11 if self.rifle else 8)
        hit_at = (TARGET_X - 3 - muzzle_x) / self.speed
        self.target(stage, since - hit_at if since >= hit_at else None)
        muzzle_y = item_fx.hand(rect, False)[1] + (-3 if self.rifle else -2)
        self.ninja(stage, preview, "idle", fx, GROUND_Y, t=t)
        anim = int(since) if 0 <= since < item_fx.FIRE_FRAMES[self.name] else None
        item_fx.weapon(stage, self.name, rect, False, int(t), anim)
        if 0 <= since < hit_at:
            img = item_fx.bullet_image(self.rifle, False)
            head = muzzle_x + since * self.speed
            stage.blit(img, (round(head) - img.get_width() + 1, muzzle_y - 1))
        elif hit_at <= since < hit_at + 8:
            item_fx.sparkle(stage, (TARGET_X - 3, muzzle_y), 2 - int(since - hit_at) // 3, item_fx.GOLD)


class Throwing(Scene):
    """Ninja stars: a star leaves the hand, spins through the target."""

    cycle = 70
    throw_at = 12

    def draw(self, stage, preview, t):
        fx = 34
        p = t % self.cycle
        since = p - self.throw_at
        rect = _hitbox(fx, GROUND_Y)
        hx, hy = item_fx.hand(rect, False)
        # a flatter arc than in a level, so it lands on the stage
        sx = hx + since * 3.0
        sy = hy - 3 - since * 1.0 + 0.06 * since * since
        hit = None
        if since >= 0 and sx >= TARGET_X - 3:
            hit = (sx - TARGET_X + 3) / 3.0
        self.target(stage, hit)
        self.ninja(stage, preview, "idle", fx, GROUND_Y, t=t)
        anim = int(since) if 0 <= since < item_fx.FIRE_FRAMES[self.name] else None
        item_fx.weapon(stage, self.name, rect, False, int(t), anim)
        if since >= 0 and sx < STAGE[0] + 8:
            angle = int(since * 20) % 360
            ghost = item_fx.star_image((angle - 20) % 360, ghost=True)
            stage.blit(ghost, (round(sx - 4.5) - ghost.get_width() // 2, round(sy + 1.5) - ghost.get_height() // 2))
            img = item_fx.star_image(angle)
            stage.blit(img, (round(sx) - img.get_width() // 2, round(sy) - img.get_height() // 2))


class Slashing(Scene):
    """Sword: raise, sweep, the crescent cuts the target."""

    cycle = 54
    swing_at = 14

    def draw(self, stage, preview, t):
        fx = 62
        p = t % self.cycle
        since = p - self.swing_at
        rect = _hitbox(fx - 2, GROUND_Y)
        img = _load_image("weapons/target.png")
        wobble = (1, -1, 1, 0)[int(since - 2) // 2] if 2 <= since < 10 else 0
        tx = rect.right + 12
        stage.blit(img, (tx - img.get_width() // 2 + wobble, GROUND_Y - img.get_height()))
        self.ninja(stage, preview, "idle", rect.centerx, GROUND_Y, t=t)
        anim = int(since) if 0 <= since < item_fx.FIRE_FRAMES[self.name] else None
        item_fx.weapon(stage, self.name, rect, False, int(t), anim)
        if 2 <= since < 9:
            for i, (dx, dy) in enumerate(((-2, -4), (3, 2), (0, 5))):
                item_fx.sparkle(stage, (tx + dx, GROUND_Y - 11 + dy), max(0, 2 - (int(since) - 2 + i) // 2))


class Grappling(Scene):
    """Grapple hook: the hook bites into a wall, the rope pulls the ninja
    over, then the ninja runs back."""

    cycle = 170
    fire_at = 20
    pull = (23, 35)  # ticks of the pull
    back = (85, 115)  # ticks of the run back

    def draw(self, stage, preview, t):
        top, side = _load_image("tiles/stone/0.png"), _load_image("tiles/stone/7.png")
        for y in range(GROUND_Y - 32, GROUND_Y + 16, 16):
            stage.blit(top if y == GROUND_Y - 32 else side, (WALL_X, y))
        p = t % self.cycle
        start, end = 30, WALL_X - 6
        if p < self.pull[0]:
            fx, anim, flip = start, "idle", False
        elif p < self.pull[1]:
            k = (p - self.pull[0]) / (self.pull[1] - self.pull[0])
            fx, anim, flip = start + (end - start) * k * k, "jump", False
        elif p < self.back[0]:
            fx, anim, flip = end, "idle", p > self.back[0] - 20
        elif p < self.back[1]:
            k = (p - self.back[0]) / (self.back[1] - self.back[0])
            fx, anim, flip = end + (start - end) * k, "run", True
        else:
            fx, anim, flip = start, "idle", p < self.back[1] + 15
        rect = _hitbox(fx, GROUND_Y)
        self.ninja(stage, preview, anim, fx, GROUND_Y, flip, t)
        grapple = None
        if self.fire_at <= p < self.pull[1]:
            anchor = (WALL_X, item_fx.hand(_hitbox(start, GROUND_Y), False)[1])
            grapple = (anchor, int(p - self.fire_at))
        item_fx.weapon(stage, self.name, rect, flip, int(t), None, grapple)


class AmmoCrate(Scene):
    """Ammo: an open crate of bullets beside the ninja, glinting."""

    def draw(self, stage, preview, t):
        fx = 40
        crate = _load_image("weapons/ammo.png")
        cx = fx + 14
        stage.blit(crate, (cx, GROUND_Y - crate.get_height()))
        self.ninja(stage, preview, "idle", fx, GROUND_Y, t=t)
        item_fx.weapon(stage, "Gun", _hitbox(fx, GROUND_Y), False, int(t))
        p = int(t) % 40
        if p < 14:
            tip = (cx + 2 + 4 * ((int(t) // 40) % 3), GROUND_Y - crate.get_height() + 1)
            item_fx.sparkle(stage, tip, (0, 1, 2, 2, 1, 0, 0)[p // 2], item_fx.GOLD)


class Dash(Scene):
    """The dash: the ninja shoots across the stage, leaving after-images."""

    cycle = 160

    def draw(self, stage, preview, t):
        half = self.cycle // 2
        p = t % half
        right = (t % self.cycle) < half
        d = 1 if right else -1
        a, b = (24, 72) if right else (72, 24)
        if p < 40:
            fx, anim = a, "idle"
        elif p < 50:
            k = (p - 40) / 10
            fx, anim = a + (b - a) * k, "run"
            for i in range(1, 4):
                gx = a + (b - a) * max(0.0, k - i * 0.09)
                self.ninja(stage, preview, "run", gx, GROUND_Y, not right, t, alpha=150 - i * 40)
            for i, y in enumerate((-12, -7, -3)):
                x0 = fx - d * (6 + i * 3)
                for j in range(6 + i * 2):
                    item_fx._px(stage, (x0 - d * j, GROUND_Y + y), (255, 255, 255), 200 - j * 25)
        else:
            fx, anim = b, "idle"
        self.ninja(stage, preview, anim, fx, GROUND_Y, not right, t)


class ShieldScene(Scene):
    """Shield: the bubble takes an enemy bullet, shatters, re-arms."""

    cycle = 220
    shot_at = 50
    speed = 2.0

    def draw(self, stage, preview, t):
        fx = STAGE[0] // 2 - 8
        rect = _hitbox(fx, GROUND_Y)
        p = t % self.cycle
        edge = rect.centerx + 13
        bx = STAGE[0] + 4 - (p - self.shot_at) * self.speed
        hit_at = self.shot_at + (STAGE[0] + 4 - edge) / self.speed
        rearm_end = self.cycle - 30
        self.ninja(stage, preview, "idle", fx, GROUND_Y, t=t)
        ready = p < hit_at or p >= rearm_end
        rearm = 0.0 if ready else (p - hit_at) / (rearm_end - hit_at)
        broke = int(p - hit_at) if hit_at <= p < hit_at + item_fx.SHIELD_BREAK_FRAMES else None
        item_fx.shield(stage, rect.center, int(t), ready, rearm, broke)
        if self.shot_at <= p < hit_at:
            enemy_bullet = _load_image("projectile.png")
            stage.blit(enemy_bullet, (round(bx), rect.centery - 2))
        if rearm_end <= p < rearm_end + 10:
            item_fx.sparkle(stage, (rect.centerx, rect.centery - 13), 2 - int(p - rearm_end) // 4, item_fx.GLOW)


class MoonBoots(Scene):
    """Moon boots: jump, then a second jump in the air off a ring of moonlight."""

    cycle = 130
    jump_at = 30
    v1, v2, g = -1.5, -1.25, 0.1

    def _height(self, s):
        """Height above ground `s` ticks after the first jump (None: landed)."""
        apex = -self.v1 / self.g
        if s < apex:
            return -(self.v1 * s + self.g * s * s / 2), True
        h1 = self.v1 * self.v1 / (2 * self.g)
        u = s - apex
        h = h1 + (-self.v2 * u - self.g * u * u / 2)
        return (h, False) if h > 0 else (None, False)

    def draw(self, stage, preview, t):
        fx = STAGE[0] // 2
        p = t % self.cycle
        s = p - self.jump_at
        h, charged = (None, False) if s < 0 else self._height(s)
        fy = GROUND_Y - (h or 0)
        rect = _hitbox(fx, fy)
        if h is None:
            item_fx.boot_glow(stage, rect, int(t), False)
        elif charged:
            item_fx.boot_glow(stage, rect, int(t), True)
        img = self.ninja(stage, preview, "jump" if h is not None else "idle", fx, fy, t=t)
        if img is not None:
            boots = item_fx.boots_overlay(preview.anim_frame("jump" if h is not None else "idle", t))
            stage.blit(boots, (round(fx) - BOX[0] // 2, round(fy) - BOX[1]))
        apex = -self.v1 / self.g
        if s >= apex:
            jump_y = GROUND_Y - self.v1 * self.v1 / (2 * self.g)
            item_fx.moon_jump(stage, (fx, jump_y), int(s - apex))


class Magnet(Scene):
    """Coin magnet: spinning coins fly in, gold dust behind them."""

    def draw(self, stage, preview, t):
        fx = STAGE[0] // 2
        rect = _hitbox(fx, GROUND_Y)
        frames = [_load_image(f"collectables/coin/{i}.png") for i in range(10)]
        cycle, fly = 90, 50  # each coin flies in for `fly` ticks, then respawns
        tx, ty = rect.center
        item_fx.magnet_field(stage, (tx, ty), int(t), 34)
        self.ninja(stage, preview, "idle", fx, GROUND_Y, t=t)
        frame = frames[int(t // 6) % len(frames)]  # img_dur=6 as in game.py
        half = frame.get_width() // 2
        for i, (dx, dy) in enumerate(((-36, -2), (32, -16), (22, -26))):
            k = ((t + i * cycle / 3) % cycle) / fly
            if k >= 1:
                continue  # collected, waiting to respawn
            pull = k * k  # speeds up as it closes in, like the magnet's pull
            x, y = tx + dx * (1 - pull), ty + dy * (1 - pull)
            item_fx.pulled_coin(stage, (x, y), (tx, ty), int(t))
            stage.blit(frame, (round(x) - half, round(y) - frame.get_height() // 2))
        item_fx.magnet(stage, item_fx.companion_spot(rect, False, int(t)), int(t), True)


class Charm(Scene):
    """Lucky charm: it floats beside the ninja and sends up the extra life."""

    cycle = 170

    def draw(self, stage, preview, t):
        fx = STAGE[0] // 2 + 4
        rect = _hitbox(fx, GROUND_Y)
        spot = item_fx.companion_spot(rect, False, int(t))
        item_fx.omamori(stage, spot, int(t))
        self.ninja(stage, preview, "idle", fx, GROUND_Y, t=t)
        item_fx.charm_heart(stage, spot, int(t % self.cycle) - 20)


SCENES = {
    "Default": Dash,
    "Gun": Shooting,
    "Rifle": Shooting,
    "Ammo": AmmoCrate,
    "Ninja Stars": Throwing,
    "Sword": Slashing,
    "Grapple Hook": Grappling,
    "Shield": ShieldScene,
    "Moon Boots": MoonBoots,
    "Coin Magnet": Magnet,
    "Lucky Charm": Charm,
}


def scene_for(name: str) -> Scene | None:
    cls = SCENES.get(name)
    return cls(name) if cls else None
