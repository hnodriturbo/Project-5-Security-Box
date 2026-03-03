# ==========================================
# file: classes/led_strip_class.py
# ==========================================
#
# Purpose:
# - Control a WS2812/NeoPixel LED strip (50 LEDs, GPIO14).
# - Provide sync and async lighting effects.
# - Provide a toggleable rainbow screensaver that runs as a background task.
#
# Key concept — blocking vs non-blocking:
# - tail_circular()         : BLOCKING — freezes code until done (use at end of a flow)
# - tail_circular_async()   : NON-BLOCKING — other tasks keep running, await it
# - blink_color_async()     : NON-BLOCKING — good for quick feedback
# - start_screensaver()     : starts forever rainbow loop as a background task
# - stop_screensaver()      : cancels the background task and turns off strip
#
# Screensaver:
# - Smooth hue rotation with a 5-LED tail going around the strip.
# - Runs forever until stop_screensaver() is called.
# - Controlled from NiceGUI dashboard via MQTT commands:
#     {"command": "led_screensaver_on"}
#     {"command": "led_screensaver_off"}
# ==========================================

import uasyncio as asyncio
from machine import Pin
import neopixel
import time


class LedStrip:

    MAX_BRIGHTNESS = 0.35   # safety cap — avoids power spikes on USB power

    # ------------------------------------------
    # Init
    # ------------------------------------------
    def __init__(self, led_count=50, brightness=0.20, color_order="RGB"):
        self.data_pin    = 14
        self.led_count   = int(led_count)
        self.color_order = color_order

        # Set brightness safely (clamped inside set_brightness)
        self.brightness = 0.0
        self.set_brightness(brightness)

        # Create NeoPixel driver
        self.pixels = neopixel.NeoPixel(Pin(self.data_pin, Pin.OUT), self.led_count)

        # Track the screensaver background task so we can cancel it later
        self.screensaver_task = None

        # Start with strip off
        self.turn_off()

    # ------------------------------------------
    # Brightness helpers
    # ------------------------------------------

    def set_brightness(self, brightness):
        # Clamp brightness between 0 and MAX_BRIGHTNESS
        if brightness < 0:
            brightness = 0
        if brightness > self.MAX_BRIGHTNESS:
            brightness = self.MAX_BRIGHTNESS
        self.brightness = brightness

    def apply_brightness_utility(self, r, g, b):
        # Scale RGB values by current brightness (0.0 – MAX_BRIGHTNESS)
        scale = self.brightness
        return (int(r * scale), int(g * scale), int(b * scale))

    def apply_color_order_utility(self, r, g, b):
        # Reorder channels based on strip type (WS2812 is usually GRB)
        if self.color_order == "GRB":
            return (g, r, b)
        return (r, g, b)   # default RGB

    def set_pixel_utility(self, index, r, g, b):
        # Set one LED with brightness + color order applied
        if index < 0 or index >= self.led_count:
            return
        r2, g2, b2 = self.apply_brightness_utility(r, g, b)
        self.pixels[index] = self.apply_color_order_utility(r2, g2, b2)

    def show(self):
        # Push pixel buffer to the physical strip
        self.pixels.write()

    # ------------------------------------------
    # Basic sync actions
    # ------------------------------------------

    def fill(self, r, g, b):
        # Set all LEDs to one color and update strip immediately
        for i in range(self.led_count):
            self.set_pixel_utility(i, r, g, b)
        self.show()

    def turn_off(self):
        # Set all LEDs to black and update strip
        for i in range(self.led_count):
            self.pixels[i] = (0, 0, 0)
        self.show()

    # ------------------------------------------
    # HSV to RGB helper (no math library needed)
    # Used by the screensaver to produce smooth color transitions
    #
    # h = hue 0-359 (color wheel position)
    # s = saturation 0-255 (255 = full color, 0 = white/grey)
    # v = value/brightness 0-255 (255 = full brightness)
    # ------------------------------------------

    def hsv_to_rgb_utility(self, h, s, v):
        # Convert HSV color space to RGB — integer math only, no floats
        if s == 0:
            return (v, v, v)   # grey when no saturation

        h = int(h) % 360
        s = int(s)
        v = int(v)

        i = h // 60             # which 60-degree sector of the color wheel
        f = h % 60              # how far into that sector (0-59)

        p = (v * (255 - s)) // 255
        q = (v * (255 - (s * f) // 60)) // 255
        t = (v * (255 - (s * (60 - f)) // 60)) // 255

        if i == 0: return (v, t, p)
        if i == 1: return (q, v, p)
        if i == 2: return (p, v, t)
        if i == 3: return (p, q, v)
        if i == 4: return (t, p, v)
        return (v, p, q)

    # ------------------------------------------
    # Screensaver — rainbow tail loop (background task)
    #
    # A 5-LED tail chases around the strip forever.
    # The color smoothly rotates through the full hue spectrum.
    # Runs as a background task — does not block anything.
    # ------------------------------------------

    def start_screensaver(self):
        # Start the screensaver only if it is not already running
        if self.screensaver_task is not None:
            return   # already running, do nothing

        # create_task() launches the loop in the background and returns immediately
        self.screensaver_task = asyncio.create_task(self.screensaver_loop_async())

    def stop_screensaver(self):
        # Cancel the background task and turn off the strip
        if self.screensaver_task is not None:
            self.screensaver_task.cancel()
            self.screensaver_task = None

        self.turn_off()

    def is_screensaver_running(self):
        # Returns True if the screensaver loop is currently active
        return self.screensaver_task is not None

    async def screensaver_loop_async(self):
        # Rainbow tail chase — runs forever until task is cancelled
        tail_strength = [255, 140, 70, 35, 15]   # fade from head to tail

        hue  = 0     # current color position on the wheel (0-359)
        step = 0     # tracks which LED is the head of the tail

        while True:
            # Clear the strip for this frame
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            # Get current color from hue — full saturation, half brightness
            r, g, b = self.hsv_to_rgb_utility(hue, 255, 180)

            # Head position wraps around when it reaches the end of the strip
            head = step % self.led_count

            # Draw 5 LEDs: head at full strength, fading toward tail
            for tail_index in range(5):
                pos = (head - tail_index) % self.led_count
                s   = tail_strength[tail_index]

                # Scale color by tail fade strength
                self.set_pixel_utility(
                    pos,
                    (r * s) // 255,
                    (g * s) // 255,
                    (b * s) // 255,
                )

            self.show()

            # Advance hue slowly so color changes smoothly over time
            hue  = (hue + 1) % 360
            step = (step + 1) % self.led_count

            # yield control — lets MQTT, RFID, and other tasks run between frames
            await asyncio.sleep_ms(40)

    # ------------------------------------------
    # Async blink effects (non-blocking)
    # Use create_task() to fire these without waiting
    # ------------------------------------------

    async def blink_color_async(self, r, g, b, times=3, on_ms=180, off_ms=180):
        # Blink a color N times — other tasks keep running during sleeps
        for _ in range(int(times)):
            self.fill(r, g, b)
            await asyncio.sleep_ms(int(on_ms))
            self.turn_off()
            await asyncio.sleep_ms(int(off_ms))

    async def blink_green_three_times_async(self):
        await self.blink_color_async(0, 255, 0, times=3)

    async def blink_red_three_times_async(self):
        await self.blink_color_async(255, 0, 0, times=3)

    # ------------------------------------------
    # Async tail (non-blocking)
    # Good for sending a tail effect while MQTT/RFID keep running
    # ------------------------------------------

    async def tail_circular_async(self, cycles=2, delay_ms=40, r=255, g=0, b=0):
        # Moving tail effect — awaitable, does not block other tasks
        tail_strength = [255, 140, 70, 35, 15]
        total_steps   = self.led_count * int(cycles)

        for step in range(total_steps):
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            head = step % self.led_count

            for tail_index in range(5):
                pos = (head - tail_index) % self.led_count
                s   = tail_strength[tail_index]
                self.set_pixel_utility(pos, (r * s) // 255, (g * s) // 255, (b * s) // 255)

            self.show()
            await asyncio.sleep_ms(int(delay_ms))

        self.turn_off()

    # ------------------------------------------
    # Blocking tail (sync)
    # Intentionally freezes everything — use at the END of a procedure
    # as a "flow finished" visual cue
    # ------------------------------------------

    def tail_circular(self, cycles=2, delay_ms=40, r=0, g=0, b=255):
        # BLOCKING — nothing else runs until this finishes
        # Only use this at the very end of a procedure on purpose
        tail_strength = [255, 140, 70, 35, 15]
        total_steps   = self.led_count * int(cycles)

        for step in range(total_steps):
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            head = step % self.led_count

            for tail_index in range(5):
                pos = (head - tail_index) % self.led_count
                s   = tail_strength[tail_index]
                self.set_pixel_utility(
                    pos,
                    (r * s) // 255,
                    (g * s) // 255,
                    (b * s) // 255,
                )

            self.show()
            time.sleep_ms(int(delay_ms))

        self.turn_off()