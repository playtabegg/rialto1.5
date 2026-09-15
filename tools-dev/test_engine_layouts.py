"""Point Rialto's game detection at the layouts real engines actually produce.

Rialto once assumed one folder shape. This asks the obvious question: how
many real engine layouts would it get wrong? Each fixture below is the
file layout a real engine emits, built as empty files at the right paths and
sizes, and asked one question - which .exe does Rialto think is the game?
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, os.path.join(REPO, "tools-dev"))
from menu_source import extract_menu_source  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def extract(src, cls, names):
    out, got = [], set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                nm = getattr(item, "name", None)
                if nm is None and isinstance(item, ast.Assign):
                    nm = getattr(item.targets[0], "id", None)
                if nm in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(nm)
    missing = set(names) - got
    if missing:
        raise SystemExit("could not extract %s" % sorted(missing))
    return "\n\n".join(out)


def host(method_src, **attrs):
    ns = {"os": os, "sys": sys, "shutil": shutil}
    exec("class Host:\n" + textwrap.indent(method_src, "    "), ns)
    h = ns["Host"]()
    h.update_status = lambda m: None
    for k, v in attrs.items():
        setattr(h, k, v)
    return h


def put(root, rel, mb=1):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"\0" * int(mb * 1024 * 1024))
    return p


# (name, files as (path, size_mb), the file a human would call "the game")
FIXTURES = [
    ("Unity", [
        ("MyGame.exe", 0.6), ("UnityCrashHandler64.exe", 1.2),
        ("UnityPlayer.dll", 25), ("MyGame_Data/globalgamemanagers", 1),
        ("MyGame_Data/level0", 30), ("MonoBleedingEdge/EmbedRuntime/mono-2.0-bdwgc.dll", 5),
    ], "MyGame.exe"),
    ("Unreal", [
        ("MyGame.exe", 0.2),
        ("MyGame/Binaries/Win64/MyGame-Win64-Shipping.exe", 90),
        ("MyGame/Content/Paks/MyGame-WindowsNoEditor.pak", 400),
        ("Engine/Binaries/ThirdParty/CEF3/Win64/chrome_elf.dll", 2),
        ("Engine/Extras/Redist/en-us/UEPrereqSetup_x64.exe", 40),
    ], "MyGame.exe"),
    ("Godot 4 (exe at root)", [
        ("MyGame.exe", 85), ("MyGame.pck", 200),
    ], "MyGame.exe"),
    ("Godot 4 (exe two folders down)", [
        ("game/Windows x86_64 Portable/MyGame.exe", 85),
        ("game/Windows x86_64 Portable/MyGame.pck", 200),
        ("game/Linux x86_64 Portable/MyGame.x86_64", 90),
        ("mod-maker/Windows x86_64/Mod Maker.exe", 60),
    ], "game/Windows x86_64 Portable/MyGame.exe"),
    ("GameMaker", [
        ("MyGame.exe", 12), ("data.win", 300), ("options.ini", 0.01),
    ], "MyGame.exe"),
    ("RPG Maker MZ", [
        ("Game.exe", 1.5), ("nw.dll", 90), ("package.json", 0.01),
        ("www/data/Map001.json", 0.1), ("d3dcompiler_47.dll", 4),
    ], "Game.exe"),
    ("Ren'Py", [
        ("MyGame.exe", 5), ("MyGame.sh", 0.01), ("lib/py3-windows-x86_64/python3.dll", 4),
        ("game/script.rpyc", 2), ("renpy/common/00console.rpy", 0.2),
    ], "MyGame.exe"),
    ("Love2D", [
        ("MyGame.exe", 6), ("love.dll", 3), ("SDL2.dll", 2),
    ], "MyGame.exe"),
    ("Electron / NW.js", [
        ("MyGame.exe", 140), ("resources/app.asar", 200),
        ("locales/en-US.pak", 0.5), ("d3dcompiler_47.dll", 4),
        ("chrome_100_percent.pak", 1),
    ], "MyGame.exe"),
    ("Java launcher", [
        ("MyGame.exe", 0.3), ("MyGame.jar", 60), ("jre/bin/javaw.exe", 1),
    ], "MyGame.exe"),
    ("launcher + game + editor", [
        ("Launcher.exe", 3), ("MyGame.exe", 120), ("LevelEditor.exe", 45),
        ("crashpad_handler.exe", 1),
    ], "MyGame.exe"),
    ("everything one level down", [
        ("bin/MyGame.exe", 70), ("bin/data.pak", 150), ("README.txt", 0.01),
    ], "bin/MyGame.exe"),
]

rialto_src = open(RIALTO, encoding="utf-8").read()
menu_src = extract_menu_source(RIALTO)

build_src = extract(rialto_src, "RialtoApp",
                    ["detect_primary_game_exe", "HELPER_EXE_NAMES", "NON_GAME_DIRS",
                     "_name_key", "_title_key"])


class Flag:
    def __init__(self, v):
        self._v = v

    def get(self):
        return self._v
menu_bits = extract(menu_src, "GameMenu",
                    ["find_game_exe", "_configured_exe", "_inside_game_dir",
                     "_is_helper_exe", "_is_reparse_point", "HELPER_EXES"])

base = tempfile.mkdtemp(prefix="engine_corpus_")
rows = []
try:
    for name, files, expected in FIXTURES:
        root = os.path.join(base, name.replace(" ", "_").replace("/", "_")
                            .replace("'", "").replace("(", "").replace(")", ""))
        os.makedirs(root, exist_ok=True)
        for rel, mb in files:
            put(root, rel, mb)

        title = "MyGame" if "MyGame.exe" in expected else "Game"
        b = host(build_src, entries={"Title": Flag(title)})
        detected = b.detect_primary_game_exe(root) or ""

        m = host(menu_bits, game_dir=root, menu_config={"game_exe": detected}, games=[])
        ns_title = title
        found, _ = m.find_game_exe()
        menu_pick = os.path.relpath(found, root).replace(os.sep, "/") if found else ""

        rows.append((name, expected, detected.replace(os.sep, "/"), menu_pick))
finally:
    shutil.rmtree(base, ignore_errors=True)

failures = []
for name, expected, detected, menu_pick in rows:
    good = (menu_pick == expected and detected == expected)
    print("  [%s] %-28s -> %s" % ("OK  " if good else "FAIL", name,
                                  menu_pick or "(nothing)"))
    if not good:
        failures.append("%s: detected %r, menu runs %r, wanted %r"
                        % (name, detected, menu_pick, expected))

print()
if failures:
    print("FAILED:")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("all %d engine layouts start the right executable." % len(rows))
