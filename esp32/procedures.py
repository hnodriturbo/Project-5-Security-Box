# ==========================================
# file: procedures.py
# ==========================================
#
# Purpose:
# - Define every "flow" the security box can run.
# - A flow is a sequence of steps that happen in order.
# - This is the ONLY file that knows how hardware steps connect together.
#
# How async works here — simple rules:
#
#   await something_async()
#       → this line PAUSES this function and waits for it to finish
#       → but uasyncio lets other tasks (MQTT, RFID, screen queue) keep running
#       → use this when the next step depends on the current step finishing
#
#   asyncio.create_task(something_async())
#       → launches something in the background and returns IMMEDIATELY
#       → this function does NOT wait for it
#       → use this for "fire and forget" side effects (blinking, screen messages)
#
#   regular_function()
#       → just a normal call — runs and returns before the next line
#       → if it takes a long time (like tail_circular) it BLOCKS everything
#
# Flows defined here:
#   - unlock_procedure_async()  : full unlock sequence (RFID or remote)
#   - handle_rfid_denied()      : denied scan feedback
#   - handle_command()          : parse incoming MQTT JSON and route to correct flow
#
# JSON commands supported (received from NiceGUI dashboard):
#   {"command": "unlock"}
#   {"command": "led_screensaver_on"}
#   {"command": "led_screensaver_off"}
#   {"command": "led_blink",  "r": 0, "g": 255, "b": 0, "times": 3}
#   {"command": "led_tail",   "r": 0, "g": 0, "b": 255, "cycles": 2, "delay_ms": 35}
#   {"command": "led_off"}
#   {"command": "set_idle_screen", "line1": "READY", "line2": "SCAN CARD", "line3": ""}
#   {"command": "oled_show",  "line1": "HELLO", "line2": "WORLD", "line3": ""}
# ==========================================

import uasyncio as asyncio


