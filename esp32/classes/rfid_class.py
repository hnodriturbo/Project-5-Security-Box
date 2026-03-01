"""
rfid_class.py - MFRC522 RFID scanner helper

Purpose:
- Initialize MFRC522 using SPI pins.
- Continuously scan for RFID tags in an async loop.
- Decide allowed/denied using:
  - Exact whitelist match (stable tags), OR
  - Prefix allow list (demo mode for unstable phone UIDs).
- Emit scan results using callbacks (on_allowed / on_denied).

Notes:
- No leading underscores in any variable or function names.
- Safe to run alongside OLED screensaver + solenoid pulse + reed monitoring in one uasyncio program.
- The scan loop avoids repeating events while the same tag stays on the reader.
"""

import uasyncio as asyncio
from machine import Pin, SoftSPI

from lib.RFID.mfrc522 import MFRC522

# -----------------------------
# Default pins (final wiring)
# -----------------------------
RFID_SCK_PIN = 18
RFID_MOSI_PIN = 5
RFID_MISO_PIN = 6
RFID_RST_PIN = 7
RFID_CS_PIN = 4

# Allowed dictionary for card and keychain
DEFAULT_WHITELIST_HEX = {
    "C495FC2984": "card",
    "439A311CF4": "keychain",
}

# Allow ALL phones (they start with 08 in HEX)
DEFAULT_ALLOW_PREFIXES_HEX = ["08"]

# -----------------------------
# Setup RFID reader + scan rules
# -----------------------------
class RFIDClass:
    def __init__(
        self,
        *,
        sck_pin=RFID_SCK_PIN,
        mosi_pin=RFID_MOSI_PIN,
        miso_pin=RFID_MISO_PIN,
        rst_pin=RFID_RST_PIN,
        cs_pin=RFID_CS_PIN,
        baudrate=100_000,
        scan_delay_ms=150,
        allow_prefixes_hex=None,
        whitelist_hex=None,
        on_allowed=None,
        on_denied=None,
    ):
        # Store callbacks used by the application layer
        self.on_allowed = on_allowed
        self.on_denied = on_denied

        # Store scan timing
        self.scan_delay_ms = int(scan_delay_ms)

        # Store allow/deny rules
        self.allow_prefixes_hex = allow_prefixes_hex or []
        self.whitelist_hex = whitelist_hex or {}

        # Track last UID to avoid repeated callbacks while a tag stays present
        self.last_uid_hex_internal = None

        # Create SPI bus for the RFID reader
        self.spi_bus = SoftSPI(
            baudrate=int(baudrate),
            polarity=0,
            phase=0,
            sck=Pin(int(sck_pin)),
            mosi=Pin(int(mosi_pin)),
            miso=Pin(int(miso_pin)),
        )
        self.spi_bus.init()

        # Create MFRC522 reader instance
        self.reader = MFRC522(
            spi=self.spi_bus,
            gpioRst=int(rst_pin),
            gpioCs=int(cs_pin),
        )

        # Auto-start the scan loop if asyncio is already running
        self.scan_task = None
        try:
            self.scan_task = asyncio.create_task(self.scan_loop_internal())
        except RuntimeError:
            self.scan_task = None

    # -----------------------------
    # Control scan loop lifecycle
    # -----------------------------
    def start(self):
        # Start the scan loop after asyncio is running (safe to call multiple times)
        if self.scan_task is None:
            self.scan_task = asyncio.create_task(self.scan_loop_internal())

    def stop(self):
        # Stop the scan loop and clear the task handle
        if self.scan_task is not None:
            self.scan_task.cancel()
            self.scan_task = None

    # -----------------------------
    # Allow / deny decision helpers
    # -----------------------------
    def is_allowed(self, uid_hex):
        # Exact whitelist match
        if uid_hex in self.whitelist_hex:
            return True

        # Prefix allow list (useful for unstable phone UIDs)
        for prefix in self.allow_prefixes_hex:
            if uid_hex.startswith(prefix):
                return True

        return False

    def label_for(self, uid_hex):
        # Return a friendly label for known tags, otherwise empty string
        return self.whitelist_hex.get(uid_hex, "")

    # -----------------------------
    # Main async scan loop
    # -----------------------------
    async def scan_loop_internal(self):
        # Scan forever without blocking other tasks (OLED/solenoid/reed/MQTT)
        while True:
            (status, _tag_type) = self.reader.request(self.reader.REQIDL)

            if status == self.reader.OK:
                (status, uid_bytes) = self.reader.anticoll()

                if status == self.reader.OK:
                    uid_hex = uid_bytes.hex().upper()
                    uid_int = int.from_bytes(uid_bytes, "big")

                    # Skip duplicates until the tag is removed and re-presented
                    if uid_hex != self.last_uid_hex_internal:
                        self.last_uid_hex_internal = uid_hex

                        allowed = self.is_allowed(uid_hex)
                        label = self.label_for(uid_hex)

                        # Emit allowed callback
                        if allowed and self.on_allowed:
                            self.on_allowed(
                                {
                                    "uid_hex": uid_hex,
                                    "uid_int": uid_int,
                                    "label": label,
                                    "method": "whitelist"
                                    if uid_hex in self.whitelist_hex
                                    else "prefix",
                                }
                            )

                        # Emit denied callback
                        if (not allowed) and self.on_denied:
                            self.on_denied(
                                {
                                    "uid_hex": uid_hex,
                                    "uid_int": uid_int,
                                    "label": label,
                                }
                            )

            else:
                # Reset last UID so the next tag presence triggers a new event
                self.last_uid_hex_internal = None

            await asyncio.sleep_ms(self.scan_delay_ms)