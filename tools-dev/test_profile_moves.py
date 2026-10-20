"""A profile saved beside a game folder that has since moved (1.5.1, end-to-end runs).

The real apply_profile_file loads a 1.5.0-style profile whose art paths all
point under the old game folder. The game folder in use now holds the same
files, some at the same place relative to it and one only directly in it:
  1. each art path (Menu Background, Game Logo, Company Logo, Game Icon, Disc
     Icon) is re-pointed and said in one log line, as the folders are;
  2. a file that is nowhere in the game folder is not guessed at, and the load
     says the true thing about it: the build cannot start without a menu
     background or a game icon, and is built without a logo;
  3. never a file outside the game folder, and a path that still resolves is
     left alone.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Entry(Var):
    def delete(self, *a):
        self.value = ""

    def insert(self, _i, value):
        self.value = value


def load():
    src = open(RIALTO, encoding="utf-8").read()
    tree = ast.parse(src)
    app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    wanted = ("apply_profile_file", "rebase_under_game", "rebase_file_under_game", "rebase_stale_paths",
              "REBASEABLE_PATHS", "REBASEABLE_FILES")
    body = [textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
            if (isinstance(i, ast.FunctionDef) and i.name in wanted)
            or (isinstance(i, ast.Assign) and getattr(i.targets[0], "id", "") in wanted)]
    ns = {"os": os, "json": json, "Path": __import__("pathlib").Path, "LAST_PROFILE_FILE": os.devnull,
          "sanitize_profile_data": lambda data: data, "tk": type("tk", (), {"END": "end"}),
          "COMPRESSION_CHOICES": (("Balanced", "lzma2/fast"), ("Smallest disc", "lzma2/max"),
                                  ("Fastest install", "none"))}
    exec("class Real:\n" + textwrap.indent("\n\n".join(body), "    "), ns)
    return ns


def main():
    ns = load()
    work = tempfile.mkdtemp(prefix="rialto_profile_moves_")
    try:
        old = "D:/Old Place/input/Sky Quest/game"
        game = os.path.join(work, "New Place", "Sky Quest", "game")
        touch(os.path.join(game, "Sky Quest.exe"), b"MZ")
        touch(os.path.join(game, "menu_background.gif"), b"GIF89a")
        touch(os.path.join(game, "art", "logo.png"), b"png")
        touch(os.path.join(game, "game_icon.ico"), b"ico")
        touch(os.path.join(game, "disc_icon.ico"), b"ico")       # the profile had it under art/; only here now
        outside = touch(os.path.join(work, "New Place", "Sky Quest", "company_logo.png"), b"png")  # beside, not in
        profile = {
            "Title": "Sky Quest", "Developer": "Your Studio",
            "Background": old + "/menu_background.gif",
            "Logo": old + "/art/logo.png",
            "CompanyLogo": "D:/Old Place/input/Sky Quest/company_logo.png",
            "Icon": old.replace("/", "\\") + "\\game_icon.ico",
            "DiscIcon": old + "/art/disc_icon.ico",
        }
        path = os.path.join(work, "Sky Quest.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(profile, fh)

        class Host(ns["Real"]):
            def __init__(self):
                self.log = []
                self.current_game_path = game
                self.entries = {"Title": Entry(), "Developer": Entry()}

            def __getattr__(self, name):
                if name.endswith("_var") or name in ("remove_wti_branding",):
                    value = Var("")
                    setattr(self, name, value)
                    return value
                return lambda *a, **k: None

            def update_status(self, message):
                self.log.append(message)

        h = Host()
        ok("the profile loads", h.apply_profile_file(path, remember=False) is True, h.log)
        ok("Menu Background, at the same place in the game folder", h.bg_path_var.get()
           == os.path.join(os.path.realpath(game), "menu_background.gif"), h.bg_path_var.get())
        ok("Game Logo, in its folder under the game folder", h.logo_path_var.get()
           == os.path.join(os.path.realpath(game), "art", "logo.png"), h.logo_path_var.get())
        ok("Game Icon, from a path written with backslashes", h.ico_path_var.get()
           == os.path.join(os.path.realpath(game), "game_icon.ico"), h.ico_path_var.get())
        ok("Disc Icon, found directly in the game folder", h.disc_icon_var.get()
           == os.path.join(os.path.realpath(game), "disc_icon.ico"), h.disc_icon_var.get())
        moved = [line for line in h.log if line.startswith("🔀")]
        ok("one log line for each, as for the folders", len(moved) == 4 and all("re-pointed at your game folder" in l
                                                                            for l in moved), moved)
        ok("a file beside the game folder, not in it, is never taken",
           h.company_logo_var.get() == profile["CompanyLogo"] and h.company_logo_var.get() != outside)
        ok("and its loss is said, with what happens: the disc is built without it",
           any("Company Logo in this profile no longer exists" in l for l in h.log)
           and any(l.strip() == "Pick Company Logo again, or the disc is built without it." for l in h.log), h.log)
        ok("nothing said about the build not starting, when the background and icon were found",
           not any("cannot start" in l for l in h.log), h.log)

        os.remove(os.path.join(game, "menu_background.gif"))
        os.remove(os.path.join(game, "game_icon.ico"))
        h = Host()
        h.apply_profile_file(path, remember=False)
        ok("a background and an icon found nowhere: the build cannot start without them, said so",
           any(l.strip() == "Pick Menu Background and Game Icon again under Step 4: the build cannot start "
               "without them." for l in h.log), h.log)
        ok("never 'built without' for a field the build refuses without",
           not any("Menu Background" in l and "built without" in l for l in h.log), h.log)

        h = Host()
        here = os.path.join(game, "art", "logo.png")
        ok("a path that still resolves is left alone", h.rebase_file_under_game(here) == "")
        ok("a file found nowhere is not invented", h.rebase_file_under_game("E:/gone/nowhere.png") == "")
        ok("a parent's name in a stored path never climbs out",
           h.rebase_file_under_game("D:/x/../../company_logo.png") == "")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nA moved profile's art follows the game folder, and every missing file is said truly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
