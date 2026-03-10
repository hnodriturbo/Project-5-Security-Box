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
    BROKER_PRIMARY,
    BROKER_FALLBACK,
    BROKER_PORT,
    TOPIC_EVENTS,
    TOPIC_COMMANDS,
    MAX_LOG_LINES,
    MAX_CONNECTION_RETRIES,
)

# --------------------------------------------------
# Shared state — updated by receive loop, read by ui.timer in dashboard.py
# --------------------------------------------------
state = {
    "mqtt_connected": False,
    "last_rfid": None,  # dict: result / display / ts
    "last_event": None,  # raw last event dict
    "active_broker": None,  # which broker we're connected to
}

# Event log list — dashboard renders this reversed (newest at top)
log_lines = []

# Thread-safe publish queue — button clicks put dicts here, loop drains and sends
publish_queue = queue.Queue()

# Internal: the MQTT thread's event loop (set when thread starts)
mqtt_loop = None

# Broker list for fallback logic
BROKERS = [BROKER_PRIMARY, BROKER_FALLBACK]


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
# format_payload() — pretty-print a dict for the log
# Converts raw JSON to a readable multi-key format
# --------------------------------------------------
def format_payload(payload, prefix=""):
    """Format a payload dict into a readable string for logging."""
    if not isinstance(payload, dict):
        return str(payload)

    parts = []
    for key, value in payload.items():
        if isinstance(value, dict):
            # Nested dict: show key=subkey:val,subkey:val
            sub_parts = ["{}:{}".format(k, v) for k, v in value.items()]
            parts.append("{}=[{}]".format(key, ", ".join(sub_parts)))
        elif value == "" or value is None:
            continue  # Skip empty values
        else:
            parts.append("{}={}".format(key, value))

    return "{} {}".format(prefix, " | ".join(parts)) if prefix else " | ".join(parts)


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
        # Check both top-level and nested data for label/uid_suffix
        label = payload.get("label", "") or data.get("label", "")
        uid_sfx = payload.get("uid_suffix", "") or data.get("uid_suffix", "")
        # Only show REMOTE if source is not rfid (i.e., dashboard triggered it)
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
# try_connect_to_broker() — attempts connection to a specific broker
# Returns the client if successful, None if failed
# --------------------------------------------------
async def try_connect_to_broker(broker_host):
    try:
        add_log("Attempting connection to {}:{}".format(broker_host, BROKER_PORT))
        client = Client(broker_host, BROKER_PORT)
        await client.__aenter__()
        return client
    except Exception as e:
        add_log("Failed to connect to {}: {}".format(broker_host, e))
        return None


# --------------------------------------------------
# connect_with_fallback() — tries primary, then fallback broker
# Returns (client, broker_host) tuple or (None, None) if both fail
# --------------------------------------------------
async def connect_with_fallback():
    for broker in BROKERS:
        client = await try_connect_to_broker(broker)
        if client:
            state["active_broker"] = broker
            add_log("Connected to broker: {}".format(broker))
            return client, broker
    return None, None


# --------------------------------------------------
# mqtt_receive_loop() — persistent subscribe connection with dual-broker fallback
# Tries primary, then fallback. If both fail, retries up to MAX_CONNECTION_RETRIES.
# --------------------------------------------------
async def mqtt_receive_loop():
    retry_count = 0

    while True:
        # Try to connect to either broker
        client, broker = await connect_with_fallback()

        if client is None:
            # Both brokers failed
            retry_count += 1
            if retry_count <= MAX_CONNECTION_RETRIES:
                add_log(
                    "Cannot connect to either broker. Reconnecting... ({}/{})".format(
                        retry_count, MAX_CONNECTION_RETRIES
                    )
                )
                await asyncio.sleep(5)
                continue
            else:
                add_log(
                    "CRITICAL: Max retries ({}) reached. Will keep trying...".format(
                        MAX_CONNECTION_RETRIES
                    )
                )
                retry_count = 0  # Reset and keep trying forever
                await asyncio.sleep(10)
                continue

        # Successfully connected
        retry_count = 0  # Reset retry counter on successful connection
        state["mqtt_connected"] = True

        try:
            add_log("MQTT connected — subscribed to: {}".format(TOPIC_EVENTS))
            await client.subscribe(TOPIC_EVENTS)

            async for message in client.messages:
                try:
                    payload = json.loads(message.payload.decode("utf-8"))
                    # Log formatted payload — readable format
                    add_log(format_payload(payload, "📥 IN:"))
                    handle_inbound(payload)
                except Exception as e:
                    add_log("Parse error: {}".format(e))

        except Exception as e:
            state["mqtt_connected"] = False
            state["active_broker"] = None
            add_log("MQTT disconnected from {}: {}".format(broker, e))
            await asyncio.sleep(5)


# --------------------------------------------------
# mqtt_publish_loop() — drain queue, send one at a time
# Uses the active broker from state, or tries both if none active
# --------------------------------------------------
async def mqtt_publish_loop():
    while True:
        try:
            # Non-blocking check with short sleep to stay async-friendly
            payload_dict = publish_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.1)
            continue

        # Determine which broker to use for publishing
        brokers_to_try = []
        if state["active_broker"]:
            brokers_to_try = [state["active_broker"]]
        else:
            brokers_to_try = BROKERS

        sent = False
        raw = json.dumps(payload_dict).encode("utf-8")

        for broker in brokers_to_try:
            try:
                async with Client(broker, BROKER_PORT) as client:
                    await client.publish(TOPIC_COMMANDS, raw)
                add_log(format_payload(payload_dict, "📤 SENT:"))
                sent = True
                break
            except Exception as e:
                add_log("Send error on {}: {}".format(broker, e))

        if not sent:
            add_log("Failed to send to any broker: {}".format(payload_dict))


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
