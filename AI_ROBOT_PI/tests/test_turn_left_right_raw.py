#!/usr/bin/env python3
"""
RAW LEFT / RIGHT MOTOR TEST
---------------------------
Uses direct GPIO + PWM
No dependency on existing motor files
"""

import RPi.GPIO as GPIO
import time

# ===== PIN DEFINITIONS =====
# Left motor
L_IN1 = 18
L_IN2 = 27
L_EN  = 17

# Right motor
R_IN1 = 22
R_IN2 = 23
R_EN  = 24
# ==========================

PWM_FREQ = 1000
TURN_SPEED = 70    # strong torque
TURN_TIME = 2.0    # seconds


def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    pins = [L_IN1, L_IN2, L_EN, R_IN1, R_IN2, R_EN]
    for p in pins:
        GPIO.setup(p, GPIO.OUT)

    left_pwm = GPIO.PWM(L_EN, PWM_FREQ)
    right_pwm = GPIO.PWM(R_EN, PWM_FREQ)

    left_pwm.start(0)
    right_pwm.start(0)

    return left_pwm, right_pwm


def stop(left_pwm, right_pwm):
    left_pwm.ChangeDutyCycle(0)
    right_pwm.ChangeDutyCycle(0)

    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.LOW)


def turn_left(left_pwm, right_pwm, speed):
    print("[ACTION] TURN LEFT")

    # Left motor backward
    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.HIGH)

    # Right motor forward
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)

    left_pwm.ChangeDutyCycle(speed)
    right_pwm.ChangeDutyCycle(speed)


def turn_right(left_pwm, right_pwm, speed):
    print("[ACTION] TURN RIGHT")

    # Left motor forward
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)

    # Right motor backward
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.HIGH)

    left_pwm.ChangeDutyCycle(speed)
    right_pwm.ChangeDutyCycle(speed)


def main():
    print("\n=== RAW LEFT / RIGHT TURN TEST ===\n")
    left_pwm, right_pwm = setup()

    try:
        # TURN LEFT
        turn_left(left_pwm, right_pwm, TURN_SPEED)
        time.sleep(TURN_TIME)
        stop(left_pwm, right_pwm)
        time.sleep(1)

        # TURN RIGHT
        turn_right(left_pwm, right_pwm, TURN_SPEED)
        time.sleep(TURN_TIME)
        stop(left_pwm, right_pwm)

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Stopped by user")

    finally:
        print("[CLEANUP] Stopping motors & cleaning GPIO")
        stop(left_pwm, right_pwm)
        left_pwm.stop()
        right_pwm.stop()
        GPIO.cleanup()
        print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()
