# ESP32-S3 Security Box — Code Documentation

This document explains how the ESP32 code works, file by file.

---

## File Overview

| File                           | Role                                             |
| ------------------------------ | ------------------------------------------------ |
| `main.py`                      | Boot sequence, creates hardware, wires callbacks |
| `box_procedures.py`            | System logic, event handlers, command router     |
| `mqtt_json_broker.py`          | WiFi + MQTT connection lifecycle                 |
| `class_files/oled_screen.py`   | SSD1306 display driver                           |
| `class_files/led_strip.py`     | WS2812 NeoPixel controller                       |
| `class_files/solenoid_lock.py` | TB6612 motor driver for latch                    |
| `class_files/reed_switch.py`   | Drawer open/close detection                      |
| `class_files/rfid_scanner.py`  | MFRC522 card reader                              |

---

## Boot Order (main.py)

The box boots in a strict order so each component can show its status on the OLED:

```
1. OledScreen   → display ready first (shows boot messages for all others)
2. LedStrip     → "LED STRIP / STARTED / OK" + idle loop starts
3. Solenoid     → "SOLENOID / STARTED / OK" (initialized locked)
4. ReedSwitch   → "REED SWITCH / STARTED / OPEN|CLOSED"
5. RFID         → created but NOT started (waits for MQTT)
6. MqttJsonBroker → connects WiFi + MQTT, shows status
7. Procedures   → wires reed callbacks, receives broker + RFID hooks
8. rfid.start() → now safe to scan cards
9. show_main_mode() → idle screen shown
```

After boot, `while True: await asyncio.sleep_ms(250)` keeps the event loop alive.

---

## box_procedures.py

**Role:** The brain of the system. Receives events from RFID, reed switch, and MQTT. Decides what to do.

### Key State Flags

| Flag                 | Purpose                                 |
| -------------------- | --------------------------------------- |
| `unlock_in_progress` | True during unlock countdown            |
| `system_locked`      | True = drop all RFID scans and commands |
| `drawer_is_open`     | True when reed detects open drawer      |

### Helper Methods

| Method                                        | What it does                                |
| --------------------------------------------- | ------------------------------------------- |
| `get_timestamp()`                             | Returns ISO-ish timestamp from RTC          |
| `publish(payload)`                            | Sends dict to MQTT (silent drop if offline) |
| `notify(line1, line2, line3, event, **extra)` | Console + OLED + optional MQTT event        |
| `ack(command, status, **extra)`               | Sends `command_ack` event back to dashboard |
| `oled_show_then_restore()`                    | Async: show text, wait, return to idle      |

### Reed Callbacks

| Callback            | Trigger                  | Actions                                                   |
| ------------------- | ------------------------ | --------------------------------------------------------- |
| `on_drawer_open()`  | Drawer physically opened | Solenoid off, show "DRAWER OPEN", publish `drawer_opened` |
| `on_drawer_close()` | Drawer physically closed | Solenoid off, publish `drawer_closed`, return to idle     |

### RFID Callbacks

| Callback                   | Trigger                  | Actions                                         |
| -------------------------- | ------------------------ | ----------------------------------------------- |
| `on_rfid_allowed(payload)` | Whitelisted card scanned | Starts `unlock_procedure_async`                 |
| `on_rfid_denied(payload)`  | Unknown card scanned     | Show "DENIED", blink red, publish `rfid_denied` |

### Unlock Procedure Steps

```
1. Guard check (already unlocking?)
2. Set system_locked = True
3. Show "ACCESS GRANTED" for 2s
4. Blink green async
5. Publish access_allowed event
6. Energize solenoid
7. 5-second countdown (break early if drawer opens)
8. De-energize solenoid
9. Branch:
   - Drawer opened → publish drawer_opened_during_unlock
   - Not opened → show "WINDOW ENDED", tail animation, publish unlock_window_ended
10. Reset flags, return to idle
```

### Command Handler

`handle_command(msg)` routes incoming JSON from dashboard:

| Command           | Action                                     |
| ----------------- | ------------------------------------------ |
| `unlock`          | Start unlock procedure (source="remote")   |
| `led_idle_on`     | Enable LED screensaver                     |
| `led_idle_off`    | Disable LED screensaver                    |
| `led_blink`       | Blink with custom RGB + times              |
| `led_idle_1`      | Switch to idle animation mode 1            |
| `led_idle_2`      | Switch to idle animation mode 2            |
| `led_tail`        | Run tail animation with color/cycles/speed |
| `led_off`         | Turn strip completely off                  |
| `set_idle_screen` | Change OLED idle text                      |
| `oled_show`       | Show custom text for hold_ms               |

---

## mqtt_json_broker.py

