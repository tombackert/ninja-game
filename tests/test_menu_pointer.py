"""Menus follow the mouse: hover selects, a click on a row confirms it, the wheel scrolls."""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["NINJA_GAME_TESTING"] = "1"

import pygame  # noqa: E402

from scripts.multiplayer_menu import FriendsState, MultiplayerMenuState  # noqa: E402
from scripts.state_manager import (  # noqa: E402
    AccessoriesState,
    LevelsState,
    MenuState,
    OptionsState,
    PauseState,
    StateManager,
    StoreState,
)
from scripts.ui_widgets import PointerRouter, ScrollableListWidget  # noqa: E402

SIZE = (1280, 720)

pygame.init()  # menu states read the display info when they are built


def _move(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, {"pos": pos, "rel": (0, 0), "buttons": (0, 0, 0)})


def _down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": button})


def _up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": button})


def _click(pos, button=1):
    return [_down(pos, button), _up(pos, button)]


def _row(widget, index):
    return next(rect.center for i, rect in widget.hit_rects if i == index)


def _rendered(state):
    state.render(pygame.Surface(SIZE))
    return state


def _manager_with(state):
    sm = StateManager()
    sm.set(state)
    return sm


def test_render_records_one_hit_rect_per_visible_row():
    menu = _rendered(MenuState())
    assert [i for i, _ in menu.list_widget.hit_rects] == list(range(len(menu.options)))
    # Rows touch, so the pointer never falls into a gap between them
    rects = [r for _, r in menu.list_widget.hit_rects]
    assert all(a.bottom >= b.top for a, b in zip(rects, rects[1:]))


def test_hover_selects_the_row_under_the_pointer():
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    sm.handle([_move(_row(menu.list_widget, 3))])
    assert menu.list_widget.selected_index == 3
    # Moving off the list keeps the selection (the keyboard still owns it)
    sm.handle([_move((5, 5))])
    assert menu.list_widget.selected_index == 3


def test_click_on_a_row_confirms_it():
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    sm.handle(_click(_row(menu.list_widget, 2)))  # Levels
    menu.update(0.016)
    assert menu.next_state == "Levels"


def test_click_beside_the_rows_does_nothing():
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    sm.handle(_click((5, 5)))
    assert menu.enter is False


def test_dragging_off_a_row_cancels_the_click():
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    sm.handle([_down(_row(menu.list_widget, 1)), _up((5, 5))])
    assert menu.enter is False


def test_release_without_press_in_this_screen_does_not_click():
    """A press from the previous screen must not click the row now under the pointer."""
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    sm.handle([_up(_row(menu.list_widget, 1))])
    assert menu.enter is False


def test_pause_menu_is_clickable():
    pause = PauseState()
    pause.on_enter(None)
    _rendered(pause)
    sm = _manager_with(pause)
    sm.handle(_click(_row(pause.widget, pause.options_keys.index("level_complete.menu"))))
    assert pause.closed and pause.return_to_menu


