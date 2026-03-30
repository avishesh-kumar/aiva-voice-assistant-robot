#!/usr/bin/env python3
"""
Motor + Emergency Stop Test
---------------------------------
- Moves robot forward
- Continuously checks ultrasonic sensor
- Triggers emergency stop immediately on obstacle
"""

import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from motors.movement_controller import MovementController
from sensors.ultrasonic import UltrasonicSensor
from safety.emergency_stop import trigger_emergency_stop


# ===== CONFIG =====
FORWARD_SPEED = 60
SAFE_DISTANCE_CM = 40      # Manual safety threshold
CHECK_INTERVAL = 0.02      # 50 Hz safety check
MAX_RUN_TIME = 20          # seconds
# ==================


def main():
    print("\n=== MOTOR + EMERGENCY STOP TEST ===\n")

    mc = None
    us = None

    try:
        print("[INIT] Initializing motors...")
        mc = MovementController()

        print("[INIT] Initializing ultrasonic sensor...")
        us = UltrasonicSensor()

        print("[TEST] Starting forward movement...")
        mc.forward(speed=FORWARD_SPEED)

        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > MAX_RUN_TIME:
                print("[TEST] Max run time reached, stopping.")
                break

            try:
                distance = us.get_distance_fast("front")
            except Exception as e:
                print(f"[WARN] Ultrasonic read error: {e}")
                distance = None

            if distance is not None:
                print(f"[SENSOR] Front distance: {distance:.1f} cm")

                if 0 < distance <= SAFE_DISTANCE_CM:
                    print(f"\n🚨 OBSTACLE DETECTED at {distance:.1f} cm")
                    print("[ACTION] Triggering EMERGENCY STOP\n")

                    trigger_emergency_stop(mc)
                    break

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Test interrupted by user")

    except Exception as e:
        print(f"[ERROR] Test failed: {e}")

    finally:
        print("[CLEANUP] Stopping motors...")
        try:
            if mc:
                mc.stop()
                mc.cleanup()
        except Exception:
            pass

        print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()
