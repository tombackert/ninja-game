# Architecture Specification

**Status Date:** 2026-01-19
**Version:** 3.0 (Post v3.0 Polish & Core Experience)

This document describes the current architecture of the Ninja Game, reflecting the completion of the v2.0 refactoring roadmap and the v3.0 polish update. The system is designed for determinism, extensibility, and future multiplayer/RL integration.

---
## 1. Goals (Achieved)

### v2.0 Core Architecture
- **Separation of Concerns:** Clear split between Simulation (Domain), Presentation (Renderer/UI), and Infrastructure (Input/Assets).
- **Determinism:** Fixed-step simulation with centralized RNG and input-driven updates, enabling reliable replays and rollback.
- **Extensibility:** Service-oriented design (ServiceContainer) and modular AI (Policy) allow adding features without invasive coupling.
- **Performance:** Optimized snapshotting (LITE mode), efficient interpolation, and batched headless simulation support.

### v3.0 Polish & Core Experience
- **Game Feel:** Fixed pause state, respawn determinism, smoother level transitions, ghost polish.
- **AI Extensibility:** Validated with new Chaser and Jumper behaviors.
- **Audio:** Per-level soundtracks, standardized SFX, audio ducking support.
- **Input:** Configurable key bindings (backend ready, loads from settings.json).
- **Localization:** i18n foundation with externalized strings.

---
## 2. High-Level Component Overview
```
GameApp (app.py)
 ├─ StateManager
 │   ├─ MenuState / LevelsState / StoreState ...
 │   ├─ GameState (The primary simulation container)
 │   └─ PauseState
 ├─ Core Systems
 │   ├─ InputRouter (Events -> Actions)
 │   ├─ AssetManager (Lazy loading, caching)
 │   ├─ AudioService (Volume control, wrapper)
 │   ├─ RNGService (Seeded, deterministic random)
 │   └─ Settings (Persistence)
 ├─ Simulation Layer (Deterministic)
 │   ├─ Game (Context object)
 │   ├─ Entities (Player, Enemy, PhysicsEntity)
 │   ├─ ProjectileSystem
 │   ├─ ParticleSystem
 │   ├─ Tilemap / Level
 │   └─ AI Policy Service (Modular behaviors)
 ├─ Replay & Networking Layer
 │   ├─ SnapshotService (Capture/Restore full state)
 │   ├─ ReplayManager (Recording, Ghost Re-simulation)
 │   ├─ Interpolation (SnapshotBuffer, Entity smoothing)
 │   └─ DeltaCompression (Bandwidth optimization)
 ├─ RL / Training Layer
 │   ├─ TrainingEnv (Gym-like API)
 │   ├─ BatchSimulation (Multiprocessing harness)
 │   ├─ FeatureExtractor (Observation builder)
 │   └─ RewardShaper
 └─ Presentation Layer
     ├─ Renderer (Unified frame composition)
     ├─ UI / Widgets
     └─ PerformanceHUD (Metrics, Overlay)
```

---
## 3. Core Architecture Pattern
The game uses a **State Pattern** via `StateManager`. The active state controls the update loop.
- **Update (Simulation):** `GameState.update(dt)` advances the logic. It relies on `InputRouter` to convert raw inputs into semantic actions (`jump`, `dash`) which are fed into entities.
- **Render (Presentation):** `GameState.render(surface)` delegates to the `Renderer`, which composes the scene (Background -> World -> Ghosts -> UI -> Effects).

---
## 4. Determinism & Replay System
A critical pillar of the architecture is **Determinism**, enabling Ghosts, Replays, and future Rollback Netcode.

### 4.1 Global Tick Counter
`game.tick`: A global simulation frame counter critical for multiplayer synchronization.
- **Initialization:** Starts at 0 when Game is created.
- **Increment:** Incremented exactly once per `GameState.update()` call.
- **Pause Behavior:** Does NOT increment when game is paused (`_paused_freeze` flag).
- **Snapshots:** Captured and restored via `SnapshotService`.
- **Usage:** Network messages, replay timestamps, reconciliation all reference this tick.

