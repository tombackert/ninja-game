"""Level hazards: spikes, crumbling blocks and flame jets.

All three are ordinary tiles of the map, placed in the editor (tile groups
`spikes`, `crumble`, `flamejet`) or by the level builder
(tools/worlds/builder.py). Each has a number to turn, so a level can be
made a little harder instead of only much harder:

- **Spikes** (`spikes`, variant = facing: 0 up, 1 down, 2 left, 3 right):
  not solid; touching their points costs a life. The dial is where they sit:
  a spike on a landing shortens it, one under a ceiling lowers it.
- **Crumbling blocks** (`crumble`, variant 0): solid, but CRUMBLE_DELAY
  frames after a player first stands on one it falls away, and comes back
  CRUMBLE_RETURN frames later (once nobody is inside it). The dial is how
  long a player may stand: a run of them must be crossed without a stop.
- **Flame jets** (`flamejet`, variant = facing as for spikes): a solid
  nozzle block that fires a flame FLAME_REACH tiles long (shorter where a
  solid tile stops it) on a beat. Optional tile fields: `period` (frames per
  cycle, default 120), `on` (frames it burns, default 48) and `phase`
  (frames it runs ahead, default 0). It flickers for FLAME_WARN frames before
  it fires. The dial is the beat: a long `on` in a short `period` leaves a
  narrow gap, jets in a row with shifted phases make a wave.

Enemies walk around spikes but burn in flames (`burn_enemies`): a player
can lure a chaser into a jet. Spikes and flames hurt like a bullet: a life
lost (Player.take_hit), the player thrown back and blinking for a moment,
no respawn. The beat runs on the system's own `clock`: simulation ticks since
the level was (re)loaded, so every attempt starts on the same beat, on every
machine and in every replay, and a planned route (its frames counted from
the spawn) can be checked against it (tools/worlds/hazard_check.py).
"""

from __future__ import annotations

from typing import Iterable

import pygame

SPIKES = "spikes"
CRUMBLE = "crumble"
FLAMEJET = "flamejet"
HAZARD_TILES = (SPIKES, CRUMBLE, FLAMEJET)

UP, DOWN, LEFT, RIGHT = range(4)
FACING = {UP: (0, -1), DOWN: (0, 1), LEFT: (-1, 0), RIGHT: (1, 0)}

# The deadly part of a spike tile (x, y, w, h inside the tile) by facing: the
# points' half, a pixel in from the sides
SPIKE_BOXES = {UP: (1, 9, 14, 7), DOWN: (1, 0, 14, 7), LEFT: (9, 1, 7, 14), RIGHT: (0, 1, 7, 14)}

CRUMBLE_DELAY = 30  # frames from the first step on a block until it falls
CRUMBLE_RETURN = 180  # frames until a fallen block is back

FLAME_REACH = 3  # tiles
FLAME_WIDTH = 10  # px across the flame
FLAME_PERIOD = 120
FLAME_ON = 48
FLAME_WARN = 24  # frames of flicker before it fires (harmless)

FLAME_OUTER = (232, 106, 36)
FLAME_INNER = (252, 206, 84)
FLAME_CORE = (255, 246, 214)
SMOKE = (70, 64, 80)


def spike_box(tx: int, ty: int, facing: int, ts: int = 16) -> tuple:
    """Deadly box (x, y, w, h) in px of a spike tile at tile (tx, ty)."""
    x, y, w, h = SPIKE_BOXES.get(facing, SPIKE_BOXES[UP])
    return (tx * ts + x, ty * ts + y, w, h)


def flame_cells(tx: int, ty: int, facing: int, is_solid, reach: int = FLAME_REACH) -> list:
    """Tiles a flame jet at (tx, ty) burns: up to `reach` in its facing,
    stopped by the first solid tile (`is_solid(x, y)`)."""
    dx, dy = FACING.get(facing, FACING[UP])
    cells = []
    for i in range(1, reach + 1):
        c = (tx + dx * i, ty + dy * i)
        if is_solid(*c):
            break
        cells.append(c)
    return cells


def flame_box(cell: tuple, facing: int, ts: int = 16) -> tuple:
    """Deadly box (x, y, w, h) in px of one burning cell."""
    x, y = cell[0] * ts, cell[1] * ts
    pad = (ts - FLAME_WIDTH) // 2
    if facing in (UP, DOWN):
        return (x + pad, y, FLAME_WIDTH, ts)
    return (x, y + pad, ts, FLAME_WIDTH)


def flame_state(tick: int, period: int = FLAME_PERIOD, on: int = FLAME_ON, phase: int = 0) -> str:
    """ "burn", "warn" (the flicker before it fires) or "off" at `tick`."""
    t = (tick + phase) % period
    if t < on:
        return "burn"
    if t >= period - FLAME_WARN:
        return "warn"
    return "off"


