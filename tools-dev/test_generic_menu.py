"""Prove the disc menu is title-agnostic and that one pre-built menu.exe serves
every disc.

Rialto used to write a menu source file with the game's title spliced in and
shell out to pyinstaller.exe once per build. A frozen Rialto cannot do that, so
the title moved into menu_config.json and the menu is now built once. Everything
below checks that move actually holds, without launching the GUI or PyQt5:

  1. nothing per-title survives in the menu source, and the title-resolution
     code is executed for real against menu_config.json files on disk
  2. the window title, the on-screen title and the taskbar identity all read
     that one value
  3. every key the menu reads out of the config is a key Rialto writes
  4. stage_menu_executable copies the pre-built exe, and falls back the way it
     claims to when there isn't one
  5. menu.spec builds something signable and unbranded

Usage: python test_generic_menu.py [path-to-rialto1.5]
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import textwrap
import types

# Titles under test include CJK and accented Latin; the default console codepage
# would raise on them before any assertion got a chance to fail honestly.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = os.path.join(REPO, "Rialto.pyw")
MENU_SPEC = os.path.join(REPO, "menu.spec")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_source import extract_menu_source  # noqa: E402

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


# --------------------------------------------------------------------------
# extraction helpers
# --------------------------------------------------------------------------
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


def module_consts(src, names):
    """Pull module-level assignments out by name.

    module_funcs only takes function bodies, so a helper that leans on a
    module constant (sanitize_text on _CONTROL_CHARS) would NameError when
    called. Extracted rather than restated here, so the test cannot drift
    away from the real table.
    """
    tree = ast.parse(src)
    out, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    out.append(ast.get_source_segment(src, node))
                    seen.add(target.id)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract module constants {sorted(missing)}")
    return "\n\n".join(out)


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


def host_from(method_src, globals_=None, **attrs):
    ns = {"os": os, "sys": sys, "shutil": shutil, "json": json}
    ns.update(globals_ or {})
    exec(f"class Host:\n{textwrap.indent(method_src, '    ')}", ns)
    host = ns["Host"]()
    host.update_status = lambda msg: None
    for k, v in attrs.items():
        setattr(host, k, v)
    return host


class Flag:
    """Stands in for a tk.StringVar / BooleanVar."""
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


RIALTO_SRC = open(RIALTO, encoding="utf-8").read()
MENU_SRC = extract_menu_source(RIALTO)
MENU_TREE = ast.parse(MENU_SRC)


# --------------------------------------------------------------------------
print("1. the menu source carries nothing per-title")
# extract_menu_source refuses a spliced template outright, so reaching here is
# already half the proof. The rest: no leftover title-shaped literals.
for banned in ("safe_title", "company.game.MockGame"):
    ok(f"no {banned!r} in the menu source", banned not in MENU_SRC)

title_reads = [ast.unparse(n) for n in ast.walk(MENU_TREE)
               if isinstance(n, ast.Call) and ast.unparse(n).startswith("self.setWindowTitle")]
check("setWindowTitle reads the config-driven title", title_reads,
      ["self.setWindowTitle(self.menu_title)"])

labels = sorted({ast.unparse(n.args[0]) for n in ast.walk(MENU_TREE)
                 if isinstance(n, ast.Call)
                 and ast.unparse(n.func) == "QtWidgets.QLabel"
                 and n.args
                 and "menu_title" in ast.unparse(n.args[0])})
check("both on-screen title labels read it too", labels, ["self.menu_title.upper()"])

appid = [ast.unparse(n.value) for n in ast.walk(MENU_TREE)
         if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "myappid"]
ok("the taskbar AppUserModelID is derived from it at runtime",
   appid and "MENU_TITLE" in appid[0], str(appid))
print()


# --------------------------------------------------------------------------
print("2. title resolution, executed against real menu_config.json files")
def startup_block(src):
    """Everything the menu runs at import to work out MENU_CONFIG and MENU_TITLE.

    Taken verbatim from the module body up to and including the MENU_TITLE
    assignment, minus the imports and the ctypes/AppUserModelID try block, so
    what runs below is the real startup code and not a paraphrase of it.
    """
    out = []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Try)):
            continue
        out.append(ast.get_source_segment(src, node))
        if isinstance(node, ast.Assign) \
                and getattr(node.targets[0], "id", "") == "MENU_TITLE":
            return "\n\n".join(out)
    raise SystemExit("MENU_TITLE is not computed at module level any more")


startup = startup_block(MENU_SRC)
ok("MENU_TITLE is computed at import from the config",
   "MENU_TITLE" in startup and "load_menu_config" in startup,
   f"{len(startup.splitlines())} lines of real startup code")


def resolve_title(config, frozen):
    """Run the menu's own startup code in a temp folder and report the title."""
    stage = tempfile.mkdtemp(prefix="rialto_title_")
    try:
        if config is not None:
            with open(os.path.join(stage, "menu_config.json"), "w", encoding="utf-8") as f:
                f.write(config if isinstance(config, str) else json.dumps(config))
        fake_sys = types.SimpleNamespace(executable=os.path.join(stage, "menu.exe"))
        if frozen:
            fake_sys.frozen = True
        ns = {"os": os, "json": json, "sys": fake_sys,
              "__file__": os.path.join(stage, "menu_launcher.py")}
        exec(startup, ns)
        return ns["MENU_TITLE"], ns["MENU_CONFIG"]
    finally:
        shutil.rmtree(stage, ignore_errors=True)


