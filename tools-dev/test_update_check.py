"""The update check trusts only a signed feed, never
fetches without a key, and every failure is one sentence. Negative controls
throughout. Standard library only.

Usage: python tools-dev/test_update_check.py [path-to-rialto1.5]
"""
import base64
import hashlib
import json
import os
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from update._ed25519 import BASE, Q, encode_point, point_mul  # noqa: E402
from update.check import check_for_update  # noqa: E402
from update.feed import FeedProblem, fetch_bytes, parse_feed  # noqa: E402
from update.fetch import FetchProblem, fetch_to_file  # noqa: E402
from update.minisig import parse_public_key  # noqa: E402
from update.keys import ENDPOINTS, trusted_keys

failures = []


def check(cond, what):
    if not cond:
        failures.append(what)


# -- a test-only signer ---------------------------------------------------

def _clamped(seed):
    digest = hashlib.sha512(seed).digest()
    lower = bytearray(digest[:32])
    lower[0] &= 248
    lower[31] &= 127
    lower[31] |= 64
    return int.from_bytes(lower, "little"), digest[32:]


def sign(seed, message):
    scalar, prefix = _clamped(seed)
    pub = encode_point(point_mul(BASE, scalar))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % Q
    r_point = encode_point(point_mul(BASE, r))
    k = int.from_bytes(hashlib.sha512(r_point + pub + message).digest(), "little") % Q
    s = (r + k * scalar) % Q
    return r_point + s.to_bytes(32, "little")


class Signer:
    def __init__(self):
        self.seed = os.urandom(32)
        self.key_id = os.urandom(8)
        scalar, _ = _clamped(self.seed)
        self.pub_raw = encode_point(point_mul(BASE, scalar))

    @property
    def pub_line(self):
        return base64.b64encode(b"Ed" + self.key_id + self.pub_raw).decode()

    def minisig(self, content, trusted="timestamp:0\tfile:x"):
        digest = hashlib.blake2b(content, digest_size=64).digest()
        signature = sign(self.seed, digest)
        global_sig = sign(self.seed, signature + trusted.encode())
        return ("untrusted comment: test\n%s\ntrusted comment: %s\n%s\n" % (
            base64.b64encode(b"ED" + self.key_id + signature).decode(), trusted,
            base64.b64encode(global_sig).decode()))


ARTIFACT = b"MZ" + bytes(range(256)) * 4
URL = "https://github.com/playtabegg/rialto1.5/releases/download/v1.6.0/Rialto.exe"


def feed_for(signer, **over):
    doc = {
        "schema": "wti.appcast/1", "app": "rialto", "channel": "stable", "version": "1.6.0",
        "pub_date": "2026-09-16T14:03:00Z", "notes": "", "notes_url": "https://github.com/playtabegg/rialto1.5/releases/tag/v1.6.0",
        "min_upgradable_from": "1.5.0",
        "platforms": {"windows-x86_64": {
            "url": URL, "signature": signer.minisig(ARTIFACT), "sha256": hashlib.sha256(ARTIFACT).hexdigest(),
            "size": len(ARTIFACT), "installer": "inno", "args": ["/VERYSILENT"]}},
    }
    doc.update(over)
    raw = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()
    return raw, signer.minisig(raw)


def fetcher(raw, sig):
    def fetch(url, cap):
        return sig.encode() if url.endswith(".minisig") else raw
    return fetch


signer = Signer()
pubs = [parse_public_key(signer.pub_line)]
check(pubs[0] is not None, "the test signer's public key does not parse")
raw, sig = feed_for(signer)
ends = ("https://github.com/x/latest.json",)

release = parse_feed(raw, sig, pubs, app="rialto", channel="stable")
check(release.version == "1.6.0", "a signed feed did not parse")

# no key: never fetches
def never(url, cap):
    raise AssertionError("fetched without a key")
out = check_for_update("1.5.0", pubs=[], fetch=never)
check(out.sentence.startswith("This build carries no release key"), "no-key sentence wrong: " + out.sentence)
# update/keys.py ships the release key (id F8E608F4766B35A6) in slot one and
# a spare (id AE1D6657A32C4E9A) in slot two, so a default check contacts the
# first endpoint.
asked = []
def offline(url, cap):
    asked.append(url)
    raise FeedProblem("Could not reach the release server.")
out = check_for_update("1.5.0", fetch=offline)
check(bool(asked) and asked[0] == ENDPOINTS[0], "the default check did not ask our first endpoint")
check(not out.sentence.startswith("This build carries no release key"), "the release key is not in the default slots")
check(len(trusted_keys()) == 2 and trusted_keys()[0].key_id.hex().upper() == "F8E608F4766B35A6", "the default key is not the release key")
check(trusted_keys()[1].key_id.hex().upper() == "AE1D6657A32C4E9A", "slot two is not the spare")

