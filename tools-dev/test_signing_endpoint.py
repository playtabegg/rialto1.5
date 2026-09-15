"""sign_file re-validates the Artifact Signing endpoint at use, not only at save.

signing_config.json is a plain file next to a portable Rialto.exe. Writing an
endpoint into it by hand used to skip save_config()'s allowlist and hand that
host to the dlib's token exchange.
"""
import os
import json
import shutil
import sys
import tempfile

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
    tmp = tempfile.mkdtemp(prefix="rialto_endpoint_")
    dummy = os.path.join(tmp, "payload.exe")
    with open(dummy, "wb") as f:
        f.write(b"MZ")

    real_config = trusted_signing.CONFIG_FILE
    real_find = trusted_signing.find_signtool
    called = []

    def boom():
        called.append(True)
        raise AssertionError("signtool must not be invoked for a bad endpoint")

    print("1. a hand-written evil endpoint is refused without invoking signtool")
    try:
        trusted_signing.CONFIG_FILE = os.path.join(tmp, "signing_config.json")
        with open(trusted_signing.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "provider": "azure_trusted_signing",
                "endpoint": "https://evil.example.com",
                "account_name": "stolen-account",
                "certificate_profile": "stolen-profile",
            }, f)
        trusted_signing.find_signtool = boom
        ok, message = trusted_signing.sign_file(dummy, status=lambda m: None)
        check("sign_file returns False", ok, False)
        says("the error names the endpoint",
             "Artifact Signing endpoint" in message, message)
        check("signtool was never invoked", called, [])
    finally:
        trusted_signing.CONFIG_FILE = real_config
        trusted_signing.find_signtool = real_find
        shutil.rmtree(tmp, ignore_errors=True)
    print()

    print("2. check_environment already flags a bad endpoint")
    # Pending details, so this does not read the author's real config file.
    results = trusted_signing.check_environment(pending={
        "endpoint": "https://evil.example.com",
        "account_name": "x",
        "certificate_profile": "y",
    })
    endpoint_rows = [r for r in results if "endpoint" in r[0].lower()
                     or "region" in r[0].lower()]
    says("check_environment reports the endpoint", bool(endpoint_rows), repr(results))
    if endpoint_rows:
        says("and it is not ok", endpoint_rows[0][1] is False, repr(endpoint_rows[0]))
    print()

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all signing-endpoint checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
