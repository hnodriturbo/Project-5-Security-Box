"""
oled_screen.py

SSD1306 OLED display driver for the Security Box.
Handles all screen output over SPI using the SSD1306_SPI driver.
No message queue - all display calls render immediately.
log_now() is the only method that holds the screen for a set duration,
used in procedures where the operator must read the screen before
the next step in the flow continues.

Role in the box:
    First hardware initialized at boot. Every other class and
    procedure uses this to show status on the physical 128x64 screen.

Methods:
    * start()            - show boot confirmation on screen
    * show_three_lines() - render 3 centered lines immediately (sync)
    * log_now()          - show lines and pause caller for hold_ms (async)
    * set_screensaver()  - update the idle screen text
    * show_main_mode()   - return to idle screen immediately
"""

import uasyncio as asyncio
from machine import Pin, SPI
from ssd1306.ssd1306 import SSD1306_SPI


class OledScreen:

    # ------------------------------------------------------------
    # Init - configure SPI bus and build the OLED driver
    # All pin numbers match the ESP32-S3 wiring for this project
    # ------------------------------------------------------------

    def __init__(
        self,
        spi_id   = 1,
        sck      = 36,
        mosi     = 35,
        dc       = 11,
        res      = 10,
        cs       = 9,
        width    = 128,
        height   = 64,
        baudrate = 1_000_000,
    ):
        # Screen geometry used for centering calculations
        self.width  = int(width)
        self.height = int(height)

        # Built-in MicroPython font is always 8x8 pixels per character
        self.font_width  = 8
        self.font_height = 8

        # Default idle screen text - updated via set_screensaver()
        self.screensaver_lines = ("SECURITY", "BOX", "READY")

        # Build the SPI bus - OLED is the only device on this bus
        spi = SPI(
            int(spi_id),
            baudrate = int(baudrate),
            polarity = 0,
            phase    = 0,
            sck      = Pin(int(sck)),
            mosi     = Pin(int(mosi)),
            miso     = None,
        )

        # Build the SSD1306 driver - wires SPI bus to the control pins
        self.oled = SSD1306_SPI(
            self.width,
            self.height,
            spi,
            dc  = Pin(int(dc),  Pin.OUT),
            res = Pin(int(res), Pin.OUT),
            cs  = Pin(int(cs),  Pin.OUT),
        )

        # Start with a blank frame so no garbage pixels show at boot
        self.clear()

    # ------------------------------------------------------------
    # Boot confirmation - OLED announces itself on its own screen
    # ------------------------------------------------------------

    def start(self):
        # Print to console and show boot message directly on screen
        print("[OLED] started")
        self.show_three_lines("OLED", "STARTED", "OK")

    # ------------------------------------------------------------
    # Layout helpers - pixel math for centering text on screen
    # ------------------------------------------------------------

    def center_x_utility(self, text):
        # X offset so the given string appears horizontally centered on screen
        text_width = len(str(text)) * self.font_width
        return max(0, (self.width - text_width) // 2)

    def center_y_utility(self, line_count, gap=2):
        # Y offset so a block of N lines appears vertically centered on screen
        block_height = line_count * self.font_height + (line_count - 1) * int(gap)
        return max(0, (self.height - block_height) // 2)

    # ------------------------------------------------------------
    # Core display - wipe screen and render 3 lines centered
    # ------------------------------------------------------------

    def clear(self):
        # Wipe the entire screen to black - safe to call before asyncio starts
        self.oled.fill(0)
        self.oled.show()

    def show_three_lines(self, line1, line2="", line3="", gap=2):
        # Render 3 lines centered on screen - replaces whatever is currently shown
        lines = [str(line1 or ""), str(line2 or ""), str(line3 or "")]

        # Clear before drawing so previous content does not bleed through
        self.oled.fill(0)

        # Start y so the 3-line block sits in the vertical center of the display
        y0 = self.center_y_utility(3, gap)

        for i, text in enumerate(lines):
            y = y0 + i * (self.font_height + int(gap))
            self.oled.text(text, self.center_x_utility(text), y)

        self.oled.show()

    # ------------------------------------------------------------
    # Blocking display - shows text and pauses the caller for hold_ms
    # Used in unlock procedure steps where each message must be read
    # before the next step starts. Other async tasks still run during wait.
    # ------------------------------------------------------------

    async def log_now(self, line1, line2="", line3="", hold_ms=3000):
        # Show lines immediately then sleep hold_ms before returning to caller
        self.show_three_lines(str(line1), str(line2), str(line3))
        await asyncio.sleep_ms(int(hold_ms))

    # ------------------------------------------------------------
    # Idle screen - the text shown when the system is waiting for input
    # ------------------------------------------------------------

    def set_screensaver(self, lines):
        # Store new idle screen text - shown every time show_main_mode() is called
        if isinstance(lines, (tuple, list)) and len(lines) >= 3:
            self.screensaver_lines = (str(lines[0]), str(lines[1]), str(lines[2]))

    def show_main_mode(self):
        # Return display to idle screen - called at end of every procedure and callback
        self.show_three_lines(*self.screensaver_lines)