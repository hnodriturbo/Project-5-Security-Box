"""
led_strip.py

WS2812 NeoPixel LED strip controller for the Security Box.
Controls 50 LEDs on GPIO14 using the MicroPython neopixel driver.

The pixel idle loop is the default idle state - automatically starts
at boot and resumes after every effect. Two idle animations are
available and switchable from the dashboard via set_idle_loop().

Role in the box:
    Visual feedback for all system events. Idle loop shows the box
    is alive and waiting. Effects signal access granted, denied, and
    procedure steps. Controlled locally by procedures and remotely
    by JSON commands from the NiceGUI dashboard.

Methods:
    * start()                         - boot confirmation, starts idle loop
    * start_idle_loop()               - enable and launch active idle animation
    * stop_idle_loop()                - stop loop and turn strip dark
    * set_idle_loop()                 - switch between idle animations (1 or 2)
    * pixel_idle_loop_async()         - mode 1: shifting dots, single color per frame
    * pixel_idle_loop_2_async()       - mode 2: even/odd alternating full rainbow flash
    * idle_loop_slide_async()         - alt: two-LED rainbow slide around strip
    * idle_loop_tail_async()          - alt: five-LED rainbow tail chase
    * blink_color_async()             - blink N times with chosen color (non-blocking)
    * blink_green_three_times_async() - shorthand for access granted blink
    * blink_red_three_times_async()   - shorthand for access denied blink
    * tail_circular_async()           - async chasing tail effect (non-blocking)
    * tail_circular()                 - blocking tail effect (use at procedure end only)
    * fill()                          - set all LEDs to one color immediately
    * turn_off()                      - set all LEDs to black immediately
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

        # Holds the running asyncio task so we can cancel it when an effect runs
        self.idle_loop_task = None

        # Stays True even while an effect is running so resume knows to restart
        self.idle_loop_enabled = False

        # Tracks which idle animation runs - 1 or 2, switchable from dashboard
        self.idle_loop_mode = 1

        # Create the NeoPixel driver for the strip
        self.pixels = neopixel.NeoPixel(Pin(self.data_pin, Pin.OUT), self.led_count)

        # Make sure strip starts dark - no leftover state from previous run
        self.turn_off()

    # ------------------------------------------------------------
    # Boot confirmation - announces LED strip then starts idle loop
    # ------------------------------------------------------------

    def start(self, oled=None):
        # Print to console and show boot message on OLED for 3 seconds
        print("[LED] started - idle loop on")
        if oled:
            oled.show_three_lines("LED STRIP", "STARTED", "OK")
            time.sleep_ms(3000)

        # Idle loop is the default visual - start it right away
        self.start_idle_loop()

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
    # HSV to RGB conversion - used by idle loops for smooth color rotation
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
    # Idle loop lifecycle - start/stop own the on/off state
    # pause/resume are used internally by effects so the loop
    # always comes back automatically after every blink or tail
    # ------------------------------------------------------------

    def start_idle_loop(self):
        # Set enabled and launch the background task if not already running
        self.idle_loop_enabled = True
        if self.idle_loop_task is None:
            loop_method = self.pixel_idle_loop_async if self.idle_loop_mode == 1 else self.pixel_idle_loop_2_async
            self.idle_loop_task = asyncio.create_task(loop_method())

    def stop_idle_loop(self):
        # Disable permanently - effects will NOT restart the loop after this
        self.idle_loop_enabled = False
        if self.idle_loop_task is not None:
            self.idle_loop_task.cancel()
            self.idle_loop_task = None
        self.turn_off()

    def pause_idle_loop_utility(self):
        # Cancel the task but keep enabled=True so resume can restart it
        if self.idle_loop_task is not None:
            self.idle_loop_task.cancel()
            self.idle_loop_task = None

    def resume_idle_loop_utility(self):
        # Restart the loop only if it was enabled before the effect ran
        if self.idle_loop_enabled and self.idle_loop_task is None:
            loop_method = self.pixel_idle_loop_async if self.idle_loop_mode == 1 else self.pixel_idle_loop_2_async
            self.idle_loop_task = asyncio.create_task(loop_method())

    def set_idle_loop(self, mode):
        # Switch animation (1 = shifting dots, 2 = even/odd rainbow flash) and restart
        self.idle_loop_mode = mode
        self.pause_idle_loop_utility()
        self.resume_idle_loop_utility()

    # ------------------------------------------------------------
    # Idle animations - mode 1 and mode 2 are dashboard-switchable
    # Alt loops below are available but not wired to start/resume
    # ------------------------------------------------------------

    async def pixel_idle_loop_async(self):
        # Mode 1 - every other LED lit, offset shifts each frame = circular movement
        # Single color per frame, hue drifts slowly over full spectrum
        offset  = 0
        hue     = 0
        spacing = 2  # gap between lit LEDs - try 3 for a more open look

        while True:
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            r, g, b = self.hsv_to_rgb_utility(hue, 255, 200)

            # Light every Nth pixel starting from current offset
            for i in range(offset, self.led_count, spacing):
                self.set_pixel_utility(i, r, g, b)

            self.show()

            # Shift offset so lit pixels appear to move by one each frame
            offset = (offset + 1) % spacing
            hue    = (hue + 2) % 360

            await asyncio.sleep_ms(60)

    async def pixel_idle_loop_2_async(self):
        # Mode 2 - alternates between all even and all odd LEDs each frame
        # Full rainbow spread across lit LEDs, base hue rotates over time
        hue   = 0
        frame = 0  # 0 = even LEDs lit, 1 = odd LEDs lit

        while True:
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            # Each LED gets its own hue offset so the set shows a full rainbow
            for i in range(self.led_count):
                if i % 2 == frame:
                    led_hue = (hue + (i * 360 // self.led_count)) % 360
                    r, g, b = self.hsv_to_rgb_utility(led_hue, 255, 240)
                    self.set_pixel_utility(i, r, g, b)

            self.show()

            # Flip between even and odd each frame
            frame = 1 - frame
            hue   = (hue + 3) % 360

            await asyncio.sleep_ms(80)

    # ------------------------------------------------------------
    # Alternative idle animations - swap into start/resume if needed
    # ------------------------------------------------------------

    async def idle_loop_slide_async(self):
        # Two-LED rainbow slide - adjacent pair steps one LED at a time around the strip
        hue  = 0
        head = 0

        while True:
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            r, g, b = self.hsv_to_rgb_utility(hue, 255, 200)

            self.set_pixel_utility(head, r, g, b)
            self.set_pixel_utility((head - 1) % self.led_count, r // 2, g // 2, b // 2)

            self.show()

            head = (head + 1) % self.led_count
            hue  = (hue + 1) % 360

            await asyncio.sleep_ms(40)

    async def idle_loop_tail_async(self):
        # Five-LED rainbow tail chase - fading brightness behind the head
        tail_strength = [255, 140, 70, 35, 15]
        hue  = 0
        step = 0

        while True:
            for i in range(self.led_count):
                self.pixels[i] = (0, 0, 0)

            r, g, b = self.hsv_to_rgb_utility(hue, 255, 180)
            head = step % self.led_count

            for t in range(5):
                pos = (head - t) % self.led_count
                s   = tail_strength[t]
                self.set_pixel_utility(pos, (r * s) // 255, (g * s) // 255, (b * s) // 255)

            self.show()

            hue  = (hue + 1) % 360
            step = (step + 1) % self.led_count

            await asyncio.sleep_ms(40)

    # ------------------------------------------------------------
    # Blink effects - non-blocking, auto-pause and resume idle loop
    # ------------------------------------------------------------

    async def blink_color_async(self, r, g, b, times=3, on_ms=180, off_ms=180):
        # Pause idle loop, blink N times with the given color, then restore
        self.pause_idle_loop_utility()

        for _ in range(int(times)):
            self.fill(r, g, b)
            await asyncio.sleep_ms(int(on_ms))
            self.turn_off()
            await asyncio.sleep_ms(int(off_ms))

        # Restart idle loop only if it was enabled before this blink
        self.resume_idle_loop_utility()

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
        # Non-blocking tail animation - pauses idle loop during, resumes after
        self.pause_idle_loop_utility()
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
        self.resume_idle_loop_utility()

    def tail_circular(self, cycles=2, delay_ms=40, r=0, g=0, b=255):
        # BLOCKING tail - freezes the event loop intentionally
        # Only use this at the very end of a procedure as a "flow finished" signal
        self.pause_idle_loop_utility()
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

        # create_task is safe to call from sync context - restarts idle loop
        self.resume_idle_loop_utility()