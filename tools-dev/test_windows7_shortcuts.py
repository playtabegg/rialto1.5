"""Windows 7 and 8: the shortcuts start the game itself (1.5.1, B8).

Setup allows Windows 7 (MinVersion=6.1), but every menu.exe is frozen with
Python 3.12, which needs Windows 8.1. So the installer's shortcuts split by
version: the menu entries carry MinVersion 6.3, and a second set that starts
the game named in the staged menu_config.json carries OnlyBelowVersion 6.3.

The generator runs on the same stub test_installer_script.py builds, with a
real menu_config.json staged beside it, so no tkinter and no ISCC are needed.
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_installer_script as tis  # noqa: E402

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def build(host, config, icon=False, title="Rocket Pals"):
    """installer.iss for a build whose staged menu config is `config` (None: none staged)."""
    out = tempfile.mkdtemp(prefix="rialto_w7_")
    try:
        if config is not None:
            os.makedirs(os.path.join(out, "menu"))
            with open(os.path.join(out, "menu", "menu_config.json"), "w", encoding="utf-8") as f:
                json.dump(config, f)
        meta = {"Title": title, "Developer": "D"}
        if icon:
            ico = os.path.join(out, "src.ico")
            open(ico, "wb").write(b"\0\0\1\0")
            meta["Icon"] = ico
        host.generate_enhanced_installer_script(out, meta)
        return open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def lines(script, section):
    return tis.directives(script, section)


def menu_lines(script, section):
    return [l for l in lines(script, section) if "menu\\menu.exe" in l]


def game_lines(script, section):
    return [l for l in lines(script, section) if "menu\\menu.exe" not in l]


def main():
    src = open(tis.RIALTO, encoding="utf-8").read()
    host, ns = tis.build_host(src)
    rel, params = ns["iss_relative_exe"], ns["iss_parameters"]

    print("1. nothing staged: the 1.5.0 shortcuts, on every Windows")
    script = build(host, None)
    says("two menu shortcuts and one Launch, no version gate",
         len(menu_lines(script, "Icons")) == 2 and len(menu_lines(script, "Run")) == 1
         and "Version:" not in script)
    says("and no game shortcut", not game_lines(script, "Icons") and not game_lines(script, "Run"))
    print()

    print("2. one game at the root")
    script = build(host, {"game_exe": "Game.exe", "games": []})
    says("the menu shortcuts and Launch are for Windows 8.1 and later",
         all(l.endswith("; MinVersion: 6.3") for l in menu_lines(script, "Icons") + menu_lines(script, "Run")))
    icons = game_lines(script, "Icons")
    says("Windows 7 and 8 get a Start Menu and a desktop shortcut to the game", icons == [
        'Name: "{group}\\Rocket Pals"; Filename: "{app}\\Game.exe"; WorkingDir: "{app}"; OnlyBelowVersion: 6.3',
        'Name: "{userdesktop}\\Rocket Pals"; Filename: "{app}\\Game.exe"; WorkingDir: "{app}"; Tasks: desktopicon; OnlyBelowVersion: 6.3',
    ], icons)
    says("and the finish page's Launch box starts the game there", game_lines(script, "Run") == [
        'Filename: "{app}\\Game.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram}"; '
        'Flags: nowait postinstall skipifsilent; OnlyBelowVersion: 6.3'], game_lines(script, "Run"))
    says("the desktop shortcut still follows the player's tick box",
         all("Tasks: desktopicon" in l for l in lines(script, "Icons") if "{userdesktop}" in l))
    print()

    print("3. an Unreal game: started from its own folder, as the menu starts it")
    script = build(host, {"game_exe": "Rocket/Binaries/Win64/Rocket-Win64-Shipping.exe"})
    says("the nested exe and its folder", all(
        'Filename: "{app}\\Rocket\\Binaries\\Win64\\Rocket-Win64-Shipping.exe"; '
        'WorkingDir: "{app}\\Rocket\\Binaries\\Win64"' in l for l in game_lines(script, "Icons")))
    print()

    print("4. the game's icon when there is one, else the exe's own")
    with_icon = build(host, {"game_exe": "Game.exe"}, icon=True)
    says("game_icon.ico on every Windows 7 shortcut",
         all('IconFilename: "{app}\\game_icon.ico"' in l for l in game_lines(with_icon, "Icons")))
    says("no IconFilename without one", all("IconFilename" not in l for l in game_lines(
        build(host, {"game_exe": "Game.exe"}), "Icons")))
    print()

    print("5. compatibility mode: one more Start Menu shortcut with its arguments")
    script = build(host, {"game_exe": "Game.exe", "compat_mode": True, "compat_args": ["-force-d3d9", "-mode", "open gl"]})
    compat = [l for l in game_lines(script, "Icons") if "Compatibility Mode" in l]
    says("one, in the Start Menu, arguments quoted Inno's way", compat == [
        'Name: "{group}\\Rocket Pals (Compatibility Mode)"; Filename: "{app}\\Game.exe"; WorkingDir: "{app}"; '
        'Parameters: "-force-d3d9 -mode ""open gl"""; OnlyBelowVersion: 6.3'], compat)
    says("compat off: none", not any("Compatibility" in l for l in game_lines(
        build(host, {"game_exe": "Game.exe", "compat_mode": False, "compat_args": ["-x"]}), "Icons")))
    says("an argument Inno would read as syntax drops the whole set",
         not any("Compatibility" in l for l in game_lines(build(host, {
             "game_exe": "Game.exe", "compat_mode": True, "compat_args": ["-a", '{cmd}']}), "Icons")))
    print()

    print("6. several games: one shortcut each, no Launch box on Windows 7")
    script = build(host, {"game_exe": "", "games": [
        {"name": "Alpha Demo", "exe": "alpha/Alpha.exe"},
        {"name": "Alpha Demo", "exe": "alpha2/Alpha.exe"},
        {"name": "Bad", "exe": "../../Windows/System32/cmd.exe"},
        {"name": None, "exe": "beta/Beta.exe"}]})
    names = re.findall(r'Name: "\{group\}\\([^"]*)"', "\n".join(game_lines(script, "Icons")))
    says("named per game, a repeat numbered, a nameless one after its exe",
         names == ["Alpha Demo", "Alpha Demo (2)", "Beta"], names)
    says("the unsafe entry is left out", "cmd.exe" not in script)
    says("no Windows 7 Launch box for a choice of games", game_lines(script, "Run") == [])
    one = build(host, {"game_exe": "", "games": [{"name": "Solo", "exe": "solo/Solo.exe"}]})
    says("a list of one is the single-game case, under the disc's title",
         'Name: "{group}\\Rocket Pals"; Filename: "{app}\\solo\\Solo.exe"' in one
         and len(game_lines(one, "Run")) == 1)
    print()

    print("7. exe paths that are not a plain relative .exe are refused")
    for bad in ["../../Windows/System32/cmd.exe", "..\\x.exe", "C:/Windows/notepad.exe", "/abs.exe",
                "\\\\server\\share\\x.exe", "game.bat", "a{b}.exe", "x;y.exe", 'q".exe',
                "a\n[Run]\nb.exe", "./.exe", "dir/./Game.exe", "dir//Game.exe", "", None, 7]:
        says("refused: %s" % ascii(bad), rel(bad) == "")
    for good, want in [("Game.exe", "Game.exe"), ("a b/My Game.EXE", "a b\\My Game.EXE"),
                       ("Spiel/Größe.exe", "Spiel\\Größe.exe")]:
        says("kept: %s" % ascii(good), rel(good) == want, rel(good))
    script = build(host, {"game_exe": "../../Windows/System32/cmd.exe"})
    says("with nothing safe to name, the 1.5.0 shortcuts stand", "Version:" not in script and "cmd.exe" not in script)
    print()

    print("8. Parameters on their own")
    says("plain", params(["-a", "-b"]) == "-a -b")
    says("a space is quoted", params(["C:\\My Saves"]) == '""C:\\My Saves""')
    says("not a list", params("-a") == "")
    says("a semicolon refuses the set", params(["-a", "b;c"]) == "")
    print()

    print("9. whatever the config says, every target is the menu or a game under {app}")
    script = build(host, {"game_exe": "Game.exe\n[Run]\nFilename: \"cmd.exe\"", "games": [
        {"name": "x\"; Filename: \"cmd.exe", "exe": "ok/Ok.exe"}], "compat_mode": True,
        "compat_args": ["\"; Filename: \"cmd.exe"]})
    targets = re.findall(r'(?<![A-Za-z])Filename:\s*"([^"]*)"', script)
    says("only {app}\\menu\\menu.exe and {app}\\ok\\Ok.exe",
         set(targets) == {"{app}\\menu\\menu.exe", "{app}\\ok\\Ok.exe"}, sorted(set(targets)))
    says("one [Run] section, one [Icons] section",
         script.count("[Run]") == 1 and script.count("[Icons]") == 1)
    says("a quote in a name never closes the field", all(l.count('"') % 2 == 0 for l in lines(script, "Icons")))

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll Windows 7 shortcut checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
