"""
solenoid_tester_tb6612.py

Purpose:
- Simple, reliable tester for a 5V solenoid lock driven by a TB6612FNG module.
- Works with the common “one-direction” wiring:
  - AIN1 = ESP32 GPIO (control)
  - AIN2 = GND (fixed direction)
  - PWMA = 3.3V (always enabled at full power)
  - STBY = 3.3V (must be HIGH or the driver is disabled)
  - VM = external 5V (solenoid power)
  - VCC = 3.3V (logic)
  - All grounds common

How it behaves:
- AIN1 HIGH  -> solenoid ON (unlock)
- AIN1 LOW   -> solenoid OFF (lock)
"""

from machine import Pin
import time
import sys
sys.path.append("..")
# ---------- PIN SETUP ----------
AIN1_PIN = 12  # Control pin from ESP32 -> TB6612 AIN1

# If you physically wired AIN2 to GND, keep this as None.
# If you wired AIN2 to an ESP32 pin instead, set it here (example: 11).
AIN2_PIN = None  # Example: 11

# If you physically wired STBY and PWMA to 3.3V, keep these as None.
# If you wired them to ESP32 pins instead, set them here (example: STBY=10, PWMA=9).
STBY_PIN = None
PWMA_PIN = None


# ---------- HARDWARE INIT ----------
ain1 = Pin(AIN1_PIN, Pin.OUT, value=0)

ain2 = None
if AIN2_PIN is not None:
    ain2 = Pin(AIN2_PIN, Pin.OUT, value=0)

stby = None
if STBY_PIN is not None:
    stby = Pin(STBY_PIN, Pin.OUT, value=1)

pwma = None
if PWMA_PIN is not None:
    pwma = Pin(PWMA_PIN, Pin.OUT, value=1)


# ---------- HELPERS ----------
def _ensure_enabled():
    # If STBY/PWMA are on GPIO, force them on.
    if stby is not None:
        stby.value(1)
    if pwma is not None:
        pwma.value(1)

    # If AIN2 is on GPIO, force direction low (one-direction use).
    if ain2 is not None:
        ain2.value(0)


def lock():
    # Turn solenoid off (locked state).
    _ensure_enabled()
    ain1.value(0)


def unlock():
    # Turn solenoid on (unlocked state).
    _ensure_enabled()
    ain1.value(1)


def unlock_ms(duration_ms=500):
    # Pulse unlock for a short time, then lock again.
    unlock()
    time.sleep_ms(int(duration_ms))
    lock()


def status_print():
    # Print current logical states (not actual voltage measurement).
    print("\n--- TB6612 SOLENOID TESTER STATUS ---")
    print("AIN1 pin:", AIN1_PIN, "value:", ain1.value())
    if AIN2_PIN is None:
        print("AIN2: wired to GND (fixed direction)")
    else:
        print("AIN2 pin:", AIN2_PIN, "value:", ain2.value())

    if STBY_PIN is None:
        print("STBY: wired to 3.3V (always enabled)")
    else:
        print("STBY pin:", STBY_PIN, "value:", stby.value())

    if PWMA_PIN is None:
        print("PWMA: wired to 3.3V (full power)")
    else:
        print("PWMA pin:", PWMA_PIN, "value:", pwma.value())

    print("------------------------------------\n")


# ---------- INTERACTIVE TEST ----------
def print_menu():
    print("Commands:")
    print("  u = unlock (ON)")
    print("  l = lock (OFF)")
    print("  p = pulse unlock (default 500ms)")
    print("  1 = pulse 200ms")
    print("  2 = pulse 500ms")
    print("  3 = pulse 1000ms")
    print("  s = status")
    print("  q = quit")
    print("Press a key then ENTER.\n")


# Safe startup: keep it locked/off
lock()
print("Solenoid tester ready. Starting in LOCKED (OFF) state.")
print_menu()

while True:
    try:
        cmd = input("> ").strip().lower()

        if cmd == "u":
            unlock()
            print("UNLOCK (ON)")

        elif cmd == "l":
            lock()
            print("LOCK (OFF)")

        elif cmd == "p":
            unlock_ms(500)
            print("PULSE 500ms")

        elif cmd == "1":
            unlock_ms(200)
            print("PULSE 200ms")

        elif cmd == "2":
            unlock_ms(500)
            print("PULSE 500ms")

        elif cmd == "3":
            unlock_ms(1000)
            print("PULSE 1000ms")

        elif cmd == "s":
            status_print()

        elif cmd == "q":
            lock()
            print("Exiting. Left in LOCKED (OFF) state.")
            break

        else:
            print("Unknown command.")
            print_menu()

    except KeyboardInterrupt:
        lock()
        print("\nInterrupted. Left in LOCKED (OFF) state.")
        break
