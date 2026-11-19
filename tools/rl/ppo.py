"""PPO for SegmentEnv, optionally after imitation: a small MLP, environments
in worker processes.

By default the agent has the route action (SegmentEnv): it already follows
the planner's way and keeps clear of what it sees coming, and PPO teaches the
policy when to leave it. Without the route action, `bc_rounds` of imitation
come first (DAgger: SegmentEnv.teacher gives the planner's move from wherever
the agent is), so the policy climbs and finds its way like the planner, and
PPO keeps a small imitation loss so it does not forget the way. On a maze
that is far weaker than the route action (a policy that agrees with the
planner on 3 moves of 4 still falls off), so it is the option, not the way.

Each worker plays its rollout with its own copy of the policy, so workers
never wait for each other within a rollout, only for the update.

Kept short on purpose: one file, torch only, no RL framework. Episode seeds
for training are drawn per worker; evaluation (tools/rl/evaluate.py) uses
seeds from EVAL_SEED_BASE on, which training never sees.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

EVAL_SEED_BASE = 10**9


class Policy(nn.Module):
    def __init__(self, obs_size: int, n_actions: int, hidden: int = 256, route_bias: float | None = None):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(obs_size, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        self.pi = nn.Linear(hidden, n_actions)
        self.v = nn.Linear(hidden, 1)
        nn.init.orthogonal_(self.pi.weight, 0.01)
        nn.init.zeros_(self.pi.bias)
        if route_bias is not None:
            # With the route action (the last), start as a player who follows
            # the planned route most of the time; PPO learns where to leave it
            with torch.no_grad():
                self.pi.bias[-1] = route_bias

    def forward(self, obs: torch.Tensor):
        h = self.body(obs)
        return self.pi(h), self.v(h).squeeze(-1)

    @torch.no_grad()
    def act(self, obs: np.ndarray, greedy: bool = False) -> int:
        logits, _ = self(torch.as_tensor(obs).unsqueeze(0))
        if greedy:
            return int(logits.argmax(-1))
        return int(torch.distributions.Categorical(logits=logits).sample())


def _worker(conn, env_kwargs: dict, seed_base: int, n_steps: int, hidden: int):
    """Plays rollouts of `n_steps` decisions with its own copy of the policy:
    the workers never wait for each other within a rollout (a reset costs
    about as much as 30 decisions), only for the update between rollouts.
    With every observation it records the teacher's move (SegmentEnv.teacher,
    -1 if it has none); with `beta` > 0 that move is played instead of the
    policy's, at that rate (DAgger's mixture)."""
    torch.set_num_threads(1)
    from tools.rl.segment_env import SegmentEnv

    env = SegmentEnv(**env_kwargs)
    policy = Policy(env.obs_size, env.n_actions, hidden=hidden)
    rng = np.random.default_rng(seed_base)
    episode = 0
    obs = env.reset(seed=seed_base)
    while True:
        cmd, payload = conn.recv()
        if cmd == "close":
            break
        state, beta = payload
        policy.load_state_dict(state)
        obs_b = np.zeros((n_steps, env.obs_size), np.float32)
        act_b = np.zeros(n_steps, np.int64)
        teach_b = np.zeros(n_steps, np.int64)
        logp_b = np.zeros(n_steps, np.float32)
        val_b = np.zeros(n_steps, np.float32)
        rew_b = np.zeros(n_steps, np.float32)
        done_b = np.zeros(n_steps, np.float32)
        outcomes = []
        with torch.no_grad():
            for t in range(n_steps):
                logits, value = policy(torch.as_tensor(obs).unsqueeze(0))
                dist = torch.distributions.Categorical(logits=logits)
                teach = env.teacher()
                action = int(dist.sample())
                if teach >= 0 and beta > 0 and rng.random() < beta:
                    action = teach
                obs_b[t], act_b[t], teach_b[t] = obs, action, teach
                logp_b[t], val_b[t] = float(dist.log_prob(torch.tensor(action))), float(value)
                obs, reward, done, info = env.step(action)
                rew_b[t], done_b[t] = reward, done
                if done:
                    outcomes.append(info["outcome"])
                    episode += 1
                    obs = env.reset(seed=seed_base + episode)
            last_v = float(policy(torch.as_tensor(obs).unsqueeze(0))[1])
        conn.send((obs_b, act_b, logp_b, val_b, rew_b, done_b, teach_b, last_v, outcomes))


class Workers:
    def __init__(self, env_kwargs: dict, n: int, seed: int, n_steps: int, hidden: int = 256):
        ctx = mp.get_context("spawn")
        self.conns, self.procs = [], []
        for i in range(n):
            a, b = ctx.Pipe()
            args = (b, env_kwargs, seed * 10**6 + i * 10**5, n_steps, hidden)
            proc = ctx.Process(target=_worker, args=args, daemon=True)
            proc.start()
            self.conns.append(a)
            self.procs.append(proc)

    def rollout(self, state: dict, beta: float = 0.0) -> list:
        for c in self.conns:
            c.send(("rollout", (state, beta)))
        return [c.recv() for c in self.conns]

    def close(self):
        for c in self.conns:
            c.send(("close", None))
        for p in self.procs:
            p.join(timeout=5)


@dataclass
class Config:
    total_steps: int = 600_000  # PPO's agent decisions over all workers
    n_envs: int = 8
    n_steps: int = 256  # per worker and update
    epochs: int = 4
    minibatch: int = 512
    lr: float = 3e-4
    gamma: float = 0.99
    lam: float = 0.95
    clip: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    seed: int = 0
    hidden: int = 256  # units per hidden layer
    route_bias: float = 3.0  # initial logit of the route action, if the env has one (see Policy)
    # Imitation first (DAgger): rounds of play, the teacher's share of the moves
    # falling from 1 to 0, each followed by fitting the policy to all the
    # teacher's moves so far; then PPO keeps an imitation loss, falling too
    bc_rounds: int = 4
    bc_steps: int = 40_000  # decisions per round
    bc_epochs: int = 3
    bc_rows: int = 200_000  # the newest labelled observations kept
    bc_coef: float = 0.5  # weight of the imitation loss in PPO, at its start ...
    bc_coef_end: float = 0.05  # ... and at its end


def _log_outcomes(log, label: str, outcomes: list, t0: float) -> None:
    recent = outcomes[-200:]
    if recent:
        share = {k: recent.count(k) / len(recent) for k in ("goal", "death", "timeout")}
        log(
            f"[{label}] {time.time() - t0:6.0f}s  last {len(recent)} episodes: "
            f"goal {share['goal']:.0%}  death {share['death']:.0%}  timeout {share['timeout']:.0%}"
        )


def _imitate(policy, workers, cfg: Config, log, t0: float) -> None:
    """DAgger: play with the teacher's moves mixed in, fit the policy to the
    teacher's move at every observation that has one, repeat."""
    import os

    opt = torch.optim.Adam(policy.parameters(), lr=1e-3)
    data_obs: list = []
    data_act: list = []
    per_round = max(1, cfg.bc_steps // (cfg.n_envs * cfg.n_steps))
    for r in range(cfg.bc_rounds):
        beta = 1.0 - r / max(1, cfg.bc_rounds - 1) if cfg.bc_rounds > 1 else 0.0
        outcomes: list = []
        for _ in range(per_round):
            state = {k: v.clone() for k, v in policy.state_dict().items()}
            for p in workers.rollout(state, beta):
                obs_b, teach_b = p[0], p[6]
                keep = teach_b >= 0
                data_obs.append(obs_b[keep].astype(np.float16))
                data_act.append(teach_b[keep])
                outcomes.extend(p[8])
        obs_all = np.concatenate(data_obs)[-cfg.bc_rows :]
        act_all = np.concatenate(data_act)[-cfg.bc_rows :]
        data_obs, data_act = [obs_all], [act_all]
        torch.set_num_threads(os.cpu_count() or 1)  # the workers wait meanwhile
        x, y = torch.as_tensor(obs_all), torch.as_tensor(act_all)
        idx = np.arange(len(y))
        hits = 0
        for epoch in range(cfg.bc_epochs):
            np.random.shuffle(idx)
            hits = 0
            for s in range(0, len(idx), cfg.minibatch):
                mb = torch.as_tensor(idx[s : s + cfg.minibatch])
                logits, _ = policy(x[mb].float())
                loss = nn.functional.cross_entropy(logits, y[mb])
                opt.zero_grad()
                loss.backward()
                opt.step()
                hits += int((logits.argmax(-1) == y[mb]).sum())
        torch.set_num_threads(1)
        log(
            f"[imitate] round {r + 1}/{cfg.bc_rounds}: teacher plays {beta:.0%}, {len(y):,} moves, "
            f"policy agrees on {hits / max(1, len(y)):.0%}"
        )
        _log_outcomes(log, "imitate", outcomes, t0)


def train(env_kwargs: dict, cfg: Config, log=print) -> Policy:
    from tools.rl.segment_env import SegmentEnv

    torch.manual_seed(cfg.seed)
    torch.set_num_threads(1)  # the cores belong to the environments; the net is small
    env = SegmentEnv(**env_kwargs)  # plans the stretch's route and guide once (cached) before the workers read them
    route = env.actions[-1] is None
    policy = Policy(env.obs_size, env.n_actions, hidden=cfg.hidden, route_bias=cfg.route_bias if route else None)
    workers = Workers(env_kwargs, cfg.n_envs, cfg.seed, cfg.n_steps, cfg.hidden)
    n, t_len = cfg.n_envs, cfg.n_steps
    t0 = time.time()
    try:
        if cfg.bc_rounds > 0:
            _imitate(policy, workers, cfg, log, t0)
        opt = torch.optim.Adam(policy.parameters(), lr=cfg.lr, eps=1e-5)
        updates = max(1, cfg.total_steps // (n * t_len))
        outcomes: list = []
        for update in range(1, updates + 1):
            state = {k: v.clone() for k, v in policy.state_dict().items()}
            parts = workers.rollout(state)
            # (time, worker) arrays, as one batched environment would give them
            obs_b, act_b, logp_b, val_b, rew_b, done_b, teach_b = (np.stack([p[k] for p in parts], 1) for k in range(7))
            last_v = np.array([p[7] for p in parts], np.float32)
            for p in parts:
                outcomes.extend(p[8])
            adv = np.zeros_like(rew_b)
            gae = np.zeros(n, np.float32)
            next_v = last_v
            for t in reversed(range(t_len)):
                nonterminal = 1.0 - done_b[t]
                delta = rew_b[t] + cfg.gamma * next_v * nonterminal - val_b[t]
                gae = delta + cfg.gamma * cfg.lam * nonterminal * gae
                adv[t] = gae
                next_v = val_b[t]
            ret = adv + val_b
            frac = (update - 1) / max(1, updates - 1)
            bc_coef = cfg.bc_coef + (cfg.bc_coef_end - cfg.bc_coef) * frac if cfg.bc_rounds > 0 else 0.0

            b_obs = torch.as_tensor(obs_b.reshape(-1, obs_b.shape[-1]))
            b_act = torch.as_tensor(act_b.ravel())
            b_teach = torch.as_tensor(teach_b.ravel())
            b_logp = torch.as_tensor(logp_b.ravel())
            b_adv = torch.as_tensor(adv.ravel())
            b_ret = torch.as_tensor(ret.ravel())
            idx = np.arange(len(b_act))
            for _ in range(cfg.epochs):
                np.random.shuffle(idx)
                for s in range(0, len(idx), cfg.minibatch):
                    mb = torch.as_tensor(idx[s : s + cfg.minibatch])
                    logits, value = policy(b_obs[mb])
                    dist = torch.distributions.Categorical(logits=logits)
                    ratio = (dist.log_prob(b_act[mb]) - b_logp[mb]).exp()
                    a = b_adv[mb]
                    a = (a - a.mean()) / (a.std() + 1e-8)
                    pg = -torch.min(ratio * a, ratio.clamp(1 - cfg.clip, 1 + cfg.clip) * a).mean()
                    vf = ((value - b_ret[mb]) ** 2).mean()
                    loss = pg + cfg.vf_coef * vf - cfg.ent_coef * dist.entropy().mean()
                    taught = b_teach[mb] >= 0
                    if bc_coef > 0 and bool(taught.any()):
                        loss = loss + bc_coef * nn.functional.cross_entropy(logits[taught], b_teach[mb][taught])
                    opt.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
                    opt.step()

            if update % 5 == 0 or update == updates:
                _log_outcomes(log, f"ppo {update * n * t_len:>8,}", outcomes, t0)
    finally:
        workers.close()
    return policy
