import random

import pygame


class Effects:
    """
    Class that handles all game effects
    """

    def screenshake(game):
        screenshake_offset = (
            random.random() * game.screenshake - game.screenshake / 2,
            random.random() * game.screenshake - game.screenshake / 2,
        )
        # Without the spare sub-pixel column/row (the legacy loop does not shift)
        view = game.display_2.subsurface((0, 0, game.BASE_W, game.BASE_H))
        game.screen.blit(
            pygame.transform.scale(view, game.screen.get_size()),
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
