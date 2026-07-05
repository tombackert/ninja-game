import math

import pygame

from scripts.collectableManager import CollectableManager as cm
from scripts.constants import (
    AIR_JUMP_VELOCITY,
    AIR_TIME_FATAL,
    DASH_DECEL_TRIGGER_FRAME,
    DASH_DURATION_FRAMES,
    DASH_MIN_ACTIVE_ABS,
    DASH_SPEED,
    DASH_TRAIL_PARTICLE_SPEED,
    ENEMY_SHOOT_BASE,
    ENEMY_SHOOT_SCALE_LOG,
    GRAPPLE_ARRIVE_DIST,
    GRAPPLE_MAX_FRAMES,
    GRAPPLE_PULL_SPEED,
    GRAVITY_ACCEL,
    HORIZONTAL_FRICTION,
    JUMP_VELOCITY,
    MAX_FALL_SPEED,
    SHIELD_REARM_FRAMES,
    WALL_JUMP_HORIZONTAL_VEL,
    WALL_JUMP_VERTICAL_VEL,
    WALL_SLIDE_MAX_SPEED,
)
from scripts.effects_util import spawn_hit_sparks
from scripts.particle import Particle
from scripts.policy_service import PolicyService
from scripts.rng_service import RNGService
from scripts.services import ServiceContainer
from scripts.settings import settings
from scripts.spark import Spark


class PhysicsEntity:
    def __init__(self, game, e_type, pos, size, id, services: ServiceContainer | None = None):
        # Retain original game reference for legacy code; prefer services if provided.
        self.game = game
        self.services = services  # May be None until systems initialized
        self.type = e_type
        self.pos = list(pos)
        self.size = size
        self.id = id
        self.velocity = [0, 0]
        self.collisions = {"up": False, "down": False, "right": False, "left": False}

        self.alive = True
        self.action = ""
        self.anim_offset = (-3, -3)
        self.flip = False
        self.set_action("idle")

        self.last_movement = [0, 0]

    def rect(self):
        return pygame.Rect(self.pos[0], self.pos[1], self.size[0], self.size[1])

    def set_action(self, action):
        if action != self.action:
            self.action = action
            if self.type == "enemy":
                self.animation = self.game.assets[self.type + "/" + self.action].copy()
            if self.type == "player":
                self.animation = self.game.assets[self.type + "/" + cm.SKIN_PATHS[self.skin] + "/" + self.action].copy()

    # --- Physics step granular methods (Issue 20) ---
    def begin_update(self):
        """Reset frame-specific collision flags.

        Called at start of each update cycle. Split out so tests can drive
        subsequent phases individually if desired.
        """
        self.collisions = {"up": False, "down": False, "right": False, "left": False}

    def compute_frame_movement(self, movement):
        """Return tuple of (dx, dy) for this frame before collision response."""
        return movement[0] + self.velocity[0], movement[1] + self.velocity[1]

    def apply_horizontal_movement(self, tilemap, frame_movement):
        self.pos[0] += frame_movement[0]
        entity_rect = self.rect()
        if frame_movement[0] != 0:
            for rect in tilemap.physics_rects_around(self.pos):  # narrow query
                if entity_rect.colliderect(rect):
                    if frame_movement[0] > 0:
                        entity_rect.right = rect.left
                        self.collisions["right"] = True
                    else:  # frame_movement[0] < 0
                        entity_rect.left = rect.right
                        self.collisions["left"] = True
                    self.pos[0] = entity_rect.x

    def apply_vertical_movement(self, tilemap, frame_movement):
        self.pos[1] += frame_movement[1]
        entity_rect = self.rect()
        if frame_movement[1] != 0:
            for rect in tilemap.physics_rects_around(self.pos):
                if entity_rect.colliderect(rect):
                    if frame_movement[1] > 0:
                        entity_rect.bottom = rect.top
                        self.collisions["down"] = True
                    else:  # frame_movement[1] < 0
                        entity_rect.top = rect.bottom
                        self.collisions["up"] = True
                    self.pos[1] = entity_rect.y

    def update_orientation(self, movement):
        if movement[0] > 0:
            self.flip = False
        elif movement[0] < 0:
            self.flip = True
        self.last_movement = movement

    def apply_gravity(self):
        self.velocity[1] = min(MAX_FALL_SPEED, self.velocity[1] + GRAVITY_ACCEL)
        if self.collisions["down"] or self.collisions["up"]:
            # Cancel vertical velocity if we contacted ceiling/floor this frame.
            self.velocity[1] = 0

    def finalize_update(self):
        self.animation.update()

    def update(self, tilemap, movement=(0, 0)):
        """Composite update preserved for backward compatibility.

        Steps:
          1. begin_update -> reset collisions
          2. compute_frame_movement
          3. apply_horizontal_movement
          4. apply_vertical_movement
          5. update_orientation
          6. apply_gravity (after collision resolution so we can nullify velocity)
          7. finalize_update (animation advance)
        """
        self.begin_update()
        frame_movement = self.compute_frame_movement(movement)
        self.apply_horizontal_movement(tilemap, frame_movement)
        self.apply_vertical_movement(tilemap, frame_movement)
        self.update_orientation(movement)
        self.apply_gravity()
        self.finalize_update()

    def render(self, surf, offset=(0, 0)):
        surf.blit(
            pygame.transform.flip(self.animation.img(), self.flip, False),
            (
                self.pos[0] - offset[0] + self.anim_offset[0],
                self.pos[1] - offset[1] + self.anim_offset[1],
            ),
        )


