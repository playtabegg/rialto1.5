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
     left alone;
  4. the developer's own Steam art (1.5.2) moves the same way, and a piece
     found nowhere is said truly: Steam gets what Rialto makes instead, or,
     with Add to Steam off, that no Steam art goes on the disc at all;
  5. the menu's font and its license (Menu Font and Colors, 1.5.2), kept in
     the menu theme, move the same way, and are said on load when found
     nowhere: the menu then uses its own font.
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
    wanted = ("apply_profile_file", "put_profile_on_form", "rebase_under_game", "rebase_file_under_game", "rebase_stale_paths",
              "REBASEABLE_PATHS", "REBASEABLE_FILES", "REBASEABLE_THEME_FILES", "STEAM_ART_PIECES", "steam_art_paths",
              "set_steam_art", "menu_theme_path")
    body = [textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
            if (isinstance(i, ast.FunctionDef) and i.name in wanted)
            or (isinstance(i, ast.Assign) and getattr(i.targets[0], "id", "") in wanted)]
    ns = {"os": os, "json": json, "Path": __import__("pathlib").Path, "LAST_PROFILE_FILE": os.devnull,
          "sanitize_profile_data": lambda data: data, "sanitize_text": str, "tk": type("tk", (), {"END": "end"}),
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
        touch(os.path.join(game, "steam", "capsule.png"), b"png")
        touch(os.path.join(game, "fonts", "Menu.ttf"), b"ttf")
        touch(os.path.join(game, "fonts", "OFL.txt"), b"SIL Open Font License")
        outside = touch(os.path.join(work, "New Place", "Sky Quest", "company_logo.png"), b"png")  # beside, not in
        profile = {
            "Title": "Sky Quest", "Developer": "Your Studio",
            "Background": old + "/menu_background.gif",
            "Logo": old + "/art/logo.png",
            "CompanyLogo": "D:/Old Place/input/Sky Quest/company_logo.png",
            "Icon": old.replace("/", "\\") + "\\game_icon.ico",
            "DiscIcon": old + "/art/disc_icon.ico",
            "SteamArt": {"Capsule": old + "/steam/capsule.png", "Icon": old + "/steam/nowhere.ico"},
            "MenuTheme": {"Font": old + "/fonts/Menu.ttf", "License": old + "/fonts/OFL.txt", "Text": "#f1e4cf"},
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
        moved = [line for line in h.log if line.startswith("🔀") and "Menu Font" not in line]
        ok("one log line for each, as for the folders", len(moved) == 5 and all("re-pointed at your game folder" in l
                                                                            for l in moved), moved)
        ok("the Library Capsule follows the game folder too", h.steam_capsule_var.get()
           == os.path.join(os.path.realpath(game), "steam", "capsule.png"), h.steam_capsule_var.get())
        ok("a Shortcut Icon found nowhere is said, with what happens: Steam gets what Rialto makes",
           any("Shortcut Icon in this profile no longer exists" in l for l in h.log)
           and any(l.strip() == "Pick Shortcut Icon again in Disc Extras, or Steam gets what Rialto makes from "
                   "your Step 4 art." for l in h.log), h.log)
        ok("a file beside the game folder, not in it, is never taken",
           h.company_logo_var.get() == profile["CompanyLogo"] and h.company_logo_var.get() != outside)
        ok("and its loss is said, with what happens: the disc is built without it",
           any("Company Logo in this profile no longer exists" in l for l in h.log)
           and any(l.strip() == "Pick Company Logo again, or the disc is built without it." for l in h.log), h.log)
        ok("nothing said about the build not starting, when the background and icon were found",
           not any("cannot start" in l for l in h.log), h.log)
        ok("the menu's font follows the game folder, kept in the menu theme",
           h.menu_theme.get("Font") == os.path.join(os.path.realpath(game), "fonts", "Menu.ttf"), h.menu_theme)
        ok("and its license", h.menu_theme.get("License") == os.path.join(os.path.realpath(game), "fonts", "OFL.txt"),
           h.menu_theme)
        ok("each said in one log line, as the art is",
           any(l.startswith("🔀 Menu Font re-pointed at your game folder") for l in h.log)
           and any(l.startswith("🔀 Menu Font's license re-pointed at your game folder") for l in h.log), h.log)
        ok("the rest of the theme is left as it was", h.menu_theme.get("Text") == "#f1e4cf", h.menu_theme)
        ok("a font found again is not said to be missing", not any("Menu Font" in l and "no longer exists" in l
                                                                   for l in h.log), h.log)

        shutil.rmtree(os.path.join(game, "fonts"))
        h = Host()
        h.apply_profile_file(path, remember=False)
        ok("a font and license found nowhere are said on load, as the art is",
           any("Menu Font in this profile no longer exists" in l for l in h.log)
           and any("Menu Font's license in this profile no longer exists" in l for l in h.log), h.log)
        ok("with what happens: the menu uses its own font",
           any(l.strip() == "Pick Menu Font and Menu Font's license again in Font and Colors, or the menu uses "
               "its own font." for l in h.log), h.log)
        ok("and never 'built without' for them", not any("Menu Font" in l and "built without" in l for l in h.log),
           h.log)

        unticked = dict(profile, SteamButton=False)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(unticked, fh)
        h = Host()
        h.apply_profile_file(path, remember=False)
        ok("Add to Steam off: a Steam piece found nowhere is still said",
           any("Shortcut Icon in this profile no longer exists" in l for l in h.log), h.log)
        ok("but not that Steam gets anything: no Steam art goes on the disc",
           not any("Steam gets what Rialto makes" in l for l in h.log)
           and any(l.strip() == "Add to Steam is off, so no Steam art goes on the disc. If you tick it, pick "
                   "Shortcut Icon again in Disc Extras." for l in h.log), h.log)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(profile, fh)

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
