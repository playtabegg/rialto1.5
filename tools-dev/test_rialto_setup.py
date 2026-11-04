"""Rialto's own Setup (packaging/rialto-setup.iss) on an upgrade (1.5.2).

Each version names its shortcuts for itself ("Rialto 1.5.1", then "Rialto 1.5.2"), so an upgrade must
remove the earlier version's shortcuts that start this install's Rialto.exe, and nothing else. And
AppName carries the version too, so Inno's own "%1 is currently running" would name the new version
while the old one is the one open: the script says it without a version.

The script is read as text, and compiled for real by an Inno Setup on this PC when there is one (the
one Rialto carries in helpers\\inno first), against a folder of stand-in files. Nothing is installed
and nothing runs: Setup itself would touch the real Start Menu.

Usage: python tools-dev/test_rialto_setup.py [path-to-rialto1.5]
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISS = os.path.join(REPO, "packaging", "rialto-setup.iss")

failures = []


def ok(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label, (" -> %r" % (detail,)) if not condition and detail != "" else ""))
    if not condition:
        failures.append(label)


def section(script, name):
    """The lines of one [Section], up to the next."""
    match = re.search(r"^\[%s\]\s*$(.*?)(?=^\[[A-Za-z]+\]\s*$|\Z)" % re.escape(name), script, re.M | re.S)
    return match.group(1) if match else ""


def pascal(code, name):
    """One function or procedure of [Code], from its header to the next one's."""
    match = re.search(r"^(?:function|procedure) %s\b.*?(?=^(?:function|procedure) |\Z)" % name, code, re.M | re.S)
    return match.group(0) if match else ""


def find_iscc():
    for path in (os.path.join(REPO, "helpers", "inno", "ISCC.exe"),
                 os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Inno Setup 6", "ISCC.exe"),
                 os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Inno Setup 6", "ISCC.exe"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")):
        if path and os.path.isfile(path):
            return path
    return None


with open(ISS, encoding="utf-8") as f:
    script = f.read()
code = section(script, "Code")

print("1. the running-Rialto message names no version")
messages = section(script, "Messages")
running = re.findall(r"^SetupAppRunningError=(.*)$", messages, re.M)
ok("[Messages] sets SetupAppRunningError once", len(running) == 1, running)
said = running[0] if running else ""
ok("without %1 (the AppName, \"Rialto 1.5.2\") and without any version",
   "%1" not in said and "{#AppVersion}" not in said and not re.search(r"[0-9]\.[0-9]", said), said)
ok("it names Rialto and says what to do", "Rialto" in said and "Close Rialto" in said and "OK" in said, said)
ok("plain words: no em dash, no exclamation", "\u2014" not in said and "!" not in said, said)
ok("AppName still carries the version, which is why", "AppName=Rialto {#AppVersion}" in script)
print()

print("2. an upgrade removes the earlier version's shortcuts that start this Rialto.exe")
step = pascal(code, "CurStepChanged")
ok("after the files and shortcuts are in place (ssPostInstall)", "CurStep = ssPostInstall" in step, step)
ok("in the Start Menu and on the desktop, the two places [Icons] puts them",
   "RemoveEarlierShortcuts(ExpandConstant('{autoprograms}'))" in step
   and "RemoveEarlierShortcuts(ExpandConstant('{autodesktop}'))" in step, step)
ok("never in the release check's throwaway install (/NOSHORTCUTS)", "WantShortcuts" in step, step)
icons = section(script, "Icons")
ok("[Icons] puts this version's shortcuts in those same two places",
   "{autoprograms}\\{#ShortcutName}" in icons and "{autodesktop}\\{#ShortcutName}" in icons, icons)
remove = pascal(code, "RemoveEarlierShortcuts")
ok("this version's own shortcut is kept", "CompareText(F.Name, '{#ShortcutName}.lnk') <> 0" in remove, remove)
ok("only Rialto's earlier names: \"Rialto 1.x\" and the plain \"Rialto\"",
   "'Rialto*.lnk'" in remove and "CompareText(F.Name, 'Rialto.lnk') = 0" in remove
   and "Pos('RIALTO 1.', Uppercase(F.Name)) = 1" in remove, remove)
ok("and only one that starts this install's Rialto.exe", "StartsThisRialto(" in remove, remove)
ok("the list is made first and deleted after, never while the folder is being read",
   "FindClose(F)" in remove and "DeleteFile(" in remove
   and remove.index("FindClose(F)") < remove.index("DeleteFile("), remove)
starts = pascal(code, "StartsThisRialto")
ok("the shortcut's target is this install's Rialto.exe, read through Windows' own shortcut object",
   "CreateOleObject('WScript.Shell')" in starts
   and "CompareText(Target, ExpandConstant('{app}\\Rialto.exe')) = 0" in starts, starts)
ok("with nothing after it (a shortcut that starts Rialto with arguments is someone's own)",
   "Trim(Arguments) = ''" in starts, starts)
ok("a shortcut Windows cannot read is left alone", "except" in starts and "Result := False;" in starts, starts)
ok("no [Code] line starts with \"[\" (ISCC would read it as a section)",
   not re.search(r"^\[", code, re.M), [line for line in code.splitlines() if line.startswith("[")])
print()

print("3. the script compiles")
iscc = find_iscc()
if not iscc:
    print("  [--  ] no Inno Setup on this PC: the compile is skipped")
else:
    inno = os.path.dirname(iscc)
    default_isl = os.path.join(inno, "Default.isl")
    if os.path.isfile(default_isl):
        with open(default_isl, encoding="utf-8", errors="replace") as f:
            ok("SetupAppRunningError is one of Inno's own message names", re.search(r"^SetupAppRunningError=", f.read(), re.M))
    work = tempfile.mkdtemp(prefix="rialto_setup_")
    try:
        package = os.path.join(work, "package")
        for rel in ("Rialto.exe", "menu.exe", "README.txt", "IMPORTANT - Before You Build.txt", "licenses/LICENSE.txt",
                    "input/SampleGame/PUT YOUR GAME FILES HERE.txt", "input/SampleGame/background.gif",
                    "input/SampleGame/game_logo.png", "input/SampleGame/game_icon.ico", "input/SampleGame/disc_icon.ico",
                    "input/SampleGame/bonus/Sample Wallpaper.jpg", "templates/Sample Game.json"):
            path = os.path.join(package, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("stand-in\n")
        # The stand-in Rialto.exe carries no version resource, so this copy alone skips the check that
        # Rialto.exe is the version being built for. Nothing else is changed.
        guard = '#if ExeVersion != AppVersion + ".0"'
        ok("the copy changes only the version guard", script.count(guard) == 1)
        copy = os.path.join(work, "rialto-setup.iss")
        with open(copy, "w", encoding="utf-8") as f:
            f.write(script.replace(guard, "#if 0"))
        result = subprocess.run([iscc, "/Q", "/DPackageDir=" + package, "/DAppVersion=1.5.2", "/O" + work, copy],
                                capture_output=True, text=True, errors="replace", timeout=300,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ok("ISCC (%s) compiles it" % iscc, result.returncode == 0, (result.stdout + result.stderr).strip()[-600:])
        ok("into Rialto-1.5.2-Setup.exe", os.path.isfile(os.path.join(work, "Rialto-1.5.2-Setup.exe")))
    finally:
        shutil.rmtree(work, ignore_errors=True)
print()

if failures:
    for item in failures:
        print("FAIL:", item)
    sys.exit(1)
print("OK: Rialto's Setup removes the earlier version's shortcuts and names no version when Rialto is open")
