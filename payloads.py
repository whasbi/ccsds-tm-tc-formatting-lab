"""
payloads.py

Mission-defined payloads for public CCSDS formatting lab.

These payload structures are intentionally simple and documented. They are not CCSDS-mandated;
CCSDS carries the bytes using packets/frames/coding. Missions define the user data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


MAX_SENSORS = 50
MAX_SWITCH_COMMANDS = 10
MAX_ATTITUDE_COMMANDS = 5


DTYPE_INT32_SCALED = 0x04


@dataclass
class Sensor:
    name: str
    value: float
    unit: str
    scale: float
    parameter_id: int
    enabled: bool = True


@dataclass
class SwitchCommand:
    name: str
    command_id: int
    state_on: bool
    enabled: bool = True


@dataclass
class AttitudeCommand:
    name: str
    command_id: int
    x_deg: float
    y_deg: float
    z_deg: float
    enabled: bool = True


def ascii_id_bytes(mission_id: str) -> bytes:
    mission_id = mission_id.strip()
    if not mission_id:
        raise ValueError("Mission ID text cannot be empty")
    b = mission_id.encode("ascii", errors="strict")
    if len(b) > 32:
        raise ValueError("Mission ID text is limited to 32 ASCII bytes")
    return b


def encode_scaled_int32(value: float, scale: float) -> int:
    if scale <= 0:
        raise ValueError("Scale must be > 0")
    count = int(round(value / scale))
    if not -(2**31) <= count <= (2**31 - 1):
        raise ValueError(f"Scaled count {count} does not fit signed int32")
    return count


def build_tm_sensor_payload(mission_id: str, sensors: List[Sensor]) -> tuple[bytes, list[str]]:
    enabled = [s for s in sensors if s.enabled]
    if len(enabled) > MAX_SENSORS:
        raise ValueError(f"Maximum enabled sensors is {MAX_SENSORS}")

    mid = ascii_id_bytes(mission_id)
    out = bytearray()
    out.append(len(mid))
    out += mid
    out.append(len(enabled))

    explanations = []
    for s in enabled:
        if not 0 <= s.parameter_id <= 0xFFFF:
            raise ValueError(f"Sensor {s.name}: parameter_id must be 0..65535")
        count = encode_scaled_int32(s.value, s.scale)
        out += s.parameter_id.to_bytes(2, "big")
        out.append(DTYPE_INT32_SCALED)
        out.append(0)  # scale descriptor placeholder; scale is printed in report
        out += int(count).to_bytes(4, "big", signed=True)
        explanations.append(
            f"{s.name}: value={s.value} {s.unit}, scale={s.scale}, count=round(value/scale)={count}, "
            f"PID=0x{s.parameter_id:04X}, encoded={int(count).to_bytes(4, 'big', signed=True).hex(' ').upper()}"
        )
    return bytes(out), explanations


def build_tc_command_payload(
    mission_id: str,
    switch_commands: List[SwitchCommand],
    attitude_commands: List[AttitudeCommand],
    attitude_scale_deg: float = 0.01,
) -> tuple[bytes, list[str]]:
    switches = [c for c in switch_commands if c.enabled]
    attitudes = [c for c in attitude_commands if c.enabled]
    if len(switches) > MAX_SWITCH_COMMANDS:
        raise ValueError(f"Maximum enabled switch commands is {MAX_SWITCH_COMMANDS}")
    if len(attitudes) > MAX_ATTITUDE_COMMANDS:
        raise ValueError(f"Maximum enabled attitude commands is {MAX_ATTITUDE_COMMANDS}")

    mid = ascii_id_bytes(mission_id)
    out = bytearray()
    out.append(len(mid))
    out += mid
    out.append(len(switches))
    out.append(len(attitudes))

    explanations = []

    for c in switches:
        if not 0 <= c.command_id <= 0xFFFF:
            raise ValueError(f"Switch command {c.name}: command_id must be 0..65535")
        out.append(0x01)  # command type: switch
        out += c.command_id.to_bytes(2, "big")
        out.append(1 if c.state_on else 0)
        explanations.append(
            f"SWITCH {c.name}: type=0x01, command_id=0x{c.command_id:04X}, state={'ON' if c.state_on else 'OFF'}"
        )

    for c in attitudes:
        if not 0 <= c.command_id <= 0xFFFF:
            raise ValueError(f"Attitude command {c.name}: command_id must be 0..65535")
        x = encode_scaled_int32(c.x_deg, attitude_scale_deg)
        y = encode_scaled_int32(c.y_deg, attitude_scale_deg)
        z = encode_scaled_int32(c.z_deg, attitude_scale_deg)
        out.append(0x02)  # command type: attitude instruction
        out += c.command_id.to_bytes(2, "big")
        out += int(x).to_bytes(4, "big", signed=True)
        out += int(y).to_bytes(4, "big", signed=True)
        out += int(z).to_bytes(4, "big", signed=True)
        explanations.append(
            f"ATTITUDE {c.name}: type=0x02, command_id=0x{c.command_id:04X}, "
            f"X={c.x_deg} deg->{x}, Y={c.y_deg} deg->{y}, Z={c.z_deg} deg->{z}, scale={attitude_scale_deg} deg/count"
        )

    return bytes(out), explanations
