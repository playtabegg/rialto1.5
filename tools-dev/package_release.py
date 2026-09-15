"""Assemble a clean Rialto release folder or zip from a built tree.

A PyInstaller `dist/` folder is a working tree, not a release: it routinely
holds signing_config.json, last_profile.json, templates, input/, output/,
build logs and unsigned copies of Rialto.exe / menu.exe. This script copies
ONLY the files a user should receive, refuses if an excluded path would land
in the output, and refuses unsigned binaries unless --allow-unsigned is set.

Usage:
    python tools-dev/package_release.py --source dist --output release\\Rialto-1.5
    python tools-dev/package_release.py --source dist --output release\\Rialto-1.5.zip
    python tools-dev/package_release.py --source dist --output release\\Rialto-1.5 --allow-unsigned
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

ALLOWED_ROOT_FILES = frozenset({
    "Rialto.exe",
    "menu.exe",
    "README.md",
    "SIGNING.md",
    "requirements.txt",
    "launch_rialto.bat",
    "debug_rialto.bat",
    "rialto.spec",
    "menu.spec",
})
ALLOWED_ROOT_DIRS = frozenset({"assets", "docs"})
REQUIRED_BINARIES = ("Rialto.exe", "menu.exe")

FORBIDDEN_NAMES = frozenset({
    "signing_config.json",
    "config.json",
    "last_profile.json",
    "build_log.txt",
})
FORBIDDEN_DIR_NAMES = frozenset({
    "input",
    "output",
    "templates",
    "tools",
    "__pycache__",
})


class PackageError(Exception):
    """Release packaging refused to continue."""


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def is_excluded(rel):
    parts = rel.replace("\\", "/").split("/")
    name = parts[-1]
    if name in FORBIDDEN_NAMES:
        return True
    if any(part in FORBIDDEN_DIR_NAMES for part in parts):
        return True
    if name.lower().endswith(".iso"):
        return True
    return False


def collect_planned(source):
    """Explicit allow-list of relative paths that will be copied."""
    planned = []
    for name in sorted(ALLOWED_ROOT_FILES):
        path = os.path.join(source, name)
        if os.path.isfile(path):
            planned.append(name)
    for dirname in sorted(ALLOWED_ROOT_DIRS):
        root = os.path.join(source, dirname)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in FORBIDDEN_DIR_NAMES]
            for filename in sorted(filenames):
                full = os.path.join(dirpath, filename)
                planned.append(_rel(full, source))
    return planned


def find_signtool():
    found = shutil.which("signtool.exe") or shutil.which("signtool")
    if found:
        return found
    kit_roots = [
        r"C:\Program Files (x86)\Windows Kits\10\bin",
        r"C:\Program Files\Windows Kits\10\bin",
    ]
    for root in kit_roots:
        if not os.path.isdir(root):
            continue
        for version in sorted(os.listdir(root), reverse=True):
            candidate = os.path.join(root, version, "x64", "signtool.exe")
            if os.path.isfile(candidate):
                return candidate
        candidate = os.path.join(root, "x64", "signtool.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def verify_authenticode(path, signtool):
    try:
        result = subprocess.run(
            [signtool, "verify", "/pa", path],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return False
    return result.returncode == 0


def print_signing_reminder():
    banner = "Rialto.exe and menu.exe MUST be signed before packaging."
    print()
    print("=" * 72)
    print("\033[1m" + banner + "\033[0m")
    print(banner)
    print("=" * 72)
    print()


def _copy_planned(source, dest, planned):
    for rel in planned:
        src = os.path.join(source, *rel.split("/"))
        dst = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _assert_dest_clean(dest, planned):
    """Fail if the assembled tree contains anything off the allow-list."""
    allowed = set(planned)
    found = []
    for dirpath, dirnames, filenames in os.walk(dest):
        for filename in filenames:
            rel = _rel(os.path.join(dirpath, filename), dest)
            found.append(rel)
            if rel not in allowed or is_excluded(rel):
                raise PackageError(
                    "Refusing to package: excluded or unexpected file would be "
                    "included: %s" % rel)
    extra = sorted(set(found) - allowed)
    missing = sorted(allowed - set(found))
    if extra:
        raise PackageError("Refusing to package unexpected files: %s" % extra)
    if missing:
        raise PackageError("Packaged tree is missing planned files: %s" % missing)
    return found


def package_release(source, dest, allow_unsigned=False, signtool=None, verify=None):
    """Copy the allow-listed release set from `source` to `dest`.

    `dest` may be a folder or a path ending in .zip. Returns the sorted
    manifest (relative POSIX paths). Raises PackageError on refusal.
    """
    source = os.path.abspath(source)
    dest = os.path.abspath(dest)
    if not os.path.isdir(source):
        raise PackageError("Source tree does not exist: %s" % source)

    planned = collect_planned(source)
    leaks = [rel for rel in planned if is_excluded(rel)]
    if leaks:
        raise PackageError(
            "Refusing to package: excluded file(s) would be included: %s"
            % ", ".join(leaks))

    for required in REQUIRED_BINARIES:
        if required not in planned:
            raise PackageError(
                "Refusing to package: %s is missing from %s" % (required, source))

    print_signing_reminder()
    if signtool is None:
        signtool = find_signtool()
    if verify is None:
        verify = verify_authenticode

    if not allow_unsigned and signtool:
        unsigned = []
        for name in REQUIRED_BINARIES:
            path = os.path.join(source, name)
            if not verify(path, signtool):
                unsigned.append(name)
        if unsigned:
            raise PackageError(
                "Refusing to package unsigned binaries: %s. "
                "Sign them first, or pass --allow-unsigned."
                % ", ".join(unsigned))
    elif not allow_unsigned:
        print("signtool.exe not found - cannot verify signatures. "
              "The reminder above still applies.")

    as_zip = dest.lower().endswith(".zip")
    staging = tempfile.mkdtemp(prefix="rialto_release_") if as_zip else dest
    try:
        if not as_zip:
            os.makedirs(staging, exist_ok=True)
        _copy_planned(source, staging, planned)
        found = _assert_dest_clean(staging, planned)
        found = sorted(found)
        if as_zip:
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel in found:
                    zf.write(os.path.join(staging, *rel.split("/")), rel.replace("\\", "/"))
        print("Packaged %d files:" % len(found))
        for rel in found:
            print("  " + rel)
        return found
    finally:
        if as_zip:
            shutil.rmtree(staging, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble a clean Rialto release (no working-tree secrets).")
    parser.add_argument("--source", default=os.path.join(REPO, "dist"),
                        help="Built tree to package from (default: dist/)")
    parser.add_argument("--output", required=True,
                        help="Destination folder, or a .zip path")
    parser.add_argument("--allow-unsigned", action="store_true",
                        help="Allow packaging Rialto.exe / menu.exe with no signature")
    args = parser.parse_args(argv)
    try:
        package_release(args.source, args.output, allow_unsigned=args.allow_unsigned)
    except PackageError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
