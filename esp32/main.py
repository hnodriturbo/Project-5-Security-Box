# =============================
# file: main.py
# =============================
# Purpose:
# - Boot OLED.
# - Connect WiFi + sync time first (sync function).
# - Start MQTT broker loop (primary first, fallback automatically).
# - Start controller (RFID + OLED + solenoid).
#
# Notes:
# - Reed switch code is kept but commented out (box not assembled yet).

import uasyncio as asyncio

from classes.oled_screen_class import OledScreen
from classes.solenoid_class import SolenoidTB6612
from classes.led_strip_class import LedStrip
from classes.rfid_class import RFIDClass, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX

from mqtt_broker import MqttBroker
from tasks import SecurityBoxController

# from classes.reed_switch_class import ReedSwitch  # Reed switch kept for later

import setup_wifi_and_time


async def main():
    oled = OledScreen()
    await oled.show_three_lines_async("BOOT", "WIFI SETUP", "")

    # WiFi + time setup is synchronous (do not await)
    wifi_result = setup_wifi_and_time.setup_wifi_and_time(oled=oled)

    if not wifi_result.get("wifi_ok"):
        await oled.show_three_lines_async("WIFI FAIL", "CHECK SSID", "")
        while True:
            await asyncio.sleep_ms(1000)

    solenoid = SolenoidTB6612()

    # LED strip optional (keep count 2 if you want small test; set 50 for final)
    led_strip = LedStrip(led_count=50, brightness=0.15, color_order="RGB")

    rfid = RFIDClass(
        whitelist_hex=DEFAULT_WHITELIST_HEX,
        allow_prefixes_hex=DEFAULT_ALLOW_PREFIXES_HEX,
        on_allowed=None,
        on_denied=None,
    )

    # reed_switch = ReedSwitch()  # Reed switch kept for later

    broker = MqttBroker()
    
    controller = SecurityBoxController(
        oled=oled,
        rfid=rfid,
        solenoid=solenoid,
        mqtt_broker=broker,
        led_strip=led_strip,
        # reed_switch=reed_switch,  # Reed switch kept for later
    )
    
    await oled.show_three_lines_async("MQTT", "CONNECTING", "")

    broker.start()

    await broker.wait_until_connected()

    await oled.show_status_async("MQTT", "CONNECTED", broker.broker_in_use)

    controller.start()

    await oled.show_three_lines_async("ENTER PIN", "OR", "SCAN CARD")

    while True:
        await asyncio.sleep_ms(1000)


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()