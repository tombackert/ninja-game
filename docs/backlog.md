# Backlog Issues
- Multiplayer mode — implemented on `multiplayer` branch (host/join lobby, full world sync, E2E-tested; see docs/multiplayer.md)
- Settings are not deterministically loaded from memory
- UI rendering is not handeled at one spot
- Mypy is not checking untyped functions (possible code quality leak)
- Editor needs extensive documentation for general usage
- Readme needs general update
- Simplify install process
- Verify that state implementation migration from old menu/game is complete + Migrate fully from old game/menu (lose all legacy functions) 
- Add collectable lives (rare)
- Add tutorial in menu
- Implement diffrent enemy behavior based on locations on the map (How is Super Mario solving this? -> Different enemy types, have different behavior. Easy!) — done: five enemy kinds (gunner, patrol, turret, chaser, jumper) cast per spot by tools/worlds/roster.py, no more level-number scaling (see docs/architecture.md, section 5)
- Add selected accessories to HUD in menu
- Performance HUD full test coverage
- Audio Ducking full implementation
- Verify deterministic respawn
- Investigate how the state manager system works (down on process management level) + Check for possible efficiency upgrade
- Add Replay button to pause menu
- Make all assets consistent style
- Introduce new worlds (currently 4: grassland, cave, dessert, and mars) -> waterworld with new physics next — water world implemented on `water-world` branch (levels 21-25: swimming, breath, currents, geysers and drains; see docs/architecture.md)
- Introduce new wapons and also balance all wapons (currently the gun is op. It lasers through everything on the horizontal axis)
- Introduce a star collectable item (similar to SuperMario Bros) which gives you superpowers for a limited amount of time. Let it drop particles when equiped. In general particles could enhance asthetics of the game a lot -> explore! 
- Introduce new enemys (like bosses). First hardcode them, later train some
- Optimize training aspect of the game and showcase it 
- New dev strategy: let openai models optimize code on a separate branch, then let opus merge what is good. Similar to how a two person team would develope a game like this
- Build all levels via the code way (now that we have it, this is the more elegant way) -> upgrade the editor so that it can also do what we now do via the code way (route planner etc.) (-> related to storage issue level 9+10 not compact)
- Have 50+ levels
- Optimize enemies: simple enemies should no longer shoot from so far away, range should go just past the frame edge. Add harder ones. — done (SIGHT_X 336 px; turret, chaser and jumper)
- Game modes: clean up menu: Solo / Online / (against AI)
- Build level map: like in Super Mario Bros
- Optimize storage -> level 9+10 not compact, trailer / sound assets are in the git code history (will become a problem later)
- Use editor from within the game -> editor should build compressed level files. Something like level to code to level. Where the level is optimized in code so that it afterwards exists in the storage-optimized form. (storage-optimized form must not mean that it needs more compute later to get back from the form into the wanted one. First understand why level 9 + 10 are so much bigger / uncompressed)
- Enemy balance - when several enemies stand in a cluster, only a certain number shoot. Enemy checks whether one very close around it has already shot. Sight range of the enemies just outside the window — done (CLUSTER_RADIUS / CLUSTER_HOLD in scripts/enemy_kinds.py)
- Improve swimming - diving head first (body rotation changes). Air after diving recharges slower than instantly.
- The new water levels were trivial for Tobi. Must then become much harder later. Question: How can one design levels on which human players get stuck for a very long time? It seems that the search/evaluation does not yet find all possible human inputs when evaluating the levels. There is still optimization potential there!
- Improve the level menu itself - based on or inspo from Super Mario Bros worlds. Maybe a 2D map in which one can walk through the worlds map? (names and preview thumbnails are done, see docs/campaign.md)

## Enemy Kinds & Hazards Follow-ups
- Difficulty model: enemies and bullets are still not in it (tools/worlds/windows, assess). Next: an exposure term per element (frames in a gunner's or turret's line of fire, frames next to a touch-kill kind) now that each kind has fixed numbers
- Hazards are only in levels 11 (crumbling crates), 12 (spikes) and 15 (flame jets): build them into the later chapters and re-cast the hand-placed enemies of the finales by design (`Level.enemy(x, y, "turret")`)
- The route planner is time-blind: it plans as if flames never burn and crumbling blocks never fall; hazard_check only rejects a route, so a jet's phase has to be tuned by hand
- Moving platforms were left out (riding, network sync and the planner's model would all need to know them)
- Editor: entity tracking of spawners is still broken (see the water world note below); placing kinds and hazards as tiles works

## Benchmark Findings (tools/bench, 2026-10-18; numbers in BENCHMARKS.md)
- Camera glide (68c2a6d) costs +1.3 ms per gameplay frame (2.14 -> 3.44 ms, +61%; first frame of a level +115%), not the ~0.4 ms its commit states: profile Renderer._present (full-window alpha upscale and blit every frame)
- `ReplayManager.abort_current_run()` does not exist: GameState calls it on death/respawn inside try/except, the AttributeError is swallowed and the recording is never aborted
- Level timer runs on wall-clock time (pygame.time.get_ticks): a simulation faster than real time (headless runs, tests, training) saves impossible best times (987 ms for level 0), and dropped frames count as play time
- Perf HUD "Render"/"Work" never show stalls in the update (level start, respawn, level finish), only Interval/Hitches do -> add an update row
- First level start of a session takes ~110 ms (~7 dropped frames) while the machine is busy (33 ms when idle): every image and sound loads on Play -> preload during the menu
- Levels 9 and 10 (4 MB maps): start ~39 ms (map JSON parse ~20 ms), respawn ~11 ms (extract() scans 20k tiles)
- Level-complete screen rescales its background every frame (as the pause screen did before 89764d0)
- HUD timer text is a new string every frame: one text-cache miss per frame (~5,600 evictions per campaign); cheap (33 us) but it churns the 256-entry cache

## Profiling Tools
- py-spy for gameplay frames: samples from outside, no instrumentation overhead (`sudo py-spy record -o profile.svg --subprocesses -- python -m tools.bench`); start with Renderer.render (3.01 of 3.18 ms frame p50)
- `tools.bench --profile` (cProfile) adds overhead to every call and skews the many small per-frame calls -> use it for call counts only
- Instruments Time Profiler only if the hotspot is inside pygame-ce/SDL
- LIKWID (HPSC lecture 3) for scripts/batch_sim.py on Linux: core scaling with likwid-topology/likwid-pin; IPC, cache misses and memory bandwidth with likwid-perfctr

## Water World Follow-ups (water-world branch)
- Enemy bullets fly through water at full speed: slowing them there would make the water feel thicker (and tone down the gun under water)
- No dive input: a swimmer only sinks (~3 tiles/s), so deep dives need drains in the level design
- TrainingEnv / feature extractor know nothing about water (no in-water or breath features)
- Editor: entity tracking checks `tile_group == 2` for spawners, but group 2 has been `sand` since the desert world (spawners are group 4): placing sand variant 0/1 registers a player/enemy, spawners register none

## Architecture-Patch Backlog
- Localization support
- Map hot reload
- Post-processing pipeline
- Profiling tool panel
