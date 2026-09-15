"""The one pinned downloader for everything Rialto fetches and then runs.

Three places used ``urllib.request.urlretrieve`` straight to disk: the
innoextract zip (hash pinned), the Artifact Signing client from NuGet, and
the Visual C++ runtimes from Microsoft. This gives them one path with a
host allowlist, an https requirement, a size cap, an optional SHA-256, and
no partial file left behind.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from typing import Iterable, Optional
from urllib.parse import urlparse


class FetchProblem(Exception):
    """``str(problem)`` says what was wrong, without a traceback."""


def _host_ok(url: str, hosts: Iterable[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "") in set(hosts)


def fetch_to_file(url: str, dest: str, *, hosts: Iterable[str], cap: int,
                  sha256: Optional[str] = None, timeout: float = 60.0) -> str:
    """Download ``url`` to ``dest`` and return ``dest``.

    Refuses a non-https URL, a host outside ``hosts`` (the final one after
    redirects too), a body over ``cap`` bytes, and a body whose SHA-256 is
    not ``sha256`` when one is given. On any refusal nothing is left at
    ``dest``.
    """
    if not _host_ok(url, hosts):
        raise FetchProblem("Rialto only downloads this from %s over https." % ", ".join(sorted(hosts)))
    request = urllib.request.Request(url, headers={"User-Agent": "Rialto/1.5"})
    digest = hashlib.sha256()
    total = 0
    folder = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(folder, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".download-", dir=folder)
    try:
        with os.fdopen(handle, "wb") as out, urllib.request.urlopen(request, timeout=timeout) as response:
            if not _host_ok(response.geturl(), hosts):
                raise FetchProblem("The download was redirected somewhere Rialto does not fetch from.")
            while True:
                block = response.read(1 << 20)
                if not block:
                    break
                total += len(block)
                if total > cap:
                    raise FetchProblem("The download is larger than Rialto expected, so it was stopped.")
                digest.update(block)
                out.write(block)
        if sha256 is not None and digest.hexdigest().lower() != sha256.lower():
            raise FetchProblem("The download did not match its expected checksum and was discarded.")
        os.replace(temp, dest)
        return dest
    except FetchProblem:
        raise
    except Exception as error:  # one sentence, whatever the socket said
        raise FetchProblem("The download did not complete (%s)." % error.__class__.__name__) from error
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass
