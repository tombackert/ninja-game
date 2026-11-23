"""Watch a trained policy play its stretch, drawn by the game's own renderer.

    python -m tools.rl.watch 11 9 --span 3                    # live, in a game window
    python -m tools.rl.watch 11 9 --span 3 --video out.mp4    # headless, to an mp4 (needs ffmpeg)

Each seed is played by the policy; the first `--route-seeds` seeds are first
played by the stretch's route blind (what the route does with the enemies
live, no dodging). Episodes use
the evaluation seeds (never seen in training); the policy samples its
actions, as in `python -m tools.rl eval`. A caption names who plays, the
seed and how it ended.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HOLD = 45  # frames the last picture of an episode stays, with its outcome
COLORS = {"goal": (120, 230, 120), "death": (240, 90, 80), "timeout": (240, 200, 90), None: (255, 255, 255)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.rl.watch")
    ap.add_argument("level", type=int)
    ap.add_argument("start", type=int)
    ap.add_argument("--span", type=int, default=3)
    ap.add_argument("--seeds", type=int, default=4, help="seeds the policy plays")
    ap.add_argument("--route-seeds", type=int, default=1, help="seeds that first show the route played blind")
    ap.add_argument("--video", default=None, help="write an mp4 instead of opening a window")
    ap.add_argument("--seed", type=int, default=0, help="seed of the policy's sampling")
    ap.add_argument("--scale", type=int, default=2, help="window / video pixels per game pixel")
    args = ap.parse_args(argv)

    if args.video is None:
        os.environ["NINJA_RL_WINDOW"] = "1"
    os.environ["NINJA_GAME_TESTING"] = "1"  # never write settings or best times

    import pygame
    import torch

    from scripts.renderer import Renderer
    from tools.rl.__main__ import _model_path
    from tools.rl.ppo import EVAL_SEED_BASE, Policy
    from tools.rl.segment_env import SegmentEnv

    path = _model_path(args.level, args.start, args.span)
    if not os.path.exists(path):
        print(f"no model at {path}: train it first (python -m tools.rl train {args.level} {args.start})")
        return 1
    data = torch.load(path, weights_only=True)
    env = SegmentEnv(**data["env"], use_guide=data["env"].get("route_action", False))
    policy = Policy(env.obs_size, env.n_actions, hidden=data.get("hidden", 256))
    policy.load_state_dict(data["state"])
    policy.eval()
    torch.manual_seed(args.seed)  # the policy samples: the same video every time

    g = env.game
    size = (g.BASE_W * args.scale, g.BASE_H * args.scale)
    renderer = Renderer(show_perf=False)
    renderer._render_hud = lambda *a, **k: None  # the caption says what matters
    if args.video:
        out = pygame.Surface(size)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}"]
            + ["-r", "60", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", args.video],
            stdin=subprocess.PIPE,
        )
    else:
        out = pygame.display.set_mode(size)
        pygame.display.set_caption(f"Ninja Game - learned playtester, level {args.level}")
        clock = pygame.time.Clock()
    font = pygame.font.Font(os.path.join("data", "font.ttf"), 8 * args.scale)
    state = {"who": "", "seed": 0, "outcome": None, "quit": False}

    def caption(surface):
        text = (
            f"{state['who']}   seed {state['seed']}   frame {env.frames}   waypoint {env.next_wp}/{len(env.waypoints)}"
        )
        if state["outcome"]:
            text += f"   {state['outcome'].upper()}"
        color = COLORS[state["outcome"]]
        pad = 6 * args.scale
        for dx, dy, c in ((args.scale, args.scale, (0, 0, 0)), (0, 0, color)):
            surface.blit(font.render(text, False, c), (pad + dx, pad + dy))

    def draw():
        g.update_camera()
        renderer.render(g, out)
        caption(out)
        if args.video:
            enc.stdin.write(pygame.image.tobytes(out, "RGB"))
        else:
            pygame.display.flip()
            clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    state["quit"] = True
                    raise KeyboardInterrupt

    def settle_camera():
        p = g.player
        g.scroll = [p.rect().centerx - g.BASE_W / 2, p.rect().centery - g.BASE_H / 2]

    env.on_frame = draw
    results = []
    try:
        for i in range(args.seeds):
            seed = EVAL_SEED_BASE + i
            runs = ["route", "policy"] if i < args.route_seeds else ["policy"]
            for who in runs:
                state.update(who="ROUTE (blind)" if who == "route" else "AGENT", seed=i, outcome=None)
                if who == "route":
                    env.on_frame = None
                    env.reset(seed)  # run_plan resets again; this one only places the camera
                    settle_camera()
                    env.on_frame = draw
                    info = env.run_plan(seed)
                else:
                    env.on_frame = None
                    obs = env.reset(seed)
                    settle_camera()
                    env.on_frame = draw
                    done = False
                    while not done:
                        obs, _r, done, info = env.step(policy.act(obs))
                state["outcome"] = info["outcome"]
                results.append((who, i, info["outcome"], info["frames"]))
                print(f"[watch] seed {i} {who:<6} {info['outcome']:<7} {info['frames']} frames")
                for _ in range(HOLD):
                    draw()
    except KeyboardInterrupt:
        pass
    finally:
        if args.video:
            enc.stdin.close()
            enc.wait()
            print(f"[watch] wrote {args.video}")
    for who in ("route", "policy"):
        mine = [r for r in results if r[0] == who]
        if mine:
            goals = sum(r[2] == "goal" for r in mine)
            print(f"[watch] {who}: {goals}/{len(mine)} reached the goal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