### 4.2 RNG Service
`scripts/rng_service.py`: A singleton wrapper around `random.Random`. All gameplay logic (enemy decisions, particle spreads, procedural generation) uses this service. The RNG state is serialized in snapshots to ensure perfectly reproducible runs.

### 4.3 Snapshots
`scripts/snapshot.py`: Captures the complete state of the simulation (Tick, RNG, Players, Enemies, Projectiles, Score).
- **Serialization:** `dataclass` based structure serialized to JSON compatible dicts.
- **Optimization:** Supports `optimized=True` (LITE mode) which strips enemies/projectiles for lightweight Ghost recordings (99% size reduction).

### 4.4 Replay & Ghost System
`scripts/replay.py`:
- **Recording:** Captures a stream of **Inputs** (per frame) and **Sparse Snapshots** (every 10 frames / 6Hz).
- **Playback (Ghost):** Instead of playing back a video of positions, the system **re-simulates** a `GhostPlayer` entity by feeding it the recorded inputs.
- **Drift Correction:** To prevent divergence (butterfly effect), the Ghost's state is hard-synced to the recorded snapshots at 6Hz intervals. This ensures smooth movement (via local physics) with absolute correctness (via snapshots).

### 4.5 Entity ID System
`scripts/entity_id.py`: Centralized, deterministic unique ID generation for all game entities.

**EntityIDGenerator (Singleton):**
- **Global Uniqueness:** All entities (players, enemies, projectiles) receive globally unique IDs from the same generator.
- **Determinism:** Generator can be reset at level load to ensure identical ID sequences across clients.
- **Serialization:** State (`get_state()`, `set_state()`) enables snapshot/restore for network sync.

**Entity ID Fields:**
- `EntitySnapshot.id`: Unique entity identifier.
- `EntitySnapshot.owner_id`: Player ID who controls this entity (for multiplayer authority).
- `ProjectileSnapshot.id`: Unique projectile identifier.
- `ProjectileSnapshot.owner_id`: Player ID who fired the projectile.

**Delta Compression (ID-Based):**
The delta system uses ID-based matching instead of index-based:
- `*_added`: Full data for new entities.
- `*_removed`: IDs of deleted entities.
- `*_diff`: Changed fields keyed by entity ID.

This allows proper delta compression even when entities are reordered or dynamically added/removed in multiplayer.

---
## 5. AI & Behavior
AI logic is decoupled from Entity classes using a **Strategy Pattern**.
- **Policy Interface:** `scripts/ai/core.py`. Defines `decide(entity, context) -> intentions`.
- **Enemy kinds** (`scripts/enemy_kinds.py`): each kind has fixed numbers (speed, bullet speed, sight, fire period, hurts on touch) and a behavior in `scripts/ai/behaviors.py`. The map stores the kind as the enemy spawner's variant, so the editor places a kind by its spawner image and old maps (variant 1) keep the gunner.
    - `gunner` (1, red): wanders, stops, fires along its line of sight (range: just past the frame edge).
    - `patrol` (2, amber): walks its platform edge to edge without a pause; no gun, hurts on touch.
    - `turret` (3, steel): stands, turns to the player, fires on a fixed beat after a wind-up.
    - `chaser` (4, purple): wakes when the player comes near and runs at them; stops at edges; hurts on touch.
    - `jumper` (5, green): hops along its platform; hurts on touch, so it cannot simply be jumped over.
    - `thrower` (6, teal): paces 2.5 tiles to either side of its spawn and throws ninja stars in an arc aimed at the player (only when the arc reaches them), on a fixed beat; a ledge is no cover.
    - Walkers turn at walls, edges, spikes and flame jets' reach. An armed enemy holds its fire while one close by just fired (cluster rule).
