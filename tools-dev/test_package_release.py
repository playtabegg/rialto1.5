"""package_release copies only the allow-listed release set.

A fixture dist tree stuffed with signing_config.json, templates, input/,
output/, build logs and ISOs must produce an output that contains none of
those, and whose manifest is exactly the allowed files.
"""
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import package_release  # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def says(label, condition, detail=""):
    print(f"  [{'OK  ' if condition else 'FAIL'}] {label}{(' -> ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def make_fixture(root):
    # Allowed
    touch(os.path.join(root, "Rialto.exe"), b"MZ rialto")
    touch(os.path.join(root, "menu.exe"), b"MZ menu")
    touch(os.path.join(root, "README.md"), b"# Rialto\n")
    touch(os.path.join(root, "SIGNING.md"), b"# Signing\n")
    touch(os.path.join(root, "requirements.txt"), b"pillow>=10,<12\n")
    touch(os.path.join(root, "launch_rialto.bat"), b"@echo off\n")
    touch(os.path.join(root, "debug_rialto.bat"), b"@echo off\n")
    touch(os.path.join(root, "rialto.spec"), b"# spec\n")
    touch(os.path.join(root, "menu.spec"), b"# spec\n")
    touch(os.path.join(root, "assets", "bird_icon.ico"), b"ico")
    touch(os.path.join(root, "docs", "rialto-guide.html"), b"<html></html>")
    # Forbidden - must not land in the output
    touch(os.path.join(root, "signing_config.json"), b'{"endpoint":"secret"}')
    touch(os.path.join(root, "config.json"), b"{}")
    touch(os.path.join(root, "last_profile.json"), b"{}")
    touch(os.path.join(root, "build_log.txt"), b"log")
    touch(os.path.join(root, "input", "Game", "game.exe"), b"MZ")
    touch(os.path.join(root, "output", "Game", "setup.exe"), b"MZ")
    touch(os.path.join(root, "templates", "client.json"), b"{}")
    touch(os.path.join(root, "tools", "TrustedSigning", "dlib.dll"), b"dll")
    touch(os.path.join(root, "__pycache__", "Rialto.cpython-39.pyc"), b"pyc")
    touch(os.path.join(root, "Game.iso"), b"iso")
    return [
        "Rialto.exe", "menu.exe", "README.md", "SIGNING.md", "requirements.txt",
        "launch_rialto.bat", "debug_rialto.bat", "rialto.spec", "menu.spec",
        "assets/bird_icon.ico", "docs/rialto-guide.html",
    ]


def listed(folder):
    found = []
    for dirpath, _dirnames, filenames in os.walk(folder):
        for name in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), folder).replace("\\", "/"))
    return sorted(found)


def main():
    base = tempfile.mkdtemp(prefix="rialto_pkg_")
    try:
        source = os.path.join(base, "dist")
        dest = os.path.join(base, "release")
        os.makedirs(source)
        expected = sorted(make_fixture(source))

        print("1. forbidden files in the source do not land in the output")
        manifest = package_release.package_release(
            source, dest, allow_unsigned=True)
        check("manifest is exactly the allowed set", sorted(manifest), expected)
        check("output listing matches the manifest", listed(dest), expected)
        for name in ("signing_config.json", "config.json", "last_profile.json",
                     "build_log.txt", "Game.iso"):
            says(f"{name} is absent", not os.path.exists(os.path.join(dest, name)))
        for folder in ("input", "output", "templates", "tools", "__pycache__"):
            says(f"{folder}/ is absent", not os.path.exists(os.path.join(dest, folder)))
        print()

        print("2. unsigned binaries are refused when signtool can check")
        try:
            package_release.package_release(
                source, os.path.join(base, "unsigned"),
                allow_unsigned=False,
                signtool="fake-signtool.exe",
                verify=lambda path, signtool: False)
            says("unsigned packaging raised", False, "PackageError not raised")
        except package_release.PackageError as e:
            says("unsigned packaging refused", "unsigned" in str(e).lower(), str(e))
        print()
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all package-release checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
