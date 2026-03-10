# Fitting Together — ESP32 + NiceGUI Communication

This document explains how the ESP32 and Dashboard work together.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      Mosquitto Broker                            │
│                   (on Raspberry Pi or Home Server)               │
│                                                                  │
│   MyTopic/Commands ◄──────────────── MyTopic/Events ◄─────────  │
│         │                                   ▲                    │
│         ▼                                   │                    │
│   ┌─────────────┐                   ┌───────┴───────┐            │
│   │   ESP32     │                   │   Dashboard   │            │
│   │ subscribes  │                   │   subscribes  │            │
│   └─────────────┘                   └───────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

**Bi-directional flow:**
- **Dashboard → ESP32:** Commands via `MyTopic/Commands`
- **ESP32 → Dashboard:** Events via `MyTopic/Events`

---

## Connection Sequence

### ESP32 Side

```
1. main.py boots all hardware
2. MqttJsonBroker.start() launches run_forever() task
3. Try primary WiFi (TskoliVESM), fallback (Hringdu-jSy6)
4. Try primary broker (10.201.48.7), fallback (192.168.1.51)
5. Subscribe to MyTopic/Commands
6. receive_loop() polls check_msg() every 30ms
7. On disconnect, reconnect forever
```

### Dashboard Side

```
1. on_startup() calls mqtt.start_mqtt_thread()
2. Separate thread with SelectorEventLoop
3. Try BROKER_PRIMARY, then BROKER_FALLBACK
4. Subscribe to MyTopic/Events
5. mqtt_receive_loop() reads messages via async for
6. mqtt_publish_loop() drains publish_queue, sends to Commands
7. On disconnect, reconnect forever
```

---

## Message Flow Examples

### Example 1: Card Scan (RFID → Dashboard)

```
[ESP32 RFID scanner detects card]
        │
        ▼
[on_rfid_allowed() called]
        │
        ▼
[unlock_procedure_async() starts]
        │
        ▼
[publish() sends JSON to MyTopic/Events]
        │
        ▼
    ┌───────────────────────────────────────┐
    │ {"event": "access_allowed",           │
    │  "source": "rfid",                    │
    │  "label": "card",                     │
    │  "uid_suffix": "FC2984",              │
    │  "timestamp": "2026-03-09 17:56:15"}  │
    └───────────────────────────────────────┘
        │
        ▼
[Dashboard mqtt_receive_loop() receives]
        │
        ▼
[handle_inbound() updates state["last_rfid"]]
        │
        ▼
[ui.timer refreshes Last RFID label]
```

### Example 2: Remote Unlock (Dashboard → ESP32)

```
[Operator clicks UNLOCK DRAWER button]
        │
        ▼
[publish_queue.put_nowait({"command": "unlock"})]
        │
        ▼
[mqtt_publish_loop() drains queue]
        │
        ▼
[Publishes to MyTopic/Commands]
        │
        ▼
    ┌───────────────────────────────────────┐
    │ {"command": "unlock"}                 │
    └───────────────────────────────────────┘
        │
        ▼
[ESP32 receive_loop() → on_message()]
        │
        ▼
[procedures.handle_command({"command": "unlock"})]
        │
        ▼
[unlock_procedure_async(source="remote", label="REMOTE")]
        │
        ▼
[ESP32 publishes access_allowed event back]
```

### Example 3: LED Control (Dashboard → ESP32)

```
[Operator sets R=255, G=0, B=0, times=5]
[Clicks "Blink" button]
        │
        ▼
    ┌───────────────────────────────────────┐
    │ {"command": "led_blink",              │
    │  "r": 255, "g": 0, "b": 0,            │
    │  "times": 5}                          │
    └───────────────────────────────────────┘
        │
        ▼
[ESP32 handle_command() matches "led_blink"]
        │
        ▼
[asyncio.create_task(led.blink_color_async(255, 0, 0, times=5))]
        │
        ▼
[ack("led_blink") sends command_ack back]
```

---

## JSON Structure Comparison

### Current ESP32 → Dashboard Events

| Event            | Structure                                                |
| ---------------- | -------------------------------------------------------- |
| `access_allowed` | `{event, source, label, uid_suffix, timestamp}`          |
| `rfid_denied`    | `{event, source, status, data: {uid_suffix}, timestamp}` |
| `drawer_opened`  | `{event, timestamp}`                                     |
| `drawer_closed`  | `{event, status, timestamp}`                             |
| `command_ack`    | `{event, command, status, timestamp}`                    |
| `heartbeat`      | `{event, uptime_s, drawer, locked, timestamp}`           |

