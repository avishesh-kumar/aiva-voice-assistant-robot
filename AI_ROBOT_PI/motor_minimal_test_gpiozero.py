from gpiozero import DigitalOutputDevice, PWMOutputDevice
import time

# ===== GPIO PINS (BCM) =====
LEFT_IN1  = 18
LEFT_IN2  = 27
LEFT_EN   = 17

RIGHT_IN1 = 22
RIGHT_IN2 = 23
RIGHT_EN  = 24

left_in1 = DigitalOutputDevice(LEFT_IN1)
left_in2 = DigitalOutputDevice(LEFT_IN2)
left_pwm = PWMOutputDevice(LEFT_EN, frequency=1000)

right_in1 = DigitalOutputDevice(RIGHT_IN1)
right_in2 = DigitalOutputDevice(RIGHT_IN2)
right_pwm = PWMOutputDevice(RIGHT_EN, frequency=1000)

def stop():
    left_in1.off()
    left_in2.off()
    right_in1.off()
    right_in2.off()
    left_pwm.value = 0
    right_pwm.value = 0

try:
    print("FORWARD")
    left_in1.on()
    left_in2.off()
    right_in1.on()
    right_in2.off()
    left_pwm.value = 0.5
    right_pwm.value = 0.5
    time.sleep(2)

    print("STOP")
    stop()
    time.sleep(1)

    print("BACKWARD")
    left_in1.off()
    left_in2.on()
    right_in1.off()
    right_in2.on()
    left_pwm.value = 0.5
    right_pwm.value = 0.5
    time.sleep(2)

    print("STOP")
    stop()
    time.sleep(1)

    print("TURN LEFT")
    left_in1.off()
    left_in2.on()
    right_in1.on()
    right_in2.off()
    left_pwm.value = 0.5
    right_pwm.value = 0.5
    time.sleep(2)

    print("STOP")
    stop()

except KeyboardInterrupt:
    pass
finally:
    stop()
    print("DONE")
