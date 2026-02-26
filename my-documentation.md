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
- Allows micro-adjustments if the 2mm locking engagement needs repositioning.

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
- Will rail tolerances provide smooth sliding without wobble?
- Will the drawer self-align perfectly into the locking pocket?
- Will friction over time wear down the locking edge?

These will only be confirmed during:
- First full assembly
- Solenoid activation testing
- MQTT + unlock validation phase

---

## Future Reports

- ESP32 Integration Phase
- MQTT Communication Testing
- NiceGUI Dashboard Integration
- Fault Handling Validation
- Final Mechanical Assembly
- Testing & Performance Results

---