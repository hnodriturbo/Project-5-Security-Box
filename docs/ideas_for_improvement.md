# Ideas for Improvement

This document lists concrete improvement ideas with file/line references and implementation strategies.

---

## 1. Standardize JSON Structure

**Problem:** ESP32 and Dashboard use inconsistent JSON formats.

### Current Inconsistencies

| Issue           | ESP32 Example                         | Dashboard Expects                |
| --------------- | ------------------------------------- | -------------------------------- |
| Nested vs flat  | `data: {uid_suffix}` in `rfid_denied` | Checks both top-level and `data` |
| Mixed key names | `command`                             | Also checks `cmd`                |
| No type field   | Just `event` or `command`             | No way to distinguish source     |

### Proposed Standard Format

**Events (ESP32 → Dashboard):**
```json
{
  "type": "event",
  "event": "access_allowed",
  "source": "rfid",
  "timestamp": "2026-03-09 17:56:15",
  "data": {
    "uid_suffix": "FC2984",
    "label": "card"
  }
}
```

**Commands (Dashboard → ESP32):**
```json
{
  "type": "command",
  "command": "led_blink",
  "timestamp": "2026-03-09 17:56:15",
  "params": {
    "r": 255,
    "g": 0,
    "b": 0,
    "times": 3
  }
}
```

**Acknowledgements (ESP32 → Dashboard):**
```json
{
  "type": "ack",
  "command": "led_blink",
  "success": true,
  "timestamp": "2026-03-09 17:56:15"
}
```

### Files to Update

