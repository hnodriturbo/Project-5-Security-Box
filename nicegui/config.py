# ==========================================
# file: config.py  (runs on Raspberry Pi)
# ==========================================
#
# Purpose:
# - One place to change broker, topics, and server settings.
# - Imported by mqtt_handler.py and dashboard.py.
#
# Since NiceGUI runs ON the Raspberry Pi, and Mosquitto also runs
# ON the Raspberry Pi, the broker address from the Pi's own perspective
# is "localhost" — not the LAN IP.
#
# The ESP32 connects to 10.201.48.7 (Pi LAN IP).
# The Pi itself connects to localhost (same machine).
# Both reach the exact same Mosquitto broker.
# ==========================================
import os
import sys
import asyncio

# -----------------------------
# CRITICAL: Set event loop policy JUST before ui.run() on Windows
# -----------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --------------------------------------------------
# MQTT Brokers — Dual-broker with automatic fallback
# --------------------------------------------------
# Primary: Raspberry Pi broker (school network)
# Fallback: Your home broker
# The mqtt_handler will try primary first, then fallback.
# --------------------------------------------------
BROKER_PRIMARY = "10.201.48.7"  # Raspberry Pi (main)
BROKER_FALLBACK = "192.168.1.51"  # Home broker (fallback)
BROKER_PORT = 1883  # standard MQTT port, no TLS, no auth

# Maximum connection attempts before giving up (tries both brokers each round)
MAX_CONNECTION_RETRIES = 10

# --------------------------------------------------
# Topics that match ESP32 box_controller.py exactly
# Direction:
#   ESP32  →  publishes to Events    (subscribe)
#   ESP32  ←  subscribes to Commands (publish)
# --------------------------------------------------
BASE_TOPIC = "MyTopic"
TOPIC_EVENTS = "MyTopic/Events"  # we subscribe — receive from ESP32
TOPIC_COMMANDS = "MyTopic/Commands"  # we publish  — send to ESP32

# --------------------------------------------------
# Dashboard access code
# User types this in the top card to unlock all controls
# --------------------------------------------------
ACCESS_CODE = "1404"

# --------------------------------------------------
# NiceGUI server
# 0.0.0.0 = listen on all interfaces so any device on the
# school network can open the dashboard in their browser
# --------------------------------------------------

# NICEGUI_HOST = "0.0.0.0"
# NICEGUI_PORT = 8090
# # open: http://10.201.48.7:8090
# e.g. http://:8090

# -----------------------------
# NiceGUI server config
# -----------------------------
NICEGUI_HOST = "0.0.0.0"
# Use "0.0.0.0" to open on LAN

# Custom port because Apache/Postgres use the default port
NICEGUI_PORT = 8090
# --------------------------------------------------
# Event log
# --------------------------------------------------
MAX_LOG_LINES = 100  # keep last 100 entries in memory
