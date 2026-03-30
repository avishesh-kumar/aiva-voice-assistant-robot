import time


class SpatialMemory:
    """
    Lightweight session-only spatial memory.
    Tracks recently used directions to avoid loops.
    """

    def __init__(self, memory_window=3.0):
        # seconds to consider a direction "recent"
        self.memory_window = memory_window

        # direction -> last time used
        self.recent_directions = {
            "LEFT": 0.0,
            "RIGHT": 0.0,
            "FORWARD": 0.0,
            "BACKWARD": 0.0,
        }

    def mark_direction(self, direction: str):
        """Mark a direction as recently used."""
        self.recent_directions[direction] = time.time()

    def is_recent(self, direction: str) -> bool:
        """Check if direction was used recently."""
        last_time = self.recent_directions.get(direction, 0.0)
        return (time.time() - last_time) < self.memory_window

    def choose_search_direction(self):
        """
        Choose the best direction to search.
        Prefers directions not used recently.
        """
        now = time.time()

        scores = {}
        for direction, last_time in self.recent_directions.items():
            age = now - last_time
            scores[direction] = age

        # Sort directions by least recently used
        sorted_dirs = sorted(scores.items(), key=lambda x: -x[1])

        # Return the best candidate
        return sorted_dirs[0][0]
    def reset(self):
        """Reset recent direction memory."""
        for direction in self.recent_directions:
            self.recent_directions[direction] = 0.0


