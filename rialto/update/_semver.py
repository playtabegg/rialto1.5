"""Dotted-integer version comparison, the same rule the release feed uses.

Non-numeric components are dropped: ``"1.0.3-beta"`` compares as ``1.0``.
The publisher only ever writes plain ``X.Y.Z``.
"""

from __future__ import annotations


def parts(version: str) -> list[int]:
    return [int(x) for x in str(version).split(".") if x.isdigit()]


def vercmp(a: str, b: str) -> int:
    """1 if ``a`` > ``b``, -1 if ``a`` < ``b``, else 0."""
    pa, pb = parts(a), parts(b)
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va != vb:
            return 1 if va > vb else -1
    return 0
