import pygame
import os

BEST_TIMES_FILE = "data/best_times.txt"

class Timer():
    def __init__(self, level):
        self.current_level = level
        self.font = pygame.font.Font(None, 36)
        self.start_time = pygame.time.get_ticks()
        self.current_time = 0
        self.elapsed_time = 0
        self.best_time = self.load_best_time_for_level()

    def update(self, level):
        self.current_level = level
        self.current_time = pygame.time.get_ticks()
        self.elapsed_time = self.current_time - self.start_time
        self.text = self.format_time(self.elapsed_time)
        

    def format_time(self, time):
        milliseconds = time % 1000 // 10
        seconds = (time // 1000) % 60
        minutes = (time // 60000) % 60
        return f"{minutes:02}:{seconds:02}.{milliseconds:02}"

    def reset(self):
        self.start_time = pygame.time.get_ticks()

    def load_best_time_for_level(self):
        best_times = {}
        if os.path.exists(BEST_TIMES_FILE):
            with open(BEST_TIMES_FILE, "r") as file:
                for line in file:
                    level, time = line.strip().split(":")
                    best_times[self.current_level] = int(time)
        return best_times.get(self.current_level, float('inf'))

    def update_best_time_for_level(self):
        current_time = pygame.time.get_ticks() - self.start_time
        if current_time < self.best_time:
            self.best_time = current_time
            self.save_best_time()

    def save_best_time(self):
        best_times = {}
        if os.path.exists(BEST_TIMES_FILE):
            with open(BEST_TIMES_FILE, "r") as file:
                for line in file:
                    level_str, time = line.strip().split(":")
                    if level_str != str(self.current_level):  # Überprüfen, ob es sich um die Zeile für das aktuelle Level handelt
                        best_times[level_str] = int(time)

        best_times[str(self.current_level)] = self.best_time

        with open(BEST_TIMES_FILE, "w") as file:
            for level_str, time in best_times.items():
                file.write(f"{level_str}:{time}\n")