class Procedures:

    def __init__(self, controller):
        # Store the controller so all flows can use hardware + log()
        self.controller = controller

    # ======================================================
    # FLOW 1: Unlock procedure
    #
    # Triggered by:
    #   - RFID scan of an allowed card
    #   - MQTT command {"command": "unlock"}
    #
    # What happens step by step:
    #   1. Guard check — exit immediately if already unlocking
    #   2. Lock the system so RFID and other commands are ignored
    #   3. Show "ACCESS GRANTED" on screen (waits 2 seconds)
    #   4. Blink green (background — does not pause the flow)
    #   5. Publish access_allowed event to MQTT
    #   6. Turn solenoid ON
    #   7. Countdown 10 → 1 on screen, one second per step
    #   8. Turn solenoid OFF
    #   9. Show "WINDOW ENDED" screen (waits 1.5 seconds)
    #  10. Green tail animation (BLOCKING — signals end of flow visually)
    #  11. Publish unlock_ended event to MQTT
    #  12. Restore system: clear guards, show idle screen
    # ======================================================

    async def unlock_procedure_async(self, source="rfid", uid_hex="", label=""):

        # Step 1 — guard: if an unlock is already happening, do nothing
        if self.controller.unlock_in_progress:
            return

        # Step 2 — mark system as busy so nothing else interrupts
        self.controller.unlock_in_progress = True
        self.controller.lock_system()

        # Stop the LED screensaver if it was running — we need the strip for feedback
        if self.controller.led_strip is not None:
            self.controller.led_strip.stop_screensaver()

        try:

            # Build display name: use label if we have one, otherwise show UID suffix
            uid_suffix   = uid_hex[-6:] if uid_hex else ""
            display_name = label if label else (uid_suffix if uid_suffix else "REMOTE")

            # Step 3 — show ACCESS GRANTED and wait 2 seconds before continuing
            # We use log_now() so the screen is visible long enough to be read
            # Other tasks (MQTT receive, screen queue) still run during this wait
            await self.controller.oled.log_now("ACCESS", "GRANTED", display_name, hold_ms=2000)

            # Step 4 — blink green in the background (fire and forget)
            # create_task means we do NOT wait for the blink to finish before step 5
            if self.controller.led_strip is not None:
                asyncio.create_task(
                    self.controller.led_strip.blink_green_three_times_async()
                )

            # Step 5 — tell the dashboard this unlock was allowed
            self.controller.log(
                "ACCESS", "GRANTED", display_name,
                hold_ms=0,                         # 0 = no extra OLED hold (screen already showed in step 3)
                publish_event="access_allowed",
                publish_source=source,
                publish_data={"label": label, "uid_suffix": uid_suffix},
                publish_success=True,
            )

            # Step 6 — energize solenoid to release the drawer latch
            if self.controller.solenoid is not None:
                self.controller.solenoid.on()

            # Step 7 — 10-second countdown shown on screen
            # Each iteration: show time left, then wait exactly 1 second
            # await asyncio.sleep_ms(1000) pauses THIS function for 1 second
            # but MQTT and other tasks keep running during that second
            for seconds_left in range(10, 0, -1):
                await self.controller.oled.log_now(
                    "OPEN NOW",
                    "TIME LEFT",
                    "{} SEC".format(seconds_left),
                    hold_ms=1000,   # show each second for exactly 1000ms
                )

            # Step 8 — countdown done, lock the drawer again
            if self.controller.solenoid is not None:
                self.controller.solenoid.off()

            # Step 9 — brief "window ended" confirmation screen
            await self.controller.oled.log_now("UNLOCK", "WINDOW", "ENDED", hold_ms=5000)

            # Step 10 — green tail animation — BLOCKING by design
            # This is the visual "procedure finished" signal
            # Nothing else runs during this (~3 seconds), which is intentional
            if self.controller.led_strip is not None:
                self.controller.led_strip.tail_circular(
                    cycles=2, delay_ms=35, r=0, g=255, b=0
                )

            # Step 11 — tell the dashboard the unlock window is over
            self.controller.log(
                "UNLOCK", "WINDOW", "ENDED",
                hold_ms=0,
                publish_event="unlock_window_ended",
                publish_source=source,
                publish_success=True,
                
            )
            
            print(f"Sent json log to dashboard: unlock_window_ended")
            
        finally:
            # Step 12 — always runs even if something crashed above
            # Clear the busy flags and return to the idle screen
            self.controller.unlock_in_progress = False
            self.controller.unlock_system()
            
            # Clear the queue so the screen doesnt stop and stick
            self.controller.oled.show_main_mode()
 

    # ======================================================
    # FLOW 2: RFID denied
    #
    # Called when an unknown card is scanned.
    # Short — just log, blink red, no solenoid action.
    # This runs directly in the RFID callback (not a separate task).
    # ======================================================

    def handle_rfid_denied(self, uid_hex):

        # Silently ignore if system is locked (unlock already in progress)
        if self.controller.system_locked:
            return

        uid_suffix = uid_hex[-6:] if uid_hex else "UNKNWN"

        # Queue the denied message on screen (fire and forget)
        self.controller.log(
            "RFID", "DENIED", uid_suffix,
            publish_event="rfid_denied",
            publish_source="rfid",
            publish_data={"uid_suffix": uid_suffix},
            publish_success=False,
        )

        # Blink red in the background — does not block anything
        if self.controller.led_strip is not None:
            asyncio.create_task(
                self.controller.led_strip.blink_red_three_times_async()
            )

    # ======================================================
    # FLOW 3: Handle incoming MQTT command
    #
    # Called by mqtt_json_broker when a message arrives on the Commands topic.
    # Receives the parsed JSON as a dict: msg = {"command": "unlock", ...}
    #
    # This function is SYNC (no async/await here) because the broker calls it
    # from its receive loop. We use create_task() for any async work.
    # ======================================================

    def handle_command(self, msg):

        # Ignore all commands while a procedure is running
        if self.controller.system_locked:
            return

        # Read the "command" field from the JSON (support both key names)
        command = msg.get("command", "") or msg.get("cmd", "")

        # --------------------------------------------------
        # command: "unlock"
        # Trigger the full unlock flow remotely from NiceGUI
        # --------------------------------------------------
        if command == "unlock":
            # create_task launches unlock_procedure_async in the background
            # handle_command returns immediately, broker loop is not blocked
            asyncio.create_task(
                self.unlock_procedure_async(source="remote", uid_hex="", label="REMOTE")
            )
            return

        # --------------------------------------------------
        # command: "led_screensaver_on"
        # Start the rainbow tail screensaver on the LED strip
        # --------------------------------------------------
        if command == "led_screensaver_on":
            if self.controller.led_strip is not None:
                self.controller.led_strip.start_screensaver()
                self.controller.log("LED", "SCREENSAVER", "ON", hold_ms=2000)
                self.controller.oled.show_main_mode()
            return

        # --------------------------------------------------
        # command: "led_screensaver_off"
        # Stop the screensaver and turn off the strip
        # --------------------------------------------------
        if command == "led_screensaver_off":
            if self.controller.led_strip is not None:
                self.controller.led_strip.stop_screensaver()
                self.controller.log("LED", "SCREENSAVER", "OFF", hold_ms=2000)
                self.controller.oled.show_main_mode()
            return

        # --------------------------------------------------
        # command: "led_blink"
        # Blink the strip with a chosen color
        # JSON example: {"command": "led_blink", "r": 255, "g": 0, "b": 0, "times": 3}
        # --------------------------------------------------
        if command == "led_blink":
            if self.controller.led_strip is not None:
                r     = int(msg.get("r", 0))
                g     = int(msg.get("g", 0))
                b     = int(msg.get("b", 255))
                times = int(msg.get("times", 3))

                asyncio.create_task(
                    self.controller.led_strip.blink_color_async(r, g, b, times=times)
                )
                self.controller.oled.show_main_mode()
            return

        # --------------------------------------------------
        # command: "led_tail"
        # Run one tail animation pass (non-blocking)
        # JSON example: {"command": "led_tail", "r": 0, "g": 255, "b": 0, "cycles": 2}
        # --------------------------------------------------
        if command == "led_tail":
            if self.controller.led_strip is not None:
                r        = int(msg.get("r", 0))
                g        = int(msg.get("g", 0))
                b        = int(msg.get("b", 255))
                cycles   = int(msg.get("cycles", 2))
                delay_ms = int(msg.get("delay_ms", 35))

                asyncio.create_task(
                    self.controller.led_strip.tail_circular(
                        cycles=cycles, delay_ms=delay_ms, r=r, g=g, b=b
                    )
                )
            return

        # --------------------------------------------------
        # command: "led_off"
        # Turn off the strip immediately
        # --------------------------------------------------
        if command == "led_off":
            if self.controller.led_strip is not None:
                self.controller.led_strip.stop_screensaver()   # cancel task if running
                self.controller.led_strip.turn_off()
            return

        # --------------------------------------------------
        # command: "set_idle_screen"
        # Change the text shown on the OLED when system is idle
        # JSON example: {"command": "set_idle_screen", "line1": "LOCKED", "line2": "SCAN CARD", "line3": ""}
        # --------------------------------------------------
        if command == "set_idle_screen":
            line1 = str(msg.get("line1", "READY"))
            line2 = str(msg.get("line2", "SCAN CARD"))
            line3 = str(msg.get("line3", ""))

            if self.controller.oled is not None:
                self.controller.oled.set_screensaver((line1, line2, line3))
                self.controller.oled.show_main_mode()
            return

        # --------------------------------------------------
        # command: "oled_show"
        # Show arbitrary text on the OLED (queued)
        # JSON example: {"command": "oled_show", "line1": "HELLO", "line2": "WORLD", "line3": "!"}
        # --------------------------------------------------
        if command == "oled_show":
            line1 = str(msg.get("line1", ""))
            line2 = str(msg.get("line2", ""))
            line3 = str(msg.get("line3", ""))
            hold  = int(msg.get("hold_ms", 3000))

            if self.controller.oled is not None:
                self.controller.oled.log_queued(line1, line2, line3, hold_ms=hold)
                self.controller.oled.show_main_mode()
            return

        # --------------------------------------------------
        # Unknown command — log it so we can debug from console/OLED
        # --------------------------------------------------
        self.controller.log("CMD", "UNKNOWN", str(command)[:16])