for mode in (False, True):
    tag = "frozen" if mode else "source"
    check(f"[{tag}] plain title", resolve_title({"title": "Bloodwake"}, mode)[0], "Bloodwake")
    check(f"[{tag}] no config at all", resolve_title(None, mode)[0], "Game")
    check(f"[{tag}] config without a title", resolve_title({"games": []}, mode)[0], "Game")
    check(f"[{tag}] empty title", resolve_title({"title": ""}, mode)[0], "Game")
    check(f"[{tag}] title that is only spaces", resolve_title({"title": "   "}, mode)[0], "Game")
    # These are exactly the characters the old spliced-source approach had to
    # escape by hand before writing them into a .pyw. Nothing is escaped now,
    # because nothing is compiled: they go through JSON and come out unchanged.
    tricky = 'Marlow\'s \\Escape\\ "Redux"'
    check(f"[{tag}] apostrophes, backslashes and quotes survive intact",
          resolve_title({"title": tricky}, mode)[0], tricky)
    check(f"[{tag}] non-ASCII survives intact",
          resolve_title({"title": "东方 Café — Ölandsvägen"}, mode)[0],
          "东方 Café — Ölandsvägen")
    check(f"[{tag}] newlines flattened, not left to break a window caption",
          resolve_title({"title": "Two\nLine\rTitle"}, mode)[0], "Two Line Title")
    check(f"[{tag}] corrupt config falls back rather than crashing",
          resolve_title("{not json at all", mode)[0], "Game")
    check(f"[{tag}] a JSON list where a dict was expected", resolve_title("[1,2,3]", mode)[0], "Game")
    check(f"[{tag}] non-string title", resolve_title({"title": 1995}, mode)[0], "1995")
print()


# --------------------------------------------------------------------------
print("3. every key the menu reads is a key Rialto writes")
config_reads = set()
for n in ast.walk(MENU_TREE):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
            and n.func.attr == "get" \
            and ast.unparse(n.func.value).endswith(("menu_config", "MENU_CONFIG")) \
            and n.args and isinstance(n.args[0], ast.Constant):
        config_reads.add(n.args[0].value)

written = None
for node in ast.walk(ast.parse(RIALTO_SRC)):
    if isinstance(node, ast.FunctionDef) and node.name == "build_menu_config":
        for sub in ast.walk(node):
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                written = {k.value for k in sub.value.keys if isinstance(k, ast.Constant)}
ok("build_menu_config returns a dict literal", written is not None, str(sorted(written or [])))
print(f"       menu reads:  {sorted(config_reads)}")
print(f"       Rialto writes: {sorted(written or [])}")
check("no key the menu reads is missing from the config Rialto writes",
      sorted(config_reads - (written or set())), [])
for required in ("title", "games", "mod_launcher", "mod_exe", "remove_wti_branding",
                 "steam_button", "company_logo", "copyright_text", "language"):
    ok(f"config carries {required!r}", required in (written or set()))
print()


# --------------------------------------------------------------------------
print("4. build_menu_config and the staging of menu.exe")
# strip_wti_mentions is a module function build_menu_config calls, so the host
# needs the real one rather than a stand-in.
_wti_ns = {"re": __import__("re")}
exec(module_consts(RIALTO_SRC, ["_CONTROL_CHARS"]), _wti_ns)
exec(module_funcs(RIALTO_SRC, ["strip_wti_mentions", "sanitize_text", "split_launch_args"]),
     _wti_ns)