def test_wheel_moves_the_selection_without_wrapping(monkeypatch):
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (5, 5))
    sm.handle([pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -2})])
    assert menu.list_widget.selected_index == 2
    sm.handle([pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": 10})])
    assert menu.list_widget.selected_index == 0


def test_clicking_a_category_opens_its_page_and_back_returns_to_the_hub():
    acc = _rendered(AccessoriesState())
    sm = _manager_with(acc)
    sm.handle(_click(_row(acc.widget, 2)))
    acc.update(0.0)
    assert acc.category == "skins"
    _rendered(acc)
    assert acc.pointer_widgets() == (acc.item_widget,)
    sm.handle([_move(_row(acc.item_widget, 1))])
    assert acc.item_widget.selected_index == 1
    sm.handle(_click(acc.back.rect.center))
    assert acc.category is None and not acc.request_back


def test_options_click_steps_value_forward_and_right_click_back():
    opts = OptionsState()
    opts.update(0.0)
    _rendered(opts)
    sm = _manager_with(opts)
    before = opts.settings.camera_style
    sm.handle(_click(_row(opts.widget, 4)))
    assert opts.settings.camera_style != before
    sm.handle(_click(_row(opts.widget, 4), button=3))
    assert opts.settings.camera_style == before


def test_states_without_lists_ignore_the_mouse():
    class _Plain:
        def pointer_widgets(self):
            return ()

    PointerRouter().process(_Plain(), _click((10, 10)))  # no error, nothing to do


def test_router_skips_states_not_accepting_input():
    widget = ScrollableListWidget(["A", "B"])
    widget.record_row(1, pygame.Rect(0, 0, 50, 20))
    selected = []

    class _Busy:
        accepts_input = False

        def pointer_widgets(self):
            return (widget,)

        def pointer_back(self):
            selected.append("back")

        def pointer_select(self, w, i):
            selected.append(i)

    PointerRouter().process(_Busy(), [_move((10, 10)), _down((10, 10), button=6)])
    assert selected == []


# Back: a clickable button bottom left in submenus, and the mouse's thumb button


def test_submenus_draw_a_back_button_bottom_left():
    for state in (LevelsState(), StoreState(), AccessoriesState(), OptionsState()):
        _rendered(state)
        assert state.back.rect.left < 40 and state.back.rect.bottom > SIZE[1] - 60, state.name


def test_clicking_back_leaves_the_submenu():
    levels = _rendered(LevelsState())
    sm = _manager_with(levels)
    sm.handle(_click(levels.back.rect.center))
    assert levels.request_back


def test_hovering_back_highlights_it_without_touching_the_list():
    store = _rendered(StoreState())
    sm = _manager_with(store)
    sm.handle([_move(store.back.rect.center)])
    assert store.back.hovered and store.widget.selected_index == 0
    sm.handle([_move((SIZE[0] // 2, 5))])
    assert not store.back.hovered


def test_right_click_on_back_does_nothing():
    opts = _rendered(OptionsState())
    sm = _manager_with(opts)
    sm.handle(_click(opts.back.rect.center, button=3))
    assert not opts.request_back


def test_mouse_back_button_goes_back():
    acc = _rendered(AccessoriesState())
    sm = _manager_with(acc)
    sm.handle([_down((SIZE[0] // 2, SIZE[1] // 2), button=6)])
    assert acc.request_back


def test_mouse_back_button_in_multiplayer_menu():
    mp = MultiplayerMenuState()
    sm = _manager_with(mp)
    sm.handle([_down((5, 5), button=6)])
    assert mp.request_back


def test_mouse_back_button_does_not_quit_the_main_menu():
    menu = _rendered(MenuState())
    sm = _manager_with(menu)
    sm.handle([_down((5, 5), button=6)])
    assert not menu.quit_requested


def test_friends_back_cancels_adding_first():
    friends = FriendsState()
    friends.adding = True
    _rendered(friends)
    sm = _manager_with(friends)
    sm.handle(_click(friends.back.rect.center))
    assert not friends.adding and not friends.request_back
    _rendered(friends)
    sm.handle(_click(friends.back.rect.center))
    assert friends.request_back


def test_store_pages_list_their_category_and_buy_with_enter():
    store = StoreState()
    store.cm.coins = 100000
    store.cm.kitsune = 0
    for category, sample in (("weapons", "Rifle"), ("gear", "Moon Boots"), ("skins", "Kitsune")):
        store.open_category(category)
        assert sample in store.items
        _rendered(store)
    store.item_widget.select(store.items.index("Kitsune"))
    store.handle_actions(["menu_select"])
    store.update(0.0)
    assert store.cm.kitsune == 1
    store.handle_actions(["menu_back"])
    assert store.category is None and not store.request_back


def test_accessories_equip_from_a_category_page():
    acc = AccessoriesState()
    acc.cm.gold_ninja = 1
    acc.open_category("skins")
    assert acc.item_widget.selected_index == acc.settings.selected_skin
    acc.item_widget.select(acc.items.index("Shogun"))
    acc.handle_actions(["menu_select"])
    acc.update(0.0)
    assert acc.settings.selected_skin == acc.cm.SKINS.index("Shogun")
