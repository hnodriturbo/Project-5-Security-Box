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
        self.drawer_is_open     = False
        
        # Stored so on_drawer_open() can cancel a running unlock task
        self.active_unlock_task = None

        # Wire reed callbacks to this class - reed has no knowledge of procedures
        if self.reed is not None:
            self.reed.on_open  = self.on_drawer_open
            self.reed.on_close = self.on_drawer_close

        # record boot time for uptime calculation
        self.boot_time = time.ticks_ms()
        
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

    
    async def heartbeat_loop(self):
        # Sends system status to dashboard every 30 seconds
        while True:
            uptime_s = time.ticks_diff(time.ticks_ms(), self.boot_time) // 1000
            self.publish({
                "event":    "heartbeat",
                "uptime_s": uptime_s,
                "drawer":   "open" if (self.reed and self.reed.is_open) else "closed",
                "locked":   not self.unlock_in_progress,
                "timestamp": self.get_timestamp(),
            })
            await asyncio.sleep(60)
            
    # ------------------------------------------------------------
    # Reed switch callbacks - wired in __init__, called by poll_loop
    # ------------------------------------------------------------

    async def on_drawer_open(self):
        print("[REED] drawer OPENED")
        
        # Set the drawer is open to true to stop the system while drawer is open
        self.drawer_is_open = True
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
    
        # Change drawer is open to False again to  go back to main system
        self.drawer_is_open = False
        
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

        # Blink red in background - idle loop auto-pauses and resumes
        asyncio.create_task(self.led.blink_color_async(255, 0, 0, times=3))

    # ------------------------------------------------------------
    # Unlock procedure - the main flow of the security box
    #
    # Steps:
    #   1. Guard - block if already running
    #   2. Set locks so no other flow interrupts
    #   3. Show ACCESS GRANTED - hold 2s
    #   4. Blink green in background
    #   5. Publish access_allowed event to dashboard
    #   6. Energize solenoid - drawer can now be opened
    #   7. 10-second countdown - exits early if drawer opens
    #   8. De-energize solenoid - window expired or drawer opened
    #   9. Branch: drawer was opened → publish event and stop
    #             drawer was NOT opened → show WINDOW ENDED + tail animation
    #  10. Publish result event to dashboard
    # ------------------------------------------------------------

    async def unlock_procedure_async(self, source="rfid", uid_hex="", label=""):

        # 1. Guard - should not be reachable but protects against edge cases
        if self.unlock_in_progress:
            return

        # 2. Set both flags so RFID and commands are silently dropped during the flow
        self.unlock_in_progress = True
        self.system_locked      = True

        try:
            uid_suffix   = uid_hex[-6:] if uid_hex else ""
            display_name = label if label else (uid_suffix if uid_suffix else "REMOTE")

            # 3. Show ACCESS GRANTED - log_now pauses here but other tasks still run
            await self.oled.log_now("ACCESS", "GRANTED", display_name, hold_ms=2000)

            # 4. Green blink fires in background - idle loop pauses and resumes around it
            asyncio.create_task(self.led.blink_color_async(0, 255, 0, times=3))

            # 5. Tell the dashboard the access was granted with full detail
            self.publish({
                "event":      "access_allowed",
                "source":     source,
                "label":      label,
                "uid_suffix": uid_suffix,
                "timestamp":  self.get_timestamp(),
            })

            # 6. Energize coil - physically releases the drawer latch
            if self.solenoid:
                self.solenoid.on()

            # 7. Countdown - breaks early if drawer is opened during the window
            # drawer_is_open is set by on_drawer_open() which runs as a background callback
            for seconds_left in range(10, 0, -1):
                if self.drawer_is_open:
                    break  # drawer opened - exit countdown naturally, no error
                await self.oled.log_now(
                    "OPEN NOW", "TIME LEFT",
                    "{} SEC".format(seconds_left),
                    hold_ms=1000,
                )

            # 8. De-energize solenoid - window expired or drawer was opened
            if self.solenoid:
                self.solenoid.off()

            # 9. Branch on what actually happened during the window
            if self.drawer_is_open:
                # Drawer was opened - this is the expected happy path
                # on_drawer_open() already showed the screen message and published drawer_opened
                # Nothing more to do here - system stays blocked until drawer closes
                self.publish({
                    "event":     "drawer_opened_during_unlock",
                    "source":    source,
                    "timestamp": self.get_timestamp(),
                })
            else:
                # 10. Full window expired without the drawer being opened
                await self.oled.log_now("UNLOCK", "WINDOW", "ENDED", hold_ms=1500)

                # Blocking tail animation - intentional freeze as "procedure done" signal
                # tail_circular() auto-resumes the LED idle loop when it finishes
                self.led.tail_circular(cycles=2, delay_ms=35, r=0, g=255, b=0)

                self.publish({
                    "event":     "unlock_window_ended",
                    "source":    source,
                    "timestamp": self.get_timestamp(),
                })

        finally:
            # Always runs - reset flow flags regardless of what happened above
            self.unlock_in_progress = False
            self.system_locked      = False
            self.active_unlock_task = None

            # Only return to idle if drawer is closed - drawer open message must stay visible
            if not self.drawer_is_open:
                self.oled.show_main_mode()

            # Screensaver restores regardless - strip should always be in idle state
            self.led.start_idle_loop()

    # ------------------------------------------------------------
    # MQTT command handler - routes JSON commands from NiceGUI dashboard
    # Called by mqtt_json_broker.on_message() on every incoming message
    # This function is sync - async work is dispatched via create_task()
    # ------------------------------------------------------------

    def handle_command(self, msg):
        # Ignore all commands while a procedure is running
        if self.system_locked:
            return

        # Blink the led strip 3 times in green color
        asyncio.create_task(self.led.blink_color_async(0, 255, 0, times=3))

        # Refuse all commands while drawer is physically open
        if self.drawer_is_open:
            self.publish({
                "event":   "command_refused",
                "reason":  "drawer is open - close drawer before sending commands",
                "timestamp": self.get_timestamp(),
            })
            return

        command = msg.get("command", "") or msg.get("cmd", "")

        # --- unlock ---
        # Start the full unlock flow remotely, identical to a card scan
        if command == "unlock":
            self.active_unlock_task = asyncio.create_task(
                self.unlock_procedure_async(source="remote", label="REMOTE")
            )

        # --- led_idle_on ---
        # Enable the pixel idle loop and return OLED to idle
        elif command == "led_idle_on":
            if self.led:
                self.led.start_idle_loop()
                self.oled.show_main_mode()

        # --- led_idle_off ---
        # Stop idle loop permanently until re-enabled - strip goes dark
        elif command == "led_idle_off":
            if self.led:
                self.led.stop_idle_loop()
                self.oled.show_main_mode()
                
        # --- led_idle_1 / led_idle_2 ---
        # Switch between idle loop animations from the dashboard
        elif command == "led_idle_1":
            if self.led:
                self.led.set_idle_loop(1)

        elif command == "led_idle_2":
            if self.led:
                self.led.set_idle_loop(2)

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

        # Stop idle loop and turn strip dark (enabled=False prevents auto-resume)
        elif command == "led_off":
            if self.led:
                self.led.stop_idle_loop()

        # --- set_idle_screen ---
        # Update the text shown on OLED when the system is waiting for input
        # JSON: {"command": "set_idle_screen", "line1": "LOCKED", "line2": "SCAN CARD", "line3": ""}
        elif command == "set_idle_screen":
            if self.oled:
                self.oled.set_idle_screen((
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
                async def _show_and_restore(l1, l2, l3, ms):
                    await self.oled.log_now(l1, l2, l3, hold_ms=ms)
                    self.oled.show_main_mode()
                asyncio.create_task(self.oled.log_now(
                    str(msg.get("line1", "")),
                    str(msg.get("line2", "")),
                    str(msg.get("line3", "")),
                    hold_ms=int(msg.get("hold_ms", 3000)),
                ))
                
        # --- unknown ---
        # Log unknown commands to console and OLED so they are easy to debug
        else:
            self.log("CMD", "UNKNOWN", str(command)[:16])