"""Check the frozen-aware path anchoring and the release spec.

Three things are proved here without launching the GUI or PyInstaller:

  1. trusted_signing.BASE_DIR is byte-identical in source mode to the old
     `os.path.dirname(os.path.abspath(__file__))`, and lands next to the exe
     when sys.frozen is set. The module is imported for real (source mode) and
     the frozen branch is re-executed from its own extracted source.
  2. Rialto.pyw's app_root()/constants are evaluated the same way, and no path
     constant is left resolving against the current directory.
  3. rialto.spec carries a real VSVersionInfo, upx=False, README.md in datas,
     and no templates/ entry.

Usage: python test_frozen_paths.py [path-to-rialto1.5]
"""
import ast
import os
import sys
import textwrap

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = os.path.join(REPO, "Rialto.pyw")
SPEC = os.path.join(REPO, "rialto.spec")
TRUSTED = os.path.join(REPO, "trusted_signing.py")

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def ok(label, cond, detail=""):
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}{(' -> ' + detail) if detail else ''}")
    if not cond:
        failures.append(label)


def extract_func(src, name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return textwrap.dedent(ast.get_source_segment(src, node))
    raise SystemExit(f"function {name!r} not found")


def uses_attr(func_src, attr):
    """True if the code (not the docstring/comments) touches `attr`."""
    for node in ast.walk(ast.parse(func_src)):
        if isinstance(node, ast.Attribute) and node.attr == attr:
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value == attr:
            return True
    return False


def call_under(func_src, name, module_file, frozen, exe_path):
    """Run the resolver with sys.frozen / sys.executable faked."""
    class FakeSys:
        pass

    fake = FakeSys()
    fake.executable = exe_path
    if frozen:
        fake.frozen = True
    ns = {"os": os, "sys": fake, "__file__": module_file}
    exec(func_src, ns)
    return ns[name]()


# --------------------------------------------------------------------------
print("trusted_signing.BASE_DIR")
sys.path.insert(0, REPO)
import trusted_signing  # noqa: E402

legacy = os.path.dirname(os.path.abspath(trusted_signing.__file__))
check("source mode identical to the old expression", trusted_signing.BASE_DIR, legacy)
check("CONFIG_FILE beside the module", trusted_signing.CONFIG_FILE,
      os.path.join(legacy, "signing_config.json"))
check("dlib cache beside the module", trusted_signing.DLIB_CACHE_DIR,
      os.path.join(legacy, "tools", "TrustedSigning"))

tsrc = open(TRUSTED, encoding="utf-8").read()
base_fn = extract_func(tsrc, "_base_dir")
frozen_dir = call_under(base_fn, "_base_dir", TRUSTED, frozen=True,
                        exe_path=r"C:\Program Files\Rialto\Rialto.exe")
check("frozen mode lands beside the exe", frozen_dir, r"C:\Program Files\Rialto")
src_dir = call_under(base_fn, "_base_dir", TRUSTED, frozen=False, exe_path=sys.executable)
check("source mode unaffected by sys.executable", src_dir, legacy)
ok("frozen branch never uses _MEIPASS", not uses_attr(base_fn, "_MEIPASS"))
print()

# --------------------------------------------------------------------------
print("Rialto.pyw app_root() and path constants")
rsrc = open(RIALTO, encoding="utf-8").read()
root_fn = extract_func(rsrc, "app_root")
frozen_root = call_under(root_fn, "app_root", RIALTO, frozen=True,
                         exe_path=r"D:\Tools\Rialto\Rialto.exe")
check("frozen app root is beside the exe", frozen_root, r"D:\Tools\Rialto")
source_root = call_under(root_fn, "app_root", RIALTO, frozen=False, exe_path=sys.executable)
check("source app root is the script folder", source_root,
      os.path.dirname(os.path.abspath(RIALTO)))
ok("app root is never sys._MEIPASS", not uses_attr(root_fn, "_MEIPASS"))

tree = ast.parse(rsrc)
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 \
            and isinstance(node.targets[0], ast.Name):
        consts[node.targets[0].id] = node.value

for name in ("CONFIG_FILE", "INPUT_DIR", "OUTPUT_DIR", "TEMPLATES_DIR",
             "LAST_PROFILE_FILE", "LAST_SESSION_FILE"):
    node = consts.get(name)
    anchored = (
        node is not None
        and isinstance(node, ast.Call)
        and any(isinstance(n, ast.Name) and n.id == "APP_ROOT" for n in ast.walk(node))
    )
    ok(f"{name} is anchored to APP_ROOT", anchored,
       ast.unparse(node) if node is not None else "MISSING")

ok("APP_ROOT comes from app_root()",
   isinstance(consts.get("APP_ROOT"), ast.Call)
   and getattr(consts["APP_ROOT"].func, "id", "") == "app_root")

cwd_hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "getcwd"]
check("no os.getcwd() left anchoring Rialto's own files", cwd_hits, [])

