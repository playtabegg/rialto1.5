"""Prove Rialto signs THIS build's copy of menu.exe, and never the shared one.

Rialto is open source and the generic menu.exe ships on discs built by anyone,
so the publicly distributed binary is unsigned on purpose. Every author signs
their own staged copy with their own Azure Artifact Signing account (BYOK). The
rules that has to hold to:

  1. trusted_signing.sign_staged_menu invokes the signer on menu/menu.exe when
     an account is configured, and skips with a clear line when it is not
  2. it never signs anything outside the build's own menu/ folder - the shared
     dist/menu.exe stays untouched, byte for byte
  3. RialtoApp.stage_menu_executable offers every staged copy for signing, on
     the pre-built path and the compiled fallback, but not when nothing staged
  4. the whole thing is gated on Sign Final Build, and a failure downgrades to
     an unsigned menu rather than killing the build

Nothing here launches the GUI, signtool, or Azure: the real methods are pulled
out of Rialto.pyw and the real trusted_signing module is driven with a fake
signer standing in for signtool.exe.

Usage: python test_staged_menu_signing.py [path-to-rialto1.5]
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

# The status lines under test carry emoji; the default console codepage would
# raise on them before any assertion got a chance to fail honestly.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = os.path.join(REPO, "Rialto.pyw")

sys.path.insert(0, REPO)
import trusted_signing  # noqa: E402  (the real module, driven with a fake signer)

failures = []


def check(label, got, want):
    good = got == want
    print(f"  [{'OK  ' if good else 'FAIL'}] {label}: {got!r}")
    if not good:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def ok(label, cond, detail=""):
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}{(' -> ' + detail) if detail else ''}")
    if not cond:
        failures.append(label)


def methods(src, class_name, names):
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


def module_funcs(src, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            seen.add(node.name)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract module functions {sorted(missing)}")
    return "\n\n".join(out)


class Flag:
    """Stands in for a tk.BooleanVar."""
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


RIALTO_SRC = open(RIALTO, encoding="utf-8").read()

SHARED_MENU_BYTES = b"MZ the one generic menu.exe everybody gets"


class FakeSigner:
    """Stands in for signtool + Azure. Records every path it was handed."""

    def __init__(self, succeeds=True):
        self.succeeds = succeeds
        self.signed = []

    def __call__(self, file_path, status=print):
        self.signed.append(os.path.abspath(file_path))
        if not self.succeeds:
            return False, "signtool failed: fake refusal"
        with open(file_path, "ab") as f:
            f.write(b"<fake authenticode blob>")
        return True, "Signed successfully with Azure Artifact Signing"


def with_signing(configured, signer, fn):
    """Run fn() with trusted_signing wired to a fake account and fake signer."""
    real_load, real_sign = trusted_signing.load_config, trusted_signing.sign_file
    trusted_signing.load_config = lambda: ({
        "provider": "azure_trusted_signing",
        "endpoint": "https://eus.codesigning.azure.net",
        "account_name": "fake-account",
        "certificate_profile": "fake-profile",
    } if configured else {})
    trusted_signing.sign_file = signer
    try:
        return fn()
    finally:
        trusted_signing.load_config, trusted_signing.sign_file = real_load, real_sign


# --------------------------------------------------------------------------
print("1. trusted_signing.sign_staged_menu")

stage = tempfile.mkdtemp(prefix="rialto_sign_")
menu_dir = os.path.join(stage, "menu")
os.makedirs(menu_dir)
staged = os.path.join(menu_dir, "menu.exe")
with open(staged, "wb") as f:
    f.write(SHARED_MENU_BYTES)

signer = FakeSigner()
signed, message = with_signing(True, signer, lambda: trusted_signing.sign_staged_menu(menu_dir, lambda m: None))
check("configured account -> signed", signed, True)
check("the signer was handed the staged copy and nothing else", signer.signed, [os.path.abspath(staged)])
ok("the staged file really changed", open(staged, "rb").read() != SHARED_MENU_BYTES, message)

signer = FakeSigner()
signed, message = with_signing(False, signer, lambda: trusted_signing.sign_staged_menu(menu_dir, lambda m: None))
check("no account configured -> skipped, not failed loudly", signed, False)
check("and the signer was never invoked", signer.signed, [])
ok("the skip line says signing is not set up", "not set up" in message, message)
ok("the skip line reassures that the disc still works", "works fine" in message, message)
ok("the skip line points at the guide", "SIGNING.md" in message, message)

signer = FakeSigner(succeeds=False)
signed, message = with_signing(True, signer, lambda: trusted_signing.sign_staged_menu(menu_dir, lambda m: None))
check("signer refuses -> reported, never raised", signed, False)
ok("and the reason is passed through", "signtool failed" in message, message)

empty = os.path.join(stage, "no_menu_here")
os.makedirs(empty)
signer = FakeSigner()
signed, message = with_signing(True, signer, lambda: trusted_signing.sign_staged_menu(empty, lambda m: None))
check("nothing staged (batch-menu fallback) -> nothing signed", signed, False)
check("and the signer was not invoked", signer.signed, [])
print()


# --------------------------------------------------------------------------
print("2. the shared source binary is never the thing that gets signed")
# Reproduce the real layout: a dist/menu.exe shared by every build, and a
# junction-free staged copy. Then point sign_staged_menu at a menu/ folder
# whose menu.exe is a symlink back to the shared binary, and watch it refuse.
shared_dir = os.path.join(stage, "dist")
os.makedirs(shared_dir)
shared = os.path.join(shared_dir, "menu.exe")
with open(shared, "wb") as f:
    f.write(SHARED_MENU_BYTES)

linked_dir = os.path.join(stage, "linked_menu")
os.makedirs(linked_dir)
link = os.path.join(linked_dir, "menu.exe")
try:
    os.symlink(shared, link)
    linkable = True
except (OSError, NotImplementedError, AttributeError):
    linkable = False  # no Developer Mode / no privilege: the copy path is all there is

if linkable:
    signer = FakeSigner()
    signed, message = with_signing(True, signer, lambda: trusted_signing.sign_staged_menu(linked_dir, lambda m: None))
    check("a menu.exe that is really the shared binary -> refused", signed, False)
    check("the signer never saw it", signer.signed, [])
    ok("the refusal explains itself", "Refusing to sign" in message, message)
else:
    print("  [SKIP] symlink guard (this account cannot create symlinks)")

# A symlink needs Developer Mode, so on most machines the case above is skipped
# and the guard goes unexercised. These two need no privilege at all, which is
# what makes them the ones an author could actually end up with.
junctioned = os.path.join(stage, "junctioned_menu")
if subprocess.run(["cmd", "/c", "mklink", "/J", junctioned, shared_dir],
                  capture_output=True).returncode == 0:
    signer = FakeSigner()
    signed, message = with_signing(True, signer, lambda: trusted_signing.sign_staged_menu(junctioned, lambda m: None))
    check("a menu/ folder that is a junction onto the shared folder -> refused",
          signed, False)
    check("the signer never saw it", signer.signed, [])
    ok("the refusal explains itself", "Refusing to sign" in message, message)
else:
    print("  [SKIP] junction guard (mklink /J refused here)")

hardlinked_dir = os.path.join(stage, "hardlinked_menu")
os.makedirs(hardlinked_dir)
try:
    os.link(shared, os.path.join(hardlinked_dir, "menu.exe"))
    hardlinkable = True
except (OSError, NotImplementedError, AttributeError):
    hardlinkable = False

if hardlinkable:
    signer = FakeSigner()
    signed, message = with_signing(True, signer, lambda: trusted_signing.sign_staged_menu(hardlinked_dir, lambda m: None))
    check("a menu.exe that is a hard link to the shared binary -> refused",
          signed, False)
    check("the signer never saw it", signer.signed, [])
    ok("the refusal explains itself", "Refusing to sign" in message, message)
else:
    print("  [SKIP] hard link guard (this filesystem has no hard links)")

check("the shared binary is byte-identical after everything above",
      open(shared, "rb").read(), SHARED_MENU_BYTES)
# The junction has to go before rmtree, or Python's cleanup walks into it.
subprocess.run(["cmd", "/c", "rmdir", junctioned], capture_output=True)
shutil.rmtree(stage, ignore_errors=True)
print()


# --------------------------------------------------------------------------
print("3. stage_menu_executable offers every staged copy for signing")
stage_src = methods(RIALTO_SRC, "RialtoApp", ["stage_menu_executable"])
helper_src = module_funcs(RIALTO_SRC, ["prebuilt_menu_exe", "write_menu_source"])

ok("stage_menu_executable calls the signing hook",
   "sign_staged_menu_exe" in stage_src,
   f"{stage_src.count('self.sign_staged_menu_exe')} call site(s)")


def run_stage(with_prebuilt, compiler_works=False):
    """Run the real stage_menu_executable, recording what it offers to sign."""
    base = tempfile.mkdtemp(prefix="rialto_stagesign_")
    app_root = os.path.join(base, "app")
    output = os.path.join(base, "output")
    os.makedirs(app_root)
    os.makedirs(output)
    source_exe = os.path.join(app_root, "menu.exe")
    if with_prebuilt:
        with open(source_exe, "wb") as f:
            f.write(SHARED_MENU_BYTES)

    helpers = {"os": os, "sys": sys, "APP_ROOT": app_root,
               "MENU_TEMPLATE_SOURCE": "# the real disc menu source\n"}
    exec(helper_src, helpers)

    ns = {"os": os, "sys": sys, "shutil": shutil, "json": json,
          "prebuilt_menu_exe": helpers["prebuilt_menu_exe"],
          "write_menu_source": helpers["write_menu_source"]}
    exec(f"class Host:\n{textwrap.indent(stage_src, '    ')}", ns)
    host = ns["Host"]()
    offered = []
    host.update_status = lambda msg: None
    host.copy_vcruntime_dlls = lambda d: None
    host.sign_staged_menu_exe = lambda menu_dir: offered.append(menu_dir)

    def fake_compile(output_path):
        if not compiler_works:
            return False
        with open(os.path.join(output_path, "menu", "menu.exe"), "wb") as f:
            f.write(b"MZ compiled here")
        os.remove(os.path.join(output_path, "menu", "menu_launcher.pyw"))
        return True

    host.compile_pyqt5_menu = fake_compile
    result = host.stage_menu_executable(output)
    source_intact = (not with_prebuilt) or open(source_exe, "rb").read() == SHARED_MENU_BYTES
    shutil.rmtree(base, ignore_errors=True)
    return result, [os.path.basename(p) for p in offered], source_intact


got, offered, intact = run_stage(with_prebuilt=True)
check("pre-built copied -> that copy is offered for signing", (got, offered), (True, ["menu"]))
ok("and the shared source exe is untouched by staging", intact)

got, offered, _ = run_stage(with_prebuilt=False, compiler_works=True)
check("compiled fallback -> its copy is offered too", (got, offered), (True, ["menu"]))

got, offered, _ = run_stage(with_prebuilt=False, compiler_works=False)
check("nothing staged -> nothing offered", (got, offered), (False, []))
print()


# --------------------------------------------------------------------------
print("4. the Sign Final Build gate and the failure path")
hook_src = methods(RIALTO_SRC, "RialtoApp", ["sign_staged_menu_exe"])


def run_hook(sign_final, configured, signer):
    base = tempfile.mkdtemp(prefix="rialto_hook_")
    menu = os.path.join(base, "menu")
    os.makedirs(menu)
    with open(os.path.join(menu, "menu.exe"), "wb") as f:
        f.write(SHARED_MENU_BYTES)
    ns = {"os": os, "sys": sys}
    exec(f"class Host:\n{textwrap.indent(hook_src, '    ')}", ns)
    host = ns["Host"]()
    log = []
    host.update_status = log.append
    host.sign_final_build = Flag(sign_final)
    try:
        result = with_signing(configured, signer, lambda: host.sign_staged_menu_exe(menu))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return result, log


signer = FakeSigner()
result, log = run_hook(sign_final=False, configured=True, signer=signer)
check("Sign Final Build off -> no signature, even with an account", result, False)
check("nothing was sent to Azure", signer.signed, [])
ok("the log explains how to turn it on", any("Sign Final Build" in m for m in log), str(log))

signer = FakeSigner()
result, log = run_hook(sign_final=True, configured=False, signer=signer)
check("ticked but unconfigured -> skipped", result, False)
check("still nothing sent to Azure", signer.signed, [])
ok("the skip is informational, not a warning",
   any(m.startswith("ℹ️") for m in log) and not any(m.startswith("⚠️") for m in log), str(log))

signer = FakeSigner()
result, log = run_hook(sign_final=True, configured=True, signer=signer)
check("ticked and configured -> signed", result, True)
check("exactly one signature, on the staged copy", [os.path.basename(p) for p in signer.signed], ["menu.exe"])
ok("the log says whose signature it is", any("your own account" in m for m in log), str(log))

signer = FakeSigner(succeeds=False)
result, log = run_hook(sign_final=True, configured=True, signer=signer)
check("a real failure -> reported, build continues", result, False)
ok("and it is a warning, because an attempt did fail",
   any(m.startswith("⚠️") for m in log), str(log))


def exploding_signer(file_path, status=print):
    raise RuntimeError("azure fell over")


result, log = run_hook(sign_final=True, configured=True, signer=exploding_signer)
check("an exception in signing never escapes the hook", result, False)
ok("it lands in the log instead", any("azure fell over" in m for m in log), str(log))
print()


if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print("All staged-menu signing assertions passed.")
