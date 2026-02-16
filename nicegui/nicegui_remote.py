"""
nicegui_remote.py

Minimal NiceGUI remote with a visible on-page log window.
- Runs on http://127.0.0.1:8090 by default
- Publishes JSON commands over MQTT to a single topic
"""

from nicegui import ui
import paho.mqtt.client as mqtt
import json
import os
import time
import warnings


# Basic config
MQTT_BROKER = os.getenv("SKULL_MQTT_BROKER", "test.mosquitto.org")
MQTT_PORT = int(os.getenv("SKULL_MQTT_PORT", "1883"))
MQTT_TOPIC_CMD = os.getenv("SKULL_TOPIC_CMD", "1404-remote-sender")

# NiceGUI server config
NICEGUI_HOST = os.getenv(
    "NICEGUI_HOST", "127.0.0.1"
)  # Use "0.0.0.0" to open on your LAN IP
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# Silence the paho-mqtt callback API deprecation warning (safe to ignore for learning)
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module=r"paho\.mqtt\.client"
)

# MQTT client (keep it simple and stable)
client = mqtt.Client()

# Track MQTT connection so it starts once (script mode safe)
mqtt_started = False

# Store recent log lines for the UI
UI_LOG: list[str] = []

# Hold a reference to the UI log box (created inside the page)
log_box = None


# Add a timestamped log line to the terminal
def log_console(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


# Add a line to the UI log and keep it short
def log_ui(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    UI_LOG.append(f"[{timestamp}] {message}")
    if len(UI_LOG) > 80:
        UI_LOG.pop(0)


# Write a message to both terminal and the on-page log window (if it exists)
def log(message: str) -> None:
    global log_box

    log_console(message)
    log_ui(message)

    if log_box is not None:
        log_box.set_value("\n".join(UI_LOG))


# Connect MQTT the first time the page is opened (or the first time a command is sent)
def ensure_mqtt_started() -> None:
    global mqtt_started

    if mqtt_started:
        return

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
    client.loop_start()
    mqtt_started = True
    log(f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT} (topic: {MQTT_TOPIC_CMD})")


# Publish a JSON command to the skull (and ensure MQTT is connected)
def send_command(payload: dict) -> None:
    ensure_mqtt_started()

    client.publish(MQTT_TOPIC_CMD, json.dumps(payload).encode("utf-8"))
    log(f"Sent: {payload}")


# Send neck angle (0..180) as JSON
def send_neck(angle: int) -> None:
    angle = max(0, min(180, int(angle)))
    send_command({"type": "neck", "angle": angle})


# Send mouth angle (0..180) as JSON
def send_mouth(angle: int) -> None:
    angle = max(55, min(110, int(angle)))
    send_command({"type": "mouth", "angle": angle})


# Turn eyes on/off (receiver decides what that means)
def set_eyes(enabled: bool) -> None:
    send_command({"type": "eyes", "enabled": enabled})


# Handle "Eyes ON" button click without using lambda
def on_eyes_on() -> None:
    set_eyes(True)


# Handle "Eyes OFF" button click without using lambda
def on_eyes_off() -> None:
    set_eyes(False)


# Handle neck slider changes without relying on event arguments
def on_neck_changed() -> None:
    send_neck(neck_slider.value)


# Handle mouth slider changes without relying on event arguments
def on_mouth_changed() -> None:
    send_mouth(mouth_slider.value)


# Build the main page UI (NiceGUI script mode friendly)
# Build the main page UI (NiceGUI script mode friendly)
@ui.page("/")
def index() -> None:
    global log_box
    global neck_slider
    global mouth_slider

    # Ensure MQTT is connected before interacting with controls
    ensure_mqtt_started()
    with ui.card().classes("w-[500px] align-center justify-center"):
        # Main container card
        with ui.card().classes("w-full p-4 border border-gray-400 rounded"):
            # Card title
            ui.label("Skull Control").classes("text-lg font-bold")

            ui.separator()

            # Buttons row
            with ui.row().classes("gap-2"):
                ui.button("Eyes ON", on_click=on_eyes_on)
                ui.button("Eyes OFF", on_click=on_eyes_off)

            ui.separator()

            # Sliders
            ui.label("Neck angle")
            neck_slider = (
                ui.slider(min=0, max=180, value=90).props("label").classes("w-full")
            )
            neck_slider.on("update:model-value", on_neck_changed)

            ui.label("Mouth angle")
            mouth_slider = (
                ui.slider(min=55, max=110, value=75).props("label").classes("w-full")
            )
            mouth_slider.on("update:model-value", on_mouth_changed)

            ui.separator()

            # Visible log window under the sliders
            log_box = (
                ui.textarea(value="", label="Log")
                .props("readonly")
                .classes("w-full h-44 border border-gray-400 rounded bg-white")
            )

    # Initial message after log_box exists
    log("UI loaded")


# Use reload when working locally to develop a interface. Don't use reload when in "production mode"
ui.run(host=NICEGUI_HOST, port=NICEGUI_PORT, reload=True)
