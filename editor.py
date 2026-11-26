"""Level editor: python editor.py [map] edits data/maps/<map>.json.

The window can be resized and maximized. The map is drawn at any zoom (down
to the whole map, scripts/editor_ui.py); the tiles are picked from the
palette on the left; the keys of the current mode are listed on the right
(H hides them); the bottom bar shows the cursor, messages and the zoom (a
click on it goes back to the default zoom). R switches to route mode, where
the route's waypoints are edited and planned (tools/worlds/editor_route.py).
"""

import os
import sys
import time
import warnings

import pygame

from scripts import editor_ui as ui
from scripts.enemy_kinds import BY_VARIANT
from scripts.settings import settings
from scripts.tilemap import Tilemap
from scripts.utils import load_image, load_images
from tools.worlds.editor_route import FAILED, GROUND, GUIDE, STOP
from tools.worlds.editor_route import KEYS as ROUTE_KEYS
from tools.worlds.editor_route import RouteLayer

MAP_NAME = "scratch"  # Default target map: a named scratch map outside the campaign (may not exist; then the
# first numbered map is loaded as a start, and saving still writes the scratch map).
CURRENT_MAP = "data/maps/" + str(MAP_NAME) + ".json"

TS = ui.TS
TOP_H = 52
STATUS_H = 34
LEFT_W = 288
RIGHT_W = 320
MIN_SIZE = (1000, 620)
CELL = 46  # palette cell
CELL_GAP = 6
PAN_SPEED = 900  # screen px per second (keys)
UNDO_LIMIT = 80
MESSAGE_SECONDS = 6.0
ROW_H = 28  # waypoint list row

GROUP_NAMES = {
    "grass": "Grass",
    "stone": "Stone",
    "sand": "Sand",
    "mars": "Mars",
    "reef": "Reef",
    "wreck": "Wreck",
    "spawners": "Spawner",
    "spikes": "Spikes",
    "crumble": "Crumbling block",
    "flamejet": "Flame jet",
    "coin": "Coin",
    "heart": "Heart",
    "checkpoint": "Checkpoint",
    "flag": "Flag",
    "decor": "Decor",
    "large_decor": "Large decor",
    "water": "Water",
}
FACING = ["up", "down", "left", "right"]
VARIANT_NAMES = {
    "spawners": ["Player"] + [BY_VARIANT[v].name.capitalize() for v in sorted(BY_VARIANT)],
    "spikes": [f"facing {f}" for f in FACING],
    "flamejet": [f"facing {f}" for f in FACING],
    "water": ["still", "current →", "current ←", "current ↑", "current ↓"],
}
# The palette, top to bottom: (section title, tile groups)
SECTIONS = [
    ("Player & enemies", ["spawners"]),
    ("Terrain", ["grass", "stone", "sand", "mars", "reef", "wreck"]),
    ("Hazards", ["spikes", "crumble", "flamejet"]),
    ("Pickups & goal", ["coin", "heart", "checkpoint", "flag"]),
    ("Water", ["water"]),
    ("Decor", ["decor"]),
    ("Large decor", ["large_decor"]),
]

TILE_KEYS = [
    ("Click", "pick a tile in the palette"),
    ("Left drag", "paint"),
    ("Right drag", "erase"),
    ("Shift Wheel", "previous / next variant"),
    ("G", "snap to grid on / off"),
    ("M", "square brush on / off"),
    ("[  ]", "brush smaller / larger"),
    ("T", "auto-tile the edges"),
]
VIEW_KEYS = [
    ("Wheel", "zoom at the mouse"),
    ("W A S D", "pan (arrow keys too)"),
    ("Space drag", "pan (middle drag too)"),
    ("0", "whole map"),
    ("1", "default zoom (click the %)"),
    ("+  -", "zoom in / out"),
]
FILE_KEYS = [
    ("R", "tiles / route mode"),
    ("Cmd Z", "undo  (Shift: redo)"),
    ("O", "save  (or Cmd S)"),
    ("Esc", "save and quit"),
    ("H", "hide / show this panel"),
]


def sprite_paths(variant: int) -> str:
    """The idle frame a spawner of `variant` shows: the player, or its enemy kind."""
    if variant == 0:
        return "entities/player/default/idle/00.png"
    kind = BY_VARIANT.get(variant)
    if kind is None or kind.name == "gunner":
        return "entities/enemy/idle/00.png"
    return f"entities/enemy/{kind.name}/idle/00.png"


