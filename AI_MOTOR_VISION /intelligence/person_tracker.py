# intelligence/person_tracker.py

import time


class PersonTracker:
    """
    Tracks person motion over time and predicts future position.
    Designed for smooth, human-like follow behavior.
    """

    def __init__(self, reaction_time=0.4, smoothing=0.7):
        """
        Args:
            reaction_time: how far into the future to predict (seconds)
            smoothing: exponential smoothing factor (0–1)
        """
        self.reaction_time = reaction_time
        self.smoothing = smoothing

        self.prev_offset = None
        self.prev_area = None
        self.prev_time = None

        self.offset_velocity = 0.0
        self.area_velocity = 0.0

        self.smoothed_offset = 0.0
        self.smoothed_area = 0.0

    def reset(self):
        """Reset tracking state (called when person lost)."""
        self.prev_offset = None
        self.prev_area = None
        self.prev_time = None
        self.offset_velocity = 0.0
        self.area_velocity = 0.0
        self.smoothed_offset = 0.0
        self.smoothed_area = 0.0

    def update(self, offset, area):
        """
        Update tracker with new observation.

        Args:
            offset: person_offset_x
            area: person_area_ratio

        Returns:
            dict with predicted_offset and predicted_area
        """
        now = time.time()

        # First observation
        if self.prev_time is None:
            self.prev_offset = offset
            self.prev_area = area
            self.prev_time = now
            self.smoothed_offset = offset
            self.smoothed_area = area

            return {
                "predicted_offset": offset,
                "predicted_area": area,
                "offset_velocity": 0.0,
                "area_velocity": 0.0,
            }

        dt = now - self.prev_time
        if dt <= 0:
            dt = 1e-6

        # Compute velocities
        raw_offset_vel = (offset - self.prev_offset) / dt
        raw_area_vel = (area - self.prev_area) / dt

        # Smooth velocities
        self.offset_velocity = (
            self.smoothing * self.offset_velocity
            + (1 - self.smoothing) * raw_offset_vel
        )
        self.area_velocity = (
            self.smoothing * self.area_velocity
            + (1 - self.smoothing) * raw_area_vel
        )

        # Smooth observations
        self.smoothed_offset = (
            self.smoothing * self.smoothed_offset
            + (1 - self.smoothing) * offset
        )
        self.smoothed_area = (
            self.smoothing * self.smoothed_area
            + (1 - self.smoothing) * area
        )

        # Predict future state
        predicted_offset = (
            self.smoothed_offset
            + self.offset_velocity * self.reaction_time
        )
        predicted_area = (
            self.smoothed_area
            + self.area_velocity * self.reaction_time
        )

        # Clamp values to safe ranges
        predicted_offset = max(-1.0, min(1.0, predicted_offset))
        predicted_area = max(0.0, min(1.0, predicted_area))

        # Update previous values
        self.prev_offset = offset
        self.prev_area = area
        self.prev_time = now

        return {
            "predicted_offset": predicted_offset,
            "predicted_area": predicted_area,
            "offset_velocity": self.offset_velocity,
            "area_velocity": self.area_velocity,
        }

