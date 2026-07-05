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
PROJECTILE_LIFETIME_FRAMES = 360  # frames before projectile expires (legacy hardcoded value)
GUN_COOLDOWN_FRAMES = 10  # frames between gun shots

# Rifle (store item): fast bullet, expensive per shot
RIFLE_PROJECTILE_SPEED = 6.5  # rifle bullet speed
RIFLE_COOLDOWN_FRAMES = 25  # frames between rifle shots
RIFLE_AMMO_COST = 2  # ammo consumed per rifle shot

# Ninja stars (store item): arcing, piercing, consumable
STAR_SPEED_X = 3.0  # shuriken horizontal speed
STAR_SPEED_Y = -1.5  # shuriken initial vertical (upward) speed
STAR_GRAVITY = 0.08  # shuriken gravity per frame (lighter than player gravity)
STAR_COOLDOWN_FRAMES = 15  # frames between star throws

# Sword (store item): melee slash, no ammo
SWORD_COOLDOWN_FRAMES = 18  # frames between sword swings
SWORD_REACH = 22  # slash hitbox width in facing direction
SWORD_HITBOX_HEIGHT = 18  # slash hitbox height (centered on player)
SWORD_SLASH_VFX_FRAMES = 6  # frames the slash effect is rendered

# Grapple hook (store item): pure mobility
GRAPPLE_RANGE = 140  # max hook distance in px
GRAPPLE_RAY_STEP = 4  # ray sampling step (< tile size 16, cannot skip tiles)
GRAPPLE_PULL_SPEED = 4.0  # player pull speed toward anchor
GRAPPLE_COOLDOWN_FRAMES = 45  # frames between grapple shots
GRAPPLE_WHIFF_COOLDOWN_FRAMES = 15  # shorter cooldown when hook misses
GRAPPLE_MAX_FRAMES = 60  # safety timeout for a pull
GRAPPLE_ARRIVE_DIST = 6  # release distance to anchor

# Gear (passive items)
SHIELD_REARM_FRAMES = 600  # ~10 s until next shield charge arms
AIR_JUMP_VELOCITY = -2.7  # moon boots double jump (weaker than ground jump)
MAGNET_RADIUS = 48  # coin magnet attraction radius
MAGNET_PULL_SPEED = 1.8  # coin movement toward player per frame
ENEMY_SHOOT_BASE = 1.15  # base enemy projectile speed factor
ENEMY_DIRECTION_BASE = 0.35  # base enemy walking direction magnitude
ENEMY_DIRECTION_SCALE_LOG = 0.8  # scale for log(level+1) when walking
ENEMY_SHOOT_SCALE_LOG = 0.59  # scale for log(level+1) when shooting
SPARK_PARTICLE_SPEED_MAX = 5  # random() * this for spark speed
SPARK_COUNT_ENEMY_HIT = 30  # sparks spawned when enemy killed or hit
SPARK_COUNT_DASH_COLLIDE = 30  # sparks spawned when dash collision occurs
SPARK_COUNT_PROJECTILE = 4  # sparks spawned on projectile spawn or impact

# Timers / Transitions
DEAD_ANIM_FADE_START = 10  # frame at which transition fade begins after death
RESPAWN_DEAD_THRESHOLD = 40  # frames until respawn when dead animation
TRANSITION_MAX = 30  # max positive transition value
TRANSITION_START = -30  # starting negative transition value
AIR_TIME_FATAL = 420  # frames in air before considered 'dead'

# Misc
LEAF_SPAWNER_CLOUD_COUNT = 16  # number of clouds (also used for initial cloud count)
SAVE_DEFAULT_LIVES = 3

__all__ = [name for name in globals().keys() if name.isupper()]
