# esp32/setup_wifi_and_time.py
"""
WiFi connection and NTP time sync helper.

Tries the school network first, then the home network.
Displays status on the OLED if one is provided.

Usage (called from main.py BEFORE starting the asyncio event loop):
    from setup_wifi_and_time import setup_wifi_and_time
    setup_wifi_and_time(oled=oled_instance)

Notes:
    - Fully synchronous — WiFi connect uses blocking sleep() internally.
    - Must run before asyncio.run() because the WiFi stack is not async.
    - oled parameter is optional; pass None to skip display updates.
"""

import network
import ntptime
import time
import machine
from machine import RTC


# Networks to try in order — first match wins
WIFI_NETWORKS = [
    ("TskoliVESM",  "Fallegurhestur"),   # School network (preferred)
    ("Hringdu-jSy6", "FmdzuC4n"),         # Home network (fallback)
]


def connect_wifi(ssid, password, oled=None, attempts=10):
    """
    Try to connect to one WiFi network.

    Args:
        ssid:     Network name
        password: Network password
        oled:     Optional OledScreen instance for status display
        attempts: How many 1-second retries before giving up

    Returns:
        ssid string if connected, None if failed
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.disconnect()   # Clear any stale connection

    print("WiFi: trying", ssid)
    if oled:
        oled.show_status("WIFI", "Connecting...", ssid[:12])

    wlan.connect(ssid, password)

    for _ in range(attempts):
        if wlan.isconnected() and wlan.config('essid') == ssid:
            ip = wlan.ifconfig()[0]
            print("WiFi: connected to", ssid, "IP:", ip)
            if oled:
                oled.show_status("WIFI OK", ssid[:12], ip)
            return ssid
        time.sleep(1)

    print("WiFi: failed to connect to", ssid)
    return None


def sync_time(oled=None):
    """Sync RTC with NTP. Silently continues if sync fails (no internet)."""
    try:
        if oled:
            oled.show_status("NTP", "Syncing time...", "")
        ntptime.settime()
        print("Time: NTP sync OK")
    except Exception as e:
        print("Time: NTP sync failed:", e)
        if oled:
            oled.show_status("NTP", "Sync failed", "using RTC")


def get_time_text():
    """Return current RTC time as a formatted string (for OLED / log lines)."""
    t = machine.RTC().datetime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[4], t[5], t[6]
    )


def setup_wifi_and_time(oled=None):
    """
    Connect to WiFi and sync NTP time. Shows status on OLED if provided.

    Tries WIFI_NETWORKS in order until one succeeds. NTP sync runs after
    a successful connection. Continues without a connection if all networks
    fail (offline mode — MQTT will reconnect later via its own retry loop).

    Args:
        oled: Optional OledScreen instance. Pass None during unit tests
              or when no display is attached.
    """
    connected_ssid = None

    for ssid, pwd in WIFI_NETWORKS:
        connected_ssid = connect_wifi(ssid, pwd, oled=oled)
        if connected_ssid:
            break

    if connected_ssid:
        sync_time(oled=oled)
        ts = get_time_text()
        print("Boot time:", ts)
        if oled:
            oled.show_status("READY", connected_ssid[:12], ts[11:])  # show HH:MM:SS
    else:
        print("WiFi: no network found — running offline")
        if oled:
            oled.show_status("OFFLINE", "No WiFi", "MQTT will retry")
        time.sleep(2)   # Let the user read the message before boot continues
