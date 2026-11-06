# Level Building Process: Brainstorm

**Date:** 2026-11-06
**Status:** Brainstorm, decided. The user decided D1-D3 on 2026-11-06 (section 6.0), and section 5.1 gives the order that follows from them. Nothing is implemented yet.

The round of levels 26-38 stopped after 7 of 15 levels ([level-building-findings.md](level-building-findings.md)). Only one level reached its time target, and each level took many rounds of trial and error. This document rethinks how a level is planned, designed, rated, tested and put into the game, so that the remaining levels (29, 30, 32-35, 39, 40) are done in a few iterations each.

It builds on the findings (sections 3, 4 and 6 there) and on the rating model in [difficulty-rating-brainstorm.md](difficulty-rating-brainstorm.md). The numbers below come from small measurements made for this document with the tools in `tools/worlds/` (section 8 says how). They ran on the committed levels and plans; no level was changed.

---

## 1. Summary

**What the measurements say:**
- **The planner needs guides because its heuristic does not see walls.**
  - The seven new routes have 122 air waypoints. 89 of them are not needed for their own segment. The other 33 sit at detours: under the Mars hooks, round the whirlpools, past the kelp trunks.
  - A heuristic that follows the air and knows the swim speed and currents plans 120 of the 122 without the guide, with 65-85 % fewer search nodes. Tried after today's first try, it keeps all 22 existing routes planning.
  - The dash cooldown and the water key matter less. Alone, their fixes save 2 and 0 of the 33 needed guides; the water key helps only on top of the new heuristic (2.2).
- **In the model, the time target is a question of length, not of tight elements.**
  - In the calibrated model, one tight element adds at most 2 s to the expert's first clear, even at 1 frame, because P goes right in front of it.
  - Between 2 and 13 frames the window hardly matters (4-9 % misses either way).
  - On levels 26-38, 60-83 % of the predicted time is just playing through. So within the design rules the expert needs about 1.2 x the played-safe time + 15-60 s. 4-6 minutes means 180-270 s of played-safe content; the levels have 84-143 s (2.3).
- **The geometry has few middle steps either.** Gap jumps of 3-9 tiles rate 13 frames almost everywhere, because the dash carries far. Middle windows appear only at the very end of its reach (2.3).
- **The dash wall climb is everywhere in the plans.** 51 % of the plans' wall jumps use it, against 1.8 % in the testers' runs (4.2).
- **Each round costs minutes and a lot of context:** planning 1-2 minutes, rating 1-5, five separate commands with long outputs, and no shortcut check (2.1, 2.4, 2.5).

**Decided by the user (section 6.0):**
- **D1: A.** The dash wall climb stays. Walls that must block get caps or ceilings, and every check scans for climbable walls.
- **D2: a realistic rating comes first.** Length alone adds no tension, and length can be added later. First the rating has to say how hard an element and a whole course really are. Then length and difficulty can be balanced and varied on purpose. The finding above that "the time target is a question of length" is the model's view. The calibration has to test it.
- **D3: yes.** The death log goes in at the one place where every death ends, as the first step, because the calibration needs its data.

**Order (section 5.1):**
1. The death log.
2. The planner fixes, with all levels re-verified once.
3. Rating as players play: no dash climb in the search for the most forgiving way.
4. The calibration course: the library's measuring harness, a test map of graded elements played by the user, and the model refitted per element.
5. One check command with a one-screen summary and a cache.
6. The shortcut checker.
7. The composer, on the calibrated model.
8. A pilot level (29), then the rest, one agent per level.

Together about 16-26 hours of agent work before the pilot. On top come about an hour of compute and about half an hour of the user's play on the calibration course.

---

## 2. Where the Process Snags

### 2.1 The Loop

Each world agent went round this loop (findings section 3): change the geometry, re-plan, re-assess, look at the stills, check the physics, probe for shortcuts, find the time still short, start again. What one pass costs on the committed levels:

| Step | Command | Cost per level | Output |
| --- | --- | --- | --- |
| Plan the route | `build N` | 52-121 s; 1-7 segments per level take 38-88 % of it (2.2) | a few lines; a failure names one waypoint |
| Rate it | `build N --assess` or `assess N --windows` | 126-328 s with the 7 levels at once on 8 cores; the difficulty doc gives 1-3 min for one level alone | one line per element (32-86 lines) and a JSON line with every element and press |
| Look at it | `stills N` | about 1 s (level 38) | one contact sheet to look at |
| Check the physics | `check_physics --maps N --route` | about 2.5 s (level 38) | one line |
| Probe for shortcuts | none: throwaway scripts | minutes to hours | ad hoc |
| Play it in the real window | `play N` | 78-132 s, in real time | a report and screenshots |

Four problems make the loop long:
- the planner needs hand-placed guides (2.2), so every geometry change can break the route somewhere new;
- the time to the first clear is known only after the full rating, at the end (2.3);
- shortcuts are found by hand or not at all (2.4);
- the checks are five commands with long outputs, and each output lands in the agent's context.

### 2.2 The Planner

The planner (`planner.plan_segment`) is a weighted best-first search over input macros: hold a direction for 1, 3 or 8 frames, optionally starting with a jump and/or a dash. A state is pruned when its key has been seen (`planner._key`: rounded position and speed, air time up to 6, jumps, wall, a dash bucket, facing, last direction, breath in seconds, swim cooldown). The heuristic is the straight-line distance in frames: 1 px per frame sideways, 1.5 up, 3 down. `route.plan_route` tries weight 5 with 20,000 nodes, then weight 2 with 120,000.

**Where the time goes on the final routes.** Every segment of the seven new routes (427 in all), planned again from the plan's own states, with the routes' guides in place. Seven levels ran at once on 8 cores, so the seconds run high:

| Level | Segments | Planning time | Segments that needed the weight-2 try | Their share of the time |
| --- | --- | --- | --- | --- |
| 26 | 50 | 74 s | 2 | 61 % |
| 27 | 49 | 79 s | 5 | 86 % |
| 28 | 42 | 121 s | 7 | 88 % |
| 31 | 77 | 56 s | 2 | 38 % |
| 36 | 91 | 57 s | 1 | 53 % |
| 37 | 67 | 59 s | 2 | 69 % |
| 38 | 51 | 52 s | 1 | 85 % |

