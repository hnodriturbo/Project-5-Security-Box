# Documentation of Creation of the Security Box

This document logs the development process of the 3D Printed IoT Security Drawer Box.  
It describes design decisions, challenges, mechanical iterations, and open questions during development.

---

## 15–22 Feb — Mechanical Design Phase (Autodesk Fusion)

During this period I focused heavily on the mechanical design of the box in Autodesk Fusion.  
This phase required significant precision because the solenoid locking mechanism only has approximately **2mm of usable locking pin depth**, which leaves very little room for error.

--- 

## 26 Feb - Box printing failed, but drawer and solenoid stand + handle on drawer printed

I will have the box late or on Monday, 2 days before assignment completion so i have started working on the codings, having everything connected together at home illustrating the box design. This is a complex coding system that I'm designing so for ease of commanding everything I created a class file for every component that will be used, so instances can call easily on premade functions within those instance related classes.

PROBLEM: I thought the pin would have more power but 4xAA is not giving the pin the power to pull in when pressure is on it. Even just a tiny bit of pressure so the spring system will be withdrawed from the design and unlocking will unlock for 5 seconds and user has to manually open the drawer but otherwise it's locked into place by the solenoid. I would need more power then 4xAA batteries for making the pin pull in with force or this is just so basic and small solenoid that I must redesign this. It was not the main purpose but I will have to acumulate to these conditions and create new TRUE PURPOSE of the box by having the user having to open the drawer manually when presented with phone, card, keychain or command from dashboard. I will focus more on the engine design, the lightings and more to make up for this and create fully functional dashboard with NiceGUI that can make many different commands to the box, change screen main texts, change lighting scenes, unlock with a code (code only unlock from dashboard for "security") and more features will also be available in the dashboard.

---

## 27-28 Feb & 1-3 Mar — Printing Issues & Coding Phase

After the first full box print, I immediately ran into mechanical issues. The bottom surface of the box printed uneven, which affected structural alignment and drawer seating. Because of this, the drawer did not fit correctly. I had to manually adjust and widen certain areas using tools just to make it fit temporarily inside the faulty print. This obviously changed tolerances and is not acceptable for final assembly.

As a result:

- The full box is being reprinted and I am currently waiting for the new version.
- The drawer also needs to be reprinted to restore its true dimensions.
- These corrected parts will be ready tomorrow, on the day of the deadline.
- Final mechanical construction and full assembly will happen immediately once the prints are ready.

Because I did not want to lose time while waiting for the reprint, I shifted focus entirely to the coding phase.

---

## ESP32 Software Architecture Development

While waiting for the new box print, I built and structured the entire ESP32 system from scratch. This part was significantly more complex than expected.

The main difficulty was not hardware — it was architecture.

I wanted:

- Separate class files for every hardware component  
- Clean separation between logic, hardware, and MQTT communication  
- Two independent MQTT pathways (receive and transmit)  
- Structured JSON communication  
- No dynamic guessing or unsafe method calls  
- Beginner-readable but structured code  

This caused several major debugging cycles.

Problems I faced during development:

- MQTT client queue handling errors  
- Async task crashes not being retrieved properly  
- Reconnect loops failing silently  
- JSON parsing issues  
- Multiple overlapping log functions that needed to be merged  
- OLED display not updating because async calls were blocked  
- Unlock flow timers interfering with display logic  
- RFID scan loop not running due to incorrect task structure  
- ESP disconnecting after publish attempts  
- Attribute errors due to inconsistent broker methods  

The system had to be redesigned more than once to make it clean and understandable.

Eventually, I simplified everything into:

- A central `SecurityBoxController`  
- Explicit `CommandRouter`  
- One unified logging system  
- Minimal JSON messages  
- Two MQTT topics:  
  - Subscribe: `1404TOPIC/Commands`  
  - Publish: `1404TOPIC/Events`  
- Clear async task separation  
- Component classes that only do their own job  

After many iterations and structural changes, the ESP32 code is now stable and behaves as expected. HOPEFULLY!

---

## NiceGUI Dashboard & Broker Setup

While developing the ESP32 code, I also completed the NiceGUI dashboard.

I am using my own MQTT broker setup at home.  
Connection between:

ESP32 ↔ Broker ↔ NiceGUI

is working properly.

The dashboard can:

- Send unlock commands  
- Trigger LED effects  
- Change OLED screen text  
- Display structured events from the ESP  
- Log events with timestamps  
- Handle connection and reconnection states  

After a large number of debugging cycles and communication fixes, the full ESP ↔ MQTT ↔ NiceGUI communication loop is functioning correctly.

---

## Current Status Before Final Assembly

At this point:

- Solenoid works electrically - NOTE: SOMETIMES I NEED TO MOVE WIRES OR KNOCK ON THE SOLENOID FOR IT TO WORK - POSSIBLE HUGE PROBLEM !!!
- MQTT communication is verified  
- NiceGUI dashboard is fully operational  
- All component classes are structured and separated  
- LED strip effects and unlock flow logic completed  
  
