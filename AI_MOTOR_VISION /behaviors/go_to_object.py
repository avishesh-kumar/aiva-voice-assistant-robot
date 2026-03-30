# behaviors/go_to_object.py

import time
from utils.logger import setup_logger
from memory.spatial_memory import SpatialMemory
from memory.grid_memory import GridMemory

logger = setup_logger("GO_TO_OBJECT", log_file="system.log")


# ---------- PID CONTROLLER FOR SMOOTH TURNING ----------
class TurningPIDController:
    """PID controller for smooth turning based on object offset."""
    
    def __init__(self, kp=1.2, ki=0.0, kd=0.6, output_min=-1.0, output_max=1.0):
        self.kp = kp  # Proportional gain
        self.ki = ki  # Integral gain (set to 0 for PD control)
        self.kd = kd  # Derivative gain
        
        self.output_min = output_min
        self.output_max = output_max
        
        self.reset()
    
    def reset(self):
        """Reset PID state (call when object lost or STOP triggered)."""
        self.prev_error = 0.0
        self.integral = 0.0
        self.prev_time = None
    
    def compute(self, error, dt):
        """
        Compute PID output.
        Args:
            error: Current error (object_offset_x, range -1.0 to 1.0)
            dt: Time delta since last computation
        Returns:
            Clamped PID output
        """
        # Proportional term
        p = self.kp * error
        
        # Integral term (disabled for now)
        self.integral += error * dt
        i = self.ki * self.integral
        self.integral = max(-0.5, min(self.integral, 0.5))
        
        # Derivative term
        d = 0.0
        if dt > 0:
            d = self.kd * (error - self.prev_error) / dt
        
        # Combine terms
        output = p + i + d
        
        # Clamp output
        output = max(self.output_min, min(output, self.output_max))
        
        # Update state
        self.prev_error = error
        return output


