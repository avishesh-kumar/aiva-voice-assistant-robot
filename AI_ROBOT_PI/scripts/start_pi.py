#!/usr/bin/env python3
"""
Main Robot Controller
Integrates CommandServer and CommandExecutor for remote control.
Handles commands from Mac and executes them safely with obstacle detection.
"""

import time
import traceback
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import threading
from sensors.imu_adxl345 import ADXL345IMU

from networking.command_server import CommandServer
from control.command_executor import CommandExecutor
from motors.movement_controller import MovementController
from sensors.ultrasonic import UltrasonicSensor


# Configuration flags
ENABLE_BACKOFF = False  # Set to True to enable automatic backoff after safety stop
DEBUG_COMMANDS = False  # Set to True to print every received command

class RobotController:
    """Main robot controller that ties everything together."""

    def __init__(self):
        """Initialize the robot controller with all components."""
        print("=" * 50)
        print("ROBOT CONTROLLER INITIALIZING")
        print("=" * 50)

        try:
            # Initialize hardware components
            print("[INIT] Setting up MovementController...")
            self.movement = MovementController()

            print("[INIT] Setting up UltrasonicSensor...")
            self.ultrasonic = UltrasonicSensor()

            # Initialize command executor (the "brain")
            print("[INIT] Setting up CommandExecutor...")
            self.executor = CommandExecutor(self.movement, self.ultrasonic)

            # Initialize command server (network interface)
            print("[INIT] Setting up CommandServer...")
            self.server = CommandServer(host="0.0.0.0", port=8890)

            # State tracking
            self.running = False
            self.emergency_stop_flag = False
            self.is_moving = False
            self.last_command_time = time.time()
            self.last_received_command_time = time.time()  # Track last command from Mac
            self.last_command_type = None

            print("[INIT] Setting up ADXL345 IMU...")
            self.imu = ADXL345IMU()
            self.imu_thread = None


            # SAFETY LOOP TIMING
            self.last_obstacle_check_time = 0.0
            self.obstacle_check_interval = 0.01

            self.is_moving_forward = False
            self.current_motion = "IDLE"  # FORWARD, LEFT, RIGHT, BACKWARD, IDLE

            # Safety stop message cooldown (avoid spamming Mac)
            self.last_safety_stop_time = 0.0
            self.safety_stop_cooldown = 0.5
            self.safety_pause_until = 0.0

            # Debug control (printing in safety loop causes delays)
            self.debug_safety = False

            print("[INIT] All components initialized successfully!")

        except Exception as e:
            print(f"[ERROR] Failed to initialize: {e}")
            traceback.print_exc()
            self.cleanup()
            raise

    def start(self):
        """Start the robot controller main loop."""
        try:
            print("[START] Starting command server...")
            self.server.start()
            self.running = True

            self._start_imu_stream()

            print("[START] Robot controller ready!")
            print("[START] Listening on 0.0.0.0:8890")
            print("[START] Waiting for commands from Mac...")

            self._main_loop()

        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Interrupted by user")
        except Exception as e:
            print(f"[ERROR] Fatal error in main loop: {e}")
            traceback.print_exc()
        finally:
            self.stop()

    def stop(self):
        """Stop the robot controller and clean up resources."""
        print("[SHUTDOWN] Stopping robot controller...")
        self.running = False

        # Emergency stop any movement
        print("[SHUTDOWN] Executing emergency stop...")
        self.executor.emergency_stop()
        self.is_moving = False
        self.current_motion = "IDLE"

        print("[SHUTDOWN] Stopping IMU stream...")

        # Close network connections
        print("[SHUTDOWN] Closing command server...")
        self.server.close()

        # Clean up hardware
        print("[SHUTDOWN] Cleaning up hardware...")
        self.movement.cleanup()

        print("[SHUTDOWN] Robot controller stopped.")

    def cleanup(self):
        """Cleanup resources (alias for stop)."""
        self.stop()

    def _main_loop(self):
        """Main processing loop - handles commands and status updates."""
        last_status_time = 0.0
        status_interval = 2.0  # Send status every 2 seconds

        while self.running:
            try:
                # Emergency stop flag
                if self.emergency_stop_flag:
                    print("[EMERGENCY] Emergency stop activated!")
                    self.executor.emergency_stop()
                    self.emergency_stop_flag = False
                    self.is_moving = False
                    self.current_motion = "IDLE"

                # Watchdog timeout stop
                self._run_watchdog()

                # Dead-man stop: if moving and no commands for 1.5 seconds
                self._run_deadman_stop()

                # Live safety stop check (fast)
                self._run_obstacle_check()

                # Accept new client if none connected
                if not self.server.is_client_connected():
                    if self.server.accept():
                        print(f"[CONNECT] Client connected from {self.server.client_address}")
                        # Reset dead-man timer on new connection
                        self.last_received_command_time = time.time()
                        welcome_status = {
                            "type": "system",
                            "status": "ready",
                            "message": "Robot controller connected and ready",
                            "timestamp": time.time(),
                        }
                        self.server.send_status(welcome_status)

                    time.sleep(0.2)
                    continue

                # Receive and process commands
                commands = self.server.receive_commands()

                for cmd in commands:
                    # Update last received command time
                    self.last_received_command_time = time.time()

                    # 🔧 RESET safety pause on new command
                    self.safety_pause_until = 0.0
                    
                    if DEBUG_COMMANDS:
                        print(f"[CMD] Received: {cmd}")

                    cmd_type = str(cmd.get("type", "")).upper()

                    # Emergency stop command
                    if cmd_type == "EMERGENCY_STOP":
                        self.emergency_stop_flag = True
                        response = self.executor.emergency_stop()
                        self.is_moving = False
                        self.current_motion = "IDLE"
                        self.server.send_status(response)
                        continue

                    # STOP command aliases (highest priority)
                    if cmd_type in ["STOP", "AUTO_STOP", "EXPLORE_STOP"]:
                        if DEBUG_COMMANDS:
                            print(f"[CMD] STOP command - executing immediately")
                        response = self.executor.execute(cmd)
                        self.is_moving = False
                        self.current_motion = "IDLE"
                        self.server.send_status(response)
                        continue

                    # Execute normal command
                    response = self.executor.execute(cmd)

                    # Update movement state based on command
                    self._update_movement_state(cmd, response)

                    # Send status back to Mac
                    self.server.send_status(response)

                # Periodic status updates
                current_time = time.time()
                if current_time - last_status_time > status_interval:
                    system_status = self._get_system_status()
                    self.server.send_status(system_status)
                    last_status_time = current_time

                # Smaller sleep to reduce reaction latency
                time.sleep(0.002)

            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Interrupted in main loop")
                break
            except Exception as e:
                # CRASH SAFETY: Stop motors immediately on any unexpected exception
                print(f"[ERROR] Unexpected error in main loop: {e}")
                try:
                    self.executor.emergency_stop()
                    self.is_moving = False
                    self.current_motion = "IDLE"
                except:
                    pass
                
                traceback.print_exc()
                # Continue running after brief pause
                time.sleep(0.5)

    def _run_deadman_stop(self):
        """Stop robot if moving and no commands received for 1.5 seconds."""

        # Do NOT dead-man stop autonomous forward motion
        if self.is_moving_forward:
            return
        
        if not self.is_moving:
            return
        
        current_time = time.time()
        time_since_last_command = current_time - self.last_received_command_time
        
        if time_since_last_command > 1.5:
            print(f"[DEADMAN] No commands for {time_since_last_command:.1f}s - emergency stop")
            
            # Execute emergency stop
            self.executor.emergency_stop()
            self.is_moving = False
            self.current_motion = "IDLE"
            
            # Send status to Mac
            deadman_status = {
                "ok": False,
                "type": "DEADMAN_STOP",
                "reason": "no_recent_commands",
                "timestamp": current_time,
                "time_since_last_command": time_since_last_command,
                "message": f"Dead-man stop: no commands for {time_since_last_command:.1f}s",
            }
            
            if self.server.is_client_connected():
                self.server.send_status(deadman_status)

    def _update_movement_state(self, cmd: dict, response: dict):
        cmd_type = str(cmd.get("type", "")).upper()

        if not response.get("ok", False):
            self.is_moving = False
            self.last_command_type = None
            self.is_moving_forward = False
            self.current_motion = "IDLE"
            return

        if cmd_type == "MOVE":
            direction = str(cmd.get("direction", "")).upper()
            self.is_moving = True
            self.last_command_type = "MOVE"
            self.is_moving_forward = (direction == "FORWARD")

            if direction == "FORWARD":
                self.current_motion = "FORWARD"
            elif direction in ["LEFT", "RIGHT"]:
                # ARC drift → treat as forward motion
                self.current_motion = "FORWARD"
            elif direction == "BACKWARD":
                self.current_motion = "BACKWARD"
            else:
                self.current_motion = "IDLE"
                
            dur = cmd.get("duration")
            if dur is not None:
                self.last_command_time = time.time() + float(dur)
            else:
                self.last_command_time = time.time()

        elif cmd_type == "TURN":
            direction = str(cmd.get("direction", "")).upper()
            self.is_moving = True
            self.last_command_type = "TURN"
            self.is_moving_forward = False

            if direction in ["LEFT", "RIGHT"]:
                self.current_motion = direction
            else:
                self.current_motion = "IDLE"

            dur = cmd.get("duration")
            if dur is not None:
                self.last_command_time = time.time() + float(dur)
            else:
                self.last_command_time = time.time()

        elif cmd_type in ["STOP", "AUTO_STOP", "EXPLORE_STOP"]:
            self.is_moving = False
            self.last_command_type = None
            self.is_moving_forward = False
            self.current_motion = "IDLE"

    def _run_watchdog(self):
        if not self.is_moving:
            return
        if self.last_command_type not in ["MOVE", "TURN"]:
            return
        if time.time() <= self.last_command_time:
            return

        print("[WATCHDOG] Duration completed - stopping robot")
        self.movement.stop()

        self.is_moving = False
        self.is_moving_forward = False
        self.last_command_type = None
        self.last_command_time = 0.0
        self.current_motion = "IDLE"

        watchdog_status = {
            "ok": False,
            "type": "WATCHDOG_STOP",
            "reason": "duration_completed",
            "timestamp": time.time(),
            "message": "Watchdog stopped robot after duration completed",
        }
        if self.server.is_client_connected():
            self.server.send_status(watchdog_status)

    def _run_obstacle_check(self):
        """Ultra-fast safety stop loop (checks only relevant sensor for motion)."""

        now = time.monotonic()

        if (now - self.last_obstacle_check_time) < self.obstacle_check_interval:
            return
        self.last_obstacle_check_time = now
        
        if now < self.safety_pause_until:
            return
            
        # Only check when moving - FIXED: prevent idle safety spam
        if not self.is_moving:
            return

        # If duration command finished, don't check
        if self.last_command_time != 0 and time.time() > self.last_command_time:
            return

        # Decide which sensor to use based on motion
        try:
            blocking_sensor = self.ultrasonic.get_blocking_sensor_for_motion(self.current_motion)
        except Exception:
            return

        # If no sensor needed (BACKWARD/IDLE), skip
        if blocking_sensor is None:
            return

        distance = self.ultrasonic.get_distance_reflex(blocking_sensor)

        # FIXED: Only trigger emergency stop for valid, close distances
        # Do not treat None or invalid readings as obstacles
        if distance is None:
            return  # Ignore sensor failure, continue movement
            
        if distance <= 0:  # Invalid negative reading
            return

        if self.debug_safety:
            print(f"[SAFETY] Motion={self.current_motion} Sensor={blocking_sensor} Distance={distance:.1f}cm")

        # STOP immediately only if unsafe AND distance is valid
        # FIXED: Only check against min_safe_distance, not arbitrary values
        if distance <= self.executor.min_safe_distance:
            motion_at_stop = self.current_motion

            # IMMEDIATE STOP (no smooth stop delay)
            self.executor.emergency_stop()

            # Reset movement state
            self.is_moving = False
            self.is_moving_forward = False
            self.last_command_type = None
            self.current_motion = "IDLE"

            # FIXED: Mode-aware safety pause
            # 0.2s for MANUAL, 0.6s for AUTONOMOUS
            if self.executor.safety_mode == "MANUAL":
                pause_duration = 0.2
            else:  # AUTONOMOUS
                pause_duration = 0.6
            self.safety_pause_until = time.monotonic() + pause_duration

            # Optional auto-backoff only for FORWARD (after stopping) if enabled
            if ENABLE_BACKOFF and motion_at_stop == "FORWARD":
                try:
                    backoff_speed = 35
                    backoff_time = 0.2  # Shorter backoff
                    self.movement.backward(speed=backoff_speed)
                    time.sleep(backoff_time)
                    self.movement.stop()
                except Exception:
                    pass

            # Notify Mac (with cooldown)
            now2 = time.time()
            if (now2 - self.last_safety_stop_time) < self.safety_stop_cooldown:
                return
            self.last_safety_stop_time = now2

            safety_status = {
                "ok": False,
                "type": "SAFETY_STOP",
                "reason": "obstacle_detected",
                "blocking_sensor": blocking_sensor,
                "distance_cm": distance,
                "safety_mode": self.executor.safety_mode,
                "timestamp": now2,
                "message": f"Safety stop: obstacle at {distance:.1f}cm on {blocking_sensor} (mode: {self.executor.safety_mode})",
            }

            if self.server.is_client_connected():
                self.server.send_status(safety_status)

    def _start_imu_stream(self):
        def imu_loop():
            while self.running:
                try:
                    imu_data = self.imu.read()

                    packet = {
                        "type": "imu",
                        "x": imu_data["x"],
                        "y": imu_data["y"],
                        "z": imu_data["z"],
                        "timestamp": time.time(),
                    }

                    if self.server.is_client_connected():
                        self.server.send_status(packet)

                    time.sleep(0.1)  # 10 Hz

                except Exception as e:
                    print(f"[IMU] Error: {e}")
                    time.sleep(0.5)

        self.imu_thread = threading.Thread(
            target=imu_loop,
            daemon=True,
            name="IMUThread"
        )
        self.imu_thread.start()

        print("[IMU] ADXL345 streaming started (10 Hz)")


    def _get_system_status(self):
        """Get comprehensive system status."""
        status = {
            "type": "system_status",
            "timestamp": time.time(),
            "connected": self.server.is_client_connected(),
            "controller": "ready" if self.running else "stopped",
            "emergency_stop": self.emergency_stop_flag,
            "is_moving": self.is_moving,
            "current_motion": self.current_motion,
            "last_command_time": self.last_command_time,
            "last_command_type": self.last_command_type,
            "time_since_last_command": time.time() - self.last_received_command_time,
        }

        # Add sensor readings if available
        try:
            distances = self.ultrasonic.get_all_distances()
            status.update(
                {
                    "front_distance_cm": distances["front"],
                    "left_distance_cm": distances["left"],
                    "right_distance_cm": distances["right"],
                }
            )

            obstacle_status = self.ultrasonic.is_obstacle_any_direction(self.executor.min_safe_distance)
            status.update(
                {
                    "obstacle_front": obstacle_status["front"],
                    "obstacle_left": obstacle_status["left"],
                    "obstacle_right": obstacle_status["right"],
                }
            )

            if self.current_motion == "FORWARD":
                status["safe_to_move"] = distances["front"] >= self.executor.min_safe_distance
            else:
                status["safe_to_move"] = True

        except Exception as e:
            status["sensor_error"] = str(e)

        exec_status = self.executor.get_status()
        status.update(exec_status)

        return status

    def __del__(self):
        """Ensure cleanup on destruction."""
        if self.running:
            self.stop()


def print_banner():
    """Print startup banner."""
    print("╔══════════════════════════════════════════════════════╗")
    print("║                ROBOT CONTROLLER v1.0                 ║")
    print("║                 Raspberry Pi Edition                  ║")
    print("║                                                      ║")
    print("║  Commands: STOP, MOVE, TURN                          ║")
    print("║  Safety: Blocks forward if obstacle < 40cm           ║")
    print("║  Network: TCP Server on 0.0.0.0:8890                 ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()


def main():
    """Main entry point for the robot controller."""
    print_banner()

    if sys.version_info < (3, 7):
        print("[ERROR] Python 3.7 or higher is required")
        sys.exit(1)

    controller = None
    try:
        controller = RobotController()
        controller.start()

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Interrupted during startup")
    except Exception as e:
        print(f"[ERROR] Failed to start robot controller: {e}")
        traceback.print_exc()
    finally:
        if controller:
            controller.cleanup()

    print("[EXIT] Robot controller exited.")


if __name__ == "__main__":
    main()
