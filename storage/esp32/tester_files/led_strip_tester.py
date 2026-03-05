# =============================
# file: led_async_test.py
# =============================
# Purpose:
# - Minimal async test for flow_five_leds_circular_async()
# - No MQTT, no OLED, no solenoid
# - Just verify animation works

import uasyncio as asyncio
from classes.led_strip_class import LedStrip


async def main():
    # Small test first (change to 50 for full strip)
    led_strip = LedStrip(led_count=50, brightness=0.2, color_order="RGB")

    # Run circular flow visibly longer
    await led_strip.flow_five_leds_circular_async(
        cycles=20,   # increase cycles so it's clearly visible
        delay_ms=80  # slow it down for human eye
    )

    # Keep script alive so board doesn't immediately reset
    while True:
        await asyncio.sleep_ms(1000)


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()