### Current Dashboard → ESP32 Commands

| Command           | Structure                                 |
| ----------------- | ----------------------------------------- |
| `unlock`          | `{command}`                               |
| `led_blink`       | `{command, r, g, b, times}`               |
| `led_tail`        | `{command, r, g, b, cycles, delay_ms}`    |
| `set_idle_screen` | `{command, line1, line2, line3}`          |
| `oled_show`       | `{command, line1, line2, line3, hold_ms}` |

---

## State Synchronization

### What Dashboard Knows

| State          | Source                    | How Updated                                    |
| -------------- | ------------------------- | ---------------------------------------------- |
| MQTT connected | `state["mqtt_connected"]` | Set in receive loop on connect/disconnect      |
| Last RFID      | `state["last_rfid"]`      | Updated by `handle_inbound()` on access events |
| Last event     | `state["last_event"]`     | Raw payload of most recent event               |
| Event log      | `log_lines[]`             | `add_log()` on every significant event         |

### What ESP32 Knows

| State              | Source                          | How Updated                     |
| ------------------ | ------------------------------- | ------------------------------- |
| Drawer state       | `reed.is_open`                  | Reed switch poll loop           |
| Unlock in progress | `procedures.unlock_in_progress` | Set/cleared by unlock procedure |
| System locked      | `procedures.system_locked`      | Set during procedures           |
| MQTT connected     | `broker.connected`              | Set in connection loop          |

---

## Offline Behavior

### ESP32 Without Broker

```
1. WiFi connects
2. Both brokers unreachable
3. broker_unreachable = True
4. main.py continues to rfid.start()
5. RFID scanning works locally
6. unlock_procedure_async() runs normally
7. publish() silently drops messages
8. Background retry every 120s
```

### ESP32 Without WiFi

```
1. Neither SSID in range
2. offline = True
3. OLED shows "Net, Broker / Not Available / Scan RFID"
4. System fully functional locally
5. Background retry every 30s
```

### Dashboard Without Broker

```
1. Both brokers unreachable
2. state["mqtt_connected"] = False
3. Badge shows "○ MQTT Offline"
4. Commands queued in publish_queue
5. Retry connection forever
```

---

## Timing Relationships

| Event                | Timing              |
| -------------------- | ------------------- |
| Dashboard UI refresh | Every 0.5s          |
| ESP32 heartbeat      | Every 60s           |
| ESP32 MQTT poll      | Every 30ms          |
| Reed switch debounce | 1s stable           |
| RFID scan delay      | 150ms between reads |
| Unlock countdown     | 5 seconds           |

---

## Error Handling

### ESP32 Side

| Failure               | Response                        |
| --------------------- | ------------------------------- |
| WiFi disconnect       | `run_forever()` reconnects      |
| Broker disconnect     | Mark `connected = False`, retry |
| JSON parse error      | Log to console, ignore message  |
| Command handler crash | Log error, continue             |

### Dashboard Side

| Failure           | Response                             |
| ----------------- | ------------------------------------ |
| Broker disconnect | Mark `mqtt_connected = False`, retry |
| JSON parse error  | Log "Parse error", ignore message    |
| Publish fail      | Try all brokers, log if all fail     |

---

## Adding a New Command (Step by Step)

### 1. Add handler in box_procedures.py

```python
# In handle_command():
elif command == "my_new_command":
    value = msg.get("value", 0)
    # Do something with value
    self.ack("my_new_command")
```

### 2. Add button in dashboard.py

```python
ui.button(
    "My New Command",
    on_click=lambda: mqtt.publish_queue.put_nowait({
        "command": "my_new_command",
        "value": 42,
    }),
)
```

### 3. (Optional) Add event handling in mqtt_handler.py

```python
# In handle_inbound():
elif event == "my_new_event":
    add_log("My new event: {}".format(data))
```

---

## Topic Summary

| Topic              | Publisher | Subscriber |
| ------------------ | --------- | ---------- |
| `MyTopic/Commands` | Dashboard | ESP32      |
| `MyTopic/Events`   | ESP32     | Dashboard  |
