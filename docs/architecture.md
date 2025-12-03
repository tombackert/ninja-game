# Architecture Specification

**Status Date:** 2025-12-01
**Version:** 2.0 (Post-Refactoring)

This document describes the current architecture of the Ninja Game, reflecting the completion of the major refactoring roadmap (Iterations 1-6). The system is designed for determinism, extensibility, and future multiplayer/RL integration.

---
## 1. Goals (Achieved)
- **Separation of Concerns:** Clear split between Simulation (Domain), Presentation (Renderer/UI), and Infrastructure (Input/Assets).
- **Determinism:** Fixed-step simulation with centralized RNG and input-driven updates, enabling reliable replays and rollback.
- **Extensibility:** Service-oriented design (ServiceContainer) and modular AI (Policy) allow adding features without invasive coupling.
- **Performance:** Optimized snapshotting (LITE mode), efficient interpolation, and batched headless simulation support.

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
    - `Patrol`: Back-and-forth movement.
    - `Shooter`: Stationary tracking turret.
- **Integration:** Enemies are initialized with a policy name. `Enemy.update` delegates decision making to the policy.

---
## 6. Networking & RL Infrastructure
The codebase contains a complete foundation for Multiplayer and Reinforcement Learning.

### 6.1 Reinforcement Learning (RL)
- **TrainingEnv:** `scripts/training_env.py` exposes a `reset()` / `step(action)` interface compatible with RL standards. It manages its own headless `Game` instance.
- **Adapters:** `scripts/training_adapter.py` provides wrappers for **Ray RLLib** and **Stable Baselines**.
- **Batch Simulation:** `scripts/batch_sim.py` allows running N environments in parallel processes for high-throughput data collection.

### 6.2 Networking Primitives
- **Interpolation:** `scripts/network/interpolation.py` implements a `SnapshotBuffer` that smoothly interpolates entity positions/velocities between server snapshots for remote rendering.
- **Delta Compression:** `scripts/network/delta.py` computes diffs between snapshots (`compute_delta`, `apply_delta`) to minimize bandwidth.

---
## 7. Rendering Pipeline
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
## 8. Directory Structure
- **`scripts/`**: Core game logic.
    - **`ai/`**: AI Policies.
    - **`network/`**: Sync, Delta, Interpolation.
    - **`weapons/`**: Weapon strategies.
- **`data/`**: Assets, Maps, Configs.
    - **`replays/`**: JSON replay files.
- **`tests/`**: Unit and Integration tests (Pytest).
- **`experiments/`**: Benchmarks and prototypes.
- **`docs/`**: Architecture and patch notes.

---
## 9. Future Directions (Backlog)
- **Multiplayer:** Implement `Transport` layer (UDP) and `NetSyncService` using the existing Snapshot/Delta infrastructure.
- **Key Bindings:** Make `InputRouter` mappings configurable via a settings UI.
- **Localization:** Externalize string literals.
- **Audio Ducking:** Dynamic mixing based on game events.

---
## 10. Performance Notes
- **Snapshots:** LITE mode takes ~0.01ms per capture.
- **Interpolation:** ~1.87us per entity.
- **Batch Sim:** Scaling limited by process startup cost on short runs; efficient for long training sessions.

End of specification.
