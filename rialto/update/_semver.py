"""Dotted-integer version comparison, the same rule the release feed uses.

Non-numeric components are dropped: ``"1.0.3-beta"`` compares as ``1.0``.
The publisher only ever writes plain ``X.Y.Z``.
"""

from __future__ import annotations

import re


def parts(version: str) -> list[int]:
    # Plain 0 to 9 only: str.isdigit() is also true of other scripts' digits and of
    # superscripts, which int() refuses.
    return [int(x) for x in str(version).split(".") if re.fullmatch(r"[0-9]+", x)]


def vercmp(a: str, b: str) -> int:
    """1 if ``a`` > ``b``, -1 if ``a`` < ``b``, else 0."""
    pa, pb = parts(a), parts(b)
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va != vb:
            return 1 if va > vb else -1
    return 0
