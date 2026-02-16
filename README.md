# Project 5 – 3D Printed Security Drawer Box

## Overview

This project is a 3D printed IoT security drawer box controlled by an ESP32-S3 and connected to a Raspberry Pi running NiceGUI.

The drawer unlocks via:
- RFID authentication
- Remote MQTT command from dashboard

The system verifies physical drawer movement using a reed switch and confirms unlock success or fault.

This project demonstrates:
- Embedded systems integration
- MQTT bidirectional communication
- JSON protocol design
- Mechanical + electrical + software system design
- Real-world validation logic

---

## System Architecture

ESP32 ↔ MQTT Broker ↔ Raspberry Pi (NiceGUI Dashboard)

ESP32 handles:
- RFID authentication
- Solenoid control via TB6612FNG
- Reed switch state detection
- OLED display feedback
- LED strip animations (GRB order)
- Audio feedback via DFPlayer
- Heartbeat messages

Raspberry Pi handles:
- Dashboard display
- Remote unlock command
- System logging
- Status monitoring

Architecture diagram available in:
docs/architecture/system_architecture.drawio
docs/architecture/system_architecture.png

---

## Hardware Components

- ESP32-S3
- TB6612FNG motor driver
- 5V solenoid lock
- Reed switch + magnet
- MFRC522 RFID reader
- 2.42" OLED display (SSD1309 SPI)
- NeoPixel LED strip (GRB)
- DFPlayer Mini + speaker
- 9V battery (logic)
- 4xAA battery pack (solenoid power)
- Raspberry Pi (NiceGUI host)

---

## Electrical Design

Power design:
- 9V → ESP32 extension board
- 4xAA → TB6612 VM → solenoid
- Shared GND across all systems
- LED strip powered from 5V rail
- RFID + OLED powered from 3.3V

Full wiring diagram:
docs/wiring/electrical_diagram.png

---

## MQTT Communication

Broker: broker.emqx.io  
Topic structure example:

security_box/status  
security_box/unlock  
security_box/heartbeat  

Example JSON from ESP32:

{
  "device": "security_box",
  "drawer_state": "closed",
  "rfid_result": "allowed",
  "unlock_status": "confirmed",
  "uptime": 15342
}

Example JSON from dashboard:

{
  "command": "unlock",
  "source": "dashboard"
}

Protocol documentation:
docs/protocol/mqtt_topics.md
docs/protocol/json_schema.md

---

## Unlock Logic Flow

1. RFID scanned
2. UID compared to whitelist
3. If allowed:
   - Activate solenoid pulse
   - Wait for reed switch state change
4. If reed switch confirms OPEN:
   - Report unlock confirmed
5. If no change:
   - Report FAULT
6. When drawer closes:
   - System resets to locked state

Flowchart:
docs/flowcharts/unlock_logic_flowchart.png

---

## Software Structure

### ESP32 (MicroPython)

Location:
esp32/

Contains:
- main.py
- oled controller
- solenoid driver
- rfid logic
- mqtt client
- state manager

Test utilities in:
esp32/testing/

---

### Raspberry Pi (NiceGUI)

Location:
raspberry_pi/

Contains:
- dashboard app
- MQTT subscriber
- remote unlock publisher
- system log viewer

---

## CAD Files

Location:
cad/

Contains:
- STL exports
- mechanical revisions
- final printable models

Design done in Autodesk Fusion.

---

## Testing & Validation

Validated features:

- Solenoid activation tested via TB6612
- Reed switch state confirmation
- OLED display feedback
- RFID allowed/denied logic
- MQTT communication verified
- Dashboard remote unlock verified
- Fault condition tested (no reed change)

Screenshots available in:
docs/screenshots/

---

## Known Limitations

- Battery powered (not permanent installation)
- Designed for demo usage (short-term deployment)
- LED strip full-white draw may cause voltage drop under heavy load

---

## Reflection

This project demonstrates full-stack embedded system design including:

- Mechanical CAD design
- Electrical wiring validation
- Embedded programming
- Network communication
- Web dashboard integration

Lessons learned:
- Importance of real-world confirmation (reed switch validation)
- Power distribution planning
- Tolerance control in 3D printing
- Structured MQTT protocol design

---

## Demonstration

Video demonstration available upon request.
