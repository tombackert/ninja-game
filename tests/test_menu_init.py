import os
import pygame

# Ensure headless mode for CI / automated test environment before importing menu.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ["NINJA_GAME_TESTING"] = "1"

import menu  # noqa: E402


def test_menu_init_no_return():
    """Issue 1: Construct Menu() without entering interactive loop and
    ensure no return value misuse.

    The previous implementation accidentally returned a pygame.font.Font
    object with an undefined variable `size`. This test validates that
    constructing the menu does not raise and that essential attributes exist.
    """
    m = menu.Menu()
    # Basic sanity checks for initialized fields
    assert hasattr(m, "screen")
    assert hasattr(m, "cm")
    assert m.paused is False
    # Ensure selected level pulled from settings
    assert hasattr(m, "selected_level")


def test_menu_does_not_start_interactive_loop():
    """By setting NINJA_GAME_TESTING, the menu loop should not run (no infinite loop)."""
    # If we reached here the constructor returned promptly;
    # just assert display initialized.
    assert pygame.display.get_surface() is not None
