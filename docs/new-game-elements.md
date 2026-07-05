# New Game Elements — Concept & Balance Design

Goal: extend the store with functional items and skins that add real gameplay
variety without breaking the existing balance (dash-kill core loop, 1-hit
projectile deaths, coin economy of ~1 coin per kill plus map coins).

## Element Overview (13 new elements)

### Weapons (active, equipped in the single weapon slot)

| # | Element | Price | Mechanics | Balancing levers |
|---|---------|-------|-----------|------------------|
| 1 | Rifle | 2000 | Fast projectile (6.5 px/f vs. gun 3.5) | Costs **2 ammo** per shot, 25-frame cooldown (gun: 10) |
| 2 | Ninja Stars | 300 per 20 | Thrown shuriken with gravity arc, **pierces** enemies | Consumable, 15-frame cooldown, arc requires aim/lead |
| 3 | Sword | 1000 | Melee slash (22×18 px hitbox in facing direction), kills enemies **and destroys enemy projectiles** | Melee range = high risk, 18-frame cooldown, no ranged option |
| 4 | Grapple Hook | 5000 | Fires a hook up to 140 px in facing direction; on solid-tile hit the player is pulled at 4 px/f | Zero damage (pure mobility), 45-frame cooldown, occupies the weapon slot |

### Gear (passive, NEW third equipment category — only one active)

| # | Element | Price | Mechanics | Balancing levers |
|---|---------|-------|-----------|------------------|
| 5 | Shield | 100 per charge | Absorbs one hit (projectile), visible bubble; re-arms after 600 frames (~10 s) if charges remain | Each absorbed hit consumes a purchased charge; blocks the gear slot |
| 6 | Moon Boots | 2500 | One extra air jump (double jump) | Air jump is weaker (-2.7 vs. -3.0); blocks the gear slot |
| 7 | Coin Magnet | 1500 | Attracts coins within 48 px radius (1.8 px/f) | No combat benefit (quality of life / speedrun routing) |
| 8 | Lucky Charm | 3000 | +1 life on fresh level start | Does not apply on respawn; blocks the gear slot |

### Skins (cosmetic prestige, palette-swap pixel art of the ninja)

| # | Element | Price | Look |
|---|---------|-------|------|
| 9 | Gold Ninja | 2000 | Gold suit, white scarf |
| 10 | Platinum Ninja | 3000 | Silver suit, blue scarf |
| 11 | Diamond Ninja | 5000 | Ice-blue suit, purple scarf |
| 12 | Assassin | 7000 | Near-black suit, crimson scarf |
| 13 | Berserker | 10000 | Red-brown suit, ember highlights, black scarf |

## Balance Principles

1. **Slot exclusivity**: one weapon + one gear. No stacking of shield, double
   jump and extra life at once — players pick a loadout (6 weapons × 5 gear =
   30 combinations).
2. **Consumables tie power to income**: ammo (2 coins/shot), rifle
   (4 coins/shot), stars (15 coins/throw), shield charges (100 coins/hit
   absorbed). Killing an enemy yields 1 coin, so sustained ranged play is a
   net cost; dash kills stay the efficient core loop.
3. **Risk/reward**: the sword is the only ammo-free weapon but forces melee
   range against shooting enemies; the projectile-destroy mechanic rewards
   timing.
4. **Mobility vs. power**: grapple hook and moon boots open new routes and
   speedrun lines but give zero combat power.
5. **Skins are pure cosmetics** — prestige pricing, no gameplay effect.

## Physics Concepts

- **Star projectiles**: extend ProjectileSystem with per-projectile
  `vy`/`gravity` (0.08/f — lighter than player gravity 0.1) and `pierce`.
  Spawn with vx ±3.0, vy −1.5 → arc peaks ~14 px above throw height,
  ~55–70 px effective range on flat ground.
- **Sword slash**: instant hitbox (no projectile), 22 px reach × 18 px height
  anchored at the player's facing edge for 1 frame; slash VFX rendered for
  ~6 frames.
- **Grapple**: discrete ray sampling every 4 px (tile size 16 → cannot skip a
  tile), max 140 px. While pulling: velocity = normalized direction × 4,
  gravity suspended, release on arrival (<6 px), collision, jump input, or
  60-frame safety timeout. Retains momentum on release (velocity carries).
- **Shield**: intercepts the two player-damage paths in ProjectileSystem
  (enemy shots and PvP shots); consumes a charge instead of a life, grants
  the same spark/screenshake feedback, re-arms after 600 frames.
- **Moon Boots**: `air_jumps` counter reset on ground contact; air jump sets
  vy −2.7 and does not consume the (already spent) ground jump.
- **Coin Magnet**: coins within 48 px move toward the player center at
  1.8 px/f (rect updated with pos so pickup collision stays correct).

## Persistence & Store

- All 13 elements get `purchaseable: True` entries in the item registry
  (single source of truth: `CollectableManager._ITEM_DEFS`).
- New persisted fields in `data/collectables.json`: `rifle`, `coin_magnet`,
  `lucky_charm` (others existed already).
- New setting: `selected_gear` (index into `CollectableManager.GEAR`).
- `WEAPONS` list is re-cut to actual weapons (Default, Gun, Rifle, Ninja
  Stars, Sword, Grapple Hook); Shield/Moon Boots move to `GEAR`
  (None, Shield, Moon Boots, Coin Magnet, Lucky Charm). `selected_weapon`
  is clamped on load for old save files.