- **Integration:** `Enemy(kind=...)` picks the kind's policy, its own character art (`entities/enemy/<kind>/`, made by `tools/gen_enemy_art.py`: ashigaru spearman, sentry automaton, oni, frog ninja, hooded star thrower; the gunner is the original ninja) and numbers. `Enemy.update` shows `run` while moving, `shoot` for `SHOT_POSE_FRAMES` after firing (turret recoil, the thrower's throw), `alert` while awake and standing still (turret lens charging, oni snarling) and `idle` otherwise; a kind without one of these animations shows its idle (`Enemy.set_action`). The jumper's `run` is one hop timed to its air time and plays once; its idle is timed to its stay on the ground. `Enemy.update` delegates decision making to the policy.
- **Difficulty:** no scaling with the level number. A level's difficulty comes from its cast: which kinds stand where (`tools/worlds/roster.py` introduces the kinds over the campaign and fills in spawners a level script leaves open). Every hit costs a life without a respawn: a bullet, a thrown star, touching a patrol, chaser or jumper, spikes or a flame (`Player.take_hit`). The player is thrown back from a touch and blinks for `HIT_INVULNERABLE_FRAMES` (1.5 s), during which nothing hits them; an armed shield takes the hit instead. Only falls and drowning are deaths (respawn at the last banner). Two ways kill any kind: a dash through it, or landing on it from above (`Player.stomp`), which bounces the player up a little (`STOMP_BOUNCE_VELOCITY`, lower than a jump). A stomp comes before the touch check, so landing on a patrol, chaser or jumper does not hurt; walking or jumping up into one does. The multiplayer client only predicts the bounce (`game.predicting`) and the server makes the kill and credits the coin.
- **Hazards** (`scripts/hazards.py`, `HazardSystem` built per level load): spikes (hurt, not solid), crumbling blocks (fall `CRUMBLE_DELAY` frames after a step, come back later) and flame jets (burn on a beat: `period`, `on`, `phase` tile fields). Their clock counts ticks since the level was (re)loaded, so every attempt starts on the same beat. The route planner sees spikes; `tools/worlds/hazard_check.py` checks a planned route against flames and crumbling blocks.

---
## 6. Audio System
`scripts/audio_service.py`: Centralized audio management.
- **Singleton Pattern:** `AudioService.get()` for global access.
- **Volume Management:** Synced with `settings.json` (music_volume, sound_volume).
- **Per-Sound Scaling:** Individual volume multipliers (e.g., ambience=0.2, hit=0.8).
- **Audio Ducking:** Temporary music volume reduction during sound effects.
- **Headless Fallback:** Null audio driver for CI environments.
- **Pre-registered Sounds:** jump, dash, hit, shoot, ambience, collect.

---
## 7. Localization (i18n)
`scripts/localization.py`: Foundation for translation support.
- **String Externalization:** UI strings moved from hardcoded values to dictionary/JSON.
- **Locale Switching:** Prepared for future language selection.
- **Usage:** `get_string(key)` retrieves localized text.

---
## 8. Networking & RL Infrastructure
The codebase contains a complete foundation for Multiplayer and Reinforcement Learning.

### 8.1 Reinforcement Learning (RL)
- **TrainingEnv:** `scripts/training_env.py` exposes a `reset()` / `step(action)` interface compatible with RL standards. It manages its own headless `Game` instance.
- **Adapters:** `scripts/training_adapter.py` provides wrappers for **Ray RLLib** and **Stable Baselines**.
- **Batch Simulation:** `scripts/batch_sim.py` allows running N environments in parallel processes for high-throughput data collection.

### 8.2 Networking Primitives
- **Interpolation:** `scripts/network/interpolation.py` implements a `SnapshotBuffer` that smoothly interpolates entity positions/velocities between server snapshots for remote rendering.
- **Delta Compression:** `scripts/network/delta.py` computes diffs between snapshots (`compute_delta`, `apply_delta`) using ID-based entity matching to minimize bandwidth.

### 8.3 UDP Transport Layer
`scripts/network/udp_transport.py`: Real network communication for multiplayer.

