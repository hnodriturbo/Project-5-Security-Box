"""
nicegui_part_1.py

Part 1 NiceGUI page
5+ Control elements
1 data element

Events + Actions using buttons, sliders

Layout using cards, rows and colums

"""

# -----------------------------
# Default imports for this part
# -----------------------------
import os
from datetime import datetime
from nicegui import ui

# -----------------------------
# NiceGUI server config
# -----------------------------

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "127.0.0.1")
# Use "0.0.0.0" to open on LAN

# Custom port because Apache/Postgres use the default port
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# List for the log lines (MY DATA ELEMENT)
# -----------------------------
# App state
# -----------------------------

MAX_LOG_LINES = 50  # keep last 50 log lines
log_lines = []  # in-memory log storage
log_box = None  # textarea reference (set in index)

# Allowed NiceGUI notification types
NOTIFY_TYPES = {
    "positive",
    "negative",
    "warning",
    "info",
    "ongoing",
}


# -----------------------------
# Add a single log to the log box and refresh it
# -----------------------------
def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")  # Time with HH:MM:SS
    log_lines.append(f"{timestamp} - {message}")
    del log_lines[:-MAX_LOG_LINES]  # Only keep last 20 logs
    render_log_box.refresh()


# -----------------------------
# Show notification with color and write to log
# -----------------------------
def notify_and_log(message, level="info"):
    if level == "positive":
        ui.notify(message, type="positive")
    elif level == "negative":
        ui.notify(message, type="negative")
    elif level == "warning":
        ui.notify(message, type="warning")
    elif level == "ongoing":
        ui.notify(message, type="ongoing")
    else:
        ui.notify(message, type="info")

    add_log(message)


# -----------------------------
# Clear the log
# -----------------------------
def clear_log():
    log_lines.clear()
    render_log_box.refresh()


# -----------------------------
# Log box (data element)
# -----------------------------
@ui.refreshable
def render_log_box():
    if not log_lines:
        ui.label("Log is empty").classes("text-xs opacity-70")
        return

    # Show the latest messages in the log box
    for line in reversed(log_lines):
        ui.label(line).classes("text-xs")


# -----------------------------
# Button actions
# -----------------------------
def button_a_clicked():
    notify_and_log("Button A Clicked !!!", "positive")


def button_b_clicked():
    notify_and_log("Button B Clicked !!!", "info")


# -----------------------------
# Slider handlers
# -----------------------------
def slider_1_changed(e):
    value = int(e.value)
    slider_1_label.set_text(f"Slider 1: {value}")
    add_log(f"Slider 1 changed to {value}")


def slider_2_changed(e):
    value = int(e.value)
    slider_2_label.set_text(f"Slider 2: {value}")
    add_log(f"Slider 2 changed to {value}")


# -----------------------------
# Main page
# -----------------------------
@ui.page("/")
def index():

    global slider_1_label
    global slider_2_label

    with ui.card().classes("max-w-5xl mx-auto p-6 space-y-4"):

        ui.label("NiceGUI – Part 1").classes("text-lg font-bold")
        ui.label("Buttons, sliders, events and a log (data element)").classes("text-sm")

        # -----------------------------
        # Controls card (top)
        # -----------------------------
        with ui.card():
            ui.label("Controls").classes("text-md font-semibold")

            with ui.row():
                ui.button("Button A", on_click=button_a_clicked)
                ui.button("Button B", on_click=button_b_clicked)
                ui.button("Clear Logs", on_click=clear_log)

            # Seperate is not a known attribute
            # ui.seperator()
            ui.element("hr")

        # -----------------------------
        # Controls (top)
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Controls").classes("text-md font-semibold")

            slider_1_label = ui.label("Slider 1: 0")
            slider_1 = ui.slider(min=0, max=10, value=5)
            slider_1.on("update:model-value", slider_1_changed)

            # Seperate is not a known attribute
            # ui.seperator()
            ui.element("hr")

            slider_2_label = ui.label("Slider 2: 0")
            slider_2 = ui.slider(min=0, max=10, value=5)
            slider_2.on("update:model-value", slider_2_changed)

        # -----------------------------
        # Log (data element, bottom)
        # -----------------------------
        with ui.card().classes("w-full"):
            ui.label("Log").classes("text-md font-semibold")
            ui.label("Shows events and actions").classes("text-sm opacity-70")

            with ui.element("div").classes(
                "w-full h-56 overflow-auto border rounded p-2"
            ):
                render_log_box()

    # Start by adding the page loaded log
    add_log("Page loaded")


# -----------------------------
# Run NiceGUI
# -----------------------------
ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=True,
    title="NiceGUI Part 1",
)
