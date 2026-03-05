from machine import Pin
import time

p = Pin(12, Pin.OUT)
p.value(1)
print("Pin 12 is HIGH")
time.sleep(2)
p.value(0)
print("Pin 12 is LOW")