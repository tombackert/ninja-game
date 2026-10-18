import json

from scripts.settings import Settings


def test_unlocked_levels_beyond_defaults_survive_reload(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"playable_levels": {"0": True, "10": True, "11": True, "16": False}}))
    s = Settings()
    s.SETTINGS_FILE = str(settings_path)
    s.load_settings()
    assert s.playable_levels[11] is True
    assert s.playable_levels[16] is False
    assert s.playable_levels[10] is True
