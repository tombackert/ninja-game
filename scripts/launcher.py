"""Console entry points for the installed *ninja-game* package.

The game loads its assets with paths relative to the current working
directory (e.g. ``data/images/...``). So the installed ``ninja-game``,
``ninja-editor`` and ``ninja-server`` commands can be launched from any
directory, each entry point first switches into the project root — the
directory that contains ``data/`` — before starting.

This assumes an *editable* install (``pip install -e .``) done from a
clone of the repository, so the source tree (and therefore ``data/``)
stays in place next to this file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# scripts/launcher.py -> project root is one directory up (holds data/, app.py, ...)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _enter_project_root() -> None:
    """Chdir into the project root so relative ``data/`` paths resolve."""
    if not (PROJECT_ROOT / "data").is_dir():
        sys.exit(
            f"ninja-game: could not find the 'data/' asset directory at {PROJECT_ROOT}.\n"
            "Install the game as an editable install from a clone of the repo:\n"
            "    git clone https://github.com/tombackert/ninja-game.git\n"
            "    cd ninja-game && pip install -e ."
        )
    os.chdir(PROJECT_ROOT)


def game() -> None:
    """Launch the main game (console script: ``ninja-game``)."""
    _enter_project_root()
    from app import main

    main()


def editor() -> None:
    """Launch the level editor (console script: ``ninja-editor``)."""
    _enter_project_root()
    from editor import main

    main()


def server() -> None:
    """Launch the dedicated multiplayer server (console script: ``ninja-server``)."""
    _enter_project_root()
    from server import main

    main()
