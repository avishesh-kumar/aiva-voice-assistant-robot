"""
Ultrasonic Sensor (HC-SR04) for distance measurement.
Supports 3 sensors: FRONT, LEFT, and RIGHT.
"""
import time
import statistics
from config.hardware_config import (
    ULTRASONIC_FRONT_TRIG, ULTRASONIC_FRONT_ECHO,
    ULTRASONIC_LEFT_TRIG, ULTRASONIC_LEFT_ECHO,
    ULTRASONIC_RIGHT_TRIG, ULTRASONIC_RIGHT_ECHO
)

try:
    # Try using gpiozero first
    from gpiozero import DistanceSensor
    GPIOZERO_AVAILABLE = True
    print("[ULTRASONIC] Using gpiozero for sensor control")
except ImportError:
    # Fall back to RPi.GPIO
    try:
        import RPi.GPIO as GPIO
        GPIOZERO_AVAILABLE = False
        print("[ULTRASONIC] Using RPi.GPIO for sensor control")
    except ImportError:
        print("[ULTRASONIC] ERROR: No GPIO library available! Running in simulation mode.")
        GPIOZERO_AVAILABLE = None


class UltrasonicSensor:
    """Ultrasonic distance sensor system for 3-direction obstacle detection."""

    # Fail-safe constants
    MAX_FAILS = 6  # After this many consecutive failures, treat as obstacle
    # --- MODIFIED ---
    FAILURE_DISTANCE = None  # Return None on failure instead of treating as obstacle
    # --- END MODIFIED ---
    OBSTACLE_THRESHOLD_CM = 40.0  # Default obstacle threshold (cm)

    def __init__(self):
        """Initialize all 3 ultrasonic sensors with specified GPIO pins."""
        # --- MODIFIED ---
        self.last_distances = {"front": None, "left": None, "right": None}
        # --- END MODIFIED ---
        self.is_active = False
        self._fast_cache = {
            # --- MODIFIED ---
            "front": (0.0, None),  # (timestamp, distance) - None indicates no valid reading
            "left": (0.0, None),
            "right": (0.0, None)
            # --- END MODIFIED ---
        }

        # Failure counters for each sensor
        self._failure_counters = {"front": 0, "left": 0, "right": 0}

        # Smaller cache window = fresher reads in safety loop
        self._fast_cache_window = 0.006  # seconds

        # Pin configuration for all sensors
        self.sensor_pins = {
            "front": {"trigger": ULTRASONIC_FRONT_TRIG, "echo": ULTRASONIC_FRONT_ECHO},
            "left": {"trigger": ULTRASONIC_LEFT_TRIG, "echo": ULTRASONIC_LEFT_ECHO},
            "right": {"trigger": ULTRASONIC_RIGHT_TRIG, "echo": ULTRASONIC_RIGHT_ECHO}
        }

        if GPIOZERO_AVAILABLE is None:
            # Simulation mode
            print("[ULTRASONIC] Running in simulation mode")
            self.simulation_mode = True
            self.simulation_distances = {"front": 100.0, "left": 100.0, "right": 100.0}
            return

        self.simulation_mode = False
        self.sensors = {}

        if GPIOZERO_AVAILABLE:
            self._init_all_gpiozero()
        else:
            self._init_all_rpigpio()

        self.is_active = True
        print("[ULTRASONIC] Ultrasonic sensors initialized")

    def _init_all_gpiozero(self):
        """Initialize all 3 sensors using gpiozero library."""
        try:
            for sensor_name, pins in self.sensor_pins.items():
                self.sensors[sensor_name] = DistanceSensor(
                    echo=pins["echo"],
                    trigger=pins["trigger"],
                    max_distance=4.0,  # 4 meters max range
                    threshold_distance=0.3  # 30cm threshold for events
                )
            print(
                f"[ULTRASONIC] Sensors initialized - FRONT: trig={self.sensor_pins['front']['trigger']}/echo={self.sensor_pins['front']['echo']}, "
                f"LEFT: trig={self.sensor_pins['left']['trigger']}/echo={self.sensor_pins['left']['echo']}, "
                f"RIGHT: trig={self.sensor_pins['right']['trigger']}/echo={self.sensor_pins['right']['echo']}"
            )
        except Exception as e:
            print(f"[ULTRASONIC] Error initializing gpiozero sensors: {e}")
            self.simulation_mode = True

    def _init_all_rpigpio(self):
        """Initialize all 3 sensors using RPi.GPIO library."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for sensor_name, pins in self.sensor_pins.items():
                GPIO.setup(pins["trigger"], GPIO.OUT)
                GPIO.setup(pins["echo"], GPIO.IN)
                GPIO.output(pins["trigger"], False)

            time.sleep(0.5)  # Settling time
            print(
                f"[ULTRASONIC] Sensors initialized - FRONT: trig={self.sensor_pins['front']['trigger']}/echo={self.sensor_pins['front']['echo']}, "
                f"LEFT: trig={self.sensor_pins['left']['trigger']}/echo={self.sensor_pins['left']['echo']}, "
                f"RIGHT: trig={self.sensor_pins['right']['trigger']}/echo={self.sensor_pins['right']['echo']}"
            )
        except Exception as e:
            print(f"[ULTRASONIC] Error initializing RPi.GPIO: {e}")
            self.simulation_mode = True

    def _measure_single_distance(self, sensor_name: str) -> float:
        """Measure single distance for a specific sensor."""
        if self.simulation_mode:
            import random
            self.simulation_distances[sensor_name] += random.uniform(-5, 5)
            if self.simulation_distances[sensor_name] < 5:
                self.simulation_distances[sensor_name] = 5
            elif self.simulation_distances[sensor_name] > 200:
                self.simulation_distances[sensor_name] = 200
            return self.simulation_distances[sensor_name]

        try:
            if GPIOZERO_AVAILABLE:
                distance_m = self.sensors[sensor_name].distance
                if distance_m is None:
                    return None
                return distance_m * 100.0
            else:
                pins = self.sensor_pins[sensor_name]

                # Trigger pulse
                GPIO.output(pins["trigger"], True)
                time.sleep(0.00001)
                GPIO.output(pins["trigger"], False)

                # Faster timeouts = faster fail-safe behavior
                timeout_s = 0.012

                # Wait echo HIGH
                start_wait = time.monotonic()
                while GPIO.input(pins["echo"]) == 0:
                    if (time.monotonic() - start_wait) > timeout_s:
                        return None

                pulse_start = time.monotonic()

                # Wait echo LOW
                start_wait = time.monotonic()
                while GPIO.input(pins["echo"]) == 1:
                    if (time.monotonic() - start_wait) > timeout_s:
                        return None

                pulse_end = time.monotonic()

                pulse_duration = pulse_end - pulse_start
                distance = pulse_duration * 17150
                return distance

        except Exception:
            return None

    def _get_measurement_with_fail_safe(self, sensor_name: str):
        """
        Get measurement with fail-safe handling.
        Increments failure counter on invalid readings, resets on valid readings.
        Returns None if MAX_FAILS exceeded.
        """
        distance = self._measure_single_distance(sensor_name)
        
        # Check if measurement is valid
        # --- MODIFIED ---
        if distance is not None and 0 < distance <= 400:
        # --- END MODIFIED ---
            # Valid reading - reset failure counter
            self._failure_counters[sensor_name] = 0
            return distance
        else:
            # Invalid reading - increment failure counter
            self._failure_counters[sensor_name] += 1
            
            # If too many failures, treat as no reading (safe)
            # --- MODIFIED ---
            if self._failure_counters[sensor_name] >= self.MAX_FAILS:
                return None  # Sensor failure, don't treat as obstacle
            else:
                return distance  # Return None or invalid reading
            # --- END MODIFIED ---

    def _get_filtered_distance(self, sensor_name: str, samples: int = 5, delay: float = 0.02):
        """Get filtered distance measurement for a specific sensor."""
        valid_readings = []

        for i in range(samples):
            # Use fail-safe measurement
            distance = self._get_measurement_with_fail_safe(sensor_name)
            
            # --- MODIFIED ---
            # If sensor is failing, return None (safe)
            if distance is None:
                self.last_distances[sensor_name] = None
                return None
            # --- END MODIFIED ---
            
            # Only add valid distances to readings
            # --- MODIFIED ---
            if distance is not None and 0 < distance <= 400:
            # --- END MODIFIED ---
                valid_readings.append(distance)

            if i < samples - 1:
                time.sleep(delay)

        if valid_readings:
            median_distance = statistics.median(valid_readings)
            self.last_distances[sensor_name] = median_distance
            return median_distance
        else:
            # --- MODIFIED ---
            self.last_distances[sensor_name] = None
            return None
            # --- END MODIFIED ---

    def get_distance(self, sensor: str = "front", samples: int = 5):
        """Get distance measurement from a specific sensor."""
        if sensor not in ["front", "left", "right"]:
            raise ValueError(f"Invalid sensor: {sensor}. Must be 'front', 'left', or 'right'")
        return self._get_filtered_distance(sensor, samples)

    def get_distance_fast(self, sensor: str = "front"):
        """
        Fast distance read for safety stop (very low latency).
        Uses 1 quick measurement and optional short caching.
        """
        if sensor not in ["front", "left", "right"]:
            raise ValueError(f"Invalid sensor: {sensor}. Must be 'front', 'left', or 'right'")

        now = time.monotonic()

        # Check cache first
        last_ts, last_val = self._fast_cache.get(sensor, (0.0, None))
        if (now - last_ts) < self._fast_cache_window:
            # If cached value exists, return it
            # --- MODIFIED ---
            if last_val is not None:
                return last_val
            else:
                return None  # No valid reading in cache
            # --- END MODIFIED ---

        # Get new measurement with fail-safe
        d = self._get_measurement_with_fail_safe(sensor)
        
        # Update cache
        self._fast_cache[sensor] = (now, d)
        self.last_distances[sensor] = d
        
        return d
    
    def get_distance_reflex(self, sensor: str):
        """
        Ultra-fast RAW distance read for emergency stop.
        NO filtering, NO cache, NO retries, NO fail-safe logic.
        """
        try:
            return self._measure_single_distance(sensor)
        except Exception:
            # --- MODIFIED ---
            return None  # Safe on failure
            # --- END MODIFIED ---

    def get_front_distance(self, samples: int = 5):
        return self._get_filtered_distance("front", samples)

    def get_left_distance(self, samples: int = 5):
        return self._get_filtered_distance("left", samples)

    def get_right_distance(self, samples: int = 5):
        return self._get_filtered_distance("right", samples)

    def get_all_distances(self, samples: int = 5) -> dict:
        return {
            "front": self.get_front_distance(samples),
            "left": self.get_left_distance(samples),
            "right": self.get_right_distance(samples)
        }

    def get_blocking_sensor_for_motion(self, motion: str) -> str:
        motion = motion.upper()

        if motion == "FORWARD":
            return "front"
        elif motion == "LEFT":
            return "left"
        elif motion == "RIGHT":
            return "right"
        elif motion == "BACKWARD":
            return None
        elif motion == "STOP":
            return None
        else:
            raise ValueError(f"Invalid motion: {motion}")

    def is_obstacle(self, sensor: str = "front", threshold_cm: float = None) -> bool:
        if threshold_cm is None:
            threshold_cm = self.OBSTACLE_THRESHOLD_CM
            
        distance = self.get_distance(sensor)
        # --- MODIFIED ---
        # Only treat as obstacle if distance is valid and below threshold
        return distance is not None and distance <= threshold_cm
        # --- END MODIFIED ---

    def is_obstacle_ahead(self, threshold_cm: int = None) -> bool:
        if threshold_cm is None:
            threshold_cm = self.OBSTACLE_THRESHOLD_CM
        return self.is_obstacle("front", threshold_cm)

    def is_obstacle_any_direction(self, threshold_cm: int = None) -> dict:
        if threshold_cm is None:
            threshold_cm = self.OBSTACLE_THRESHOLD_CM
        distances = self.get_all_distances()
        return {
            # --- MODIFIED ---
            "front": distances["front"] is not None and distances["front"] <= threshold_cm,
            "left": distances["left"] is not None and distances["left"] <= threshold_cm,
            "right": distances["right"] is not None and distances["right"] <= threshold_cm
            # --- END MODIFIED ---
        }

    def get_average_distance(self, sensor_name: str = "front", samples: int = 3):
        if samples < 1:
            samples = 1

        total = 0.0
        valid_samples = 0

        for _ in range(samples):
            distance = self._get_filtered_distance(sensor_name, samples=5)
            # --- MODIFIED ---
            if distance is not None and distance < 400:
            # --- END MODIFIED ---
                total += distance
                valid_samples += 1
            time.sleep(0.05)

        if valid_samples > 0:
            return total / valid_samples
        else:
            # --- MODIFIED ---
            return None  # Safe on failure
            # --- END MODIFIED ---

    def cleanup(self):
        """Clean up all sensor resources."""
        if not self.is_active:
            return

        print("[ULTRASONIC] Cleaning up sensors...")

        if GPIOZERO_AVAILABLE and not self.simulation_mode:
            for sensor_name, sensor in self.sensors.items():
                try:
                    sensor.close()
                except:
                    pass
        elif not GPIOZERO_AVAILABLE and not self.simulation_mode:
            try:
                GPIO.cleanup()
            except:
                pass

        self.is_active = False
        print("[ULTRASONIC] Cleanup complete")

    def get_status(self):
        return {
            "active": self.is_active,
            "simulation": self.simulation_mode,
            "last_distances": self.last_distances,
            "failure_counters": self._failure_counters
        }


if __name__ == "__main__":
    print("Testing UltrasonicSensor System...")
    print("Testing all 3 sensors: FRONT, LEFT, RIGHT")
    print("Press Ctrl+C to stop\n")

    try:
        sensor = UltrasonicSensor()

        test_count = 0
        while True:
            test_count += 1
            print(f"\n--- Test #{test_count} ---")

            distances = sensor.get_all_distances()
            print(f"FRONT: {distances['front']} cm")
            print(f"LEFT: {distances['left']} cm")
            print(f"RIGHT: {distances['right']} cm")

            front_dist = sensor.get_distance("front")
            print(f"Using get_distance('front'): {front_dist} cm")

            motions = ["FORWARD", "LEFT", "RIGHT", "BACKWARD", "STOP"]
            for motion in motions:
                blocking_sensor = sensor.get_blocking_sensor_for_motion(motion)
                print(f"Blocking sensor for {motion}: {blocking_sensor}")

            obstacle_front = sensor.is_obstacle("front", 30)
            obstacle_left = sensor.is_obstacle("left", 30)
            obstacle_right = sensor.is_obstacle("right", 30)
            print(
                f"Obstacle detection (30cm threshold): Front={obstacle_front}, Left={obstacle_left}, Right={obstacle_right}"
            )

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nTest stopped by user")
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        sensor.cleanup()
