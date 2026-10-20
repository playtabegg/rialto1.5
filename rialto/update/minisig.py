"""Read minisign public keys and prehashed signatures. Verify only.

Format (minisign): a public key is base64 of ``Ed`` + 8-byte key id +
32-byte Ed25519 key. A ``.minisig`` is four lines: an untrusted comment,
base64 of ``ED`` + key id + 64-byte signature over BLAKE2b-512 of the file,
``trusted comment: ...``, and base64 of a 64-byte global signature over
signature + trusted comment. The legacy ``Ed`` signature tag (unhashed) is
refused; the publisher never writes it.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from ._ed25519 import verify as ed25519_verify

SIG_ALG = b"ED"
PUB_ALG = b"Ed"


@dataclass(frozen=True)
class PublicKey:
    key_id: bytes
    raw: bytes


def _unb64(text: str) -> bytes | None:
    try:
        return base64.b64decode(text.strip(), validate=True)
    except (ValueError, TypeError):
        return None


def parse_public_key(text: str) -> PublicKey | None:
    """A ``.pub`` file's text or just its base64 line. None if malformed."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    payload = [line for line in lines if not line.startswith("untrusted comment:")]
    if len(payload) != 1:
        return None
    blob = _unb64(payload[0])
    if blob is None or len(blob) != 42 or blob[:2] != PUB_ALG:
        return None
    return PublicKey(blob[2:10], blob[10:])


def prehash(content: bytes) -> bytes:
    return hashlib.blake2b(content, digest_size=64).digest()


def verify_bytes(content: bytes, sig_text: str, pub: PublicKey) -> bool:
    """True iff ``sig_text`` is a valid prehashed signature over ``content``
    by ``pub``. Never raises."""
    lines = sig_text.splitlines()
    if len(lines) < 4:
        return False
    blob = _unb64(lines[1])
    if blob is None or len(blob) != 74 or blob[:2] != SIG_ALG:
        return False
    if blob[2:10] != pub.key_id:
        return False
    signature = blob[10:]
    if not lines[2].startswith("trusted comment: "):
        return False
    trusted = lines[2][len("trusted comment: "):]
    global_sig = _unb64(lines[3])
    if global_sig is None or len(global_sig) != 64:
        return False
    if not ed25519_verify(pub.raw, prehash(content), signature):
        return False
    return ed25519_verify(pub.raw, signature + trusted.encode("utf-8"), global_sig)


def verify_any(content: bytes, sig_text: str, pubs: list[PublicKey]) -> bool:
    return any(verify_bytes(content, sig_text, pub) for pub in pubs)
