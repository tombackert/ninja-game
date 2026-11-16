# Level Building Process: Results of Steps 1-7

**Date:** 2026-11-16
**Status:** Steps 1-7 of [level-building-process-brainstorm.md](level-building-process-brainstorm.md) (section 5.1) are implemented and tested. The calibration course is built but not yet played, so the refit of step 4 is still open. The pilot (step 8) has not started.

This document records what was built, what was measured against section 5.2 of the brainstorm, and what is still open.

---

## 1. Summary

| Step | What exists now | State |
| --- | --- | --- |
| 1 Death log | `scripts/death_log.py`, written in the death block of `GameState.update` | done, tested |
| 2 Planner fixes F1-F5 | `planner.py`, `route.py`; 22 levels re-planned from fewer waypoints | done; the planning time target is missed on 4 levels |
| 3 Rate as players play | `windows.DASH_CLIMB = False`, trick elements flagged | done |
| 4 Calibration course | `library.py`, `course.py`, map `calibration` (start with `python app.py --map calibration`) | built; **waits for the user's play**, then `course fit` |
| 5 Check command | `python -m tools.worlds.check N`, exact caches in `cache.py` | done, tested |
| 6 Shortcut checker | `shortcuts.py`: climb scan, skip probes, obstacle probes; climb scan and obstacles run over 11-38 | done; the skip probes proved too slow to run over all levels |
| 7 Composer | `compose.py`: prediction, parts, balance of length and difficulty | done; its numbers wait for the refit |

**Open:**
- The user plays the calibration course. Then `python -m tools.worlds.course fit` refits sigma and lapse.
- Level 31 can be crossed over its crags six times (section 7). It needs caps.
- The other shortcut findings of section 7 need a decision per level: fix the geometry or allow the way.
- Level 38's last element rates far harder than before (4.1). It needs one look.
- The composer's library numbers do not carry over exactly into a built level (section 5).

---

## 2. Step 1: Death Log

- One JSON line per death goes to `data/deaths/<level>.jsonl`. The line is written where every death ends: the death and respawn block of `GameState.update`.
- The sites only name the cause: `air_time`, `fell_out`, `breath` (`entities.py`), `restart` (the R key), `out_of_lives` (the block itself). The first cause wins.
- Other events: `hit` (a bullet takes a life), `save` (the manual checkpoint P), `clear`, `quit`. So every attempt ends in a death, a clear or a quit.
- Every line carries: level, attempt, tick, ticks since the last reload, session time, position, the banners reached, the map file's hash and the gear.
- Only a human's single-player play is logged. `app.main()` switches the log on, and `GameState` hands it to its `Game`. The route bot sets `NINJA_DEATH_LOG=0`. The benchmark, the trailer, the training runs and multiplayer never call `app.main()` or never reach the block.
- `data/deaths/` is in `.gitignore`.

**Side finding, not fixed:** the death block calls `replay_mgr.abort_current_run()`. `ReplayManager` has no such method, and the surrounding `try` swallows the error. It has no visible effect, because `load_level` restarts the recording anyway.

---

## 3. Step 2: Planner Fixes

### 3.1 What Changed

`plan_segment` is unchanged by default: with all fixes off it expands the same nodes as before (checked on 86 segments of levels 13, 27 and 37). The fixes are switches:

| Fix | Switch | What it does |
| --- | --- | --- |
| F1 | `field` | Heuristic from a distance field round the goal (48 tiles sideways, 32 up and down) |
| F2 | `water_key` | Breath in 3-second buckets, swim cooldown in 4-frame buckets |
| F3 | `wait` | A macro that holds on until the dash is ready |
| F4 | `safe` | An air waypoint is reached first by a state that can still land; others only once the search is spent |
| F5 | in `route.plan_route` | Up to 4 distinct arrivals per waypoint; the next segment is tried from each before the route fails |

`route.plan_route` runs four tries per segment: today's search at weight 5, the fixed search at weight 5 and at weight 2, and today's search at weight 2 as the last resort.

