# behaviors/follow_person.py

import time
from utils.logger import setup_logger
from memory.spatial_memory import SpatialMemory
from memory.grid_memory import GridMemory

logger = setup_logger("FOLLOW", log_file="system.log")


class TargetState:
    """Maintains temporal memory of the locked target person."""
    
    def __init__(self):
        self.offset_x = 0.0
        self.area_ratio = 0.0
        self.last_seen_time = 0.0
        self.visible = False
        self.last_known_direction = None  # "LEFT" or "RIGHT"
        self.alpha = 0.7  # Exponential smoothing factor
        self.locked = False
        self.loss_start_time = 0.0
        self.locked_offset_sign = 0  # 1 for right, -1 for left, 0 for not locked
        
    def update(self, current_offset, current_area, visible_now):
        """Update state with new observation using exponential smoothing."""
        current_time = time.time()
        
        if visible_now:
            # Enforce target lock: ignore opposite-sign jumps
            if self.locked and self.locked_offset_sign != 0:
                if current_offset * self.locked_offset_sign < -0.4:
                    # Sudden target flip - likely different person, ignore
                    return
            
            if not self.locked:
                # First detection - initialize directly
                self.offset_x = current_offset
                self.area_ratio = current_area
                self.locked = True
                # Record initial offset sign for target lock
                self.locked_offset_sign = 1 if current_offset > 0 else -1
            else:
                # Smooth update
                self.offset_x = (self.alpha * current_offset + 
                               (1 - self.alpha) * self.offset_x)
                self.area_ratio = (self.alpha * current_area + 
                                 (1 - self.alpha) * self.area_ratio)
            
            self.visible = True
            self.last_seen_time = current_time
            self.loss_start_time = 0.0  # Reset loss timer
            
            # Track direction for search
            if current_offset < -0.1:
                self.last_known_direction = "LEFT"
            elif current_offset > 0.1:
                self.last_known_direction = "RIGHT"
                
        else:
            # Debounce visibility: wait 0.25s before marking invisible
            if current_time - self.last_seen_time > 0.25:
                self.visible = False
                if self.locked and self.loss_start_time == 0:
                    self.loss_start_time = current_time
    
    def reset_loss_timer(self):
        """Reset loss timer when person reappears."""
        self.loss_start_time = 0.0
    
    def get_loss_duration(self):
        """Get how long person has been missing (0 if visible)."""
        if self.visible or self.loss_start_time == 0:
            return 0.0
        return time.time() - self.loss_start_time
    
    def is_recently_lost(self):
        """Check if person lost for less than brief wait threshold."""
        loss_duration = self.get_loss_duration()
        return 0 < loss_duration < 0.6  # Brief wait threshold
    
    def is_search_time(self):
        """Check if should enter search mode."""
        loss_duration = self.get_loss_duration()
        return 0.6 <= loss_duration < 3.0  # Search threshold range
    
    def is_lost_timeout(self):
        """Check if person lost for too long."""
        loss_duration = self.get_loss_duration()
        return loss_duration >= 3.0  # Final timeout


