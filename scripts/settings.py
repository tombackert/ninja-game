import json
import os

from scripts.logger import get_logger

log = get_logger("settings")


class Settings:
    SETTINGS_FILE = "data/settings.json"

    def __init__(self):
        # Default settings
        self._music_volume = 0.5
        self._sound_volume = 0.5
        self._selected_level = 0
        self.selected_editor_level = 0
        self.selected_weapon = 0
        self.selected_skin = 0
        self.show_perf_overlay = True
        self._ghost_enabled = True
        self._ghost_mode = "best" # "best" or "last"
        self._dirty = False
        self.playable_levels = {
            0: True,
            1: False,
            2: False,
            3: False,
            4: False,
            5: False,
            6: False,
            7: False,
            8: False,
            9: False,
            10: False,
            15: False,
        }
        self.load_settings()

    @property
    def music_volume(self):
        return self._music_volume

    @music_volume.setter
    def music_volume(self, value):
        new_val = max(0.0, max(0.0, min(1.0, round(value * 10) / 10)))
        if new_val != self._music_volume:
            self._music_volume = new_val
            self._dirty = True

    @property
    def sound_volume(self):
        return self._sound_volume

    @sound_volume.setter
    def sound_volume(self, value):
        new_val = max(0.0, max(0.0, min(1.0, round(value * 10) / 10)))
        if new_val != self._sound_volume:
            self._sound_volume = new_val
            self._dirty = True

    @property
    def selected_level(self):
        return self._selected_level

    @selected_level.setter
    def selected_level(self, value):
        new_val = max(0, value)
        if new_val != self._selected_level:
            self._selected_level = new_val
            self._dirty = True

    @property
    def ghost_enabled(self) -> bool:
        return self._ghost_enabled

    @ghost_enabled.setter
    def ghost_enabled(self, value: bool) -> None:
        new_val = bool(value)
        if new_val != self._ghost_enabled:
            self._ghost_enabled = new_val
            self._dirty = True

    @property
    def ghost_mode(self) -> str:
        return self._ghost_mode

    @ghost_mode.setter
    def ghost_mode(self, value: str) -> None:
        if value in ("best", "last") and value != self._ghost_mode:
            self._ghost_mode = value
            self._dirty = True

    def set_editor_level(self, value):
        self.selected_editor_level = max(0, value)

    def get_selected_editor_level(self):
        return self.selected_editor_level

    def set_level_to_playable(self, level):
        """Legacy API used by older code paths to unlock a level.

        Now delegates to ProgressTracker (Issue 22) so that dynamic progression
        logic remains the single source of truth. Retains dict update for
        backward compatibility with any code still reading settings directly.
        """
        if level in self.playable_levels and not self.playable_levels[level]:
            self.playable_levels[level] = True
            self._dirty = True
        # Delegate to progress tracker
        # (lazy import to avoid circular import at module load)
        try:  # pragma: no cover - defensive
            if "PYTEST_CURRENT_TEST" in os.environ:
                # Tests manage unlock flow explicitly; avoid side-effects
                return
            from scripts.progress_tracker import get_progress_tracker

            tracker = get_progress_tracker()
            if level not in tracker.unlocked:
                tracker.unlocked.add(level)
                # Sync tracker back to settings
                tracker._sync_settings()
        except Exception as e:  # pragma: no cover - safety guard
            log.warn("ProgressTracker delegation failed", e)

    def get_playable_levels(self):
        return self.playable_levels

    def is_level_playable(self, level):
        """Deprecated: Use ProgressTracker.is_unlocked.

        Provides a transparent bridge for legacy callers by delegating to the
        active ProgressTracker instance if initialized. Falls back to the
        local settings map otherwise (e.g., during very early startup or tests).
        """
        # Attempt delegation; avoid during tests for deterministic expectations.
        if "PYTEST_CURRENT_TEST" not in os.environ:
            try:  # pragma: no cover - defensive
                from scripts.progress_tracker import get_progress_tracker

                tracker = get_progress_tracker()
                return tracker.is_unlocked(level)
            except Exception as e:  # pragma: no cover
                log.warn("Delegation to ProgressTracker failed, falling back", e)
        return self.playable_levels.get(level, False)

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
                    self.selected_weapon = data.get("selected_weapon", self.selected_weapon)
                    self.selected_skin = data.get("selected_skin", self.selected_skin)
                    self.show_perf_overlay = data.get("show_perf_overlay", self.show_perf_overlay)
                    self._ghost_enabled = bool(data.get("ghost_enabled", self._ghost_enabled))
                    self._ghost_mode = str(data.get("ghost_mode", self._ghost_mode))
                    playable_levels = data.get("playable_levels", {})
                    for level in self.playable_levels:
                        self.playable_levels[level] = playable_levels.get(str(level), self.playable_levels[level])
            except (json.JSONDecodeError, IOError) as e:
                log.warn("Error loading settings; regenerating", e)
                self._dirty = True
                self.flush()
        else:
            self._dirty = True
            self.flush()

    def save_settings(self):  # backward compatibility; now conditional
        if self._dirty:
            self.flush()

    def flush(self):
        """Write settings to disk if dirty and clear dirty flag."""
        if not self._dirty:
            return
        data = {
            "music_volume": self._music_volume,
            "sound_volume": self._sound_volume,
            "selected_level": self._selected_level,
            "selected_editor_level": self.selected_editor_level,
            "selected_skin": self.selected_skin,
            "selected_weapon": self.selected_weapon,
            "playable_levels": {str(k): v for k, v in self.playable_levels.items()},
            "show_perf_overlay": self.show_perf_overlay,
            "ghost_enabled": self._ghost_enabled,
            "ghost_mode": self._ghost_mode,
        }
        try:
            os.makedirs(os.path.dirname(self.SETTINGS_FILE), exist_ok=True)
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=4)
            self._dirty = False
            log.debug("Settings flushed")
        except IOError as e:
            log.error("Error saving settings", e)


settings = Settings()