**UDPTransport Class:**
- Non-blocking UDP socket operations
- Packet sequencing with monotonically increasing sequence numbers
- Ack tracking with 32-bit bitfield for reliability detection
- Graceful handling of malformed packets
- Context manager support for automatic cleanup

**Packet Structure:**
```python
Packet:
  header:
    sequence: int      # Packet sequence number
    ack: int           # Last received sequence from peer
    ack_bitfield: int  # Bitfield of 32 recent acks
  message:
    type: str          # Message type (input, snapshot, ack)
    payload: dict      # Message-specific data
```

**Convenience Classes:**
- `UDPClient`: Client-side wrapper with default server address
- `UDPServer`: Server-side wrapper with client tracking and broadcast

**NetSyncService:**
`scripts/network/netsync_service.py`: High-level API for game networking.
- `send_input(tick, inputs)` - Send player inputs
- `send_snapshot(tick, snapshot_data)` - Send game state
- `send_ack(tick)` - Acknowledge received data
- `process_messages() -> List[Tuple[Message, Address]]` - Receive pending messages with sender addresses (uniform return type for all transports)
- Works with both `LocalLoopbackTransport` (testing) and `UDPTransport` (real network)
- `LOOPBACK_ADDRESS = ("127.0.0.1", 0)` sentinel used as default address for loopback transport

---
## 9. Rendering Pipeline
The `Renderer` (`scripts/renderer.py`) ensures consistent draw order:
1.  **Clear:** Wipe buffer.
2.  **Background:** Parallax layers.
3.  **Ghosts:** Rendered via `ReplayManager` (tinted, semi-transparent).
4.  **World:** Tilemap, Entities, Particles (via UI helper). On water levels the water is drawn as one body (one smooth gradient by depth for the whole level): the sea and the air pockets' back walls behind the tiles first, the pockets' rounded rock right after the tiles (so it gets their outline), and a light tint, the wave crest, the drifting current streaks and breath meters over them last.
5.  **Effects (Pre):** Transitions.
6.  **HUD:** UI overlays.
7.  **PerfOverlay:** Optional debug metrics (F1).
8.  **Effects (Post):** Screenshake.
9.  **Present:** Blit to window.

---
## 10. Directory Structure
```
ninja-game/
├── app.py                    # Main entry point (StateManager-based)
├── game.py                   # Game class: world state and simulation step
├── editor.py                 # Level editor tool
├── scripts/                  # Core game logic (~52 files)
│   ├── entities.py           # Player, Enemy, PhysicsEntity
│   ├── state_manager.py      # State pattern implementation
│   ├── input_router.py       # Event → Action mapping
│   ├── renderer.py           # Unified rendering pipeline
│   ├── audio_service.py      # Audio abstraction
│   ├── asset_manager.py      # Image/animation/sound caching
│   ├── settings.py           # Persistent settings & key bindings
│   ├── services.py           # Service container (DI)
│   ├── tilemap.py            # Level/tile management
│   ├── ui.py                 # UI rendering & caching
│   ├── ui_widgets.py         # Menu widgets
│   ├── timer.py              # Level timer & best times
│   ├── localization.py       # i18n support
│   ├── projectile_system.py  # Centralized projectile logic
│   ├── particle_system.py    # Particle & spark management
│   ├── replay.py             # Ghost/replay recording
│   ├── snapshot.py           # Game state serialization
│   ├── rng_service.py        # Deterministic RNG
│   ├── perf_hud.py           # Performance metrics overlay
│   ├── constants.py          # Physics & tuning constants
│   ├── ai/                   # AI policy implementations
│   │   ├── core.py           # Policy base & registry
│   │   └── behaviors.py      # Enemy behaviors
│   ├── network/              # Networking infrastructure
│   │   ├── interpolation.py  # Entity smoothing
│   │   ├── delta.py          # Delta compression
│   │   └── netsync_service.py
│   └── weapons/              # Weapon system
│       ├── base.py
│       ├── gun.py
│       └── registry.py
├── data/                     # Assets & configuration
│   ├── images/               # Sprites & backgrounds
│   ├── sfx/                  # Sound effects
│   ├── music/                # Background music
│   ├── maps/                 # Level JSON files
│   ├── replays/              # Ghost data
│   └── settings.json         # User settings
├── tests/                    # Pytest suite (~44 test files)
├── experiments/              # Benchmarks & prototypes
├── tools/                    # Utility scripts
└── docs/                     # Architecture & patch notes
```

