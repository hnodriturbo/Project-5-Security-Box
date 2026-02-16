"""
OLED DISPLAY NOTES (128x64)

Resolution and coordinates:
- Screen is 128 pixels wide and 64 pixels tall.
- (0, 0) is the top-left corner.
- X increases left → right (0 to 127)
- Y increases top → bottom (0 to 63)

Text rendering:
- Built-in MicroPython font is 8x8 pixels.
- Text width in pixels = len(text) * 8
- Text height is always 8 pixels.

Layout idea in this simplified version:
- show_status() vertically centers 1–3 lines automatically.
- draw_progress() draws a bar near the bottom.
"""

# classes/oled_screen_class.py
# Simple OLED helper for SPI SSD1306/SSD1309 screens on ESP32-S3.
# Contains basic layout helpers + simple animations (cleaner structure).

import time
from machine import Pin, SPI
from ssd1306.ssd1306 import SSD1306_SPI


class OledScreen:
    # Initialize SPI bus + OLED driver and store layout settings.
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
        self.width = width
        self.height = height

        # Store font size used by MicroPython text()
        self.font_width = 8
        self.font_height = 8

        # Create SPI bus for OLED communication (write-only SPI)
        spi = SPI(
            spi_id,
            baudrate=baudrate,
            polarity=0,
            phase=0,
            sck=Pin(sck),
            mosi=Pin(mosi),
            miso=None,
        )

        # Create OLED driver instance (control pins required for SPI OLED)
        self.oled = SSD1306_SPI(
            width,
            height,
            spi,
            dc=Pin(dc, Pin.OUT),
            res=Pin(res, Pin.OUT),
            cs=Pin(cs, Pin.OUT),
        )

        # Start with a clean screen so startup is visually confirmed
        self.clear()

    # Clear entire display buffer and push to screen.
    def clear(self):
        self.oled.fill(0)
        self.oled.show()

    # Return X coordinate that centers text horizontally.
    def _center_x(self, text):
        # Calculate total text width in pixels
        text_width_px = len(text) * self.font_width

        # Center relative to screen width
        x = (self.width - text_width_px) // 2

        # Clamp to prevent negative starting position
        return 0 if x < 0 else x

    # Return Y coordinate that vertically centers a block of lines.
    def _center_y(self, line_count, gap=2):
        # Total height of text block including gaps
        block_height = (line_count * self.font_height) + ((line_count - 1) * gap)

        # Center block vertically
        y = (self.height - block_height) // 2

        # Clamp to prevent drawing above screen
        return 0 if y < 0 else y

    # Draw one line of text and optionally clear before drawing.
    def draw_text(self, text, x=0, y=0, clear_first=False):
        # Replace previous frame if requested
        if clear_first:
            self.oled.fill(0)

        # Draw text into framebuffer and flush
        self.oled.text(text, x, y)
        self.oled.show()

    # Draw a single centered line.
    def draw_center(self, text, y=28, clear_first=False):
        # Use horizontal centering helper
        self.draw_text(text, x=self._center_x(text), y=y, clear_first=clear_first)

    # Show up to three centered lines as one complete screen.
    def show_status(self, title, line1="", line2="", gap=2):
        # Collect only lines that contain text
        lines = [title]
        if line1:
            lines.append(line1)
        if line2:
            lines.append(line2)

        # Clear once so entire screen updates as one frame
        self.oled.fill(0)

        # Compute vertical start position for block
        start_y = self._center_y(len(lines), gap=gap)

        # Draw each line centered with consistent spacing
        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + gap))
            self.oled.text(text, self._center_x(text), y)

        # Flush once at end
        self.oled.show()

    # Draw a simple progress bar at bottom of screen (0–100%).
    def draw_progress(self, percent, y=54, height=8):
        # Clamp percent to safe range
        if percent < 0:
            percent = 0
        if percent > 100:
            percent = 100

        # Draw outline rectangle
        self.oled.rect(0, y, self.width, height, 1)

        # Calculate filled width inside border
        fill_width = int((self.width - 2) * (percent / 100))

        # Fill interior if progress > 0
        if fill_width > 0:
            self.oled.fill_rect(1, y + 1, fill_width, height - 2, 1)

        # Push update to screen
        self.oled.show()

    # Blink invert display to visually confirm OLED is alive.
    def blink_invert(self, times=4, delay_ms=200):
        # Toggle invert state without redrawing text
        for _ in range(times):
            self.oled.invert(1)
            time.sleep_ms(delay_ms)
            self.oled.invert(0)
            time.sleep_ms(delay_ms)

    # Scroll text from right edge to left edge.
    def marquee(self, text, y=None, speed_ms=25, loops=1):
        # Default vertical position is centered single line
        if y is None:
            y = self._center_y(1)

        # Compute total pixel width of text
        text_width = len(text) * self.font_width

        # Move from right side to fully off left
        for _ in range(loops):
            for x in range(self.width, -text_width - 1, -1):
                self.oled.fill(0)
                self.oled.text(text, x, y)
                self.oled.show()
                time.sleep_ms(speed_ms)

    # Slide text in from right until it reaches centered position.
    def slide_in_center(self, text, y=None, speed_ms=12):
        # Default Y is vertical center
        if y is None:
            y = self._center_y(1)

        # Target centered X position
        target_x = self._center_x(text)

        # Start fully off screen on right and move left
        for x in range(self.width, target_x - 1, -1):
            self.oled.fill(0)
            self.oled.text(text, x, y)
            self.oled.show()
            time.sleep_ms(speed_ms)
