# Refactoring Roadmap (ninja-game)

Status Date: 2025-08-14

Goal: Simplify, unify, and harden the codebase (clean code, clear architecture, testable modules, reduced redundancy). This roadmap structures concrete iterations with explicit issues & acceptance criteria. All code and documentation now in English only.

MANDATORY: For every issue and iteration the following are required before merge: (1) A written Definition of Done (DoD) satisfied, (2) Automated tests covering success + at least one edge case, (3) Manual smoke test (launch, menu navigation, start game, pause) recorded in PR notes. No merge without green tests and DoD checklist fully checked.

---
## Guiding Principles
- Single event loop & explicit game states (Menu, Game, Pause, Store, etc.)
- Separation of concerns: domain (gameplay) vs presentation (render/UI) vs infrastructure (assets, persistence, input)
- No magic numbers → central constants
- Data orientation: prefer small, pure functions
- Minimize IO (asset, text & level list caching)
- Deterministic & testable logic (headless where possible)
- Incremental migration (backward compatible for existing save data)

---
## Target Architecture (High-Level)
```
main.py / GameApp
 ├─ StateManager (active: MenuState, GameState, StoreState, PauseState ...)
 │   └─ Each State: handle_events(events), update(dt), render(surface)
 ├─ Systems
 │   ├─ AssetManager (images, sounds, animations, lazy cache)
 │   ├─ AudioService (SFX/Music playback + volume abstraction)
 │   ├─ InputRouter (bind -> action)
 │   ├─ ProjectileSystem
 │   ├─ ParticleSystem
 │   ├─ Physics / Collision helpers
 │   └─ SaveService (settings, collectables, runs)
 ├─ Domain
 │   ├─ Entities (Player, Enemy, ...)
 │   └─ Collectables
 └─ UI Layer (Renderer, widgets: ListBox, Label, Icon, Message)
```

---
## Iterations (Phases)

### Iteration 1: Quick Wins & Hygiene (Low Risk)
Focus: Obvious bugs & fast unifications without changing gameplay behavior.

Issues:
1. Menu `__init__` bugfix
   - Remove erroneous `return pygame.font.Font(...)` (undefined `size`).
   - Acceptance: Constructor returns None, menu starts without exception.
2. Naming consistency
   - `lifes` → `lives` (internal attributes + UI labels) with JSON backward compatibility layer.
   - Acceptance: Lives display correct; saving/loading unchanged.
3. Introduce constants module (`scripts/constants.py`)
   - Includes: PLAYER_MAX_FALL_SPEED, PLAYER_JUMP_VELOCITY, DASH_START, DASH_DECEL_FRAME, ENEMY_BASE_SPEED_FACTORS, TRANSITION_MAX, etc.
   - Acceptance: Hard-coded numbers replaced in at least `entities.py`, `game.py`.
4. Padlock/static UI asset caching
   - Load padlock & other static images once (not per frame in `ui.render_ui_img`).
   - Acceptance: No regressions; manual profiling shows fewer disk loads.
5. CollectableManager cleanup (phase 1)
   - Remove deprecated coin_count load/save legacy.
   - Normalize spelling "Berserker" (fix typo Berzerker if present).
   - Acceptance: Purchase & save still work; JSON holds full state.
6. Level list caching
   - Utility `list_levels()` (sorted + startup cache; later refresh API for editor).
   - Remove per-frame os.listdir() usage in game loop.
   - Acceptance: Level progression unchanged.
7. Projectile hit / spark utility
   - Extract duplicate blocks (enemy hit / projectile impact) → `effects.spawn_hit_sparks(center, count=30)`.
   - Acceptance: Visual result identical.
8. Logging introduction (lightweight)
   - `logger` module wrapper (fallback to print). No external dependency.
9. Settings write throttle
   - Dirty flag; persist only when changed (or on state transition / shutdown).
   - Acceptance: Functionally identical; file writes reduced.

### Iteration 2: Structure & State Management
Focus: Single event loop, explicit states, unified input.

Issues:
1. StateManager foundation
   - Interface: `push(state)`, `pop()`, `set(state)`, `current.update(dt)`, `current.render(surface)`, `current.handle(events)`.
   - Migrate Menu, Game, Pause to states.
2. InputRouter centralization
   - Single event fetch per frame inside `GameApp.run()`.
   - Key→Action mapping configurable per state.
