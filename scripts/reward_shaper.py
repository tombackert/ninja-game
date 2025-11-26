from typing import Any, Dict, List

from scripts.snapshot import SimulationSnapshot


class RewardShaper:
    """Calculates a reward based on state changes.

    This module allows pluggable reward functions for RL training.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = {
            "survival_reward": 0.01,  # Reward per step alive
            "death_penalty": -10.0,
            "win_reward": 100.0,
            "coin_reward": 1.0,  # Reward per coin collected
            "damage_penalty": -1.0,  # Penalty per life lost
            "enemy_kill_reward": 5.0,  # Reward per enemy killed
        }
        if config:
            self.config.update(config)

    def calculate(
        self,
        prev_snap: SimulationSnapshot,
        current_snap: SimulationSnapshot,
        info: Dict[str, Any], # Contains additional flags like 'done', 'level_cleared', 'player_dead'
    ) -> float:
        """Calculate reward based on changes between snapshots and info."""
        reward = 0.0

        # Survival reward
        reward += self.config["survival_reward"]

        # Win/Loss
        if info.get("done"):
            if info.get("level_cleared"):
                reward += self.config["win_reward"]
            elif info.get("player_dead"):
                reward += self.config["death_penalty"]

        # Coins collected
        if current_snap.score > prev_snap.score:
            reward += (current_snap.score - prev_snap.score) * self.config["coin_reward"]

        # Lives lost
        # Assume player 0 is the agent
        prev_lives = next((p.lives for p in prev_snap.players if p.id == 0), 0)
        curr_lives = next((p.lives for p in current_snap.players if p.id == 0), 0)
        if curr_lives < prev_lives:
            reward += (curr_lives - prev_lives) * self.config["damage_penalty"]

        # Enemy kills
        if len(current_snap.enemies) < len(prev_snap.enemies):
            reward += (len(prev_snap.enemies) - len(current_snap.enemies)) * self.config["enemy_kill_reward"]

        return reward
