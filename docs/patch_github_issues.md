# GitHub Issues Seed (Refactoring Roadmap)

All issues must satisfy Definition of Done (see roadmap) and include automated tests + manual smoke validation before merge.

---
## Iteration 1 – Quick Wins & Hygiene

### Issue 1: Fix Menu __init__ Return Bug
### Context
Remove erroneous return statement with undefined variable `size` in `menu.py` constructor causing potential confusion and unreachable code.
### Tasks
- [ ] Remove stray `return` line from `Menu.__init__`
- [ ] Verify no other constructors return accidental values
### Changes
- `menu.py`
### Acceptance Criteria
- [ ] `Menu()` instantiation runs without exceptions.
- [ ] No constructor returns an unexpected non-None value.
### Risks
Low.
### Test Cases
1. Instantiate `Menu` headless (SDL_VIDEODRIVER=dummy) -> no exception.
### Definition of Done
- [ ] Test added (simple import + construct)
- [ ] Manual smoke: launch menu

### Issue 2: Naming Consistency lifes -> lives
### Context
Standardize naming: rename `lifes` to `lives` for clarity and proper English.
### Tasks
- [ ] Introduce property / adapter to keep backward compatibility for any serialized data
- [ ] Rename UI labels and variable usages
- [ ] Update save/load logic to map old key to new
### Changes
- `entities.py`, `game.py`, `menu.py`, `tilemap.py`, any save serialization code
### Acceptance Criteria
- [ ] Game displays "Lives" consistently
- [ ] Existing save files still load without crash
### Risks
Legacy JSON key mismatch.
### Test Cases
1. Simulate legacy JSON containing `lifes` → load → object has `lives` value
2. Lives decrement on damage remains functional
### Definition of Done
- [ ] Tests for migration + runtime behavior
- [ ] Manual run verifying UI label

### Issue 3: Introduce constants module
### Context
Eliminate magic numbers by centralizing gameplay constants.
### Tasks
- [ ] Create `scripts/constants.py`
- [ ] Move dash, gravity caps, jump velocity, transition max, enemy speed factors
- [ ] Replace in `entities.py`, `game.py`
### Changes
- New file `scripts/constants.py`
- Edits in entities & game loop
### Acceptance Criteria
- [ ] No bare magic numbers (selected scope) remain in touched files
### Risks
Behavior changes if wrong values copied
### Test Cases
1. Dash distance unchanged vs baseline (manual compare frame count)
2. Jump still functions (player leaves ground)
### Definition of Done
- [ ] Test verifying constant import & usage (e.g., assert constant references exist)
- [ ] Manual movement check

### Issue 4: Cache static UI images
### Context
`ui.render_ui_img` loads images each call leading to repeated IO.
### Tasks
- [ ] Implement simple cache dictionary in UI or dedicated asset manager placeholder
- [ ] Replace direct loads with cache lookups
### Changes
- `ui.py`
### Acceptance Criteria
- [ ] Subsequent calls do not re-hit disk (verified by adding temporary debug counter or monkeypatch for tests)
### Risks
Stale images if replaced externally (acceptable)
### Test Cases
1. Call render_ui_img twice → underlying load invoked only once (mock patch)
### Definition of Done
- [ ] Test with monkeypatched `pygame.image.load`
- [ ] Manual visual check

### Issue 5: CollectableManager cleanup (phase 1)
### Context
Remove deprecated coin_count legacy and unify item spelling.
### Tasks
- [ ] Remove deprecated load/save functions
- [ ] Ensure JSON persistence covers all active tracked fields (coins, ammo, gun, skins)
- [ ] Correct spelling "Berserker" if needed
### Changes
- `collectableManager.py`
### Acceptance Criteria
- [ ] Buying items updates JSON
- [ ] Deprecated functions absent
### Risks
Accidentally drop a needed field
### Test Cases
1. Purchase gun with enough coins -> JSON updated
2. Attempt purchase without funds -> proper return code
### Definition of Done
- [ ] Tests for success & insufficient funds

