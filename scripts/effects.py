import pygame


class Effects:
    """
    Class that handles all game effects
    """

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
