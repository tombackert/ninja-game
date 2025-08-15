"""Centralized input routing (Issue 11).

Transforms raw pygame events into high-level *actions* depending on the
active state. This decouples states from direct event parsing and
enables later rebinding / intent modeling.

Design (minimal iteration):
- Stateless mapping: a dict from state name -> list of predicate/action
  rules processed in declaration order.
- Each rule is a function(event) -> action|None. First matching rule
  adds its action to the output list (multiple actions per frame
  possible). Duplicate actions in one frame are collapsed preserving
  order of first occurrence.
- Future iterations can evolve this into configurable bindings +
  continuous axes (e.g., movement) or throttled repeat behavior.
"""

from __future__ import annotations
from typing import Callable, Iterable, List, Dict
import pygame

Action = str
Rule = Callable[[pygame.event.Event], Action | None]


def _key_rule(key: int, action: Action, event_type=pygame.KEYDOWN) -> Rule:
    def _r(e: pygame.event.Event):  # type: ignore[override]
        if e.type == event_type and getattr(e, "key", None) == key:
            return action
        return None

    return _r


def _mouse_button_rule(button: int, action: Action, event_type=pygame.MOUSEBUTTONDOWN) -> Rule:
    def _r(e: pygame.event.Event):  # type: ignore[override]
        if e.type == event_type and getattr(e, "button", None) == button:
            return action
        return None

    return _r


class InputRouter:
    """Maps pygame events to semantic actions for the active state."""

    def __init__(self) -> None:
        self._rules: Dict[str, List[Rule]] = {}
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        menu_rules: List[Rule] = [
            _key_rule(pygame.K_UP, "menu_up"),
            _key_rule(pygame.K_w, "menu_up"),
            _key_rule(pygame.K_DOWN, "menu_down"),
            _key_rule(pygame.K_s, "menu_down"),
            _key_rule(pygame.K_RETURN, "menu_select"),
            _key_rule(pygame.K_KP_ENTER, "menu_select"),
            _key_rule(pygame.K_ESCAPE, "menu_quit"),
            _key_rule(pygame.K_BACKSPACE, "menu_back"),
            _key_rule(pygame.K_LEFT, "options_left"),
            _key_rule(pygame.K_a, "options_left"),
            _key_rule(pygame.K_RIGHT, "options_right"),
            _key_rule(pygame.K_d, "options_right"),
            _key_rule(pygame.K_TAB, "accessories_switch"),
            _mouse_button_rule(1, "menu_select"),
        ]
        game_rules: List[Rule] = [
            _key_rule(pygame.K_ESCAPE, "pause_toggle"),
        ]
        pause_rules: List[Rule] = [
            _key_rule(pygame.K_ESCAPE, "pause_close"),
            _key_rule(pygame.K_m, "pause_menu"),
            _key_rule(pygame.K_UP, "menu_up"),
            _key_rule(pygame.K_w, "menu_up"),
            _key_rule(pygame.K_DOWN, "menu_down"),
            _key_rule(pygame.K_s, "menu_down"),
            _key_rule(pygame.K_RETURN, "menu_select"),
            _key_rule(pygame.K_KP_ENTER, "menu_select"),
        ]
        self._rules.update(
            {
                "MenuState": menu_rules,
                "GameState": game_rules,
                "PauseState": pause_rules,
                "LevelsState": menu_rules,
                "StoreState": menu_rules,
                "AccessoriesState": menu_rules,
                "OptionsState": menu_rules,
            }
        )

    def register_rules(self, state_name: str, rules: Iterable[Rule], append: bool = True) -> None:
        lst = self._rules.setdefault(state_name, [])
        if append:
            lst.extend(rules)
        else:
            self._rules[state_name] = list(rules)

    def process(self, events: Iterable[pygame.event.Event], state_name: str) -> List[Action]:
        rules = self._rules.get(state_name, [])
        actions: List[Action] = []
        for e in events:
            for rule in rules:
                a = rule(e)
                if a:
                    if a not in actions:  # de-duplicate per frame
                        actions.append(a)
                    break  # stop at first rule match for this event
        return actions

    # Convenience hook for tests / introspection
    def actions_for(self, key: int, state_name: str) -> List[Action]:  # pragma: no cover - helper
        evt = pygame.event.Event(pygame.KEYDOWN, {"key": key})
        return self.process([evt], state_name)


__all__ = ["InputRouter", "Action"]