class Enemy(PhysicsEntity):
    def __init__(
        self, game, pos, size=(15, 8), id=0, services: ServiceContainer | None = None, policy: str = "scripted_enemy"
    ):
        super().__init__(game, "enemy", pos, size, id, services=services)
        self.walking = 0
        self.policy = PolicyService.get(policy)

    def update(self, tilemap, movement=(0, 0)):
        rng = RNGService.get()
        # Delegate behavior to policy
        decision = self.policy.decide(self, self.game)

        # Apply movement intent
        intent_movement = decision.get("movement", (0, 0))
        # Combine with external movement (if any) or replace?
        # Usually update's movement arg is external forces.
        combined_movement = (movement[0] + intent_movement[0], movement[1] + intent_movement[1])

        # Apply jump intent
        if decision.get("jump") and self.collisions["down"]:
            self.velocity[1] = JUMP_VELOCITY

        # Apply shooting intent
        if decision.get("shoot"):
            if self.services:
                self.services.play("shoot")
            else:
                self.game.audio.play("shoot")

            shoot_dir = decision.get("shoot_direction", 0)
            if shoot_dir != 0:
                direction = (
                    shoot_dir * ENEMY_SHOOT_BASE * (1 + ENEMY_SHOOT_SCALE_LOG * math.log(settings.selected_level + 1))
                )
                # Ensure we spawn slightly offset to avoid self-hit immediately if not careful,
                # though ProjectileSystem handles owner check.
                # Original logic used centerx +/- 15.
                spawn_x = self.rect().centerx + (15 if shoot_dir > 0 else -15)
                (self.services.projectiles.spawn if self.services else self.game.projectiles.spawn)(
                    spawn_x,
                    self.rect().centery,
                    direction,
                    "enemy",
                )

        super().update(tilemap, movement=combined_movement)

        if combined_movement[0] != 0:
            self.set_action("run")
        else:
            self.set_action("idle")

        # Dash kill & projectile collision checks
        if abs(self.game.player.dashing) >= DASH_MIN_ACTIVE_ABS:
            if self.rect().colliderect(self.game.player.rect()):
                self.game.screenshake = max(16, self.game.screenshake)
                if self.services:
                    self.services.play("hit")
                else:
                    self.game.audio.play("hit")
                # Multiplayer servers credit the killing player; single player
                # falls back to the global coin counter.
                award = getattr(self.game, "award_coin", None)
                if award:
                    award(getattr(self.game.player, "id", None))
                else:
                    self.game.cm.coins += 1
                spawn_hit_sparks(self.game, self.rect().center)
                self.game.sparks.append(Spark(self.rect().center, 0, 5 + rng.random()))
                self.game.sparks.append(Spark(self.rect().center, math.pi, 5 + rng.random()))
                return True

    # Collision with player projectiles handled centrally in ProjectileSystem.update

    def render(self, surf, offset=(0, 0)):
        super().render(surf, offset=offset)

        if self.flip:
            surf.blit(
                pygame.transform.flip(self.game.assets["gun"], True, False),
                (
                    self.rect().centerx - 4 - self.game.assets["gun"].get_width() - offset[0],
                    self.rect().centery - offset[1],
                ),
            )
        else:
            surf.blit(
                self.game.assets["gun"],
                (self.rect().centerx + 4 - offset[0], self.rect().centery - offset[1]),
            )


