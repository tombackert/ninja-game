import json
import os

class Settings:
    SETTINGS_FILE = "data/settings.json"

    def __init__(self):
        # Default settings
        self._music_volume = 0.5
        self._sound_volume = 0.5
        self._selected_level = 0
        self.selected_editor_level = 0

        self.load_settings()

    @property
    def music_volume(self):
        return self._music_volume

    @music_volume.setter
    def music_volume(self, value):
        self._music_volume = max(0.0, max(0.0, min(1.0, round(value * 10) / 10)))
        self.save_settings()

    @property
    def sound_volume(self):
        return self._sound_volume

    @sound_volume.setter
    def sound_volume(self, value):
        self._sound_volume = max(0.0, max(0.0, min(1.0, round(value * 10) / 10)))
        self.save_settings()

    @property
    def selected_level(self):
        return self._selected_level

    @selected_level.setter
    def selected_level(self, value):
        self._selected_level = max(0, value)
        self.save_settings()

    def set_editor_level(self, value):
        self.selected_editor_level = max(0, value)
    
    def get_selected_editor_level(self):
        return self.selected_editor_level

    def load_settings(self):
        """Load settings from the JSON file."""
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self._music_volume = data.get("music_volume", self._music_volume)
                    self._sound_volume = data.get("sound_volume", self._sound_volume)
                    self._selected_level = data.get("selected_level", self._selected_level)
                    self.selected_editor_level = data.get("selected_editor_level", self.selected_editor_level)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading settings: {e}")
                self.save_settings()
        else:
            self.save_settings()

    def save_settings(self):
        """Save current settings to the JSON file."""
        data = {
            "music_volume": self._music_volume,
            "sound_volume": self._sound_volume,
            "selected_level": self._selected_level,
            "selected_editor_level": self.selected_editor_level
        }
        try:
            os.makedirs(os.path.dirname(self.SETTINGS_FILE), exist_ok=True)
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Error saving settings: {e}")

settings = Settings()