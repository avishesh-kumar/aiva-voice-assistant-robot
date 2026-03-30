# memory/grid_memory.py

import math


class GridMemory:
    """
    Lightweight 2D occupancy grid.
    Session-only spatial memory.
    """

    UNKNOWN = 0
    FREE = 1
    OBSTACLE = 2
    VISITED = 3

    def __init__(self, size=21):
        """
        Args:
            size: grid width/height (odd number, robot starts in center)
        """
        self.size = size

        self.grid = [
            [self.UNKNOWN for _ in range(size)]
            for _ in range(size)
        ]

        # Robot starts at center
        self.cx = size // 2
        self.cy = size // 2
        self.heading = 0  # 0=up, 1=right, 2=down, 3=left

        self.grid[self.cy][self.cx] = self.VISITED

    # -------------------------------------------------
    def choose_search_direction(self):
        """
        Choose LEFT or RIGHT based on which side
        looks less explored and less blocked.
        """
        scores = {}

        for direction in ["LEFT", "RIGHT"]:
            nx, ny = self._cell_in_direction(direction)

            if not self._in_bounds(nx, ny):
                scores[direction] = -999
                continue

            cell = self.grid[ny][nx]

            if cell == self.OBSTACLE:
                scores[direction] = -100
            elif cell == self.UNKNOWN:
                scores[direction] = 50
            elif cell == self.FREE:
                scores[direction] = 20
            elif cell == self.VISITED:
                scores[direction] = 5
            else:
                scores[direction] = 0

        # Choose best direction
        return max(scores, key=scores.get)
    def _cell_in_direction(self, direction):
        if direction == "LEFT":
            h = (self.heading - 1) % 4
        elif direction == "RIGHT":
            h = (self.heading + 1) % 4
        else:
            h = self.heading

        if h == 0:
            return self.cx, self.cy - 1
        elif h == 1:
            return self.cx + 1, self.cy
        elif h == 2:
            return self.cx, self.cy + 1
        else:
            return self.cx - 1, self.cy


    def mark_obstacle_ahead(self):
        nx, ny = self._cell_in_front()
        if self._in_bounds(nx, ny):
            self.grid[ny][nx] = self.OBSTACLE

    def mark_free_ahead(self):
        nx, ny = self._cell_in_front()
        if self._in_bounds(nx, ny):
            if self.grid[ny][nx] == self.UNKNOWN:
                self.grid[ny][nx] = self.FREE

    def move_forward(self):
        nx, ny = self._cell_in_front()
        if self._in_bounds(nx, ny):
            self.cx, self.cy = nx, ny
            self.grid[ny][nx] = self.VISITED

    def turn_left(self):
        self.heading = (self.heading - 1) % 4

    def turn_right(self):
        self.heading = (self.heading + 1) % 4

    # -------------------------------------------------

    def _cell_in_front(self):
        if self.heading == 0:      # up
            return self.cx, self.cy - 1
        elif self.heading == 1:    # right
            return self.cx + 1, self.cy
        elif self.heading == 2:    # down
            return self.cx, self.cy + 1
        else:                      # left
            return self.cx - 1, self.cy

    def _in_bounds(self, x, y):
        return 0 <= x < self.size and 0 <= y < self.size
