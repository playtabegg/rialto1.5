"""One check, one sentence. Stateless: nothing is read or written."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import keys as trust
from ._semver import vercmp
from .feed import FeedNotPublished, FeedProblem, Release, fetch_bytes, fetch_release


@dataclass(frozen=True)
class Outcome:
    #: What the person is told. Always a sentence.
    sentence: str
    #: The verified release, when there is a newer one.
    release: Optional[Release] = None
    #: True when the server answered but publishes no feed yet: the person may look at the releases page.
    look_yourself: bool = False

    @property
    def newer(self) -> bool:
        return self.release is not None


def no_key_sentence() -> str:
    return "This build carries no release key, so it cannot check for a new one."


def up_to_date_sentence(version: str) -> str:
    return "You have the newest Rialto, %s." % version


def newer_sentence(version: str, running: str) -> str:
    return "Rialto %s is out. You have %s." % (version, running)


def check_for_update(running, *, endpoints=trust.ENDPOINTS, pubs=None, fetch=fetch_bytes, log=None):
    keys = trust.trusted_keys() if pubs is None else pubs
    if not keys:
        return Outcome(no_key_sentence())
    try:
        release = fetch_release(endpoints, keys, fetch=fetch, log=log)
    except FeedNotPublished as problem:
        return Outcome(str(problem), look_yourself=True)
    except FeedProblem as problem:
        return Outcome(str(problem))
    if vercmp(release.version, running) <= 0:
        return Outcome(up_to_date_sentence(running))
    return Outcome(newer_sentence(release.version, running), release)
