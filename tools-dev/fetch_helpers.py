"""Put the tools Rialto carries into helpers/, each file checked against its pin.

Rialto 1.5.1 carries Inno Setup 6.5.4 and cdrtools 3.02a10's mkisofs inside
Rialto.exe, so nobody has to install them. The binaries stay out of git: this
copies them from the pinned local installs named in helpers/MANIFEST.json and
checks each file's SHA-256 and size. packaging/rialto.spec runs the same check
(problems() below) and refuses to build if anything is missing, changed, or
not in the manifest.

Usage (from the repo root):
    python tools-dev/fetch_helpers.py           copy what is missing, check everything
    python tools-dev/fetch_helpers.py --check   check helpers/ only, copy nothing
    python tools-dev/fetch_helpers.py --pin     rewrite the pins from the sources
                                                (only when moving to a new version
                                                on purpose; say so in the commit)
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HELPERS = os.path.join(REPO, "helpers")
MANIFEST = os.path.join(HELPERS, "MANIFEST.json")
# The folders that ride inside Rialto.exe. Everything in them must be pinned.
CARRIED_FOLDERS = ("inno", "cdrtools")

INNO_SOURCE = "C:/Program Files (x86)/Inno Setup 6"
CDRTOOLS_SOURCE = "C:/cdrtools"
INNO_LANGUAGES = ("BrazilianPortuguese", "Catalan", "Czech", "Danish", "Dutch", "Finnish", "French", "German",
                  "Hebrew", "Italian", "Japanese", "Norwegian", "Polish", "Portuguese", "Russian", "Slovak",
                  "Slovenian", "Spanish", "Turkish", "Ukrainian")
INNO = {"component": "Inno Setup", "version": "6.5.4",
        "license": "Inno Setup License (licenses/InnoSetup-license.txt)"}
MKISOFS = {"component": "mkisofs (cdrtools)", "version": "3.02a10 2021/07/23, i686-pc-cygwin, from cdrtfe 1.5.9.1",
           "license": "GPL-2.0-or-later, with CDDL-1.0 parts (licenses/GPL-2.0.txt, licenses/THIRD-PARTY.txt)"}
CYGWIN = {"component": "Cygwin DLL", "version": "2.3.1",
          "license": "GPL-3.0-or-later (licenses/GPL-3.0.txt)"}


def plan():
    """{path under helpers/: (source, facts)} for --pin. The manifest is what counts after that."""
    files = {}
    for name in ("ISCC.exe", "ISCmplr.dll", "ISPP.dll", "ISPPBuiltins.iss", "Setup.e32", "SetupLdr.e32",
                 "islzma.dll", "Default.isl", "license.txt", "ISCmplr.dll.issig", "ISPP.dll.issig",
                 "Setup.e32.issig", "SetupLdr.e32.issig", "islzma.dll.issig"):
        files["inno/" + name] = (INNO_SOURCE + "/" + name, INNO)
    for language in INNO_LANGUAGES:
        files["inno/Languages/%s.isl" % language] = (INNO_SOURCE + "/Languages/%s.isl" % language, INNO)
    files["cdrtools/mkisofs.exe"] = (CDRTOOLS_SOURCE + "/mkisofs.exe", MKISOFS)
    files["cdrtools/cygwin1.dll"] = (CDRTOOLS_SOURCE + "/cygwin1.dll", CYGWIN)
    # The license texts travel with the binaries they cover.
    files["cdrtools/GPL-2.0.txt"] = ("licenses/GPL-2.0.txt", MKISOFS)
    files["cdrtools/CDDL-1.0.txt"] = ("licenses/CDDL-1.0.txt", MKISOFS)
    files["cdrtools/GPL-3.0.txt"] = ("licenses/GPL-3.0.txt", CYGWIN)
    files["cdrtools/THIRD-PARTY.txt"] = ("licenses/THIRD-PARTY.txt",
                                         {"component": "Rialto", "version": "1.5.1", "license": "MIT"})
    return files


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path=MANIFEST):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def source_path(source, repo=REPO):
    return source if os.path.isabs(source) else os.path.join(repo, *source.split("/"))


def problems(helpers=HELPERS, manifest=None):
    """Everything wrong with helpers/ against the manifest, as sentences. [] when it is exactly as pinned."""
    if manifest is None:
        try:
            manifest = load_manifest(os.path.join(helpers, "MANIFEST.json"))
        except (OSError, ValueError) as e:
            return ["helpers/MANIFEST.json cannot be read: %s" % e]
    pinned = manifest.get("files", {})
    found = []
    for rel, pin in sorted(pinned.items()):
        path = os.path.join(helpers, *rel.split("/"))
        if not os.path.isfile(path):
            found.append("helpers/%s is missing" % rel)
        elif os.path.getsize(path) != pin["size"] or sha256(path) != pin["sha256"]:
            found.append("helpers/%s does not match its pin" % rel)
    for folder in CARRIED_FOLDERS:
        for dirpath, _dirs, names in os.walk(os.path.join(helpers, folder)):
            for name in names:
                rel = os.path.relpath(os.path.join(dirpath, name), helpers).replace("\\", "/")
                if rel not in pinned:
                    found.append("helpers/%s is not in the manifest" % rel)
    return found


def fetch(helpers=HELPERS, manifest=None, repo=REPO):
    """Copy every pinned file that is missing or wrong from its source. Returns the problems left."""
    manifest = manifest or load_manifest(os.path.join(helpers, "MANIFEST.json"))
    for rel, pin in sorted(manifest["files"].items()):
        dest = os.path.join(helpers, *rel.split("/"))
        if os.path.isfile(dest) and os.path.getsize(dest) == pin["size"] and sha256(dest) == pin["sha256"]:
            continue
        source = source_path(pin["source"], repo)
        if not os.path.isfile(source):
            print("  missing source: %s (for helpers/%s)" % (source, rel))
            continue
        if sha256(source) != pin["sha256"]:
            print("  the source does not match its pin, not copied: %s" % source)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(source, dest)
        print("  copied helpers/%s" % rel)
    return problems(helpers, manifest)


def pin(helpers=HELPERS, repo=REPO):
    files = {}
    for rel, (source, facts) in sorted(plan().items()):
        path = source_path(source, repo)
        files[rel] = dict(facts, source=source, size=os.path.getsize(path), sha256=sha256(path))
    manifest = {
        "about": "The tools Rialto carries inside Rialto.exe (1.5.1). tools-dev/fetch_helpers.py copies "
                 "each file from its source and checks it; packaging/rialto.spec refuses to build unless helpers/ "
                 "matches this exactly. Licenses and source: licenses/THIRD-PARTY.txt.",
        "files": files,
    }
    os.makedirs(helpers, exist_ok=True)
    with open(os.path.join(helpers, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("pinned %d files in helpers/MANIFEST.json" % len(files))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Put the tools Rialto carries into helpers/.")
    parser.add_argument("--check", action="store_true", help="check helpers/ only, copy nothing")
    parser.add_argument("--pin", action="store_true", help="rewrite the pins from the sources")
    args = parser.parse_args(argv)
    if args.pin:
        pin()
    left = problems() if args.check else fetch()
    if left:
        print("helpers/ is not ready:")
        for line in left:
            print("  " + line)
        return 1
    print("helpers/ matches helpers/MANIFEST.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
