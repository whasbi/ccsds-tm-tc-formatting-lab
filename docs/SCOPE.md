# Scope

This software teaches CCSDS-style formatting and validation:

```text
TM:
user sensors
→ mission-defined sensor payload
→ TM Space Packet
→ RS(255,223) with I=5 interleaving
→ randomizer
→ ASM/CADU
→ full RS decode trace

TC:
user commands
→ mission-defined command payload
→ TC Space Packet
→ TC Transfer Frame
→ optional FECF validation
```

BCH/CLTU and COP-1 are intentionally not implemented in this version.
