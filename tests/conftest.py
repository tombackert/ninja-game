import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path for module imports (menu, scripts, etc.)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Headless / test mode environment variables
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("NINJA_GAME_TESTING", "1")

# Optional: suppress pygame welcome if desired (could patch later)
