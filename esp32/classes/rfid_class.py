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
- This file does not modify sys.path. Keep your project import path setup in main.py.
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

class RFIDClass:
    # Create SPI bus, initialize MFRC522, and optionally auto-start the scan loop
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
        self._last_uid_hex = None

        # Create SPI bus for the RFID reader
        self._spi = SoftSPI(
            baudrate=int(baudrate),
            polarity=0,
            phase=0,
            sck=Pin(int(sck_pin)),
            mosi=Pin(int(mosi_pin)),
            miso=Pin(int(miso_pin)),
        )
        self._spi.init()

        # Create MFRC522 reader instance
        self._reader = MFRC522(
            spi=self._spi,
            gpioRst=int(rst_pin),
            gpioCs=int(cs_pin),
        )

        # Try to auto-start when an event loop is already running
        self._task = None
        try:
            self._task = asyncio.create_task(self._scan_loop())
        except RuntimeError:
            self._task = None

    # Start the scan loop after asyncio is running (safe to call multiple times)
    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._scan_loop())

    # Stop the scan loop and clear the task handle
    def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None

    # Decide whether a UID hex string is allowed
    def is_allowed(self, uid_hex):
        if uid_hex in self.whitelist_hex:
            return True

        for prefix in self.allow_prefixes_hex:
            if uid_hex.startswith(prefix):
                return True

        return False

    # Return a friendly label for known tags, otherwise empty string
    def label_for(self, uid_hex):
        return self.whitelist_hex.get(uid_hex, "")

    # Async scan loop that requests + anticoll, then calls callbacks on change
    async def _scan_loop(self):
        while True:
            (status, _tag_type) = self._reader.request(self._reader.REQIDL)

            if status == self._reader.OK:
                (status, uid_bytes) = self._reader.anticoll()

                if status == self._reader.OK:
                    uid_hex = uid_bytes.hex().upper()
                    uid_int = int.from_bytes(uid_bytes, "big")

                    # Skip duplicates until the tag is removed and re-presented
                    if uid_hex != self._last_uid_hex:
                        self._last_uid_hex = uid_hex

                        allowed = self.is_allowed(uid_hex)
                        label = self.label_for(uid_hex)

                        # Build a compact event payload for the application layer
                        if allowed and self.on_allowed:
                            self.on_allowed(
                                {
                                    "uid_hex": uid_hex,
                                    "uid_int": uid_int,
                                    "label": label,
                                    "method": "whitelist" if uid_hex in self.whitelist_hex else "prefix",
                                }
                            )

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
                self._last_uid_hex = None

            await asyncio.sleep_ms(self.scan_delay_ms)


DEFAULT_WHITELIST_HEX = {
    "C495FC2984": "card",
    "439A311CF4": "keychain",
}

DEFAULT_ALLOW_PREFIXES_HEX = ["08"]