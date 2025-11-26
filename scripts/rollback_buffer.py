from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from scripts.snapshot import SimulationSnapshot


@dataclass
class FrameData:
    snapshot: SimulationSnapshot
    inputs: List[str]  # Actions active this frame


class RollbackBuffer:
    """Ring buffer storing recent simulation states and inputs.

    Used for:
    1. Network reconciliation (server authoritative correction).
    2. Local prediction rollback.
    3. Debugging / Replays.

    Access is O(1) via tick lookup.
    """

    def __init__(self, capacity: int = 600):
        self.capacity = capacity
        # Pre-allocate buffer
        self.buffer: List[Optional[FrameData]] = [None] * capacity
        self._tick_to_index: Dict[int, int] = {}
        self.newest_tick: int | None = None
        self.oldest_tick: int | None = None

    def push(self, snapshot: SimulationSnapshot, inputs: List[str]) -> None:
        """Add a frame to the buffer, overwriting oldest if full."""
        tick = snapshot.tick
        
        # If we are overwriting, remove old mapping
        index = tick % self.capacity
        existing = self.buffer[index]
        if existing is not None:
            old_tick = existing.snapshot.tick
            if old_tick in self._tick_to_index:
                del self._tick_to_index[old_tick]
                if self.oldest_tick == old_tick:
                    self.oldest_tick = None # Will be updated next push effectively or remains vague

        # Insert new
        self.buffer[index] = FrameData(snapshot, inputs)
        self._tick_to_index[tick] = index
        self.newest_tick = tick
        
        # Maintain oldest tracker (simple approx or precise?)
        # Precise: If we just deleted oldest, the new oldest is tick - capacity + 1 (roughly)
        # But since we mod, it's implicitly managed.
        # We can determine validity by `tick in self._tick_to_index`

    def get(self, tick: int) -> Optional[FrameData]:
        """Retrieve state at specific tick."""
        idx = self._tick_to_index.get(tick)
        if idx is None:
            return None
        return self.buffer[idx]

    def get_latest(self) -> Optional[FrameData]:
        if self.newest_tick is None:
            return None
        return self.get(self.newest_tick)

    def clear(self) -> None:
        self.buffer = [None] * self.capacity
        self._tick_to_index.clear()
        self.newest_tick = None
