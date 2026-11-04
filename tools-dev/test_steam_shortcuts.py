"""ADD TO STEAM, against the ways a real shortcuts.vdf goes wrong.

The disc menu writes into a file Steam owns and that already holds every
non-Steam game the player has ever added. Getting it wrong does not lose a
Rialto build, it loses somebody's library. So the interesting cases are all
failure cases: a corrupt list, a zero-byte one, a read-only one, a disk that
fills up mid-write, a second click, and a game whose real binary is three
folders down.

The real methods are pulled out of Rialto.pyw's MENU_TEMPLATE_SOURCE by AST
extraction and exec'd on a stub host, so what runs here is what ships on discs.

Whether Steam is running is checked against a stand-in registry and stand-in
process lists (14 to 18), then the real process helpers are run once against
this PC's own processes (19). No test here reads or writes the real registry,
and none needs Steam.

Usage: python test_steam_shortcuts.py [path-to-Rialto.pyw]
"""
import ast
import contextlib
import ctypes
import json
import os
import shutil
import subprocess
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
    "_vdf_existing_exes", "_vdf_present_shortcuts", "_count_vdf_entries", "_steam_appid",
    "_vdf_shortcut_entry", "_write_vdf_atomically", "_install_steam_art", "_install_steam_icon",
    "_keep_steam_picture", "_update_steam_icon",
    "_steam_game_list", "add_to_steam",
    "_steam_is_running", "_pid_image_name", "_process_names",
]

ACTIVE_PROCESS = r"Software\Valve\Steam\ActiveProcess"


class FakeRegistry:
    """Stands in for winreg, answering the one read _steam_is_running makes.

    pid=None means Steam's ActiveProcess key is not there at all. Every key
    opened is recorded, so a test can say nothing else was looked at.
    """
    HKEY_CURRENT_USER = "HKEY_CURRENT_USER"
    HKEY_LOCAL_MACHINE = "HKEY_LOCAL_MACHINE"

    def __init__(self, pid):
        self.pid = pid
        self.opened = []

    def OpenKey(self, hive, path):
        self.opened.append((hive, path))
        if self.pid is None:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return (hive, path)

    def QueryValueEx(self, key, name):
        if name != "pid":
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return self.pid, 4  # REG_DWORD

    def CloseKey(self, key):
        pass


@contextlib.contextmanager
def fake_registry(pid=None):
    """Put a FakeRegistry where `import winreg` will find it, then put winreg back."""
    fake = FakeRegistry(pid)
    module = types.ModuleType("winreg")
    for name in ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "OpenKey", "QueryValueEx", "CloseKey"):
        setattr(module, name, getattr(fake, name))
    saved = sys.modules.get("winreg")
    sys.modules["winreg"] = module
    try:
        yield fake
    finally:
        if saved is None:
            sys.modules.pop("winreg", None)
        else:
            sys.modules["winreg"] = saved


def stub_processes(menu, image=None, names=(), image_error=None, names_error=None):
    """Stand-ins for the two process helpers.

    image is what the registry's pid turns out to be (None: no live process);
    names is the list of running programs. menu.asked records each pid looked up.
    """
    asked = []

    def pid_image_name(pid):
        asked.append(pid)
        if image_error is not None:
            raise image_error
        return image

    def process_names():
        if names_error is not None:
            raise names_error
        return set(names)

    menu._pid_image_name = pid_image_name
    menu._process_names = process_names
    menu.asked = asked


def english_strings():
    """The menu's English strings: every popup line now comes from the translations."""
    tree = ast.parse(menu_source(open(RIALTO, encoding="utf-8").read()))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "attr", "") == "translations" for t in node.targets):
            return ast.literal_eval(node.value)["English"]
    raise SystemExit("translations not found")


