#!/usr/bin/env python3
"""
RAW MOTOR + ULTRASONIC EMERGENCY STOP TEST
-----------------------------------------
- Forward movement
- Left & Right turning
- Continuous ultrasonic emergency stop
- No dependency on existing motor logic
"""

import RPi.GPIO as GPIO
import time

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
CHECK_INTERVAL = 0.02   # 50 Hz


# ---------- GPIO SETUP ----------
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    pins = [L_IN1, L_IN2, L_EN, R_IN1, R_IN2, R_EN, TRIG]
    for p in pins:
        GPIO.setup(p, GPIO.OUT)

    GPIO.setup(ECHO, GPIO.IN)

    left_pwm = GPIO.PWM(L_EN, PWM_FREQ)
    right_pwm = GPIO.PWM(R_EN, PWM_FREQ)

    left_pwm.start(0)
    right_pwm.start(0)

    GPIO.output(TRIG, GPIO.LOW)
    time.sleep(0.1)

    return left_pwm, right_pwm


# ---------- ULTRASONIC ----------
def get_distance():
    GPIO.output(TRIG, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG, GPIO.LOW)

    start = time.time()
    timeout = start + 0.02

    while GPIO.input(ECHO) == 0:
        if time.time() > timeout:
            return None
        pulse_start = time.time()

    while GPIO.input(ECHO) == 1:
        if time.time() > timeout:
            return None
        pulse_end = time.time()

    duration = pulse_end - pulse_start
    distance = duration * 17150
    return round(distance, 1)


# ---------- MOTOR ACTIONS ----------
def stop_motors(lpwm, rpwm):
    lpwm.ChangeDutyCycle(0)
    rpwm.ChangeDutyCycle(0)

    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.LOW)


def forward(lpwm, rpwm, speed):
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)

    lpwm.ChangeDutyCycle(speed)
    rpwm.ChangeDutyCycle(speed)


def turn_left(lpwm, rpwm, speed):
    GPIO.output(L_IN1, GPIO.LOW)
    GPIO.output(L_IN2, GPIO.HIGH)
    GPIO.output(R_IN1, GPIO.HIGH)
    GPIO.output(R_IN2, GPIO.LOW)

    lpwm.ChangeDutyCycle(speed)
    rpwm.ChangeDutyCycle(speed)


def turn_right(lpwm, rpwm, speed):
    GPIO.output(L_IN1, GPIO.HIGH)
    GPIO.output(L_IN2, GPIO.LOW)
    GPIO.output(R_IN1, GPIO.LOW)
    GPIO.output(R_IN2, GPIO.HIGH)

    lpwm.ChangeDutyCycle(speed)
    rpwm.ChangeDutyCycle(speed)


# ---------- MAIN TEST ----------
def main():
    print("\n=== RAW FORWARD + TURN + EMERGENCY STOP TEST ===\n")
    lpwm, rpwm = setup_gpio()

    try:
        # -------- FORWARD --------
        print("[ACTION] FORWARD")
        forward(lpwm, rpwm, FORWARD_SPEED)

        while True:
            d = get_distance()
            if d is not None:
                print(f"[SENSOR] Front distance: {d} cm")
                if d <= SAFE_DISTANCE_CM:
                    print("\n🚨 EMERGENCY STOP (FORWARD)")
                    break
            time.sleep(CHECK_INTERVAL)

        stop_motors(lpwm, rpwm)
        time.sleep(1)

        # -------- LEFT TURN --------
        print("\n[ACTION] TURN LEFT")
        turn_left(lpwm, rpwm, TURN_SPEED)
        time.sleep(1.5)
        stop_motors(lpwm, rpwm)
        time.sleep(1)

        # -------- RIGHT TURN --------
        print("\n[ACTION] TURN RIGHT")
        turn_right(lpwm, rpwm, TURN_SPEED)
        time.sleep(1.5)
        stop_motors(lpwm, rpwm)

    except KeyboardInterrupt:
        print("\n[INTERRUPT] User stopped test")

    finally:
        print("\n[CLEANUP] Stopping motors & cleaning GPIO")
        stop_motors(lpwm, rpwm)
        lpwm.stop()
        rpwm.stop()
        GPIO.cleanup()
        print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()
