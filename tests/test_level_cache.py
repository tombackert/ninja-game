from scripts.level_cache import list_levels, invalidate_level_cache


def test_level_cache_basic(tmp_path, monkeypatch):
    # Point MAPS_DIR to temp dir
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    monkeypatch.setattr("scripts.level_cache.MAPS_DIR", str(maps_dir))
    # Invalidate any prior global cache state
    invalidate_level_cache()

    # Initially empty
    assert list_levels() == []

    # Add some level files
    for name in ["3.json", "1.json", "2.json", "not_level.txt"]:
        (maps_dir / name).write_text("{}")
    invalidate_level_cache()  # ensure refresh
    assert list_levels() == [1, 2, 3]

    # Add another level; bump mtime by touching directory (create file)
    (maps_dir / "10.json").write_text("{}")
    invalidate_level_cache()
    assert list_levels() == [1, 2, 3, 10]

    # Ensure copy semantics (mutating returned list doesn't affect cache)
    levels_copy = list_levels()
    levels_copy.append(999)
    assert list_levels() == [1, 2, 3, 10]
