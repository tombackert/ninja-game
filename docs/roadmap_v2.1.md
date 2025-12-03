# Roadmap v2.1: Polish & Core Experience

**Status:** Planned
**Focus:** Stabilize the single-player experience, fix "game feel" bugs, and improve codebase extensibility.

---

## 1. Critical Bug Fixes (Game Feel)
These issues directly degrade the player experience and are the top priority.

- [ ] **Fix Pause State**
    - **Issue:** The camera continues to scroll/update even when the game is paused, breaking immersion.
    - **Solution:** Move camera scroll logic from `Renderer.render` to `GameState.update`.
- [ ] **Fix Respawn Determinism**
    - **Issue:** Players do not always respawn at the exact same coordinates, causing replay drift.
    - **Solution:** Enforce strict coordinate resets and ensure RNG is correctly managed during respawn.
- [ ] **Fix Performance HUD**
    - **Issue:** HUD parameters are failing due to conflicting control sources.
    - **Solution:** Centralize the "Show HUD" source of truth in `Settings`.

## 2. Core Features & Extensibility
Prove the v2.0 architecture's flexibility while adding value.

- [ ] **Configurable Key Bindings**
    - **Goal:** Allow users to define their own controls.
    - **Tech:** Refactor `InputRouter` to load bindings from `Settings` instead of hardcoded values.
- [ ] **New AI Behavior: "Chaser"**
    - **Goal:** Add an enemy that actively follows the player.
    - **Tech:** Implement a new `ChaserPolicy` in `scripts/ai/behaviors.py`.
- [ ] **Smoother Level Transitions**
    - **Goal:** Replace the abrupt level switch with a "Level Complete" summary and confirmation.
    - **Tech:** Add a `LevelCompleteState` to `StateManager`.

## 3. Technical Debt (Infrastructure)
- [ ] **Localization Foundation (i18n)**
    - **Goal:** Move hardcoded strings from `scripts/ui.py` to a dictionary/JSON file.
    - **Why:** Prepares for future translation support.

---

## Dropped / Postponed (Backlog)
- **Multiplayer:** Postponed to v2.2. Requires significant transport layer work.
- **Map Hot Reload:** Nice to have, but low priority.
