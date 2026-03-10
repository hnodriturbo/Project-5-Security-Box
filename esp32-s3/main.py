"""
main.py

Boot sequence and entry point for the Security Box.
Creates all hardware instances in the correct order, wires
all callbacks and references together, then hands control
to the asyncio event loop permanently.

Boot order:
    1. OledScreen  - first, so all following steps can show messages
    2. LedStrip    - start() shows "LED STRIP STARTED OK", idle loop on
    3. Solenoid    - start() shows "SOLENOID STARTED OK"
    4. ReedSwitch  - start() shows real drawer state (OPEN or CLOSED)
    5. RFID        - created but NOT started yet (waits for MQTT)
    6. MqttJsonBroker - connect WiFi + MQTT, show status on OLED
    7. Procedures  - wires reed callbacks, RFID callbacks, broker hooks
    8. rfid.start() - safe now that MQTT is up and callbacks are wired
    9. show_main_mode() - clear boot messages, show idle screen

The while True loop at the bottom keeps main() alive so all
background tasks (MQTT receive, LED idle loop, reed polling,
RFID scanning) keep running indefinitely.
"""

import uasyncio as asyncio

from class_files.oled_screen   import OledScreen
from class_files.led_strip     import LedStrip
from class_files.solenoid_lock import Solenoid
from class_files.reed_switch   import ReedSwitch
from class_files.rfid_scanner  import RFID, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX
from mqtt_json_broker      import MqttJsonBroker
from box_procedures        import Procedures


async def main():
    # --------------------------------------------------
    # Step 1 - OLED
    # Must be first - every following start() uses oled to show boot messages
    # --------------------------------------------------
    oled = OledScreen()
    oled.start()  # shows "OLED / STARTED / OK" on itself

    # Set the text that will be shown when the system is idle and waiting
    oled.set_idle_screen(("READY", "SCAN CARD", "OR PHONE"))

    # --------------------------------------------------
    # Step 2 - LED strip
    # start() shows "LED STRIP / STARTED / OK" for 3s then starts idle loop
    # --------------------------------------------------
    led = LedStrip(led_count=50, brightness=0.2, color_order="RGB")
    led.start(oled)

    # --------------------------------------------------
    # Step 3 - Solenoid
    # start() shows "SOLENOID / STARTED / OK" for 3s
    # Solenoid is initialized locked (off) inside its own __init__
    # --------------------------------------------------
    solenoid = Solenoid()
    solenoid.start(oled)

    # --------------------------------------------------
    # Step 4 - Reed switch
    # start() reads real drawer state and shows "REED SWITCH / STARTED / OPEN|CLOSED" for 3s
    # Callbacks (on_open / on_close) are wired later inside Procedures.__init__
    # --------------------------------------------------
    
    # reed = ReedSwitch(inverted=True)
    reed = ReedSwitch()
    reed.start(oled)

    # --------------------------------------------------
    # Step 5 - RFID reader
    # Created here but NOT started yet - start() is called after MQTT connects
    # This prevents card scan events firing before the system is fully ready
    # --------------------------------------------------
    rfid = RFID(
        whitelist_hex      = DEFAULT_WHITELIST_HEX,
        allow_prefixes_hex = DEFAULT_ALLOW_PREFIXES_HEX,
    )

    # --------------------------------------------------
    # Step 6 - MQTT broker
    # Primary WiFi + broker tried first, fallback used on school network
    # broker.start() launches connection in background - returns immediately
    # wait_connected() pauses here until first connection succeeds
    # --------------------------------------------------
    broker = MqttJsonBroker(
        wifi_primary    = {"ssid": "TskoliVESM",    "password": "Fallegurhestur"},
        wifi_fallback   = {"ssid": "Hringdu-jSy6",  "password": "FmdzuC4n"},
        broker_primary  = "10.201.48.7",   # Pi on school network - tried first
        broker_fallback = "192.168.1.51",  # home broker - fallback
        base_topic      = "MyTopic",
    )
    
    # Start the broker
    broker.start(oled)
    
    # Waits until connected, offline confirmed, or both brokers failed
    await broker.wait_ready()
    
    # If broker is offline (no networks found) show alternate idle screen
    if broker.offline:
        oled.show_three_lines("NO NETWORK", "OFFLINE MODE", "SCAN RFID")
        await asyncio.sleep_ms(2500)

    # WiFi ok but both brokers unreachable - go to main mode, retry in background
    elif broker.broker_unreachable:
        oled.show_three_lines("NO BROKER", "MAIN MODE", "RETRYING...")
        await asyncio.sleep_ms(2500)
        oled.show_three_lines("WILL RETRY", "IN BACKGROUND", "NOTIFY IF OK")
        await asyncio.sleep_ms(2500)


    # --------------------------------------------------
    # Step 7 - Procedures
    # Wires reed callbacks internally. RFID and broker hooks wired below.
    # --------------------------------------------------
    procedures = Procedures(oled, led, solenoid, reed, broker)

    # Uptime heartbeat status updates to dashboard
    asyncio.create_task(procedures.heartbeat_loop())
    
    # Wire RFID callbacks - must happen before rfid.start()
    rfid.on_allowed = procedures.on_rfid_allowed
    rfid.on_denied  = procedures.on_rfid_denied

    # Wire broker hooks - command handler and post-connect idle screen restore
    broker.set_callback(procedures.handle_command)
    broker.set_on_connected_callback(oled.show_main_mode)

    # --------------------------------------------------
    # Step 8 - Start RFID
    # Safe to start now: MQTT is connected, all callbacks are wired
    # start() shows "RFID / STARTED / SCANNING" for 3s
    # --------------------------------------------------
    rfid.start(oled)

    # --------------------------------------------------
    # Step 9 - Show idle screen
    # All boot messages are done - show the normal waiting screen
    # --------------------------------------------------
    oled.show_main_mode()

    # --------------------------------------------------
    # Keep-alive loop
    # main() must never return or all background tasks stop.
    # Yield every 250ms so MQTT, LED, reed, and RFID tasks keep running.
    # --------------------------------------------------
    while True:
        await asyncio.sleep_ms(250)


# --------------------------------------------------
# Entry point
# asyncio.run() starts the event loop and runs main().
# The finally block creates a fresh event loop if something crashes
# which is MicroPython best practice to avoid a stuck loop on reset.
# --------------------------------------------------
try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()