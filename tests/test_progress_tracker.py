import os

from scripts.progress_tracker import ProgressTracker

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["NINJA_GAME_TESTING"] = "1"


def test_tracker_scans_and_unlocks(tmp_path, monkeypatch):
    # Create fake maps directory
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    # Create level files 0..3
    for lvl in (0, 1, 2, 3):
        (maps_dir / f"{lvl}.json").write_text("{}")

    # Monkeypatch MAPS_DIR constant used by list_levels
    # via environment by changing cwd
    monkeypatch.chdir(tmp_path.parent)  # ensure relative path resolution

    # Monkeypatch list_levels to scan our temp directory directly
    from scripts import level_cache as lc

    lc.MAPS_DIR = str(maps_dir)
    lc.invalidate_level_cache()

    tracker = ProgressTracker()
    assert tracker.levels == [0, 1, 2, 3]
    # Initially only level 0 guaranteed unlocked
    assert 0 in tracker.unlocked
    # Unlock after completing 0 -> unlock 1
    unlocked = tracker.unlock_next(0)
    assert unlocked == 1
    assert 1 in tracker.unlocked
    # Completing last level does not unlock beyond
    assert tracker.unlock_next(3) is None
