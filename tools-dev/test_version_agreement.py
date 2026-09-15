"""One version, three readers, all agreeing.

Rialto.pyw carries ``__version__``; rialto.spec and menu.spec read it from
that line for the EXE version resources; the release feed compares against
it. This pins that the three cannot drift.

Usage: python tools-dev/test_version_agreement.py [path-to-rialto1.5]
"""
import os
import re
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

failures = []


def check(cond, what):
    if not cond:
        failures.append(what)


def read(name):
    with open(os.path.join(REPO, name), encoding="utf-8") as f:
        return f.read()


source = read("Rialto.pyw")
match = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"$', source, re.M)
check(match is not None, 'Rialto.pyw has no __version__ = "X.Y.Z" line')
version = match.group(1) if match else ""

for spec in ("rialto.spec", "menu.spec"):
    text = read(spec)
    check("VERSION = (1, 5, 0, 0)" not in text, spec + " still hard-codes a version tuple")
    check('__version__ = "' in text and "Rialto.pyw" in text, spec + " does not read __version__ from Rialto.pyw")

check('("Check for a New Rialto…", self.check_for_new_rialto)' in source,
      "the Help menu has no Check for a New Rialto item")
check("check_for_update(__version__)" in source, "the check does not compare against __version__")
check("urllib.request.urlretrieve(" not in source, "Rialto.pyw still uses urlretrieve somewhere")
check("urllib.request.urlretrieve(" not in read("trusted_signing.py"), "trusted_signing.py still uses urlretrieve")

if failures:
    for item in failures:
        print("FAIL:", item)
    sys.exit(1)
print("OK: version %s agreed by Rialto.pyw, rialto.spec and menu.spec" % version)
