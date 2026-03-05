# ==========================================
# file: box_controller.py
# ==========================================
#
# Purpose:
# - Create ALL hardware instances in one place and in the correct boot order.
# - OLED is created first so every other class can use it for feedback.
# - Provide a single log() function that replaces print() everywhere:
#     - Prints to console (useful during development)
#     - Shows on OLED via the queue (non-blocking by default)
#     - Optionally publishes JSON event to MQTT dashboard
#
# Boot order:
#   1. OLED  (needed first so all others can show messages)
#   2. LED strip
#   3. Solenoid
#   4. Reed switch  (commented out — hardware not connected yet)
#   5. RFID  (created here but NOT started — started after MQTT connects)
#
# OLED queue rule:
# - log() uses log_queued() by default — fire and forget, code keeps running.
# - For boot messages that must be readable, pass hold=True to log()
#   which uses log_now() and makes the caller wait.
# - Always call oled.start_queue_worker() after asyncio starts (done in main.py).
#
# Shared state:
# - unlock_in_progress  : True while the drawer unlock flow is running
# - system_locked       : True during exclusive procedures (silent ignores RFID/cmds)
# ==========================================

import uasyncio as asyncio
import time

from classes.oled_screen_class  import OledScreen
from classes.led_strip_class    import LedStrip
from classes.solenoid_class     import Solenoid
# from classes.reed_switch_class import ReedSwitch   # commented out — not connected
from classes.rfid_class         import RFID, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX


class BoxController:

    # --------------------------------------------------
    # Init — create hardware in boot order
    # --------------------------------------------------
    def __init__(self):

        # --- 1. OLED first so we can show boot messages ---
        self.oled = OledScreen()
        self.oled.show_status("BOOTING", "PLEASE", "WAIT")

        # Set the idle screen text (shown when system is ready and waiting)
        self.oled.set_screensaver(("READY", "SCAN CARD", ""))

        # --- 2. LED strip ---
        self.led_strip = LedStrip(led_count=50, brightness=0.2, color_order="RGB")
        self.oled.log_queued("LED STRIP", "OK", "")

        # --- 3. Solenoid ---
        self.solenoid = Solenoid()
        self.oled.log_queued("SOLENOID", "OK", "")

        # --- 4. Reed switch (commented out — not connected yet) ---
        # self.reed = ReedSwitch()
        # self.oled.log_queued("REED", "OK", "")
        self.reed = None   # placeholder so other code can check without crashing

        # --- 5. RFID — created but NOT started yet ---
        # We pass the callbacks here but start the scan loop only after MQTT connects.
        # This avoids RFID firing before the system is fully ready.
        self.rfid = RFID(
            whitelist_hex=DEFAULT_WHITELIST_HEX,
            allow_prefixes_hex=DEFAULT_ALLOW_PREFIXES_HEX,
            on_allowed=self.handle_rfid_allowed_sync,
            on_denied=self.handle_rfid_denied_sync,
        )

        # MQTT broker reference — injected later by main.py after broker is created
        self.broker = None

        # Procedures reference — injected later so callbacks can trigger flows
        self.procedures = None

        # Unlock guard: prevents two unlocks running at the same time
        self.unlock_in_progress = False

        # System lock: while True, RFID and remote commands are silently ignored
        self.system_locked = False

    # --------------------------------------------------
    # Inject references (called from main.py after creating broker/procedures)
    # --------------------------------------------------

    def set_broker(self, broker):
        # Wire in the MQTT broker so log() can publish events
        self.broker = broker

    def set_procedures(self, procedures):
        # Wire in procedures so RFID callbacks can trigger the unlock flow
        self.procedures = procedures

    # --------------------------------------------------
    # System lock helpers
    # Used by procedures to block new RFID/command events during a flow
    # --------------------------------------------------

    def lock_system(self):
        self.system_locked = True

    def unlock_system(self):
        self.system_locked = False

    # --------------------------------------------------
    # Timestamp helper
    # Returns current time as a readable string for MQTT payloads
    # --------------------------------------------------

    def get_timestamp(self):
        try:
            year, month, day, hour, minute, second, _, _ = time.localtime()
            return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                year, month, day, hour, minute, second
            )
        except Exception:
            return "NO_TIME"

    # --------------------------------------------------
    # log() — the single function that replaces print() everywhere
    #
    # By default: queued (non-blocking), message waits its turn on screen.
    # Pass blocking=True to make the caller wait (uses log_now inside async context).
    #
    # publish_event: if set, sends a JSON event to MQTT dashboard.
    # --------------------------------------------------

    def log(
        self,
        line1,
        line2="",
        line3="",
        hold_ms=3000,
        blocking=False,
        publish_event=None,
        publish_source=None,
        publish_data=None,
        publish_success=True,
    ):
        # Always print to console (useful during development via USB serial)
        print("[LOG]", line1, "|", line2, "|", line3)

        # Show on OLED
        if self.oled is not None:
            if blocking:
                # Caller must await this — used in async procedures when screen must be read
                # NOTE: if calling the log(blocking=True) from a sync function it won't wait
                # Return a coroutine so the caller can await it
                return self.oled.log_now(line1, line2, line3, hold_ms=hold_ms)
            else:
                # Fire and forget — message goes into queue, code continues immediately
                self.oled.log_queued(line1, line2, line3, hold_ms=hold_ms)

        # Optional: publish JSON event to MQTT dashboard
        if publish_event is not None and self.broker is not None:
            payload = {
                "event": publish_event,
                "source": publish_source or "esp32",
                "status": "ok" if publish_success else "fail",
                "timestamp": self.get_timestamp(),
            }
            if publish_data is not None:
                payload["data"] = publish_data

            self.broker.send_json(payload)

        # Return None for non-blocking path (no await needed)
        return None

    # --------------------------------------------------
    # RFID callbacks (sync wrappers)
    # RFID scan loop is sync — it calls these directly.
    # We use create_task() to hand off to the async procedure.
    # --------------------------------------------------

     # Called by RFID class when an allowed tag is scanned
    def handle_rfid_allowed_sync(self, payload):
        # Silently ignore if system is busy or locked
        if self.system_locked or self.unlock_in_progress:
            return

        if self.procedures is None:
            return

        uid_hex    = payload.get("uid_hex", "")
        card_label = payload.get("label", "")

        # Hand off to the async unlock procedure without blocking the scan loop
        asyncio.create_task(
            self.procedures.unlock_procedure_async(
                source="rfid",
                uid_hex=uid_hex,
                label=card_label,
            )
        )

    def handle_rfid_denied_sync(self, payload):
        # Called by RFID class when an unknown tag is scanned
        # Silently ignore if locked
        if self.system_locked:
            return

        uid_hex    = payload.get("uid_hex", "")
        uid_suffix = uid_hex[-6:] if uid_hex else "UNKNWN"

        # Queue screen message and publish denial event
        self.log(
            "RFID",
            "DENIED",
            uid_suffix,
            publish_event="rfid_denied",
            publish_source="rfid",
            publish_data={"uid_suffix": uid_suffix},
            publish_success=False,
        )

        # Blink red as visual denied feedback — fire and forget
        if self.led_strip is not None:
            asyncio.create_task(self.led_strip.blink_red_three_times_async())

    # --------------------------------------------------
    # Start RFID scan loop
    # Called from main.py AFTER MQTT has connected
    # --------------------------------------------------

    def start_rfid(self):
        # Start the RFID background scan loop
        if self.rfid is not None:
            self.rfid.start()
            self.log("RFID", "STARTED", "")