3. Menu screens refactor
   - Introduce `ScrollableListWidget` (options[], selected_index, visible_rows, on_select).
   - Apply to: Levels, Store, Accessories (weapons/skins dual list), Options.
4. Pause menu integration
   - PauseState overlay (no new `Menu()` instantiation).
5. Unified rendering pipeline
   - Steps: update -> systems update -> state render(offscreen) -> post effects -> flip.
6. AssetManager introduction
   - Lazy loaders: `get_image`, `get_animation`.
   - UI no longer calls `pygame.image.load` directly.
7. AudioService
   - Methods: `play_sfx(name)`, `loop_music(track)`, `set_music_volume(value)`, `set_sfx_volume(value)`.
   - Remove direct `pygame.mixer.Sound` usage in entities & game loop.
8. Deterministic RNG Service (foundation for rollback, replays, RL)
   - Provide seeded RNG interface (`rng.next_float()`, `rng.state()`) and ability to snapshot/restore.
   - Acceptance: All random gameplay calls (enemy AI movement seeds, particle jitter) routed through service.

### Iteration 3: Domain Decomposition & Systems
Focus: Decoupling & testability.

Issues:
1. ProjectileSystem
   - Dataclass `Projectile(pos: list[float], vel: float, lifetime_frames: int)`.
   - API: `spawn(...)`, `update(tilemap, players)`, `render(surface, offset)`, hit callback.
   - Remove raw projectile list from Game.
2. ParticleSystem & Spark API
   - Unified `emit(type, pos, **kwargs)` registry.
   - Central update & render.
3. Entity decoupling
   - Player/Enemy receive only needed services (particles, audio, projectiles, config).
   - Remove direct heavy coupling to Game where feasible.
4. Physics separation
   - From `PhysicsEntity.update` extract `apply_gravity()`, `move_and_collide(...)`, `update_animation()`.
   - Headless tests for move/collision on synthetic maps.
5. Save/Load versioning
   - Add JSON `"version": 2`.
   - Loader migrates legacy version; unit roundtrip test.
6. Settings modernization
   - Dynamic playable levels (scan map files); progress = highest completed index.
   - Unlock logic in `ProgressTracker` service.
7. Weapon / equipment layer
   - Strategy or mapping approach; remove `if selected_weapon == 1` pattern.
8. Performance optimizations
   - Text outline cache (key: (text, size, color, scale)).
   - Optional particle frustum culling.
9. SimulationSnapshot DTO & serializer
   - Serializable aggregate of deterministic state (tick id, entities, projectiles, collectables, rng state).
   - Acceptance: Can produce and reapply snapshot (roundtrip test) without desync.
10. Rollback Buffer
   - Ring buffer storing last N snapshots + input history for eventual networking.
   - Acceptance: Configurable size; retrieval cost O(1); basic rollback test (apply older snapshot then re-sim same inputs matches original).
11. FeatureExtractor module (RL)
   - Build structured observation from snapshot/entity perspective.
   - Acceptance: Consistent shape & deterministic output given fixed snapshot.

### Iteration 4: Polishing & Enhancements (Optional)
- Headless CI setup (SDL_VIDEODRIVER=dummy) + GitHub Actions workflow.
- Code style enforcement (ruff, black, mypy).
- Metrics hook (frame time rolling avg, entity counts, etc.).
- Configurable key bindings (persistent).
- In-game debug overlay (F1).
- Training Environment Wrapper (`TrainingEnv`) enabling reset/step API for RL.
- RewardShaper module (pluggable reward functions referencing FeatureExtractor output).
- NetSyncService scaffolding (message schemas, basic client/server loop without prediction yet).

### Iteration 5: Feature Hardening
- Replay / ghost system (record player inputs & positions).
- Modular AI behavior scripts.
- ECS migration (optional, only if justified).
- PolicyService integration (pluggable scripted vs learned AI policies).
- Prediction & Reconciliation (client prediction, server authoritative correction using rollback buffer).

### Iteration 6: Multiplayer & RL Expansion (Optional / Stretch)
- Interpolation buffers & lag compensation.
- Snapshot delta compression & bandwidth metrics.
- Batch headless simulation harness for large-scale RL data generation.
- Distributed training hooks (stub interfaces, not full infra).

