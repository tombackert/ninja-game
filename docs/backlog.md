# Backlog Issues
- Multiplayer mode — implemented on `multiplayer` branch (host/join lobby, full world sync, E2E-tested; see docs/multiplayer.md)
- Add restart button to pause menu
- Settings are not deterministically loaded from memory
- UI rendering is not handeled at one spot
- Mypy is not checking untyped functions (possible code quality leak)
- Editor needs extensive documentation for general usage
- Readme needs general update
- Simplify install process
- Verify that state implementation migration from old menu/game is complete + Migrate fully from old game/menu (lose all legacy functions) 
- Can't select via mouse in pause menu
- Add collectable lives (rare)
- Add tutorial in menu
- Implement diffrent enemy behavior based on locations on the map (How is Super Mario solving this? -> Different enemy types, have different behavior. Easy!) 
- Add selected accessories to HUD in menu
- Performance HUD full test coverage
- Audio Ducking full implementation
- Add Game Over screen
- Verify deterministic respawn
- Investigate how the state manager system works (down on process management level) + Check for possible efficiency upgrade
- Add Replay button to pause menu
- Make all assets consistent style
- Introduce new worlds (currently 4: grassland, cave, dessert, and mars) -> waterworld with new physics next
- Introduce new wapons and also balance all wapons (currently the gun is op. It lasers through everything on the horizontal axis)
- Introduce a star collectable item (similar to SuperMario Bros) which gives you superpowers for a limited amount of time. Let it drop particles when equiped. In general particles could enhance asthetics of the game a lot -> explore! 
- Introduce new enemys (like bosses). First hardcode them, later train some
- Optimize training aspect of the game and showcase it 
- New dev strategy: let openai models optimize code on a separate branch, then let opus merge what is good. Similar to how a two person team would develope a game like this

## Benchmark Findings (tools/bench, 2026-10-18; numbers in BENCHMARKS.md)
- Camera glide (68c2a6d) costs +1.3 ms per gameplay frame (2.14 -> 3.44 ms, +61%; first frame of a level +115%), not the ~0.4 ms its commit states: profile Renderer._present (full-window alpha upscale and blit every frame)
- `ReplayManager.abort_current_run()` does not exist: GameState calls it on death/respawn inside try/except, the AttributeError is swallowed and the recording is never aborted
- Level timer runs on wall-clock time (pygame.time.get_ticks): a simulation faster than real time (headless runs, tests, training) saves impossible best times (987 ms for level 0), and dropped frames count as play time
- Perf HUD "Render"/"Work" never show stalls in the update (level start, respawn, level finish), only Interval/Hitches do -> add an update row
- First level start of a session takes ~110 ms (~7 dropped frames) while the machine is busy (33 ms when idle): every image and sound loads on Play -> preload during the menu
- Levels 9 and 10 (4 MB maps): start ~39 ms (map JSON parse ~20 ms), respawn ~11 ms (extract() scans 20k tiles)
- Level-complete screen rescales its background every frame (as the pause screen did before 89764d0)
- HUD timer text is a new string every frame: one text-cache miss per frame (~5,600 evictions per campaign); cheap (33 us) but it churns the 256-entry cache

## Architecture-Patch Backlog
- Localization support
- Map hot reload
- Post-processing pipeline
- Profiling tool panel
