from smbus2 import SMBus
import time

class ADXL345:
    ADDR = 0x53

    def __init__(self, bus=1):
        self.bus = SMBus(bus)
        self.bus.write_byte_data(self.ADDR, 0x2D, 0x08)  # Measurement mode
        time.sleep(0.05)

        self.ax = 0
        self.ay = 0
        self.az = 0

    def _read_word(self, reg):
        try:
            l = self.bus.read_byte_data(self.ADDR, reg)
            h = self.bus.read_byte_data(self.ADDR, reg + 1)
            val = (h << 8) | l
            if val & (1 << 15):
                val -= 1 << 16
            return val
        except OSError:
            return None

    def read(self):
        x = self._read_word(0x32)
        y = self._read_word(0x34)
        z = self._read_word(0x36)

        if x is None or y is None or z is None:
            return None

        # Low-pass filter (critical)
        self.ax = int(self.ax * 0.7 + x * 0.3)
        self.ay = int(self.ay * 0.7 + y * 0.3)
        self.az = int(self.az * 0.7 + z * 0.3)

        return self.ax, self.ay, self.az
