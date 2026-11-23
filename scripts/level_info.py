"""Level names, chapters and preview thumbnails for the menus.

Levels keep their numeric ids everywhere (map files, saves, replays, best
times); this module only gives them the names of the campaign
(docs/campaign.md), read from data/levels.json. A level that is not listed
there, e.g. a new map, is shown as "Level <id>".

Thumbnails are rendered by tools/thumbnails.py into data/thumbnails/levels/.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

LEVELS_FILE = "data/levels.json"
THUMBNAIL_DIR = "data/thumbnails/levels"


@dataclass(frozen=True)
class LevelInfo:
    id: int
    name: str
    setting: str = ""
    chapter: int = 0  # 1-based; 0 = not in the campaign
    chapter_name: str = ""


_cache: Optional[Dict[int, LevelInfo]] = None


def _load() -> Dict[int, LevelInfo]:
    global _cache
    if _cache is None:
        _cache = {}
        try:
            with open(LEVELS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        for number, chapter in enumerate(data.get("chapters", []), start=1):
            for lvl in chapter.get("levels", []):
                _cache[int(lvl["id"])] = LevelInfo(
                    id=int(lvl["id"]),
                    name=lvl["name"],
                    setting=lvl.get("setting", ""),
                    chapter=number,
                    chapter_name=chapter.get("name", ""),
                )
    return _cache


def level_info(level) -> LevelInfo:
    """The campaign entry of `level`, or a "Level <id>" stand-in."""
    try:
        key = int(level)
    except (TypeError, ValueError):  # a named map (e.g. "calibration")
        return LevelInfo(id=-1, name=str(level))
    return _load().get(key) or LevelInfo(id=key, name=f"Level {key}")


def level_name(level) -> str:
    return level_info(level).name


def thumbnail_path(level) -> Optional[str]:
    """The preview image of `level`, or None if none has been rendered."""
    path = os.path.join(THUMBNAIL_DIR, f"{level}.png")
    return path if os.path.exists(path) else None


def reload() -> None:
    """Forget the cached names (tests, or after editing data/levels.json)."""
    global _cache
    _cache = None


__all__ = ["LevelInfo", "level_info", "level_name", "thumbnail_path", "reload", "LEVELS_FILE", "THUMBNAIL_DIR"]
