"""
oled_test_simple.py

Simple tester for OledScreen using the simplified class.
Shows: status screens → invert blink → progress bar → marquee → slide-in → loop.
"""

import time
from classes.oled_screen_class import OledScreen


# Create OLED instance with your current pin defaults
oled = OledScreen(
    spi_id=1,
    sck=36,
    mosi=35,
    dc=11,
    res=10,
    cs=9,
    width=128,
    height=64,
    baudrate=1_000_000,
)


# Show a few basic status screens
oled.show_status("OLED", "Boot OK")
time.sleep_ms(900)

oled.show_status("Status", "Line 1", "Line 2")
time.sleep_ms(1200)

# Quick alive check (invert blink)
oled.show_status("Check", "Invert blink")
time.sleep_ms(400)
oled.blink_invert(times=2, delay_ms=150)
time.sleep_ms(400)

# Progress bar demo (0 → 100)
for percent in range(0, 101, 5):
    oled.show_status("Loading", f"{percent}%")
    oled.draw_progress(percent)
    time.sleep_ms(60)

# Simple animations
oled.show_status("Animation", "Slide Across")
time.sleep_ms(2000)
oled.marquee("Hello OLED", speed_ms=18, loops=1)

oled.show_status("Animation:", "Slide in center")
time.sleep_ms(2000)
oled.slide_in_center("Done!", speed_ms=10)
time.sleep_ms(1000)

# End screen
oled.show_status("OK", "Test finished")
time.sleep_ms(5000)

# Clear the screen
oled.clear()

