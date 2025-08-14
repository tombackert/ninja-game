"""Gameplay and tuning constants.

Centralizes numeric tuning values to eliminate magic numbers and enable
consistent adjustments. Part of Issue 3 (Introduce constants module).
"""

# Physics / Movement
GRAVITY_ACCEL = 0.1  # acceleration per frame (positive down)
MAX_FALL_SPEED = 5  # vertical velocity clamp
HORIZONTAL_FRICTION = 0.1  # velocity reduction per frame when no input
WALL_SLIDE_MAX_SPEED = 0.5  # downward velocity cap when wall sliding
JUMP_VELOCITY = -3  # initial Y velocity for a jump
WALL_JUMP_HORIZONTAL_VEL = 3.5  # horizontal push from wall jump
WALL_JUMP_VERTICAL_VEL = -2.5  # vertical component of wall jump

# Dash
DASH_DURATION_FRAMES = 60  # total dash frames magnitude (positive or negative)
DASH_DECEL_TRIGGER_FRAME = 51  # frame at which abrupt slow-down occurs
DASH_MIN_ACTIVE_ABS = 50  # absolute value threshold to consider in dash effects
DASH_SPEED = 8  # horizontal speed during primary dash frames
DASH_TRAIL_PARTICLE_SPEED = 3  # particle horizontal speed factor

# Combat / Shooting
PROJECTILE_SPEED = 3.5  # base projectile horizontal speed
ENEMY_SHOOT_BASE = 1.15  # base enemy projectile speed factor
ENEMY_DIRECTION_BASE = 0.35  # base enemy walking direction magnitude
ENEMY_DIRECTION_SCALE_LOG = 0.8  # scale for log(level+1) when walking
ENEMY_SHOOT_SCALE_LOG = 0.59  # scale for log(level+1) when shooting
SPARK_PARTICLE_SPEED_MAX = 5  # random() * this for spark speed
SPARK_COUNT_ENEMY_HIT = 30  # sparks spawned when enemy killed or hit
SPARK_COUNT_DASH_COLLIDE = 30  # sparks spawned when dash collision occurs
SPARK_COUNT_PROJECTILE = 4  # sparks spawned on projectile spawn or impact

# Timers / Transitions
RESPAWN_DEAD_THRESHOLD = 40  # frames until respawn when dead animation
TRANSITION_MAX = 30  # max positive transition value
TRANSITION_START = -30  # starting negative transition value
AIR_TIME_FATAL = 420  # frames in air before considered 'dead'

# Misc
LEAF_SPAWNER_CLOUD_COUNT = 16  # number of clouds
SAVE_DEFAULT_LIVES = 3

__all__ = [name for name in globals().keys() if name.isupper()]
