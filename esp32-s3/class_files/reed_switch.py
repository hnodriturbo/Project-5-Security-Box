"""
reed_switch.py

Reed switch input handler for the Security Box drawer.
Detects whether the drawer is physically open or closed using
a magnetic reed switch connected to a GPIO input with pull-up.

Wiring logic (pull-up enabled):
    Magnet near switch  -> pin reads LOW  (0) -> drawer CLOSED
    Magnet away         -> pin reads HIGH (1) -> drawer OPEN

A 1-second debounce prevents false triggers from magnet bounce
or brief interruptions during drawer movement. The new state must
hold stable for the full debounce period before any callback fires.

Role in the box:
    Monitors drawer state continuously in a background task.
    on_open fires when drawer is opened - cancels active unlock.
    on_close fires when drawer closes - guarantees solenoid is off
    and returns OLED to idle screen. Both callbacks are wired by
    Procedures.__init__() so this class has no dependency on procedures.

Methods:
    * start()   - boot confirmation, shows real drawer state, launches poll loop
    * stop()    - cancel the poll loop cleanly
    * read_raw() - read current pin value (True = open, no debounce)
    * poll_loop() - background task: debounce + callback dispatch
"""

from machine import Pin
import uasyncio as asyncio
import time

# GPIO pin the reed switch signal wire is connected to
REED_GPIO   = 16

# New state must remain stable this long before callback fires
DEBOUNCE_MS = 1000


class ReedSwitch:

    # ------------------------------------------------------------
    # Init - configure GPIO input with pull-up and read initial state
    # ------------------------------------------------------------

    def __init__(self, pin=REED_GPIO, on_open=None, on_close=None, inverted=False):
        # Input pin with internal pull-up resistor enabled
        self.pin = Pin(int(pin), Pin.IN, Pin.PULL_UP)

        # Async callbacks wired by Procedures - called on confirmed state change
        self.on_open  = on_open   # called when drawer opens (pin goes HIGH)
        self.on_close = on_close  # called when drawer closes (pin goes LOW)

        # flip open/close logic without rewiring
        self.inverted = inverted
        
        # Read the real hardware state at boot so is_open reflects reality
        self.is_open = self.read_raw()
        
        # Task handle - stored so stop() can cancel it cleanly
        self.poll_task = None

    # ------------------------------------------------------------
    # Boot confirmation - shows drawer state on OLED then starts polling
    # ------------------------------------------------------------

    def start(self, oled=None):
        # Show the actual drawer state detected at boot, not a hardcoded value
        state = "OPEN" if self.is_open else "CLOSED"
        print("[REED] started - drawer is", state)
        if oled:
            oled.show_three_lines("REED SWITCH", "STARTED", state)
            time.sleep_ms(3000)

        # Launch the background poll loop now that callbacks should be wired
        if self.poll_task is None:
            self.poll_task = asyncio.create_task(self.poll_loop())

    # ------------------------------------------------------------
    # Stop - cancel poll loop cleanly without crashing
    # ------------------------------------------------------------

    def stop(self):
        if self.poll_task is not None:
            self.poll_task.cancel()
            self.poll_task = None

    # ------------------------------------------------------------
    # Raw pin read - True means drawer is open (no magnet)
    # ------------------------------------------------------------

    def read_raw(self):
        # Pin HIGH (1) = no magnet = drawer open
        raw = self.pin.value() == 1
        return not raw if self.inverted else raw  # flip if wiring logic is reversed

    # ------------------------------------------------------------
    # Poll loop - runs forever, debounces pin, fires callbacks on change
    # A candidate state must hold for DEBOUNCE_MS before it is confirmed
    # ------------------------------------------------------------

    async def poll_loop(self):
        # Start with the state we already read at boot as the confirmed baseline
        confirmed = self.is_open
        candidate = None   # the new state we are watching stabilize
        since     = None   # when this candidate was first seen

        while True:
            raw = self.read_raw()

            if raw != confirmed:
                if candidate != raw:
                    # New candidate detected - start the debounce timer
                    candidate = raw
                    since = time.ticks_ms()
                elif time.ticks_diff(time.ticks_ms(), since) >= DEBOUNCE_MS:
                    # Candidate held stable long enough - confirm it and fire callback
                    confirmed    = raw
                    self.is_open = raw
                    candidate    = None  # reset so next change starts fresh

                    if raw and self.on_open:
                        await self.on_open()
                    elif not raw and self.on_close:
                        await self.on_close()
            else:
                # Raw matches confirmed state - discard any in-progress candidate
                candidate = None

            # Poll at 20Hz - fast enough to catch state changes, light on CPU
            await asyncio.sleep_ms(50)