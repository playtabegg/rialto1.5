"""ADD TO STEAM from a later disc of a game already in Steam (1.5.2, his word of 4 Nov 2026).

The shortcut is already in the player's list, so the press adds nothing, and
the list and its .rialto-backup are left exactly as they are. What it does do is
copy this disc's pictures from menu/steam/ into Steam's grid folder, under the
appid the list files that shortcut under (a later disc may name the game
another way, and so make another appid), and say so: "Already in Steam", and
"Its pictures are updated from this disc." in every language the menu has. A
disc with no Steam art changes nothing and keeps the old words. Steam running
still refuses before anything is touched.

Everything runs on temp folders through the stub disc menu of
test_steam_shortcuts.py, with the real methods from MENU_TEMPLATE_SOURCE: never
the real Steam folder.

Usage: python test_steam_later_disc.py [path-to-Rialto.pyw]
"""
import ast
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_steam_shortcuts as shortcuts  # noqa: E402  the stub disc menu with the real Steam methods on it

FAILURES = []
PIECES = (("capsule", "%dp"), ("wide", "%d"), ("hero", "%d_hero"), ("logo", "%d_logo"))
UPDATED = "Its pictures are updated from this disc."


def ok(label, passed, detail=""):
    print("  [%s] %s" % ("OK  " if passed else "FAIL", label))
    if not passed:
        FAILURES.append("%s: %r" % (label, detail))


def put_art(game_dir, tag, extension=".png"):
    """This disc's four pieces in menu/steam/, each holding its own tag."""
    art = os.path.join(game_dir, "menu", "steam")
    shutil.rmtree(art, ignore_errors=True)
    os.makedirs(art)
    for stem, _pattern in PIECES:
        with open(os.path.join(art, stem + extension), "wb") as fh:
            fh.write(("%s %s" % (tag, stem)).encode())


def grid_holds(grid, appid, tag, extension=".png"):
    """Every piece in the grid folder under this appid is the one tagged so."""
    for stem, pattern in PIECES:
        path = os.path.join(grid, (pattern % appid) + extension)
        if not os.path.isfile(path) or open(path, "rb").read() != ("%s %s" % (tag, stem)).encode():
            return False
    return True


def steam_entry(appid, name, exe):
    """A shortcut as Steam itself writes one: its own appid, not the one Rialto works out."""
    return (b"\x000\x00" + b"\x02appid\x00" + struct.pack("<I", appid)
            + b"\x01AppName\x00" + name.encode() + b"\x00"
            + b"\x01Exe\x00\"" + exe.encode() + b"\"\x00"
            + b"\x01StartDir\x00\"" + os.path.dirname(exe).encode() + b"\"\x00"
            + b"\x00tags\x00\x08" + b"\x08")


def first_disc(tmp):
    """The game installed and added to Steam from its first disc; a second disc's menu then."""
    game_dir, exe = shortcuts.make_disc(tmp, with_art=False)
    put_art(game_dir, "first")
    vdf = os.path.join(tmp, "Steam", "userdata", "123456789", "config", "shortcuts.vdf")
    os.makedirs(os.path.dirname(vdf), exist_ok=True)
    menu = shortcuts.make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
    menu.add_to_steam()
    return game_dir, exe, vdf, menu


