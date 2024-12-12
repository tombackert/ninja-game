
import pygame



class UI:

    def get_font(size):
        return pygame.font.Font("data/font.ttf", size)
    
    def render_game_ui(game):
        # Current time
        timer = game.timer.text
        TIMER_TEXT = game.get_font(10).render(f"{timer}", True, "black")
        TIMER_RECT = TIMER_TEXT.get_rect(center=(270, 10))
        game.display_2.blit(TIMER_TEXT, TIMER_RECT)

        # Best time
        best_time = game.timer.best_time_text
        BEST_TIME_TEXT = game.get_font(10).render(f"{best_time}", True, "black")
        BEST_TIME_RECT = BEST_TIME_TEXT.get_rect(center=(270, 25))
        game.display_2.blit(BEST_TIME_TEXT, BEST_TIME_RECT)

        # Display lifes
        lifes = 'LIFES:' + str(game.player.lifes)
        LIFE_TEXT = game.get_font(10).render(lifes, True, "black")
        LIFE_RECT = LIFE_TEXT.get_rect(center=(45, 10))
        game.display_2.blit(LIFE_TEXT, LIFE_RECT)

        # Display level
        level = 'LEVEL:' + str(game.level)
        LEVEL_TEXT = game.get_font(10).render(level, True, "black")
        LEVEL_RECT = LEVEL_TEXT.get_rect(center=(165, 10))
        game.display_2.blit(LEVEL_TEXT, LEVEL_RECT)

        # Coins
        coins_str = 'COINS:' + str(game.collectable_manager.coin_count)
        COIN_TEXT = game.get_font(10).render(coins_str, True, "black")
        COIN_RECT = COIN_TEXT.get_rect(center=(50, 25))
        #game.display_2.blit(COIN_TEXT, COIN_RECT)