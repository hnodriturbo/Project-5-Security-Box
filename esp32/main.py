# esp32/main.py
"""
Boot orchestrator for the Security Box.

Flow:
    1. Create OLED early so WiFi status can be shown during boot
    2. Run WiFi + NTP setup (synchronous — must finish before asyncio starts)
    3. Create SecurityBoxController (creates all other hardware objects internally)
    4. Hand off to the asyncio event loop via controller.start()

Notes:
    - WiFi setup must be synchronous because the network stack uses blocking calls.
    - SecurityBoxController creates its own OledScreen internally. The one created
      here is only used during setup_wifi_and_time() and is then unused.
    - If the system crashes at the top level, the exception is printed to serial.
"""

import sys
import uasyncio as asyncio

from classes.oled_screen_class import OledScreen
from setup_wifi_and_time import setup_wifi_and_time
from tasks import SecurityBoxController


def main():
    # Create OLED first — used to show WiFi/NTP status during synchronous boot
    oled = OledScreen()
    oled.show_status("SECURITY BOX", "Booting...", "")

    # WiFi + NTP (synchronous — runs before asyncio loop starts)
    setup_wifi_and_time(oled=oled)

    # Create the controller (it creates its own OledScreen and all device objects)
    controller = SecurityBoxController()

    # Start the asyncio event loop — runs forever
    try:
        asyncio.run(controller.start())
    except Exception as e:
        # Print crash info to serial for debugging with Thonny or mpremote
        print("[MAIN] Fatal error:", e)
        sys.print_exception(e)


main()
