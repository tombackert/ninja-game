from typing import Any, Dict, Tuple

from game import Game
from scripts.feature_extractor import FeatureExtractor
from scripts.reward_shaper import RewardShaper
from scripts.rng_service import RNGService
from scripts.snapshot import SimulationSnapshot, SnapshotService


class TrainingEnv:
    """RL-compatible environment wrapper for the Ninja Game.

    Provides a gym-like interface (reset, step) to drive the simulation
    deterministically for training agents.
    """

    def __init__(self, seed: int = 42, level_id: int = 0, max_steps: int = 3600):
        self.seed_val = seed
        self.level_id = level_id
        self.max_steps = max_steps
        self.steps = 0

        # Underlying game instance
        self.game = Game()

        # Helpers
        self.extractor = FeatureExtractor()
        self.reward_shaper = RewardShaper()  # Initialize RewardShaper
        self.prev_snap: SimulationSnapshot | None = None  # Store previous snapshot for reward calculation

        self.action_map = [
            [],  # 0: No-op
            ["left"],  # 1: Left
            ["right"],  # 2: Right
            ["jump"],  # 3: Jump
            ["left", "jump"],  # 4: Left+Jump
            ["right", "jump"],  # 5: Right+Jump
            ["dash"],  # 6: Dash
            ["shoot"],  # 7: Shoot
        ]

    def reset(self) -> Dict[str, Any]:
        """Reset environment to initial state."""
        self.steps = 0

        # Deterministic RNG reset
        RNGService.get().seed(self.seed_val)

        # Reload level
        self.game.load_level(self.level_id)

        # Ensure player exists
        if not self.game.players:
            # Defensive: level might be empty
            self.prev_snap = None
            return self.extractor._empty_observation()

        # Capture initial state
        self.prev_snap = SnapshotService.capture(self.game)  # Store initial snapshot
        obs = self.extractor.extract(self.prev_snap, entity_id=self.game.player.id)
        return obs

    def step(self, action_idx: int) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        """Advance simulation by one tick (or frame-skip steps)."""
        self.steps += 1

        # Map integer action to input flags
        if 0 <= action_idx < len(self.action_map):
            inputs = self.action_map[action_idx]
        else:
            inputs = []

        # Same simulation step as live play (GameState.update)
        p = self.game.player
        self.game.apply_inputs(inputs)
        self.game.step()

        # Check termination
        done = False
        level_cleared = False
        player_dead = False

        if p.lives <= 0 or self.game.dead:
            done = True
            player_dead = True

        if self.game.endpoint:  # Level clear
            done = True
            level_cleared = True

        if self.steps >= self.max_steps:
            done = True

        # Capture current state for observation and reward calculation
        current_snap = SnapshotService.capture(self.game)
        obs = self.extractor.extract(current_snap, entity_id=p.id)

        # Prepare info dict for reward shaper
        info = {
            "lives": p.lives,
            "coins": self.game.cm.coins,
            "tick": self.steps,
            "done": done,
            "level_cleared": level_cleared,
            "player_dead": player_dead,
        }

        # Calculate reward
        reward = self.reward_shaper.calculate(self.prev_snap, current_snap, info)  # type: ignore

        # Update previous snapshot for next step
        self.prev_snap = current_snap

        return obs, reward, done, info
