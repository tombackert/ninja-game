# Level Building: Findings From Levels 26-38

**Date:** 2026-11-06
**Status:** Round stopped after 7 of 15 levels. The build process gets a rethink before more levels are built.

The plan was 15 new levels, 5 per world: desert 26-30, Mars 31-35, water 36-40. They had to be built from code (`tools/worlds/levels/level_N.py`) and to hit the targets in [difficulty-rating-brainstorm.md](difficulty-rating-brainstorm.md) section 9: an expert needs 4-6 minutes for the first clear of a normal level, and 15-20 minutes for a world finale. One subagent built each world.

The round stopped after 7 levels (26, 27, 28, 31, 36, 37, 38). The process cost too much for what it delivered, and only one level reached its target. This document records what was built, why the targets were missed, where the effort went, and what the next process has to fix.

---

## 1. What Was Built

All seven levels pass these checks:
- The route plans from the spawn to the flag.
- The banner is on the route.
- The physics replica matches the game for 20,000 frames (`check_physics --route`).
- The stills of the real game, with live enemies, reach the flag with 0 deaths.
- The route bot cleared each level in the real game window on its first attempt (`python -m tools.worlds.play`: menu, keyboard input, live enemies). It took 78-132 s per level and lost one life, on 36.

The window profiles are in [difficulty-rating-brainstorm.md](difficulty-rating-brainstorm.md) section 8.

| Level | World | Concept | Signature | Expert, first clear | Target |
| --- | --- | --- | --- | --- | --- |
| 26 The Buried City | desert | a sunken stone city: aqueduct, tower houses, alley, roofs, bell tower, a cistern under the palace, minarets | dash through tower windows | 3.3 min / 2.1 deaths | ~4 |
| 27 Hoodoo Valley | desert | hoodoos and balanced rocks over quicksand | climb notched slots between stems, out past the overhanging cap | 2.9 min / 0.4 deaths | ~4.5 |
| 28 The Sinkhole | desert | the first level going down: a throat, a bell-shaped cavern over a void, a riverbed tunnel, a spring shaft | ledges tucked under overhanging lips | 2.4 min / 1.4 deaths | ~5 |
| 31 Rift Bridge | Mars | a rock bridge over a bottomless rift; tall crags on its back force six crossings underneath | hook swing: drop past a claw, dash under it, jump to the next | 4.2 min / 4.2 deaths | ~4 |
| 36 Tide Pools | water | climbing a headland at low tide | leaps out of pools with undercut far rims | 3.4 min / 0.6 deaths | ~4 |
| 37 The Whirlpool | water | current rings around rock cores under a reef | ride a ring and break out at its exit; meshing rings decide the way on | 3.3 min / 1.0 deaths | ~4.7 |
| 38 Kelp Forest | water | kelp on rock trunks, air only in hollows | up and down current lanes, timed passes through gaps in the trunks | 2.4 min / 0.5 deaths | ~5.3 |

Not started: 29, 30 (desert finale), 32-35 (35 is the Mars finale), 39, 40 (water finale).

The level numbers have gaps, and that is fine. The game orders levels by their sorted map ids (`scripts/level_cache.py`, `state_manager`), so after 28 comes 31, then 36-38, then the experimental maps 41 and 42.

## 2. Why the Targets Were Missed

Six of seven levels stay below their target. Level 31 meets it only because of many exposed presses: 59, against a guideline of at most 8 per half.

- **Most elements count as free, so adding elements adds little time.** The windows model rates most hops, cap jumps, pillar hops, dash crossings and swims at 13 frames or more, which counts as free. A free element costs about its played-safe time and almost no deaths. So the expert's first clear comes out at only about 1.4-2 times the played-safe time (84-143 s in these levels). Reaching 4-5 minutes this way would need roughly 140-230 s of played-safe content per level, up to twice what the levels have now.
- **Making an element hard is a cliff, not a dial.**
  - Elements with a 4-8 frame window barely move the time. They cost the expert little.
  - The agents could not find a reliable middle step: variants they tried came out either at 5-9 frames or at five 1-frame presses in a row.
  - One example: taking the rests out of a notched climb produced exactly that, five 1-frame presses, about 35 minutes for the average profile.
  - The search for the most forgiving way also tends to find slack in a tight design: variants of the Mars hook swing with bigger gaps or overhangs widened to 5-9 frames.
