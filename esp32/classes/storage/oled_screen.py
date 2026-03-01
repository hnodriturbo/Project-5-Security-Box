# oled_screen.py
# Simple reusable OLED controller for ESP32-S3 (SPI)

from machine import Pin, SPI
import ssd1306
import time

class OledScreen:
    # Class initialize function
    def __init__(
        self,
        spi_id=1,
        sck=36,
        mosi=35,
        dc=11,
        res=10,
        cs=9,
        width=128,
        height=64
    ):
        # Initialize SPI
        self.spi = SPI(
            spi_id,
            baudrate=1_000_000,
            polarity=0,
            phase=0,
            sck=Pin(sck),
            mosi=Pin(mosi),
            miso=None
        )

        # Initialize OLED
        self.oled = ssd1306.SSD1306_SPI(
            width,
            height,
            self.spi,
            dc=Pin(dc),
            res=Pin(res),
            cs=Pin(cs)
        )

        self.clear()

    def clear(self):
        self.oled.fill(0)
        self.oled.show()

    def text(self, message, x=0, y=0):
        self.oled.text(message, x, y)
        self.oled.show()

    def center_text(self, message, y=28):
        x = (128 - len(message) * 8) // 2
        self.oled.text(message, x, y)
        self.oled.show()

    def invert(self, state=True):
        self.oled.invert(1 if state else 0)

    def splash(self):
        self.clear()
        self.center_text("SECURITY BOX", 10)
        self.center_text("INITIALIZING", 30)
        time.sleep(2)
        self.clear()
