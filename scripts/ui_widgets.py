"""UI Widgets module (Issue 12).

Introduces ScrollableListWidget to unify list selection logic across
various menu screens (main menu, levels, store, accessories, options).

The widget is responsible only for state management & rendering of its
own options list; higher level states decide which actions map to
`move_up`, `move_down`, or `activate`.

Mouse: each render records where its rows were drawn (`hit_rects`), and
`PointerRouter` turns mouse events into the same selection a keyboard
gives (see its docstring for the conventions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Sequence, Tuple

import pygame

from scripts.audio_service import ui_sound
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
    # (option index, screen rect) of each row drawn by the last render
    hit_rects: List[Tuple[int, pygame.Rect]] = field(default_factory=list, repr=False)

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

    def select(self, index: int) -> None:
        if 0 <= index < len(self.options):
            self.selected_index = index
            self._ensure_visible()

    def step(self, steps: int) -> None:
        """Move the selection by `steps` rows without wrapping (mouse wheel)."""
        if self.options:
            self.select(max(0, min(len(self.options) - 1, self.selected_index + steps)))

    def activate(self) -> None:
        if self.on_activate and 0 <= self.selected_index < len(self.options):
            self.on_activate(self.options[self.selected_index], self.selected_index)

    # Internal helpers ------------------------------------------------
    def _ensure_visible(self) -> None:
        if self.selected_index < self._scroll_offset:
            self._scroll_offset = self.selected_index
        elif self.selected_index >= self._scroll_offset + self.visible_rows:
            self._scroll_offset = self.selected_index - self.visible_rows + 1

    # Mouse hit testing --------------------------------------------
    def clear_hit_rects(self) -> None:
        self.hit_rects = []

    def record_row(self, index: int, text_rect: pygame.Rect, pad_x: int = 16) -> None:
        """Make the row under `text_rect` clickable: as tall as the row pitch, so rows leave no gaps."""
        rect = pygame.Rect(0, 0, text_rect.width + 2 * pad_x, max(self.spacing, text_rect.height))
        rect.center = text_rect.center
        self.hit_rects.append((index, rect))

    def index_at(self, pos: Tuple[int, int]) -> int | None:
        for index, rect in self.hit_rects:
            if rect.collidepoint(pos):
                return index
        return None

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
        rects = UI.render_o_box(
            surface,
            opts,
            self.visible_selected_local_index(),
            center_x,
            start_y,
            self.spacing,
            self.font_size,
        )
        self.clear_hit_rects()
        for local, rect in enumerate(rects):
            self.record_row(self._scroll_offset + local, rect)


class BackButton:
    """The clickable "back" in a submenu's bottom-left corner (Esc does the same)."""

    PAD = 8  # extra clickable margin around the text

    def __init__(self, label: str) -> None:
        self.label = label
        self.rect: pygame.Rect | None = None  # where the last render drew it
        self.hovered = False  # set by PointerRouter

    def render(self, surface: pygame.Surface, x: int = 20, bottom_margin: int = 40) -> None:
        color = UI.SELECTOR_COLOR if self.hovered else UI.GAME_UI_COLOR
        drawn = UI.draw_text_with_outline(
            surface=surface,
            font=UI.get_font(15),
            text=self.label,
            x=x,
            y=surface.get_height() - bottom_margin,
            text_color=color,
            scale=2,
        )
        self.rect = drawn.inflate(2 * self.PAD, 2 * self.PAD)

    def contains(self, pos) -> bool:
        return self.rect is not None and self.rect.collidepoint(pos)


Hit = Tuple[ScrollableListWidget, int]
BACK = "back"  # press target of the back button
MOUSE_BACK = 6  # the thumb "back" button (SDL X1; pygame shifts it past the wheel buttons 4/5)


