"""
solenoid_lock.py

TB6612FNG motor driver used to control the solenoid door latch
of the Security Box drawer. Only the A-channel of the driver is used.

AIN1 drives the solenoid direction. AIN2 is held low when present
to avoid floating states. STBY and PWM_EN pins are optional and
driven high at boot to bring the driver out of standby.

Role in the box:
    Receives on() / off() calls from the unlock procedure.
    Stays off (locked) at all times except during the 10-second
    unlock window. Safety: solenoid.off() is also called from
    on_drawer_close() to guarantee the latch is locked.

Methods:
    * start()          - boot confirmation on OLED
    * on()             - energize solenoid - releases drawer latch
    * off()            - de-energize solenoid - drawer locks
    * enable_driver()  - bring TB6612 out of standby
    * disable_driver() - put TB6612 into standby and cut current
    * pulse()          - async unlock for a set duration then auto-lock
"""

from machine import Pin
import uasyncio as asyncio
import time

# AIN1 pin drives the solenoid through the TB6612 A-channel
SOLENOID_AIN1_PIN = 12


class Solenoid:

    # ------------------------------------------------------------
    # Init - configure TB6612 control pins and ensure latch is locked
    # ------------------------------------------------------------

    def __init__(
        self,
        ain1_pin       = SOLENOID_AIN1_PIN,
        ain2_pin       = None,
        standby_pin    = None,
        pwm_enable_pin = None,
        active_high    = True,
    ):
        # Main drive pin - this is what energizes the solenoid coil
        self.ain1_pin = Pin(int(ain1_pin), Pin.OUT)

        # Optional second drive pin - held low to prevent floating inputs on TB6612
        self.ain2_pin = Pin(int(ain2_pin), Pin.OUT) if ain2_pin is not None else None

        # Optional standby pin - must be high for the TB6612 to output anything
        self.standby_pin = Pin(int(standby_pin), Pin.OUT) if standby_pin is not None else None

        # Optional PWM enable pin - controls whether the channel is active
        self.pwm_enable_pin = Pin(int(pwm_enable_pin), Pin.OUT) if pwm_enable_pin is not None else None

        # Polarity flag - some boards invert the logic levels on STBY/EN
        self.active_high = bool(active_high)

        # Lock the solenoid first so the drawer starts in the locked state
        self.off()

        # Then bring driver out of standby so the channel is ready to fire
        self.enable_driver()

    # ------------------------------------------------------------
    # Boot confirmation - announces solenoid is ready on OLED
    # ------------------------------------------------------------

    def start(self, oled=None):
        # Print to console and show boot message on OLED for 3 seconds
        print("[SOLENOID] started")
        if oled:
            oled.show_three_lines("SOLENOID", "STARTED", "OK")
            time.sleep_ms(3000)

    # ------------------------------------------------------------
    # Driver control - bring TB6612 in and out of standby
    # ------------------------------------------------------------

    def enable_driver(self):
        # Drive STBY and EN pins to active level so the channel can output
        if self.standby_pin    is not None: self.standby_pin.value(1    if self.active_high else 0)
        if self.pwm_enable_pin is not None: self.pwm_enable_pin.value(1 if self.active_high else 0)

    def disable_driver(self):
        # Turn off solenoid first then put TB6612 into standby to cut current
        self.off()
        if self.pwm_enable_pin is not None: self.pwm_enable_pin.value(0 if self.active_high else 1)
        if self.standby_pin    is not None: self.standby_pin.value(0    if self.active_high else 1)

    # ------------------------------------------------------------
    # Solenoid on / off - the two calls used by the unlock procedure
    # ------------------------------------------------------------

    def on(self):
        # Energize the solenoid coil - physically releases the drawer latch
        self.enable_driver()

        # Drive AIN1 to the active level to push current through the coil
        self.ain1_pin.value(1 if self.active_high else 0)

        # Hold AIN2 low so the TB6612 sees a defined direction, not a float
        if self.ain2_pin is not None:
            self.ain2_pin.value(0 if self.active_high else 1)

    def off(self):
        # De-energize the coil - spring or gravity returns latch to locked position
        self.ain1_pin.value(0 if self.active_high else 1)

        # AIN2 also low - both pins low = brake mode on TB6612, clean stop
        if self.ain2_pin is not None:
            self.ain2_pin.value(0 if self.active_high else 1)

    # ------------------------------------------------------------
    # Timed pulse - unlock for a set window then auto-lock (async)
    # Not used by the main procedure (which controls timing itself)
    # but available for simple one-shot unlock from a command
    # ------------------------------------------------------------

    async def pulse(self, open_duration_ms=5000):
        # Turn solenoid on, wait for the duration, then turn it off
        self.on()
        await asyncio.sleep_ms(int(open_duration_ms))
        self.off()