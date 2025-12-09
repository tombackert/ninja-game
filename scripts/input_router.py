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

from typing import Callable, Dict, Iterable, List

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
        from scripts.settings import settings

        # Helper to generate rules for a list of keys
        def bind(keys, action, event_type=pygame.KEYDOWN):
            rules = []
            for k in keys:
                rules.append(_key_rule(k, action, event_type))
            return rules

        # MenuState (simple press)
        menu_binds = settings.key_bindings.get("MenuState", {})
        menu_rules: List[Rule] = []
        for act, keys in menu_binds.items():
            menu_rules.extend(bind(keys, act))
        # Add mouse rule manually (not in settings yet?)
        menu_rules.append(_mouse_button_rule(1, "menu_select"))

        # GameState (complex)
        game_binds = settings.key_bindings.get("GameState", {})
        game_rules: List[Rule] = []

        # Simple press actions
        for act in ["pause_toggle", "debug_toggle", "dash", "shoot", "jump"]:
            if act in game_binds:
                game_rules.extend(bind(game_binds[act], act))

        # Movement (press/release)
        if "left" in game_binds:
            game_rules.extend(bind(game_binds["left"], "left", pygame.KEYDOWN))
            game_rules.extend(bind(game_binds["left"], "stop_left", pygame.KEYUP))

        if "right" in game_binds:
            game_rules.extend(bind(game_binds["right"], "right", pygame.KEYDOWN))
            game_rules.extend(bind(game_binds["right"], "stop_right", pygame.KEYUP))

        # PauseState
        pause_binds = settings.key_bindings.get("PauseState", {})
        pause_rules: List[Rule] = []
        for act, keys in pause_binds.items():
            pause_rules.extend(bind(keys, act))

        self._rules.update(
            {
                "MenuState": menu_rules,
                "GameState": game_rules,
                "PauseState": pause_rules,
                "LevelsState": menu_rules,
                "StoreState": menu_rules,
                "AccessoriesState": menu_rules,
                "OptionsState": menu_rules,
                "LevelCompleteState": menu_rules,
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
