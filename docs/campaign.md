# Campaign Overview

The campaign has 41 levels (0-40) in eight chapters. This page lists each level's name, its place in the story and what the player does there. The menus and the HUD show these names, read from `data/levels.json` (name, chapter, story setting; keep it in step with this page). Map files, saves, replays and best times keep the numbers.

Each level has a preview in the level menu, `data/thumbnails/levels/<id>.png`, rendered by `python tools/thumbnails.py [ids]`: a 320x180 frame of the real game from the first 30% of the run, chosen for the most to see (or hand-picked in its `PICKS`), so the finale stays unseen. Locked levels show it pixelated under a padlock.

Levels 0-10 are hand-drawn maps without a written story; their names and settings here are proposals. Levels 11-40 are built from code in `tools/worlds/levels/`, and each file's docstring tells its story in full.

## The Story in Short

A ninja sets out from the floating islands over the clouds, finds the way down into the caves beneath them and, from there, travels to every edge of the world: through ruins and fortresses, deserts and jungles, all the way to the top of Olympus Mons. The road then leads under the sea. Three last journeys follow, each deeper into the past: a desert full of the monuments of forgotten kings, Mars and the traces of whoever was there before us, and the sea floor, where the bones of the leviathan lie.

| Chapter | Levels | World | Arc |
| --- | --- | --- | --- |
| 1 | 0-8 | Sky islands | Learn to move on islands over the clouds, then find the way through ever larger island courses |
| 2 | 9-10 | Underground | The islands' roots: two great cave labyrinths |
| 3 | 11-20 | Journey across the world | Sky ruins, caverns, desert, Mars, jungle; ends on Olympus Mons |
| 4 | 21-25 | The sea | Learn to swim, breathe and ride currents; ends in the abyss |
| 5 | 26-30 | The desert of kings | A buried civilisation; ends on the crown of the Colossus |
| 6 | 31-35 | Ancient Mars | Structures nobody can explain; ends at the top of the Beacon |
| 7 | 36-40 | The deep sea | From the tide pools down to the leviathan; the final level |

## Levels

### Chapter 1: Sky Islands (0-8)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 0 | First Steps | A small island in the clouds, where the journey starts | Run, jump and collect coins on a few grass islands |
| 1 | Island Hop | Islands drift apart over the void | Hops between islands, the first enemies |
| 2 | Broken Bridge | A chain of islands where a stone bridge once ran | Longer hops over floating rocks |
| 3 | The Cliff | A stone cliff hanging under the islands | Ledges along the cliff and islands below it |
| 4 | Sky Course | Rock walls standing in the open sky | Wall jumps and coin trails along walls and platforms |
| 5 | The Ramparts | Ruined stone walls float in the clouds | Wall-jump shafts, ramps and platform chains |
| 6 | Cloud Gardens | Overgrown islands with stone towers | A long course mixing climbs, hops and enemies |
| 7 | The Arch | A great arch of floating platforms | Platform arcs, a first small labyrinth |
| 8 | Sky Labyrinths | The largest island course | Two labyrinths and a long drop to the END island |

### Chapter 2: Underground (9-10)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 9 | Root Caves | Under the islands, earth and stone hold hollow caves | A large cave labyrinth with chambers and tunnels |
| 10 | Deep Labyrinth | The heart of the rock | The largest labyrinth in the game, with many enemies |

