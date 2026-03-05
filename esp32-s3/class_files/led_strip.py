"""
led_strip.py

WS2812 NeoPixel LED strip controller for the Security Box.
Controls 50 LEDs on GPIO14 using the MicroPython neopixel driver.

The screensaver is the default idle state - a rainbow tail that chases
around the strip forever. Every effect (blink, tail) automatically pauses
the screensaver before running and restores it after, so the screensaver
is always the fallback visual state without any extra calls from procedures.

Role in the box:
    Visual feedback for all system events. Screensaver shows the box
    is alive and idle. Effects signal access granted, denied, and
    procedure steps. Controlled locally by procedures and remotely
    by JSON commands from the NiceGUI dashboard.

Methods:
    * start()                  - boot confirmation, starts screensaver
    * start_screensaver()      - enable and launch rainbow loop
    * stop_screensaver()       - stop loop and turn strip dark
    * blink_color_async()      - blink N times with chosen color (non-blocking)
    * blink_green_three_times_async() - shorthand for access granted blink
    * blink_red_three_times_async()   - shorthand for access denied blink
    * tail_circular_async()    - async chasing tail effect (non-blocking)
    * tail_circular()          - blocking tail effect (use at procedure end only)
    * fill()                   - set all LEDs to one color immediately
    * turn_off()               - set all LEDs to black immediately
"""

import uasyncio as asyncio
from machine import Pin
import neopixel
import time


