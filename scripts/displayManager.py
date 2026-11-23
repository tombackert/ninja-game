import pygame

from scripts.config import SCALER
from scripts.logger import get_logger

log = get_logger("display")


class DisplayManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        display_info = pygame.display.Info()
        self.BASE_W = 640
        self.BASE_H = 360
        print(display_info.current_w, display_info.current_h)
        scale_x = display_info.current_w / self.BASE_W
        scale_y = display_info.current_h / self.BASE_H
        scale = min(scale_x, scale_y)
        scale *= SCALER
        if scale < 1:
            scale = 1

        self.WIN_W = int(self.BASE_W * scale)
        self.WIN_H = int(self.BASE_H * scale)

        self.WIN_W = min(self.WIN_W, display_info.current_w)
        self.WIN_H = min(self.WIN_H, display_info.current_h)
        self.scale = self.WIN_W / self.BASE_W


WINDOW_SIZE = (1280, 720)


def apply_window_mode(fullscreen: bool) -> pygame.Surface:
    """Open (or switch) the game window: 1280x720, or fullscreen.

    Fullscreen keeps the 1280x720 surface and lets SDL scale it to the
    screen on the GPU (pygame.SCALED, letterboxed). Measured on an M1 this
    costs nothing over the window, while drawing at the screen's own size
    in software costs ~1.6 ms per frame per megapixel. The surface stays
    the same object, so the game and every cached buffer keep working.
    """
    # SDL keeps the last error message even when nothing failed (the mouse
    # leaves "Unknown touch device id -1, cannot reset"), and set_mode can
    # report that stale message as its own failure. Start from a clean slate.
    pygame.set_error("")
    if fullscreen:
        try:
            return pygame.display.set_mode(WINDOW_SIZE, pygame.SCALED | pygame.FULLSCREEN)
        except pygame.error as e:
            log.warn("Fullscreen failed; staying in the window", e)
    return pygame.display.set_mode(WINDOW_SIZE)
