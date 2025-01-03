import pygame
import sys
import os
from datetime import datetime
from scripts.button import Button
from scripts.settings import settings
from scripts.tilemap import Tilemap

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
                        # Adjust start_index if necessary
                        if level_index < start_index:
                            start_index = level_index
                        elif level_index >= start_index + levels_per_page:
                            start_index = level_index - levels_per_page + 1
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        level_index = (level_index + 1) % len(levels)
                        # Adjust start_index if necessary
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
            title_text = self.get_font(40).render("Select Level", True, "Black")
            title_rect = title_text.get_rect(center=(320, 50))
            self.screen.blit(title_text, title_rect)

            # Position settings
            start_y = 120
            spacing = 40

            level_rects = []

            # Only render levels from start_index to end_index
            end_index = min(start_index + levels_per_page, len(levels))

            for i in range(start_index, end_index):
                level = levels[i]
                idx = i  # Absolute index in levels list
                is_selected = level == self.selected_level

                # Determine if this level is highlighted (by keyboard or mouse)
                temp_rect = pygame.Rect(320 - 100, start_y + (i - start_index) * spacing - 15, 200, 30)
                if idx == level_index or temp_rect.collidepoint(mouse_pos):
                    base_color = "Red"
                else:
                    base_color = "Black"

                # Fixed x position for all level texts
                level_text_x = 200  # Adjust as needed
                level_text_y = start_y + (i - start_index) * spacing

                # Shift selected level to the left
                shift_amount = -20 if is_selected else 0
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
        options = ["Back"]
        selected_option = 0

        while True:
            # Event handling
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
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if options[selected_option] == "Back":
                            self.menu()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_pos = pygame.mouse.get_pos()
                        for i, rect in enumerate(option_rects):
                            if rect.collidepoint(mouse_pos):
                                selected_option = i
                                if options[selected_option] == "Back":
                                    self.menu()

            # Get mouse position for highlighting
            mouse_pos = pygame.mouse.get_pos()

            # Render the background
            self.display.blit(self.bg, (0, 0))
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the store menu
            title_text = self.get_font(40).render("Store", True, "Black")
            title_rect = title_text.get_rect(center=(320, 50))
            self.screen.blit(title_text, title_rect)

            # Position settings
            start_y = 200

            option_rects = []

            for i, option in enumerate(options):
                if i == selected_option:
                    base_color = "Red"
                else:
                    base_color = "Black"

                option_text = self.get_font(30).render(option, True, base_color)
                option_rect = option_text.get_rect(center=(320, start_y))
                self.screen.blit(option_text, option_rect)
                option_rects.append(option_rect)

                # Highlighting with mouse hover
                if option_rect.collidepoint(mouse_pos):
                    selected_option = i

            pygame.display.update()
            self.clock.tick(60)

    def options(self):
        options = ["Music Volume", "Sound Volume", "Back"]
        selected_option = 0

        while True:
            # Event handling
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
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if options[selected_option] == "Back":
                            self.menu()
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                        if options[selected_option] == "Music Volume":
                            settings.music_volume = max(0.0, settings.music_volume - 0.1)
                            pygame.mixer.music.set_volume(settings.music_volume)
                        elif options[selected_option] == "Sound Volume":
                            settings.sound_volume = max(0.0, settings.sound_volume - 0.1)
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        if options[selected_option] == "Music Volume":
                            settings.music_volume = min(1.0, settings.music_volume + 0.1)
                            pygame.mixer.music.set_volume(settings.music_volume)
                        elif options[selected_option] == "Sound Volume":
                            settings.sound_volume = min(1.0, settings.sound_volume + 0.1)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_pos = pygame.mouse.get_pos()
                        for i, rect in enumerate(option_rects):
                            if rect.collidepoint(mouse_pos):
                                selected_option = i
                                if options[selected_option] == "Back":
                                    self.menu()

            # Get mouse position for highlighting
            mouse_pos = pygame.mouse.get_pos()

            # Render the background
            self.display.blit(self.bg, (0, 0))
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the options menu
            title_text = self.get_font(40).render("Options", True, "Black")
            title_rect = title_text.get_rect(center=(320, 50))
            self.screen.blit(title_text, title_rect)

            # Position settings
            start_y = 150
            spacing = 50

            option_rects = []

            for i, option in enumerate(options):
                if i == selected_option:
                    base_color = "Red"
                else:
                    base_color = "Black"

                if option == "Music Volume":
                    text = f"Music Volume: {int(settings.music_volume * 100)}%"
                elif option == "Sound Volume":
                    text = f"Sound Volume: {int(settings.sound_volume * 100)}%"
                else:
                    text = option

                option_text = self.get_font(30).render(text, True, base_color)
                option_rect = option_text.get_rect(center=(320, start_y + i * spacing))
                self.screen.blit(option_text, option_rect)
                option_rects.append(option_rect)

                # Highlighting with mouse hover
                if option_rect.collidepoint(mouse_pos):
                    selected_option = i

            pygame.display.update()
            self.clock.tick(60)

    def menu(self):
        # List of menu options
        menu_options = ["PLAY", "LEVELS", "STORE", "OPTIONS", "QUIT"]
        self.selected_option = 0 

        while True:
            # Render the background on the scaled display
            self.display.blit(self.bg, (0, 0))

            # Scale up the display and blit onto the screen
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the menu text directly on the main screen
            MENU_TEXT = self.get_font(50).render("MENU", True, "Black")
            MENU_RECT = MENU_TEXT.get_rect(center=(320, 50))
            self.screen.blit(MENU_TEXT, MENU_RECT)

            # Position of the buttons
            spacing = 50
            button_positions = [x for x in range(180, 480, spacing)]

            # Event-Handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                        pygame.quit()
                        sys.exit()
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.selected_option = (self.selected_option - 1) % len(menu_options)
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.selected_option = (self.selected_option + 1) % len(menu_options)
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        if menu_options[self.selected_option] == "PLAY":
                            self.play()
                        if menu_options[self.selected_option] == "LEVELS":
                            self.levels()
                        if menu_options[self.selected_option] == "STORE":
                            self.store()
                        if menu_options[self.selected_option] == "OPTIONS":
                            self.options()
                        if menu_options[self.selected_option] == "QUIT":
                            pygame.quit()
                            sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for i, pos in enumerate(button_positions):
                        button_rect = pygame.Rect(320 - 100, pos - 25, 200, 50)
                        if button_rect.collidepoint(event.pos):
                            if menu_options[i] == "PLAY":
                                self.play()
                            if menu_options[i] == "LEVELS":
                                self.levels()
                            if menu_options[i] == "STORE":
                                self.store()
                            if menu_options[i] == "OPTIONS":
                                self.options()
                            if menu_options[i] == "QUIT":
                                pygame.quit()
                                sys.exit()

            MENU_MOUSE_POS = pygame.mouse.get_pos()

            for i, option in enumerate(menu_options):
                if i == self.selected_option:
                    base_color = "Red"
                else:
                    base_color = "Black"

                # Check if the mouse is hovering over the button
                button_rect = pygame.Rect(320 - 100, button_positions[i] - 25, 200, 50)
                if button_rect.collidepoint(MENU_MOUSE_POS):
                    base_color = "#b68f40"
                    if pygame.mouse.get_pressed()[0]:
                        if option == "PLAY":
                            self.play()
                        if option == "LEVELS":
                            self.levels()
                        if option == "STORE":
                            self.store()
                        if option == "OPTIONS":
                            self.options()
                        if option == "QUIT":
                            pygame.quit()
                            sys.exit()

                button = Button(image=None, pos=(320, button_positions[i]),
                                text_input=option, font=self.get_font(30),
                                base_color=base_color, hovering_color="#b68f40")
                button.update(self.screen)

            pygame.display.update()
            self.clock.tick(60)

    def pause_menu(game):
        options = ["Continue", "Save Game", "Menu"]
        selected_option = 0
        pause = True
        message = ""
        message_timer = 0

        current_time = game.timer.text
        best_time = game.timer.best_time_text

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
                            message_timer = 180
                        elif chosen == "Menu":
                            #game.tilemap.save_game()
                            game.running = False
                            pause = False
                            Menu().menu()
                            return
                        
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mouse_pos = pygame.mouse.get_pos()
                        for i, rect in enumerate(option_rects):
                            if rect.collidepoint(mouse_pos):
                                selected_option = i
                                if options[selected_option] == "Continue":
                                    print("Continue")
                                    game.paused = False
                                    pause = False
                                elif options[selected_option] == "Save Game":
                                    print("Save Game feature not implemented yet.")
                                elif options[selected_option] == "Menu":
                                    print("Menu")
                                    game.running = False
                                    pause = False

            mouse_pos = pygame.mouse.get_pos()

            base_color = "Black"

            # Render the background
            game.display_3.blit(game.assets['background'], (0, 0))
            scaled_display = pygame.transform.scale(game.display_3, game.screen.get_size())
            game.screen.blit(scaled_display, (0, 0))

            # Title
            title_text = game.get_font(40).render("Paused", True, base_color)
            title_rect = title_text.get_rect(center=(320, 50))
            game.screen.blit(title_text, title_rect)

            # Display message if timer is active
            if message_timer > 0:
                message_text = game.get_font(15).render(message, True, base_color)
                message_rect = message_text.get_rect(center=(320, 400))
                game.screen.blit(message_text, message_rect)
                message_timer -= 1

            start_y = 100
            spacing = 20

            # Level info
            info_text = f"Level: {game.level}"
            info_surface = game.get_font(15).render(info_text, True, base_color)
            info_rect = info_surface.get_rect(center=(320, start_y + spacing))
            game.screen.blit(info_surface, info_rect)

            # Current time info
            info_text = f"Current Time: {current_time}"
            info_surface = game.get_font(15).render(info_text, True, base_color)
            info_rect = info_surface.get_rect(center=(320, start_y + 2 * spacing))
            game.screen.blit(info_surface, info_rect)

            # Best time info
            info_text = f"Best Time: {best_time}"
            info_surface = game.get_font(15).render(info_text, True, base_color)
            info_rect = info_surface.get_rect(center=(320, start_y + 3 * spacing))
            game.screen.blit(info_surface, info_rect)

            # coins
            info_text = f"Coins: {game.collectable_manager.coin_count}"
            info_surface = game.get_font(15).render(info_text, True, base_color)
            info_rect = info_surface.get_rect(center=(320, start_y + 4 * spacing))
            game.screen.blit(info_surface, info_rect)

            # Menu options
            option_rects = []
            start_y = 250
            spacing = 40

            for i, option in enumerate(options):
                temp_rect = pygame.Rect(320 - 100, start_y + i * spacing - 15, 200, 30)
                if i == selected_option or temp_rect.collidepoint(mouse_pos):
                    button_color = "Red"
                else:
                    button_color = base_color

                # Render menu elements
                option_text_surface = game.get_font(30).render(option, True, button_color)
                option_rect = option_text_surface.get_rect(center=(320, start_y + i * spacing))
                game.screen.blit(option_text_surface, option_rect)
                option_rects.append(option_rect)

            pygame.display.update()
            game.clock.tick(60)

        return

if __name__ == "__main__":
    Menu()