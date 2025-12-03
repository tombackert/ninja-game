from scripts.ui_widgets import ScrollableListWidget


def test_basic_navigation_wrap():
    w = ScrollableListWidget(["A", "B", "C"], visible_rows=2, wrap=True)
    assert w.selected_index == 0
    w.move_down()
    assert w.selected_index == 1
    w.move_down()
    assert w.selected_index == 2
    w.move_down()
    assert w.selected_index == 0  # wrapped
    w.move_up()
    assert w.selected_index == 2  # wrapped upwards


def test_non_wrap_navigation():
    w = ScrollableListWidget(["A", "B", "C"], visible_rows=2, wrap=False)
    w.move_up()
    assert w.selected_index == 0
    w.move_down()
    w.move_down()
    w.move_down()
    assert w.selected_index == 2


def test_scroll_offset_adjustment():
    w = ScrollableListWidget([str(i) for i in range(6)], visible_rows=3, wrap=False)
    assert w._scroll_offset == 0
    w.move_down()
    w.move_down()
    w.move_down()
    # Selected index now 3, should have scrolled so offset > 0
    assert w.selected_index == 3
    assert w._scroll_offset == 1  # lines 1,2,3 visible


def test_activation_callback():
    captured = []

    def on_act(opt, idx):
        captured.append((opt, idx))

    w = ScrollableListWidget(["A", "B"], visible_rows=2, on_activate=on_act)
    w.activate()
    assert captured == [("A", 0)]
    w.move_down()
    w.activate()
    assert captured[-1] == ("B", 1)
