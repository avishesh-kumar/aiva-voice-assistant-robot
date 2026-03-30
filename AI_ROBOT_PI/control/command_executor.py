import time
from typing import Dict, Any
from motors.movement_controller import MovementController
from sensors.ultrasonic import UltrasonicSensor
# --- MODIFIED ---
from safety.emergency_stop import trigger_emergency_stop
# --- END MODIFIED ---


class CommandExecutor:
    """
    Executes commands safely with obstacle detection.
    Uses MovementController for movement and UltrasonicSensor for safety checks.
    """

    # Configuration constants
    # --- MODIFIED ---
    MIN_SAFE_DISTANCE_MANUAL = 40  # cm for manual control
    MIN_SAFE_DISTANCE_AUTO = 25    # cm for autonomous control
    MICRO_STEP_DISTANCE = 2.5      # cm for micro-step movement (2-3 cm)
    # --- END MODIFIED ---
    TURN_SAFE_DISTANCE = 25  # cm for turning left/right
    DEBUG_SENSORS = False  # Set to True to print ultrasonic errors

    def __init__(self, movement_controller: MovementController, ultrasonic_sensor: UltrasonicSensor):
        """
        Initialize the command executor with required controllers.

        Args:
            movement_controller: Controller for motor movements
            ultrasonic_sensor: Sensor for obstacle detection
        """
        self.mc = movement_controller
        self.us = ultrasonic_sensor
        self.current_command = None
        self.last_execution_time = 0
        # --- MODIFIED ---
        self.safety_mode = "MANUAL"  # MANUAL or AUTONOMOUS
        self.min_safe_distance = self.MIN_SAFE_DISTANCE_MANUAL  # Default to manual
        # --- END MODIFIED ---
        self.last_action = "IDLE"  # IDLE, FORWARD, BACKWARD, LEFT, RIGHT, TURN_LEFT, TURN_RIGHT
        self.current_motion = None   # MOVE | TURN
        self.turn_mode = None        # ARC | INPLACE

    # --- MODIFIED ---
    def set_safety_mode(self, mode: str):
        """
        Set safety mode (MANUAL or AUTONOMOUS).
        
        Args:
            mode: "MANUAL" or "AUTONOMOUS"
        """
        mode = mode.upper()
        if mode not in ["MANUAL", "AUTONOMOUS"]:
            raise ValueError(f"Invalid safety mode: {mode}. Must be 'MANUAL' or 'AUTONOMOUS'")
        
        self.safety_mode = mode
        # Update safe distance based on mode
        if mode == "MANUAL":
            self.min_safe_distance = self.MIN_SAFE_DISTANCE_MANUAL
        else:  # AUTONOMOUS
            self.min_safe_distance = self.MIN_SAFE_DISTANCE_AUTO
        
        print(f"[SAFETY] Mode set to {mode}, safe distance: {self.min_safe_distance}cm")
    # --- END MODIFIED ---

    def execute(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a command safely.

        Args:
            cmd: Command dictionary with at minimum a "type" field

        Returns:
            Dict containing execution status and details
        """
        if not cmd or "type" not in cmd:
            return self._error_response("Invalid command format", "INVALID")

        cmd_type = cmd["type"].upper()
        self.current_command = cmd
        self.last_execution_time = time.time()

        try:
            if cmd_type == "STOP":
                return self._execute_stop(cmd)
            elif cmd_type == "MOVE":
                return self._execute_move(cmd)
            elif cmd_type == "TURN":
                return self._execute_turn(cmd)
            # --- MODIFIED ---
            elif cmd_type == "SET_SAFETY_MODE":
                return self._execute_set_safety_mode(cmd)
            # --- END MODIFIED ---
            else:
                return self._error_response(f"Unknown command type: {cmd_type}", "UNKNOWN_COMMAND")

        except Exception as e:
            return self._error_response(f"Execution error: {str(e)}", "EXECUTION_ERROR")

    def _validate_speed(self, speed: Any) -> int:
        """Validate speed parameter, return 50 if invalid."""
        try:
            speed_int = int(speed)
            if 0 <= speed_int <= 100:
                return speed_int
        except (ValueError, TypeError):
            pass
        return 50  # Default

    def _validate_duration(self, duration: Any) -> tuple[bool, float, str]:
        """Validate duration parameter, return (is_valid, duration_float, error_message)."""
        if duration is None:
            return True, 0.0, ""  # No duration is valid (continuous)
        
        try:
            duration_float = float(duration)
            if 0.05 <= duration_float <= 10.0:
                return True, duration_float, ""
            else:
                return False, 0.0, f"Duration {duration_float} must be between 0.05 and 10.0 seconds"
        except (ValueError, TypeError):
            return False, 0.0, f"Invalid duration value: {duration}"

    def _execute_stop(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Execute STOP command - immediately stop all movement."""
        # --- MODIFIED ---
        # Use emergency stop for instant, dominant stopping
        trigger_emergency_stop(self.mc)
        # --- END MODIFIED ---
        self.last_action = "IDLE"

        return {
            "ok": True,
            "type": "STOPPED",
            "command": "STOP",
            "timestamp": time.time(),
            "message": "Movement stopped",
        }

    # --- MODIFIED ---
    def _runtime_safety_check_manual(self, direction: str) -> bool:
        """
        Runtime safety check for MANUAL mode forward motion.
        Returns True if safe to continue, False if emergency stop was triggered.
        """
        if self.safety_mode != "MANUAL":
            return True
            
        # Only check forward motion components
        if direction not in ["FORWARD", "LEFT", "RIGHT"]:
            return True
            
        try:
            d = self.us.get_distance_fast("front")
            # Only trigger emergency stop if distance is valid and too close
            if d is not None and 0 < d <= self.MIN_SAFE_DISTANCE_MANUAL:
                trigger_emergency_stop(self.mc)
                self.last_action = "IDLE"
                return False
        except Exception as e:
            if self.DEBUG_SENSORS:
                print(f"Runtime safety check error: {e}")
            # Fail-open: continue if sensor fails
        
        return True
    # --- END MODIFIED ---

    def _execute_move(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute MOVE command with safety checks.

        Expected format:
            {"type": "MOVE", "direction": "FORWARD/BACKWARD/LEFT/RIGHT", "distance": 100}
            or
            {"type": "MOVE", "direction": "FORWARD/BACKWARD/LEFT/RIGHT", "duration": 2.0}
            or
            {"type": "MOVE", "direction": "FORWARD/BACKWARD/LEFT/RIGHT"} (continuous)

        Backward default rule:
            if direction == BACKWARD and no duration/distance -> duration=2.0
        """
        if "direction" not in cmd:
            return self._error_response("Missing direction in MOVE command", "INVALID_MOVE")

        direction = str(cmd["direction"]).upper()
        distance = cmd.get("distance")
        duration = cmd.get("duration")
        
        # Validate speed
        speed = self._validate_speed(cmd.get("speed", 50))
        
        # Validate duration if present
        if duration is not None:
            duration_valid, duration_float, duration_error = self._validate_duration(duration)
            if not duration_valid:
                return self._error_response(duration_error, "INVALID_DURATION")
            duration = duration_float

        # Backward default 2s
        if direction == "BACKWARD" and duration is None and distance is None:
            duration = 2.0

        # Allow MOVE in 4 directions now
        if direction not in ["FORWARD", "BACKWARD", "LEFT", "RIGHT"]:
            return self._error_response(f"Invalid direction: {direction}", "INVALID_DIRECTION")

        # --- ADDED: MANUAL MODE PRE-MOVE SAFETY GATING ---
        # Block forward motion in MANUAL mode if obstacle is too close
        if self.safety_mode == "MANUAL" and direction in ["FORWARD", "LEFT", "RIGHT"]:
            try:
                d = self.us.get_distance_fast("front")
                # Only block if distance is valid and less than safe threshold
                if d is not None and 0 < d <= self.MIN_SAFE_DISTANCE_MANUAL:
                    self.last_action = "IDLE"
                    return {
                        "ok": False,
                        "type": "BLOCKED",
                        "command": f"MOVE_{direction}",
                        "timestamp": time.time(),
                        "blocking_sensor": "front",
                        "distance_cm": d,
                        "safe_threshold": self.MIN_SAFE_DISTANCE_MANUAL,
                        "safety_mode": self.safety_mode,
                        "message": f"Obstacle detected at {d:.1f}cm (front) - manual mode blocked",
                    }
            except Exception as e:
                if self.DEBUG_SENSORS:
                    print(f"Pre-move safety check error: {e}")
                # Continue if sensor fails (fail-open)
        # --- END MODIFIED ---

        # Direction-based safety check (fast sensor reads)
        try:
            if direction == "FORWARD":
                d = self.us.get_distance_fast("front")
                # Only block if distance is valid and less than safe threshold
                if d is not None and 0 < d < self.min_safe_distance:
                    self.last_action = "IDLE"
                    return {
                        "ok": False,
                        "type": "BLOCKED",
                        "command": f"MOVE_{direction}",
                        "timestamp": time.time(),
                        "blocking_sensor": "front",
                        "distance_cm": d,
                        "safe_threshold": self.min_safe_distance,
                        "message": f"Obstacle detected at {d:.1f}cm (front)",
                    }

            # BACKWARD has no ultrasonic block (as you requested)
        except Exception as e:
            if self.DEBUG_SENSORS:
                print(f"Ultrasonic sensor error: {e}")
            # Continue even if sensor fails

        # Execute movement
        try:
            if direction == "FORWARD":
                self.last_action = "FORWARD"

                if distance is not None:

                    # MANUAL MODE → timed micro-slice (non-blocking style with fast safety checks)
                    if self.safety_mode == "MANUAL":

                        total_time = self.mc.estimate_forward_time(distance, speed)

                        # 20ms slice = 50Hz safety reaction
                        slice_time = 0.02

                        self.mc.forward(speed=speed)
                        start_time = time.time()

                        while time.time() - start_time < total_time:

                            # Runtime safety check
                            if not self._runtime_safety_check_manual(direction):
                                self.mc.stop()
                                return {
                                    "ok": False,
                                    "type": "SAFETY_STOP_RUNTIME",
                                    "command": f"MOVE_{direction}",
                                    "timestamp": time.time(),
                                    "safety_mode": self.safety_mode,
                                    "message": "Runtime safety stop during forward movement",
                                }

                            time.sleep(slice_time)

                        self.mc.stop()

                        message = f"Moved forward {distance}cm at speed {speed} (timed micro-slice mode)"
                    else:
                        # AUTONOMOUS MODE → normal distance movement
                        self.mc.forward(speed=speed)
                        move_time = self.mc.estimate_forward_time(distance, speed)
                        time.sleep(move_time)
                        self.mc.stop()

                        message = f"Moved forward {distance}cm at speed {speed}"


                elif duration is not None:

                    self.mc.forward(speed=speed)

                    if self.safety_mode == "MANUAL":
                        start_time = time.time()

                        while time.time() - start_time < duration:
                            if not self._runtime_safety_check_manual(direction):
                                self.mc.stop()
                                return {
                                    "ok": False,
                                    "type": "SAFETY_STOP_RUNTIME",
                                    "command": f"MOVE_{direction}",
                                    "timestamp": time.time(),
                                    "safety_mode": self.safety_mode,
                                    "message": "Runtime safety stop during forward movement",
                                }

                            time.sleep(0.02)

                        self.mc.stop()

                        

                    else:
                        time.sleep(duration)
                        self.mc.stop()

                    message = f"Moved forward for {duration} seconds at speed {speed}"

                else:
                    # Continuous forward
                    self.mc.forward(speed=speed)

                    message = f"Moving forward continuously at speed {speed}"

            elif direction == "BACKWARD":
                self.last_action = "BACKWARD"
                if distance is not None:
                    self.mc.backward(distance_cm=distance, speed=speed)
                    message = f"Moved backward {distance}cm at speed {speed}"
                elif duration is not None:
                    self.mc.backward(speed=speed)
                    self.last_execution_time = time.time()
                    message = f"Moving backward for {duration} seconds at speed {speed}"
                else:
                    self.mc.backward(speed=speed)
                    message = f"Moving backward continuously at speed {speed}"

            elif direction == "LEFT":
                self.current_motion = "MOVE"
                # Runtime safety for manual mode arc turns
                self.mc._arc_turn("LEFT", speed)
                if self.safety_mode == "MANUAL":
                    # Check for a short period to ensure initial safety
                    for _ in range(50):  # 0.5 seconds of initial safety checks
                        if not self._runtime_safety_check_manual(direction):
                            return {
                                "ok": False,
                                "type": "SAFETY_STOP_RUNTIME",
                                "command": f"MOVE_{direction}",
                                "timestamp": time.time(),
                                "safety_mode": self.safety_mode,
                                "message": f"Runtime safety stop during left arc movement",
                            }
                        time.sleep(0.01)
                message = f"Drifting left at speed {speed}"

            elif direction == "RIGHT":
                self.current_motion = "MOVE"
                # Runtime safety for manual mode arc turns
                self.mc._arc_turn("RIGHT", speed)
                if self.safety_mode == "MANUAL":
                    # Check for a short period to ensure initial safety
                    for _ in range(50):  # 0.5 seconds of initial safety checks
                        if not self._runtime_safety_check_manual(direction):
                            return {
                                "ok": False,
                                "type": "SAFETY_STOP_RUNTIME",
                                "command": f"MOVE_{direction}",
                                "timestamp": time.time(),
                                "safety_mode": self.safety_mode,
                                "message": f"Runtime safety stop during right arc movement",
                            }
                        time.sleep(0.01)
                message = f"Drifting right at speed {speed}"

            response = {
                "ok": True,
                "type": "EXECUTED",
                "command": f"MOVE_{direction}",
                "timestamp": time.time(),
                "message": message,
            }
            
            # Include duration in response if specified
            if duration is not None:
                response["duration"] = duration
            if speed != 50:  # Only include speed if not default
                response["speed"] = speed
            if distance is not None:
                response["distance"] = distance

            return response

        except Exception as e:
            self.mc.stop()
            self.last_action = "IDLE"
            return self._error_response(f"Movement error: {str(e)}", "MOVEMENT_ERROR")

    def _execute_turn(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute TURN command.

        Expected format:
            {"type": "TURN", "direction": "LEFT/RIGHT", "angle": 90}
            or
            {"type": "TURN", "direction": "LEFT/RIGHT", "duration": 1.0}
            or
            {"type": "TURN", "direction": "LEFT/RIGHT"} (continuous)
        """

        self.current_motion = "TURN"
        if "direction" not in cmd:
            return self._error_response("Missing direction in TURN command", "INVALID_TURN")

        direction = str(cmd["direction"]).upper()
        angle = cmd.get("angle")
        duration = cmd.get("duration")
        
        # Validate speed
        speed = self._validate_speed(cmd.get("speed", 50))
        
        # Validate duration if present
        if duration is not None:
            duration_valid, duration_float, duration_error = self._validate_duration(duration)
            if not duration_valid:
                return self._error_response(duration_error, "INVALID_DURATION")
            duration = duration_float

        if direction not in ["LEFT", "RIGHT"]:
            return self._error_response(f"Invalid direction: {direction}", "INVALID_DIRECTION")

        # --- TURN SAFETY (GATED) ---
        self.turn_mode = "ARC" if speed < 45 else "INPLACE"

        try:
            if self.turn_mode == "INPLACE":
                if direction == "LEFT":
                    d = self.us.get_distance_fast("left")
                    # Only block if distance is valid and less than safe threshold
                    if d is not None and 0 < d < self.TURN_SAFE_DISTANCE:
                        return self._error_response(
                            f"Obstacle on left at {d:.1f}cm", "BLOCKED"
                        )

                elif direction == "RIGHT":
                    d = self.us.get_distance_fast("right")
                    # Only block if distance is valid and less than safe threshold
                    if d is not None and 0 < d < self.TURN_SAFE_DISTANCE:
                        return self._error_response(
                            f"Obstacle on right at {d:.1f}cm", "BLOCKED"
                        )
            # ARC turns ignore side sensors
        except Exception:
            pass
        
        # --- EXECUTE TURN ---
        try:
            if direction == "LEFT":
                self.last_action = "TURN_LEFT"
                if self.turn_mode == "ARC":
                    self.mc._arc_turn("LEFT", speed)
                else:
                    self.mc.turn_left(speed=speed)
            else:
                self.last_action = "TURN_RIGHT"
                if self.turn_mode == "ARC":
                    self.mc._arc_turn("RIGHT", speed)
                else:
                    self.mc.turn_right(speed=speed)

            message = f"Turning {direction.lower()} at speed {speed}"

            return {
                "ok": True,
                "type": "EXECUTED",
                "command": f"TURN_{direction}",
                "timestamp": time.time(),
                "message": message,
                "speed": speed,
            }

        except Exception as e:
            self.mc.stop()
            self.last_action = "IDLE"
            return self._error_response(f"Turn error: {str(e)}", "TURN_ERROR")

    # --- MODIFIED --- (NEW METHOD)
    def _execute_set_safety_mode(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute SET_SAFETY_MODE command.
        
        Expected format:
            {"type": "SET_SAFETY_MODE", "mode": "MANUAL" | "AUTONOMOUS"}
        """
        if "mode" not in cmd:
            return self._error_response("Missing mode in SET_SAFETY_MODE command", "INVALID_MODE")
        
        mode = str(cmd["mode"]).upper()
        if mode not in ["MANUAL", "AUTONOMOUS"]:
            return self._error_response(f"Invalid safety mode: {mode}. Must be 'MANUAL' or 'AUTONOMOUS'", "INVALID_MODE")
        
        try:
            self.set_safety_mode(mode)
            return {
                "ok": True,
                "type": "SAFETY_MODE_SET",
                "command": "SET_SAFETY_MODE",
                "timestamp": time.time(),
                "message": f"Safety mode set to {mode} (safe distance: {self.min_safe_distance}cm)",
                "mode": mode,
                "safe_distance_cm": self.min_safe_distance
            }
        except Exception as e:
            return self._error_response(f"Failed to set safety mode: {str(e)}", "SAFETY_MODE_ERROR")
    # --- END MODIFIED ---

    def _error_response(self, reason: str, error_type: str) -> Dict[str, Any]:
        """Create a standardized error response."""
        return {
            "ok": False,
            "type": error_type,
            "command": self.current_command.get("type") if self.current_command else "UNKNOWN",
            "timestamp": time.time(),
            "message": f"Command failed: {reason}",
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the executor."""
        # --- MODIFIED ---
        status = {
            "timestamp": time.time(),
            "current_command": self.current_command,
            "last_execution_time": self.last_execution_time,
            "safety_mode": self.safety_mode,
            "min_safe_distance": self.min_safe_distance,
            "turn_safe_distance": self.TURN_SAFE_DISTANCE,
            "last_action": self.last_action,
        }
        # --- END MODIFIED ---

        try:
            status["front_distance"] = self.us.get_distance_fast("front")
            status["left_distance"] = self.us.get_distance_fast("left")
            status["right_distance"] = self.us.get_distance_fast("right")
            # --- MODIFIED ---
            # Only check safety if distance is valid
            if status["front_distance"] is not None:
                status["is_safe_front"] = status["front_distance"] >= self.min_safe_distance
            else:
                status["is_safe_front"] = True  # Assume safe if sensor fails
                
            if status["left_distance"] is not None:
                status["is_safe_left"] = status["left_distance"] >= self.TURN_SAFE_DISTANCE
            else:
                status["is_safe_left"] = True
                
            if status["right_distance"] is not None:
                status["is_safe_right"] = status["right_distance"] >= self.TURN_SAFE_DISTANCE
            else:
                status["is_safe_right"] = True
            # --- END MODIFIED ---
        except Exception as e:
            if self.DEBUG_SENSORS:
                status["sensor_error"] = str(e)

        return status

    def emergency_stop(self) -> Dict[str, Any]:
        """Perform emergency stop and return status."""
        # --- MODIFIED ---
        # Use the centralized emergency stop function
        result = trigger_emergency_stop(self.mc)
        self.last_action = "IDLE"
        return result
        # --- END MODIFIED ---


if __name__ == "__main__":
    print("Testing CommandExecutor...")

    from motors.movement_controller import MovementController
    from sensors.ultrasonic import UltrasonicSensor

    try:
        movement_ctrl = MovementController()
        ultrasonic = UltrasonicSensor()

        executor = CommandExecutor(movement_ctrl, ultrasonic)

        test_commands = [
            {"type": "STOP"},
            {"type": "MOVE", "direction": "FORWARD", "distance": 50, "speed": 30},
            {"type": "MOVE", "direction": "BACKWARD", "duration": 2.0, "speed": 40},
            {"type": "MOVE", "direction": "LEFT", "duration": 1.0, "speed": 40},
            {"type": "MOVE", "direction": "RIGHT", "duration": 1.0, "speed": 40},
            {"type": "TURN", "direction": "LEFT", "angle": 90, "speed": 50},
            {"type": "TURN", "direction": "RIGHT", "duration": 1.5, "speed": 60},
            # --- MODIFIED ---
            {"type": "SET_SAFETY_MODE", "mode": "AUTONOMOUS"},
            {"type": "SET_SAFETY_MODE", "mode": "MANUAL"},
            {"type": "SET_SAFETY_MODE", "mode": "INVALID"},
            # --- END MODIFIED ---
            {"type": "UNKNOWN", "data": "should fail"},
            {},
        ]

        for cmd in test_commands:
            print(f"\nExecuting command: {cmd}")
            result = executor.execute(cmd)
            print(f"Result: {result}")
            time.sleep(0.5)

        print("\nGetting executor status:")
        print(executor.get_status())

        print("\nTesting emergency stop:")
        print(executor.emergency_stop())

    except Exception as e:
        print(f"Setup error (might be expected if not on Pi): {e}")
