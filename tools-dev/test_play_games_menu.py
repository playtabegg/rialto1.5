"""Play Games on a disc of several games (1.5.1, the owner's word of 19 October 2026).

The real disc menu, opened off screen against a staged install folder: every
game is listed under PLAY GAMES, A to Z; a star lifts a game to the top of that
list and of the Choose Your Game page, and a player can star as many as they
like; the page has no "?" in its title bar (it did nothing); every label starts
in the menu's language and follows a change; the language a player picks is
remembered on the PC; a long list scrolls and never pushes UNINSTALL or EXIT
out of the window.

Opens Qt windows on the offscreen platform: nothing is shown on the desktop.
"""
import ast
import json
import os
import runpy
import shutil
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# Real fonts, so text is measured as on a player's PC: with none, a title that wraps
# measures too short to show what the column does with it.
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ.pop("RIALTO_PREVIEW", None)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def template_source():
    src = open(RIALTO, encoding="utf-8").read()
    return ast.literal_eval(next(
        n.value for n in ast.parse(src).body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))


class Disc:
    """A staged install folder: menu/menu_launcher.pyw, menu/menu_config.json, one exe per game."""

    def __init__(self, root, template):
        self.root = root
        self.menu = os.path.join(root, "menu")
        os.makedirs(self.menu, exist_ok=True)
        self.script = os.path.join(self.menu, "menu_launcher.pyw")
        with open(self.script, "w", encoding="utf-8") as f:
            f.write(template)

    def configure(self, title, names, **extra):
        games = []
        for name in names:
            folder = os.path.join(self.root, name.replace(" ", "_")[:40])
            os.makedirs(folder, exist_ok=True)
            exe = os.path.join(folder, "Game.exe")
            open(exe, "wb").close()
            games.append({"name": name, "exe": os.path.relpath(exe, self.root).replace("\\", "/")})
        config = {"title": title, "games": games}
        config.update(extra)
        with open(os.path.join(self.menu, "menu_config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f)
        return games

    def open(self, prefs=None):
        """A fresh menu module (MENU_CONFIG is read at import) and its window, shown and laid out."""
        mod = runpy.run_path(self.script, run_name="menu_under_test")
        if prefs is not None:
            mod["write_player_prefs"](mod["MENU_TITLE"], prefs)
        window = mod["GameMenu"]()
        window.show()
        settle()
        return mod, window


def settle():
    app = QtWidgets.QApplication.instance()
    for _ in range(5):
        app.processEvents()
        # Rows a page rebuilt are deleted later; inside the page's own loop, now.
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def lines(window):
    return [b.text() for b in window.quick_btns]


def open_chooser(window, inspect):
    """Open the Choose Your Game page, hand it to `inspect`, then close it."""
    seen = {}

    def look():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            seen["result"] = inspect(dialog)
        finally:
            if dialog is not None:
                dialog.reject()

    QtCore.QTimer.singleShot(0, look)
    window.show_game_chooser()
    return seen.get("result")


def row_names(dialog):
    return [w.text().replace(chr(0x200B), "") for w in dialog.findChildren(QtWidgets.QLabel)
            if w.objectName() == "gameName"]


def main():
    template = template_source()
    app = QtWidgets.QApplication(sys.argv)  # noqa: F841 (kept alive for every window below)
    app.setFont(QtGui.QFont("Segoe UI", 9))  # what Windows gives a Qt program
    work = tempfile.mkdtemp(prefix="rialto_playgames_")
    old_appdata = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = os.path.join(work, "appdata")
    try:
        disc = Disc(os.path.join(work, "disc"), template)

        print("1. every game under PLAY GAMES, A to Z, nothing starred to start")
        games = disc.configure("Demo Disc", ["Zeta", "alpha", "Mid"])
        exe = {g["name"]: g["exe"] for g in games}
        mod, window = disc.open()
        says("the top button says PLAY GAMES", window.play_btn.text() == "PLAY GAMES", window.play_btn.text())
        says("all three games listed, A to Z, no stars", lines(window) == ["alpha", "Mid", "Zeta"], lines(window))
        says("the list is on the screen", window.quick_scroll.isVisible())
        says("nothing is starred by default", mod["read_player_prefs"]("Demo Disc")["stars"] == [])
        order = window.nav_buttons()
        says("the keyboard and a controller reach every game, right after PLAY GAMES",
             order[1:4] == window.quick_btns, [b.text() for b in order])
        window.activateWindow()
        window.play_btn.setFocus()
        settle()
        walked = []
        for _ in range(5):
            QTest.keyClick(QtWidgets.QApplication.focusWidget() or window, QtCore.Qt.Key_Down)
            settle()
            walked.append(QtWidgets.QApplication.focusWidget())
        says("Down walks the real keys through every game and on past the list",
             walked[:3] == window.quick_btns and walked[3] is order[4] and walked[4] is order[5],
             [getattr(w, "text", lambda: None)() for w in walked])
        QTest.keyClick(QtWidgets.QApplication.focusWidget() or window, QtCore.Qt.Key_Up)
        QTest.keyClick(QtWidgets.QApplication.focusWidget() or window, QtCore.Qt.Key_Up)
        settle()
        says("and Up walks back into the list", QtWidgets.QApplication.focusWidget() is window.quick_btns[2],
             getattr(QtWidgets.QApplication.focusWidget(), "text", lambda: None)())
        window.play_btn.setFocus()
        settle()
        for key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_Left, QtCore.Qt.Key_Right):
            QTest.keyClick(QtWidgets.QApplication.focusWidget() or window, key)
        settle()
        says("Left and Right never jump past the games", QtWidgets.QApplication.focusWidget() is window.play_btn,
             getattr(QtWidgets.QApplication.focusWidget(), "text", lambda: None)())
        tabbed = []
        for _ in range(4):
            QTest.keyClick(QtWidgets.QApplication.focusWidget() or window, QtCore.Qt.Key_Tab)
            settle()
            tabbed.append(QtWidgets.QApplication.focusWidget())
        says("Tab follows the screen too", tabbed == order[1:5],
             [getattr(w, "text", lambda: None)() for w in tabbed])
        window.close()

        print("2. a star lifts a game to the top; any number of stars")
        mod, window = disc.open({"stars": [exe["Zeta"]], "sort": "disc"})
        says("one star: that game first, the rest A to Z", lines(window) == ["Zeta  ★", "alpha", "Mid"],
             lines(window))
        window.close()
        mod, window = disc.open({"stars": [exe["Zeta"], exe["Mid"]], "sort": "disc"})
        says("two stars: both first, A to Z between them",
             lines(window) == ["Mid  ★", "Zeta  ★", "alpha"], lines(window))
        window.close()
        many = disc.configure("Six Games", ["F", "E", "D", "C", "B", "A"])
        mod, window = disc.open({"stars": [g["exe"] for g in many[:5]], "sort": "disc"})
        says("five of six starred, all five kept", sum(t.endswith("★") for t in lines(window)) == 5,
             lines(window))
        window.close()

        print("3. the Choose Your Game page")
        games = disc.configure("Demo Disc", ["Zeta", "alpha", "Mid"])
        mod, window = disc.open({"stars": [exe["Zeta"]], "sort": "disc"})
        got = open_chooser(window, lambda d: {
            "help": bool(d.windowFlags() & QtCore.Qt.WindowContextHelpButtonHint),
            "rows": row_names(d)})
        says("no \"?\" in its title bar", got and got["help"] is False, got)
        says("the starred game first, then as on the disc", got and got["rows"] == ["ZETA", "ALPHA", "MID"], got)

        def star_alpha(dialog):
            rows = row_names(dialog)
            stars = [b for b in dialog.findChildren(QtWidgets.QPushButton) if b.objectName() == "star"]
            stars[rows.index("ALPHA")].click()
            settle()
            return row_names(dialog)

        rows = open_chooser(window, star_alpha)
        says("starring a second game lifts it too", rows == ["ZETA", "ALPHA", "MID"], rows)
        says("and the main menu follows at once", lines(window) == ["alpha  ★", "Zeta  ★", "Mid"],
             lines(window))
        settle()
        line_h = window.quick_btns[0].sizeHint().height()
        says("and keeps every line in view: a star from the page never squeezes the list",
             window.quick_scroll.height() >= 3 * line_h - 1 and all(b.isVisible() for b in window.quick_btns)
             and window.quick_scroll.maximumHeight() >= 3 * line_h - 1,
             (window.quick_scroll.height(), window.quick_scroll.maximumHeight(), line_h))
        says("both stars kept on the PC", sorted(mod["read_player_prefs"]("Demo Disc")["stars"])
             == sorted([exe["Zeta"], exe["alpha"]]))
        window.player_prefs["sort"] = "az"
        rows = open_chooser(window, row_names)
        says("A to Z keeps the starred games first", rows == ["ALPHA", "ZETA", "MID"], rows)

        def walk_rows(dialog):
            dialog.activateWindow()
            ring = [w for w in dialog.findChildren(QtWidgets.QFrame) if w.objectName() == "gameRow" and w.isVisible()]
            ring[0].setFocus()
            settle()
            seen = []
            for key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Down, QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
                QTest.keyClick(QtWidgets.QApplication.focusWidget() or dialog, key)
                settle()
                focus = QtWidgets.QApplication.focusWidget()
                seen.append(ring.index(focus) if focus in ring else type(focus).__name__)
            return seen

        walked = open_chooser(window, walk_rows)
        says("on the page, Up and Down go row to row and stop at the ends, never onto a star",
             walked == [1, 2, 2, 1], walked)
        window.close()

        print("4. the menu's language")
        mod, window = disc.open({"stars": [], "sort": "disc", "lang": "Japanese"})
        ja = window.translations["Japanese"]
        says("a remembered language opens the menu in it", window.current_lang == "Japanese")
        says("every label starts in it",
             (window.play_btn.text(), window.uninstall_btn.text(), window.exit_btn.text())
             == (ja["play_games"].upper(), ja["uninstall"].upper(), ja["exit"].upper()),
             (window.play_btn.text(), window.uninstall_btn.text(), window.exit_btn.text()))
        window.lang_combo.setCurrentText("French")
        settle()
        says("a new pick is remembered on the PC", mod["read_player_prefs"]("Demo Disc")["lang"] == "French")
        broken = []
        for lang in sorted(window.translations):
            window.change_language(lang)
            t = window.translations[lang]
            want = (window.shout(t["play_games"]), window.shout(t["uninstall"]), window.shout(t["exit"]))
            have = (window.play_btn.text(), window.uninstall_btn.text(), window.exit_btn.text())
            if want != have or not all(want):
                broken.append(lang)
        says("all %d languages relabel the menu" % len(window.translations), not broken, broken)
        broken = []
        for lang in sorted(window.translations):
            if not window.translations[lang]["tip_star"].strip():
                broken.append(lang)
        says("and each has the page's star line", not broken, broken)
        window.change_language("Turkish")
        says("Turkish capitals keep the dot on an i", window.shout("Oyununuzu seçin") == "OYUNUNUZU SEÇİN"
             and window.shout("Çıkış") == "ÇIKIŞ", window.shout("Oyununuzu seçin"))
        window.change_language("Greek")
        says("Greek capitals drop their accents", window.shout("Παίξε") == "ΠΑΙΞΕ"
             and window.play_btn.text() == "ΠΑΙΞΕ", window.play_btn.text())
        window.change_language("German")
        says("every other language is plain capitals", window.play_btn.text() == "SPIELEN", window.play_btn.text())
        shown = []

        def capture(box):
            shown.append((box.windowTitle(), box.text(), box.informativeText(),
                          [b.text() for b in box.buttons()]))
            return 0

        real_exec = QtWidgets.QMessageBox.exec_
        QtWidgets.QMessageBox.exec_ = capture
        try:
            for lang in ("German", "Chinese (Simplified)"):
                window.change_language(lang)
                t = window.translations[lang]
                del shown[:]
                window.open_bonus()
                window.launch_configured_exe("missing/Nothing.exe")
                window._report_missing_game(["C:/Games/Somewhere"])
                window._report_missing_game(["C:/Games/%d" % n for n in range(8)])
                says("%s: and the folder count past six" % lang, (t["and_more"] % 2) in shown[3][2], shown[3][2][-80:])
                says("%s: a popup is in the menu's language, its OK button too" % lang,
                     shown[0] == (t["warning"], t["bonus_not_found"], t["bonus_detail"], [t["ok"]]),
                     shown[:1])
                says("%s: and so are the lines under it" % lang,
                     shown[1][2] == t["looked_for"] % "missing/Nothing.exe"
                     and shown[2][2].startswith(t["looked_in"]) and shown[2][2].endswith(t["play_again"]),
                     [x[2] for x in shown[1:3]])
        finally:
            QtWidgets.QMessageBox.exec_ = real_exec
        window.close()
        disc.configure("Demo Disc", ["Zeta", "alpha", "Mid"], language="German",
                       steam_button=True)
        open(os.path.join(disc.root, "unins000.exe"), "wb").close()
        os.remove(mod["player_prefs_path"]("Demo Disc"))
        mod, window = disc.open()
        de = window.translations["German"]
        says("a disc set to German opens in German, not half in English",
             (window.play_btn.text(), window.uninstall_btn.text(), window.exit_btn.text(),
              window.steam_btn.text() if window.steam_btn else None)
             == (de["play_games"].upper(), de["uninstall"].upper(), de["exit"].upper(), de["steam"]),
             (window.play_btn.text(), window.uninstall_btn.text(), window.exit_btn.text()))
        window.change_language("English")
        says("Add to Steam follows the language too", window.steam_btn.text() == "Add to Steam",
             window.steam_btn.text())
        window.close()
        os.remove(os.path.join(disc.root, "unins000.exe"))
        mod, window = disc.open({"stars": [], "sort": "disc", "lang": "Klingon"})
        says("a language the menu does not have falls back to the disc's", window.current_lang == "German",
             window.current_lang)
        window.close()

        print("5. one game, a long name, a long list")
        disc.configure("Solo", ["Only"])
        mod, window = disc.open()
        says("one game: PLAY GAME, no list", window.play_btn.text() == "PLAY GAME" and not window.quick_btns
             and not window.quick_scroll.isVisible(), window.play_btn.text())
        window.close()
        long_name = "Sky_Quest_Remastered_Definitive_Edition_With_Every_Extra_Ever_Made"
        disc.configure("Long", [long_name, "Short"])
        mod, window = disc.open()
        cut = next(b for b in window.quick_btns if b.text() != "Short")
        says("a long name ends in an ellipsis and shows whole as a tooltip",
             cut.text().endswith("…") and cut.toolTip() == long_name, (cut.text(), cut.toolTip()))
        window.close()
        disc.configure("Thirty", ["Game %02d" % n for n in range(30)])
        mod, window = disc.open()
        height = window.height()

        def bottom(widget):
            return widget.mapTo(window, QtCore.QPoint(0, widget.height())).y()

        says("thirty games listed", len(window.quick_btns) == 30, len(window.quick_btns))
        says("UNINSTALL and EXIT stay inside the window",
             bottom(window.uninstall_btn) <= height and bottom(window.exit_btn) <= height
             and window.exit_btn.isVisible(), (bottom(window.exit_btn), height))
        says("the language box stays inside the window", bottom(window.lang_combo) <= height,
             (bottom(window.lang_combo), height))
        says("the list scrolls instead", window.quick_scroll.height() < window.quick_box.sizeHint().height(),
             (window.quick_scroll.height(), window.quick_box.sizeHint().height()))
        buttons = window.nav_buttons()
        window.current_button_index = 0
        for _ in range(30):
            window.navigate_down(buttons)
        settle()
        says("the keyboard scrolls the last game into view",
             window.quick_scroll.verticalScrollBar().value() > 0
             and window.current_button_index == 30, window.quick_scroll.verticalScrollBar().value())
        window.close()

        print("6. a crowded column")
        title = "The Extraordinary Adventures Of Somebody"
        disc.configure(title, ["Zeta", "alpha"], steam_button=True)
        os.makedirs(os.path.join(disc.root, "bonus"), exist_ok=True)
        open(os.path.join(disc.root, "unins000.exe"), "wb").close()
        mod, window = disc.open()
        label = next(w for w in window.findChildren(QtWidgets.QLabel) if w.text() == title.upper())
        says("a title that wraps keeps every line, with Add to Steam and Bonus there too",
             label.height() >= label.heightForWidth(label.width()) - 1, (label.height(), label.heightForWidth(label.width())))
        says("and EXIT and the language box stay in the window",
             bottom(window.exit_btn) <= window.height() and bottom(window.lang_combo) <= window.height(),
             (bottom(window.exit_btn), bottom(window.lang_combo), window.height()))
        window.close()
        os.makedirs(os.path.join(disc.root, "mods"), exist_ok=True)
        open(os.path.join(disc.root, "mods", "Tool.exe"), "wb").close()
        for long_title in (title, "One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
                                  "Fourteen Fifteen Sixteen Seventeen Eighteen"):
            disc.configure(long_title, ["Zeta", "alpha"], steam_button=True, mod_launcher=True,
                           mod_exe="mods/Tool.exe")
            mod, window = disc.open()
            label = next(w for w in window.findChildren(QtWidgets.QLabel) if w.text() == long_title.upper())
            words_end = label.mapTo(window, QtCore.QPoint(0, label.height())).y() - int(20 * window.scale_factor)
            top = window.play_btn.mapTo(window, QtCore.QPoint(0, 0)).y()
            says("with Mods, Add to Steam and Bonus too, a %d-word title never runs into PLAY GAMES"
                 % len(long_title.split()), window.mods_btn.isVisible() and words_end <= top, (words_end, top))
            says("and both games still show under it", window.quick_scroll.height() >= 2 * window.quick_btns[0].height(),
                 (window.quick_scroll.height(), window.quick_btns[0].height()))
            says("and EXIT and the language box stay in the window ",
                 bottom(window.exit_btn) <= window.height() and bottom(window.lang_combo) <= window.height(),
                 (bottom(window.exit_btn), bottom(window.lang_combo), window.height()))
            window.close()
        shutil.rmtree(os.path.join(disc.root, "mods"))
        disc.configure(title, ["Zeta", "alpha"], steam_button=True)
        logo = QtGui.QImage(512, 512, QtGui.QImage.Format_ARGB32)
        logo.fill(QtGui.QColor(200, 60, 60))
        logo.save(os.path.join(disc.menu, "game_logo.png"))
        mod, window = disc.open()
        pictures = [w for w in window.findChildren(QtWidgets.QLabel)
                    if w.pixmap() is not None and not w.pixmap().isNull() and w.mapTo(window, QtCore.QPoint(0, 0)).x() < 200
                    and w.width() > 100]
        lowest = max((w.mapTo(window, QtCore.QPoint(0, w.height())).y() for w in pictures), default=0)
        top = window.play_btn.mapTo(window, QtCore.QPoint(0, 0)).y()
        says("a square logo on a disc of several games leaves PLAY GAMES clear", pictures and top >= lowest,
             (len(pictures), top, lowest))
        window.close()
        os.remove(os.path.join(disc.menu, "game_logo.png"))
        os.remove(os.path.join(disc.root, "unins000.exe"))
        shutil.rmtree(os.path.join(disc.root, "bonus"))
        prefs = mod["player_prefs_path"](title)
        os.makedirs(os.path.dirname(prefs), exist_ok=True)
        for bad in (b"[" * 100000, b'{"stars": ' + b"[" * 100000 + b"}", b'{"stars": []}' + b" " * 70000):
            with open(prefs, "wb") as f:
                f.write(bad)
            try:
                got = mod["read_player_prefs"](title)
            except BaseException as error:  # noqa: B036 (the point is that nothing escapes)
                got = error
            says("a player.json the menu cannot use is ignored, never a crash (%d bytes)" % len(bad),
                 got == {"stars": [], "sort": "disc", "lang": ""}, repr(got)[:80])
        os.remove(prefs)

        print("7. a controller (a stand-in XInput pad in slot 0)")
        games = disc.configure("Demo Disc", ["Zeta", "alpha", "Mid"])
        exe = {g["name"]: g["exe"] for g in games}
        prefs_file = mod["player_prefs_path"]("Demo Disc")
        if os.path.exists(prefs_file):
            os.remove(prefs_file)
        mod, window = disc.open()
        P = {k: mod[k] for k in ("PAD_UP", "PAD_DOWN", "PAD_LEFT", "PAD_RIGHT", "PAD_A", "PAD_B", "PAD_Y")}

        class Pad:
            """XInputGetState for one pad in slot 0: the buttons and the left stick it is told."""
            def __init__(self):
                self.buttons, self.lx, self.ly = 0, 0, 0

            def __call__(self, slot, state):
                if slot != 0:
                    return 1167  # ERROR_DEVICE_NOT_CONNECTED
                pad = state._obj.Gamepad
                pad.wButtons, pad.sThumbLX, pad.sThumbLY = self.buttons, self.lx, self.ly
                return 0

        pad = Pad()
        says("the menu reads Windows' own XInput, from System32", mod["load_xinput"]() is not None
             and window.gamepad_timer.isActive())
        window.xinput = pad
        window.pad_scan_due = 0
        started = []
        window.start_one_game = lambda exe_, args=None: started.append(exe_)
        window.activateWindow()
        window.play_btn.setFocus()
        settle()

        def tap(bits, hold=80):
            pad.buttons = bits
            QTest.qWait(hold)
            pad.buttons = 0
            QTest.qWait(80)

        def focused():
            return QtWidgets.QApplication.focusWidget()

        tap(P["PAD_DOWN"])
        says("D-pad down moves from PLAY GAMES to the first game", focused() is window.quick_btns[0],
             getattr(focused(), "text", lambda: None)())
        pad.ly = -20000
        QTest.qWait(80)
        pad.ly = 0
        QTest.qWait(80)
        says("so does the left stick", focused() is window.quick_btns[1], getattr(focused(), "text", lambda: None)())
        tap(P["PAD_UP"], hold=700)
        says("held, it repeats like a held key", focused() is window.play_btn or focused() in window.nav_buttons()[-2:],
             getattr(focused(), "text", lambda: None)())
        window.play_btn.setFocus()
        settle()
        for _ in range(3):  # a resting thumb wobbling across the stick's mark, for less than the repeat's wait
            pad.ly = -12100
            QTest.qWait(50)
            pad.ly = -11900
            QTest.qWait(50)
        pad.ly = 0
        QTest.qWait(80)
        says("a thumb wobbling at the stick's mark moves one row, not one per wobble",
             focused() is window.quick_btns[0], getattr(focused(), "text", lambda: None)())
        window.play_btn.setFocus()
        settle()
        tap(P["PAD_DOWN"])
        tap(P["PAD_A"])
        says("A on a game's line starts that game", started == [window.listed_games()[0]["exe"]], started)
        seen = {}

        def drive_page():
            page = QtWidgets.QApplication.activeModalWidget()
            seen["open"] = page is not None and page.windowTitle() == window.translations["English"]["choose_game"]
            seen["first"] = getattr(page.focusWidget(), "exe", None) if page else None
            tap(P["PAD_DOWN"])
            seen["second"] = getattr(page.focusWidget(), "exe", None)
            tap(P["PAD_Y"])
            seen["stars"] = list(window.player_prefs.get("stars", []))
            seen["kept"] = getattr(page.focusWidget(), "exe", None)
            tap(P["PAD_RIGHT"])
            seen["on_star"] = page.focusWidget().objectName() if page.focusWidget() else None
            tap(P["PAD_Y"])
            seen["unstarred"] = list(window.player_prefs.get("stars", []))
            seen["still_on_star"] = getattr(page.focusWidget(), "exe", None), page.focusWidget().objectName()
            tap(P["PAD_LEFT"])
            seen["back_on_row"] = page.focusWidget().objectName(), getattr(page.focusWidget(), "exe", None)
            tap(P["PAD_LEFT"])
            seen["left_on_row_stays"] = page.focusWidget().objectName()
            tap(P["PAD_B"])
            seen["closed"] = QtWidgets.QApplication.activeModalWidget() is None

        del started[:]
        window.play_btn.setFocus()
        settle()
        QtCore.QTimer.singleShot(400, drive_page)
        tap(P["PAD_A"], hold=200)
        QTest.qWait(1500)
        says("A on PLAY GAMES opens the page, the first game ready", seen.get("open") and seen.get("first") == exe["Zeta"],
             seen)
        says("on the page, down moves row to row", seen.get("second") == exe["alpha"], seen)
        says("Y stars the game in focus, and the focus stays on that game", seen.get("stars") == [exe["alpha"]]
             and seen.get("kept") == exe["alpha"], seen)
        says("right reaches its star", seen.get("on_star") == "star", seen)
        says("Y on the star itself unstars it, and the focus stays on that star",
             seen.get("unstarred") == [] and seen.get("still_on_star") == (exe["alpha"], "star"), seen)
        says("left goes back to its row, and left on a row stays put",
             seen.get("back_on_row") == ("gameRow", exe["alpha"]) and seen.get("left_on_row_stays") == "gameRow", seen)
        says("B closes the page", seen.get("closed") is True, seen)
        settle()
        says("and the main menu shows the stars as they were left: none", not any(
            b.text().endswith("★") for b in window.quick_btns), [b.text() for b in window.quick_btns])
        window.play_btn.setFocus()
        settle()
        window.activateWindow()  # Windows gives activation back when a dialog closes; offscreen does not
        settle()
        window.play_btn.setFocus()
        settle()
        tap(P["PAD_DOWN"])
        says("the pad still works on the main menu after the page", focused() is window.quick_btns[0],
             getattr(focused(), "text", lambda: None)())
        window.close()
        if os.path.exists(prefs_file):
            os.remove(prefs_file)

        held = Pad()
        held.buttons = P["PAD_A"]
        menu_globals = mod["GameMenu"].init_controller_support.__globals__  # runpy hands back a copy of them
        real_load = menu_globals["load_xinput"]
        menu_globals["load_xinput"] = lambda: held
        try:
            window = mod["GameMenu"]()
        finally:
            menu_globals["load_xinput"] = real_load
        opened = []
        window.show_game_chooser = lambda args=None: opened.append("page")
        window.start_one_game = lambda exe_, args=None: opened.append(exe_)
        window.show()
        window.activateWindow()
        window.play_btn.setFocus()
        settle()
        QTest.qWait(250)
        says("a button already held as the menu opens is not a press", not opened, opened)
        held.buttons = 0
        QTest.qWait(80)
        held.buttons = P["PAD_A"]
        QTest.qWait(80)
        held.buttons = 0
        QTest.qWait(80)
        says("its next press is", opened == ["page"], opened)
        window.close()

        print("8. the source")
        says("no pygame: nothing new rides on the disc", "pygame" not in template)
        says("XInput is loaded by its full path in System32, never from the disc or the install folder",
             "GetSystemDirectoryW" in template and "os.path.join(system, name)" in template
             and "ctypes.WinDLL(path)" in template)
        says("the keyboard's place shows: focus looks like hover, on the big buttons and the quiet lines",
             template.count("QPushButton:hover, QPushButton:focus {") == 2)
        says("no \"?\" on any dialog the menu opens", "AA_DisableWindowContextHelpButton" in template
             and template.index("AA_DisableWindowContextHelpButton") < template.index("app = QtWidgets.QApplication(sys.argv)"))
        says("a preview never keeps a language either",
             "if not self.preview_mode:\n            write_player_prefs" in template
             and 'self.player_prefs["lang"] = lang\n        self.keep_player_prefs()' in template)
    finally:
        if old_appdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_appdata
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll Play Games checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