**Role:** Owns WiFi and MQTT connection. Reconnects forever on failure.

### Connection Strategy

1. Try primary WiFi → if fail, try fallback WiFi
2. Try primary broker → if fail, try fallback broker
3. If both brokers fail: `broker_unreachable = True`, retry in background
4. If no WiFi found: `offline = True`, retry in 30s

### Topics

| Topic              | Direction                          |
| ------------------ | ---------------------------------- |
| `MyTopic/Commands` | Subscribe (receive from dashboard) |
| `MyTopic/Events`   | Publish (send to dashboard)        |

### Key Methods

| Method             | Purpose                                     |
| ------------------ | ------------------------------------------- |
| `start(oled)`      | Launch `run_forever()` as background task   |
| `wait_ready()`     | Blocks until connected OR offline confirmed |
| `send_json(dict)`  | Publish dict as JSON to Events topic        |
| `set_callback(fn)` | Wire command handler                        |

### Receive Loop

Polls `client.check_msg()` every 30ms. When message arrives:
1. Decode JSON
2. Call `command_callback(payload)` → `procedures.handle_command()`

---

## Hardware Classes

### oled_screen.py

- **Driver:** SSD1306_SPI over SPI bus
- **Resolution:** 128×64 pixels
- **Main method:** `show_three_lines(line1, line2, line3)` — clears screen, draws 3 centered lines
- **Idle screen:** `set_idle_screen((l1, l2, l3))` stores text, `show_main_mode()` displays it
- **Async hold:** `log_now(l1, l2, l3, hold_ms)` — shows text and pauses caller

### led_strip.py

- **Driver:** NeoPixel on GPIO14
- **Count:** 50 LEDs
- **Brightness cap:** 35% max (USB power safety)

**Idle Loop System:**
- `start_idle_loop()` → launch animation task
- `stop_idle_loop()` → cancel + turn off
- `pause_idle_loop_utility()` → cancel task, keep enabled flag
- `resume_idle_loop_utility()` → restart if still enabled

**Two idle animations:**
- Mode 1: Shifting dots, single hue per frame
- Mode 2: Even/odd alternating, full rainbow

**Effects:**
- `blink_color_async(r, g, b, times)` — auto-pauses idle, blinks, resumes
- `tail_circular_async(cycles, delay_ms, r, g, b)` — chasing tail

### solenoid_lock.py

- **Driver:** TB6612FNG motor driver (A-channel)
- **GPIO:** AIN1 on pin 12
- **`on()`** → energize coil (release latch)
- **`off()`** → de-energize (lock)

### reed_switch.py

- **GPIO:** Pin 16 with pull-up
- **Logic:** LOW = closed (magnet near), HIGH = open
- **Debounce:** 1 second stable before callback fires
- **Background task:** `poll_loop()` runs forever, fires `on_open` / `on_close`

### rfid_scanner.py

- **Driver:** MFRC522 over SoftSPI
- **Whitelist:** Dict mapping UID hex → label
- **Prefix match:** `["08"]` for phones
- **Scan loop:** Runs in background, fires `on_allowed` / `on_denied`

---

## JSON Events (ESP32 → Dashboard)

| Event                         | Trigger                              | Key Fields                                   |
| ----------------------------- | ------------------------------------ | -------------------------------------------- |
| `access_allowed`              | Card accepted                        | `source`, `label`, `uid_suffix`, `timestamp` |
| `rfid_denied`                 | Card rejected                        | `source`, `data.uid_suffix`, `timestamp`     |
| `drawer_opened`               | Reed detects open                    | `timestamp`                                  |
| `drawer_closed`               | Reed detects close                   | `status`, `timestamp`                        |
| `drawer_opened_during_unlock` | Drawer opened during countdown       | `source`, `timestamp`                        |
| `unlock_window_ended`         | Countdown expired, drawer not opened | `source`, `timestamp`                        |
| `command_ack`                 | Command processed                    | `command`, `status`, `timestamp`             |
| `heartbeat`                   | Every 60s                            | `uptime_s`, `drawer`, `locked`, `timestamp`  |

---

## JSON Commands (Dashboard → ESP32)

| Command           | Parameters                           |
| ----------------- | ------------------------------------ |
| `unlock`          | none                                 |
| `led_idle_on`     | none                                 |
| `led_idle_off`    | none                                 |
| `led_off`         | none                                 |
| `led_idle_1`      | none                                 |
| `led_idle_2`      | none                                 |
| `led_blink`       | `r`, `g`, `b`, `times`               |
| `led_tail`        | `r`, `g`, `b`, `cycles`, `delay_ms`  |
| `set_idle_screen` | `line1`, `line2`, `line3`            |
| `oled_show`       | `line1`, `line2`, `line3`, `hold_ms` |
