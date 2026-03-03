# ==========================================
# file: dashboard.py  (runs on Raspberry Pi)
# ==========================================
#
# Purpose:
# - NiceGUI web dashboard for the Security Box.
# - Access gate: user types code before controls appear.
# - Event log is the main feature — shows everything happening on the box.
# - All commands go through publish_queue (never inline publish).
#
# Run on the Pi:
#   pip install nicegui aiomqtt
#   python dashboard.py
#   Open in browser: http://10.201.48.7:8090
#
# File structure:
#   config.py        - broker address, topics, access code
#   mqtt_handler.py  - MQTT loops run in separate thread with SelectorEventLoop
#   dashboard.py     - this file, UI only
# ==========================================

# --------------------------------------------------
# NiceGUI imports
# --------------------------------------------------
from nicegui import ui, app

# Import shared state, log, queue and background loops from mqtt_handler
import mqtt_handler as mqtt
from config import ACCESS_CODE, NICEGUI_HOST, NICEGUI_PORT

# --------------------------------------------------
# Dashboard-level state
# --------------------------------------------------
dashboard_unlocked = False  # True after correct access code is entered

# UI element references — set during page build, updated by ui.timer
ref_status_badge = None
ref_rfid_label = None
ref_unlock_button = None


# --------------------------------------------------
# update_ui() — called every 0.5s by ui.timer
# Reads shared state from mqtt_handler and refreshes UI elements
# --------------------------------------------------
def update_ui():
    # Update broker connection badge
    if ref_status_badge is not None:
        if mqtt.state["mqtt_connected"]:
            ref_status_badge.set_text("● MQTT Connected")
            ref_status_badge.props("color=positive outline")
        else:
            ref_status_badge.set_text("○ MQTT Offline")
            ref_status_badge.props("color=negative outline")

    # Update last RFID event label
    if ref_rfid_label is not None:
        rfid = mqtt.state.get("last_rfid")
        if rfid:
            color = "text-green-700" if rfid["result"] == "ALLOWED" else "text-red-600"
            text = "[{}]  {}  @ {}".format(rfid["result"], rfid["display"], rfid["ts"])
            ref_rfid_label.set_text(text)
            ref_rfid_label.classes(add=color)


# --------------------------------------------------
# Refreshable log renderer
# Called by ui.timer every 0.5s — renders newest entries at top
# --------------------------------------------------
@ui.refreshable
def render_log():
    if not mqtt.log_lines:
        ui.label("Waiting for events...").classes("text-xs text-gray-400 italic")
        return

    # Reversed so newest is at the top of the scroll area
    for line in reversed(mqtt.log_lines):
        # Color-code lines based on content keywords
        if "DENIED" in line or "error" in line.lower() or "fail" in line.lower():
            css = "text-xs font-mono text-red-500"
        elif "ALLOWED" in line or "SENT" in line or "connected" in line.lower():
            css = "text-xs font-mono text-green-700"
        elif "RAW IN" in line:
            css = "text-xs font-mono text-blue-500"
        else:
            css = "text-xs font-mono text-gray-700"

        ui.label(line).classes(css)


