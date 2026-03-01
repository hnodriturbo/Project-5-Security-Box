"""
nicegui_dashboard.py

Main Dashboard for ESP32 Security Box Control
- Connects to MQTT broker (with fallback support)
- Displays log box for all events
- Sends structured commands to ESP32
- Receives and displays data from ESP32

Uses nicegui_broker.py for all MQTT communication.

"""

# -----------------------------
# Imports
# -----------------------------
import os
import sys
import asyncio
from datetime import datetime
from nicegui import ui, app

# Import our broker module
import nicegui_broker as broker

# -----------------------------
# NiceGUI Server Configuration
# -----------------------------

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "127.0.0.1")
# Use "0.0.0.0" to open on LAN

# Custom port (avoiding conflicts with Apache/Postgres)
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# Dashboard title
DASHBOARD_TITLE = "ESP32 Security Box Dashboard"

# -----------------------------
# App State
# -----------------------------

MAX_LOG_LINES = 100  # Keep last 100 log lines
log_lines = []  # In-memory log storage

# Received data storage
received_data = {}  # Latest data from ESP32

# UI element references
log_box_container = None
status_label = None
data_display = None


# -----------------------------
# Logging Functions
# -----------------------------
def add_log(message: str, level: str = "info"):
    """
    Add a message to the log box.

    Args:
        message: The log message
        level: Log level (info, success, warning, error)
    """
    timestamp = datetime.now().strftime("%H:%M:%S")

    # Add level prefix for non-info messages
    if level == "success":
        prefix = "[OK]"
    elif level == "warning":
        prefix = "[WARN]"
    elif level == "error":
        prefix = "[ERR]"
    else:
        prefix = ""

    if prefix:
        log_entry = f"{timestamp} {prefix} {message}"
    else:
        log_entry = f"{timestamp} - {message}"

    log_lines.append(log_entry)

    # Keep only the last MAX_LOG_LINES
    del log_lines[:-MAX_LOG_LINES]

    # Refresh the log box display
    render_log_box.refresh()


def clear_log():
    """Clear all log entries."""
    log_lines.clear()
    render_log_box.refresh()
    add_log("Log cleared")


@ui.refreshable
def render_log_box():
    """
    Render the log box content.
    Uses @ui.refreshable for efficient updates.
    """
    if not log_lines:
        ui.label("Log is empty - waiting for events...").classes(
            "text-xs opacity-70 italic"
        )
        return

    # Show logs in reverse order (newest first)
    for line in reversed(log_lines):
        # Color code based on content
        if "[ERR]" in line:
            classes = "text-xs text-red-500"
        elif "[WARN]" in line:
            classes = "text-xs text-yellow-600"
        elif "[OK]" in line:
            classes = "text-xs text-green-600"
        else:
            classes = "text-xs"

        ui.label(line).classes(classes)


# -----------------------------
# Data Handling
# -----------------------------
def handle_received_data(data: dict):
    """
    Handle data received from ESP32 via MQTT.
    This is called by the broker module.

    Args:
        data: Parsed JSON data from ESP32
    """
    global received_data

    # Store the latest data
    received_data = data

    # Log what we received
    if "raw" in data:
        add_log(f"Raw data: {data['raw']}")
    else:
        # Format nicely for common data types
        if "temperature" in data:
            add_log(f"Temperature: {data['temperature']}°C", "success")
        if "humidity" in data:
            add_log(f"Humidity: {data['humidity']}%", "success")
        if "status" in data:
            add_log(f"ESP32 Status: {data['status']}", "info")
        if "event" in data:
            add_log(f"Event: {data['event']}", "info")

    # Refresh the data display if it exists
    if data_display:
        render_data_display.refresh()


@ui.refreshable
def render_data_display():
    """
    Render the current data from ESP32.
    """
    if not received_data:
        ui.label("No data received yet").classes("text-sm opacity-70")
        return

    # Display key-value pairs
    for key, value in received_data.items():
        if key != "raw":
            with ui.row().classes("gap-2"):
                ui.label(f"{key}:").classes("text-sm font-medium")
                ui.label(f"{value}").classes("text-sm")


# -----------------------------
# Command Functions
# -----------------------------
def send_lock_command():
    """Send lock command to ESP32."""
    asyncio.create_task(broker.send_command("lock"))
    add_log("Sending LOCK command...")


def send_unlock_command():
    """Send unlock command to ESP32."""
    asyncio.create_task(broker.send_command("unlock"))
    add_log("Sending UNLOCK command...")


def send_led_on():
    """Send LED on command to ESP32."""
    asyncio.create_task(broker.send_command("led", "on"))
    add_log("Sending LED ON command...")


def send_led_off():
    """Send LED off command to ESP32."""
    asyncio.create_task(broker.send_command("led", "off"))
    add_log("Sending LED OFF command...")


