import math
import random

import pygame

from scripts.particle import Particle
from scripts.spark import Spark
from scripts.effects_util import spawn_hit_sparks, spawn_projectile_sparks
from scripts.settings import settings
from scripts.collectableManager import CollectableManager as cm
from scripts.constants import (
    GRAVITY_ACCEL,
    MAX_FALL_SPEED,
    HORIZONTAL_FRICTION,
    WALL_SLIDE_MAX_SPEED,
    JUMP_VELOCITY,
    WALL_JUMP_HORIZONTAL_VEL,
    WALL_JUMP_VERTICAL_VEL,
    DASH_DURATION_FRAMES,
    DASH_DECEL_TRIGGER_FRAME,
    DASH_MIN_ACTIVE_ABS,
    DASH_SPEED,
    DASH_TRAIL_PARTICLE_SPEED,
    PROJECTILE_SPEED,
    ENEMY_DIRECTION_BASE,
    ENEMY_DIRECTION_SCALE_LOG,
    ENEMY_SHOOT_BASE,
    ENEMY_SHOOT_SCALE_LOG,
    SPARK_PARTICLE_SPEED_MAX,
    SPARK_COUNT_ENEMY_HIT,
    SPARK_COUNT_PROJECTILE,
    AIR_TIME_FATAL,
)


class PhysicsEntity:
    def __init__(self, game, e_type, pos, size, id):
        self.game = game
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
                self.animation = self.game.assets[
                    self.type + "/" + cm.SKIN_PATHS[self.skin] + "/" + self.action
                ].copy()

    def update(self, tilemap, movement=(0, 0)):
        self.collisions = {"up": False, "down": False, "right": False, "left": False}

        frame_movement = (
            movement[0] + self.velocity[0],
            movement[1] + self.velocity[1],
        )

        self.pos[0] += frame_movement[0]
        entity_rect = self.rect()
        for rect in tilemap.physics_rects_around(self.pos):
            if entity_rect.colliderect(rect):
                if frame_movement[0] > 0:
                    entity_rect.right = rect.left
                    self.collisions["right"] = True
                if frame_movement[0] < 0:
                    entity_rect.left = rect.right
                    self.collisions["left"] = True
                self.pos[0] = entity_rect.x

        self.pos[1] += frame_movement[1]
        entity_rect = self.rect()
        for rect in tilemap.physics_rects_around(self.pos):
            if entity_rect.colliderect(rect):
                if frame_movement[1] > 0:
                    entity_rect.bottom = rect.top
                    self.collisions["down"] = True
                if frame_movement[1] < 0:
                    entity_rect.top = rect.bottom
                    self.collisions["up"] = True
                self.pos[1] = entity_rect.y

        if movement[0] > 0:
            self.flip = False
        if movement[0] < 0:
            self.flip = True

        self.last_movement = movement

        # Gravity & vertical collision resolution
        self.velocity[1] = min(MAX_FALL_SPEED, self.velocity[1] + GRAVITY_ACCEL)
        if self.collisions["down"] or self.collisions["up"]:
            self.velocity[1] = 0

        self.animation.update()

    def render(self, surf, offset=(0, 0)):
        surf.blit(
            pygame.transform.flip(self.animation.img(), self.flip, False),
            (
                self.pos[0] - offset[0] + self.anim_offset[0],
                self.pos[1] - offset[1] + self.anim_offset[1],
            ),
        )


