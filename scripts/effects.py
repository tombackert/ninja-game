import pygame
import random


class Effects:
    """
    Class that handles all game effects
    """

    def screenshake(game):
        screenshake_offset = (
            random.random() * game.screenshake - game.screenshake / 2,
            random.random() * game.screenshake - game.screenshake / 2,
        )
        game.screen.blit(
            pygame.transform.scale(game.display_2, game.screen.get_size()),
            screenshake_offset,
        )

    def transition(game):
        transition_surf = pygame.Surface(game.display.get_size())
        pygame.draw.circle(
            transition_surf,
            (255, 255, 255),
            (game.display.get_width() // 2, game.display.get_height() // 2),
            (30 - abs(game.transition)) * 8,
        )
        transition_surf.set_colorkey((255, 255, 255))
        game.display.blit(transition_surf, (0, 0))
