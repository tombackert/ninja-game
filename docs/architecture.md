# Architecture Specification (Planned Refactor)

Status Date: 2025-08-14
Version: Draft 1

This document describes the target architecture as outlined in the refactoring roadmap and extends it with foundations required for future Online Multiplayer and RL-trained Enemy AI.

---
## 1. Goals
- Clear separation of concerns (simulation vs presentation vs infrastructure).
- Deterministic, headless-capable simulation loop suitable for testing & AI training.
- Extensible service-oriented design for new systems (networking, AI policies) without invasive changes.
- Reduced redundancy and improved readability (Clean Code & explicit data/control flow).
- Performance stability (consistent frame times, minimized IO during runtime).

---
## 2. High-Level Component Overview
```
GameApp (entry)
 ├─ StateManager
 │   ├─ MenuState
 │   ├─ GameState
 │   ├─ PauseState
 │   ├─ StoreState
 |   ├─ OptionsState 
 │   └─ (Future) MultiplayerLobbyState / MatchState
 ├─ Core Loop
 │   1. Poll events (InputRouter)
 │   2. Advance simulation tick(s)
 │   3. Render (if graphical mode)
 │   4. Present + instrumentation
 ├─ Systems Layer
 │   ├─ AssetManager
 │   ├─ AudioService
 │   ├─ InputRouter
 │   ├─ ProjectileSystem
 │   ├─ ParticleSystem
 │   ├─ Physics / CollisionHelpers
 │   ├─ Effects (screenshake, transitions)
 │   ├─ SaveService (settings, runs, collectables)
 │   ├─ ProgressTracker
 │   ├─ Logging / Metrics
 │   ├─ (Future) NetSyncService
 │   └─ (Future) AIScheduler / PolicyService
 ├─ Domain Layer
 │   ├─ Entities (Player, Enemy, NPC, Collectable...)
 │   ├─ Components (optional future: ECS migration)
 │   ├─ Tilemap / Level Representation
 │   └─ GameRules (win/lose, progression)
 ├─ Presentation Layer
 │   ├─ UI Renderer (widgets, list box)
 │   ├─ EffectsRenderer
 │   ├─ DebugOverlay
 │   └─ (Future) Spectator HUD / Net Diagnostics
 └─ Integration / Adapters
     ├─ Serialization (Save / Load / Network messages)
     ├─ Configuration (constants, tuning)
     └─ Headless Harness (for CI & RL training)
```

---
## 3. Dependency Direction
- Presentation depends on Domain + Systems (read-only access to state, commands via services).
- Entities depend only on narrow service interfaces (e.g. `AudioPort`, `ParticlesPort`, `ProjectilesPort`, `Config`).
- Systems are mostly independent (AssetManager, AudioService) and orchestrated by GameState.
- StateManager is ignorant of concrete internals; it only drives lifecycle methods.
- Networking and AI modules plug into Systems layer with explicit ports.

Avoided: Domain referencing UI or raw Pygame APIs (except data types like `Rect` until abstracted later).

---
## 4. Update Loop (GameState)
```
for frame:
  events = pygame.event.get()                # Single poll location
  input_router.dispatch(events)              # Update input mapping -> intents
  accumulator += real_dt
  while accumulator >= FIXED_TICK:           # Deterministic simulation steps
      simulation_tick(FIXED_TICK)
      accumulator -= FIXED_TICK
  render(interp_ratio=accumulator/FIXED_TICK)
  present()
```
### Simulation Tick Responsibilities
1. Apply pending player input intents (movement, dash, shoot).
2. Update physics (entities & projectiles) in deterministic order.
3. Resolve collisions & game rules (damage, pickups, transitions).
4. Spawn & update particles (logic; visual interpolation handled in render).
5. Run AI policies (enemy decisions) – future.
6. Net synchronization (if online) – future.
7. Metrics sampling / instrumentation.

This fixed-step design enables: deterministic replays, rollback potential, RL batch stepping, and network reconciliation.

---
## 5. Constants & Configuration
Centralized in `scripts/constants.py`:
- Physics: gravity, max fall speed, horizontal friction.
- Player: jump velocity, dash frames, dash speed curve.
- Enemy: base speed factors per difficulty/level.
- Timers: transition frames, projectile lifetime.
- Networking (future): tick rate, snapshot interval, buffer sizes.
- AI Training (future): max episode length, reward shaping scalars.

