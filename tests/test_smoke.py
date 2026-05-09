"""
Smoke test for ccsds-tm-tc-formatting-lab.

Run from the repository root:

    python tests/test_smoke.py

This test verifies:
1. TM sensor payload can be packetized.
2. TM CADU can be built.
3. TM RS decoding can correct injected bit errors.
4. TC command payload can be packetized.
5. TC Transfer Frame FECF validates.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from payloads import (
    Sensor,
    SwitchCommand,
    AttitudeCommand,
    build_tm_sensor_payload,
    build_tc_command_payload,
)
from ccsds_tm import (
    ASM,
    TMConfig,
    build_tm_space_packet,
    build_tm_cadu,
    receive_tm_cadu,
    flip_bits,
)
from ccsds_tc import (
    TCConfig,
    build_tc_space_packet,
    build_tc_transfer_frame,
)


def main() -> None:
    mission_id = "DEMO-SAT"

    tm_payload, sensor_notes = build_tm_sensor_payload(
        mission_id,
        [
            Sensor("BAT_V", 7.42, "V", 0.01, 0x0001),
            Sensor("BAT_I", 0.85, "A", 0.01, 0x0002),
            Sensor("SP_X", 0.31, "A", 0.01, 0x0003),
        ],
    )
    assert tm_payload, "TM payload is empty"
    assert sensor_notes, "TM sensor conversion notes are empty"

    tm_cfg = TMConfig()
    tm_packet = build_tm_space_packet(tm_payload, tm_cfg)
    tm_build = build_tm_cadu(tm_packet, tm_cfg)

    # Bit positions are relative to the randomized transmitted codeblock after ASM is removed.
    broken_randomized, events = flip_bits(tm_build["randomized"], [96, 104, 298])
    assert len(events) == 3, "Expected three injected bit-error events"

    tm_rx = receive_tm_cadu(ASM + broken_randomized, len(tm_packet), tm_cfg)
    assert tm_rx["passed"], "TM RS decode did not pass"

    tc_payload, command_notes = build_tc_command_payload(
        mission_id,
        [SwitchCommand("UHF_TX", 0x0001, True)],
        [AttitudeCommand("POINT_TARGET_1", 0x0101, 10.5, -2.0, 35.0)],
    )
    assert tc_payload, "TC payload is empty"
    assert command_notes, "TC command conversion notes are empty"

    tc_cfg = TCConfig()
    tc_packet = build_tc_space_packet(tc_payload, tc_cfg)
    tc_frame = build_tc_transfer_frame(tc_packet, tc_cfg)

    assert tc_frame["fecf_valid"] is True, "TC FECF validation failed"

    print("SMOKE TEST PASS")


if __name__ == "__main__":
    main()
