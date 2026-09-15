"""ADD TO STEAM, against the ways a real shortcuts.vdf goes wrong.

The disc menu writes into a file Steam owns and that already holds every
non-Steam game the player has ever added. Getting it wrong does not lose a
Rialto build, it loses somebody's library. So the interesting cases are all
failure cases: a corrupt list, a zero-byte one, a read-only one, a disk that
fills up mid-write, a second click, and a game whose real binary is three
folders down.

The real methods are pulled out of Rialto.pyw's MENU_TEMPLATE_SOURCE by AST
extraction and exec'd on a stub host, so what runs here is what ships on discs.

Usage: python test_steam_shortcuts.py [path-to-Rialto.pyw]
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, wanted {want!r}")
    return ok


def menu_source(src):
    """MENU_TEMPLATE_SOURCE, the disc menu as it is written onto every disc."""
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE":
            return ast.literal_eval(node.value)
    raise SystemExit("MENU_TEMPLATE_SOURCE not found")


def methods(src, class_name, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name in names:
                    out.append(ast.get_source_segment(src, sub))
                    seen.add(sub.name)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract {sorted(missing)}")
    return "\n\n".join(out)


HEADER = b"\x00shortcuts\x00"

STEAM_METHODS = [
    "_vdf_existing_exes", "_count_vdf_entries", "_steam_appid",
    "_vdf_shortcut_entry", "_write_vdf_atomically", "_install_steam_art",
    "_steam_game_list", "add_to_steam",
]


def make_menu(tmp, game_dir, vdf_paths, steam_running=False, art=True,
              games_config=None, resolved_exe=None):
    """A stub disc menu with the real Steam methods on it."""
    ns = {"os": os, "sys": sys, "shutil": shutil,
          "menu_dir": lambda: os.path.join(game_dir, "menu")}
    exec(f"class Menu:\n{textwrap.indent(methods(menu_source(open(RIALTO, encoding='utf-8').read()), 'GameMenu', STEAM_METHODS), '    ')}", ns)
    menu = ns["Menu"]()
    menu.game_dir = game_dir
    menu.menu_title = "Mock Game"
    menu.preview_mode = False
    menu.games = games_config or []
    menu.menu_config = {}
    menu.find_game_exe = lambda: (resolved_exe, [game_dir])
    menu._steam_shortcuts_paths = lambda: list(vdf_paths)
    menu._steam_is_running = lambda: steam_running
    menu.show_preview_notice = lambda: None

    said = []
    menu._menu_message = lambda title, text, detail="": said.append((title, text, detail))
    menu.said = said
    return menu


def make_disc(tmp, with_art=True, exe_rel="game.exe"):
    """An installed game folder, menu/ beside it, optionally with Steam art."""
    game_dir = os.path.join(tmp, "install")
    os.makedirs(os.path.join(game_dir, "menu"), exist_ok=True)
    full = os.path.join(game_dir, exe_rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "wb").write(b"MZ")
    if with_art:
        art_dir = os.path.join(game_dir, "menu", "steam")
        os.makedirs(art_dir, exist_ok=True)
        for name in ("capsule.png", "wide.png", "hero.png", "logo.png"):
            open(os.path.join(art_dir, name), "wb").write(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    return game_dir, full


def new_vdf(path, entries=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(HEADER + entries + b"\x08\x08")


def main():
    print("ADD TO STEAM, hardened\n")

    # ---------------------------------------------------------------- 1
    print("1. a profile that has never had a non-Steam game (no shortcuts.vdf)")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        check("the list is created", os.path.exists(vdf), True)
        check("it says it was added", menu.said[-1][0], "Added to Steam")
        data = open(vdf, "rb").read()
        check("well formed", data.startswith(HEADER) and data.endswith(b"\x08\x08"), True)
        check("one entry", menu._count_vdf_entries(data), 1)
        grid = os.path.join(os.path.dirname(vdf), "grid")
        appid = menu._steam_appid("Mock Game", exe)
        check("capsule art filed under the shortcut's own appid",
              os.path.exists(os.path.join(grid, "%dp.png" % appid)), True)
        check("hero art too", os.path.exists(os.path.join(grid, "%d_hero.png" % appid)), True)
    print()

    # ---------------------------------------------------------------- 2
    print("2. pressing it twice")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        menu.add_to_steam()
        check("still one entry, not two", menu._count_vdf_entries(open(vdf, "rb").read()), 1)
        check("and it says so", menu.said[-1][0], "Already in Steam")
    print()

    # ---------------------------------------------------------------- 3
    print("3. an existing library is preserved, not replaced")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        seed = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        existing = (seed._vdf_shortcut_entry(0, "Someone Elses Game", r"C:\Other\thing.exe",
                                             r"C:\Other", "")
                    + seed._vdf_shortcut_entry(1, "And Another", r"C:\Other\two.exe",
                                               r"C:\Other", ""))
        new_vdf(vdf, existing)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        data = open(vdf, "rb").read()
        check("three entries now", menu._count_vdf_entries(data), 3)
        check("the other games are still in there",
              b"Someone Elses Game" in data and b"And Another" in data, True)
        check("a backup was left behind",
              os.path.exists(vdf + ".rialto-backup"), True)
    print()

    # ---------------------------------------------------------------- 4
    print("4. a corrupt list is left alone")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        garbage = b"\x00shortcuts\x00\x07not a real field at all\x08\x08"
        open(vdf, "wb").write(garbage)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        check("the file is untouched", open(vdf, "rb").read(), garbage)
        check("and it says it could not", menu.said[-1][0], "Could not add to Steam")
    print()

    # ---------------------------------------------------------------- 5
    print("5. a zero-byte list is treated as empty, not as corrupt")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        open(vdf, "wb").close()
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        check("added", menu.said[-1][0], "Added to Steam")
        check("one entry", menu._count_vdf_entries(open(vdf, "rb").read()), 1)
    print()

    # ---------------------------------------------------------------- 6
    print("6. the write fails part-way: the old list must survive intact")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        seed = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        original = HEADER + seed._vdf_shortcut_entry(0, "Precious", r"C:\P\p.exe", r"C:\P", "") + b"\x08\x08"
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        open(vdf, "wb").write(original)

        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)

        real_open = open

        def exploding_open(path, mode="r", *a, **k):
            if str(path).endswith(".rialto-new"):
                handle = real_open(path, mode, *a, **k)
                original_write = handle.write

                def boom(chunk):
                    original_write(chunk[:16])
                    raise OSError(28, "No space left on device")
                handle.write = boom
                return handle
            return real_open(path, mode, *a, **k)

        import builtins
        builtins.open = exploding_open
        try:
            menu.add_to_steam()
        finally:
            builtins.open = real_open

        check("the original list is byte-for-byte intact",
              real_open(vdf, "rb").read(), original)
        check("no half-written temp file left behind",
              os.path.exists(vdf + ".rialto-new"), False)
        check("and the player is told", menu.said[-1][0], "Could not add to Steam")
    print()

    # ---------------------------------------------------------------- 7
    print("7. Steam is running: nothing written, told to exit Steam first")
    # It used to write anyway and tell the player to restart Steam. Steam holds
    # this list in memory and writes its own copy back out when it exits, so
    # that entry was discarded the moment they quit - the game looked added and
    # then was not there. Refusing before touching the file is the only version
    # of this that does not waste their time.
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        with open(vdf, "wb") as f:
            f.write(b"\x00shortcuts\x00\x08\x08")
        before = open(vdf, "rb").read()
        menu = make_menu(tmp, game_dir, [vdf], steam_running=True, resolved_exe=exe)
        menu.add_to_steam()
        check("refused", menu.said[-1][0], "Exit Steam first")
        check("says nothing was added yet",
              "nothing has been added yet" in menu.said[-1][1], True)
        check("tells them the tray icon, not the window",
              "notification area" in menu.said[-1][2], True)
        check("the list was not touched", open(vdf, "rb").read(), before)
        check("and no backup was made either",
              os.path.exists(vdf + ".rialto-backup"), False)

        # the same click with Steam closed goes through
        menu = make_menu(tmp, game_dir, [vdf], steam_running=False, resolved_exe=exe)
        menu.add_to_steam()
        check("closing Steam and clicking again works",
              menu.said[-1][0], "Added to Steam")
        check("and it no longer tells them to restart Steam",
              "Close it completely" in menu.said[-1][2], False)
    print()

    # ---------------------------------------------------------------- 8
    print("8. two Steam profiles on one PC")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        a = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        b = os.path.join(tmp, "userdata", "222", "config", "shortcuts.vdf")
        for path in (a, b):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        menu = make_menu(tmp, game_dir, [a, b], resolved_exe=exe)
        menu.add_to_steam()
        check("both profiles got it",
              all(os.path.exists(p) for p in (a, b)), True)
        appid = menu._steam_appid("Mock Game", exe)
        check("both got the art",
              all(os.path.exists(os.path.join(os.path.dirname(p), "grid", "%dp.png" % appid))
                  for p in (a, b)), True)
    print()

    # ---------------------------------------------------------------- 9
    print("9. a disc built before Steam art existed")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp, with_art=False)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        check("still added", menu.said[-1][0], "Added to Steam")
        check("no mention of art that does not exist",
              "Cover art" in menu.said[-1][2], False)
    print()

    # --------------------------------------------------------------- 10
    print("10. no Steam on this PC at all")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        menu = make_menu(tmp, game_dir, [], resolved_exe=exe)
        menu.add_to_steam()
        check("says Steam was not found", menu.said[-1][0], "Steam not found")
    print()

    # --------------------------------------------------------------- 11
    print("11. an Unreal-shaped game: Steam points at what PLAY starts")
    with tempfile.TemporaryDirectory() as tmp:
        rel = os.path.join("Project", "Binaries", "Win64", "Project-Win64-Shipping.exe")
        game_dir, exe = make_disc(tmp, exe_rel=rel)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        data = open(vdf, "rb").read()
        check("the deep binary is the one registered",
              b"Project-Win64-Shipping.exe" in data, True)
    print()

    # --------------------------------------------------------------- 12
    print("12. the appid in the file is the appid the art is filed under")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        import struct
        data = open(vdf, "rb").read()
        at = data.index(b"\x02appid\x00") + len(b"\x02appid\x00")
        in_file = struct.unpack("<I", data[at:at + 4])[0]
        check("they match", in_file, menu._steam_appid("Mock Game", exe))
    print()

    # --------------------------------------------------------------- 13
    print("13. a game name with characters outside ASCII")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.menu_title = "Sœur Café 東京"
        menu.add_to_steam()
        data = open(vdf, "rb").read()
        check("written as UTF-8", "Sœur Café 東京".encode("utf-8") in data, True)
        check("and the file still parses", menu._count_vdf_entries(data), 1)
    print()

    if FAILURES:
        print("FAILED (%d):" % len(FAILURES))
        for line in FAILURES:
            print("  - " + line)
        return 1
    print("All Steam shortcut checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