- 20 segments of 427 needed the fallback, and they take 38-88 % of the planning time.
- Most of them start on dry land and end on a ledge just round an edge: the hanging stairs of 28 (ledges under overhanging lips), the caps of 27, tower room 6 of 26.
- The two in water (37 "the gap into the eye", 38 "deep trunk 13") are the most expensive: 40,000-88,000 nodes after the first 20,000.

**What the guides are worth.** The routes have 122 air waypoints (not ground stops; the flags left out): 4 in 26, 5 in 27, 2 in 28, 14 in 31, 29 in 36, 27 in 37, 41 in 38. Most are guides placed so the planner gets through. Each one was dropped in turn, and the planner went from where its segment starts straight to the waypoint after it, with route.py's two tries:

| | 26 | 27 | 28 | 31 | 36 | 37 | 38 | All |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Guides | 4 | 5 | 2 | 14 | 29 | 27 | 41 | 122 |
| Planned without the guide, planner as it is | 4 | 5 | 1 | 8 | 28 | 22 | 21 | **89** |
| ... with a heuristic that sees the walls (3.2) | 4 | 5 | 2 | 14 | 29 | 26 | 40 | **120** |
| ... with all three fixes (3.2) | 4 | 5 | 2 | 14 | 29 | 26 | 40 | **120** |

- **About 73 % of the guides are not needed for their own segment.** The level files do not say why they are there: left over from earlier geometry, or placed on purpose.
- **The 33 that are needed sit mostly in three places:** the drops under the Mars hooks (31: 6), the whirlpool rings and the eye (37: 5), and the passes over and through the kelp trunks (38: 20). The other two are "into the bell" (28) and the blowhole cave (36).
- **There each failure runs the full 140,000 nodes,** about 20 s. The planner as it is spent 6.0 million nodes on the 122 cases. With all fixes it spent 0.9 million.

**Causes, from the code, with what each fix measured:**

1. **The heuristic does not see the walls. This is the main cause.**
   - It measures a straight line through rock. Wherever the way first goes round something, the search fills the pocket in front of it before it tries the detour: under a hook in 31, round a whirlpool's core and into the eye in 37, over a kelp trunk in 38, round an overhanging lip in 28.
   - A guide at the drop point or the far side turns the detour into two straight lines.
   - A heuristic that follows the air (a distance field, 3.2) alone plans 120 of the 122 cases and spends 70 % fewer nodes.
2. **In water the heuristic is wrong about the speed, and the state key splits states.**
   - The heuristic assumes 1 px per frame sideways and 3 px down. A swimmer moves 0.7 px per frame sideways, 0.2 against a current, and sinks at most 0.83. So in a current the search is pulled toward the goal against the flow, and it underestimates the cost up to 5 times.
   - The key holds the breath in whole seconds and the swim cooldown in 13 values. So the same place at the same speed becomes a new state every second and after every stroke.
   - A coarser water key alone changes nothing (89 of 122). With the distance field it halves the nodes again: 1.77 million, then 0.92 million with all three fixes.
3. **The dash cooldown is a coarse bucket.**
   - The key stores a cooling dash as `100 + |dash| // 16`, so 47 frames of cooldown fall into three buckets.
   - Standing still or any slow move during the cooldown leads to a key that is already seen, and the search drops it. So "wait until the dash is ready, then dash" can only be found through detours that change the position.
   - Measured on a 5-tile gap that needs a dash: 10 nodes with the dash ready, 65 with 10 frames of cooldown left, 499 with 23, 10,463 with 40.
   - Arriving in the middle of a dash is the same problem, with up to 60 frames to wait.
   - The "wait" macro alone saves only 2 more of the 33 guides (two drops in 31), so this cause matters less than the findings suggested.
4. **Arrival is accepted at the first frame inside the box.** `Waypoint.contains` does not ask whether the player can still land. A guide box that a doomed state can reach (falling, no jump left) makes the next segment fail, and the planner does not go back. Not measured here; it shows up as a failure one segment later.

The two cases that still fail with all fixes are both in water with currents: 37 "second eddy bottom" to "the air over the second junction", and 38 "trunk 14" to "the clearing". Pricing water tiles by the current (3.2) is the part of the fix that is still a guess.

### 2.3 Rating: the Time Comes From Length and Exposure

**What moves the expert's time.** The calibrated model (`windows.first_clear`), applied to a test level of 40 free elements of 3 s (120 s played safe) with a banner halfway. The expert's first clear is 144 s, 1.2 times the played-safe time. Then one press is added, or k exposed presses per half:

