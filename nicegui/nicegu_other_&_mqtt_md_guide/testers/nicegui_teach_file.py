"""
nicegui_remote_skull.py

NiceGUI learning file: a simple web-based remote control for your skull (eyes + servos) using MQTT.

What this file teaches:
- Basic NiceGUI layout (header, cards, tabs)
- Handling UI events (buttons, sliders, color picker)
- Running async scenes without freezing the UI
- Keeping a small live log + connection indicator updated
- Sending JSON commands over MQTT to your ESP32

Install:
  pip install nicegui paho-mqtt

Run:
  python nicegui_remote_skull.py

Environment overrides (optional):
  SKULL_MQTT_BROKER, SKULL_MQTT_PORT, SKULL_TOPIC_CMD, SKULL_TOPIC_ACK, NICEGUI_HOST, NICEGUI_PORT
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass

from nicegui import ui, app
import paho.mqtt.client as mqtt


# -----------------------------
# Configuration values used by NiceGUI and MQTT
# -----------------------------

MQTT_BROKER = os.getenv("SKULL_MQTT_BROKER", "test.mosquitto.org")
MQTT_PORT = int(os.getenv("SKULL_MQTT_PORT", "1883"))

MQTT_TOPIC_CMD = os.getenv("SKULL_TOPIC_CMD", "1404-skull/cmd")
MQTT_TOPIC_ACK = os.getenv("SKULL_TOPIC_ACK", "1404-skull/ack")

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "0.0.0.0")
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8080"))


# -----------------------------
# State container shared by UI and MQTT helpers
# -----------------------------


@dataclass
class SkullState:
    # Stores the latest UI-selected values so they can be resent at any time
    eyes_enabled: bool = True
    eyes_brightness: int = 80

    # NeoPixel color order for this project is GRB
    eyes_g: int = 255
    eyes_r: int = 0
    eyes_b: int = 0

    # Servo angles
    neck_angle: int = 90
    mouth_angle: int = 10
    mouth_min: int = 10
    mouth_max: int = 50

    # Prevents multiple scenes from running at the same time
    scene_running: bool = False


STATE = SkullState()

# Simple rolling log shown in the UI
LOG_LINES = []


# Add a timestamped line to the rolling UI log
def log(message):
    message = str(message)
    timestamp = time.strftime("%H:%M:%S")
    LOG_LINES.append(f"[{timestamp}] {message}")
    if len(LOG_LINES) > 200:
        del LOG_LINES[:50]


# -----------------------------
# MQTT bridge between NiceGUI and the skull
# -----------------------------


class MqttBridge:
    """
    Manages MQTT connection for NiceGUI apps.
    Uses paho-mqtt library (for desktop/server Python).
    
    For ESP32, you would use umqtt.simple instead - see MqttBridgeESP class below.
    """
    
    def __init__(self):
        # Create MQTT client and register callbacks
        self.client = mqtt.Client()
        self.connected = False
        
        # Register callback methods
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def connect(self):
        # Connect to the broker and start the MQTT loop in the background
        self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def disconnect(self):
        # Stop the MQTT loop and disconnect cleanly
        try:
            self.client.loop_stop()
        finally:
            self.client.disconnect()

    def publish_json(self, topic, payload):
        # Publish a Python dict as JSON on the given MQTT topic
        topic = str(topic)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        raw = json.dumps(payload).encode("utf-8")
        self.client.publish(topic, raw, qos=0, retain=False)
        log(f"MQTT -> {topic}: {payload}")

    def on_connect(self, client, userdata, flags, rc):
        # Handle successful connection to the broker
        self.connected = True
        log(f"MQTT connected: {MQTT_BROKER}:{MQTT_PORT} (rc={rc})")
        try:
            client.subscribe(MQTT_TOPIC_ACK, qos=0)
        except Exception as e:
            log(f"MQTT subscribe failed: {e}")

    def on_disconnect(self, client, userdata, rc):
        # Handle broker disconnection
        self.connected = False
        log(f"MQTT disconnected (rc={rc})")

    def on_message(self, client, userdata, msg):
        # Handle incoming messages from the skull (ACK/status)
        try:
            text = msg.payload.decode("utf-8", errors="replace")
            log(f"MQTT <- {msg.topic}: {text}")
        except Exception as e:
            log(f"MQTT message parse error: {e}")


# -----------------------------
# ESP32 version of MqttBridge (for reference)
# Copy this class to your ESP32 project and adjust as needed
# -----------------------------

"""
# ESP32 MqttBridge using umqtt.simple
# This is a simplified version for MicroPython on ESP32

from umqtt.simple import MQTTClient
import ujson

