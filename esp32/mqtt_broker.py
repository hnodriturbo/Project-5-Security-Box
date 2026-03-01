# esp32/mqtt_broker.py
"""
MQTT manager for the Security Box ESP32 side.

Design — two asyncio tasks:
    rx_task():  polls check_msg() every 50ms so other tasks keep running.
                Reconnects automatically if the socket drops.
    tx_task():  drains an outbound list-queue and publishes JSON every 20ms.
                Drops oldest messages if the queue grows past TX_QUEUE_MAX.

Why two tasks?
    RX never waits on TX. A slow or failed publish cannot delay incoming
    commands. Both loops yield frequently so RFID, OLED, and solenoid tasks
    are never starved.

MicroPython constraints handled here:
    - umqtt.simple is synchronous — use check_msg() (non-blocking), not wait_msg()
    - No asyncio.Queue on MicroPython — plain list used as a FIFO queue
    - umqtt.simple has no reconnect() — create a new MQTTClient on each attempt
    - All JSON decode is inside try/except — bad messages never crash the task

Usage:
    mqtt = MqttBroker(client_id="box_001", on_message=my_callback)
    mqtt.start_tasks()   # call after asyncio loop is running
    mqtt.publish_nowait({"event": "boot"})
"""

import uasyncio as asyncio
import ujson
from umqtt.simple import MQTTClient


# Broker addresses — primary is the Raspberry Pi on the school LAN
PRIMARY_BROKER  = "10.201.48.7"
FALLBACK_BROKER = "broker.emqx.io"

# Single topic for all messages (commands in, telemetry out)
MQTT_TOPIC = "1404TOPIC"

# How often rx_task() calls check_msg() (milliseconds)
RX_POLL_MS = 50

# How often tx_task() checks the outbound queue (milliseconds)
TX_POLL_MS = 20

# Maximum queued outbound messages before oldest are dropped
TX_QUEUE_MAX = 10

# Seconds to wait between reconnect attempts
RECONNECT_WAIT_MS = 5000


class MqttBroker:

    def __init__(self, client_id,
                 topic=MQTT_TOPIC,
                 primary_broker=PRIMARY_BROKER,
                 fallback_broker=FALLBACK_BROKER,
                 on_message=None):
        """
        Prepare the MQTT manager. Does NOT connect — call start_tasks() after
        the asyncio event loop starts (i.e., from inside asyncio.run()).

        Args:
            client_id:      Unique string ID for this MQTT client
            topic:          Topic to subscribe to and publish on
            primary_broker: Preferred broker IP (Raspberry Pi)
            fallback_broker:Public broker if primary is unreachable
            on_message:     Callback(payload_dict) fired on every valid inbound JSON
        """
        self.client_id       = str(client_id)
        self.topic           = topic.encode()   # umqtt.simple expects bytes for topic
        self.primary_broker  = str(primary_broker)
        self.fallback_broker = str(fallback_broker)
        self.on_message      = on_message

        # Connection state (read by controller to show "MQTT OK" on OLED)
        self.connected     = False
        self.active_broker = None

        # Outbound queue — list used as a FIFO (append right, pop left)
        self.tx_queue_utility = []

        # The umqtt.simple client instance (replaced on each reconnect)
        self.client_utility = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def on_raw_message_utility(self, topic, msg):
        """
        Called synchronously by umqtt.simple when check_msg() finds a message.
        Decodes JSON and forwards to the on_message callback.
        Bad JSON is silently ignored — never crashes.
        """
        try:
            payload = ujson.loads(msg)
        except Exception:
            print("[MQTT] ignoring bad JSON:", msg[:40])
            return

        if self.on_message is not None:
            try:
                self.on_message(payload)
            except Exception as e:
                print("[MQTT] on_message error:", e)

    def try_connect_utility(self):
        """
        Attempt a fresh connection to primary then fallback broker.
        Creates a new MQTTClient on each attempt (umqtt.simple has no reconnect).
        Returns True on success, False if both brokers fail.
        """
        for broker_addr in (self.primary_broker, self.fallback_broker):
            try:
                print("[MQTT] connecting to", broker_addr)
                client = MQTTClient(self.client_id, broker_addr, port=1883, keepalive=30)
                client.set_callback(self.on_raw_message_utility)
                client.connect()
                client.subscribe(self.topic)
                self.client_utility = client
                self.active_broker  = broker_addr
                self.connected      = True
                print("[MQTT] connected:", broker_addr)
                return True
            except Exception as e:
                print("[MQTT] connect failed:", broker_addr, e)

        self.connected      = False
        self.client_utility = None
        self.active_broker  = None
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish_nowait(self, payload_dict):
        """
        Enqueue a message for publishing. Non-blocking — safe to call from
        anywhere including RFID callbacks and MQTT command handlers.

        If the queue is full, the oldest entry is dropped to make room.
        tx_task() will pick this up within TX_POLL_MS milliseconds.

        Args:
            payload_dict: Python dict — will be serialized to JSON before publish
        """
        if len(self.tx_queue_utility) >= TX_QUEUE_MAX:
            self.tx_queue_utility.pop(0)   # drop oldest to cap memory use

        self.tx_queue_utility.append(payload_dict)

    def start_tasks(self):
        """
        Create rx_task and tx_task as asyncio tasks. Call this once, inside
        the asyncio event loop (from controller.start() or similar).
        """
        asyncio.create_task(self.rx_task())
        asyncio.create_task(self.tx_task())

    # ------------------------------------------------------------------
    # Asyncio tasks
    # ------------------------------------------------------------------

    async def rx_task(self):
        """
        Receive loop — runs forever as an asyncio task.

        Flow:
            1. If not connected: try to connect (retry every RECONNECT_WAIT_MS)
            2. Call check_msg() — non-blocking, fires on_raw_message_utility if a
               message is ready, returns immediately otherwise
            3. On OSError (socket disconnected): mark disconnected, retry
            4. Always yield with sleep_ms(RX_POLL_MS) between calls
        """
        while True:
            if not self.connected:
                ok = self.try_connect_utility()
                if not ok:
                    # Wait before trying again to avoid hammering the broker
                    await asyncio.sleep_ms(RECONNECT_WAIT_MS)
                    continue

            # Poll for one incoming message (non-blocking)
            try:
                self.client_utility.check_msg()
            except OSError as e:
                print("[MQTT] rx disconnected:", e)
                self.connected      = False
                self.client_utility = None
            except Exception as e:
                print("[MQTT] rx error:", e)
                self.connected      = False
                self.client_utility = None

            # Yield — lets RFID, OLED, solenoid, and tx_task run
            await asyncio.sleep_ms(RX_POLL_MS)

    async def tx_task(self):
        """
        Transmit loop — runs forever as an asyncio task.

        Flow:
            1. If the queue is non-empty and connected: serialize and publish
            2. On error: mark disconnected (rx_task will reconnect)
            3. Always yield with sleep_ms(TX_POLL_MS)

        Note: if not connected, messages stay in the queue until rx_task
        establishes a new connection. Queue is capped at TX_QUEUE_MAX so
        memory usage stays bounded during an outage.
        """
        while True:
            if self.tx_queue_utility and self.connected:
                payload_dict = self.tx_queue_utility.pop(0)
                try:
                    raw = ujson.dumps(payload_dict)
                    self.client_utility.publish(self.topic, raw)
                except Exception as e:
                    print("[MQTT] tx error:", e)
                    self.connected      = False
                    self.client_utility = None
                    # Put the message back at the front so it isn't lost
                    self.tx_queue_utility.insert(0, payload_dict)

            await asyncio.sleep_ms(TX_POLL_MS)