### Issue 6: Level list caching
### Context
Avoid per-frame filesystem scans.
### Tasks
- [ ] Add utility `level_index.py` with `list_levels()` caching result
- [ ] Replace dynamic os.listdir calls in loops
### Changes
- New file `scripts/level_index.py`
- Edits in `game.py`, `menu.py`
### Acceptance Criteria
- [ ] Level progression logic maintained
- [ ] Cache invalidation hook (simple function) present
### Risks
Cache stale after adding new maps (acceptable initial)
### Test Cases
1. list_levels returns sorted ints
2. Manual progression to next level still loads
### Definition of Done
- [ ] Unit test for sorting

### Issue 7: Projectile hit/spark utility
### Context
Duplicate spark + particle spawn code.
### Tasks
- [ ] Add function `spawn_hit_sparks(center, count=30)` in `effects.py` or new `effects_util.py`
- [ ] Replace duplicate code in enemy & projectile collision areas
### Changes
- `entities.py`, `ui.py`, `effects.py`
### Acceptance Criteria
- [ ] Visual output unchanged (qualitative)
- [ ] Code duplication removed
### Risks
Miss a variation of effect parameters
### Test Cases
1. Trigger projectile hit & verify list length of sparks/particles consistent with baseline constant
### Definition of Done
- [ ] Basic test: calling utility appends expected number of items when given stub game

### Issue 8: Logging module introduction
### Context
Centralize logging & prepare for future verbosity control.
### Tasks
- [ ] Add `scripts/logger.py` with wrapper (info, warn, error)
- [ ] Replace `print` in targeted files (not all yet, just touched ones)
### Changes
- New file `scripts/logger.py`
- Edits in modified modules
### Acceptance Criteria
- [ ] All new/modified files use logger not bare print
### Risks
Overhead negligible
### Test Cases
1. Logger.info outputs to stdout (captured)
### Definition of Done
- [ ] Test capturing stdout

### Issue 9: Settings write throttle
### Context
Reduce excessive disk writes.
### Tasks
- [ ] Add dirty flag in `Settings`
- [ ] Batch save on explicit `flush()` or graceful shutdown
- [ ] Update setters to mark dirty only when value actually changes
### Changes
- `settings.py`
### Acceptance Criteria
- [ ] Repeated assignment of same value does not write file
- [ ] Changed value writes on flush
### Risks
Data loss if crash before flush (documented)
### Test Cases
1. Set same volume twice -> file mtime unchanged
2. Change value -> flush -> file updated
### Definition of Done
- [ ] Tests verifying mtime behavior

---
## Iteration 2 – Structure & State Management

### Issue 10: StateManager foundation
### Context
Introduce unified state handling for menu/game/pause.
### Tasks
- [ ] Implement State base class
- [ ] Implement StateManager with push/pop/set
- [ ] Port Menu, Game, Pause to states minimally
### Changes
- New: `state_manager.py`, state classes
- Refactor `game.py`, `menu.py`
### Acceptance Criteria
- [ ] Single event polling loop in app root
- [ ] State transitions work (manual cycle)
### Risks
Initial regressions in transitions
### Test Cases
1. Automated: create mock states, push/pop order verified
2. Manual: menu→game→pause→game→menu
### Definition of Done
- [ ] Unit tests for push/pop

### Issue 11: InputRouter centralization
### Context
Remove scattered event consumption.
### Tasks
- [ ] Add `input_router.py`
- [ ] States register handlers
- [ ] Replace direct event parsing in game & menu
### Changes
- New router file + edits
### Acceptance Criteria
- [ ] Only root loop calls `pygame.event.get()`
### Risks
Missing handler mapping
### Test Cases
1. Simulate key event -> correct bound action invoked
### Definition of Done
- [ ] Unit test with synthetic events

### Issue 12: ScrollableListWidget component
### Context
Unify list rendering & selection logic across menus.
### Tasks
- [ ] Implement widget (render, navigate, selection)
- [ ] Integrate into Levels, Store, Accessories, Options
### Changes
- New `ui_widgets.py`
- Modified menu states
### Acceptance Criteria
- [ ] All previous list screens functional & visually consistent
### Risks
Edge-case pagination errors
### Test Cases
1. Navigate beyond bounds wraps or clamps appropriately
### Definition of Done
- [ ] Unit test for navigation logic