class FlameJet:
    def __init__(self, tile: dict, cells: list, ts: int):
        self.pos = tuple(tile["pos"])
        self.facing = tile.get("variant", UP)
        self.period = max(1, int(tile.get("period", FLAME_PERIOD)))
        self.on = int(tile.get("on", FLAME_ON))
        self.phase = int(tile.get("phase", 0))
        self.cells = cells
        self.ts = ts

    def state(self, tick: int) -> str:
        return flame_state(tick, self.period, self.on, self.phase)

    def burning(self, tick: int) -> bool:
        return self.state(tick) == "burn"


class HazardSystem:
    """The hazards of the loaded level: deadly zones by tile and the state of
    the crumbling blocks. Built by every level load (Game.load_level,
    HeadlessGame._load_level); `restore()` puts fallen blocks back before a
    respawn."""

    def __init__(self, tilemap):
        self.tilemap = tilemap
        ts = self.ts = tilemap.tile_size
        self.jets: list[FlameJet] = []
        # tile -> [(rect, cause, jet or None)]: zones overlapping that tile
        self.zones: dict[tuple, list] = {}
        self.crumbling: dict[str, int] = {}  # tile key -> frames until it falls
        self.fallen: dict[str, list] = {}  # tile key -> [tile, frames until it is back]
        self.crumble_count = 0
        self.clock = 0  # ticks since the level was loaded (update() counts them)

        def solid(x, y):
            return bool(tilemap.solid_check((x * ts, y * ts)))

        for tile in list(tilemap.tilemap.values()):
            kind = tile["type"]
            tx, ty = tile["pos"]
            if kind == SPIKES:
                self._zone((tx, ty), pygame.Rect(spike_box(tx, ty, tile.get("variant", UP), ts)), "spikes", None)
            elif kind == FLAMEJET:
                jet = FlameJet(tile, flame_cells(tx, ty, tile.get("variant", UP), solid), ts)
                self.jets.append(jet)
                for cell in jet.cells:
                    self._zone(cell, pygame.Rect(flame_box(cell, jet.facing, ts)), "flame", jet)
            elif kind == CRUMBLE:
                self.crumble_count += 1

    def _zone(self, cell, rect, cause, jet):
        self.zones.setdefault(cell, []).append((rect, cause, jet))

    @property
    def empty(self) -> bool:
        return not self.zones and not self.crumble_count

    # --- deadly zones ---------------------------------------------------------------
    def lethal(self, rect: pygame.Rect, tick: int | None = None, only: str | None = None) -> str | None:
        """Cause of a hit ("spikes", "flame") if `rect` touches a deadly zone at
        `tick` (default: now, `clock`), else None. `only`: that cause alone."""
        touch = self.touching(rect, tick, only)
        return touch[0] if touch else None

    def touching(
        self, rect: pygame.Rect, tick: int | None = None, only: str | None = None
    ) -> "tuple[str, pygame.Rect] | None":
        """(cause, zone) of the deadly zone `rect` touches at `tick`, or None."""
        if not self.zones:
            return None
        if tick is None:
            tick = self.clock
        ts = self.ts
        for tx in range(rect.left // ts, (rect.right - 1) // ts + 1):
            for ty in range(rect.top // ts, (rect.bottom - 1) // ts + 1):
                for zone, cause, jet in self.zones.get((tx, ty), ()):
                    if only is not None and cause != only:
                        continue
                    if zone.colliderect(rect) and (jet is None or jet.burning(tick)):
                        return cause, zone
        return None

    def burn_enemies(self, enemies: list, game=None) -> int:
        """Remove the enemies standing in a burning flame (spikes they walk
        around, see scripts/ai/behaviors.py). Returns how many burned."""
        if not self.jets:
            return 0
        burned = 0
        for enemy in list(enemies):
            if self.lethal(enemy.rect(), only="flame"):
                enemies.remove(enemy)
                enemy.alive = False
                burned += 1
                if game is not None and hasattr(game, "sparks"):
                    from scripts.effects_util import spawn_hit_sparks

                    spawn_hit_sparks(game, enemy.rect().center, count=12)
        return burned

    # --- crumbling blocks -----------------------------------------------------------
    def update(self, players: Iterable, game=None) -> None:
        """Advance one tick: the clock, and the crumbling blocks (start the ones a
        player stands on, drop the ripe ones, bring fallen ones back)."""
        self.clock += 1
        if not self.crumble_count:
            return
        tm = self.tilemap.tilemap
        ts = self.ts
        for p in players:
            if not p.collisions.get("down"):
                continue
            r = p.rect()
            for x in (r.left, r.right - 1):
                key = f"{x // ts};{r.bottom // ts}"
                tile = tm.get(key)
                if tile is not None and tile["type"] == CRUMBLE and key not in self.crumbling:
                    self.crumbling[key] = CRUMBLE_DELAY
                    tile["variant"] = 1  # cracked
        broke = False
        for key in list(self.crumbling):
            self.crumbling[key] -= 1
            if self.crumbling[key] <= 0:
                del self.crumbling[key]
                tile = tm.pop(key, None)
                if tile is not None:
                    tile["variant"] = 0
                    self.fallen[key] = [tile, CRUMBLE_RETURN]
                    broke = True
                    if game is not None and hasattr(game, "sparks"):
                        from scripts import dust
                        from scripts.effects_util import spawn_hit_sparks

                        spawn_hit_sparks(game, ((tile["pos"][0] + 0.5) * ts, (tile["pos"][1] + 0.5) * ts), count=6)
                        frames = getattr(game, "assets", {}).get(CRUMBLE)
                        rect = pygame.Rect(tile["pos"][0] * ts, tile["pos"][1] * ts, ts, ts)
                        dust.rubble(game, rect, frames[0] if frames else None)
        audio = getattr(game, "audio", None)
        if broke and audio is not None:
            audio.play("crumble")  # once, however many blocks give way together
        players = list(players)
        for key in list(self.fallen):
            entry = self.fallen[key]
            entry[1] -= 1
            if entry[1] > 0:
                continue
            tile = entry[0]
            rect = pygame.Rect(tile["pos"][0] * ts, tile["pos"][1] * ts, ts, ts)
            if any(rect.colliderect(p.rect()) for p in players):
                continue  # wait until nobody stands inside it
            tm[key] = tile
            del self.fallen[key]

    def restore(self) -> None:
        """Put every fallen or cracking block back whole (respawn)."""
        tm = self.tilemap.tilemap
        for key, (tile, _left) in self.fallen.items():
            tile["variant"] = 0
            tm[key] = tile
        for key in self.crumbling:
            if key in tm:
                tm[key]["variant"] = 0
        self.fallen.clear()
        self.crumbling.clear()

    # --- drawing --------------------------------------------------------------------
    def render(self, surf: pygame.Surface, offset=(0, 0), tick: int | None = None) -> None:
        """Draw the flames (the nozzles, spikes and blocks are tiles). Reads
        nothing but the clock: no RNG, so drawing never changes the game."""
        if not self.jets:
            return
        if tick is None:
            tick = self.clock
        ts = self.ts
        w, h = surf.get_size()
        for jet in self.jets:
            jx, jy = jet.pos[0] * ts - offset[0], jet.pos[1] * ts - offset[1]
            reach = (FLAME_REACH + 1) * ts
            if jx < -reach or jy < -reach or jx > w + reach or jy > h + reach:
                continue
            state = jet.state(tick)
            if state == "off":
                continue
            if state == "warn":
                self._draw_warn(surf, jet, offset, tick)
            else:
                self._draw_flame(surf, jet, offset, tick)

    def _mouth(self, jet: FlameJet, offset) -> tuple:
        """Screen px of the middle of the nozzle's open side."""
        ts = self.ts
        dx, dy = FACING.get(jet.facing, FACING[UP])
        cx = jet.pos[0] * ts + ts / 2 + dx * ts / 2 - offset[0]
        cy = jet.pos[1] * ts + ts / 2 + dy * ts / 2 - offset[1]
        return cx, cy

    def _draw_warn(self, surf, jet: FlameJet, offset, tick: int) -> None:
        dx, dy = FACING.get(jet.facing, FACING[UP])
        cx, cy = self._mouth(jet, offset)
        for i in range(3):
            # puffs drift out of the mouth and flicker on alternate frames
            t = (tick // 3 + i * 2) % 6
            if (tick + i) % 2:
                continue
            px, py = cx + dx * (t + 1) + (i - 1) * 2 * abs(dy), cy + dy * (t + 1) + (i - 1) * 2 * abs(dx)
            color = FLAME_OUTER if t < 2 else SMOKE
            surf.fill(color, (int(px), int(py), 2, 2))

    def _draw_flame(self, surf, jet: FlameJet, offset, tick: int) -> None:
        if not jet.cells:
            return
        ts = self.ts
        dx, dy = FACING.get(jet.facing, FACING[UP])
        length = len(jet.cells) * ts
        cx, cy = self._mouth(jet, offset)
        for step in range(0, length, 2):
            # the flame narrows toward its tip and wavers with the tick
            frac = step / length
            wave = ((tick // 2 + step // 4) % 3) - 1
            half_outer = max(1, int((FLAME_WIDTH / 2) * (1 - 0.55 * frac)) + wave)
            half_inner = max(0, half_outer - 2)
            half_core = max(0, half_outer - 4)
            px, py = cx + dx * step, cy + dy * step
            for half, color in ((half_outer, FLAME_OUTER), (half_inner, FLAME_INNER), (half_core, FLAME_CORE)):
                if half <= 0:
                    continue
                if dy:
                    surf.fill(color, (int(px - half), int(py) - (1 if dy < 0 else 0), half * 2, 2))
                else:
                    surf.fill(color, (int(px) - (1 if dx < 0 else 0), int(py - half), 2, half * 2))
