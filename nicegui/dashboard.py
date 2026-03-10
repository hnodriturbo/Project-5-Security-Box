# ==========================================
# file: dashboard.py  (runs on Raspberry Pi)
# ==========================================
#
# NiceGUI web dashboard for the Security Box.
#
# Access gate:
#   Controls are hidden in a column with set_visibility(False).
#   Correct code → show controls, change button to "Lock Dashboard".
#   Lock button → hide controls again, re-enable input, reset state.
#
# MQTT:
#   All commands go through publish_queue.put_nowait() — never inline.
#   mqtt_handler.py owns the connection; dashboard only reads shared state.
#
# Run on Pi:
#   Open in browser: http://10.201.48.7:8090
# ==========================================

from nicegui import ui, app

import mqtt_handler as mqtt
from config import ACCESS_CODE, NICEGUI_HOST, NICEGUI_PORT

# --------------------------------------------------
# Dashboard state
# --------------------------------------------------

# Tracks whether the operator has unlocked the controls
dashboard_unlocked = False

# References to UI elements that need updating from the timer
ref_status_badge = None
ref_rfid_label = None


# --------------------------------------------------
# update_ui
# Called every 0.5s by ui.timer — reads mqtt_handler shared state
# and refreshes the badge and RFID label without rebuilding the page.
# --------------------------------------------------
def update_ui():
    # Update MQTT connection badge in the header
    if ref_status_badge is not None:
        if mqtt.state["mqtt_connected"]:
            ref_status_badge.set_text("● MQTT Connected")
            ref_status_badge.props("color=positive outline")
        else:
            ref_status_badge.set_text("○ MQTT Offline")
            ref_status_badge.props("color=negative outline")

    # Update the last RFID scan label — green for allowed, red for denied
    if ref_rfid_label is not None:
        rfid = mqtt.state.get("last_rfid")
        if rfid:
            color = "text-green-700" if rfid["result"] == "ALLOWED" else "text-red-600"
            text = "[{}]  {}  @ {}".format(rfid["result"], rfid["display"], rfid["ts"])
            ref_rfid_label.set_text(text)
            ref_rfid_label.classes(add=color)


# --------------------------------------------------
# render_log
# Refreshable block — ui.timer calls render_log.refresh() every 0.5s.
# Renders the log_lines list from mqtt_handler, newest entries first.
# Color-coded by keyword: red=denied/fail, green=allowed/sent, blue=incoming.
# --------------------------------------------------
@ui.refreshable
def render_log():
    # Show placeholder if nothing has arrived yet
    if not mqtt.log_lines:
        ui.label("Waiting for events...").classes("text-xs text-gray-300 italic")
        return

    # Iterate reversed so newest message appears at the top of the scroll area
    for line in reversed(mqtt.log_lines):
        if "DENIED" in line or "error" in line.lower() or "fail" in line.lower():
            css = "text-xs font-mono text-red-400"
        elif "ALLOWED" in line or "SENT" in line or "connected" in line.lower():
            css = "text-xs font-mono text-green-400"
        elif "📥 IN:" in line:
            css = "text-xs font-mono text-blue-400"
        elif "📤 SENT:" in line:
            css = "text-xs font-mono text-yellow-400"
        else:
            css = "text-xs font-mono text-white"

        ui.label(line).classes(css)


