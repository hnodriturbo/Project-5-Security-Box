# =============================
# file: mqtt_json_client.py
# =============================
# Purpose:
# - Connect to PRIMARY broker first (Raspberry Pi Mosquitto).
# - If that fails, connect to FALLBACK broker (training broker).
# - Publish dict payloads as JSON.
# - Receive JSON and forward dict payloads to a handler function.

import uasyncio as asyncio
import ujson
from mqtt_as import MQTTClient, config

MQTT_TOPIC = "1404TOPIC"

PRIMARY_BROKER = "10.201.48.7"      # Raspberry Pi broker IP
FALLBACK_BROKER = "broker.emqx.io"  # Training broker

message_handler = None
is_connected = False

def on_mqtt_message(topic, msg, retained):
    try:
        topic_text = topic.decode() if isinstance(topic, (bytes, bytearray)) else str(topic)
        payload_text = msg.decode() if isinstance(msg, (bytes, bytearray)) else str(msg)
        payload_dict = ujson.loads(payload_text)

        if message_handler:
            message_handler(topic_text, payload_dict)

    except Exception as error:
        print("MQTT JSON decode/handler error:", error)

def on_mqtt_connect(client):
    global is_connected
    is_connected = True
    print("MQTT connected")

def on_mqtt_disconnect(client):
    global is_connected
    is_connected = False
    print("MQTT disconnected")

def set_message_handler(handler_function):
    # Purpose: store a function(topic_str, payload_dict) that will receive JSON messages
    global message_handler
    message_handler = handler_function

async def connect_with_fallback():
    # Purpose: try PRIMARY broker, then FALLBACK if PRIMARY fails

    config["subs_cb"] = on_mqtt_message
    config["connect_coro"] = on_mqtt_connect
    config["wifi_coro"] = None
    config["queue_len"] = 1

    # True when Raspberry Pi broker is running, else False for training
    USE_PI_BROKER = False  
    
    brokers_to_try = [PRIMARY_BROKER, FALLBACK_BROKER] if USE_PI_BROKER else [FALLBACK_BROKER]

    last_error = None
    for broker in brokers_to_try:
        try:
            print("MQTT trying broker:", broker)
            config["server"] = broker

            client = MQTTClient(config)
            await client.connect()

            await client.subscribe(MQTT_TOPIC)
            print("MQTT subscribed:", MQTT_TOPIC)

            return client, broker

        except Exception as error:
            last_error = error
            print("MQTT broker failed:", broker, "error:", error)
            await asyncio.sleep_ms(800)

    raise Exception("MQTT could not connect to any broker. Last error: {}".format(last_error))

async def publish_dict(client, payload_dict, topic=MQTT_TOPIC):
    # Purpose: publish a dict as JSON to topic
    try:
        payload_bytes = ujson.dumps(payload_dict).encode()
        await client.publish(topic, payload_bytes)
    except Exception as error:
        print("MQTT publish error:", error)

def is_connected():
    return is_connected