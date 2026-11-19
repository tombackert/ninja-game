"""Death rate of a trained policy on its stretch, next to the planned route's.

For every goal the agent reaches, the planner is asked to take over from
there to the level's next waypoint (`handoff`).

Episodes use seeds from EVAL_SEED_BASE on, which training never sees. The
policy samples its actions (a player is not the same every attempt).
"""

from __future__ import annotations

import os

from tools.rl.ppo import EVAL_SEED_BASE


def _summary(results: list) -> dict:
    n = len(results) or 1
    goals = [r["frames"] for r in results if r["outcome"] == "goal"]
    return {
        "episodes": len(results),
        "goal": sum(r["outcome"] == "goal" for r in results) / n,
        "death": sum(r["outcome"] == "death" for r in results) / n,
        "timeout": sum(r["outcome"] == "timeout" for r in results) / n,
        "frames": sum(goals) / len(goals) if goals else float("nan"),
        "waypoints": sum(r["waypoints"] for r in results) / n,
        "kills": sum(r.get("kills", 0) for r in results) / n,  # per episode
        # of the goals: the planner took over from where the agent arrived
        "handoff": (
            (sum(r.get("handoff", True) for r in results if r["outcome"] == "goal") / len(goals))
            if goals
            else float("nan")
        ),
    }


def evaluate(env_kwargs: dict, model_path: str | None, episodes: int = 200, per_start: int = 0) -> dict:
    """`per_start` > 0 also plays that many episodes from every waypoint of
    the stretch on (report["from"]: label and goal share per start): where in
    a long stretch the agent fails."""
    import torch

    from tools.rl.ppo import Policy
    from tools.rl.segment_env import SegmentEnv

    # The guide backs the route action; without one, it only teaches
    env = SegmentEnv(**env_kwargs, use_guide=env_kwargs.get("route_action", False))
    report: dict = {"plan_frames": env.plan_frames, "enemies": None, "end": env.end}
    route = [env.run_plan(EVAL_SEED_BASE + i) for i in range(episodes)]
    report["enemies"] = len(env.game.enemies)
    report["route"] = _summary(route)
    if env.actions[-1] is None:  # the route action alone: what the agent adds to it
        results = []
        for i in range(episodes):
            env.reset(EVAL_SEED_BASE + i)
            done = False
            while not done:
                _obs, _r, done, info = env.step(env.n_actions - 1)
            results.append(info)
        report["route action"] = _summary(results)
    if model_path and os.path.exists(model_path):
        data = torch.load(model_path, weights_only=True)
        policy = Policy(env.obs_size, env.n_actions, hidden=data.get("hidden", 256))
        policy.load_state_dict(data["state"])
        policy.eval()
        results = []
        for i in range(episodes):
            obs = env.reset(EVAL_SEED_BASE + i)
            done = False
            while not done:
                obs, _r, done, info = env.step(policy.act(obs))
            if info["outcome"] == "goal":
                info["handoff"] = env.handoff()
            results.append(info)
        report["policy"] = _summary(results)
        if per_start:
            report["from"] = []
            for w in range(len(env.waypoints)):
                runs = []
                for i in range(per_start):
                    obs = env.reset(EVAL_SEED_BASE + i, from_wp=w)
                    done = False
                    while not done:
                        obs, _r, done, info = env.step(policy.act(obs))
                    runs.append(info)
                label = env.waypoints[w - 1].label if w else "start"
                report["from"].append((label, _summary(runs)["goal"]))
    return report
