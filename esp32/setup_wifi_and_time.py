# =============================
# file: setup_wifi_and_time.py
# =============================
# Purpose:
# - Handle WiFi connection ONLY.
# - Sync NTP time.
# - Completely separate from MQTT logic.
# - Recover from ESP32 "Wifi Internal State Error".
#
# Notes:
# - This file is synchronous (do NOT await it).
# - Safe reset logic included for unstable WiFi states.

import network
import ntptime
import time
import machine
import gc


# ------------------------------------------------------------
# OLED helper (optional)
# ------------------------------------------------------------
def show_status(oled, line1, line2="", line3=""):
    if oled is None:
        return

    if hasattr(oled, "show_status"):
        oled.show_status(line1, line2, line3)
        return

    if hasattr(oled, "show_three_lines"):
        oled.show_three_lines(line1, line2, line3)
        return


# ------------------------------------------------------------
# Force reset WiFi stack (fixes internal state error)
# ------------------------------------------------------------
def reset_wifi_stack(wlan, oled=None):
    show_status(oled, "WIFI", "Resetting...", "")

    try:
        wlan.disconnect()
    except Exception:
        pass

    try:
        wlan.active(False)
    except Exception:
        pass

    time.sleep(1)
    gc.collect()

    try:
        wlan.active(True)
    except Exception:
        pass

    time.sleep(1)
    gc.collect()


# ------------------------------------------------------------
# Connect to one WiFi network safely
# ------------------------------------------------------------
def connect_wifi(ssid, password, oled=None, attempts=10):

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        wlan.disconnect()
        time.sleep(1)

    show_status(oled, "WIFI", "Connecting...", ssid)
    print("WiFi connecting:", ssid)

    for attempt_index in range(int(attempts)):

        try:
            wlan.connect(ssid, password)
        except OSError as error:
            print("WiFi connect OSError:", error)
            reset_wifi_stack(wlan, oled=oled)
            continue

        time.sleep(1)

        if wlan.isconnected() and wlan.config("essid") == ssid:
            ip_info = wlan.ifconfig()
            show_status(oled, "WIFI OK", ssid, ip_info[0])
            print("WiFi connected:", ssid, ip_info)
            return {
                "wifi_ok": True,
                "ssid": ssid,
                "ip_info": ip_info,
                "wlan": wlan,
            }

        print("WiFi attempt", attempt_index + 1, "failed for", ssid)

    show_status(oled, "WIFI FAIL", ssid, "Trying next")
    print("WiFi failed:", ssid)

    return {
        "wifi_ok": False,
        "ssid": None,
        "wifi_pw": None,
        "ip_info": None,
        "wlan": wlan,
    }


# ------------------------------------------------------------
# Sync time using NTP
# ------------------------------------------------------------
def sync_time(oled=None):

    show_status(oled, "TIME", "Syncing NTP...", "")
    print("NTP syncing...")

    try:
        ntptime.settime()
        show_status(oled, "TIME OK", "NTP synced", "")
        print("NTP synced")
        return True
    except Exception as error:
        show_status(oled, "TIME FAIL", "NTP error", "")
        print("NTP error:", error)
        return False


# ------------------------------------------------------------
# Read RTC time and return readable string
# ------------------------------------------------------------
def get_time_text():
    rtc = machine.RTC()
    current_time = rtc.datetime()

    year = current_time[0]
    month = current_time[1]
    day = current_time[2]
    hour = current_time[4]
    minute = current_time[5]
    second = current_time[6]

    return "{}-{}-{} {:02d}:{:02d}:{:02d}".format(
        year, month, day, hour, minute, second
    )


# ------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------
def setup_wifi_and_time(oled=None):

    wifi_networks = [
        ("TskoliVESM", "Fallegurhestur"),
        ("Hringdu-jSy6", "FmdzuC4n"),
    ]

    result = None

    for ssid, password in wifi_networks:
        result = connect_wifi(ssid, password, oled=oled, attempts=10)
        if result["wifi_ok"]:
            break

    if not result or not result["wifi_ok"]:
        show_status(oled, "WIFI", "No connection", "")
        print("No WiFi connection")

        return {
            "wifi_ok": False,
            "ssid": None,
            "ip_info": None,
            "time_ok": False,
            "time_text": None,
        }

    time_ok = sync_time(oled=oled)
    time_text = get_time_text()

    show_status(oled, "READY", result["ssid"], time_text)
    print("RTC time:", time_text)

    return {
        "wifi_ok": True,
        "ssid": result["ssid"],
        "wifi_pw": result.get("wifi_pw"),
        "ip_info": result["ip_info"],
        "time_ok": time_ok,
        "time_text": time_text,
    }
