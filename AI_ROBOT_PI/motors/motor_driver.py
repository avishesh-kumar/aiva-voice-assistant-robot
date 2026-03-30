"""
Motor Driver for L298N or similar H-bridge motor controller.
Controls two DC motors with PWM speed control.
"""
import time
from config.hardware_config import (
    LEFT_MOTOR_IN1, LEFT_MOTOR_IN2, LEFT_MOTOR_EN,
    RIGHT_MOTOR_IN1, RIGHT_MOTOR_IN2, RIGHT_MOTOR_EN,
    PWM_FREQUENCY, MIN_SPEED, MAX_SPEED
)

try:
    from gpiozero import DigitalOutputDevice, PWMOutputDevice
    GPIOZERO_AVAILABLE = True
    print("[MOTOR] Using gpiozero for GPIO control")
except ImportError:
    try:
        import RPi.GPIO as GPIO
        GPIOZERO_AVAILABLE = False
        print("[MOTOR] Using RPi.GPIO for GPIO control")
    except ImportError:
        print("[MOTOR] ERROR: No GPIO library available! Running in simulation mode.")
        GPIOZERO_AVAILABLE = None


class MotorDriver:
    """Driver for two DC motors with independent speed control."""

    def __init__(self):
        """Initialize motor driver with specified GPIO pins."""
        self.left_speed = 0
        self.right_speed = 0
        self.is_running = False

        if GPIOZERO_AVAILABLE is None:
            print("[MOTOR] Running in simulation mode")
            self.simulation_mode = True
            return

        self.simulation_mode = False

        if GPIOZERO_AVAILABLE:
            self._init_gpiozero()
        else:
            self._init_rpigpio()

        self.is_running = True
        print("[MOTOR] Motor driver initialized")

    def _init_gpiozero(self):
        """Initialize using gpiozero library."""
        self.left_in1 = DigitalOutputDevice(LEFT_MOTOR_IN1)
        self.left_in2 = DigitalOutputDevice(LEFT_MOTOR_IN2)
        self.left_pwm = PWMOutputDevice(LEFT_MOTOR_EN, frequency=PWM_FREQUENCY)

        self.right_in1 = DigitalOutputDevice(RIGHT_MOTOR_IN1)
        self.right_in2 = DigitalOutputDevice(RIGHT_MOTOR_IN2)
        self.right_pwm = PWMOutputDevice(RIGHT_MOTOR_EN, frequency=PWM_FREQUENCY)

    def _init_rpigpio(self):
        """Initialize using RPi.GPIO library."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        GPIO.setup(LEFT_MOTOR_IN1, GPIO.OUT)
        GPIO.setup(LEFT_MOTOR_IN2, GPIO.OUT)
        GPIO.setup(LEFT_MOTOR_EN, GPIO.OUT)

        GPIO.setup(RIGHT_MOTOR_IN1, GPIO.OUT)
        GPIO.setup(RIGHT_MOTOR_IN2, GPIO.OUT)
        GPIO.setup(RIGHT_MOTOR_EN, GPIO.OUT)

        self.left_pwm = GPIO.PWM(LEFT_MOTOR_EN, PWM_FREQUENCY)
        self.right_pwm = GPIO.PWM(RIGHT_MOTOR_EN, PWM_FREQUENCY)

        self.left_pwm.start(0)
        self.right_pwm.start(0)

        # Ensure stopped at boot
        GPIO.output(LEFT_MOTOR_IN1, GPIO.LOW)
        GPIO.output(LEFT_MOTOR_IN2, GPIO.LOW)
        GPIO.output(RIGHT_MOTOR_IN1, GPIO.LOW)
        GPIO.output(RIGHT_MOTOR_IN2, GPIO.LOW)

    def _clamp_speed(self, speed: int) -> int:
        """Clamp speed to valid range [-100, 100]."""
        if speed > MAX_SPEED:
            return MAX_SPEED
        if speed < -MAX_SPEED:
            return -MAX_SPEED
        return speed

    def _speed_to_duty_cycle(self, speed: int) -> float:
        """Convert speed percentage to PWM duty cycle."""
        return abs(speed)

    def _set_motor_direction(self, in1, in2, speed, gpiozero_mode=True):
        """
        Set motor direction based on speed sign.

        gpiozero_mode=True:
            in1/in2 are gpiozero DigitalOutputDevice objects.
        gpiozero_mode=False:
            in1/in2 are BCM pin numbers (ints).
        """
        if gpiozero_mode:
            if speed > 0:
                in1.on()
                in2.off()
            elif speed < 0:
                in1.off()
                in2.on()
            else:
                in1.off()
                in2.off()
        else:
            # RPi.GPIO mode: in1/in2 are pins
            if speed > 0:
                GPIO.output(in1, GPIO.HIGH)
                GPIO.output(in2, GPIO.LOW)
            elif speed < 0:
                GPIO.output(in1, GPIO.LOW)
                GPIO.output(in2, GPIO.HIGH)
            else:
                GPIO.output(in1, GPIO.LOW)
                GPIO.output(in2, GPIO.LOW)

    def set_speed(self, left_speed: int, right_speed: int):
        """
        Set speed for both motors.

        Args:
            left_speed: Left motor speed (-100 to 100)
            right_speed: Right motor speed (-100 to 100)
        """
        left_speed = self._clamp_speed(left_speed)
        right_speed = self._clamp_speed(right_speed)

        self.left_speed = left_speed
        self.right_speed = right_speed

        if self.simulation_mode:
            print(f"[MOTOR] Sim: L={left_speed}, R={right_speed}")
            return

        if GPIOZERO_AVAILABLE:
            self._set_motor_direction(self.left_in1, self.left_in2, left_speed, gpiozero_mode=True)
            self._set_motor_direction(self.right_in1, self.right_in2, right_speed, gpiozero_mode=True)

            self.left_pwm.value = self._speed_to_duty_cycle(left_speed) / 100.0
            self.right_pwm.value = self._speed_to_duty_cycle(right_speed) / 100.0
        else:
            # Correct RPi.GPIO direction handling
            self._set_motor_direction(LEFT_MOTOR_IN1, LEFT_MOTOR_IN2, left_speed, gpiozero_mode=False)
            self._set_motor_direction(RIGHT_MOTOR_IN1, RIGHT_MOTOR_IN2, right_speed, gpiozero_mode=False)

            self.left_pwm.ChangeDutyCycle(self._speed_to_duty_cycle(left_speed))
            self.right_pwm.ChangeDutyCycle(self._speed_to_duty_cycle(right_speed))

    def stop(self):
        """Stop both motors immediately."""
        self.set_speed(0, 0)
        # print("[MOTOR] Motors stopped")  # optional (printing can slow loops)

    def hard_stop(self):
        """Immediately cut motor power (emergency stop)."""
        if self.simulation_mode:
            return

        if GPIOZERO_AVAILABLE:
            self.left_pwm.off()
            self.right_pwm.off()
            self.left_in1.off()
            self.left_in2.off()
            self.right_in1.off()
            self.right_in2.off()
        else:
            self.left_pwm.ChangeDutyCycle(0)
            self.right_pwm.ChangeDutyCycle(0)

    
    def cleanup(self):
        """Clean up GPIO resources."""
        if not self.is_running:
            return

        print("[MOTOR] Cleaning up motor driver...")

        self.stop()

        if self.simulation_mode:
            print("[MOTOR] Simulation cleanup complete")
            return

        if GPIOZERO_AVAILABLE:
            self.left_in1.close()
            self.left_in2.close()
            self.left_pwm.close()
            self.right_in1.close()
            self.right_in2.close()
            self.right_pwm.close()
        else:
            self.left_pwm.stop()
            self.right_pwm.stop()
            GPIO.cleanup()

        self.is_running = False
        print("[MOTOR] Cleanup complete")

    def get_status(self):
        """Get current motor status."""
        return {
            "left_speed": self.left_speed,
            "right_speed": self.right_speed,
            "running": self.is_running,
            "simulation": self.simulation_mode,
        }


if __name__ == "__main__":
    print("Testing MotorDriver...")

    try:
        motor = MotorDriver()

        print("Moving forward at 50% speed...")
        motor.set_speed(50, 50)
        time.sleep(2)

        print("Moving backward at 30% speed...")
        motor.set_speed(-30, -30)
        time.sleep(2)

        print("Turning left...")
        motor.set_speed(-40, 40)
        time.sleep(1)

        print("Stopping...")
        motor.stop()
        time.sleep(1)

        print("Test complete!")

    except KeyboardInterrupt:
        print("\nTest interrupted")
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        motor.cleanup()
