import time
import board
import busio
import adafruit_adxl34x

# Initialize I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize ADXL345
accelerometer = adafruit_adxl34x.ADXL345(i2c)

# Optional: set measurement range (±2G, ±4G, ±8G, ±16G)
accelerometer.range = adafruit_adxl34x.Range.RANGE_4_G

print("ADXL345 Test Started")
print("Press CTRL+C to stop\n")

try:
    while True:
        x, y, z = accelerometer.acceleration  # m/s^2

        print(
            f"X: {x:6.2f} m/s² | "
            f"Y: {y:6.2f} m/s² | "
            f"Z: {z:6.2f} m/s²"
        )

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nTest stopped")
