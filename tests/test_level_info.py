"""Level names and thumbnails: every campaign map has both."""

from scripts.level_cache import list_levels
from scripts.level_info import level_info, level_name, thumbnail_path


def test_every_level_has_a_name_chapter_and_thumbnail():
    for lvl in list_levels():
        info = level_info(lvl)
        assert info.chapter, f"level {lvl} is missing from data/levels.json"
        assert info.name and not info.name.startswith("Level "), lvl
        assert thumbnail_path(lvl), f"no thumbnail for level {lvl}: run python tools/thumbnails.py {lvl}"


def test_names_are_unique():
    names = [level_name(lvl) for lvl in list_levels()]
    assert len(names) == len(set(names))


def test_unknown_levels_fall_back():
    assert level_name(999) == "Level 999"
    assert level_name("calibration") == "calibration"
    assert thumbnail_path(999) is None
