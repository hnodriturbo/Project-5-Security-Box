"""
solenoid_class.py - TB6612FNG solenoid driver (A channel)

Purpose:
- Drive a 2-wire solenoid through TB6612FNG A-channel pins.
- Support optional standby (STBY) and optional enable pin.
- Provide a short pulse helper for latch-release behavior.

Notes:
- This assumes the TB6612 output is wired so AIN1 drives the solenoid direction needed.
- If AIN2 is present, it is driven low during activation to avoid floating states.
"""

from machine import Pin
import uasyncio as asyncio

# -----------------------------
# Default pins (final wiring)
# -----------------------------
SOLENOID_AIN1_PIN = 12

class SolenoidTB6612:
    def __init__(
        self,
        ain1_pin=SOLENOID_AIN1_PIN,
        ain2_pin=None,
        standby_pin=None,
        pwm_enable_pin=None,
        active_high=True,
    ):
        # Create output pins used by the TB6612 channel
        self.ain1_pin = Pin(int(ain1_pin), Pin.OUT)
        self.ain2_pin = Pin(int(ain2_pin), Pin.OUT) if ain2_pin is not None else None
        self.standby_pin = Pin(int(standby_pin), Pin.OUT) if standby_pin is not None else None
        self.pwm_enable_pin = Pin(int(pwm_enable_pin), Pin.OUT) if pwm_enable_pin is not None else None

        # Store polarity for boards that invert STBY/EN logic
        self.active_high = bool(active_high)

        # Start with solenoid off, then enable driver so the channel is ready
        self.off()
        self.enable_driver()

    # Enable TB6612 standby and enable pins when present
    def enable_driver(self):
        if self.standby_pin is not None:
            self.standby_pin.value(1 if self.active_high else 0)

        if self.pwm_enable_pin is not None:
            self.pwm_enable_pin.value(1 if self.active_high else 0)

    # Disable TB6612 control pins and ensure outputs are off first
    def disable_driver(self):
        self.off()

        if self.pwm_enable_pin is not None:
            self.pwm_enable_pin.value(0 if self.active_high else 1)

        if self.standby_pin is not None:
            self.standby_pin.value(0 if self.active_high else 1)

    # Drive the solenoid output on
    def on(self):
        self.enable_driver()

        # Drive main control pin to active level
        self.ain1_pin.value(1 if self.active_high else 0)

        # Hold the second pin low when available to avoid floating outputs
        if self.ain2_pin is not None:
            self.ain2_pin.value(0 if self.active_high else 1)

    # Turn the solenoid output off
    def off(self):
        self.ain1_pin.value(0 if self.active_high else 1)

        if self.ain2_pin is not None:
            self.ain2_pin.value(0 if self.active_high else 1)

    # Open solenoid for 5 seconds and then turn it off
    async def pulse(self):
        """
        Unlock the drawer for a fixed 5 seconds.

        Behavior:
        - Solenoid turns ON immediately
        - Stays energized for 5000 ms
        - Turns OFF automatically
        - Does not block other async tasks
        """

        open_duration_ms = 5000  # Fixed unlock window

        self.on()
        await asyncio.sleep_ms(open_duration_ms)
        self.off()