# esp32/tasks.py
"""
SecurityBoxController — the main coordinator for the security box.

Responsibilities:
    - Create all hardware objects (OLED, RFID, solenoid, LED, reed, MQTT)
    - Register RFID callbacks and route events into the async main loop
    - Manage the unlock sequence: OLED + LED animation + solenoid pulse
    - Handle MQTT command dispatch (cmd: unlock, call: whitelisted methods)
    - Keep OLED showing current state at all times
    - Reed switch code is present but commented out (magnet not available yet)

Usage (from main.py):
    controller = SecurityBoxController()
    asyncio.run(controller.start())
"""

import uasyncio as asyncio
import time

from classes.oled_screen_class import OledScreen
from classes.rfid_class import RFIDClass, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX
from classes.solenoid_class import SolenoidTB6612
# from classes.reed_switch_class import ReedSwitch   # uncomment when magnet is installed
from classes.led_strip_class import LedStrip
from mqtt_broker import MqttBroker


# ------------------------------------------------------------------
# Whitelist: which device methods can be called from MQTT commands
# ------------------------------------------------------------------
ALLOWED_CALLS = {
    "oled": ["show_status_async", "show_three_lines_async", "clear_async"],
    "led":  ["turn_off", "fill", "set_brightness", "flow_five_leds_circular_async"],
}


