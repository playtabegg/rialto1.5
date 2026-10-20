"""Files the installer places for the player (1.5.1, B10).

CodedRubyChan's request: a mod that needs its config and save files made before
the game first runs. Rialto stages each file or folder beside the build folder
(never in it, where Inno would make even an excluded folder on the player's
PC) and writes one [Files] line each: never over a file already there unless
asked, kept by the uninstaller unless asked. Copying only, no commands.

Seen for real with ISCC 6.5.4 on Windows 11 (the session's proof): a config in
the install folder and a saves folder in AppData Local land, a reinstall leaves
a changed save alone, and the uninstaller removes only what it was told to.
"""
import ast
import json
import os
import shutil
import subprocess
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


def main():
    src = open(tis.RIALTO, encoding="utf-8").read()
    host, ns = tis.build_host(src)
    stage = next(textwrap.dedent(ast.get_source_segment(src, i)) for n in ast.parse(src).body
                 if isinstance(n, ast.ClassDef) and n.name == "RialtoApp" for i in n.body
                 if isinstance(i, ast.FunctionDef) and i.name == "stage_placed_files")
    exec(stage, ns)
    sub, lines = ns["placed_subfolder"], ns["placed_files_lines"]

    print("1. a typed sub-folder stays under its place")
    for typed, want in [("MyStudio/MyGame", "MyStudio\\MyGame"), ("MyStudio\\MyGame\\", "MyStudio\\MyGame"),
                        ("..\\..\\Windows\\System32", "Windows\\System32"), ("C:\\Windows", "C\\Windows"),
                        ("{app}\\x", "app\\x"), ("a;b\"c", "abc"), ("NUL\\saves", "saves"), ("", ""), (None, "")]:
        says("%s -> %s" % (ascii(typed), ascii(want)), sub(typed) == want, sub(typed))
    print()

    print("2. one [Files] line per staged row")
    got = lines([{"n": 1, "name": "mod.ini", "place": "The install folder", "subfolder": "cfg"}])
    says("a file: never over theirs, kept after uninstall, by default", got == [
        'Source: "..\\.rialto-placed\\1\\mod.ini"; DestDir: "{app}\\cfg"; '
        'Flags: ignoreversion onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist'], got)
    got = lines([{"n": 2, "name": "", "place": "Saved Games", "subfolder": "MyStudio\\MyGame", "keep": False, "remove": True}])
    says("a folder, every file in it, replace and remove when asked", got == [
        'Source: "..\\.rialto-placed\\2\\*"; DestDir: "{usersavedgames}\\MyStudio\\MyGame"; '
        'Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist'], got)
    dests = [lines([{"n": 1, "name": "a.txt", "place": label}])[0].split('DestDir: "')[1].split('"')[0]
             for label, _const in ns["PLACED_FILE_PLACES"]]
    says("every place resolves on any PC", dests == ["{userdocs}", "{usersavedgames}", "{userappdata}",
                                                     "{localappdata}", "{%USERPROFILE}\\AppData\\LocalLow", "{app}"], dests)
    for bad, why in [({"n": 1, "name": "a.txt", "place": "C:\\Windows"}, "a place Rialto does not know"),
                     ({"n": 1, "name": "a;b.txt", "place": "Documents"}, "a name Inno would read as syntax"),
                     ({"n": 1, "name": "..\\a.txt", "place": "Documents"}, "a name that is a path"),
                     ({"n": "x", "name": "a.txt", "place": "Documents"}, "a number that is not one"),
                     ("row", "a row that is not a row")]:
        says("left out: %s" % why, lines([bad]) == [])
    says("a manifest that is not a list places nothing", lines({"n": 1}) == [] and lines(None) == [])
    print()

    print("3. staging, beside the build folder")
    work = tempfile.mkdtemp(prefix="rialto_b10t_")
    try:
        out, mine = os.path.join(work, "output", "Game"), os.path.join(work, "mine")
        os.makedirs(out)
        os.makedirs(os.path.join(mine, "saves", "slot1"))
        open(os.path.join(mine, "mod.ini"), "w").write("x")
        open(os.path.join(mine, "saves", "slot1", "s.dat"), "w").write("y")
        root = ns["placed_files_root"](out)
        os.makedirs(os.path.join(root, "9"))
        open(os.path.join(root, "9", "stale.txt"), "w").write("old build")
        log = []
        host.update_status = log.append
        host.current_game_path = mine  # sources come from inside the game folder
        host.placed_files = [
            {"source": os.path.join(mine, "mod.ini"), "place": "Documents", "subfolder": "Mod"},
            {"source": os.path.join(mine, "gone.txt"), "place": "Documents"},
            {"source": os.path.join(mine, "saves"), "place": "AppData Local", "keep": True, "remove": False}]
        manifest = ns["stage_placed_files"](host, out)
        says("beside the build folder, not in it", root == os.path.join(work, "output", ".rialto-placed")
             and not os.path.exists(os.path.join(out, ".rialto-placed")))
        says("an earlier build's files are gone", not os.path.exists(os.path.join(root, "9")))
        says("a file and a folder staged, numbered by row",
             os.path.isfile(os.path.join(root, "1", "mod.ini")) and os.path.isfile(os.path.join(root, "3", "slot1", "s.dat")))
        says("a missing source is reported and left out", [m["n"] for m in manifest] == [1, 3]
             and any("not found" in m for m in log), log)
        says("the manifest is what the installer reads",
             json.load(open(os.path.join(root, "placed.json"))) == manifest)

        host.generate_enhanced_installer_script(out, {"Title": "T", "Developer": "D"})
        script = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        placed = [l for l in tis.directives(script, "Files") if "rialto-placed" in l]
        says("the installer places both", len(placed) == 2, placed)
        host.placed_files = []
        ns["stage_placed_files"](host, out)
        host.generate_enhanced_installer_script(out, {"Title": "T", "Developer": "D"})
        script = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        says("none asked for: the 1.5.0 installer, and an empty manifest so no old one is read again",
             "rialto-placed" not in script and json.load(open(os.path.join(root, "placed.json"))) == [])
        says("the game's own wildcard is the 1.5.0 one", "check_runtime.bat,game\\saves\\*" in script)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()

    print("4. a shared profile cannot place an attacker's file (1.5.1 security review)")
    problem = ns["placed_row_problem"]
    work = tempfile.mkdtemp(prefix="rialto_b10s_")
    try:
        game = os.path.join(work, "Game")
        os.makedirs(os.path.join(game, "extras", "cfg"))
        for name in ("mod.ini", "evil.lnk", "tool.exe"):
            open(os.path.join(game, "extras", name), "w").write("x")
        open(os.path.join(work, "outside.ini"), "w").write("x")
        ok = lambda row: problem(row, game) == ""
        row = lambda src, place="Documents", sub="": {"source": src, "place": place, "subfolder": sub}
        says("a file inside the game folder, to Documents", ok(row(os.path.join(game, "extras", "mod.ini"), sub="MyStudio\\MyGame")))
        says("refused: a network share", "network share" in problem(row("\\\\evil\\s\\x.ini"), game))
        says("refused: outside the game folder", "outside your game folder" in problem(row(os.path.join(work, "outside.ini")), game))
        says("refused: a relative path", "full path" in problem(row("extras\\mod.ini"), game))
        says("refused: .. back out of the game folder",
             "outside" in problem(row(os.path.join(game, "..", "outside.ini")), game))
        for sub in ("Microsoft\\Windows\\Start Menu\\Programs\\Startup", "Microsoft\\Word\\STARTUP",
                    "Programs\\Startup", "WindowsPowerShell", "Microsoft\\WindowsApps"):
            says("refused: the folder %s" % sub, "starts programs" in problem(
                row(os.path.join(game, "extras", "mod.ini"), "AppData Roaming", sub), game))
        says("refused: a shortcut outside the install folder",
             "install folder" in problem(row(os.path.join(game, "extras", "evil.lnk")), game))
        says("refused: a program outside the install folder",
             "install folder" in problem(row(os.path.join(game, "extras", "tool.exe"), "AppData Local", "Tools"), game))
        says("a program into the install folder is fine",
             ok(row(os.path.join(game, "extras", "tool.exe"), "The install folder", "bin")))
        says("a place Rialto does not know is refused", "place" in problem(row(os.path.join(game, "extras", "mod.ini"), "C:\\Windows"), game))

        # A folder: nothing in it that runs goes outside {app}, and a link is never followed out.
        made = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(game, "extras", "cfg", "escape"), work],
                              capture_output=True, text=True).returncode == 0
        out = os.path.join(work, "output", "Game")
        os.makedirs(out)
        log = []
        host.update_status = log.append
        host.current_game_path = game
        host.placed_files = [row(os.path.join(game, "extras"), "Saved Games", "Game")]
        manifest = ns["stage_placed_files"](host, out)
        staged = os.path.join(ns["placed_files_root"](out), "1")
        says("the folder's data is placed", os.path.isfile(os.path.join(staged, "mod.ini")))
        says("its program and shortcut are left out of a place outside the install folder",
             not os.path.exists(os.path.join(staged, "tool.exe")) and not os.path.exists(os.path.join(staged, "evil.lnk")))
        if made:
            says("a junction inside it is not followed out of the game folder",
                 not os.path.exists(os.path.join(staged, "cfg", "escape")))
        else:
            print("  [SKIP] could not make a junction here")
        says("every row is said in the log", any("Will place on the player's PC" in line for line in log), log)
        host.placed_files = [row("\\\\evil\\s\\x.lnk", "AppData Roaming", "Microsoft\\Windows\\Start Menu\\Programs\\Startup")]
        says("the review's attack row is never staged", ns["stage_placed_files"](host, out) == [])
        says("and the installer it would have made places nothing",
             ns["placed_files_lines"]([{"n": 1, "name": "x.lnk", "place": "AppData Roaming",
                                        "subfolder": "Microsoft\\Windows\\Start Menu\\Programs\\Startup"}]) == [])
    finally:
        subprocess.run(["cmd", "/c", "rmdir", os.path.join(work, "Game", "extras", "cfg", "escape")], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
    flat = src.replace("\r\n", "\n")
    says("the pre-build check refuses a bad row before anything is copied",
         "problem = placed_row_problem(row, game_path)" in flat)
    print()

    print("5. Rialto keeps the rows with the profile")
    says("saved with the profile", 'profile_data["PlacedFiles"] = self.placed_files' in src)
    says("read back on load and on restore, rows only",
         src.count('self.placed_files = [r for r in profile_data.get("PlacedFiles", []) or [] if isinstance(r, dict)]') == 2)
    says("cleared for a new profile", "        self.placed_files = []\n        self.refresh_game_exes_summary()" in src.replace("\r\n", "\n"))
    says("the build stages them before the installer script",
         src.index("self.stage_placed_files(output_path)") < src.index("self.generate_enhanced_installer_script(output_path, meta)"))

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll placed-file checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
