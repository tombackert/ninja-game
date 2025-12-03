"""UI Widgets module (Issue 12).

Introduces ScrollableListWidget to unify list selection logic across
various menu screens (main menu, levels, store, accessories, options).

The widget is responsible only for state management & rendering of its
own options list; higher level states decide which actions map to
`move_up`, `move_down`, or `activate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence

import pygame

from scripts.ui import UI

ActivateCallback = Callable[[str, int], None]


@dataclass
class ScrollableListWidget:
    options: List[str]
    visible_rows: int = 7
    spacing: int = 50
    font_size: int = 30
    wrap: bool = True
    selected_index: int = 0
    _scroll_offset: int = 0
    on_activate: ActivateCallback | None = None

    def set_options(self, new_options: Sequence[str]) -> None:
        self.options = list(new_options)
        self.selected_index = 0 if self.options else -1
        self._scroll_offset = 0

    # Navigation ------------------------------------------------------
    def move_up(self) -> None:
        if not self.options:
            return
        if self.wrap:
            self.selected_index = (self.selected_index - 1) % len(self.options)
        else:
            self.selected_index = max(0, self.selected_index - 1)
        self._ensure_visible()

    def move_down(self) -> None:
        if not self.options:
            return
        if self.wrap:
            self.selected_index = (self.selected_index + 1) % len(self.options)
        else:
            self.selected_index = min(len(self.options) - 1, self.selected_index + 1)
        self._ensure_visible()

    def activate(self) -> None:
        if self.on_activate and 0 <= self.selected_index < len(self.options):
            self.on_activate(self.options[self.selected_index], self.selected_index)

    # Internal helpers ------------------------------------------------
    def _ensure_visible(self) -> None:
        if self.selected_index < self._scroll_offset:
            self._scroll_offset = self.selected_index
        elif self.selected_index >= self._scroll_offset + self.visible_rows:
            self._scroll_offset = self.selected_index - self.visible_rows + 1

    # Visible slice ---------------------------------------------------
    def visible_options(self) -> List[str]:
        return self.options[self._scroll_offset : self._scroll_offset + self.visible_rows]

    def visible_selected_local_index(self) -> int:
        if self.selected_index == -1:
            return -1
        return self.selected_index - self._scroll_offset

    # Rendering -------------------------------------------------------
    def render(self, surface: pygame.Surface, center_x: int, start_y: int) -> None:
        opts = self.visible_options()
        UI.render_o_box(
            surface,
            opts,
            self.visible_selected_local_index(),
            center_x,
            start_y,
            self.spacing,
            self.font_size,
        )


__all__ = ["ScrollableListWidget"]
