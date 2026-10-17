import pygame

from scripts.asset_manager import AssetManager
from scripts.audio_service import AudioService
from scripts.clouds import Clouds
from scripts.collectableManager import CollectableManager
from scripts.constants import (
    CALM_CAMERA_BAND_Y,
    CALM_CAMERA_DEADZONE_X,
    CALM_CAMERA_EASE_FRAMES,
    CALM_CAMERA_SNAP,
    CAMERA_EASE_FRAMES,
    LEAF_SPAWNER_CLOUD_COUNT,
    TRANSITION_START,
)
from scripts.displayManager import DisplayManager
from scripts.entities import Enemy, Player
from scripts.entity_id import EntityIDGenerator
from scripts.keyboardManager import KeyboardManager
from scripts.particle import Particle
from scripts.particle_system import ParticleSystem
from scripts.projectile_system import ProjectileSystem
from scripts.replay import ReplayManager
from scripts.rng_service import RNGService
from scripts.settings import settings
from scripts.tilemap import Tilemap
from scripts.timer import Timer


class Game:
    """World state and simulation: level, entities and systems.

    `GameState` (see app.py) drives it each frame: `step()` advances the
    world one tick and `scripts.renderer.Renderer` draws it.
    """

    def __init__(self, fullscreen=True):
        pygame.init()

        dm = DisplayManager()
        self.BASE_W = dm.BASE_W
        self.BASE_H = dm.BASE_H
        self.WIN_W = dm.WIN_W
        self.WIN_H = dm.WIN_H

        pygame.display.set_caption("Ninja Game")
        if fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            # Every level start builds a new Game: keep a window that is
            # already open at this size (recreating it stalls 5-12 ms)
            self.screen = pygame.display.get_surface()
            if self.screen is None or self.screen.get_size() != (self.WIN_W, self.WIN_H):
                self.screen = pygame.display.set_mode((self.WIN_W, self.WIN_H))
        self.WIN_W, self.WIN_H = self.screen.get_size()

        # World buffers have one spare column/row: the renderer draws at
        # floor(scroll) and shifts the upscaled image by the remainder.
        # display_2 has alpha so the background can stay unshifted beneath it.
        self.display = pygame.Surface((self.BASE_W + 1, self.BASE_H + 1), pygame.SRCALPHA)
        self.display_2 = pygame.Surface((self.BASE_W + 1, self.BASE_H + 1), pygame.SRCALPHA)
        self.display_3 = pygame.Surface((self.BASE_W, self.BASE_H))

        # Clock
        self.clock = pygame.time.Clock()

        # Movement flags
        self.movement = [False, False]

        # Initialize RNG service to ensure it's ready for gameplay
        from scripts.rng_service import RNGService

        RNGService.get()

        # Asset Manager (Issue 15). Gradually replace direct util calls with manager.
        am = AssetManager.get()
        self.assets = {
            "decor": am.get_image_frames("tiles/decor"),
            "grass": am.get_image_frames("tiles/grass"),
            "large_decor": am.get_image_frames("tiles/large_decor"),
            "stone": am.get_image_frames("tiles/stone"),
            "player": am.get_image("entities/player.png"),
            "background": am.get_image("background-big.png"),
            "clouds": am.get_image_frames("clouds"),
            "enemy/idle": am.get_animation("entities/enemy/idle", img_dur=6),
            "enemy/run": am.get_animation("entities/enemy/run", img_dur=4),
            "particle/leaf": am.get_animation("particles/leaf", img_dur=20, loop=False),
            "particle/particle": am.get_animation("particles/particle", img_dur=6, loop=False),
            "coin": am.get_animation("collectables/coin", img_dur=6),
            "flag": am.get_image_frames("tiles/collectables/flag"),
            "gun": am.get_image("gun.png"),
            "rifle": am.get_image("rifle.png"),
            "sword": am.get_image("sword.png"),
            "slash": am.get_image("slash.png"),
            "star": am.get_image("star.png"),
            "hook": am.get_image("hook.png"),
            "projectile": am.get_image("projectile.png"),
        }
        # Register every store skin's animation set (all palette swaps of default)
        for skin_path in CollectableManager.SKIN_PATHS:
            base = f"entities/player/{skin_path}"
            self.assets[f"player/{skin_path}/idle"] = am.get_animation(f"{base}/idle", img_dur=6)
            self.assets[f"player/{skin_path}/run"] = am.get_animation(f"{base}/run", img_dur=4)
            self.assets[f"player/{skin_path}/jump"] = am.get_animation(f"{base}/jump")
            self.assets[f"player/{skin_path}/slide"] = am.get_animation(f"{base}/slide")
            self.assets[f"player/{skin_path}/wall_slide"] = am.get_animation(f"{base}/wall_slide")

        # Audio service replaces direct sound dict (Issue 16)
        self.audio = AudioService.get()

        # Entities
        self.clouds = Clouds(self.assets["clouds"], count=LEAF_SPAWNER_CLOUD_COUNT)
        self.tilemap = Tilemap(self, tile_size=16)

        # Global variables
        self.level = settings.selected_level
        self.screenshake = 0
        self.timer = Timer(self.level)

        # Collectable Manager
        self.cm = CollectableManager(self)
        self.cm.load_collectables()

        # Replay / ghost manager (Issue 30)
        self.replay = ReplayManager(self)

        # Keyboard Manager
        self.km = KeyboardManager(self)

        self.playerID = 0
        self.playerSkin = settings.selected_skin

        # Load the selected level
        self.load_level(self.level)

        # Debug prints (kept as comments for reference)
        # print(f"id: {self.players[self.playerID].id}")
        # print(f"size: {self.players[self.playerID].size}")

        # Global simulation tick counter for multiplayer synchronization
        # Incremented once per simulation tick in step()
        self.tick = 0

    # Backward compatibility shim for old calls (will be removed):
    def update_sound_volumes(self):  # pragma: no cover - compatibility
        self.audio.apply_volumes()

    def load_level(self, map_id, lives=3, respawn=False):
        self.timer.reset()
        path = "data/maps/" + str(map_id) + ".json"
        if respawn and self.tilemap.loaded_path == path:
            # Tiles only change by extraction (spawners, pickups): put those
            # back instead of parsing the map file again (up to ~45 ms)
            self.tilemap.restore_extracted()
        else:
            self.tilemap.load(path)
            # Precompute immutable tile type counts for performance HUD (tiles static during gameplay)
            try:
                self.tilemap._cached_type_counts = self.tilemap._recompute_type_counts()  # type: ignore[attr-defined]
            except Exception:
                pass

        # Extract flags
        self.flags = []
        flag_tiles = self.tilemap.extract([("flag", 0)], keep=True)
        for tile in flag_tiles:
            flag_rect = pygame.Rect(tile["pos"][0], tile["pos"][1], 16, 16)
            self.flags.append(flag_rect)

        self.leaf_spawners = []
        for tree in self.tilemap.extract([("large_decor", 2)], keep=True):
            self.leaf_spawners.append(pygame.Rect(4 + tree["pos"][0], 4 + tree["pos"][1], 23, 13))

        # START LOAD LEVEL
        self.enemies = []
        # Only clear players if this is a fresh load, not a respawn
        if not respawn:
            self.players = []

        # RNG Determinism (Issue 48)
        from scripts.rng_service import RNGService

        rng = RNGService.get()
        id_gen = EntityIDGenerator.get()

        if respawn:
            # Restore RNG state to ensure deterministic replay
            if hasattr(self, "level_rng_state") and self.level_rng_state is not None:
                rng.set_state(self.level_rng_state)
            # Restore entity ID generator state for deterministic enemy IDs (MP-02)
            if hasattr(self, "level_id_gen_state"):
                id_gen.set_state(self.level_id_gen_state)

            for player in self.players:
                # Enforce strict coordinate reset
                player.pos = list(player.respawn_pos)
                player.air_time = 0
                player.velocity = [0, 0]  # Reset velocity too for safety
            for spawner in self.tilemap.extract([("spawners", 0), ("spawners", 1)]):
                if spawner["variant"] == 1:
                    self.enemies.append(Enemy(self, spawner["pos"], (8, 15), id_gen.next_id()))
        else:
            # Capture RNG state at start of level
            self.level_rng_state = rng.get_state()
            # Reset and capture entity ID generator state (MP-02)
            id_gen.reset(0)
            self.level_id_gen_state = id_gen.get_state()

            skin = self.playerSkin
            # Lucky Charm gear: +1 life on fresh level start (not on respawn)
            try:
                gear_name = CollectableManager.GEAR[settings.selected_gear]
            except (IndexError, AttributeError):
                gear_name = "None"
            if gear_name == "Lucky Charm" and self.cm.lucky_charm > 0:
                lives += 1
            for spawner in self.tilemap.extract([("spawners", 0), ("spawners", 1)]):
                if spawner["variant"] == 0:
                    player = Player(
                        self,
                        spawner["pos"],
                        (8, 15),
                        id_gen.next_id(),
                        lives=lives,
                        respawn_pos=list(spawner["pos"]),
                    )
                    player.skin = skin
                    player.air_time = 0
                    self.players.append(player)
                else:
                    self.enemies.append(Enemy(self, spawner["pos"], (8, 15), id_gen.next_id()))
            self.saves = 1

            # Set the current player if there are any players
            if self.players:
                self.player = self.players[self.playerID]
        # END LOAD LEVEL

        # Systems / collections (post-refactor additions)
        self.projectiles = ProjectileSystem(self)
        self.particle_system = ParticleSystem(self)
        # Backward compatibility aliases so existing code that directly
        # appends to game.particles / game.sparks continues to work.
        self.particles = self.particle_system.particles
        self.sparks = self.particle_system.sparks

        self.scroll = [0, 0]
        self.dead = 0
        if self.players:
            # Set using canonical name; alias still supports legacy code.
            self.player.lives = lives
        self.transition = TRANSITION_START
        self.endpoint = False

        self.cm.load_collectables_from_tilemap(self.tilemap)
        # Initialise replay state now that level and player exist
        player_ref = getattr(self, "player", None)
        if player_ref is not None:
            try:
                self.replay.on_level_load(self.level, player_ref)
            except Exception:
                pass

    def apply_inputs(self, inputs):
        """Map input names (left/right/jump/dash/shoot) onto the player."""
        self.movement = [False, False]
        for key in inputs:
            if key == "left":
                self.movement[0] = True
            elif key == "right":
                self.movement[1] = True
            elif key == "jump":
                self.player.jump()
            elif key == "dash":
                self.player.dash()
            elif key == "shoot":
                self.player.shoot()

    def step(self):
        """Advance the world by one simulation tick.

        The single source of truth for update order. Every single-player
        loop (GameState, legacy run, TrainingEnv, prediction re-simulation)
        calls this, so all of them consume the shared RNG identically.
        Rendering must never touch simulation state.
        """
        self.tick += 1
        self.screenshake = max(0, self.screenshake - 1)

        self.projectiles.update(self.tilemap, self.players, self.enemies)
        self.clouds.update()

        for enemy in self.enemies.copy():
            kill = enemy.update(self.tilemap, (0, 0))
            if kill:
                self.enemies.remove(enemy)

        if not self.dead:
            for idx, player in enumerate(self.players):
                # Use list index (not entity ID) to match playerID selection
                if idx == self.playerID:
                    player.update(self.tilemap, (self.movement[1] - self.movement[0], 0))
                else:
                    player.update(self.tilemap, (0, 0))

        self.particle_system.update()
        self.spawn_leaves()
        self.cm.update(self.player.rect())

        for flag_rect in self.flags:
            if self.player.rect().colliderect(flag_rect):
                self.endpoint = True

    def update_camera(self):
        """Ease the camera toward the player (once per tick).

        "classic" always eases back to center the player. "calm" lets the
        player move within a box around the center, follows vertically only
        on the ground (or when the player leaves a band mid-air, e.g. falling)
        and stops once it arrives, so the picture stands still more often.
        """
        cx = self.player.rect().centerx - self.BASE_W / 2
        cy = self.player.rect().centery - self.BASE_H / 2
        if settings.camera_style != "calm":
            self.scroll[0] += (cx - self.scroll[0]) / CAMERA_EASE_FRAMES
            self.scroll[1] += (cy - self.scroll[1]) / CAMERA_EASE_FRAMES
            return
        tx = min(max(self.scroll[0], cx - CALM_CAMERA_DEADZONE_X), cx + CALM_CAMERA_DEADZONE_X)
        ty = cy
        if not self.player.collisions["down"]:
            ty = min(max(self.scroll[1], cy - CALM_CAMERA_BAND_Y), cy + CALM_CAMERA_BAND_Y)
        for axis, target in ((0, tx), (1, ty)):
            gap = target - self.scroll[axis]
            if abs(gap) < CALM_CAMERA_SNAP:
                self.scroll[axis] = target
            else:
                self.scroll[axis] += gap / CALM_CAMERA_EASE_FRAMES

    def spawn_leaves(self):
        rng = RNGService.get()
        for rect in self.leaf_spawners:
            if rng.random() * 49999 < rect.width * rect.height:
                pos = (
                    rect.x + rng.random() * rect.width,
                    rect.y + rng.random() * rect.height,
                )
                self.particles.append(
                    Particle(
                        self,
                        "leaf",
                        pos,
                        velocity=[-0.1, 0.3],
                        frame=rng.randint(0, 20),
                    )
                )
