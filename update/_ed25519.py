"""Verify-only Ed25519 (RFC 8032), standard library only.

The same arithmetic as the publisher's own signing tool, without the
signing half. Auditability over speed: affine coordinates, the
arithmetic reads like the RFC, no key generation and no signing
because Rialto never holds a private key. ``S`` is range-checked and
point decoding rejects non-canonical encodings and small-order
keys.
"""

from __future__ import annotations

import hashlib

P = 2**255 - 19
Q = 2**252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


D = -121665 * _inv(121666) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)

Point = tuple[int, int]


def _x_recover(y: int) -> int:
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * SQRT_M1) % P
    if x % 2 != 0:
        x = P - x
    return x


_BASE_Y = 4 * _inv(5) % P
BASE: Point = (_x_recover(_BASE_Y), _BASE_Y)
IDENTITY: Point = (0, 1)


def point_add(p1: Point, p2: Point) -> Point:
    x1, y1 = p1
    x2, y2 = p2
    prod = D * x1 * x2 * y1 * y2
    denom_x = (1 + prod) % P
    denom_y = (1 - prod) % P
    both = _inv(denom_x * denom_y % P)
    x3 = (x1 * y2 + x2 * y1) * (both * denom_y)
    y3 = (y1 * y2 + x1 * x2) * (both * denom_x)
    return (x3 % P, y3 % P)


def point_mul(point: Point, scalar: int) -> Point:
    result = IDENTITY
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        scalar >>= 1
    return result


def is_on_curve(point: Point) -> bool:
    x, y = point
    return (-x * x + y * y - 1 - D * x * x * y * y) % P == 0


def encode_point(point: Point) -> bytes:
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def decode_point(data: bytes) -> Point | None:
    if len(data) != 32:
        return None
    encoded = int.from_bytes(data, "little")
    y = encoded & ((1 << 255) - 1)
    if y >= P:
        return None
    sign = encoded >> 255
    x = _x_recover(y)
    if x == 0 and sign == 1:
        return None
    if x & 1 != sign:
        x = P - x
    point = (x % P, y)
    if not is_on_curve(point):
        return None
    return point


def _hash_to_scalar(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % Q


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """True iff ``signature`` is valid. Never raises: malformed is False."""
    if not isinstance(public_key, (bytes, bytearray)):
        return False
    if not isinstance(signature, (bytes, bytearray)):
        return False
    if len(public_key) != 32 or len(signature) != 64:
        return False
    r_point = decode_point(bytes(signature[:32]))
    if r_point is None:
        return False
    a_point = decode_point(bytes(public_key))
    if a_point is None:
        return False
    if point_mul(a_point, 8) == IDENTITY:
        return False
    s_scalar = int.from_bytes(bytes(signature[32:]), "little")
    if s_scalar >= Q:
        return False
    k = _hash_to_scalar(bytes(signature[:32]) + bytes(public_key) + bytes(message))
    left = point_mul(BASE, s_scalar)
    right = point_add(r_point, point_mul(a_point, k))
    return left == right


__all__ = ["BASE", "Q", "encode_point", "point_mul", "verify"]
