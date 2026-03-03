"""
nicegui_broker.py

MQTT Broker Communication Module
- Handles connection to primary and fallback MQTT brokers
- Sends JSON commands to ESP32
- Receives JSON data from ESP32
- Provides async functions for dashboard integration

Primary Broker: Raspberry Pi Mosquitto (school network)
Fallback Broker: broker.emqx.io (public cloud broker)

"""

# -----------------------------
# Imports
# -----------------------------
import json
import asyncio
from datetime import datetime
from aiomqtt import Client, MqttError

# -----------------------------
# MQTT Broker Configuration
# -----------------------------

# Primary broker - Raspberry Pi Mosquitto on school network
PRIMARY_BROKER = "10.201.48.7"

# Fallback broker - Public EMQX broker
FALLBACK_BROKER = "broker.emqx.io"

# Alternative fallback (uncomment if needed)
# FALLBACK_BROKER = "test.mosquitto.org"

# MQTT Topic for communication
MQTT_TOPIC = "1404TOPIC"

# Connection timeout in seconds
CONNECTION_TIMEOUT = 5

# -----------------------------
# Module State
# -----------------------------

# Track which broker is currently active
active_broker = None

# Callback function for logging (set by dashboard)
log_callback_handler = None

# Callback function for received data (set by dashboard)
data_callback_handler = None


# -----------------------------
# Logging Helper
# -----------------------------
def broker_log(message: str):
    """
    Internal logging function.
    Calls the dashboard's log callback if set.
    """
    if log_callback_handler:
        log_callback_handler(message)
    else:
        # Fallback to console if no callback set
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[BROKER] {timestamp} - {message}")


def set_log_callback(callback):
    """
    Set the logging callback function.
    Dashboard calls this to receive log messages.

    Args:
        callback: Function that accepts a string message
    """
    global log_callback_handler
    log_callback_handler = callback


def set_data_callback(callback):
    """
    Set the data received callback function.
    Dashboard calls this to receive parsed JSON data from ESP32.

    Args:
        callback: Function that accepts a dict (parsed JSON)
    """
    global data_callback_handler
    data_callback_handler = callback


# -----------------------------
# Broker Connection Functions
# -----------------------------
async def try_connect_broker(broker_address: str) -> bool:
    """
    Attempt to connect to a specific MQTT broker.

    Args:
        broker_address: The broker IP or hostname

    Returns:
        True if connection successful, False otherwise
    """
    try:
        broker_log(f"Attempting connection to {broker_address}...")
        async with Client(broker_address, timeout=CONNECTION_TIMEOUT) as client:
            # Try subscribing to verify connection works
            await client.subscribe(MQTT_TOPIC)
            broker_log(f"Successfully connected to {broker_address}")
            return True
    except MqttError as e:
        broker_log(f"Failed to connect to {broker_address}: {e}")
        return False
    except Exception as e:
        broker_log(f"Connection error for {broker_address}: {e}")
        return False


async def get_active_broker() -> str:
    """
    Determine which broker to use.
    Tries primary first, falls back to secondary if needed.

    Returns:
        The broker address to use, or None if both unavailable
    """
    global active_broker

    # Try primary broker first
    if await try_connect_broker(PRIMARY_BROKER):
        active_broker = PRIMARY_BROKER
        broker_log(f"Using PRIMARY broker: {PRIMARY_BROKER}")
        return PRIMARY_BROKER

    # Fallback to secondary broker
    broker_log("Primary broker unavailable, trying fallback...")
    if await try_connect_broker(FALLBACK_BROKER):
        active_broker = FALLBACK_BROKER
        broker_log(f"Using FALLBACK broker: {FALLBACK_BROKER}")
        return FALLBACK_BROKER

    # Both brokers failed
    broker_log("ERROR: All brokers unavailable!")
    active_broker = None
    return None  # type: ignore