All gameplay logic imports from this module—no magic numeric literals in domain code.

---
## 6. Systems Detail
### 6.1 AssetManager
- Lazy loads images, sounds, animations; caches references.
- Provides `get_image(key)`, `get_animation(key)`, `get_sound(key)`.
- Preload list for latency-sensitive assets.

### 6.2 AudioService
- Abstracts mixer. Methods: `play_sfx(id)`, `play_music(track, loop=True)`, `set_volumes(music, sfx)`.
- Queues & throttling (future) to prevent sound spam.

### 6.3 InputRouter
- Maps (device event → semantic action) per state.
- Supports rebinding (Iteration 4) via settings persist.
- Produces a normalized `InputIntent` struct consumed by simulation.

### 6.4 ProjectileSystem
- Owns projectile list.
- Provides `spawn(origin, velocity, meta)` and `update(tilemap, entities)`.
- Collision callbacks decoupled from Entities (Entities raise spawn requests rather than mutating global lists).

### 6.5 ParticleSystem
- Structured particle records (type, pos, vel, lifetime, style data).
- Rendering stage filters visible subset (culling extension).

### 6.6 Effects
- High-level visual transformations (screen shake, transitions) parameterized; no direct game state mutation besides effect state.

### 6.7 SaveService
- Versioned schema (adds `version` field).
- Provides `save_run(snapshot)` and `load_run(path)` with migration map.

### 6.8 ProgressTracker
- Scans available maps on startup.
- Maintains unlocked level index; updates after completion event.

### 6.9 Logging / Metrics
- Thin wrapper around Python logging (INFO default, DEBUG for instrumentation).
- Frame time sampling; optionally exports CSV or JSON session logs.

### 6.10 NetSyncService (Future)
- (Planned) Manages client prediction + server authoritative reconciliation:
  - Input buffering (sequence numbers).
  - State snapshots (compressed entity states).
  - Interpolation buffers for remote entities.
  - Rollback hooks (re-simulate stored inputs on corrected snapshot).

### 6.11 AIScheduler / PolicyService (Future)
- Orchestrates selection and execution of AI policies per entity.
- Exposes synchronous `decide(entity, observation) -> action` and async vectorized batch (for RL inference acceleration).

---
## 7. Domain Entities
Entities are plain Python objects with minimal direct system knowledge (through service ports). Core methods:
- `gather_observation()` (for AI / RL) – returns structured dict or numpy array (lazy import to avoid hard dependency when not training).
- `apply_action(action)` – interprets high-level action (move left/right, jump, dash, fire).
- `tick(dt)` – updates its internal timers/state (movement intentions resolved by Physics helpers).

### Service Ports (Interfaces)
```
class AudioPort: play_sfx(name: str) -> None
class ProjectilePort: spawn(spec: ProjectileSpec) -> None
class ParticlePort: emit(type: str, pos, **kwargs) -> None
class ConfigPort: get(key: str) -> Any
```
Entities receive only these ports; actual implementations backed by systems.

---
## 8. Networking Foundations (Design Considerations)
Planned architecture already supports multiplayer with the following adjustments:
- Deterministic fixed-step tick enables lockstep or rollback designs.
- Entity state is serializable (positions, velocities, action flags, RNG seeds).
- Need an explicit RNG stream (e.g. `random.Random` per simulation) to guarantee determinism across peers.
- Introduce `SimulationSnapshot` DTO with: tick_id, players[], projectiles[], collectables[], level meta.
- Add `apply_snapshot(snapshot)` to GameState for reconciliation.
- Add input compression format (bit-packed: movement bits, jump, dash, shoot, timestamp).

Additional modules to schedule:
- `network/messages.py` (schemas & (de)serialization)
- `network/transport.py` (UDP/TCP abstraction) – or deferrable.
- `network/replication_rules.py` (what to sync, frequency, LOD policies).

### Latency Mitigation Plan
- Client prediction: immediately apply local input.
- Server authoritative corrections: diff snapshots, rollback N ticks (store last N input + states ring buffer).
- Interpolation for remote players: maintain N-lag buffer (e.g. 100ms) and interpolate between known snapshots.

