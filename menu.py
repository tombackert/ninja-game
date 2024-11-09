import pygame, sys
from scripts.button import Button
from game import Game

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

        # Start the main menu
        self.menu()

    def get_font(self, size):
        return pygame.font.Font("data/font.ttf", size)

    def play(self):
        Game().run()
        # After the game ends, return to the main menu
        self.menu()

    def levels(self):
        while True:
            # Render the background on the scaled display
            self.display.blit(self.bg, (0, 0))

            # Scale up the display and blit onto the screen
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the text and buttons directly on the main screen
            LEVELS_TEXT = self.get_font(25).render("This is the LEVELS screen.", True, "Black")
            LEVELS_RECT = LEVELS_TEXT.get_rect(center=(320, 160))
            self.screen.blit(LEVELS_TEXT, LEVELS_RECT)

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