| Window (frames) | 1 | 2 | 4 | 8 | 13 |
| --- | --- | --- | --- | --- | --- |
| One exposed press, anywhere | +2.0 s | +0.5 s | +0.4 s | +0.3 s | +0.2 s |
| One press whose miss only costs a retry | +1.3 s | +0.3 s | +0.3 s | +0.2 s | +0.1 s |
| 4 exposed per half | +87 s | +18 s | +14 s | +11 s | +8 s |
| 8 exposed per half (the guideline's limit) | +343 s | +49 s | +36 s | +28 s | +19 s |
| 15 exposed per half | +2265 s | +122 s | +86 s | +65 s | +42 s |
| A run of 5 one-frame presses in one element, P in front of it | +20 s | | | | |

What this says:
- **A single tight element adds almost nothing**, even at 1 frame. The model puts the manual checkpoint P right in front of it, so a death there costs only the element itself.
- **Time comes from exposed presses spread over a stretch.** Each one risks the whole way back to the last checkpoint. That cost grows faster than the number of presses.
- **Between 2 and 13 frames the window hardly matters.** The expert misses 4-9 % of such presses, and that rate comes mostly from lapses, not from the window. Only 1-frame presses are clearly harder (27 %).

So within the design rules (at most 8 exposed presses per half, 1-3 tight elements), the expert's time is about **1.2 x the played-safe time + 15-60 s**. Checked on longer test levels, with 4-8 exposed presses per half and one 3-frame highlight per half: 180 s played safe gives 3.9-4.3 min, 270 s gives 5.8-6.4 min. A 4-6 minute target therefore needs about **180-270 s of played-safe content**. Levels 26-38 have 84-143 s. This is the "cliff" of the findings (section 2 there), and it sits in the model: there is no middle step to find in the geometry, because a press of 6 frames costs about the same as one of 12.

The seven new levels show the same split. Each expert first clear is split into three parts: the played-safe time x 1.2, the retries (misses that only cost another try of the element), and the restarts (deaths that send the player back to a checkpoint):

| Level | Played safe | x 1.2 | Retries | Restarts | Expert, first clear | Share of x 1.2 | Exposed presses |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 26 | 109 s | 131 s | 16 s | 51 s | 198 s (3.3 min) | 66 % | 52 |
| 27 | 98 s | 118 s | 43 s | 10 s | 172 s (2.9 min) | 69 % | 13 |
| 28 | 84 s | 101 s | 25 s | 20 s | 146 s (2.4 min) | 69 % | 47 |
| 31 | 128 s | 153 s | 16 s | 85 s | 254 s (4.2 min) | 60 % | 59 |
| 36 | 143 s | 172 s | 30 s | 5 s | 206 s (3.4 min) | 83 % | 16 |
| 37 | 117 s | 141 s | 30 s | 28 s | 199 s (3.3 min) | 71 % | 33 |
| 38 | 91 s | 109 s | 25 s | 12 s | 146 s (2.4 min) | 75 % | 19 |

60-83 % of the predicted time is just playing the level through. The retries add 16-43 s, spread over the 134-304 non-free presses per level. The restarts make the big difference between levels, and they follow the exposed presses: 31 and 26 have the most.

**The geometry has few middle windows too.** A gap jump between two ledges over a void, gap 3-9 tiles, landing 3 rows lower to 2 rows higher, rated by `windows.profile_built` (narrowest window in frames; "2x" = 2 exposed presses):

| Gap (tiles) \ landing | 3 lower | 2 lower | 1 lower | level | 1 higher | 2 higher |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 13 | 25 | 13 (2x) | 13 | 13 | 13 |
| 4 | 13 (2x) | 13 | 13 | 13 | 13 | 13 |
| 5 | 13 (2x) | 13 | 13 | 13 | 25 | 25 |
| 6 | 13 (2x) | 13 | 13 | 13 (1x) | 25 | 22 |
| 7 | 13 (3x) | 13 (2x) | 13 (2x) | 13 (1x) | 14 | 13 (2x) |
| 8 | 13 (3x) | 13 (2x) | 13 (2x) | 12 (2x) | 10 (2x) | 13 (3x) |
| 9 | 13 (3x) | 13 (2x) | 13 (2x) | 13 (3x) | 4 (9x) | 7 (8x) |

- 13 frames is the window of a jump off an edge: up to 12 frames early is fine, a frame late falls. Almost every gap rates 13, because the dash carries about 64 px, so a jump with a dash clears up to 8 tiles.
- Middle windows (4-10) appear only at the very end of the dash's reach (8-9 tiles and higher). There the most forgiving programs get long (up to 18 presses and 5 s, probably catching and climbing the landing's face), and the exposed presses multiply (8-9).
- The results do not change smoothly with the parameters. One row more can make a gap free, as at 5 and 6 tiles and 1 higher (25 frames). A library has to measure its grid and cannot interpolate between points.

### 2.4 Shortcuts

There is no shortcut checker. The agents wrote throwaway scripts that skip one or two stops, and did not run them on the final versions of 27, 28 and 36-38. The dash wall climb (section 4) makes it worse: any wall that blocks only by its height can be climbed, by the planner at about 3-4 rows per second. The planner uses that trick in every route (section 4.2), so a shortcut search with the planner finds such climbs everywhere.

### 2.5 Output and Context

`assess N --windows` prints one line per element and then the whole profile as one JSON line, with every element's press windows and fatal shares. That is several thousand characters per level, read by the agent on every pass. `build --assess` adds the previous metric on top. Five separate commands also mean five chances to forget one: the shortcut probes were skipped on five of the seven final levels.

---

## 3. Options

### 3.1 An Element Library, Composed to the Target Before Building

**Idea.** Parametrized elements, each measured once in isolation with the windows model. The level is composed from them to the target on paper, then built and verified once.

**Why composition can be exact.** The windows model rates each element on its own when the element starts settled, standing on a ledge with the dash ready (`windows.analyse_route`). `first_clear` then only combines per-element numbers: seconds, pass chance and death chance. So a level made of elements that join at settled ledges gets exactly the sum the library predicts. Three things can break this, and the composer has to check them:
- the surroundings: a wall nearby that offers a more forgiving way, or a ceiling that removes one;
- elements started on the move, such as rhythm runs over pillars without a rest; these must be measured as one element;
- the walks between elements, which add played-safe time.

**What goes into the library.**
- Element types with their parameters, as functions that stamp into a `Level` at an entry ledge and return the exit ledge and their semantic waypoints:
  - gap jump: gap, height difference, ceiling, what lies below;
  - cap hop;
  - chimney: width, height, rest spacing;
  - notched climb;
  - hook swing;
  - pool leap;
  - current lane and ring;
  - pillar run.
- Per parameter point: narrowest window, played-safe seconds, presses of 4 frames or less, exposed presses, the fatal share of each press, whether the program uses a dash or the dash climb, and the program itself (it is the seed for the full assessment later).
- A context tag: void, floor or quicksand below, walls within reach.

**The composer** (`compose.py`) reads a level outline: the element list with parameters, the banners and the walks between elements. It prints the predicted first clear per profile, the exposed presses per half and the tight elements per half, against the targets, using `first_clear` itself. After the build, the full assessment is compared element by element. Any element off by more than a tolerance is a context effect and gets flagged.

