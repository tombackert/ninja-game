"""How the store's weapons and gear look on the ninja.

One place draws them for a level (Player.render) and for the store and
accessories cards (scripts/item_showcase.py), so a card shows exactly what
a level does. Sprites come from tools/gen_pixel_art.py.

Everything here is drawn from timers and a tick count, never from the
simulation RNG, so drawing never changes a run (replays, multiplayer).
Positions are screen positions: callers subtract the camera offset.
"""

from __future__ import annotations

import math
import os

import pygame

IMG_DIR = "data/images"

# Weapon in the hand: sprite and the pixel of it the hand holds
HELD = {
    "Gun": ("weapons/pistol.png", (2, 4)),
    "Rifle": ("weapons/rifle.png", (7, 7)),
    "Sword": ("weapons/katana.png", (2, 2)),
    "Grapple Hook": ("weapons/hook.png", (1, 4)),
    "Ninja Stars": ("star.png", (4, 4)),
}
MUZZLE = {"Gun": (10, 2), "Rifle": (18, 4)}  # just past the barrel, sprite pixels
HOOK_TIP = (10, 4)  # the hook's point (it bites into the wall there)

# Frames a weapon's fire animation runs (Player.fire_fx counts them down)
FIRE_FRAMES = {"Gun": 9, "Rifle": 20, "Ninja Stars": 10, "Sword": 18, "Grapple Hook": 10}
KICK = {"Gun": 2, "Rifle": 3}  # recoil in pixels
SWING_FRAMES = 6  # the blade sweeps down, then returns to rest
SWORD_REST, SWORD_UP, SWORD_DOWN = 20, 105, -60  # blade angles (degrees, facing right)
STAR_RELOAD = 7  # frames the hand is empty after a throw
GRAPPLE_SHOT = 3  # frames the hook flies to its anchor
SHIELD_BREAK_FRAMES = 16
MOON_JUMP_FRAMES = 20
CHARM_INTRO_FRAMES = 110  # the charm's heart rising at a level's start

ROPE = ((96, 58, 32), (196, 146, 86))  # twisted rope: dark and light strands
GOLD = (255, 214, 90)
SPARK = (255, 250, 220)
GLOW = (150, 232, 255)
BOOT = {"cuff": (40, 96, 190), "shaft": (226, 222, 255), "sole": (150, 232, 255)}

_cache: dict = {}


def image(rel: str, flip: bool = False) -> pygame.Surface:
    """A sprite under data/images (black is transparent), mirrored if `flip`."""
    key = (rel, flip)
    img = _cache.get(key)
    if img is None:
        if flip:
            img = pygame.transform.flip(image(rel), True, False)
        else:
            img = pygame.image.load(os.path.join(IMG_DIR, rel))
            img.set_colorkey((0, 0, 0))
        _cache[key] = img
    return img


def _alpha(img: pygame.Surface, alpha: int) -> pygame.Surface:
    key = ("alpha", id(img), alpha)
    out = _cache.get(key)
    if out is None:
        out = img.copy()
        out.set_alpha(alpha)
        _cache[key] = (img, out)  # keep img alive: its id stays unique
        return out
    return out[1]


def blit_pivot(surf, img, pivot, at, angle: float = 0.0) -> None:
    """Draw `img` so its pixel `pivot` lands on `at`, turned `angle` degrees
    counter-clockwise around that pixel."""
    if not angle:
        surf.blit(img, (round(at[0] - pivot[0]), round(at[1] - pivot[1])))
        return
    turned = pygame.transform.rotate(img, angle)
    v = pygame.Vector2(pivot[0] + 0.5 - img.get_width() / 2, pivot[1] + 0.5 - img.get_height() / 2)
    v = v.rotate(-angle)
    rect = turned.get_rect(center=(round(at[0] - v.x), round(at[1] - v.y)))
    surf.blit(turned, rect)