class Player(PhysicsEntity):
    def __init__(
        self,
        game,
        pos,
        size,
        id,
        lives,
        respawn_pos,
        services: ServiceContainer | None = None,
    ):
        """Player entity.

        Parameter 'lives' replaces legacy 'lifes'.
        Internally we migrate to the proper English term 'lives'.
        Legacy attribute 'lifes' provided as property alias for old references.
        """
        self.skin = 0
        super().__init__(game, "player", pos, size, id, services=services)
        self.air_time = 0
        self.jumps = 1
        self.wall_slide = False
        self.dashing = 0
        # Store canonical field _lives and expose property alias.
        self._lives = lives
        self.respawn_pos = respawn_pos
        self.shoot_cooldown = 10
        # Store item state (new game elements)
        self.air_jumps = 0  # extra air jumps left (moon boots)
        self.slash_timer = 0  # frames the sword slash VFX stays visible
        self.grapple_point = None  # active grapple anchor [x, y] or None
        self.grapple_frames = 0  # frames spent in current pull (safety timeout)
        self.shield_ready = False  # armed shield charge absorbs next hit
        self.shield_rearm = 0  # frames until next charge arms

    # --- New canonical attribute ---
    @property
    def lives(self):  # noqa: D401 simple property
        return self._lives

    @lives.setter
    def lives(self, value):
        self._lives = value

    # --- Backward compatibility alias (will be removed in later iteration) ---
    @property
    def lifes(self):  # type: ignore[override]
        return self._lives

    @lifes.setter
    def lifes(self, value):  # type: ignore[override]
        self._lives = value

    def shoot(self):
        from scripts.collectableManager import CollectableManager as cm
        from scripts.weapons import WEAPON_KEYS, get_weapon  # local import to avoid circulars

        # Map selected index to weapon name list
        try:
            name = cm.WEAPONS[settings.selected_weapon]
        except Exception:  # pragma: no cover - defensive
            name = "Default"
        weapon = get_weapon(WEAPON_KEYS.get(name, "none"))
        return weapon.fire(self)

    # --- Gear helpers (passive store items) ---
    def gear_name(self) -> str:
        from scripts.collectableManager import CollectableManager as cm

        try:
            return cm.GEAR[settings.selected_gear]
        except Exception:  # pragma: no cover - defensive
            return "None"

    def absorb_hit(self) -> bool:
        """Consume an armed shield charge instead of a life. Returns True if absorbed."""
        game_cm = getattr(self.game, "cm", None)
        if not self.shield_ready or game_cm is None or game_cm.shield <= 0:
            return False
        game_cm.shield -= 1
        self.shield_ready = False
        self.shield_rearm = SHIELD_REARM_FRAMES
        spawn_hit_sparks(self.game, self.rect().center)
        return True

    def update(self, tilemap, movement=(0, 0)):
        # Grapple pull: steer velocity toward the anchor; gravity is
        # overwritten each frame while the pull is active.
        if self.grapple_point is not None:
            cx, cy = self.rect().center
            dx = self.grapple_point[0] - cx
            dy = self.grapple_point[1] - cy
            dist = math.hypot(dx, dy)
            if dist > 0:
                self.velocity[0] = dx / dist * GRAPPLE_PULL_SPEED
                self.velocity[1] = dy / dist * GRAPPLE_PULL_SPEED
            self.grapple_frames += 1

        super().update(tilemap, movement=movement)

        # Grapple release: arrival, collision or safety timeout
        if self.grapple_point is not None:
            cx, cy = self.rect().center
            dx = self.grapple_point[0] - cx
            dy = self.grapple_point[1] - cy
            if (
                dx * dx + dy * dy <= GRAPPLE_ARRIVE_DIST**2
                or any(self.collisions.values())
                or self.grapple_frames > GRAPPLE_MAX_FRAMES
            ):
                self.grapple_point = None

        rng = RNGService.get()
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
        if self.slash_timer > 0:
            self.slash_timer -= 1

        # Shield gear: arm a charge after the re-arm delay
        game_cm = getattr(self.game, "cm", None)
        if self.gear_name() == "Shield" and game_cm is not None and game_cm.shield > 0:
            if not self.shield_ready:
                if self.shield_rearm > 0:
                    self.shield_rearm -= 1
                if self.shield_rearm == 0:
                    self.shield_ready = True
        else:
            self.shield_ready = False

        self.air_time += 1

        if self.air_time > AIR_TIME_FATAL:
            if not self.game.dead:
                self.game.screenshake = max(16, self.game.screenshake)
                # Duck audio on death impact
                if self.services:
                    self.services.audio.trigger_ducking(intensity=0.2)
                elif hasattr(self.game, "audio"):
                    self.game.audio.trigger_ducking(intensity=0.2)
            self.game.dead += 1

        if self.collisions["down"]:
            self.air_time = 0
            self.jumps = 1
            self.air_jumps = 1  # moon boots double jump recharges on landing

        self.wall_slide = False
        if (self.collisions["right"] or self.collisions["left"]) and self.air_time > 4:
            self.wall_slide = True
            self.velocity[1] = min(self.velocity[1], WALL_SLIDE_MAX_SPEED)
            if self.collisions["right"]:
                self.flip = False
            else:
                self.flip = True
            self.set_action("wall_slide")

        if not self.wall_slide:
            if self.air_time > 4:
                self.set_action("jump")
            elif movement[0] != 0:
                self.set_action("run")
            else:
                self.set_action("idle")

        if abs(self.dashing) in {DASH_DURATION_FRAMES, DASH_MIN_ACTIVE_ABS}:
            for i in range(20):
                angle = rng.random() * math.pi * 2
                speed = rng.random() * 0.5 + 0.5
                pvelocity = [math.cos(angle) * speed, math.sin(angle) * speed]
                self.game.particles.append(
                    Particle(
                        self.game,
                        "particle",
                        self.rect().center,
                        velocity=pvelocity,
                        frame=rng.randint(0, 7),
                    )
                )
        if self.dashing > 0:
            self.dashing = max(0, self.dashing - 1)
        if self.dashing < 0:
            self.dashing = min(0, self.dashing + 1)
        if abs(self.dashing) > DASH_MIN_ACTIVE_ABS:
            self.velocity[0] = abs(self.dashing) / self.dashing * DASH_SPEED
            if abs(self.dashing) == DASH_DECEL_TRIGGER_FRAME:
                self.velocity[0] *= 0.1
            pvelocity = [
                abs(self.dashing) / self.dashing * rng.random() * DASH_TRAIL_PARTICLE_SPEED,
                0,
            ]
            self.game.particles.append(
                Particle(
                    self.game,
                    "particle",
                    self.rect().center,
                    velocity=pvelocity,
                    frame=rng.randint(0, 7),
                )
            )

        if self.velocity[0] > 0:
            self.velocity[0] = max(self.velocity[0] - HORIZONTAL_FRICTION, 0)
        else:
            self.velocity[0] = min(self.velocity[0] + HORIZONTAL_FRICTION, 0)

    # Held-weapon overlay: weapon display name -> (asset key, ownership attr)
    _HELD_WEAPON_ASSETS = {
        "Gun": ("gun", "gun"),
        "Rifle": ("rifle", "rifle"),
        "Sword": ("sword", "sword"),
        "Grapple Hook": ("hook", "grapple_hook"),
    }

    def render(self, surf, offset=(0, 0)):
        if abs(self.dashing) <= DASH_MIN_ACTIVE_ABS:
            super().render(surf, offset=offset)

        # Grapple rope behind the player sprite additions
        if self.grapple_point is not None:
            pygame.draw.line(
                surf,
                (200, 205, 215),
                (self.rect().centerx - offset[0], self.rect().centery - offset[1]),
                (self.grapple_point[0] - offset[0], self.grapple_point[1] - offset[1]),
                1,
            )

        self._render_held_weapon(surf, offset)
        self._render_slash_vfx(surf, offset)
        self._render_shield_bubble(surf, offset)

    def _render_held_weapon(self, surf, offset):
        from scripts.collectableManager import CollectableManager as cm

        try:
            name = cm.WEAPONS[settings.selected_weapon]
        except (IndexError, TypeError):  # pragma: no cover - defensive
            return
        entry = self._HELD_WEAPON_ASSETS.get(name)
        if entry is None:
            return
        asset_key, owned_attr = entry
        if getattr(self.game.cm, owned_attr, 0) <= 0:
            return
        img = self.game.assets.get(asset_key) if hasattr(self.game.assets, "get") else None
        if img is None:
            return
        if self.flip:
            surf.blit(
                pygame.transform.flip(img, True, False),
                (
                    self.rect().centerx - 4 - img.get_width() - offset[0],
                    self.rect().centery - offset[1],
                ),
            )
        else:
            surf.blit(
                img,
                (
                    self.rect().centerx + 4 - offset[0],
                    self.rect().centery - offset[1],
                ),
            )

    def _render_slash_vfx(self, surf, offset):
        if self.slash_timer <= 0:
            return
        img = self.game.assets.get("slash") if hasattr(self.game.assets, "get") else None
        if img is None:
            return
        prect = self.rect()
        if self.flip:
            surf.blit(
                pygame.transform.flip(img, True, False),
                (prect.left - img.get_width() - 2 - offset[0], prect.centery - img.get_height() // 2 - offset[1]),
            )
        else:
            surf.blit(
                img,
                (prect.right + 2 - offset[0], prect.centery - img.get_height() // 2 - offset[1]),
            )

    def _render_shield_bubble(self, surf, offset):
        if not self.shield_ready:
            return
        radius = 13
        bubble = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(bubble, (120, 200, 255, 60), (radius, radius), radius)
        pygame.draw.circle(bubble, (170, 220, 250, 150), (radius, radius), radius, 1)
        surf.blit(
            bubble,
            (self.rect().centerx - radius - offset[0], self.rect().centery - radius - offset[1]),
        )

    def jump(self):
        # Jump input releases an active grapple with a small upward boost
        # (skill move: swing release).
        if self.grapple_point is not None:
            self.grapple_point = None
            self.velocity[1] = AIR_JUMP_VELOCITY
            self.air_time = 5
            return True

        if self.wall_slide:
            if self.flip and self.last_movement[0] < 0:
                self.velocity[0] = WALL_JUMP_HORIZONTAL_VEL
                self.velocity[1] = WALL_JUMP_VERTICAL_VEL
                self.air_time = 5
                self.jumps = max(0, self.jumps - 1)
                return True
            elif not self.flip and self.last_movement[0] > 0:
                self.velocity[0] = -WALL_JUMP_HORIZONTAL_VEL
                self.velocity[1] = WALL_JUMP_VERTICAL_VEL
                self.air_time = 5
                self.jumps = max(0, self.jumps - 1)
                return True

        elif self.jumps:
            self.velocity[1] = JUMP_VELOCITY
            self.jumps -= 1
            self.air_time = 5
            return True

        # Moon boots gear: one extra (weaker) air jump
        elif (
            self.air_jumps > 0
            and self.gear_name() == "Moon Boots"
            and getattr(self.game, "cm", None) is not None
            and self.game.cm.moon_boots > 0
        ):
            self.velocity[1] = AIR_JUMP_VELOCITY
            self.air_jumps -= 1
            self.air_time = 5
            rng = RNGService.get()
            for _ in range(10):
                angle = rng.random() * math.pi + math.pi  # downward burst
                speed = rng.random() * 0.5 + 0.5
                self.game.particles.append(
                    Particle(
                        self.game,
                        "particle",
                        self.rect().midbottom,
                        velocity=[math.cos(angle) * speed, -math.sin(angle) * speed],
                        frame=rng.randint(0, 7),
                    )
                )
            return True

    def dash(self):
        if not self.dashing:
            if self.services:
                self.services.play("dash")
            else:
                self.game.audio.play("dash")
            if self.flip:
                self.dashing = -DASH_DURATION_FRAMES
            else:
                self.dashing = DASH_DURATION_FRAMES
