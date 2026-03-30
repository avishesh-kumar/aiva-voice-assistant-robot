import RPi.GPIO as GPIO
import time

# ===== GPIO PINS (BCM MODE) =====
LEFT_IN1  = 18
LEFT_IN2  = 27
LEFT_EN   = 17

RIGHT_IN1 = 22
RIGHT_IN2 = 23
RIGHT_EN  = 24

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(LEFT_IN1, GPIO.OUT)
GPIO.setup(LEFT_IN2, GPIO.OUT)
GPIO.setup(LEFT_EN, GPIO.OUT)

GPIO.setup(RIGHT_IN1, GPIO.OUT)
GPIO.setup(RIGHT_IN2, GPIO.OUT)
GPIO.setup(RIGHT_EN, GPIO.OUT)

left_pwm  = GPIO.PWM(LEFT_EN, 1000)
right_pwm = GPIO.PWM(RIGHT_EN, 1000)

left_pwm.start(0)
right_pwm.start(0)

def stop():
    GPIO.output(LEFT_IN1, GPIO.LOW)
    GPIO.output(LEFT_IN2, GPIO.LOW)
    GPIO.output(RIGHT_IN1, GPIO.LOW)
    GPIO.output(RIGHT_IN2, GPIO.LOW)
    left_pwm.ChangeDutyCycle(0)
    right_pwm.ChangeDutyCycle(0)

try:
    print("FORWARD")
    GPIO.output(LEFT_IN1, GPIO.HIGH)
    GPIO.output(LEFT_IN2, GPIO.LOW)
    GPIO.output(RIGHT_IN1, GPIO.HIGH)
    GPIO.output(RIGHT_IN2, GPIO.LOW)
    left_pwm.ChangeDutyCycle(50)
    right_pwm.ChangeDutyCycle(50)
    time.sleep(2)

    print("STOP")
    stop()
    time.sleep(1)

    print("BACKWARD")
    GPIO.output(LEFT_IN1, GPIO.LOW)
    GPIO.output(LEFT_IN2, GPIO.HIGH)
    GPIO.output(RIGHT_IN1, GPIO.LOW)
    GPIO.output(RIGHT_IN2, GPIO.HIGH)
    left_pwm.ChangeDutyCycle(50)
    right_pwm.ChangeDutyCycle(50)
    time.sleep(2)

    print("STOP")
    stop()
    time.sleep(1)

    print("TURN LEFT")
    GPIO.output(LEFT_IN1, GPIO.LOW)
    GPIO.output(LEFT_IN2, GPIO.HIGH)
    GPIO.output(RIGHT_IN1, GPIO.HIGH)
    GPIO.output(RIGHT_IN2, GPIO.LOW)
    left_pwm.ChangeDutyCycle(50)
    right_pwm.ChangeDutyCycle(50)
    time.sleep(2)

    print("STOP")
    stop()

except KeyboardInterrupt:
    pass
finally:
    stop()
    left_pwm.stop()
    right_pwm.stop()
    GPIO.cleanup()
    print("DONE")
