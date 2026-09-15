"""Simulate build_all's staging sequence on a temp tree and say exactly where
bonus/ (and mods/) end up: installer payload, disc root, menu-findable.

Nothing here is mocked away that matters: the real methods are pulled out of
Rialto.pyw by AST extraction and exec'd on a stub host, and the Inno [Files]
Source/Excludes line is read out of the real generator source, so the sweep we
simulate is the one ISCC would actually perform.

Order replicated (build_all in Rialto.pyw):
    step 2    copy_game_files_to_output
    step 3.5  stage_mod_launcher
    step 6    ISCC  -> snapshot the {app} payload from the Excludes sweep
    step 3.6  build_bonus_gallery
    step 10   create_iso -> _collect_disc_fileset

Scenario E does the same for the third place the menu can run from: the
preview. The real preview_disc_menu is executed with PyQt5, the menu compiler
and subprocess stubbed out, so the folder it stages is inspected without ever
opening a window.

Usage: python test_bonus_staging.py [path-to-Rialto.pyw]
"""
import ast
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

# What Preview names its staging folders. Asserted against Rialto.pyw's own
# constant below, because the sweep only finds what the staging created.
PREVIEW_PREFIX = "rialto_preview_"

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------
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


def make_host(method_src, extra_globals=None, **attrs):
    ns = {"os": os, "sys": sys, "shutil": shutil, "glob": __import__("glob")}
    ns.update(extra_globals or {})
    exec(f"class Host:\n{textwrap.indent(method_src, '    ')}", ns)
    host = ns["Host"]()
    for k, v in attrs.items():
        setattr(host, k, v)
    host.update_status = lambda msg: None
    return host


class Flag:
    """Stands in for a tk.BooleanVar."""
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


def inno_files_line(src):
    """The 'Source: "*" ... Excludes: "..."' line the generator writes.

    The Excludes list stopped being one string constant when the
    in-root save patterns landed: the generator now writes a literal
    prefix, appends one `,pattern` per entry of `in_root_saves`, and
    closes the quote. So the constant this finds ends mid-list, and
    reading it alone used to crash `parse_excludes` looking for a
    closing quote that is added at runtime.

    Rebuilt here the way the generator builds it, from the same source
    of truth, so an engine added to `in_root_saves` shows up in the
    sweep instead of silently making this harness wrong.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_enhanced_installer_script":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                        and sub.value.startswith('Source: "*"'):
                    line = sub.value
                    if line.count('"') % 2:  # Excludes list left open
                        saves = "".join(f",{p}" for p, _dest in in_root_save_patterns(src))
                        line += saves + '"'
                    return line
    raise SystemExit("no `Source: \"*\"` line found in generate_enhanced_installer_script")


def in_root_save_patterns(src):
    """`in_root_saves` as the generator declares it: [(pattern, dest), ...].

    Player data that lives inside the install root, which the wildcard
    must NOT sweep up (a reinstall would overwrite the save) and which
    gets its own `onlyifdoesntexist uninsneveruninstall` entry instead.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_enhanced_installer_script":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) \
                        and getattr(sub.targets[0], "id", "") == "in_root_saves":
                    return ast.literal_eval(sub.value)
    raise SystemExit("`in_root_saves` not found in generate_enhanced_installer_script")


def module_constant(src, name):
    """The value of a module-level string constant in Rialto.pyw."""
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise SystemExit(f"module constant {name!r} not found")


