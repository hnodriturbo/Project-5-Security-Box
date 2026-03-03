# ==========================================
# file: mqtt_handler.py  (runs on Raspberry Pi)
# ==========================================
#
# Two async background loops:
#   mqtt_receive_loop()  - subscribes to Events, updates state + log
#   mqtt_publish_loop()  - drains publish_queue, sends to Commands
#
# RULE: Never publish inline in a button click.
#       Always use: publish_queue.put_nowait({"command": "..."})
#
# Windows fix: Runs in a separate thread with SelectorEventLoop
# because aiomqtt uses add_reader/add_writer (not supported on ProactorEventLoop).
# ==========================================

import sys
import json
import asyncio
import threading
import queue
from datetime import datetime

from aiomqtt import Client

from config import (
    BROKER_HOST,
    BROKER_PORT,
    TOPIC_EVENTS,
    TOPIC_COMMANDS,
    MAX_LOG_LINES,
)

# --------------------------------------------------
# Shared state — updated by receive loop, read by ui.timer in dashboard.py
# --------------------------------------------------
state = {
    "mqtt_connected": False,
    "last_rfid": None,  # dict: result / display / ts
    "last_event": None,  # raw last event dict
}

# Event log list — dashboard renders this reversed (newest at top)
log_lines = []

# Thread-safe publish queue — button clicks put dicts here, loop drains and sends
publish_queue = queue.Queue()

# Internal: the MQTT thread's event loop (set when thread starts)
mqtt_loop = None


# --------------------------------------------------
# add_log() — timestamped log entry
# --------------------------------------------------
def add_log(message):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = "{}  {}".format(ts, message)
    log_lines.append(entry)
    if len(log_lines) > MAX_LOG_LINES:
        del log_lines[:-MAX_LOG_LINES]


# --------------------------------------------------
# handle_inbound() — process one event dict from ESP32
# --------------------------------------------------
def handle_inbound(payload):
    event = payload.get("event", "")
    source = payload.get("source", "esp32")
    status = payload.get("status", "")
    data = payload.get("data", {})
    ts = payload.get("timestamp", "")

    state["last_event"] = payload

    if event == "access_allowed":
        label = data.get("label", "")
        uid_sfx = data.get("uid_suffix", "")
        display = label if label else (uid_sfx if uid_sfx else "REMOTE")
        state["last_rfid"] = {"result": "ALLOWED", "display": display, "ts": ts}
        add_log("ACCESS ALLOWED  ->  {}  [{}]".format(display, source))

    elif event == "box_online":
        add_log("BOX ONLINE  ->  {}".format(payload.get("data", {}).get("message", "")))

    elif event == "rfid_denied":
        uid_sfx = data.get("uid_suffix", "??????")
        state["last_rfid"] = {"result": "DENIED", "display": uid_sfx, "ts": ts}
        add_log("RFID DENIED  ->  UID suffix: {}".format(uid_sfx))

    elif event == "unlock_window_ended":
        add_log("Unlock window ended  [{}]".format(source))

    elif event:
        # Show everything — nothing should be invisible
        add_log(
            "ESP32 event: {}  source={}  status={}  data={}".format(
                event, source, status, data
            )
        )


# --------------------------------------------------
# mqtt_receive_loop() — persistent subscribe connection
# Reconnects automatically on disconnect
# --------------------------------------------------
async def mqtt_receive_loop():
    while True:
        try:
            add_log("MQTT connecting -> {}:{}".format(BROKER_HOST, BROKER_PORT))
            async with Client(BROKER_HOST, BROKER_PORT) as client:
                state["mqtt_connected"] = True
                add_log("MQTT connected — subscribed to: {}".format(TOPIC_EVENTS))
                await client.subscribe(TOPIC_EVENTS)

                async for message in client.messages:
                    try:
                        payload = json.loads(message.payload.decode("utf-8"))
                        # Log raw JSON first — full visibility
                        add_log("RAW IN: {}".format(json.dumps(payload)))
                        handle_inbound(payload)
                    except Exception as e:
                        add_log("Parse error: {}".format(e))

        except Exception as e:
            state["mqtt_connected"] = False
            add_log("MQTT disconnected: {}".format(e))
            await asyncio.sleep(5)


# --------------------------------------------------
# mqtt_publish_loop() — drain queue, send one at a time
# Uses thread-safe queue.Queue — polls with timeout
# --------------------------------------------------
async def mqtt_publish_loop():
    while True:
        try:
            # Non-blocking check with short sleep to stay async-friendly
            payload_dict = publish_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.1)
            continue

        try:
            raw = json.dumps(payload_dict).encode("utf-8")
            async with Client(BROKER_HOST, BROKER_PORT) as client:
                await client.publish(TOPIC_COMMANDS, raw)
            add_log("SENT -> {}".format(json.dumps(payload_dict)))
        except Exception as e:
            add_log("Send error: {}  payload={}".format(e, payload_dict))


# --------------------------------------------------
# run_mqtt_loops() — entry point for the MQTT thread
# Creates a SelectorEventLoop and runs both loops forever
# --------------------------------------------------
def run_mqtt_loops():
    global mqtt_loop

    # Force SelectorEventLoop on Windows (aiomqtt requirement)
    if sys.platform.startswith("win"):
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    mqtt_loop = loop

    add_log("MQTT thread started with SelectorEventLoop")

    # Run both loops concurrently
    loop.run_until_complete(
        asyncio.gather(
            mqtt_receive_loop(),
            mqtt_publish_loop(),
        )
    )


# --------------------------------------------------
# start_mqtt_thread() — called from dashboard on_startup
# Spawns daemon thread so it exits when main process exits
# --------------------------------------------------
def start_mqtt_thread():
    thread = threading.Thread(target=run_mqtt_loops, daemon=True)
    thread.start()
    add_log("MQTT background thread launched")
