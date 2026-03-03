# ==========================================
# file: mqtt_json_broker.py
# ==========================================
#
# Purpose:
# - Own WiFi + MQTT connection lifecycle completely.
# - Reconnect forever if connection drops — never gives up.
# - Two topics:
#     Subscribe: <base_topic>/Commands  ← receives JSON from NiceGUI dashboard
#     Publish:   <base_topic>/Events    ← sends JSON to NiceGUI dashboard
#
# Screen display rule:
# - Every connection step shows a message on the OLED queue.
# - After successful connect the on_connected_callback is called
#   so main.py can return the screen to idle mode.
#
# How to use from main.py:
#   broker = MqttJsonBroker(...)
#   broker.set_logger(controller.log)          ← wire up screen logging
#   broker.set_callback(procedures.handle_command)  ← wire up command handler
#   broker.set_on_connected_callback(oled.show_main_mode_now_utility)
#   broker.start()                             ← launches background task
#   await broker.wait_connected()              ← wait until first connect succeeds
#
# Sending JSON from anywhere:
#   broker.send_json({"event": "access_allowed", "source": "rfid", ...})
# ==========================================

import uasyncio as asyncio
import network
import ujson
import time

from umqtt.simple import MQTTClient


class MqttJsonBroker:

    def __init__(
        self,
        wifi_primary,
        wifi_fallback,
        broker_primary,
        broker_fallback,
        base_topic,
    ):
        # WiFi credentials — primary is tried first, fallback if primary fails
        self.wifi_primary  = wifi_primary
        self.wifi_fallback = wifi_fallback

        # MQTT broker addresses — primary first, fallback if primary unreachable
        self.broker_primary  = broker_primary
        self.broker_fallback = broker_fallback

        # Build topic strings from base topic
        self.base_topic    = base_topic
        self.command_topic = "{}/Commands".format(base_topic)   # we subscribe to this
        self.event_topic   = "{}/Events".format(base_topic)     # we publish to this

        # Injected hooks — set with set_* methods before calling start()
        self.logger              = None   # controller.log function
        self.callback            = None   # procedures.handle_command function
        self.on_connected_callback = None # called after each successful connect

        # WiFi interface
        self.wlan = network.WLAN(network.STA_IF)

        # MQTT client — created fresh on each connection attempt
        self.client = None

        # Connection state flag — checked by send_json() and wait_connected()
        self.connected = False

    # --------------------------------------------------
    # Wiring methods — call these before start()
    # --------------------------------------------------

    def set_logger(self, logger_fn):
        # Wire in the log function (controller.log) for screen + console output
        self.logger = logger_fn

    def set_callback(self, callback_fn):
        # Wire in the command handler (procedures.handle_command)
        self.callback = callback_fn

    def set_on_connected_callback(self, fn):
        # Wire in a function to call immediately after MQTT connects
        # Typically used to restore the OLED to idle/main mode
        self.on_connected_callback = fn

    # --------------------------------------------------
    # Internal log helper
    # Uses the wired logger if available, otherwise plain print
    # hold_ms=0 means no extra screen hold (status messages pass quickly)
    # --------------------------------------------------

    def log_utility(self, line1, line2="", line3="", hold_ms=2000):
        if self.logger is not None:
            self.logger(line1, line2, line3, hold_ms=hold_ms)
        else:
            print("[BROKER]", line1, line2, line3)

    # --------------------------------------------------
    # start() — launch the connection loop as a background task
    # Returns immediately. Connection happens in the background.
    # --------------------------------------------------

    def start(self):
        # create_task launches run_forever in the background — does not block
        asyncio.create_task(self.run_forever())

    # --------------------------------------------------
    # wait_connected() — await this to pause until first connection succeeds
    # Used in main.py to hold off starting RFID until MQTT is stable
    # --------------------------------------------------

    async def wait_connected(self):
        # Poll every 200ms — other tasks still run during this wait
        while not self.connected:
            await asyncio.sleep_ms(200)

    # --------------------------------------------------
    # send_json() — publish a dict as JSON to the Events topic
    # Called from controller.log() when publish_event is set
    # Safe to call at any time — silently drops if not connected
    # --------------------------------------------------

    def send_json(self, payload_dict):
        if not self.connected or self.client is None:
            # Not connected — drop the message silently, do not crash
            print("[BROKER] NOT CONNECTED — drop:", payload_dict)
            return

        try:
            payload_text = ujson.dumps(payload_dict)
            self.client.publish(self.event_topic, payload_text)
        except Exception as publish_error:
            print("[BROKER] PUBLISH FAIL:", publish_error)
            # Mark as disconnected so run_forever reconnects on next cycle
            self.connected = False

    # --------------------------------------------------
    # run_forever() — main lifecycle loop
    # Tries to connect WiFi + MQTT, then listens for messages.
    # If anything breaks, waits briefly and tries again.
    # --------------------------------------------------

    async def run_forever(self):
        while True:
            try:
                # Connect WiFi
                await self.connect_wifi_internal()

                # Connect MQTT (subscribe + set callback)
                await self.connect_mqtt_internal()

                # Listen for incoming messages until connection drops
                await self.rx_loop_internal()

            except Exception as loop_error:
                print("[BROKER] LOOP ERROR:", loop_error)

            # Mark as disconnected and show screen message
            self.connected = False
            self.client    = None
            self.log_utility("MQTT", "DISCONNECTED", "RETRYING...", hold_ms=2000)

            # Short wait before next reconnect attempt
            await asyncio.sleep_ms(800)

    # --------------------------------------------------
    # WiFi connection
    # Tries primary network first, then fallback
    # --------------------------------------------------

    async def connect_wifi_internal(self):
        self.wlan.active(True)

        # Try primary WiFi first
        connected = await self.try_wifi_internal(self.wifi_primary)
        if connected:
            return

        # Primary failed — try fallback
        await self.try_wifi_internal(self.wifi_fallback)

    async def try_wifi_internal(self, wifi_cfg):
        ssid     = wifi_cfg.get("ssid", "")
        password = wifi_cfg.get("password", "")

        if not ssid:
            return False

        self.log_utility("WIFI", "CONNECTING", ssid, hold_ms=1500)
        self.wlan.connect(ssid, password)

        # Poll up to 10 seconds (40 x 250ms)
        for attempt in range(40):
            if self.wlan.isconnected():
                self.log_utility("WIFI", "CONNECTED", ssid, hold_ms=1500)
                return True
            await asyncio.sleep_ms(250)

        self.log_utility("WIFI", "FAILED", ssid, hold_ms=1500)
        return False

    # --------------------------------------------------
    # MQTT connection
    # Tries primary broker first, then fallback
    # --------------------------------------------------

    async def connect_mqtt_internal(self):
        # Try primary broker
        connected = await self.try_connect_internal(self.broker_primary)
        if connected:
            return

        # Primary broker unreachable — try fallback (local Raspberry Pi broker)
        await self.try_connect_internal(self.broker_fallback)

    async def try_connect_internal(self, broker_host):
        if not broker_host:
            return False

        self.log_utility("MQTT", "CONNECTING", broker_host, hold_ms=1500)

        try:
            # Use ticks_ms as part of client_id to avoid duplicate client conflicts
            client_id = "security_box_{}".format(time.ticks_ms())

            # Create fresh MQTT client
            self.client = MQTTClient(client_id, broker_host, keepalive=30)

            # Wire the raw MQTT message callback
            self.client.set_callback(self.on_message_internal)

            # Connect and subscribe to Commands topic
            self.client.connect()
            self.client.subscribe(self.command_topic)

            # Mark as connected
            self.connected = True

            # Show connection info on screen
            self.log_utility("MQTT", "CONNECTED", broker_host, hold_ms=1500)
            self.log_utility("SUB", self.command_topic[:16], "", hold_ms=1000)
            self.log_utility("PUB", self.event_topic[:16], "", hold_ms=1000)

            # Notify main.py so the OLED returns to idle mode
            if self.on_connected_callback is not None:
                try:
                    self.on_connected_callback()
                except Exception:
                    pass

            return True

        except Exception as connect_error:
            self.log_utility("MQTT", "CONN FAIL", str(connect_error)[:16], hold_ms=2000)
            self.connected = False
            self.client    = None
            return False

    # --------------------------------------------------
    # on_message_internal() — called by umqtt when a message arrives
    # Parses JSON and passes the dict to the wired callback (handle_command)
    # --------------------------------------------------

    def on_message_internal(self, topic_bytes, msg_bytes):
        try:
            payload_text = msg_bytes.decode()
            payload_dict = ujson.loads(payload_text)
        except Exception as parse_error:
            self.log_utility("RX", "BAD JSON", str(parse_error)[:16], hold_ms=2000)
            return

        # Pass to procedures.handle_command if wired
        if self.callback is not None:
            try:
                self.callback(payload_dict)
            except Exception as handler_error:
                self.log_utility("RX", "HANDLER ERR", str(handler_error)[:16], hold_ms=2000)

    # --------------------------------------------------
    # rx_loop_internal() — check for incoming messages in a loop
    # This keeps running while connected.
    # check_msg() reads one message if available, then returns.
    # --------------------------------------------------

    async def rx_loop_internal(self):
        while self.connected and self.client is not None:
            try:
                # check_msg() is non-blocking — returns immediately if no message
                self.client.check_msg()
            except Exception as rx_error:
                self.log_utility("MQTT", "RX FAIL", str(rx_error)[:16], hold_ms=2000)
                self.connected = False
                return

            # Yield to other tasks every 30ms — this is what keeps RFID/OLED alive
            await asyncio.sleep_ms(30)