cfg_host = host_from(
    methods(RIALTO_SRC, "RialtoApp", ["build_menu_config", "write_menu_config"]),
    {"strip_wti_mentions": _wti_ns["strip_wti_mentions"],
     "sanitize_text": _wti_ns["sanitize_text"],
     "split_launch_args": _wti_ns["split_launch_args"]},
    entries={"Title": Flag("  Marlow's Escape  ")},
    company_logo_var=Flag(""),
    publisher_text_var=Flag("(c) 2026 Mock Studio"),
    remove_wti_branding=Flag(True),
    steam_button_var=Flag(True),
    mod_launcher_var=Flag(False),
    compat_mode_var=Flag(False),
    compat_args_var=Flag(""),
    compat_label_var=Flag(""),
    compat_hint_var=Flag(""),
)
cfg_host.validated_game_executables = lambda: [{"name": "Marlow", "exe": "game.exe"}]
cfg_host.detect_primary_game_exe = lambda root: "game.exe"
built = cfg_host.build_menu_config("C:\\nowhere")
check("the title is trimmed but otherwise untouched", built["title"], "Marlow's Escape")
check("white-label flag rides in the config", built["remove_wti_branding"], True)
check("mod_exe stays empty when the mod launcher is off", built["mod_exe"], "")
check("compatibility mode is off unless the author turned it on", built["compat_mode"], False)
check("and carries no arguments while it is off", built["compat_args"], [])
check("the auto-detected game exe rides in the config too", built["game_exe"], "game.exe")

# White label has to reach the copyright line, not only the artwork. An author
# who typed "Distributed by We the Indies." into the box, or loaded a profile
# carrying it, was still shipping it across the bottom of an unbranded disc.
cfg_host.publisher_text_var = Flag(
    "Published by Mock Publishing. Developed by Jane Smith 2026. "
    "All rights reserved.\nDistributed by We the Indies.")
check("white label strips We the Indies out of the copyright line",
      cfg_host.build_menu_config("C:\\nowhere")["copyright_text"],
      "Published by Mock Publishing. Developed by Jane Smith 2026. All rights reserved.")

cfg_host.remove_wti_branding = Flag(False)
check("and leaves it alone when the disc is not white-labelled",
      "We the Indies" in cfg_host.build_menu_config("C:\\nowhere")["copyright_text"], True)
cfg_host.remove_wti_branding = Flag(True)
cfg_host.publisher_text_var = Flag("(c) 2026 Mock Studio")

cfg_host.entries = {"Title": Flag("")}
check("a blank title falls back to Game", cfg_host.build_menu_config("C:\\nowhere")["title"], "Game")

stage_src = methods(RIALTO_SRC, "RialtoApp", ["stage_menu_executable"])
helper_src = module_funcs(RIALTO_SRC, ["prebuilt_menu_exe", "write_menu_source"])


PREBUILT_BYTES = b"MZ pre-built generic menu"


