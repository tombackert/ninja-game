import pygame

class InputManager:
    def __init__(self):
        self.key_down_actions = {}
        self.key_up_actions = {}
        self.mouse_down_actions = {}
        self.mouse_up_actions = {}

    def bind_key_down(self, key, action):
        self.key_down_actions[key] = action

    def bind_key_up(self, key, action):
        self.key_up_actions[key] = action
    
    def bind_mouse_down(self, button, action):
        self.mouse_down_actions[button] = action
    
    def bind_mouse_up(self, button, action):
        self.mouse_up_actions[button] = action
    
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            action = self.key_down_actions.get(event.key)
            if action:
                action()
        elif event.type == pygame.KEYUP:
            action = self.key_up_actions.get(event.key)
            if action:
                action()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            action = self.mouse_down_actions.get(event.button)
            if action:
                action()
        elif event.type == pygame.MOUSEBUTTONUP:
            action = self.mouse_up_actions.get(event.button)
            if action:
                action()