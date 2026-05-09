# CCSDS-TM-TC-Formatting-lab
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20091994.svg)](https://doi.org/10.5281/zenodo.20091994)

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

## Repository structure

    ccsds-tm-tc-formatting-lab/
    ├── ccsds_gui.py                 # Main GUI application
    ├── ccsds_packets.py             # CCSDS Space Packet construction and parsing
    ├── ccsds_rs.py                  # Reed-Solomon RS(255,223) encoder/decoder
    ├── ccsds_tm.py                  # TM chain: Space Packet, RS, interleaving, randomizer, ASM/CADU
    ├── ccsds_tc.py                  # TC chain: Space Packet, TC Transfer Frame, FECF
    ├── payloads.py                  # TM sensor and TC command payload encoding
    ├── requirements.txt             # Python requirements
    ├── run_gui_windows.bat          # Windows launcher
    ├── README.md                    # Project overview and usage
    ├── LICENSE                      # MIT License
    ├── CITATION.cff                 # Citation metadata and Zenodo DOI
    ├── .gitignore                   # Files ignored by Git
    │
    ├── docs/
    │   ├── CONSTANTS_AND_FIELDS.md  # CCSDS constants and field explanations
    │   └── SCOPE.md                 # Scope and implementation boundary
    │
    ├── examples/
    │   └── demo_config.json         # Example input configuration
    │
    └── tests/
        └── test_smoke.py            # Basic TM/TC smoke test

## License

This project is licensed under the MIT License. See `LICENSE`.

## Credit

If you use, modify, or redistribute this software, keep the credit and license notice:

    Developed by Wahyudi Hasbi | Licensed under the MIT License

## Citation

If you use this software in academic work, reports, or publications, please cite:

    Wahyudi Hasbi. (2026). CCSDS-TM-TC-Formatting-lab (v1.0.0). Zenodo. https://doi.org/10.5281/zenodo.20091994
