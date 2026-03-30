import threading
import time


class RobotState:
    def __init__(self):
        self._lock = threading.Lock()

        # Latest IMU data
        self.imu = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "timestamp": 0.0,
        }

    def update_imu(self, x, y, z, timestamp):
        with self._lock:
            self.imu["x"] = x
            self.imu["y"] = y
            self.imu["z"] = z
            self.imu["timestamp"] = timestamp

    def get_imu(self):
        with self._lock:
            return dict(self.imu)

