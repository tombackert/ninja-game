"""Entry point for the PyInstaller desktop build (``packaging/ninja-game.spec``).

The game loads assets and writes save state with paths relative to the
current working directory (``data/...``). Inside a frozen app the bundled
files are read-only, and a fresh player must not see the developer's saves,
so on start this:

- makes a per-user folder (``~/Library/Application Support/Ninja Game`` on
  macOS, ``%APPDATA%/Ninja Game`` on Windows, ``~/.local/share/ninja-game``
  elsewhere) with a ``data/`` dir in it,
- links each bundled read-only asset (images, maps, sfx, ...) into that
  ``data/`` dir (a copy where symlinks are not allowed, as on Windows), and
  redoes this when a new build runs or the app was moved,
- chdirs there, so saves, settings, best times and replays land in the user
  folder while assets resolve to the bundle.

Hosting a multiplayer game spawns ``sys.executable server.py ...``; in the
frozen app ``sys.executable`` is this binary, so a ``server.py`` first
argument is dispatched to the dedicated server instead of the game.

Started without a console (the windowed Windows build from Explorer),
``sys.stdout`` and ``sys.stderr`` are None and anything that writes to them
crashes; they then go to ``logs/game.log`` (``logs/server.log`` for a hosted
server) in the user folder, rewritten on each start.

CI smoke test: with ``NINJA_GAME_SMOKE_SECONDS`` set, the app writes ``ok``
to ``NINJA_GAME_SMOKE_RESULT`` and exits 0 if it is still running after that
many seconds; a crash writes the traceback there and exits 1 (no error dialog
that would leave a windowed build hanging).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable

APP_NAME = "Ninja Game"
ASSET_STAMP = ".bundle-assets.json"  # in the user data dir: which build linked the assets


def _bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _user_root() -> Path:
    override = os.environ.get("NINJA_GAME_USER_DIR")
    if override:
        root = Path(override).expanduser().resolve()
        os.environ["NINJA_GAME_USER_DIR"] = str(root)  # a hosted server subprocess starts elsewhere
        return root
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ninja-game"


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _link(src: Path, dst: Path) -> None:
    """Point ``dst`` at ``src``: a symlink, or a copy where symlinks are not allowed."""
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _prepare_user_dir() -> Path:
    bundle_root = _bundle_root()
    bundle_data = bundle_root / "data"
    user_root = _user_root()
    user_data = user_root / "data"
    user_data.mkdir(parents=True, exist_ok=True)

    build_file = bundle_root / "build_id.txt"
    build = build_file.read_text().strip() if build_file.is_file() else ""
    stamp = {"build": build, "bundle": str(bundle_data)}
    stamp_path = user_data / ASSET_STAMP
    try:
        old = json.loads(stamp_path.read_text())
    except (OSError, ValueError):
        old = {}
    assets = sorted(entry.name for entry in bundle_data.iterdir())

    if {k: old.get(k) for k in stamp} != stamp:
        # A new build or a moved app: drop the asset links/copies of the old one.
        # Only bundle asset names are touched, never the player's saves or settings.
        for name in set(old.get("assets", [])) | set(assets):
            _remove(user_data / name)
    for name in assets:
        dst = user_data / name
        if not (dst.is_symlink() or dst.exists()):
            _link(bundle_data / name, dst)
    stamp_path.write_text(json.dumps({**stamp, "assets": assets}, indent=2))
    return user_root


def _attach_missing_streams(name: str) -> None:
    """Give a console-less start a stdout/stderr: a log file in the user folder
    (os.devnull if that cannot be opened). Streams that exist stay as they are."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_dir = _user_root() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stream = open(log_dir / f"{name}.log", "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _run(entry: Callable[[], None]) -> None:
    seconds = os.environ.get("NINJA_GAME_SMOKE_SECONDS")
    if not seconds:
        entry()
        return
    result = Path(os.environ.get("NINJA_GAME_SMOKE_RESULT", "smoke-result.txt"))

    def survived() -> None:
        result.write_text("ok\n")
        os._exit(0)

    timer = threading.Timer(float(seconds), survived)
    timer.daemon = True
    timer.start()
    try:
        entry()
        result.write_text("exited before the smoke test ended\n")
    except BaseException:
        result.write_text(traceback.format_exc())
    os._exit(1)


def main() -> None:
    server = len(sys.argv) > 1 and sys.argv[1] == "server.py"
    _attach_missing_streams("server" if server else "game")
    if os.environ.get("NINJA_GAME_SMOKE_RESULT"):
        # Resolve against the launch directory before the chdir below.
        os.environ["NINJA_GAME_SMOKE_RESULT"] = str(Path(os.environ["NINJA_GAME_SMOKE_RESULT"]).resolve())
    os.chdir(_prepare_user_dir())
    if server:
        # Spawned by start_host_server() as `<this binary> server.py --port ...`.
        sys.argv = sys.argv[1:]
        from server import main as server_main

        _run(server_main)
        return

    from app import main as app_main

    _run(app_main)


if __name__ == "__main__":
    main()
