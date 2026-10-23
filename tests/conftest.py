import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure repository root is on sys.path for module imports (menu, scripts, etc.)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Headless / test mode environment variables
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

# Optional: suppress pygame welcome if desired (could patch later)

# Tests save settings and collectables (coins, store items) the way the game
# does. Point both files at a scratch copy before any test module imports
# them, so a test run never touches the player's own data.
_SAVE_DIR = tempfile.mkdtemp(prefix="ninja_test_data_")
atexit.register(shutil.rmtree, _SAVE_DIR, True)
for _name in ("settings.json", "collectables.json"):
    if (ROOT / "data" / _name).exists():
        shutil.copy(ROOT / "data" / _name, os.path.join(_SAVE_DIR, _name))

from scripts import collectableManager as _collectables  # noqa: E402
from scripts.settings import Settings as _Settings  # noqa: E402

_collectables.DATA_FILE = os.path.join(_SAVE_DIR, "collectables.json")
_Settings.SETTINGS_FILE = os.path.join(_SAVE_DIR, "settings.json")

# Multiplayer session logs go to the scratch directory too
from scripts.network import netstats as _netstats  # noqa: E402

_netstats.NETLOG_DIR = os.path.join(_SAVE_DIR, "netlogs")