def hand(rect: pygame.Rect, flip: bool) -> tuple[int, int]:
    """Where the ninja's front hand is (hitbox in screen space)."""
    return (rect.centerx - 6, rect.centery + 1) if flip else (rect.centerx + 5, rect.centery + 1)


def _sprite_point(name: str, point, at, flip: bool) -> tuple[float, float]:
    """Screen position of sprite pixel `point` of a weapon held at `at`."""
    rel, grip = HELD[name]
    dx = point[0] - grip[0]
    return (at[0] - dx if flip else at[0] + dx, at[1] + point[1] - grip[1])


def _held(surf, name, at, flip, angle=0.0):
    rel, grip = HELD[name]
    img = image(rel, flip)
    if flip:
        grip = (img.get_width() - 1 - grip[0], grip[1])
        angle = -angle
    blit_pivot(surf, img, grip, at, angle)


def _px(surf, pos, color, alpha=255):
    x, y = int(pos[0]), int(pos[1])
    if alpha <= 0 or not (0 <= x < surf.get_width() and 0 <= y < surf.get_height()):
        return
    if alpha >= 255:
        surf.set_at((x, y), color)
        return
    # blend (also right on the level's transparent layer)
    key = ("dot", tuple(color[:3]), alpha // 8)
    dot = _cache.get(key)
    if dot is None:
        dot = pygame.Surface((1, 1), pygame.SRCALPHA)
        dot.fill(tuple(color[:3]) + (min(255, (alpha // 8) * 8 + 4),))
        _cache[key] = dot
    surf.blit(dot, (x, y))


def sparkle(surf, pos, size: int, color=SPARK, alpha=255) -> None:
    """A little four-point twinkle (size 0 = one pixel)."""
    x, y = int(pos[0]), int(pos[1])
    _px(surf, (x, y), (255, 255, 255), alpha)
    for i in range(1, size + 1):
        a = alpha * (size + 1 - i) // (size + 1)
        for dx, dy in ((i, 0), (-i, 0), (0, i), (0, -i)):
            _px(surf, (x + dx, y + dy), color, a)


def muzzle_flash(surf, pos, flip: bool, since: int, big: bool) -> None:
    """Bright star at the barrel's end for the first frames after a shot."""
    d = -1 if flip else 1
    x, y = int(pos[0]), int(pos[1])
    length = (5 if big else 3) - since * 2
    if length <= 0:
        return
    core = (255, 255, 235)
    for i in range(length):
        col = core if i < length // 2 else GOLD if i < length - 1 else (255, 150, 60)
        _px(surf, (x + d * i, y), col)
    for i in range(1, max(2, length // 2)):
        col = GOLD if i == 1 else (255, 150, 60)
        _px(surf, (x + d * (length // 3), y - i), col)
        _px(surf, (x + d * (length // 3), y + i), col)
    if big and since == 0:
        _px(surf, (x + d * 2, y - 2), (255, 150, 60))
        _px(surf, (x + d * 2, y + 2), (255, 150, 60))


def _smoke(surf, pos, flip, since):
    d = -1 if flip else 1
    for i in range(3):
        t = since - 2 - i * 2
        if t < 0:
            continue
        life = 16
        if t >= life:
            continue
        r = 1 + t // 6
        x = pos[0] + d * (2 + i * 2 + t * 0.25)
        y = pos[1] - 1 - t * 0.45 - i
        a = int(150 * (1 - t / life))
        puff = pygame.Surface((r * 2 + 1, r * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(puff, (215, 215, 225, a), (r, r), r)
        surf.blit(puff, (round(x - r), round(y - r)))


def _casing(surf, at, flip, since):
    """A spent shell flips out of the gun's top and falls behind."""
    if since >= 10:
        return
    d = -1 if flip else 1
    x = at[0] - d * since * 0.7
    y = at[1] - 3 - 1.6 * since + 0.22 * since * since
    _px(surf, (x, y), GOLD)
    _px(surf, (x - d, y), (190, 130, 40))


def rope(surf, a, b) -> None:
    """Twisted rope from a to b, one pixel thick."""
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])))
    for i in range(n + 1):
        t = i / n if n else 0
        _px(surf, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), ROPE[(i // 2) % 2])


def hook_at(surf, tip, pointing_left: bool) -> None:
    img = image(HELD["Grapple Hook"][0], pointing_left)
    tx = img.get_width() - 1 - HOOK_TIP[0] if pointing_left else HOOK_TIP[0]
    blit_pivot(surf, img, (tx, HOOK_TIP[1]), tip)


def slash(surf, rect: pygame.Rect, flip: bool, since: int) -> None:
    """The sword's crescent in front of the ninja."""
    if not 0 <= since < SWING_FRAMES:
        return
    idx = (0, 1, 2, 2, 3, 3)[since]
    img = image(f"weapons/slash/{idx}.png", flip)
    y = rect.centery - img.get_height() // 2
    x = rect.left - img.get_width() + 1 if flip else rect.right - 1
    surf.blit(img, (x, y))


def sword_angle(since: int | None) -> float:
    """Blade angle: raised, swept down, then back to rest."""
    if since is None:
        return SWORD_REST
    if since < SWING_FRAMES:
        p = since / (SWING_FRAMES - 1)
        return SWORD_UP + (SWORD_DOWN - SWORD_UP) * (1 - (1 - p) ** 2)
    total = FIRE_FRAMES["Sword"] - SWING_FRAMES
    q = min(1.0, (since - SWING_FRAMES + 1) / total)
    return SWORD_DOWN + (SWORD_REST - SWORD_DOWN) * (1 - (1 - q) ** 3)


def weapon(
    surf,
    name: str,
    rect: pygame.Rect,
    flip: bool,
    tick: int,
    since: int | None = None,
    grapple=None,
    whiff: bool = False,
) -> None:
    """The weapon in the ninja's hand with its animation. `since`: frames
    since it was last used (None: at rest); `grapple`: (anchor in screen
    space, frames pulled) while hooked; `whiff`: the last throw missed."""
    if name not in HELD:
        return
    at = hand(rect, flip)
    d = -1 if flip else 1
    if name in ("Gun", "Rifle"):
        kick = 0
        if since is not None:
            kick = max(0, KICK[name] - since // 2)
        grip_at = (at[0] - d * kick, at[1] - (1 if since is not None and since < 2 else 0))
        _held(surf, name, grip_at, flip)
        if since is not None:
            muzzle = _sprite_point(name, MUZZLE[name], grip_at, flip)
            muzzle_flash(surf, muzzle, flip, since, big=name == "Rifle")
            _casing(surf, grip_at, flip, since)
            if name == "Rifle":
                _smoke(surf, muzzle, flip, since)
    elif name == "Sword":
        _held(surf, name, at, flip, sword_angle(since))
        if since is not None:
            slash(surf, rect, flip, since)
    elif name == "Ninja Stars":
        if since is not None and since < STAR_RELOAD:
            return
        bob = round(math.sin(tick * 0.12))
        _held(surf, name, (at[0], at[1] - 3 + bob), flip)
        if since is not None and since < STAR_RELOAD + 3:
            sparkle(surf, (at[0], at[1] - 3), 2 - (since - STAR_RELOAD))
    elif name == "Grapple Hook":
        if grapple is not None:
            anchor, frames = grapple
            t = min(1.0, (frames + 1) / GRAPPLE_SHOT)
            tip = (at[0] + (anchor[0] - at[0]) * t, at[1] + (anchor[1] - at[1]) * t)
            rope(surf, at, tip)
            hook_at(surf, tip, anchor[0] < at[0])
            if 1 <= frames < 6:
                sparkle(surf, anchor, 3 - frames // 2, GOLD)
        elif whiff and since is not None and since < FIRE_FRAMES["Grapple Hook"]:
            half = FIRE_FRAMES["Grapple Hook"] // 2
            reach = 70 * (since / half if since < half else (FIRE_FRAMES["Grapple Hook"] - since) / half)
            tip = (at[0] + d * reach, at[1])
            rope(surf, at, tip)
            hook_at(surf, tip, flip)
        else:
            _held(surf, name, at, flip)


# --- Bullets and stars in flight ---------------------------------------------


def bullet_image(rifle: bool, left: bool) -> pygame.Surface:
    """The ninja's bullet: a hot head with a fading tracer (longer for the rifle)."""
    key = ("bullet", rifle, left)
    img = _cache.get(key)
    if img is None:
        length = 14 if rifle else 8
        img = pygame.Surface((length, 3), pygame.SRCALPHA)
        trail = (120, 220, 255) if rifle else (255, 170, 60)
        for x in range(length - 2):
            a = int(200 * (x + 1) / (length - 2))
            img.set_at((x, 1), trail + (a,))
        mid = (200, 245, 255) if rifle else GOLD
        img.set_at((length - 3, 1), mid + (255,))
        img.fill((255, 255, 240, 255), pygame.Rect(length - 2, 0, 2, 3))
        img.set_at((length - 2, 0), mid + (255,))
        img.set_at((length - 2, 2), mid + (255,))
        if left:
            img = pygame.transform.flip(img, True, False)
        _cache[key] = img
    return img


def star_image(angle: int, ghost: bool = False) -> pygame.Surface:
    """The spinning shuriken; `ghost` is its faint after-image."""
    key = ("star", angle, ghost)
    img = _cache.get(key)
    if img is None:
        img = pygame.transform.rotate(image("star.png"), angle)
        if ghost:
            img = img.copy()
            img.set_alpha(80)
        _cache[key] = img
    return img


# --- Gear ---------------------------------------------------------------------


def boots_overlay(frame: pygame.Surface) -> pygame.Surface:
    """Moon boots over a ninja frame: the lowest pixels of each leg turn into
    a blue cuff, a silver shaft and a glowing sole. Works for every skin and
    every move, since it follows the frame's own feet."""
    key = ("boots", id(frame))
    hit = _cache.get(key)
    if hit is not None:
        return hit[1]
    w, h = frame.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    colorkey = frame.get_colorkey()

    def solid(x, y):
        c = frame.get_at((x, y))
        return c.a > 0 and (colorkey is None or tuple(c)[:3] != tuple(colorkey)[:3])

    bottoms = [max((y for y in range(h) if solid(x, y)), default=-1) for x in range(w)]
    low = max(bottoms)
    for x, bottom in enumerate(bottoms):
        if bottom < low - 4:  # not a leg (hair, scarf, a tail end)
            continue
        for depth, part in ((0, "sole"), (1, "shaft"), (2, "cuff")):
            y = bottom - depth
            if y >= 0 and solid(x, y):
                out.set_at((x, y), BOOT[part] + (255,))
    _cache[key] = (frame, out)
    return out


def boot_glow(surf, rect: pygame.Rect, tick: int, charged: bool) -> None:
    """Soft light under the soles; it pulses while the air jump is ready."""
    a = 120 + int(50 * math.sin(tick * 0.2)) if charged else 45
    glow = pygame.Surface((12, 4), pygame.SRCALPHA)
    pygame.draw.ellipse(glow, GLOW + (a // 2,), glow.get_rect())
    pygame.draw.ellipse(glow, GLOW + (a,), pygame.Rect(3, 1, 6, 2))
    surf.blit(glow, (rect.centerx - 6, rect.bottom - 1))


def moon_jump(surf, pos, since: int) -> None:
    """The double jump: a ring of moonlight bursts from the soles and little
    stars drift down."""
    if not 0 <= since < MOON_JUMP_FRAMES:
        return
    k = since / MOON_JUMP_FRAMES
    for lag, color in ((0, GLOW), (4, (255, 255, 255))):
        s = since - lag
        if s < 0:
            continue
        w = int(6 + s * 1.1)
        hgt = max(3, w // 3)
        ring = pygame.Surface((w + 2, hgt + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, color + (int(240 * (1 - k)),), ring.get_rect(), 1)
        surf.blit(ring, (round(pos[0] - ring.get_width() / 2), round(pos[1] - ring.get_height() / 2 + s * 0.3)))
    for i, ang in enumerate((0.4, 2.7, 1.3, 1.9)):
        dist = 3 + since * (0.8 + 0.15 * i)
        x = pos[0] + math.cos(ang) * dist * (1 if i % 2 else -1)
        y = pos[1] + math.sin(ang) * dist * 0.5 + since * 0.25
        size = 1 if since < MOON_JUMP_FRAMES * 0.6 else 0
        sparkle(surf, (x, y), size, (200, 240, 255), int(255 * (1 - k)))


def shield(surf, center, tick: int, ready: bool, rearm: float = 0.0, broke: int | None = None) -> None:
    """Energy bubble around the ninja. While a charge re-arms a dotted ring
    fills up (`rearm` 0..1); `broke`: frames since a hit shattered it."""
    cx, cy = int(center[0]), int(center[1])
    r = 13
    if ready:
        b = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        c = (r + 1, r + 1)
        pulse = int(14 * math.sin(tick * 0.08))
        pygame.draw.circle(b, (110, 190, 255, 42 + pulse), c, r)
        pygame.draw.circle(b, (200, 240, 255, 50), c, r - 2, 1)
        pygame.draw.circle(b, (170, 225, 255, 190), c, r, 1)
        # a glint runs around the rim, another sits top-left
        for k in range(6):
            ang = tick * 0.05 - k * 0.11
            x = c[0] + math.cos(ang) * (r - 0.5)
            y = c[1] + math.sin(ang) * (r - 0.5)
            b.set_at((int(x), int(y)), (255, 255, 255, 230 - k * 35))
        for x, y in ((-6, -9), (-8, -7), (-9, -5)):
            b.set_at((c[0] + x, c[1] + y), (255, 255, 255, 170))
        surf.blit(b, (cx - c[0], cy - c[1]))
    elif rearm > 0:
        steps = int(72 * rearm)
        for i in range(steps):
            if i % 3 == 2:
                continue
            ang = -math.pi / 2 + i * math.tau / 72
            _px(surf, (cx + math.cos(ang) * r, cy + math.sin(ang) * r), (200, 240, 255), 170)
    if broke is not None and 0 <= broke < SHIELD_BREAK_FRAMES:
        fade = broke / SHIELD_BREAK_FRAMES
        rr = int(r + broke * 1.1)
        ring = pygame.Surface((rr * 2 + 2, rr * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(ring, (200, 240, 255, int(210 * (1 - fade))), (rr + 1, rr + 1), rr, 1)
        surf.blit(ring, (cx - rr - 1, cy - rr - 1))
        for i in range(8):
            ang = i * math.tau / 8 + 0.4
            dist = r - 2 + broke * 1.6
            x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist + broke * 0.15
            a = int(255 * (1 - fade))
            _px(surf, (x, y), (170, 225, 255), a)
            _px(surf, (x + math.cos(ang), y + math.sin(ang)), (255, 255, 255), a)


def companion_spot(rect: pygame.Rect, flip: bool, tick: int) -> tuple[float, float]:
    """Where a floating charm hovers: behind the ninja's shoulder, bobbing."""
    behind = 1 if flip else -1
    return (
        rect.centerx + behind * 10 + math.sin(tick * 0.035) * 1.0,
        rect.top - 3 + math.sin(tick * 0.07) * 1.6,
    )


def _twinkles(surf, center, tick, color, every=45, spread=(14, 12)):
    """A twinkle now and then around `center` (spots cycle through a table)."""
    spots = ((-5, -6), (6, -3), (-6, 4), (4, 6), (1, -8), (-7, -1))
    t = tick % every
    life = 16
    if t < life:
        dx, dy = spots[(tick // every) % len(spots)]
        size = (0, 1, 2, 2, 1, 1, 0)[min(6, t * 7 // life)]
        sparkle(surf, (center[0] + dx * spread[0] / 14, center[1] + dy * spread[1] / 12), size, color)


def omamori(surf, center, tick: int) -> None:
    """The lucky charm floating beside the ninja, glinting gold."""
    img = image("gear/omamori.png")
    surf.blit(img, (round(center[0] - img.get_width() / 2), round(center[1] - img.get_height() / 2)))
    _twinkles(surf, center, tick, GOLD)


def charm_heart(surf, center, since: int) -> None:
    """At a level's start the charm sends up a heart: the extra life."""
    if not 0 <= since < CHARM_INTRO_FRAMES:
        return
    heart = image("gear/heart.png")
    plus = image("gear/plus_one.png")
    rise = min(since, 50) * 0.2
    a = 255 if since < CHARM_INTRO_FRAMES - 30 else int(255 * (CHARM_INTRO_FRAMES - since) / 30)
    pop = 1 if since < 6 else 0
    x = round(center[0] - (heart.get_width() + plus.get_width() + 1) / 2)
    y = round(center[1] - 10 - rise - pop)
    surf.blit(_alpha(heart, a), (x, y))
    surf.blit(_alpha(plus, a), (x + heart.get_width() + 1, y))
    if since < 24:
        sparkle(surf, (x - 2, y + 1), 1 + (since // 8) % 2, GOLD)
        sparkle(surf, (x + 16, y + 5), 1 - (since // 8) % 2, GOLD)


def magnet(surf, center, tick: int, pulling: bool) -> None:
    """The coin magnet floating beside the ninja; sparks jump between its
    poles while it pulls."""
    img = image("gear/magnet.png")
    x, y = round(center[0] - img.get_width() / 2), round(center[1] - img.get_height() / 2)
    surf.blit(img, (x, y))
    if pulling and (tick // 3) % 3 != 2:
        bottom = y + img.get_height()
        for i, (px, dy) in enumerate(((1, 1), (2, 2), (6, 2), (7, 1))):
            if (tick // 3 + i) % 2:
                _px(surf, (x + px, bottom + dy), GLOW)
        _px(surf, (x + 4, bottom + 1 + (tick // 3) % 2), (255, 255, 255))


def magnet_field(surf, center, tick: int, radius: int) -> None:
    """Dotted rings closing in on the ninja: the magnet's reach."""
    for k in range(2):
        t = ((tick + k * 30) % 60) / 60
        r = radius * (1 - t)
        if r < 6:
            continue
        a = int(150 * min(1.0, 3 * t) * (1 - t))  # fades in at the rim, out at the ninja
        steps = max(12, int(r * 0.8))
        for i in range(0, steps, 2):
            ang = i * math.tau / steps + tick * 0.01
            _px(surf, (center[0] + math.cos(ang) * r, center[1] + math.sin(ang) * r), (255, 236, 150), a)


def pulled_coin(surf, coin_center, toward, tick: int) -> None:
    """Gold dust trailing a coin the magnet pulls."""
    dx, dy = toward[0] - coin_center[0], toward[1] - coin_center[1]
    dist = math.hypot(dx, dy) or 1
    ux, uy = dx / dist, dy / dist
    for i, back in enumerate((6, 9, 12)):
        if (tick // 2 + i) % 3 == 0:
            continue
        _px(surf, (coin_center[0] - ux * back, coin_center[1] - uy * back), GOLD, 200 - i * 50)