---
## 9. RL / AI Training Foundations
Requirements & hooks to support RL-trained enemy AI:
- Headless mode: disable rendering & audio completely (environment runs faster than realtime).
- Deterministic seeding: `SimulationConfig(seed)` sets RNGs for physics randomness & procedural aspects.
- Environment API:
```
class TrainingEnv:
    def reset(self) -> Observation: ...
    def step(action_dict) -> (Observation, Reward, Done, Info): ...
```
- Observation extraction isolated (feature builder): positional deltas, velocities, tile proximities, collectables, enemy states.
- Reward shaping pluggable (e.g., time alive, progress to flag, damage dealt/taken).
- Batch stepping: multiple parallel env instances (process or thread pool) for faster experience collection.
- PolicyService supports swapping in scripted vs learned policies at runtime.

Additions to baseline plan:
1. Introduce `FeatureExtractor` module (Iteration 3 extension).
2. RNG management service (store & advance seeds) – needed for reproducible training.
3. Headless harness script `train_env.py` (Iteration 4+).
4. Optional memory profiler hooks for large batch runs.

---
## 10. Data & Serialization
### Save Schema (v2)
```
{
  "version": 2,
  "meta": {"map": int, "timestamp": iso8601, "best_times": {...}},
  "players": [...],
  "enemies": [...],
  "projectiles": [...],
  "collectables": {...}
}
```
Backward compatibility: loader attempts legacy parse (v1) then upgrades to v2 by injecting missing fields with defaults.

### Network Snapshot (Draft)
```
{
  "tick": int,
  "rng_state": str,         # optional for strict determinism
  "players": [{id, x, y, vx, vy, facing, action_flags}],
  "enemies": [...],
  "projectiles": [...],
  "events": [ {type, data} ]
}
```

---
## 11. Extensibility Points
| Extension | Mechanism |
|-----------|-----------|
| New weapon type | Add weapon strategy implementing `fire(player, services)` |
| New AI policy | Register callable in `PolicyService` dispatch map |
| New entity | Subclass base entity + register in factory (and snapshot serializer) |
| Additional effect | Append to Effects pipeline chain |
| Protocol evolution | Version field in network messages + negotiation |

---
## 12. Risk & Mitigation Summary
| Risk | Mitigation |
|------|------------|
| Over-abstraction early | Stage advanced systems (NetSync, AI) behind clear interfaces only when needed |
| Determinism drift | Single RNG stream + fixed tick accumulation, unit tests comparing checksum of snapshot sequence |
| Performance overhead | Profiling hooks + iterative optimization (cache, pooling) |
| Save/Net schema churn | Version fields + migration utilities |
| RL feature creep | Keep training harness outside core runtime; integrate via thin adapter |

---
## 13. Roadmap Adjustments for Multiplayer & RL
Additional issues to append to roadmap:
1. Deterministic RNG Service (Iteration 2 or early 3)
2. SimulationSnapshot DTO & serializer (Iteration 3)
3. Rollback Buffer (configurable ring buffer of prior states) (Iteration 3)
4. NetSyncService scaffolding + message schema draft (Iteration 4)
5. Training Environment Wrapper (Iteration 4)
6. FeatureExtractor & RewardShaper modules (Iteration 4)
7. PolicyService integration (Iteration 5)
8. Prediction & Reconciliation implementation (Iteration 5+)

---
## 14. Testing Strategy Summary
| Layer | Approach |
|-------|----------|
| Constants | Assert logical relationships (e.g., dash_duration > 0) |
| Physics | Deterministic scenario tests (expected positions) |
| Systems | Unit tests with mocks (Audio, Asset) |
| Integration | Headless run N ticks, snapshot hash stable |
| Networking (future) | Simulate latency & packet loss, assert convergence |
| RL Harness | Step/reset reproducibility with fixed seed |

Continuous integration will run all tests headless; performance benchmarks optional nightly.

---
## 15. Open Questions
- Will networking be lockstep or authoritative server? (Default assumption: server authoritative w/ client prediction.)
- Required maximum player count? (Impacts snapshot size & interpolation tuning.)
- RL training scale expectation (single machine vs distributed)?

Answers will refine NetSync & PolicyService design.

---
## 16. Summary
The planned architecture already establishes most foundations for future online and RL features (deterministic loop, modular systems, service interfaces). Added roadmap items (RNG service, snapshot DTO, rollback buffer, training harness, policy service) ensure clean integration without rework.

End of specification.
