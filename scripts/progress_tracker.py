"""ProgressTracker (Issue 22)

Automatically discovers playable levels (map JSON files) and tracks unlock
progression. Replaces static hard-coded `settings.playable_levels` map.

Design:
- On initialization, scans `data/maps` for integer-named JSON files.
- Maintains an internal unlocked set. Level 0 always unlocked.
- `unlock_next(completed_level)` unlocks the immediate next numerical
  level if present.
- Persists unlock state back into `settings.playable_levels` for backward
  compatibility with existing UI code until it is migrated to query this
  tracker directly.

Tests will assert:
1. Scanning returns sorted list of existing levels.
2. Completing a level unlocks the next if it exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Set

from scripts.level_cache import list_levels
from scripts.logger import get_logger
from scripts.settings import settings

log = get_logger("progress")


@dataclass
class ProgressTracker:
    levels: List[int] = field(default_factory=list)
    unlocked: Set[int] = field(default_factory=set)

    def __post_init__(self):
        if not self.levels:
            self.levels = list_levels()
        # Ensure deterministic ordering
        self.levels.sort()
        # Initialize unlocked set from settings legacy structure
        # (skip during tests for determinism)
        if "PYTEST_CURRENT_TEST" not in os.environ:
            if settings.playable_levels:
                # Migration: import every level flagged True (legacy behavior) so existing
                # players retain their progress. Always ensure level 0 is included.
                for lvl, playable in settings.playable_levels.items():
                    if playable:
                        self.unlocked.add(lvl)
                self.unlocked.add(0)
            if not self.unlocked:
                # Fallback safety
                self.unlocked.add(0)
        else:
            # Test environment: start with only level 0 unlocked
            # regardless of persisted settings.
            self.unlocked = {0}
        # Developer override: if DEV_UNLOCK_LEVELS=1,
        # treat all discovered levels unlocked
        if os.environ.get("DEV_UNLOCK_LEVELS") == "1" and "PYTEST_CURRENT_TEST" not in os.environ:
            self.unlocked.update(self.levels)
        # Normalize settings map to discovered levels only
        self._sync_settings()
        log.debug("ProgressTracker init", self.levels, self.unlocked)

    # Internal ---------------------------------------------------
    def _sync_settings(self) -> None:
        # Update settings.playable_levels to reflect current unlocked
        settings.playable_levels = {lvl: (lvl in self.unlocked) for lvl in self.levels}
        settings._dirty = True  # mark for persistence

    # API ---------------------------------------------------------
    def is_unlocked(self, level: int) -> bool:
        return level in self.unlocked

    def unlock_next(self, completed_level: int) -> int | None:
        """Unlock the next sequential level if available.

        Returns the unlocked level number or None if nothing unlocked.
        """
        if completed_level not in self.levels:
            return None
        # Find index of completed level; unlock next if exists
        try:
            idx = self.levels.index(completed_level)
        except ValueError:  # pragma: no cover - guarded above
            return None
        if idx + 1 < len(self.levels):
            nxt = self.levels[idx + 1]
            if nxt not in self.unlocked:
                self.unlocked.add(nxt)
                self._sync_settings()
                log.info("Unlocked level", nxt)
                return nxt
        return None

    def get_unlocked_levels(self) -> List[int]:
        return sorted(self.unlocked)


_tracker: ProgressTracker | None = None


def get_progress_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProgressTracker()
    return _tracker


__all__ = ["get_progress_tracker", "ProgressTracker"]