def main():
    print("ADD TO STEAM from a later disc of the same game\n")
    work = tempfile.mkdtemp(prefix="rialto_later_disc_")
    try:
        print("1. a later disc with its own pictures")
        tmp = os.path.join(work, "one")
        game_dir, exe, vdf, menu = first_disc(tmp)
        grid = os.path.join(os.path.dirname(vdf), "grid")
        appid = menu._steam_appid("Mock Game", exe)
        ok("the first disc adds the game, with its pictures", menu.said[-1][0] == "Added to Steam"
           and grid_holds(grid, appid, "first"), menu.said)
        os.remove(os.path.join(grid, "%d.json" % appid))
        listed = open(vdf, "rb").read()
        put_art(game_dir, "second")
        later = shortcuts.make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        later.menu_title = "Mock Game Deluxe"  # another name, so another _steam_appid
        later.add_to_steam()
        title, text, detail = later.said[-1]
        ok("it says Already in Steam", title == "Already in Steam" and "Mock Game Deluxe" in text, later.said)
        ok("and that its pictures are updated from this disc", detail == UPDATED, detail)
        ok("every piece is this disc's, under the appid the list files the shortcut under",
           grid_holds(grid, appid, "second"))
        other = later._steam_appid("Mock Game Deluxe", exe)
        ok("none under the appid the new name would make", not any(
            os.path.exists(os.path.join(grid, (p % other) + ".png")) for _s, p in PIECES))
        ok("the list is not written", open(vdf, "rb").read() == listed)
        ok("and no .rialto-backup is made", not os.path.exists(vdf + ".rialto-backup"))
        ok("nothing is left beside the list", sorted(os.listdir(os.path.dirname(vdf))) == ["grid", "shortcuts.vdf"],
           os.listdir(os.path.dirname(vdf)))
        place = os.path.join(grid, "%d.json" % appid)
        ok("the logo's place is written when it is absent", os.path.isfile(place)
           and json.load(open(place))["logoPosition"]["pinnedPosition"] == "BottomLeft")
        with open(place, "w") as fh:
            fh.write('{"nVersion":1,"logoPosition":{"pinnedPosition":"CenterCenter"}}')
        put_art(game_dir, "third", ".jpg")
        later.add_to_steam()
        ok("a third disc's JPGs take the place of the PNGs", grid_holds(grid, appid, "third", ".jpg") and not any(
            os.path.exists(os.path.join(grid, (p % appid) + ".png")) for _s, p in PIECES))
        ok("and the place the player set is left alone", "CenterCenter" in open(place).read())
        print()

        print("2. a later disc with no Steam art")
        shutil.rmtree(os.path.join(game_dir, "menu", "steam"))
        before = sorted((n, open(os.path.join(grid, n), "rb").read()) for n in os.listdir(grid))
        later.add_to_steam()
        title, _text, detail = later.said[-1]
        ok("Already in Steam, with the old words", title == "Already in Steam" and detail == (
            "Nothing was changed. Remove it from Steam first if you want to add it again."), detail)
        ok("and the grid folder is as it was", sorted(
            (n, open(os.path.join(grid, n), "rb").read()) for n in os.listdir(grid)) == before)
        ok("the list is still not written", open(vdf, "rb").read() == listed)
        print()

        print("3. Steam running: refused, as before")
        put_art(game_dir, "fourth")
        running = shortcuts.make_menu(tmp, game_dir, [vdf], steam_running=True, resolved_exe=exe)
        running.add_to_steam()
        ok("it says to exit Steam first", running.said[-1][0] == "Exit Steam first", running.said)
        ok("and no picture is touched", sorted(
            (n, open(os.path.join(grid, n), "rb").read()) for n in os.listdir(grid)) == before)
        print()

        print("4. a shortcut Steam wrote itself, with its own appid, beside another game")
        tmp = os.path.join(work, "four")
        game_dir, exe = shortcuts.make_disc(tmp, with_art=False)
        put_art(game_dir, "disc")
        vdf = os.path.join(tmp, "Steam", "userdata", "1", "config", "shortcuts.vdf")
        theirs = 0x8ABCDEF0
        seed = shortcuts.make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        other = seed._vdf_shortcut_entry(1, "Someone Elses Game", r"C:\Other\thing.exe", r"C:\Other", "")
        shortcuts.new_vdf(vdf, steam_entry(theirs, "Mock Game", exe) + other)
        listed = open(vdf, "rb").read()
        grid = os.path.join(os.path.dirname(vdf), "grid")
        menu = shortcuts.make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        ok("the list's appid is read for the game's Exe",
           menu._vdf_present_shortcuts(listed) == {
               os.path.normcase(os.path.normpath(exe)): [(theirs, "")],
               os.path.normcase(r"C:\Other\thing.exe"):
                   [(menu._steam_appid("Someone Elses Game", r"C:\Other\thing.exe"), "")]},
           menu._vdf_present_shortcuts(listed))
        menu.add_to_steam()
        ok("the pictures go under Steam's own appid for it", grid_holds(grid, theirs, "disc"))
        ok("the other game gets none", not any(name.startswith(str(menu._steam_appid(
            "Someone Elses Game", r"C:\Other\thing.exe"))) for name in os.listdir(grid)), os.listdir(grid))
        ok("the list is not written", open(vdf, "rb").read() == listed)
        ok("an unreadable list gives no appids, it raises", raises(menu._vdf_present_shortcuts, listed[:-9]))
        print()

        print("5. the words in every language the menu has")
        tree = ast.parse(shortcuts.menu_source(open(shortcuts.RIALTO, encoding="utf-8").read()))
        table = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and any(getattr(t, "attr", "") == "translations" for t in n.targets))
        missing = [lang for lang, words in table.items() if not words.get("steam_art_updated", "").strip()
                   or words["steam_art_updated"] == words.get("steam_already_detail")]
        ok("all %d languages say it, in their own words" % len(table), not missing and len(table) >= 30, missing)
        ok("English says it in his words", table["English"].get("steam_art_updated") == UPDATED)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()

    if FAILURES:
        print("FAILED (%d):" % len(FAILURES))
        for line in FAILURES:
            print("  - " + line)
        return 1
    print("All later-disc checks passed.")
    return 0


def raises(call, *args):
    try:
        call(*args)
    except (ValueError, IndexError):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
