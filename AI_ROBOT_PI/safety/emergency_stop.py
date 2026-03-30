"""
Emergency stop handler - provides immediate, dominant motor-level stopping.
"""
import time

def trigger_emergency_stop(movement_controller):
    """
    Perform emergency stop - immediate, dominant motor-level stop.
    
    Args:
        movement_controller: MovementController instance to stop
    """
    try:
        # Bypass all distance checks and cancel any ongoing movement
        # Call motor driver directly for fastest possible stop
        movement_controller.motor.stop()  # Hard stop at motor level
        
        # Also call the controller's stop method to update state
        movement_controller.stop()
        
        # Ensure we're really stopped
        movement_controller.is_moving = False
        movement_controller.current_movement = None
        
        return {
            "ok": True,
            "type": "EMERGENCY_STOP",
            "timestamp": time.time(),
            "message": "Emergency stop executed"
        }
    except Exception as e:
        # Even if there's an error, try to stop
        try:
            movement_controller.motor.set_speed(0, 0)
        except:
            pass
        raise e