def go_to_object_loop(
    stop_event,
    scene_state,
    command_client,
    obstacle_flag,
    target_label: str,
    loop_hz: float = 5.0,
):
    """
    Autonomous behavior: navigate to a specified object using vision and PID-based turning.
    
    Args:
        stop_event: threading.Event to request stop
        scene_state: SceneState instance (shared world model)
        command_client: CommandClient to send motor commands
        obstacle_flag: function returning bool for obstacle detection
        target_label: YOLO class name (e.g., "chair", "bottle")
        loop_hz: control loop frequency
    """
    
    if not command_client or not command_client.is_connected():
        logger.warning("Command client not connected. GO_TO_OBJECT aborted.")
        return
    
    period = 1.0 / loop_hz
    
    # ---------- TUNING PARAMETERS ----------
    # Timing
    COMMAND_COOLDOWN = 0.3  # Minimum time between motor commands
    SEARCH_TIMEOUT = 8.0    # Maximum search duration in seconds
    FORWARD_DURATION = 0.25 # Short forward pulses
    
    # PID tuning
    TURN_KP = 2.5
    TURN_KD = 0.9
    TURN_KI = 0.0
    TURN_THRESHOLD = 0.05  # PID output deadzone for forward movement
    
    # Speed limits
    MIN_TURN_SPEED = 50    # Minimum speed for in-place turning
    MAX_TURN_SPEED = 70    # Maximum turning speed
    BASE_FORWARD_SPEED = 60
    MAX_FORWARD_SPEED = 75
    
    # Distance control
    STOP_OBJECT_AREA = 0.40  # Area ratio threshold for stopping
    SLOW_DOWN_AREA = 0.25    # Start slowing down at this distance
    
    # Search mode
    SEARCH_TURN_SPEED = 55
    SEARCH_TURN_DURATION = 1.5  # How long to turn in each direction
    # ---------------------------------------
    
    logger.info(f"GO_TO_OBJECT started for target: '{target_label}'")
    
    # Initialize components
    last_command_time = time.time()
    last_command = None
    
    # Initialize PID controller
    pid_controller = TurningPIDController(
        kp=TURN_KP,
        ki=TURN_KI,
        kd=TURN_KD,
        output_min=-1.0,
        output_max=1.0
    )
    last_pid_time = time.time()
    
    # Search mode variables
    search_start_time = None
    search_direction = "LEFT"
    search_last_switch = time.time()
    
    # Object tracking
    object_last_seen_time = time.time()
    consecutive_lost_frames = 0
    MAX_LOST_FRAMES = 15  # ~3 seconds at 5Hz
    
    # Spatial memory (optional, for future path planning)
    memory = SpatialMemory()
    grid = GridMemory()
    
    # Main behavior loop
    while True:
        # ---------- STOP HANDLING (CRITICAL) ----------
        if stop_event.is_set():
            logger.info("GO_TO_OBJECT: Stop requested")
            _send_stop(command_client, last_command)
            break
        
        start_time = time.time()
        
        # ---------- OBSTACLE HANDLING ----------
        if obstacle_flag():
            logger.warning("GO_TO_OBJECT: Obstacle detected, stopping")
            _send_stop(command_client, last_command)
            last_command = "STOP"
            pid_controller.reset()
            
            # Wait briefly for obstacle to clear
            _interruptible_sleep(stop_event, 0.5)
            continue
        
        # ---------- SCENE STATE VALIDITY ----------
        if scene_state.is_stale():
            logger.debug("Scene state stale, waiting")
            _send_stop(command_client, last_command)
            last_command = "STOP"
            _interruptible_sleep(stop_event, period)
            continue
        
        # ---------- FIND TARGET OBJECT ----------
        target_object = None
        max_area = 0.0
        
        # Look for the target object in detections
        if hasattr(scene_state, 'objects') and scene_state.objects:
            for obj in scene_state.objects:
                if obj.get('label', '').lower() == target_label.lower():
                    area = obj.get('area_ratio', 0.0)
                    if area > max_area:
                        max_area = area
                        target_object = obj
        
        # ---------- OBJECT VISIBILITY HANDLING ----------
        current_time = time.time()
        
        if target_object:
            # Object is visible
            object_last_seen_time = current_time
            consecutive_lost_frames = 0
            search_start_time = None  # Reset search timer
            
            # Extract object data
            offset = target_object.get('offset_x', 0.0)
            area = target_object.get('area_ratio', 0.0)
            
            # Clamp values
            offset = max(-1.0, min(1.0, offset))
            area = max(0.0, min(1.0, area))
            
            logger.debug(f"Target '{target_label}' found: offset={offset:.3f}, area={area:.3f}")
            
        else:
            # Object not visible
            consecutive_lost_frames += 1
            time_since_seen = current_time - object_last_seen_time
            
            # Check if we should enter search mode
            if consecutive_lost_frames < MAX_LOST_FRAMES and time_since_seen < 2.0:
                # Brief flicker - wait
                _send_stop(command_client, last_command)
                last_command = "STOP"
                _interruptible_sleep(stop_event, period)
                continue
            
            # ---------- ENTER SEARCH MODE ----------
            if search_start_time is None:
                logger.info(f"Target '{target_label}' lost. Entering SEARCH mode")
                search_start_time = current_time
                search_direction = "LEFT"
                search_last_switch = current_time
                pid_controller.reset()
            
            # Check search timeout
            if current_time - search_start_time > SEARCH_TIMEOUT:
                logger.warning(f"GO_TO_OBJECT: Search timeout ({SEARCH_TIMEOUT}s). Target not found.")
                _send_stop(command_client, last_command)
                break
            
            # ---------- SEARCH BEHAVIOR ----------
            # Switch direction periodically
            if current_time - search_last_switch > SEARCH_TURN_DURATION:
                search_direction = "RIGHT" if search_direction == "LEFT" else "LEFT"
                search_last_switch = current_time
                logger.debug(f"Search: switching to {search_direction}")
            
            # Send search turn command
            if current_time - last_command_time >= COMMAND_COOLDOWN:
                cmd = {
                    "type": "TURN",
                    "direction": search_direction,
                    "speed": SEARCH_TURN_SPEED,
                    "duration": period * 2,
                }
                try:
                    command_client.send_command(cmd)
                    last_command = "SEARCH_TURN"
                    last_command_time = current_time
                    
                    # Update grid memory
                    if cmd["direction"] == "LEFT":
                        grid.turn_left()
                    elif cmd["direction"] == "RIGHT":
                        grid.turn_right()
                        
                except Exception:
                    logger.exception("Failed to send SEARCH command")
                
            _interruptible_sleep(stop_event, period)
            continue
        
        # ---------- STOPPING AT TARGET ----------
        area = target_object.get('area_ratio', 0.0)
        depth = target_object.get("depth", 1.0)

        # Stop when object fills enough of frame OR is extremely close
        if area >= STOP_OBJECT_AREA or depth < 0.15:
            logger.info(f"GO_TO_OBJECT: Target reached (area={area:.3f}, depth={depth:.3f})")
            _send_stop(command_client, last_command)
            last_command = "STOP"
            break
        
        # ---------- COMMAND THROTTLING ----------
        if current_time - last_command_time < COMMAND_COOLDOWN:
            _interruptible_sleep(stop_event, period)
            continue
        
        # ---------- PID-BASED TURNING ----------
        # Compute PID output for smooth turning
        if last_pid_time is None:
            dt = period
        else:
            dt = current_time - last_pid_time
            dt = max(dt, 0.05)
        
        # Error is the object offset (negative = left, positive = right)
        error = offset
        
        # Compute PID output
        pid_output = pid_controller.compute(error, dt)
        last_pid_time = current_time
        
        action = None
        cmd = None
        
        # ---------- TURN WHEN OBJECT IS OFF-CENTER ----------
        if abs(pid_output) > TURN_THRESHOLD:
            # Map PID output to turn speed
            turn_speed = MIN_TURN_SPEED + abs(pid_output) * (MAX_TURN_SPEED - MIN_TURN_SPEED)
            turn_speed = int(max(MIN_TURN_SPEED, min(turn_speed, MAX_TURN_SPEED)))
            
            # Determine direction
            direction = "RIGHT" if pid_output > 0 else "LEFT"
            
            cmd = {
                "type": "TURN",
                "direction": direction,
                "speed": turn_speed,
                "duration": period * 2,
            }
            action = f"TURN_{direction}"
            logger.info(f"GO_TO_OBJECT: offset={offset:.3f}, pid={pid_output:.3f} → {direction} at {turn_speed}")
        
        # ---------- MOVE FORWARD WHEN OBJECT IS CENTERED ----------
        elif abs(pid_output) <= TURN_THRESHOLD:
            # Calculate forward speed (slower when close)
            forward_speed = BASE_FORWARD_SPEED
            
            area = target_object.get('area_ratio', 0.0)

            if area >= SLOW_DOWN_AREA:
                forward_speed = int(BASE_FORWARD_SPEED * 0.6)
            else:
                depth = target_object.get("depth", 1.0)
                if depth < 0.45:
                    forward_speed = int(BASE_FORWARD_SPEED * 0.6)

                        
            forward_speed = max(45, min(forward_speed, MAX_FORWARD_SPEED))
            
            cmd = {
                "type": "MOVE",
                "direction": "FORWARD",
                "speed": forward_speed,
                "duration": FORWARD_DURATION,
            }
            action = "MOVE_FORWARD"
            logger.info(f"GO_TO_OBJECT: centered (pid={pid_output:.3f}), area={area:.3f} → FORWARD at {forward_speed}")
        
        # ---------- SEND COMMAND ----------
        if cmd:
            try:
                command_client.send_command(cmd)
                last_command = cmd["type"]
                last_command_time = current_time
                
                # Update memory and grid
                if cmd["type"] == "MOVE":
                    memory.mark_direction(cmd["direction"])
                    if cmd["direction"] == "FORWARD":
                        grid.move_forward()
                elif cmd["type"] == "TURN":
                    if cmd["direction"] == "LEFT":
                        grid.turn_left()
                    elif cmd["direction"] == "RIGHT":
                        grid.turn_right()
                        
            except Exception:
                logger.exception("Failed to send GO_TO_OBJECT command")
                _send_stop(command_client, last_command)
                last_command = "STOP"
        else:
            # No action needed, maintain stop
            if last_command != "STOP":
                _send_stop(command_client, last_command)
                last_command = "STOP"
                last_command_time = current_time
        
        # ---------- MAINTAIN LOOP RATE ----------
        elapsed = time.time() - start_time
        sleep_time = period - elapsed
        if sleep_time > 0:
            _interruptible_sleep(stop_event, sleep_time)
    
    # ---------- CLEANUP ON EXIT ----------
    logger.info(f"GO_TO_OBJECT behavior for '{target_label}' exiting")
    try:
        command_client.send_command({"type": "STOP"})
    except Exception:
        pass


def _interruptible_sleep(stop_event, duration, step=0.05):
    """Sleep in small steps so stop_event can interrupt."""
    end_time = time.time() + duration
    while time.time() < end_time:
        if stop_event.is_set():
            break
        time.sleep(step)


def _send_stop(command_client, last_command):
    """Send STOP command and update last_command."""
    try:
        command_client.send_command({"type": "STOP"})
    except Exception:
        pass
