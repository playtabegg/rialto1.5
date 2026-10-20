"""Many games on one disc (1.5.1, B9).

A demo disc is a folder of game folders. Rialto finds the game in each, with
its folder's name and picture; the menu config carries a picture and a line
only when set (a 1.5.0 profile writes what it always wrote); the disc menu's
Play page keeps the player's stars, sort and language on the PC, read back
with suspicion; every game listed under PLAY GAMES joins the keyboard and controller order; and a
Start Menu shortcut for each game reaches every Windows only when asked for.

Source-extracted: no tkinter or Qt window is opened.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_installer_script as tis  # noqa: E402

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def class_items(src, cls, names):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return [textwrap.dedent(ast.get_source_segment(src, item)) for item in node.body
                    if (isinstance(item, ast.FunctionDef) and item.name in names)
                    or (isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") in names)]
    raise SystemExit("class %s not found" % cls)


def module_function(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit("%s not found" % name)


def main():
    src = open(tis.RIALTO, encoding="utf-8").read()
    template = ast.literal_eval(next(
        n.value for n in ast.parse(src).body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))

    # ------------------------------------------------------------ Rialto side
    names = {"games_in_subfolders", "detect_primary_game_exe", "_title_key", "_name_key",
             "validated_game_executables", "GAME_PICTURES", "NON_GAME_DIRS", "HELPER_EXE_NAMES"}
    ns = {"os": os}
    table = next(ast.get_source_segment(src, n) for n in ast.parse(src).body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_CONTROL_CHARS")
    exec(table + "\n\n" + module_function(src, "sanitize_text"), ns)
    body = "\n\n".join(class_items(src, "RialtoApp", names))
    exec("class Host:\n" + textwrap.indent(body, "    "), ns)
    host = ns["Host"]()
    host.entries = {}
    host.update_status = lambda message: None

    work = tempfile.mkdtemp(prefix="rialto_b9t_")
    try:
        base = os.path.join(work, "Demos")
        for folder, files in {"Alpha Run": ["Alpha.exe", "cover.png"],
                              "Beta Caves/Beta/Binaries/Win64": ["Beta-Win64-Shipping.exe"],
                              "Beta Caves": ["Beta.exe", "icon.ico", "cover.jpg"],
                              "Gamma": ["readme.txt"],
                              "bonus": ["Viewer.exe"],
                              ".git": ["x.exe"]}.items():
            os.makedirs(os.path.join(base, folder), exist_ok=True)
            for f in files:
                open(os.path.join(base, folder, f), "wb").write(b"MZ" if f.endswith(".exe") else b"x")
        open(os.path.join(base, "Loose.exe"), "wb").write(b"MZ")

        print("1. a game in each folder")
        found = host.games_in_subfolders(base)
        says("one row per folder holding a game, in name order", [g["name"] for g in found] == ["Alpha Run", "Beta Caves"],
             found)
        says("each starts the exe a single-game disc would", [g["exe"] for g in found] == ["Alpha Run/Alpha.exe", "Beta Caves/Beta.exe"], found)
        says("a picture beside it, icon before cover", [g.get("icon") for g in found] == ["Alpha Run/cover.png", "Beta Caves/icon.ico"], found)
        says("bonus, hidden folders and folders with no exe are passed over",
             not any(g["name"] in ("bonus", ".git", "Gamma") for g in found))
        says("a missing folder is no games, not a crash", host.games_in_subfolders(os.path.join(work, "nope")) == [])
        print()

        print("2. what the menu config carries")
        host.current_game_path = base
        host.game_executables = [
            {"name": "Alpha Run", "exe": "Alpha Run/Alpha.exe"},
            {"name": "Beta", "exe": "Beta Caves\\Beta.exe", "icon": "Beta Caves/icon.ico", "blurb": "Caves\nand more"},
            {"name": "Bad picture", "exe": "Alpha Run/Alpha.exe", "icon": "../../secret.png"},
            {"name": "Gone", "exe": "Alpha Run/cover.png", "icon": "Alpha Run/missing.png"}]
        games = host.validated_game_executables()
        says("a 1.5.0 entry is written exactly as before", games[0] == {"name": "Alpha Run", "exe": "Alpha Run/Alpha.exe"}, games[0])
        says("a picture and a line ride along when set, the line on one line",
             games[1] == {"name": "Beta", "exe": "Beta Caves/Beta.exe", "icon": "Beta Caves/icon.ico", "blurb": "Cavesand more"}, games[1])
        says("a picture outside the game folder is dropped", "icon" not in games[2], games[2])
        print()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("3. a Start Menu shortcut for each game, only when asked")
    lines = ns2 = tis.build_host(src)[1]
    w7 = ns2["windows7_shortcut_lines"]
    config = {"games": [{"name": "Demo Disc", "exe": "a/A.exe"}, {"name": "Beta", "exe": "b/B.exe"}]}
    icons, _runs = w7("Demo Disc", config, False)
    says("not asked: every game shortcut is for Windows 7 and 8 alone",
         all(l.endswith("OnlyBelowVersion: 6.3") for l in icons), icons)
    icons, _runs = w7("Demo Disc", dict(config, start_menu_per_game=True), False)
    group = [l for l in icons if l.startswith('Name: "{group}')]
    desk = [l for l in icons if l.startswith('Name: "{userdesktop}')]
    says("asked: the Start Menu ones reach every Windows", group and all("Version" not in l for l in group), group)
    says("the desktop ones stay Windows 7 and 8 only", desk and all(l.endswith("OnlyBelowVersion: 6.3") for l in desk), desk)
    says("no game takes the disc's own name beside the menu's shortcut",
         'Name: "{group}\\Demo Disc (2)"' in "\n".join(group), group)
    icons, _runs = w7("Solo", {"games": [{"name": "Only", "exe": "a/A.exe"}], "start_menu_per_game": True}, False)
    says("one game: the flag changes nothing", all(l.endswith("OnlyBelowVersion: 6.3") for l in icons), icons)
    extract = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "build_menu_config")
    body = ast.get_source_segment(src, extract)
    says("Rialto writes the flag only when ticked on a disc of several",
         'if getattr(self, "game_shortcuts", False) and len(config["games"]) > 1:' in body)
    print()

    # -------------------------------------------------------------- menu side
    print("4. the player's stars and sort, on the PC, read with suspicion")
    mns = {"os": os, "json": json}
    exec("MAX_STARS = 200\n" + "\n\n".join(module_function(template, n) for n in
                                                ("player_prefs_path", "read_player_prefs", "write_player_prefs")), mns)
    appdata = tempfile.mkdtemp(prefix="rialto_b9p_")
    old = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = appdata
    try:
        path = mns["player_prefs_path"]("Demo: Disc\\..\\..")
        says("kept under the disc's title, which cannot leave the folder",
             os.path.dirname(os.path.dirname(path)) == os.path.join(appdata, "Rialto Disc Menu")
             and os.path.basename(os.path.dirname(path)) == "Demo Disc", path)
        says("nothing kept yet: no stars, as on the disc", mns["read_player_prefs"]("T") == {"stars": [], "sort": "disc", "lang": ""})
        mns["write_player_prefs"]("T", {"stars": ["a/A.exe"], "sort": "az", "lang": "French"})
        says("written and read back", mns["read_player_prefs"]("T") == {"stars": ["a/A.exe"], "sort": "az", "lang": "French"})
        for garbage in (b"not json", b"[1,2]", b'{"stars": "a", "sort": 5}', b'{"stars": [1, null, "x"], "sort": "evil"}',
                        json.dumps({"stars": ["1", "2", "3", "4", "5"]}).encode(),
                        json.dumps({"stars": [str(n) for n in range(5000)] + ["1"] * 3, "lang": 7}).encode(),
                        json.dumps({"stars": ["x" * 500, "y"], "lang": "L" * 99}).encode()):
            open(mns["player_prefs_path"]("T"), "wb").write(garbage)
            got = mns["read_player_prefs"]("T")
            says("a rewritten file reads safely: %s" % garbage[:30].decode(),
                 isinstance(got["stars"], list) and all(isinstance(x, str) for x in got["stars"])
                 and len(got["stars"]) <= 200 and len(set(got["stars"])) == len(got["stars"])
                 and all(len(x) < 400 for x in got["stars"]) and got["sort"] in ("disc", "az")
                 and isinstance(got["lang"], str) and len(got["lang"]) < 40, str(got)[:120])
        open(mns["player_prefs_path"]("T"), "wb").write(json.dumps({"stars": ["1", "2", "3", "4", "5"]}).encode())
        says("any number of stars: five read back as five",
             mns["read_player_prefs"]("T")["stars"] == ["1", "2", "3", "4", "5"])
    finally:
        if old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old
        shutil.rmtree(appdata, ignore_errors=True)
    print()

    print("5. the menu")
    says("a preview never keeps the author's clicks", "if not self.preview_mode:\n            write_player_prefs" in template)
    says("a picture is held to the install folder and a size", "self._inside_game_dir(path)" in template
         and "8 * 1024 * 1024" in template)
    says("the keyboard and controller both follow the screen", template.count("buttons = self.nav_buttons()") == 2
         and "btn.installEventFilter(self)" in template
         and "buttons = [self.play_btn]" not in template)
    tree = ast.parse(template)
    nav = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "nav_buttons")
    order = [a.value for a in ast.walk(nav) if isinstance(a, ast.Constant) and isinstance(a.value, str)
             and a.value.endswith("_btn")]
    says("in the screen's order: compat, quick starts, mods, Steam, bonus",
         order == ["compat_btn", "mods_btn", "steam_btn", "bonus_btn"], order)
    says("every game listed under PLAY GAMES only on an installed disc of several",
         'if len(self.games) < 2 or getattr(self, "installer_path", ""):' in template)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll many-games checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
