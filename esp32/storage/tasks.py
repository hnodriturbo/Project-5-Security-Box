# esp32/tasks.py
"""
PRODUCTION Security Box Controller
- Uses default pins from all classes
- Uses positional arguments only (no keywords)
- Minimal, working code
"""

import uasyncio as asyncio
import time

from classes.oled_screen_class import OledScreen
from classes.rfid_class import RFIDClass, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX
from classes.solenoid_class import SolenoidTB6612
from classes.led_strip_class import LedStrip
from mqtt_broker import MqttBroker


ALLOWED_COMMANDS = ["unlock"]

ALLOWED_CALLS = {
    "oled": ["show_status_async", "show_three_lines_async", "clear_async"],
    "led": ["turn_off", "fill", "set_brightness"],
}


class SecurityBoxController:
    
    def __init__(self):
        # All use default pins
        self.oled = OledScreen()
        self.led = LedStrip()
        self.solenoid = SolenoidTB6612()
        
        self.rfid_event = None
        self.rfid_seq = 0
        self.rfid_handled_seq = 0
        
        # RFID requires keyword args (has * in signature)
        self.rfid = RFIDClass(
            whitelist_hex=DEFAULT_WHITELIST_HEX,
            allow_prefixes_hex=DEFAULT_ALLOW_PREFIXES_HEX,
            on_allowed=self.on_allowed_utility,
            on_denied=self.on_denied_utility,
        )
        
        self.mqtt = MqttBroker(
            client_id="box_001",
            on_message=self.on_command_utility
        )
        
        self.animation_task = None
        self.unlocking = False
    
    def on_command_utility(self, msg):
        if not isinstance(msg, dict):
            return
        
        if msg.get("cmd") == "unlock":
            asyncio.create_task(self.unlock())
        elif "call" in msg:
            asyncio.create_task(self.remote_call_utility(msg["call"]))
    
    async def remote_call_utility(self, call):
        dev = call.get("device", "")
        method = call.get("method", "")
        args = call.get("args", {})
        
        if dev not in ALLOWED_CALLS or method not in ALLOWED_CALLS[dev]:
            return
        
        obj = self.oled if dev == "oled" else self.led if dev == "led" else None
        if not obj:
            return
        
        func = getattr(obj, method, None)
        if not func:
            return
        
        try:
            result = func(**args) if args else func()
            if hasattr(result, "send"):
                await result
        except Exception as e:
            print(f"[CMD] {dev}.{method} error: {e}")
    
    def on_allowed_utility(self, ev):
        self.rfid_event = {
            "ok": True,
            "uid": ev.get("uid_hex", ""),
            "label": ev.get("label", ""),
            "ts": self.time_utility()
        }
        self.rfid_seq += 1
    
    def on_denied_utility(self, ev):
        self.rfid_event = {
            "ok": False,
            "uid": ev.get("uid_hex", ""),
            "ts": self.time_utility()
        }
        self.rfid_seq += 1
    
    async def unlock(self, src="rfid", uid="", label=""):
        if self.unlocking:
            return
        
        self.unlocking = True
        self.oled.mark_activity()
        
        try:
            if self.animation_task:
                self.animation_task.cancel()
            
            name = label or (uid[-6:] if uid else "REMOTE")
            await self.oled.show_status_async("ACCESS", "GRANTED", name)
            
            # Green animation - POSITIONAL ONLY
            self.animation_task = asyncio.create_task(
                self.self.led_flow_tail_utility()
            )
            
            self.mqtt.send({
                "event": "allowed",
                "uid": uid,
                "label": label,
                "ts": self.time_utility()
            })
            
            await self.oled.show_status_async("UNLOCKING", "OPEN NOW", "")
            await self.solenoid.pulse()
            await self.oled.show_status_async("UNLOCKED", "at", self.time_utility())
            await asyncio.sleep_ms(3000)
            
        finally:
            self.unlocking = False
            await self.oled.show_three_lines_async("Enter PIN", "or", "Scan card")
    
    async def denied(self, ev):
        uid = ev.get("uid", "")
        self.oled.mark_activity()
        
        if self.animation_task:
            self.animation_task.cancel()
        
        self.animation_task = asyncio.create_task(self.red_flash_utility())
        
        await self.oled.show_status_async("ACCESS", "DENIED", uid[-6:] if uid else "?")
        
        self.mqtt.send({
            "event": "denied",
            "uid": uid,
            "ts": self.time_utility()
        })
        
        await asyncio.sleep_ms(3000)
        await self.oled.show_three_lines_async("Enter PIN", "or", "Scan card")
    
    async def green_flow_utility(self):
        """Green animation - uses fill() to avoid method signature issues."""
        try:
            for _ in range(8):
                # Fill green, wait, off, wait
                self.led.fill(0, 255, 0)  # positional: r, g, b
                await asyncio.sleep_ms(200)
                self.led.turn_off()
                await asyncio.sleep_ms(100)
        except asyncio.CancelledError:
            self.led.turn_off()
            raise
    
    async def red_flash_utility(self):
        """Red flash."""
        try:
            for _ in range(3):
                self.led.fill(255, 0, 0)  # positional: r, g, b
                await asyncio.sleep_ms(150)
                self.led.turn_off()
                await asyncio.sleep_ms(150)
        except asyncio.CancelledError:
            self.led.turn_off()
            raise
    
    async def main_loop_utility(self):
        await self.oled.show_three_lines_async("Enter PIN", "or", "Scan card")
        
        while True:
            if self.rfid_event and self.rfid_seq != self.rfid_handled_seq:
                self.rfid_handled_seq = self.rfid_seq
                ev = self.rfid_event
                
                if ev["ok"]:
                    await self.unlock("rfid", ev["uid"], ev["label"])
                else:
                    await self.denied(ev)
            
            await asyncio.sleep_ms(30)
    
    async def start(self):
        self.mqtt.start()
        self.rfid.start()
        asyncio.create_task(self.oled.screensaver_loop(60000))  # positional arg
        
        await self.oled.show_status_async("SECURITY", "Starting", "")
        await asyncio.sleep_ms(500)
        
        await self.oled.show_status_async("MQTT", "Connecting", "")
        await asyncio.sleep_ms(800)
        
        await self.main_loop_utility()
    
    def time_utility(self):
        t = time.localtime()
        return f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"