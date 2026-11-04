"""ADD TO STEAM from a later disc: what the press keeps, and which shortcuts it reaches (1.5.2, review of 4 Nov).

1. Pictures already in the grid folder, the player's own among them, are kept
   beside the new ones as <name>.rialto-backup before they are replaced or
   removed; the same disc pressed again keeps nothing new and loses nothing.
2. A list entry with no appid field is filed by Steam under the id it works
   out from the Exe and AppName as stored (quotes and all): the pictures go
   there, never under a guess from this disc's name. An entry with neither
   gets no pictures, and the box keeps the old words.
3. Every shortcut with the game's Exe gets the pictures, not only the first.
4. The Shortcut Icon: where the list's icon field already names the grid copy
   an earlier disc made, this disc's icon goes over it; a field naming the
   installed game_icon.ico is left alone, and the Help Guide says so.

Everything runs on temp folders through the stub disc menu of
test_steam_shortcuts.py, with the real methods: never the real Steam folder.

Usage: python test_steam_later_disc_kept.py [path-to-Rialto.pyw]
"""
import os
import shutil
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_steam_later_disc as later  # noqa: E402  put_art, grid_holds, the pieces and his words
import test_steam_shortcuts as shortcuts  # noqa: E402  the stub disc menu with the real Steam methods on it

FAILURES = []
OLD_WORDS = "Nothing was changed. Remove it from Steam first if you want to add it again."


def ok(label, passed, detail=""):
    print("  [%s] %s" % ("OK  " if passed else "FAIL", label))
    if not passed:
        FAILURES.append("%s: %r" % (label, detail))


def entry(index, exe, name=None, appid=None, icon=None):
    """A list entry as some other writer leaves one: any of appid, AppName and icon may be missing."""
    out = b"\x00" + str(index).encode() + b"\x00"
    if appid is not None:
        out += b"\x02appid\x00" + struct.pack("<I", appid)
    if name is not None:
        out += b"\x01AppName\x00" + name.encode() + b"\x00"
    out += b"\x01Exe\x00\"" + exe.encode() + b"\"\x00"
    if icon is not None:
        out += b"\x01icon\x00" + icon.encode() + b"\x00"
    return out + b"\x00tags\x00\x08" + b"\x08"


def setup(work, tag, entries_for):
    """An installed game with this disc's art, and a list made by entries_for(exe, grid)."""
    tmp = os.path.join(work, tag)
    game_dir, exe = shortcuts.make_disc(tmp, with_art=False)
    later.put_art(game_dir, "disc")
    vdf = os.path.join(tmp, "Steam", "userdata", "1", "config", "shortcuts.vdf")
    grid = os.path.join(os.path.dirname(vdf), "grid")
    shortcuts.new_vdf(vdf, entries_for(exe, grid))
    menu = shortcuts.make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
    menu.menu_title = "Mock Game Deluxe"
    return game_dir, exe, vdf, grid, menu


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def names(grid):
    """What the grid folder holds; nothing when the press never made it."""
    return sorted(os.listdir(grid)) if os.path.isdir(grid) else []


def player_art(work):
    print("1. the pictures there before are kept beside the new ones")
    appid = 0x8000BEEF
    game_dir, exe, vdf, grid, menu = setup(work, "kept", lambda exe, grid: entry(0, exe, "Mock Game", appid))
    os.makedirs(grid)
    for name, body in (("%dp.jpg" % appid, b"player capsule"), ("%d_hero.jpg" % appid, b"player hero"),
                       ("%d.png" % appid, b"player header")):
        with open(os.path.join(grid, name), "wb") as fh:
            fh.write(body)
    listed = read(vdf)
    menu.add_to_steam()
    ok("the box says the pictures are updated", menu.said[-1][2] == later.UPDATED, menu.said)
    ok("this disc's pictures are in place", later.grid_holds(grid, appid, "disc"), os.listdir(grid))
    kept = {n: read(os.path.join(grid, n)) for n in os.listdir(grid) if n.endswith(".rialto-backup")}
    ok("the player's own are kept beside them", kept == {
        "%dp.jpg.rialto-backup" % appid: b"player capsule", "%d_hero.jpg.rialto-backup" % appid: b"player hero",
        "%d.png.rialto-backup" % appid: b"player header"}, kept)
    ok("and none of them stands in for this disc's", not any(
        os.path.exists(os.path.join(grid, "%d%s.jpg" % (appid, s))) for s in ("p", "_hero")))
    menu.add_to_steam()
    again = {n: read(os.path.join(grid, n)) for n in os.listdir(grid) if n.endswith(".rialto-backup")}
    ok("the same disc pressed again keeps the player's pictures as they were", again == kept, again)
    ok("the list is not written", read(vdf) == listed and not os.path.exists(vdf + ".rialto-backup"))
    print()


