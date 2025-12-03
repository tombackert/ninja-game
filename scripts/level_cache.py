"""Level listing with simple caching.

Provides list_levels() to return sorted list of available level IDs (ints)
from the data/maps directory. Avoids repeated os.listdir() calls every
frame / menu open. Cache invalidates automatically if directory mtime
changes, or manually via invalidate_level_cache().
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

MAPS_DIR = "data/maps"


_cache: Dict[str, Any] = {
    "levels": None,
    "mtime": None,
}


def _scan_levels() -> List[int]:
    try:
        entries = [f for f in os.listdir(MAPS_DIR) if f.endswith(".json")]
    except FileNotFoundError:
        return []
    levels = []
    for f in entries:
        name = f.rsplit(".", 1)[0]
        if name.isdigit():
            try:
                levels.append(int(name))
            except ValueError:
                pass
    levels.sort()
    return levels


def list_levels() -> List[int]:
    """Return sorted list of level integers with directory mtime caching."""
    try:
        mtime = os.path.getmtime(MAPS_DIR)
    except OSError:
        mtime = None
    # Refresh cache if empty or mtime changed
    if _cache["levels"] is None or _cache["mtime"] != mtime:
        _cache["levels"] = _scan_levels()
        _cache["mtime"] = mtime
    return list(_cache["levels"])  # type: ignore[arg-type]


def invalidate_level_cache() -> None:
    """Force next list_levels() call to rescan directory."""
    _cache["levels"] = None
    _cache["mtime"] = None


__all__ = ["list_levels", "invalidate_level_cache", "MAPS_DIR"]