def spawner_sprite(variant: int, fallback: pygame.Surface) -> tuple:
    """(image, offset from the tile's top left) of a spawner as the game shows
    its character: the sprite at the entity's anim_offset, an armed enemy with
    its gun or star (scripts/entities.py)."""
    try:
        body = load_image(sprite_paths(variant))
    except (FileNotFoundError, pygame.error):
        return fallback, (0, 0)
    parts = [(body, (-3, -3 - (body.get_height() - 18)))]
    kind = BY_VARIANT.get(variant) if variant else None
    if kind is not None and kind.armed:
        try:
            if kind.projectile == "star":
                star = load_image("star.png")
                parts.append((star, (4 + 6 - star.get_width() // 2, -2)))
            else:
                parts.append((load_image("gun.png"), (8, 7)))
        except (FileNotFoundError, pygame.error):
            pass
    rect = pygame.Rect(parts[0][1], parts[0][0].get_size())
    for img, off in parts[1:]:
        rect.union_ip(pygame.Rect(off, img.get_size()))
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    for img, off in parts:
        surf.blit(img, (off[0] - rect.x, off[1] - rect.y))
    return surf, rect.topleft


def line_tiles(a: tuple, b: tuple) -> list:
    """Tiles on the line from a to b (both in), so a fast stroke leaves no gaps."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err, out = dx + dy, []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class Editor:
    def __init__(self, map_name: str = MAP_NAME):
        """`map_name`: the map edited and saved, data/maps/<map_name>.json (python editor.py 3)."""
        self.map_name = str(map_name)
        self.map_path = "data/maps/" + self.map_name + ".json"
        pygame.init()
        self.screen = pygame.display.set_mode(self._start_size(), pygame.RESIZABLE)
        try:
            with warnings.catch_warnings():  # from_display_module is deprecated, but the only handle on this window
                warnings.simplefilter("ignore", DeprecationWarning)
                pygame.Window.from_display_module().minimum_size = MIN_SIZE
        except (AttributeError, pygame.error):
            pass
        pygame.display.set_caption(f"Ninja Editor  ·  {os.path.basename(self.map_path)}")
        pygame.key.set_repeat(300, 40)
        self.clock = pygame.time.Clock()
        self.fonts = ui.Fonts()

        self.assets = {
            "grass": load_images("tiles/grass"),
            "stone": load_images("tiles/stone"),
            "sand": load_images("tiles/sand"),
            "mars": load_images("tiles/mars"),
            "spawners": load_images("tiles/spawners"),
            "large_decor": load_images("tiles/large_decor"),
            "decor": load_images("tiles/decor"),
            "coin": load_images("tiles/collectables/coin"),
            "heart": load_images("tiles/collectables/heart"),
            "flag": load_images("tiles/collectables/flag"),
            "reef": load_images("tiles/reef"),
            "wreck": load_images("tiles/wreck"),
            # Hazards (scripts/hazards.py); variant = facing for spikes and flame jets
            "spikes": load_images("tiles/spikes"),
            "crumble": load_images("tiles/crumble")[:1],
            "flamejet": load_images("tiles/flamejet"),
            # Water layer brush: the variant is the flow (0 still, 1-4 a current)
            "water": load_images("tiles/water"),
            # Checkpoint banner, drawn from its tile down: place it one tile over
            # the air tile above the ground (or offgrid, its foot on the ground)
            "checkpoint": load_images("tiles/collectables/checkpoint")[:1],
        }
        self.water_icons = []
        for img in self.assets["water"]:
            icon = img.copy()
            icon.set_alpha(150)
            self.water_icons.append(icon)
        # Spawners show the character they spawn, as in the game
        self.sprites = [spawner_sprite(v, img) for v, img in enumerate(self.assets["spawners"])]

        self.tilemap = Tilemap(self, tile_size=TS)
        self._load_map()
        self.view = ui.WorldView(self.tilemap, self.assets, self.water_icons)

        self.tile_list = list(self.assets)
        self.tile_group = "grass"
        self.tile_variant = 0
        self.ongrid = True
        self.multi_tile = False
        self.multi_tile_size = 3

        # View: world px at the viewport's top left, screen px per world px
        self.zoom = ui.DEFAULT_ZOOM
        self._zoom_f = self.zoom
        self.cam = [0.0, 0.0]
        self.keys_held: set = set()
        self.panning_from = None  # (mouse, cam) while the view is dragged
        self.space = False

        # Painting: a stroke runs from mouse down to mouse up
        self.clicking = False
        self.right_clicking = False
        self.stroke_tile = None
        self.stroke_before = None  # the state before the stroke (undo), until it changes something
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.unsaved = False
        self.version = 0  # counts edits: caches below follow it
        self._spawner_cache = (-1, [])

        self.show_help = True
        self.palette_scroll = 0
        self.route_scroll = 0
        self.buttons: list = []  # (rect, action, tooltip) of the last frame
        self.message = ("", ui.DIM, 0.0)
        self.icon_cache: dict = {}
        self.sprite_cache: dict = {}
        self.mouse = (0, 0)

        settings.load_settings()
        if self.map_name.isdigit():
            settings.set_editor_level(int(self.map_name))
        settings.save_settings()

        # Route mode (R): the waypoints of map_data.route, edited and planned in place
        self.route_layer = RouteLayer(self.tilemap, self.map_name, self.save)
        self.center_on_map()

    # --- setup ---------------------------------------------------------------------
    @staticmethod
    def _start_size() -> tuple:
        """Most of the screen, leaving room for the menu bar, the dock and the title bar."""
        try:
            w, h = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            w, h = 1600, 1000
        return max(MIN_SIZE[0], min(1760, w - 80)), max(MIN_SIZE[1], min(1040, h - 170))

    def _load_map(self) -> None:
        if os.path.exists(self.map_path):
            self.tilemap.load(self.map_path, load_entities=False)
            return
        # The requested map does not exist yet: start from the first numbered map
        try:
            candidates = [f for f in os.listdir("data/maps") if f.endswith(".json")]
        except FileNotFoundError:
            candidates = []
        numeric = sorted(int(f.split(".")[0]) for f in candidates if f.split(".")[0].isdigit())
        if numeric:
            self.tilemap.load(f"data/maps/{numeric[0]}.json", load_entities=False)
            settings.set_editor_level(numeric[0])

    # --- layout --------------------------------------------------------------------
    def layout(self) -> dict:
        w, h = self.screen.get_size()
        right = RIGHT_W if self.show_help else 0
        return {
            "top": pygame.Rect(0, 0, w, TOP_H),
            "left": pygame.Rect(0, TOP_H, LEFT_W, h - TOP_H - STATUS_H),
            "right": pygame.Rect(w - right, TOP_H, right, h - TOP_H - STATUS_H),
            "view": pygame.Rect(LEFT_W, TOP_H, max(1, w - LEFT_W - right), max(1, h - TOP_H - STATUS_H)),
            "status": pygame.Rect(0, h - STATUS_H, w, STATUS_H),
        }

    # --- view ----------------------------------------------------------------------
    def world_at(self, pos) -> tuple:
        v = self.layout()["view"]
        return (pos[0] - v.x) / self.zoom + self.cam[0], (pos[1] - v.y) / self.zoom + self.cam[1]

    def tile_at(self, pos) -> tuple:
        x, y = self.world_at(pos)
        return int(x // TS), int(y // TS)

    def to_screen(self, wx: float, wy: float) -> tuple:
        """Screen px of world px (wx, wy) inside the viewport surface."""
        return round(wx * self.zoom) - round(self.cam[0] * self.zoom), round(wy * self.zoom) - round(
            self.cam[1] * self.zoom
        )

    def set_zoom(self, z: float, anchor=None) -> None:
        """Zoom to `z`, keeping the world point under `anchor` (screen px; default the view's middle) in place."""
        v = self.layout()["view"]
        anchor = anchor or v.center
        wx, wy = self.world_at(anchor)
        self._zoom_f = max(ui.MIN_ZOOM, min(ui.MAX_ZOOM, z))
        self.zoom = ui.clamp_zoom(self._zoom_f)
        self.cam = [wx - (anchor[0] - v.x) / self.zoom, wy - (anchor[1] - v.y) / self.zoom]

    def center_on(self, wx: float, wy: float) -> None:
        v = self.layout()["view"]
        self.cam = [wx - v.w / 2 / self.zoom, wy - v.h / 2 / self.zoom]

    def center_on_map(self) -> None:
        """Default zoom, on the player's spawner (else the map's middle)."""
        spawn = next((pos for pos, var in self.spawners() if var == 0), None)
        if spawn is not None:
            self.center_on(spawn[0] + 8, spawn[1] + 8)
        else:
            b = ui.map_bounds(self.tilemap)
            self.center_on(*(b.center if b else (0, 0)))

    def reset_zoom(self) -> None:
        self.set_zoom(ui.DEFAULT_ZOOM)
        self.flash(f"Zoom {ui.zoom_label(self.zoom)} (default)")

    def fit_map(self) -> None:
        """Zoom out (or in) until the whole map fills the view."""
        b = ui.map_bounds(self.tilemap)
        if b is None:
            return
        v = self.layout()["view"]
        z = min((v.w - 40) / max(b.w, 1), (v.h - 40) / max(b.h, 1))
        self._zoom_f = max(ui.MIN_ZOOM, min(ui.MAX_ZOOM, z))
        self.zoom = max(ui.MIN_ZOOM, int(self._zoom_f / ui.ZOOM_STEP) * ui.ZOOM_STEP)
        self.center_on(*b.center)
        self.flash(f"Whole map: {b.w // TS} x {b.h // TS} tiles at {ui.zoom_label(self.zoom)}")

    # --- edits and undo ----------------------------------------------------------------
    def snapshot(self, route_only: bool = False) -> dict:
        snap = {"route": [dict(r) for r in self.tilemap.route]}
        if not route_only:
            snap["tilemap"] = {k: dict(v) for k, v in self.tilemap.tilemap.items()}
            snap["offgrid"] = [dict(t) for t in self.tilemap.offgrid_tiles]
            snap["water"] = dict(self.tilemap.water)
        return snap

    def restore(self, snap: dict) -> None:
        if "tilemap" in snap:
            self.tilemap.tilemap = {k: dict(v) for k, v in snap["tilemap"].items()}
            self.tilemap.offgrid_tiles = [dict(t) for t in snap["offgrid"]]
            self.tilemap.water = dict(snap["water"])
            self.tilemap._water_renderer = None
            self.view.invalidate_all()
        layer = self.route_layer
        self.tilemap.route = [dict(r) for r in snap["route"]]
        layer.trail = layer.failed_at = None
        if layer.selected is not None and layer.selected >= len(self.tilemap.route):
            layer.selected = None
        self.changed()

    def push_undo(self, snap: dict) -> None:
        self.undo_stack.append(snap)
        del self.undo_stack[:-UNDO_LIMIT]
        self.redo_stack.clear()

    def undo(self, redo: bool = False) -> None:
        src, dst = (self.redo_stack, self.undo_stack) if redo else (self.undo_stack, self.redo_stack)
        if not src:
            self.flash("Nothing to redo" if redo else "Nothing to undo", ui.DIM)
            return
        snap = src.pop()
        dst.append(self.snapshot(route_only="tilemap" not in snap))
        self.restore(snap)
        self.flash("Redone" if redo else "Undone")

    def changed(self) -> None:
        self.unsaved = True
        self.version += 1

    def _stroke_edit(self) -> None:
        """The stroke changes the map: its undo step is the state before it."""
        if self.stroke_before is not None:
            self.push_undo(self.stroke_before)
            self.stroke_before = None
        self.changed()

    def set_tile(self, pos: tuple) -> None:
        group, variant = self.tile_group, self.tile_variant
        if group == "water":
            if self.tilemap.water.get(pos) != variant:
                self._stroke_edit()
                self.tilemap.water[pos] = variant
                self.tilemap._water_renderer = None
                self.view.invalidate_tiles([pos])
            return
        key = f"{pos[0]};{pos[1]}"
        old = self.tilemap.tilemap.get(key)
        if old is not None and old["type"] == group and old["variant"] == variant:
            return
        self._stroke_edit()
        self.tilemap.tilemap[key] = {"type": group, "variant": variant, "pos": [pos[0], pos[1]]}
        self.view.invalidate_tiles([pos])

    def erase_tile(self, pos: tuple, world: tuple | None = None) -> None:
        if self.tile_group == "water":
            if pos in self.tilemap.water:
                self._stroke_edit()
                del self.tilemap.water[pos]
                self.tilemap._water_renderer = None
                self.view.invalidate_tiles([pos])
            return
        key = f"{pos[0]};{pos[1]}"
        if key in self.tilemap.tilemap:
            self._stroke_edit()
            del self.tilemap.tilemap[key]
            self.view.invalidate_tiles([pos])
        if world is not None:
            for tile in self.tilemap.offgrid_tiles[::-1]:
                r = self.offgrid_rect(tile)
                if r is not None and r.collidepoint(world):
                    self._stroke_edit()
                    self.tilemap.offgrid_tiles.remove(tile)
                    self.view.invalidate_px_rect(r)

    def offgrid_rect(self, tile: dict) -> pygame.Rect | None:
        if tile["type"] == "spawners":
            img, off = self.sprites[tile["variant"]] if tile["variant"] < len(self.sprites) else (None, None)
            if img is None:
                return None
            return pygame.Rect(int(tile["pos"][0]) + off[0], int(tile["pos"][1]) + off[1], *img.get_size())
        return self.view.offgrid_rect(tile)

    def place_offgrid(self, world: tuple) -> None:
        if self.tile_group == "water":
            return
        tile = {"type": self.tile_group, "variant": self.tile_variant, "pos": [world[0], world[1]]}
        self._stroke_edit()
        self.tilemap.offgrid_tiles.append(tile)
        r = self.offgrid_rect(tile)
        if r is not None:
            self.view.invalidate_px_rect(r)

    def brush_tiles(self, tile_pos) -> list:
        """Tiles under the brush: the one under the mouse, or the square around it."""
        if not self.multi_tile:
            return [tuple(tile_pos)]
        r = range(-(self.multi_tile_size // 2), self.multi_tile_size - self.multi_tile_size // 2)
        return [(tile_pos[0] + x, tile_pos[1] + y) for x in r for y in r]

    def autotile(self) -> None:
        before = self.snapshot()
        self.tilemap.autotile()
        if before["tilemap"] != self.tilemap.tilemap:
            self.push_undo(before)
            self.changed()
            self.view.invalidate_all()
            self.flash("Edges auto-tiled")
        else:
            self.flash("Auto-tile: nothing to change", ui.DIM)

    def save(self) -> bool:
        ok = self.tilemap.save(self.map_path)
        if ok:
            self.unsaved = False
            self.flash(f"Saved {self.map_path}  ·  {time.strftime('%H:%M:%S')}", ui.OK)
        else:
            self.flash(f"Could not save {self.map_path}", ui.ERR)
        return ok

    def flash(self, text: str, color=ui.TEXT) -> None:
        self.message = (text, color, time.monotonic())

    def spawners(self) -> list:
        """((x, y) world px, variant) of every spawner, grid and offgrid."""
        if self._spawner_cache[0] != self.version:
            out = [
                ((t["pos"][0] * TS, t["pos"][1] * TS), t["variant"])
                for t in self.tilemap.tilemap.values()
                if t["type"] == "spawners"
            ]
            out += [
                ((int(t["pos"][0]), int(t["pos"][1])), t["variant"])
                for t in self.tilemap.offgrid_tiles
                if t["type"] == "spawners"
            ]
            self._spawner_cache = (self.version, out)
        return self._spawner_cache[1]

    def select(self, group: str, variant: int) -> None:
        self.tile_group, self.tile_variant = group, variant

    # --- events ----------------------------------------------------------------------
    def handle_event(self, event) -> bool:
        """Act on one event; False when the editor should close."""
        lay = self.layout()
        if event.type == pygame.QUIT:
            return False
        if event.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
            self.screen = pygame.display.get_surface()
            return True
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
            if self.panning_from is not None:
                (mx, my), (cx, cy) = self.panning_from
                self.cam = [cx - (event.pos[0] - mx) / self.zoom, cy - (event.pos[1] - my) / self.zoom]
            return True
        if event.type == pygame.MOUSEWHEEL:
            return self._wheel(event, lay)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            return True  # the wheel comes as MOUSEWHEEL too
        if event.type == pygame.MOUSEBUTTONUP and event.button in (4, 5):
            return True

        route = self.route_layer
        in_view = lay["view"].collidepoint(self.mouse)
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse = event.pos
            in_view = lay["view"].collidepoint(event.pos)
            if event.button == 2 or (event.button == 1 and self.space and in_view):
                self.panning_from = (event.pos, tuple(self.cam))
                return True
            if event.button == 1 and not in_view:
                for rect, action, _tip in reversed(self.buttons):
                    if rect.collidepoint(event.pos):
                        action()
                        break
                return True
            if not in_view:
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2) and self.panning_from is not None:
            self.panning_from = None
            return True

        # Route mode: the route layer has the mouse in the view and its own keys
        if route.active and (
            event.type == pygame.KEYDOWN
            or (
                event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
                and event.button in (1, 3)
                and (in_view or event.type == pygame.MOUSEBUTTONUP)
            )
        ):
            if not (event.type == pygame.KEYDOWN and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)):
                before = self.tilemap.route
                snap = None
                if event.type != pygame.MOUSEBUTTONUP or route.drag_start is not None:
                    snap = {"route": [dict(r) for r in before]}
                if route.handle_event(event, self.tile_at(self.mouse)):
                    if self.tilemap.route is not before and snap is not None:
                        self.push_undo(snap)
                        self.changed()
                    return True

        if event.type == pygame.MOUSEBUTTONDOWN and not route.active:
            tile = self.tile_at(event.pos)
            if event.button == 1:
                self.clicking = True
                self.stroke_before = self.snapshot()
                self.stroke_tile = tile
                if self.ongrid:
                    for t in self.brush_tiles(tile):
                        self.set_tile(t)
                else:
                    self.place_offgrid(self.world_at(event.pos))
            elif event.button == 3:
                self.right_clicking = True
                self.stroke_before = self.snapshot()
                self.stroke_tile = tile
                for t in self.brush_tiles(tile):
                    self.erase_tile(t, self.world_at(event.pos))
            return True
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.clicking = False
            if event.button == 3:
                self.right_clicking = False
            if not (self.clicking or self.right_clicking):
                self.stroke_before = None
                self.stroke_tile = None
            return True

        if event.type == pygame.KEYDOWN:
            return self._key(event)
        if event.type == pygame.KEYUP:
            self.keys_held.discard(event.key)
            if event.key == pygame.K_SPACE:
                self.space = False
        return True

    def _wheel(self, event, lay) -> bool:
        y = getattr(event, "precise_y", event.y)
        x = getattr(event, "precise_x", event.x)
        if lay["left"].collidepoint(self.mouse):
            if self.route_layer.active:
                self.route_scroll -= int(y * 40)
            else:
                self.palette_scroll -= int(y * 40)
            return True
        if not lay["view"].collidepoint(self.mouse):
            return True
        if pygame.key.get_mods() & pygame.KMOD_SHIFT and not self.route_layer.active:
            n = len(self.assets[self.tile_group])
            step = -1 if y > 0 else 1
            self.tile_variant = (self.tile_variant + step) % n
            return True
        if y:
            self.set_zoom(self._zoom_f * (1.18**y), self.mouse)
        if x:
            self.cam[0] += x * 40 / self.zoom
        return True

    def _key(self, event) -> bool:
        k, mod = event.key, event.mod
        cmd = mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
        shift = mod & pygame.KMOD_SHIFT
        if cmd:
            if k == pygame.K_z:
                self.undo(redo=bool(shift))
            elif k == pygame.K_y:
                self.undo(redo=True)
            elif k == pygame.K_s:
                self.save()
            return True
        if k in (
            pygame.K_a,
            pygame.K_d,
            pygame.K_w,
            pygame.K_s,
            pygame.K_LEFT,
            pygame.K_RIGHT,
            pygame.K_UP,
            pygame.K_DOWN,
        ):
            self.keys_held.add(k)
        elif k == pygame.K_SPACE:
            self.space = True
        elif k == pygame.K_ESCAPE:
            self.save()
            return False
        elif k == pygame.K_o:
            self.save()
        elif k == pygame.K_r:
            self.toggle_route_mode()
        elif k == pygame.K_h:
            self.show_help = not self.show_help
        elif k in (pygame.K_0, pygame.K_KP0):
            self.fit_map()
        elif k in (pygame.K_1, pygame.K_KP1):
            self.reset_zoom()
        elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.set_zoom(self._zoom_f * 1.5)
        elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.set_zoom(self._zoom_f / 1.5)
        elif self.route_layer.active:
            return True
        elif k == pygame.K_g:
            self.ongrid = not self.ongrid
            self.flash("Snap to grid on" if self.ongrid else "Snap to grid off: free placement")
        elif k == pygame.K_m:
            self.multi_tile = not self.multi_tile
        elif k == pygame.K_LEFTBRACKET:
            self.resize_brush(-1)
        elif k == pygame.K_RIGHTBRACKET:
            self.resize_brush(1)
        elif k == pygame.K_t:
            self.autotile()
        return True

    def resize_brush(self, delta: int) -> None:
        self.multi_tile = True
        self.multi_tile_size = max(1, min(25, self.multi_tile_size + delta))

    def toggle_route_mode(self) -> None:
        self.route_layer.toggle_active()
        self.clicking = self.right_clicking = False
        self.stroke_before = None
        self.flash("Route mode" if self.route_layer.active else "Tiles mode")

    # --- per frame -------------------------------------------------------------------
    def update(self, dt: float) -> None:
        held = self.keys_held
        dx = (pygame.K_d in held or pygame.K_RIGHT in held) - (pygame.K_a in held or pygame.K_LEFT in held)
        dy = (pygame.K_s in held or pygame.K_DOWN in held) - (pygame.K_w in held or pygame.K_UP in held)
        if dx or dy:
            self.cam[0] += dx * PAN_SPEED * dt / self.zoom
            self.cam[1] += dy * PAN_SPEED * dt / self.zoom
        # keys held while the window lost focus never send KEYUP
        if held and not pygame.key.get_focused():
            held.clear()

        view = self.layout()["view"]
        if self.route_layer.active or not view.collidepoint(self.mouse) or self.panning_from is not None:
            return
        tile = self.tile_at(self.mouse)
        if (self.clicking and self.ongrid) or self.right_clicking:
            path = line_tiles(self.stroke_tile, tile) if self.stroke_tile else [tile]
            for t in path:
                for b in self.brush_tiles(t):
                    if self.clicking:
                        self.set_tile(b)
                    else:
                        self.erase_tile(b, self.world_at(self.mouse))
            self.stroke_tile = tile

    # --- drawing ---------------------------------------------------------------------
    def icon(self, group: str, variant: int, box: int) -> pygame.Surface:
        """A tile's image to fit a `box` px square: whole-pixel steps when enlarged."""
        key = (group, variant, box)
        if key not in self.icon_cache:
            img = self.sprites[variant][0] if group == "spawners" else self.assets[group][variant]
            w, h = img.get_size()
            f = min(box / w, box / h)
            f = int(f) if f >= 1 else f
            self.icon_cache[key] = ui.scale_image(img, (round(w * f), round(h * f)))
        return self.icon_cache[key]

    def scaled_sprite(self, variant: int) -> tuple:
        key = (variant, self.zoom)
        if key not in self.sprite_cache:
            if len(self.sprite_cache) > 64:
                self.sprite_cache.clear()
            img, off = self.sprites[variant]
            w, h = img.get_size()
            self.sprite_cache[key] = (ui.scale_image(img, (round(w * self.zoom), round(h * self.zoom))), off)
        return self.sprite_cache[key]

    def button(self, surf, rect, label, action, *, active=False, tip="", font=None, enabled=True) -> None:
        hover = rect.collidepoint(self.mouse) and enabled
        fill = ui.ACCENT_DIM if active else ui.PANEL_3 if hover else ui.PANEL_2
        pygame.draw.rect(surf, fill, rect, border_radius=6)
        pygame.draw.rect(surf, ui.ACCENT if active else ui.BORDER, rect, 1, border_radius=6)
        color = ui.TEXT if enabled else ui.FAINT
        ui.draw_text(surf, self.fonts, label, rect.center, font or self.fonts.small, color, "center")
        if enabled:
            self.buttons.append((rect, action, tip))

    def draw(self) -> None:
        self.buttons = []
        lay = self.layout()
        self.screen.fill(ui.BG)
        self.draw_view(lay["view"])
        self.draw_top(lay["top"])
        self.draw_left(lay["left"])
        if self.show_help:
            self.draw_help(lay["right"])
        self.draw_status(lay["status"])
        self.draw_tooltip()

    def draw_view(self, rect: pygame.Rect) -> None:
        surf = self.screen.subsurface(rect)
        surf.fill(ui.CANVAS)
        z = self.zoom
        self.view.render(surf, self.cam, z)
        for (x, y), variant in self.spawners():
            if variant < len(self.sprites):
                img, off = self.scaled_sprite(variant)
                sx, sy = self.to_screen(x + off[0], y + off[1])
                if -img.get_width() < sx < rect.w and -img.get_height() < sy < rect.h:
                    surf.blit(img, (sx, sy))
        tpx = TS * z
        if tpx >= 12:  # the tile grid, where tiles are big enough for it to help
            grid = pygame.Surface(rect.size, pygame.SRCALPHA)
            ox, oy = self.to_screen(0, 0)
            x0, y0 = ox % tpx, oy % tpx
            for i in range(int(rect.w / tpx) + 2):
                pygame.draw.line(grid, ui.GRID, (x0 + i * tpx, 0), (x0 + i * tpx, rect.h))
            for i in range(int(rect.h / tpx) + 2):
                pygame.draw.line(grid, ui.GRID, (0, y0 + i * tpx), (rect.w, y0 + i * tpx))
            surf.blit(grid, (0, 0))

        tile = self.tile_at(self.mouse)
        if self.route_layer.active:
            self.route_layer.render(surf, self.cam, self.fonts.small, tile, TS, zoom=z, hud=False)
        elif rect.collidepoint(self.mouse) and self.panning_from is None and not self.space:
            self.draw_brush(surf, tile)
        pygame.draw.rect(self.screen, ui.BORDER, rect, 1)

    def draw_brush(self, surf, tile: tuple) -> None:
        z = self.zoom
        group, variant = self.tile_group, self.tile_variant
        if group == "spawners":
            img, off = self.scaled_sprite(variant)
        else:
            src = self.assets[group][variant]
            img, off = ui.scale_image(src, (round(src.get_width() * z), round(src.get_height() * z))), (0, 0)
        img = img.copy()
        img.set_alpha(170)
        if self.ongrid:
            tiles = self.brush_tiles(tile)
            for tx, ty in tiles:
                surf.blit(img, self.to_screen(tx * TS + off[0], ty * TS + off[1]))
            xs = [t[0] for t in tiles]
            ys = [t[1] for t in tiles]
            x, y = self.to_screen(min(xs) * TS, min(ys) * TS)
            r = pygame.Rect(x, y, round((max(xs) - min(xs) + 1) * TS * z), round((max(ys) - min(ys) + 1) * TS * z))
            pygame.draw.rect(surf, (0, 0, 0), r.inflate(2, 2), 1)
            pygame.draw.rect(surf, ui.CURSOR, r, 1)
        else:
            wx, wy = self.world_at(self.mouse)
            surf.blit(img, self.to_screen(wx + off[0], wy + off[1]))

    def draw_top(self, rect: pygame.Rect) -> None:
        s, f = self.screen, self.fonts
        pygame.draw.rect(s, ui.PANEL, rect)
        pygame.draw.line(s, ui.BORDER, rect.bottomleft, (rect.right, rect.bottom - 1))
        x = 16
        r = ui.draw_text(s, f, "Ninja Editor", (x, rect.centery), f.title, ui.TEXT, "midleft")
        x = r.right + 14
        r = ui.draw_text(s, f, os.path.basename(self.map_path), (x, rect.centery), f.ui, ui.DIM, "midleft")
        x = r.right + 12
        if self.unsaved:
            pygame.draw.circle(s, ui.WARN, (x + 5, rect.centery), 5)
            ui.draw_text(s, f, "Unsaved changes", (x + 16, rect.centery), f.small, ui.WARN, "midleft")
        else:
            ui.draw_text(s, f, "✓ Saved", (x, rect.centery), f.small, ui.OK, "midleft")

        # mode tabs
        tabs_w = 220
        tx = max(LEFT_W + 8, rect.centerx - tabs_w // 2)
        if tx < x + 150:
            tx = x + 150
        tab = pygame.Rect(tx, rect.y + 9, tabs_w, rect.h - 18)
        pygame.draw.rect(s, ui.PANEL_2, tab, border_radius=8)
        route = self.route_layer.active
        for i, (name, on) in enumerate((("Tiles", not route), ("Route", route))):
            r = pygame.Rect(tab.x + 3 + i * (tabs_w // 2 - 2), tab.y + 3, tabs_w // 2 - 4, tab.h - 6)
            if on:
                pygame.draw.rect(s, ui.ACCENT, r, border_radius=6)
            elif r.collidepoint(self.mouse):
                pygame.draw.rect(s, ui.PANEL_3, r, border_radius=6)
            ui.draw_text(s, f, name, r.center, f.bold, ui.TEXT if on else ui.DIM, "center")
            if not on:
                self.buttons.append((r, self.toggle_route_mode, "Switch mode (R)"))

        # actions, right to left
        bx = rect.right - 12
        for label, action, tip, enabled in (
            ("Keys", lambda: setattr(self, "show_help", not self.show_help), "Show / hide the key panel (H)", True),
            ("Save", self.save, "Save the map (O, Cmd S)", True),
            ("Auto-tile", self.autotile, "Fit the terrain edges (T)", not route),
            ("Redo", lambda: self.undo(redo=True), "Redo (Cmd Shift Z)", bool(self.redo_stack)),
            ("Undo", self.undo, "Undo (Cmd Z)", bool(self.undo_stack)),
        ):
            w = f.small.size(label)[0] + 26
            r = pygame.Rect(bx - w, rect.y + 11, w, rect.h - 22)
            if r.left < tab.right + 12:
                break
            active = label == "Keys" and self.show_help
            self.button(s, r, label, action, active=active, tip=tip, enabled=enabled)
            bx = r.left - 8

    def draw_left(self, rect: pygame.Rect) -> None:
        s = self.screen
        pygame.draw.rect(s, ui.PANEL, rect)
        pygame.draw.line(s, ui.BORDER, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom))
        if self.route_layer.active:
            self.draw_route_panel(rect)
        else:
            self.draw_palette(rect)

    def draw_palette(self, rect: pygame.Rect) -> None:
        s, f = self.screen, self.fonts
        pad = 14
        # the current brush
        y = rect.y + 12
        card = pygame.Rect(rect.x + pad, y, rect.w - 2 * pad, 64)
        pygame.draw.rect(s, ui.PANEL_2, card, border_radius=8)
        box = pygame.Rect(card.x + 8, card.y + 8, 48, 48)
        pygame.draw.rect(s, ui.CANVAS, box, border_radius=6)
        icon = self.icon(self.tile_group, self.tile_variant, 40)
        s.blit(icon, icon.get_rect(center=box.center))
        name = GROUP_NAMES.get(self.tile_group, self.tile_group)
        vname = self.variant_name(self.tile_group, self.tile_variant)
        ui.draw_text(s, f, name, (box.right + 12, card.y + 14), f.bold)
        ui.draw_text(s, f, vname, (box.right + 12, card.y + 36), f.small, ui.DIM)
        y = card.bottom + 10
        # brush options
        half = (card.w - 8) // 2
        self.button(
            s,
            pygame.Rect(card.x, y, half, 30),
            "Snap to grid  G",
            lambda: setattr(self, "ongrid", not self.ongrid),
            active=self.ongrid,
            tip="Off: place freely (decor, offgrid)",
        )
        self.button(
            s,
            pygame.Rect(card.x + half + 8, y, half, 30),
            "Square brush  M",
            lambda: setattr(self, "multi_tile", not self.multi_tile),
            active=self.multi_tile,
            tip="Paint a square of tiles",
        )
        y += 38
        ui.draw_text(s, f, "Brush size", (card.x, y + 15), f.small, ui.DIM, "midleft")
        n = self.multi_tile_size
        self.button(s, pygame.Rect(card.right - 104, y, 30, 30), "−", lambda: self.resize_brush(-1), tip="[")
        ui.draw_text(
            s, f, f"{n} × {n}", (card.right - 52, y + 15), f.bold, ui.TEXT if self.multi_tile else ui.FAINT, "center"
        )
        self.button(s, pygame.Rect(card.right - 30, y, 30, 30), "+", lambda: self.resize_brush(1), tip="]")
        y += 42
        pygame.draw.line(s, ui.BORDER, (rect.x, y), (rect.right - 1, y))

        # the palette, scrolled
        area = pygame.Rect(rect.x, y + 1, rect.w - 1, rect.bottom - y - 1)
        cols = max(1, (area.w - 2 * pad + CELL_GAP) // (CELL + CELL_GAP))
        content = 0
        for _title, groups in SECTIONS:
            n = sum(len(self.assets[g]) for g in groups)
            content += 34 + ((n + cols - 1) // cols) * (CELL + CELL_GAP)
        self.palette_scroll = max(0, min(self.palette_scroll, content + 12 - area.h))
        s.set_clip(area)
        cy = area.y + 8 - self.palette_scroll
        for title, groups in SECTIONS:
            ui.draw_text(s, f, title.upper(), (area.x + pad, cy + 12), f.small, ui.FAINT)
            cy += 34
            cells = [(g, v) for g in groups for v in range(len(self.assets[g]))]
            for i, (g, v) in enumerate(cells):
                c = pygame.Rect(
                    area.x + pad + (i % cols) * (CELL + CELL_GAP), cy + (i // cols) * (CELL + CELL_GAP), CELL, CELL
                )
                if c.bottom < area.top or c.top > area.bottom:
                    continue
                sel = (g, v) == (self.tile_group, self.tile_variant)
                hover = c.collidepoint(self.mouse) and area.collidepoint(self.mouse)
                pygame.draw.rect(s, ui.ACCENT_DIM if sel else ui.PANEL_3 if hover else ui.PANEL_2, c, border_radius=7)
                if sel or hover:
                    pygame.draw.rect(s, ui.ACCENT if sel else ui.BORDER, c, 2 if sel else 1, border_radius=7)
                ic = self.icon(g, v, CELL - 8)
                s.blit(ic, ic.get_rect(center=c.center))
                vis = c.clip(area)
                if vis.w and vis.h:
                    tip = f"{GROUP_NAMES.get(g, g)} · {self.variant_name(g, v)}"
                    self.buttons.append((vis, lambda g=g, v=v: self.select(g, v), tip))
            cy += ((len(cells) + cols - 1) // cols) * (CELL + CELL_GAP)
        s.set_clip(None)
        self._scrollbar(area, content + 12, self.palette_scroll)

    def _scrollbar(self, area: pygame.Rect, content: int, scroll: int) -> None:
        if content <= area.h:
            return
        h = max(30, area.h * area.h // content)
        y = area.y + (area.h - h) * scroll // max(1, content - area.h)
        pygame.draw.rect(self.screen, ui.PANEL_3, (area.right - 6, y, 4, h), border_radius=2)

    def variant_name(self, group: str, variant: int) -> str:
        names = VARIANT_NAMES.get(group)
        if names and variant < len(names):
            return names[variant]
        return f"variant {variant}" if len(self.assets[group]) > 1 else ""

    def draw_route_panel(self, rect: pygame.Rect) -> None:
        s, f = self.screen, self.fonts
        layer = self.route_layer
        route = layer.route
        pad = 14
        y = rect.y + 14
        ui.draw_text(s, f, "Route", (rect.x + pad, y), f.title)
        ui.draw_text(s, f, f"{len(route)} waypoints", (rect.right - pad, y + 3), f.small, ui.DIM, "topright")
        y += 34
        w = (rect.w - 2 * pad - 16) // 3

        def shift() -> bool:
            return bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)

        def act(fn):
            def run():
                snap = {"route": [dict(r) for r in self.tilemap.route]}
                before = self.tilemap.route
                fn()
                if self.tilemap.route is not before:
                    self.push_undo(snap)
                    self.changed()

            return run

        for i, (label, fn, tip) in enumerate(
            (
                ("Draft  N", lambda: layer.draft(shift()), "Spawn, checkpoints, flag (Shift: replace)"),
                ("Replay  L", lambda: layer.from_replay(shift()), "From the best run (Shift: replace)"),
                ("Plan  P", layer.plan, "Save and plan the route"),
            )
        ):
            self.button(
                s,
                pygame.Rect(rect.x + pad + i * (w + 8), y, w, 32),
                label,
                act(fn),
                tip=tip,
                enabled=not (label.startswith("Plan") and layer.planning),
            )
        y += 44
        # legend
        lx = rect.x + pad
        for name, color in (("ground", GROUND), ("stop", STOP), ("guide", GUIDE), ("failed", FAILED)):
            pygame.draw.rect(s, color, (lx, y + 4, 10, 10), border_radius=2)
            r = ui.draw_text(s, f, name, (lx + 15, y), f.small, ui.DIM)
            lx = r.right + 12
        y += 26
        pygame.draw.line(s, ui.BORDER, (rect.x, y), (rect.right - 1, y))
        area = pygame.Rect(rect.x, y + 1, rect.w - 1, rect.bottom - y - 1)
        content = len(route) * ROW_H + 8
        if layer.selected is not None and getattr(self, "_route_follow", None) != layer.selected:
            # keep the selected row in sight when it changes by key
            top = layer.selected * ROW_H
            if top < self.route_scroll:
                self.route_scroll = top
            elif top + ROW_H > self.route_scroll + area.h - 8:
                self.route_scroll = top + ROW_H - area.h + 8
            self._route_follow = layer.selected
        self.route_scroll = max(0, min(self.route_scroll, content - area.h))
        s.set_clip(area)
        if not route:
            ui.draw_text(s, f, "No route yet.", (area.x + pad, area.y + 14), f.ui, ui.DIM)
            ui.draw_text(s, f, "Drag over the map or press N.", (area.x + pad, area.y + 38), f.small, ui.FAINT)
        for i, wp in enumerate(route):
            r = pygame.Rect(area.x + 6, area.y + 4 + i * ROW_H - self.route_scroll, area.w - 14, ROW_H - 2)
            if r.bottom < area.top or r.top > area.bottom:
                continue
            sel = i == layer.selected
            hover = r.collidepoint(self.mouse) and area.collidepoint(self.mouse)
            if sel or hover:
                pygame.draw.rect(s, ui.ACCENT_DIM if sel else ui.PANEL_2, r, border_radius=5)
            color = FAILED if i == layer.failed_at else GUIDE if wp.guide else GROUND if wp.ground else STOP
            chip = pygame.Rect(r.x + 6, r.y + 4, 32, r.h - 8)
            pygame.draw.rect(s, color, chip, border_radius=4)
            ui.draw_text(s, f, str(i), chip.center, f.small, (255, 255, 255), "center")
            where = f"{wp.x0},{wp.y0}" if (wp.x0, wp.y0) == (wp.x1, wp.y1) else f"{wp.x0},{wp.y0} – {wp.x1},{wp.y1}"
            ui.draw_text(s, f, where, (chip.right + 8, r.centery), f.mono, ui.TEXT, "midleft")
            label = ui.fit_text(f, wp.label, f.small, 92)
            ui.draw_text(s, f, label, (r.right - 8, r.centery), f.small, ui.DIM, "midright")
            vis = r.clip(area)
            if vis.w and vis.h:
                self.buttons.append((vis, lambda i=i: self.select_waypoint(i), ""))
        s.set_clip(None)
        self._scrollbar(area, content, self.route_scroll)

    def select_waypoint(self, i: int) -> None:
        """Select waypoint i from the list, and bring it into view."""
        layer = self.route_layer
        layer.selected = i
        self._route_follow = i
        wp = layer.route[i]
        cx, cy = (wp.x0 + wp.x1 + 1) * TS / 2, (wp.y0 + wp.y1 + 1) * TS / 2
        v = self.layout()["view"]
        sx, sy = (cx - self.cam[0]) * self.zoom, (cy - self.cam[1]) * self.zoom
        if not (40 < sx < v.w - 40 and 40 < sy < v.h - 40):
            self.center_on(cx, cy)

    def draw_help(self, rect: pygame.Rect) -> None:
        s, f = self.screen, self.fonts
        pygame.draw.rect(s, ui.PANEL, rect)
        pygame.draw.line(s, ui.BORDER, rect.topleft, rect.bottomleft)
        pad = 16
        y = rect.y + 14
        mode = "Route mode" if self.route_layer.active else "Tiles mode"
        ui.draw_text(s, f, "Keys", (rect.x + pad, y), f.title)
        ui.draw_text(s, f, mode, (rect.right - pad, y + 3), f.small, ui.ACCENT, "topright")
        y += 36
        edit = ROUTE_KEYS if self.route_layer.active else TILE_KEYS
        chip_w = 12 + max(ui.key_chip_width(f, k) for k, _ in edit + VIEW_KEYS + FILE_KEYS)
        for title, rows in (("Edit", edit), ("View", VIEW_KEYS), ("General", FILE_KEYS)):
            ui.draw_text(s, f, title.upper(), (rect.x + pad, y), f.small, ui.FAINT)
            y += 22
            for keys, desc in rows:
                if y > rect.bottom - 24:
                    return
                kr = ui.key_chip(s, f, keys, (rect.x + pad, y))
                text = ui.fit_text(f, desc, f.small, rect.w - 2 * pad - chip_w - 6)
                ui.draw_text(s, f, text, (rect.x + pad + chip_w, kr.centery), f.small, ui.TEXT, "midleft")
                y += kr.h + 7
            y += 10

    def draw_status(self, rect: pygame.Rect) -> None:
        s, f = self.screen, self.fonts
        pygame.draw.rect(s, ui.PANEL, rect)
        pygame.draw.line(s, ui.BORDER, rect.topleft, rect.topright)
        cy = rect.centery
        route = self.route_layer.active
        badge = pygame.Rect(rect.x + 10, rect.y + 7, 64, rect.h - 14)
        pygame.draw.rect(s, ui.ACCENT if not route else GROUND, badge, border_radius=5)
        ui.draw_text(s, f, "ROUTE" if route else "TILES", badge.center, f.small, (255, 255, 255), "center")
        x = badge.right + 14
        view = self.layout()["view"]
        if view.collidepoint(self.mouse):
            tx, ty = self.tile_at(self.mouse)
            r = ui.draw_text(s, f, f"x {tx}   y {ty}", (x, cy), f.mono, ui.TEXT, "midleft")
            under = self.tilemap.tilemap.get(f"{tx};{ty}")
            what = "empty"
            if under:
                group = GROUP_NAMES.get(under["type"], under["type"])
                what = f"{group} {self.variant_name(under['type'], under['variant'])}".strip()
            if (tx, ty) in self.tilemap.water:
                what += "  ·  water"
            r = ui.draw_text(s, f, what, (r.right + 16, cy), f.small, ui.DIM, "midleft")
            x = r.right + 24
        else:
            x += 200

        # zoom, bottom right: a click goes back to the default zoom
        zr = pygame.Rect(rect.right - 92, rect.y + 5, 82, rect.h - 10)
        self.button(
            s,
            zr,
            ui.zoom_label(self.zoom),
            self.reset_zoom,
            active=self.zoom == ui.DEFAULT_ZOOM,
            tip=f"Click: default zoom {ui.zoom_label(ui.DEFAULT_ZOOM)} (1)",
            font=f.bold,
        )
        fr = pygame.Rect(zr.x - 88, zr.y, 80, zr.h)
        self.button(s, fr, "Whole map", self.fit_map, tip="Zoom to the whole map (0)")
        info = ""
        if not route:
            snap = "grid" if self.ongrid else "free"
            size = f"{self.multi_tile_size}×{self.multi_tile_size}" if self.multi_tile else "1×1"
            info = f"{snap}  ·  brush {size}"
        else:
            layer = self.route_layer
            if layer.selected is not None and layer.selected < len(layer.route):
                wp = layer.route[layer.selected]
                flags = " ".join(n for n, on in (("ground", wp.ground), ("guide", wp.guide)) if on)
                info = f"waypoint {layer.selected}  {flags}"
        if info:
            r = ui.draw_text(s, f, info, (fr.x - 16, cy), f.small, ui.DIM, "midright")
            right_edge = r.left - 16
        else:
            right_edge = fr.x - 16

        # the message: the route's status in route mode, else the last action
        text, color, at = self.message
        if route and (self.route_layer.status or self.route_layer.planning):
            text = self.route_layer.status
            color = (
                ui.OK
                if text.startswith("OK")
                else ui.ERR if text.startswith(("UNREACHED", "planner error")) else ui.TEXT
            )
            if self.route_layer.planning:
                text += " " + "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.monotonic() * 10) % 10]
                color = ui.WARN
        elif time.monotonic() - at > MESSAGE_SECONDS:
            text = ""
        if text and right_edge - x > 40:
            ui.draw_text(s, f, ui.fit_text(f, text, f.ui, right_edge - x), (x, cy), f.ui, color, "midleft")

    def draw_tooltip(self) -> None:
        for rect, _action, tip in reversed(self.buttons):
            if tip and rect.collidepoint(self.mouse):
                img = self.fonts.text(tip, self.fonts.small)
                w, h = self.screen.get_size()
                r = pygame.Rect(self.mouse[0] + 14, self.mouse[1] + 18, img.get_width() + 16, img.get_height() + 10)
                r.right = min(r.right, w - 4)
                if r.bottom > h - 4:
                    r.bottom = self.mouse[1] - 8
                pygame.draw.rect(self.screen, ui.PANEL_3, r, border_radius=6)
                pygame.draw.rect(self.screen, ui.BORDER, r, 1, border_radius=6)
                self.screen.blit(img, (r.x + 8, r.y + 5))
                return

    # --- loop --------------------------------------------------------------------------
    def run(self):
        # Optional frame cap for automated testing / CI (set EDITOR_MAX_FRAMES)
        max_frames_env = os.environ.get("EDITOR_MAX_FRAMES")
        max_frames = int(max_frames_env) if max_frames_env and max_frames_env.isdigit() else None
        frame_counter = 0
        running = True
        while running:
            dt = self.clock.tick(60) / 1000
            for event in pygame.event.get():
                if not self.handle_event(event):
                    running = False
                    break
            if not running:
                break
            self.update(dt)
            self.draw()
            pygame.display.flip()
            if max_frames is not None:
                frame_counter += 1
                if frame_counter >= max_frames:
                    break  # auto-exit for test harness usage
        pygame.quit()


def main():
    Editor(sys.argv[1] if len(sys.argv) > 1 else MAP_NAME).run()


if __name__ == "__main__":
    main()