### Issue 13: PauseState integration
### Context
Remove ad-hoc pause menu creation.
### Tasks
- [ ] PauseState overlay rendering
- [ ] Resume & return-to-menu actions via StateManager
### Changes
- New pause state file
- Remove old `Menu.pause_menu` static function path
### Acceptance Criteria
- [ ] Pause toggles correctly with ESC
### Risks
Stale references to old pause flow
### Test Cases
1. ESC triggers pause; ESC again resumes
### Definition of Done
- [ ] Automated test toggling pause flag

### Issue 14: Unified rendering pipeline
### Context
Standard sequence for deterministic rendering.
### Tasks
- [ ] Introduce `Renderer` orchestrator
- [ ] Migrate existing render calls
### Changes
- New file `renderer.py`
- Adjust `game.py`
### Acceptance Criteria
- [ ] Frame renders without ordering glitches
### Risks
Missing layering order
### Test Cases
1. Ensure background drawn before entities (assert pixel difference?)
### Definition of Done
- [ ] Basic render order test (mock surfaces)

### Issue 15: AssetManager introduction
### Context
Central asset loading & caching.
### Tasks
- [ ] Implement singleton or injected manager
- [ ] Move image/sound loading out of `game.py`
- [ ] Provide animation builder
### Changes
- New `asset_manager.py`
- Edits to `game.py`, `ui.py`
### Acceptance Criteria
- [ ] No raw `pygame.image.load` outside manager (except manager itself)
### Risks
Paths mis-specified
### Test Cases
1. Request same asset twice returns same object id
### Definition of Done
- [ ] Unit test for caching

### Issue 16: AudioService abstraction
### Context
Uniform audio control.
### Tasks
- [ ] Wrap music & sfx calls
- [ ] Replace direct `pygame.mixer.Sound` usage
### Changes
- New `audio_service.py`
- Edits in `entities.py`, `game.py`
### Acceptance Criteria
- [ ] Volume adjustments propagate
### Risks
Latency differences minimal
### Test Cases
1. Adjust volume -> underlying channel volume changes
### Definition of Done
- [ ] Unit test (mock mixer)

---
## Iteration 3 – Domain Decomposition & Systems

### Issue 17: ProjectileSystem extraction
### Context
Decouple projectile logic from Game & UI pipeline.
### Tasks
- [ ] Dataclass for projectile
- [ ] System update & collision handling
- [ ] Integrate with Entity shooting
### Changes
- New `projectile_system.py`
- Remove projectile loops from `ui.py`
### Acceptance Criteria
- [ ] Projectiles behave unchanged
### Risks
Collision edge cases
### Test Cases
1. Projectile lifetime expiration
2. Projectile hits enemy -> removed
### Definition of Done
- [ ] Unit tests listed passing

### Issue 18: ParticleSystem & spark API
### Context
Central particle emission & lifecycle.
### Tasks
- [ ] Introduce ParticleSystem
- [ ] Replace direct list manipulations
### Changes
- New `particle_system.py`
- Edits where particles appended
### Acceptance Criteria
- [ ] Particle visuals intact
### Risks
Performance overhead
### Test Cases
1. Emission count matches spec
### Definition of Done
- [ ] Unit test with deterministic seed

### Issue 19: Entity service decoupling
### Context
Reduce direct Game coupling for testability.
### Tasks
- [ ] Inject service container into entities
- [ ] Replace direct attribute traversals
### Changes
- `entities.py`
- New `services.py`
### Acceptance Criteria
- [ ] Entities operate via services
### Risks
Ref wiring mistakes
### Test Cases
1. Mock services allow Player jump test headless
### Definition of Done
- [ ] Unit test for player jump

### Issue 20: Physics update separation
### Context
Clean separation of movement & animation.
### Tasks
- [ ] Split PhysicsEntity.update into granular methods
- [ ] Add tests for collision resolution
### Changes
- `entities.py`
### Acceptance Criteria
- [ ] Behavior parity
### Risks
Subtle collision regressions
### Test Cases
1. Horizontal collision stops movement
2. Gravity capped at constant
### Definition of Done
- [ ] Unit tests for both cases

### Issue 21: Save/Load versioning
### Context
Future-proof save schema.
### Tasks
- [ ] Add version field
- [ ] Migration logic for old saves
### Changes
- `tilemap.py`, save/load modules
### Acceptance Criteria
- [ ] Old save loads with defaults
### Risks
Unrecognized schema fields
### Test Cases
1. Load old schema (no version)
2. Load new schema (version=2)
### Definition of Done
- [ ] Tests for both