| File                                                      | Line               | Change                       |
| --------------------------------------------------------- | ------------------ | ---------------------------- |
| [box_procedures.py](esp32-s3/box_procedures.py#L239-L252) | `publish()` calls  | Wrap in standard format      |
| [box_procedures.py](esp32-s3/box_procedures.py#L95-L103)  | `ack()` method     | Add `type: "ack"`, `success` |
| [mqtt_handler.py](nicegui/mqtt_handler.py#L93-L130)       | `handle_inbound()` | Parse new format             |
| [dashboard.py](nicegui/dashboard.py#L237-L265)            | Command buttons    | Use `params` wrapper         |

---

## 2. LED Strip Zone System

**Problem:** LEDs stop and restart during effects because the whole strip is treated as one unit.

### Proposed Solution: Index-Based Zones

Split the 50 LEDs into named zones:

```python
LED_ZONES = {
    "front":  range(0, 12),     # indices 0-11
    "right":  range(12, 25),    # indices 12-24
    "back":   range(25, 38),    # indices 25-37
    "left":   range(38, 50),    # indices 38-49
}
```

### New Zone Methods

```python
def fill_zone(self, zone_name, r, g, b):
    """Fill a specific zone with color."""
    for i in LED_ZONES.get(zone_name, []):
        self.set_pixel_utility(i, r, g, b)
    self.show()

def chase_zone(self, zone_name, r, g, b, delay_ms=50):
    """Chase effect within one zone only."""
    indices = list(LED_ZONES.get(zone_name, []))
    for i in indices:
        self.set_pixel_utility(i, r, g, b)
        self.show()
        await asyncio.sleep_ms(delay_ms)
        self.set_pixel_utility(i, 0, 0, 0)
```

### Zone-Aware Idle Loop

Instead of iterating `range(led_count)`, iterate per zone:

```python
async def zone_chase_idle_async(self):
    """Chase around the box: front → right → back → left."""
    hue = 0
    while True:
        for zone in ["front", "right", "back", "left"]:
            for i in LED_ZONES[zone]:
                self.turn_off()
                r, g, b = self.hsv_to_rgb_utility(hue, 255, 200)
                self.set_pixel_utility(i, r, g, b)
                self.show()
                hue = (hue + 5) % 360
                await asyncio.sleep_ms(30)
```

### File to Update

| File                                                        | Line        | Change               |
| ----------------------------------------------------------- | ----------- | -------------------- |
| [led_strip.py](esp32-s3/class_files/led_strip.py#L51-L74)   | After init  | Add `LED_ZONES` dict |
| [led_strip.py](esp32-s3/class_files/led_strip.py#L200-L230) | New methods | Add zone fill/chase  |

---

## 3. Effect Queue System

**Problem:** Multiple effects can crash if started simultaneously.

### Current Behavior

```python
# In handle_command:
elif command == "led_blink":
    asyncio.create_task(self.led.blink_color_async(...))
elif command == "led_tail":
    asyncio.create_task(self.led.tail_circular_async(...))
```

If both are sent quickly, both tasks run and fight over the LEDs.

### Proposed Solution: Single Effect Lock

```python
class LedStrip:
    def __init__(self, ...):
        ...
        self.effect_lock = asyncio.Lock()
        self.current_effect = None

    async def run_effect(self, name, coro):
        """Queue an effect - only one runs at a time."""
        if self.effect_lock.locked():
            print(f"[LED] Dropping {name} - another effect running")
            return False
        
        async with self.effect_lock:
            self.current_effect = name
            self.pause_idle_loop_utility()
            try:
                await coro
            finally:
                self.current_effect = None
                self.resume_idle_loop_utility()
        return True
```

### Usage

```python
# In handle_command:
elif command == "led_blink":
    asyncio.create_task(self.led.run_effect(
        "blink",
        self.led.blink_color_raw_async(r, g, b, times)
    ))
```

### File to Update

| File                                                        | Line    | Change                 |
| ----------------------------------------------------------- | ------- | ---------------------- |
| [led_strip.py](esp32-s3/class_files/led_strip.py#L51-L74)   | Init    | Add `effect_lock`      |
| [led_strip.py](esp32-s3/class_files/led_strip.py#L295-L320) | Effects | Wrap in `run_effect()` |

---

## 4. Circular Flow Animation (Your Request)

**Goal:** Smooth continuous chase around all 4 sides.

### Implementation

```python
async def circular_chase_async(self, delay_ms=25, tail_length=5):
    """
    Smooth chase around all zones: front → right → back → left → repeat.
    Uses a fading tail for motion blur effect.
    """
    # Build full path: front(0-11) + right(12-24) + back(25-37) + left(38-49)
    path = list(range(50))
    tail_brightness = [255, 180, 100, 50, 20][:tail_length]
    
    self.pause_idle_loop_utility()
    hue = 0
    head = 0
    
    while self.idle_loop_enabled:  # runs until stop_idle_loop()
        # Clear strip
        for i in range(self.led_count):
            self.pixels[i] = (0, 0, 0)
        
        # Draw tail behind head
        r, g, b = self.hsv_to_rgb_utility(hue, 255, 200)
        for t, brightness in enumerate(tail_brightness):
            pos = (head - t) % len(path)
            idx = path[pos]
            br = brightness / 255
            self.set_pixel_utility(idx, int(r*br), int(g*br), int(b*br))
        
        self.show()
        
        head = (head + 1) % len(path)
        hue = (hue + 2) % 360
        await asyncio.sleep_ms(delay_ms)
    
    self.resume_idle_loop_utility()
```

### Add as Idle Mode 3

```python
def set_idle_loop(self, mode):
    self.idle_loop_mode = mode
    self.pause_idle_loop_utility()
    self.resume_idle_loop_utility()

def resume_idle_loop_utility(self):
    if self.idle_loop_enabled and self.idle_loop_task is None:
        if self.idle_loop_mode == 1:
            loop_method = self.pixel_idle_loop_async
        elif self.idle_loop_mode == 2:
            loop_method = self.pixel_idle_loop_2_async
        elif self.idle_loop_mode == 3:
            loop_method = self.circular_chase_async
        self.idle_loop_task = asyncio.create_task(loop_method())
```

### New Dashboard Button

```python
ui.button(
    "Idle 3 (Chase)",
    on_click=lambda: mqtt.publish_queue.put_nowait({"command": "led_idle_3"}),
)
```

---

## 5. Command Registration System

**Problem:** Adding commands requires editing multiple places.

### Current Flow to Add Command

1. Edit `handle_command()` in `box_procedures.py`
2. Add button in `dashboard.py`
3. Optionally add event handler in `mqtt_handler.py`

### Proposed: Command Registry

```python
# In box_procedures.py
COMMANDS = {}

def register_command(name):
    """Decorator to register a command handler."""
    def decorator(fn):
        COMMANDS[name] = fn
        return fn
    return decorator

class Procedures:
    @register_command("unlock")
    async def cmd_unlock(self, msg):
        await self.unlock_procedure_async(source="remote", label="REMOTE")
    
    @register_command("led_blink")
    async def cmd_led_blink(self, msg):
        r, g, b = msg.get("r", 0), msg.get("g", 0), msg.get("b", 255)
        await self.led.blink_color_async(r, g, b, msg.get("times", 3))
        self.ack("led_blink")

    def handle_command(self, msg):
        cmd = msg.get("command", "")
        handler = COMMANDS.get(cmd)
        if handler:
            asyncio.create_task(handler(self, msg))
        else:
            self.ack("unknown", status="fail", received=cmd)
```

### Benefits

- Self-documenting: `list(COMMANDS.keys())` shows all commands
- Centralized: Command logic lives next to its decorator
- Extensible: Easy to add metadata (help text, required params)

---

## 6. Dashboard Command Builder

**Problem:** Dashboard has hardcoded buttons for each command.

### Proposed: Dynamic Command Panel

Read available commands from a config or discover them:

```python
AVAILABLE_COMMANDS = [
    {"name": "unlock", "label": "Unlock Drawer", "params": []},
    {"name": "led_blink", "label": "Blink", "params": [
        {"name": "r", "type": "int", "min": 0, "max": 255},
        {"name": "g", "type": "int", "min": 0, "max": 255},
        {"name": "b", "type": "int", "min": 0, "max": 255},
        {"name": "times", "type": "int", "min": 1, "max": 10},
    ]},
    ...
]

def build_command_card(cmd):
    with ui.card():
        ui.label(cmd["label"])
        inputs = {}
        for param in cmd["params"]:
            inputs[param["name"]] = ui.number(param["name"], ...)
        
        def send():
            payload = {"command": cmd["name"]}
            payload.update({k: v.value for k, v in inputs.items()})
            mqtt.publish_queue.put_nowait(payload)
        
        ui.button("Send", on_click=send)
```

---

## 7. Better Error Feedback

**Problem:** When commands fail, dashboard doesn't know why.

### Current

ESP32 sends `{"event": "command_refused", "reason": "drawer is open"}` but dashboard doesn't highlight it.

### Proposed

Add toast notifications on error:

```python
# In mqtt_handler.py handle_inbound():
elif event == "command_refused":
    reason = payload.get("reason", "Unknown")
    add_log(f"⚠️ COMMAND REFUSED: {reason}")
    # Dashboard could show a toast here

elif event == "command_ack":
    if payload.get("status") == "fail":
        add_log(f"❌ COMMAND FAILED: {payload.get('command')}")
```

### Dashboard Toast

```python
# In update_ui():
last = mqtt.state.get("last_event", {})
if last.get("event") == "command_refused":
    ui.notify(last.get("reason"), type="warning")
```

---

## 8. Heartbeat Display

**Problem:** Heartbeat events are logged but not surfaced.

### Current

Only appears in log every 60s.

### Proposed

Add a status card showing:
- Uptime
- Drawer state
- Lock state
- Last heartbeat time

```python
with ui.card().classes("..."):
    ui.label("Box Status")
    status_uptime = ui.label("Uptime: --")
    status_drawer = ui.label("Drawer: --")
    status_lock = ui.label("Lock: --")
    status_last_seen = ui.label("Last seen: --")

# In update_ui():
hb = mqtt.state.get("last_heartbeat")
if hb:
    status_uptime.set_text(f"Uptime: {hb['uptime_s']}s")
    status_drawer.set_text(f"Drawer: {hb['drawer']}")
    ...
```

### File to Update

| File                                                | Line            | Change                   |
| --------------------------------------------------- | --------------- | ------------------------ |
| [mqtt_handler.py](nicegui/mqtt_handler.py#L93-L130) | handle_inbound  | Store heartbeat in state |
| [dashboard.py](nicegui/dashboard.py#L220-L230)      | After RFID card | Add status card          |

---

## 9. Reconnection Indicators

**Problem:** Dashboard badge shows connected/offline but not "reconnecting".

### Proposed States

| State        | Badge Text        | Color  |
| ------------ | ----------------- | ------ |
| Connected    | ● MQTT Connected  | Green  |
| Reconnecting | ◐ Reconnecting... | Yellow |
| Offline      | ○ MQTT Offline    | Red    |

### Add to state

```python
state = {
    ...
    "connection_state": "disconnected",  # "connected", "reconnecting", "disconnected"
}
```

---

## 10. Config Sync

**Problem:** WiFi credentials and broker IPs are hardcoded in two places.

### Files with Duplicated Config

| Config     | ESP32 Location                              | Dashboard Location                             |
| ---------- | ------------------------------------------- | ---------------------------------------------- |
| Broker IPs | [main.py#L87-L90](esp32-s3/main.py#L87-L90) | [config.py#L34-L35](nicegui/config.py#L34-L35) |
| Topics     | [main.py#L91](esp32-s3/main.py#L91)         | [config.py#L45-L47](nicegui/config.py#L45-L47) |

### Proposed

Create a shared constants file or use environment variables:

```
# .env on both systems
BROKER_PRIMARY=10.201.48.7
BROKER_FALLBACK=192.168.1.51
MQTT_TOPIC=MyTopic
```

---

## Summary: Priority Order

1. **JSON standardization** — Affects all communication
2. **Effect queue system** — Prevents LED crashes
3. **Zone system** — Enables circular flow
4. **Circular chase animation** — Specific request
5. **Command registry** — Makes adding features easier
6. **Error feedback** — Better UX
7. **Heartbeat display** — Surface hidden data
8. **Config sync** — Reduce duplication
9. **Reconnection states** — Clearer connection status
10. **Dynamic command panel** — Future-proofing