# ======================================================
# PAGE DEFINITION
# NiceGUI builds the page when @ui.page('/') is called
# Every ui.X() call inside here adds an element to the page
# ======================================================
@ui.page("/")
def index():
    global ref_status_badge, ref_rfid_label, dashboard_unlocked

    # ---- Dark-ish page background ----
    ui.query("body").classes("bg-gray-100")

    # ---- Top header bar ----
    with ui.header().classes(
        "bg-gray-900 text-white px-6 py-3 flex items-center justify-between"
    ):
        ui.label("🔒 Security Box Dashboard").classes("text-xl font-bold tracking-wide")
        ref_status_badge = ui.badge("MQTT: connecting...").props("outline color=orange")

    # ---- Main content column ----
    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):

        # ==================================================
        # CARD 1 — Access gate
        # All controls are hidden until user enters correct code
        # ==================================================
        with ui.card().classes("w-full rounded-2xl shadow p-5"):
            ui.label("Dashboard Access").classes(
                "text-base font-semibold text-gray-700"
            )
            ui.label("Enter your access code to unlock controls.").classes(
                "text-sm text-gray-400 mb-3"
            )

            with ui.row().classes("items-center gap-3"):
                code_input = ui.input(
                    placeholder="Access code",
                    password=True,
                    password_toggle_button=True,
                ).classes("w-40")
                access_msg = ui.label("").classes("text-sm")

            # This column holds ALL controls — hidden until code is correct
            controls = ui.column().classes("w-full gap-4 mt-3")
            controls.set_visibility(False)

            def check_code():
                global dashboard_unlocked
                if code_input.value.strip() == ACCESS_CODE:
                    dashboard_unlocked = True
                    access_msg.set_text("✅ Access granted")
                    access_msg.classes("text-green-600")
                    controls.set_visibility(True)
                    code_input.disable()
                    mqtt.add_log("Dashboard unlocked by operator")
                else:
                    access_msg.set_text("❌ Wrong code")
                    access_msg.classes("text-red-500")

            # Enter key or button click both trigger the check
            code_input.on("keydown.enter", check_code)
            ui.button("Unlock Dashboard", on_click=check_code).classes(
                "bg-gray-800 text-white rounded-lg px-4 py-2 text-sm"
            )

        # ==================================================
        # CARD 2 — Last RFID event status
        # Updated by ui.timer via ref_rfid_label
        # ==================================================
        with ui.card().classes("w-full rounded-2xl shadow p-5"):
            ui.label("Last RFID Event").classes(
                "text-base font-semibold text-gray-700 mb-1"
            )
            ref_rfid_label = ui.label("No RFID events received yet").classes(
                "text-sm font-mono text-gray-500"
            )

        # ==================================================
        # CONTROLS — inside the hidden container
        # Only visible after correct access code is entered
        # ==================================================
        with controls:

            # ---- Drawer Unlock ----
            with ui.card().classes(
                "w-full rounded-2xl shadow p-5 bg-green-50 border border-green-200"
            ):
                ui.label("🔓 Drawer").classes(
                    "text-base font-semibold text-green-800 mb-3"
                )

                ui.button(
                    "UNLOCK DRAWER",
                    on_click=lambda: (
                        mqtt.publish_queue.put_nowait({"command": "unlock"}),
                        mqtt.add_log("DASHBOARD: unlock command queued"),
                    ),
                ).classes(
                    "bg-green-600 text-white text-lg w-full py-3 rounded-xl hover:bg-green-500"
                )

            # ---- LED Strip ----
            with ui.card().classes(
                "w-full rounded-2xl shadow p-5 bg-blue-50 border border-blue-200"
            ):
                ui.label("💡 LED Strip").classes(
                    "text-base font-semibold text-blue-800 mb-3"
                )

                # Screensaver row
                with ui.row().classes("gap-2 mb-3"):
                    ui.button(
                        "Screensaver ON",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_screensaver_on"}
                        ),
                    ).classes("bg-blue-500 text-white rounded-lg px-3 py-2 text-sm")

                    ui.button(
                        "Screensaver OFF",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_screensaver_off"}
                        ),
                    ).classes("bg-blue-300 text-blue-900 rounded-lg px-3 py-2 text-sm")

                    ui.button(
                        "Strip OFF",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_off"}
                        ),
                    ).classes("bg-gray-400 text-white rounded-lg px-3 py-2 text-sm")

                ui.separator()

                # Blink section
                ui.label("Blink").classes("text-sm font-medium text-blue-700 mt-2 mb-1")
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    blink_r = ui.number("R", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    blink_g = ui.number("G", value=255, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    blink_b = ui.number("B", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    blink_times = ui.number("Times", value=3, min=1, max=10).classes(
                        "w-20"
                    )

                    ui.button(
                        "Blink",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_blink",
                                "r": int(blink_r.value),
                                "g": int(blink_g.value),
                                "b": int(blink_b.value),
                                "times": int(blink_times.value),
                            }
                        ),
                    ).classes("bg-blue-600 text-white rounded-lg px-4 py-2 text-sm")

                ui.separator()

                # Tail section
                ui.label("Tail animation").classes(
                    "text-sm font-medium text-blue-700 mt-2 mb-1"
                )
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    tail_r = ui.number("R", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    tail_g = ui.number("G", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    tail_b = ui.number("B", value=255, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    tail_cycles = ui.number("Cycles", value=2, min=1, max=10).classes(
                        "w-20"
                    )
                    tail_speed = ui.number(
                        "Speed ms", value=35, min=10, max=200
                    ).classes("w-24")

                    ui.button(
                        "Run Tail",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_tail",
                                "r": int(tail_r.value),
                                "g": int(tail_g.value),
                                "b": int(tail_b.value),
                                "cycles": int(tail_cycles.value),
                                "delay_ms": int(tail_speed.value),
                            }
                        ),
                    ).classes("bg-blue-600 text-white rounded-lg px-4 py-2 text-sm")

            # ---- OLED Controls ----
            with ui.card().classes(
                "w-full rounded-2xl shadow p-5 bg-purple-50 border border-purple-200"
            ):
                ui.label("📺 OLED Display").classes(
                    "text-base font-semibold text-purple-800 mb-3"
                )

                # Change idle screen text
                ui.label("Change idle screen").classes(
                    "text-sm font-medium text-purple-700 mb-1"
                )
                with ui.row().classes("gap-2 flex-wrap items-end"):
                    idle1 = ui.input("Line 1", value="READY").classes("w-28")
                    idle2 = ui.input("Line 2", value="SCAN CARD").classes("w-28")
                    idle3 = ui.input("Line 3", value="").classes("w-28")

                    ui.button(
                        "Set Idle Screen",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "set_idle_screen",
                                "line1": idle1.value[:16],
                                "line2": idle2.value[:16],
                                "line3": idle3.value[:16],
                            }
                        ),
                    ).classes("bg-purple-600 text-white rounded-lg px-4 py-2 text-sm")

                ui.separator()

                # Show custom text on OLED
                ui.label("Show custom text on OLED").classes(
                    "text-sm font-medium text-purple-700 mt-2 mb-1"
                )
                with ui.row().classes("gap-2 flex-wrap items-end"):
                    show1 = ui.input("Line 1", value="HELLO").classes("w-28")
                    show2 = ui.input("Line 2", value="FROM").classes("w-28")
                    show3 = ui.input("Line 3", value="DASHBOARD").classes("w-28")
                    show_ms = ui.number(
                        "Hold ms", value=3000, min=500, max=10000, step=500
                    ).classes("w-28")

                    ui.button(
                        "Send to OLED",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "oled_show",
                                "line1": show1.value[:16],
                                "line2": show2.value[:16],
                                "line3": show3.value[:16],
                                "hold_ms": int(show_ms.value),
                            }
                        ),
                    ).classes("bg-purple-600 text-white rounded-lg px-4 py-2 text-sm")

        # ==================================================
        # CARD 3 — Event Log (always visible, main feature)
        # ==================================================
        with ui.card().classes("w-full rounded-2xl shadow p-5"):
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("📋 Event Log").classes(
                    "text-base font-semibold text-gray-700"
                )
                ui.button(
                    "Clear",
                    on_click=lambda: (mqtt.log_lines.clear(), render_log.refresh()),
                ).props("flat dense size=sm")

            # Tall scrollable area — this is the main thing to watch
            with ui.scroll_area().classes(
                "w-full h-96 border rounded-lg bg-gray-900 p-3"
            ):
                render_log()

    # ---- Timer: refresh UI state + log every 500ms ----
    ui.timer(0.5, lambda: (update_ui(), render_log.refresh()))

    mqtt.add_log("Dashboard page loaded")


# --------------------------------------------------
# Startup hook — launch MQTT background thread
# Runs for the lifetime of the server
# --------------------------------------------------
@app.on_startup
def on_startup():
    mqtt.start_mqtt_thread()


@app.on_shutdown
def on_shutdown():
    mqtt.add_log("Dashboard shutting down")


# --------------------------------------------------
# Start NiceGUI server
# reload=False is important on Pi
# --------------------------------------------------
ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=False,
    title="Security Box",
)
