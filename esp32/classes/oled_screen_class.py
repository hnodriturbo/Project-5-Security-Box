"""
classes/oled_screen_class.py - OLED helper + animations (merged)

Purpose:
- Provide a small, predictable OLED API for the Security Box:
  - clear(), show_status(), show_three_lines()
  - draw_progress()
  - blink_invert(), marquee(), slide_in_center()
  - animate_progress(), bounce_dot()
  - Async wrappers: show_status_async(), show_three_lines_async(), clear_async()
  - screensaver_loop() — runs as a background asyncio task

Notes:
- Designed for 128x64 OLEDs using SSD1306/SSD1309 SPI driver.
- Uses the built-in MicroPython 8x8 font for simple layout math.
- Blocking animations (time.sleep_ms) are kept for boot-time demos only.
- Async wrappers yield to the event loop so other tasks keep running.
"""

import time
import uasyncio as asyncio
from machine import Pin, SPI
from ssd1306.ssd1306 import SSD1306_SPI


class OledScreen:
    # -------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------

    def __init__(
        self,
        spi_id=1,
        sck=36,
        mosi=35,
        dc=11,
        res=10,
        cs=9,
        width=128,
        height=64,
        baudrate=1_000_000,
    ):
        # Store display size so layout math never hardcodes 128x64
        self.width = int(width)
        self.height = int(height)

        # Used by screensaver_loop() and mark_activity() to track idle time
        self.last_activity_utility = asyncio.ticks_ms()

        # Store font size used by MicroPython text()
        self.font_width = 8
        self.font_height = 8

        # Create SPI bus for OLED communication (write-only SPI)
        spi = SPI(
            spi_id,
            baudrate=int(baudrate),
            polarity=0,
            phase=0,
            sck=Pin(sck),
            mosi=Pin(mosi),
            miso=None,
        )

        # Create OLED driver instance (control pins required for SPI OLED)
        self.oled = SSD1306_SPI(
            self.width,
            self.height,
            spi,
            dc=Pin(dc, Pin.OUT),
            res=Pin(res, Pin.OUT),
            cs=Pin(cs, Pin.OUT),
        )

        # Start with a clean screen so startup is visually confirmed
        self.clear()

    # -------------------------------------------------------------------
    # Basic drawing helpers
    # -------------------------------------------------------------------

    def clear(self):
        # Clear entire display buffer and push to screen
        self.oled.fill(0)
        self.oled.show()

    def center_x_utility(self, text):
        # Return X coordinate that centers text horizontally
        text_width_px = len(text) * self.font_width
        x = (self.width - text_width_px) // 2
        return 0 if x < 0 else x

    def center_y_utility(self, line_count, gap=2):
        # Return Y coordinate that vertically centers a block of lines
        line_count = int(line_count)
        gap = int(gap)

        block_height = (line_count * self.font_height) + ((line_count - 1) * gap)
        y = (self.height - block_height) // 2
        return 0 if y < 0 else y

    def draw_text(self, text, x=0, y=0, clear_first=False):
        # Draw one line of text and optionally clear before drawing
        if clear_first:
            self.oled.fill(0)

        self.oled.text(text, int(x), int(y))
        self.oled.show()

    def draw_center(self, text, y=28, clear_first=False):
        # Draw a single centered line
        self.draw_text(text, x=self.center_x_utility(text), y=y, clear_first=clear_first)

    # -------------------------------------------------------------------
    # Screen layouts used by the project
    # -------------------------------------------------------------------

    def show_status(self, title, line1="", line2="", gap=2):
        # Show up to three centered lines as one complete screen
        lines = [title]
        if line1:
            lines.append(line1)
        if line2:
            lines.append(line2)

        self.oled.fill(0)

        start_y = self.center_y_utility(len(lines), gap=gap)
        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + int(gap)))
            self.oled.text(text, self.center_x_utility(text), y)

        self.oled.show()

    def show_three_lines(self, line1, line2, line3, gap=2):
        # Show exactly three centered lines (used for the idle prompt screen)
        lines = [line1 or "", line2 or "", line3 or ""]

        self.oled.fill(0)

        start_y = self.center_y_utility(3, gap=gap)
        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + int(gap)))
            self.oled.text(text, self.center_x_utility(text), y)

        self.oled.show()

    # -------------------------------------------------------------------
    # Progress bar helpers
    # -------------------------------------------------------------------

    def draw_progress(self, percent, y=54, height=8):
        # Draw a simple progress bar at bottom of screen (0–100%)
        percent = int(percent)
        y = int(y)
        height = int(height)

        if percent < 0:
            percent = 0
        if percent > 100:
            percent = 100

        self.oled.rect(0, y, self.width, height, 1)

        fill_width = int((self.width - 2) * (percent / 100))
        if fill_width > 0:
            self.oled.fill_rect(1, y + 1, fill_width, height - 2, 1)

        self.oled.show()

    def animate_progress(self, step=10, delay_ms=120, y=54, height=8):
        # Animate a progress bar from 0 to 100 (demo loading effect)
        step = int(step)
        delay_ms = int(delay_ms)

        self.oled.fill(0)
        self.oled.show()

        for percent in range(0, 101, step):
            self.oled.fill(0)
            self.draw_progress(percent, y=y, height=height)
            time.sleep_ms(delay_ms)

    # -------------------------------------------------------------------
    # Simple animations (blocking)
    # -------------------------------------------------------------------

    def blink_invert(self, times=4, delay_ms=200):
        # Blink invert display to visually confirm OLED is alive
        times = int(times)
        delay_ms = int(delay_ms)

        for _ in range(times):
            self.oled.invert(1)
            time.sleep_ms(delay_ms)
            self.oled.invert(0)
            time.sleep_ms(delay_ms)

    def marquee(self, text, y=None, speed_ms=25, loops=1, loop_count=None):
        # Scroll text from right edge to left edge
        # Accept both "loops" and "loop_count" so older tester code keeps working
        if loop_count is not None:
            loops = loop_count

        loops = int(loops)
        speed_ms = int(speed_ms)

        if y is None:
            y = self.center_y_utility(1)

        text_width = len(text) * self.font_width

        for _ in range(loops):
            for x in range(self.width, -text_width - 1, -1):
                self.oled.fill(0)
                self.oled.text(text, x, int(y))
                self.oled.show()
                time.sleep_ms(speed_ms)

    def slide_in_center(self, text, y=None, speed_ms=12):
        # Slide text in from right until it reaches centered position
        speed_ms = int(speed_ms)

        if y is None:
            y = self.center_y_utility(1)

        target_x = self.center_x_utility(text)

        for x in range(self.width, target_x - 1, -1):
            self.oled.fill(0)
            self.oled.text(text, x, int(y))
            self.oled.show()
            time.sleep_ms(speed_ms)

    def bounce_dot(self, y=32, speed_ms=15, loops=2):
        # Animate a tiny dot bouncing left-right (cheap refresh test)
        y = int(y)
        speed_ms = int(speed_ms)
        loops = int(loops)

        dot_size = 2

        for _ in range(loops):
            for x in range(0, self.width - dot_size):
                self.oled.fill(0)
                self.oled.fill_rect(x, y, dot_size, dot_size, 1)
                self.oled.show()
                time.sleep_ms(speed_ms)

            for x in range(self.width - dot_size - 1, -1, -1):
                self.oled.fill(0)
                self.oled.fill_rect(x, y, dot_size, dot_size, 1)
                self.oled.show()
                time.sleep_ms(speed_ms)

    # -------------------------------------------------------------------
    # Async wrappers — use these from asyncio tasks (controller, etc.)
    # -------------------------------------------------------------------

    async def show_status_async(self, title, line1="", line2=""):
        """Call show_status() then yield so other tasks keep running."""
        self.show_status(title, line1, line2)
        await asyncio.sleep_ms(0)

    async def show_three_lines_async(self, line1, line2, line3):
        """Call show_three_lines() then yield."""
        self.show_three_lines(line1, line2, line3)
        await asyncio.sleep_ms(0)

    async def clear_async(self):
        """Call clear() then yield."""
        self.clear()
        await asyncio.sleep_ms(0)

    def mark_activity(self):
        """
        Reset the idle timer. Call this whenever something happens on the box
        (RFID scan, remote command, etc.) to prevent the screensaver from
        activating during active use.
        """
        self.last_activity_utility = asyncio.ticks_ms()

    async def screensaver_loop(self, idle_ms=60000):
        """
        Run forever as a background asyncio task.

        After idle_ms milliseconds of inactivity (no mark_activity() call),
        shows a static "SECURITY BOX READY" screen.
        Returns to normal as soon as mark_activity() is called by the controller.

        Notes:
            - Checks every 500ms — low CPU cost.
            - Does NOT override show_status_async() calls; it only sets
              a flag. The controller always calls mark_activity() before
              any real event, which resets the timer and suppresses the
              screensaver for the duration of the event.
        """
        screensaver_active = False

        while True:
            elapsed = asyncio.ticks_diff(asyncio.ticks_ms(), self.last_activity_utility)

            if elapsed >= idle_ms and not screensaver_active:
                # Gone idle — show screensaver
                screensaver_active = True
                self.show_status("SECURITY", "BOX", "READY")

            elif elapsed < idle_ms and screensaver_active:
                # Activity resumed — clear screensaver flag
                # Controller will write the correct state on the next event
                screensaver_active = False

            await asyncio.sleep_ms(500)