**What it buys, given 2.3.** The time target is mostly a question of length and exposure. Those are simple per-element numbers: seconds and exposed presses. So the composer hits the target before anything is built. The library also shows the rare middle windows (2.3: only at the end of the dash's reach). The designer no longer has to search for them by trial and error.

**Cost.**
- Writing the element functions: most exist in `builder.py` and the kits.
- The measuring harness and the composer: about 4-6 hours of agent work.
- Measuring: the gap grid of 42 points took 211 s of CPU time (median 1.4 s per point, at most 50 s). Climbs and water elements take longer, so 8 types x 30-60 points is about 10-30 minutes once on 7 cores.
- The library has to be re-measured when the physics or the model changes, for example after decision D1.

**Limits.**
- It is only as right as the calibration (findings, section 6, point 5).
- Elements with water and currents depend on more context than dry jumps.
- The grid has to be measured densely, because the windows are not smooth in the parameters (2.3).

### 3.2 Planner Fixes, So Routes Plan From Semantic Waypoints

**Idea.** A route keeps only semantic waypoints: the stops where elements start (rests, ledges), the banner, the flag, and the section labels the rating uses. The planner finds the way between them on its own. In the probes, three fixes did this for 120 of 122 guides (2.2).

| Fix | What changes | Measured |
| --- | --- | --- |
| **F1 Distance field** | Per goal, a Dijkstra over the tiles that are not solid gives the travel cost in frames. Air costs 16 per tile sideways, 10.7 up, 5.3 down. Water costs 16 over the swim speed plus the tile's current along the move. The heuristic is the larger of the straight line and the field less one tile. In open air the two agree. | alone: 120 of 122 guides not needed; nodes -70 % |
| **F2 Water key** | Breath in 3-second buckets, and only once it is below full. Swim cooldown in 4-frame buckets. | alone: no effect; with F1 and F3: nodes halved again (-85 % in all) |
| **F3 Wait macro** | While the dash cools down, one more macro: hold a direction for exactly the frames until the dash is ready. | alone: 2 more of 33; it matters for the "wait, then dash" moves the findings name |
| **F4 Safe arrival** | An air waypoint counts as reached only by a state that can still land (`windows.saved`). | not measured; removes the doomed-box rule of the findings |
| **F5 Several arrivals** | Keep the first 3-5 distinct arrival states per waypoint. If the next segment fails, try it from the next arrival before giving up. | not measured; covers mid-dash and cooldown arrivals generally |

The ways found without guides are about as long as the designed ones: median 1.03x. The longest is 1.74x, in 38 from the top of the cave chimney to the headland. The planner only finds a way; the rating looks for the most forgiving one anyway.

**Cost.**
- About 150-250 lines in `planner.py` and `route.py`. The field takes 0.03-0.06 s per goal (measured on 31 and 38) and can be cached per goal.
- A regression run: all 22 levels re-planned from their semantic waypoints, then the physics check and the bot run. Mostly compute, about 20-30 minutes.
- **It shifts the ratings.** `windows.most_forgiving` searches with the same planner, so a better planner can find more forgiving programs. All levels need one re-assessment and one re-calibration (`assess --calibrate`) afterwards. The model's numbers in the difficulty doc change a little.

**Benefit.**
- No more hand guides: 122 air waypoints in 7 levels, of which 33 were really needed.
- A geometry change no longer needs a new guide, which removes one round of the loop per change.
- On today's routes the combined search spends about 40 % fewer nodes. Without guides, the hard segments no longer run into the 140,000-node limit (about 20 s each).
- The shortcut checker (3.3) depends on it: a planner that cannot find the intended way cannot be trusted to rule out the unintended one.

**Regression on whole routes: keep today's search as the first try.** All 22 routes were planned again from their saved waypoints with the current physics:
- **F1-F3 instead of today's search:** 18 of 22 plan. 13 ("s5 zigzag"), 21 ("step"), 23 ("cabin ledge") and 25 ("second air") fail. The distance field is not better everywhere: in these four places today's heuristic happens to find the way and the new one does not.
- **Today's weight-5 try first, then F1-F3 at weight 5 and weight 2, then today's weight-2 try as a last resort:** 22 of 22 plan, and the last resort was never needed.
  - On the routes of 26-38 (with their guides) this spends 40 % fewer nodes than today, 0.36-1.14x per level.
  - It still plans 120 of the 122 dropped guides, with 65 % fewer nodes than today.

So the fix is an addition, not a replacement: easy moves stay as they are, and the hard ones get the better search.

### 3.3 A Shortcut Checker

**Idea.** `tools/worlds/shortcuts.py`. For each obstacle or stretch it says **proven** (a way round was found, with its time and position), **refuted** (the search ran out of states, so within its moves there is none) or **not proven** (the budget ran out).

**Three probes, from cheap to expensive:**
1. **Static wall scan (milliseconds).** Every sheer wall face with free air beside it and nothing overhanging its top can be climbed with the dash trick (if D1 keeps it). The scan lists each such wall whose top reaches a place later on the route than its foot.
2. **Skip probes (about a minute per level on 7 cores).** For every waypoint i, plan from the arrival state at i straight to waypoints i+2 and i+3, with a fixed budget of 30,000 nodes. Then compare the time against the designed route. That is what the agents did by hand.
3. **Blocked-trail probes for declared obstacles (about 25 s each).** The level file names its obstacles (a box, a label). The probe makes the designed route's trail between the waypoints before and after the obstacle deadly, so the search has to find another way. The search runs until the goal or until it runs out of states, inside a bounding box round the obstacle. Running out inside the box is the "refuted" answer, and it is cheap because the box is small.

**Cost.** About 3-4 hours for the three probes and the obstacle declarations, plus the planner fixes (3.2), without which the probes report "not proven" too often.
**Benefit.** The shortcut work becomes a fixed step with a yes or no answer, instead of an optional script. It also covers the old levels once.

### 3.4 One Check Command, One Screen

**Idea.** `python -m tools.worlds.check N [--stills] [--full]` runs everything a level needs and prints at most about 40 lines:
- build and save, plan the route, physics check along the route, banner on the route, windows rating, shortcut probes, breath;
- optionally stills and the bot run (`play`), which are slow and only needed at the end.

```
level 39 The Grotto (water)                              check 2 of this level
route      OK   61 waypoints, 0 guides, 98.4 s, planned in 41 s
physics    OK   20,000 frames identical along the route
banner     OK   on the route at element 27 of 52
shortcuts  OK   static 0 | skip 0 of 118 | obstacles 9 refuted, 0 not proven
breath     OK   least 3.8 s left (needle cave)
rating          expert 4.6 min / 0.7 deaths   average 5.8 min / 1.3     target 4-6 / <=0.8
                played safe 196 s, exposed 7 + 6 per half, <=4 frames: 2 + 1
                hardest: kelp gate 3, the eye 4, cave chimney rest 31 8
vs composer     +0.2 min; 2 elements off by >15 %: kelp gate (narrower), ledge 12 (wider)
details    out/check/39/report.json, out/check/39/elements.txt
```

**Caching makes it cheap to run again.**
- The search for an element only reads the tiles near the states it simulates. Keying each element's result by its start state, its goals and the tiles in the box it explored (plus a margin) gives an exact cache.
- After a local change, only the elements whose box touches the change are rated again. Planned segments can be cached the same way.

**Cost.** About 2-4 hours, the cache included.
**Benefit.**
- The loop step shrinks from five commands and thousands of characters to one command and one screen.
- The checks are the same for every level, so none is forgotten.
- Re-checks after small changes take seconds to a minute instead of minutes.

### 3.5 A Death Log in the Game, for Calibration

**Idea.** Today the replay restarts at every respawn, so deaths are invisible (difficulty doc, section 6). The game records each lost life as one JSON line:
- level, attempt, tick and session time;
- position, the respawn point and the last checkpoint reached;
- the cause: fall below the kill line, air time, breath, bullet, out of lives, or restart (R).

**Where it goes.** Every death ends in one place: the death and respawn block in `scripts/state_manager.py`. There `g.dead` counts up, and the level reloads at the respawn point.
- The causes are known where they happen: `entities.py` (air time, kill line, breath), `keyboardManager.py` (R) and `state_manager.py` itself (out of lives). Each site only sets the cause. The central block writes the line once per death.
- A bullet hit only costs a life (`projectile_system.py`). The player dies of it only when no life is left. Hits are therefore logged as events of their own.
- A fall costs no life: the level reloads with the same lives.
- The block calls `replay_mgr.abort_current_run()`. `ReplayManager` has no such method, and the surrounding `try` swallows the error. The block is still the natural place for the log.
- The log must record only a human's play. The route bot (`tools/worlds/play.py`) drives the real game loop with a patched `StateManager`. The benchmark, the trailer and the training runs drive the same game headless.

**Three tiers:**
1. Death log only (`data/deaths/<level>.jsonl`). A few hundred bytes per death. With the replica it pins each death to an element of the route. About 1-2 hours.
2. Also keep the recording of every failed attempt (`data/replays/attempts/<level>/<n>.json`, 400-600 KB each with snapshots, much less without). Then `calibrate` can replay each failed attempt and find the press that missed. About 3-4 hours.
3. Also record dash and jump as different keys, and the mouse dash. The calibration now guesses them from snapshots (difficulty doc, section 6). This changes the replay format, so old replays need a reader for both.

**Benefit.**
- Deaths per element instead of per session. That is the data that can say whether the lapse rate (2.3) is real.
- Bullets are separated from falls; the model does not see bullets (difficulty doc, section 10).

**Cost.** Small code, but it writes into the user's `data/`, so the user decides it. It only pays off with playtests of 26-38.

### 3.6 Smaller Options

- **Level outline first.** Before any code, a short outline file per level: concept, sections, elements with parameters, banners, the composer's prediction. The agent builds from it. It is reviewed once, before building, and costs nothing new.
- **One agent per level, with an iteration budget.** At most three check rounds before the agent stops and reports. A world agent's context filled up with three levels at once.
- **A faster replica.** About 8,000 planner nodes per second in CPython. PyPy or a compiled `step` would speed every tool up 5-20 times. It is a bigger change, and the cache (3.4) gets most of the benefit for re-checks.

### 3.7 Overview

Effort is a rough guess in hours of agent work.

| Option | Effort | Removes | Expected gain |
| --- | --- | --- | --- |
| 3.2 Planner fixes | 3-5 h + 1 h compute | hand guides, the minutes of fallback searches | 120 of 122 guides gone in the probe; all 22 routes still plan; 40-65 % fewer nodes |
| 3.4 Check command + cache | 2-4 h | five commands, long outputs, forgotten checks | one screen per round; re-checks in about a minute |
| 3.3 Shortcut checker | 3-4 h | hand probes | every obstacle proven or refuted |
| 3.1 Library + composer | 4-6 h + 30 min compute | trial and error on the time target | the target is hit on paper; 1-2 build rounds |
| 3.5 Death log | 1-2 h (tier 1) | guessing deaths from session time | calibration per element, once there are playtests |
| 3.6 Outline, agent budget | none | context overflow, open-ended loops | predictable cost per level |

---

## 4. The Dash Wall Climb

### 4.1 What It Is

[level-building-findings.md](level-building-findings.md) section 4 explains it. While a dash is active (its first 10 frames), it sets the speed toward the wall every frame. That cancels the push-off of a wall jump, so the player keeps the wall jump's lift and stays on the wall. Wall jumps cost nothing, so a player can climb any single sheer wall: about one row per second with one dash and one jump a second (the findings' test). The planner does it much faster, 12 rows in 3.3 s. With B1 (4.4) the planner gets 6 rows up a lone wall and not 8.