---
## 11. Future Directions (Backlog)

### High Priority
- **Multiplayer:** Implement `Transport` layer (UDP) and `NetSyncService` using the existing Snapshot/Delta infrastructure.
- **Key Bindings UI:** Build settings menu for custom key remapping (backend ready).
- **Game Over Screen:** Add dedicated screen for player defeat.

### Medium Priority
- **Performance HUD Full Coverage:** Complete test coverage for metrics display.
- **Map Hot Reload:** Live level editing without restart.
- **Tutorial Mode:** In-game onboarding for new players.

### Infrastructure
- **Post-processing Pipeline:** Screen effects (bloom, vignette).
- **Profiling Tool Panel:** In-game performance analysis.
- **Full Localization:** Complete translation support with language selection UI.

---
## 12. Performance Notes
- **Snapshots:** LITE mode takes ~0.01ms per capture.
- **Interpolation:** ~1.87µs per entity.
- **Batch Sim:** Scaling limited by process startup cost on short runs; efficient for long training sessions.
- **Asset Loading:** Lazy loading with LRU caching (images: 64 entries, text: 256 entries).
- **Performance HUD:** Throttled refresh (every 10 frames) to minimize overhead.

---
## 13. Service Container & Dependency Injection
`scripts/services.py`: Protocol-based service interfaces for decoupling.

**Service Ports (Protocols):**
- `AudioPort`: `play(name, loops)` - Sound playback abstraction.
- `ProjectilePort`: `spawn(x, y, vx, owner)` - Projectile creation.
- `ParticlePort`: `spawn_particle()`, `spawn_spark()` - Visual effects.
- `CollectablePort`: coins, ammo, gun properties - Game state access.

**ServiceContainer Dataclass:**
```python
@dataclass
class ServiceContainer:
    audio: AudioPort
    projectiles: ProjectilePort
    particles: ParticlePort | None
    collectables: CollectablePort
```

**Benefit:** Entities depend on narrow interfaces, not the entire Game object, improving testability and reducing coupling.

---
## 14. Physics & Entity System
`scripts/entities.py`: Core gameplay entities with granular physics.

### PhysicsEntity Base Class
**Granular Physics Steps (for determinism):**
1. `begin_update()` - Reset collision flags; `update()` then reads the water at the start position (`water_flow`).
2. `compute_frame_movement(movement)` - Calculate next position (in water: slower, plus the current's push).
3. `apply_horizontal_movement(tilemap, frame_movement)` - X-axis collision.
4. `apply_vertical_movement(tilemap, frame_movement)` - Y-axis collision.
5. `update_orientation(movement)` - Face direction.
6. `apply_gravity()` - Gravity acceleration & velocity clamp (in water: drag and a slow sink).
7. `finalize_update()` - Animation advance.

### Player Abilities
- **Jump:** Double-jump support (configurable via `jumps` counter).
- **Wall-slide:** Reduced fall speed when sliding on walls.
- **Dash:** Burst movement with deceleration and invulnerability frames.
- **Shoot:** Projectile spawning with cooldown.
- **Swim (water world):** Under water a jump is a swim stroke (with a cooldown), at the surface a leap out. No fall death in water, but `breath` runs down while the eyes are under water and drowning costs the same respawn as a fall.
- **Fall death:** A fall ends at the level's kill line (`Tilemap.kill_line`: `FALL_KILL_DEPTH` tiles under its lowest solid tile, below which nothing can catch the player), at the latest after `AIR_TIME_FATAL` frames in the air. Single player, the multiplayer server and the physics replica (`tools/worlds/physics.py`, `Terrain.kill_y`) all use it.

### Checkpoints (`scripts/checkpoints.py`)
Checkpoint banners are tiles of type `checkpoint` (grid or offgrid; the level builder places them offgrid with `Level.checkpoint`), drawn 16x32 from their position down. Touching one for the first time hoists it (variant 0 furled, 1 hoisted) and moves that player's respawn point to its foot, so a death sends the player back there instead of to the spawn. The banner's state lives in the tilemap's tile: it survives a respawn (which keeps the tiles) and is furled again when the level is loaded anew (game over). Each player keeps the checkpoints they reached, so on the multiplayer server everyone respawns at their own. The manual checkpoint (P, once per level) still works on top. Levels put one banner halfway, where every route passes (Super Mario style; a world's finale may take a second): `tools.worlds.assess --playtime` shows that the first banner takes almost all the frustration out of a hard level, more of them mostly take the tension out.

