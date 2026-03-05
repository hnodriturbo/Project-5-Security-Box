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
        
        # wired via start(oled) - shows boot status on screen
        self.oled = None 
        
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
        
        # True when no network found - box runs in local-only mode
        self.offline   = False
        
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

    def start(self, oled=None):
        # Create the oled
        self.oled = oled
        # Launch the connection loop as a background task - returns immediately
        asyncio.create_task(self.run_forever())

    async def wait_connected(self):
        # Pause the caller until the first connection succeeds
        # Other background tasks (OLED, LED screensaver) still run during this wait
        while not self.connected:
            await asyncio.sleep_ms(200)
            
    async def wait_ready(self):
        # Unblocks when either connected to broker OR offline mode is confirmed
        # Replaces wait_connected() - allows main() to proceed without network
        while not self.connected and not self.offline:
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

    def scan_available(self, ssid):
        # Scan visible networks and return True if ssid is in range
        # Avoids wasting 10s connect timeout on a network that isn't there
        try:
            networks = self.wlan.scan()
            return any(n[0].decode() == ssid for n in networks)
        except Exception:
            return False

    async def run_forever(self):
        # Outer loop - keeps trying forever, 30s between offline retries
        while True:
            try:
                connected_wifi = await self.connect_wifi()

                if not connected_wifi:
                    # No network in range - enter offline mode and retry in 30s
                    self.offline = True
                    self.log("OFFLINE", "no network found", "retry in 30s")
                    await asyncio.sleep_ms(30000)
                    continue  # skip broker, go back to top and scan again

                # WiFi up - try broker
                self.offline = False
                await self.connect_mqtt()
                await self.receive_loop()

            except Exception as error:
                print("[BROKER] loop error:", error)

            self.connected = False
            self.client    = None
            self.log("DISCONNECTED", "retrying soon")
            await asyncio.sleep_ms(800)



    # ------------------------------------------------------------
    # WiFi connection - tries primary then fallback
    # ------------------------------------------------------------
    
    async def connect_wifi(self):
        # Returns True if either network connects, False if both unavailable
        self.wlan.active(True)
        if await self.try_wifi(self.wifi_primary):
            return True
        if await self.try_wifi(self.wifi_fallback):
            return True
        return False
    
    """
    async def connect_wifi(self):
        # Activate the WiFi radio in station mode
        self.wlan.active(True)

        # Try the primary network first, fall back if it times out
        if not await self.try_wifi(self.wifi_primary):
            await self.try_wifi(self.wifi_fallback)
    """
    
    async def try_wifi(self, cfg):
        # Scan first - skip if SSID not visible (saves 10s timeout)
        # Resets radio state before connecting to fix internal stuck state
        ssid = cfg.get("ssid", "")
        if not ssid:
            return False

        if not self.scan_available(ssid):
            self.log("WIFI", "not in range", ssid)
            if self.oled:
                self.oled.show_three_lines("WIFI", "CONNECTING", ssid[:10])
            return False

        # Reset radio to clear any stuck internal state from previous attempt
        self.wlan.disconnect()
        self.wlan.active(False)
        await asyncio.sleep_ms(300)
        self.wlan.active(True)

        self.log("WIFI", "connecting", ssid)
        self.wlan.connect(ssid, cfg.get("password", ""))

        for _ in range(40):
            if self.wlan.isconnected():
                self.log("WIFI", "connected", ssid)
                if self.oled:
                    self.oled.show_three_lines("WIFI", "CONNECTED", ssid[:10])
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
        if self.oled:
            self.oled.show_three_lines("MQTT", "CONNECTING", host)

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
            self.log("Subscribed to:", self.command_topic)
            self.log("Publishing to:", self.event_topic)
            if self.oled:
                self.oled.show_three_lines("MQTT", "CONNECTED", host)

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