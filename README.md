# CCSDS-TM-TC-Formatting-lab
[https://doi.org/10.5281/zenodo.20091994](https://zenodo.org/badge/DOI/10.5281/zenodo.20091994.svg)

Developed by **Wahyudi Hasbi**  
Licensed under the **MIT License**

Transparent CCSDS TM/TC formatting lab for study.

This public version is generic. It does not use any mission-specific hard-coded satellite name.

## Implemented

- User-defined mission ID text carried inside the Packet Data Field
- Up to 50 numeric TM sensor records
- TM Space Packet construction
- TM RS(255,223), `E=16`, full encode/decode trace
- TM RS interleaving, default `I=5`
- TM pseudo-randomizer demonstration and ASM/CADU generation
- Up to 10 switch ON/OFF TC commands
- Up to 5 attitude instruction commands for OBDH → ADCS pointing simulation
- TC Space Packet construction
- TC Transfer Frame primary header
- Optional TC FECF validation
- Full display of constants, configuration fields, byte values, bit positions, and timing

## Not implemented

- TC BCH/CLTU
- COP-1
- Authentication/security services
- Flight-qualified CCSDS conformance certification

## Run

```bash
python ccsds_gui.py
```

On Windows, with Python installed:

```bat
py ccsds_gui.py
```

## The boundary

This is a transparent implementation. It is designed to make bytes, fields, parity, correction, and frame validation visible.

It is not flight software and should not be used for operational spacecraft commanding or telemetry processing without independent conformance testing.

## Repository name

Recommended GitHub name:

```text
ccsds-tm-tc-formatting-lab
```
