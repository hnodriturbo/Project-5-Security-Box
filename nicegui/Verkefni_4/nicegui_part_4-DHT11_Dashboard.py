"""
nicegui_part_4-DHT11_Dashboard.py

Part 4 - DHT11 Dashboard
- Receives temperature and humidity from ESP32 via MQTT
- Displays current values with labels
- Shows last 10 readings in a line chart
- Uses logger utility pattern from part 1

"""

# -----------------------------
# Default imports for this part
# -----------------------------
"""
import os
import json
from datetime import datetime
import asyncio
from aiomqtt import Client
from nicegui import ui, app
"""
import os
import json
from datetime import datetime
import sys
import asyncio

from aiomqtt import Client
from nicegui import ui, app

# -----------------------------
# NiceGUI server config
# -----------------------------

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "127.0.0.1")
# Use "0.0.0.0" to open on LAN

# Custom port because Apache/Postgres use the default port
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# -----------------------------
# MQTT config
# -----------------------------

# MQTT_BROKER = "test.mosquitto.org"
MQTT_BROKER = "broker.emqx.io"
MQTT_TOPIC = "1404TOPIC"

# -----------------------------
# App state
# -----------------------------
MAX_LOG_LINES = 50  # Keep last 50 log lines
MAX_DATA_POINTS = 10  # Keep last 10 readings for charting

# Lists
log_lines = []
temperature_history = []  # Last 10 temperature readings
humidity_history = []  # Last 10 humidity readings
time_labels = []  # Time stampts for the chart

# Current Values
current_temp = None
current_humidity = None

# UI referances
temp_label = None
humidity_label = None
chart = None


# -----------------------------
# MY AWESOME LOGGER UTILITY
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
# Data handling
# -----------------------------
def add_data_point(temp, humidity):
    # Globalize current_temp and current_humidity for updating their values
    global current_temp, current_humidity

    # Put current values into basic variables
    current_temp = temp
    current_humidity = humidity

    # Add to history of the chart
    timestamp = datetime.now().strftime("%H:%M:%S")
    time_labels.append(timestamp)
    temperature_history.append(temp)
    humidity_history.append(humidity)

    # Make sure to keep only the last 10 readings
    del time_labels[:-MAX_DATA_POINTS]
    del temperature_history[:-MAX_DATA_POINTS]
    del humidity_history[:-MAX_DATA_POINTS]


def update_chart():
    if chart is None:
        return

    chart.options["xAxis"]["data"] = time_labels
    chart.options["series"][0]["data"] = temperature_history
    chart.options["series"][1]["data"] = humidity_history
    chart.update()


# -----------------------------
# MQTT receiver
# -----------------------------
async def mottaka_gagna():
    # Globalize current_temp and current_humidity for updating their values
    global current_temp, current_humidity

    # Add log to log box
    add_log(f"Connecting to topic: {MQTT_TOPIC}")

    # Main async function
    async with Client(MQTT_BROKER) as client:
        await client.subscribe(MQTT_TOPIC)
        add_log(f"Subscribed to topic: {MQTT_TOPIC}")

        async for message in client.messages:
            try:
                payload = message.payload.decode()
                data = json.loads(payload)

                # Get temp and humidity from the json data
                temp = data.get("hitastig")
                humidity = data.get("rakastig")

                # Add temp and humidity only if we have value to the chart
                if temp is not None and humidity is not None:
                    add_data_point(temp, humidity)
                    add_log(f"Received temperature: {temp}°C, Humidity {humidity}%")
            except Exception as e:
                add_log(f"Error: {e}")


# -----------------------------
# UI update timer callback
# -----------------------------
def update_ui():
    if temp_label is not None and current_temp is not None:
        temp_label.set_text(f"{current_temp}°C")

    if humidity_label is not None and current_humidity is not None:
        humidity_label.set_text(f"{current_humidity}%")

    update_chart()


# -----------------------------
# Main page
# -----------------------------
@ui.page("/")
def index():
    # Globalize to get and update info
    global temp_label, humidity_label, chart

    with ui.card().classes("max-w-6xl w-full mx-auto p-6 space-y-4"):

        ui.label("NiceGUI - Part 4: DHT 11 Dashboard").classes(
            "w-full text-center text-lg font-bold"
        )
        ui.label("Temperature and humidity received from ESP32 via MQTT").classes(
            "w-full text-center text-sm"
        )

        # -----------------------------
        # Current values card
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Current readings").classes(
                "w-full text-center text-md font-semibold"
            )

            with ui.row().classes("w-full justify-around"):
                # Temperature display
                with ui.column().classes("items-center"):
                    ui.label("Temperature").classes("text-sm")
                    temp_label = ui.label("--°C").classes(
                        "text-4xl font-bold text-red-500"
                    )

                # Humidity display
                with ui.column().classes("items-center"):
                    ui.label("Humidity").classes("text-sm")
                    humidity_label = ui.label("--%").classes(
                        "text-4xl font-bold text-blue-500"
                    )

        # -----------------------------
        # Chart card
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Last 10 readings").classes(
                "w-full text-md font-semibold text-center"
            )

            chart = ui.echart(
                {
                    "grid": {
                        "left": "3%",
                        "right": "3%",
                        "bottom": "10%",
                        "top": "15%",
                        "containLabel": True,
                    },
                    "xAxis": {
                        "type": "category",
                        "data": [],
                    },
                    "yAxis": {
                        "type": "value",
                    },
                    "legend": {
                        "data": ["Temperature (°C)", "Humidity (%)"],
                        "top": "2%",
                    },
                    "series": [
                        {
                            "name": "Temperature (°C)",
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "itemStyle": {"color": "#ef4444"},
                        },
                        {
                            "name": "Humidity (%)",
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "itemStyle": {"color": "#3b82f6"},
                        },
                    ],
                    "tooltip": {
                        "trigger": "axis",
                    },
                }
            ).style("width: 100%; height: 300px;")

        # -----------------------------
        # Log card (OUTSIDE the row now)
        # -----------------------------
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("Log").classes("text-md font-semibold")
                ui.button("Clear", on_click=clear_log).props("size=sm")

            with ui.element("div").classes(
                "w-full h-40 overflow-auto border rounded p-2"
            ):
                render_log_box()

        # Timer to update UI every second (outside all cards)
        ui.timer(1.0, update_ui)

        # Initial log
        add_log("Dashboard loaded")


# -----------------------------
# Startup
# -----------------------------
app.on_startup(mottaka_gagna)

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
    title="NiceGUI Part 4 - DHT11 Dashboard",
)
