"""One version, three readers, all agreeing.

Rialto.pyw carries ``__version__``; packaging/rialto.spec and packaging/menu.spec read it from
that line for the EXE version resources; the release feed compares against
it. This pins that the three cannot drift, and that the Help Guide and the
build commands' examples name the same version (1.5.2).

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

for spec in ("packaging/rialto.spec", "packaging/menu.spec"):
    text = read(spec)
    check("VERSION = (1, 5, 0, 0)" not in text, spec + " still hard-codes a version tuple")
    check('__version__ = "' in text and "Rialto.pyw" in text, spec + " does not read __version__ from Rialto.pyw")

# Where else the version is written out (1.5.2): the guide's masthead and footer, and the build commands'
# examples. A bump that misses one leaves the last release's number there.
guide = read("docs/rialto-guide.html")
check("Version %s</p>" % version in guide and "<strong>Rialto %s</strong>" % version in guide,
      "docs/rialto-guide.html does not carry version %s in its masthead and footer" % version)
check('Disc Maker folder>" /DAppVersion=%s' % version in read("packaging/rialto-setup.iss"),
      "packaging/rialto-setup.iss's build example is not for %s" % version)
check("Rialto-%s-Disc-Maker.zip" % version in read("tools-dev/package_release.py"),
      "tools-dev/package_release.py's example does not name the %s zip" % version)
for name in ("docs/rialto-guide.html", "tools-dev/package_release.py"):
    stale = sorted(set(re.findall(r"(?:Version |Rialto[ -]|AppVersion=)([0-9]+\.[0-9]+\.[0-9]+)", read(name))) - {version})
    check(not stale, "%s still names %s" % (name, ", ".join(stale)))

check('("Check for a New Rialto…", self.check_for_new_rialto)' in source,
      "the Help menu has no Check for a New Rialto item")
check("check_for_update(__version__)" in source, "the check does not compare against __version__")
check("urllib.request.urlretrieve(" not in source, "Rialto.pyw still uses urlretrieve somewhere")
check("urllib.request.urlretrieve(" not in read("rialto/trusted_signing.py"), "rialto/trusted_signing.py still uses urlretrieve")

if failures:
    for item in failures:
        print("FAIL:", item)
    sys.exit(1)
print("OK: version %s agreed by Rialto.pyw, packaging/rialto.spec and packaging/menu.spec" % version)
