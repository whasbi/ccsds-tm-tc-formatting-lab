"""
ccsds_tm.py

Full CCSDS-style TM chain:
Space Packet -> RS(255,223), I=5 interleaving -> randomizer -> ASM -> CADU.

This is a transparent implementation, not flight-qualified conformance software.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from ccsds_rs import RS_K, RS_N, RS_PARITY, RS_T, RSDecodeReport, rs_encode, rs_decode
from ccsds_packets import build_space_packet, SpacePacketConfig


ASM = bytes.fromhex("1A CF FC 1D")
FILL_BYTE = 0x55
INTERLEAVING_DEPTH = 5


@dataclass
class TMConfig:
    tm_apid: int = 100
    tm_sequence_count: int = 1
    bitrate_bps: int = 9600
    interleaving_depth: int = INTERLEAVING_DEPTH
    fill_byte: int = FILL_BYTE
    space_packet_config: SpacePacketConfig = field(default_factory=SpacePacketConfig)


def pn_bits(nbits: int) -> List[int]:
    """
    Pseudo-randomizer sequence based on h(x)=x^17+x^14+1 style feedback.

    The operation is transparent:
        randomized_bit_i = input_bit_i XOR PN_i
        derandomized_bit_i = received_bit_i XOR PN_i
    """
    state = [1] * 17
    out = []
    for _ in range(nbits):
        out.append(state[-1])
        fb = state[-1] ^ state[-4]
        state = [fb] + state[:-1]
    return out


def xor_randomize(data: bytes) -> bytes:
    bits = pn_bits(len(data) * 8)
    out = bytearray(data)
    for bit_index, pn in enumerate(bits):
        if pn:
            out[bit_index // 8] ^= 0x80 >> (bit_index % 8)
    return bytes(out)


def build_tm_space_packet(payload: bytes, cfg: TMConfig) -> bytes:
    return build_space_packet(
        packet_type=0,
        apid=cfg.tm_apid,
        sequence_count=cfg.tm_sequence_count,
        data_field=payload,
        config=cfg.space_packet_config,
    )


def interleaved_rs_encode(data_space: bytes, depth: int = INTERLEAVING_DEPTH) -> tuple[bytes, list[bytes], bytes]:
    if len(data_space) != RS_K * depth:
        raise ValueError(f"Data space must be k*I = {RS_K * depth} bytes")
    codewords = []
    parities = []
    for i in range(depth):
        data_i = data_space[i::depth]
        cw, parity = rs_encode(data_i)
        codewords.append(cw)
        parities.append(parity)

    check = bytearray()
    for p in range(RS_PARITY):
        for i in range(depth):
            check.append(parities[i][p])

    transmitted_codeblock = data_space + bytes(check)
    return transmitted_codeblock, codewords, bytes(check)


def interleaved_rs_decode(codeblock: bytes, depth: int = INTERLEAVING_DEPTH) -> tuple[bytes, list[RSDecodeReport], list[bytes]]:
    expected = RS_N * depth
    if len(codeblock) != expected:
        raise ValueError(f"Codeblock must be n*I = {expected} bytes")
    data_part = codeblock[:RS_K * depth]
    check_part = codeblock[RS_K * depth:]

    corrected_codewords = []
    reports = []
    for i in range(depth):
        data_i = data_part[i::depth]
        parity_i = bytes(check_part[p * depth + i] for p in range(RS_PARITY))
        cw = data_i + parity_i
        corrected, report = rs_decode(cw)
        corrected_codewords.append(corrected)
        reports.append(report)

    corrected_data_space = bytearray(RS_K * depth)
    for i, cw in enumerate(corrected_codewords):
        corrected_data_space[i::depth] = cw[:RS_K]

    return bytes(corrected_data_space), reports, corrected_codewords


def build_tm_cadu(space_packet: bytes, cfg: TMConfig) -> dict:
    depth = cfg.interleaving_depth
    data_space_len = RS_K * depth
    if len(space_packet) > data_space_len:
        raise ValueError(f"TM Space Packet length {len(space_packet)} exceeds data space {data_space_len}")
    data_space = space_packet + bytes([cfg.fill_byte]) * (data_space_len - len(space_packet))
    codeblock, codewords, check = interleaved_rs_encode(data_space, depth)
    randomized = xor_randomize(codeblock)
    cadu = ASM + randomized
    return {
        "space_packet": space_packet,
        "data_space": data_space,
        "codeblock": codeblock,
        "codewords": codewords,
        "check": check,
        "randomized": randomized,
        "cadu": cadu,
    }


def flip_bits(data: bytes, bit_positions: List[int]) -> tuple[bytes, list[tuple[int, int, int, int, int, int]]]:
    out = bytearray(data)
    events = []
    for bit in bit_positions:
        if bit < 0 or bit >= len(out) * 8:
            raise ValueError(f"Bit {bit} outside range 0..{len(out)*8-1}")
        byte_i = bit // 8
        bit_i = bit % 8
        mask = 0x80 >> bit_i
        before = out[byte_i]
        out[byte_i] ^= mask
        after = out[byte_i]
        events.append((bit, byte_i, bit_i, mask, before, after))
    return bytes(out), events


def receive_tm_cadu(cadu: bytes, expected_packet_len: int, cfg: TMConfig) -> dict:
    if not cadu.startswith(ASM):
        raise ValueError("ASM not found at CADU start")
    randomized_codeblock = cadu[len(ASM):]
    derandomized = xor_randomize(randomized_codeblock)
    corrected_data_space, reports, corrected_codewords = interleaved_rs_decode(derandomized, cfg.interleaving_depth)
    recovered_packet = corrected_data_space[:expected_packet_len]
    return {
        "derandomized": derandomized,
        "corrected_data_space": corrected_data_space,
        "corrected_codewords": corrected_codewords,
        "reports": reports,
        "recovered_packet": recovered_packet,
        "passed": all(r.passed for r in reports),
    }
