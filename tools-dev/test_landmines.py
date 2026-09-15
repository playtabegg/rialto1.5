"""No IsWin64 landmine, no dead DRM, find_game_exe does not follow junctions.
"""
import ast
import os
import shutil
import subprocess
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


def says(label, condition, detail=""):
    print(f"  [{'OK  ' if condition else 'FAIL'}] {label}{(' -> ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


def extract(src, class_name, names):
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


def make_menu(method_src, **attrs):
    ns = {"os": os, "sys": sys}
    exec("class Host:\n" + textwrap.indent(method_src, "    "), ns)
    host = ns["Host"]()
    for k, v in attrs.items():
        setattr(host, k, v)
    return host


def main():
    src = open(RIALTO, encoding="utf-8").read()
    menu_src = extract_menu_source(RIALTO)

    print("1. dead DRM and the IsWin64 landmine are gone")
    says("create_lock_file is gone", "def create_lock_file" not in src)
    says("check_dvd.bat is gone", "check_dvd.bat" not in src)
    says("DRM folder sweep is gone", "Including DRM folder" not in src)
    says("no function IsWin64 in Rialto.pyw generators",
         "function IsWin64" not in src)
    print()

    print("2. find_game_exe does not follow a junction out of the install folder")
    runtime_src = extract(menu_src, "GameMenu", [
        "find_game_exe", "_configured_exe", "_inside_game_dir",
        "_is_helper_exe", "_is_reparse_point", "HELPER_EXES",
    ])
    base = tempfile.mkdtemp(prefix="rialto_junction_")
    try:
        game_dir = os.path.join(base, "game")
        outside = os.path.join(base, "outside")
        os.makedirs(os.path.join(game_dir, "Binaries", "Win64"))
        os.makedirs(outside)
        real_exe = os.path.join(game_dir, "Binaries", "Win64", "Game-Win64-Shipping.exe")
        decoy = os.path.join(outside, "huge.exe")
        with open(real_exe, "wb") as f:
            f.write(b"MZ" + b"r" * 100)
        with open(decoy, "wb") as f:
            f.write(b"MZ" + b"H" * 10000)
        trap = os.path.join(game_dir, "trap")
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", trap, outside],
            capture_output=True, text=True)
        if not (result.returncode == 0 and os.path.isdir(trap)):
            print("  [SKIP] junction walk (mklink /J refused here)")
        else:
            says("junction created", True)
            host = make_menu(runtime_src, game_dir=game_dir, menu_config={})
            found, searched = host.find_game_exe()
            says("returned an exe", bool(found), repr(found))
            if found:
                says("returned path is inside the game folder",
                     os.path.normcase(os.path.realpath(found)).startswith(
                         os.path.normcase(os.path.realpath(game_dir)) + os.sep),
                     found)
                says("returned path is not through the junction",
                     "trap" not in os.path.normcase(found), found)
                says("returned the real shipping exe, not the outside decoy",
                     os.path.normcase(os.path.realpath(found))
                     == os.path.normcase(os.path.realpath(real_exe)),
                     found)
            says("walk never listed the outside folder as searched",
                 not any(os.path.normcase(os.path.realpath(p))
                         == os.path.normcase(os.path.realpath(outside))
                         for p in searched),
                 repr(searched))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print()

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all landmine / junction checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
