"""Preview staging and the guide copied out of the bundle write only where they should (1.5.1 reviews).

  1. stage_preview_games, with real junctions as Preview makes them: a game's
     picture under bonus\\, whose junction leads to the author's own folder, is
     refused, and that folder is left exactly as it was (no file overwritten, no
     folder made). Two games sharing one picture are staged once with no false
     "large and on another drive" line. A picture the menu would refuse (over
     8 MB, or not a picture type) stages the exe, whose icon the menu shows.
  2. doc_path, as a frozen Rialto: the guide is copied to APP_ROOT\\docs, never
     through a hard link, a symbolic link or a junction put at that name, and a
     copy that is already the same is left alone.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


def write(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def junction(link, target):
    return subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True).returncode == 0


def snapshot(folder):
    found = {}
    for dirpath, dirs, files in os.walk(folder):
        for name in dirs + files:
            path = os.path.join(dirpath, name)
            found[os.path.relpath(path, folder)] = open(path, "rb").read() if os.path.isfile(path) else None
    return found


def load():
    src = open(RIALTO, encoding="utf-8").read()
    tree = ast.parse(src)
    app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    body = [textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
            if (isinstance(i, ast.FunctionDef) and i.name in ("stage_preview_games", "doc_path"))
            or (isinstance(i, ast.Assign) and getattr(i.targets[0], "id", "") in (
                "PREVIEW_EXE_COPY_LIMIT", "MENU_PICTURE_TYPES", "MENU_PICTURE_LIMIT"))]
    ns = {"os": os, "json": json, "shutil": shutil, "tempfile": tempfile}
    exec(next(ast.get_source_segment(src, n) for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "same_file_bytes"), ns)
    exec("class Real:\n" + textwrap.indent("\n\n".join(body), "    "), ns)
    return ns


def main():
    ns = load()
    work = tempfile.mkdtemp(prefix="rialto_preview_docs_")
    try:
        print("1. Preview staging")
        game = os.path.join(work, "Two Games")
        author = os.path.join(work, "Author's Own Folder")   # the bonus folder picked in Disc Extras
        write(os.path.join(author, "cover.png"), b"the author's own cover")
        write(os.path.join(game, "bonus", "cover.png"), b"png")
        write(os.path.join(game, "bonus", "deep", "art.png"), b"png")
        write(os.path.join(game, "shared.png"), b"png")
        write(os.path.join(game, "big.png"), b"p" * (8 * 1024 * 1024 + 1))
        write(os.path.join(game, "notes.txt"), b"not a picture")
        for exe in ("a.exe", "b.exe", "c.exe", "d.exe", "e.exe", "f.exe"):
            write(os.path.join(game, exe), b"MZ")
        before = snapshot(author)

        temp_root = tempfile.mkdtemp(prefix="preview_", dir=work)
        menu_dir = os.path.join(temp_root, "menu")
        os.makedirs(menu_dir)
        made = junction(os.path.join(temp_root, "bonus"), author)
        ok("the bonus junction is made, as Preview makes it", made)
        games = [{"name": "In bonus", "exe": "a.exe", "icon": "bonus/cover.png"},
                 {"name": "Deep in bonus", "exe": "b.exe", "icon": "bonus/deep/art.png"},
                 {"name": "First", "exe": "c.exe", "icon": "shared.png"},
                 {"name": "Second", "exe": "d.exe", "icon": "shared.png"},
                 {"name": "Too big", "exe": "e.exe", "icon": "big.png"},
                 {"name": "Not a picture", "exe": "f.exe", "icon": "notes.txt"}]
        with open(os.path.join(menu_dir, "menu_config.json"), "w", encoding="utf-8") as fh:
            json.dump({"games": games}, fh)

        class Host(ns["Real"]):
            current_game_path = game

            def __init__(self):
                self.log = []

            def update_status(self, message):
                self.log.append(message)
        h = Host()
        ok("a disc of several games", h.stage_preview_games(menu_dir, temp_root) is True)
        ok("the author's folder behind the bonus junction is exactly as it was: nothing overwritten, no folder made",
           snapshot(author) == before, sorted(set(snapshot(author)) ^ set(before)))
        ok("the refusal is said plainly",
           any("In bonus" in l and "Deep in bonus" in l and "bonus or mods folder" in l for l in h.log), h.log)
        ok("two games sharing one picture: staged once, and no false 'large and on another drive' line",
           os.path.isfile(os.path.join(temp_root, "shared.png"))
           and not any("another drive" in l for l in h.log), h.log)
        ok("a picture over 8 MB: the exe is staged, so the menu shows its icon",
           os.path.isfile(os.path.join(temp_root, "e.exe")) and not os.path.exists(os.path.join(temp_root, "big.png")))
        ok("a file that is not a picture type: the exe is staged",
           os.path.isfile(os.path.join(temp_root, "f.exe")) and not os.path.exists(os.path.join(temp_root, "notes.txt")))
        os.rmdir(os.path.join(temp_root, "bonus"))  # the junction only, never what it points to
        print()

        print("2. doc_path")
        app_root = os.path.join(work, "Rialto")
        bundle = os.path.join(work, "_MEI1")
        page = write(os.path.join(bundle, "docs", "guide.html"), b"<html>the 1.5.1 guide</html>")
        ns["sys"] = types.SimpleNamespace(_MEIPASS=bundle, frozen=True)
        ns["APP_ROOT"] = app_root
        target = os.path.join(app_root, "docs", "guide.html")
        host = ns["Real"]()
        ok("the first time: copied out beside Rialto", host.doc_path("guide.html") == target
           and open(target, "rb").read() == open(page, "rb").read())
        stamp = os.stat(target).st_mtime_ns
        os.utime(target, ns=(stamp - 10**10, stamp - 10**10))
        stamp = os.stat(target).st_mtime_ns
        host.doc_path("guide.html")
        ok("a copy that is already the same is left alone", os.stat(target).st_mtime_ns == stamp)

        elsewhere = write(os.path.join(work, "elsewhere", "precious.txt"), b"keep me")
        os.remove(target)
        os.link(elsewhere, target)
        ok("a hard link put at docs\\guide.html: the guide replaces the name, the other file is untouched",
           host.doc_path("guide.html") == target and open(elsewhere, "rb").read() == b"keep me"
           and open(target, "rb").read() == open(page, "rb").read())
        os.remove(target)
        try:
            os.symlink(elsewhere, target)
            linked = True
        except OSError:
            linked = False
            print("  [--  ] no symbolic link privilege here: the symbolic link case is skipped")
        if linked:
            host.doc_path("guide.html")
            ok("a symbolic link put there: what it points at is untouched", open(elsewhere, "rb").read() == b"keep me"
               and not os.path.islink(target))
            os.remove(target)
        os.makedirs(os.path.join(work, "a folder"))
        junction(target, os.path.join(work, "a folder"))
        got = host.doc_path("guide.html")
        ok("a junction put there: nothing is written into the folder it leads to",
           os.listdir(os.path.join(work, "a folder")) == [] and got in (target, page), got)
        ok("no temporary file is left in docs", all(not n.startswith(".rialto-") for n in os.listdir(os.path.dirname(target))),
           os.listdir(os.path.dirname(target)))
        if os.path.isdir(target):
            os.rmdir(target)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nPreview staging and the guide write only inside their own folders.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
