import pygame, sys
from scripts.button import Button
from game import Game

pygame.init()

SCREEN = pygame.display.set_mode((640, 480))
pygame.display.set_caption("Menu")

BG = pygame.image.load("data/menu/Background.png")

def get_font(size): # Returns Press-Start-2P in the desired size
    return pygame.font.Font("data/menu/font.ttf", size)

def play():
    Game().run()

def levels():
    while True:
        LEVELS_MOUSE_POS = pygame.mouse.get_pos()

        SCREEN.fill("white")

        LEVELS_TEXT = get_font(25).render("This is the LEVELS screen.", True, "Black")
        LEVELS_RECT = LEVELS_TEXT.get_rect(center=(320, 160))
        SCREEN.blit(LEVELS_TEXT, LEVELS_RECT)

        LEVELS_BACK = Button(image=None, pos=(320, 400), 
                            text_input="BACK", font=get_font(50), base_color="Black", hovering_color="Green")

        LEVELS_BACK.changeColor(LEVELS_MOUSE_POS)
        LEVELS_BACK.update(SCREEN)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if LEVELS_BACK.checkForInput(LEVELS_MOUSE_POS):
                    main_menu()

        pygame.display.update()

def store():
    while True:
        STORE_MOUSE_POS = pygame.mouse.get_pos()

        SCREEN.fill("black")

        STORE_TEXT = get_font(25).render("This is the STORE screen.", True, "White")
        STORE_RECT = STORE_TEXT.get_rect(center=(320, 160))
        SCREEN.blit(STORE_TEXT, STORE_RECT)

        STORE_BACK = Button(image=None, pos=(320, 400), 
                            text_input="BACK", font=get_font(50), base_color="White", hovering_color="Green")

        STORE_BACK.changeColor(STORE_MOUSE_POS)
        STORE_BACK.update(SCREEN)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if STORE_BACK.checkForInput(STORE_MOUSE_POS):
                    main_menu()

        pygame.display.update()

def options():
    while True:
        OPTIONS_MOUSE_POS = pygame.mouse.get_pos()

        SCREEN.fill("white")

        OPTIONS_TEXT = get_font(25).render("This is the OPTIONS screen.", True, "Black")
        OPTIONS_RECT = OPTIONS_TEXT.get_rect(center=(320, 160))
        SCREEN.blit(OPTIONS_TEXT, OPTIONS_RECT)

        OPTIONS_BACK = Button(image=None, pos=(320, 400), 
                            text_input="BACK", font=get_font(50), base_color="Black", hovering_color="Green")

        OPTIONS_BACK.changeColor(OPTIONS_MOUSE_POS)
        OPTIONS_BACK.update(SCREEN)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if OPTIONS_BACK.checkForInput(OPTIONS_MOUSE_POS):
                    main_menu()

        pygame.display.update()

def main_menu():
    while True:
        SCREEN.blit(BG, (0, 0))

        MENU_MOUSE_POS = pygame.mouse.get_pos()

        MENU_TEXT = get_font(50).render("MAIN MENU", True, "#b68f40")
        MENU_RECT = MENU_TEXT.get_rect(center=(320, 50))

        PLAY_BUTTON = Button(image=None, pos=(320, 180), 
                            text_input="PLAY", font=get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
        LEVELS_BUTTON = Button(image=None, pos=(320, 245),
                            text_input="LEVELS", font=get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
        STORE_BUTTON = Button(image=None, pos=(320, 310),
                            text_input="STORE", font=get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
        OPTIONS_BUTTON = Button(image=None, pos=(320, 375), 
                            text_input="OPTIONS", font=get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")
        QUIT_BUTTON = Button(image=None, pos=(320, 440), 
                            text_input="QUIT", font=get_font(25), base_color="#d7fcd4", hovering_color="#b68f40")

        SCREEN.blit(MENU_TEXT, MENU_RECT)

        for button in [PLAY_BUTTON, LEVELS_BUTTON, STORE_BUTTON, OPTIONS_BUTTON, QUIT_BUTTON]:
            button.changeColor(MENU_MOUSE_POS)
            button.update(SCREEN)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if PLAY_BUTTON.checkForInput(MENU_MOUSE_POS):
                    play()
                if LEVELS_BUTTON.checkForInput(MENU_MOUSE_POS):
                    levels()
                if STORE_BUTTON.checkForInput(MENU_MOUSE_POS):
                    store()
                if OPTIONS_BUTTON.checkForInput(MENU_MOUSE_POS):
                    options()
                if QUIT_BUTTON.checkForInput(MENU_MOUSE_POS):
                    pygame.quit()
                    sys.exit()

        pygame.display.update()

main_menu()