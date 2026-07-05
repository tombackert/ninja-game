# Store Expansion — 13 New Game Elements

Full design & balance rationale: [docs/new-game-elements.md](../new-game-elements.md)

## New weapons (weapon slot)
- **Rifle** ($2000): 6.5 px/f bullet, 2 ammo/shot, 25f cooldown
- **Ninja Stars** ($300 / 20): arcing, piercing shuriken; consumable
- **Sword** ($1000): melee slash, kills in reach, parries enemy projectiles
- **Grapple Hook** ($5000): pulls the player to walls within 140 px

## New gear category (passive slot, one active)
- **Shield** ($100/charge): absorbs one hit, ~10 s re-arm
- **Moon Boots** ($2500): double jump
- **Coin Magnet** ($1500): attracts coins within 48 px
- **Lucky Charm** ($3000): +1 life on fresh level start

## New skins (palette-swap pixel art, `tools/gen_pixel_art.py`)
Gold ($2000), Platinum ($3000), Diamond ($5000), Assassin ($7000),
Berserker ($10000)

## System changes
- `CollectableManager`: every item purchaseable; new `GEAR` list; new
  persisted fields `rifle`, `coin_magnet`, `lucky_charm`
- `settings.selected_gear` (new); equip indices clamped on load (migration)
- `ProjectileSystem`: per-projectile `vy`/`gravity`/`kind`/`pierce`,
  `destroy_in_rect` (sword parry), rotating star rendering
- Accessories menu: third panel (TAB cycles Weapons → Gear → Skins),
  padlocks now show ownership
- HUD: contextual `Stars:`/`Shield:` lines when equipped

## Verification
- `tests/test_new_items.py` (25 unit tests; suite total 239 green)
- `tools/items_e2e.py`: real-process E2E in an isolated data sandbox —
  buys all items through the store UI, equips via accessories UI, exercises
  every mechanic in-game and pixel-checks rendering (56/56 checks)
- `tools/mp_e2e.py` still green (multiplayer unaffected)
