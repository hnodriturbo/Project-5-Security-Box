# Project 5 – 3D Printed Security Drawer Box

## Overview

3D printed IoT security drawer box built around an ESP32-S3 + Raspberry Pi (NiceGUI).

Unlock:
- RFID authentication
- Remote MQTT unlock from dashboard

The system validates real physical movement using a reed switch and reports unlock confirmed vs fault.

---

## System Architecture

ESP32 ↔ MQTT Broker ↔ Raspberry Pi (NiceGUI)

ESP32:
- RFID auth
- Solenoid control (TB6612FNG)
- Reed switch state detection
- OLED feedback
- LED animations
- Heartbeat + JSON status

Raspberry Pi:
- Dashboard UI
- Remote unlock command
- Status monitoring
- Logging

Architecture file:
- `draw.io/Project-5-Final.drawio`
- `draw.io/Project-5-Final.png` (for GitHub preview)

---

## Hardware

- ESP32-S3  
- TB6612FNG motor driver  
- 5V solenoid lock  
- Reed switch + magnet  
- MFRC522 RFID reader  
- 2.42" OLED (SSD1309 SPI)  
- NeoPixel LED strip  
- 9V battery (logic)  
- 4xAA battery pack (solenoid)  
- Raspberry Pi  

---

## MQTT

Broker: `broker.emqx.io`
Backup Broker: 

Topics:
- `security_box/status`
- `security_box/unlock`
- `security_box/heartbeat`

### ESP32 JSON example

    {
      "device": "security_box",
      "drawer_state": "closed",
      "rfid_result": "allowed",
      "unlock_status": "confirmed",
      "uptime": 15342
    }

### Dashboard command example

    {
      "command": "unlock",
      "source": "dashboard"
    }

Protocol:
- MQTT
- JSON

---

## Unlock Logic

1. RFID scanned  
2. UID checked against whitelist  
3. If allowed → solenoid pulse  
4. Wait for reed switch change  
5. If OPEN detected → confirm unlock  
6. If no change → fault  
7. Drawer closes → reset to locked  

Flowchart included in draw.io project.

---

## Software Structure

### ESP32 (MicroPython) — `esp32/`

- main.py will import and use special files for handling each part. 
  - This will be the most challenging part in coding, making everything fit together in one file.
- rfid logic  
- solenoid control  
- mqtt client  
- state manager  
- oled control  

Testing utilities:
- `esp32/testing/`

### Raspberry Pi (NiceGUI) — `raspberry_pi/`

- dashboard app  
- MQTT subscriber  
- remote unlock publisher  
- log viewer  

---

## CAD

`cad/`

- STL exports  
- Final printable box  
- Drawer  
- Solenoid mounting structure  

Designed in Autodesk Fusion.

---

## Testing & Validation

Validated:

- Dashboard usage
- Solenoid activation - OLED Shows confirmation
- Reed switch confirmation - OLED - || -
- RFID allow/deny logic - OLED - || -
- MQTT communication - OLED - || -
- Remote unlock via dashboard with correct code - OLED - || -
- Fault handling done in code - OLED - || -

Screenshots:
- `docs/screenshots/`

---

## Known Limits

- Battery powered (demo build)  
- Heavy LED + solenoid load may cause voltage drop  

---

## Optional (If Time)

- DFPlayer Mini + speaker for audio feedback  