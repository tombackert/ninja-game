# This module contains the Settings class that manages the game settings.
import json
import os

class Settings:
    SETTINGS_FILE = "data/settings.json"

    def __init__(self):
        # Default settings
        self._music_volume = 0.5
        self._sound_volume = 0.5
        self._selected_level = 0

        # Load settings from the JSON file if it exists
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

    def load_settings(self):
        """Load settings from the JSON file."""
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self._music_volume = data.get("music_volume", self._music_volume)
                    self._sound_volume = data.get("sound_volume", self._sound_volume)
                    self._selected_level = data.get("selected_level", self._selected_level)
                # print("Settings loaded successfully.")
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading settings: {e}")
                self.save_settings()  # Save default settings if loading fails
        else:
            self.save_settings()  # Create the settings file with default values

    def save_settings(self):
        """Save current settings to the JSON file."""
        data = {
            "music_volume": self._music_volume,
            "sound_volume": self._sound_volume,
            "selected_level": self._selected_level
        }
        try:
            os.makedirs(os.path.dirname(self.SETTINGS_FILE), exist_ok=True)
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=4)
            # print("Settings saved successfully.")
        except IOError as e:
            print(f"Error saving settings: {e}")

# Create a global Settings instance
settings = Settings()