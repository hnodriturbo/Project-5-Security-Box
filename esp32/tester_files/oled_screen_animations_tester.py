# testing/test_oled_animations.py
# Quick test runner for OLED drawing + animations.

import sys
sys.path.append("..")

from classes.oled_screen_class import OledScreen
import time

# Create screen instance (pins are easy to change later when RFID/LED take GPIO space)
screen = OledScreen(
    sck=36,
    mosi=35,
    cs=9,
    dc=11,
    res=10
)

# Basic status screen
screen.show_status("OLED TEST", "Basic UI", "Starting...")
time.sleep(1)

# Invert blink "alive" check
screen.blink_invert(times=4, delay_ms=180)

# Slide in text, then hold
screen.slide_in_center("HELLO", y=24, speed_ms=10)
time.sleep(1)

# Scroll text demo
screen.marquee("Scrolling text works!", y=36, speed_ms=20, loop_count=1)
time.sleep(1)

# Progress animation demo
screen.draw_center("Loading...", y=10, clear_first=True)
screen.animate_progress(step=10, delay_ms=120, y=54, height=8)
time.sleep(1)

# Bouncing dot demo (simple refresh test)
screen.draw_center("Bounce dot", y=0, clear_first=True)
screen.bounce_dot(y=40, speed_ms=12, loops=2)

# Finished screen
screen.show_status("DONE", "OLED OK", "")
