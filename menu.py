import pygame
import sys
import os
from datetime import datetime
from scripts.button import Button
from scripts.settings import settings
from scripts.tilemap import Tilemap
from scripts.collectableManager import CollectableManager
from scripts.ui import UI

class Menu:

    def __init__(self):
        pygame.init()
        # Initialize screen and display surfaces
        self.screen = pygame.display.set_mode((640, 480))
        pygame.display.set_caption("Ninja Game")
        self.display = pygame.Surface((320, 240))
        self.clock = pygame.time.Clock()
        self.bg = pygame.image.load("data/images/background.png")

        # Load music
        pygame.mixer.music.load('data/music.wav')
        pygame.mixer.music.set_volume(settings.music_volume)
        pygame.mixer.music.play(-1)

        self.selected_level = settings.selected_level

        self.paused = False

        self.cm = CollectableManager(None)
        self.cm.load_collectables()

        self.selector_color = "#DD6E42"
        self.base_color = "#172A3A"
        self.warning_color = "#EF2917"

        self.menu()

    def get_font(self, size):
        return pygame.font.Font("data/font.ttf", size)

    def play(self):
        from game import Game
        Game().run()
        self.menu()

    def levels(self):

        # Get a list of all level files in the 'data/maps' directory
        level_files = [f for f in os.listdir('data/maps') if f.endswith('.json')]
        level_files.sort()  # Ensure levels are in order

        # Extract level numbers from filenames
        levels = [int(f.split('.')[0]) for f in level_files]
        levels.sort()

        # Index of the currently highlighted level
        level_index = levels.index(self.selected_level) if self.selected_level in levels else 0
        start_index = 0  # Index of the first level displayed
        levels_per_page = 8  # Number of levels displayed at once

        while True:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE): 
                        self.menu()
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        level_index = (level_index - 1) % len(levels)
                        if level_index < start_index:
                            start_index = level_index
                        elif level_index >= start_index + levels_per_page:
                            start_index = level_index - levels_per_page + 1
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        level_index = (level_index + 1) % len(levels)
                        if level_index >= start_index + levels_per_page:
                            start_index = level_index - levels_per_page + 1
                        elif level_index < start_index:
                            start_index = level_index
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        self.selected_level = levels[level_index]
                        settings.selected_level = self.selected_level
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_pos = pygame.mouse.get_pos()
                        for level_rect, idx in level_rects:
                            if level_rect.collidepoint(mouse_pos):
                                level_index = idx
                                self.selected_level = levels[level_index]
                                settings.selected_level = self.selected_level

            # Get mouse position for highlighting
            mouse_pos = pygame.mouse.get_pos()

            # Render the background on the scaled display
            self.display.blit(self.bg, (0, 0))
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the levels list on the main screen
            title_text = self.get_font(40).render("Select Level", True, self.base_color)
            title_rect = title_text.get_rect(center=(320, 50))
            self.screen.blit(title_text, title_rect)

            # Position settings
            START_Y = 120
            SPACING = 40
            SELECTED_OFFSET = -20

            level_rects = []

            # Only render levels from start_index to end_index
            end_index = min(start_index + levels_per_page, len(levels))

            for i in range(start_index, end_index):
                level = levels[i]
                idx = i  # Absolute index in levels list
                is_selected = level == self.selected_level

                # Determine if this level is highlighted (by keyboard or mouse)
                temp_rect = pygame.Rect(320 - 100, START_Y + (i - start_index) * SPACING - 15, 200, 30)
                if idx == level_index or temp_rect.collidepoint(mouse_pos):
                    base_color = self.selector_color
                else:
                    base_color = self.base_color

                # Fixed x position for all level texts
                level_text_x = 200  # Adjust as needed
                level_text_y = START_Y + (i - start_index) * SPACING

                # Shift selected level to the left
                shift_amount = SELECTED_OFFSET if is_selected else 0
                text_pos_x = level_text_x + shift_amount

                # Render the level text
                level_text_surface = self.get_font(30).render(f"Level {level}", True, base_color)
                level_text_rect = level_text_surface.get_rect(topleft=(text_pos_x, level_text_y))
                self.screen.blit(level_text_surface, level_text_rect)

                # Render the star if this is the selected level
                if is_selected:
                    star_text_surface = self.get_font(30).render("*", True, base_color)
                    star_text_rect = star_text_surface.get_rect()
                    # Position the star to the right of the level text
                    star_text_rect.midleft = (level_text_rect.right + 10, level_text_rect.centery)
                    self.screen.blit(star_text_surface, star_text_rect)
                    # Update the level_rect to include the star
                    level_rect = level_text_rect.union(star_text_rect)
                else:
                    level_rect = level_text_rect

                # Store the level_rect and index for interaction
                level_rects.append((level_rect, idx))

            pygame.display.update()
            self.clock.tick(60)

    def store(self):
        
        options = list(self.cm.ITEMS.keys())
        prices = list(self.cm.ITEMS.values())

        max_option_length = max(len(option) for option in options)
        options = [f"{options[i].ljust(max_option_length)}  ${prices[i]:<5}" for i in range(len(options))]

        selected_option = 0
        start_index = 0
        options_per_page = 5
        msg = "Item is not purchaseable!"
        msg_timer = 0

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self.menu()
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        selected_option = (selected_option - 1) % len(options)
                    if selected_option < start_index:
                        start_index = selected_option
                    elif selected_option >= start_index + options_per_page:
                        start_index = selected_option - options_per_page + 1
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected_option = (selected_option + 1) % len(options)
                    if selected_option >= start_index + options_per_page:
                        start_index = selected_option - options_per_page + 1
                    elif selected_option < start_index:
                        start_index = selected_option
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if options[selected_option] == "Back":
                            self.menu()
                        else:
                            item_name = options[selected_option].split('$')[0].strip()
                            buy_item = self.cm.buy_collectable(item_name)
                            if buy_item == "not purchaseable":
                                msg_timer = 60

            UI.render_menu_bg(self.screen, self.display, self.bg)
            UI.render_menu_title(self.screen, "Store", 320, 50)

            end_index = min(start_index + options_per_page, len(options))
            UI.render_o_box(self.screen, options[start_index:end_index], selected_option - start_index, 320, 120, 50)

            if msg_timer > 0:
                UI.render_menu_msg(self.screen, msg, 320, 400)
                msg_timer -= 1

            pygame.display.update()
            self.clock.tick(60)



    def options(self):
        title = "Options"
        selected_option = 0

        while True:
            
            options = [
                f"Music Volume:{int(settings.music_volume * 100):3d}%", 
                f"Sound Volume:{int(settings.sound_volume * 100):3d}%"
            ]

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self.menu()
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        selected_option = (selected_option - 1) % len(options)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected_option = (selected_option + 1) % len(options)
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                        if options[selected_option] == options[0]:
                            settings.music_volume = max(0.0, settings.music_volume - 0.1)
                            pygame.mixer.music.set_volume(settings.music_volume)
                        elif options[selected_option] == options[1]:
                            settings.sound_volume = max(0.0, settings.sound_volume - 0.1)
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        if options[selected_option] == options[0]:
                            settings.music_volume = min(1.0, settings.music_volume + 0.1)
                            pygame.mixer.music.set_volume(settings.music_volume)
                        elif options[selected_option] == options[1]:
                            settings.sound_volume = min(1.0, settings.sound_volume + 0.1)
            
            UI.render_menu_bg(self.screen, self.display, self.bg)
            UI.render_menu_title(self.screen, title, 320, 50)
            UI.render_o_box(self.screen, options, selected_option, 320, 150, 50)

            pygame.display.update()
            self.clock.tick(60)

    def menu(self):

        title = "Menu"
        options = ["PLAY", "LEVELS", "STORE", "OPTIONS", "QUIT"]
        self.selected_option = 0 

        while True:

            UI.render_menu_bg(self.screen, self.display, self.bg)
            UI.render_menu_title(self.screen, title, 320, 50)
            UI.render_o_box(self.screen, options, self.selected_option, 320, 200, 50)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                        pygame.quit()
                        sys.exit()
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.selected_option = (self.selected_option - 1) % len(options)
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.selected_option = (self.selected_option + 1) % len(options)
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        if options[self.selected_option] == options[0]:
                            self.play()
                        if options[self.selected_option] == options[1]:
                            self.levels()
                        if options[self.selected_option] == options[2]:
                            self.store()
                        if options[self.selected_option] == options[3]:
                            self.options()
                        if options[self.selected_option] == options[4]:
                            pygame.quit()
                            sys.exit()

            pygame.display.update()
            self.clock.tick(60)

    def pause_menu(game):
        title = "Pause Menu"
        info = [
            f"Level: {game.level}", 
            f"Time: {game.timer.text}", 
            f"Best Time: {game.timer.best_time_text}", 
            f"Coins: {game.cm.coins}"
        ]
        options = ["Continue", "Save Game", "Menu"]
        selected_option = 0
        pause = True
        message = ""
        message_timer = 0

        while pause:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    game.save_game()
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_LEFT):
                        game.tilemap.save_game()
                        game.running = False
                        pause = False
                        Menu().menu()  
                        return
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        selected_option = (selected_option - 1) % len(options)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected_option = (selected_option + 1) % len(options)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        chosen = options[selected_option]
                        if chosen == "Continue":
                            game.paused = False
                            pause = False
                        elif chosen == "Save Game":
                            success, filename = game.tilemap.save_game()
                            if success:
                                message = f"Game saved as {filename}"
                            else:
                                message = "Failed to save game"
                            message_timer = 60
                        elif chosen == "Menu":
                            #game.tilemap.save_game()
                            game.running = False
                            pause = False
                            Menu().menu()
                            return
            
            screen = game.screen
            display = game.display_3
            bg = game.assets['background']

            UI.render_menu_bg(screen, display, bg)
            UI.render_menu_title(screen, title, 320, 50)
            UI.render_info_box(screen, info, 100, 20)
            UI.render_o_box(screen, options, selected_option, 320, 250, 40)
            
            if message_timer > 0:
                UI.render_menu_msg(screen, message, 320, 400)
                message_timer -= 1

            pygame.display.update()
            game.clock.tick(60)

        return

if __name__ == "__main__":
    Menu()