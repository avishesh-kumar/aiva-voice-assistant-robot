"""
Movement Controller for robot navigation.
Uses MotorDriver for low-level motor control.
"""
import time
from config.hardware_config import FORWARD_100CM_TIME, TURN_90DEG_TIME
from motors.motor_driver import MotorDriver

# Debug flag to reduce console spam
DEBUG_MOVEMENT = False


class MovementController:
    """High-level movement controller for robot navigation."""
    
    def __init__(self):
        """Initialize movement controller with motor driver."""
        self.motor = MotorDriver()
        self.is_moving = False
        self.current_movement = None  # Track current movement type
        if DEBUG_MOVEMENT:
            print("[MOVEMENT] Movement controller initialized")

    def _arc_turn(self, direction, speed):
        """
        Smooth arc turn using differential speed.
        """
        base = speed
        delta = int(speed * 0.45)   # curvature factor

        if direction == "LEFT":
            self.motor.set_speed(base - delta, base)
        else:
            self.motor.set_speed(base, base - delta)
    
    def forward(self, speed: int = 50, distance_cm: int = None):
        """
        Move robot forward.
        
        Args:
            speed: Speed percentage (0-100)
            distance_cm: Optional distance in cm to move (non-blocking)
        """
        if DEBUG_MOVEMENT:
            print(f"[MOVEMENT] Forward: speed={speed}, distance={distance_cm}cm")
        
        # Set movement state
        self.is_moving = True
        self.current_movement = "FORWARD"
        
        # Start movement immediately (non-blocking)
        self.motor.set_speed(speed, speed)
    
    def backward(self, speed: int = 50, distance_cm: int = None):
        """
        Move robot backward.
        
        Args:
            speed: Speed percentage (0-100)
            distance_cm: Optional distance in cm to move (non-blocking)
        """
        if DEBUG_MOVEMENT:
            print(f"[MOVEMENT] Backward: speed={speed}, distance={distance_cm}cm")
        
        # Set movement state
        self.is_moving = True
        self.current_movement = "BACKWARD"
        
        # Start movement immediately (non-blocking)
        self.motor.set_speed(-speed, -speed)
    
    def turn(self, direction, speed):
        """
        Hybrid turning:
        - Small speed → arc turn
        - High speed → in-place turn
        """

        ARC_THRESHOLD = 45   # 🔥 key value

        if speed < ARC_THRESHOLD:
            # ✅ Smooth arc turn
            self._arc_turn(direction, speed)
        else:
            # ✅ Precise in-place turn (kept for large correction)
            if direction == "LEFT":
                self.motor.set_speed(speed, -speed)
            else:
                self.motor.set_speed(-speed, speed)

    def turn_left(self, speed: int = 50, angle: int = None):
        self.is_moving = True
        self.current_movement = "TURN_LEFT"
        self.turn("LEFT", speed)

    def turn_right(self, speed: int = 50, angle: int = None):
        self.is_moving = True
        self.current_movement = "TURN_RIGHT"
        self.turn("RIGHT", speed)
    
    # --- MODIFIED ---
    def stop(self):
        """Stop all movement immediately (HARD STOP)."""
        if self.is_moving or self.current_movement:
            self.motor.stop()   # Ensure complete stop
            
            self.is_moving = False
            self.current_movement = None
            if DEBUG_MOVEMENT:
                print("[MOVEMENT] Hard stop executed")
    # --- END MODIFIED ---
    
    def estimate_forward_time(self, distance_cm: int, speed: int = 50) -> float:
        """
        Estimate time needed to move forward/backward a given distance.
        
        Args:
            distance_cm: Distance in cm
            speed: Speed percentage (0-100)
            
        Returns:
            float: Estimated time in seconds
        """
        if distance_cm <= 0:
            return 0.0
        
        # Calculate time needed based on calibration
        # Using formula: time = (distance/100) * FORWARD_100CM_TIME * (50/speed)
        base_time_per_cm = FORWARD_100CM_TIME / 100.0
        speed_factor = 50.0 / max(1, speed)  # Avoid division by zero
        return (distance_cm * base_time_per_cm) * speed_factor
    
    def estimate_turn_time(self, angle: int, speed: int = 50) -> float:
        """
        Estimate time needed to turn a given angle.
        
        Args:
            angle: Angle in degrees
            speed: Speed percentage (0-100)
            
        Returns:
            float: Estimated time in seconds
        """
        if angle <= 0:
            return 0.0
        
        # Calculate time needed based on calibration
        # Using formula: time = (angle/90) * TURN_90DEG_TIME * (50/speed)
        base_time_per_degree = TURN_90DEG_TIME / 90.0
        speed_factor = 50.0 / max(1, speed)  # Avoid division by zero
        return (angle * base_time_per_degree) * speed_factor
    
    def cleanup(self):
        """Clean up motor driver resources."""
        if DEBUG_MOVEMENT:
            print("[MOVEMENT] Cleaning up movement controller...")
        self.stop()
        self.motor.cleanup()
        if DEBUG_MOVEMENT:
            print("[MOVEMENT] Cleanup complete")
    
    def get_status(self):
        """Get current movement status."""
        return {
            "is_moving": self.is_moving,
            "current_movement": self.current_movement,
            "motor_status": self.motor.get_status()
        }


# Test function
if __name__ == "__main__":
    print("Testing MovementController...")
    
    try:
        controller = MovementController()
        
        # Test forward movement (non-blocking)
        print("\n1. Moving forward 30cm at speed 40 (non-blocking)...")
        controller.forward(speed=40, distance_cm=30)
        estimated_time = controller.estimate_forward_time(30, 40)
        print(f"   Estimated time: {estimated_time:.2f}s")
        time.sleep(estimated_time)
        controller.stop()
        time.sleep(1)
        
        # Test backward movement (non-blocking)
        print("\n2. Moving backward 20cm at speed 30 (non-blocking)...")
        controller.backward(speed=30, distance_cm=20)
        estimated_time = controller.estimate_forward_time(20, 30)
        print(f"   Estimated time: {estimated_time:.2f}s")
        time.sleep(estimated_time)
        controller.stop()
        time.sleep(1)
        
        # Test left turn (non-blocking)
        print("\n3. Turning left 45 degrees at speed 50 (non-blocking)...")
        controller.turn_left(speed=50, angle=45)
        estimated_time = controller.estimate_turn_time(45, 50)
        print(f"   Estimated time: {estimated_time:.2f}s")
        time.sleep(estimated_time)
        controller.stop()
        time.sleep(1)
        
        # Test right turn (non-blocking)
        print("\n4. Turning right 90 degrees at speed 60 (non-blocking)...")
        controller.turn_right(speed=60, angle=90)
        estimated_time = controller.estimate_turn_time(90, 60)
        print(f"   Estimated time: {estimated_time:.2f}s")
        time.sleep(estimated_time)
        controller.stop()
        time.sleep(1)
        
        # Test continuous movement with stop
        print("\n5. Continuous forward movement...")
        controller.forward(speed=40)
        time.sleep(2)
        controller.stop()
        
        print("\nAll tests completed successfully!")
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        controller.cleanup()