On a wall the player always faces the wall, and a dash goes the way the player faces. So **every wall jump made while a dash is active is this trick**, whether it climbs a whole wall or only buys one extra hop.

### 4.2 How Much Already Depends on It

Wall jumps made while a dash was active, counted frame by frame in the replica:

| | Wall jumps | During an active dash |
| --- | --- | --- |
| Route plans of levels 11-28, 31, 36-38 (22 plans) | 821 | **420 (51 %)**, in every plan: 1-32 per level |
| Testers' clearing runs, levels 11-25 (15 runs) | 606 | **11 (1.8 %)**, in 5 runs: levels 12, 13, 14 (5), 15, 22 (3) |
| Developer's run of level 26 (first version) | 13 | 1 |

So the planner uses the trick all the time, and the testers almost never do. Many routes the planner found, and many "most forgiving" programs the windows model rates, climb this way. The testers climbed the same walls without it.

### 4.3 Option A: Keep It and Design Around It

The trick stays an advanced technique. Design and tools change:
- **Rule:** height alone never blocks. Every wall that is meant to block gets an overhanging cap or meets a ceiling, or the climb is allowed and leads nowhere useful.
- **Check:** the shortcut checker (section 3.3) has a static scan for walls a player can climb this way, and planner probes for each one.
- **Old levels:** 11-25 were built when nobody knew about the trick. They need the same scan once. Each wall it flags needs a fix or an explicit "allowed".