class LedStrip:

    # Safety brightness cap - prevents power spikes when running on USB
    MAX_BRIGHTNESS = 0.35

    # ------------------------------------------------------------
    # Init - create NeoPixel driver and set initial state
    # ------------------------------------------------------------

    def __init__(self, led_count=50, brightness=0.20, color_order="RGB"):
        # GPIO pin the data line of the strip is connected to
        self.data_pin = 14

        self.led_count   = int(led_count)
        self.color_order = color_order

        # Start brightness at 0 then apply via set_brightness so clamping runs
        self.brightness = 0.0
        self.set_brightness(brightness)

        # screensaver_task holds the running asyncio task so we can cancel it
        self.screensaver_task    = None

        # screensaver_enabled stays True even while an effect is running
        # so resume_screensaver_utility() knows whether to restart the loop
        self.screensaver_enabled = False

        # Create the NeoPixel driver for the strip
        self.pixels = neopixel.NeoPixel(Pin(self.data_pin, Pin.OUT), self.led_count)

        # Make sure strip starts dark - no leftover state from previous run
        self.turn_off()

    # ------------------------------------------------------------
    # Boot confirmation - announces LED strip then starts screensaver
    # ------------------------------------------------------------

    def start(self, oled=None):
        # Print to console and show boot message on OLED for 3 seconds
        print("[LED] started - screensaver on")
        if oled:
            oled.show_three_lines("LED STRIP", "STARTED", "OK")
            time.sleep_ms(3000)

        # Screensaver is the default idle visual - start it right away
        self.start_screensaver()

    # ------------------------------------------------------------
    # Brightness helpers - applied to every pixel write
    # ------------------------------------------------------------

    def set_brightness(self, brightness):
        # Clamp brightness between 0.0 and MAX_BRIGHTNESS before storing
        self.brightness = max(0.0, min(float(brightness), self.MAX_BRIGHTNESS))

    def apply_brightness_utility(self, r, g, b):
        # Scale raw RGB values down by the current brightness factor
        s = self.brightness
        return (int(r * s), int(g * s), int(b * s))

    def apply_color_order_utility(self, r, g, b):
        # Reorder channels to match the physical strip wiring (WS2812 is often GRB)
        return (g, r, b) if self.color_order == "GRB" else (r, g, b)

    def set_pixel_utility(self, index, r, g, b):
        # Write one pixel with brightness scaling and color order applied
        if 0 <= index < self.led_count:
            r2, g2, b2 = self.apply_brightness_utility(r, g, b)
            self.pixels[index] = self.apply_color_order_utility(r2, g2, b2)

    def show(self):
        # Push the pixel buffer to the physical strip
        self.pixels.write()

    # ------------------------------------------------------------
    # Basic fill and clear
    # ------------------------------------------------------------

    def fill(self, r, g, b):
        # Set every LED to the same color and push to strip immediately
        for i in range(self.led_count):
            self.set_pixel_utility(i, r, g, b)
        self.show()

    def turn_off(self):
        # Set every LED to black (off) and push to strip immediately
        for i in range(self.led_count):
            self.pixels[i] = (0, 0, 0)
        self.show()

    # ------------------------------------------------------------
    # HSV to RGB conversion - used by screensaver for smooth color rotation
    # Pure integer math - no floats, no math module needed
    # h = hue 0-359, s = saturation 0-255, v = brightness 0-255
    # ------------------------------------------------------------

    def hsv_to_rgb_utility(self, h, s, v):
        # Achromatic case - no color, just grey at the given brightness
        if s == 0:
            return (v, v, v)

        h, s, v = int(h) % 360, int(s), int(v)

        # Which 60-degree sector of the color wheel we are in
        i = h // 60
        f = h % 60  # how far into that sector (0-59)

        # Pre-calculate the three transition values
        p = (v * (255 - s)) // 255
        q = (v * (255 - (s * f) // 60)) // 255
        t = (v * (255 - (s * (60 - f)) // 60)) // 255

        if i == 0: return (v, t, p)
        if i == 1: return (q, v, p)
        if i == 2: return (p, v, t)
        if i == 3: return (p, q, v)
        if i == 4: return (t, p, v)
        return     (v, p, q)

    # ------------------------------------------------------------
    # Screensaver - rainbow tail that runs forever as a background task
    # start_screensaver() and stop_screensaver() control the lifecycle.
    # pause/resume utilities are used internally by effects.
    # ------------------------------------------------------------

    def start_screensaver(self):
        # Set enabled flag and launch the loop if it is not already running
        self.screensaver_enabled = True
        if self.screensaver_task is None:
            self.screensaver_task = asyncio.create_task(self.screensaver_loop_async())

    def stop_screensaver(self):
        # Disable screensaver permanently - effects will NOT restart it after stop
        self.screensaver_enabled = False
        if self.screensaver_task is not None:
            self.screensaver_task.cancel()
            self.screensaver_task = None
        self.turn_off()

    def pause_screensaver_utility(self):
        # Cancel the running task but keep enabled=True so resume can restart it
        if self.screensaver_task is not None:
            self.screensaver_task.cancel()
            self.screensaver_task = None

    def resume_screensaver_utility(self):
        # Restart the loop only if screensaver was enabled before the effect ran
        if self.screensaver_enabled and self.screensaver_task is None:
            self.screensaver_task = asyncio.create_task(self.screensaver_loop_async())

    async def screensaver_loop_2_async(self):
        # Rainbow tail chase - 5 LED tail with fading brightness rotates around strip
        tail_strength = [255, 140, 70, 35, 15]  # brightness at each tail position
        hue  = 0   # current color on the wheel (0-359)
        step = 0   # which LED is currently the head of the tail

        while True:
            # Clear all pixels for this frame
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            # Get the RGB color for the current hue position
            r, g, b = self.hsv_to_rgb_utility(hue, 255, 180)

            # Head wraps around when it reaches the end of the strip
            head = step % self.led_count

            # Draw 5 pixels - head at full strength fading toward the tail
            for t in range(5):
                pos = (head - t) % self.led_count
                s   = tail_strength[t]
                self.set_pixel_utility(pos, (r * s) // 255, (g * s) // 255, (b * s) // 255)

            self.show()

            # Advance hue slowly for smooth color transition over time
            hue  = (hue + 1) % 360
            step = (step + 1) % self.led_count

            # Yield so MQTT, RFID, and reed tasks keep running between frames
            await asyncio.sleep_ms(40)
            
    async def screensaver_loop_async(self):
        # Two-LED rainbow slide - adjacent pair steps one LED at a time around the strip
        # Head and tail are always neighbors, color rotates through full hue spectrum
        hue  = 0
        head = 0  # the leading LED of the pair

        while True:
            # Clear all LEDs for this frame
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            # Get current color from hue wheel
            r, g, b = self.hsv_to_rgb_utility(hue, 255, 200)

            # Draw head at full brightness, tail one step behind at half
            self.set_pixel_utility(head, r, g, b)
            self.set_pixel_utility((head - 1) % self.led_count, r // 2, g // 2, b // 2)

            self.show()

            # Step head forward one LED per frame
            head = (head + 1) % self.led_count

            # Advance hue slowly - full cycle completes after 360 steps
            hue = (hue + 1) % 360

            await asyncio.sleep_ms(40)
    # ------------------------------------------------------------
    # Blink effects - non-blocking, auto-pause and resume screensaver
    # ------------------------------------------------------------

    async def blink_color_async(self, r, g, b, times=3, on_ms=180, off_ms=180):
        # Pause screensaver, blink N times with the given color, then restore
        self.pause_screensaver_utility()

        for _ in range(int(times)):
            self.fill(r, g, b)
            await asyncio.sleep_ms(int(on_ms))
            self.turn_off()
            await asyncio.sleep_ms(int(off_ms))

        # Restart screensaver only if it was enabled before this blink
        self.resume_screensaver_utility()

    async def blink_green_three_times_async(self):
        # Shorthand for access granted visual feedback
        await self.blink_color_async(0, 255, 0, times=3)

    async def blink_red_three_times_async(self):
        # Shorthand for access denied visual feedback
        await self.blink_color_async(255, 0, 0, times=3)

    # ------------------------------------------------------------
    # Tail effects - chasing tail animation around the strip
    # Async version is non-blocking. Sync version blocks intentionally.
    # ------------------------------------------------------------

    async def tail_circular_async(self, cycles=2, delay_ms=40, r=255, g=0, b=0):
        # Non-blocking tail animation - pauses screensaver during, resumes after
        self.pause_screensaver_utility()
        tail_strength = [255, 140, 70, 35, 15]

        for step in range(self.led_count * int(cycles)):
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            head = step % self.led_count
            for t in range(5):
                pos = (head - t) % self.led_count
                s   = tail_strength[t]
                self.set_pixel_utility(pos, (r * s) // 255, (g * s) // 255, (b * s) // 255)

            self.show()
            await asyncio.sleep_ms(int(delay_ms))

        self.turn_off()
        self.resume_screensaver_utility()

    def tail_circular(self, cycles=2, delay_ms=40, r=0, g=0, b=255):
        # BLOCKING tail - freezes the event loop intentionally
        # Only use this at the very end of a procedure as a "flow finished" signal
        self.pause_screensaver_utility()
        tail_strength = [255, 140, 70, 35, 15]

        for step in range(self.led_count * int(cycles)):
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            head = step % self.led_count
            for t in range(5):
                pos = (head - t) % self.led_count
                s   = tail_strength[t]
                self.set_pixel_utility(pos, (r * s) // 255, (g * s) // 255, (b * s) // 255)

            self.show()
            time.sleep_ms(int(delay_ms))

        self.turn_off()

        # create_task is safe to call from sync context - restarts screensaver loop
        self.resume_screensaver_utility()