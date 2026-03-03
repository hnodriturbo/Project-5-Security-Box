"""
nicegui_part1_page.py

Part 1 NiceGUI page.
Shows:
- 5+ control elements
- 1 data element (log box)
- events + actions
- clean layout with cards, rows, and columns

No ESP, no MQTT, no asyncio.
"""

import os
from datetime import datetime
from nicegui import ui


# -----------------------------
# App state
# -----------------------------

log_lines = []  # stores log messages (data element)


# -----------------------------
# Logging functions
# -----------------------------


# Add a timestamped line to the log and refresh the log UI
def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_lines.append(f"{timestamp} - {message}")
    del log_lines[:-20]  # keep last 20 log entries
    render_log_box.refresh()


# Show colored notification and write message to log
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
# Log box (data element)
# -----------------------------


@ui.refreshable
def render_log_box():
    if not log_lines:
        ui.label("Log is empty").classes("text-xs opacity-70")
        return

    # Show newest messages at the top
    for line in reversed(log_lines):
        ui.label(line).classes("text-xs")


# -----------------------------
# Main page
# -----------------------------


@ui.page("/")
def index():
    ui.label("NiceGUI – Part 1 Demo Page").classes("text-2xl font-bold")
    ui.label(
        "Demonstrates controls, events, actions, and a data element (log)."
    ).classes("text-sm opacity-70")

    with ui.row().classes("w-full"):
        # LEFT SIDE: Log
        with ui.column().classes("w-1/2"):
            with ui.card().classes("w-full"):
                ui.label("Log").classes("text-lg font-semibold")
                ui.label("This log updates when actions happen.").classes(
                    "text-sm opacity-70"
                )

                # Bordered log area
                with ui.element("div").classes(
                    "w-full h-56 overflow-auto border rounded p-2"
                ):
                    render_log_box()

                with ui.row():
                    ui.button(
                        "Test notification",
                        on_click=lambda: notify_and_log(
                            "This is a test notification", "positive"
                        ),
                    )
                    ui.button(
                        "Clear log",
                        on_click=lambda: (log_lines.clear(), render_log_box.refresh()),
                    )

        # RIGHT SIDE: Controls
        with ui.column().classes("w-1/2"):
            with ui.card().classes("w-full"):
                ui.label("Controls").classes("text-lg font-semibold")
                ui.label("Examples of control elements and events.").classes(
                    "text-sm opacity-70"
                )

                # 1) Input + Button
                name_input = ui.input("Name", placeholder="Type your name...")

                def greet():
                    name = name_input.value or "stranger"
                    notify_and_log(f"Hello {name}!", "positive")

                ui.button("Greet", on_click=greet)

                ui.separator()

                # 2) Slider
                slider_value_label = ui.label("Slider value: 0").classes("text-sm")
                slider = ui.slider(min=0, max=100, value=0)

                def on_slider_change(e):
                    value = int(e.value)
                    slider_value_label.set_text(f"Slider value: {value}")
                    add_log(f"Slider moved to {value}")

                slider.on("update:model-value", on_slider_change)

                ui.separator()

                # 3) Switch
                power_switch = ui.switch("Power")

                def on_power_change(e):
                    state = "ON" if e.value else "OFF"
                    notify_and_log(f"Power switched {state}", "warning")

                power_switch.on("update:model-value", on_power_change)

                # 4) Checkbox
                agree_checkbox = ui.checkbox("I agree")

                def on_agree_change(e):
                    state = "checked" if e.value else "unchecked"
                    add_log(f"Agreement {state}")

                agree_checkbox.on("update:model-value", on_agree_change)

                # 5) Select dropdown
                color_select = ui.select(
                    label="Pick a color",
                    options=["Red", "Green", "Blue"],
                    value="Green",
                )

                def on_color_change(e):
                    notify_and_log(f"Color selected: {e.value}", "info")

                color_select.on("update:model-value", on_color_change)

                ui.separator()

                # 6) Textarea + Button
                notes_area = ui.textarea(
                    "Notes", placeholder="Write something..."
                ).classes("w-full")

                def save_notes():
                    length = len(notes_area.value or "")
                    notify_and_log("Notes saved", "positive")
                    add_log(f"Notes length: {length} characters")

                ui.button("Save notes", on_click=save_notes)

    add_log("Page loaded")


# -----------------------------
# NiceGUI server config
# -----------------------------

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "127.0.0.1")  # use 0.0.0.0 for LAN
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))  # avoid Apache/Postgres ports

ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=True,
    title="NiceGUI Part 1 – Controls, Events, Log",
)