### Issue 22: Dynamic playable levels & ProgressTracker
### Context
Automate level unlock progression.
### Tasks
- [ ] Implement ProgressTracker scanning map files
- [ ] Replace static playable_levels
### Changes
- `settings.py`, new `progress_tracker.py`
### Acceptance Criteria
- [ ] Finishing level unlocks next
### Risks
Race conditions on file changes (low)
### Test Cases
1. Mark level complete -> next playable
### Definition of Done
- [ ] Unit test

### Issue 23: Weapon/equipment abstraction
### Context
Remove hard-coded weapon logic.
### Tasks
- [ ] Strategy map or classes for weapon behaviors
- [ ] Integrate in Player.shoot
### Changes
- New `weapons/` package
- Edit `entities.py`
### Acceptance Criteria
- [ ] Gun still works, extensibility proven with mock weapon
### Risks
Timing/animation mismatch
### Test Cases
1. Equip default vs gun -> expected projectile spawn difference
### Definition of Done
- [ ] Tests for both weapons

### Issue 24: Performance optimizations (text outline & culling)
### Context
Reduce redundant rendering overhead.
### Tasks
- [ ] Cache rendered outlined text surfaces
- [ ] Optional particle frustum culling flag
### Changes
- `ui.py`, systems
### Acceptance Criteria
- [ ] Outline cache hit ratio > 70% during menu loop (log once)
### Risks
Memory growth (bounded by LRU)
### Test Cases
1. Repeated text render uses cache (mock counter)
### Definition of Done
- [ ] Unit test with spy

---
## Iteration 4 – Polishing & Enhancements

### Issue 25: Headless CI setup
### Context
Automate tests in CI without display.
### Tasks
- [ ] GitHub Actions workflow
- [ ] SDL_VIDEODRIVER=dummy configuration
### Changes
- `.github/workflows/ci.yml`
### Acceptance Criteria
- [ ] CI run green executing tests headless
### Risks
Platform-specific mixer issues
### Test Cases
1. CI pipeline run
### Definition of Done
- [ ] CI badge added to README

### Issue 26: Code style & static analysis
### Context
Consistent code quality.
### Tasks
- [ ] Add ruff, black config
- [ ] Add mypy (lenient initially)
### Changes
- `pyproject.toml` or config files
### Acceptance Criteria
- [ ] Lint & format tasks succeed
### Risks
Large initial diff
### Test Cases
1. Run lint job passes
### Definition of Done
- [ ] CI includes lint step

### Issue 27: Metrics hook
### Context
Visibility into runtime performance.
### Tasks
- [ ] performance module collecting frame times
- [ ] Periodic logging (DEBUG)
### Changes
- `performance.py`
### Acceptance Criteria
- [ ] Rolling average computed
### Risks
Log noise (mitigate log level)
### Test Cases
1. Simulated frame updates produce expected average
### Definition of Done
- [ ] Unit test for average calc

### Issue 28: Configurable key bindings
### Context
Allow user remapping.
### Tasks
- [ ] Key binding schema in settings
- [ ] InputRouter respects mapping
### Changes
- `settings.py`, `input_router.py`
### Acceptance Criteria
- [ ] Remap left/right works in game
### Risks
Conflicting bindings
### Test Cases
1. Change left key -> movement still works
### Definition of Done
- [ ] Unit test adjusting binding

### Issue 29: In-game debug overlay
### Context
Runtime diagnostics.
### Tasks
- [ ] Toggle overlay with F1
- [ ] Show fps, entity counts, memory (optional)
### Changes
- `debug_overlay.py`
### Acceptance Criteria
- [ ] Overlay toggles & displays metrics
### Risks
Overdraw cost (minor)
### Test Cases
1. Toggle twice returns to hidden
### Definition of Done
- [ ] Manual visual confirm + simple test

---
## Iteration 5 – Feature Hardening

### Issue 30: Replay / ghost system
### Context
Record player inputs & positions for playback.
### Tasks
- [ ] Input recorder
- [ ] Ghost entity playback
### Changes
- `replay.py`, entity integration
### Acceptance Criteria
- [ ] Ghost replicates prior run path
### Risks
Desync if map changed
### Test Cases
1. Record short run -> replay matches position trace
### Definition of Done
- [ ] Unit test comparing position frames

