import pygame
import sys
import os
from scripts.displayManager import DisplayManager
from scripts.settings import settings
from scripts.collectableManager import CollectableManager
from scripts.ui import UI


class Menu:

    def __init__(self):
        """Initialize main menu resources.

        Note: No return value (constructors must return None). The previous
        stray return statement with an undefined variable `size` was
        removed as part of Issue #1 (Quick Wins & Hygiene) to avoid
        confusion and unreachable code.

        For automated tests set environment variable NINJA_GAME_TESTING=1 to
        prevent entering the interactive infinite menu loop and to avoid
        using fullscreen / system specific video drivers.
        """

        pygame.init()

        dm = DisplayManager()
        self.BASE_W = dm.BASE_W
        self.BASE_H = dm.BASE_H
        self.WIN_W = dm.WIN_W
        self.WIN_H = dm.WIN_H

        is_test = os.environ.get("NINJA_GAME_TESTING") == "1"

        pygame.display.set_caption("Ninja Game")
        # Use windowed mode with base resolution in test environment to work
        # with the SDL_VIDEODRIVER=dummy driver headless.
        if is_test:
            self.screen = pygame.display.set_mode((self.BASE_W, self.BASE_H))
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.WIN_W, self.WIN_H = self.screen.get_size()

        self.display_1 = pygame.Surface((self.BASE_W, self.BASE_H), pygame.SRCALPHA)
        self.clock = pygame.time.Clock()
        self.bg = pygame.image.load("data/images/background-big.png")

        # Audio init: only play music when not in test mode to speed up CI and
        # avoid potential audio driver issues in headless environments.
        if not is_test:
            pygame.mixer.music.load("data/music.wav")
            pygame.mixer.music.set_volume(settings.music_volume)
            pygame.mixer.music.play(-1)

        self.selected_level = settings.selected_level

        self.paused = False

        self.cm = CollectableManager(None)
        self.cm.load_collectables()

        self.pl = 10
        self.pr = 10
        self.pt = 10
        self.pb = 25

        # Enter interactive loop only outside automated tests.
        if not is_test:
            self.menu()

    def play(self):
        from game import Game

        Game().run()
        self.menu()

    def levels(self):

        level_files = [f for f in os.listdir("data/maps") if f.endswith(".json")]
        level_files.sort()
        levels = [int(f.split(".")[0]) for f in level_files]
        levels.sort()

        level_index = (
            levels.index(self.selected_level) if self.selected_level in levels else 0
        )
        start_index = 0
        levels_per_page = 5

        msg_timer = 0

        enter = False

        while True:
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
                        enter = True
                if event.type == pygame.MOUSEBUTTONDOWN:
                    enter = True
                if enter:
                    if settings.is_level_playable(levels[level_index]):
                        self.selected_level = levels[level_index]
                        settings.selected_level = self.selected_level
                    else:
                        msg_timer = 60
                if event.type == pygame.KEYUP:
                    enter = False
                if event.type == pygame.MOUSEBUTTONUP:
                    enter = False

            UI.render_menu_bg(self.screen, self.display_1, self.bg)
            UI.render_menu_title(self.screen, "Select Level", self.WIN_W // 2, 200)

            if msg_timer > 0:
                UI.render_menu_msg(
                    self.screen, "Level not unlocked!", self.WIN_W // 2, 600
                )
                msg_timer -= 1

            level_options = []
            for level in levels[start_index: start_index + levels_per_page]:
                if level == self.selected_level:
                    level_options.append(f"*Level {level:<2}")
                else:
                    level_options.append(f"Level {level:<2}")

            UI.render_o_box(
                self.screen,
                level_options,
                level_index - start_index,
                self.WIN_W // 2,
                300,
                50,
                30,
            )
            UI.render_menu_ui_element(
                self.screen, f"Level: {self.selected_level}", self.pl, self.pt
            )
            UI.render_menu_ui_element(
                self.screen, "backspace to menu", self.pl, self.WIN_H - self.pb
            )
            UI.render_menu_ui_element(
                self.screen,
                "w/a to navigate",
                self.WIN_W // 2 - 100,
                self.WIN_H - self.pb,
            )

            for i, level in enumerate(level_options):
                current_level = levels[start_index + i]
                if settings.is_level_playable(current_level):
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-o.png",
                        self.WIN_W // 2 + 150,
                        300 + (i * 50),
                        0.15,
                    )
                else:
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-c.png",
                        self.WIN_W // 2 + 150,
                        300 + (i * 50),
                        0.15,
                    )

            pygame.display.update()
            self.clock.tick(60)

    def store(self):

        options = list(self.cm.ITEMS.keys())
        prices = list(self.cm.ITEMS.values())

        max_option_length = max(len(option) for option in options)
        options = [
            f"{options[i].ljust(max_option_length)}  ${prices[i]:<6}"
            for i in range(len(options))
        ]

        selected_option = 0
        start_index = 0
        options_per_page = 5
        w_msg_timer = 0
        enter = False

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
                        enter = True
                if event.type == pygame.MOUSEBUTTONDOWN:
                    enter = True
                if enter:
                    if options[selected_option] == "Back":
                        self.menu()
                    else:
                        item_name = options[selected_option].split("$")[0].strip()
                        buy_item = self.cm.buy_collectable(item_name)
                        if buy_item == "not purchaseable":
                            w_msg = "Item is not purchaseable!"
                            w_msg_timer = 60
                        elif buy_item == "not enough coins":
                            w_msg = "Not enough coins!"
                            w_msg_timer = 60
                        else:
                            w_msg = (
                                f"Bought {item_name} for ${self.cm.ITEMS[item_name]}"
                            )
                            w_msg_timer = 60

                if event.type == pygame.KEYUP:
                    enter = False
                if event.type == pygame.MOUSEBUTTONUP:
                    enter = False

            UI.render_menu_bg(self.screen, self.display_1, self.bg)
            UI.render_menu_title(self.screen, "Store", self.WIN_W // 2, 200)
            UI.render_menu_ui_element(
                self.screen, f"${self.cm.coins}", self.pl, self.pt
            )

            end_index = min(start_index + options_per_page, len(options))
            visible_options = options[start_index:end_index]
            UI.render_o_box(
                self.screen,
                visible_options,
                selected_option - start_index,
                self.WIN_W // 2,
                300,
                50,
                30,
            )

            for i, option in enumerate(visible_options):
                item_name = option.split("$")[0].strip()
                y_pos = 300 + (i * 50)
                if not self.cm.is_purchaseable(item_name):
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-c.png",
                        self.WIN_W // 2 + 350,
                        y_pos,
                        0.15,
                    )
                else:
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-o.png",
                        self.WIN_W // 2 + 350,
                        y_pos,
                        0.15,
                    )

            item_name = options[selected_option].split("$")[0].strip()
            msg = f"{item_name}: {str(self.cm.get_amount(item_name)):<4}"
            UI.render_menu_ui_element(
                self.screen, msg, self.WIN_W - self.pr, self.pt, "right"
            )

            if w_msg_timer > 0:
                UI.render_menu_msg(self.screen, w_msg, self.WIN_W // 2, 800)
                w_msg_timer -= 1

            UI.render_menu_ui_element(
                self.screen, "backspace to menu", self.pl, self.WIN_H - self.pb
            )
            UI.render_menu_ui_element(
                self.screen,
                "w/a to navigate",
                self.WIN_W // 2 - 100,
                self.WIN_H - self.pb,
            )

            pygame.display.update()
            self.clock.tick(60)

    def accessoires(self):
        title = "Accessoires"
        selected_option = 0

        weapons = self.cm.WEAPONS
        skins = self.cm.SKINS

        max_option_length = max(len(weapons) for w in weapons)
        weapons = [
            f"{weapons[i].ljust(max_option_length):<12}" for i in range(len(weapons))
        ]

        max_wappon_length = max(len(skins) for s in skins)
        skins = [f"{skins[i].ljust(max_wappon_length):<15}" for i in range(len(skins))]

        selected_option = 0
        selected_weapon = 0
        selected_skin = 0
        options_per_page = 2
        enter = False

        while True:

            UI.render_menu_bg(self.screen, self.display_1, self.bg)
            UI.render_menu_title(self.screen, title, self.WIN_W // 2, 200)
            UI.render_menu_subtitle(self.screen, "Weapons", self.WIN_W // 2 - 350, 320)
            UI.render_menu_subtitle(self.screen, "Skins", self.WIN_W // 2 + 350, 320)
            UI.render_menu_ui_element(
                self.screen, f"${self.cm.coins}", self.pl, self.pt
            )
            UI.render_menu_ui_element(
                self.screen,
                f"Skin: {self.cm.SKINS[settings.selected_skin]}",
                self.pl,
                self.pt + 20,
            )
            UI.render_menu_ui_element(
                self.screen,
                f"Weapon: {self.cm.WEAPONS[settings.selected_weapon]}",
                self.pl,
                self.pt + 20 * 2,
            )
            UI.render_menu_ui_element(
                self.screen,
                "tab to switch between weapons/skins",
                self.WIN_W // 2 - 270,
                self.WIN_H - self.pb,
            )
            UI.render_menu_ui_element(
                self.screen, "esc to menu", self.pl, self.WIN_H - self.pb
            )

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self.menu()
                    if event.key in (pygame.K_UP, pygame.K_w):
                        if selected_option == 0:
                            selected_weapon = (selected_weapon - 1) % len(weapons)
                        else:
                            selected_skin = (selected_skin - 1) % len(skins)
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        if selected_option == 0:
                            selected_weapon = (selected_weapon + 1) % len(weapons)
                        else:
                            selected_skin = (selected_skin + 1) % len(skins)
                    if event.key == pygame.K_TAB:
                        selected_option = (selected_option + 1) % 2
                        selected_weapon = 0
                        selected_skin = 0
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        enter = True

                if event.type == pygame.MOUSEBUTTONDOWN:
                    enter = True
                if enter:
                    if selected_option == 0:
                        selected_weapon_name = weapons[selected_weapon].strip()
                        if self.cm.get_amount(selected_weapon_name) > 0:
                            settings.selected_weapon = selected_weapon
                    else:
                        selected_skin_name = skins[selected_skin].strip()
                        if self.cm.get_amount(selected_skin_name) > 0:
                            settings.selected_skin = selected_skin

                if event.type == pygame.KEYUP:
                    enter = False
                if event.type == pygame.MOUSEBUTTONUP:
                    enter = False

            options_per_page = 4
            weapon_start = 0
            skin_start = 0

            # Handle scrolling for weapons
            if selected_option == 0:
                if selected_weapon >= weapon_start + options_per_page:
                    weapon_start = selected_weapon - options_per_page + 1
                elif selected_weapon < weapon_start:
                    weapon_start = selected_weapon

            # Handle scrolling for skins
            if selected_option == 1:
                if selected_skin >= skin_start + options_per_page:
                    skin_start = selected_skin - options_per_page + 1
                elif selected_skin < skin_start:
                    skin_start = selected_skin

            weapon_options = []
            for i in range(
                weapon_start, min(weapon_start + options_per_page, len(weapons))
            ):
                if i == settings.selected_weapon:
                    weapon_options.append(f"*{weapons[i]}")
                else:
                    weapon_options.append(f" {weapons[i]}")

                weapon = weapons[i].strip()
                if not self.cm.is_purchaseable(weapon):
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-c.png",
                        self.WIN_W // 2 - 150,
                        430 + ((i - weapon_start) * 50),
                        0.15,
                    )
                else:
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-o.png",
                        self.WIN_W // 2 - 150,
                        430 + ((i - weapon_start) * 50),
                        0.15,
                    )

            skin_options = []
            for i in range(skin_start, min(skin_start + options_per_page, len(skins))):
                if i == settings.selected_skin:
                    skin_options.append(f"*{skins[i]}")
                else:
                    skin_options.append(f" {skins[i]}")

                skin = skins[i].strip()
                if not self.cm.is_purchaseable(skin):
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-c.png",
                        self.WIN_W // 2 + 600,
                        430 + ((i - skin_start) * 50),
                        0.15,
                    )
                else:
                    UI.render_ui_img(
                        self.screen,
                        "data/images/padlock-o.png",
                        self.WIN_W // 2 + 600,
                        430 + ((i - skin_start) * 50),
                        0.15,
                    )

            UI.render_o_box(
                self.screen,
                weapon_options,
                (selected_weapon - weapon_start) if selected_option == 0 else -1,
                self.WIN_W // 2 - 350,
                430,
                50,
                30,
            )

            UI.render_o_box(
                self.screen,
                skin_options,
                (selected_skin - skin_start) if selected_option == 1 else -1,
                self.WIN_W // 2 + 350,
                430,
                50,
                30,
            )

            pygame.display.update()
            self.clock.tick(60)

    def options(self):
        title = "Options"
        selected_option = 0

        while True:

            options = [
                f"Music Volume:{int(settings.music_volume * 100):3d}%",
                f"Sound Volume:{int(settings.sound_volume * 100):3d}%",
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
                            settings.music_volume = max(
                                0.0, settings.music_volume - 0.1
                            )
                            pygame.mixer.music.set_volume(settings.music_volume)
                        elif options[selected_option] == options[1]:
                            settings.sound_volume = max(
                                0.0, settings.sound_volume - 0.1
                            )
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        if options[selected_option] == options[0]:
                            settings.music_volume = min(
                                1.0, settings.music_volume + 0.1
                            )
                            pygame.mixer.music.set_volume(settings.music_volume)
                        elif options[selected_option] == options[1]:
                            settings.sound_volume = min(
                                1.0, settings.sound_volume + 0.1
                            )

            UI.render_menu_bg(self.screen, self.display_1, self.bg)
            UI.render_menu_title(self.screen, title, self.WIN_W // 2, 200)
            UI.render_o_box(
                self.screen, options, selected_option, self.WIN_W // 2, 300, 50
            )
            UI.render_menu_ui_element(
                self.screen, "backspace to menu", self.pl, self.WIN_H - self.pb
            )
            UI.render_menu_ui_element(
                self.screen,
                "w/a to navigate",
                self.WIN_W // 2 - 100,
                self.WIN_H - self.pb,
            )

            pygame.display.update()
            self.clock.tick(60)

    def menu(self):

        title = "Menu"
        options = ["Play", "Levels", "Store", "Accessoires", "Options", "Quit"]
        self.selected_option = 0
        enter = False

        while True:

            UI.render_menu_bg(self.screen, self.display_1, self.bg)
            UI.render_menu_title(self.screen, title, self.WIN_W // 2, 200)
            UI.render_o_box(
                self.screen, options, self.selected_option, self.WIN_W // 2, 300, 50
            )
            UI.render_menu_ui_element(
                self.screen,
                "w/a to navigate",
                self.WIN_W // 2 - 100,
                self.WIN_H - self.pb,
            )
            UI.render_menu_ui_element(
                self.screen, "esc to quit", self.pl, self.WIN_H - self.pb
            )

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                        pass
                        # pygame.quit()
                        # sys.exit()
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.selected_option = (self.selected_option - 1) % len(options)
                    if event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.selected_option = (self.selected_option + 1) % len(options)
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        enter = True
                    if event.key == pygame.K_ESCAPE:
                        self.cm.save_collectables()
                        settings.save_settings()
                        pygame.quit()
                        sys.exit()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    enter = True

                if enter:
                    if options[self.selected_option] == options[0]:
                        self.play()
                    if options[self.selected_option] == options[1]:
                        self.levels()
                    if options[self.selected_option] == options[2]:
                        self.store()
                    if options[self.selected_option] == options[3]:
                        self.accessoires()
                    if options[self.selected_option] == options[4]:
                        self.options()
                    if options[self.selected_option] == options[5]:
                        pygame.quit()
                        sys.exit()

                if event.type == pygame.KEYUP:
                    enter = False
                if event.type == pygame.MOUSEBUTTONUP:
                    enter = False

            pygame.display.update()
            self.clock.tick(60)

    def pause_menu(game):
        title = "Pause Menu"
        options = ["Continue", "Save Game", "Menu"]
        selected_option = 0
        pause = True
        message = ""
        message_timer = 0
        enter = False

        while pause:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    game.save_game()
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (
                        pygame.K_ESCAPE,
                        pygame.K_BACKSPACE,
                        pygame.K_LEFT,
                    ):
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
                        enter = True
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        enter = True
                if enter:
                    chosen = options[selected_option]
                    if chosen == "Continue":
                        game.paused = False
                        pause = False
                        game.player.shoot_cooldown = 10
                    elif chosen == "Save Game":
                        success, filename = game.tilemap.save_game()
                        if success:
                            message = f"Game saved as {filename}"
                        else:
                            message = "Failed to save game"
                        message_timer = 60
                    elif chosen == "Menu":
                        # game.tilemap.save_game()
                        game.running = False
                        pause = False
                        Menu().menu()
                        return
                if event.type == pygame.KEYUP:
                    enter = False
                if event.type == pygame.MOUSEBUTTONUP:
                    enter = False

            screen = game.screen
            display = game.display_3
            bg = game.assets["background"]

            UI.render_menu_bg(screen, display, bg)
            UI.render_menu_title(screen, title, game.WIN_W // 2, 200)
            UI.render_menu_ui_element(screen, f"{game.timer.text}", game.WIN_W - 130, 5)
            UI.render_menu_ui_element(
                screen, f"{game.timer.best_time_text}", game.WIN_W - 130, 25
            )
            UI.render_menu_ui_element(
                screen, f"Level: {game.level}", game.WIN_W // 2 - 40, 5
            )
            UI.render_menu_ui_element(screen, f"Lives: {game.player.lifes}", 5, 5)
            UI.render_menu_ui_element(screen, f"Coins: ${game.cm.coins}", 5, 25)
            UI.render_menu_ui_element(screen, f"Ammo:  {game.cm.ammo}", 5, 45)
            UI.render_o_box(screen, options, selected_option, game.WIN_W // 2, 450, 50)
            UI.render_menu_ui_element(
                screen, "w/a to navigate", game.WIN_W // 2 - 100, game.WIN_H - 25
            )

            if message_timer > 0:
                UI.render_menu_msg(screen, message, game.WIN_W // 2, 700)
                message_timer -= 1

            pygame.display.update()
            game.clock.tick(60)

        return


if __name__ == "__main__":
    Menu()
