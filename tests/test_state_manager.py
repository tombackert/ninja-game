import os

import pytest

from scripts.state_manager import State, StateManager

os.environ["NINJA_GAME_TESTING"] = "1"  # ensure Menu/Game constructors stay non-interactive


class DummyState(State):
    def __init__(self, label: str, tracker: list):
        self.label = label
        self.tracker = tracker

    def on_enter(self, previous):  # record transitions
        self.tracker.append(f"enter:{self.label}:{previous.label if previous else 'None'}")

    def on_exit(self, next_state):
        self.tracker.append(f"exit:{self.label}:{next_state.label if next_state else 'None'}")


def test_push_and_current():
    sm = StateManager()
    t = []
    a = DummyState("A", t)
    sm.push(a)
    assert sm.current is a
    assert t == ["enter:A:None"]


def test_push_push_pop():
    sm = StateManager()
    t = []
    a = DummyState("A", t)
    b = DummyState("B", t)
    sm.push(a)
    sm.push(b)
    assert sm.stack_size() == 2
    popped = sm.pop()
    assert popped is b
    assert sm.current is a
    assert t == ["enter:A:None", "enter:B:A", "exit:B:A"]


def test_set_replaces_stack():
    sm = StateManager()
    t = []
    a = DummyState("A", t)
    b = DummyState("B", t)
    c = DummyState("C", t)
    sm.push(a)
    sm.push(b)
    sm.set(c)
    # A exited referencing new root (c) because we pop in order,
    # B exits referencing C, then C enters.
    assert sm.current is c
    assert sm.stack_size() == 1
    assert t == [
        "enter:A:None",
        "enter:B:A",
        "exit:B:C",  # B sees upcoming replacement C as next
        "exit:A:None",  # A is last popped; no remaining stack so next_state None
        "enter:C:None",
    ]


def test_pop_empty_returns_none():
    sm = StateManager()
    assert sm.pop() is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
