# Deprecated legacy game loop for backward compatibility.!!!!


import pygame
import time

from scripts.displayManager import DisplayManager
from scripts.entities import Player, Enemy
from scripts.asset_manager import AssetManager
from scripts.audio_service import AudioService
from scripts.tilemap import Tilemap
from scripts.clouds import Clouds
from scripts.timer import Timer
from scripts.constants import (
    TRANSITION_START,
    TRANSITION_MAX,
    LEAF_SPAWNER_CLOUD_COUNT,
    DEAD_ANIM_FADE_START,
    RESPAWN_DEAD_THRESHOLD,
)
from scripts.settings import settings
from scripts.collectableManager import CollectableManager
from scripts.level_cache import list_levels
from scripts.ui import UI
from scripts.keyboardManager import KeyboardManager
from scripts.effects import Effects
from scripts.projectile_system import ProjectileSystem
from scripts.particle_system import ParticleSystem

"""Legacy monolithic Game loop.

Note:
    The refactored application now uses `StateManager` (see `app.py`) and
    `GameState` for per-frame update & render. The legacy in-method pause
    handling (nested `while not self.paused` and the blocking
    `Menu.pause_menu(self)` call) has been removed as part of Issue 13
    (PauseState integration). Pressing ESC in the modern flow is routed
    to an action (`pause_toggle`) which pushes a `PauseState` overlay.

    This `run()` method remains for backward compatibility with older
    entry points but no longer provides an in-loop pause menu. It should
    be considered deprecated and will be deleted once all callers migrate
    to the state-driven architecture.
"""