class DiskFillsUp:
    """shutil, except copy2 runs out of room part-way - what ENOSPC does.

    menu.exe is 40 MB and lands on whatever drive the author pointed output/ at,
    so this is the everyday failure: a full disc, or an external drive pulled
    out mid-build.
    """
    @staticmethod
    def copy2(src, dst, *args, **kwargs):
        blob = open(src, "rb").read()
        with open(dst, "wb") as f:
            f.write(blob[:len(blob) // 3])
        raise OSError(28, "No space left on device")


def run_stage(with_prebuilt, compiler_works=False, disk_fills_up=False):
    """Run the real stage_menu_executable against a temp output folder."""
    base = tempfile.mkdtemp(prefix="rialto_stage_")
    app_root = os.path.join(base, "app")
    output = os.path.join(base, "output")
    os.makedirs(app_root)
    os.makedirs(output)
    if with_prebuilt:
        with open(os.path.join(app_root, "menu.exe"), "wb") as f:
            f.write(PREBUILT_BYTES)

    helpers = {"os": os, "sys": sys, "APP_ROOT": app_root,
               "MENU_TEMPLATE_SOURCE": "# the real disc menu source\n"}
    exec(helper_src, helpers)

    host = host_from(stage_src, globals_={
        "prebuilt_menu_exe": helpers["prebuilt_menu_exe"],
        "write_menu_source": helpers["write_menu_source"],
        **({"shutil": DiskFillsUp} if disk_fills_up else {}),
    })
    log = []
    host.update_status = log.append
    host.copy_vcruntime_dlls = lambda d: log.append(f"vcruntime -> {d}")
    # BYOK signing of the staged copy has its own harness
    # (test_staged_menu_signing.py); here it only has to not get in the way.
    host.sign_staged_menu_exe = lambda menu_dir: log.append(f"sign -> {menu_dir}")

    def fake_compile(output_path):
        if not compiler_works:
            return False
        with open(os.path.join(output_path, "menu", "menu.exe"), "wb") as f:
            f.write(b"MZ compiled here")
        os.remove(os.path.join(output_path, "menu", "menu_launcher.pyw"))
        return True

    host.compile_pyqt5_menu = fake_compile
    result = host.stage_menu_executable(output)
    menu_dir = os.path.join(output, "menu")
    staged = sorted(os.listdir(menu_dir))
    body = open(os.path.join(menu_dir, "menu.exe"), "rb").read() \
        if os.path.exists(os.path.join(menu_dir, "menu.exe")) else None
    shutil.rmtree(base, ignore_errors=True)
    return result, staged, body, log


got, staged, body, log = run_stage(with_prebuilt=True)
check("pre-built exe present -> staged", got, True)
check("it is copied byte-for-byte, not rebuilt", body, PREBUILT_BYTES)
check("and no menu source goes near the disc", staged, ["menu.exe"])
ok("the runtime DLLs still land beside it", any("vcruntime" in m for m in log), str(log))

# A half-copied menu.exe must never reach the disc. Nothing downstream
# re-checks it: the installer's shortcuts and its post-install Run entry all
# point at {app}\menu\menu.exe, so a fragment left under the real name is a
# corrupt executable in the player's Start menu, and the batch menu that exists
# to cover this never gets a look in.
got, staged, body, log = run_stage(with_prebuilt=True, disk_fills_up=True)
check("the drive fills up mid-copy -> staging reports failure", got, False)
check("no truncated menu.exe is left under the real name", body, None)
check("and no scratch file is left on the disc either", staged, [])
# "Not found" and "found it, could not copy it" send an author looking in
# completely different places, so the log has to tell them apart.
ok("the log names the exe it found and why the copy failed",
   any("menu.exe" in m and "could not copy it" in m and "No space left" in m
       for m in log), str(log))
ok("and does not claim there was no pre-built menu.exe",
   not any("No pre-built menu.exe found" in m for m in log), str(log))
ok("it still says what happens next", any("Falling back" in m for m in log), str(log))

got, staged, body, log = run_stage(with_prebuilt=False, compiler_works=True)
check("no pre-built exe, PyInstaller available -> compiled fallback", got, True)
check("the compiled exe is staged", body, b"MZ compiled here")
check("still no source left on the disc", staged, ["menu.exe"])

got, staged, body, log = run_stage(with_prebuilt=False, compiler_works=False)
check("neither -> falls through to the batch menu", got, False)
check("and the half-written source is cleaned up, not shipped", staged, [])
print()


# --------------------------------------------------------------------------
print("5. menu.spec")
spec_src = open(MENU_SPEC, encoding="utf-8").read()
spec_tree = ast.parse(spec_src)
ok("menu.spec compiles", bool(compile(spec_tree, MENU_SPEC, "exec")))

spec_strings = {}
for node in ast.walk(spec_tree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "StringStruct" \
            and len(node.args) == 2 and isinstance(node.args[0], ast.Constant):
        val = node.args[1]
        spec_strings[node.args[0].value] = val.value if isinstance(val, ast.Constant) \
            else ast.unparse(val)
check("OriginalFilename", spec_strings.get("OriginalFilename"), "menu.exe")
# One exe ships on branded and white-labelled discs alike, and its metadata
# cannot vary per build without breaking the signature. So it names nobody.
ok("no CompanyName (white-labelled discs get this same file)",
   "CompanyName" not in spec_strings)
ok("no LegalCopyright either", "LegalCopyright" not in spec_strings)
ok("FileDescription set for the properties dialog",
   bool(spec_strings.get("FileDescription")), spec_strings.get("FileDescription"))

exe_call = None
for node in ast.walk(spec_tree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "EXE":
        exe_call = node
kwargs = {kw.arg: kw.value for kw in (exe_call.keywords if exe_call else [])}
check("built windowed, no console flash",
      isinstance(kwargs.get("console"), ast.Constant) and kwargs["console"].value, False)
check("named menu, so it stages as menu.exe",
      isinstance(kwargs.get("name"), ast.Constant) and kwargs["name"].value, "menu")
ok("upx off, same as Rialto.exe",
   isinstance(kwargs.get("upx"), ast.Constant) and kwargs["upx"].value is False)
ok("carries a version resource", "version" in kwargs)
ok("the neutral icon exists", os.path.isfile(os.path.join(REPO, "assets", "menu_icon.ico")))

# PyInstaller 6 raises on these the moment they are truthy; they must be gone
# from both specs, not merely set to a falsy value.
for spec_path in (MENU_SPEC, os.path.join(REPO, "rialto.spec")):
    tree = ast.parse(open(spec_path, encoding="utf-8").read())
    passed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("Analysis", "PYZ"):
            passed.update(kw.arg for kw in node.keywords)
    dead = passed & {"cipher", "win_no_prefer_redirects", "win_private_assemblies"}
    check(f"{os.path.basename(spec_path)}: no PyInstaller-6-removed kwargs", sorted(dead), [])
    legacy_toc = [ast.unparse(a) for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("PYZ", "EXE")
                  for a in node.args
                  if ast.unparse(a) in ("a.zipfiles", "a.zipped_data")]
    check(f"{os.path.basename(spec_path)}: no dead zipped-egg TOCs", legacy_toc, [])
print()

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print("All generic-menu assertions passed.")
