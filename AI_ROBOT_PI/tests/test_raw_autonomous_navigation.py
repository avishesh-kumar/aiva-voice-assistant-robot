#!/usr/bin/env python3
"""
RAW AUTONOMOUS NAVIGATION TEST
-----------------------------
- Forward autonomous movement
- Obstacle detection
- Turn & retry navigation
- Uses raw GPIO logic only
"""

import RPi.GPIO as GPIO
import time
import random

# ================= MOTOR PINS =================
L_IN1 = 18
L_IN2 = 27
L_EN  = 17

R_IN1 = 22
R_IN2 = 23
R_EN  = 24
# =============================================

# ================= ULTRASONIC =================
TRIG = 26
ECHO = 19
SAFE_DISTANCE_CM = 40
# =============================================

PWM_FREQ = 1000
FORWARD_SPEED = 60
TURN_SPEED = 70

CHECK_INTERVAL = 0.02
TURN_TIME = 0.7


# ---------- GPIO SETUP ----------
def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    pins = [L_IN1, L_IN2, L_EN, R_IN1, R_IN2, R_EN, TRIG]
    for p in pins:
        GPIO.setup(p, GPIO.OUT)

    GPIO.setup(ECHO, GPIO.IN)

    lpwm = GPIO.PWM(L_EN, PWM_FREQ)
    rpwm = GPIO.PWM(R_EN, PWM_FREQ)

    lpwm.start(0)
    rpwm.start(0)

    GPIO.output(TRIG, GPIO.LOW)
    time.sleep(0.1)

    return lpwm, rpwm


# ---------- ULTRASONIC ----------
def get_distance():
    GPIO.output(TRIG, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG, GPIO.LOW)

    timeout = time.time() + 0.02

    while GPIO.input(ECHO) == 0:
        if time.time() > timeout:
            return None
        pulse_start = time.time()

    while GPIO.input(ECHO) == 1:
        if time.time() > timeout:
            return None
        pulse_end = time.time()

    duration = pulse_end - pulse_start
    return round(duration * 17150, 1)


# ---------- MOTOR ACTIONS ----------
def stop(lpwm, rpwm):
    lpwm.ChangeDutyCycle(0)
    rpwm.ChangeDutyCycle(0)
    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.LOW)


def forward(lpwm, rpwm):
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)
    lpwm.ChangeDutyCycle(FORWARD_SPEED)
    rpwm.ChangeDutyCycle(FORWARD_SPEED)


def turn_left(lpwm, rpwm):
    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.HIGH)
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)
    lpwm.ChangeDutyCycle(TURN_SPEED)
    rpwm.ChangeDutyCycle(TURN_SPEED)


def turn_right(lpwm, rpwm):
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.HIGH)
    lpwm.ChangeDutyCycle(TURN_SPEED)
    rpwm.ChangeDutyCycle(TURN_SPEED)


# ---------- AUTONOMOUS LOOP ----------
def main():
    print("\n=== RAW AUTONOMOUS NAVIGATION TEST ===\n")
    lpwm, rpwm = setup()

    try:
        while True:
            print("[AUTO] Moving forward")
            forward(lpwm, rpwm)

            while True:
                d = get_distance()
                if d is not None:
                    print(f"[SENSOR] Front: {d} cm")
                    if d <= SAFE_DISTANCE_CM:
                        print("🚨 Obstacle detected → stopping")
                        break
                time.sleep(CHECK_INTERVAL)

            stop(lpwm, rpwm)
            time.sleep(0.2)

            # Decide turn direction
            turn_dir = random.choice(["LEFT", "RIGHT"])
            print(f"[AUTO] Turning {turn_dir}")

            if turn_dir == "LEFT":
                turn_left(lpwm, rpwm)
            else:
                turn_right(lpwm, rpwm)

            time.sleep(TURN_TIME)
            stop(lpwm, rpwm)
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Autonomous test stopped by user")

    finally:
        stop(lpwm, rpwm)
        lpwm.stop()
        rpwm.stop()
        GPIO.cleanup()
        print("\n=== AUTONOMOUS TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()
