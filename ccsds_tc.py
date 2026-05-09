"""
ccsds_tc.py

TC chain:
TC Space Packet -> TC Transfer Frame -> optional FECF validation.

Not implemented:
- TC BCH/CLTU
- COP-1
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ccsds_packets import build_space_packet, SpacePacketConfig


@dataclass
class TCConfig:
    tc_apid: int = 200
    tc_sequence_count: int = 7
    bitrate_bps: int = 1200
    tfvn: int = 0
    bypass: int = 0
    control: int = 0
    spare: int = 0
    scid: int = 0x2AA
    vcid: int = 0
    frame_sequence_number: int = 7
    include_fecf: bool = True
    space_packet_config: SpacePacketConfig = field(default_factory=SpacePacketConfig)


def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """
    FECF calculation using generator polynomial:
        G(X) = X^16 + X^12 + X^5 + 1 = 0x1021
    """
    poly = 0x1021
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def build_tc_space_packet(payload: bytes, cfg: TCConfig) -> bytes:
    return build_space_packet(
        packet_type=1,
        apid=cfg.tc_apid,
        sequence_count=cfg.tc_sequence_count,
        data_field=payload,
        config=cfg.space_packet_config,
    )


def validate_tc_config(cfg: TCConfig) -> None:
    checks = [
        ("TFVN", cfg.tfvn, 0, 3),
        ("Bypass", cfg.bypass, 0, 1),
        ("Control", cfg.control, 0, 1),
        ("Spare", cfg.spare, 0, 3),
        ("SCID", cfg.scid, 0, 0x3FF),
        ("VCID", cfg.vcid, 0, 0x3F),
        ("Frame Sequence Number", cfg.frame_sequence_number, 0, 0xFF),
    ]
    for name, value, lo, hi in checks:
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be {lo}..{hi}")


def build_tc_transfer_frame(space_packet: bytes, cfg: TCConfig) -> dict:
    validate_tc_config(cfg)
    total_len = 5 + len(space_packet) + (2 if cfg.include_fecf else 0)
    if total_len > 1024:
        raise ValueError("TC Transfer Frame length exceeds 1024 octets in this model")
    frame_len_c = total_len - 1

    header_value = (
        ((cfg.tfvn & 0x3) << 38)
        | ((cfg.bypass & 0x1) << 37)
        | ((cfg.control & 0x1) << 36)
        | ((cfg.spare & 0x3) << 34)
        | ((cfg.scid & 0x3FF) << 24)
        | ((cfg.vcid & 0x3F) << 18)
        | ((frame_len_c & 0x3FF) << 8)
        | (cfg.frame_sequence_number & 0xFF)
    )
    header = header_value.to_bytes(5, "big")
    frame_without_fecf = header + space_packet

    fecf = b""
    frame = frame_without_fecf
    if cfg.include_fecf:
        fecf = crc16_ccitt(frame_without_fecf).to_bytes(2, "big")
        frame = frame_without_fecf + fecf

    return {
        "header": header,
        "frame_without_fecf": frame_without_fecf,
        "fecf": fecf,
        "frame": frame,
        "frame_length_c": frame_len_c,
        "fecf_valid": validate_fecf(frame) if cfg.include_fecf else None,
    }


def validate_fecf(frame: bytes) -> bool:
    if len(frame) < 7:
        return False
    return crc16_ccitt(frame[:-2]).to_bytes(2, "big") == frame[-2:]
