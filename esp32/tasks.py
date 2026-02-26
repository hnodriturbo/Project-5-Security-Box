"""
tasks.py - Security Box demo task runner

Purpose:
- Connect WiFi and sync RTC time (NTP) using setup_wifi_and_time.py
- Start OLED and show a short boot sequence
- Show a persistent user prompt: Enter PIN / or / Scan card
- Listen for RFID allowed/denied events (callbacks)
- Pulse solenoid on allowed scan
- Reed switch confirmation logic is prepared but disabled (box not assembled yet)

Notes:
- This file is intended to be imported and started by main.py on boot.
- Uses a simple "latest event + sequence number" pattern to safely move data
  from RFID callbacks into the async main loop.
"""

import time
import uasyncio as asyncio

from setup_wifi_and_time import setup_wifi_and_time

from classes.oled_screen_class import OledScreen
from classes.rfid_class import RFIDClass, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX
from classes.solenoid_class import SolenoidTB6612
from classes.reed_switch_class import ReedSwitch
# from classes.led_class import LedClass   # LED strip not connected yet


# -------------------------------------------------------------------
# Module state (shared between RFID callbacks and async main loop)
# -------------------------------------------------------------------

# Latest RFID event (allowed/denied + uid + label + timestamp)
lastRfidEvent = None

# Monotonic sequence number used to detect "new event arrived"
rfidEventSequenceNumber = 0


# -------------------------------------------------------------------
# Time helpers
# -------------------------------------------------------------------

def buildTimestampString():
    """
    Return a readable RTC timestamp after NTP sync.

    Format:
    - YYYY-MM-DD HH:MM:SS

    Notes:
    - Uses time.localtime() so it matches the RTC after setup_wifi_and_time().
    """
    currentTime = time.localtime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        currentTime[0], currentTime[1], currentTime[2],
        currentTime[3], currentTime[4], currentTime[5],
    )


# -------------------------------------------------------------------
# RFID event helpers
# -------------------------------------------------------------------

def buildRfidEventCopy(isAllowed, event):
    """
    Create a safe event copy with added fields.

    Adds:
    - allowed: bool
    - timestamp: string (RTC time)

    Notes:
    - Avoids dict-unpacking (**event) for MicroPython compatibility.
    """
    copiedEvent = {}
    copiedEvent["allowed"] = isAllowed
    copiedEvent["timestamp"] = buildTimestampString()

    if event:
        for key in event:
            copiedEvent[key] = event[key]

    return copiedEvent


def onRfidAllowed(event):
    """
    RFID callback for allowed tag.

    Behavior:
    - Stores the latest allowed event
    - Increments the sequence number so the async loop can react once
    """
    global lastRfidEvent, rfidEventSequenceNumber
    lastRfidEvent = buildRfidEventCopy(True, event)
    rfidEventSequenceNumber += 1


def onRfidDenied(event):
    """
    RFID callback for denied tag.

    Behavior:
    - Stores the latest denied event
    - Increments the sequence number so the async loop can react once
    """
    global lastRfidEvent, rfidEventSequenceNumber
    lastRfidEvent = buildRfidEventCopy(False, event)
    rfidEventSequenceNumber += 1


# -------------------------------------------------------------------
# Main async task runner
# -------------------------------------------------------------------

async def runSecurityBoxTasks():
    """
    Main demo runner.

    Flow:
    - WiFi + NTP time sync
    - OLED boot screens
    - Start RFID scanning
    - React to new RFID events:
      - Allowed: show UI + pulse solenoid + show last event time
      - Denied:  show UI + show last event time
    """

    # -------------------------------
    # Boot: WiFi + RTC (NTP)
    # -------------------------------
    # This should complete before showing timestamps on OLED.
    setup_wifi_and_time()

    # -------------------------------
    # Hardware instances (current phase)
    # -------------------------------
    oled = OledScreen()
    solenoid = SolenoidTB6612()

    # Hardware prepared but not used in this phase
    # reed = ReedSwitch()
    # leds = LedClass()

    # -------------------------------
    # OLED boot UI
    # -------------------------------
    oled.show_status("SECURITY BOX", "Booting...", "")
    await asyncio.sleep_ms(700)

    # Main idle prompt screen
    oled.show_three_lines("Enter PIN", "or", "Scan card")

    # -------------------------------
    # RFID start (scans in background)
    # -------------------------------
    rfid = RFIDClass(
        whitelist_hex=DEFAULT_WHITELIST_HEX,
        allow_prefixes_hex=DEFAULT_ALLOW_PREFIXES_HEX,
        on_allowed=onRfidAllowed,
        on_denied=onRfidDenied,
    )
    rfid.start()

    # Track what the loop has already handled
    handledRfidEventSequenceNumber = 0

    # -------------------------------
    # Main loop
    # -------------------------------
    while True:
        global lastRfidEvent, rfidEventSequenceNumber

        # Only react when a new RFID event arrives
        hasNewEvent = (
            lastRfidEvent is not None
            and rfidEventSequenceNumber != handledRfidEventSequenceNumber
        )

        if hasNewEvent:
            handledRfidEventSequenceNumber = rfidEventSequenceNumber
            event = lastRfidEvent

            # Pull common fields defensively
            uidHex = event.get("uid_hex", "")
            label = event.get("label", "")
            timestamp = event.get("timestamp", "")

            # ---------------------------
            # Allowed flow
            # ---------------------------
            if event.get("allowed"):

                # Show allowed message and a short identifier (label preferred)
                oled.show_status("ACCESS", "GRANTED", label or uidHex[-6:])
                await asyncio.sleep_ms(400)

                # Pulse solenoid to release latch
                oled.show_status("UNLOCK", "Solenoid pulse", "")
                await solenoid.pulse(duration_ms=500, cooldown_ms=200)

                # Reed confirmation logic (enable when box assembled)
                #
                # oled.show_status("CHECK", "Waiting reed...", "")
                # newState = await reed.wait_for_change(timeout_ms=1200, poll_ms=15)
                # if newState is None:
                #     oled.show_status("FAULT", "No movement", "")
                # else:
                #     oled.show_status("CONFIRMED", "Drawer moved", "")

                # Optional: show event time briefly
                oled.show_status("LAST EVENT", "Unlocked at", timestamp)
                await asyncio.sleep_ms(3000)

                # Return to idle prompt
                oled.show_three_lines("Enter PIN", "or", "Scan card")

            # ---------------------------
            # Denied flow
            # ---------------------------
            else:
                oled.show_status("ACCESS", "DENIED", uidHex[-6:] if uidHex else "")
                await asyncio.sleep_ms(3000)

                # Optional: show event time briefly
                oled.show_status("LAST EVENT", "Denied at", timestamp)
                await asyncio.sleep_ms(3000)

                # Return to idle prompt
                oled.show_three_lines("Enter PIN", "or", "Scan card")

        # Small delay so the loop stays responsive but not CPU-heavy
        await asyncio.sleep_ms(30)


# -------------------------------------------------------------------
# Entry point (called by main.py)
# -------------------------------------------------------------------

def main():
    """
    Start the async runner.

    Notes:
    - asyncio.run() owns the event loop.
    - Keep finally block so a future cleanup hook can be added safely.
    """
    try:
        asyncio.run(runSecurityBoxTasks())
    finally:
        pass


main()