"""What a check trusts: the release keys and where the feed lives.

Two keys are trusted: the release key and its cold spare. Only the public
halves are here; the private halves never enter a repository. A build
that carries no key ends every check in "this build carries no release
key" and offers nothing.

Two slots, so a cold spare is trusted before it is ever used.
"""

from __future__ import annotations

from .minisig import PublicKey, parse_public_key

APP = "rialto"
CHANNEL = "stable"

#: minisign public key lines (base64 of ``Ed`` + key id + key), one per
#: slot: the release key first, its cold spare second.
TRUSTED_PUBLIC_KEYS: tuple = (
    # wti-app-release, key id F8E608F4766B35A6, generated 29 Aug 2026.
    # This is the public half; the private half never enters a
    # repository.
    "RWT45gj0dms1pn+/EcXvdcsp3FS3rpjSDgQ1QTBG4aMJnSeRpDF1W3M7",
    # wti-app-release-spare, key id AE1D6657A32C4E9A, generated 28 Aug 2026.
    # Public half only; the private half never enters a repository. It is
    # trusted before it is ever used, so rotating to it needs no new
    # build to be trusted first.
    "RWSuHWZXoyxOmitvRQxp1PdGnlNd92Opi8xZy/EOXeTa4GhqI0gjaCqd",
)

ENDPOINTS: tuple = (
    "https://github.com/playtabegg/rialto1.5/releases/latest/download/latest.json",
    "https://updates.wetheindies.com/apps/rialto/stable/latest.json",
)

ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "updates.wetheindies.com",
    }
)

RELEASE_PAGE = "https://github.com/playtabegg/rialto1.5/releases/latest"


def trusted_keys(lines=TRUSTED_PUBLIC_KEYS):
    keys = []
    for line in lines:
        parsed = parse_public_key(line)
        if parsed is not None:
            keys.append(parsed)
    return keys
