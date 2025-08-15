import sys
import time
import platform
import random

import pygame


def main(num_balls=1000, run_time=10):
    """
    Ein einfaches Performance-Testskript für Pygame-CE.
    Zeichnet 'num_balls' Bälle, die zufällig durch das Fenster bouncen,
    und misst die FPS über 'run_time' Sekunden.
    """
    # -- System-/Versions-Infos --
    print("=== Pygame-CE Performance Test ===")
    print(f"Python Version: {sys.version}")
    print(f"Platform:       {platform.platform()}")
    print(f"Pygame Version: {pygame.version.ver}")
    print(f"SDL Version:    {pygame.version.SDL}")

    pygame.init()

    # Video-Backend (z.B. "cocoa" auf macOS, "win32" oder "directx" auf Windows)
    # Beachte: Das allein sagt nicht immer aus, ob HW-Beschleunigung an ist.
    try:
        current_video_driver = pygame.display.get_driver()
        print(f"Video driver:   {current_video_driver}")
    except:
        print("Video driver could not be determined.")

    # -- Fenster erstellen --
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Pygame-CE Performance Test")

    clock = pygame.time.Clock()

    # -- Bälle initialisieren --
    balls = []
    for _ in range(num_balls):
        x = random.randint(0, 800 - 10)
        y = random.randint(0, 600 - 10)
        dx = random.choice([-3, -2, -1, 1, 2, 3])
        dy = random.choice([-3, -2, -1, 1, 2, 3])
        balls.append([x, y, dx, dy])

    start_time = time.time()
    frames = 0

    # -- Hauptloop: run_time Sekunden --
    while True:
        elapsed = time.time() - start_time
        if elapsed >= run_time:
            break

        # Events abfragen
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # Logik & Zeichnen
        screen.fill((0, 0, 0))

        for b in balls:
            # Position aktualisieren
            b[0] += b[2]
            b[1] += b[3]
            # Abprallen an den Rändern
            if b[0] < 0 or b[0] > 790:
                b[2] *= -1
            if b[1] < 0 or b[1] > 590:
                b[3] *= -1

            # Ball zeichnen
            pygame.draw.circle(screen, (255, 255, 255), (b[0], b[1]), 10)

        pygame.display.flip()

        # Tick ohne FPS-Limit, um "echte" Performance zu messen
        clock.tick()
        frames += 1

    # -- Ergebnis ausgeben --
    pygame.quit()

    total_time = time.time() - start_time
    avg_fps = frames / total_time if total_time > 0 else 0

    print("\n=== Test-Ergebnis ===")
    print(f"Anzahl Bälle:        {num_balls}")
    print(f"Laufzeit:            {total_time:.2f} Sekunden")
    print(f"Gerenderte Frames:   {frames}")
    print(f"Durchschn. FPS:      {avg_fps:.2f}")


if __name__ == "__main__":
    main()