### Water Layer (`scripts/water.py`)
Water is a layer of its own beside the tile grid (`Tilemap.water`, `{(tx, ty): flow}`), so coins, enemies and decor can sit in it; maps store it as runs `[ty, tx0, tx1, flow]` under `map_data.water`. A flow is still water (0) or a current to the right, left, up or down (1-4, `WATER_CURRENTS`). Water is held like real water: rock or more water beside and under every water tile, so air only sits over water, as its surface or trapped under rock (`water_leaks`; the world builder refuses a level that breaks this and a test checks every map). Everything in water moves at `WATER_MOVE_SCALE`, and a current pushes it every frame. Dry levels take none of the water branches, so their physics is unchanged (`tools/worlds/check_physics.py` compares the real game with an exact replica frame by frame).

### Physics Constants (`scripts/constants.py`)
- `GRAVITY_ACCEL = 0.1`
- `MAX_FALL_SPEED = 5`
- `JUMP_VELOCITY = -3`
- `WALL_SLIDE_MAX_SPEED = 0.5`
- `DASH_DURATION_FRAMES = 60`
- `DASH_SPEED = 8`
- `PROJECTILE_SPEED = 3.5`
- `WATER_GRAVITY = 0.05`, `WATER_DRAG = 0.94`, `WATER_MAX_SINK = 1.5`
- `SWIM_STROKE_VELOCITY = -2.0`, `SWIM_STROKE_COOLDOWN = 12`
- `BREATH_FRAMES = 720`

---
## 15. UI & Widget System
`scripts/ui.py`, `scripts/ui_widgets.py`: Presentation layer utilities.

### Caching Systems
- **Image Cache:** LRU with 64 entries.
- **Text Cache:** LRU with 256 entries (pre-rendered with outlines).
- **Performance Overlay:** Throttled rebuild every 10 frames.

### UI Widgets
- **ScrollableListWidget:** Menu navigation with visible row limits.

### Rendering Functions
- `render_game_elements()` - Tiles, entities, projectiles, particles.
- `render_game_ui_element()` - HUD (timer, level, lives, coins, ammo).
- `render_perf_overlay()` - Performance metrics display.

---
## 16. Timer & Progress System
`scripts/timer.py`, `scripts/progress_tracker.py`: Level timing and progression.

### Timer
- Tracks level completion time.
- Stores best times in `data/best_times.json`.
- Rendered in HUD during gameplay.

### Progress Tracker
- Manages level unlock status.
- Persists progress to `data/settings.json`.

---
## 17. Weapon System
`scripts/weapons/`: Extensible weapon architecture.

- **base.py:** Abstract weapon classes and interfaces.
- **gun.py:** Gun weapon implementation (projectile-based).
- **registry.py:** Weapon registration and lookup.

**Design:** Strategy pattern allows adding new weapon types without modifying entity code.

End of specification.
