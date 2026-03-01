"""
classes/oled_screen_class.py - OLED helper (non-blocking, async-friendly)

Purpose:
- Provide a predictable OLED API for the Security Drawer Box.
- Designed to run alongside MQTT, RFID, solenoid and reed switch tasks.
- No blocking time.sleep_ms() calls in loops.
- All longer visual effects use async + await so the system never freezes.

System Architecture Concept:
- MQTT loop runs forever.
- RFID loop runs forever.
- Screensaver loop runs forever.
- All cooperate through uasyncio.
- This class NEVER blocks the event loop.
"""

import time
import uasyncio as asyncio
from machine import Pin, SPI
from ssd1306.ssd1306 import SSD1306_SPI


class OledScreen:

    # -------------------------------------------------------------------
    # SETUP PHASE (runs once at startup)
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
        # Store display size so all layout math adapts automatically
        self.width = int(width)
        self.height = int(height)

        # Built-in MicroPython font size (text() is 8x8)
        self.font_width = 8
        self.font_height = 8

        # Create SPI bus for OLED communication
        # This is write-only SPI (miso=None)
        spi = SPI(
            spi_id,
            baudrate=int(baudrate),
            polarity=0,
            phase=0,
            sck=Pin(sck),
            mosi=Pin(mosi),
            miso=None,
        )

        # Create OLED driver instance
        self.oled = SSD1306_SPI(
            self.width,
            self.height,
            spi,
            dc=Pin(dc, Pin.OUT),
            res=Pin(res, Pin.OUT),
            cs=Pin(cs, Pin.OUT),
        )

        # -----------------------------
        # SCREENSAVER STATE
        # -----------------------------
        # These values control idle behavior of the screen.
        self.screensaver_lines = ("ENTER PIN", "OR", "SCAN CARD")
        self.screensaver_after_ms = 6000

        # This tracks last time something happened (RFID, MQTT, etc.)
        self.last_activity_ms = time.ticks_ms()

        # Task handle for the background idle loop
        self.screensaver_task = None

        # Master enable/disable flag
        self.screensaver_enabled = True

        # Start with clean display
        self.clear()

    # -------------------------------------------------------------------
    # ACTIVITY TRACKING
    # -------------------------------------------------------------------

    def mark_activity(self):
        """
        Called whenever something meaningful happens.

        Why this matters:
        - Prevents screensaver from interrupting live information.
        - Should be called on:
            - RFID scan
            - MQTT message received
            - Drawer open/close
            - Remote command
        """
        self.last_activity_ms = time.ticks_ms()

    def set_screensaver(self, lines=None, after_ms=None, enabled=None):
        """
        Allows NiceGUI or internal logic to modify idle behavior live.

        This is how MQTT JSON can control the OLED.
        """

        # Update text shown during idle
        if lines is not None:
            self.screensaver_lines = (
                str(lines[0]),
                str(lines[1]),
                str(lines[2]),
            )

        # Update inactivity timeout
        if after_ms is not None:
            self.screensaver_after_ms = int(after_ms)

        # Enable/disable idle mode completely
        if enabled is not None:
            self.screensaver_enabled = bool(enabled)

        # Any change counts as activity
        self.mark_activity()

    def start_screensaver(self):
        """
        Starts background idle monitoring.

        Important:
        - Only start once.
        - This runs forever in background.
        - It never blocks other tasks.
        """
        if self.screensaver_task is None:
            self.screensaver_task = asyncio.create_task(self.screensaver_loop())

    async def screensaver_loop(self):
        """
        This runs forever.

        It checks:
        - Has there been inactivity longer than threshold?
        If yes:
        - Show idle screen.

        Uses await asyncio.sleep_ms() so it never blocks MQTT/RFID.
        """
        while True:

            if self.screensaver_enabled:

                # Calculate time since last activity
                elapsed = time.ticks_diff(
                    time.ticks_ms(),
                    self.last_activity_ms
                )

                # If exceeded threshold -> show idle screen
                if elapsed >= self.screensaver_after_ms:
                    await self.show_screensaver_now_async()

                    # Small pause to avoid redraw spam
                    await asyncio.sleep_ms(300)

            # Loop check interval
            await asyncio.sleep_ms(100)

    async def show_screensaver_now_async(self):
        """
        Immediately draw the configured idle screen.
        """
        await self.show_three_lines_async(
            self.screensaver_lines[0],
            self.screensaver_lines[1],
            self.screensaver_lines[2],
        )

    # -------------------------------------------------------------------
    # BASIC DRAWING
    # -------------------------------------------------------------------

    def clear(self):
        """
        Clear full screen buffer and push to display.
        Fast operation, safe to call anytime.
        """
        self.oled.fill(0)
        self.oled.show()

    def center_x(self, text):
        """
        Compute horizontal centering based on font width.
        """
        text_width_px = len(text) * self.font_width
        x = (self.width - text_width_px) // 2
        return 0 if x < 0 else x

    def center_y(self, line_count, gap=2):
        """
        Compute vertical centering for multi-line blocks.
        """
        block_height = (
            (line_count * self.font_height)
            + ((line_count - 1) * gap)
        )
        y = (self.height - block_height) // 2
        return 0 if y < 0 else y

    # -------------------------------------------------------------------
    # SCREEN LAYOUTS
    # -------------------------------------------------------------------

    def show_status(self, title, line1="", line2="", gap=2):
        """
        Draw 1–3 centered lines.

        This is the main layout used for:
        - ACCESS ALLOWED
        - ACCESS DENIED
        - REMOTE UNLOCK
        - FAULT
        """

        lines = [str(title)]
        if line1:
            lines.append(str(line1))
        if line2:
            lines.append(str(line2))

        self.oled.fill(0)

        start_y = self.center_y(len(lines), gap=gap)

        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + gap))
            self.oled.text(text, self.center_x(text), int(y))

        self.oled.show()

    def show_three_lines(self, line1, line2, line3, gap=2):
        """
        Strict 3-line layout.
        Used mainly for idle screen.
        """

        lines = [str(line1), str(line2), str(line3)]

        self.oled.fill(0)
        start_y = self.center_y(3, gap=gap)

        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + gap))
            self.oled.text(text, self.center_x(text), int(y))

        self.oled.show()

    # -------------------------------------------------------------------
    # ASYNC WRAPPERS
    # -------------------------------------------------------------------

    async def show_status_async(self, title, line1="", line2=""):
        """
        Async-safe wrapper.

        Why await sleep(0)?
        - It yields control back to the event loop.
        - Ensures MQTT/RFID continue running.
        """
        self.mark_activity()
        self.show_status(title, line1, line2)
        await asyncio.sleep_ms(0)

    async def show_three_lines_async(self, line1, line2, line3):
        self.mark_activity()
        self.show_three_lines(line1, line2, line3)
        await asyncio.sleep_ms(0)

    async def clear_async(self):
        self.mark_activity()
        self.clear()
        await asyncio.sleep_ms(0)

    # -------------------------------------------------------------------
    # NON-BLOCKING ANIMATIONS
    # -------------------------------------------------------------------

    async def blink_invert_async(self, times=4, delay_ms=200):
        """
        Visual confirmation animation.

        Non-blocking:
        - Each step yields back to system.
        """
        self.mark_activity()

        for _ in range(times):
            self.oled.invert(1)
            await asyncio.sleep_ms(delay_ms)
            self.oled.invert(0)
            await asyncio.sleep_ms(delay_ms)

    async def marquee_async(self, text, y=None, speed_ms=25, loops=1):
        """
        Scroll text from right to left.

        Important:
        - Uses await sleep
        - Does NOT freeze MQTT/RFID
        """

        self.mark_activity()

        if y is None:
            y = self.center_y(1)

        text = str(text)
        text_width = len(text) * self.font_width

        for _ in range(loops):
            x = self.width
            while x >= (-text_width - 1):
                self.oled.fill(0)
                self.oled.text(text, int(x), int(y))
                self.oled.show()
                await asyncio.sleep_ms(speed_ms)
                x -= 1