class Enemy(PhysicsEntity):
    def __init__(self, game, pos, size=(15, 8), id=0):
        super().__init__(game, "enemy", pos, size, id)
        self.walking = 0

    def update(self, tilemap, movement=(0, 0)):
        if self.walking:
            if tilemap.solid_check(
                (self.rect().centerx + (-7 if self.flip else 7), self.pos[1] + 23)
            ):
                if self.collisions["right"] or self.collisions["left"]:
                    self.flip = not self.flip
                else:
                    direction = ENEMY_DIRECTION_BASE * (
                        1
                        + ENEMY_DIRECTION_SCALE_LOG
                        * math.log(settings.selected_level + 1)
                    )
                    movement = (
                        movement[0] - direction if self.flip else direction,
                        movement[1],
                    )
            else:
                self.flip = not self.flip
            self.walking = max(0, self.walking - 1)
            if not self.walking:
                dis = (
                    self.game.player.pos[0] - self.pos[0],
                    self.game.player.pos[1] - self.pos[1],
                )
                if abs(dis[1]) < 15:
                    if self.flip and dis[0] < 0:
                        self.game.sfx["shoot"].play()
                        direction = -ENEMY_SHOOT_BASE * (
                            1
                            + ENEMY_SHOOT_SCALE_LOG
                            * math.log(settings.selected_level + 1)
                        )
                        self.game.projectiles.append(
                            [
                                [self.rect().centerx - 15, self.rect().centery],
                                direction,
                                0,
                            ]
                        )
                        spawn_projectile_sparks(
                            self.game, self.game.projectiles[-1][0], direction
                        )

                    if not self.flip and dis[0] > 0:
                        self.game.sfx["shoot"].play()
                        direction = ENEMY_SHOOT_BASE * (
                            1
                            + ENEMY_SHOOT_SCALE_LOG
                            * math.log(settings.selected_level + 1)
                        )
                        self.game.projectiles.append(
                            [
                                [self.rect().centerx + 15, self.rect().centery],
                                direction,
                                0,
                            ]
                        )
                        spawn_projectile_sparks(
                            self.game, self.game.projectiles[-1][0], direction
                        )
        elif random.random() < 0.01:
            self.walking = random.randint(30, 120)

        super().update(tilemap, movement=movement)
        if movement[0] != 0:
            self.set_action("run")
        else:
            self.set_action("idle")

        # Dash kill & projectile collision checks
        if abs(self.game.player.dashing) >= DASH_MIN_ACTIVE_ABS:
            if self.rect().colliderect(self.game.player.rect()):
                self.game.screenshake = max(16, self.game.screenshake)
                self.game.sfx["hit"].play()
                self.game.cm.coins += 1
                spawn_hit_sparks(self.game, self.rect().center)
                self.game.sparks.append(
                    Spark(self.rect().center, 0, 5 + random.random())
                )
                self.game.sparks.append(
                    Spark(self.rect().center, math.pi, 5 + random.random())
                )
                return True

        rect = pygame.Rect(self.pos[0], self.pos[1], self.size[0], self.size[1])
        for projectile in self.game.projectiles.copy():
            projectile_rect = pygame.Rect(projectile[0][0], projectile[0][1], 4, 4)
            if rect.colliderect(projectile_rect):
                self.game.projectiles.remove(projectile)
                self.game.screenshake = max(16, self.game.screenshake)
                self.game.sfx["hit"].play()
                self.game.cm.coins += 1
                spawn_hit_sparks(self.game, self.rect().center)
                return True

    def render(self, surf, offset=(0, 0)):
        super().render(surf, offset=offset)

        if self.flip:
            surf.blit(
                pygame.transform.flip(self.game.assets["gun"], True, False),
                (
                    self.rect().centerx
                    - 4
                    - self.game.assets["gun"].get_width()
                    - offset[0],
                    self.rect().centery - offset[1],
                ),
            )
        else:
            surf.blit(
                self.game.assets["gun"],
                (self.rect().centerx + 4 - offset[0], self.rect().centery - offset[1]),
            )


class Player(PhysicsEntity):
    def __init__(self, game, pos, size, id, lifes, respawn_pos):
        """Player entity.

        Parameter 'lifes' kept for backward compatibility with existing code &
        serialized saves. Internally we migrate to the proper English term
        'lives'. Access via self.lives; legacy attribute 'lifes' provided as
        property alias for old references until fully refactored.
        """
        self.skin = 0
        super().__init__(game, "player", pos, size, id)
        self.air_time = 0
        self.jumps = 1
        self.wall_slide = False
        self.dashing = 0
        # Store canonical field _lives and expose property alias.
        self._lives = lifes
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
        if (
            self.game.cm.gun
            and self.game.cm.ammo > 0
            and self.shoot_cooldown == 0
            and settings.selected_weapon == 1
        ):
            self.game.sfx["shoot"].play()
            direction = -PROJECTILE_SPEED if self.flip else PROJECTILE_SPEED
            self.game.projectiles.append(
                [
                    [
                        self.rect().centerx + (7 * (-1 if self.flip else 1)),
                        self.rect().centery,
                    ],
                    direction,
                    0,
                ]
            )
            self.game.cm.ammo -= 1
            self.shoot_cooldown = 10

            spawn_projectile_sparks(self.game, self.game.projectiles[-1][0], direction)

    def update(self, tilemap, movement=(0, 0)):
        super().update(tilemap, movement=movement)
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
                angle = random.random() * math.pi * 2
                speed = random.random() * 0.5 + 0.5
                pvelocity = [math.cos(angle) * speed, math.sin(angle) * speed]
                self.game.particles.append(
                    Particle(
                        self.game,
                        "particle",
                        self.rect().center,
                        velocity=pvelocity,
                        frame=random.randint(0, 7),
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
                abs(self.dashing)
                / self.dashing
                * random.random()
                * DASH_TRAIL_PARTICLE_SPEED,
                0,
            ]
            self.game.particles.append(
                Particle(
                    self.game,
                    "particle",
                    self.rect().center,
                    velocity=pvelocity,
                    frame=random.randint(0, 7),
                )
            )

        if self.velocity[0] > 0:
            self.velocity[0] = max(self.velocity[0] - HORIZONTAL_FRICTION, 0)
        else:
            self.velocity[0] = min(self.velocity[0] + HORIZONTAL_FRICTION, 0)

    def render(self, surf, offset=(0, 0)):
        if abs(self.dashing) <= DASH_MIN_ACTIVE_ABS:
            super().render(surf, offset=offset)

        if self.game.cm.gun and settings.selected_weapon == 1:
            if self.flip:
                surf.blit(
                    pygame.transform.flip(self.game.assets["gun"], True, False),
                    (
                        self.rect().centerx
                        - 4
                        - self.game.assets["gun"].get_width()
                        - offset[0],
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
            self.game.sfx["dash"].play()
            if self.flip:
                self.dashing = -DASH_DURATION_FRAMES
            else:
                self.dashing = DASH_DURATION_FRAMES
