# =============================
# file: classes/led_strip_class.py
# =============================
# Purpose:
# - Control a WS2812/NeoPixel LED strip using fixed GPIO14.
# - Provide simple helper functions and test patterns.
#
# Safety:
# - Brightness is permanently limited by MAX_BRIGHTNESS.
# - Any higher brightness request is automatically clamped.

from machine import Pin
import neopixel
import time
import uasyncio as asyncio

class LedStrip:

    # Absolute safety brightness limit (never exceeded)
    MAX_BRIGHTNESS = 0.25

    # Fixed data pin for this project
    DATA_PIN_NUMBER = 14

    # Create LED strip controller (GPIO14 is fixed)
    def __init__(self, led_count=50, brightness=0.15, color_order="RGB"):

        # Store configuration
        self.led_count = int(led_count)
        self.color_order = str(color_order).upper()

        # Clamp brightness to safe range
        self.brightness = self.clamp_brightness_utility(brightness)

        # Setup hardware pin and pixel buffer
        self.data_pin = Pin(self.DATA_PIN_NUMBER, Pin.OUT)
        self.pixels = neopixel.NeoPixel(self.data_pin, self.led_count)

        # Start in safe OFF state
        self.turn_off()

    # Clamp brightness into safe allowed range
    def clamp_brightness_utility(self, brightness):

        brightness_value = float(brightness)

        if brightness_value < 0.0:
            brightness_value = 0.0

        if brightness_value > self.MAX_BRIGHTNESS:
            brightness_value = self.MAX_BRIGHTNESS

        return brightness_value

    # Update brightness (always clamped)
    def set_brightness(self, brightness):
        self.brightness = self.clamp_brightness_utility(brightness)

    # Send current buffer to LED strip
    def show(self):
        self.pixels.write()

    # Turn entire strip OFF immediately
    def turn_off(self):
        self.pixels.fill((0, 0, 0))
        self.show()

    # Convert RGB input to strip order + apply brightness
    def rgb_to_strip_tuple_utility(self, red, green, blue):

        # Clamp raw channels to valid 0–255
        red_value = max(0, min(255, int(red)))
        green_value = max(0, min(255, int(green)))
        blue_value = max(0, min(255, int(blue)))

        # Apply brightness scaling
        scaled_red = int(red_value * self.brightness)
        scaled_green = int(green_value * self.brightness)
        scaled_blue = int(blue_value * self.brightness)

        # Map to configured strip color order
        if self.color_order == "RGB":
            return (scaled_red, scaled_green, scaled_blue)

        # Default to GRB (common WS2812 order)
        return (scaled_green, scaled_red, scaled_blue)

    # Set one LED (buffer only, call show() to apply)
    def set_pixel(self, index, red, green, blue):

        pixel_index = int(index)

        if pixel_index < 0 or pixel_index >= self.led_count:
            return

        self.pixels[pixel_index] = self.rgb_to_strip_tuple_utility(red, green, blue)

    # Fill entire strip with one color and write immediately
    def fill(self, red, green, blue):

        strip_color = self.rgb_to_strip_tuple_utility(red, green, blue)

        self.pixels.fill(strip_color)
        self.show()

    async def flow_five_leds_circular_async(self, cycles=3, delay_ms=40):

        tail_strengths = [1.0, 0.6, 0.35, 0.2, 0.1]
        total_steps = self.led_count * int(cycles)

        for step in range(total_steps):

            head_index = step % self.led_count
            progress = head_index / (self.led_count - 1)

            if progress <= 0.5:
                blend = progress / 0.5
                red_value = int(255 * (1 - blend))
                green_value = int(255 * blend)
                blue_value = 0
            else:
                blend = (progress - 0.5) / 0.5
                red_value = 0
                green_value = int(255 * (1 - blend))
                blue_value = int(255 * blend)

            # Clear buffer only (do NOT call turn_off here)
            self.pixels.fill((0, 0, 0))

            for offset in range(5):
                pixel_index = (head_index - offset) % self.led_count
                strength = tail_strengths[offset]

                self.set_pixel(
                    pixel_index,
                    int(red_value * strength),
                    int(green_value * strength),
                    int(blue_value * strength),
                )

            self.show()
            await asyncio.sleep_ms(int(delay_ms))

        self.turn_off()
        
    # =============================
    # TESTER FUNCTIONS
    # =============================
    # Quick wiring + color test
    def test_solid_colors(self, hold_ms=600):

        self.fill(255, 0, 0)
        time.sleep_ms(int(hold_ms))

        self.fill(0, 255, 0)
        time.sleep_ms(int(hold_ms))

        self.fill(0, 0, 255)
        time.sleep_ms(int(hold_ms))

        self.fill(255, 255, 255)
        time.sleep_ms(int(hold_ms))

        self.turn_off()

    # Move a single dot across the strip
    def test_chase_dot(self, red=255, green=0, blue=0, delay_ms=30, loops=2):

        for loop_index in range(int(loops)):
            for pixel_index in range(self.led_count):

                self.turn_off()
                self.set_pixel(pixel_index, red, green, blue)
                self.show()
                time.sleep_ms(int(delay_ms))

        self.turn_off()

    # Sweep brightness up and down (still clamped by MAX_BRIGHTNESS)
    def test_brightness_sweep(self, red=255, green=255, blue=255, step=0.05, delay_ms=70):

        original_brightness = self.brightness

        brightness_value = 0.0
        while brightness_value <= 1.0:
            self.set_brightness(brightness_value)
            self.fill(red, green, blue)
            time.sleep_ms(int(delay_ms))
            brightness_value += float(step)

        brightness_value = 1.0
        while brightness_value >= 0.0:
            self.set_brightness(brightness_value)
            self.fill(red, green, blue)
            time.sleep_ms(int(delay_ms))
            brightness_value -= float(step)

        self.set_brightness(original_brightness)
        self.turn_off()