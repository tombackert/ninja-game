"""Physics replica against the real game, over every map of the campaign.

Runs tools.worlds.check_physics on each map (from the planned route where a
plan exists, so the random player also reaches what lies far from the
spawn) and reports how many frames matched. A single differing frame fails
the map.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
from typing import Any, Dict

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

CAMPAIGN = range(26)  # maps 26 and 27 are experimental


def collect(frames: int) -> Dict[str, Any]:
    from game import Game
    from tools.worlds.check_physics import check_map
    from tools.worlds.route import PLANS_DIR

    game = Game(fullscreen=False)
    rows = []
    for map_id in CAMPAIGN:
        planned = os.path.exists(os.path.join(PLANS_DIR, f"{map_id}.json"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            failed = check_map(game, map_id, frames, 1 + map_id, planned)
        wet = re.search(r"\((\d+) of them in water, (\d+) in a current\)", out.getvalue())
        rows.append(
            {
                "map": map_id,
                "frames": frames,
                "identical": not failed,
                "from_route": planned,
                "in_water": int(wet.group(1)) if wet else 0,
                "in_current": int(wet.group(2)) if wet else 0,
            }
        )
        print(f"map {map_id}: {'FAILED' if failed else 'identical'}", flush=True)
    return {
        "frames_per_map": frames,
        "maps": rows,
        "frames_compared": sum(r["frames"] for r in rows),
        "all_identical": all(r["identical"] for r in rows),
    }
