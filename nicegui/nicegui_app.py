# nicegui/nicegui_app.py
"""
Security Box Dashboard — runs on the Raspberry Pi.

Shows:
    - MQTT connection status (live badge)
    - Last RFID event (allowed/denied, UID, timestamp)
    - Drawer state (when reed switch is active)
    - Rolling event log (last 100 lines)

Controls:
    - Unlock button
    - LED: flow animation, turn off, brightness slider
    - OLED text: custom title + two lines

Architecture:
    - mqtt_receive_loop(): async aiomqtt subscriber, updates module-level state
    - mqtt_publish_loop(): drains publish_queue and sends JSON
    - ui.timer(0.5, update_ui): polls state and refreshes UI elements
    - All MQTT publish actions enqueue to publish_queue (never publish inline)

Run on Raspberry Pi:
    pip install nicegui aiomqtt
    python nicegui_app.py
"""

import os
import sys
import json
import asyncio
from datetime import datetime

from aiomqtt import Client as AioMqttClient
from nicegui import ui, app


# ------------------------------------------------------------------
# Config (override with environment variables if needed)
# ------------------------------------------------------------------
MQTT_PRIMARY  = os.getenv("MQTT_BROKER",  "10.201.48.7")   # Raspberry Pi LAN
MQTT_FALLBACK = os.getenv("MQTT_FALLBACK", "broker.emqx.io")
MQTT_TOPIC    = "1404TOPIC"
NICEGUI_HOST  = os.getenv("NICEGUI_HOST", "0.0.0.0")
NICEGUI_PORT  = int(os.getenv("NICEGUI_PORT", "8090"))
MAX_LOG       = 100


# ------------------------------------------------------------------
# Shared state (updated by mqtt_receive_loop, read by update_ui)
# ------------------------------------------------------------------
state = {
    "mqtt_connected": False,
    "last_rfid":      None,   # dict with result/uid/label/ts
    "drawer_open":    None,   # True / False / None (unknown)
}
log_lines    = []
publish_queue = asyncio.Queue()   # full Python asyncio.Queue is available here


# ------------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------------

def add_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    log_lines.append("{} {}".format(ts, msg))
    if len(log_lines) > MAX_LOG:
        del log_lines[:-MAX_LOG]


# ------------------------------------------------------------------
# Inbound message handler
# ------------------------------------------------------------------

def handle_inbound(payload):
    """Update shared state from an ESP32 event message."""
    event = payload.get("event")

    if event == "rfid_allowed":
        state["last_rfid"] = {
            "result": "ALLOWED",
            "uid":    payload.get("uid", ""),
            "label":  payload.get("label", ""),
            "ts":     payload.get("ts",    ""),
        }
        add_log("RFID ALLOWED: {}".format(payload.get("label") or payload.get("uid", "")[-6:]))

    elif event == "rfid_denied":
        state["last_rfid"] = {
            "result": "DENIED",
            "uid":    payload.get("uid", ""),
            "label":  "",
            "ts":     payload.get("ts", ""),
        }
        add_log("RFID DENIED:  {}".format(payload.get("uid", "")[-6:]))

    elif event == "drawer_state":
        drawer_state = payload.get("state", "")
        state["drawer_open"] = (drawer_state == "open")
        add_log("Drawer: {}".format(drawer_state))

    elif event == "unlock_fault":
        add_log("FAULT: {}".format(payload.get("reason", "")))

    elif event == "unlock_confirmed":
        add_log("Confirmed: drawer {}".format(payload.get("state", "")))

    elif event:
        # Show any other events in the log so nothing is invisible
        add_log("ESP: {}".format(event))


# ------------------------------------------------------------------
# MQTT receive loop
# ------------------------------------------------------------------

async def mqtt_receive_loop():
    """
    Subscribe and receive MQTT messages from the ESP32.
    Tries primary broker first, alternates to fallback on disconnect.
    Reconnects automatically.
    """
    broker = MQTT_PRIMARY
    while True:
        try:
            add_log("MQTT connecting: {}".format(broker))
            async with AioMqttClient(broker) as client:
                state["mqtt_connected"] = True
                add_log("MQTT connected: {}".format(broker))
                await client.subscribe(MQTT_TOPIC)

                async for message in client.messages:
                    try:
                        payload = json.loads(message.payload.decode("utf-8"))
                        handle_inbound(payload)
                    except Exception as e:
                        add_log("Parse error: {}".format(e))

        except Exception as e:
            state["mqtt_connected"] = False
            add_log("MQTT disconnected: {}".format(e))
            # Alternate between primary and fallback on each failure
            broker = MQTT_FALLBACK if broker == MQTT_PRIMARY else MQTT_PRIMARY
            await asyncio.sleep(5)


# ------------------------------------------------------------------
# MQTT publish loop
# ------------------------------------------------------------------

async def mqtt_publish_loop():
    """
    Drain publish_queue and send each JSON payload.
    Opens a fresh connection per message — simple and reliable for
    low-frequency dashboard commands.
    """
    broker = MQTT_PRIMARY
    while True:
        payload_dict = await publish_queue.get()
        try:
            async with AioMqttClient(broker) as client:
                raw = json.dumps(payload_dict).encode()
                await client.publish(MQTT_TOPIC, raw)
                add_log("Sent: {}".format(payload_dict))
        except Exception as e:
            add_log("Send error: {}".format(e))
            # Try fallback next time
            broker = MQTT_FALLBACK if broker == MQTT_PRIMARY else MQTT_PRIMARY