class PointerRouter:
    """Mouse navigation for the menus of the active state.

    The usual conventions of menu-driven games:
    - hovering a row selects it, so mouse and keyboard share one highlight
      (the keyboard keeps working; the mouse only takes over when it moves)
    - a row is activated when the button is pressed and released on it, so
      a click on empty space does nothing and dragging off a row cancels
    - the wheel moves the selection of the list under the pointer
    - submenus have a "back" button bottom left; the mouse's thumb back
      button goes back as well
    - the hand cursor shows while the pointer is over something clickable

    A state opts in with `pointer_widgets()` / `back` and may override the
    `pointer_select` / `pointer_activate` / `pointer_scroll` /
    `pointer_back` hooks (see `State`). States that are not accepting input
    (`accepts_input` False) are ignored.
    """

    def __init__(self) -> None:
        # What a press landed on: ((widget, index) or BACK, button)
        self._pressed: tuple[Hit | str, int] | None = None
        self._hand = False

    def reset(self) -> None:
        """Called when the state changes: a press in one screen never clicks the next."""
        self._pressed = None
        self._set_hand(False)

    def process(self, state, events: Sequence[pygame.event.Event]) -> None:
        widgets = state.pointer_widgets() if hasattr(state, "pointer_widgets") else ()
        back: BackButton | None = getattr(state, "back", None)
        if not hasattr(state, "pointer_back") or not getattr(state, "accepts_input", True):
            self._set_hand(False)
            return
        for e in events:
            if e.type == pygame.MOUSEMOTION:
                target = self._target(widgets, back, e.pos)
                self._set_hand(target is not None)
                if back is not None:
                    back.hovered = target == BACK
                if isinstance(target, tuple):
                    state.pointer_select(*target)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == MOUSE_BACK:
                ui_sound("menu_back")
                state.pointer_back()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
                target = self._target(widgets, back, e.pos)
                self._pressed = (target, e.button) if target is not None else None
                if isinstance(target, tuple):
                    state.pointer_select(*target)
            elif e.type == pygame.MOUSEBUTTONUP and e.button in (1, 3):
                pressed, self._pressed = self._pressed, None
                target = self._target(widgets, back, e.pos)
                if pressed is None or target is None or not self._same(pressed, target, e.button):
                    continue
                if target == BACK:
                    if e.button == 1:
                        ui_sound("menu_back")
                        state.pointer_back()
                elif isinstance(target, tuple):
                    ui_sound("menu_select")
                    state.pointer_activate(target[0], e.button)
            elif e.type == pygame.MOUSEWHEEL and e.y and widgets:
                pos = pygame.mouse.get_pos()
                hit = self._hit(widgets, pos)
                widget = hit[0] if hit is not None else self._widget_column(widgets, pos)
                state.pointer_scroll(widget, -e.y)

    def _target(self, widgets, back: BackButton | None, pos) -> Hit | str | None:
        if back is not None and back.contains(pos):
            return BACK
        return self._hit(widgets, pos)

    @staticmethod
    def _same(pressed: tuple[Hit | str, int], target: Hit | str, button: int) -> bool:
        what, pressed_button = pressed
        if pressed_button != button:
            return False
        if isinstance(what, tuple) and isinstance(target, tuple):
            return what[0] is target[0] and what[1] == target[1]
        return what == target

    @staticmethod
    def _hit(widgets: Sequence[ScrollableListWidget], pos) -> Hit | None:
        for widget in widgets:
            index = widget.index_at(pos)
            if index is not None:
                return widget, index
        return None

    @staticmethod
    def _widget_column(widgets: Sequence[ScrollableListWidget], pos) -> ScrollableListWidget:
        """The list horizontally closest to the pointer (side-by-side panels)."""
        if len(widgets) == 1:
            return widgets[0]

        def distance(widget: ScrollableListWidget) -> float:
            if not widget.hit_rects:
                return float("inf")
            left = min(r.left for _, r in widget.hit_rects)
            right = max(r.right for _, r in widget.hit_rects)
            return 0 if left <= pos[0] <= right else min(abs(pos[0] - left), abs(pos[0] - right))

        return min(widgets, key=distance)

    def _set_hand(self, hand: bool) -> None:
        if hand == self._hand:
            return
        self._hand = hand
        try:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if hand else pygame.SYSTEM_CURSOR_ARROW)
        except pygame.error:  # no window / headless video driver
            pass


__all__ = ["ScrollableListWidget", "BackButton", "PointerRouter"]