class Game:
    def __init__(self):
        pygame.init()

        dm = DisplayManager()
        self.BASE_W = dm.BASE_W
        self.BASE_H = dm.BASE_H
        self.WIN_W = dm.WIN_W
        self.WIN_H = dm.WIN_H

        pygame.display.set_caption("Ninja Game")
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.WIN_W, self.WIN_H = self.screen.get_size()

        self.display = pygame.Surface((self.BASE_W, self.BASE_H), pygame.SRCALPHA)
        self.display_2 = pygame.Surface((self.BASE_W, self.BASE_H))
        self.display_3 = pygame.Surface((self.BASE_W, self.BASE_H))

        # Clock
        self.clock = pygame.time.Clock()

        # Movement flags
        self.movement = [False, False]

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
            "player/default/idle": am.get_animation("entities/player/default/idle", img_dur=6),
            "player/default/run": am.get_animation("entities/player/default/run", img_dur=4),
            "player/default/jump": am.get_animation("entities/player/default/jump"),
            "player/default/slide": am.get_animation("entities/player/default/slide"),
            "player/default/wall_slide": am.get_animation("entities/player/default/wall_slide"),
            "player/red/idle": am.get_animation("entities/player/red/idle", img_dur=6),
            "player/red/run": am.get_animation("entities/player/red/run", img_dur=4),
            "player/red/jump": am.get_animation("entities/player/red/jump"),
            "player/red/slide": am.get_animation("entities/player/red/slide"),
            "player/red/wall_slide": am.get_animation("entities/player/red/wall_slide"),
            "particle/leaf": am.get_animation("particles/leaf", img_dur=20, loop=False),
            "particle/particle": am.get_animation("particles/particle", img_dur=6, loop=False),
            "coin": am.get_animation("collectables/coin", img_dur=6),
            "flag": am.get_image_frames("tiles/collectables/flag"),
            "gun": am.get_image("gun.png"),
            "projectile": am.get_image("projectile.png"),
        }

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

        # Keyboard Manager
        self.km = KeyboardManager(self)

        self.playerID = 0
        self.playerSkin = settings.selected_skin

        # Load the selected level
        self.load_level(self.level)

        # Debug prints (kept as comments for reference)
        # print(f"id: {self.players[self.playerID].id}")
        # print(f"size: {self.players[self.playerID].size}")

        # Game state (legacy loop compatibility)
        self.running = True
        # Legacy pause flag retained only for backward compatibility; the
        # new architecture uses PauseState overlays.
        self.paused = False
        # Performance HUD (shared abstraction with modern renderer)
        from scripts.perf_hud import PerformanceHUD  # local import to avoid early cost if unused

        self.perf_hud = PerformanceHUD(enabled=True)

    # Backward compatibility shim for old calls (will be removed):
    def update_sound_volumes(self):  # pragma: no cover - compatibility
        self.audio.apply_volumes()

    def load_level(self, map_id, lives=3, respawn=False):
        self.timer.reset()
        self.tilemap.load("data/maps/" + str(map_id) + ".json")
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
        self.players = []

        if respawn:
            enemy_id = 0
            for player in self.players:
                player.pos = player.respawn_pos
                player.air_time = 0
            for spawner in self.tilemap.extract([("spawners", 0), ("spawners", 1)]):
                if spawner["variant"] == 1:
                    self.enemies.append(Enemy(self, spawner["pos"], (8, 15), enemy_id))
                    enemy_id += 1
        else:
            enemy_id = 0
            player_id = 0
            skin = self.playerSkin
            for spawner in self.tilemap.extract([("spawners", 0), ("spawners", 1)]):
                if spawner["variant"] == 0:
                    player = Player(
                        self,
                        spawner["pos"],
                        (8, 15),
                        player_id,
                        lifes=lives,
                        respawn_pos=list(spawner["pos"]),
                    )
                    player.skin = skin
                    player.air_time = 0
                    self.players.append(player)
                    player_id += 1
                else:
                    self.enemies.append(Enemy(self, spawner["pos"], (8, 15), enemy_id))
                    enemy_id += 1
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

    def run(self):
        self.audio.play_music("data/music.wav", loops=-1)
        self.audio.play("ambience", loops=-1)

        # Simplified legacy loop (no in-loop pause handling). For full
        # gameplay use the state-driven `app.main()` harness.
        while self.running:
            self.perf_hud.begin_frame()

            self.timer.update(self.level)
            self.display.fill((0, 0, 0, 0))
            self.display_2.blit(self.assets["background"], (0, 0))
            self.screenshake = max(0, self.screenshake - 1)

            # Flag & level completion logic (unchanged)
            for flag_rect in self.flags:
                if self.player.rect().colliderect(flag_rect):
                    self.endpoint = True
            if self.endpoint:
                self.transition += 1
                if self.transition > TRANSITION_MAX:
                    self.timer.update_best_time()
                    levels = list_levels()
                    current_level_index = levels.index(self.level)
                    if current_level_index == len(levels) - 1:
                        self.load_level(self.level)
                    else:
                        next_level = levels[current_level_index + 1]
                        self.level = next_level
                    settings.set_level_to_playable(self.level)
                    settings.selected_level = self.level
                    self.load_level(self.level)
            if self.transition < 0:
                self.transition += 1

            if self.player.lifes < 1:
                self.dead += 1
            if self.dead:
                self.dead += 1
                if self.dead >= DEAD_ANIM_FADE_START:
                    self.transition = min(TRANSITION_MAX, self.transition + 1)
                if self.dead > RESPAWN_DEAD_THRESHOLD and self.player.lifes >= 1:
                    self.load_level(self.level, self.player.lifes, respawn=True)
                if self.dead > RESPAWN_DEAD_THRESHOLD and self.player.lifes < 1:
                    self.load_level(self.level)

            # Camera smoothing
            self.scroll[0] += (self.player.rect().centerx - self.display.get_width() / 2 - self.scroll[0]) / 30
            self.scroll[1] += (self.player.rect().centery - self.display.get_height() / 2 - self.scroll[1]) / 30
            render_scroll = (int(self.scroll[0]), int(self.scroll[1]))

            UI.render_game_elements(self, render_scroll)
            # Update projectiles after entities so newly spawned
            # this frame move immediately
            if hasattr(self.projectiles, "update"):
                self.projectiles.update(self.tilemap, self.players, self.enemies)
            self.km.handle_keyboard_input()  # Legacy direct polling
            self.km.handle_mouse_input()

            if self.transition:
                Effects.transition(self)
            self.display_2.blit(self.display, (0, 0))

            # HUD
            UI.render_game_ui_element(self.display_2, f"{self.timer.text}", self.BASE_W - 70, 5)
            UI.render_game_ui_element(self.display_2, f"{self.timer.best_time_text}", self.BASE_W - 70, 15)
            UI.render_game_ui_element(self.display_2, f"Level: {self.level}", self.BASE_W // 2 - 40, 5)
            UI.render_game_ui_element(self.display_2, f"Lives: {self.player.lifes}", 5, 5)
            UI.render_game_ui_element(self.display_2, f"${self.cm.coins}", 5, 15)
            UI.render_game_ui_element(self.display_2, f"Ammo:  {self.cm.ammo}", 5, 25)

            # Mark end of work segment for HUD
            self.perf_hud.end_work_segment()
            # Render overlay using prior full frame data
            self.perf_hud.render(self.display_2, x=5, y=self.BASE_H - 90)
            # Present (screenshake applied after overlay so it can shake as well)
            Effects.screenshake(self)
            pygame.display.update()
            # Cap / sleep & finalize full frame timing (available next frame)
            self.clock.tick(60)
            self.perf_hud.end_frame(clock=self.clock)

            # If ESC pressed (legacy flag),
            # exit loop (pause handled externally in new system)
            if self.paused:
                self.running = False

        self.cm.save_collectables()
        print("Game Over (legacy run loop exited)")


if __name__ == "__main__":
    Game().run()