def send_status_request():
    """Request current status from ESP32."""
    asyncio.create_task(broker.send_command("status_request"))
    add_log("Requesting status from ESP32...")


def send_custom_command(cmd_input, value_input):
    """
    Send a custom command with optional value.

    Args:
        cmd_input: The command input element
        value_input: The value input element
    """
    cmd = cmd_input.value.strip()
    value = value_input.value.strip()

    if not cmd:
        add_log("Error: Command cannot be empty", "error")
        return

    # Parse value if it looks like a number
    if value:
        try:
            if "." in value:
                value = float(value)
            else:
                value = int(value)
        except ValueError:
            pass  # Keep as string
    else:
        value = None

    asyncio.create_task(broker.send_command(cmd, value))
    add_log(f"Sending custom command: {cmd} = {value}")

    # Clear inputs
    cmd_input.value = ""
    value_input.value = ""


# -----------------------------
# UI Status Updates
# -----------------------------
def update_connection_status():
    """Update the connection status display."""
    status = broker.get_broker_status()

    if status["connected"]:
        if status_label:
            status_label.set_text(f"Connected to: {status['active_broker']}")
            status_label.classes(remove="text-red-500", add="text-green-600")
    else:
        if status_label:
            status_label.set_text("Disconnected - Reconnecting...")
            status_label.classes(remove="text-green-600", add="text-red-500")


# -----------------------------
# Main Dashboard Page
# -----------------------------
@ui.page("/")
def index():
    """Main dashboard page."""
    global status_label, data_display

    # Page container with dark mode support
    with ui.column().classes("w-full max-w-4xl mx-auto p-4 space-y-4"):

        # -----------------------------
        # Header Section
        # -----------------------------
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(DASHBOARD_TITLE).classes("text-xl font-bold")
                status_label = ui.label("Connecting...").classes(
                    "text-sm text-yellow-600"
                )

        # -----------------------------
        # Control Buttons Section
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Quick Commands").classes("text-lg font-semibold mb-2")

            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("LOCK", on_click=send_lock_command).classes(
                    "bg-red-500 text-white"
                )
                ui.button("UNLOCK", on_click=send_unlock_command).classes(
                    "bg-green-500 text-white"
                )
                ui.button("LED ON", on_click=send_led_on).classes("bg-yellow-500")
                ui.button("LED OFF", on_click=send_led_off).classes(
                    "bg-gray-500 text-white"
                )
                ui.button("Request Status", on_click=send_status_request).classes(
                    "bg-blue-500 text-white"
                )

        # -----------------------------
        # Custom Command Section
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Custom Command").classes("text-lg font-semibold mb-2")

            with ui.row().classes("w-full gap-2 items-end"):
                cmd_input = ui.input(
                    label="Command", placeholder="e.g., led, motor, status"
                ).classes("flex-1")

                value_input = ui.input(
                    label="Value (optional)", placeholder="e.g., on, 90, 255"
                ).classes("flex-1")

                ui.button(
                    "Send", on_click=lambda: send_custom_command(cmd_input, value_input)
                ).classes("bg-purple-500 text-white")

        # -----------------------------
        # Data Display Section
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("ESP32 Data").classes("text-lg font-semibold mb-2")
            data_display = render_data_display()

        # -----------------------------
        # Log Box Section (Main Feature!)
        # -----------------------------
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("Event Log").classes("text-lg font-semibold")
                ui.button("Clear Log", on_click=clear_log).classes("text-xs").props(
                    "flat dense"
                )

            # Scrollable log container
            with ui.scroll_area().classes("w-full h-64 border rounded p-2"):
                render_log_box()

        # -----------------------------
        # Broker Info Section
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Broker Configuration").classes("text-md font-semibold mb-2")

            status = broker.get_broker_status()
            ui.label(f"Primary: {status['primary_broker']}").classes("text-xs")
            ui.label(f"Fallback: {status['fallback_broker']}").classes("text-xs")
            ui.label(f"Topic: {status['topic']}").classes("text-xs")

    # -----------------------------
    # UI Update Timer
    # -----------------------------
    # Update connection status every 2 seconds
    ui.timer(2.0, update_connection_status)

    # Initial log entry
    add_log("Dashboard loaded")


# -----------------------------
# Startup - Connect broker callbacks
# -----------------------------
async def setup_broker():
    """Set up broker callbacks and start receiver."""
    # Set log callback so broker messages appear in our log
    broker.set_log_callback(add_log)

    # Set data callback so we receive ESP32 data
    broker.set_data_callback(handle_received_data)

    # Start the receiver as a background task
    asyncio.create_task(broker.start_receiver())


# Register the MQTT receiver to start with the app
app.on_startup(setup_broker)


# -----------------------------
# Windows Event Loop Policy
# -----------------------------
# CRITICAL: Set event loop policy BEFORE ui.run() on Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# -----------------------------
# Run the Dashboard
# -----------------------------
ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=True,
    title=DASHBOARD_TITLE,
)
