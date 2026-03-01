# =============================
# file: tasks.py
# =============================
# Purpose:
# - Coordinate OLED UI, RFID scanning, solenoid pulse, and MQTT reporting.
# - Keep the device usable even if MQTT is offline.
# - Keep reed switch support in the file, but do not depend on it (can be enabled later).
#
# Behavior:
# - On boot: show CONNECTING WIFI / MQTT
# - Wait up to BOOT_MQTT_WAIT_MS for MQTT to connect
# - If it connects: show MQTT CONNECTED then show ENTER PIN / OR / SCAN CARD
# - If it does not connect: show MQTT OFFLINE then still show ENTER PIN / OR / SCAN CARD

import uasyncio as asyncio


BOOT_MQTT_WAIT_MS = 8000


def looks_like_coroutine(value):
    # Purpose: detect coroutine objects safely (prevents int(generator) mistakes)
    return (value is not None) and hasattr(value, "send")


class SecurityBoxController:
    def __init__(
        self,
        *,
        oled,
        rfid,
        solenoid,
        mqtt_broker,
        led_strip=None,
        reed_switch=None,
    ):
        self.oled = oled
        self.rfid = rfid
        self.solenoid = solenoid
        self.led_strip = led_strip
        self.reed_switch = reed_switch
        self.mqtt_broker = mqtt_broker

        self.is_unlock_running = False

        self.allowed_remote_calls = {
            "oled": {
                "set_screensaver",
                "mark_activity",
                "clear",
                "show_status",
                "show_three_lines",
                "clear_async",
                "show_status_async",
                "show_three_lines_async",
                "blink_invert_async",
                "marquee_async",
            },
            "led_strip": {}
        }

    # ------------------------------------------------------------
    # Purpose: Start all modules and background tasks
    # ------------------------------------------------------------
    def start(self):
        # Link RFID callbacks into this controller
        self.rfid.on_allowed = self.on_rfid_allowed
        self.rfid.on_denied = self.on_rfid_denied

        # Start UI and RFID scanning
        self.oled.start_screensaver()
        self.rfid.start()

        # Start MQTT loop and route commands to this controller
        self.mqtt_broker.set_command_handler(self.handle_mqtt_command)
        self.mqtt_broker.start()

        # Boot UI flow always runs
        asyncio.create_task(self.boot_status_flow())

        # Watcher fixes: MQTT might connect AFTER the timeout, so update OLED when it finally connects
        asyncio.create_task(self.mqtt_connected_watcher_loop())

    async def mqtt_connected_watcher_loop(self):
        # Do nothing if already connected before this starts
        if self.mqtt_broker.is_connected:
            return

        # Wait until MQTT connects at some later point
        while not self.mqtt_broker.is_connected:
            await asyncio.sleep_ms(250)

        # Show a quick confirmation, then return to idle screen
        await self.oled.show_status_async("MQTT", "CONNECTED", self.mqtt_broker.broker_in_use)
        await asyncio.sleep_ms(2000)
        await self.oled.show_three_lines_async("ENTER PIN", "OR", "SCAN CARD")
        
        # ------------------------------------------------------------
        # Reed switch support kept, but disabled for now (per your request)
        # ------------------------------------------------------------
        # if self.reed_switch is not None and self.get_reed_reader is not None:
        #     asyncio.create_task(self.reed_monitor_loop())

    # ------------------------------------------------------------
    # Purpose: Get a reed read function if available (supports multiple class versions)
    # - Returns a callable that may be sync OR async
    # - Returns None if no supported read function exists
    # ------------------------------------------------------------
    @property
    def get_reed_reader(self):
        if self.reed_switch is None:
            return None

        # Prefer a stable/debounced method if available (usually async)
        if hasattr(self.reed_switch, "read_stable"):
            return self.reed_switch.read_stable

        # Fallback to raw read names (usually sync)
        if hasattr(self.reed_switch, "read_raw"):
            return self.reed_switch.read_raw

        if hasattr(self.reed_switch, "read_value"):
            return self.reed_switch.read_value

        if hasattr(self.reed_switch, "value"):
            return self.reed_switch.value

        return None

    # ------------------------------------------------------------
    # Purpose: Boot screen + MQTT wait with timeout
    # ------------------------------------------------------------
    async def boot_status_flow(self):
        await self.oled.show_three_lines_async("CONNECTING", "WIFI / MQTT", "")

        waited_ms = 0
        while (not self.mqtt_broker.is_connected) and (waited_ms < BOOT_MQTT_WAIT_MS):
            await asyncio.sleep_ms(250)
            waited_ms += 250

        if self.mqtt_broker.is_connected:
            await self.oled.show_status_async("MQTT", "CONNECTED", self.mqtt_broker.broker_in_use)
            await asyncio.sleep_ms(700)
        else:
            await self.oled.show_status_async("MQTT", "OFFLINE", "LOCAL MODE")
            await asyncio.sleep_ms(900)

        await self.oled.show_three_lines_async("ENTER PIN", "OR", "SCAN CARD")

    # ------------------------------------------------------------
    # RFID events
    # ------------------------------------------------------------
    def on_rfid_allowed(self, payload):
        asyncio.create_task(self.rfid_allowed_async(payload))

    def on_rfid_denied(self, payload):
        asyncio.create_task(self.rfid_denied_async(payload))

    async def rfid_allowed_async(self, payload):
        await self.oled.show_status_async("ACCESS", "ALLOWED", payload.get("label", ""))
        await self.mqtt_broker.publish_event("rfid_allowed", payload)
        await self.unlock_sequence_async(reason="rfid", details=payload)

    async def rfid_denied_async(self, payload):
        await self.oled.show_status_async("ACCESS", "DENIED", "")
        await self.oled.blink_invert_async(times=2, delay_ms=150)
        await self.mqtt_broker.publish_event("rfid_denied", payload)

        if self.led_strip is not None:
            self.led_strip.fill(40, 0, 0)
            await asyncio.sleep_ms(250)
            self.led_strip.turn_off()

    # ------------------------------------------------------------
    # Unlock sequence
    # ------------------------------------------------------------
    async def unlock_sequence_async(self, reason, details=None):
        if self.is_unlock_running:
            await self.mqtt_broker.publish_log("Unlock ignored: already running.", level="warn", source="esp32")
            return

        self.is_unlock_running = True
        await self.mqtt_broker.publish_state("lock", "unlocking", {"reason": reason})

        await self.oled.show_status_async("UNLOCK", "OPENING", reason)

        led_task = None
        if self.led_strip is not None and hasattr(self.led_strip, "flow_five_leds_circular_async"):
            led_task = asyncio.create_task(self.led_strip.flow_five_leds_circular_async(cycles=3, delay_ms=40))

        await self.solenoid.pulse()

        if led_task is not None:
            try:
                await led_task
            except Exception:
                pass

        if self.led_strip is not None:
            self.led_strip.turn_off()

        await self.mqtt_broker.publish_state("lock", "locked", {"reason": "pulse_finished"})

        self.is_unlock_running = False
        await self.oled.show_three_lines_async("ENTER PIN", "OR", "SCAN CARD")

    # ------------------------------------------------------------
    # MQTT command handling
    # ------------------------------------------------------------
    def handle_mqtt_command(self, topic, payload):
        command = payload.get("command")

        if command == "unlock":
            return self.handle_unlock_command(payload)

        if command == "call":
            return self.handle_remote_call(payload)

        return None

    async def handle_unlock_command(self, payload):
        await self.mqtt_broker.publish_event("remote_unlock_received", payload)
        await self.unlock_sequence_async(reason="remote", details=payload)

    async def handle_remote_call(self, payload):
        target = payload.get("target")
        method = payload.get("method")
        args = payload.get("args", [])

        if target not in self.allowed_remote_calls:
            await self.mqtt_broker.publish_log("Remote call blocked: bad target", level="warn", source="esp32")
            return

        if method not in self.allowed_remote_calls[target]:
            await self.mqtt_broker.publish_log("Remote call blocked: bad method", level="warn", source="esp32")
            return

        obj = getattr(self, target, None)
        if obj is None:
            return

        fn = getattr(obj, method, None)
        if fn is None:
            return

        if isinstance(args, list):
            result = fn(*args)
        else:
            result = fn(args)

        # If a remote call returns a coroutine, await it
        if looks_like_coroutine(result):
            await result

        await self.mqtt_broker.publish_event("remote_call_ok", {"target": target, "method": method})

    # ------------------------------------------------------------
    # Reed monitor (kept, but currently disabled in start())
    # Fixes your crash:
    # - read_stable() is async, so we must await it.
    # - This function supports both sync and async reed readers.
    # ------------------------------------------------------------
    async def reed_monitor_loop(self):
        reed_reader = self.get_reed_reader
        if reed_reader is None:
            return

        # Initial read (sync or async)
        try:
            initial = reed_reader()
            last_value = (await initial) if looks_like_coroutine(initial) else initial
        except Exception:
            return

        while True:
            try:
                current = reed_reader()
                current_value = (await current) if looks_like_coroutine(current) else current
            except Exception:
                return

            if current_value != last_value:
                last_value = current_value
                await self.mqtt_broker.publish_state(
                    "drawer",
                    "open" if int(current_value) == 0 else "closed",
                    {},
                )

            await asyncio.sleep_ms(200)