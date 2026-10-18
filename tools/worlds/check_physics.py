"""Verify tools/worlds/physics.py against the real game, frame by frame.

Plays random inputs on real maps with the real `Game` / `Player` (headless)
and the replica side by side, and fails on the first frame where position,
velocity or any movement state differs.

Usage:
    python -m tools.worlds.check_physics [--maps 8 9 10] [--frames 20000]
"""

from __future__ import annotations

import argparse
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

from tools.worlds import physics as ph  # noqa: E402


def real_state(p) -> tuple:
    return (
        p.pos[0],
        p.pos[1],
        p.velocity[0],
        p.velocity[1],
        p.air_time,
        p.jumps,
        p.wall_slide,
        p.dashing,
        p.flip,
        p.last_movement[0],
    )


def check_map(game, map_id, frames: int, seed: int) -> int:
    game.load_level(map_id)
    solids = ph.solids_from_map(game.tilemap.tilemap)
    p = game.player
    s = real_state(p)
    rng = random.Random(seed)
    m, hold = 0, 0
    for f in range(frames):
        if hold <= 0:
            m = rng.choice((-1, 0, 1, 1, -1))
            hold = rng.randint(1, 40)
        hold -= 1
        jump = rng.random() < 0.06
        dash = rng.random() < 0.01
        # Real game: key presses (KeyboardManager), then Game.step()
        if jump:
            p.jump()
        if dash:
            p.dash()
        game.movement = [m < 0, m > 0]
        game.step()
        s, _down, dead = ph.apply_frame(s, m, jump, dash, solids)
        r = real_state(p)
        if r != s:
            print(f"map {map_id} frame {f}: MISMATCH\n real    {r}\n replica {s}")
            return 1
        if dead or game.dead:
            # Respawn both at the spawn point, as the game does
            game.dead = 0
            p.pos = list(p.respawn_pos)
            p.velocity = [0, 0]
            p.air_time = 0
            s = real_state(p)
    print(f"map {map_id}: {frames} frames identical")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", nargs="+", default=["8", "9", "10"])
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    from game import Game

    game = Game(fullscreen=False)
    fails = 0
    for i, map_id in enumerate(args.maps):
        fails += check_map(game, map_id, args.frames, args.seed + i)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
