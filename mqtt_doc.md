# MQTT Architecture Documentation  
Project 5 – 3D Printed Security Drawer Box  

---

# 1. Overview

This system uses a local MQTT broker running on the Raspberry Pi to connect:

- ESP32-S3 (MicroPython device inside the box)  
- NiceGUI dashboard (running on Raspberry Pi)  
- Mosquitto broker (running on Raspberry Pi)  

The broker acts as a message router between ESP32 and NiceGUI.

There is no direct communication between ESP32 and NiceGUI.  
All communication flows through MQTT.

---

# 2. System Architecture

## ESP32-S3

- RFID reader (MFRC522)  
- Reed switch (drawer state)  
- Solenoid (TB6612FNG driver)  
- OLED display  
- NeoPixel LED strip (GRB)  
- DFPlayer audio  
- MQTT client (MicroPython)

## Raspberry Pi

- Mosquitto MQTT Broker (port 1883)  
- NiceGUI Dashboard (Python application)  
- MQTT client inside NiceGUI  

---

# 3. Network Structure

## MQTT Broker

Runs locally on Raspberry Pi:

`Mosquitto`  
`Port: 1883`  
`Listener: 0.0.0.0`  
`Anonymous: true (demo mode)`

BROKER IP !!!!
`10.201.48.7`

## Connection Targets

| Device   | Broker Address |
| -------- | -------------- |
| NiceGUI  | `127.0.0.1`    |
| ESP32-S3 | `10.201.48.77` |

---

# 4. Communication Flow

ESP32 publishes telemetry → Broker → NiceGUI receives  
NiceGUI publishes commands → Broker → ESP32 receives  

The broker is the central router.

---

# 5. Topic Structure

Base namespace:

`security_box/`

## 5.1 Telemetry (ESP32 → Pi)

`security_box/telemetry/heartbeat`  
`security_box/telemetry/drawer_state`  
`security_box/telemetry/system_status`

## 5.2 Events (ESP32 → Pi)

`security_box/event/rfid`  
`security_box/event/unlock_result`  
`security_box/event/fault`

## 5.3 Commands (Pi → ESP32)

`security_box/cmd/unlock`  
`security_box/cmd/led`   
`security_box/cmd/oled`

---

# 6. Unlock Flow Example

1. RFID scanned on ESP32  
2. ESP32 checks allowed UID  
3. If allowed:  
   - Activate solenoid  
   - Wait for reed switch change  
   - Publish `security_box/event/unlock_result`  
4. NiceGUI receives and logs result  

Remote unlock works similarly:

1. NiceGUI publishes to `security_box/cmd/unlock`  
2. ESP32 activates solenoid  
3. Reed switch validates open  
4. ESP32 publishes unlock result  

---

# 7. Summary

Raspberry Pi runs:

- Mosquitto (MQTT message router)  
- NiceGUI dashboard  

ESP32 runs:

- Hardware control logic  
- MQTT client  

All communication is JSON over MQTT using a structured namespace.