Cost: no rework of plans or replays. Every new obstacle needs a cap or a ceiling, and each level needs the scan.
Risk: the planner keeps finding the trick everywhere, so the "most forgiving" programs stay unlike what testers play (1.8 %). That bends the windows model.

### 4.4 Option B: Change the Physics

The smallest change: **a wall jump ends an active dash** (B1). The dash counter drops to its cooldown, so the wall jump's push-off applies. The dash's 60-frame cycle stays as it is. A broader variant, **a dash ends when it hits a wall** (B2), changes more runs: 3-168 dash frames per plan, and 14 of 15 testers' runs, push into a wall. B2 is listed only for completeness.

Consequences of B1:
- **Route plans:** every one of the 22 plans has wall jumps during a dash, so every plan has to be re-planned and re-verified (physics check, stills, the bot run). Re-planning each level's saved waypoints with B1 in the replica:

  | Planner | Plans | Fails (at waypoint) |
  | --- | --- | --- |
  | as it is | 6 of 22: 17, 18, 22, 23, 24, 28 | 16, mostly at chimney rests and climbs: 11 "chimney rest ledge", 14 "obelisk rest 1", 16 "canyon chimney rest 44", 19 "giant tree rest 46", 20 "floor chimney rest 131", 36 "needle rest 39", 37 "crack rest 27", 38 "trunks rest 23", ... |
  | combined with F1-F3 (3.2) | 11 of 22: also 12, 19, 20, 21, 31 | 11: 11 "spire rest ledge", 13 "s5 zigzag", 14 "obelisk rest 1", 15 "crater 30 far rim", 16 "canyon chimney rest 44", 25 "geyser", 26 "minaret balcony", 27 "tall cap 0", 36, 37, 38 as above |

  - F1-F3 alone, without today's first try, plan 12 of 22, with 16 and 26 in and 21 out. So "about half" holds for any of the planners tried.
  - The testers' runs of 11, 16, 21 and 25 never use the trick, so they play exactly the same under B1. Those levels can still be cleared, though perhaps not over every rest the route stops at.
  - The rest ledges are one-tile notches on a chimney wall. Getting onto one from the wall below seems to be where the planner leaned on the trick most.
  - So B1 means: about half the levels re-plan by themselves, and about eleven need work. Some of it is the planner (a chimney climb without the trick needs tightly timed wall jumps), and some may be geometry (a rest that can only be reached with the trick).
- **Windows and times:** every level has to be re-assessed, and the tables in [difficulty-rating-brainstorm.md](difficulty-rating-brainstorm.md) section 8 change.
- **Testers' replays:** 5 of the 15 calibration runs use the trick 1-5 times. After the change, the replica no longer meets their snapshots exactly. `calibrate` carries on from the next snapshot, so most of each run stays usable. A `legacy_dash` switch in `physics.py` would keep them exact for calibration. It is only a few lines, but the replica and the game would then differ on purpose.
- **In-game ghosts:** the ghost re-simulates the recorded inputs and is put back on its snapshot every 10 ticks (`scripts/replay.py`). A ghost of a run that used the trick drifts for up to 10 frames and then jumps back. That is a visible glitch, not a broken ghost.
- **Benchmark:** the determinism check of `tools.bench` compares the sessions of one build with each other (`tools/bench/runner.py`), so it keeps working. Its recorded history may shift where the benchmark's runs use the trick.
- **Players:** a technique that 2 % of the testers' wall jumps used goes away.

### 4.5 What It Means for the Process

The decision changes what blocks a player. So it comes before the element library is measured (section 3.1) and before the shortcut checker gets its rules (section 3.3). Either way, the planner and the checker have to see the same physics as the game.

---

## 5. Recommendation

### 5.1 Order

The decisions of section 6.0 set the order. D2 makes a realistic rating the first goal. The balance of length and difficulty can only be set once the rating says how hard an element really is. So the work that produces real player data and checks the model against it comes first, and the composer comes last. The planner stays the base, because the rating's search and the element cut ride on it.

| Step | What | Why at this point | Effort (rough, agent hours) |
| --- | --- | --- | --- |
| 1 | **Death log**, tier 1 (3.5), written in the death and respawn block of `scripts/state_manager.py`; the sites only set the cause | every calibration with real data needs it; playtests can start while the tools are built | 1-2 h |
| 2 | **Planner fixes** F1-F5 (3.2). Re-plan all 22 levels from semantic waypoints, re-verify (physics check, bot run), re-assess | the rating's most forgiving search uses the planner; calibrating before the fix would mean calibrating twice | 3-5 h + about 1 h compute |
| 3 | **Rate as players play.** The rating's search for the most forgiving way gets a mode without the dash climb, that is, no wall jump while a dash is active. An element that can only be done with the trick is flagged as a trick element. The planner and the shortcut checker keep the full physics | with D1 = A the trick stays in the game, but 51 % of the plans' wall jumps use it against 1.8 % of the testers' (4.2); the rating should rate what players do | 1-2 h |
| 4 | **Calibration course and refit** (see below) | the core of D2: a rating that is measured right per element, not fitted from 15 session totals | 4-6 h + about 20-30 min of the user's play per course |
| 5 | **Check command** with its one-screen summary and the element cache (3.4) | every level step uses it | 2-4 h |
| 6 | **Shortcut checker** (3.3) with the static climb scan, wired into the check. One run over 11-38 | with D1 = A the scan is needed on every level; the open shortcut questions of 27, 28, 31 and 36-38 are answered in one go | 3-4 h |
| 7 | **Composer** (3.1) on the calibrated model. Length and difficulty become two parameters to balance on purpose | only now are its per-element numbers worth composing from | 2-3 h |
| 8 | **Pilot:** level 29 built with the new process: outline, composer, build, check. Then the other levels, one agent per level, at most three check rounds each | measures the new process against the old one | 1 + 8 levels |

