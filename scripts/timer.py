# timer.py
import json
import os
from datetime import datetime

import pygame

BEST_TIMES_FILE = "data/best_times.json"


class Timer:
    def __init__(self, level):
        self.current_level = str(level)
        self.font = pygame.font.Font(None, 36)
        self.start_time = pygame.time.get_ticks()
        self.current_time = 0
        self.elapsed_time = 0
        self.best_times = self.load_best_times()
        self.best_time = self.get_best_time_value(self.current_level)
        self.text = "00:00.00"
        self.best_time_text = self.format_time(self.best_time) if self.best_time != float("inf") else "--:--:--"

    def update(self, level):
        self.current_level = str(level)
        self.current_time = pygame.time.get_ticks()
        self.elapsed_time = self.current_time - self.start_time
        self.text = self.format_time(self.elapsed_time)
        self.best_time = self.get_best_time_value(self.current_level)
        self.best_time_text = self.format_time(self.best_time) if self.best_time != float("inf") else "--:--:--"

    def format_time(self, time):
        if time == float("inf"):
            return "--:--:--"
        milliseconds = time % 1000 // 10
        seconds = (time // 1000) % 60
        minutes = (time // 60000) % 60
        return f"{minutes:02}:{seconds:02}.{milliseconds:02}"

    def reset(self):
        self.start_time = pygame.time.get_ticks()
        self.elapsed_time = 0
        self.text = self.format_time(self.elapsed_time)

    def load_best_times(self):
        if os.path.exists(BEST_TIMES_FILE):
            try:
                with open(BEST_TIMES_FILE, "r") as file:
                    return json.load(file)
            except json.JSONDecodeError:
                print("Error reading best times file. Creating new one.")
                return {}
        return {}

    def get_best_time_value(self, level):
        val = self.best_times.get(level, float("inf"))
        if isinstance(val, dict):
            return val.get("time", float("inf"))
        else:
            return val

    def update_best_time(self):
        current_time = self.elapsed_time
        old_best = self.get_best_time_value(self.current_level)
        if current_time < old_best:
            self.best_times[self.current_level] = {
                "time": current_time,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.best_time = current_time
            self.best_time_text = self.format_time(self.best_time)
            self.save_best_times()
            return True
        return False

    def save_best_times(self):
        with open(BEST_TIMES_FILE, "w") as file:
            json.dump(self.best_times, file, indent=4, sort_keys=True)
