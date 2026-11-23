# Difficulty Rating Brainstorm

**Date:** 2026-11-05
**Status:** Implemented. The profiles in section 7.3 are superseded: the rating now plays without the dash wall climb, and sigma, pace and lapse were refitted on 2026-11-16 ([level-building-process-results.md](level-building-process-results.md), section 4.2). Implemented (`tools/worlds/windows.py`, `tools/worlds/calibrate.py`, `python -m tools.worlds.assess --windows / --calibrate`, `build --assess`); calibrated on 16 playtests

The level tools rate how hard a level is before anybody plays it, so new levels can be balanced in the build loop. The rating in use (`assess --playtime`) turned out far too pessimistic against real runs. This document records the evidence, the diagnosis, the options, the method that replaced it (timing windows per element, calibrated on real runs), the calibration, the window profiles of levels 11-38 and the targets for the next levels. No new levels are built until this exists.

---

## 1. The Question

How hard is a level, really, and how long does a player need for the first clear? The answer has to come from the level's geometry and the physics (the levels are built from code, `tools/worlds/levels/level_N.py`), it has to match what testers actually do, and it has to say where a level is hard, not only how hard.

## 2. Evidence: The Old Rating Against Real Runs

**Level 26 ("The Buried City", new, one checkpoint banner halfway).** The developer, the less skilled of the two testers, played it on the first try in 95.8 s without a single fall (one life lost to an enemy bullet). Replay: `data/replays/last_runs/26.json`. Pace per section against the designed (fastest) route:

| Section | outskirts | houses | tower rooms | alley | roof of house Q | high roofs | bell tower beams | dome / minarets | overall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Time / route time | 1.9x | 1.5x | 1.6x | 1.3x | 0.9x | 0.7x | 2.7x | 1.3-1.6x | 1.47x |

The old model predicted for an *expert* on level 26, with the banner and an optimally placed manual checkpoint P: **~5.0 min to clear and ~11.7 deaths**, with "high roof" the worst death hotspot (~2 deaths per clear). Without any checkpoint: 27 min (expert) and 220 min (average).

**Levels 11-25.** The main tester (experienced gamer) played them in one session on 2026-11-03; the times between consecutive clears (failed attempts, restarts and menus included) are in section 7. His clearing runs took 1.4-2.3x the designed route's time, 0-2 lives lost to bullets.

## 3. Diagnosis

1. **Noise on the frame-optimal route.** The old model replays the planner's route with gaussian key timing noise. The planner finds the *fastest* inputs: jumps from the last pixel of a ledge, dashes on the one frame that clears a window. Nobody plays that way: players pick a line with margin. The noise model punishes the planner's choice, not the level.
2. **Open loop.** The inputs are fixed in advance with one correction after 10 frames. Players correct continuously, and they stop on a ledge before a hard jump.
3. **The wrong failure.** A piece "fails" if the player ends more than 10 px from the planned position, even when that is harmless (a jump 3 px further along the same roof).
4. **Never validated on deaths.** The profiles were fitted on clear times of mostly harmless levels. Deaths were never compared with anything.

What the replays added (sections 6 and 7): where the planner's route needs 1-2-frame presses, the testers mostly played with wide windows (median narrowest window per element 15 frames; on level 26 the first tower rooms at 13 frames or more where the planner's route has 1). But they also hit many tight presses without trouble, and their deaths do not sit at the tight moves: they look like occasional blunders and enemy fire, spread over the session.

## 4. Options Considered

| Option | Idea | Verdict |
| --- | --- | --- |
| Retune the old model | smaller sigma, longer pieces | rejected: wrong shape. It still rates the planner's frame-tight line, and the ±10 px criterion makes every long level hard |
| Closed-loop simulated human | a controller that re-plans after a reaction delay, with motor noise | rejected for now: the re-planning is frame-perfect (superhuman), the controller needs many free parameters that 16 playtests cannot pin down, and it is slow |
| Robust planning | search directly for inputs that succeed under a whole bundle of timing errors (a "funnel") | rejected: a much bigger search; per-element windows give most of the benefit at a fraction of the cost |
| Pure replay statistics | rate levels from how testers played them | used for calibration only: it needs playtests of every level and cannot rate a level before it is played |
| **Timing windows per element, calibrated** | for every element of the route find the most forgiving way to play it and measure how many frames each key press may be off; a calibrated precision turns windows into success chances and time | **chosen** |

