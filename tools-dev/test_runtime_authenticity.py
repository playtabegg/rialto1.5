"""downloaded VC++ redistributables must be Microsoft-signed, or discarded.

A size check is not an authenticity check. An unverified vcredist that later
lands in Inno [Files] is copied into setup.exe and Authenticode-signed by the
author. Failed / unavailable verification deletes the file and the build
continues without it.
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap
import urllib.request

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

sys.path.insert(0, REPO)
import trusted_signing  # noqa: E402
import update.fetch as fetch_module  # noqa: E402

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


def extract_funcs(src, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            seen.add(node.name)
        elif isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in names:
            out.append(ast.get_source_segment(src, node))
            seen.add(node.targets[0].id)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract {sorted(missing)}")
    return "\n\n".join(out)


def extract_methods(src, class_name, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    seen.add(item.name)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


def make_host(src):
    helper = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.FunctionDef) and n.name == "iss_value")
    reads = {n.id for n in ast.walk(helper)
             if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    constants = [ast.get_source_segment(src, node) for node in ast.parse(src).body
                 if isinstance(node, ast.Assign)
                 and getattr(node.targets[0], "id", "") in reads]
    methods = extract_methods(src, "RialtoApp", [
        "download_essential_runtimes", "_accept_microsoft_runtime",
        "generate_enhanced_installer_script",
    ])
    ns = {"os": os, "re": __import__("re"), "shutil": shutil,
          "urllib": urllib, "sys": sys}
    exec("\n\n".join(constants + [ast.get_source_segment(src, helper)]), ns)
    exec("class Host:\n" + textwrap.indent(methods, "    "), ns)
    host = ns["Host"]()
    host.log = []
    host.update_status = host.log.append
    host.get_disk_slice_size = lambda: None
    return host


def fake_fetch(_url, dest, **_options):
    """Stands in for update.fetch.fetch_to_file: no network, a small MZ stub."""
    with open(dest, "wb") as f:
        f.write(b"MZ" + b"\x00" * 2048)


def main():
    src = open(RIALTO, encoding="utf-8").read()
    host = make_host(src)
    real_signed = trusted_signing.signed_by_microsoft
    real_fetch = fetch_module.fetch_to_file
    real_urlopen = urllib.request.urlopen
    network = []

    def no_network(*args, **kwargs):
        network.append(args[0] if args else kwargs)
        raise AssertionError("the harness tried to reach the network")

    urllib.request.urlopen = no_network

    print("1. unsigned / non-Microsoft fake exe is rejected and deleted")
    out = tempfile.mkdtemp(prefix="rialto_rt_bad_")
    try:
        fetch_module.fetch_to_file = fake_fetch
        trusted_signing.signed_by_microsoft = lambda path: False
        host.log.clear()
        host.download_essential_runtimes(out)
        for name in ("vcredist_x64.exe", "vcredist_x86.exe"):
            path = os.path.join(out, name)
            says(f"{name} was deleted", not os.path.exists(path), path)
        joined = "\n".join(host.log)
        says("status says the file is not Microsoft-signed",
             "not a Microsoft-signed" in joined)
        says("status says the build continues without it",
             "continues without it" in joined)
        host.generate_enhanced_installer_script(out, {"Title": "T", "Developer": "D"})
        iss = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        says("unverified runtimes never reach Inno [Files]",
             'Source: "vcredist_x86.exe"' not in iss
             and 'Source: "vcredist_x64.exe"' not in iss)
    finally:
        fetch_module.fetch_to_file = real_fetch
        trusted_signing.signed_by_microsoft = real_signed
        shutil.rmtree(out, ignore_errors=True)
    print()

    print("2. signtool unavailable (None) is also a reject")
    out = tempfile.mkdtemp(prefix="rialto_rt_none_")
    try:
        fetch_module.fetch_to_file = fake_fetch
        trusted_signing.signed_by_microsoft = lambda path: None
        host.log.clear()
        host.download_essential_runtimes(out)
        says("x64 discarded when signtool is missing",
             not os.path.exists(os.path.join(out, "vcredist_x64.exe")))
        says("status names signtool",
             "signtool.exe was not found" in "\n".join(host.log),
             "\n".join(host.log)[-400:])
    finally:
        fetch_module.fetch_to_file = real_fetch
        trusted_signing.signed_by_microsoft = real_signed
        shutil.rmtree(out, ignore_errors=True)
    print()

    print("3. happy path: stubbed Microsoft signature is packaged")
    out = tempfile.mkdtemp(prefix="rialto_rt_ok_")
    try:
        fetch_module.fetch_to_file = fake_fetch
        trusted_signing.signed_by_microsoft = lambda path: True
        host.log.clear()
        host.download_essential_runtimes(out)
        says("x64 kept", os.path.isfile(os.path.join(out, "vcredist_x64.exe")))
        says("x86 kept", os.path.isfile(os.path.join(out, "vcredist_x86.exe")))
        says("status says Microsoft-signed",
             "Microsoft-signed" in "\n".join(host.log),
             "\n".join(host.log)[-400:])
        host.generate_enhanced_installer_script(out, {"Title": "T", "Developer": "D"})
        iss = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        says("verified x86 reaches [Files]",
             'Source: "vcredist_x86.exe"' in iss)
        says("verified x64 reaches [Files]",
             'Source: "vcredist_x64.exe"' in iss)
    finally:
        fetch_module.fetch_to_file = real_fetch
        trusted_signing.signed_by_microsoft = real_signed
        shutil.rmtree(out, ignore_errors=True)
    print()

    print("4. download_essential_runtimes uses signed_by_microsoft, not a size check alone")
    dl = extract_methods(src, "RialtoApp", ["download_essential_runtimes"])
    acc = extract_methods(src, "RialtoApp", ["_accept_microsoft_runtime"])
    says("downloader calls _accept_microsoft_runtime",
         "_accept_microsoft_runtime" in dl)
    says("acceptor calls signed_by_microsoft",
         "signed_by_microsoft" in acc)
    print()

    urllib.request.urlopen = real_urlopen
    says("no scenario reached the network", not network, repr(network))

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all runtime-authenticity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