### Issue 31: Modular AI behavior scripts
### Context
Pluggable enemy behaviors.
### Tasks
- [ ] Behavior interface
- [ ] Example: patrol, shooter
### Changes
- `ai/` package
### Acceptance Criteria
- [ ] Enemy can swap behaviors via config
### Risks
Complexity overhead
### Test Cases
1. Behavior switch alters movement pattern
### Definition of Done
- [ ] Unit test for behavior dispatch

### Issue 32: ECS migration feasibility (exploratory)
### Context
Assess benefit of ECS architecture.
### Tasks
- [ ] Prototype minimal ECS for projectiles/particles
- [ ] Measure complexity vs benefit
### Changes
- Prototype folder `experiments/ecs/`
### Acceptance Criteria
- [ ] Documented decision (proceed or not)
### Risks
Time sink
### Test Cases
1. N/A (documentation-driven)
### Definition of Done
- [ ] ADR (architecture decision record) committed


## Added Multiplayer & RL Related Issues

### Issue 33: Deterministic RNG Service
### Context
Provide a single seeded RNG stream (and optional substreams) to ensure deterministic simulation (supports rollback, replays, RL).
### Tasks
- [ ] Implement RNG wrapper (seed, get_state, set_state)
- [ ] Replace `random.random()` calls in gameplay with service usage
### Changes
- `rng_service.py`
- Edits in `entities.py`, `effects.py`, particle spawning
### Acceptance Criteria
- [ ] All randomness goes through service
- [ ] Can snapshot & restore RNG state producing identical next values
### Risks
Missed direct random usage causing nondeterminism
### Test Cases
1. Capture state → generate N values → restore → regenerate → sequences match
### Definition of Done
- [ ] Unit test for state roundtrip

### Issue 34: SimulationSnapshot DTO & Serializer
### Context
Capture full deterministic state for rollback, networking, replay.
### Tasks
- [ ] Define dataclasses for snapshot
- [ ] Implement serialize/deserialize (JSON or binary first pass)
- [ ] Integrate snapshot production in GameState
### Changes
- `snapshot.py`
- `game_state.py`
### Acceptance Criteria
- [ ] Snapshot roundtrip equality (hash or deep compare)
### Risks
Floating point drift; large payload size
### Test Cases
1. Create snapshot -> serialize -> deserialize -> compare hashed canonical form
### Definition of Done
- [ ] Unit test

### Issue 35: Rollback Buffer
### Context
Store fixed number of past snapshots + inputs for correction.
### Tasks
- [ ] Ring buffer implementation
- [ ] API: push(snapshot, inputs), get(tick)
### Changes
- `rollback_buffer.py`
### Acceptance Criteria
- [ ] O(1) access & insertion
### Risks
Memory usage if snapshot large
### Test Cases
1. Insert > capacity -> oldest evicted
### Definition of Done
- [ ] Unit test

### Issue 36: FeatureExtractor Module
### Context
Produce structured observation for RL & AI decisions.
### Tasks
- [ ] Define observation schema
- [ ] Deterministic extraction using snapshot
### Changes
- `feature_extractor.py`
### Acceptance Criteria
- [ ] Stable output for identical snapshot
### Risks
Schema churn; performance overhead
### Test Cases
1. Two extractions of same snapshot identical
### Definition of Done
- [ ] Unit test

### Issue 37: Training Environment Wrapper
### Context
Expose gym-like API for RL training.
### Tasks
- [ ] `TrainingEnv.reset()` builds initial snapshot
- [ ] `TrainingEnv.step(action_dict)` advances fixed ticks
### Changes
- `training_env.py`
### Acceptance Criteria
- [ ] Deterministic sequence with fixed seed
### Risks
Drift if actions not applied consistently
### Test Cases
1. Two seeded runs produce identical reward sequence
### Definition of Done
- [ ] Unit test

### Issue 38: RewardShaper Module
### Context
Pluggable reward shaping logic.
### Tasks
- [ ] Implement default shaping (progress, survival)
- [ ] Configurable weights
### Changes
- `reward_shaper.py`
### Acceptance Criteria
- [ ] Reward matches documented formula
### Risks
Overfitting shaping early
### Test Cases
1. Known scenario -> expected reward value
### Definition of Done
- [ ] Unit test

