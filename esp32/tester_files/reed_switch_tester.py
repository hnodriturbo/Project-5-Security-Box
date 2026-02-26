# reed_switch_tester.py
# Purpose: Print "reed on" / "reed off" when the reed switch changes state.

from machine import Pin  # Pin access for ESP32
import time  # Simple timing / debounce

REED_GPIO = 16  # Change this to the GPIO you wired to the reed switch

# Use internal pull-up so the pin is stable when the switch is open
reed_pin = Pin(REED_GPIO, Pin.IN, Pin.PULL_UP)

last_value = reed_pin.value()  # Track last read so I only print on change

print("Reed tester running...")
print("Expected: open=1 (off), closed=0 (on)\n")

while True:
    current_value = reed_pin.value()  # Read reed state

    # Only react when state changes (clean output)
    if current_value != last_value:
        time.sleep_ms(30)  # Small debounce
        current_value = reed_pin.value()  # Re-read after debounce

        if current_value == 0:
            print("reed on")   # Magnet closes switch (to GND)
        else:
            print("reed off")  # Switch open (pulled up)

        last_value = current_value  # Save new state

    time.sleep_ms(10)  # Light loop delay