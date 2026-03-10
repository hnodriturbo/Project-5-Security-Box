# NiceGUI Dashboard — Code Documentation

This document explains how the dashboard code works, file by file.

---

## File Overview

| File              | Role                                                   |
| ----------------- | ------------------------------------------------------ |
| `config.py`       | Broker addresses, topics, access code, server settings |
| `mqtt_handler.py` | MQTT connection + publish/subscribe loops              |
| `dashboard.py`    | Web UI built with NiceGUI                              |

---

## config.py

Central configuration file. All settings in one place.

| Setting           | Value              | Purpose                  |
| ----------------- | ------------------ | ------------------------ |
| `BROKER_PRIMARY`  | `10.201.48.7`      | School Raspberry Pi      |
| `BROKER_FALLBACK` | `192.168.1.51`     | Home broker              |
| `BROKER_PORT`     | `1883`             | Standard MQTT port       |
| `TOPIC_EVENTS`    | `MyTopic/Events`   | Subscribe (from ESP32)   |
| `TOPIC_COMMANDS`  | `MyTopic/Commands` | Publish (to ESP32)       |
| `ACCESS_CODE`     | `1404`             | Dashboard unlock code    |
| `NICEGUI_HOST`    | `0.0.0.0`          | Listen on all interfaces |
| `NICEGUI_PORT`    | `8090`             | Web server port          |
| `MAX_LOG_LINES`   | `100`              | Event log buffer size    |

**Windows fix:** Sets `WindowsSelectorEventLoopPolicy` for aiomqtt compatibility.

---

## mqtt_handler.py

**Role:** Owns MQTT connection in a background thread. Dashboard only reads shared state.

### Shared State

```python
state = {
    "mqtt_connected": False,    # True when subscribed
    "last_rfid": None,          # {result, display, ts}
    "last_event": None,         # Raw last payload
    "active_broker": None,      # Which broker is connected
}

log_lines = []                  # Event log entries
publish_queue = queue.Queue()   # Commands waiting to send
```

### Why a Separate Thread?

NiceGUI runs its own asyncio loop. aiomqtt needs `add_reader`/`add_writer` which only work on `SelectorEventLoop`. Windows defaults to `ProactorEventLoop`. Solution: run MQTT in a dedicated thread with its own `SelectorEventLoop`.

### Two Async Loops

| Loop                  | Purpose                                       |
| --------------------- | --------------------------------------------- |
| `mqtt_receive_loop()` | Subscribe to Events, process incoming JSON    |
| `mqtt_publish_loop()` | Drain `publish_queue`, send to Commands topic |

### Connection Flow

```
1. Try BROKER_PRIMARY
2. If fail, try BROKER_FALLBACK
3. If both fail, retry up to MAX_CONNECTION_RETRIES
4. After max retries, reset counter and keep trying forever
5. On success, subscribe to TOPIC_EVENTS
6. Receive messages via async for message in client.messages
```

### handle_inbound(payload)

Routes incoming events from ESP32:

| Event                 | Action                                        |
| --------------------- | --------------------------------------------- |
| `access_allowed`      | Update `last_rfid` with label/uid_suffix, log |
| `rfid_denied`         | Update `last_rfid` with DENIED status, log    |
| `box_online`          | Log message                                   |
| `unlock_window_ended` | Log                                           |
| (any other)           | Log raw event data                            |

### Payload Parsing

Checks both top-level and nested `data` dict for `label`/`uid_suffix`:
```python
label = payload.get("label", "") or data.get("label", "")
uid_sfx = payload.get("uid_suffix", "") or data.get("uid_suffix", "")
```

---

## dashboard.py

**Role:** NiceGUI web application. Builds the UI, reads MQTT state, sends commands.

### Startup Flow

```
1. @app.on_startup: mqtt.start_mqtt_thread()
2. Browser visits /
3. @ui.page("/") index() builds the page
4. ui.timer(0.5s) refreshes UI elements
```

### UI Structure

```
┌─────────────────────────────────────────┐
│ Header: "Security Box Dashboard" + Badge│
├─────────────────────────────────────────┤
│ CARD 1: Access Gate                     │
│   - Code input + Unlock/Lock button     │
│   - Controls column (hidden by default) │
├─────────────────────────────────────────┤
│ CARD 2: Last RFID Event                 │
│   - Shows [ALLOWED/DENIED] label @ time │
├─────────────────────────────────────────┤
│ CONTROLS (when unlocked):               │
│   - Drawer Unlock card                  │
│   - LED Strip card                      │
│   - OLED Display card                   │
├─────────────────────────────────────────┤
│ CARD 3: Event Log                       │
│   - Scrollable terminal view            │
└─────────────────────────────────────────┘
```

