"""The game's own name on every surface, the store's format kept off (4 Nov 2026).

A developer's ask: a store names the format after the
title, "Moth Lamp (PC CD)", and that is for the store page. Typed into Game
Title it put "Moth Lamp PC CD" on the player's shortcuts. player_title() takes
one format off, by the factory's own rule, and every name the player sees
goes through it: Setup and its
uninstall entry, the install folder, Start Menu and desktop shortcuts (Windows
7 ones too), the disc menu's title and ADD TO STEAM's name, the Mac and Linux
packages and their START HERE, README, autorun, the disc's label, menu.bat, the
USB and multi-disc notes and the .msix. The Game Title box, the master sheet
and the build log keep what the developer typed.

The install's identity is the factory's design too: the game's name, so two
titles of one game are one install, unless the PC has a disc installed from
before under the title as typed, or the game's name in another format the
store sells, which is then installed over, found by Inno's own key (shortened
past 57 characters) where Setup looks for it (the user's keys, or the
machine's with /ALLUSERS).

Both are proved on the factory's own vectors, store_title_vectors.json and
install_identity_vectors.json beside this file, the factory's own with the
game names changed: copy them again whenever the factory's change.

Source-extracted and run on stubs, as the other harnesses are: no tkinter or Qt
window, no ISCC, no disc tool.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import progress_stub  # noqa: E402
import test_image_tool_chain as tic  # noqa: E402
import test_installer_script as tis  # noqa: E402
import test_steam_shortcuts as tss  # noqa: E402

RIALTO = tis.RIALTO
STORE = "Moth Lamp (PC CD)"
NAME = "Moth Lamp"
failures = []
# [store_title, game_name] pairs, and {inno_keys, cases}: Inno's key for an identity, and what Setup answers on a
# PC holding the installs a case lists (its "about" says how to read them).
TITLE_VECTORS = json.load(open(os.path.join(HERE, "store_title_vectors.json"), encoding="utf-8"))
IDENTITY_VECTORS = json.load(open(os.path.join(HERE, "install_identity_vectors.json"), encoding="utf-8"))
UNINSTALL = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
CHECK = re.compile(r"if RegKeyExists\(RootKey, '((?:[^']|'')*)'\) then\n    Result := (\d+)")
ANSWER = re.compile(r"^    (\d+): Result := '((?:[^']|'')*)';$", re.M)
OTHERWISE = re.compile(r"^  else\n    Result := '((?:[^']|'')*)';\n  end;$", re.M)
#: The factory's [Code] for Moth Lamp (PC CD), line for line (the factory's own test disc).
FACTORY_CODE = ["[Code]", "var", "  EarlierGroupName: String;", "", "function EarlierInstall: Integer;", "var",
                "  RootKey: Integer;", "begin", "  if IsAdminInstallMode then", "    RootKey := HKLM", "  else",
                "    RootKey := HKCU;", "  if RegKeyExists(RootKey, '%s\\Moth Lamp_is1') then\n    Result := 0" % UNINSTALL] + [
    "  else if RegKeyExists(RootKey, '%s\\Moth Lamp (%s)_is1') then\n    Result := %d" % (
        UNINSTALL, f, i) for i, f in enumerate(
        ("PC CD", "PC DVD", "PC CD+Soundtrack CD", "PC DVD+Soundtrack CD"), start=1)] + [
    "  else", "    Result := 0;", "end;", "", "function FoundEarlier: Boolean;", "begin",
    "  Result := EarlierInstall <> 0;", "end;", "", "function IsEarlier(Which: Integer): Boolean;", "begin",
    "  Result := EarlierInstall = Which;", "end;", "", "function InstallIdentity(Param: String): String;", "begin",
    "  case EarlierInstall of", "    1: Result := 'Moth Lamp (PC CD)';", "    2: Result := 'Moth Lamp (PC DVD)';",
    "    3: Result := 'Moth Lamp (PC CD+Soundtrack CD)';", "    4: Result := 'Moth Lamp (PC DVD+Soundtrack CD)';",
    "  else", "    Result := 'Moth Lamp';", "  end;", "end;", "", "function EarlierGroup(Param: String): String;",
    "begin", "  if EarlierGroupName = '' then", "    Result := ExpandConstant('{group}')", "  else",
    "    Result := ExpandConstant('{autoprograms}\\') + EarlierGroupName;", "end;", "", "procedure InitializeWizard;",
    "begin", "  if FoundEarlier then", "  begin", "    EarlierGroupName := WizardForm.GroupEdit.Text;",
    "    WizardForm.GroupEdit.Text := 'Moth Lamp';", "  end;", "end;"]


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def methods(src, names):
    found = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == "RialtoApp":
            for item in node.body:
                if (isinstance(item, ast.FunctionDef) and item.name in names) \
                        or (isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") in names):
                    found[getattr(item, "name", None) or item.targets[0].id] = \
                        textwrap.dedent(ast.get_source_segment(src, item))
    missing = set(names) - set(found)
    if missing:
        raise SystemExit("could not extract %s" % sorted(missing))
    return [found[n] for n in names]


def module_closure(src, used_names):
    """Module-level functions and constants the methods lean on, and theirs in turn."""
    defs = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            defs[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defs[target.id] = node
    wanted, queue, seen = [], [n for n in used_names if n in defs], set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        node = defs[name]
        if node not in wanted:
            wanted.append(node)
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and inner.id in defs and inner.id not in seen:
                queue.append(inner.id)
    wanted.sort(key=lambda n: n.lineno)
    return "\n\n".join(ast.get_source_segment(src, n) for n in wanted)


def host(src, names, extra="", **attrs):
    """A stub carrying the real methods named (and `extra`, class-body source), and the module code they read."""
    bodies = methods(src, names) + ([extra] if extra else [])
    used = {n.id for body in bodies for n in ast.walk(ast.parse(body)) if isinstance(n, ast.Name)}
    ns = dict(progress_stub.namespace(), sys=sys, re=re, json=json)
    exec(module_closure(src, used), ns)
    exec("class Host:\n" + textwrap.indent("\n\n".join(bodies), "    "), ns)
    obj = ns["Host"]()
    obj.log = []
    obj.update_status = obj.log.append
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj, ns


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def form(title=STORE):
    """The form as a developer leaves it: Start Menu Name and Disc Name followed the title."""
    return {"Title": Var(title), "Developer": Var("Larkin"), "Publisher": Var(""), "Start Menu Name": Var(title)}


def body_of(src, name):
    return "\n".join(methods(src, [name]))


def code_of(script):
    """The [Code] section's lines, from its header to the next section or the end."""
    lines = script.splitlines()
    if "[Code]" not in lines:
        return []
    start = lines.index("[Code]")
    end = next((i for i in range(start + 1, len(lines)) if re.fullmatch(r"\[\w+\]", lines[i])), len(lines))
    return lines[start:end]