# The filenames are allowed to appear once each, inside the anchored constant
# definitions at the top. Anywhere else means something rebuilt the path by
# hand and lost the anchoring. Found by node identity rather than by a line
# number, which went stale the first time anything above it grew.
anchored_literals = set()
for name in ("LAST_PROFILE_FILE", "LAST_SESSION_FILE"):
    node = consts.get(name)
    if node is not None:
        anchored_literals.update(id(n) for n in ast.walk(node))
bare = [n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value in ("last_session.json", "last_profile.json")
        and id(n) not in anchored_literals]
check("no bare session/profile filenames in the body", bare, [])

# os.getcwd() is not the only way to end up CWD-relative: a bare filename passed
# to os.path.join/open is resolved against the process CWD just the same. That is
# what a frozen Rialto.exe launched from a shortcut with a different "Start in"
# hits, and what an installed copy under C:\Program Files hits (not writable).
# Only inspect Rialto's OWN code - the disc menu lives in a string literal and
# legitimately resolves paths relative to wherever the disc is. Found by name
# rather than by line number, which went stale the moment the file was edited.
GENERATED_STRING_START = next(
    (n.lineno for n in tree.body
     if isinstance(n, ast.Assign)
     and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"),
    None)
ok("the disc-menu template was located in Rialto.pyw",
   GENERATED_STRING_START is not None, f"line {GENERATED_STRING_START}")
cwd_relative = []
for n in ast.walk(tree):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
            and n.func.attr == "join" and n.lineno < GENERATED_STRING_START:
        if n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str) \
                and not os.path.isabs(n.args[0].value):
            cwd_relative.append((n.lineno, ast.unparse(n)))
check("no os.path.join() anchored on a bare relative filename", cwd_relative, [])

open_relative = []
for n in ast.walk(tree):
    if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "open" \
            and n.lineno < GENERATED_STRING_START and n.args \
            and isinstance(n.args[0], ast.Constant) \
            and isinstance(n.args[0].value, str):
        open_relative.append((n.lineno, n.args[0].value))
check("no open() on a bare string literal path", open_relative, [])

# build_log.txt specifically: it is written on the SUCCESS path of build_all and
# is not wrapped in try/except, so a failed write turns a finished build into a
# reported failure. It must at least land where the rest of Rialto's files live.
log_fn = extract_func(rsrc, "log_build_event")
ok("log_build_event anchors build_log.txt to APP_ROOT",
   "APP_ROOT" in log_fn,
   [ast.unparse(n) for n in ast.walk(ast.parse(log_fn))
    if isinstance(n, ast.Assign) and "log_path" in ast.unparse(n.targets[0])][0])

# Both guides go through doc_path, which has to look where the spec actually
# puts the HTML pages - and has to copy a bundled page out of _MEIPASS before
# the browser sees it, because that folder is deleted when Rialto exits.
doc_src = extract_func(rsrc, "doc_path")
ok("doc_path checks sys._MEIPASS", "_MEIPASS" in doc_src)
ok("doc_path checks beside the exe (APP_ROOT)", "APP_ROOT" in doc_src)
ok("doc_path copies a bundled page out of the temp folder", "shutil.copy2" in doc_src)

# A frozen Rialto has no checkout behind it and no public copy of the guides to
# fall back on - a link to one would be a 404, which is worse than no button.
help_src = extract_func(rsrc, "open_help_guide")
signing_src = extract_func(rsrc, "open_signing_guide")
opener_src = extract_func(rsrc, "open_doc")
ok("Help Guide opens the HTML manual", "rialto-guide.html" in help_src)
ok("Read the Guide opens the HTML signing guide", "signing-guide.html" in signing_src)
ok("and does not send anyone to a URL instead",
   "webbrowser" not in opener_src and "http" not in opener_src)

