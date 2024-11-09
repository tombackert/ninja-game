import pygame, sys
from scripts.button import Button
from game import Game
import os

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
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)

        self.selected_level = 0

        # Start the main menu
        self.menu()

    def get_font(self, size):
        return pygame.font.Font("data/font.ttf", size)

    def play(self):
        Game(self.selected_level).run()
        # After the game ends, return to the main menu
        self.menu()

    def levels(self):

        # Get a list of all level files in the 'data/maps' directory
        level_files = [f for f in os.listdir('data/maps') if f.endswith('.json')]
        level_files.sort()  # Ensure levels are in order

        # Extract level numbers from filenames
        levels = [int(f.split('.')[0]) for f in level_files]
        levels.sort()

        # Index of the currently highlighted level
        level_index = 0  # Start with the first level highlighted
        start_index = 0  # Index of the first level displayed
        levels_per_page = 9  # Number of levels displayed at once

        while True:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
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
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_pos = pygame.mouse.get_pos()
                        for level_rect, idx in level_rects:
                            if level_rect.collidepoint(mouse_pos):
                                level_index = idx
                                self.selected_level = levels[level_index]

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
            MENU_TEXT = self.get_font(50).render("MENU", True, "#b68f40")
            MENU_RECT = MENU_TEXT.get_rect(center=(320, 50))
            self.screen.blit(MENU_TEXT, MENU_RECT)

            # Position of the buttons
            button_positions = [180, 245, 310, 375, 440]

            # Event-Handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
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
                    base_color = "#b68f40"
                else:
                    base_color = "#d7fcd4"

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
                                text_input=option, font=self.get_font(25),
                                base_color=base_color, hovering_color="#b68f40")
                button.update(self.screen)

            pygame.display.update()
            self.clock.tick(60)

# Run the main menu
if __name__ == "__main__":
    Menu()