# ======================================================
# PAGE DEFINITION
# NiceGUI calls this function once per browser visit to build the page.
# All ui.X() calls here produce visible HTML elements in the browser.
# ======================================================
@ui.page("/")
def index():
    global ref_status_badge, ref_rfid_label, dashboard_unlocked

    # Gray background for the whole page body
    ui.query("body").classes("bg-gray-100")

    # --------------------------------------------------
    # Header bar — full-width dark strip at top of page
    # flex + items-center + justify-between = title left, badge right
    # --------------------------------------------------
    with ui.header().classes(
        "bg-gray-900 text-white px-6 py-3 flex items-center justify-between"
    ):
        ui.label("🔒 Security Box Dashboard").classes("text-xl font-bold tracking-wide")

        # Badge updates every 0.5s via ref_status_badge in update_ui()
        ref_status_badge = ui.badge("MQTT: connecting...").props("outline color=orange")

    # --------------------------------------------------
    # Main column — centers content and limits max width
    # mx-auto + max-w-3xl = centered on wide screens
    # --------------------------------------------------
    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):

        # ==================================================
        # CARD 1 — Access gate
        # All controls live in a hidden column beneath.
        # Correct code reveals them; Lock button hides them again.
        # ==================================================
        with ui.card().classes("w-full rounded-2xl shadow p-5"):

            # Card title and subtitle
            ui.label("Dashboard Access").classes(
                "text-base font-semibold text-gray-700 text-center w-full"
            )
            ui.label("Enter your access code to unlock controls.").classes(
                "text-sm text-gray-400 text-center w-full mb-4"
            )

            # Center the input + status message vertically in a column
            with ui.column().classes("items-center w-full gap-3"):

                # Password input — Enter key triggers check_code
                code_input = ui.input(
                    placeholder="Access code",
                    password=True,
                    password_toggle_button=True,
                ).classes("w-48")

                # Small status text — shows ✅ or ❌ after submit attempt
                access_msg = ui.label("").classes("text-sm text-center")

                # Toggle button — starts as "Unlock Dashboard"
                # After unlock: changes text to "Lock Dashboard"
                # Clicking again re-locks and hides all controls
                toggle_btn = ui.button(
                    "Unlock Dashboard", on_click=lambda: toggle_access()
                ).classes("bg-gray-800 text-white rounded-lg px-6 py-2 text-sm w-48")

            # Hidden container — holds ALL feature cards
            # set_visibility(False) makes it invisible but keeps it in DOM
            controls = ui.column().classes("w-full gap-4 mt-4")
            controls.set_visibility(False)

            # --------------------------------------------------
            # toggle_access
            # Single function that handles both lock and unlock.
            # Reads dashboard_unlocked to know which direction to go.
            # --------------------------------------------------
            def toggle_access():
                global dashboard_unlocked

                if not dashboard_unlocked:
                    # --- Unlock path ---
                    if code_input.value.strip() == ACCESS_CODE:
                        dashboard_unlocked = True

                        # Show success and reveal all controls
                        access_msg.set_text("✅ Access granted")
                        access_msg.classes(remove="text-red-500", add="text-green-600")
                        controls.set_visibility(True)
                        code_input.disable()

                        # Change button to Lock Dashboard
                        toggle_btn.set_text("🔒 Lock Dashboard")
                        toggle_btn.classes(
                            remove="bg-gray-800", add="bg-red-700 hover:bg-red-600"
                        )

                        mqtt.add_log("Dashboard unlocked by operator")
                    else:
                        access_msg.set_text("❌ Wrong code")
                        access_msg.classes(remove="text-green-600", add="text-red-500")

                else:
                    # --- Lock path ---
                    dashboard_unlocked = False

                    # Hide controls and restore the input field
                    controls.set_visibility(False)
                    code_input.enable()
                    code_input.set_value("")

                    # Reset status message
                    access_msg.set_text("")

                    # Change button back to Unlock Dashboard
                    toggle_btn.set_text("Unlock Dashboard")
                    toggle_btn.classes(
                        remove="bg-red-700 hover:bg-red-600", add="bg-gray-800"
                    )

                    mqtt.add_log("Dashboard locked by operator")

            # Enter key on the input also triggers toggle_access
            code_input.on("keydown.enter", toggle_access)

        # ==================================================
        # CARD 2 — Last RFID event
        # Always visible — shows the most recent scan result.
        # Updated every 0.5s via ref_rfid_label in update_ui().
        # ==================================================
        with ui.card().classes("w-full rounded-2xl shadow p-5"):
            ui.label("Last RFID Event").classes(
                "text-base font-semibold text-gray-700 mb-1"
            )
            ref_rfid_label = ui.label("No RFID events received yet").classes(
                "text-sm font-mono text-gray-500"
            )

        # ==================================================
        # CONTROLS SECTION
        # All feature cards are children of the hidden `controls` column.
        # They all appear/disappear together when controls is toggled.
        # ==================================================
        with controls:

            # ---- Drawer Unlock card ----
            # Green theme — visually signals "action" card
            with ui.card().classes(
                "w-full rounded-2xl shadow p-5 bg-green-50 border border-green-200"
            ):
                ui.label("🔓 Drawer").classes(
                    "text-base font-semibold text-green-800 mb-3"
                )

                # Big wide unlock button — hard to miss
                ui.button(
                    "UNLOCK DRAWER",
                    on_click=lambda: (
                        mqtt.publish_queue.put_nowait({"command": "unlock"}),
                        mqtt.add_log("DASHBOARD: unlock command queued"),
                    ),
                ).classes(
                    "bg-green-600 text-white text-lg w-full py-3 rounded-xl hover:bg-green-500"
                )

            # ---- LED Strip card ----
            # Blue theme — groups all LED controls together
            with ui.card().classes(
                "w-full rounded-2xl shadow p-5 bg-blue-50 border border-blue-200"
            ):
                ui.label("💡 LED Strip").classes(
                    "text-base font-semibold text-blue-800 mb-3"
                )

                # Quick screensaver and strip-off buttons in one row
                with ui.row().classes("gap-2 mb-3 flex-wrap"):
                    ui.button(
                        "Screensaver ON",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_idle_on"}
                        ),
                    ).classes("bg-blue-500 text-white rounded-lg px-3 py-2 text-sm")

                    ui.button(
                        "Screensaver OFF",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_idle_off"}
                        ),
                    ).classes("bg-blue-300 text-blue-900 rounded-lg px-3 py-2 text-sm")

                    ui.button(
                        "Strip OFF",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_off"}
                        ),
                    ).classes("bg-gray-400 text-white rounded-lg px-3 py-2 text-sm")

                # Idle mode selector buttons
                ui.label("Idle Modes").classes("text-sm font-medium text-blue-700 mb-1")
                with ui.row().classes("gap-2 mb-3 flex-wrap"):
                    ui.button(
                        "Mode 1 - Shifting",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_idle_1"}
                        ),
                    ).classes("bg-purple-500 text-white rounded-lg px-3 py-2 text-sm")

                    ui.button(
                        "Mode 2 - Rainbow",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_idle_2"}
                        ),
                    ).classes("bg-purple-400 text-white rounded-lg px-3 py-2 text-sm")

                    ui.button(
                        "Mode 3 - Slow Alt",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {"command": "led_idle_3"}
                        ),
                    ).classes(
                        "bg-purple-300 text-purple-900 rounded-lg px-3 py-2 text-sm"
                    )

                ui.separator()

                # Blink section — R/G/B inputs + times + fire button
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

                # Tail animation section — color + cycles + speed + fire button
                ui.label("Tail Chase").classes(
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

                ui.separator()

                # Rainbow wave section
                ui.label("Rainbow Wave").classes(
                    "text-sm font-medium text-blue-700 mt-2 mb-1"
                )
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    rainbow_cycles = ui.number(
                        "Cycles", value=2, min=1, max=10
                    ).classes("w-20")
                    rainbow_speed = ui.number(
                        "Speed ms", value=30, min=10, max=150
                    ).classes("w-24")

                    ui.button(
                        "Run Rainbow",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_rainbow",
                                "cycles": int(rainbow_cycles.value),
                                "speed_ms": int(rainbow_speed.value),
                            }
                        ),
                    ).classes(
                        "bg-gradient-to-r from-red-500 via-yellow-500 to-blue-500 text-white rounded-lg px-4 py-2 text-sm"
                    )

                ui.separator()

                # Pulse section — fade in/out effect
                ui.label("Pulse (Fade In/Out)").classes(
                    "text-sm font-medium text-blue-700 mt-2 mb-1"
                )
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    pulse_r = ui.number("R", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    pulse_g = ui.number("G", value=100, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    pulse_b = ui.number("B", value=255, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    pulse_cycles = ui.number("Cycles", value=3, min=1, max=10).classes(
                        "w-20"
                    )
                    pulse_speed = ui.number(
                        "Speed ms", value=20, min=5, max=100
                    ).classes("w-24")

                    ui.button(
                        "Run Pulse",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_pulse",
                                "r": int(pulse_r.value),
                                "g": int(pulse_g.value),
                                "b": int(pulse_b.value),
                                "cycles": int(pulse_cycles.value),
                                "speed_ms": int(pulse_speed.value),
                            }
                        ),
                    ).classes("bg-indigo-500 text-white rounded-lg px-4 py-2 text-sm")

                ui.separator()

                # Sparkle section — random LEDs flash
                ui.label("Sparkle (Random Flash)").classes(
                    "text-sm font-medium text-blue-700 mt-2 mb-1"
                )
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    sparkle_r = ui.number(
                        "R", value=255, min=0, max=255, step=1
                    ).classes("w-16")
                    sparkle_g = ui.number(
                        "G", value=255, min=0, max=255, step=1
                    ).classes("w-16")
                    sparkle_b = ui.number(
                        "B", value=255, min=0, max=255, step=1
                    ).classes("w-16")
                    sparkle_dur = ui.number(
                        "Duration ms", value=3000, min=500, max=10000, step=500
                    ).classes("w-28")
                    sparkle_density = ui.number(
                        "Density %", value=20, min=5, max=50
                    ).classes("w-24")

                    ui.button(
                        "Run Sparkle",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_sparkle",
                                "r": int(sparkle_r.value),
                                "g": int(sparkle_g.value),
                                "b": int(sparkle_b.value),
                                "duration_ms": int(sparkle_dur.value),
                                "density": int(sparkle_density.value),
                            }
                        ),
                    ).classes("bg-yellow-500 text-black rounded-lg px-4 py-2 text-sm")

                ui.separator()

                # Side chase section — lights each box side sequentially
                ui.label("Side Chase (Box Sides)").classes(
                    "text-sm font-medium text-blue-700 mt-2 mb-1"
                )
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    side_r = ui.number("R", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    side_g = ui.number("G", value=255, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    side_b = ui.number("B", value=100, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    side_cycles = ui.number("Cycles", value=2, min=1, max=10).classes(
                        "w-20"
                    )
                    side_hold = ui.number(
                        "Hold ms", value=300, min=100, max=1000
                    ).classes("w-24")

                    ui.button(
                        "Run Side Chase",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_side_chase",
                                "r": int(side_r.value),
                                "g": int(side_g.value),
                                "b": int(side_b.value),
                                "cycles": int(side_cycles.value),
                                "hold_ms": int(side_hold.value),
                            }
                        ),
                    ).classes("bg-teal-500 text-white rounded-lg px-4 py-2 text-sm")

                ui.separator()

                # Fill color section — solid color on entire strip
                ui.label("Fill (Solid Color)").classes(
                    "text-sm font-medium text-blue-700 mt-2 mb-1"
                )
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    fill_r = ui.number("R", value=255, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    fill_g = ui.number("G", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )
                    fill_b = ui.number("B", value=0, min=0, max=255, step=1).classes(
                        "w-16"
                    )

                    ui.button(
                        "Fill Strip",
                        on_click=lambda: mqtt.publish_queue.put_nowait(
                            {
                                "command": "led_fill",
                                "r": int(fill_r.value),
                                "g": int(fill_g.value),
                                "b": int(fill_b.value),
                            }
                        ),
                    ).classes("bg-red-500 text-white rounded-lg px-4 py-2 text-sm")

            # ---- OLED Controls card ----
            # Purple theme — display/screen related controls
            with ui.card().classes(
                "w-full rounded-2xl shadow p-5 bg-purple-50 border border-purple-200"
            ):
                ui.label("📺 OLED Display").classes(
                    "text-base font-semibold text-purple-800 mb-3"
                )

                # Section: change the text shown when the box is idle
                ui.label("Change idle screen").classes(
                    "text-sm font-medium text-purple-700 mb-1"
                )
                with ui.row().classes("gap-2 flex-wrap items-end"):
                    idle1 = ui.input("Line 1", value="READY").classes("w-28")
                    idle2 = ui.input("Line 2", value="SCAN CARD").classes("w-28")
                    idle3 = ui.input("Line 3", value="").classes("w-28")

                    # Trim to 16 chars — OLED screen width limit
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

                # Section: push any custom text to the OLED right now
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
        # CARD 3 — Event Log (always visible)
        # The main feature of the dashboard.
        # Scrollable dark terminal showing all MQTT events.
        # Refreshed every 0.5s by the timer at the bottom.
        # ==================================================
        with ui.card().classes("w-full rounded-2xl shadow p-5"):

            # Title row with Clear button aligned to the right
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("📋 Event Log").classes(
                    "text-base font-semibold text-gray-700"
                )
                # Clear wipes the list and forces a re-render immediately
                ui.button(
                    "Clear",
                    on_click=lambda: (mqtt.log_lines.clear(), render_log.refresh()),
                ).props("flat dense size=sm")

            # Medium-dark scrollable area — fixed height, renders log entries inside
            with ui.scroll_area().classes(
                "w-full h-96 border rounded-lg bg-gray-700 p-3"
            ):
                render_log()

    # Timer fires every 500ms — updates badge, RFID label, and log
    ui.timer(0.5, lambda: (update_ui(), render_log.refresh()))

    mqtt.add_log("Dashboard page loaded")


# --------------------------------------------------
# on_startup
# Called once by NiceGUI when the server starts.
# Launches the MQTT background thread so broker
# connection is ready before any browser connects.
# --------------------------------------------------
@app.on_startup
def on_startup():
    mqtt.start_mqtt_thread()


@app.on_shutdown
def on_shutdown():
    mqtt.add_log("Dashboard shutting down")


# --------------------------------------------------
# Start the NiceGUI web server
# reload=False is required on the Pi — auto-reload breaks the MQTT thread
# --------------------------------------------------
ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=False,
    title="Security Box",
)