# -----------------------------
# Send Data Functions
# -----------------------------
async def send_json(data: dict, topic: str = None) -> bool:  # type: ignore
    """
    Send JSON data to ESP32 via MQTT.

    Args:
        data: Dictionary to send as JSON
        topic: Optional custom topic (defaults to MQTT_TOPIC)

    Returns:
        True if sent successfully, False otherwise
    """
    global active_broker

    # Use default topic if not specified
    if topic is None:
        topic = MQTT_TOPIC

    # Determine which broker to use
    broker = active_broker
    if broker is None:
        broker = await get_active_broker()
        if broker is None:
            broker_log("Cannot send: No broker available")
            return False

    try:
        # Convert data to JSON string
        payload = json.dumps(data)

        async with Client(broker) as client:
            await client.publish(topic, payload)
            broker_log(f"Sent to {topic}: {payload}")
            return True

    except MqttError as e:
        broker_log(f"MQTT send error: {e}")
        # Reset active broker to trigger reconnection attempt
        active_broker = None
        return False
    except Exception as e:
        broker_log(f"Send error: {e}")
        return False


async def send_command(command: str, value=None, extra: dict = None) -> bool:  # type: ignore
    """
    Send a structured command to ESP32.

    Args:
        command: The command name (e.g., "lock", "unlock", "led_on")
        value: Optional value for the command
        extra: Optional additional key-value pairs

    Returns:
        True if sent successfully, False otherwise
    """
    # Build command payload
    payload = {
        "cmd": command,
        "timestamp": datetime.now().isoformat(),
    }

    if value is not None:
        payload["value"] = value

    if extra:
        payload.update(extra)

    return await send_json(payload)


# -----------------------------
# Receive Data Functions
# -----------------------------
async def start_receiver():
    """
    Start the MQTT message receiver.
    Runs continuously, receiving messages and calling the data callback.
    Uses fallback broker if primary is unavailable.

    This should be called from app.on_startup in the dashboard.
    """
    global active_broker

    broker_log("Starting MQTT receiver...")

    while True:
        # Get active broker (with fallback logic)
        broker = await get_active_broker()

        if broker is None:
            broker_log("No broker available, retrying in 5 seconds...")
            await asyncio.sleep(5)
            continue

        try:
            async with Client(broker) as client:
                await client.subscribe(MQTT_TOPIC)
                broker_log(f"Subscribed to topic: {MQTT_TOPIC}")

                async for message in client.messages:
                    await handle_incoming_message(message)

        except MqttError as e:
            broker_log(f"MQTT receiver error: {e}")
            active_broker = None  # Reset to try reconnection
            await asyncio.sleep(2)
        except Exception as e:
            broker_log(f"Receiver error: {e}")
            await asyncio.sleep(2)


async def handle_incoming_message(message):
    """
    Handle an incoming MQTT message.
    Parses JSON and calls the data callback.

    Args:
        message: The MQTT message object
    """
    try:
        # Decode payload
        payload_str = message.payload.decode()
        broker_log(f"Received: {payload_str}")

        # Try to parse as JSON
        try:
            data = json.loads(payload_str)

            # Call the data callback if set
            if data_callback_handler:
                data_callback_handler(data)

        except json.JSONDecodeError:
            # Not JSON, log as plain text
            broker_log(f"Non-JSON message: {payload_str}")

            # Still notify callback with raw string
            if data_callback_handler:
                data_callback_handler({"raw": payload_str})

    except Exception as e:
        broker_log(f"Message handling error: {e}")


# -----------------------------
# Utility Functions
# -----------------------------
def get_broker_status() -> dict:
    """
    Get the current broker connection status.

    Returns:
        Dict with broker status information
    """
    return {
        "active_broker": active_broker,
        "primary_broker": PRIMARY_BROKER,
        "fallback_broker": FALLBACK_BROKER,
        "topic": MQTT_TOPIC,
        "connected": active_broker is not None,
    }


def get_topic() -> str:
    """Get the current MQTT topic."""
    return MQTT_TOPIC


def set_topic(topic: str):
    """
    Set a new MQTT topic.

    Args:
        topic: The new topic to use
    """
    global MQTT_TOPIC
    MQTT_TOPIC = topic
    broker_log(f"Topic changed to: {topic}")
