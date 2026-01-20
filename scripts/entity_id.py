"""Entity ID Generator (MP-02).

Provides centralized, deterministic unique ID generation for all game entities.
This is critical for multiplayer synchronization - entities must have stable
IDs that can be referenced across network messages.

The generator is a singleton that can be seeded for deterministic replay.
IDs are globally unique within a game session.

Usage:
    from scripts.entity_id import EntityIDGenerator

    gen = EntityIDGenerator.get()
    gen.reset()  # Call at level load for determinism
    entity_id = gen.next_id()
"""

from __future__ import annotations

from typing import Optional


class EntityIDGenerator:
    """Singleton ID generator for game entities."""

    _instance: Optional[EntityIDGenerator] = None

    def __init__(self):
        self._next_id: int = 0

    @classmethod
    def get(cls) -> EntityIDGenerator:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = EntityIDGenerator()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def next_id(self) -> int:
        """Generate the next unique ID."""
        current = self._next_id
        self._next_id += 1
        return current

    def reset(self, start_id: int = 0) -> None:
        """Reset the counter (call at level load for determinism)."""
        self._next_id = start_id

    def peek_next(self) -> int:
        """Peek at what the next ID will be without consuming it."""
        return self._next_id

    def get_state(self) -> int:
        """Get the current state (for serialization)."""
        return self._next_id

    def set_state(self, state: int) -> None:
        """Restore state (for deserialization)."""
        self._next_id = state


# Convenience function for quick access
def generate_entity_id() -> int:
    """Generate a unique entity ID."""
    return EntityIDGenerator.get().next_id()


__all__ = ["EntityIDGenerator", "generate_entity_id"]
