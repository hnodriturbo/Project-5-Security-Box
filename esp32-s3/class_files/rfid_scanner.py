"""
rfid_scanner.py

MFRC522 RFID card scanner for the Security Box.
Scans for RFID tags in a continuous background loop and fires
callbacks based on whether the tag is on the whitelist or not.

Tag matching uses two methods:
    - Exact UID hex match against the whitelist dict
    - Prefix match for phones (phones have unstable full UIDs
      but their first bytes are consistent, e.g. prefix "08")

Duplicate events are suppressed while the same tag stays on
the reader - a new event only fires after the tag is removed
and re-presented to the reader.

Role in the box:
    Provides the primary local trigger for the unlock procedure.
    RFID is started last at boot (after MQTT connects) so that
    card scan events can be published to the dashboard immediately.
    on_allowed / on_denied are wired from main.py after Procedures
    is created so the callbacks are always ready before scanning starts.

Methods:
    * start()        - boot confirmation on OLED, launches scan loop
    * stop()         - cancel scan loop cleanly
    * is_allowed()   - check if a UID hex string is permitted
    * label_for()    - return a friendly name for a known UID
    * scan_loop_internal() - background poll and callback dispatch
"""

import uasyncio as asyncio
from machine import Pin, SoftSPI
from lib.RFID.mfrc522 import MFRC522
import time

# SPI pins for the MFRC522 module
RFID_SCK_PIN  = 18
RFID_MOSI_PIN = 5
RFID_MISO_PIN = 6
RFID_RST_PIN  = 7
RFID_CS_PIN   = 4

# Known cards - UID hex string maps to a friendly label shown on OLED
DEFAULT_WHITELIST_HEX = {
    "C495FC2984": "card",
    "439A311CF4": "keychain",
}

# Any UID starting with these hex prefixes is allowed (phones use this)
DEFAULT_ALLOW_PREFIXES_HEX = ["08"]


class RFID:

    # ------------------------------------------------------------
    # Init - configure SPI bus, create MFRC522 reader, store rules
    # Callbacks are set as attributes and can be wired after __init__
    # ------------------------------------------------------------

    def __init__(
        self,
        *,
        sck_pin            = RFID_SCK_PIN,
        mosi_pin           = RFID_MOSI_PIN,
        miso_pin           = RFID_MISO_PIN,
        rst_pin            = RFID_RST_PIN,
        cs_pin             = RFID_CS_PIN,
        baudrate           = 100_000,
        scan_delay_ms      = 150,
        allow_prefixes_hex = None,
        whitelist_hex      = None,
        on_allowed         = None,
        on_denied          = None,
    ):
        # Callbacks - can be set directly as attributes before start() is called
        self.on_allowed = on_allowed
        self.on_denied  = on_denied

        # How long to wait between each scan attempt (ms)
        self.scan_delay_ms = int(scan_delay_ms)

        # Tag matching rules
        self.whitelist_hex      = whitelist_hex      or {}
        self.allow_prefixes_hex = allow_prefixes_hex or []

        # Stores the last seen UID so repeat events are not fired while tag stays
        self.last_uid_hex_internal = None

        # Scan task handle - None until start() is called
        self.scan_task = None

        # Build the SPI bus for the MFRC522 module
        self.spi_bus = SoftSPI(
            baudrate = int(baudrate),
            polarity = 0,
            phase    = 0,
            sck      = Pin(int(sck_pin)),
            mosi     = Pin(int(mosi_pin)),
            miso     = Pin(int(miso_pin)),
        )
        self.spi_bus.init()

        # Create the MFRC522 reader using the SPI bus and control pins
        self.reader = MFRC522(
            spi     = self.spi_bus,
            gpioRst = int(rst_pin),
            gpioCs  = int(cs_pin),
        )

    # ------------------------------------------------------------
    # Boot confirmation - shows RFID ready on OLED, then starts scan loop
    # Called last in main.py after MQTT is connected and callbacks are wired
    # ------------------------------------------------------------

    def start(self, oled=None):
        # Print to console and show boot message on OLED for 3 seconds
        print("[RFID] started - scanning for tags")
        if oled:
            oled.show_three_lines("RFID", "STARTED", "SCANNING")
            time.sleep_ms(3000)

        # Launch background scan loop - only if not already running
        if self.scan_task is None:
            self.scan_task = asyncio.create_task(self.scan_loop_internal())

    # ------------------------------------------------------------
    # Stop - cancel scan loop without crashing
    # ------------------------------------------------------------

    def stop(self):
        if self.scan_task is not None:
            self.scan_task.cancel()
            self.scan_task = None

    # ------------------------------------------------------------
    # Tag matching helpers
    # ------------------------------------------------------------

    def is_allowed(self, uid_hex):
        # Check exact whitelist match first (fastest check for known cards)
        if uid_hex in self.whitelist_hex:
            return True

        # Then check prefix list - any matching prefix means allowed
        return any(uid_hex.startswith(p) for p in self.allow_prefixes_hex)

    def label_for(self, uid_hex):
        # Return the friendly label for a known UID, empty string for unknown
        return self.whitelist_hex.get(uid_hex, "")

    # ------------------------------------------------------------
    # Scan loop - polls reader continuously, dedupes, fires callbacks
    # Runs as a background task - yields every scan_delay_ms so other
    # tasks (OLED, MQTT, reed) keep running between scans
    # ------------------------------------------------------------

    async def scan_loop_internal(self):
        while True:
            # Request step - check if any tag is in the RF field
            status, _ = self.reader.request(self.reader.REQIDL)

            if status == self.reader.OK:
                # Anti-collision step - read the UID bytes from the tag
                status, uid_bytes = self.reader.anticoll()

                if status == self.reader.OK:
                    uid_hex = uid_bytes.hex().upper()
                    uid_int = int.from_bytes(uid_bytes, "big")

                    # Only fire if this is a new tag (not the same one still present)
                    if uid_hex != self.last_uid_hex_internal:
                        self.last_uid_hex_internal = uid_hex

                        allowed = self.is_allowed(uid_hex)
                        label   = self.label_for(uid_hex)

                        if allowed and self.on_allowed:
                            self.on_allowed({
                                "uid_hex": uid_hex,
                                "uid_int": uid_int,
                                "label":   label,
                                "method":  "whitelist" if uid_hex in self.whitelist_hex else "prefix",
                            })
                        elif not allowed and self.on_denied:
                            self.on_denied({
                                "uid_hex": uid_hex,
                                "uid_int": uid_int,
                                "label":   label,
                            })
            else:
                # No tag detected - reset last UID so re-presenting the same tag fires again
                self.last_uid_hex_internal = None

            # Yield to other tasks before next scan
            await asyncio.sleep_ms(self.scan_delay_ms)