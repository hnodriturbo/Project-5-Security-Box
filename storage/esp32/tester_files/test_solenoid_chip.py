from machine import Pin
import time

# Required control pin (you already proved this toggles)
AIN1 = Pin(12, Pin.OUT)

# If these are wired to ESP32 GPIO, set them and uncomment.
# STBY = Pin(XX, Pin.OUT)
# PWMA = Pin(YY, Pin.OUT)
# AIN2 = Pin(ZZ, Pin.OUT)

# If GPIO-controlled, force enable + direction.
# STBY.value(1)
# PWMA.value(1)
# AIN2.value(0)

print("Pulse test starting...")

for i in range(5):
    AIN1.value(1)
    time.sleep(0.5)
    AIN1.value(0)
    time.sleep(0.5)

print("Pulse test done.")