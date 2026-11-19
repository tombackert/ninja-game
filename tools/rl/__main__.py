"""Learned playtester for the fights along a level's planned route.

    python -m tools.rl threats 11                 # enemies near each segment of the route
    python -m tools.rl train 11 10 --span 3       # PPO on segments 10-12 of level 11
    python -m tools.rl eval 11 10 --span 3        # death rate of the trained policy

`eval` also runs the planned route itself from the same starts (no dodging):
the gap between the two shows what the enemies cost a player who reacts
versus one who does not. Models go to tools/rl/models/<level>_<start>_<span>.pt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

MODELS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def _model_path(level: int, start: int, span: int) -> str:
    return os.path.join(MODELS, f"{level}_{start}_{span}.pt")


def _env_kwargs(args) -> dict:
    return {
        "level": args.level,
        "start": args.start,
        "span": args.span,
        "action_repeat": args.repeat,
        "reaction_delay": args.delay,
        "route_action": not args.no_route_action,
    }


def cmd_threats(args) -> int:
    from tools.rl.segment_env import segment_threats

    print(f"level {args.level}: segment, waypoint, planned frames, enemies near")
    for i, (label, frames, count) in enumerate(segment_threats(args.level)):
        print(f"{i:>3}  {label:<28} {frames:>5}  {'#' * count}{count if count else ''}")
    return 0


def cmd_train(args) -> int:
    import torch

    from tools.rl.ppo import Config, train

    cfg = Config(
        total_steps=args.steps,
        n_envs=args.envs,
        seed=args.seed,
        route_bias=args.route_bias,
        bc_rounds=args.imitate,
        hidden=args.hidden,
    )
    t0 = time.time()
    policy = train(dict(_env_kwargs(args), spread=args.spread), cfg)
    os.makedirs(MODELS, exist_ok=True)
    path = _model_path(args.level, args.start, args.span)
    torch.save({"state": policy.state_dict(), "env": _env_kwargs(args), "hidden": cfg.hidden}, path)
    print(f"[train] saved {path} after {time.time() - t0:.0f}s")
    return 0


def cmd_eval(args) -> int:
    from tools.rl.evaluate import evaluate

    report = evaluate(_env_kwargs(args), _model_path(args.level, args.start, args.span), args.episodes, args.per_start)
    if args.json:
        print(json.dumps(report))
        return 0
    print(f"level {args.level}, segments {args.start}-{report['end'] - 1}, {args.episodes} episodes each")
    for name in ("policy", "route action", "route"):
        r = report.get(name)
        if r is None:
            continue
        print(
            f"  {name:<12} goal {r['goal']:.0%}  death {r['death']:.0%}  timeout {r['timeout']:.0%}  "
            f"kills {r['kills']:.1f}  frames to goal {r['frames']:.0f} (plan {report['plan_frames']})"
            + (f"  planner takes over {r['handoff']:.0%}" if name == "policy" else "")
        )
    for label, goal in report.get("from", []):
        print(f"  from {label:<28} goal {goal:.0%}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.rl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("threats")
    t.add_argument("level", type=int)
    for name in ("train", "eval"):
        p = sub.add_parser(name)
        p.add_argument("level", type=int)
        p.add_argument("start", type=int)
        p.add_argument("--span", type=int, default=3)
        p.add_argument("--repeat", type=int, default=4, help="frames per decision")
        p.add_argument("--delay", type=int, default=12, help="reaction delay in frames")
        p.add_argument("--no-route-action", action="store_true", help="only the agent's own moves, no route action")
        if name == "train":
            p.add_argument("--steps", type=int, default=600_000)
            p.add_argument("--envs", type=int, default=os.cpu_count() or 2)
            p.add_argument("--seed", type=int, default=0)
            p.add_argument("--route-bias", type=float, default=3.0, help="initial preference for the route action")
            p.add_argument("--spread", type=float, default=0.5, help="share of episodes started at a later waypoint")
            p.add_argument("--imitate", type=int, default=0, help="rounds of imitating the planner before PPO")
            p.add_argument("--hidden", type=int, default=256, help="units per hidden layer")
        else:
            p.add_argument("--episodes", type=int, default=200)
            p.add_argument("--json", action="store_true")
            p.add_argument("--per-start", type=int, default=0, help="also play N episodes from every waypoint on")
    args = ap.parse_args(argv)
    return {"threats": cmd_threats, "train": cmd_train, "eval": cmd_eval}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
