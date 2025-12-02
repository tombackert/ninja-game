from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple
from scripts.training_env import TrainingEnv

class RLAdapter(ABC):
    """
    Abstract base class for adapting the internal TrainingEnv to external RL frameworks.
    """
    @abstractmethod
    def reset(self) -> Any:
        pass

    @abstractmethod
    def step(self, action: Any) -> Tuple[Any, float, bool, Dict]:
        pass

class RayRLLibAdapter(RLAdapter):
    """
    Adapter compatible with Ray RLLib's MultiAgentEnv or simple Env interface.
    (Stub implementation as we don't want to depend on 'ray' package directly in core)
    """
    def __init__(self, config: Dict[str, Any]):
        self.env = TrainingEnv(**config)
        # Define action/observation spaces if using gym.spaces (omitted for lightweight stub)

    def reset(self) -> Any:
        # RLLib often expects (obs, info) in newer gym versions
        obs = self.env.reset()
        return obs, {}

    def step(self, action: int) -> Tuple[Any, float, bool, bool, Dict]:
        obs, reward, done, info = self.env.step(action)
        truncated = False # Ninja game currently has hard limit handled in done, or add specific logic
        return obs, reward, done, truncated, info

class StableBaselinesAdapter(RLAdapter):
    """
    Adapter for Stable Baselines 3 (Gymnasium compatible).
    """
    def __init__(self, seed=42):
        self.env = TrainingEnv(seed=seed)
        
    def reset(self, seed=None) -> Tuple[Any, Dict]:
        if seed is not None:
            # Re-init env or rng if supported
            pass 
        obs = self.env.reset()
        return obs, {}

    def step(self, action: int) -> Tuple[Any, float, bool, bool, Dict]:
        obs, reward, done, info = self.env.step(action)
        return obs, reward, done, False, info