def follow_person_loop(
    stop_event,
    scene_state,
    command_client,
    obstacle_flag,
    behavior_mode: str = "FOLLOW",   # "FOLLOW" | "COME_HERE"
    loop_hz: float = 5.0,
):
    """
    Autonomous behavior: follow the closest detected person.
    
    New design principles:
    1. Lock onto ONE person when follow starts
    2. Turn-first policy: turn in place until centered, then move forward
    3. Time-based loss handling (not frame-based)
    4. Maintain temporal memory of target
    """
    
    if not command_client or not command_client.is_connected():
        logger.warning("Command client not connected. FOLLOW aborted.")
        return
    
    period = 1.0 / loop_hz
    
    # ---------- TUNING PARAMETERS ----------
    # Centering thresholds
    CENTER_THRESHOLD = 0.15  # If offset > this, turn in place
    
    # Distance control
    TARGET_AREA = 0.25 if behavior_mode == "FOLLOW" else 0.45
    STOP_AREA = 0.35 if behavior_mode == "FOLLOW" else 0.60
    
    # Motion parameters
    TURN_SPEED = 65          # Speed for in-place turning
    FORWARD_SPEED = 70       # Base forward speed
    FORWARD_DURATION = 0.25  # Short forward pulses
    SEARCH_SPEED = 45        # Slower speed for searching
    
    # Timeouts
    COME_HERE_TIMEOUT = 25.0  # Overall timeout for COME_HERE mode
    
    # ---------- INITIALIZATION ----------
    logger.info(f"FOLLOW_PERSON starting in {behavior_mode} mode")
    
    target = TargetState()
    come_here_started_at = time.time() if behavior_mode == "COME_HERE" else None
    
    # State variables
    last_command = None
    search_direction = "LEFT"  # Default search direction
    
    # Initialize helpers (kept for compatibility)
    memory = SpatialMemory()
    grid = GridMemory()
    
    while True:
        if stop_event.is_set():
            _send_stop(command_client, last_command)
            last_command = "STOP"
            break
        
        start_time = time.time()
        
        # ---------- SAFETY CHECKS ----------
        if obstacle_flag():
            logger.warning("Obstacle detected. Stopping.")
            _send_stop(command_client, last_command)
            last_command = "STOP"
            _interruptible_sleep(stop_event, period)
            continue
        
        # Check COME_HERE timeout
        if (behavior_mode == "COME_HERE" and 
            come_here_started_at and 
            time.time() - come_here_started_at > COME_HERE_TIMEOUT):
            logger.warning("COME_HERE timeout. Stopping.")
            _send_stop(command_client, last_command)
            last_command = "STOP"
            break
        
        # ---------- UPDATE TARGET STATE ----------
        target.update(
            scene_state.person_offset_x,
            scene_state.person_area_ratio,
            scene_state.person_visible
        )
        
        # ---------- LOSS HANDLING (TIME-BASED) ----------
        if not target.visible:
            loss_duration = target.get_loss_duration()
            
            if target.is_recently_lost():
                # Brief loss: wait without action
                logger.debug(f"Person briefly lost ({loss_duration:.1f}s). Waiting...")
                _interruptible_sleep(stop_event, period)
                continue
            
            elif target.is_search_time():
                # Search mode: slow turn toward last known direction
                search_dir = target.last_known_direction or search_direction
                logger.info(f"Searching ({loss_duration:.1f}s), turning {search_dir}")
                
                command_client.send_command({
                    "type": "TURN",
                    "direction": search_dir,
                    "speed": SEARCH_SPEED,
                    "duration": period,
                })
                last_command = "SEARCH_TURN"
                
                # Alternate search direction for next iteration
                search_direction = "RIGHT" if search_dir == "LEFT" else "LEFT"
                
                # Check if person reappeared during search
                _interruptible_sleep(stop_event, period)
                continue
            
            elif target.is_lost_timeout():
                # Final timeout: stop and exit
                logger.warning(f"Person lost for {loss_duration:.1f}s. Stopping follow.")
                _send_stop(command_client, last_command)
                last_command = "STOP"
                break
            
            else:
                # Should not reach here
                _interruptible_sleep(stop_event, period)
                continue
        
        # ---------- PERSON IS VISIBLE ----------
        # Extract smoothed values
        offset = target.offset_x
        area = target.area_ratio
        
        # ---------- SAFETY STOP (PERSON TOO CLOSE) ----------
        if area >= STOP_AREA:
            logger.info("Person at stop distance. Holding position.")
            _send_stop(command_client, last_command)
            last_command = "STOP"
            
            # For COME_HERE mode, exit when target reached
            if behavior_mode == "COME_HERE" and area >= STOP_AREA:
                logger.info("COME_HERE complete. Target reached.")
                break
            
            _interruptible_sleep(stop_event, period)
            continue
        
        # ---------- TURN-FIRST POLICY ----------
        # Check if need to turn to center person
        if abs(offset) > CENTER_THRESHOLD:
            # Turn in place (no forward motion)
            direction = "RIGHT" if offset > 0 else "LEFT"
            logger.info(f"Turning {direction} to center (offset: {offset:.2f})")
            
            command_client.send_command({
                "type": "TURN",
                "direction": direction,
                "speed": TURN_SPEED,
                "duration": period * 1.5,  # Slightly longer for smooth turn
            })
            last_command = "TURN"
            
            # Update memory
            if direction == "LEFT":
                grid.turn_left()
            else:
                grid.turn_right()
            memory.mark_direction(direction)
        
        # ---------- FORWARD MOVEMENT ----------
        # Only move forward if person is centered AND we're too far
        elif abs(offset) <= CENTER_THRESHOLD and area < TARGET_AREA:
            logger.info(f"Moving forward (distance: {area:.2f})")
            
            command_client.send_command({
                "type": "MOVE",
                "direction": "FORWARD",
                "speed": FORWARD_SPEED,
                "duration": FORWARD_DURATION,
            })
            last_command = "FORWARD"
            
            # Update memory
            memory.mark_direction("FORWARD")
            grid.move_forward()
        
        # ---------- HOLD POSITION ----------
        # Person centered and at proper distance
        else:
            if last_command != "STOP":
                _send_stop(command_client, last_command)
                last_command = "STOP"
        
        # ---------- MAINTAIN LOOP RATE ----------
        elapsed = time.time() - start_time
        sleep_time = period - elapsed
        if sleep_time > 0:
            _interruptible_sleep(stop_event, sleep_time)
    
    # ---------- CLEANUP ----------
    logger.info("FOLLOW_PERSON loop exiting")
    try:
        command_client.send_command({"type": "STOP"})
    except Exception:
        pass


def _interruptible_sleep(stop_event, duration, step=0.05):
    """Sleep in small steps so stop_event can interrupt."""
    end_time = time.time() + duration
    while time.time() < end_time:
        if stop_event.is_set():
            return
        time.sleep(min(step, end_time - time.time()))


def _send_stop(command_client, last_command):
    """Send stop command if not already stopped."""
    if last_command == "STOP":
        return
    try:
        command_client.send_command({"type": "STOP"})
    except Exception:
        pass