### Access Gate Logic

```python
def toggle_access():
    if not dashboard_unlocked:
        if code == ACCESS_CODE:
            controls.set_visibility(True)
            toggle_btn.set_text("🔒 Lock Dashboard")
    else:
        controls.set_visibility(False)
        toggle_btn.set_text("Unlock Dashboard")
```

### UI Timer (0.5s interval)

```python
ui.timer(0.5, lambda: (update_ui(), render_log.refresh()))
```

- `update_ui()`: Updates MQTT badge and Last RFID label
- `render_log.refresh()`: Re-renders event log from `mqtt.log_lines`

### Sending Commands

**Rule:** Never publish inline. Always use the queue.

```python
mqtt.publish_queue.put_nowait({"command": "unlock"})
```

The `mqtt_publish_loop()` drains this queue and sends to broker.

### Command Buttons

| Button          | JSON Sent                                                                     |
| --------------- | ----------------------------------------------------------------------------- |
| UNLOCK DRAWER   | `{"command": "unlock"}`                                                       |
| Screensaver ON  | `{"command": "led_idle_on"}`                                                  |
| Screensaver OFF | `{"command": "led_idle_off"}`                                                 |
| Strip OFF       | `{"command": "led_off"}`                                                      |
| Idle 1          | `{"command": "led_idle_1"}`                                                   |
| Idle 2          | `{"command": "led_idle_2"}`                                                   |
| Blink           | `{"command": "led_blink", "r": X, "g": Y, "b": Z, "times": N}`                |
| Run Tail        | `{"command": "led_tail", "r": X, "g": Y, "b": Z, "cycles": N, "delay_ms": M}` |
| Set Idle Screen | `{"command": "set_idle_screen", "line1": "...", ...}`                         |
| Send to OLED    | `{"command": "oled_show", "line1": "...", "hold_ms": N}`                      |

### Event Log Rendering

```python
@ui.refreshable
def render_log():
    for line in reversed(mqtt.log_lines):
        if "DENIED" in line:
            css = "text-red-400"
        elif "ALLOWED" in line:
            css = "text-green-400"
        elif "📥 IN:" in line:
            css = "text-blue-400"
        ...
```

Color coding:
- Red: denied, error, fail
- Green: allowed, sent, connected
- Blue: incoming messages
- Yellow: outgoing messages
- White: other

---

## JSON Events Received (ESP32 → Dashboard)

| Event            | Key Fields                                   | UI Update                  |
| ---------------- | -------------------------------------------- | -------------------------- |
| `access_allowed` | `source`, `label`, `uid_suffix`, `timestamp` | Last RFID label, log       |
| `rfid_denied`    | `data.uid_suffix`, `timestamp`               | Last RFID label (red), log |
| `drawer_opened`  | `timestamp`                                  | Log                        |
| `drawer_closed`  | `status`, `timestamp`                        | Log                        |
| `command_ack`    | `command`, `status`                          | Log                        |
| `heartbeat`      | `uptime_s`, `drawer`, `locked`               | Log                        |

---

## JSON Commands Sent (Dashboard → ESP32)

| Command           | Parameters                           | Purpose               |
| ----------------- | ------------------------------------ | --------------------- |
| `unlock`          | none                                 | Remote drawer open    |
| `led_idle_on`     | none                                 | Start screensaver     |
| `led_idle_off`    | none                                 | Stop screensaver      |
| `led_off`         | none                                 | Strip dark            |
| `led_idle_1`      | none                                 | Idle mode 1           |
| `led_idle_2`      | none                                 | Idle mode 2           |
| `led_blink`       | `r`, `g`, `b`, `times`               | Colored blink         |
| `led_tail`        | `r`, `g`, `b`, `cycles`, `delay_ms`  | Tail animation        |
| `set_idle_screen` | `line1`, `line2`, `line3`            | Change OLED idle text |
| `oled_show`       | `line1`, `line2`, `line3`, `hold_ms` | Show temp message     |

---

## Running the Dashboard

**On Raspberry Pi:**
```bash
cd nicegui
python dashboard.py
# Open http://10.201.48.7:8090
```

**On Windows (development):**
```powershell
cd nicegui
.\.venv\Scripts\Activate.ps1
python dashboard.py
# Open http://localhost:8090
```
