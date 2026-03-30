import time
import board
import busio
import adafruit_adxl34x


class ADXL345IMU:
    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.sensor = adafruit_adxl34x.ADXL345(i2c)

        # Best resolution for motion intent
        self.sensor.range = adafruit_adxl34x.Range.RANGE_2_G

        # Simple low-pass filter state
        self.alpha = 0.3
        self.fx = self.fy = self.fz = 0.0

    def read(self):
        x, y, z = self.sensor.acceleration

        # Low-pass filter
        self.fx = self.alpha * x + (1 - self.alpha) * self.fx
        self.fy = self.alpha * y + (1 - self.alpha) * self.fy
        self.fz = self.alpha * z + (1 - self.alpha) * self.fz

        return {
            "x": round(self.fx, 3),
            "y": round(self.fy, 3),
            "z": round(self.fz, 3),
        }