Steps 5 and 6 can run while the user plays the calibration course.

**The calibration course (step 4).**
- Use the library's measuring harness (3.1) to build a short test map outside the campaign. It holds element families at graded windows: gap jumps at the end of the dash's reach (the only middle windows, 2.3), chimneys of several widths, hook swings, timed swims. Each family covers 2, 4, 8 and 13 frames where the geometry allows.
- A banner goes in front of every element, so a miss costs only that element. The death log then counts attempts and deaths per element: one attempt per death, plus one for the pass.
- The user plays it with the death log on. A few hundred attempts in all is about 20-30 minutes of play. That is enough to see whether the window matters between 2 and 13 frames (the model says 4-9 % misses either way, 2.3). It is not enough to pin small differences.
- Fit the miss chance against the window per element type. Do this by sigma and lapse first, and with per-type parameters only if the data asks for them. Check the closed-loop windows of chimneys and swims (section 7) against the observed misses.
- Check the refitted model against playtests of 26-38: the first clear per level and the deaths per element from the death log.
- Tier 2 of the death log (failed attempts recorded) would give the timing error of each missed press. It is the next step only if the pass and fail counts turn out to be too coarse. It writes much more into `data/`, so the user decides it then.

The finale levels (30, 35, 40) come last in their worlds, as they are the longest. The water finale (40) also needs the library's water entries checked against a playtest first (section 7).

### 5.2 How to Tell the New Process Is Better

Measured on the pilot and then on every level, against the round 26-38:

| Measure | Round 26-38 | Target |
| --- | --- | --- |
| Check rounds until all checks pass | many: a trial-and-error loop, three stretches per world agent | at most 3 |
| Hand-placed guides | 122 air waypoints in 7 levels, 33 of them needed | 0 needed, at most 2 |
| Planning per level | 52-121 s; 20 segments at the weight-2 fallback | no segment at the node limit; under a minute |
| Composer's prediction against the check (expert minutes) | no prediction | within 10 %; at most 1 element in 10 flagged |
| Levels within their time target on the first full check | 1 of 7 | at least 4 of 5 |
| Shortcut checks | hand probes, skipped on 5 of 7 levels | every declared obstacle proven or refuted |
| Agent cost per level | the last stretch of a world agent alone: about 35 minutes and half a million tokens for its 2-3 levels | under 150,000 tokens and 30 minutes per level, everything included |
| Check output read per round | thousands of characters from five commands | one screen |
| Rating against play, per element (calibration course) | not measurable: deaths are invisible | the model's miss chance per element type within the error bars of the observed misses |
| Rating against play, per level (playtests of 26-38) | fitted on 15 session totals | predicted first clear within about 20 % of the observed one (a proposal, to be set with the first data) |

The rating rows come first. Under D2, a level that hits its target on paper only counts if the rating behind it has been checked against play.

---

## 6. Decisions for the User

### 6.0 Decided on 2026-11-06

- **D1: A, keep the dash wall climb and design around it.**
  - Every wall that must block gets a cap or a ceiling.
  - The static climb scan is part of every check, and the old levels 11-25 get it once (4.3).
  - The rating does not play the trick (step 3 in 5.1), so its most forgiving ways stay close to how the testers play.
- **D2: none of (a)-(c) for now. A realistic rating comes first.**
  - In the user's words, length alone would add no tension, and length can still be added later.
  - The first goal is a reliable and effective way to rate how hard elements and whole courses really are. With that, length and difficulty are two parameters whose balance can be set and varied on purpose.
  - Section 2.3 is therefore the current model's view, not a measured fact. Its key claim, that the window hardly matters between 2 and 13 frames, is exactly what the calibration course has to test (5.1, step 4; section 7, "Is the lapse real?").
  - The options below stay as the choices for after the calibration.
- **D3: yes, tier 1, at the one place where every death ends** (3.5). It comes first in the order, because the calibration needs its data.

The text below is the decision brief as it was put to the user.

### D1: The Dash Wall Climb

| | A: keep it, design around it | B1: a wall jump ends an active dash |
| --- | --- | --- |
| Game | unchanged | a few lines in `scripts/entities.py` and the same in `tools/worlds/physics.py` |
| What blocks a player | only overhangs and ceilings; any sheer wall can be climbed (the planner: 12 rows in 3.3 s) | walls block by height again (a lone wall: 6 rows, not 8) |
| Existing plans (22) | stay valid | all re-planned and re-verified once. With the fixed planner 11-12 of 22 plan by themselves; the others need work at chimney rests and climbs (planner or geometry) |
| Testers' replays | play back exactly | 5 of 15 calibration runs diverge at 1-5 wall jumps; a legacy switch in the replica keeps them exact |
| In-game ghosts | unchanged | runs that used the trick jitter for up to 10 frames, then snap back |
| Planner and rating | keep using the trick in 51 % of wall jumps, unlike the testers (1.8 %) | play closer to how the testers play |
| Every new level | needs caps or ceilings on every wall that must block, plus the static scan | no extra rule |
| Old levels 11-25 | need one scan, plus fixes or an explicit "allowed" per wall it flags | covered by the re-verification |

