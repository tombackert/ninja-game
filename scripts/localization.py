"""Localization Service (Issue 56).

Handles loading and retrieving localized strings.
"""

import json
import os
from typing import Dict

from scripts.logger import get_logger

log = get_logger("localization")


class LocalizationService:
    _instance: "LocalizationService | None" = None
    DEFAULT_LOCALE = "en-US"

    def __init__(self) -> None:
        self._strings: Dict[str, Dict[str, str]] = {}
        self._current_locale = self.DEFAULT_LOCALE
        self._load_strings()

    @classmethod
    def get(cls) -> "LocalizationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_strings(self) -> None:
        path = "data/strings.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._strings = json.load(f)
            except Exception as e:
                log.error(f"Failed to load localization file: {e}")
        else:
            log.warn(f"Localization file not found at {path}")

    def set_locale(self, locale: str) -> None:
        if locale in self._strings:
            self._current_locale = locale
        else:
            log.warn(f"Locale {locale} not found, keeping {self._current_locale}")

    def translate(self, key: str, *args) -> str:
        """Retrieve and format a string for the current locale.

        Args:
            key: The string key (e.g., "menu.play").
            *args: Arguments for string formatting (e.g., numbers).

        Returns:
            The formatted localized string, or the key itself if not found.
        """
        locale_data = self._strings.get(self._current_locale, {})
        # Fallback to default if missing in current
        if key not in locale_data and self._current_locale != self.DEFAULT_LOCALE:
            locale_data = self._strings.get(self.DEFAULT_LOCALE, {})

        template = locale_data.get(key, key)
        try:
            if args:
                return template.format(*args)
            return template
        except Exception as e:
            log.warn(f"Error formatting string '{key}': {e}")
            return template


# Convenience alias
_ = LocalizationService.get().translate
