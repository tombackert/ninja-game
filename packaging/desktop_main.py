"""Entry point for the PyInstaller desktop build (``packaging/ninja-game.spec``).

The game loads assets and writes save state with paths relative to the
current working directory (``data/...``). Inside a frozen app the bundled
files are read-only, and a fresh player must not see the developer's saves,
so on start this:

- makes a per-user folder (``~/Library/Application Support/Ninja Game`` on
  macOS, ``%APPDATA%/Ninja Game`` on Windows, ``~/.local/share/ninja-game``
  elsewhere) with a ``data/`` dir in it,
- links each bundled read-only asset (images, maps, sfx, ...) into that
  ``data/`` dir, refreshing the links if the app was moved,
- chdirs there, so saves, settings, best times and replays land in the user
  folder while assets resolve to the bundle.

Hosting a multiplayer game spawns ``sys.executable server.py ...``; in the
frozen app ``sys.executable`` is this binary, so a ``server.py`` first
argument is dispatched to the dedicated server instead of the game.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Ninja Game"


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _user_root() -> Path:
    override = os.environ.get("NINJA_GAME_USER_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ninja-game"


def _link(src: Path, dst: Path) -> None:
    """Point ``dst`` at ``src``: a symlink, or a copy where symlinks are not allowed."""
    if dst.is_symlink():
        if os.readlink(dst) == str(src):
            return
        dst.unlink()
    elif dst.exists():
        return  # a real file/dir the player owns (e.g. written by the game): keep it
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _prepare_user_dir() -> Path:
    bundle_data = _bundle_root() / "data"
    user_root = _user_root()
    user_data = user_root / "data"
    user_data.mkdir(parents=True, exist_ok=True)
    for entry in bundle_data.iterdir():
        _link(entry, user_data / entry.name)
    return user_root


def main() -> None:
    os.chdir(_prepare_user_dir())
    if len(sys.argv) > 1 and sys.argv[1] == "server.py":
        # Spawned by start_host_server() as `<this binary> server.py --port ...`.
        sys.argv = sys.argv[1:]
        from server import main as server_main

        server_main()
        return

    from app import main as app_main

    app_main()


if __name__ == "__main__":
    main()
