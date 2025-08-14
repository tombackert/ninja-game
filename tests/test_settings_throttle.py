import os
import time
from scripts.settings import Settings


def test_settings_no_write_on_same_value(tmp_path, monkeypatch):
    # Use a temp settings file
    settings_path = tmp_path / "settings.json"
    s = Settings()
    s.SETTINGS_FILE = str(settings_path)
    s._dirty = True
    s.flush()  # initial write
    assert settings_path.exists()
    first_mtime = os.path.getmtime(settings_path)
    time.sleep(0.01)  # ensure mtime granularity
    # Assign same value; should not mark dirty -> no flush
    s.music_volume = s.music_volume
    s.flush()
    second_mtime = os.path.getmtime(settings_path)
    assert first_mtime == second_mtime


def test_settings_write_after_change_and_flush(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    s = Settings()
    s.SETTINGS_FILE = str(settings_path)
    s._dirty = True
    s.flush()
    first_mtime = os.path.getmtime(settings_path)
    time.sleep(0.01)
    s.music_volume = 0.7  # change
    s.flush()
    second_mtime = os.path.getmtime(settings_path)
    assert second_mtime > first_mtime


def test_settings_save_settings_backward_compat(tmp_path):
    settings_path = tmp_path / "settings.json"
    s = Settings()
    s.SETTINGS_FILE = str(settings_path)
    s._dirty = True
    s.flush()
    first_mtime = os.path.getmtime(settings_path)
    time.sleep(0.01)
    s.sound_volume = 0.2
    s.save_settings()  # should flush
    second_mtime = os.path.getmtime(settings_path)
    assert second_mtime > first_mtime