# The confirmation before a local page is handed to the browser. The
# rule: say it is offline, say it is a browser, and ask first.
confirm_src = extract_func(rsrc, "confirm_open_offline_page")
ok("the open-in-browser prompt says browser", "browser" in confirm_src)
ok("the open-in-browser prompt says offline", "offline" in confirm_src)
ok("the open-in-browser prompt is yes/no", 'kind="yesno"' in confirm_src)
ok("open_doc asks before opening", "confirm_open_offline_page" in opener_src)
print()

# --------------------------------------------------------------------------
print("rialto.spec")
ssrc = open(SPEC, encoding="utf-8").read()
stree = ast.parse(ssrc)
ok("spec compiles", bool(compile(stree, SPEC, "exec")))

imported = {alias.name for node in ast.walk(stree)
            if isinstance(node, ast.ImportFrom) and node.module
            and "versioninfo" in node.module
            for alias in node.names}
ok("imports VSVersionInfo from PyInstaller", "VSVersionInfo" in imported,
   ", ".join(sorted(imported)))
exe_call = None
for node in ast.walk(stree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "EXE":
        exe_call = node
kwargs = {kw.arg: kw.value for kw in (exe_call.keywords if exe_call else [])}
ok("no ignored version_info= kwarg left on EXE", "version_info" not in kwargs)
ok("EXE(version=version_resource)",
   "version" in kwargs and getattr(kwargs["version"], "id", "") == "version_resource")
ok("EXE(upx=False)", "upx" in kwargs
   and isinstance(kwargs["upx"], ast.Constant) and kwargs["upx"].value is False)

# version strings
strings = {}
for node in ast.walk(stree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "StringStruct" \
            and len(node.args) == 2 and isinstance(node.args[0], ast.Constant):
        val = node.args[1]
        strings[node.args[0].value] = val.value if isinstance(val, ast.Constant) \
            else ast.unparse(val)
# Spelled the way the signing certificate spells it (CN="We The Indies, LLC"),
# so the Details tab and the Digital Signatures tab of a signed build agree.
check("CompanyName", strings.get("CompanyName"), "We The Indies, LLC")
check("ProductName", strings.get("ProductName"), "Rialto")
ok("FileVersion/ProductVersion track VERSION_STR",
   strings.get("FileVersion") == "VERSION_STR" == strings.get("ProductVersion"))
ok("LegalCopyright set", bool(strings.get("LegalCopyright")), strings.get("LegalCopyright"))

# VERSION is no longer a literal: the spec reads `__version__` out of
# Rialto.pyw (tools-dev/test_version_agreement.py pins the three together), so
# this evaluates that one assignment the way the spec does, with SPECPATH set.
version_tuple = None
for node in stree.body:
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "VERSION":
        try:
            version_tuple = ast.literal_eval(node.value)
        except ValueError:
            scope = {"SPECPATH": REPO, "os": os, "__name__": "spec_version_probe"}
            preamble = [n for n in stree.body[:stree.body.index(node) + 1]
                        if isinstance(n, (ast.Import, ast.ImportFrom, ast.With, ast.If, ast.Assign))
                        and not (isinstance(n, ast.ImportFrom) and n.module and "PyInstaller" in n.module)]
            exec(compile(ast.Module(body=preamble, type_ignores=[]), SPEC, "exec"), scope)
            version_tuple = scope.get("VERSION")
check("version tuple is 1.5.0.0", version_tuple, (1, 5, 0, 0))

datas = None
for node in ast.walk(stree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Analysis":
        for kw in node.keywords:
            if kw.arg == "datas":
                datas = [ast.literal_eval(e) for e in kw.value.elts]
ok("datas present", datas is not None, str(datas))
sources = [d[0] for d in (datas or [])]
ok("the HTML manual is bundled under docs/",
   ("docs/rialto-guide.html", "docs") in (datas or []))
ok("the HTML signing guide is bundled under docs/",
   ("docs/signing-guide.html", "docs") in (datas or []))
ok("README.md bundled at the bundle root", ("README.md", ".") in (datas or []))
ok("SIGNING.md bundled at the bundle root", ("SIGNING.md", ".") in (datas or []))
ok("assets kept", any(s.startswith("assets/") for s in sources))
ok("templates dropped", not any("templates" in s for s in sources))
for src_name, _dest in datas or []:
    ok(f"datas source exists: {src_name}",
       os.path.exists(os.path.join(REPO, src_name.replace("/", os.sep))))
print()

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print("All frozen-path and spec assertions passed.")
