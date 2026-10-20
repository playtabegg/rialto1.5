"""The tools Rialto carries (1.5.1): where they are found, their pins, and a real mkisofs disc.

Rialto.exe carries Inno Setup 6.5.4 and cdrtools 3.02a10's mkisofs, so nobody
has to install anything. This checks:
  1. helper_path: a frozen Rialto runs only the copies inside its EXE, never a
     helpers folder beside it; a source run uses the checkout's helpers\\; and
     a folder counts only when it holds the tool's whole set.
  2. helpers/MANIFEST.json: every file Rialto needs is pinned (every Inno
     language Rialto's scripts name, and no other), with a source, a version
     and a license; the license texts match licenses/; fetch_helpers.problems
     finds a missing, changed or unpinned file; and when helpers/ has been
     fetched, it matches its pins exactly.
  3. mkisofs_command, pure: graft points keep every folder where it belongs
     (without them mkisofs put menu\\, Mac\\, bonus\\ and the mods folder loose
     at the disc root), long Joliet names, UTF-8 names, UDF over 4 GiB.
  4. When helpers/ or C:\\cdrtools is present: a REAL disc written through
     Rialto's own _write_one_image, then read back with isoinfo (-l -J): the
     folder tree and every name intact, a 90-character name, "Cafe" with its
     accent and a Japanese name among them. Written under
     F:\\WTI-RialtoTest\\scratch-tools when F: is there, else a temp folder.
  5. The same with names Cygwin's command-line parser used to change (security
     review, 1.5.1): an apostrophe, braces, square brackets, a leading dash,
     "=", a leading "@", a backslash-looking name, spaces, non-English names, in
     a build folder whose own name has an apostrophe and braces, and a label
     with a quote, braces and a star. Every item lands, exactly named.
"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, HERE)
import fetch_helpers  # noqa: E402

SCRATCH = r"F:\WTI-RialtoTest\scratch-tools"
CDRTOOLS = r"C:\cdrtools"
failures = []


def ok(label, cond, detail=""):
    shown = (" -> " + ascii(detail)) if (detail and not cond) else ""
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, shown))
    if not cond:
        failures.append(label)


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def module_functions(src, tree, names):
    found = {n.name: ast.get_source_segment(src, n) for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name in names}
    missing = [n for n in names if n not in found]
    if missing:
        raise SystemExit("could not extract " + ", ".join(missing))
    return "\n\n".join(found[n] for n in names)


def class_methods(src, tree, names):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    found = {i.name: ast.get_source_segment(src, i) for i in cls.body if isinstance(i, ast.FunctionDef) and i.name in names}
    return "\n\n".join("    " + found[n] for n in names)


def main():
    with open(RIALTO, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)

    print("1. helper_path")
    sets_node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "CARRIED_SETS")
    code = ast.get_source_segment(src, sets_node) + "\n\n" + module_functions(src, tree, ["helper_path", "carried_mkisofs"])
    work = tempfile.mkdtemp(prefix="rialto_carried_")
    try:
        app, bundle = os.path.join(work, "app"), os.path.join(work, "_MEI42")
        ns = {"os": os, "re": re, "APP_ROOT": app, "sys": types.SimpleNamespace(frozen=True, _MEIPASS=bundle)}
        exec(code, ns)
        sets = ns["CARRIED_SETS"]

        def carry(root, tool, leave_out=()):
            for name in sets[tool]:
                if name not in leave_out:
                    touch(os.path.join(root, "helpers", tool, *name.split("/")))
            return os.path.join(root, "helpers", tool, sets[tool][0])
        ok("nothing carried: None", ns["helper_path"]("inno", "ISCC.exe") is None)
        carry(bundle, "inno", leave_out=("ISPP.dll.issig",))
        ok("a frozen Rialto: an ISCC inside the EXE without one of its .issig files is not offered",
           ns["helper_path"]("inno", "ISCC.exe") is None)
        inside = carry(bundle, "inno")
        ok("the whole set inside the EXE: its ISCC", ns["helper_path"]("inno", "ISCC.exe") == inside)
        carry(app, "inno")
        carry(app, "cdrtools")
        ok("a frozen Rialto never runs a helpers folder beside Rialto.exe, whole or not",
           ns["helper_path"]("inno/ISCC.exe") == inside and ns["carried_mkisofs"]() is None)
        touch(os.path.join(bundle, "helpers", "cdrtools", "mkisofs.exe"))
        ok("mkisofs without cygwin1.dll is not offered", ns["carried_mkisofs"]() is None)
        touch(os.path.join(bundle, "helpers", "cdrtools", "cygwin1.dll"))
        ok("mkisofs with cygwin1.dll is", ns["carried_mkisofs"]() == os.path.join(bundle, "helpers", "cdrtools", "mkisofs.exe"))
        ns["sys"] = types.SimpleNamespace()
        ok("a source run (no _MEIPASS): the checkout's helpers, each set whole",
           ns["helper_path"]("cdrtools", "mkisofs.exe") == os.path.join(app, "helpers", "cdrtools", "mkisofs.exe")
           and ns["helper_path"]("inno", "ISCC.exe") == os.path.join(app, "helpers", "inno", "ISCC.exe"))
        os.remove(os.path.join(app, "helpers", "cdrtools", "cygwin1.dll"))
        os.remove(os.path.join(app, "helpers", "inno", "ISCmplr.dll"))
        ok("a source run: a part of a set is never used",
           ns["carried_mkisofs"]() is None and ns["helper_path"]("inno", "ISCC.exe") is None)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()

    print("2. the pins")
    manifest = fetch_helpers.load_manifest()
    pinned = manifest["files"]
    languages = set(re.findall(r'MessagesFile: "compiler:Languages\\\\([A-Za-z]+)\.isl"', src))
    ok("Rialto's scripts name 20 Inno languages", len(languages) == 20, sorted(languages))
    carried_languages = {rel.split("/")[-1][:-4] for rel in pinned if rel.startswith("inno/Languages/")}
    ok("every language Rialto names is carried, and no other", carried_languages == languages,
       sorted(carried_languages ^ languages))
    ok("Default.isl, which the english line names, is carried", 'compiler:Default.isl' in src and "inno/Default.isl" in pinned)
    needed = ["ISCC.exe", "ISCmplr.dll", "ISPP.dll", "ISPPBuiltins.iss", "Setup.e32", "SetupLdr.e32", "islzma.dll",
              "license.txt", "ISCmplr.dll.issig", "ISPP.dll.issig", "Setup.e32.issig", "SetupLdr.e32.issig",
              "islzma.dll.issig"]
    ok("the minimum Inno Setup set, with the .issig files ISCC will not start without",
       all("inno/" + name in pinned for name in needed), [n for n in needed if "inno/" + n not in pinned])
    ok("mkisofs and the cygwin1.dll it needs", "cdrtools/mkisofs.exe" in pinned and "cdrtools/cygwin1.dll" in pinned)
    ok("every file helper_path asks for in a whole set is pinned, so the bundle always holds the whole set",
       all("%s/%s" % (tool, name) in pinned for tool, names in sets.items() for name in names),
       [t + "/" + n for t, names in sets.items() for n in names if t + "/" + n not in pinned])
    ok("the Inno languages helper_path asks for are the ones Rialto's scripts name",
       {n[len("Languages/"):-4] for n in sets["inno"] if n.startswith("Languages/")} == languages)
    ok("the license texts travel with them", all(k in pinned for k in (
        "inno/license.txt", "cdrtools/GPL-2.0.txt", "cdrtools/GPL-3.0.txt", "cdrtools/THIRD-PARTY.txt")))
    ok("every pin has a SHA-256, a size, a source, a version and a license",
       all(re.fullmatch(r"[0-9a-f]{64}", p["sha256"]) and p["size"] > 0 and p["source"] and p["version"] and p["license"]
           for p in pinned.values()))
    ok("Inno Setup is pinned at 6.5.4, the version Rialto names",
       all(p["version"] == "6.5.4" for r, p in pinned.items() if r.startswith("inno/"))
       and 'CARRIED_INNO_VERSION = "6.5.4"' in src)
    ok("mkisofs is 3.02a10 and cygwin1.dll 2.3.1", pinned["cdrtools/mkisofs.exe"]["version"].startswith("3.02a10")
       and pinned["cdrtools/cygwin1.dll"]["version"] == "2.3.1")
    for rel, pin in sorted(pinned.items()):
        if not os.path.isabs(pin["source"]):
            path = fetch_helpers.source_path(pin["source"])
            ok("%s matches %s in the repo (re-pin after editing it)" % (rel, pin["source"]),
               os.path.isfile(path) and fetch_helpers.sha256(path) == pin["sha256"])
    ok("licenses/ names each component", all(word in open(os.path.join(REPO, "licenses", "THIRD-PARTY.txt"),
                                                          encoding="utf-8").read()
                                              for word in ("Inno Setup 6.5.4", "mkisofs 3.02a10", "Cygwin DLL 2.3.1",
                                                           "GPL", "CDDL", "Source:")))

    # The checker itself, on a tiny pretend manifest
    work = tempfile.mkdtemp(prefix="rialto_pins_")
    try:
        body = b"ISCC"
        fake = {"files": {"inno/ISCC.exe": {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}}}
        touch(os.path.join(work, "inno", "ISCC.exe"), body)
        ok("problems(): exactly as pinned", fetch_helpers.problems(work, fake) == [])
        touch(os.path.join(work, "inno", "Compil32.exe"))
        ok("problems(): an unpinned file is named", fetch_helpers.problems(work, fake) == ["helpers/inno/Compil32.exe is not in the manifest"])
        os.remove(os.path.join(work, "inno", "Compil32.exe"))
        touch(os.path.join(work, "inno", "ISCC.exe"), b"ISCX")
        ok("problems(): a changed file is named", fetch_helpers.problems(work, fake) == ["helpers/inno/ISCC.exe does not match its pin"])
        os.remove(os.path.join(work, "inno", "ISCC.exe"))
        ok("problems(): a missing file is named", fetch_helpers.problems(work, fake) == ["helpers/inno/ISCC.exe is missing"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if os.path.isdir(os.path.join(REPO, "helpers", "inno")):
        left = fetch_helpers.problems()
        ok("helpers/ in this checkout matches its pins exactly", left == [], left)
    else:
        print("  [--  ] helpers/ not fetched in this checkout (python tools-dev/fetch_helpers.py)")
    print()

    print("3. the mkisofs command (pure)")
    pure = {"os": os}
    exec(mkisofs_code(src, tree), pure)
    command = pure["mkisofs_command"]
    items = ["setup.exe", "setup-1.bin", "menu", "Mac", "bonus", "a=b", "-mods"]
    got = command("mk.exe", "GAME", False)
    ok("one disc: Joliet, long names, Rock Ridge for everyone, graft points, the label, the image to a plain name",
       got == ["mk.exe", "-o", "rialto-image.part", "-input-charset", "UTF-8", "-J", "-r", "-joliet-long",
               "-graft-points", "-V", "GAME", "-path-list", "rialto-graft-points.txt"], got)
    listed = pure["mkisofs_path_list"](items, {"menu", "Mac", "bonus", "a=b", "-mods"})
    ok("each folder grafted where it belongs, each file as itself, one a line in the -path-list file",
       listed.split("\n") == ["setup.exe=setup.exe", "setup-1.bin=setup-1.bin", "menu/=menu", "Mac/=Mac",
                              "bonus/=bonus", "a\\=b/=a\\=b", "/-mods/=./-mods", ""], listed)
    got = command("mk.exe", "GAME D2", True, False)
    ok("UDF for a file over 4 GiB, and no charset for a build that is not Cygwin's",
       got == ["mk.exe", "-o", "rialto-image.part", "-J", "-r", "-joliet-long", "-graft-points", "-V", "GAME D2",
               "-udf", "-iso-level", "3", "-path-list", "rialto-graft-points.txt"], got)
    ok("a name with a backslash is escaped too", pure["mkisofs_graft"]("a\\b", False) == "a\\\\b=a\\\\b")
    label = pure["mkisofs_label"]
    ok("the label keeps letters, digits, spaces and accents", label("CAF\u00c9 GAME D1") == "CAF\u00c9 GAME D1")
    ok("the label loses what Cygwin's parser acts on: quotes, braces, star, ?, brackets, a leading - or @",
       label("Bob's \"{a,b}\" *[x]?") == "Bobs _a,b_ __x__" and label("-@Game") == "Game" and label("''") == "GAME",
       label("Bob's \"{a,b}\" *[x]?"))
    ok("a lone ~ never reaches Cygwin, which would write the builder's home folder (and user name) as the label",
       label("~") == "_" and label("@~") == "_" and "~" not in label("~Demo"), label("~"))
    print()

    print("4. a real disc")
    mkisofs = None
    for candidate in (os.path.join(REPO, "helpers", "cdrtools", "mkisofs.exe"), os.path.join(CDRTOOLS, "mkisofs.exe")):
        if os.path.isfile(candidate) and os.path.isfile(os.path.join(os.path.dirname(candidate), "cygwin1.dll")):
            mkisofs = candidate
            break
    isoinfo = os.path.join(CDRTOOLS, "isoinfo.exe")
    if not mkisofs or not os.path.isfile(isoinfo):
        print("  [--  ] no mkisofs or isoinfo on this PC: the real disc is skipped")
    else:
        real_disc(src, tree, mkisofs, isoinfo)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nThe carried tools are found in order, pinned, and write a disc with every folder and name intact.")
    return 0


def mkisofs_code(src, tree):
    """The module-level mkisofs pieces: the two file names, the label, the path list, the command."""
    consts = "\n".join(ast.get_source_segment(src, n) for n in tree.body if isinstance(n, ast.Assign)
                       and getattr(n.targets[0], "id", "") in ("MKISOFS_IMAGE_PART", "MKISOFS_PATH_LIST"))
    return consts + "\n\n" + module_functions(src, tree, ["mkisofs_graft", "mkisofs_label", "mkisofs_path_list",
                                                         "mkisofs_command", "mkisofs_reads_utf8"])


def isoinfo_tree(isoinfo, iso, joliet):
    """{path: is_folder} read back from the image, with Joliet names (UTF-8) or Rock Ridge names."""
    flags = ["-l", "-J", "-j", "UTF-8"] if joliet else ["-l", "-R"]
    out = subprocess.run([isoinfo] + flags + ["-i", iso], capture_output=True).stdout.decode("utf-8", "replace")
    tree, folder, modes = {}, "/", {}
    for line in out.splitlines():
        if line.startswith("Directory listing of "):
            folder = line[len("Directory listing of "):].rstrip()
            continue
        # The name follows isoinfo's "[ extent flags]" field; a name may hold "]" itself.
        m = re.match(r"\s*\d+\s+([d-][rwx-]{9})\s.*?\[\s*\d+\s+\d+\]\s(.*?)\s?$", line)
        if not m or m.group(2) in (".", ".."):
            continue
        path = folder + m.group(2)
        tree[path] = m.group(1).startswith("d")
        modes[path] = m.group(1)
    return tree, modes


def real_disc(src, tree, mkisofs, isoinfo):
    base = SCRATCH if os.path.isdir(os.path.dirname(SCRATCH)) else tempfile.gettempdir()
    root = os.path.join(base, "gate-real-disc")
    shutil.rmtree(root, ignore_errors=True)
    # The build folder takes the game's name, which may be anything: an accent and Japanese here.
    output = os.path.join(root, "Caf\u00e9 \u30b2\u30fc\u30e0")
    # 90 characters, the same for the first 64: mkisofs stopped on these before -joliet-long. (Joliet
    # keeps up to 103 characters with it; Rock Ridge keeps more.)
    long_a = ("A" * 64 + "_the_first_of_two").ljust(86, "x") + ".txt"
    long_b = ("A" * 64 + "_the_other_of_two").ljust(86, "x") + ".txt"
    staged = {
        "setup.exe": b"MZ", "setup-1.bin": b"bin" * 1000, "autorun.inf": b"[autorun]", "game.ico": b"ico",
        "menu/menu.exe": b"MZ", "menu/menu_config.json": b"{}", "menu/assets/bg.gif": b"GIF89a",
        "Mac/Game.app/Contents/Info.plist": b"<plist/>", "Mac/Game.app/Contents/MacOS/Game": b"\xcf\xfa\xed\xfe",
        "bonus/Art Book/page 1.png": b"png", "bonus/" + long_a: b"a", "bonus/" + long_b: b"b",
        "bonus/Caf\u00e9/cr\u00e8me br\u00fbl\u00e9e.txt": b"c",
        "bonus/\u65e5\u672c\u8a9e\u306e\u30d5\u30a9\u30eb\u30c0/\u30b2\u30fc\u30e0.txt": b"j",
        "mods/My Mod/mod.dll": b"MZ",
    }
    for rel, data in staged.items():
        touch(os.path.join(output, *rel.split("/")), data)
    ok("two 90-character names, alike for 64, are staged", len(long_a) == len(long_b) == 90, len(long_a))
    items = ["setup.exe", "autorun.inf", "setup-1.bin", "game.ico", "menu", "Mac", "bonus", "mods"]

    calls = []

    class Host:
        def run_tool_watched(self, tool, cwd, timeout, step, watch=None, on_line=None):
            calls.append(tool)
            return subprocess.run(tool, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout)

        def update_status(self, message):
            pass

    ns = {"os": os, "re": re, "shutil": shutil, "subprocess": subprocess}
    exec(mkisofs_code(src, tree), ns)
    exec("class Real(Host):\n" + class_methods(src, tree, ["_write_one_image", "_fileset_size", "image_growth"]),
         dict(ns, Host=Host), ns)
    iso = os.path.join(output, "Caf\u00e9 \u30b2\u30fc\u30e0.iso")
    made, why = ns["Real"]()._write_one_image("mkisofs", mkisofs, output, iso, items, "CAFE GAME", False,
                                              "temp_iso_build", "Writing the disc image")
    ok("Rialto's own _write_one_image writes the disc with %s" % mkisofs, made and os.path.isfile(iso), why)
    if not made:
        return
    ok("through the one mkisofs_command, with graft points read from a file", calls and "-graft-points" in calls[0]
       and "-path-list" in calls[0] and "menu/=menu" not in calls[0])

    want = {}
    for rel in staged:
        parts = rel.split("/")
        for depth in range(1, len(parts)):
            want["/" + "/".join(parts[:depth])] = True
        want["/" + rel] = False
    joliet, _ = isoinfo_tree(isoinfo, iso, True)
    ok("Joliet: every folder where it belongs, nothing loose at the root",
       {p for p, d in joliet.items() if p.count("/") == 1} == {"/" + i for i in items}, sorted(joliet))
    ok("Joliet: the whole tree and every name intact (90 characters, the accent, Japanese)",
       joliet == want, sorted(set(joliet.items()) ^ set(want.items())))
    rock, modes = isoinfo_tree(isoinfo, iso, False)
    ok("Rock Ridge: the same tree, for a Mac or Linux PC", rock == want, sorted(set(rock.items()) ^ set(want.items())))
    ok("Rock Ridge: everything readable by everyone (-r), not just the account that built it",
       modes and all(m[7] == "r" for m in modes.values()), sorted(set(modes.values())))
    ok("the build folder holds no temp folder, path list or unfinished image afterward",
       not any(os.path.exists(os.path.join(output, n)) for n in ("temp_iso_build", "rialto-graft-points.txt",
                                                               "rialto-image.part")))
    shutil.rmtree(root, ignore_errors=True)
    hostile_disc(src, tree, mkisofs, isoinfo, Host, ns)


def hostile_disc(src, tree, mkisofs, isoinfo, Host, ns):
    """Names Cygwin's own command-line parser changed before 1.5.1 (security review)."""
    base = SCRATCH if os.path.isdir(os.path.dirname(SCRATCH)) else tempfile.gettempdir()
    root = os.path.join(base, "gate-hostile-disc")
    shutil.rmtree(root, ignore_errors=True)
    # The game folder's own name, which becomes the build folder's, with an apostrophe and braces.
    output = os.path.join(root, "Bob's {Big,Small} Game")
    long_name = ("L" * 60 + "_a_long_icon_name").ljust(86, "x") + ".ico"
    # Windows refuses * ? \ " < > | : in a file name, so the star and the backslash are tried where they
    # can be: the label below, and a name with a backslash-looking character (U+FF3C).
    roots = ["Rock'n'Roll.ico", "{a,b}.ico", "[x].ico", "-evil.ico", "a=b.ico", "@words.ico", "x\uff3cy.ico",
             "has space.ico", " leading space.ico", long_name, "Caf\u00e9.ico", "\u30b2\u30fc\u30e0.ico",
             "\u0418\u0433\u0440\u0430.ico", "\u2605star.ico", "setup.exe", "autorun.inf"]
    staged = {name: b"ico" for name in roots}
    staged.update({
        "menu/menu.exe": b"MZ", "menu/it's {here}.json": b"{}",
        "bonus/Bob's [Art] Book/page {1}.png": b"png", "bonus/-dash/=equals=.txt": b"e",
        "Bob's {c,d} Mods/in [side]/it's=ok.txt": b"m", "Bob's {c,d} Mods/\u6a21\u7d44/mod.dll": b"MZ",
    })
    for rel, data in staged.items():
        touch(os.path.join(output, *rel.split("/")), data)
    ok("a 90-character root name is staged", len(long_name) == 90, len(long_name))
    items = roots + ["menu", "bonus", "Bob's {c,d} Mods"]
    iso = os.path.join(output, "Bob's {Big,Small} Game.iso")
    made, why = ns["Real"]()._write_one_image("mkisofs", mkisofs, output, iso, items, "Bob's {Big} *Game", False,
                                              "temp_iso_build", "Writing the disc image")
    ok("the hostile disc is written", made and os.path.isfile(iso), why)
    if not made:
        return
    want = {}
    for rel in staged:
        parts = rel.split("/")
        for depth in range(1, len(parts)):
            want["/" + "/".join(parts[:depth])] = True
        want["/" + rel] = False
    joliet, _ = isoinfo_tree(isoinfo, iso, True)
    ok("Joliet: every item lands, exactly named, folders intact",
       joliet == want, sorted(set(joliet.items()) ^ set(want.items())))
    rock, _ = isoinfo_tree(isoinfo, iso, False)
    ok("Rock Ridge: the same", rock == want, sorted(set(rock.items()) ^ set(want.items())))
    info = subprocess.run([isoinfo, "-d", "-i", iso], capture_output=True).stdout.decode("utf-8", "replace")
    volume = next((l.split(":", 1)[1].strip() for l in info.splitlines() if l.startswith("Volume id:")), None)
    ok("the label, made safe, is the disc's volume id", volume == "Bobs _Big_ _Game", volume)
    ok("nothing left beside it but what was staged",
       sorted(os.listdir(output)) == sorted(set(r.split("/")[0] for r in staged) | {os.path.basename(iso)}),
       sorted(os.listdir(output)))
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
