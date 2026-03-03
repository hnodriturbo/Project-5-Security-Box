"""
nicegui_part_3-Motor_Control.py

Part 3 of V4.md - Control ESP32 motors from NiceGUI
- Two text inputs + button to send motor angles
- Joystick control for motors
- Display current motor status

"""

# -----------------------------
# Default imports for this part
# -----------------------------
import os
import sys
import json
from datetime import datetime
import asyncio
from aiomqtt import Client
from nicegui import ui

# -----------------------------
# NiceGUI server config
# -----------------------------

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "127.0.0.1")
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# -----------------------------
# MQTT config
# -----------------------------

# MQTT_BROKER = "test.mosquitto.org"
MQTT_BROKER = "broker.emqx.io"
MQTT_TOPIC_MOTORS = "1404TOPIC_MOTORS"

# -----------------------------
# Servo limits (matching ESP32)
# -----------------------------

NECK_MIN = 0
NECK_MAX = 180
NECK_START = 90

MOUTH_MIN = 10
MOUTH_MAX = 50
MOUTH_START = 10

# -----------------------------
# App state
# -----------------------------

MAX_LOG_LINES = 50
log_lines = []

# Motor angles for input binding
motor_input = {
    "neck": NECK_START,
    "mouth": MOUTH_START,
}

# Joystick axis enable/disable
joystick_settings = {
    "neck_enabled": True,
    "mouth_enabled": False,
}

# UI references for status display
neck_status_label = None
mouth_status_label = None


# -----------------------------
# Logger utility
# -----------------------------
def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_lines.append(f"{timestamp} - {message}")
    del log_lines[:-MAX_LOG_LINES]
    render_log_box.refresh()


def clear_log():
    log_lines.clear()
    render_log_box.refresh()


@ui.refreshable
def render_log_box():
    if not log_lines:
        ui.label("Log is empty").classes("text-xs opacity-70")
        return

    for line in reversed(log_lines):
        ui.label(line).classes("text-xs")


# -----------------------------
# Update status labels
# -----------------------------
def update_status_display(neck_angle, mouth_angle):
    if neck_status_label:
        neck_status_label.set_text(f"{neck_angle}°")
    if mouth_status_label:
        mouth_status_label.set_text(f"{mouth_angle}°")


# -----------------------------
# Send motor command via MQTT
# -----------------------------
async def send_motor_command(neck_angle, mouth_angle):
    # Clamp to limits
    neck_angle = max(NECK_MIN, min(NECK_MAX, int(neck_angle)))
    mouth_angle = max(MOUTH_MIN, min(MOUTH_MAX, int(mouth_angle)))

    # Update input state
    motor_input["neck"] = neck_angle
    motor_input["mouth"] = mouth_angle

    # Create payload
    payload = {
        "motor1": neck_angle,
        "motor2": mouth_angle,
    }

    # Send via MQTT
    try:
        async with Client(MQTT_BROKER) as client:
            await client.publish(MQTT_TOPIC_MOTORS, json.dumps(payload).encode())
            add_log(f"Sent: Neck={neck_angle}°, Mouth={mouth_angle}°")
    except Exception as error:
        add_log(f"MQTT Error: {error}")

    # Update display
    update_status_display(neck_angle, mouth_angle)


# -----------------------------
# Button click handler
# -----------------------------
def send_button_clicked():
    neck_angle = int(motor_input["neck"])
    mouth_angle = int(motor_input["mouth"])
    asyncio.create_task(send_motor_command(neck_angle, mouth_angle))


# -----------------------------
# Joystick handlers
# -----------------------------
def joystick_moved(event):
    neck_angle = motor_input["neck"]
    mouth_angle = motor_input["mouth"]

    if joystick_settings["neck_enabled"]:
        neck_center = (NECK_MIN + NECK_MAX) // 2
        neck_range = (NECK_MAX - NECK_MIN) // 2
        neck_angle = int(neck_center + (event.x * neck_range))

    if joystick_settings["mouth_enabled"]:
        mouth_center = (MOUTH_MIN + MOUTH_MAX) // 2
        mouth_range = (MOUTH_MAX - MOUTH_MIN) // 2
        mouth_angle = int(mouth_center + (event.y * mouth_range))

    asyncio.create_task(send_motor_command(neck_angle, mouth_angle))


