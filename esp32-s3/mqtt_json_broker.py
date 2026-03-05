"""
mqtt_json_broker.py

WiFi and MQTT connection manager for the Security Box.
Owns the full connection lifecycle - connects, subscribes,
receives commands, publishes events, and reconnects forever
if the connection drops at any point.

Two topics are used:
    Subscribe: <base_topic>/Commands  <- JSON commands from NiceGUI dashboard
    Publish:   <base_topic>/Events    <- JSON events sent to NiceGUI dashboard

Primary WiFi and broker are tried first. If either fails the
fallback credentials are used instead. This allows the box to
work both on the home network and the school network without
changing code.

Role in the box:
    Bridge between the ESP32 and the NiceGUI dashboard on the Pi.
    Receives unlock and LED commands from the dashboard.
    Forwards all system events (access granted, denied, drawer state)
    back to the dashboard as JSON payloads.

Methods:
    * start()                   - launch connection loop as background task
    * wait_connected()          - pause caller until first connection succeeds
    * send_json()               - publish a dict as JSON to the Events topic
    * set_callback()            - wire the incoming command handler
    * set_on_connected_callback() - wire function called after each connect
"""

import uasyncio as asyncio
import network
import ujson
import time

from umqtt.simple import MQTTClient


class MqttJsonBroker:

    # ------------------------------------------------------------
    # Init - store credentials and build empty connection state
    # ------------------------------------------------------------

    def __init__(
        self,
        wifi_primary,
        wifi_fallback,
        broker_primary,
        broker_fallback,
        base_topic,
    ):
        # WiFi credentials - primary tried first, fallback if primary fails
        self.wifi_primary  = wifi_primary
        self.wifi_fallback = wifi_fallback

        # MQTT broker addresses - primary tried first, fallback if unreachable
        self.broker_primary  = broker_primary
        self.broker_fallback = broker_fallback

        # Build the full topic strings from the shared base topic
        self.base_topic    = base_topic
        self.command_topic = "{}/Commands".format(base_topic)  # we subscribe to this
        self.event_topic   = "{}/Events".format(base_topic)    # we publish to this

        # WiFi interface - STA_IF = station mode (client, not access point)
        self.wlan = network.WLAN(network.STA_IF)

        # MQTT client instance - created fresh on each connection attempt
        self.client = None

        # True when connected and ready to publish/receive
        self.connected = False

        # Wired externally before start() using set_* methods below
        self.command_callback      = None  # fn(dict) called with each incoming JSON command
        self.on_connected_callback = None  # fn() called after each successful MQTT connect

    # ------------------------------------------------------------
    # Wiring methods - call these before start()
    # ------------------------------------------------------------

    def set_callback(self, fn):
        # Wire the command handler - receives parsed JSON dict from incoming messages
        self.command_callback = fn

    def set_on_connected_callback(self, fn):
        # Wire function called after each successful MQTT connect (e.g. show idle screen)
        self.on_connected_callback = fn

    # ------------------------------------------------------------
    # Internal console log - broker does not use OLED directly
    # OLED feedback for WiFi/MQTT status comes from the universal logger
    # ------------------------------------------------------------

    def log(self, line1, line2="", line3=""):
        print("[BROKER]", line1, "|", line2, "|", line3)

    # ------------------------------------------------------------
    # Public API - called from main.py and procedures
    # ------------------------------------------------------------

    def start(self):
        # Launch the connection loop as a background task - returns immediately
        asyncio.create_task(self.run_forever())

    async def wait_connected(self):
        # Pause the caller until the first connection succeeds
        # Other background tasks (OLED, LED screensaver) still run during this wait
        while not self.connected:
            await asyncio.sleep_ms(200)

    def send_json(self, payload_dict):
        # Publish a Python dict as a JSON string to the Events topic
        # Silent drop if not connected - never crashes on network loss
        if not self.connected or self.client is None:
            print("[BROKER] not connected - dropped:", payload_dict)
            return

        try:
            self.client.publish(self.event_topic, ujson.dumps(payload_dict))
        except Exception as error:
            print("[BROKER] publish failed:", error)
            # Mark disconnected so run_forever triggers a reconnect on next cycle
            self.connected = False

    # ------------------------------------------------------------
    # Connection lifecycle - connect WiFi, connect MQTT, receive loop
    # Repeats forever on any failure - the box must always reconnect
    # ------------------------------------------------------------

    async def run_forever(self):
        # Outer loop - restarts the whole connection process on any failure
        while True:
            try:
                await self.connect_wifi()
                await self.connect_mqtt()
                await self.receive_loop()
            except Exception as error:
                print("[BROKER] loop error:", error)

            # Mark as disconnected and wait briefly before the next attempt
            self.connected = False
            self.client    = None
            self.log("DISCONNECTED", "retrying soon")
            await asyncio.sleep_ms(800)

    # ------------------------------------------------------------
    # WiFi connection - tries primary then fallback
    # ------------------------------------------------------------

    async def connect_wifi(self):
        # Activate the WiFi radio in station mode
        self.wlan.active(True)

        # Try the primary network first, fall back if it times out
        if not await self.try_wifi(self.wifi_primary):
            await self.try_wifi(self.wifi_fallback)

    async def try_wifi(self, cfg):
        # Attempt to connect to one WiFi network, polling for up to 10 seconds
        ssid = cfg.get("ssid", "")
        if not ssid:
            return False

        self.log("WIFI", "connecting", ssid)
        self.wlan.connect(ssid, cfg.get("password", ""))

        # Poll every 250ms for up to 10 seconds (40 attempts)
        for _ in range(40):
            if self.wlan.isconnected():
                self.log("WIFI", "connected", ssid)
                return True
            await asyncio.sleep_ms(250)

        self.log("WIFI", "failed", ssid)
        return False

    # ------------------------------------------------------------
    # MQTT connection - tries primary broker then fallback
    # ------------------------------------------------------------

    async def connect_mqtt(self):
        # Try the primary broker first, fall back to the Pi broker if unreachable
        if not await self.try_mqtt(self.broker_primary):
            await self.try_mqtt(self.broker_fallback)

    async def try_mqtt(self, host):
        # Attempt to connect to one MQTT broker, subscribe, and mark as connected
        if not host:
            return False

        self.log("MQTT", "connecting", host)

        try:
            # Unique client ID prevents the broker from rejecting duplicate connections
            client_id = "security_box_{}".format(time.ticks_ms())

            # Build a fresh client every attempt - avoids stale socket state
            self.client = MQTTClient(client_id, host, keepalive=30)

            # Wire the message callback before connecting
            self.client.set_callback(self.on_message)

            self.client.connect()
            self.client.subscribe(self.command_topic)

            # Mark connected so send_json() and wait_connected() unblock
            self.connected = True

            self.log("MQTT", "connected", host)
            self.log("SUB", self.command_topic)
            self.log("PUB", self.event_topic)

            # Notify main.py so it can return the OLED to idle mode
            if self.on_connected_callback:
                self.on_connected_callback()

            return True

        except Exception as error:
            self.log("MQTT", "failed", str(error)[:20])
            self.connected = False
            self.client    = None
            return False

    # ------------------------------------------------------------
    # Receive loop - polls for incoming messages while connected
    # Yields every 30ms so RFID, reed, and OLED tasks keep running
    # ------------------------------------------------------------

    async def receive_loop(self):
        while self.connected and self.client is not None:
            try:
                # check_msg() returns immediately if no message is waiting
                self.client.check_msg()
            except Exception as error:
                self.log("MQTT", "rx error", str(error)[:20])
                self.connected = False
                return

            # Short yield - keeps the event loop responsive between message checks
            await asyncio.sleep_ms(30)

    # ------------------------------------------------------------
    # Message handler - called by umqtt on each incoming message
    # Parses JSON and passes the dict to the wired command callback
    # ------------------------------------------------------------

    def on_message(self, topic_bytes, msg_bytes):
        # Decode and parse - log to console on failure, never crash
        try:
            payload = ujson.loads(msg_bytes.decode())
        except Exception as error:
            self.log("RX", "bad JSON", str(error)[:20])
            return

        # Hand the parsed dict to procedures.handle_command
        if self.command_callback:
            try:
                self.command_callback(payload)
            except Exception as error:
                self.log("RX", "handler error", str(error)[:20])