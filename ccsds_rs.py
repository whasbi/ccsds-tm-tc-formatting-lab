"""
ccsds_rs.py

Transparent Reed-Solomon RS(255,223) implementation for CCSDS-style TM.

Implements:
- GF(256) using F(x)=x^8+x^7+x^2+x+1 = 0x187
- Generator-root convention:
    g(x)=product from j=128-E to 127+E of (x-alpha^(11j)), E=16
- Systematic RS encoding
- Full unknown-error decoder:
    syndromes -> Berlekamp-Massey locator -> Chien search -> Forney magnitudes -> XOR correction

The boundary:
This module is written for readability and details. It is not flight-qualified conformance software.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


J = 8
E = 16
RS_N = (2 ** J) - 1       # 255
RS_PARITY = 2 * E         # 32
RS_K = RS_N - RS_PARITY   # 223
RS_T = E                  # 16
GF_PRIM_POLY = 0x187      # x^8 + x^7 + x^2 + x + 1
ALPHA = 2
RS_BETA_POWER = 11
RS_FCR = 128 - E          # 112


GF_EXP = [0] * 512
GF_LOG = [0] * 256


def gf_init() -> None:
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= GF_PRIM_POLY
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]


gf_init()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return GF_EXP[(GF_LOG[a] + GF_LOG[b]) % 255]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("GF division by zero")
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] - GF_LOG[b]) % 255]


def gf_pow(a: int, p: int) -> int:
    if p == 0:
        return 1
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] * (p % 255)) % 255]


def gf_inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("GF inverse of zero")
    return GF_EXP[(255 - GF_LOG[a]) % 255]


def poly_mul_desc(p: List[int], q: List[int]) -> List[int]:
    """Multiply polynomials whose coefficients are descending-power order."""
    r = [0] * (len(p) + len(q) - 1)
    for i, pi in enumerate(p):
        for j, qj in enumerate(q):
            r[i + j] ^= gf_mul(pi, qj)
    return r


def poly_eval_desc(poly: List[int], x: int) -> int:
    """Evaluate descending-power polynomial by Horner's method."""
    y = poly[0]
    for c in poly[1:]:
        y = gf_mul(y, x) ^ c
    return y


def poly_mul_asc(p: List[int], q: List[int]) -> List[int]:
    """Multiply polynomials whose coefficients are ascending-power order."""
    r = [0] * (len(p) + len(q) - 1)
    for i, pi in enumerate(p):
        for j, qj in enumerate(q):
            r[i + j] ^= gf_mul(pi, qj)
    return r


def poly_eval_asc(poly: List[int], x: int) -> int:
    """Evaluate ascending-power polynomial."""
    y = 0
    xp = 1
    for c in poly:
        y ^= gf_mul(c, xp)
        xp = gf_mul(xp, x)
    return y


BETA = gf_pow(ALPHA, RS_BETA_POWER)


def rs_generator_poly() -> Tuple[List[int], List[int]]:
    g = [1]
    roots = []
    for j in range(128 - E, 128 + E):  # 112..143, 32 roots/factors
        root = gf_pow(ALPHA, RS_BETA_POWER * j)
        roots.append(root)
        g = poly_mul_desc(g, [1, root])  # x - root; minus equals plus in GF(2^8)
    return g, roots


RS_GEN, RS_ROOTS = rs_generator_poly()


@dataclass
class RSDecodeReport:
    syndromes_before: List[int]
    nonzero_before: int
    locator: List[int]
    locator_degree: int
    bm_trace: List[Tuple[int, int, int]]
    positions: List[int]
    magnitudes: List[int]
    omega: List[int]
    derivative: List[int]
    forney_details: List[Tuple[int, int, int, int, int, int, int]]
    syndromes_after: List[int]
    nonzero_after: int
    passed: bool


def rs_encode(data223: bytes) -> Tuple[bytes, bytes]:
    """
    Systematic RS encode.

    Formula:
        r(x) = x^32 m(x) mod g(x)
        c(x) = x^32 m(x) + r(x)

    Returns:
        (255-byte codeword, 32-byte parity)
    """
    if len(data223) != RS_K:
        raise ValueError(f"RS encode needs exactly {RS_K} bytes, got {len(data223)}")
    work = list(data223) + [0] * RS_PARITY
    for i in range(RS_K):
        coef = work[i]
        if coef:
            for j in range(1, len(RS_GEN)):
                work[i + j] ^= gf_mul(RS_GEN[j], coef)
    parity = bytes(work[-RS_PARITY:])
    return bytes(data223) + parity, parity


