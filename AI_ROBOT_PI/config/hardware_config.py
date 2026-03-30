"""
Hardware Pin Configuration for Raspberry Pi Robot
LOCKED GPIO pins - DO NOT CHANGE
"""

# Motor Driver Pins (L298N or similar)
LEFT_MOTOR_IN1 = 18
LEFT_MOTOR_IN2 = 27
LEFT_MOTOR_EN = 17   # PWM pin for left motor speed

RIGHT_MOTOR_IN1 = 22
RIGHT_MOTOR_IN2 = 23
RIGHT_MOTOR_EN = 24  # PWM pin for right motor speed

# Ultrasonic Sensor Pins (HC-SR04)
ULTRASONIC_FRONT_TRIG = 26
ULTRASONIC_FRONT_ECHO = 19

ULTRASONIC_LEFT_TRIG = 6
ULTRASONIC_LEFT_ECHO = 5

ULTRASONIC_RIGHT_TRIG = 21
ULTRASONIC_RIGHT_ECHO = 20

# PWM Frequency (Hz) for motor control
PWM_FREQUENCY = 2000

# Motor speed range
MIN_SPEED = 0
MAX_SPEED = 100

# Physical constants (approximate - adjust based on your robot)
# Time in seconds to move 100cm forward at speed 50
FORWARD_100CM_TIME = 2.0
# Time in seconds to turn 90 degrees at speed 50
TURN_90DEG_TIME = 0.6
