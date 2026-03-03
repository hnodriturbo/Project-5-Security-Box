"""
classes/oled_screen_class.py - OLED helper with message queue

Purpose:
- Provide a small, predictable OLED API for the Security Box.
- Support two display modes:
    log_queued()  -> fire and forget, message waits its turn in a queue
    log_now()     -> caller awaits, screen shows immediately and holds

Queue behavior:
- Messages are processed one at a time in order.
- Each message holds for hold_ms before the next one shows.
- Code that calls log_queued() continues running immediately.
- The queue worker runs as a background task (start with start_queue_worker()).

Notes:
- No MQTT/RFID/solenoid imports here. Display logic only.
- No automatic time-based reverts. Procedures decide when to return to main mode.
"""

import uasyncio as asyncio
from machine import Pin, SPI
from ssd1306.ssd1306 import SSD1306_SPI


class OledScreen:
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
        # Store geometry for consistent layout
        self.width = int(width)
        self.height = int(height)

        # Font metrics for built-in MicroPython font
        self.font_width = 8
        self.font_height = 8

        # Main mode text (3 lines shown when system is idle)
        self.screensaver_lines = ("SECURITY", "BOX", "READY")

        # Message queue: list of (line1, line2, line3, hold_ms) tuples
        # log_queued() appends here, worker pops from front
        self.message_queue = []

        # Flag so we know if the worker task is already running
        self.queue_worker_running = False

        # Build SPI bus (OLED only)
        spi = SPI(
            int(spi_id),
            baudrate=int(baudrate),
            polarity=0,
            phase=0,
            sck=Pin(int(sck)),
            mosi=Pin(int(mosi)),
            miso=None,
        )

        # Build OLED driver (SSD1306/SSD1309 compatible)
        self.oled = SSD1306_SPI(
            self.width,
            self.height,
            spi,
            dc=Pin(int(dc), Pin.OUT),
            res=Pin(int(res), Pin.OUT),
            cs=Pin(int(cs), Pin.OUT),
        )

        # Start from a clean frame
        self.clear()

    # ------------------------------------------------------------
    # Layout helpers (internal calculations)
    # ------------------------------------------------------------

    def center_x_utility(self, text):
        # Calculate x position to center text horizontally
        text = str(text)
        text_width = len(text) * self.font_width
        x = (self.width - text_width) // 2
        return 0 if x < 0 else int(x)

    def center_y_utility(self, line_count, gap=2):
        # Calculate y start position to center a block of N lines vertically
        line_count = int(line_count)
        gap = int(gap)
        block_height = (line_count * self.font_height) + ((line_count - 1) * gap)
        y = (self.height - block_height) // 2
        return 0 if y < 0 else int(y)

    # ------------------------------------------------------------
    # Basic control
    # ------------------------------------------------------------

    def clear(self):
        # Wipe screen immediately (sync, used at boot)
        self.oled.fill(0)
        self.oled.show()

    # ------------------------------------------------------------
    # Core drawing — show exactly 3 lines centered
    # ------------------------------------------------------------

    def show_three_lines(self, line1, line2, line3, gap=2):
        # Draw 3 lines centered on screen (sync, no waiting)
        lines = [str(line1 or ""), str(line2 or ""), str(line3 or "")]

        self.oled.fill(0)
        start_y = self.center_y_utility(3, gap)

        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + int(gap)))
            self.oled.text(text, self.center_x_utility(text), int(y))

        self.oled.show()

    # ------------------------------------------------------------
    # METHOD 1: log_queued()
    # - Fire and forget. Adds message to the queue.
    # - Code calling this continues immediately.
    # - Worker shows it when previous message finishes.
    # ------------------------------------------------------------

    def log_queued(self, line1, line2="", line3="", hold_ms=3000):
        """
        Add a message to the display queue.
        Returns instantly — caller does NOT wait.
        Worker will show it in order after previous message holds.
        """
        # Append as a tuple — worker reads these in order
        self.message_queue.append((str(line1), str(line2), str(line3), int(hold_ms)))

    # ------------------------------------------------------------
    # METHOD 2: log_now()
    # - Blocking await. Skips queue, shows immediately.
    # - Caller WAITS hold_ms before continuing.
    # - Use this when the procedure MUST pause for the screen.
    # ------------------------------------------------------------

    async def log_now(self, line1, line2="", line3="", hold_ms=3000):
        """
        Show a message immediately and hold for hold_ms.
        Caller awaits this — code stops here until hold_ms passes.
        Other async tasks (MQTT, RFID) still run during the wait.
        """
        # Show right away, bypassing the queue
        self.show_three_lines(str(line1), str(line2), str(line3))

        # Hold here — but uasyncio lets other tasks run during this sleep
        await asyncio.sleep_ms(int(hold_ms))

    # ------------------------------------------------------------
    # Queue worker — runs forever as a background task
    # Call start_queue_worker() once after asyncio starts
    # ------------------------------------------------------------

    def start_queue_worker(self):
        # Start the background worker only once
        if not self.queue_worker_running:
            self.queue_worker_running = True
            asyncio.create_task(self.queue_worker_loop())

    async def queue_worker_loop(self):
        # Process one message at a time from the queue
        # Runs forever in background — never returns
        while True:
            if len(self.message_queue) > 0:
                # Take the first message from the front of the queue
                line1, line2, line3, hold_ms = self.message_queue.pop(0)

                # Draw it to the screen
                self.show_three_lines(line1, line2, line3)

                # Hold for the requested duration before processing next message
                await asyncio.sleep_ms(hold_ms)
            else:
                # Queue is empty — check again in 20ms (keeps loop efficient)
                await asyncio.sleep_ms(20)

    def clear_queue(self):
        # Discard all pending queued messages (useful before showing urgent screen)
        self.message_queue.clear()

    # ------------------------------------------------------------
    # Main mode — the idle screen shown between events
    # ------------------------------------------------------------

    # Update the text shown in main/idle mode
    def set_screensaver(self, lines):
        if not isinstance(lines, (tuple, list)):
            return
        line1 = str(lines[0]) if len(lines) > 0 else ""
        line2 = str(lines[1]) if len(lines) > 1 else ""
        line3 = str(lines[2]) if len(lines) > 2 else ""
        self.screensaver_lines = (line1, line2, line3)

    # Show main/idle screen immediately (sync, no waiting)
    def show_main_mode_now_utility(self):
        line1, line2, line3 = self.screensaver_lines
        self.show_three_lines(line1, line2, line3)

    # Show main mode without blocking the caller
    async def show_main_mode_async_utility(self):
        line1, line2, line3 = self.screensaver_lines
        self.show_three_lines(line1, line2, line3)
        await asyncio.sleep_ms(0)

    # Return the current idle screen lines as a tuple
    def get_screensaver_lines_utility(self):
        return self.screensaver_lines

    # Clear pending queue messages then show idle screen
    def show_main_mode(self):
        self.clear_queue()
        self.show_main_mode_now_utility()

    # ------------------------------------------------------------
    # Legacy helpers (kept for compatibility)
    # ------------------------------------------------------------

    def show_status(self, title, line1="", line2="", gap=2):
        # Sync display — used during boot before asyncio is running
        lines = [str(title)]
        if line1:
            lines.append(str(line1))
        if line2:
            lines.append(str(line2))

        self.oled.fill(0)
        start_y = self.center_y_utility(len(lines), gap)

        for index, text in enumerate(lines):
            y = start_y + (index * (self.font_height + int(gap)))
            self.oled.text(text, self.center_x_utility(text), y)

        self.oled.show()

    async def show_three_lines_async(self, line1, line2, line3, gap=2):
        # Legacy async wrapper — still works, no hold time
        self.show_three_lines(line1, line2, line3, gap)
        await asyncio.sleep_ms(0)
