import pygame
import sys
import os
from datetime import datetime
from scripts.button import Button
from scripts.displayManager import DisplayManager
from scripts.settings import settings
from scripts.tilemap import Tilemap
from scripts.collectableManager import CollectableManager
from scripts.ui import UI
from scripts.inputManager import InputManager


class SingleMenu:
    def __init__(self, title, options, actions, screen, display, bg, music, input_manager):
        
        self.title = title
        self.options = options
        self.actions = actions
        self.screen = screen
        self.display = display
        self.bg = bg
        self.music = music
        self.im = input_manager
        self.selection_index = 0

        self.running = False

        self.pl = 10
        self.pr = 10
        self.pt = 10
        self.pb = 25

        self.setup_music()
        self.setup_input_bindings()

    def setup_input_bindings(self):
        self.im.bind_key_down(pygame.K_UP, self.move_up)
        self.im.bind_key_down(pygame.K_w, self.move_up)
        self.im.bind_key_down(pygame.K_DOWN, self.move_down)
        self.im.bind_key_down(pygame.K_s, self.move_down)
        self.im.bind_key_down(pygame.K_RETURN, self.select_option)
        self.im.bind_key_down(pygame.K_ESCAPE, self.on_escape)
        self.im.bind_mouse_down(1, self.select_option)

    def move_up(self):
        self.selection_index = (self.selection_index - 1) % len(self.options)

    def move_down(self):
        self.selection_index = (self.selection_index + 1) % len(self.options)

    def on_escape(self):
        self.running = False

    def select_option(self):
        action = self.actions[self.selection_index]
        if action:
            action()

    def setup_music(self):
        pygame.mixer.music.set_volume(settings.music_volume)
        pygame.mixer.music.play(-1)

    def render_menu(self):
        UI.render_menu_bg(self.screen, self.display, self.bg)
        UI.render_menu_title(self.screen, self.title, self.screen.get_width() // 2, 200)
        
    def render_o_box(self):
        UI.render_o_box(self.screen, self.options, self.selection_index, self.screen.get_width() // 2, 300, 50)
        
    def render_navigation_description(self):
        UI.render_menu_ui_element(self.screen, "w/a to navigate", self.screen.get_width() // 2 - 100, self.screen.get_height() - 25)
        UI.render_menu_ui_element(self.screen, "esc to quit", self.screen.get_width() - 150, self.screen.get_height() - 25)

    def run(self):
        self.running = True
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                self.im.handle_event(event)
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.render_menu()
            self.render_o_box()
            self.render_navigation_description()
            pygame.display.update()
            clock.tick(60)


class DoubleMenu(SingleMenu):
    def __init__(self, title, options1, actions, screen, display, bg, input_manager, music, options2, actions2):
        super().__init__(title, options1, actions, screen, display, bg, input_manager, music)
        self.options2 = options2
        self.actions2 = actions2
        self.options_index = 0

        self.setup_input_bindings()

    def setup_input_bindings(self):
        super().setup_input_bindings()
        self.im.bind_key_down(pygame.K_TAB, self.switch_options)
    
    def switch_options(self):
        self.options_index = (self.options_index + 1) % 2
    
    def render_o_box(self):
        UI.render_o_box(self.screen, self.options1, self.selection_index, self.screen.get_width() // 2, 300, 50)
        UI.render_o_box(self.screen, self.options2, self.selection_index, self.screen.get_width() // 2, 300, 50)