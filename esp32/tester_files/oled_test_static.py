# testing/test_oled_static.py
# Simple non-animated OLED test using only the class methods.

import sys
sys.path.append("..")

from classes.oled_screen_class import OledScreen
import time

screen = OledScreen(
    sck=36,
    mosi=35,
    cs=9,
    dc=11,
    res=10
)

# Basic centered text tests
screen.draw_center("STATIC TEST", y=0, clear_first=True)
time.sleep(1.5)

screen.draw_center("TOP", y=10, clear_first=True)
time.sleep(1.5)

screen.draw_center("MIDDLE", y=28, clear_first=True)
time.sleep(1.5)

screen.draw_center("BOTTOM", y=46, clear_first=True)
time.sleep(1.5)

# Status layout tests (auto-vertical-centering)
screen.show_status("STATUS", "Line 1 OK", "Line 2 OK")
time.sleep(2.5)

screen.show_status("LOCKED", "Scan RFID", "")
time.sleep(2.5)

# Progress bar test (still non-animated)
screen.clear()
screen.draw_center("PROGRESS", y=0, clear_first=False)
screen.draw_progress(75, y=54, height=8)
time.sleep(3)

screen.show_status("DONE", "OLED OK", "")