## 5. The Method

### 5.1 Elements

The designed route is a list of waypoints. An **element** is the stretch from one place a player can stand still to the next: up to the next ground waypoint, or to a waypoint where a player who lets go of all keys comes to rest (a maze cell's floor, a belfry arch; not the top of a chimney). Non-stable waypoints in between are passed in order. Level 26 has 33 waypoints and 33 elements, level 13 has 52 waypoints and 43 elements.

An element starts **settled** (standing still on the ledge before it, dash ready) when the waypoint before it is stable, else on the move from where the element before ended.

### 5.2 Timing windows

A program is a list of per-frame inputs. Its **presses** are jump presses, dash presses and changes of the held direction (start, stop, turn). The **window** of a press is the number of frames it can be pressed on with the element still played through (all waypoints reached in order, standing for ground ones, no death, within the program's length plus 1 s). Each shift of the press (up to ±12 frames) is replayed in the physics replica in two ways:

- **alone**: the other presses keep their frames (timed by the world: a jump at an edge),
- **carried**: the presses after it move along (timed from this press: steering after a jump).

The window counts the more forgiving of the two. A window of 25 frames (both sides free) is "free"; the first press from standing still is always free (any moment to start is as good). Since a dead or harmless outcome of a shifted press usually converges back onto the nominal run (landing on the same floor), runs stop as soon as they reach the nominal state again, which makes a level take 1-3 minutes.

### 5.3 The most forgiving way through an element

Players converge on the most forgiving execution, so the element's difficulty is measured on that one. The search (`most_forgiving`):

1. the route planner with seven settings: coarse input macros (hold a direction 4/8/16 or 6/12/24 frames, the programs people play) before fine ones (1/3/8), with and without dashes,
2. the same from spots on the ledge walked to first (the edge, a little short of it, a run-up back), standing still a moment before the next move,
3. then the tightest presses of the best program are moved a few frames (a dash to the top of its jump) and the rest is planned anew.

Programs are compared by their chance to be played through with a timing error of 1.5 frames, less 1e-4 per frame of length (a much longer way round is not worth a sliver of safety). An element whose best program still has a press of 5 frames or less gets three times the search budget before it is called hard.

### 5.4 Precision, deaths and the time to the first clear

A press with a window of *w* frames hits with **p(w) = (1 − λ) · erf(w / (2√2 σ)) + λ · w / 25**: the player aims at the middle and is off by a gaussian error of σ frames, and with a small chance λ (the lapse) the press is a blunder instead, anywhere within ±12 frames. A free press (25 frames) always hits. An element is played through on one try with the product over its presses. A miss is a **death** if no quick correction lands the player where the element can be gone on from (steer either way or not at all, jump once or not, after 10 frames of reaction; landing deeper than a tile below the lower of the element's start and end is a pit, as good as a death; a swimmer still alive counts as saved; `saved`), otherwise the element is simply tried again (the cost of one more try). A press whose misses mostly kill is **exposed**.

Per element and arrival: time = (tries until through or dead) × (element time × pace + pause before presses of ≤ 4 frames) + deaths × (fall and fade, 1.7 s). Elements chain into stretches between checkpoints (the level's banners, and the manual checkpoint P put where it saves the most); a death sends the player back to the start of the stretch (`assess.time_to_beat`). Results: minutes and deaths to the first clear (with and without P), the chance of a clean first try, the clean run time.

## 6. Replays in the Replica

`tools/worlds/calibrate.py` plays the recorded runs back in the physics replica:

- A replay holds the key events per tick and a snapshot of the player every 10 ticks. **Space (dash) and Up/W (jump) are both recorded as "jump"**, sometimes both on one tick, and a mouse dash is not recorded at all. Every 10 frames all readings of the presses in between (jump, dash, both, nothing) are tried and the one that lands exactly on the next snapshot is kept; a dash without a key event is put where the snapshot's dash counter says it began.
- The main tester played with **Moon Boots** (one extra air jump): 10 air jumps on levels 12 and 13, 1-2 on 18, 19, 23 and 24. The playback models them; pieces with an air jump are left out of the window comparison (the replica cannot shift them).
- **The recording starts over at every respawn** (and the timer too), so a replay is the last life of a run and holds no deaths. Deaths can only be read from the time between clears.
- **Fidelity: every snapshot of all 16 runs (levels 11-26, 8 558 snapshots) is met exactly.**

Each run is laid over the level's elements (the frame it first reaches each waypoint; elements are merged where the run skipped a waypoint), and the window of every press the tester made is measured exactly as for the model's programs.

## 7. Calibration Data and Results

### 7.1 The playtests

From `data/best_times.json` and `data/replays/last_runs` (read only; `calibrate.observations`). "Lost" is the time between two clears less the clearing run and 2 s for the level-complete screen: the failed attempts. A level counts as a clean first try if less than 10 s were lost.

| Level | Player | Clearing run | Since the clear before | Lost | Clean first try | Lives lost to bullets in the run | Air jumps (Moon Boots) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | tester | 85.7 s | (first of the session) | ? | ? | 0 (started with 2) | 0 |
| 12 | tester | 112.4 s | 12.3 min (a break) | ? | ? | 0 | 10 |
| 13 | tester | 130.5 s | 2.2 min | 2 s | yes | 0 | 10 |
| 14 | tester | 150.6 s | 3.3 min | 44 s | no | 1 | 0 |
| 15 | tester | 91.0 s | 1.9 min | 22 s | no | 0 (started with 2) | 0 |
| 16 | tester | 92.0 s | 1.6 min | 0 | yes | 1 | 0 |
| 17 | tester | 93.8 s | 5.0 min | 202 s | no | 2 | 0 |
| 18 | tester | 107.7 s | 1.8 min | 0 | yes | 0 | 1 |
| 19 | tester | 96.5 s | 3.1 min | 90 s | no | 2 | 1 |
| 20 | tester | 95.9 s | 1.6 min | 0 | yes | 1 | 0 |
| 21 | tester | 64.8 s | 1.1 min | 0 | yes | 0 | 0 |
| 22 | tester | 64.9 s | 1.1 min | 0 | yes | 0 | 0 |
| 23 | tester | 40.8 s | 1.6 min | 51 s | no | 0 (started with 2) | 1 |
| 24 | tester | 53.1 s | 0.9 min | 0 | yes | 0 | 2 |
| 25 | tester | 52.5 s | 0.9 min | 0 | yes | 0 | 0 |
| 26 | developer | 95.8 s | - | - | yes (his account) | 1 | 0 |

Levels 13-25: 8 of 13 clean first tries, 6.8 min lost in all (25.6 min for 13 levels). Level 21's clear was no new best (an old 3 s best of another map stands), so its clear time comes from the replay file's time; only the last runs are used (the old best-time replay `data/replays/21.json` is of an older map).

### 7.2 What the testers' presses look like

The clearing runs cut into the same elements as the model (276 elements compared on levels 11-26):

- The model's most forgiving way is at least as forgiving as the tester's run in 175 elements, less forgiving in 101. Median narrowest window per element: model 13 frames, tester 15.
- Where the model misses the forgiving way, the testers found clever ones: on level 26, tower room 1 is a wall jump off the next tower's wall and a dash through its window from the top of that jump (narrowest 14 frames; the model's best is 5).
- But the testers also play **tighter than needed**: their clearing runs hold 3 798 presses, 24 with a window of 1 frame, 61 of 2 frames or less and 144 of 4 or less, where the model's programs for the same levels have 8 presses of 2 frames or less. Many are in wall-jump chimneys, where a player times each jump off the wall contact (closed loop) and the open-loop window understates the slack.
- Hitting all of them by timing alone needs an error of about 0.4 frames in these window units (the chance to hit all 3 798 presses is e^-2.4 at sigma 0.3, e^-11 at 0.5, e^-46 at 1.0). So sigma is an *effective* parameter of the window measure, not a motor precision in milliseconds.

### 7.3 The fit

The deaths are few and spread out, so the profiles are fitted to the **session totals** (`calibrate.fit_precision`): the number of clean first tries (the sum of the predicted chances) and the minutes lost to failed attempts (predicted time to the first clear less a clean run), over levels 13-25. Timing error sigma and lapse rate (the chance that a press is a blunder, anywhere within 12 frames) trade off along a ridge: any sigma up to ~0.5 fits with a lapse of 0.08, sigma 1.0 needs 0.06 and fits worse. The pace is the testers' total time over the model's total time.

| Profile | Fitted on | sigma | lapse | pace | Session check |
| --- | --- | --- | --- | --- | --- |
| expert | main tester, levels 13-25 | 0.4 frames | 0.08 | 1.20 | clean first tries 8.5 predicted / 8 seen; 6.9 / 6.8 min lost |
| average | developer, level 26 | 0.6 (1.5x) | 0.12 (1.5x) | 1.26 | one playtest cannot fit it: 1.5x the expert's error and lapses, assumed |

The least-squares pause before a press of 4 frames or less came out at 0.16 s (expert) and 0 (developer): negligible, as the model's programs already stop on the ledge before each element. The developer's clean first try on level 26 has a predicted chance of 36 % with the average profile (53 % as expert).

Chance that a press is missed, by window (frames):

| Window | 1 | 2 | 3 | 4 | 6 | 8 | 13 | 20 | 25 (free) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expert | 27 % | 8.5 % | 7.1 % | 6.7 % | 6.1 % | 5.4 % | 3.8 % | 1.6 % | 0 |
| average | 47 % | 20 % | 12 % | 10 % | 9.1 % | 8.2 % | 5.8 % | 2.4 % | 0 |

A miss only kills where no quick correction lands the player (an **exposed** press); elsewhere it costs one more try of the element.

### 7.4 Predicted against observed

Minutes to the first clear (with the best P), deaths, and the chance of a clean first try; the previous model's expert prediction for comparison.

| Level | Seen: min | clean first try | New: min | deaths | p(clean 1st) | Previous: min | deaths |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 13 | 2.2 | yes | 2.9 | 0.90 | 0.48 | 2.2 | 0.0 |
| 14 | 3.2 | no | 2.2 | 0.31 | 0.75 | 2.4 | 0.8 |
| 15 | 1.9 | no | 2.9 | 2.79 | 0.18 | 4.4 | 9.7 |
| 16 | 1.5 | yes | 2.1 | 0.10 | 0.91 | 2.4 | 6.2 |
| 17 | 4.9 | no | 2.0 | 0.22 | 0.81 | 1.9 | 0.0 |
| 18 | 1.8 | yes | 1.5 | 0.10 | 0.91 | 1.7 | 1.1 |
| 19 | 3.1 | no | 1.9 | 0.29 | 0.78 | 2.2 | 0.8 |
| 20 | 1.6 | yes | 2.1 | 0.18 | 0.84 | 2.3 | 0.0 |
| 21 | 1.1 | yes | 2.3 | 2.78 | 0.18 | 1.3 | 0.0 |
| 22 | 1.1 | yes | 1.5 | 0.84 | 0.55 | 1.4 | 1.0 |
| 23 | 1.5 | no | 1.2 | 0.40 | 0.72 | 1.1 | 1.1 |
| 24 | 0.9 | yes | 1.9 | 0.86 | 0.52 | 1.9 | 3.1 |
| 25 | 0.9 | yes | 1.3 | 0.10 | 0.91 | 1.4 | 0.2 |
| **13-25** | **25.6** | **8 of 13** | **25.8** | **9.9** | **8.5** | **26.6** | **24.0** |
| 26 (developer) | 1.6 (run) | yes | 2.5 (average) / 2.0 (expert) | 1.33 / 0.75 | 0.36 / 0.53 | 5.0 (expert) | 11.7 |

What it gets right: the totals (time, clean first tries, ~10 deaths for ~7 lost minutes), and level 26 (2.0-2.5 min and about one death instead of 5 min and 12 deaths). What it does not: **which** levels go wrong. Rank correlation of predicted and seen minutes on 13-25 is 0.38 (the previous model, fitted on these very levels, 0.44); the per-level chance of a clean first try scores worse than the base rate (Brier 0.29 against 0.24). The levels with failed attempts are the ones where the tester also lost lives to bullets in his clearing run (1.0 lives per run against 0.25 on the clean levels; level 17, the worst at 202 s lost, is the castle with the murder holes): enemy fire, which the model does not see, is the likeliest cause. The water levels 21 and 22 are rated too hard (long swims with many exposed strokes).

## 8. Window Profiles of Levels 11-38

Elements by their narrowest window on the most forgiving way (frames), exposed presses (a miss kills), the designed route's time and the most forgiving programs' time, and the calibrated first clear (minutes / deaths, with the best P).

| Level | Elements | ≤2 | ≤4 | ≤8 | ≤12 | free (13+) | Exposed presses | Route | Played safe | Expert | Average | Hardest elements (narrowest window) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 46 | 1 | 1 | 0 | 3 | 41 | 19 | 66 s | 85 s | 2.3 / 0.7 | 3.0 / 1.4 | tower top 1, right spire top 3 |
| 12 | 33 | 0 | 0 | 2 | 2 | 29 | 22 | 61 s | 83 s | 2.2 / 1.3 | 2.8 / 2.6 | tower base .. tower top 5, maze 8 |
| 13 | 43 | 0 | 1 | 1 | 1 | 40 | 27 | 70 s | 101 s | 2.9 / 0.9 | 3.8 / 1.6 | s5 zigzag .. s6 box 50 4, s4 exit .. s5 pit 1 6 |
| 14 | 45 | 1 | 0 | 2 | 3 | 39 | 11 | 65 s | 87 s | 2.2 / 0.3 | 2.7 / 0.5 | obelisk rest 2 2, right tower top 7 |
| 15 | 39 | 0 | 2 | 4 | 2 | 31 | 45 | 66 s | 92 s | 2.9 / 2.8 | 4.1 / 6.0 | chimney rest 2 3, crater 46 far rim 4, crater 62 far rim 5 |
| 16 | 44 | 0 | 1 | 0 | 3 | 40 | 4 | 54 s | 86 s | 2.1 / 0.1 | 2.5 / 0.2 | canyon chimney rest 44 4 |
| 17 | 40 | 0 | 0 | 4 | 2 | 34 | 7 | 63 s | 84 s | 2.0 / 0.2 | 2.3 / 0.4 | tower zigzag ledges 2 and 4: 6 |
| 18 | 37 | 0 | 0 | 0 | 0 | 37 | 3 | 51 s | 70 s | 1.5 / 0.1 | 1.7 / 0.2 | none below 13 |
| 19 | 48 | 0 | 0 | 2 | 2 | 44 | 8 | 60 s | 81 s | 1.9 / 0.3 | 2.2 / 0.5 | giant tree rest 39 5, canopy crate 84 5 |
| 20 | 39 | 0 | 0 | 4 | 3 | 32 | 5 | 69 s | 85 s | 2.1 / 0.2 | 2.6 / 0.3 | floor chimney rest 124 5, summit chimney rest 6 |
| 21 | 17 | 0 | 1 | 1 | 0 | 15 | 40 | 44 s | 52 s | 2.3 / 2.8 | 4.2 / 7.3 | chimney .. lighthouse rock 3, arch surface .. arch ledge 8 |
| 22 | 20 | 1 | 0 | 0 | 1 | 18 | 7 | 45 s | 52 s | 1.5 / 0.8 | 2.5 / 3.0 | cave air .. flag rock 1 |
| 23 | 11 | 0 | 0 | 0 | 2 | 9 | 7 | 34 s | 42 s | 1.3 / 0.4 | 1.7 / 0.8 | stern door .. tower top 9 |
| 24 | 24 | 1 | 0 | 0 | 3 | 20 | 22 | 51 s | 62 s | 1.9 / 0.9 | 3.1 / 1.6 | shaft .. flag cave 2 |
| 25 | 21 | 0 | 0 | 1 | 1 | 19 | 5 | 48 s | 55 s | 1.3 / 0.1 | 1.5 / 0.2 | sea stack rest 2 5 |
| 26 (first version) | 33 | 1 | 1 | 2 | 1 | 28 | 18 | 65 s | 76 s | 2.0 / 0.8 | 2.5 / 1.3 | roof of house Q 1, minaret balcony 4, tower room 1 5 |

The first levels built against the targets of section 9 (2026-11-06; what was learned building them: [level-building-findings.md](level-building-findings.md)):

| Level | Elements | ≤2 | ≤4 | ≤8 | ≤12 | free (13+) | Exposed presses | Route | Played safe | Expert | Average | Hardest elements (narrowest window) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26 | 48 | 0 | 1 | 6 | 0 | 41 | 52 | 88 s | 110 s | 3.3 / 2.1 | 4.4 / 3.8 | minaret balcony 3, roof of house Q 5, tower rooms 1 and 7 5 |
| 27 | 44 | 0 | 1 | 3 | 0 | 40 | 13 | 71 s | 98 s | 2.9 / 0.4 | 4.0 / 0.7 | twin stems slot 3, Chimney Rock slot 5, Sentinel slot 7 |
| 28 | 41 | 1 | 0 | 2 | 9 | 29 | 47 | 80 s | 84 s | 2.4 / 1.4 | 3.3 / 2.6 | the spring 2, spring rest 7, swallows' cave 8 |
| 31 | 63 | 1 | 1 | 1 | 10 | 50 | 59 | 96 s | 128 s | 4.2 / 4.2 | 6.3 / 9.3 | u1 shaft 2, u4 shaft 4, u5 basket door 7 |
| 36 | 86 | 0 | 2 | 1 | 14 | 69 | 16 | 96 s | 143 s | 3.4 / 0.6 | 4.0 / 0.9 | needle rest 4, cleft rest 4, step 2 rim 8 |
| 37 | 53 | 0 | 0 | 5 | 1 | 47 | 33 | 98 s | 118 s | 3.3 / 1.0 | 4.4 / 1.8 | crack rest 5, crack top 6, first hull top 6 |
| 38 | 32 | 0 | 1 | 2 | 2 | 27 | 19 | 77 s | 91 s | 2.4 / 0.5 | 3.0 / 0.9 | cave chimney rest 4, the clearing 8, cave chimney rest 31 8 |

Level 26 (first version) in detail: 28 of 33 elements are free. The hard ones are the roof of house Q (1 frame, but a miss only drops the player back into the alley: not exposed), the minaret balcony (4, not exposed either) and tower rooms 1 and 3 (5 and 8 frames; there half or more of the misses end in the quicksand street). The bell tower beams, where the developer slowed to 2.7x, are 13 frames each on the most forgiving way (he played two of them at 5-6).

## 9. Targets for the Next Levels

The calibration says two things for design: a press only becomes hard below ~4 frames (above that, misses are blunders whose rate depends only mildly on the window), and every **exposed** press costs an average player 2-10 % of a death (6 % at the typical 13 frames) however wide its window. So length is cheap as long as it is made of safe elements (wide windows, or a miss that only costs a retry), and difficulty should come from a few deliberate tight elements, not from many exposed ones.

| | Normal level | Hard level / world finale |
| --- | --- | --- |
| Elements | 35-50 (longer is fine) | 40-60 |
| Exposed presses per half (spawn to banner, banner to flag) | ≤ 8 | ≤ 15 |
| Elements with narrowest window ≤ 4 frames | 1-3 per level, at least one per half as the half's highlight | 3-6 |
| Elements with narrowest window ≤ 2 frames | 0-1, not exposed (a miss falls back to retry) | ≤ 2, the exposed one right after the banner |
| Average profile: first clear | 2-3 min, ≤ 1.5 deaths | 3-5 min, ≤ 3 deaths |
| Expert profile: deaths | ≤ 0.8 | ≤ 1.5 |

**Decision (2026-11-05): the new levels aim higher than the table above.** Levels 11-26 clear in about 2 minutes for the main tester, which he found too easy. Targets for levels 26-40, for the expert profile without gear (no Moon Boots):

| | Expert: time to the first clear | Average profile (about twice) | Banners |
| --- | --- | --- | --- |
| Normal level (26-29, 31-34, 36-39) | 4-6 min, rising within a world (the first ~4, the fourth ~6) | ~8-12 min | one, halfway |
| World finale (30, 35, 40) | 15-20 min | ~30-40 min | two, at the thirds |

The rules of the table above still decide *how* a level gets there: length from safe elements (more elements per level is welcome), difficulty from deliberate tight elements (2-4 frames) placed right after the spawn or a banner where a death is cheap, as few exposed presses as the design allows, enemies only as seasoning. Re-check these targets against the next playtests (section 11).

For calibration of the feel: level 18 (0 tight elements, 3 exposed presses) and level 16 (1 tight, 4 exposed) were clean first tries; level 15 (2 tight, 45 exposed presses over crater rims) is the hardest of 11-20 by the model; level 26 (2 tight, 18 exposed, banner halfway) sits at the upper end of the normal target (about 9 exposed presses per half). To raise difficulty, move elements from "free" to 6-12 frames and add a 3-4-frame highlight per half, rather than adding more exposed presses. Use `python -m tools.worlds.build <id> --assess` after each change: it prints the element list with windows, the histogram and both profiles' first clear.

## 10. Limitations and Open Questions

- **No per-level skill yet.** The totals match, the ranking of levels does not (section 7.4). Most likely cause: enemies. Bullets cost lives (three and the level restarts), and the failed first tries coincide with lives lost. A next step is an enemy exposure measure per element (frames spent in an enemy's line of fire, from the projectile system's aim rules).
- **Open-loop windows understate reacting players.** Wall-jump chimneys and long swims come out tighter than players experience them; sigma (0.4 frames) is only meaningful in these units. A closed-loop window (re-time the next press after a shifted one) would fix it at several times the cost.
- **The search misses some forgiving ways** (101 of 276 elements had a wider narrowest window in the tester's run), e.g. wall jump plus dash from the apex. Such elements are rated harder than they are.
- **Testers do not always take the forgiving way**: they play tight to be fast and mostly succeed. "Players converge on the most forgiving way" holds for where they *can* go, not for how they actually play.
- **Moon Boots**: the tester's gear (one air jump) helped on levels 12-13 (10 air jumps each) and saves misses; the model has no gear.
- **Deaths are not recorded**: a replay is the last life only (the recording restarts at every respawn), so where players died is unknown; only time between clears tells how many attempts failed.
- **The average profile is assumed** (1.5x the expert's error and lapses), from a single playtest.
- **Breath, currents and coins** are left to the planner (it keeps breath); detours for coins are in the pace.
- **Run time**: 1-3 minutes per level on one core (level 26: ~2 min; hard elements get a three times longer search), the calibration ~6 minutes on 8 cores.

## 11. Keeping It Calibrated

1. After a playtest, keep `data/best_times.json` and `data/replays/last_runs/` as they are. A run the replica no longer plays back exactly (the level was changed after it was played) is left out, so calibrate before reworking a level that was just tested.
2. Note who played what in `tools/worlds/calibrate.py` (`PLAYED_BY` for levels not played by the main tester, `PLAYERS` for who that is, `FIRST_TRY` for first tries the files cannot show, `BREAKS` for pauses in a session).
3. `python -m tools.worlds.assess --calibrate --json calibration.json`: re-plays every run, checks that each snapshot is met, fits the profiles and prints predicted against observed.
4. Copy the fitted sigma, lapse and pace into `windows.PROFILES` and update sections 7 and 8 here.
5. Better data would help most: a small death log in the game (position, cause: fall or bullet, per attempt) would let deaths be checked per element instead of per session, and a few playtests by a third, less experienced player would fit the average profile.

## 12. Usage

```
python -m tools.worlds.assess 26 --windows            # elements, windows, histogram, first clear (+ previous metric)
python -m tools.worlds.assess --calibrate [levels]    # fit the profiles to the playtests in data/
python -m tools.worlds.build 27 --assess              # build, plan, then the same profile
```

In code: `windows.profile_map(id)` for a saved level, `windows.profile_built(lv)` for a `builder.Level` in memory, `calibrate.human_run(id)` to play a replay back in the replica.
