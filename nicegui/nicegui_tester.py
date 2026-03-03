import time
import paho.mqtt.client as mqtt

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
TOPIC = "1404TOPIC/Events"


def on_connect(client, userdata, flags, reason_code, properties=None):
    print("CONNECTED:", reason_code)
    client.subscribe(TOPIC)


def on_message(client, userdata, message):
    payload_text = message.payload.decode(errors="replace")
    print("RX:", message.topic, payload_text)


def on_disconnect(client, userdata, reason_code, properties=None):
    print("DISCONNECTED:", reason_code)


# ✅ Proper v2 API
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

print(f"CONNECTING -> {BROKER_HOST}:{BROKER_PORT}")
client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)

client.loop_start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop()
    client.disconnect()
