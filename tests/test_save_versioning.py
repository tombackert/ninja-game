import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["NINJA_GAME_TESTING"] = "1"

from game import Game  # noqa: E402


def test_save_contains_version(tmp_path):
    g = Game()
    tm = g.tilemap
    g.load_level(g.level)
    path = tmp_path / "v2_save.json"
    tm.save(str(path))
    text = path.read_text()
    data = json.loads(text)
    assert data["meta_data"].get("version") == 2
    # maps are stored compact so the editor never bloats them again
    assert text == json.dumps(data, separators=(",", ":"))


def test_load_legacy_injects_version(tmp_path):
    # Legacy save (no version key) approximating v1
    legacy = {
        "meta_data": {
            "map": 0,
            "timer": {"current_time": "00:00:00", "start_time": "00:00:00"},
        },
        "entities_data": {"players": [], "enemies": []},
        "map_data": {"tilemap": {}, "tile_size": 16, "offgrid": []},
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy))
    g = Game()
    tm = g.tilemap
    tm.load(str(path))
    assert tm.version == 2  # migrated
    assert tm.meta_data.get("version") == 2
