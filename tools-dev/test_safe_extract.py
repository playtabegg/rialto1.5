"""Zip members must not extract outside the destination directory.

Python 3.9-3.12 ZipFile.extractall trusts member paths. A `..` component or
an absolute name is zip-slip. safe_extract_all skips those with a warning and
still extracts the good members.
"""
import os
import shutil
import sys
import tempfile
import zipfile

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import trusted_signing  # noqa: E402

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


def main():
    base = tempfile.mkdtemp(prefix="rialto_zipslip_")
    try:
        dest = os.path.join(base, "dest")
        os.makedirs(dest)
        zip_path = os.path.join(base, "payload.zip")
        abs_target = os.path.abspath(os.path.join(base, "abs_evil.txt"))
        abs_member = abs_target.replace("\\", "/")

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("ok.txt", "good")
            zf.writestr("nested/ok2.txt", "also good")
            zf.writestr("../evil.txt", "outside")
            zf.writestr("foo/../../outside.txt", "outside too")
            zf.writestr(abs_member, "absolute")

        warnings = []
        with zipfile.ZipFile(zip_path) as zf:
            trusted_signing.safe_extract_all(zf, dest, status=warnings.append)

        says("good member extracted",
             os.path.isfile(os.path.join(dest, "ok.txt"))
             and open(os.path.join(dest, "ok.txt"), encoding="utf-8").read() == "good")
        says("nested good member extracted",
             os.path.isfile(os.path.join(dest, "nested", "ok2.txt")))
        says(".. member did not write next to dest",
             not os.path.exists(os.path.join(base, "evil.txt")))
        says("foo/../../ member did not write outside dest",
             not os.path.exists(os.path.join(base, "outside.txt")))
        says("absolute member did not write outside dest",
             not os.path.exists(abs_target))
        says("warnings were logged for the skipped members",
             any("unsafe zip member" in w for w in warnings),
             repr([w.encode("ascii", "replace").decode() for w in warnings]))
        says("ensure_dlib source uses safe_extract_all",
             "safe_extract_all" in open(
                 os.path.join(REPO, "trusted_signing.py"), encoding="utf-8").read())
        says("Rialto innoextract path uses safe_extract_all",
             "safe_extract_all" in open(
                 os.path.join(REPO, "Rialto.pyw"), encoding="utf-8").read())
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all safe-extract checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