class MqttBridgeESP:
    '''
    Manages MQTT connection for ESP32 (MicroPython).
    Uses umqtt.simple library.
    '''
    
    def __init__(self, client_id, broker, port=1883):
        client_id = str(client_id)
        broker = str(broker)
        port = int(port)
        
        self.broker = broker
        self.port = port
        self.client = MQTTClient(client_id, broker, port)
        self.connected = False
        self.callback = None
    
    def set_callback(self, callback_function):
        # Set the function to call when a message arrives
        self.callback = callback_function
        self.client.set_callback(self.on_message)
    
    def connect(self):
        # Connect to the MQTT broker
        try:
            self.client.connect()
            self.connected = True
            print(f"MQTT connected to {self.broker}:{self.port}")
        except Exception as e:
            self.connected = False
            print(f"MQTT connect failed: {e}")
    
    def disconnect(self):
        # Disconnect from the MQTT broker
        try:
            self.client.disconnect()
        except:
            pass
        self.connected = False
    
    def subscribe(self, topic):
        # Subscribe to a topic
        topic = str(topic)
        try:
            self.client.subscribe(topic)
            print(f"Subscribed to: {topic}")
        except Exception as e:
            print(f"Subscribe failed: {e}")
    
    def publish_json(self, topic, payload):
        # Publish a dict as JSON
        topic = str(topic)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        raw = ujson.dumps(payload)
        self.client.publish(topic, raw)
        print(f"MQTT -> {topic}: {payload}")
    
    def publish(self, topic, message):
        # Publish a simple string message
        topic = str(topic)
        message = str(message)
        self.client.publish(topic, message)
    
    def on_message(self, topic, msg):
        # Called when a message arrives
        try:
            topic = topic.decode("utf-8")
            message = msg.decode("utf-8")
            print(f"MQTT <- {topic}: {message}")
            if self.callback:
                self.callback(topic, message)
        except Exception as e:
            print(f"Message error: {e}")
    
    def check_messages(self):
        # Call this in your main loop to check for new messages
        try:
            self.client.check_msg()
        except:
            pass