- **Exposed presses are the only knob that works, but it is the wrong one.** Each exposed press adds deaths. That is how 31 reached its time, against the design rule of making difficulty from a few deliberate tight elements.
- **The average profile sits close to the expert.** For the new levels it comes out at about 1.2-1.5 times the expert, not about twice. So the "average ~8-12 min" target cannot be met while the expert stays at 4-6.

**Is the model even right?** The tester data says to be careful:
- The developer cleared the first version of 26 on the first try, with 0 falls, in 1:33. The model gives the expert 2.0 min / 0.8 deaths there, and the developer plays less well than the main tester.
- Water levels came out rated too hard in the calibration.

So the true times of these seven levels are probably shorter than the table says. That leaves them even further from the targets.

## 3. Where the Effort Went

Each world agent worked in three stretches, with two stops at rate limits. The last stretch alone took each agent about 35 minutes, 66-78 tool calls and roughly half a million tokens. The loop was trial and error:

1. Change the geometry.
2. Re-plan the route (minutes each time).
3. Re-assess (1-3 minutes per level).
4. Look at the stills.
5. Check the physics.
6. Probe for shortcuts.
7. Find the time still short, or a new shortcut, and start again.

What made that loop expensive:

- **The planner fails on easy moves in some states, so routes need guide waypoints placed by hand.**

  | Where | What happens |
  | --- | --- |
  | Dash cooldown | A trivial hop onto a cap fails at 120k expansions when the start state still has dash cooldown (DASH=23). The same hop with DASH=0 plans in 9 expansions. |
  | Mid-dash arrival | Arriving at a waypoint in the middle of a dash makes the default planner settings fail. Only the simplest setting succeeded. |
  | Water | The search explodes in and near water. Every pass over a rift, every gap in a trunk and the gap into the whirlpool's eye needed its own guide waypoint. |
  | Mars hook swing | One swing needs 130-150k nodes, which is about the route planner's limit. So every swing has a guide waypoint at its drop point. |
  | Doomed states | The planner stops at the first frame inside a waypoint, even when the player is already doomed there (falling with no jump left). Waypoint boxes have to be placed so that no doomed state can reach them. |
  | Two-wide wells and slots | They need an extra waypoint inside them to plan within the route budget. |

- **There is no shortcut checker.** Each agent wrote throwaway scripts that try routes skipping one or two stops and look for ways over each obstacle. They ran only when there was time. On the final versions of 27, 28, 36, 37 and 38 they did not run at all.
- **Each change needs a full re-check.** Plan, windows assessment, stills and physics take minutes per level and fill the context with output, and every geometry change repeats them.
- **Targets were only checked at the end.** There is no way to estimate the time while designing, so each attempt to raise the difficulty was one more round of the loop.

## 4. A Physics Finding: Dash Wall Climb

The game lets a player climb any single sheer wall, without limit.

**How it works:**
- Hold toward the wall and dash into it.
- Press jump while the dash is active (its first 10 frames).
- While the dash is active it sets the speed to 8 px/frame toward the wall every frame. That overrides the push-off of the wall jump (`scripts/entities.py`, `DASH_*` and `WALL_JUMP_*` in `scripts/constants.py`).
- The player keeps the wall jump's lift and stays on the wall. Wall jumps cost nothing (`jumps` only goes down to 0), and the next dash is ready 60 frames later.

**How fast it climbs:** checked in the replica, which matches the game frame for frame. A 40-row wall on flat ground, one dash and one jump press per second:
- The player rises one row per second: 3.6, 4.7, 5.7, ... rows, 15.0 after 12 s.
- A second jump press later in each cycle makes it a little faster: 17.2 rows after 12 s.
- Without a dash, wall jumps at the same wall top out at 4.5 rows.