def make_menu(tmp, game_dir, vdf_paths, steam_running=False, art=True,
              games_config=None, resolved_exe=None):
    """A stub disc menu with the real Steam methods on it.

    steam_running=None keeps the real _steam_is_running, for the tests that
    put a fake registry and stand-in process helpers under it.
    """
    ns = {"os": os, "sys": sys, "shutil": shutil, "ctypes": ctypes, "json": json,
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
    if steam_running is not None:
        menu._steam_is_running = lambda: steam_running
    menu.show_preview_notice = lambda: None
    menu.translations = {"English": english_strings()}
    menu.current_lang = "English"

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
        check("and it is the list from before the press", open(vdf + ".rialto-backup", "rb").read(),
              HEADER + existing + b"\x08\x08")
        # The readiness run (4 Nov): a second press that added nothing rewrote the backup with the list
        # that already held the game, so the player's own list was gone from it.
        menu = make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        menu.add_to_steam()
        check("a second press adds nothing", menu.said[-1][0], "Already in Steam")
        check("and the backup still holds the player's own list", open(vdf + ".rialto-backup", "rb").read(),
              HEADER + existing + b"\x08\x08")
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

    # --------------------------------------------------------------- 14
    print("14. Steam was ended from Task Manager: the registry still names a pid that is gone")
    # A developer's report (30 Oct 2026): ADD TO STEAM said Steam was running
    # even after he ended every Steam process and restarted the disc. Steam
    # zeroes ActiveProcess\pid only on a clean exit, and the menu used to trust
    # any number it found there. The helpers left behind (steamwebhelper.exe,
    # steamservice.exe) are in the list on purpose: only steam.exe is Steam.
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "Steam", "userdata", "123456789", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], steam_running=None, resolved_exe=exe)
        stub_processes(menu, image=None,
                       names={"explorer.exe", "steamwebhelper.exe", "steamservice.exe"})
        with fake_registry(pid=12345) as registry:
            check("Steam is not counted as running", menu._steam_is_running(), False)
            menu.add_to_steam()
        check("the registry's pid was the one asked about", menu.asked, [12345, 12345])
        check("it says it was added", menu.said[-1][0], "Added to Steam")
        data = open(vdf, "rb").read()
        check("the shortcut is in the profile's shortcuts.vdf",
              menu._count_vdf_entries(data) == 1 and os.path.basename(exe).encode() in data, True)
        check("only Steam's ActiveProcess key was read",
              set(registry.opened), {("HKEY_CURRENT_USER", ACTIVE_PROCESS)})
    print()

    # --------------------------------------------------------------- 15
    print("15. Steam really is running: the registry's pid is a live steam.exe")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "Steam", "userdata", "123456789", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = make_menu(tmp, game_dir, [vdf], steam_running=None, resolved_exe=exe)
        # The process list is left empty, so the pid alone has to catch it.
        stub_processes(menu, image="steam.exe", names=set())
        with fake_registry(pid=4242):
            check("Steam is running", menu._steam_is_running(), True)
            menu.add_to_steam()
        check("refused", menu.said[-1][0], "Exit Steam first")
        check("says nothing was added yet",
              "nothing has been added yet" in menu.said[-1][1], True)
        check("no list was written", os.path.exists(vdf), False)
        check("and no backup either", os.path.exists(vdf + ".rialto-backup"), False)
    print()

    # --------------------------------------------------------------- 16
    print("16. the pid now belongs to some other program")
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        menu = make_menu(tmp, game_dir, [], steam_running=None, resolved_exe=exe)
        stub_processes(menu, image="notepad.exe", names={"notepad.exe", "explorer.exe"})
        with fake_registry(pid=4242):
            check("a reused pid is not Steam", menu._steam_is_running(), False)
        stub_processes(menu, image="", names={"svchost.exe"})
        with fake_registry(pid=4242):
            check("a pid Windows will not name, and no steam.exe: not running",
                  menu._steam_is_running(), False)
        stub_processes(menu, image="", names={"svchost.exe", "steam.exe"})
        with fake_registry(pid=4242):
            check("a pid Windows will not name, but steam.exe is up: running",
                  menu._steam_is_running(), True)
    print()

    # --------------------------------------------------------------- 17
    print("17. the registry says 0, or has no key, but a steam.exe is running")
    # Steam started under another Windows account, or a registry value that is
    # stale-zero: an entry written now is still lost when that Steam exits.
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        menu = make_menu(tmp, game_dir, [], steam_running=None, resolved_exe=exe)
        stub_processes(menu, image=None, names={"explorer.exe", "steam.exe"})
        with fake_registry(pid=0):
            check("pid 0 with steam.exe running: running", menu._steam_is_running(), True)
        check("a pid of 0 is never looked up", menu.asked, [])
        with fake_registry(pid=None):
            check("no ActiveProcess key with steam.exe running: running",
                  menu._steam_is_running(), True)
        with fake_registry(pid="not a number"):
            check("a value that is not a number with steam.exe running: running",
                  menu._steam_is_running(), True)
        stub_processes(menu, image=None, names={"explorer.exe"})
        with fake_registry(pid=None):
            check("no key and no steam.exe: not running", menu._steam_is_running(), False)
        with fake_registry(pid=0):
            check("pid 0 and no steam.exe: not running", menu._steam_is_running(), False)
    print()

    # --------------------------------------------------------------- 18
    print("18. the check itself fails: treated as running, nothing written")
    # A false "running" costs the player one more press. A false "not running"
    # writes under a live Steam, which throws the entry away on exit.
    with tempfile.TemporaryDirectory() as tmp:
        game_dir, exe = make_disc(tmp)
        vdf = os.path.join(tmp, "Steam", "userdata", "123456789", "config", "shortcuts.vdf")
        new_vdf(vdf)
        before = open(vdf, "rb").read()
        menu = make_menu(tmp, game_dir, [vdf], steam_running=None, resolved_exe=exe)
        stub_processes(menu, image_error=OSError(31, "A device attached to the system is not functioning"),
                       names=set())
        with fake_registry(pid=4242):
            check("asking about the pid fails: running", menu._steam_is_running(), True)
        stub_processes(menu, image=None, names_error=OSError(8, "Not enough memory"))
        with fake_registry(pid=4242):
            check("the process list fails after a dead pid: running", menu._steam_is_running(), True)
        with fake_registry(pid=0):
            check("the process list fails with pid 0: running", menu._steam_is_running(), True)
        stub_processes(menu, image=None, names_error=RuntimeError("anything at all"))
        with fake_registry(pid=None):
            check("any other error: running", menu._steam_is_running(), True)
            menu.add_to_steam()
        check("and the player is told to exit Steam", menu.said[-1][0], "Exit Steam first")
        check("the list was not touched", open(vdf, "rb").read(), before)
    print()

    # --------------------------------------------------------------- 19
    print("19. the real process helpers on this PC (no Steam needed)")
    if sys.platform != "win32":
        print("  [SKIP] Windows only")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            game_dir, exe = make_disc(tmp)
            menu = make_menu(tmp, game_dir, [], steam_running=None, resolved_exe=exe)
            own = os.path.basename(sys.executable).lower()
            check("this test's own pid is named", menu._pid_image_name(os.getpid()), own)
            # No console window, even when the parent has none (the review of 30 Oct 2026).
            child = subprocess.Popen([sys.executable, "-c", "pass"],
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            child.wait()
            # Popen still holds a handle, so the ended process can be opened:
            # only its exit code says it is gone.
            check("a process that has ended is not alive", menu._pid_image_name(child.pid), None)
            check("a pid no process has", menu._pid_image_name(0x7FFFFFFC), None)
            names = menu._process_names()
            check("the process list holds this test's own program", own in names, True)
            check("and many others", len(names) > 5, True)
            print("  (steam.exe is %srunning on this PC)" % ("" if "steam.exe" in names else "not "))
            menu._process_names = lambda: set()
            with fake_registry(pid=os.getpid()):
                check("a live pid that is not steam.exe is not Steam",
                      menu._steam_is_running(), False)
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
