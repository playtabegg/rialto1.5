"""Exercise the mod-exe resolution on both sides against a real temp tree.

Build side:  RialtoApp.detect_mod_launcher_exe  (lives in Rialto.pyw directly)
Menu side:   GameMenu._resolve_mods_dir / _resolve_mod_exe (live in the template)

Both are pulled out by source extraction and exec'd on a stub object, so no
tkinter and no PyQt5 are needed.
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_source import extract_menu_source  # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def extract(src, class_name, names):
    """Return exec'able source for the named methods and attributes of a class.

    Class-level assignments come along as well as methods, because the code
    under test leans on one: _configured_exe screens a configured path through
    _is_helper_exe, which reads HELPER_EXES. Copying that list into the test
    would let the two drift apart, which is exactly the drift worth catching.
    """
    tree = ast.parse(src)
    out, got = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.name)
                elif isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.targets[0].id)
    missing = set(names) - got
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


class Flag:
    """Stands in for a tk.StringVar / BooleanVar."""
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


def make_host(method_src, **attrs):
    ns = {"os": os, "sys": sys}
    exec(f"class Host:\n{textwrap.indent(method_src, '    ')}", ns)
    host = ns["Host"]()
    for k, v in attrs.items():
        setattr(host, k, v)
    host.update_status = lambda msg: None
    return host


def touch(*parts):
    p = os.path.join(*parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write("x")
    return p


def main():
    src = open(RIALTO, encoding="utf-8").read()
    # The mod folder is a picker now, not always a folder called "mods".
    build_src = extract(src, "RialtoApp",
                        ["detect_mod_launcher_exe", "default_mod_dir",
                         "resolved_mod_dir", "staged_mod_dir_name"])
    menu_src = extract_menu_source(RIALTO)
    runtime_src = extract(menu_src, "GameMenu",
                          ["_resolve_mods_dir", "_resolve_mod_exe", "_configured_exe",
                           "_inside_game_dir", "_is_helper_exe", "HELPER_EXES"])

    root = tempfile.mkdtemp(prefix="rialto_modtest_")
    # A sibling of the install folder, standing in for anywhere on the player's
    # disk a configured path might try to reach.
    elsewhere = tempfile.mkdtemp(prefix="rialto_elsewhere_")
    try:
        build = make_host(build_src, mod_folder_var=Flag(""), current_game_path="")

        print("BUILD SIDE - detect_mod_launcher_exe")
        # Nothing found means nothing found. This used to answer
        # "mods/ModLauncher.exe" whether or not such a file existed, and
        # that invented path could end up in a disc's menu_config.json.
        check("no mods folder -> nothing", build.detect_mod_launcher_exe(root), "")

        os.makedirs(os.path.join(root, "mods"))
        check("empty mods folder -> nothing", build.detect_mod_launcher_exe(root), "")

        touch(root, "mods", "MO2", "ModOrganizer.exe")
        check("nested exe found", build.detect_mod_launcher_exe(root), "mods/MO2/ModOrganizer.exe")

        touch(root, "mods", "Vortex.exe")
        check("top level wins over nested", build.detect_mod_launcher_exe(root), "mods/Vortex.exe")

        touch(root, "mods", "readme.txt")
        check("non-exe ignored", build.detect_mod_launcher_exe(root), "mods/Vortex.exe")

        # The folder does not have to be called "mods". A game can keep its
        # tool in mod-maker/, and the MODS button used to never appear.
        game = tempfile.mkdtemp(prefix="rialto_game_")
        os.makedirs(os.path.join(game, "mod-maker", "Windows x86_64"))
        touch(root, "mod-maker", "Windows x86_64", "MyGame Mod Maker.exe")
        picked = make_host(build_src,
                           mod_folder_var=Flag(os.path.join(game, "mod-maker")),
                           current_game_path=game)
        check("an author-named folder is found",
              picked.detect_mod_launcher_exe(root),
              "mod-maker/Windows x86_64/MyGame Mod Maker.exe")
        shutil.rmtree(game, ignore_errors=True)

        print("MENU SIDE - _resolve_mod_exe")
        menu = make_host(runtime_src, game_dir=root, menu_config={"mod_exe": "mods/Vortex.exe"})
        check("configured exe used", menu._resolve_mod_exe(), os.path.join(root, "mods", "Vortex.exe"))

        menu.menu_config = {"mod_exe": "mods/Ghost.exe"}
        check("stale config falls back to scan", menu._resolve_mod_exe(), os.path.join(root, "mods", "Vortex.exe"))

        menu.menu_config = {}
        check("no config, scan finds top level", menu._resolve_mod_exe(), os.path.join(root, "mods", "Vortex.exe"))

        os.remove(os.path.join(root, "mods", "Vortex.exe"))
        check("scan falls through to nested", menu._resolve_mod_exe(), os.path.join(root, "mods", "MO2", "ModOrganizer.exe"))

        shutil.rmtree(os.path.join(root, "mods"))
        check("no mods dir -> None", menu._resolve_mod_exe(), None)
        check("_resolve_mods_dir -> None", menu._resolve_mods_dir(), None)

        # Windows is case-insensitive, so an uppercase MODS folder resolves via
        # the first candidate; compare case-insensitively.
        os.makedirs(os.path.join(root, "MODS"))
        got = menu._resolve_mods_dir()
        check("uppercase MODS dir found", got and got.lower(), os.path.join(root, "MODS").lower())
        touch(root, "MODS", "Nexus.exe")
        got = menu._resolve_mod_exe()
        check("exe inside uppercase MODS found", got and os.path.basename(got), "Nexus.exe")

        # menu_config.json sits unsigned next to a signed menu.exe, so a
        # configured path is untrusted input. None of these may resolve to the
        # thing they name; each should fall back to scanning the mods folder.
        print("MENU SIDE - configured paths that try to leave the install folder")
        outside = touch(elsewhere, "evil.exe")
        escape = os.path.relpath(outside, root)
        for label, rel in [
            ("absolute path", r"C:\Windows\System32\calc.exe"),
            ("UNC path", r"\\attacker\share\evil.exe"),
            ("parent traversal", escape),
            ("traversal through mods", os.path.join("MODS", "..", escape)),
        ]:
            menu.menu_config = {"mod_exe": rel}
            got = menu._resolve_mod_exe()
            check(f"{label} refused", got and os.path.basename(got), "Nexus.exe")

        # The helper blocklist used to guard only the folder scan, which left
        # the configured path - the reachable one - as the way around it.
        touch(root, "MODS", "setup.exe")
        menu.menu_config = {"mod_exe": "MODS/setup.exe"}
        got = menu._resolve_mod_exe()
        check("configured helper exe refused", got and os.path.basename(got), "Nexus.exe")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(elsewhere, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all mod-resolution checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
