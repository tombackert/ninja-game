# PyInstaller spec for the desktop build of Ninja Game.
#
#   pip install pyinstaller pillow
#   pyinstaller packaging/ninja-game.spec --noconfirm
#
# Output: dist/Ninja Game.app on macOS, dist/Ninja Game/ elsewhere.
# Only shipped assets go in: no saves, replays, logs, best times or settings,
# so the build starts like a fresh install (see packaging/desktop_main.py).
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
APP_NAME = "Ninja Game"

# Player-state and dev-only entries under data/ that a fresh install must not carry.
EXCLUDED_DATA = {
    "saves", "replays", "netlogs", "deaths", "maps-old",
    "online.json", "collectables.json", "best_times.json", "settings.json",
}
datas = []
for entry in sorted((ROOT / "data").iterdir()):
    if entry.name in EXCLUDED_DATA or entry.name.startswith("."):
        continue
    datas.append((str(entry), str(Path("data") / entry.name) if entry.is_dir() else "data"))

# App icon: the default ninja's first idle frame, scaled up pixel-crisp.
icon = None
try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    frame = pygame.image.load(str(ROOT / "data/images/entities/player/default/idle/00.png"))
    w, h = frame.get_size()
    scale = 900 // max(w, h)
    canvas = pygame.Surface((1024, 1024), pygame.SRCALPHA)
    big = pygame.transform.scale(frame, (w * scale, h * scale))
    canvas.blit(big, big.get_rect(center=(512, 512)))
    icon_png = Path(workpath) / "icon.png"
    icon_png.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(canvas, str(icon_png))
    icon = str(icon_png)  # PyInstaller converts it to .icns/.ico when Pillow is installed
except Exception as exc:  # the icon is cosmetic: build without it
    print(f"ninja-game.spec: no app icon ({exc})")

hiddenimports = ["app", "game", "server"] + collect_submodules("scripts")

a = Analysis(
    [str(ROOT / "packaging" / "desktop_main.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["numpy", "tkinter", "pytest", "matplotlib", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="io.github.tombackert.ninjagame",
        info_plist={
            "CFBundleShortVersionString": "3.0.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.games",
        },
    )
