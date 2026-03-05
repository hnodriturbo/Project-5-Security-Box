# esp/classes/led_class.py
"""
LED / NeoPixel class (RGB order)

Purpose:
- Control 1+ NeoPixel LEDs on a single data pin using RGB color order.
- Works for “eyes” (2 LEDs) or a single heartbeat LED (1 LED).

Important:
- This class expects RGB tuples: (red, green, blue)
"""

from machine import Pin
from neopixel import NeoPixel
from time import sleep_ms
import random

# -----------------------------
# Default pins (I will set when i know the final NeoPixel data GPIO)
# -----------------------------
NEOPIXEL_DATA_PIN = None

class LedClass:
    def __init__(self, data_pin=NEOPIXEL_DATA_PIN, led_count=2, name="LEDs"):
        # Stop early if the default pin is not configured yet
        if data_pin is None:
            raise ValueError("NEOPIXEL_DATA_PIN is not set yet. Set it in led_class.py.")

        # Store simple metadata for debugging
        self.name = name
        self.led_count = int(led_count)

        # Create NeoPixel instance on the provided pin (or the configured default)
        self.neo = NeoPixel(Pin(int(data_pin), Pin.OUT), self.led_count)
        
        # Common “eyes” indexing (still useful even if led_count != 2)
        self.LED_LEFT = 0
        self.LED_RIGHT = 1

        # Track current color as RGB
        self.current_color = (0, 0, 0)

        # Start off
        self.off()

    def get_color(self):
        # Return current RGB color
        return self.current_color

    def off(self):
        # Turn all LEDs off
        self.current_color = (0, 0, 0)
        self.neo.fill((0, 0, 0))
        self.neo.write()

    def fill(self, r, g, b):
        # Set all LEDs to same RGB color
        self.current_color = (r, g, b)
        self.neo.fill((r, g, b))
        self.neo.write()

    def set_led(self, led_index, r, g, b):
        # Set one LED by index (RGB)
        self.neo[led_index] = (r, g, b)
        self.neo.write()

    def set_leds(self, left_rgb, right_rgb):
        # Set two LEDs to different RGB colors (index 0 and 1)
        self.neo[self.LED_LEFT] = left_rgb
        self.neo[self.LED_RIGHT] = right_rgb
        self.neo.write()

    def set_leds_same_color(self, rgb):
        # Set two LEDs to the same RGB color
        self.neo[self.LED_LEFT] = rgb
        self.neo[self.LED_RIGHT] = rgb
        self.neo.write()

    def blink(self, r, g, b, times=5, on_ms=300, off_ms=300):
        # Blink all LEDs
        for _ in range(times):
            self.fill(r, g, b)
            sleep_ms(on_ms)
            self.off()
            sleep_ms(off_ms)

    def random_dimmed_colors(self, max_value=60):
        # Set two LEDs to random dim RGB colors
        left_rgb = (
            random.randint(0, max_value),
            random.randint(0, max_value),
            random.randint(0, max_value),
        )
        right_rgb = (
            random.randint(0, max_value),
            random.randint(0, max_value),
            random.randint(0, max_value),
        )
        self.set_leds(left_rgb, right_rgb)