def joystick_released(_):
    if joystick_settings["neck_enabled"]:
        neck_angle = NECK_START
    else:
        neck_angle = motor_input["neck"]

    if joystick_settings["mouth_enabled"]:
        mouth_angle = MOUTH_START
    else:
        mouth_angle = motor_input["mouth"]

    asyncio.create_task(send_motor_command(neck_angle, mouth_angle))


# -----------------------------
# Main page
# -----------------------------
@ui.page("/")
def index():
    global neck_status_label, mouth_status_label

    with ui.card().classes("max-w-7xl w-full mx-auto p-6 space-y-4"):

        ui.label("NiceGUI - Part 3: Motor Control").classes("text-lg font-bold")
        ui.label("Control ESP32 servos via MQTT").classes("text-sm opacity-70")

        # -----------------------------
        # Motor status card
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Servo Status").classes("text-md font-semibold")

            with ui.row().classes("w-full justify-around"):
                with ui.column().classes("items-center"):
                    ui.label("Neck").classes("text-sm")
                    ui.label(f"{NECK_MIN}° - {NECK_MAX}°").classes("text-xs opacity-70")
                    neck_status_label = ui.label(f"{NECK_START}°").classes(
                        "text-4xl font-bold text-green-500"
                    )

                with ui.column().classes("items-center"):
                    ui.label("Mouth").classes("text-sm")
                    ui.label(f"{MOUTH_MIN}° - {MOUTH_MAX}°").classes(
                        "text-xs opacity-70"
                    )
                    mouth_status_label = ui.label(f"{MOUTH_START}°").classes(
                        "text-4xl font-bold text-purple-500"
                    )

        # -----------------------------
        # Method 1: Manual input
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Method 1: Manual Input").classes("text-md font-semibold")

            with ui.row().classes("w-full items-end gap-4"):
                ui.number(
                    label=f"Neck ({NECK_MIN}-{NECK_MAX})",
                    min=NECK_MIN,
                    max=NECK_MAX,
                ).bind_value(motor_input, "neck").classes("w-48").on(
                    "keydown.enter", send_button_clicked
                )

                ui.number(
                    label=f"Mouth ({MOUTH_MIN}-{MOUTH_MAX})",
                    min=MOUTH_MIN,
                    max=MOUTH_MAX,
                ).bind_value(motor_input, "mouth").classes("w-48").on(
                    "keydown.enter", send_button_clicked
                )

                ui.button("Send", on_click=send_button_clicked).classes("bg-blue-500")

        # -----------------------------
        # Method 2: Joystick
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Method 2: Joystick Control").classes("text-md font-semibold")

            ui.checkbox("Enable Neck (X-axis)").bind_value(
                joystick_settings, "neck_enabled"
            )
            ui.checkbox("Enable Mouth (Y-axis)").bind_value(
                joystick_settings, "mouth_enabled"
            )

            with ui.row().classes("w-full justify-center"):
                ui.joystick(
                    color="blue",
                    size=300,
                    on_move=joystick_moved,
                    on_end=joystick_released,
                    throttle=0.1,
                    options={
                        "restOpacity": 1,
                        "mode": "static",
                        "position": {"left": "50%", "top": "50%"},
                    },
                ).classes("bg-slate-200 rounded-full").style(
                    "width: 320px; height: 320px;"
                )

        # -----------------------------
        # Log card
        # -----------------------------
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("Log").classes("text-md font-semibold")
                ui.button("Clear", on_click=clear_log).props("size=sm")

            with ui.element("div").classes(
                "w-full h-40 overflow-auto border rounded p-2"
            ):
                render_log_box()

    add_log("Page loaded")


# -----------------------------
# CRITICAL: Set event loop policy JUST before ui.run() on Windows
# -----------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# -----------------------------
# Run NiceGUI
# -----------------------------
ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=True,
    title="NiceGUI Part 3 - Motor Control",
)