### Chapter 3: Journey Across the World (11-20)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 11 | Sky Ruins | The ruins of a city on the islands | Pillar run, a dash chasm, a chimney up a ruined tower, crumbling crates (first crumbling blocks), a ruin labyrinth |
| 12 | Deep Caverns | Caves under the mountains | A drop shaft, a low crawlway over pits (first spikes), a zigzag chimney, a labyrinth, a gauntlet under ceiling spikes |
| 13 | Crate Tower | A storehouse tower full of crates | Six storeys, each a different climb up to the hole in the floor above |
| 14 | Desert | The first desert: dunes, a canyon, a pyramid | Quicksand, sandstone pillars, a stepped pyramid with a tomb labyrinth |
| 15 | Mars | The first landing on Mars | Crater dashes, a mesa chimney, lava tubes under flaming vents (first flame jets), the launch pad |
| 16 | Sandstone Canyons | A plateau cut by canyons | Pillar runs, holed chimneys, wall bounces, a cave labyrinth |
| 17 | Sky Fortress | A castle on an island in the sky | Moat, murder holes, battlements, a sky bridge to the floating keep |
| 18 | Mars Caverns | Lava caverns under the Martian crust | Stalagmites, a free-standing chimney, a tube labyrinth, lava pits |
| 19 | Jungle Temple | A temple in the swamp | Vine pillars, a stepped temple, a gorge, a wall-bounce ladder |
| 20 | Olympus Mons | The highest volcano in the solar system (finale) | A vertical climb inside the volcano to the caldera |

### Chapter 4: The Sea (21-25)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 21 | Coral Lagoon | A shallow lagoon behind a lighthouse | Learn to swim: wading, diving, a reef tunnel with one breathing hole |
| 22 | Kelp Currents | A kelp sea under rock islands | Currents that carry, geysers, a drain into a flooded cave |
| 23 | Sunken Galleon | A shipwreck on the sea floor | Down through the holds, air behind the bulkheads, up the stern tower |
| 24 | Undertow Caves | Flooded caves | Breath management in a flooded labyrinth, drains, a geyser shaft |
| 25 | The Abyss | The deepest trench of the sea (finale) | A drain to the bottom, a current along the floor, a geyser up the whole depth |

### Chapter 5: The Desert of Kings (26-30)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 26 | The Buried City | A city the desert swallowed; only roofs and towers stand out of the sand | Wall jumps in narrow alleys, dashes through tower windows, a cistern under the palace |
| 27 | Hoodoo Valley | A valley of mushroom rocks over quicksand | Climbs between stems, out past the overhanging caps |
| 28 | The Sinkhole | One night the desert floor fell in | The first level going down: ledges tucked under overhangs, into the dark |
| 29 | The Hourglass | A monument of the old kings in the shape of an hourglass | Wide chamber, narrow waist, wide chamber, out on to its crown |
| 30 | The Colossus | A king carved out of a mountain, sitting on his throne (finale) | Climb him: foot, knee overhang, arm and scepter, shoulder, crown |

### Chapter 6: Ancient Mars (31-35)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 31 | Rift Bridge | A rock bridge over a bottomless rift in the crust | Under the bridge from hook to hook, six crossings |
| 32 | The Geode | A lava bubble lined with crystal under the red plain | Round and round up the inside wall to the hole at the top |
| 33 | The Monolith Field | Black slabs, some hovering; nobody knows who set them up | Climbs between monoliths, through a window, over drifting fragments |
| 34 | The Polar Layers | The ice cap, a million years of ice and dust sheets | Storey by storey up through offset cracks, each storey a new obstacle |
| 35 | The Beacon | A lighthouse for ships nobody has seen (finale) | Up the tower, outside along its antenna mast, to the lamp |

### Chapter 7: The Deep Sea (36-40)

| # | Name | Story setting | Gameplay |
| --- | --- | --- | --- |
| 36 | Tide Pools | Low tide on a headland | Leaps out of pools whose rims the waves undercut |
| 37 | The Whirlpool | Two tides meet and the sea never stops turning | Ride eddies, break out at the right moment |
| 38 | Kelp Forest | Kelp on rock pillars under the cliffs | Current lanes up and down, gaps in the trunks, little air |
| 39 | The Drowned City | A coastal town that sank into a cave under the sea | Air only in the attics; alleys with currents, up the bell tower |
| 40 | The Leviathan's Bones | The skeleton of a sea monster in the trench (finale of the campaign) | Through the ribcage, air under the spine, out through the skull's teeth |