def app_id(script, held, mode="user"):
    """The AppId Setup takes from `script` on a PC holding `held` ((root, key under Uninstall)): [Code] as Inno runs it.

    Setup reads an earlier install only under the root it installs to: the user's, or with /ALLUSERS the machine's.
    """
    setup = tis.directives(script, "Setup")
    if not setup[0].startswith("AppId="):
        # No AppId: Inno takes AppName, as ISCC reads a directive, its ends trimmed.
        return next(line for line in setup if line.startswith("AppName="))[len("AppName="):].strip()
    if setup[0] != "AppId={code:InstallIdentity}":
        return setup[0][len("AppId="):]
    code = "\n".join(code_of(script))
    root = "HKLM" if mode == "all users" else "HKCU"
    # The registry does not tell case apart in a key's name.
    keys = {(r, key.casefold()) for r, key in held}
    answers = {index: answer.replace("''", "'") for index, answer in ANSWER.findall(code)}
    otherwise = OTHERWISE.findall(code)[0].replace("''", "'")
    for key, index in CHECK.findall(code):
        if (root, key.replace("''", "'")[len(UNINSTALL) + 1:].casefold()) in keys:
            return answers.get(index, otherwise)  # 0 is this disc's own install
    return otherwise


def main():
    src = open(RIALTO, encoding="utf-8").read()
    names_ns = {"re": re}
    exec(module_closure(src, {"player_title", "is_store_format", "store_format_note"}), names_ns)
    player_title, note = names_ns["player_title"], names_ns["store_format_note"]
    is_store_format = names_ns["is_store_format"]
    work = tempfile.mkdtemp(prefix="rialto_monik_")
    try:
        print("1. the rule: the factory's, proved on the factory's own %d vectors" % len(TITLE_VECTORS))
        wrong = [(store, name, player_title(store)) for store, name in TITLE_VECTORS if player_title(store) != name]
        says("player_title gives the factory's game_name for every pair in store_title_vectors.json", not wrong,
             wrong[:5])
        says("and there are enough of them to mean it",
             len({tuple(pair) for pair in TITLE_VECTORS}) >= 80, len(TITLE_VECTORS))
        # A format comes off only in a bracket or after a spaced dash: a bare word at the end is part of a name.
        for title in ["Home PC", "Big Mac", "Escape from Linux", "Mac & PC", "The Last PC CD", "Moth Lamp PC CD"]:
            says("kept whole: %r" % title, [title, title] in TITLE_VECTORS and player_title(title) == title,
                 player_title(title))
        says("the developer's own characters, never NFKC's: Moth Lamp\u2122",
             player_title("Moth Lamp\u2122 (PC CD)") == "Moth Lamp\u2122", player_title("Moth Lamp\u2122 (PC CD)"))
        says("Final Fantasy \u2166 keeps its numeral",
             player_title("Final Fantasy \u2166 (PC DVD)") == "Final Fantasy \u2166",
             player_title("Final Fantasy \u2166 (PC DVD)"))
        says("is_store_format reads full-width words as NFKC does",
             is_store_format("\uff30\uff23 \uff23\uff24") and not is_store_format("Remastered"))
        long_one = "pc " * 50000 + "x"
        says("a hostile title ends quickly and whole", player_title(long_one) == long_one)
        says("so does a long run of bare format words", player_title("Moth Lamp" + " PC" * 20) == "Moth Lamp" + " PC" * 20)
        says("only one format comes off, however many there are",
             player_title("Moth Lamp (PC CD) (PC CD)") == "Moth Lamp (PC CD)")
        says("no title at all is no title", player_title(None) == "")
        print()

        print("2. Setup: the game's name everywhere, one install per game")
        iss_host, iss_ns = tis.build_host(src)

        def iss(title, start_menu=None, config=None):
            out = tempfile.mkdtemp(prefix="iss_", dir=work)
            if config is not None:
                os.makedirs(os.path.join(out, "menu"))
                with open(os.path.join(out, "menu", "menu_config.json"), "w", encoding="utf-8") as f:
                    json.dump(config, f)
            iss_host.generate_enhanced_installer_script(
                out, {"Title": title, "Developer": "Larkin",
                      "Start Menu Name": title if start_menu is None else start_menu})
            return open(os.path.join(out, "installer.iss"), encoding="utf-8").read()

        config = {"game_exe": "MothLamp.exe", "compat_mode": True, "compat_args": ["-force-d3d9"]}
        script = iss(STORE, config=config)
        setup = tis.directives(script, "Setup")
        for line in ("AppName=Moth Lamp", "UninstallDisplayName=Moth Lamp", "DefaultDirName=C:\\Games\\Moth Lamp",
                     "DefaultGroupName=Moth Lamp"):
            says(line, line in setup, setup)
        icons = tis.directives(script, "Icons")
        shortcut_names = re.findall(r'^Name: "\{(?:group|userdesktop)\}\\([^"]*)"', "\n".join(icons), re.M)
        says("every shortcut, the menu's and Windows 7's, is named Moth Lamp",
             shortcut_names == [NAME, NAME, NAME, NAME, "Moth Lamp (Compatibility Mode)"], shortcut_names)
        says("the store's format is on no name the player sees",
             not any("PC CD" in l for l in setup + icons), setup + icons)
        says("the identity is decided on the PC: AppId={code:InstallIdentity}, first in [Setup]",
             setup[0] == "AppId={code:InstallIdentity}", setup[:2])
        says("with UsePreviousLanguage=no, without which ISCC refuses it", "UsePreviousLanguage=no" in setup)
        code = code_of(script)
        says("[Code] is the factory's, line for line: this disc's own install, the title as typed, then the game's "
             "name in each store format",
             "\n".join(code) == "\n".join(FACTORY_CODE), code)
        says("it looks where Setup looks: the user's keys, or the machine's with /ALLUSERS",
             "HKCU, '" not in "\n".join(code) and "HKLM, '" not in "\n".join(code))
        says("an earlier install's Start Menu folder is offered under the game's name",
             "    WizardForm.GroupEdit.Text := 'Moth Lamp';" in code)
        says("one [Code], and no IsWin64 of its own", script.count("[Code]") == 1 and "function IsWin64" not in script)

        # What this disc wrote before 4 Nov: the same generator, the title passed through untouched.
        before_ns = dict(iss_ns, player_title=lambda value: value, earlier_installs=lambda title, name: [])
        exec("class Before:\n" + textwrap.indent(
            textwrap.dedent(body_of(src, "generate_enhanced_installer_script")), "    "), before_ns)
        before = before_ns["Before"]()
        before.update_status = lambda message: None
        before.get_disk_slice_size = lambda: None
        out = tempfile.mkdtemp(prefix="iss_before_", dir=work)
        os.makedirs(os.path.join(out, "menu"))
        with open(os.path.join(out, "menu", "menu_config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f)
        before.generate_enhanced_installer_script(out, {"Title": STORE, "Developer": "Larkin", "Start Menu Name": STORE})
        old = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        old_setup = tis.directives(old, "Setup")
        says("the earlier disc wrote no AppId of its own, so its identity was its AppName",
             not any(l.startswith("AppId=") for l in old_setup) and app_id(old, []) == STORE, old_setup[:1])
        says("on a PC with it, Setup answers that AppName and installs over it",
             app_id(script, {("HKCU", STORE + "_is1")}) == app_id(old, set()), app_id(script, {("HKCU", STORE + "_is1")}))
        says("on a PC without it, the game's name", app_id(script, set()) == NAME, app_id(script, set()))
        says("installed for all users, it is not one a per-user Setup upgrades",
             app_id(script, {("HKLM", STORE + "_is1")}) == NAME
             and app_id(script, {("HKLM", STORE + "_is1")}, "all users") == STORE)
        deleted = tis.directives(script, "InstallDelete")
        old_names = re.findall(r'^Name: "\{(?:group|userdesktop)\}\\([^"]*)"', "\n".join(tis.directives(old, "Icons")),
                               re.M)
        says("[InstallDelete] takes away the old-named shortcuts, the ones the earlier disc made", deleted[:3] == [
            'Type: files; Name: "{code:EarlierGroup}\\Moth Lamp (PC CD).lnk"; Check: IsEarlier(1)',
            'Type: files; Name: "{code:EarlierGroup}\\Moth Lamp (PC CD) (Compatibility Mode).lnk"; Check: IsEarlier(1)',
            'Type: files; Name: "{userdesktop}\\Moth Lamp (PC CD).lnk"; Check: IsEarlier(1)'] and
             {n + ".lnk" for n in old_names} == {re.search(r'\\([^"\\]*)"', l).group(1) for l in deleted[:3]},
             (deleted, old_names))
        says("and only where that install is the one upgraded: every line has its Check",
             all(re.search(r"; Check: (IsEarlier\(\d\)|FoundEarlier)$", l) for l in deleted)
             and deleted[-1] == 'Type: dirifempty; Name: "{code:EarlierGroup}"; Check: FoundEarlier', deleted)
        says("one [InstallDelete], one [Icons]", script.count("[InstallDelete]") == 1 and script.count("[Icons]") == 1)

        for plain in ["Juno's Adventure", "Ghosts (Remastered)", "KESTREL - Deluxe Edition"]:
            out = tempfile.mkdtemp(prefix="iss_plain_", dir=work)
            before.generate_enhanced_installer_script(out, {"Title": plain, "Developer": "Larkin",
                                                           "Start Menu Name": plain})
            was = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
            now = iss(plain)
            # The readiness review (4 Nov): a title typed without its format may follow a disc that carried one,
            # so the installer adds only the search for it, and installs under the title as before.
            added = ("AppId={code:InstallIdentity}", "UsePreviousLanguage=no")
            kept = [l for l in re.sub(r"\n\[(InstallDelete|Code)\]\n.*?(?=\n\[\w+\]\n|\Z)", "", now,
                                      flags=re.S).splitlines() if l not in added]
            says("a title without a format writes the installer it always did, and the search: %s" % plain,
                 kept == was.splitlines() and all(a in now for a in added) and app_id(now, set()) == plain
                 and app_id(was, set()) == plain, [l for l in kept if l not in was.splitlines()][:3])
        plain = iss("Juno's Adventure")
        says("and on a PC with a disc from before under the game's name in a store format, Setup installs over it",
             app_id(plain, {("HKCU", "Juno's Adventure (PC CD)_is1")}) == "Juno's Adventure (PC CD)"
             and app_id(plain, {("HKCU", "Juno's Adventure (PC DVD+Soundtrack CD)_is1")})
             == "Juno's Adventure (PC DVD+Soundtrack CD)"
             and app_id(plain, {("HKCU", "Juno's Adventure_is1")}) == "Juno's Adventure",
             app_id(plain, {("HKCU", "Juno's Adventure (PC CD)_is1")}))
        larkin = iss(STORE, start_menu="Larkin Games (PC CD)")
        says("a Start Menu Name the developer typed keeps its words, the format off",
             "DefaultGroupName=Larkin Games" in larkin
             and "    WizardForm.GroupEdit.Text := 'Larkin Games';" in code_of(larkin))
        hostile = iss('{sys} Moth "Lamp"; x (PC CD)')
        says("an identity cannot open an Inno constant or close a field",
             "    1: Result := 'sys Moth Lamp x (PC CD)';" in code_of(hostile)
             and all(l.count('"') % 2 == 0 for l in tis.directives(hostile, "InstallDelete")), code_of(hostile))
        quoted = code_of(iss("Juno's Adventure (PC CD)"))
        says("a quote is doubled as Pascal doubles it", "    1: Result := 'Juno''s Adventure (PC CD)';" in quoted
             and "    Result := 'Juno''s Adventure';" in quoted, quoted)
        long_name = "The Very Long Night of the " + "Lantern " * 12 + "Keeper"
        capped = iss(long_name + " (PC CD)")
        says("a name the 120-character cap makes the same as its title is one install: no [Code], no AppId",
             "[Code]" not in capped and not tis.directives(capped, "Setup")[0].startswith("AppId="),
             tis.directives(capped, "Setup")[:1])
        print()

        print("2b. the install's identity, on the factory's own %d vectors" % len(IDENTITY_VECTORS["cases"]))
        # Each case's installs are discs as Rialto made them: before 4 Nov, AppName (iss_value of the title as
        # typed) was the identity, so the key is Inno's for that, shortened past 57 characters as Inno does.
        iss_value = iss_ns["iss_value"]
        inno_key = iss_ns["inno_uninstall_key"]
        wrong = [(i, k, inno_key(i)) for i, k in IDENTITY_VECTORS["inno_keys"] if inno_key(i) != k]
        says("Inno's key for every identity in the vectors, the factory's own", not wrong, wrong)
        for case in IDENTITY_VECTORS["cases"]:
            site, name, mode = case["site_title"], case["game_name"], case["mode"]
            root = "HKLM" if mode == "all users" else "HKCU"
            script = iss(site)
            own = iss_value(name, "Game").strip()
            pc = {(r, inno_key(own if title is None else iss_value(title, "Game").strip()))
                  for r, title in case["installed"]}
            expected = own if case["answer"] is None else iss_value(case["answer"], "Game").strip()
            answer = app_id(script, pc, mode)
            says("%s: %s" % (case["why"], expected), player_title(site) == name and answer == expected
                 and app_id(script, set(), mode) == own, (answer, sorted(pc)))
            # Setup writes the key of what it answered; asked again in the same Setup, it answers the same.
            says("  and the same answer when Setup asks again",
                 app_id(script, pc | {(root, inno_key(answer))}, mode) == answer)
            looked_for = [(key.replace("''", "'").casefold(), index)
                          for key, index in CHECK.findall("\n".join(code_of(script)))]
            own_key = ("%s\\%s" % (UNINSTALL, inno_key(own))).casefold()
            says("  and this disc's own key first, answering its own identity, never an earlier install's",
                 (not looked_for or looked_for[0] == (own_key, "0"))
                 and [index for key, index in looked_for if key == own_key] in ([], ["0"]), looked_for)
        dvd, cd = iss("Moth Lamp (PC DVD)"), iss(STORE)
        says("two titles of one game are one install in one folder: a disc under each answers Moth Lamp",
             app_id(dvd, set()) == app_id(cd, set()) == NAME and app_id(cd, {("HKCU", NAME + "_is1")}) == NAME
             and all("DefaultDirName=C:\\Games\\Moth Lamp" in tis.directives(s, "Setup") for s in (dvd, cd)))
        says("and either finds a disc from before under the other's title",
             app_id(cd, {("HKCU", "Moth Lamp (PC DVD)_is1")}) == "Moth Lamp (PC DVD)"
             and app_id(dvd, {("HKCU", STORE + "_is1")}) == STORE)
        print()

        print("3. the disc menu: its title, and ADD TO STEAM's name")
        cfg_host, _ = host(src, ["build_menu_config", "menu_theme_config", "menu_theme_font"],
                           entries=form(), company_logo_var=Var(""), publisher_text_var=Var("(c) 2026 Larkin"),
                           remove_wti_branding=Var(True), steam_button_var=Var(True), mod_launcher_var=Var(False),
                           compat_mode_var=Var(False), compat_args_var=Var(""), compat_label_var=Var(""),
                           compat_hint_var=Var(""))
        cfg_host.validated_game_executables = lambda: []
        cfg_host.detect_primary_game_exe = lambda root: "MothLamp.exe"
        config = cfg_host.build_menu_config(work)
        says("menu_config.json's title is Moth Lamp", config["title"] == NAME, config["title"])
        cfg_host.entries = form("Juno's Adventure")
        says("and a title without a format as typed", cfg_host.build_menu_config(work)["title"] == "Juno's Adventure")

        template = ast.literal_eval(next(
            n.value for n in ast.parse(src).body
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))
        reading = [ast.get_source_segment(template, n) for n in ast.parse(template).body
                   if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("_raw_title", "MENU_TITLE")]
        menu_ns = {"MENU_CONFIG": config}
        exec("\n".join(reading), menu_ns)
        says("the menu's caption and on-screen title read it: MENU_TITLE is Moth Lamp",
             menu_ns["MENU_TITLE"] == NAME, menu_ns["MENU_TITLE"])
        says("which is the caption", "self.setWindowTitle(self.menu_title)" in template
             and "self.menu_title = MENU_TITLE" in template)
        steam = os.path.join(work, "steam")
        os.makedirs(steam)
        game_dir, exe = tss.make_disc(steam)
        vdf = os.path.join(steam, "userdata", "111", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = tss.make_menu(steam, game_dir, [vdf], resolved_exe=exe)
        menu.menu_title = menu_ns["MENU_TITLE"]
        menu.add_to_steam()
        data = open(vdf, "rb").read()
        says("ADD TO STEAM names the game Moth Lamp in the player's library",
             b"\x01AppName\x00Moth Lamp\x00" in data and b"PC CD" not in data, data[:120])
        print()

        print("4. the Mac and Linux packages, and their START HERE")
        raw = os.path.join(work, "LinuxRaw")
        os.makedirs(raw)
        open(os.path.join(raw, "MothLamp.x86_64"), "wb").write(b"\x7fELF" + b"\0" * 64)
        pack, _ = host(src, ["package_unix_build", "unix_archive_stem", "_is_unix_executable", "_unix_launch_target",
                             "unix_launcher_script", "write_unix_launcher", "folder_is_already_packaged",
                             "folder_bytes", "UNIX_EXEC_SUFFIXES", "UNIX_ARCHIVE_SUFFIXES", "UNIX_LAUNCH_PRIORITY"],
                       extra=progress_stub.methods(src), entries=form())
        out = os.path.join(work, "Linux")
        os.makedirs(out)
        archive = pack.package_unix_build(raw, out, "Linux")
        says("the archive is Moth Lamp-Linux.tar.gz", archive == "Moth Lamp-Linux.tar.gz", archive)
        with tarfile.open(os.path.join(out, archive)) as tar:
            roots = {m.name.split("/")[0] for m in tar.getmembers()}
        says("and it unpacks to Moth Lamp-Linux", roots == {"Moth Lamp-Linux"}, roots)
        unix, _ = host(src, ["write_unix_instructions"], entries=form())
        unix.write_unix_instructions(out, "Linux", archive=archive)
        unix.write_unix_instructions(os.path.join(work), "Mac", archive="Moth Lamp-Mac.tar.gz")
        for label, folder in (("Linux", out), ("Mac", work)):
            notes = open(os.path.join(folder, "START HERE.txt"), encoding="utf-8").read()
            says("%s START HERE names Moth Lamp" % label,
                 notes.startswith("%s on %s" % (NAME, label)) and "PC CD" not in notes, notes[:60])
        print()

        print("5. the disc: README, autorun, label, menu.bat")
        disc, _ = host(src, ["generate_readme", "generate_autorun", "create_batch_menu_fallback",
                             "create_compatibility_test_script"],
                       entries=form(), disc_name_var=Var(STORE), disc_icon_var=Var(""),
                       remove_wti_branding=Var(False))
        disc.detect_primary_game_exe = lambda root: "MothLamp.exe"
        root = os.path.join(work, "disc")
        os.makedirs(root)
        disc.generate_readme(root, {"Title": STORE})
        disc.generate_autorun(root)
        disc.create_batch_menu_fallback(root)
        disc.create_compatibility_test_script(root)
        readme = open(os.path.join(root, "README.txt"), encoding="utf-8").read()
        says("README.txt: === Moth Lamp === and thank you for buying Moth Lamp!",
             "=== Moth Lamp ===" in readme and "thank you for buying Moth Lamp!" in readme and "PC CD" not in readme)
        autorun = open(os.path.join(root, "autorun.inf"), encoding="cp1252").read()
        says("autorun.inf: Label=Moth Lamp", "Label=Moth Lamp\n" in autorun and "PC CD" not in autorun, autorun)
        bat = open(os.path.join(root, "menu.bat"), encoding="cp1252", errors="replace").read()
        says("menu.bat names Moth Lamp", "MOTH LAMP" in bat and "PC CD" not in bat)
        test_bat = open(os.path.join(root, "compatibility_test.bat"), encoding="cp1252", errors="replace").read()
        says("the compatibility test names Moth Lamp", "Moth Lamp - Compatibility Test" in test_bat
             and "PC CD" not in test_bat)
        disc.disc_name_var = Var("")
        disc.generate_autorun(root)
        autorun = open(os.path.join(root, "autorun.inf"), encoding="cp1252").read()
        says("Disc Name left empty: the label follows the title, and is Moth Lamp", "Label=Moth Lamp\n" in autorun,
             autorun)

        tic.TOOLS[:] = [("mkisofs", tic.MKISOFS, False)]
        image = tic.Host({tic.MKISOFS: "ok"})
        image.disc_name_var = Var(STORE)
        image_out = os.path.join(work, "Moth Lamp")
        image.create_iso(tic.stage(image_out), {"GameName": "MothLamp", "Title": STORE})
        command = image.calls[0][2]
        says("the disc's label in File Explorer is Moth Lamp", command[command.index("-V") + 1] == NAME, command)
        for typed, label in (("Hollow Knight: Silksong (PC DVD)", "Hollow Knight"),
                             ("Grim Fandango Remastered (PC CD)", "Grim Fandango"),
                             ("Paintbox - Squares and Lines", "Paintbox")):
            named = tic.Host({tic.MKISOFS: "ok"})
            named.disc_name_var = Var(typed)
            named.create_iso(tic.stage(image_out), {"GameName": "MothLamp", "Title": typed})
            got = named.calls[0][2][named.calls[0][2].index("-V") + 1]
            says("past 16 characters the label keeps whole words, as the factory's: %s" % label, got == label, got)
        span = tic.Host({tic.MKISOFS: "ok"}, capacity=4 * 1024 * 1024 + tic.NS["Real"].SPAN_MARGIN)
        span.disc_name_var = Var(STORE)
        span.create_iso(tic.stage(image_out, ["setup-1.bin", "setup-2.bin"]), {"GameName": "MothLamp", "Title": STORE})
        multi = open(os.path.join(image_out, "MULTI-DISC README.txt"), encoding="utf-8").read()
        says("MULTI-DISC README.txt: Moth Lamp comes on more than one disc",
             multi.startswith("Moth Lamp comes on more than one disc!"), multi[:60])
        labels = [c[2][c[2].index("-V") + 1] for c in span.calls]
        says("and each disc of the set is labelled from the game's name", all(l.startswith("Moth Lamp") for l in labels)
             and not any("PC" in l for l in labels), labels)

        stick = os.path.join(work, "stick")
        os.makedirs(stick)
        usb_ns = dict(tic.NS, Host=tic.Host,
                      filedialog=type("filedialog", (), {"askdirectory": staticmethod(lambda **k: stick)}))
        exec("class Usb(Host):\n" + textwrap.indent(body_of(src, "export_usb_fileset"), "    "), usb_ns)
        usb = usb_ns["Usb"]({})
        usb.export_usb_fileset(tic.stage(image_out), {"Title": STORE})
        hint = open(os.path.join(stick, "START HERE - double click setup.txt"), encoding="utf-8").read()
        says("the USB stick's START HERE: Thanks for grabbing Moth Lamp!", hint.startswith("Thanks for grabbing Moth Lamp!"),
             hint[:60])
        print()

        print("6. the .msix: the game's name shown, its identity kept")
        sys.path.insert(0, REPO)
        from rialto import msix_export
        game = os.path.join(work, "msix-game")
        os.makedirs(game)
        open(os.path.join(game, "MothLamp.exe"), "wb").close()
        manifests = []
        real_find = msix_export.find_makeappx
        msix_export.find_makeappx = lambda: r"C:\SDK\makeappx.exe"
        try:
            def run_here(command, timeout):
                layout = command[command.index("/d") + 1]
                manifests.append(open(os.path.join(layout, "AppxManifest.xml"), encoding="utf-8").read())
                return subprocess.CompletedProcess(command, 1, "", "stand-in")
            for identity in (STORE, None):
                msix_export.build_msix(game, NAME, "CN=Larkin", "Larkin", "1.0.0.0", "MothLamp.exe", None,
                                       os.path.join(work, "s.msix"), status=lambda line: None, run=run_here,
                                       identity_title=identity)
        finally:
            msix_export.find_makeappx = real_find
        says("DisplayName is Moth Lamp", "<DisplayName>Moth Lamp</DisplayName>" in manifests[0])
        says("the Identity is the one the typed title always made",
             'Identity Name="Rialto.MothLampPCCD"' in manifests[0], manifests[0][:400])
        says("without one, the Identity follows the title, as before",
             'Identity Name="Rialto.MothLamp"' in manifests[1])
        export = body_of(src, "export_msix")
        says("Export .msix shows player_title and hands build_msix the typed title for the identity",
             'title = player_title(self.entries["Title"].get().strip())' in export
             and 'identity_title=self.entries["Title"].get().strip()' in export)
        print()

        print("7. what keeps the typed title, and the one line in the build log")
        says("the log line", note(STORE) == "Shortcuts and Setup use Moth Lamp: (PC CD) is for the store page.",
             note(STORE))
        says("after a dash too", note("Moth Lamp - PC DVD") == "Shortcuts and Setup use Moth Lamp: PC DVD is for the "
             "store page.", note("Moth Lamp - PC DVD"))
        says("in the developer's own characters",
             note("Moth Lamp™（PC CD）") == "Shortcuts and Setup use Moth Lamp™: （PC CD） is for "
             "the store page.", note("Moth Lamp™（PC CD）"))
        says("and no line for a name that ends in a platform", note("Big Mac") == "" and note("Moth Lamp PC CD") == "",
             note("Big Mac"))
        says("and no line for a title without a format", note("Juno's Adventure") == "" and note("") == "")
        build = body_of(src, "build_all")
        says("the build says it, once, from the title as typed",
             build.count("store_format_note(") == 1 and 'note = store_format_note(meta.get("Title"))' in build
             and 'self.update_status("ℹ️ " + note)' in build)
        says("the build's own meta keeps the title as typed",
             'meta = {k: self.entries[k].get().strip() for k in self.entries}' in build
             and "player_title" not in build)
        for kept in ("write_pressing_files", "log_build_event", "save_profile"):
            says("%s keeps what the developer typed" % kept, "player_title" not in body_of(src, kept))
        says("Game Title fills Start Menu Name and Disc Name word for word, as typed",
             "title = self._title_var.get()" in src and "self.disc_name_var.set(title)" in src)
        says("and nothing writes the game's name back into a box",
             not re.search(r"\.(set|insert)\([^\n]*player_title", src))
        guide = open(os.path.join(REPO, "docs", "rialto-guide.html"), encoding="utf-8").read()
        row = next(l for l in guide.splitlines() if "<td>Game Title</td>" in l)
        says("the Help Guide's Game Title row says it in one sentence",
             "A store's format at the end, like (PC CD), stays off the shortcuts, Setup and the disc, "
             "because it is for the store page." in row, row)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nEvery surface names the game; the store's format stays on the store page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