- Reed switch should block everything that's going on and display on screen DRAWER OPEN until the magnet on the drawer connects the reed switch (then unlock the screen and loop)
- ESP32 code is stable except for reed sensor testing that is hard to do when not with the printed box and magnet glued on the drawer

Remaining steps:

- Receive corrected box and drawer print  
- Assemble full hardware  
- Mount electronics  
- Perform final mechanical alignment  
- Validate full unlock + drawer interaction  
- Record final test results  
  
Despite multiple mechanical and coding setbacks, the system is now logically complete and ready for final physical integration. (without reed sensor)

---

# Project information !!!

### CAD Tool Decision

I chose Autodesk Fusion because it provides:

- Parametric modeling
- Precise dimensional control
- Better constraint handling
- Timeline-based modification for iterative design

This project requires millimeter-level precision, especially around:
- Solenoid placement
- Drawer rail tolerances
- Reed switch alignment
- Magnet positioning

---

### Solenoid Mount Strategy

One important architectural decision was to design the solenoid stand as a **separate modular component** that will be glued into place.

Reasoning:

- If tolerances are slightly off after printing, I can reprint only the solenoid mount.
- Avoids reprinting the entire box structure.
- Allows micro-adjustments if the 2mm locking engagement needs repositioning
  
### Solenoid update 3.3.2026
- After positioning solenoid in the solenoid 3d printed stand it is exactly like it's supposed to be and fits perfectly even with its 1.7mm locking space inside the side of the drawer. Only check left is to see if it will open when springs on drawer will put light pressure on it (must have full battery power for stronger solenoid signal).
---

### Drawer & Internal Structure Challenges

Designing the internal structure took significantly more time than expected.

Key challenge:
Creating a space behind the inner drawer wall for:
- Springs
- Reed switch
- Magnet alignment

Final decision:
- **10mm gap** between drawer back wall and inner back wall.
- Magnet glued to rear of drawer.
- Reed switch mounted on internal wall.
- On closed position → magnet activates reed sensor.
- Solenoid engages locking pocket.

Because of spring pressure pushing the drawer forward, this entire system requires:
- Precise rail guidance
- Minimal side wobble
- Controlled alignment at locking point

To achieve this I:

- Increased wall thickness to **5mm standard**
- Added structural rails
- Designed inner reinforcement walls
- Added a mechanical stopper feature at the front so the drawer seats fully before rail alignment takes over

---

### Rail & Tolerance Adjustments

Several iterations were made regarding:

- Side clearances (0.3–0.6 mm precision clearences?)
- Vertical rail spacing
- Rail width (4mm → considered 5mm)
- Friction concerns with solenoid side-contact

Because the solenoid does not have a latch hook, friction against its body was a major design constraint.  
A slide geometry was introduced to gently push the solenoid inward ~1mm before it drops into the locking pocket.

The locking pocket itself was extended upward to allow manual widening with tools if necessary after printing.

---

### Front Panel & Electronics Mounting

Additional design work completed:

- Screw holes (4mm diameter, 10mm depth planned)
- Reinforced lid screw zones (extra material added)
- Inward extrudes for PCB mounting (OLED + RFID)
- Relief cut for OLED header pins
- Circular opening for RFID antenna to improve signal reliability

Special attention was given to:
- Avoiding stress concentration at corners
- Ensuring enough material thickness behind PCB mount areas
- Making sure drawer removal remains possible

---

### Power & Structural Considerations

Power design:
- 9V battery for ESP32 logic rail
- 4xAA battery pack for solenoid
- Shared ground

Concerns:
- Solenoid draws ~1A+
- LED strip can draw multiple amps at full white
- Risk of ESP brownout under heavy load

Structural reinforcement was added where necessary to reduce flex around locking area.

---

### Open Questions (To Be Answered After First Print)

The following mechanical uncertainties cannot be confirmed until physical testing:

- Will the 2mm solenoid locking depth reliably hold the drawer while springs push forward?

- When spring force is applied to the locking pin, will the solenoid release smoothly or bind due to lateral pressure?
  -  TRUE - Solenoid cannot open when even the slightest pressure is on it. I have no time to reprint new design to make the locking in a different way structurally. But would if i had more // 🕗 

- Will rail tolerances provide smooth sliding without wobble?

- Will the drawer self-align perfectly into the rails and locking pin lock the drawer?

- Will friction over time wear down the locking edge?
  - No it will not since this is only a part project that will be taken apart when finished.

These will only be confirmed during:
- First full assembly
- Solenoid activation testing
- MQTT + unlock validation phase

---

## Future Reports

- ESP32 Integration Phase :
  - 
- MQTT Communication Testing :
  - 
- NiceGUI Dashboard Integration :
  - 
- Fault Handling Validation :
  - 
- Final Mechanical Assembly:
  - 
- Testing & Performance Results:
  - Testing the solenoid with all connected parts (not inside the box) seems good. Only problem is we need to exclude the springs because the solenoid will not open when friction is pushing on it by the springs pushing the drawer outwards.

---