### Issue 39: NetSyncService Scaffolding
### Context
Prepare networking: message schemas & basic server/client loop (local stub).
### Tasks
- [ ] Define message types (Input, Snapshot, Ack)
- [ ] Implement local loopback transport for early tests
### Changes
- `network/messages.py`, `network/netsync_service.py`
### Acceptance Criteria
- [ ] Can send snapshot & receive acknowledgment locally
### Risks
Premature complexity
### Test Cases
1. Loopback send/receive roundtrip
### Definition of Done
- [ ] Unit test

### Issue 40: PolicyService Integration
### Context
Register & invoke behavioral policies (scripted or learned) per enemy.
### Tasks
- [ ] Service with registry {policy_name: callable}
- [ ] Enemy references selected policy each tick
### Changes
- `policy_service.py`, `entities.py`
### Acceptance Criteria
- [ ] Switch policy at runtime alters behavior deterministically
### Risks
Policy side-effects
### Test Cases
1. Two different policies produce different action sequence given same observation
### Definition of Done
- [ ] Unit test

### Issue 41: Prediction & Reconciliation
### Context
Client-side prediction with rollback on authoritative correction.
### Tasks
- [ ] Apply predicted inputs locally
- [ ] On snapshot mismatch: rollback & re-sim inputs
### Changes
- Extend `netsync_service.py`, use `rollback_buffer`
### Acceptance Criteria
- [ ] Divergence corrected within N frames in test harness
### Risks
Edge timing glitches
### Test Cases
1. Inject artificial latency & corrections -> final state matches authoritative
### Definition of Done
- [ ] Automated test harness

### Issue 42: Replay / Ghost via Snapshots
### Context
Use snapshots & inputs to recreate ghost runs.
### Tasks
- [ ] Record input + periodic snapshots
- [ ] Playback interpolating between snapshots
### Changes
- `replay.py`
### Acceptance Criteria
- [ ] Ghost path matches original within tolerance
### Risks
Interpolation drift
### Test Cases
1. Record small session -> playback diff under threshold
### Definition of Done
- [ ] Unit test

### Issue 43: Interpolation Buffers
### Context
Smooth remote entity movement between delayed snapshots.
### Tasks
- [ ] Buffer snapshots per remote entity
- [ ] Interpolate based on render time offset
### Changes
- `interpolation.py`
### Acceptance Criteria
- [ ] No stutter with uniform snapshot interval
### Risks
Catch-up jitter on burst delay
### Test Cases
1. Simulated 100ms latency scenario -> movement continuity
### Definition of Done
- [ ] Unit test

### Issue 44: Snapshot Delta Compression
### Context
Reduce bandwidth by sending only changed fields.
### Tasks
- [ ] Compute diff vs previous snapshot
- [ ] Apply patch on receiver
### Changes
- `network/delta.py`
### Acceptance Criteria
- [ ] Reconstructed snapshot equals full snapshot
### Risks
Complexity & CPU cost
### Test Cases
1. Random state changes -> diff+apply roundtrip match
### Definition of Done
- [ ] Unit test

### Issue 45: Batch Headless Simulation Harness
### Context
Run multiple env instances for RL data collection.
### Tasks
- [ ] Manager launching N TrainingEnv in threads/processes
- [ ] Aggregate observations & rewards
### Changes
- `batch_sim.py`
### Acceptance Criteria
- [ ] Throughput > single env baseline (documented)
### Risks
GIL contention or process overhead
### Test Cases
1. Run 4 envs parallel -> aggregated step count > sequential
### Definition of Done
- [ ] Performance test script

### Issue 46: Distributed Training Hooks (Optional)
### Context
Prepare for external RL frameworks (Ray, etc.).
### Tasks
- [ ] Provide adapter interface (serialize observation, action application)
- [ ] Document integration example
### Changes
- `training_adapter.py`
### Acceptance Criteria
- [ ] Minimal example script executes one train loop iteration
### Risks
Scope creep
### Test Cases
1. Example script returns a policy update step
### Definition of Done
- [ ] Example included



---
## Backlog Issues (Triage Later)
- Localization support
- Audio ducking
- Map hot reload
- Post-processing pipeline
- Profiling tool panel

---
## Global Definition of Done Reminder
Every issue must have: tests added & passing, DoD checklist completed, documentation updated if concepts changed.
