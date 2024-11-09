import pygame, sys
from scripts.button import Button
from game import Game

class MainMenu:
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
        self.main_menu()

    def get_font(self, size):
        return pygame.font.Font("data/font.ttf", size)

    def play(self):
        Game().run()
        # After the game ends, return to the main menu
        self.main_menu()

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

            LEVELS_BACK = Button(image=None, pos=(320, 400),
                                 text_input="BACK", font=self.get_font(50), base_color="Black", hovering_color="Green")

            LEVELS_MOUSE_POS = pygame.mouse.get_pos()

            LEVELS_BACK.changeColor(LEVELS_MOUSE_POS)
            LEVELS_BACK.update(self.screen)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if LEVELS_BACK.checkForInput(LEVELS_MOUSE_POS):
                        self.main_menu()

            pygame.display.update()
            self.clock.tick(60)

    def store(self):
        while True:
            # Render the background on the scaled display
            self.display.blit(self.bg, (0, 0))

            # Scale up the display and blit onto the screen
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the text and buttons directly on the main screen
            STORE_TEXT = self.get_font(25).render("This is the STORE screen.", True, "White")
            STORE_RECT = STORE_TEXT.get_rect(center=(320, 160))
            self.screen.blit(STORE_TEXT, STORE_RECT)

            STORE_BACK = Button(image=None, pos=(320, 400),
                                text_input="BACK", font=self.get_font(50), base_color="White", hovering_color="Green")

            STORE_MOUSE_POS = pygame.mouse.get_pos()

            STORE_BACK.changeColor(STORE_MOUSE_POS)
            STORE_BACK.update(self.screen)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if STORE_BACK.checkForInput(STORE_MOUSE_POS):
                        self.main_menu()

            pygame.display.update()
            self.clock.tick(60)

    def options(self):
        while True:
            # Render the background on the scaled display
            self.display.blit(self.bg, (0, 0))

            # Scale up the display and blit onto the screen
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the text and buttons directly on the main screen
            OPTIONS_TEXT = self.get_font(25).render("This is the OPTIONS screen.", True, "Black")
            OPTIONS_RECT = OPTIONS_TEXT.get_rect(center=(320, 160))
            self.screen.blit(OPTIONS_TEXT, OPTIONS_RECT)

            OPTIONS_BACK = Button(image=None, pos=(320, 400),
                                  text_input="BACK", font=self.get_font(50), base_color="Black", hovering_color="Green")

            OPTIONS_MOUSE_POS = pygame.mouse.get_pos()

            OPTIONS_BACK.changeColor(OPTIONS_MOUSE_POS)
            OPTIONS_BACK.update(self.screen)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if OPTIONS_BACK.checkForInput(OPTIONS_MOUSE_POS):
                        self.main_menu()

            pygame.display.update()
            self.clock.tick(60)

    def main_menu(self):
        while True:
            # Render the background on the scaled display
            self.display.blit(self.bg, (0, 0))

            # Scale up the display and blit onto the screen
            scaled_display = pygame.transform.scale(self.display, self.screen.get_size())
            self.screen.blit(scaled_display, (0, 0))

            # Draw the menu text and buttons directly on the main screen
            MENU_TEXT = self.get_font(50).render("MAIN MENU", True, "#b68f40")
            MENU_RECT = MENU_TEXT.get_rect(center=(320, 50))
            self.screen.blit(MENU_TEXT, MENU_RECT)

            PLAY_BUTTON = Button(image=None, pos=(320, 180),
                                 text_input="PLAY", font=self.get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
            LEVELS_BUTTON = Button(image=None, pos=(320, 245),
                                   text_input="LEVELS", font=self.get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
            STORE_BUTTON = Button(image=None, pos=(320, 310),
                                  text_input="STORE", font=self.get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
            OPTIONS_BUTTON = Button(image=None, pos=(320, 375),
                                    text_input="OPTIONS", font=self.get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
            QUIT_BUTTON = Button(image=None, pos=(320, 440),
                                 text_input="QUIT", font=self.get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")

            MENU_MOUSE_POS = pygame.mouse.get_pos()

            for button in [PLAY_BUTTON, LEVELS_BUTTON, STORE_BUTTON, OPTIONS_BUTTON, QUIT_BUTTON]:
                button.changeColor(MENU_MOUSE_POS)
                button.update(self.screen)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if PLAY_BUTTON.checkForInput(MENU_MOUSE_POS):
                        self.play()
                    if LEVELS_BUTTON.checkForInput(MENU_MOUSE_POS):
                        self.levels()
                    if STORE_BUTTON.checkForInput(MENU_MOUSE_POS):
                        self.store()
                    if OPTIONS_BUTTON.checkForInput(MENU_MOUSE_POS):
                        self.options()
                    if QUIT_BUTTON.checkForInput(MENU_MOUSE_POS):
                        pygame.quit()
                        sys.exit()

            pygame.display.update()
            self.clock.tick(60)

# Run the main menu
if __name__ == "__main__":
    MainMenu()