# ------------------------------------------------------------------
# UI references (filled when the page builds)
# ------------------------------------------------------------------
status_badge_utility  = None
rfid_label_utility    = None
drawer_label_utility  = None


def update_ui():
    """Poll shared state and refresh UI elements. Called every 0.5s by ui.timer."""
    if status_badge_utility is not None:
        if state["mqtt_connected"]:
            status_badge_utility.set_text("MQTT: connected")
            status_badge_utility.props("color=green outline")
        else:
            status_badge_utility.set_text("MQTT: offline")
            status_badge_utility.props("color=red outline")

    if rfid_label_utility is not None:
        ev = state.get("last_rfid")
        if ev:
            uid_short = ev.get("uid", "")[-6:] or "?"
            display   = ev.get("label") or uid_short
            text = "[{}]  {}  @ {}".format(ev["result"], display, ev.get("ts", ""))
            rfid_label_utility.set_text(text)

    if drawer_label_utility is not None:
        d = state.get("drawer_open")
        if d is True:
            drawer_label_utility.set_text("Drawer: OPEN")
        elif d is False:
            drawer_label_utility.set_text("Drawer: CLOSED")
        else:
            drawer_label_utility.set_text("Drawer: unknown")


# ------------------------------------------------------------------
# Log renderer (refreshable)
# ------------------------------------------------------------------

@ui.refreshable
def render_log():
    for line in reversed(log_lines):
        ui.label(line).classes("text-xs font-mono")


# ------------------------------------------------------------------
# Page definition
# ------------------------------------------------------------------

@ui.page("/")
def index():
    global status_badge_utility, rfid_label_utility, drawer_label_utility

    with ui.card().classes("max-w-4xl w-full mx-auto mt-4 p-4 gap-4"):

        # --- Header ---
        ui.label("Security Box Dashboard").classes("text-2xl font-bold w-full text-center")

        # --- Status row ---
        with ui.row().classes("w-full justify-between items-center"):
            status_badge_utility = ui.badge("MQTT: connecting...").props("outline color=orange")
            drawer_label_utility = ui.label("Drawer: unknown").classes("text-sm text-gray-500")

        ui.separator()

        # --- Last RFID event ---
        with ui.card().classes("w-full"):
            ui.label("Last RFID Event").classes("font-semibold mb-1")
            rfid_label_utility = ui.label("No events yet").classes("text-sm font-mono text-gray-600")

        ui.separator()

        # --- Controls ---
        with ui.card().classes("w-full gap-2"):
            ui.label("Controls").classes("font-semibold")

            # Unlock
            ui.button(
                "UNLOCK DRAWER",
                color="green",
                on_click=lambda: publish_queue.put_nowait({"cmd": "unlock"})
            ).classes("w-full")

            ui.separator()

            # LED controls
            ui.label("LED Strip").classes("text-sm font-semibold")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button(
                    "LED: Flow Blue",
                    on_click=lambda: publish_queue.put_nowait({
                        "call": {
                            "device": "led",
                            "method": "flow_five_leds_circular_async",
                            "args":   {"r": 0, "g": 0, "b": 200, "cycles": 3, "delay_ms": 40},
                        }
                    })
                )
                ui.button(
                    "LED: Off",
                    on_click=lambda: publish_queue.put_nowait({
                        "call": {"device": "led", "method": "turn_off", "args": {}}
                    })
                )

            with ui.row().classes("items-center gap-4 w-full"):
                ui.label("Brightness").classes("text-sm w-24 shrink-0")
                brightness_slider = ui.slider(min=0.0, max=1.0, step=0.05, value=0.15).classes("flex-1")

            ui.button(
                "Set Brightness",
                on_click=lambda: publish_queue.put_nowait({
                    "call": {
                        "device": "led",
                        "method": "set_brightness",
                        "args":   {"level": brightness_slider.value},
                    }
                })
            )

            ui.separator()

            # OLED controls
            ui.label("OLED Display").classes("text-sm font-semibold")
            with ui.row().classes("gap-2 flex-wrap"):
                oled_title = ui.input("Title",  value="HELLO").classes("w-28")
                oled_line1 = ui.input("Line 1", value="FROM").classes("w-28")
                oled_line2 = ui.input("Line 2", value="SERVER").classes("w-28")

            ui.button(
                "Send to OLED",
                on_click=lambda: publish_queue.put_nowait({
                    "call": {
                        "device": "oled",
                        "method": "show_status_async",
                        "args": {
                            "title": oled_title.value,
                            "line1": oled_line1.value,
                            "line2": oled_line2.value,
                        },
                    }
                })
            )

        ui.separator()

        # --- Log ---
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full justify-between items-center mb-1"):
                ui.label("Event Log").classes("font-semibold")
                ui.button(
                    "Clear",
                    on_click=lambda: (log_lines.clear(), render_log.refresh())
                ).props("size=sm flat")

            with ui.scroll_area().classes("h-48 w-full border rounded p-2"):
                render_log()

        # Refresh UI elements every 500ms
        ui.timer(0.5, lambda: (update_ui(), render_log.refresh()))

    add_log("Dashboard loaded")


# ------------------------------------------------------------------
# Startup / shutdown hooks
# ------------------------------------------------------------------

@app.on_startup
async def on_startup():
    asyncio.create_task(mqtt_receive_loop())
    asyncio.create_task(mqtt_publish_loop())
    add_log("Background tasks started")


@app.on_shutdown
def on_shutdown():
    add_log("Dashboard shutting down")


# ------------------------------------------------------------------
# Windows asyncio policy fix (needed if developing on Windows)
# ------------------------------------------------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


ui.run(
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
    reload=False,
    title="Security Box",
)
