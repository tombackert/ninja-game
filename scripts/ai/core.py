from abc import ABC, abstractmethod
from typing import Any, Dict


class Policy(ABC):
    """Abstract base class for entity behavior policies."""

    @abstractmethod
    def decide(self, entity: Any, context: Any) -> Dict[str, Any]:
        """Decide on an action based on the entity and context (game state).

        Args:
            entity: The entity executing the policy (e.g., Enemy).
            context: The game context (e.g., Game instance).

        Returns:
            Dict containing action intentions (e.g. {'movement': (1,0), 'shoot': True})
        """
        pass


class PolicyService:
    """Registry for behavioral policies."""

    _policies: Dict[str, Policy] = {}

    @classmethod
    def register(cls, name: str, policy: Policy) -> None:
        cls._policies[name] = policy

    @classmethod
    def get(cls, name: str) -> Policy:
        if name not in cls._policies:
            # Fallback to default if missing to prevent crashes, or raise?
            # For robustness, let's log and return a no-op or default.
            # But for now, raising helps debugging configuration.
            raise ValueError(f"Policy '{name}' not found in registry.")
        return cls._policies[name]