# newer / same / older
out = check_for_update("1.5.0", endpoints=ends, pubs=pubs, fetch=fetcher(raw, sig))
check(out.newer and out.release.version == "1.6.0", "a newer release was not offered")
check(out.sentence == "Rialto 1.6.0 is out. You have 1.5.0.", "newer sentence wrong: " + out.sentence)
out = check_for_update("1.6.0", endpoints=ends, pubs=pubs, fetch=fetcher(raw, sig))
check(not out.newer and out.sentence == "You have the newest Rialto, 1.6.0.", "same-version sentence wrong: " + out.sentence)
out = check_for_update("2.0.0", endpoints=ends, pubs=pubs, fetch=fetcher(raw, sig))
check(not out.newer, "an older feed was offered")

# forged, tampered, wrong app
forged = Signer()
fraw, fsig = feed_for(forged)
out = check_for_update("1.5.0", endpoints=ends, pubs=pubs, fetch=fetcher(fraw, fsig))
check(out.sentence == "The release feed is not signed by We The Indies.", "forged feed accepted: " + out.sentence)
out = check_for_update("1.5.0", endpoints=ends, pubs=pubs, fetch=fetcher(raw.replace(b'"1.6.0"', b'"9.9.9"'), sig))
check(out.sentence == "The release feed is not signed by We The Indies.", "tampered feed accepted")
praw, psig = feed_for(signer, app="otherapp")
out = check_for_update("1.5.0", endpoints=ends, pubs=pubs, fetch=fetcher(praw, psig))
check("different program" in out.sentence, "another program's feed was accepted by Rialto")
hraw, hsig = feed_for(signer, platforms={"windows-x86_64": {"url": "https://evil.example/Rialto.exe", "signature": "x", "sha256": "0" * 64, "size": 1, "installer": "inno", "args": []}})
out = check_for_update("1.5.0", endpoints=ends, pubs=pubs, fetch=fetcher(hraw, hsig))
check("does not fetch from" in out.sentence, "a stranger's host was accepted")

# endpoint fallback, and a bad signature is not an outage
calls = []
def flaky(url, cap):
    calls.append(url)
    if url.startswith("https://github.com/"):
        raise FeedProblem("Could not reach the release server.")
    return sig.encode() if url.endswith(".minisig") else raw
out = check_for_update("1.5.0", endpoints=("https://github.com/x/latest.json", "https://updates.wetheindies.com/y/latest.json"), pubs=pubs, fetch=flaky)
check(out.newer and out.release.endpoint.startswith("https://updates.wetheindies.com"), "the second endpoint was not used")

# the real fetcher refuses strangers without a socket
try:
    fetch_bytes("https://evil.example/latest.json", 10)
    check(False, "fetch_bytes opened a stranger's host")
except FeedProblem as problem:
    check("not one Rialto fetches from" in str(problem), "wrong refusal: " + str(problem))
try:
    fetch_bytes("http://github.com/latest.json", 10)
    check(False, "fetch_bytes accepted plain http")
except FeedProblem:
    pass

# the pinned downloader refuses before it connects
import tempfile
with tempfile.TemporaryDirectory() as folder:
    dest = os.path.join(folder, "x.bin")
    for url in ("http://constexpr.org/x.zip", "https://evil.example/x.zip"):
        try:
            fetch_to_file(url, dest, hosts={"constexpr.org"}, cap=1024)
            check(False, "fetch_to_file accepted " + url)
        except FetchProblem:
            pass
    check(not os.path.exists(dest), "a refused download left a file behind")
    check(not os.listdir(folder), "a refused download left a temp file behind")

    # An allowed host that sends more than the cap: the body is read, the cap
    # trips mid-stream, and the temp file the stream was going into is gone.
    import urllib.request

    class _Over:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def geturl(self):
            return "https://constexpr.org/x.zip"

        def read(self, n):
            return b"x" * n

    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: _Over()
    try:
        try:
            fetch_to_file("https://constexpr.org/x.zip", dest, hosts={"constexpr.org"}, cap=4096)
            check(False, "an over-cap download was accepted")
        except FetchProblem as problem:
            check("larger than Rialto expected" in str(problem), "wrong cap sentence: " + str(problem))
        check(not os.path.exists(dest), "an over-cap download left a file behind")
        check(not os.listdir(folder), "an over-cap download left its temp file behind")

        class _Wrong(_Over):
            def read(self, n):
                if getattr(self, "_done", False):
                    return b""
                self._done = True
                return b"not the bytes"

        urllib.request.urlopen = lambda *a, **k: _Wrong()
        try:
            fetch_to_file("https://constexpr.org/x.zip", dest, hosts={"constexpr.org"}, cap=4096, sha256="00" * 32)
            check(False, "a wrong-hash download was accepted")
        except FetchProblem as problem:
            check("checksum" in str(problem), "wrong hash sentence: " + str(problem))
        check(not os.listdir(folder), "a wrong-hash download left a file behind")
    finally:
        urllib.request.urlopen = real_urlopen

if failures:
    for item in failures:
        print("FAIL:", item)
    sys.exit(1)
print("OK: update check trusts only a signed feed")