"""


MQTT = MqttBridge()


# -----------------------------
# Command helper functions used by the UI
# -----------------------------


# Send current eye state (enabled, GRB color, brightness) to the skull
def send_eyes():
    payload = {
        "type": "eyes",
        "enabled": STATE.eyes_enabled,
        "g": STATE.eyes_g,
        "r": STATE.eyes_r,
        "b": STATE.eyes_b,
        "brightness": STATE.eyes_brightness,
    }
    MQTT.publish_json(MQTT_TOPIC_CMD, payload)


# Clamp and send the neck servo angle
def send_neck(angle):
    angle = int(angle)
    angle = max(0, min(180, angle))
    STATE.neck_angle = angle
    MQTT.publish_json(MQTT_TOPIC_CMD, {"type": "neck", "angle": angle})


# Clamp and send the mouth servo angle
def send_mouth(angle):
    angle = int(angle)
    angle = max(STATE.mouth_min, min(STATE.mouth_max, angle))
    STATE.mouth_angle = angle
    MQTT.publish_json(MQTT_TOPIC_CMD, {"type": "mouth", "angle": angle})


# Ask the skull to stop any running animations or scenes
def send_stop_all():
    MQTT.publish_json(MQTT_TOPIC_CMD, {"type": "stop_all"})


# Demonstration async scene that moves mouth and eyes without blocking the UI
async def laugh_scene():
    if STATE.scene_running:
        log("Scene already running; ignoring.")
        return

    STATE.scene_running = True
    try:
        log("Scene: laugh start")
        MQTT.publish_json(
            MQTT_TOPIC_CMD, {"type": "scene", "name": "laugh", "action": "start"}
        )

        for _ in range(6):
            send_mouth(STATE.mouth_max)
            STATE.eyes_g, STATE.eyes_r, STATE.eyes_b = 0, 0, 255
            send_eyes()
            await asyncio.sleep(0.25)

            send_mouth(STATE.mouth_min)
            STATE.eyes_g, STATE.eyes_r, STATE.eyes_b = 255, 0, 0
            send_eyes()
            await asyncio.sleep(0.25)

        log("Scene: laugh end")
        MQTT.publish_json(
            MQTT_TOPIC_CMD, {"type": "scene", "name": "laugh", "action": "end"}
        )
    finally:
        STATE.scene_running = False


# -----------------------------
# NiceGUI user interface
# -----------------------------

ui.page_title("Skull Remote (NiceGUI)")

with ui.header().classes("items-center justify-between"):
    ui.label("Skull Remote Control").classes("text-xl font-bold")
    connection_badge = ui.badge("MQTT: connecting...").props("outline")

with ui.row().classes("w-full gap-4"):
    with ui.card().classes("w-full"):
        ui.label("Quick actions").classes("font-semibold")
        with ui.row().classes("gap-2"):
            ui.button(
                "Eyes ON",
                on_click=lambda: (setattr(STATE, "eyes_enabled", True), send_eyes()),
            )
            ui.button(
                "Eyes OFF",
                on_click=lambda: (setattr(STATE, "eyes_enabled", False), send_eyes()),
            )
            ui.button("Center neck (90°)", on_click=lambda: send_neck(90))
            ui.button("Mouth close", on_click=lambda: send_mouth(STATE.mouth_min))
            ui.button("STOP ALL", color="negative", on_click=send_stop_all)

    with ui.card().classes("w-full"):
        ui.label("Scenes").classes("font-semibold")
        ui.button(
            "Laugh demo (async)", on_click=lambda: asyncio.create_task(laugh_scene())
        )
        ui.label("Async scene keeps the UI responsive.").classes(
            "text-sm text-gray-600"
        )

with ui.tabs().classes("w-full") as tabs:
    tab_eyes = ui.tab("Eyes")
    tab_motors = ui.tab("Motors")
    tab_debug = ui.tab("Debug")

with ui.tab_panels(tabs, value=tab_eyes).classes("w-full"):
    with ui.tab_panel(tab_eyes):
        with ui.card().classes("w-full"):
            ui.label("Eyes (NeoPixel)").classes("font-semibold")

            color_picker = ui.color_input(
                label="Pick color (UI is RGB, sent as GRB)"
            ).props("format=rgb")
            brightness_slider = (
                ui.slider(min=0, max=255, value=STATE.eyes_brightness)
                .props("label")
                .classes("w-full")
            )

            with ui.row().classes("gap-2"):
                ui.button("Send eyes now", on_click=send_eyes)
                ui.button(
                    "Blink (receiver decides)",
                    on_click=lambda: MQTT.publish_json(
                        MQTT_TOPIC_CMD, {"type": "eyes", "action": "blink"}
                    ),
                )

            # Convert NiceGUI RGB value into GRB and send it
            def on_color_change(e):
                text = str(e.value or "")
                try:
                    inside = text[text.find("(") + 1 : text.find(")")]
                    r_str, g_str, b_str = [x.strip() for x in inside.split(",")]
                    r, g, b = int(r_str), int(g_str), int(b_str)
                except Exception:
                    r, g, b = 0, 0, 0

                STATE.eyes_g, STATE.eyes_r, STATE.eyes_b = g, r, b
                send_eyes()

            # Update brightness and resend eyes immediately
            def on_brightness_change(e):
                STATE.eyes_brightness = int(e.value)
                send_eyes()

            color_picker.on("update:model-value", on_color_change)
            brightness_slider.on("update:model-value", on_brightness_change)

    with ui.tab_panel(tab_motors):
        with ui.card().classes("w-full"):
            ui.label("Motors").classes("font-semibold")

            neck_slider = (
                ui.slider(min=0, max=180, value=STATE.neck_angle)
                .props("label")
                .classes("w-full")
            )
            mouth_slider = (
                ui.slider(
                    min=STATE.mouth_min,
                    max=STATE.mouth_max,
                    value=STATE.mouth_angle,
                )
                .props("label")
                .classes("w-full")
            )

            with ui.row().classes("gap-2"):
                ui.button("Send neck", on_click=lambda: send_neck(neck_slider.value))
                ui.button("Send mouth", on_click=lambda: send_mouth(mouth_slider.value))

            neck_slider.on(
                "update:model-value",
                lambda: send_neck(neck_slider.value),
            )

            mouth_slider.on(
                "update:model-value",
                lambda: send_mouth(mouth_slider.value),
            )

            ui.separator()
            ui.label("Tip").classes("font-semibold")
            ui.label("Live slider updates feel like direct remote control.").classes(
                "text-sm text-gray-600"
            )

    with ui.tab_panel(tab_debug):
        with ui.card().classes("w-full"):
            ui.label("Debug / Log").classes("font-semibold")
            log_area = ui.textarea(value="").props("readonly").classes("w-full")

            with ui.row().classes("gap-2"):
                ui.button(
                    "Clear log",
                    on_click=lambda: (LOG_LINES.clear(), log_area.set_value("")),
                )
                ui.button(
                    "Ping skull",
                    on_click=lambda: MQTT.publish_json(
                        MQTT_TOPIC_CMD, {"type": "ping"}
                    ),
                )

            ui.label("ACK or status messages from the skull will appear here.").classes(
                "text-sm text-gray-600"
            )


# -----------------------------
# Background refresh loop
# -----------------------------


# Periodically update connection badge and log area without blocking the UI
async def ui_refresh_loop():
    while True:
        connection_badge.set_text(
            "MQTT: connected" if MQTT.connected else "MQTT: disconnected"
        )
        log_area.set_value("\n".join(LOG_LINES[-120:]))
        await asyncio.sleep(0.2)


# Connect MQTT and start UI refresh when NiceGUI starts
@app.on_startup
async def on_startup():
    MQTT.connect()
    asyncio.create_task(ui_refresh_loop())
    log("NiceGUI started")


# Disconnect MQTT cleanly when the server shuts down
@app.on_shutdown
def on_shutdown():
    try:
        MQTT.disconnect()
    except Exception:
        pass


# -----------------------------
# Start NiceGUI server
# -----------------------------

ui.run(host=NICEGUI_HOST, port=NICEGUI_PORT, reload=False)