### 3.2 Guides

A guide candidate is an air waypoint where a player who lets go of the keys does not come to rest. Ground waypoints and resting places are stops of the design and stay. `python -m tools.worlds.guides` asks of each candidate whether the planner gets from before it straight to the waypoint after it.

| | Levels 11-25 | Levels 26-38 | All 22 |
| --- | --- | --- | --- |
| Candidates | 94 | 60 | 154 |
| Dropped from the level files | 76 | 56 | 132 |
| Still needed, now marked `guide=True` | 11 | 2 | 13 |
| Kept: the way without it is at least 20 % shorter and misses its box | 6 | 2 | 8 |
| Kept for another reason | 1 | 0 | 1 |

- **The 13 guides:** level 13 (3), 22 (2), 23 (5), 25 (1), 31 (2: `u1 drop 3`, `u4 drop 2`).
  - In level 23, three of the five plan without the guide one by one, but the route then fails at "cabin ledge". All five stay.
- **The 8 kept ones are possible shortcuts.** The planner found a shorter way that does not pass the waypoint: level 12 "tower base", 13 "s4 exit", 23 "room C air", 24 "air over 1,0" and "air over 3,0", 25 "third air", 37 "the air over the second junction" and "the eye". They are listed again in section 7.
- Against 5.2 ("0 needed, at most 2"): met on 26-38 (2 guides in 7 levels, both in 31). The old water levels 22, 23 and 25 still need 8.

### 3.3 Planning and Verification

All 22 routes plan. The last resort was never needed. Planned with 8 levels at once on 8 cores:

| Level | Waypoints (before) | Planned in | Nodes | Segments that needed the weight-2 try |
| --- | --- | --- | --- | --- |
| 11 | 44 (52) | 54 s | 174,000 | 0 |
| 12 | 35 (43) | 28 s | 107,000 | 0 |
| 13 | 47 (52) | 260 s | 132,000 | 0 |
| 14 | 43 (50) | 41 s | 148,000 | 0 |
| 15 | 39 (47) | 64 s | 161,000 | 1 |
| 16 | 44 (49) | 64 s | 217,000 | 0 |
| 17 | 40 (42) | 31 s | 125,000 | 0 |
| 18 | 36 (44) | 25 s | 91,000 | 0 |
| 19 | 48 (50) | 64 s | 220,000 | 0 |
| 20 | 39 (42) | 65 s | 227,000 | 0 |
| 21 | 17 (21) | 23 s | 79,000 | 0 |
| 22 | 22 (26) | 20 s | 81,000 | 0 |
| 23 | 20 (20) | 17 s | 52,000 | 0 |
| 24 | 28 (36) | 45 s | 92,000 | 0 |
| 25 | 23 (27) | 14 s | 55,000 | 0 |
| 26 | 48 (50) | 52 s | 185,000 | 0 |
| 27 | 44 (49) | 108 s | 290,000 | 2 |
| 28 | 41 (42) | 54 s | 179,000 | 0 |
| 31 | 65 (77) | 220 s | 609,000 | 5 |
| 36 | 85 (91) | 27 s | 143,000 | 0 |
| 37 | 54 (67) | 158 s | 321,000 | 2 |
| 38 | 34 (51) | 72 s | 185,000 | 0 |

Against 5.2 ("no segment at the node limit, under a minute"):
- **Weight-2 fallbacks on 26-38:** 9 segments, against 20 before, and with 56 fewer waypoints.
- **The time target is missed on 13, 27, 31 and 37.**
  - Level 13 spends its time on one F5 step back at "s5 chimney base".
  - Levels 27, 31 and 37 pay 20,000 nodes for today's first try on every hard segment before the fixed search runs. With their old guides in place the same levels planned in 56-95 s.
  - This is the cost of keeping today's search first. Swapping the order regressed four old routes in the brainstorm's probe, so it stays.
- The check command caches planned segments, so a level pays this once per changed stretch, not once per check.