def rs_syndromes(codeword: bytes) -> List[int]:
    if len(codeword) != RS_N:
        raise ValueError(f"RS decode needs {RS_N}-byte codeword, got {len(codeword)}")
    return [poly_eval_desc(list(codeword), root) for root in RS_ROOTS]


def berlekamp_massey(synd: List[int]) -> Tuple[List[int], int, List[Tuple[int, int, int]]]:
    """
    Berlekamp-Massey. Locator polynomial in ascending order:
        Lambda(z) = C0 + C1 z + C2 z^2 + ...
    """
    C = [1]
    B = [1]
    L = 0
    m = 1
    b = 1
    trace: List[Tuple[int, int, int]] = []

    for n in range(len(synd)):
        d = synd[n]
        for i in range(1, L + 1):
            d ^= gf_mul(C[i], synd[n - i])
        trace.append((n + 1, d, L))

        if d != 0:
            T = C[:]
            coef = gf_div(d, b)
            if len(C) < len(B) + m:
                C += [0] * (len(B) + m - len(C))
            for i in range(len(B)):
                C[i + m] ^= gf_mul(coef, B[i])
            if 2 * L <= n:
                L = n + 1 - L
                B = T
                b = d
                m = 1
            else:
                m += 1
        else:
            m += 1

    while len(C) > 1 and C[-1] == 0:
        C.pop()
    return C, L, trace


def chien_search(locator: List[int]) -> List[int]:
    positions = []
    for pos in range(RS_N):
        power = RS_N - 1 - pos
        z = gf_inv(gf_pow(BETA, power))
        if poly_eval_asc(locator, z) == 0:
            positions.append(pos)
    return positions


def forney_magnitudes(
    synd: List[int],
    locator: List[int],
    positions: List[int],
) -> Tuple[List[int], List[int], List[int], List[Tuple[int, int, int, int, int, int, int]]]:
    """
    Forney calculation for the implemented root convention.
    """
    omega = poly_mul_asc(synd, locator)[:RS_PARITY]

    derivative = [0] * max(1, len(locator) - 1)
    for i in range(1, len(locator)):
        if i % 2 == 1:  # derivative in characteristic 2 keeps odd powers
            derivative[i - 1] = locator[i]

    magnitudes = []
    details = []
    for pos in positions:
        power = RS_N - 1 - pos
        X = gf_pow(BETA, power)
        Xinv = gf_inv(X)
        om = poly_eval_asc(omega, Xinv)
        der = poly_eval_asc(derivative, Xinv)
        if der == 0:
            raise ValueError("Forney denominator is zero")
        mag = gf_div(gf_mul(gf_pow(X, 1 - RS_FCR), om), der)
        magnitudes.append(mag)
        details.append((pos, power, X, Xinv, om, der, mag))
    return magnitudes, omega, derivative, details


def rs_decode(codeword: bytes) -> Tuple[bytes, RSDecodeReport]:
    synd = rs_syndromes(codeword)
    nonzero_before = sum(1 for s in synd if s)

    if nonzero_before == 0:
        return bytes(codeword), RSDecodeReport(
            syndromes_before=synd,
            nonzero_before=0,
            locator=[1],
            locator_degree=0,
            bm_trace=[],
            positions=[],
            magnitudes=[],
            omega=[],
            derivative=[],
            forney_details=[],
            syndromes_after=synd[:],
            nonzero_after=0,
            passed=True,
        )

    locator, L, trace = berlekamp_massey(synd)
    positions = chien_search(locator)
    if len(positions) != L:
        raise ValueError(f"Chien search found {len(positions)} positions but locator degree is {L}")
    if len(positions) > RS_T:
        raise ValueError(f"Located {len(positions)} RS symbol errors; exceeds E={RS_T}")

    magnitudes, omega, derivative, forney_details = forney_magnitudes(synd, locator, positions)
    corrected = bytearray(codeword)
    for pos, mag in zip(positions, magnitudes):
        corrected[pos] ^= mag

    synd_after = rs_syndromes(bytes(corrected))
    nonzero_after = sum(1 for s in synd_after if s)

    return bytes(corrected), RSDecodeReport(
        syndromes_before=synd,
        nonzero_before=nonzero_before,
        locator=locator,
        locator_degree=L,
        bm_trace=trace,
        positions=positions,
        magnitudes=magnitudes,
        omega=omega,
        derivative=derivative,
        forney_details=forney_details,
        syndromes_after=synd_after,
        nonzero_after=nonzero_after,
        passed=(nonzero_after == 0),
    )


def hxlst(values: List[int]) -> str:
    return " ".join(f"{v:02X}" for v in values)
