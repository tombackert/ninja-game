"""Lightweight logging wrapper (Issue 8).

Provides simple leveled logging with environment-based minimum level.
Future expansion can route to files or structured logs.
"""

from __future__ import annotations
import os
import sys
import time
from dataclasses import dataclass
from typing import TextIO

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_DEFAULT_LEVEL_NAME = os.environ.get("NINJA_LOG_LEVEL", "INFO").upper()
_MIN_LEVEL = _LEVELS.get(_DEFAULT_LEVEL_NAME, 20)


@dataclass
class Logger:
    name: str
    stream: TextIO = sys.stdout

    def _log(self, level: str, *parts):
        numeric = _LEVELS[level]
        if numeric < _MIN_LEVEL:
            return
        ts = time.strftime("%H:%M:%S")
        msg = " ".join(str(p) for p in parts)
        self.stream.write(f"[{ts}] {level:<5} {self.name}: {msg}\n")
        self.stream.flush()

    def debug(self, *parts):
        self._log("DEBUG", *parts)

    def info(self, *parts):
        self._log("INFO", *parts)

    def warn(self, *parts):
        self._log("WARN", *parts)

    def error(self, *parts):
        self._log("ERROR", *parts)


_default_logger = Logger("game")


def get_logger(name: str = "game") -> Logger:
    return Logger(name)


# Convenience module-level functions
info = _default_logger.info
debug = _default_logger.debug
warn = _default_logger.warn
error = _default_logger.error

__all__ = ["get_logger", "info", "debug", "warn", "error", "Logger"]
