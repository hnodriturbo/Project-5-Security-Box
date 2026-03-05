# ==========================================
# file: controller.py
# ==========================================
# Purpose:
# - Hold shared system state + shared utilities.
# - Provide ONE log() function:
#   - prints to console
#   - shows on OLED (non-blocking)
#   - optionally publishes JSON to the dashboard (MQTT)
#
# OLED rule:
# - No timers in log().
# - log() only shows the requested message.
# - Procedures decide exactly when to return to main mode.
# ==========================================

import uasyncio as asyncio
import time


class SecurityBoxController:
    def __init__(self, oled, led_strip, solenoid, reed, rfid):
        # Hardware references
        self.oled = oled
        self.led_strip = led_strip
        self.solenoid = solenoid
        self.reed = reed
        self.rfid = rfid

        # MQTT broker reference (injected)
        self.broker = None

        # Unlock guard
        self.unlock_in_progress = False

        # System lock (silent ignore) for procedures that must be exclusive
        self.system_locked = False

    # --------------------------------------------------
    # Exclusive lock helpers (silent ignore behavior)
    # --------------------------------------------------
    def lock_system_now_utility(self):
        self.system_locked = True

    def unlock_system_now_utility(self):
        self.system_locked = False

    # --------------------------------------------------
    # Wiring: inject broker so controller can publish events
    # --------------------------------------------------
    def set_broker(self, broker):
        self.broker = broker

    # --------------------------------------------------
    # Timestamp helper
    # --------------------------------------------------
    def time_utility(self):
        try:
            year, month, day, hour, minute, second, _, _ = time.localtime()
            return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                year, month, day, hour, minute, second
            )
        except Exception:
            return ""

    # --------------------------------------------------
    # Unified logger (no timers, no auto-revert)
    # --------------------------------------------------
    def log(
        self,
        line1,
        line2="",
        line3="",
        publish_event=None,
        publish_source=None,
        publish_data=None,
        publish_success=True,
    ):
        # Console output is always useful for debugging
        print(line1, line2, line3)

        # OLED output is fire-and-forget, because procedures should block when needed
        if self.oled is not None:
            asyncio.create_task(
                self.oled.show_three_lines_async(
                    str(line1),
                    str(line2),
                    str(line3),
                )
            )

        # Optional JSON publish
        if publish_event and self.broker is not None:
            payload = {
                "event": publish_event,
                "source": publish_source or "esp32",
                "status": "ok" if publish_success else "fail",
                "timestamp": self.time_utility(),
            }

            if publish_data is not None:
                payload["data"] = publish_data

            self.broker.send_json(payload)

    # --------------------------------------------------
    # RFID callbacks
    # --------------------------------------------------
    async def rfid_allowed_async(self, uid_hex, card_label, unlock_procedure_async):
        # Silent ignore while locked or already unlocking
        if self.system_locked or self.unlock_in_progress:
            return

        # Start unlock flow
        await unlock_procedure_async(source="rfid", uid_hex=uid_hex, label=card_label)

    async def rfid_denied_async(self, uid_hex):
        # Silent ignore while locked
        if self.system_locked:
            return

        uid_suffix = uid_hex[-6:] if uid_hex else ""

        self.log(
            "RFID",
            "DENIED",
            uid_suffix,
            publish_event="rfid_denied",
            publish_source="rfid",
            publish_data={"uid_suffix": uid_suffix},
            publish_success=False,
        )

        if self.led_strip:
            asyncio.create_task(self.led_strip.blink_red_three_times_async())