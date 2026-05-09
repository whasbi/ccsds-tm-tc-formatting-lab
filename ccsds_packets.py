"""
ccsds_packets.py

Space Packet Protocol.

Implements the 6-octet Space Packet Primary Header:
  PVN(3) | Type(1) | Secondary Header Flag(1) | APID(11)
  Sequence Flags(2) | Sequence Count(14)
  Packet Data Length(16) = Packet Data Field octets - 1
"""

from __future__ import annotations

from dataclasses import dataclass


PVN_DEFAULT = 0
SEQ_FLAGS_UNSEGMENTED = 0b11


@dataclass
class SpacePacketConfig:
    pvn: int = PVN_DEFAULT
    secondary_header_flag: int = 0
    sequence_flags: int = SEQ_FLAGS_UNSEGMENTED


@dataclass
class SpacePacketHeader:
    pvn: int
    packet_type: int
    secondary_header_flag: int
    apid: int
    sequence_flags: int
    sequence_count: int
    packet_data_length: int
    packet_data_field_octets: int


def validate_apid(apid: int) -> None:
    if not 0 <= apid <= 0x7FF:
        raise ValueError("APID must be 0..2047")


def build_space_packet(
    packet_type: int,
    apid: int,
    sequence_count: int,
    data_field: bytes,
    config: SpacePacketConfig | None = None,
) -> bytes:
    if config is None:
        config = SpacePacketConfig()
    validate_apid(apid)
    if not 0 <= sequence_count <= 0x3FFF:
        raise ValueError("Space Packet sequence count must be 0..16383")
    if packet_type not in (0, 1):
        raise ValueError("packet_type must be 0 for TM/reporting or 1 for TC/requesting")
    if not data_field:
        raise ValueError("Space Packet Data Field must contain at least 1 octet")
    if len(data_field) > 65536:
        raise ValueError("Space Packet Data Field must be <= 65536 octets")

    word0 = ((config.pvn & 0x7) << 13) | ((packet_type & 1) << 12) | ((config.secondary_header_flag & 1) << 11) | (apid & 0x7FF)
    word1 = ((config.sequence_flags & 0x3) << 14) | (sequence_count & 0x3FFF)
    word2 = len(data_field) - 1
    return word0.to_bytes(2, "big") + word1.to_bytes(2, "big") + word2.to_bytes(2, "big") + data_field


def parse_space_packet_header(packet: bytes) -> SpacePacketHeader:
    if len(packet) < 7:
        raise ValueError("Space Packet must be at least 7 octets")
    w0 = int.from_bytes(packet[0:2], "big")
    w1 = int.from_bytes(packet[2:4], "big")
    w2 = int.from_bytes(packet[4:6], "big")
    return SpacePacketHeader(
        pvn=(w0 >> 13) & 0x7,
        packet_type=(w0 >> 12) & 0x1,
        secondary_header_flag=(w0 >> 11) & 0x1,
        apid=w0 & 0x7FF,
        sequence_flags=(w1 >> 14) & 0x3,
        sequence_count=w1 & 0x3FFF,
        packet_data_length=w2,
        packet_data_field_octets=w2 + 1,
    )


def hex_bytes(data: bytes, max_len: int | None = None) -> str:
    if max_len is not None:
        data = data[:max_len]
    return " ".join(f"{b:02X}" for b in data)