---
## Backlog (Unscheduled)
- Localization layer (multi-language UI text via JSON).
- Audio ducking (dynamic SFX vs music balance).
- Hot-reload maps (editor integration).
- Shader / post-processing (scanline, bloom) abstractions.
- Profiling tool (mini UI panel with per-system timings).
- Network transport abstraction (pluggable UDP / WebSockets) beyond initial scaffolding.
- Encryption / authentication layer (if public multiplayer planned).

---
## Dependencies & Order
- Iteration 1 builds foundation.
- StateManager (Iter 2) precedes Projectile / Particle systems (Iter 3) to centralize update loop.
- AssetManager precedes UI caching (shared references).
- Save versioning after services (Iter 3) to avoid duplicate migration work.
- Deterministic RNG precedes Snapshot & Rollback.
- Snapshot & Rollback precede NetSyncService and Prediction/Reconciliation.
- FeatureExtractor precedes RewardShaper & PolicyService.

---
## Risk Analysis & Mitigation
| Risk | Description | Mitigation |
|------|-------------|------------|
| Menu regressions | New StateManager alters flow | Keep legacy paths temporarily until tests pass |
| Save incompatibility | Old saves not loadable | Version key + migration path |
| Performance drop | Extra abstraction layers add overhead | Micro-profile after each iteration |
| Incomplete coverage | Old patterns remain | Checklist + code search for banned patterns (e.g. direct pygame.image.load) |

---
## High-Level Acceptance Criteria
- No sustained frame drops (< 16.7ms average frame in base level) after Iteration 3.
- Only one central `pygame.event.get()` site (from Iteration 2 onwards).
- No direct image loads in UI/Entities (all via AssetManager) after Iteration 2.
- Zero unexplained magic numbers in entities/game loop (Iteration 3 complete) → all via constants.
- Unit tests (>= 8 core cases) headless pass.
- Settings file not written more than necessary (<= 1 write / second during rapid changes or only on flush).
- Snapshot roundtrip hash stable (after Iteration 3).
- Rollback re-sim consistency (checksum match within epsilon) (after Iteration 3).
- RL environment reset/step deterministic with fixed seed (after Iteration 4).
- Basic NetSync scaffolding exchanges snapshots (after Iteration 4).

---
## Instrumentation
- Add `performance.py` (frame time sampler + rolling average) in Iteration 1 (optional).
- Log active particle / projectile counts (DEBUG) after Iteration 3.

---
## Minimum Test Plan
1. Settings roundtrip (Iteration 1)
2. Collectable purchase (enough coins / insufficient / not purchasable) (Iteration 1)
3. Level transition -> next level index correctness (Iteration 1)
4. StateManager: Menu→Game→Pause→Game→Menu cycle (Iteration 2)
5. ProjectileSystem: hit removes projectile & decrements lives (Iteration 3)
6. Dash: velocity constants correct (Iteration 3)
7. Save version migration (legacy -> new) (Iteration 3)
8. Autotile pattern consistency (Iteration 3)
9. Snapshot roundtrip consistency (Iteration 3)
10. Rollback reproducibility (Iteration 3)
11. FeatureExtractor deterministic output (Iteration 3)
12. TrainingEnv step/reset reproducibility (Iteration 4)
13. Basic NetSync handshake & snapshot transfer (Iteration 4)
14. Replay / ghost deterministic reproduction (Iteration 5)
15. Prediction divergence correction (Iteration 5)

---
## Definition of Done (per Issue)
- Relevant type annotations added (where trivial)
- No linter warnings (once linter is introduced)
- Docstrings for public classes / methods
- Automated tests added & green (unit/integration as applicable)
- Manual smoke test (start game, load level, pause, store open) passes without crash
- Updated documentation (if architecture/concepts change)

---
## Immediate Next Steps
1. Create branch `refactor/iter1-quick-wins`.
2. Implement issues 1–4 (bugfix, naming, constants, asset cache).
3. Add light tests for settings + collectable purchase + level listing.
4. Merge & smoke test.
5. Proceed with remaining Iteration 1 items.

---
## GitHub Issue Template
```
### Context
Short description & goal.

### Tasks
- [ ] Task 1
- [ ] Task 2

### Changes
Components / files

### Acceptance Criteria
- [ ] Criterion 1

### Risks
(optional)

### Test Cases
1. Case

### Definition of Done
- [ ] Tests added & green
- [ ] DoD items satisfied
- [ ] Docs updated (if needed)
```

---
## Glossary
- State: Independent screen/logical context with its own update/render.
- System: Non-UI service (e.g., ProjectileSystem).
- Entity: Game object with position/behavior.
