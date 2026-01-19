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

### 4.1 RNG Service
`scripts/rng_service.py`: A singleton wrapper around `random.Random`. All gameplay logic (enemy decisions, particle spreads, procedural generation) uses this service. The RNG state is serialized in snapshots to ensure perfectly reproducible runs.

### 4.2 Snapshots
`scripts/snapshot.py`: Captures the complete state of the simulation (Tick, RNG, Players, Enemies, Projectiles, Score).
- **Serialization:** `dataclass` based structure serialized to JSON compatible dicts.
- **Optimization:** Supports `optimized=True` (LITE mode) which strips enemies/projectiles for lightweight Ghost recordings (99% size reduction).

### 4.3 Replay & Ghost System
`scripts/replay.py`:
- **Recording:** Captures a stream of **Inputs** (per frame) and **Sparse Snapshots** (every 10 frames / 6Hz).
- **Playback (Ghost):** Instead of playing back a video of positions, the system **re-simulates** a `GhostPlayer` entity by feeding it the recorded inputs.
- **Drift Correction:** To prevent divergence (butterfly effect), the Ghost's state is hard-synced to the recorded snapshots at 6Hz intervals. This ensures smooth movement (via local physics) with absolute correctness (via snapshots).

---
## 5. AI & Behavior
AI logic is decoupled from Entity classes using a **Strategy Pattern**.
- **Policy Interface:** `scripts/ai/core.py`. Defines `decide(entity, context) -> intentions`.
- **Behaviors:**
    - `ScriptedEnemy`: Legacy random walk + shoot.
    - `Patrol`: Back-and-forth movement, no shooting.
    - `Shooter`: Stationary tracking turret, shoots when player aligned.
    - `Chaser`: Actively pursues player within territory, jumps obstacles.
    - `Jumper`: Patrols with frequent jumps, harder to hit.
- **Integration:** Enemies are initialized with a policy name. `Enemy.update` delegates decision making to the policy.
- **Difficulty Scaling:** Shoot probability scales with `log(level + 1)` via RNGService.

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
- **Delta Compression:** `scripts/network/delta.py` computes diffs between snapshots (`compute_delta`, `apply_delta`) to minimize bandwidth.

---
## 9. Rendering Pipeline
The `Renderer` (`scripts/renderer.py`) ensures consistent draw order:
1.  **Clear:** Wipe buffer.
2.  **Background:** Parallax layers.
3.  **Ghosts:** Rendered via `ReplayManager` (tinted, semi-transparent).
4.  **World:** Tilemap, Entities, Particles (via UI helper).
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
├── game.py                   # Legacy Game class (backward compatible)
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
1. `begin_update()` - Reset collision flags.
2. `compute_frame_movement(movement)` - Calculate next position.
3. `apply_horizontal_movement(tilemap, frame_movement)` - X-axis collision.
4. `apply_vertical_movement(tilemap, frame_movement)` - Y-axis collision.
5. `update_orientation(movement)` - Face direction.
6. `apply_gravity()` - Gravity acceleration & velocity clamp.
7. `finalize_update()` - Animation advance.

### Player Abilities
- **Jump:** Double-jump support (configurable via `jumps` counter).
- **Wall-slide:** Reduced fall speed when sliding on walls.
- **Dash:** Burst movement with deceleration and invulnerability frames.
- **Shoot:** Projectile spawning with cooldown.

### Physics Constants (`scripts/constants.py`)
- `GRAVITY_ACCEL = 0.1`
- `MAX_FALL_SPEED = 5`
- `JUMP_VELOCITY = -3`
- `WALL_SLIDE_MAX_SPEED = 0.5`
- `DASH_DURATION_FRAMES = 60`
- `DASH_SPEED = 8`
- `PROJECTILE_SPEED = 3.5`

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
