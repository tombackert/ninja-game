import pygame
import sys
import os
from scripts.displayManager import DisplayManager
from scripts.settings import settings
from scripts.collectableManager import CollectableManager
from scripts.inputManager import InputManager
from scripts.genericMenu import SingleMenu


class MenuSystem:

    def __init__(self):

        pygame.init()

        self.dm = DisplayManager()

        pygame.display.set_caption("Ninja Game")
        self.screen = pygame.display.set_mode((self.dm.WIN_W, self.dm.WIN_H))

        self.dm.WIN_W, self.dm.WIN_H = self.screen.get_size()
        self.display = pygame.Surface((self.dm.BASE_W, self.dm.BASE_H), pygame.SRCALPHA)

        self.bg = pygame.image.load("data/images/background-big.png")
        self.music = pygame.mixer.music.load("data/music.wav")

        self.im = InputManager()
        self.cm = CollectableManager(None)
        self.cm.load_collectables()

    def create_main_menu(self):
        print("Main Menu")
        title = "Menu"
        options = ["Play", "Levels", "Store", "Accessoires", "Options", "Quit"]
        actions = [
            self.play,
            self.create_levels_menu,
            self.store,
            self.accessoires,
            self.options,
            self.quit,
        ]
        main_menu = SingleMenu(
            title,
            options,
            actions,
            self.screen,
            self.display,
            self.bg,
            self.music,
            self.im,
        )
        main_menu.run()

    def play(self):
        from game import Game

        Game().run()

    def create_levels_menu(self):
        print("Levels")
        title = "Levels"

        level_files = [f for f in os.listdir("data/maps") if f.endswith(".json")]
        level_files.sort()
        levels = [int(f.split(".")[0]) for f in level_files]
        levels.sort()

        options = [f"Level {level}" for level in levels]
        actions = [self.set_level(level) for level in levels]

        levels_menu = SingleMenu(
            title,
            options,
            actions,
            self.screen,
            self.display,
            self.bg,
            self.music,
            self.im,
        )

        levels_menu.run()
        ms.create_main_menu()

    def store(self):
        print("Store")

    def accessoires(self):
        print("Accessoires")

    def options(self):
        print("Options")

    def quit(self):
        pygame.quit()
        sys.exit()

    def set_level(self, level):
        if settings.is_level_playable(level):
            settings.selected_level = level
        else:
            print("Level not unlocked")


if __name__ == "__main__":
    ms = MenuSystem()
    while True:
        ms.create_main_menu()
