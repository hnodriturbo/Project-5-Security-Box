# ==========================================
# file: main.py
# ==========================================
#
# Purpose:
# - Boot the security box in the correct order.
# - Wire everything together (controller → broker → procedures).
# - Then hand off control to the asyncio event loop forever.
#
# Boot order:
#   1. Create BoxController
#      - OLED is created first inside BoxController
#      - All other hardware (LED, solenoid, reed, RFID) created there too
#   2. Start OLED queue worker (needs asyncio running first)
#   3. Create MqttJsonBroker and wire it to controller
#   4. Create Procedures and wire it to controller
#   5. Start broker background task
#   6. Wait until MQTT connects
#   7. Start RFID scan loop
#   8. Show idle screen
#   9. Keep-alive loop forever
#
# ==========================================
# - The while True loop at the bottom keeps main() alive forever
#   so tasks like MQTT rx loop, OLED queue, RFID scan keep running.
# ==========================================

import uasyncio as asyncio

from box_controller    import BoxController
from mqtt_json_broker  import MqttJsonBroker
from procedures        import Procedures


async def main():

    # --------------------------------------------------
    # Step 1 — Create BoxController
    # This creates OLED first, then all other hardware.
    # OLED shows "BOOTING..." as soon as it's initialized.
    # --------------------------------------------------
    controller = BoxController()

    # --------------------------------------------------
    # Step 2 — Start OLED queue worker
    # The queue worker is a background task that picks messages
    # from the queue and shows each one for hold_ms milliseconds.
    # MUST be started after asyncio is running (we are inside async now).
    # --------------------------------------------------
    controller.oled.start_queue_worker()

    # --------------------------------------------------
    # Step 3 — Create MQTT broker
    # Primary WiFi + broker for internet testing.
    # Fallback WiFi + broker for local Raspberry Pi setup.
    # --------------------------------------------------
    broker = MqttJsonBroker(
        wifi_primary   = {"ssid": "Hringdu-jSy6",  "password": "FmdzuC4n"},
        wifi_fallback  = {"ssid": "TskoliVESM",    "password": "Fallegurhestur"},
        broker_primary="192.168.1.51",
        # broker_primary="localhost",
        # broker_primary = "broker.emqx.io",
        broker_fallback= "10.201.48.7",             # local Raspberry Pi broker
        base_topic     = "MyTopic",
    )

    # --------------------------------------------------
    # Step 4 — Create Procedures and wire everything together
    # Procedures needs the controller to access hardware + log()
    # Controller needs procedures for RFID callbacks
    # Broker needs procedures.handle_command to process JSON commands
    # --------------------------------------------------
    procedures = Procedures(controller)

    controller.set_broker(broker)            # controller.log() can now publish MQTT
    controller.set_procedures(procedures)    # RFID callbacks can now trigger flows

    broker.set_logger(controller.log)        # broker shows status on OLED + console
    broker.set_callback(procedures.handle_command)   # incoming JSON → handle_command

    # When broker connects or reconnects, return OLED to idle mode immediately
    broker.set_on_connected_callback(controller.oled.show_main_mode)

    # --------------------------------------------------
    # Step 5 — Start broker background task
    # start() uses create_task() internally — returns immediately
    # Broker will connect WiFi + MQTT in the background
    # --------------------------------------------------
    controller.log("WIFI", "STARTING", "...", hold_ms=1500)
    broker.start()

    # --------------------------------------------------
    # Step 6 — Wait until MQTT connects before starting RFID
    # wait_connected() polls every 200ms until self.connected is True
    # Other background tasks (broker, OLED queue) run during this wait
    # --------------------------------------------------
    await broker.wait_connected()

    # --------------------------------------------------
    # Step 7 — Start RFID scan loop
    # Now that MQTT is stable, it is safe to start accepting card scans.
    # RFID events will publish JSON to the dashboard immediately.
    # --------------------------------------------------
    controller.start_rfid()

    # --------------------------------------------------
    # Step 8 — Show idle screen
    # Queue worker and broker are running, RFID is scanning.
    # Clear any boot messages and show the normal idle screen.
    # --------------------------------------------------
    controller.oled.clear_queue()               # Discard any leftover boot messages
    broker.set_on_connected_callback(controller.oled.show_main_mode) # Show "READY / SCAN CARD"

    # --------------------------------------------------
    # Step 9 — Keep-alive loop
    # Does nothing except yield every 250ms so all background tasks keep running.
    # If this loop stopped, main() would return and the whole program would stop.
    # --------------------------------------------------
    while True:
        await asyncio.sleep_ms(250)


# --------------------------------------------------
# Entry point
# asyncio.run(main()) starts the event loop and runs main().
# The finally block creates a fresh event loop if something crashes,
# which is MicroPython best practice to avoid a stuck event loop.
# --------------------------------------------------
try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()