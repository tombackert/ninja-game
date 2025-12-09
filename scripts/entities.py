import math

import pygame

from scripts.collectableManager import CollectableManager as cm
from scripts.constants import (
    AIR_TIME_FATAL,
    DASH_DECEL_TRIGGER_FRAME,
    DASH_DURATION_FRAMES,
    DASH_MIN_ACTIVE_ABS,
    DASH_SPEED,
    DASH_TRAIL_PARTICLE_SPEED,
    ENEMY_SHOOT_BASE,
    ENEMY_SHOOT_SCALE_LOG,
    GRAVITY_ACCEL,
    HORIZONTAL_FRICTION,
    JUMP_VELOCITY,
    MAX_FALL_SPEED,
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
        from scripts.weapons import get_weapon  # local import to avoid circulars

        # Map selected index to weapon name list
        try:
            name = cm.WEAPONS[settings.selected_weapon]
        except Exception:  # pragma: no cover - defensive
            name = "Default"
        # Registry uses lowercase canonical names
        key = name.lower()
        # Normalize some known names
        if key == "default":
            key = "none"
        weapon = get_weapon(key if key in ("gun", "none") else "gun")
        return weapon.fire(self)

    def update(self, tilemap, movement=(0, 0)):
        super().update(tilemap, movement=movement)
        rng = RNGService.get()
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1

        self.air_time += 1

        if self.air_time > AIR_TIME_FATAL:
            if not self.game.dead:
                self.game.screenshake = max(16, self.game.screenshake)
            self.game.dead += 1

        if self.collisions["down"]:
            self.air_time = 0
            self.jumps = 1

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

    def render(self, surf, offset=(0, 0)):
        if abs(self.dashing) <= DASH_MIN_ACTIVE_ABS:
            super().render(surf, offset=offset)
        # Render gun overlay only if equipped weapon is gun
        from scripts.collectableManager import CollectableManager as cm

        try:
            gun_index = cm.WEAPONS.index("Gun")
        except ValueError:  # pragma: no cover
            gun_index = 1
        if self.game.cm.gun and settings.selected_weapon == gun_index:
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
                    (
                        self.rect().centerx + 4 - offset[0],
                        self.rect().centery - offset[1],
                    ),
                )

    def jump(self):
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
