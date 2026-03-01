# esp32/classes/led_strip_class.py
"""
NeoPixel LED strip helper for the 50-LED GRB WS2812B strip.

Hardware: GPIO14, 50 LEDs, WS2812B, driven at 3.3V logic (works for most WS2812B).

Usage:
    from classes.led_strip_class import LedStrip
    led = LedStrip()
    led.fill(0, 0, 200)   # blue
    asyncio.run(led.flow_five_leds_circular_async(cycles=2))
"""

import uasyncio as asyncio
from machine import Pin
from neopixel import NeoPixel


# Default hardware config — change here if you rewire
LED_STRIP_PIN      = 14
LED_COUNT          = 50
DEFAULT_BRIGHTNESS = 0.15   # 15% — bright enough to see, low enough to not blind


class LedStrip:

    def __init__(self, pin=LED_STRIP_PIN, led_count=LED_COUNT,
                 brightness=DEFAULT_BRIGHTNESS, color_order="GRB"):
        """
        Set up the NeoPixel strip.

        Args:
            pin:         GPIO number for the data line
            led_count:   Total LEDs on the strip
            brightness:  0.0 to 1.0 scale factor applied before every write
            color_order: "GRB" (WS2812B default) or "RGB" — controls channel swap
        """
        self.led_count   = int(led_count)
        self.color_order = color_order
        self.brightness_utility = max(0.0, min(1.0, float(brightness)))

        self.neo = NeoPixel(Pin(int(pin), Pin.OUT), self.led_count)

        # Start with all LEDs off
        self.turn_off()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def scale_utility(self, r, g, b):
        """Apply brightness and clamp to 0-255. Returns (r, g, b) ints."""
        br = self.brightness_utility
        return (
            int(max(0, min(255, r * br))),
            int(max(0, min(255, g * br))),
            int(max(0, min(255, b * br))),
        )

    def write_pixel_utility(self, index, r, g, b):
        """
        Write one pixel into the NeoPixel buffer (no hardware write yet).
        Handles GRB vs RGB channel order so the caller always uses (r, g, b).
        """
        sr, sg, sb = self.scale_utility(r, g, b)
        if self.color_order == "GRB":
            # WS2812B stores Green in the first byte position
            self.neo[index] = (sg, sr, sb)
        else:
            self.neo[index] = (sr, sg, sb)

    # ------------------------------------------------------------------
    # Public sync methods
    # ------------------------------------------------------------------

    def show(self):
        """Push the current pixel buffer to the hardware strip."""
        self.neo.write()

    def turn_off(self):
        """Turn all LEDs off immediately."""
        self.neo.fill((0, 0, 0))
        self.neo.write()

    def fill(self, r, g, b):
        """Fill every LED with one color and push to hardware."""
        for i in range(self.led_count):
            self.write_pixel_utility(i, r, g, b)
        self.neo.write()

    def set_pixel(self, index, r, g, b):
        """Set one pixel and push immediately."""
        self.write_pixel_utility(index, r, g, b)
        self.neo.write()

    def set_brightness(self, level):
        """
        Change the brightness scale (0.0 to 1.0).
        Does NOT push to hardware — call fill() or show() after to apply visually.
        """
        self.brightness_utility = max(0.0, min(1.0, float(level)))

    # ------------------------------------------------------------------
    # Async animation
    # ------------------------------------------------------------------

    async def flow_five_leds_circular_async(self, r=0, g=0, b=200,
                                             cycles=3, delay_ms=40):
        """
        Animate a 5-LED window that travels around the strip in a circle.

        Why this fixes the hiccup:
            Each frame ends with 'await asyncio.sleep_ms(delay_ms)'.
            During that sleep, uasyncio runs all other tasks — RFID scan,
            OLED updates, MQTT polling. The animation never holds the event
            loop longer than one neo.write() call (~1-2ms for 50 LEDs).

        Args:
            r, g, b:   Color of the moving window (default: blue)
            cycles:    How many full rotations before the coroutine returns
            delay_ms:  Time between frames — 40ms gives ~25 effective fps

        Notes:
            - asyncio.CancelledError is caught so the strip turns off cleanly
              when a new event (RFID, remote cmd) cancels the running task.
            - Re-raises CancelledError so uasyncio marks the task as cancelled.
        """
        window = 5   # number of lit LEDs in the moving tail
        total_frames = self.led_count * cycles

        try:
            for frame in range(total_frames):
                head = frame % self.led_count

                # Clear the entire buffer before writing the new window
                for i in range(self.led_count):
                    self.neo[i] = (0, 0, 0)

                # Write the 5-LED window, wrapping around at the end
                for offset in range(window):
                    pixel_index = (head + offset) % self.led_count
                    self.write_pixel_utility(pixel_index, r, g, b)

                # Push to hardware — takes ~1-2ms
                self.neo.write()

                # YIELD HERE — this is the critical point that prevents blocking
                await asyncio.sleep_ms(delay_ms)

        except asyncio.CancelledError:
            # Clean up and signal the task was properly cancelled
            self.turn_off()
            raise
