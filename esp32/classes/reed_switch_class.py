"""
reed_switch_class.py - Reed switch input helper

Purpose:
- Read a reed switch as a digital input.
- Provide debounced reading for stable state detection.
- Provide an async wait method to detect open/close transitions.

Notes:
- Default wiring assumes reed switch to ground (pull-up enabled).
- Set inverted=True if wiring logic is reversed.
"""

from machine import Pin
import uasyncio as asyncio
import time

# Default pins (final wiring)
REED_GPIO = 16


class ReedSwitch:

    # Initialize reed input and capture initial baseline state
    def __init__(self, pin=REED_GPIO, use_pull_up=True, debounce_ms=30, inverted=False):
        # Select correct pull resistor configuration
        pull_mode = Pin.PULL_UP if use_pull_up else Pin.PULL_DOWN

        # Configure GPIO as digital input
        self.pin = Pin(int(pin), Pin.IN, pull_mode)

        # Store debounce timing (milliseconds)
        self.debounce_ms = int(debounce_ms)

        # Store optional polarity inversion flag
        self.inverted = bool(inverted)

        # Capture initial stable state at startup
        self.last_stable_state = self.read_raw()

    # Read the current raw digital value from the pin
    def read_raw(self):
        value = self.pin.value()

        # Apply logical inversion if required
        if self.inverted:
            value = 0 if value else 1

        return value

    # Read a stable debounced value using simple double-sampling
    async def read_stable(self):
        # First sample
        first = self.read_raw()
        await asyncio.sleep_ms(self.debounce_ms)

        # Second sample
        second = self.read_raw()
        if first == second:
            self.last_stable_state = second
            return second

        # Third sample if mismatch detected
        await asyncio.sleep_ms(self.debounce_ms)
        third = self.read_raw()

        self.last_stable_state = third
        return third

    # Wait until reed state changes or timeout occurs
    async def wait_for_change(self, timeout_ms=None, poll_ms=10):
        poll_ms = int(poll_ms)
        start_time = time.ticks_ms()

        # Establish baseline state before waiting
        baseline = await self.read_stable()

        while True:
            current = await self.read_stable()

            # Return new state immediately if changed
            if current != baseline:
                return current

            # Handle timeout if configured
            if timeout_ms is not None:
                elapsed = time.ticks_diff(time.ticks_ms(), start_time)
                if elapsed >= int(timeout_ms):
                    return None

            await asyncio.sleep_ms(poll_ms)