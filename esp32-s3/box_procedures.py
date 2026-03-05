"""
box_procedures.py

All operational flows and event callbacks for the Security Box.
This is the brain of the system - it knows the order of every step
in every procedure and how the hardware pieces connect together.

No hardware is created here. Hardware instances are passed in from
main.py so this file only contains logic, not pin numbers or drivers.

Procedures own the system_locked and unlock_in_progress flags which
prevent two flows from running at the same time. The reed switch
callbacks are also wired here since they are part of the unlock flow.

Role in the box:
    Receives events from RFID, reed switch, and MQTT commands.
    Decides what to do and in what order. Talks to oled, led,
    solenoid, and broker as needed.

Methods / callbacks:
    * log()                    - console + OLED + optional MQTT publish
    * on_drawer_open()         - reed callback: cancel unlock, publish event
    * on_drawer_close()        - reed callback: lock solenoid, return to idle
    * on_rfid_allowed()        - RFID callback: start unlock procedure
    * on_rfid_denied()         - RFID callback: show denied, blink red
    * unlock_procedure_async() - full unlock flow with countdown
    * handle_command()         - route incoming JSON commands from dashboard
"""

import uasyncio as asyncio
import time


class Procedures:

    # ------------------------------------------------------------
    # Init - store hardware references and wire reed callbacks
    # ------------------------------------------------------------

    def __init__(self, oled, led, solenoid, reed, broker):
        # Hardware references - used by all flows and callbacks
        self.oled     = oled
        self.led      = led
        self.solenoid = solenoid
        self.reed     = reed
        self.broker   = broker

        # Guard flags - prevent two unlocks from overlapping
        self.unlock_in_progress = False
        self.system_locked      = False  # True = silently drop all RFID and commands

        # Stored so on_drawer_open() can cancel a running unlock task
        self.active_unlock_task = None

        # Wire reed callbacks to this class - reed has no knowledge of procedures
        if self.reed is not None:
            self.reed.on_open  = self.on_drawer_open
            self.reed.on_close = self.on_drawer_close

    # ------------------------------------------------------------
    # Helpers - timestamp and publish used throughout all flows
    # ------------------------------------------------------------

    def get_timestamp(self):
        # Build an ISO-ish timestamp from the RTC for MQTT payloads
        try:
            t = time.localtime()
            return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                t[0], t[1], t[2], t[3], t[4], t[5])
        except:
            return "NO_TIME"

    def publish(self, payload):
        # Send a JSON dict to the MQTT dashboard - silent drop if not connected
        if self.broker:
            self.broker.send_json(payload)

    def log(self, line1, line2="", line3="", hold_ms=2000,
            publish_event=None, publish_source=None, publish_data=None, publish_success=True):
        # Print to console and show on OLED immediately (no queue)
        print("[LOG]", line1, "|", line2, "|", line3)
        if self.oled:
            self.oled.show_three_lines(line1, line2, line3)

        # Optionally build and publish a JSON event to the dashboard
        if publish_event and self.broker:
            payload = {
                "event":     publish_event,
                "source":    publish_source or "esp32",
                "status":    "ok" if publish_success else "fail",
                "timestamp": self.get_timestamp(),
            }
            if publish_data:
                payload["data"] = publish_data
            self.broker.send_json(payload)

    # ------------------------------------------------------------
    # Reed switch callbacks - wired in __init__, called by poll_loop
    # ------------------------------------------------------------

    async def on_drawer_open(self):
        print("[REED] drawer OPENED")

        # Cancel unlock countdown if it was running
        if self.active_unlock_task is not None and not self.active_unlock_task.done():
            self.active_unlock_task.cancel()

        # Solenoid off immediately - no need to keep it energized
        if self.solenoid:
            self.solenoid.off()

        # Show drawer open message - stays on screen until drawer closes
        self.oled.show_three_lines("DRAWER OPEN", "PLEASE CLOSE", "DRAWER FULLY")

        self.publish({
            "event":     "drawer_opened",
            "timestamp": self.get_timestamp(),
        })

    async def on_drawer_close(self):
        print("[REED] drawer CLOSED")

        # Guarantee solenoid is off regardless of how drawer was closed
        if self.solenoid:
            self.solenoid.off()

        self.publish({
            "event":     "drawer_closed",
            "status":    "locked",
            "timestamp": self.get_timestamp(),
        })

        # Return to idle - drawer is secured
        self.oled.show_main_mode()


    # ------------------------------------------------------------
    # RFID callbacks - wired from main.py after Procedures is created
    # ------------------------------------------------------------

    def on_rfid_allowed(self, payload):
        # Drop scan silently if a flow is already running - one unlock at a time
        if self.system_locked or self.unlock_in_progress:
            return

        # Store the task reference so on_drawer_open can cancel it
        self.active_unlock_task = asyncio.create_task(
            self.unlock_procedure_async(
                source  = "rfid",
                uid_hex = payload.get("uid_hex", ""),
                label   = payload.get("label", ""),
            )
        )

    def on_rfid_denied(self, payload):
        # Show denied on screen, publish event, blink red as visual feedback
        if self.system_locked:
            return

        uid_hex    = payload.get("uid_hex", "")
        uid_suffix = uid_hex[-6:] if uid_hex else "UNKNWN"

        self.log(
            "RFID", "DENIED", uid_suffix,
            publish_event  = "rfid_denied",
            publish_source = "rfid",
            publish_data   = {"uid_suffix": uid_suffix},
            publish_success = False,
        )

        # Blink red in background - screensaver auto-pauses and resumes
        asyncio.create_task(self.led.blink_color_async(255, 0, 0, times=3))

    # ------------------------------------------------------------
    # Unlock procedure - the main flow of the security box
    #
    # Steps:
    #   1. Guard check - exit if already running
    #   2. Set locks so no other flow can start
    #   3. Show ACCESS GRANTED - hold 2s
    #   4. Blink green in background
    #   5. Publish access_allowed event to dashboard
    #   6. Energize solenoid - drawer can now be opened
    #   7. 10-second countdown on screen
    #   8. De-energize solenoid - window expired
    #   9. Show WINDOW ENDED - hold 1.5s
    #  10. Blocking tail animation as end-of-procedure signal
    #  11. Publish unlock_window_ended event
    #
    # CancelledError path (drawer opened mid-countdown):
    #   - Solenoid turns off immediately
    #   - Dashboard is notified with unlock_cancelled event
    #   - finally block still runs to reset all state
    # ------------------------------------------------------------

    async def unlock_procedure_async(self, source="rfid", uid_hex="", label=""):
        # Guard - should not be reachable but protects against edge cases
        if self.unlock_in_progress:
            return

        # Set both flags so RFID and commands are silently dropped during the flow
        self.unlock_in_progress = True
        self.system_locked      = True

        try:
            uid_suffix   = uid_hex[-6:] if uid_hex else ""
            display_name = label if label else (uid_suffix if uid_suffix else "REMOTE")

            # Show ACCESS GRANTED - log_now pauses here but other tasks still run
            await self.oled.log_now("ACCESS", "GRANTED", display_name, hold_ms=2000)

            # Green blink fires in background - screensaver pauses and resumes around it
            asyncio.create_task(self.led.blink_color_async(0, 255, 0, times=3))

            # Tell the dashboard the access was granted with full detail
            self.publish({
                "event":      "access_allowed",
                "source":     source,
                "label":      label,
                "uid_suffix": uid_suffix,
                "timestamp":  self.get_timestamp(),
            })

            # Energize coil - physically releases the drawer latch
            if self.solenoid:
                self.solenoid.on()

            # 10-second countdown - each log_now holds exactly 1 second
            # CancelledError is raised here if on_drawer_open() cancels this task
            for seconds_left in range(10, 0, -1):
                await self.oled.log_now(
                    "OPEN NOW", "TIME LEFT",
                    "{} SEC".format(seconds_left),
                    hold_ms=1000,
                )

            # Window expired - lock the drawer again
            if self.solenoid:
                self.solenoid.off()

            # Brief confirmation that the unlock window is over
            await self.oled.log_now("UNLOCK", "WINDOW", "ENDED", hold_ms=1500)

            # Blocking tail animation - intentional freeze as "procedure done" signal
            # tail_circular() auto-resumes the LED screensaver when it finishes
            self.led.tail_circular(cycles=2, delay_ms=35, r=0, g=255, b=0)

            # Tell the dashboard the full unlock sequence completed normally
            self.publish({
                "event":     "unlock_window_ended",
                "source":    source,
                "timestamp": self.get_timestamp(),
            })

        except asyncio.CancelledError:
            # Drawer was opened mid-countdown - lock immediately and notify dashboard
            if self.solenoid:
                self.solenoid.off()

            self.publish({
                "event":     "unlock_cancelled",
                "reason":    "drawer_opened",
                "timestamp": self.get_timestamp(),
            })

            # Re-raise so asyncio marks the task as properly cancelled
            raise

        finally:
            # Runs on both normal end and cancel - always restore the system state
            self.unlock_in_progress = False
            self.system_locked      = False
            self.active_unlock_task = None

            # Return OLED to idle and ensure LED screensaver is back on
            self.oled.show_main_mode()
            self.led.start_screensaver()

    # ------------------------------------------------------------
    # MQTT command handler - routes JSON commands from NiceGUI dashboard
    # Called by mqtt_json_broker.on_message() on every incoming message
    # This function is sync - async work is dispatched via create_task()
    # ------------------------------------------------------------

    def handle_command(self, msg):
        # Ignore all commands while a procedure is running
        if self.system_locked:
            return

        command = msg.get("command", "") or msg.get("cmd", "")

        # --- unlock ---
        # Start the full unlock flow remotely, identical to a card scan
        if command == "unlock":
            self.active_unlock_task = asyncio.create_task(
                self.unlock_procedure_async(source="remote", label="REMOTE")
            )

        # --- led_screensaver_on ---
        # Enable the rainbow tail loop and return OLED to idle
        elif command == "led_screensaver_on":
            if self.led:
                self.led.start_screensaver()
                self.oled.show_main_mode()

        # --- led_screensaver_off ---
        # Stop screensaver permanently until re-enabled - strip goes dark
        elif command == "led_screensaver_off":
            if self.led:
                self.led.stop_screensaver()
                self.oled.show_main_mode()

        # --- led_blink ---
        # One-shot blink with a custom RGB color and repeat count
        # JSON: {"command": "led_blink", "r": 255, "g": 0, "b": 0, "times": 3}
        elif command == "led_blink":
            if self.led:
                asyncio.create_task(self.led.blink_color_async(
                    int(msg.get("r", 0)),
                    int(msg.get("g", 0)),
                    int(msg.get("b", 255)),
                    times = int(msg.get("times", 3)),
                ))

        # --- led_tail ---
        # One-shot tail animation with custom color, cycles, and speed
        # JSON: {"command": "led_tail", "r": 0, "g": 255, "b": 0, "cycles": 2, "delay_ms": 35}
        elif command == "led_tail":
            if self.led:
                asyncio.create_task(self.led.tail_circular_async(
                    cycles   = int(msg.get("cycles", 2)),
                    delay_ms = int(msg.get("delay_ms", 35)),
                    r        = int(msg.get("r", 0)),
                    g        = int(msg.get("g", 0)),
                    b        = int(msg.get("b", 255)),
                ))

        # --- led_off ---
        # Stop screensaver and turn strip dark (enabled=False prevents auto-resume)
        elif command == "led_off":
            if self.led:
                self.led.stop_screensaver()

        # --- set_idle_screen ---
        # Update the text shown on OLED when the system is waiting for input
        # JSON: {"command": "set_idle_screen", "line1": "LOCKED", "line2": "SCAN CARD", "line3": ""}
        elif command == "set_idle_screen":
            if self.oled:
                self.oled.set_screensaver((
                    str(msg.get("line1", "READY")),
                    str(msg.get("line2", "SCAN CARD")),
                    str(msg.get("line3", "")),
                ))
                self.oled.show_main_mode()

        # --- oled_show ---
        # Show arbitrary text on the OLED immediately (replaces current screen)
        # JSON: {"command": "oled_show", "line1": "HELLO", "line2": "WORLD", "line3": ""}
        elif command == "oled_show":
            if self.oled:
                self.oled.show_three_lines(
                    str(msg.get("line1", "")),
                    str(msg.get("line2", "")),
                    str(msg.get("line3", "")),
                )

        # --- unknown ---
        # Log unknown commands to console and OLED so they are easy to debug
        else:
            self.log("CMD", "UNKNOWN", str(command)[:16])