**What it means:**
- Any obstacle that is meant to block only by its height can be climbed. The planner found such a shortcut at the end of 31: over the last crag and the 15-row needle to the east rim, without going under the bridge.
- Older levels with lone walls are affected too. Nobody has checked them for it.
- Whether testers use it is unknown.

**Options:**
1. Keep it as an advanced technique, and design so that height alone never blocks: ceilings, overhanging caps, walls that meet a roof.
2. Change the physics, for example so that a wall jump ends an active dash. That changes the route plans of every level, so all of them must be re-planned and re-verified, and the replays recorded so far no longer play back.

## 5. Open Issues per Level

**Shortcuts**
- **31:** the wall climb at the end (section 4). The fix is overhanging caps on the last crag and the needle top, then rebuild and re-check. Crags 1-5 are not proven safe: the planner found no way over them within 150k nodes.
- **27:** shortcut checks were not run. Suspect spots:
  - low cap 5 → east twin cap;
  - the Anvil → Chimney Rock;
  - pin 7 → the Sentinel.
- **28:** shortcut checks were not run. Suspect spots:
  - first shelf → throat ledge 13 (a free fall down the 8-wide throat, past the ledges);
  - the lip → the wadi, over the ridge.
- **36-38:** checked only by looking at the geometry; the probes did not run on the final versions.
- **26:** probed. No real shortcut was found; the probes only skipped one column in the cistern and the balcony rest in the alley.

**Difficulty**
- 37 has no element at 4 frames or less.
- 38 has none in its first half.
- 31 has far more exposed presses than the guideline (25 before the banner, 34 after).

**Breath:** in 36 and 37 the closest call leaves only 2.1 s of breath.

**Visuals**
- 26: the cistern vaults look jagged.
- 27: stems standing on one-row tunnel roofs look thin at the foot. Some slots needed an entrance cut through one wall, so upper parts float.
- 28: the riverbed sinks are cut down to the bottom, so the tunnel floor reads as tall pillars.
- 36: the beach is plain. Large flat rock masses throughout the water levels.
- 38: the air caves inside the rock show the sky through them.

**Not yet tested:** none of the seven levels has been played by a tester.

## 6. What the Next Process Has to Do

These are inputs for the rethink, not decisions.

1. **Estimate before building.**
   - Keep a library of parametrized elements with measured windows, time and death cost: a chimney with a given rest spacing, a cap hop with a given gap and height, a hook swing, a pool leap, a current lane.
   - Compose a level from it to the target, then build and verify it once.
   - The element measurements come from the same windows model, so they are only as good as its calibration (point 5).
2. **Make the planner reliable.**
   - Fix the dash-cooldown and mid-dash failures and the blow-up in water.
   - Routes should plan from a few semantic waypoints, without hand-placed guides.
3. **Add a shortcut checker to `tools/worlds`.** Build it from what the agents did by hand: skip one or two stops, look for a way over each obstacle, search with a fixed node budget. It should report proven, refuted or not proven.
4. **Run all checks with one command.** Plan, windows assessment, stills, physics, banner and shortcuts, with a one-screen summary. This saves agent context and makes the checks the same for every level.
5. **Get real data on the new levels.**
   - Playtests of 26-38 by the main tester and the developer.
   - A death log in the game: position and cause of each death.
   - Then recalibrate (`assess --calibrate`) and check the targets and the average profile against reality.
6. **Decide the wall climb first** (section 4). It changes which geometry blocks a player.
7. **Revisit the targets** once the data is in. A 4-6 minute first clear needs either about twice the content per level or a working middle difficulty step. Right now the model does not offer that step.

## 7. Files

- Levels:
  - `tools/worlds/levels/level_{26,27,28,31,36,37,38}.py`
  - their maps `data/maps/N.json` and route plans `tools/worlds/plans/N.json`
- Shared helpers per world:
  - `tools/worlds/kits/desert.py`
  - `tools/worlds/kits/mars.py`
  - `tools/worlds/kits/water.py` (pools, air pockets, current rings and meshing rings, shift)
- The experimental maps that used to be 26 and 27 are now `data/maps/41.json` and `42.json`.