def no_appid(work):
    print("2. an entry with no appid: Steam's own id from the Exe and AppName as stored")
    game_dir, exe, vdf, grid, menu = setup(work, "noid", lambda exe, grid: entry(0, exe, "Mock Game"))
    steams = (zlib.crc32(('"%s"' % exe).encode() + b"Mock Game") | 0x80000000) & 0xFFFFFFFF
    menu.add_to_steam()
    ok("the pictures go under the id Steam works out", later.grid_holds(grid, steams, "disc"), names(grid))
    guess = menu._steam_appid("Mock Game Deluxe", exe)
    ok("none under a guess from this disc's name", not any(n.startswith(str(guess)) for n in names(grid)))
    ok("and the box says they are updated", menu.said[-1][2] == later.UPDATED, menu.said)

    game_dir, exe, vdf, grid, menu = setup(work, "bare", lambda exe, grid: entry(0, exe))
    menu.add_to_steam()
    ok("an entry with neither appid nor AppName gets no pictures", not names(grid), names(grid))
    ok("and the box keeps the old words", menu.said[-1][0] == "Already in Steam"
       and menu.said[-1][2] == OLD_WORDS, menu.said)
    print()


def two_shortcuts(work):
    print("3. two shortcuts to the game: both get the pictures")
    first, second = 0x80000AAA, 0x80000BBB
    game_dir, exe, vdf, grid, menu = setup(work, "two", lambda exe, grid: entry(0, exe, "Mock Game", first)
                                           + entry(1, exe, "My Own Name", second))
    menu.add_to_steam()
    ok("Rialto's shortcut", later.grid_holds(grid, first, "disc"))
    ok("and the one the player added", later.grid_holds(grid, second, "disc"), os.listdir(grid))
    print()


def shortcut_icon(work):
    print("4. the Shortcut Icon")
    appid = 0x80000CCC
    game_dir, exe, vdf, grid, menu = setup(work, "icon", lambda exe, grid: entry(
        0, exe, "Mock Game", appid, os.path.join(grid, "%d_icon.png" % appid)))
    os.makedirs(grid)
    icon = os.path.join(grid, "%d_icon.png" % appid)
    with open(icon, "wb") as fh:
        fh.write(b"first disc icon")
    with open(os.path.join(game_dir, "menu", "steam", "icon.png"), "wb") as fh:
        fh.write(b"this disc icon")
    listed = read(vdf)
    menu.add_to_steam()
    ok("this disc's icon goes over the copy the list names", read(icon) == b"this disc icon")
    ok("the earlier one is kept beside it", read(icon + ".rialto-backup") == b"first disc icon")
    ok("the list is not written", read(vdf) == listed)

    installed = os.path.join(work, "icon2", "install", "game_icon.ico")
    game_dir, exe, vdf, grid, menu = setup(work, "icon2", lambda exe, grid: entry(
        0, exe, "Mock Game", appid, installed))
    with open(os.path.join(game_dir, "menu", "steam", "icon.png"), "wb") as fh:
        fh.write(b"this disc icon")
    menu.add_to_steam()
    ok("a field naming the installed game_icon.ico is left alone", not any(
        "_icon" in n for n in names(grid)), names(grid))
    guide = open(os.path.join(os.path.dirname(HERE), "docs", "rialto-guide.html"), encoding="utf-8").read()
    ok("the Help Guide says when the Shortcut Icon changes", " ".join((
        "When the game is already in Steam, from an earlier disc, the button updates its pictures from this",
        "disc. The Shortcut Icon changes only when the earlier disc gave one of the same kind, .ico or .png.",
    )) in " ".join(guide.split()))
    print()


def main():
    print("ADD TO STEAM from a later disc: what it keeps, and which shortcuts it reaches\n")
    work = tempfile.mkdtemp(prefix="rialto_later_kept_")
    try:
        player_art(work)
        no_appid(work)
        two_shortcuts(work)
        shortcut_icon(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if FAILURES:
        print("FAILED (%d):" % len(FAILURES))
        for line in FAILURES:
            print("  - " + line)
        return 1
    print("All kept-picture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
