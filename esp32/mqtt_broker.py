# =============================
# file: mqtt_broker.py
# =============================
# Purpose:
# - Simple MQTT connector that does NOT manage WiFi.
# - Try PRIMARY broker first, then FALLBACK automatically.
# - Subscribe to one topic and forward incoming JSON to your handler.
# - Publish JSON immediately (drop messages if offline).
#
# Why this replaces mqtt_as:
# - mqtt_as may touch WiFi internals and cause "Wifi Internal State Error".
# - umqtt.simple only uses the existing WiFi connection and does not reconfigure SSID.
#
# Requirement:
# - WiFi must already be connected by setup_wifi_and_time.py before calling start().

import uasyncio as asyncio
import ujson

from umqtt.simple import MQTTClient


# -----------------------------
# MQTT defaults (security box)
# -----------------------------
MQTT_TOPIC = "1404TOPIC"

PRIMARY_BROKER = "10.201.48.7"      # Raspberry Pi Mosquitto (school network)
FALLBACK_BROKER = "broker.emqx.io"  # Public fallback


# -----------------------------
# Small helpers
# -----------------------------
def force_dict(value):
    if isinstance(value, dict):
        return value
    return {}


def merge_dicts(base_dict, extra_dict):
    base_dict = force_dict(base_dict)
    extra_dict = force_dict(extra_dict)

    for key in extra_dict:
        base_dict[key] = extra_dict[key]

    return base_dict


def decode_to_str(value):
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode()
        except Exception:
            return ""
    return str(value)


# -----------------------------
# MQTT broker manager
# -----------------------------
class MqttBroker:
    def __init__(
        self,
        topic=MQTT_TOPIC,
        primary=PRIMARY_BROKER,
        fallback=FALLBACK_BROKER,
        client_id="esp32_security_box",
        keepalive=30,
    ):
        self.topic = str(topic)
        self.primary = str(primary)
        self.fallback = str(fallback)

        self.client_id = str(client_id)
        self.keepalive = int(keepalive)

        self.client = None
        self.is_connected = False
        self.broker_in_use = ""

        # Lock onto the first broker that succeeds (no switching while WiFi stays up)
        self.locked_broker = None

        # handler(topic_str, payload_dict) -> may return coroutine or None
        self.command_handler = None

        self.connect_task = None
    
    # Wait until connected for showing screen information
    async def wait_until_connected(self):
        while not self.is_connected:
            await asyncio.sleep_ms(200)
            
    # If a broker already worked, only ever try that one again
    def pick_brokers_to_try(self):
        if self.locked_broker:
            return [self.locked_broker]
        return [self.primary, self.fallback]

    # First successful broker becomes the locked one
    def mark_connected_broker(self, broker):
        if not self.locked_broker:
            self.locked_broker = str(broker)
            
    # -----------------------------
    # Set inbound JSON handler
    # -----------------------------
    def set_command_handler(self, handler_function):
        self.command_handler = handler_function


    # -----------------------------
    # Start background loop
    # -----------------------------
    def start(self):
        if self.connect_task is None:
            self.connect_task = asyncio.create_task(self.connect_loop())


    # -----------------------------
    # Internal RX callback from umqtt
    # -----------------------------
    def on_message(self, topic, msg):
        try:
            topic_text = decode_to_str(topic)
            msg_text = decode_to_str(msg)

            payload_any = ujson.loads(msg_text)
            payload_dict = force_dict(payload_any)

            if self.command_handler:
                result = self.command_handler(topic_text, payload_dict)

                # Schedule async handler if it returned a coroutine
                if (result is not None) and hasattr(result, "send"):
                    asyncio.create_task(result)

        except Exception as error:
            print("MQTT RX error:", str(error))


    # -----------------------------
    # Publish JSON (drop if offline)
    # -----------------------------
    async def publish(self, payload_dict, topic=None):
        payload_dict = force_dict(payload_dict)
        topic_to_use = self.topic if topic is None else str(topic)

        if (not self.is_connected) or (self.client is None):
            return

        try:
            payload_bytes = ujson.dumps(payload_dict).encode()
            self.client.publish(topic_to_use, payload_bytes)
        except Exception as error:
            print("MQTT TX error:", str(error))
            self.reset_connection_state()


    def publish_nowait(self, payload_dict, topic=None):
        asyncio.create_task(self.publish(payload_dict, topic=topic))


    async def publish_event(self, event_name, data_dict=None):
        payload = {"event": str(event_name)}
        payload = merge_dicts(payload, data_dict)
        await self.publish(payload)


    async def publish_log(self, message, level="info", source="esp32"):
        payload = {
            "event": "log",
            "level": str(level),
            "source": str(source),
            "message": str(message),
        }
        await self.publish(payload)


    async def publish_state(self, state_name, value, details_dict=None):
        payload = {
            "event": "state",
            "name": str(state_name),
            "value": value,
        }
        payload = merge_dicts(payload, details_dict)
        await self.publish(payload)


    # -----------------------------
    # Reset connection state
    # -----------------------------
    def reset_connection_state(self):
        self.is_connected = False
        self.client = None


    # -----------------------------
    # Connect + listen loop (primary -> fallback)
    # -----------------------------
    async def connect_loop(self):
        while True:

            if self.is_connected and (self.client is not None):
                try:
                    self.client.check_msg()
                except Exception as error:
                    print("MQTT connection lost:", str(error))
                    self.reset_connection_state()

                await asyncio.sleep_ms(200)
                continue

            # Not connected -> try brokers in order
            for broker in self.pick_brokers_to_try():
                self.broker_in_use = str(broker)

                try:
                    # New client each attempt (clean state)
                    self.client = MQTTClient(
                        client_id=self.client_id,
                        server=self.broker_in_use,
                        keepalive=self.keepalive,
                    )

                    self.client.set_callback(self.on_message)
                    self.client.connect()
                    self.client.subscribe(self.topic)

                    self.is_connected = True
                    print("MQTT connected:", self.broker_in_use, "topic:", self.topic)
                    self.mark_connected_broker(self.broker_in_use)

                    # Optional “online” event
                    try:
                        await self.publish_event("esp_online", {"broker": self.broker_in_use})
                    except Exception:
                        pass

                    break

                except Exception as error:
                    print("MQTT connect failed:", self.broker_in_use, "error:", str(error))
                    self.reset_connection_state()
                    await asyncio.sleep_ms(900)

            await asyncio.sleep_ms(900)