**Lean: A, for now.**
- B1's cost is measured and large: about eleven of 22 levels need rework at their chimney rests and climbs, plus a re-calibration with diverging runs.
- A's cost is a design rule that the kits can carry (the desert kit's hoodoo caps already overhang) and a static scan that takes milliseconds.
- The testers barely use the trick, so it hurts the design tools more than the players.
- Switch to B1 if the scan of 11-38 (step 3) finds many climbable bypasses in the old levels, or if the composer's predictions keep missing at climbs because the model plays them with the trick and the testers do not. Either way, decide before the library is measured.

### D2: What the Time Target Is Made Of

The model puts the expert at about 1.2 x the played-safe time plus 15-60 s (2.3). Tight elements barely move that. For the 4-6 minute target there are three ways:

- **(a) Length.** About 180-270 s of played-safe content per normal level, about twice what 26-38 have. Difficulty comes from a few deliberate tight elements and at most 8 exposed presses per half, as the design rules say. Bigger levels, more building, but predictable with the library.
- **(b) Exposure.** Keep today's length and allow more exposed presses: 15 per half adds about 40-120 s, depending on their windows (2.3). That is level 31's way. It means more deaths, against the rule that difficulty comes from a few deliberate elements.
- **(c) Lower the target for now.** Build to about 3-4 minutes, the length the levels have now, until playtests of 26-38 show the real times. The findings suggest the model rates these levels too long, not too short.

The world finales (15-20 minutes) are far off in every case. With two banners, the best P and 8-15 exposed presses per third, the model needs about 520-750 s of played-safe content for 15-20 minutes. That is 5-7 times the average level of 26-38 (110 s).

**Lean:** (a) for the normal levels, with the playtests of 26-38 as the check before the finales are composed. The finale target should be revisited (findings, section 6, point 7).

### D3: A Death Log in the Game

The game would write a small file per level into `data/` (3.5). Tier 1 (the death log alone) is enough to start. Tiers 2-3 change what gets recorded and the replay format.

**Lean:** tier 1 now, the rest after the first playtests with it.

---

## 7. Open Questions

- **Is the lapse real?** The time model rests on the expert missing 4-9 % of all presses between 2 and 13 frames, whatever the window (2.3). That came from fitting session totals, not from observed deaths. The death log (3.5) is the way to check it. If the lapse is smaller, length matters even more and tight elements even less.
- **Enemies.** The model does not see bullets, and the failed first tries of 13-25 coincide with lives lost to bullets (difficulty doc, section 7.4). An enemy exposure measure per element would be one more library column.
- **The average profile** is still 1.5x the expert's error, assumed from one playtest. With it the average player needs only 1.2-1.5x the expert's time on levels 26-38, so "about twice" in the targets cannot come out of the model.
- **Water elements** were rated too hard in the calibration (21 and 22). Their library entries need a playtest check before the water finale (40) is composed from them.
- **Closed-loop windows** (difficulty doc, section 10): chimneys and swims rate tighter than players feel them. That bends the library the same way it bends the levels, so the composer's prediction stays consistent with the check, but both may be off from reality.

---

## 8. How the Numbers Were Measured

All on the committed maps and plans of 2026-11-06, with the replica in `tools/worlds/physics.py`, on one machine with 8 cores. The scripts were throwaway probes and are not in the repo. Each is small enough to rebuild from this description; the planner work (3.2) would turn the useful ones into tests.

- **Segment costs (2.2):** replay each saved plan in the replica. From the state at the start of each segment, run `route.plan_route`'s two tries against that segment's waypoint. Record the nodes, the seconds and the start state's class (water, dash active, dash cooling, wall, air).
- **Guides (2.2, 3.2):**
  - For every air waypoint k that is not the flag, plan from the state where segment k starts to waypoint k+1, with route.py's two tries (20,000 nodes at weight 5, then 120,000 at weight 2).
  - The same with a copy of `plan_segment` that has the fixes switched on. With all fixes off, the copy expands the same nodes as the original.
  - "Field": a Dijkstra from the goal box over the tiles that are not solid. Costs per tile are in frames: 16 sideways, 10.7 up, 5.3 down in air. In water they are 16 over the swim speed (0.7 sideways, 1.0 up, 0.8 down) plus the tile's current along the move, at least 0.1. The heuristic is the larger of the old straight line and the field less one tile.
  - "Water key": breath in 3-second buckets once it is below full, swim cooldown in 4-frame buckets.
  - "Wait": an extra macro "hold for exactly the frames left until the dash is ready" while the dash cools down.
- **Dash cooldown (2.2):** a 5-tile gap over a void between two flat ledges, the player standing 2 tiles before the edge, its dash counter set to 0, 10, 23 or 40, planned with the route settings.
- **Time model (2.3):** `windows.element_costs` and `assess.time_to_beat` on synthetic element lists: 40 elements of 3 s with three free presses each and a banner after element 20. One element gets an extra press of window w with fatal share 1 (exposed) or 0 (a retry). P is placed where it saves the most, as `first_clear` does.
- **Gap grid (2.3):** a `builder.Level` with a 13-tile ledge, a void, and a 6-tile landing `gap` tiles further and `dh` rows higher. The player spawns 3 tiles before the edge, and one ground waypoint sits on the landing. Rated with `windows.profile_built`.
- **Dash climb in plans and replays (4.2):** every frame where a jump press is taken as a wall jump while the dash counter is above 50. Plans come from `tools/worlds/plans`; the testers' runs from `calibrate.human_run` on `data/replays/last_runs` (read only). The runs of 11-25 meet every snapshot. The files of 26 and 27 are of earlier map versions and match only partly.
- **Climb height (4.1):** a lone wall 40 rows tall on flat ground. The planner (route settings) aims for a box beside the wall 4, 5, 6, 8 and 12 rows up, once with the game's physics and once with B1.
- **Blast radius of B1 (4.4):** `physics.press_jump` patched in the probe's process, so that a wall jump during an active dash sets the counter to 50 (cooldown). Then each level's saved waypoints were planned again: with `route.plan_route` as it is, with `plan_segment` swapped for the copy with F1-F3, and with the combined tries of 3.2. The same three runs with the game's physics are the regression in 3.2.
