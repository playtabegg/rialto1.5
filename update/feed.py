"""Fetch and read a ``wti.appcast/1`` feed. The only module here that
touches the network, together with :mod:`fetch`.

Every failure is a :class:`FeedProblem` with one sentence for the person.
Python 3.9 upward.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import keys as trust
from .minisig import PublicKey, verify_any

SCHEMA = "wti.appcast/1"
PLATFORM = "windows-x86_64"
FEED_CAP = 256 * 1024
#: The most Rialto will fetch for an installer, whatever the feed says.
INSTALLER_CAP = 512 * 1024 * 1024
TIMEOUT_SECONDS = 15.0
USER_AGENT = "Rialto-update-check/1"

Fetch = Callable[[str, int], bytes]


class FeedProblem(Exception):
    """The feed could not be trusted or read. ``str(problem)`` is the sentence."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    size: int
    signature: str
    installer: str
    args: tuple[str, ...]
    notes_url: str = ""
    notes: str = ""
    min_upgradable_from: str = ""
    endpoint: str = ""


@dataclass
class FetchLog:
    """What a check tried, for the log line. Never sent anywhere."""

    tried: list[str] = field(default_factory=list)


def host_allowed(url: str, allowed: frozenset[str] = trust.ALLOWED_HOSTS) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "") in allowed


def fetch_bytes(url: str, cap: int, timeout: float = TIMEOUT_SECONDS) -> bytes:
    """GET ``url`` over https, no cookies, no identifiers, at most ``cap`` bytes.

    Raises :class:`FeedProblem` for anything that is not a complete, in-cap
    body from an allowed host (redirects included).
    """
    if not host_allowed(url):
        raise FeedProblem("That address is not one Rialto fetches from.")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not host_allowed(response.geturl()):
                raise FeedProblem("The download was sent somewhere Rialto does not fetch from.")
            data = response.read(cap + 1)
    except FeedProblem:
        raise
    except Exception as error:
        raise FeedProblem("Could not reach the release server.") from error
    if len(data) > cap:
        raise FeedProblem("The release server sent more than Rialto will read.")
    return bytes(data)


def parse_feed(
    raw: bytes,
    sig_text: str,
    pubs: list[PublicKey],
    *,
    app: str = trust.APP,
    channel: str = trust.CHANNEL,
) -> Release:
    """A verified :class:`Release`, or :class:`FeedProblem`. Signature first,
    then shape: nothing unsigned is even parsed."""
    if not pubs:
        raise FeedProblem("This build carries no release key, so it cannot check.")
    if not verify_any(raw, sig_text, pubs):
        raise FeedProblem("The release feed is not signed by We The Indies.")
    try:
        feed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise FeedProblem("The release feed could not be read.") from error
    if not isinstance(feed, dict) or feed.get("schema") != SCHEMA:
        raise FeedProblem("The release feed is in a shape this Rialto does not read.")
    if feed.get("app") != app or feed.get("channel") != channel:
        raise FeedProblem("The release feed is for a different program.")
    version = str(feed.get("version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise FeedProblem("The release feed names a version this Rialto does not read.")
    block = (feed.get("platforms") or {}).get(PLATFORM)
    if not isinstance(block, dict):
        raise FeedProblem("The release feed has nothing for Windows.")
    url = str(block.get("url", ""))
    if not host_allowed(url):
        raise FeedProblem("The release feed points somewhere Rialto does not fetch from.")
    sha256 = str(block.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise FeedProblem("The release feed has no usable checksum.")
    size = block.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise FeedProblem("The release feed has no usable size.")
    if size > INSTALLER_CAP:
        raise FeedProblem("The release feed names a download larger than Rialto will fetch.")
    signature = block.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        raise FeedProblem("The release feed carries no signature for the installer.")
    args = block.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise FeedProblem("The release feed's install arguments could not be read.")
    return Release(
        version=version,
        url=url,
        sha256=sha256,
        size=size,
        signature=signature,
        installer=str(block.get("installer", "")),
        args=tuple(args),
        # The one URL handed to the browser: only from a host we fetch from.
        notes_url=(str(feed.get("notes_url", "")) if host_allowed(str(feed.get("notes_url", ""))) else ""),
        notes=str(feed.get("notes", "")),
        min_upgradable_from=str(feed.get("min_upgradable_from", "")),
    )


def fetch_release(
    endpoints: tuple[str, ...],
    pubs: list[PublicKey],
    *,
    fetch: Fetch = fetch_bytes,
    log: FetchLog | None = None,
) -> Release:
    """The first endpoint that yields a verified feed wins. A signed feed
    that fails verification at one endpoint does not fall through to the
    next: a bad signature is an answer, not an outage."""
    if not pubs:
        raise FeedProblem("This build carries no release key, so it cannot check.")
    last: FeedProblem | None = None
    for endpoint in endpoints:
        if log is not None:
            log.tried.append(endpoint)
        try:
            raw = fetch(endpoint, FEED_CAP)
            sig_text = fetch(endpoint + ".minisig", FEED_CAP).decode("utf-8", errors="replace")
        except FeedProblem as problem:
            last = problem
            continue
        release = parse_feed(raw, sig_text, pubs)
        return Release(**{**release.__dict__, "endpoint": endpoint})
    raise last or FeedProblem("Could not reach the release server.")