Verification of the 22 new plans:
- The maps are byte-identical to the committed ones. Only waypoints changed.
- `check_physics --route`: 20,000 frames identical on every map.
- The banner is on the route on every level that has one (26-38).
- No death in the replica. Least breath on the route: unchanged within 0.4 s, except level 22 (1.1 s, was 2.5 s). Levels 23-25 were at 0.0-0.1 s before and still are.
- `tools/trailer_replays/25-best.json` (the benchmark's water run) is the plan of level 25 by construction. It was rebuilt from the new plan the same way.
- **The route bot in the real window:** all 22 levels cleared on the first attempt (`python -m tools.worlds.play`, one level at a time, 35-162 s each). The bot lost lives to enemy fire on levels 12 (4, one restart of the level), 17 (2), 18 (1) and 20 (1), none on the other 18. On 26-38 it never had to re-plan.
  - The first attempt (2026-11-06) ran while two other jobs used all cores, and the bot hung in level 11. Alone, it clears level 11 on the first attempt in 73.5 s without losing a life. The bot's re-planning now uses the fixed search too.

---

## 4. Step 3: Rating as Players Play

- The rating's search for the most forgiving way no longer uses the dash wall climb: no wall jump while a dash is active, and none in the frame a dash is pressed (`planner.dash_climb_press`). Programs that contain it are rejected, the designed route's own program included.
- An element with no way without the trick gets one deeper search (the route's first two tries, without the trick). Only if that fails too is it rated with the trick and flagged as a trick element.
- The press windows themselves are still measured with the game's full physics. A mistimed press does what it does in the game.
- The planner, the route and the shortcut checker keep the full physics.
- A sheer block of 5 rows or more is only climbed with the trick (measured: 4 rows without, 5-7 only with it).

### 4.1 How the Ratings of 26-38 Shift

Expert profile, minutes to the first clear / deaths. The first two columns use the same profile (sigma 0.4, pace 1.2), so they show the trick alone. The last column uses the refitted profile of 4.2.

| Level | With the trick | Without (as players play) | Trick elements | Refitted profile |
| --- | --- | --- | --- | --- |
| 26 | 3.2 / 2.0 | 2.8 / 1.4 | none | 3.0 / 1.4 |
| 27 | 3.1 / 0.3 | 3.3 / 1.3 | tall cap 0 | 3.5 / 1.9 |
| 28 | 2.4 / 1.5 | 2.3 / 1.3 | none | 2.6 / 1.3 |
| 31 | 4.4 / 4.6 | 4.4 / 5.1 | none | 4.7 / 6.2 |
| 36 | 3.7 / 0.8 | 3.8 / 1.5 | needle rest 39 | 4.0 / 2.2 |
| 37 | 3.9 / 2.2 | 3.2 / 0.4 | crack rest 27, first hull top | 3.4 / 0.4 |
| 38 | 2.5 / 0.3 | 3.4 / 1.4 | cliff top | 6.1 / 5.8 |

What this says:
- **Five elements in 26-38 cannot be played without the trick** within the search's budget. They are flagged. A tester should try them: either the search misses a way, or the level asks for a technique 2 % of wall jumps use.
- **The shifts are small and go both ways.** 27, 36 and 38 get harder without the trick, as expected. 26 and 37 get easier, which a perfect search could not produce: without the trick every way is also a way with it. The search is a heuristic with a node budget, and the deeper fallback search found more forgiving ways for some elements. So differences below about half a minute are search noise, not level difficulty.
- **Level 38 is an outlier under the refitted profile** (6.1 minutes, average profile 49 minutes). Its last element, from the cave chimney's rest to the headland, now rates at 1 frame with 10 presses of 4 frames or less. The old route had a waypoint at the chimney's top. Most likely the search misses the forgiving way there. It needs one look before 38 is judged.
- All seven levels stay below the 4-6 minute target, as before.

### 4.2 Re-calibration on the Testers' Session

`python -m tools.worlds.assess --calibrate --jobs 8`, on the new routes, rating without the trick (levels 13-25, the main tester's session of 2026-11-03):

| Profile | sigma | lapse | pace | Session check |
| --- | --- | --- | --- | --- |
| expert, before | 0.4 | 0.08 | 1.20 | 8.5 clean first tries predicted / 8 seen; 6.9 / 6.8 min lost |
| expert, with the trick (new routes) | 0.3 | 0.08 | 1.21 | 8.4 / 8; 6.8 / 6.8 |
| **expert, without the trick** | **0.6** | **0.08** | **1.25** | 8.2 / 8; 6.8 / 6.8 |
| average (1.5x the expert, assumed) | 0.9 | 0.12 | 1.26 | one playtest |

`windows.PROFILES` now holds the third row. With sigma 0.6 the chance to miss a press is:

| Window (frames) | 1 | 2 | 3 | 4 | 6 | 8 | 13 | 20 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expert | 45 % | 16 % | 8.2 % | 6.8 % | 6.1 % | 5.4 % | 3.8 % | 1.6 % |
| average | 62 % | 35 % | 19 % | 12 % | 9.2 % | 8.2 % | 5.8 % | 2.4 % |

- The lapse did not move. Between 4 and 13 frames the model still says the window hardly matters (7-4 % misses).
- Below 4 frames the refit is steeper than before: a 2-frame press now misses 16 %, not 8.5 %.
- This is still a fit to 13 session totals. Sigma moved from 0.3 to 0.6 with the same data and a changed search, which shows how weakly the totals pin it. The calibration course is the real test.

---

## 5. Step 4: Calibration Course

- `tools/worlds/library.py` holds the element types (`gap`, `chimney`, `hook`, `pillars`) and the measuring harness: one element on its own between two ledges over a void, rated with the windows model. Results are cached in `tools/worlds/library/<kind>.json` under a hash of the model's code.
- `tools/worlds/course.py` picks, per family, the measured points closest to 2, 4, 8 and 13 frames, and builds the course: a banner before every element, every element over the void. So a miss is a death, and a death costs only that element.
- The map is `data/maps/calibration.json`. It has a name, not a number: the menu lists only numbered maps, so it is outside the campaign. Start it with `python app.py --map calibration`. Its death log is `data/deaths/calibration.jsonl`.
- `python -m tools.worlds.course fit` counts deaths and passes per element from the log and refits sigma and lapse by maximum likelihood. It fits the families separately too, and a likelihood-ratio test says whether they need parameters of their own. Its table per window class answers the question of decision D2: does the window matter between 2 and 13 frames?
- The fit is tested on synthetic data: it recovers the sigma and lapse the data was drawn from.

**The course as built** (`python -m tools.worlds.course measure`, then `build`):

- The library measured 52 points in 2 minutes 40 seconds on 7 cores. 11 elements were picked.
- The route through the course takes 63 s. The replica matches the game on it for 20,000 frames.
- `course fit` rates the course itself and attributes each death by its place, so it does not depend on which banners a player touched.

| Element | Library, alone (narrowest window) | In the course | Expected deaths per attempt (expert / average) |
| --- | --- | --- | --- |
| gap 3 | 13 | 13 | 0.00 / 0.00 |
| gap 2 | 8 | 13 | 0.18 / 0.26 |
| gap 1 | 3 | 13 | 0.05 / 0.08 |
| chimney 2 | 13 | 13 | 0.21 / 0.30 |
| chimney 1 | 8 | 13 | 0.08 / 0.13 |
| hook 4 | 13 | 3 | 0.16 / 0.32 |
| hook 3 | 7 | 4 | 0.15 / 0.24 |
| hook 2 | 4 | 8 | 0.12 / 0.20 |
| hook 1 | 2 | 7 | 0.22 / 0.38 |
| pillars 2 | 13 | 13 | 0.07 / 0.12 |
| pillars 1 | 6 | 13 | 0.08 / 0.14 |

**Two findings from building it:**
- **Library numbers do not carry over exactly.** 6 of 11 elements rate differently in the course than alone. The brainstorm (3.1) expected exact composition for elements that start settled. Two things break it here: the gates and ledge lengths change where an element starts, and the search for the most forgiving way is noisy (4.1). The fit is not affected, because it uses the course's own rating. The composer is: its prediction cannot be trusted to 10 % yet.
- **The course grades less finely than planned.** It has windows of 3, 4, 7, 8 and 13 frames, seven of them at 13. It still tests the model's main claim: the model expects 5-22 % deaths per attempt on elements that all count as "free or nearly free", and 0 % on the first gap. About 20 attempts per element (220 in all) separate those rates.
- Chimney misses mostly slide back to the ledge instead of falling, so chimneys add few deaths to count.

**Limits:**
- There is no timed swim in the course. A swimmer only dies of breath, so a miss in water is not a death and the tier-1 log cannot count it.
- Tier 2 of the death log (recordings of failed attempts) is not built. It is the next step only if these counts turn out too coarse.

---

## 6. Step 5: Check Command

`python -m tools.worlds.check N` builds and saves the level, plans the route, checks the physics along it, the banner, the shortcuts and the breath, and rates it. It prints at most 16 lines; details go to `out/check/N/`.

```
level 9004 Test Steps (stone)                              check 1 of this level
route      OK   3 waypoints, 0 guides, 5.0 s, planned in 1 s (0 of 3 cached segments)
physics    OK   1500 frames identical along the route
banner     OK   on the route at element 2 of 3 (by the route: the rating's programs pass it by)
shortcuts  OK   climbs 0 walls, 0 proven | skip 0 of 3 proven | obstacles 0 refuted, 0 proven, 0 not proven (6 s)
rating          expert 0.2 min / 0.0 deaths   average 0.2 min / 0.0
                played safe 8 s, exposed 0 per half, <=4 frames: 0, trick elements 0
                hardest: second ledge 13, third ledge 13
                rated in 1 s (0 of 3 cached elements)
details    out/check/9004/report.json, out/check/9004/elements.txt
```

- **The cache is exact.** A search records the box of every position the physics steps from, and the tiles its distance fields cover. Its result is stored with a hash of the tiles and water in that box. A later lookup is a hit only if those tiles are unchanged. The kill line and a hash of the code are part of the key.
- After a change far from an element, the element's rating and its route segments come from the cache. The test runs the check twice on a small level: the second run takes every segment and every element from the cache and gives the same first clear.
- `--stills` and `--play` add the contact sheet and the route bot. `--fresh` ignores the caches.

---

## 7. Step 6: Shortcut Checker

`python -m tools.worlds.shortcuts N` runs three probes. Each finding is proven, refuted or not proven.

1. **Climb scan:** every sheer face of 5 rows or more with open air beside it and nothing over its top, whose climb would skip at least 1.5 s of the route. Each wall is then probed with the planner.
2. **Skip probes:** from each waypoint straight to the second and third one after it, with the skipped waypoints walled off, 30,000 nodes each. Off by default in the check.
3. **Obstacle probes:** for obstacles a level file declares with `lv.obstacle(...)`. The designed trail through the obstacle is blocked, and the search stays inside a box (60,000 nodes). If no open tiles connect the two sides, it is refuted at once. Level 31 declares its six crag crossings.

**One run over all 22 levels** (climb scan and obstacle probes, 62 s on 7 cores):

| Level | Walls the scan lists | Climbs proven shorter | Not proven |
| --- | --- | --- | --- |
| 11 | 2 | 0 | 0 |
| 12 | 2 | 2 | 0 |
| 13 | 12 | 3 | 5 |
| 14 | 6 | 3 | 0 |
| 15 | 5 | 2 | 1 |
| 16 | 4 | 1 | 0 |
| 17 | 9 | 5 | 2 |
| 18 | 7 | 6 | 0 |
| 19 | 1 | 0 | 1 |
| 20 | 9 | 6 | 2 |
| 21 | 4 | 1 | 0 |
| 22, 23, 25 | 0, 1, 1 | 0 | 0 |
| 24 | 2 | 1 | 0 |
| 26 | 3 | 2 | 0 |
| 27, 28, 36 | 2, 2, 1 | 0 | 0 |
| 31 | 9 | 2 | 0 |
| 37 | 4 | 1 | 2 |
| 38 | 9 | 0 | 1 |

- **Level 31: all six crag crossings are proven open.** With the trail down through the hole blocked, the planner gets over each crag on the bridge's back with the dash wall climb, in 4-11 s instead of the 8-18 s under the bridge. The level's whole idea, "the crossing goes underneath", can be skipped six times. Under decision D1 = A the crags need overhanging caps (or a ceiling), then one re-check.
- **35 climbs are proven shorter in 13 levels**, most of them by about 2 s. Most are walls of chimneys and zigzags the route climbs anyway, rest by rest: the trick takes the wall in one go. They skip rests, not sections. The larger ones deserve a look: level 13 (a 7-row wall, 3.5 s instead of 10.3 s), 15 (a 12-row wall), 20 (7 rows, 2.8 s instead of 6.2 s), 37 (a 14-row wall near the end, 5.0 s instead of 8.6 s).
- "Not proven" means the probe's 15,000 nodes ran out. A wall of 66 rows in level 13 is in that group.
- Only level 31 declares obstacles so far. The suspect spots of 27 and 28 in the findings (section 5 there) need declarations to be answered; the climb scan found no proven climb in either.

**Skip probes were not completed.** One run over levels 26-38 was stopped after 35 minutes. Two probes of up to 30,000 nodes per waypoint cost about 25 CPU minutes per level, not the minute the brainstorm estimated. They are therefore off in the check by default (`--skips` adds them). The 8 waypoints of section 3.2 that the guide analysis kept are the skip candidates it already found.

---

## 8. Step 7: Composer

`python -m tools.worlds.compose outline.json` reads a level outline (elements with parameters, walks, banners), takes each element's numbers from the library and combines them with `windows.first_clear`, the same function the check uses.

It prints, per profile:
- the first clear and the deaths;
- the time split into three parts: played-safe time x pace (length), retries and restarts (difficulty);
- exposed presses and tight elements per half.

`balance` prices the distance to a target in both currencies: seconds of played-safe length at this difficulty, or exposed 8-frame presses per half at this length. `stamp` builds an outline into a level; the calibration course is built this way. The check prints a "vs composer" line when `tools/worlds/outlines/N.json` exists.

The composer's numbers are only as good as the model's parameters. They are worth composing from once the course has been played and the model refitted.

---

## 9. Why the First Attempt Stalled

The first attempt at these steps (2026-11-06) did not finish. The causes, for the next round of work:

- **Whole-campaign runs for every question.** Each check was a run over all 22 levels: re-plan (3-8 minutes), rate (11 minutes per mode), bot (40 minutes). Several ran at once on 8 cores. The load reached 76, every run took 3-5 times as long, and the bot hung.
- **Step 2 grew.** "Drop the guides" meant editing all 22 level files, re-planning them and rebuilding a benchmark replay. That was the largest block of work, and the pilot does not need it for the old levels.
- **An unbounded search in the rating.** The fallback for elements without a trick-free way ran up to 160,000 nodes per goal. The rating of the 22 levels did not finish. It is now capped at 40,000, and 15 levels rate in under 7 minutes on 8 cores.
- **No intermediate commits.** All seven steps sat in one working tree, so no step could be called done.
- **A cost estimate taken on trust.** The skip probes were planned at a minute per level and cost 25 CPU minutes. The run had no progress output and no partial results, so it could only be waited for or thrown away.
- **A test wrote into `data/`.** The death log's "clear" test saved a best time for map 9002 into `data/best_times.json`. The entry was removed, and the tests now redirect best times and replays.

What changed in the way of working: one measurement run per question, runs one after another instead of side by side, and sampling (26-38) where the full set adds little.