class SecurityBoxController:

    def __init__(self):
        """
        Create all hardware objects and wire callbacks.
        Does NOT start tasks — call start() once the asyncio loop is running.
        """

        # OLED comes first so every step below can update the screen
        self.oled = OledScreen()

        # LED strip (50 LEDs, GRB, 15% brightness)
        self.led = LedStrip(pin=14, led_count=50, brightness=0.15, color_order="GRB")

        # Solenoid via TB6612 A-channel
        self.solenoid = SolenoidTB6612(ain1_pin=12)

        # Reed switch — object not created yet (magnet not available)
        # self.reed = ReedSwitch(pin=16, use_pull_up=True, debounce_ms=30)

        # RFID — callbacks use the seq-number pattern: controller stores the
        # latest event and increments a counter; main_loop_utility() detects the change
        self.rfid_event_utility       = None
        self.rfid_seq_utility         = 0
        self.rfid_handled_seq_utility = 0

        self.rfid = RFIDClass(
            whitelist_hex=DEFAULT_WHITELIST_HEX,
            allow_prefixes_hex=DEFAULT_ALLOW_PREFIXES_HEX,
            on_allowed=self.on_rfid_allowed_utility,
            on_denied=self.on_rfid_denied_utility,
        )

        # MQTT manager — on_message callback is handled synchronously inside rx_task
        self.mqtt = MqttBroker(
            client_id="security_box_001",
            on_message=self.handle_mqtt_command_utility,
        )

        # Animation task reference — stored so we can cancel before starting a new one
        self.animation_task_utility = None

        # Prevents two unlock sequences from running at the same time
        self.is_unlock_running = False

    # ------------------------------------------------------------------
    # RFID callbacks (called synchronously from within the RFID scan loop)
    # ------------------------------------------------------------------

    def on_rfid_allowed_utility(self, event):
        """Store latest allowed scan event and tick the sequence counter."""
        self.rfid_event_utility = {"allowed": True,
                                   "uid_hex": event.get("uid_hex", ""),
                                   "uid_int": event.get("uid_int", 0),
                                   "label":   event.get("label",   ""),
                                   "method":  event.get("method",  ""),
                                   "ts":      self.timestamp_utility()}
        self.rfid_seq_utility += 1

    def on_rfid_denied_utility(self, event):
        """Store latest denied scan event and tick the sequence counter."""
        self.rfid_event_utility = {"allowed": False,
                                   "uid_hex": event.get("uid_hex", ""),
                                   "uid_int": event.get("uid_int", 0),
                                   "label":   event.get("label",   ""),
                                   "ts":      self.timestamp_utility()}
        self.rfid_seq_utility += 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def timestamp_utility(self):
        """Return RTC time as HH:MM:SS string."""
        t = time.localtime()
        return "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])

    def cancel_animation_utility(self):
        """Cancel the running LED animation task if one is active."""
        if self.animation_task_utility is not None:
            try:
                self.animation_task_utility.cancel()
            except Exception:
                pass
            self.animation_task_utility = None

    def is_coroutine_utility(self, obj):
        """Return True if obj is a coroutine (needs to be awaited)."""
        return hasattr(obj, "send") and hasattr(obj, "throw")

    # ------------------------------------------------------------------
    # MQTT command dispatch
    # ------------------------------------------------------------------

    def handle_mqtt_command_utility(self, payload):
        """
        Called synchronously when an MQTT message arrives.
        Schedules async work via asyncio.create_task() so this returns fast.

        Supported payload shapes:
            {"cmd": "unlock"}
            {"call": {"device": "oled", "method": "show_status_async",
                      "args": {"title": "HI", "line1": "", "line2": ""}}}
            {"call": {"device": "led", "method": "set_brightness",
                      "args": {"level": 0.5}}}
        """
        if not isinstance(payload, dict):
            return

        # Simple unlock command
        if payload.get("cmd") == "unlock":
            asyncio.create_task(
                self.unlock_sequence_async(reason="mqtt")
            )
            return

        # Whitelisted device.method call
        call = payload.get("call")
        if isinstance(call, dict):
            asyncio.create_task(self.dispatch_call_async_utility(call))

    async def dispatch_call_async_utility(self, call):
        """
        Execute one whitelisted remote device call from an MQTT command.
        Validates device and method against ALLOWED_CALLS before doing anything.
        """
        device_name = call.get("device", "")
        method_name = call.get("method", "")
        args        = call.get("args", {})

        # Check against whitelist
        allowed_methods = ALLOWED_CALLS.get(device_name)
        if allowed_methods is None or method_name not in allowed_methods:
            print("[CMD] rejected:", device_name, method_name)
            return

        # Resolve device object
        device_map = {"oled": self.oled, "led": self.led}
        device_obj = device_map.get(device_name)
        if device_obj is None:
            return

        # Resolve method
        method = getattr(device_obj, method_name, None)
        if method is None:
            return

        # Call with keyword args, await if the result is a coroutine
        try:
            if isinstance(args, dict):
                result = method(**args)
            else:
                result = method()

            if self.is_coroutine_utility(result):
                await result
        except Exception as e:
            print("[CMD] call error:", device_name, method_name, e)

    # ------------------------------------------------------------------
    # Unlock sequence
    # ------------------------------------------------------------------

    async def unlock_sequence_async(self, reason="rfid", uid="", label=""):
        """
        Full unlock flow: OLED status + LED animation (as a parallel task)
        + solenoid pulse.

        The LED animation runs in a separate asyncio task so it does not
        block RFID scanning, OLED updates, or MQTT polling.
        Re-entrant calls are silently ignored via is_unlock_running.
        """
        if self.is_unlock_running:
            return

        self.is_unlock_running = True
        self.oled.mark_activity()

        try:
            # Cancel any currently running animation before starting a new one
            self.cancel_animation_utility()

            # Show who was granted access
            display = label if label else (uid[-6:] if uid else "")
            await self.oled.show_status_async("ACCESS", "GRANTED", display)

            # Start the LED animation as a background task (returns immediately)
            # Running it as a task means RFID and MQTT keep running concurrently
            self.animation_task_utility = asyncio.create_task(
                self.led.flow_five_leds_circular_async(
                    r=0, g=255, b=0,   # green = granted
                    cycles=2,
                    delay_ms=40,
                )
            )

            # Publish the event to NiceGUI dashboard
            self.mqtt.publish_nowait({
                "event": "rfid_allowed",
                "uid":   uid,
                "label": label,
                "ts":    self.timestamp_utility(),
            })

            # Tell user to open the drawer while solenoid is pulsing
            await self.oled.show_status_async("UNLOCKING", "OPEN DRAWER", "")

            # Pulse solenoid: 500ms on + 200ms cooldown
            await self.solenoid.pulse(duration_ms=500, cooldown_ms=200)

            # --- Reed switch confirmation (uncomment when magnet is installed) ---
            # await self.oled.show_status_async("CHECK", "Waiting...", "")
            # new_state = await self.reed.wait_for_change(timeout_ms=1500, poll_ms=15)
            # if new_state is None:
            #     await self.oled.show_status_async("FAULT", "No movement", "")
            #     self.mqtt.publish_nowait({"event": "unlock_fault", "reason": "reed_timeout"})
            # else:
            #     await self.oled.show_status_async("CONFIRMED", "Drawer moved", "")
            #     self.mqtt.publish_nowait({"event": "unlock_confirmed", "state": new_state})

            # Show the time of last unlock for 3 seconds
            await self.oled.show_status_async("LAST UNLOCK", "at:", self.timestamp_utility())
            await asyncio.sleep_ms(3000)

        finally:
            # Always return to idle and clear the guard, even on error
            self.is_unlock_running = False
            await self.oled.show_three_lines_async("Enter PIN", "or", "Scan card")

    # ------------------------------------------------------------------
    # Denied flow
    # ------------------------------------------------------------------

    async def denied_async_utility(self, event):
        """
        Show denied message + brief red LED flash. The user can try again
        immediately after the 3-second display period ends.
        """
        uid = event.get("uid_hex", "")
        display_uid = uid[-6:] if uid else "?"

        self.oled.mark_activity()

        # Cancel any running animation, start a red flash instead
        self.cancel_animation_utility()
        self.animation_task_utility = asyncio.create_task(self.red_flash_async_utility())

        await self.oled.show_status_async("ACCESS", "DENIED", display_uid)

        self.mqtt.publish_nowait({
            "event": "rfid_denied",
            "uid":   uid,
            "ts":    self.timestamp_utility(),
        })

        await asyncio.sleep_ms(3000)
        await self.oled.show_three_lines_async("Enter PIN", "or", "Scan card")

    async def red_flash_async_utility(self):
        """Three quick red blinks for denied feedback. Cancellable."""
        try:
            for _ in range(3):
                self.led.fill(255, 0, 0)
                await asyncio.sleep_ms(150)
                self.led.turn_off()
                await asyncio.sleep_ms(150)
        except asyncio.CancelledError:
            self.led.turn_off()
            raise

    # ------------------------------------------------------------------
    # Main event loop
    # ------------------------------------------------------------------

    async def main_loop_utility(self):
        """
        Watch for new RFID events and dispatch unlock or denied flows.
        Runs forever. Yields every 30ms so all other tasks stay responsive.
        """
        # Show idle screen on first run
        await self.oled.show_three_lines_async("Enter PIN", "or", "Scan card")

        while True:
            # A new RFID event is detected by comparing sequence numbers
            if (self.rfid_event_utility is not None
                    and self.rfid_seq_utility != self.rfid_handled_seq_utility):

                self.rfid_handled_seq_utility = self.rfid_seq_utility
                event = self.rfid_event_utility

                if event.get("allowed"):
                    await self.unlock_sequence_async(
                        reason="rfid",
                        uid=event.get("uid_hex", ""),
                        label=event.get("label", ""),
                    )
                else:
                    await self.denied_async_utility(event)

            await asyncio.sleep_ms(30)

    # ------------------------------------------------------------------
    # Reed switch telemetry loop (ready but commented out)
    # ------------------------------------------------------------------

    # async def reed_monitor_loop_utility(self):
    #     """Poll reed switch and publish state changes to MQTT."""
    #     last_published = None
    #     while True:
    #         state = await self.reed.read_stable()
    #         label = "open" if state else "closed"
    #         if label != last_published:
    #             last_published = label
    #             self.mqtt.publish_nowait({"event": "drawer_state", "state": label})
    #         await asyncio.sleep_ms(500)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self):
        """
        Initialize all tasks and run the main loop forever.

        Order:
            1. MQTT rx/tx tasks
            2. RFID scan loop (auto-started by RFIDClass, start() is idempotent)
            3. OLED screensaver background task
            4. Main event loop (blocks here forever)
        """
        # Start MQTT two-task manager
        self.mqtt.start_tasks()

        # Ensure RFID scan loop is running (safe to call even if already started)
        self.rfid.start()

        # Start screensaver — shows idle message after 60 seconds of no activity
        asyncio.create_task(self.oled.screensaver_loop(idle_ms=60000))

        # Start reed monitor — uncomment when magnet is installed
        # asyncio.create_task(self.reed_monitor_loop_utility())

        # Boot splash
        await self.oled.show_status_async("SECURITY BOX", "Starting...", "")
        await asyncio.sleep_ms(800)

        # Brief MQTT connecting notice (MQTT connects in the background)
        await self.oled.show_status_async("MQTT", "Connecting...", "")
        await asyncio.sleep_ms(1000)

        # Hand off to the main event loop — never returns
        await self.main_loop_utility()