def class_constant(src, class_name, name):
    """The value of a literal class attribute on RialtoApp, read from source."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if isinstance(sub, ast.Assign) and getattr(sub.targets[0], "id", "") == name:
                    return ast.literal_eval(sub.value)
    raise SystemExit(f"class constant {class_name}.{name!r} not found")


def parse_excludes(line):
    marker = 'Excludes: "'
    i = line.index(marker) + len(marker)
    return [p.strip() for p in line[i:line.index('"', i)].split(",") if p.strip()]


def inno_sweep(source_dir, excludes):
    """Effective file set of `Source: "*"; recursesubdirs; Excludes: ...`.

    Inno matches each Excludes pattern against the item name at every level and
    against the path relative to the source root; a matched directory drops its
    whole subtree. Wildcard-free entries match names literally.
    """
    def excluded(name):
        return any(fnmatch.fnmatch(name.lower(), pat.lower()) for pat in excludes)

    payload = []

    def walk(rel):
        base = os.path.join(source_dir, rel) if rel else source_dir
        for name in sorted(os.listdir(base)):
            if excluded(name):
                continue
            child_rel = f"{rel}/{name}" if rel else name
            full = os.path.join(base, name)
            if os.path.isdir(full):
                walk(child_rel)
            else:
                payload.append(child_rel)

    walk("")
    return payload


def junctions_allowed():
    """True where mklink /J works; some locked-down machines refuse it."""
    probe = tempfile.mkdtemp(prefix="rialto_jprobe_")
    link = os.path.join(probe, "link")
    target = os.path.join(probe, "target")
    os.makedirs(target)
    try:
        made = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                              capture_output=True).returncode == 0
        return made and os.path.isdir(link)
    finally:
        try:
            os.rmdir(link)
        except OSError:
            pass
        shutil.rmtree(probe, ignore_errors=True)


def menu_finds(root, folder):
    """The generated menu's own check: game_dir/<folder> in three casings.

    game_dir = dirname(dirname(menu exe)) i.e. the install root / disc root
    (the menu source in Rialto.pyw), so `root` here is that directory.
    """
    for name in (folder, folder.upper(), folder.capitalize()):
        p = os.path.join(root, name)
        if os.path.exists(p) and os.path.isdir(p):
            return True
    return False


# --------------------------------------------------------------------------
# fixture
# --------------------------------------------------------------------------
def make_input_tree(base, with_bonus=True, with_mods=True):
    game = os.path.join(base, "input", "MockGame")
    os.makedirs(game, exist_ok=True)
    for rel in ("MockGame.exe", "game_logo.png", "data/assets.pak"):
        p = os.path.join(game, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write("x")
    if with_bonus:
        for rel in ("bonus/artbook.pdf", "bonus/ost/track01.mp3"):
            p = os.path.join(game, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write("x")
    if with_mods:
        p = os.path.join(game, "mods", "ModLauncher.exe")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write("x")
    return game


def run_pipeline(base, src, mod_launcher=True, with_bonus=True, with_mods=True):
    """Returns (output_path, installer_payload, disc_fileset)."""
    game_path = make_input_tree(base, with_bonus, with_mods)
    output_path = os.path.join(base, "output", "MockGame")
    os.makedirs(output_path, exist_ok=True)

    methods = extract_methods(src, "RialtoApp", [
        "copy_game_files_to_output",
        "build_bonus_gallery",
        "stage_mod_launcher",
        "_collect_disc_fileset",
        "default_mod_dir", "resolved_mod_dir", "staged_mod_dir_name",
    ])
    host = make_host(methods, mod_launcher_var=Flag(mod_launcher),
                     mod_folder_var=Flag(""), current_game_path=game_path)

    # step 2
    host.copy_game_files_to_output(game_path, output_path)
    # step 3.5
    host.stage_mod_launcher(game_path, output_path)
    # step 3.6
    host.build_bonus_gallery(game_path, output_path)
    # step 5/6: the installer script lands in the output folder, then ISCC runs
    # with that folder as SourceDir and consumes it.
    open(os.path.join(output_path, "installer.iss"), "w").write("; generated")
    payload = inno_sweep(output_path, parse_excludes(inno_files_line(src)))
    # ISCC's product
    open(os.path.join(output_path, "setup.exe"), "w").write("MZ")
    # a couple of files later steps drop in that the disc whitelist names
    for name in ("autorun.inf", "README.txt", "game_icon.ico"):
        open(os.path.join(output_path, name), "w").write("x")
    os.makedirs(os.path.join(output_path, "menu"), exist_ok=True)
    open(os.path.join(output_path, "menu", "menu.exe"), "w").write("MZ")
    # step 10
    disc = host._collect_disc_fileset(output_path)
    return output_path, payload, disc


def materialise_disc(output_path, disc_items, dest):
    """What create_iso hands mkisofs/oscdimg: only the whitelisted items."""
    os.makedirs(dest, exist_ok=True)
    for item in disc_items:
        src = os.path.join(output_path, item)
        dst = os.path.join(dest, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.exists(src):
            shutil.copy2(src, dst)
    return dest


def materialise_install(payload, dest):
    """What Inno unpacks into {app}."""
    for rel in payload:
        p = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write("x")
    return dest


def extract_module_funcs(src, names):
    """Return exec'able source for module-level functions of Rialto.pyw.

    Assignments come too, because sanitize_text leans on the _CONTROL_CHARS
    table. Extracted rather than restated here, so the two cannot drift.
    """
    tree = ast.parse(src)
    out, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            seen.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    out.append(ast.get_source_segment(src, node))
                    seen.add(target.id)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract module functions {sorted(missing)}")
    return "\n\n".join(out)


def run_preview(base, src, with_bonus=True, with_mods=True, mod_launcher=True,
                prebuilt=False):
    """Run the real preview_disc_menu with everything visual stubbed out.

    Returns (preview_root, status_log, popen_calls). No window is ever opened:
    Popen only records the argv it was handed.

    `prebuilt` picks which of the two real paths runs - the shipping one, where
    a pre-built generic menu.exe is copied in and launched, or the source-checkout
    fallback that writes menu_launcher.pyw and runs it under python. Both are
    driven through the REAL prebuilt_menu_exe(), with APP_ROOT pointed at a temp
    folder, so the lookup order is exercised rather than mocked.
    """
    game_path = make_input_tree(base, with_bonus, with_mods)
    popen_calls = []

    class FakePopen:
        def __init__(self, argv, cwd=None, env=None):
            popen_calls.append((list(argv), cwd, dict(env or {})))

    # preview_disc_menu imports PyQt5 only to check it is installed.
    sys.modules.setdefault("PyQt5", types.ModuleType("PyQt5"))

    # A stand-in Rialto install folder, so prebuilt_menu_exe() looks somewhere
    # we control instead of at the real repo.
    app_root = os.path.join(base, "_app")
    os.makedirs(app_root, exist_ok=True)
    if prebuilt:
        with open(os.path.join(app_root, "menu.exe"), "wb") as f:
            f.write(b"MZ pre-built generic menu")

    helper_ns = {"os": os, "sys": sys, "shutil": shutil, "subprocess": subprocess,
                 "tempfile": tempfile, "time": time,
                 "PREVIEW_PREFIX": PREVIEW_PREFIX, "_STARTED_AT": 0.0,
                 "APP_ROOT": app_root,
                 "MENU_TEMPLATE_SOURCE": "# the real disc menu source\n"}
    exec(extract_module_funcs(
        src, ["prebuilt_menu_exe", "write_menu_source", "link_or_copy_tree",
              "remove_preview_dir", "sweep_stale_previews", "sanitize_text",
              "split_launch_args", "_CONTROL_CHARS"]),
        helper_ns)

    # The sweep is exercised for real further down, against a sandbox. Here it
    # only has to be called - pointing the real one at the machine's %TEMP%
    # during a test run would delete previews this harness knows nothing about.
    swept = []
    registered = []

    methods = extract_methods(src, "RialtoApp",
                              ["preview_disc_menu", "detect_mod_launcher_exe",
                               "build_menu_config", "write_menu_config",
                               "default_bonus_dir", "resolved_bonus_dir",
                               "default_mod_dir", "resolved_mod_dir",
                               "staged_mod_dir_name",
                               "detect_primary_game_exe"])
    host = make_host(
        methods,
        extra_globals={
            "json": json,
            "tempfile": tempfile,
            "atexit": types.SimpleNamespace(
                register=lambda fn, *a: registered.append((fn.__name__, a))),
            "subprocess": types.SimpleNamespace(Popen=FakePopen),
            "prebuilt_menu_exe": helper_ns["prebuilt_menu_exe"],
            "write_menu_source": helper_ns["write_menu_source"],
            "link_or_copy_tree": helper_ns["link_or_copy_tree"],
            "remove_preview_dir": helper_ns["remove_preview_dir"],
            "sweep_stale_previews": lambda *a, **k: (swept.append(True), 0)[1],
            "PREVIEW_PREFIX": PREVIEW_PREFIX,
            "sanitize_text": helper_ns["sanitize_text"],
            "split_launch_args": helper_ns["split_launch_args"],
        },
        current_game_path=game_path,
        mod_launcher_var=Flag(mod_launcher),
        mod_folder_var=Flag(""),
        compat_mode_var=Flag(False),
        compat_args_var=Flag(""),
        compat_label_var=Flag(""),
        compat_hint_var=Flag(""),
        company_logo_var=Flag(""),
        publisher_text_var=Flag("(c) Mock Studio"),
        remove_wti_branding=Flag(False),
        steam_button_var=Flag(False),
        ico_path_var=Flag(""),
        # Empty = "use <game>/bonus if it is there", the path every disc built
        # before Disc Extras grew a bonus picker takes.
        bonus_folder_var=Flag(""),
        entries={"Title": Flag("Mock Game")},
        # Class attributes detect_primary_game_exe reads, taken from the real
        # source rather than restated here, so a change to either list is
        # exercised instead of shadowed.
        HELPER_EXE_NAMES=class_constant(src, "RialtoApp", "HELPER_EXE_NAMES"),
        NON_GAME_DIRS=class_constant(src, "RialtoApp", "NON_GAME_DIRS"),
    )
    log = []
    host.update_status = log.append
    host.show_centered_popup = lambda *a, **k: log.append(f"POPUP {a}")
    host.validated_game_executables = lambda: []

    seen = {}

    def fake_artwork(menu_dir):
        """Stands in for stage_menu_artwork, which only copies image files.
        Its folder is how we find the temp preview root."""
        seen["menu_dir"] = menu_dir

    host.stage_menu_artwork = fake_artwork
    host.preview_disc_menu()
    menu_dir = seen.get("menu_dir")
    root = os.path.dirname(menu_dir) if menu_dir else None
    return root, log, popen_calls, {"swept": bool(swept), "registered": registered}


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------
def main():
    src = open(RIALTO, encoding="utf-8").read()

    line = inno_files_line(src)
    excludes = parse_excludes(line)
    print("Inno [Files] sweep")
    print(f"  Source line: {line.strip()}")
    print(f"  Excludes:    {excludes}")
    check("'bonus' is NOT excluded by Inno", "bonus" in excludes, False)
    check("the sweep looks for the prefix Preview actually stages under",
          module_constant(src, "PREVIEW_PREFIX"), PREVIEW_PREFIX)
    print()

    base = tempfile.mkdtemp(prefix="rialto_bonus_")
    try:
        # --- scenario A: bonus + mods present, mod launcher on -------------
        root = os.path.join(base, "A")
        os.makedirs(root)
        out, payload, disc = run_pipeline(root, src, mod_launcher=True)

        print("Scenario A - bonus/ and mods/ present, Mod Launcher ON")
        print(f"  installer payload ({len(payload)}): {payload}")
        print(f"  disc fileset:      {disc}")
        print()

        bonus_in_payload = any(p.startswith("bonus/") for p in payload)
        mods_in_payload = any(p.startswith("mods/") for p in payload)
        check("bonus reaches the installer payload ({app})", bonus_in_payload, True)
        check("mods reaches the installer payload ({app})", mods_in_payload, True)
        check("bonus reaches the disc root (ISO whitelist)", "bonus" in disc, True)
        check("mods reaches the disc root (ISO whitelist)", "mods" in disc, True)

        installed = materialise_install(payload, os.path.join(root, "installed"))
        discroot = materialise_disc(out, disc, os.path.join(root, "discroot"))
        check("menu finds bonus in the INSTALLED copy", menu_finds(installed, "bonus"), True)
        check("menu finds bonus at the DISC root", menu_finds(discroot, "bonus"), True)
        check("menu finds mods in the INSTALLED copy", menu_finds(installed, "mods"), True)
        check("menu finds mods at the DISC root", menu_finds(discroot, "mods"), True)
        print()

        # --- scenario B: no bonus folder at all ----------------------------
        root = os.path.join(base, "B")
        os.makedirs(root)
        out, payload, disc = run_pipeline(root, src, mod_launcher=False,
                                          with_bonus=False, with_mods=False)
        print("Scenario B - no bonus/, no mods/, Mod Launcher OFF")
        check("no phantom bonus entry on the disc", "bonus" in disc, False)
        check("no phantom mods entry on the disc", "mods" in disc, False)
        check("setup.exe still on the disc", "setup.exe" in disc, True)
        check("menu folder still on the disc", "menu" in disc, True)
        print()

        # --- scenario C: bonus present, mod launcher off -------------------
        root = os.path.join(base, "C")
        os.makedirs(root)
        out, payload, disc = run_pipeline(root, src, mod_launcher=False,
                                          with_bonus=True, with_mods=True)
        print("Scenario C - bonus/ present, mods/ present but Mod Launcher OFF")
        check("bonus still reaches the disc", "bonus" in disc, True)
        check("mods stays off the disc when the option is off", "mods" in disc, False)
        check("bonus still in the installer payload",
              any(p.startswith("bonus/") for p in payload), True)
        print()

        # --- scenario D: build_bonus_gallery is a re-copy, not the source ---
        # Prove step 2 alone already puts bonus in the payload: run the sweep
        # with build_bonus_gallery never called.
        root = os.path.join(base, "D")
        os.makedirs(root)
        game_path = make_input_tree(root)
        output_path = os.path.join(root, "output", "MockGame")
        os.makedirs(output_path)
        host = make_host(extract_methods(src, "RialtoApp", ["copy_game_files_to_output"]),
                         mod_launcher_var=Flag(False))
        host.copy_game_files_to_output(game_path, output_path)
        payload = inno_sweep(output_path, excludes)
        print("Scenario D - step 2 only, build_bonus_gallery never called")
        check("copy_game_files_to_output alone puts bonus in {app}",
              any(p.startswith("bonus/") for p in payload), True)
        check("copy_game_files_to_output alone puts mods in {app}",
              any(p.startswith("mods/") for p in payload), True)
        print()

        # --- scenario E: the preview stages the same folders ---------------
        # Third place the menu runs from, after the disc root and {app}: the
        # temp folder Preview Disc Menu builds. Same three-casing lookup.
        root = os.path.join(base, "E")
        os.makedirs(root)
        preview_root, log, popen_calls, cleanup = run_preview(root, src)
        print("Scenario E - Preview Disc Menu, bonus/ and mods/ present")
        print(f"  preview root: {sorted(os.listdir(preview_root))}")
        check("preview stages bonus/ next to menu/",
              os.path.isdir(os.path.join(preview_root, "bonus")), True)
        check("preview stages mods/ next to menu/",
              os.path.isdir(os.path.join(preview_root, "mods")), True)
        check("the bonus files came too, not just the folder",
              os.path.exists(os.path.join(preview_root, "bonus", "ost", "track01.mp3")), True)
        check("menu finds bonus in the PREVIEW root", menu_finds(preview_root, "bonus"), True)
        check("menu finds mods in the PREVIEW root", menu_finds(preview_root, "mods"), True)
        launcher = popen_calls[0][0][-1]
        game_dir = os.path.dirname(os.path.dirname(os.path.abspath(launcher)))
        check("the menu's own game_dir IS the folder we staged into",
              os.path.normcase(game_dir), os.path.normcase(preview_root))
        check("the launcher runs in preview mode",
              popen_calls[0][2].get("RIALTO_PREVIEW"), "1")
        check("no pre-built menu.exe -> the source launcher is run",
              os.path.basename(launcher), "menu_launcher.pyw")

        # Staged by junction, not by copy: a bonus folder is routinely gigabytes
        # and the preview only reads it. What matters afterwards is that tearing
        # the preview down cannot reach through the junction and delete the
        # author's originals.
        staged_bonus = os.path.join(preview_root, "bonus")
        reparse = subprocess.run(["cmd", "/c", "dir", "/AL", preview_root],
                                 capture_output=True, text=True).stdout
        if junctions_allowed():
            check("bonus/ is staged as a junction, not copied",
                  "<JUNCTION>" in reparse and "bonus" in reparse, True)
        else:
            print("  [SKIP] junction staging (mklink /J refused here; the preview copies instead)")
        source_track = os.path.join(root, "input", "MockGame", "bonus", "ost", "track01.mp3")
        check("the source file is there to begin with", os.path.exists(source_track), True)
        shutil.rmtree(preview_root, ignore_errors=True)
        check("tearing down the preview leaves the author's bonus files alone",
              os.path.exists(source_track), True)
        check("and the staged folder is gone", os.path.exists(staged_bonus), False)

        # Nothing else was ever going to remove that folder, so Preview clears
        # the previous runs' before staging another and books this one for the
        # way out.
        check("Preview sweeps earlier runs' leftovers first", cleanup["swept"], True)
        check("and registers this preview folder for cleanup on exit",
              [(fn, os.path.normcase(a[0])) for fn, a in cleanup["registered"]],
              [("remove_preview_dir", os.path.normcase(preview_root))])
        print()

        # --- scenario F: preview of a game with no extras ------------------
        root = os.path.join(base, "F")
        os.makedirs(root)
        preview_root, log, popen_calls, cleanup = run_preview(root, src, with_bonus=False,
                                                              with_mods=False)
        print("Scenario F - Preview Disc Menu, no bonus/ and no mods/")
        check("no bonus folder means nothing staged",
              os.path.exists(os.path.join(preview_root, "bonus")), False)
        check("preview would hide BONUS CONTENT, like the disc does",
              menu_finds(preview_root, "bonus"), False)
        check("preview still launched", len(popen_calls), 1)
        shutil.rmtree(preview_root, ignore_errors=True)
        print()

        # --- scenario G: the shipping preview path -------------------------
        # With a pre-built menu.exe beside Rialto, the preview runs that exe -
        # the very file the disc gets - instead of shelling out to python. This
        # is the only path a frozen Rialto has, since it has no python.exe to
        # hand and no PyQt5 importable.
        root = os.path.join(base, "G")
        os.makedirs(root)
        preview_root, log, popen_calls, cleanup = run_preview(root, src, prebuilt=True)
        print("Scenario G - Preview Disc Menu with a pre-built menu.exe")
        argv = popen_calls[0][0]
        check("the preview runs menu.exe directly, not python", len(argv), 1)
        check("and it is the staged copy inside menu/",
              os.path.normcase(argv[0]),
              os.path.normcase(os.path.join(preview_root, "menu", "menu.exe")))
        check("menu.exe really was copied in",
              os.path.isfile(os.path.join(preview_root, "menu", "menu.exe")), True)
        check("no menu source left beside it",
              os.path.exists(os.path.join(preview_root, "menu", "menu_launcher.pyw")), False)
        check("still preview mode", popen_calls[0][2].get("RIALTO_PREVIEW"), "1")
        cfg = json.load(open(os.path.join(preview_root, "menu", "menu_config.json"),
                             encoding="utf-8"))
        check("the title reaches the generic menu through the config",
              cfg.get("title"), "Mock Game")
        check("bonus/ and mods/ staged as before",
              (os.path.isdir(os.path.join(preview_root, "bonus")),
               os.path.isdir(os.path.join(preview_root, "mods"))), (True, True))
        shutil.rmtree(preview_root, ignore_errors=True)
        print()

        # --- scenario H: the sweep, against a real junction ----------------
        # The one thing the sweep must never do is reach through a junction
        # into the author's originals. Run against a sandbox rather than the
        # machine's %TEMP%, with a real junction over a real canary folder.
        sweep_ns = {"os": os, "shutil": shutil, "subprocess": subprocess,
                    "tempfile": tempfile, "time": time,
                    "PREVIEW_PREFIX": PREVIEW_PREFIX, "_STARTED_AT": 0.0}
        exec(extract_module_funcs(
            src, ["remove_preview_dir", "sweep_stale_previews", "link_or_copy_tree"]),
            sweep_ns)

        root = os.path.join(base, "H")
        fake_temp = os.path.join(root, "temp")
        os.makedirs(fake_temp)

        canary = os.path.join(root, "author", "bonus")
        os.makedirs(os.path.join(canary, "ost"))
        master = os.path.join(canary, "ost", "track01.mp3")
        open(master, "wb").write(b"master tape")

        stale = os.path.join(fake_temp, PREVIEW_PREFIX + "deadbeef")
        os.makedirs(os.path.join(stale, "menu"))
        open(os.path.join(stale, "menu", "menu_config.json"), "w").write("{}")
        kind = sweep_ns["link_or_copy_tree"](canary, os.path.join(stale, "bonus"))

        # A preview from a Rialto that is still running, and something that is
        # simply not ours - neither may be touched.
        fresh_preview = os.path.join(fake_temp, PREVIEW_PREFIX + "stillopen")
        os.makedirs(fresh_preview)
        bystander = os.path.join(fake_temp, "someone_elses_temp_folder")
        os.makedirs(bystander)

        now = time.time()
        os.utime(stale, (now - 3600, now - 3600))
        os.utime(fresh_preview, (now + 60, now + 60))

        print("Scenario H - sweeping leftover previews")
        if junctions_allowed():
            check("the leftover staged its bonus by junction", kind, "junction")
        else:
            print("  [SKIP] junction sweep (mklink /J refused here; checked against a copy)")
        removed = sweep_ns["sweep_stale_previews"](root=fake_temp, older_than=now)
        check("one leftover removed", removed, 1)
        check("and it is gone", os.path.exists(stale), False)
        check("the author's master file survives the sweep",
              os.path.exists(master), True)
        check("with its contents intact", open(master, "rb").read(), b"master tape")
        check("a preview newer than this run is left alone",
              os.path.isdir(fresh_preview), True)
        check("and folders that are not ours are never considered",
              os.path.isdir(bystander), True)
        print()
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print("  - " + f)
        return 1
    print("All bonus/mods staging assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
