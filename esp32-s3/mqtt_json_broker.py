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
        self.wifi_primary = wifi_primary
        self.wifi_fallback = wifi_fallback

        # MQTT broker addresses - primary tried first, fallback if unreachable
        self.broker_primary = broker_primary
        self.broker_fallback = broker_fallback

        # Build the full topic strings from the shared base topic
        self.base_topic = base_topic
        self.command_topic = "{}/Commands".format(base_topic)  # we subscribe to this
        self.event_topic = "{}/Events".format(base_topic)  # we publish to this

        # WiFi interface - STA_IF = station mode (client, not access point)
        self.wlan = network.WLAN(network.STA_IF)

        # MQTT client instance - created fresh on each connection attempt
        self.client = None

        # True when connected and ready to publish/receive
        self.connected = False

        # True when no network found - box runs in local-only mode
        self.offline = False
        self.broker_unreachable = False  # WiFi ok but both brokers failed

        # Wired externally before start() using set_* methods below
        self.command_callback = None  # fn(dict) called with each incoming JSON command
        self.on_connected_callback = (
            None  # fn() called after each successful MQTT connect
        )

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
            
    async def log(self, line1, line2="", line3="", hold_ms=2000):
        print("[BROKER]", line1, "|", line2, "|", line3)
        if self.oled:
            self.oled.show_three_lines(str(line1)[:16], str(line2)[:16], str(line3)[:16])
            await asyncio.sleep_ms(hold_ms)
            
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
        while not self.connected and not self.offline and not self.broker_unreachable:
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
        # Outer loop - keeps the box connected forever, restarts on any failure
        while True:
            try:
                # Skip WiFi reconnect if already connected - only re-enter on full drop
                if not self.wlan.isconnected():
                    connected_wifi = await self.connect_wifi()
                    if not connected_wifi:
                        # No network in range - go offline and scan again in 30s
                        self.offline = True
                        await self.log("OFFLINE", "NO NETWORK", "RETRY IN 90S")
                        await asyncio.sleep_ms(90000)
                        continue

                # WiFi is up - clear offline flag and attempt broker connection
                self.offline = False
                
                if self.broker_unreachable:
                    await self.log("RETRYING", "BROKERS...", "", hold_ms=1500)
                    
                await self.connect_mqtt()
                
                # Retry failed again - restore idle screen so box looks normal
                if self.broker_unreachable and self.oled:
                    self.oled.show_main_mode()

                # Blocks here until connection drops - loops back on any error
                await self.receive_loop()

            except Exception as error:
                print("[BROKER] loop error:", error)

            # Clean up stale client state before retrying
            self.connected = False
            self.client = None
            await self.log("DISCONNECTED", "RETRYING SOON", "")
            # Slow retry when broker is unreachable but WiFi is fine - true background mode
            retry_delay = 120000 if self.broker_unreachable else 800
            await asyncio.sleep_ms(retry_delay)

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

    async def try_wifi(self, cfg):
        ssid = cfg.get("ssid", "")
        if not ssid:
            return False

        if not self.scan_available(ssid):
            await self.log("WIFI", "NOT IN RANGE", ssid[:10])
            return False

        # Reset radio to clear any stuck internal state from previous attempt
        self.wlan.disconnect()
        self.wlan.active(False)
        await asyncio.sleep_ms(300)
        self.wlan.active(True)

        # Show connecting - short hold, no need to wait long
        await self.log("WIFI", "CONNECTING", ssid[:10], hold_ms=500)
        self.wlan.connect(ssid, cfg.get("password", ""))

        for _ in range(40):
            if self.wlan.isconnected():
                await self.log("WIFI", "CONNECTED", ssid[:10], hold_ms=2000)
                return True
            await asyncio.sleep_ms(250)

        await self.log("WIFI", "FAILED", ssid[:10])
        return False

    # ------------------------------------------------------------
    # MQTT connection - tries primary broker then fallback
    # ------------------------------------------------------------

    async def connect_mqtt(self):
        # Try primary then fallback - if both fail, mark unreachable so main() can proceed
        if await self.try_mqtt(self.broker_primary):
            return
        if await self.try_mqtt(self.broker_fallback):
            return
        self.broker_unreachable = True
        await self.log("MQTT", "FAILED - Retry","After 90 seconds")

    async def try_mqtt(self, host):
        # Attempt to connect to one MQTT broker, subscribe, and mark as connected
        if not host:
            return False

        if not self.broker_unreachable:
            await self.log("MQTT", "CONNECTING", host[:16], hold_ms=500)
        else:
            print("[BROKER] MQTT | CONNECTING |", host)

        try:
            # Unique client ID prevents the broker from rejecting duplicate connections
            client_id = "security_box_{}".format(time.ticks_ms())

            # Build a fresh client every attempt - avoids stale socket state
            self.client = MQTTClient(client_id, host, keepalive=60)

            # Wire the message callback before connecting
            self.client.set_callback(self.on_message)

            self.client.connect()
            self.client.subscribe(self.command_topic)

            # Mark connected so send_json() and wait_connected() unblock
            self.connected = True

            print("[BROKER] Subscribed:", self.command_topic)
            print("[BROKER] Publishing:", self.event_topic)
            if not self.broker_unreachable:
                await self.log("MQTT", "CONNECTED", host[:16])
            else:
                print("[BROKER] MQTT | CONNECTED |", host)

            # If recovering from a previous broker failure, show a recovery message
            if self.broker_unreachable:
                self.broker_unreachable = False
                await self.log("BROKER", "RECOVERED", host[:16], hold_ms=2500)

            # Notify main.py so it can return the OLED to idle mode
            if self.on_connected_callback:
                self.on_connected_callback()

            return True

        except Exception as error:
            await self.log("MQTT", "FAILED", str(error)[:16])
            self.connected = False
            self.client = None
            return False

    # ------------------------------------------------------------
    # Receive loop - polls for incoming messages while connected
    # Yields every 30ms so RFID, reed, LED's and OLED tasks keep running
    # ------------------------------------------------------------

    async def receive_loop(self):
        # umqtt.simple does NOT send keepalive pings automatically.
        # We must call ping() manually before the broker's keepalive window expires.
        # keepalive=60s -> ping every 20s to stay safely inside the window.
        last_ping = time.ticks_ms()
        ping_interval_ms = 20000

        while self.connected and self.client is not None:
            try:
                self.client.check_msg()
            except Exception as error:
                await self.log("MQTT", "RX ERROR", str(error)[:16])
                self.connected = False
                return

            # Send keepalive ping before broker times out
            now = time.ticks_ms()
            if time.ticks_diff(now, last_ping) >= ping_interval_ms:
                try:
                    self.client.ping()
                    last_ping = now
                    
                    # Disable this print so it doesnt fill up the console constantly
                    #print("Pinging", "Server","For KeepAlive")
                   
                except Exception as error:
                    await self.log("MQTT", "PING FAILED", str(error)[:16])
                    self.connected = False
                    return

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
            print("[BROKER] RX | bad JSON |", str(error)[:20])
            return

        # Hand the parsed dict to procedures.handle_command
        if self.command_callback:
            try:
                self.command_callback(payload)
            except Exception as error:
                print("[BROKER] RX | handler error |", str(error)[:20])