## Project Information & Purpose

This project is a security drawer box controlled by an ESP32 and connected to a Raspberry Pi running NiceGUI.  
The drawer is locked using a 5V solenoid and released via RFID or remote challenge unlock.  
The system focuses on bidirectional IoT communication using MQTT and JSON, with full dashboard control and confirmation feedback.

---

## Verified Components

- **ESP32-S3**
	- Main controller for sensors, actuators, and MQTT communication

- **5V Solenoid Lock**
	- Physically locks the drawer

- **ULN2803 Driver + Flyback Diode**
	- Safe switching and protection for solenoid

- **External 5V Power Supply**
	- Dedicated power for solenoid system

- **MFRC522 RFID Reader**
	- Card / key fob / phone NFC access control

- **Reed Switch (Drawer Sensor)**
	- Detects open / closed state of drawer


- **Capacitive Touch Sensor**
	- Touch-based interaction without mechanical buttons

- **DFPlayer Mini + Speaker**
	- Audio feedback and alarm functionality

- **LED Strips**
	- Decorative lighting and status animations

- **OLED Screen**
	- Displays system status and instructions

- **Status LED (Single RGB or Indicator LED)**
	- Quick visual system state feedback

- **Solenoid Current Sensor**
	- Confirms actual solenoid activation and detects faults

- **Raspberry Pi**
	- Runs MQTT broker and NiceGUI dashboard

---

## Measurements of Box

- The Main Box:
  - Width: 180 mm
  - Height: 140 mm
  - Depth: ? (now at 220 mm but want to reduce it so drawer can be more solid and lighter for the springs to push it)
  
  - ALL WALLS OUTER & INNER ARE 4 MM

- Breadboad with esp32:
  - Depth: 59 mm (safe min depth of breadboard + esp)
  - Width wide: 165 mm
  
- Solenoid
  - Width: 27.5 mm(from pin on the backside to the edge of the outer pin skinner)
  - Height: 12 mm
  - Depth: 12 mm

- Screen:
  - width: 62.3 mm
  - height: 40 mm

- Battery bracket (either 9v or 4xAA batteries)

- LED light (show status signal green or red)
  - Drill hole for that and just glue it in




---

## ESP32 → Raspberry Pi (NiceGUI) Data Flow

- Heartbeat status
	- Online state, uptime, signal strength

- Drawer state
	- Open / Closed

- RFID scan results
	- Allowed / Denied / Challenge mode

- Motion detection events
	- Presence detected / cleared

- Solenoid activation result
	- Confirmed open / Fault detected

- Lighting state
	- Active mode and brightness levels

- Audio state
	- Playing / Stopped / Alert mode

---

## Raspberry Pi (NiceGUI) → ESP32 Commands

- Unlock drawer
	- Timed pulse control

- Challenge unlock
	- One-time secure token validation through the rrfid sensor

- Arm / Disarm system
	- Change security mode

- Lighting control
	- Mode selection, brightness adjustment

- OLED message update
	- Display custom text

- Audio control
	- Play sound, stop sound, alarm mode

- Time-based access configuration
	- Allowed hours for unlocking

- Automation rules
	- Auto-lock delay, motion-triggered responses
