"""A background with its own title, and the disc's own font and colours (1.5.2, his words of 21 October and 3 November 2026).

A developer whose menu background already shows the game's name ticks "Hide
the menu's title and logo" beside Menu Background. The disc menu then lays
nothing over the picture: no dark shading, no title (text or logo), and the
buttons sit at the foot of the column so the top of the art stays clear. A
soft dark edge around the letters keeps them readable on a bright picture, and
the quiet lines are lit a little more. Every other disc's menu is exactly what
it was. Font and Colors... beside it sets the menu's own font (only with its
license), its three colours, its size and its top line.

The menu half opens the real disc menu off screen (the Windows fonts, as in
test_play_games_menu.py); the build half runs the real build_menu_config and
reads the profile, session and reset code. Part 9 reads fonts as Windows does
and holds that against Qt; part 11 holds the build's warning about a squeezed
column against the real menu; part 12 holds the letter edge's layer against
the effect it replaced, picture for picture, and over a moving GIF.
"""
import ast
import json
import os
import runpy
import shutil
import struct
import sys
import tempfile
import textwrap
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ.pop("RIALTO_PREVIEW", None)
# The menu keeps a player's language and stars under %LOCALAPPDATA%, by title, and Windows names
# are not case sensitive: a test disc called DEMO DISC would write into a real Demo Disc's file.
APPDATA = tempfile.mkdtemp(prefix="rialto_title_in_art_appdata_")
os.environ["LOCALAPPDATA"] = APPDATA

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: E402

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


SRC = open(RIALTO, encoding="utf-8").read()
TREE = ast.parse(SRC)
TEMPLATE = ast.literal_eval(next(
    n.value for n in TREE.body
    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))


def settle():
    app = QtWidgets.QApplication.instance()
    for _ in range(6):
        app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def png(path, size=(400, 150), colour=(220, 180, 40, 255)):
    image = QtGui.QImage(size[0], size[1], QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor(*colour))
    image.save(path)


def open_menu(root, games, own_art, installed=True, logo=True, bonus=True, theme=None, font=None,
              extra=None, patch=None, picture=None):
    """A staged install folder with its menu, opened off screen. Returns (module, window).

    `extra` is more of menu_config.json, `patch` is called with the menu's module
    before the window is made, and `picture` is a background file to use.
    """
    menu = os.path.join(root, "menu")
    os.makedirs(menu, exist_ok=True)
    if font:
        shutil.copy2(font, os.path.join(menu, "menu_font" + os.path.splitext(font)[1].lower()))
    script = os.path.join(menu, "menu_launcher.pyw")
    with open(script, "w", encoding="utf-8") as f:
        f.write(TEMPLATE)
    if picture:
        shutil.copy2(picture, os.path.join(menu, "background" + os.path.splitext(picture)[1].lower()))
    else:
        # A bright picture: the case the letter edge is for.
        background = QtGui.QImage(1280, 720, QtGui.QImage.Format_RGB32)
        background.fill(QtGui.QColor(240, 240, 240))
        background.save(os.path.join(menu, "background.jpg"))
    if logo:
        png(os.path.join(menu, "game_logo.png"))
    listed = []
    for name in games:
        folder = os.path.join(root, name.replace(" ", "_"))
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, "Game.exe"), "wb").close()
        listed.append({"name": name, "exe": name.replace(" ", "_") + "/Game.exe"})
    if bonus:
        os.makedirs(os.path.join(root, "bonus"), exist_ok=True)
    if installed:
        open(os.path.join(root, "unins000.exe"), "wb").close()
    config = {"title": "DEMO DISC", "games": listed, "remove_wti_branding": True,
              "copyright_text": "Published by Owlbright.", "language": "English"}
    if len(listed) == 1:
        config["game_exe"] = listed[0]["exe"]
    if own_art:
        config["background_has_title"] = True
    if theme is not None:
        config["theme"] = theme
    config.update(extra or {})
    with open(os.path.join(menu, "menu_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)
    mod = runpy.run_path(script, run_name="menu_under_test")
    if patch is not None:
        patch(mod)
    window = mod["GameMenu"]()
    window.show()
    settle()
    return mod, window


def top(window, widget):
    return widget.mapTo(window, QtCore.QPoint(0, 0)).y()


def bottom(window, widget):
    return top(window, widget) + widget.height()


def shading(window):
    return [w for w in window.findChildren(QtWidgets.QWidget)
            if "rgba(0, 0, 0, 30)" in w.styleSheet()]


def gradients(window):
    return [w for w in window.findChildren(QtWidgets.QWidget) if "qlineargradient" in w.styleSheet()]


def titles(window):
    """Labels in the menu column showing the title text or a picture (the logo)."""
    found = []
    for label in window.findChildren(QtWidgets.QLabel):
        if label is getattr(window, "background", None) or label is getattr(window, "movie_label", None):
            continue
        if label.text().strip().upper() == "DEMO DISC":
            found.append(label)
        elif label.pixmap() is not None and not label.pixmap().isNull():
            found.append(label)
    return found


def edged(widget):
    """The letter edge: drawn by the menu's layer under the column (LetterEdges), never an effect on the label."""
    layer = getattr(widget.window(), "letter_edges", None)
    return layer is not None and id(widget) in layer.labels and widget.graphicsEffect() is None


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
work = tempfile.mkdtemp(prefix="rialto_title_in_art_")
try:
    print("1. The usual menu is untouched: shading, the logo, the buttons under it")
    _mod, usual = open_menu(os.path.join(work, "usual"), ["Marlow"], own_art=False)
    height = usual.height()
    says("the dark shading is laid over the picture", len(shading(usual)) == 1)
    says("the menu column keeps its dark band", len(gradients(usual)) >= 1)
    says("the game's logo is shown", len(titles(usual)) == 1, [l.text() for l in titles(usual)])
    says("PLAY sits under the logo, high in the window",
         top(usual, usual.play_btn) < height * 0.45, (top(usual, usual.play_btn), height))
    says("no letter edge on the usual menu", not edged(usual.play_btn) and not edged(usual.exit_btn))
    usual.close()

    _mod, usual_text = open_menu(os.path.join(work, "usual-text"), ["Marlow"], own_art=False, logo=False)
    says("with no logo, the title is written out", any(
        l.text().strip().upper() == "DEMO DISC" for l in usual_text.findChildren(QtWidgets.QLabel)))
    usual_text.close()
    print()

    print("2. Title and logo hidden: nothing over the picture")
    _mod, own = open_menu(os.path.join(work, "own"), ["Marlow"], own_art=True)
    says("no dark shading over the picture", shading(own) == [])
    says("no dark band down the menu column", gradients(own) == [])
    says("no title and no logo, though game_logo.png is beside the menu", titles(own) == [],
         [(l.text(), l.pixmap() is not None) for l in titles(own)])
    says("the window keeps its one size", own.size() == usual.size(), (own.size(), usual.size()))
    print()

    print("3. Title and logo hidden: the buttons sit at the foot of the column")
    says("PLAY moves down, below the top of the picture",
         top(own, own.play_btn) > height * 0.35, (top(own, own.play_btn), height))
    says("EXIT stays above the language box",
         bottom(own, own.exit_btn) <= top(own, own.lang_label.parentWidget()) + 1,
         (bottom(own, own.exit_btn), top(own, own.lang_label.parentWidget())))
    says("the language box stays in the window",
         bottom(own, own.lang_label.parentWidget()) <= height,
         (bottom(own, own.lang_label.parentWidget()), height))
    print()

    print("4. Title and logo hidden: the letters read on a bright picture")
    says("PLAY, UNINSTALL and EXIT carry a dark edge",
         edged(own.play_btn) and edged(own.uninstall_btn) and edged(own.exit_btn))
    says("the language label carries one too", edged(own.lang_label))
    says("the quiet lines are lit more than on the shaded menu",
         "#c8c8c8" in own.quick_style and "#888888" not in own.quick_style)
    own.close()
    print()

    print("5. Title and logo hidden, a disc of many games: the list still fits")
    many = ["Game %02d" % n for n in range(1, 14)]
    _mod, crowd = open_menu(os.path.join(work, "crowd"), many, own_art=True)
    says("every game has its line", len(crowd.quick_btns) == len(many), len(crowd.quick_btns))
    says("each line carries the dark edge, even rebuilt after a star",
         all(edged(b) for b in crowd.quick_btns))
    crowd.refresh_quick_starts()
    settle()
    says("and after the list is rebuilt", all(edged(b) for b in crowd.quick_btns))
    says("PLAY GAMES stays in the window", top(crowd, crowd.play_btn) >= 0, top(crowd, crowd.play_btn))
    says("EXIT stays above the language box",
         bottom(crowd, crowd.exit_btn) <= top(crowd, crowd.lang_label.parentWidget()) + 1,
         (bottom(crowd, crowd.exit_btn), top(crowd, crowd.lang_label.parentWidget())))
    crowd.close()
    print()

    print("6. Title and logo hidden before install (the disc's own menu): PLAY installs")
    _mod, fresh = open_menu(os.path.join(work, "fresh"), ["Marlow"], own_art=True, installed=False)
    says("no shading, no title before install either", shading(fresh) == [] and titles(fresh) == [])
    fresh.close()
    print()
finally:
    shutil.rmtree(work, ignore_errors=True)


print("7. The disc's own font and colours")
# A Windows font stands in for the developer's, so this runs on any Windows PC.
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "georgia.ttf")
CLIENT = {"font": "menu_font.ttf", "text": "#f1e4cf", "accent": "#e8c25b", "quiet": "#dccfb8",
          "scale": 1.12, "top": 240}
work = tempfile.mkdtemp(prefix="rialto_menu_theme_")
try:
    _mod, themed = open_menu(os.path.join(work, "themed"), ["10hit", "Brazilian Drug Dealer Before 4", "BRINE"],
                             own_art=True, theme=CLIENT, font=FONT)
    family = themed.theme["family"]
    says("the font beside the menu is loaded, and named", family == "Georgia", family)
    says("the headings wear it, in its one weight",
         'font-family: "Georgia"; font-weight: normal;' in themed.play_btn.styleSheet())
    says("the words take the theme's colour", "color: #f1e4cf" in themed.play_btn.styleSheet())
    says("the focus look takes the accent", "#e8c25b" in themed.play_btn.styleSheet())
    says("the quiet lines take the quiet colour and the font",
         "#dccfb8" in themed.quick_style and 'font-family: "Georgia"' in themed.quick_style)
    says("the size grows by the theme's scale",
         ("font-size: %dpx" % int(22 * themed.scale_factor * 1.12)) in themed.play_btn.styleSheet())
    says("PLAY never rises above the theme's top line",
         top(themed, themed.play_btn) >= int(240 * themed.scale_factor) - 1,
         (top(themed, themed.play_btn), int(240 * themed.scale_factor)))
    says("EXIT stays above the language box",
         bottom(themed, themed.exit_btn) <= top(themed, themed.lang_label.parentWidget()) + 1)
    seen = {}

    def look():
        dialog = QtWidgets.QApplication.activeModalWidget()
        if dialog is not None:
            seen["sheet"] = dialog.styleSheet()
            dialog.reject()

    QtCore.QTimer.singleShot(0, look)
    themed.show_game_chooser()
    sheet = seen.get("sheet", "")
    says("the Choose Your Game page wears the font and the accent",
         'font-family: "Georgia"' in sheet and "#e8c25b" in sheet, sheet[:80])
    themed.close()

    bad = {"font": "..\\..\\evil.ttf", "text": "red", "accent": "#12345", "quiet": "#zzzzzz",
           "scale": 9, "top": -5}
    _mod, refused = open_menu(os.path.join(work, "refused"), ["Marlow"], own_art=True, theme=bad, font=FONT)
    says("a font named with a path, colours that are not six hex digits, a scale or top line out of range: "
         "all left at the menu's own",
         refused.theme == {"text": "", "accent": "", "quiet": "", "family": "", "scale": 1.0, "top": 0},
         refused.theme)
    says("and the menu still opens with its own look", refused.font_rule == "" and
         "color: #ffffff" in refused.play_btn.styleSheet())
    refused.close()

    _mod, plain = open_menu(os.path.join(work, "plain"), ["Marlow"], own_art=False, font=FONT)
    says("a font file with no theme asking for it changes nothing", plain.font_rule == "")
    says("and its labels are never refitted", not hasattr(plain.play_btn, "_rialto_full_sheet"))
    plain.close()

    big = dict(CLIENT, scale=1.5)
    _mod, wide = open_menu(os.path.join(work, "wide"), ["10hit", "BRINE"], own_art=True, theme=big, font=FONT,
                           installed=True)
    room = int(390 * wide.scale_factor) - int(15 * wide.scale_factor)
    heads = [b for b in (wide.play_btn, getattr(wide, "bonus_btn", None), wide.uninstall_btn, wide.exit_btn) if b]
    cut = []
    for lang in sorted(wide.translations):
        wide.change_language(lang)
        settle()
        for b in heads:
            if b.sizeHint().width() > room:
                sheet = b.styleSheet()
                at = sheet.find("font-size: ")
                size = int(sheet[at + 11:sheet.find("px", at)])
                full = int(22 * wide.scale_factor * 1.5)
                if size > max(1, int(full * 0.7)):
                    cut.append((lang, b.text(), b.sizeHint().width(), room))
    says("at scale 1.5, every heading fits the column in all %d languages (or sits at its smallest)"
         % len(wide.translations), cut == [], cut[:4])
    wide.change_language("English")
    settle()
    says("and English comes back at full size",
         ("font-size: %dpx" % int(22 * wide.scale_factor * 1.5)) in wide.exit_btn.styleSheet())
    wide.close()
finally:
    shutil.rmtree(work, ignore_errors=True)
print()


print("8. Rialto: the menu's settings ride in the config, the profile and a cleared form")


class Flag:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v

    def set(self, value):
        self._v = value


def module_funcs(names):
    return "\n\n".join(ast.get_source_segment(SRC, n) for n in TREE.body
                       if isinstance(n, ast.FunctionDef) and n.name in names)


def method_src(name):
    app_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    node = next(i for i in app_class.body if isinstance(i, ast.FunctionDef) and i.name == name)
    return textwrap.dedent(ast.get_source_segment(SRC, node))


consts = "\n".join(ast.get_source_segment(SRC, n) for n in TREE.body
                   if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "")
                   in ("_CONTROL_CHARS", "VIDEO_EXTENSIONS", "MENU_DEFAULT_FONT_FACTS",
                       "MENU_FONT_LICENSE_MAX_BYTES", "MENU_FONT_LICENSE_TYPES"))
ns = {"os": os, "re": __import__("re"), "json": json, "shutil": shutil}
exec(consts, ns)
exec(module_funcs({"strip_wti_mentions", "sanitize_text", "split_launch_args", "font_facts", "menu_font_family_ok",
                   "font_license_beside", "menu_font_check", "menu_theme_from_form", "menu_column_overflow",
                   "font_license_problem", "format_megabytes"}), ns)
body = "\n\n".join(method_src(n) for n in ("build_menu_config", "menu_theme_config", "menu_theme_path",
                                             "menu_font_choice", "menu_theme_font", "stage_menu_artwork",
                                             "warn_menu_column_squeezed"))
sys.path.insert(0, HERE)
import store_title_stub  # noqa: E402
ns.update(store_title_stub.namespace(SRC))  # the menu's title names the game (4 Nov 2026)
exec("class Host:\n" + textwrap.indent(body, "    "), ns)
host = ns["Host"]()
for attr, value in dict(entries={"Title": Flag("Demo Disc")}, company_logo_var=Flag(""),
                        publisher_text_var=Flag("Published by Owlbright."), remove_wti_branding=Flag(True),
                        steam_button_var=Flag(False), mod_launcher_var=Flag(False), compat_mode_var=Flag(False),
                        compat_args_var=Flag(""), compat_hint_var=Flag(""), bg_path_var=Flag(""),
                        logo_path_var=Flag(""), menu_music_var=Flag(""), current_game_path="").items():
    setattr(host, attr, value)
host.validated_game_executables = lambda: []
host.detect_primary_game_exe = lambda root: "game.exe"
host.update_status = lambda message: None

says("a host with neither setting (an older caller) writes neither key",
     not ({"background_has_title", "theme"} & set(host.build_menu_config("C:\\nowhere"))))
host.bg_has_title_var = Flag(False)
host.menu_theme = {}
says("off: the config carries neither key, as every disc before 1.5.2",
     not ({"background_has_title", "theme"} & set(host.build_menu_config("C:\\nowhere"))))
host.bg_has_title_var = Flag(True)
says("on: the config says background_has_title",
     host.build_menu_config("C:\\nowhere").get("background_has_title") is True)
says("the disc menu reads the same key", 'self.menu_config.get("background_has_title")' in TEMPLATE)

work = tempfile.mkdtemp(prefix="rialto_theme_build_")
try:
    fonts = os.path.join(work, "fonts")
    os.makedirs(fonts)
    shutil.copy2(FONT, os.path.join(fonts, "Client-Regular.ttf"))
    with open(os.path.join(fonts, "OFL.txt"), "w", encoding="utf-8") as f:
        f.write("SIL Open Font License")
    host.menu_theme = {"Font": os.path.join(fonts, "Client-Regular.ttf"), "Text": "#F1E4CF",
                       "Accent": "#e8c25b", "Quiet": "#dccfb8", "Scale": 1.12, "Top": 240, "Extra": "dropped"}
    theme = host.build_menu_config("C:\\nowhere").get("theme")
    says("a profile's MenuTheme reaches the config as the menu reads it",
         theme == {"text": "#F1E4CF", "accent": "#e8c25b", "quiet": "#dccfb8", "scale": 1.12, "top": 240,
                   "font": "menu_font.ttf"}, theme)
    menu = os.path.join(work, "menu")
    os.makedirs(menu)
    open(os.path.join(menu, "menu_font.otf"), "wb").close()  # a stale font from an earlier build
    host.stage_menu_artwork(menu)
    says("the font is staged beside the menu as menu_font.ttf",
         os.path.isfile(os.path.join(menu, "menu_font.ttf")))
    says("its licence travels with it", os.path.isfile(os.path.join(menu, "menu_font_license.txt")))
    says("an earlier build's font is cleared", not os.path.exists(os.path.join(menu, "menu_font.otf")))

    host.menu_theme = {"Font": os.path.join(fonts, "missing.ttf"), "Text": "white", "Scale": 3, "Top": True}
    says("a missing font, a named colour, a scale and top line out of range: none of it reaches the disc",
         host.build_menu_config("C:\\nowhere").get("theme") is None,
         host.build_menu_config("C:\\nowhere").get("theme"))
    host.stage_menu_artwork(menu)
    says("and the font staged by the last build is cleared", not os.path.exists(os.path.join(menu, "menu_font.ttf")))

    said = []
    host.update_status = said.append
    host.menu_theme = {"Text": "#fff", "Scale": 2, "Font": "gone.ttf", "accent": "#e8c25b"}
    host.build_menu_config("C:\\nowhere")
    host.build_menu_config("C:\\nowhere")
    warned = [m for m in said if "font and colors" in m]
    says("a theme value left out is said, once for the theme, naming each one",
         len(warned) == 1 and all(w in warned[0] for w in ("Text", "Scale", "Font", "'accent'")), said)

    mixed = os.path.join(work, "mixed")
    os.makedirs(mixed)
    shutil.copy2(FONT, os.path.join(mixed, "menu.ttf"))
    open(os.path.join(mixed, "LICENSE.txt"), "w").write("the game's own licence")
    os.makedirs(os.path.join(mixed, "data"))  # a game's folder, though no exe sits at its top
    host.menu_theme = {"Font": os.path.join(mixed, "menu.ttf")}
    del said[:]
    host.stage_menu_artwork(menu)
    says("a LICENSE beside a game is not taken for the font's",
         not os.path.exists(os.path.join(menu, "menu_font_license.txt")))
    says("no license, no font: the font is not staged either", not os.path.exists(os.path.join(menu, "menu_font.ttf")))
    theme = host.build_menu_config("C:\\nowhere").get("theme")
    says("and the config asks for no font", theme is None, theme)
    says("and Rialto says plainly that no license was found, so the font is not used",
         any("no license file was found beside it" in m and "Font" in m for m in said), said)
    picked = os.path.join(work, "Client-OFL.txt")
    with open(picked, "w", encoding="utf-8") as f:
        f.write("the font's own OFL, kept apart")
    host.menu_theme = {"Font": os.path.join(mixed, "menu.ttf"), "License": picked}
    host.stage_menu_artwork(menu)
    says("a license the author picks lets the font ride, and it is the one staged",
         os.path.isfile(os.path.join(menu, "menu_font.ttf"))
         and open(os.path.join(menu, "menu_font_license.txt"), encoding="utf-8").read()
         == "the font's own OFL, kept apart")
    says("and the config asks for the font", host.build_menu_config("C:\\nowhere").get("theme") == {"font": "menu_font.ttf"})
    host.menu_theme = {"Font": os.path.join(mixed, "menu.ttf"), "License": os.path.join(work, "gone.txt")}
    del said[:]
    host.build_menu_config("C:\\nowhere")
    says("a picked license that is not there: no font, said",
         host.menu_theme_font() == "" and any("license file picked for it is not there" in m for m in said), said)
    host.update_status = lambda message: None

    host.current_game_path = work
    host.menu_theme = {"Font": os.path.join("fonts", "Client-Regular.ttf")}
    says("a font path kept relative is read against the game folder",
         host.build_menu_config("C:\\nowhere").get("theme") == {"font": "menu_font.ttf"})
finally:
    shutil.rmtree(work, ignore_errors=True)

for name, needles in (("current_profile_data", ('profile_data["BackgroundHasTitle"]', 'profile_data["MenuTheme"]')),
                      # Load Profile and the start put a profile on the form through one list (readiness, 4 Nov).
                      ("put_profile_on_form", ('profile_data.get("BackgroundHasTitle"', 'profile_data.get("MenuTheme")')),
                      ("apply_profile_file", ("self.put_profile_on_form(profile_data)",)),
                      ("save_last_session", ('session_data["BackgroundHasTitle"]', 'session_data["MenuTheme"]')),
                      ("load_last_session", ('"BackgroundHasTitle"', '"MenuTheme"')),
                      ("restore_page", ("self.bg_has_title_var.set(False)", "self.menu_theme = {}")),
                      ("load_last_used_profile", ("self.put_profile_on_form(profile_data, at_start=True)",))):
    says("%s carries the menu's settings" % name, all(n in method_src(name) for n in needles))

# The last session, round and back: Rialto closed and opened again with no profile keeps the whole menu look.
session_dir = tempfile.mkdtemp(prefix="rialto_session_")
try:
    session_ns = {"os": os, "json": json, "tk": type("tk", (), {"END": "end"}),
                  "LAST_SESSION_FILE": os.path.join(session_dir, "last_session.json")}
    exec("class Session:\n" + textwrap.indent(method_src("save_last_session") + "\n\n"
                                              + method_src("load_last_session"), "    "), session_ns)

    def session_host():
        host = session_ns["Session"]()
        host.current_game_path, host.entries = "", {}
        host.theme_mode = Flag("dark")
        host.apply_dark_theme = host.apply_light_theme = lambda: None
        for name in ("bg_path_var", "menu_music_var", "logo_path_var", "ico_path_var", "disc_icon_var",
                     "disc_name_var"):
            setattr(host, name, Flag(""))
        host.bg_has_title_var = Flag(False)
        host.steam_art_paths = lambda: {}
        host.set_steam_art = lambda stored: None
        host.menu_theme = {}
        return host

    look = {"Font": r"D:\Games\Sky Quest\fonts\Menu.ttf", "Text": "#f1e4cf", "Accent": "#e8c25b", "Top": 300}
    before = session_host()
    before.bg_has_title_var.set(True)
    before.menu_theme = dict(look)
    before.save_last_session()
    after = session_host()
    after.load_last_session()
    says("the last session keeps Menu Font and Colors, as it keeps the tick box beside it",
         after.menu_theme == look and after.bg_has_title_var.get() is True, after.menu_theme)
    with open(session_ns["LAST_SESSION_FILE"], "w", encoding="utf-8") as fh:
        json.dump({"MenuTheme": ["not", "a", "theme"]}, fh)
    after = session_host()
    after.menu_theme = dict(look)
    after.load_last_session()
    says("a rewritten session's MenuTheme that is not a theme loads as none", after.menu_theme == {}, after.menu_theme)
    with open(session_ns["LAST_SESSION_FILE"], "w", encoding="utf-8") as fh:
        json.dump({"BackgroundHasTitle": True}, fh)
    after = session_host()
    after.load_last_session()
    says("a session from before has no theme, as before", after.menu_theme == {}, after.menu_theme)
finally:
    shutil.rmtree(session_dir, ignore_errors=True)


def literal_strings(name):
    """Every whole string a method of RialtoApp carries, adjacent literals joined as Python joins them."""
    app_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    node = next(i for i in app_class.body if isinstance(i, ast.FunctionDef) and i.name == name)
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


widgets = method_src("create_widgets")
row = widgets[widgets.index('ttk.Label(img_row, text="Menu Background:"'):widgets.index("# game logo")]
says("the tick box is on the Menu Background row, in his words, on the setting the build reads",
     'self.themed_check(img_row, "Hide the menu\'s title and logo", self.bg_has_title_var' in row)
says("its tooltip, in his words",
     "Tick this when your background has the game's name or logo drawn in. The menu then leaves the picture "
     "as it is: no dark shading, no game title or Game Logo on top, and the buttons sit at the foot. The "
     "Company Logo stays in its corner. Leave Company Logo empty to show none."
     in literal_strings("create_widgets"))
says("Font and Colors\u2026 sits beside it and opens Menu Font and Colors",
     'text="Font and Colors\u2026", command=self.configure_menu_theme' in row)
GUIDE = open(os.path.join(REPO, "docs", "rialto-guide.html"), encoding="utf-8").read()
says("the Help Guide has a row for each, under Artwork",
     "<tr><td>Hide the menu's title and logo</td>" in GUIDE and "<tr><td>Font and Colors</td>" in GUIDE)
hide_row = GUIDE[GUIDE.index("<tr><td>Hide the menu's title and logo</td>"):]
hide_row = hide_row[:hide_row.index("</tr>")]
says("its row in American words: a soft dark edge around the words",
     "A soft dark edge around the words" in hide_row and " round the" not in hide_row, hide_row)
dialog_src = method_src("configure_menu_theme")
says("Menu Font and Colors keeps what Save is given by the rule part 10 holds, and checks the font as the "
     "build does", "menu_theme_from_form(" in dialog_src and "self.menu_theme = kept" in dialog_src
     and "menu_font_check(" in dialog_src and "colorchooser.askcolor(" in dialog_src
     and "self.fit_dialog_to_screen(dialog, 640)" in dialog_src)
says("the build looks for a squeezed column once the config is written",
     "self.warn_menu_column_squeezed(output_path)" in method_src("compile_menu_launcher"))
print()


print("9. A font's family name and line height, read from the file as Windows reads it")
font_facts, check = ns["font_facts"], ns["menu_font_check"]
WINDOWS_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
# Windows' own fonts anywhere, and more from the folder RIALTO_TEST_FONTS names when it is set
# (1.5.2 was tried on Google Fonts' downloads, Metamorphous among them).
DOWNLOADED = os.environ.get("RIALTO_TEST_FONTS", "")
candidates = [os.path.join(WINDOWS_FONTS, n) for n in ("georgia.ttf", "arial.ttf", "times.ttf", "segoeui.ttf",
                                                       "segoeuib.ttf", "verdana.ttf", "consola.ttf", "tahoma.ttf")]
if os.path.isdir(DOWNLOADED):
    candidates += sorted(os.path.join(DOWNLOADED, n) for n in os.listdir(DOWNLOADED)
                         if n.lower().endswith((".ttf", ".otf")))
candidates = [c for c in candidates if os.path.isfile(c)]
disagree = []
for path in candidates:
    font_id = QtGui.QFontDatabase.addApplicationFont(path)
    loaded = QtGui.QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    facts = font_facts(path)
    if not facts or not loaded or facts["family"] != loaded[0]:
        disagree.append((os.path.basename(path), facts and facts["family"], loaded[:1]))
says("the family read from the file is the one Qt loads, for each of %d fonts" % len(candidates),
     len(candidates) >= 3 and disagree == [], disagree)
georgia = font_facts(FONT)
sized = QtGui.QFont("Georgia")
sized.setPixelSize(22)
says("and the line height is the font's own: Georgia at 22 px is as tall as Qt draws it",
     georgia and int(-(-georgia["ascent"] * 22 // 1)) + int(-(-georgia["descent"] * 22 // 1))
     == QtGui.QFontMetrics(sized).height(), (georgia, QtGui.QFontMetrics(sized).height()))


def sfnt(records, magic=b"\x00\x01\x00\x00"):
    """A font file holding only a name table: (platform, encoding, language, name id, bytes) for each record."""
    table = struct.pack(">HHH", 0, len(records), 6 + 12 * len(records))
    at = 0
    for platform, encoding, language, name_id, raw in records:
        table += struct.pack(">HHHHHH", platform, encoding, language, name_id, len(raw), at)
        at += len(raw)
    table += b"".join(r[4] for r in records)
    return magic + struct.pack(">HHHH", 1, 16, 0, 0) + b"name" + struct.pack(">III", 0, 28, len(table)) + table


work = tempfile.mkdtemp(prefix="rialto_font_names_")
try:
    def font_file(name, data):
        path = os.path.join(work, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    with open(os.path.join(work, "OFL.txt"), "w", encoding="utf-8") as f:
        f.write("SIL Open Font License")
    win = lambda text, language=0x409: (3, 1, language, 1, text.encode("utf-16-be"))  # noqa: E731
    plain = font_file("Plain.ttf", sfnt([win("Nom Francais", 0x40C), win("Plain Face-2")]))
    says("Windows' US English name is the one taken, over another language's",
         font_facts(plain)["family"] == "Plain Face-2", font_facts(plain))
    says("such a font, with its OFL beside it, is used, and named",
         check(plain)[1:] == (os.path.join(work, "OFL.txt"), "Plain Face-2", ""), check(plain))
    mac = font_file("Mac.otf", sfnt([(1, 0, 0, 1, b"Mac Face")], magic=b"OTTO"))
    says("an OpenType font with only a Mac name is read too", font_facts(mac)["family"] == "Mac Face")
    for name, data, words in (
            ("Odd.ttf", sfnt([win("Odd;Name")]), 'its name, "Odd;Name", has more than letters, digits, spaces and hyphens'),
            ("Nameless.ttf", sfnt([]), "it carries no family name"),
            ("Picture.ttf", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "it is not a TrueType or OpenType font"),
            ("Cut.ttf", b"\x00\x01\x00\x00\x00\x32" + b"\x00" * 10, "it is not a TrueType or OpenType font"),
            ("Web.woff", sfnt([win("Web Face")]), "it is not a .ttf or .otf file")):
        got = check(font_file(name, data))
        says("%s: not used, and said plainly: %s" % (name, words), got[:3] == ("", "", "") and words in got[3], got)
    says("a font that is not there: said", check(os.path.join(work, "Gone.ttf"))[3] == "the file is not there")
    os.remove(os.path.join(work, "OFL.txt"))
    got = check(plain)
    says("no license beside it and none picked: no font, and the words say how to give one",
         got[0] == "" and "no license file was found beside it" in got[3] and "pick the license in Font and Colors" in got[3], got)
    picked = font_file("Its-License.txt", b"OFL")
    says("a license picked by the author is taken instead", check(plain, picked)[1] == picked)
finally:
    shutil.rmtree(work, ignore_errors=True)
print()


print("10. Menu Font and Colors' boxes become the profile's MenuTheme")
form = ns["menu_theme_from_form"]
kept, problems = form({"Font": " C:/Fonts/Client.ttf ", "License": "", "Text": "F1E4CF", "Accent": "#E8C25B",
                       "Quiet": "", "Scale": "1.12", "Top": "240"})
says("colors with or without their #, a size and a top line: kept as the build reads them, empty boxes left out",
     problems == [] and kept == {"Font": "C:/Fonts/Client.ttf", "Text": "#f1e4cf", "Accent": "#e8c25b",
                                 "Scale": 1.12, "Top": 240}, (kept, problems))
kept, problems = form({"Text": "red", "Accent": "#12345", "Scale": "2", "Top": "-5"})
says("a named color, five hex digits, a size and a top line out of range: each named, none kept",
     kept == {} and len(problems) == 4 and problems[0].startswith("Words:") and problems[1].startswith("Chosen item:")
     and problems[2].startswith("Size:") and problems[3].startswith("Top line:"), problems)
says("every box empty is the menu's own look", form({k: "" for k in ("Font", "Text", "Scale", "Top")}) == ({}, []))
host.menu_theme, host.current_game_path = form({"Text": "#f1e4cf", "Scale": "0.8", "Top": "0"})[0], ""
says("and what the dialog keeps reaches the config",
     host.build_menu_config("C:\\nowhere").get("theme") == {"text": "#f1e4cf", "scale": 0.8, "top": 0},
     host.build_menu_config("C:\\nowhere").get("theme"))
print()


print("11. The build says so when the buttons would climb above the top line")
overflow = ns["menu_column_overflow"]
METAMORPHOUS = os.path.join(DOWNLOADED, "metamorphous_Metamorphous-Regular.ttf") if DOWNLOADED else ""
work = tempfile.mkdtemp(prefix="rialto_squeeze_")
misses, apart, cases, squeezed = [], [], 0, 0
# The menu's own words are in Windows' own font, Segoe UI, where Windows draws them. Off screen Qt picks
# another unless told.
own_font = app.font()
app.setFont(QtGui.QFont("Segoe UI", 9))
try:
    for font in [None, FONT] + ([METAMORPHOUS] if os.path.isfile(METAMORPHOUS) else []):
        facts = font_facts(font) if font else None
        for scale in (1.0, 1.25, 1.5):
            for top_line in (180, 300):
                for count in (1, 8):
                    for extras in (False, True):
                        theme = dict({"scale": scale, "top": top_line}, **({"font": "menu_font.ttf"} if font else {}))
                        extra = {"steam_button": True, "compat_mode": True, "compat_args": ["-dx11"]} if extras else {}
                        names = ["Game %02d" % n for n in range(count)]
                        _mod, squeeze = open_menu(os.path.join(work, str(cases)), names, own_art=True, logo=False,
                                                  bonus=extras, theme=theme, font=font, extra=extra)
                        factor = squeeze.scale_factor
                        real = max(0, int(top_line * factor) - top(squeeze, squeeze.play_btn))
                        squeeze.close()
                        said = overflow(dict(extra, games=[{}] * count, background_has_title=True, theme=theme),
                                        extras, facts, factor)
                        case = (os.path.basename(font or "menu's own"), scale, top_line, count, extras,
                                round(real), said)
                        squeezed += real > 3
                        if real > 3 and not said:
                            misses.append(case)
                        if not real - 4 <= said <= real + 12:
                            apart.append(case)
                        cases += 1
finally:
    app.setFont(own_font)
    shutil.rmtree(work, ignore_errors=True)
says("of %d discs laid out by the real menu, %d squeezed, and the build warns of every one" % (cases, squeezed),
     squeezed > 0 and misses == [], misses[:4])
says("and its count of the pixels is the menu's own within 4, or up to 12 more where a label too wide for the "
     "column steps its type down (the count takes every label at its full size)",
     apart == [], apart[:4])

root = tempfile.mkdtemp(prefix="rialto_squeeze_warn_")
try:
    os.makedirs(os.path.join(root, "menu"))
    os.makedirs(os.path.join(root, "bonus"))

    def warning(config):
        with open(os.path.join(root, "menu", "menu_config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f)
        said = []
        host.update_status = said.append
        host.menu_theme = {}
        over = host.warn_menu_column_squeezed(root)
        host.update_status = lambda message: None
        return over, said

    over, said = warning({"background_has_title": True, "theme": {"scale": 1.5, "top": 300},
                          "games": [{}] * 8, "steam_button": True, "mod_launcher": True})
    says("eight games, every extra button and a big size under a low top line: said at build time, in plain words",
         over > 0 and len(said) == 1 and ("rise about %d pixels above the Top line (300)" % over) in said[0]
         and "set in Font and Colors," in said[0], said)
    over, said = warning({"background_has_title": True, "theme": {"top": 240}, "games": [{}]})
    says("one game under the same kind of line: nothing said", over == 0 and said == [], said)
    over, said = warning({"theme": {"scale": 1.5, "top": 400}, "games": [{}] * 8})
    says("a menu that keeps its own title has no top line to climb over: nothing said", over == 0 and said == [])
finally:
    shutil.rmtree(root, ignore_errors=True)
print()


print("12. The letter edge is drawn from kept pictures: the look it always had, and a moving GIF costs what plain labels cost")


def effect_edge(self, widget):
    """The edge as it was drawn before the layer: a blur effect on each label, run again on every paint."""
    if not getattr(self, "own_art", False):
        return
    edge = QtWidgets.QGraphicsDropShadowEffect(widget)
    edge.setBlurRadius(int(14 * self.scale_factor))
    edge.setOffset(0, 0)
    edge.setColor(QtGui.QColor(0, 0, 0, 255))
    widget.setGraphicsEffect(edge)


def as_before(mod):
    mod["GameMenu"]._shade_text = effect_edge


def no_edge(mod):
    mod["GameMenu"]._shade_text = lambda self, widget: None


def apart_by(first, second):
    """(the largest difference of any channel, the pixels apart by more than 2) between two grabs."""
    from PIL import Image, ImageChops
    images = []
    for grab in (first, second):
        image = grab.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        images.append(Image.frombuffer("RGBA", (image.width(), image.height()),
                                       image.constBits().asstring(image.sizeInBytes()), "raw", "BGRA", 0, 1)
                      .convert("RGB"))
    if images[0].size != images[1].size:
        return 255, -1
    difference = ImageChops.difference(*images).convert("L")
    histogram = difference.histogram()
    return max(i for i, n in enumerate(histogram) if n), sum(histogram[3:])


work = tempfile.mkdtemp(prefix="rialto_letter_edge_")
try:
    # A busy, bright picture: stripes and a sky, where the edge shows most.
    art = QtGui.QImage(1280, 720, QtGui.QImage.Format_RGB32)
    painter = QtGui.QPainter(art)
    sky = QtGui.QLinearGradient(0, 0, 1280, 720)
    sky.setColorAt(0, QtGui.QColor(250, 240, 210))
    sky.setColorAt(1, QtGui.QColor(60, 90, 160))
    painter.fillRect(art.rect(), sky)
    for x in range(0, 1280, 40):
        painter.fillRect(x, 0, 14, 720, QtGui.QColor(255, 255, 255, 90))
    painter.end()
    still = os.path.join(work, "art.jpg")
    art.save(still, quality=95)
    games = ["10hit", "Brazilian Drug Dealer Before 4", "BRINE"]

    looks = {}
    for name, patch in (("layer", None), ("effect", as_before)):
        _mod, edged_menu = open_menu(os.path.join(work, name), games, own_art=True, theme=CLIENT, font=FONT,
                                     picture=still, patch=patch)
        looks[name] = [edged_menu.grab()]
        QtWidgets.QApplication.setActiveWindow(edged_menu)
        edged_menu.play_btn.setFocus()
        settle()
        looks[name].append((edged_menu.play_btn.hasFocus(), edged_menu.grab()))
        if name == "layer":
            says("no label of the menu carries an effect: the layer draws every edge",
                 all(w.graphicsEffect() is None for w in edged_menu.findChildren(QtWidgets.QWidget))
                 and len(edged_menu.letter_edges.labels) >= 7, len(edged_menu.letter_edges.labels))
        edged_menu.close()
    most, many = apart_by(looks["layer"][0], looks["effect"][0])
    says("on a still picture the menu looks as it did with an effect on each label (no channel off by more than 2)",
         most <= 2, (most, many))
    focused = looks["layer"][1][0] and looks["effect"][1][0]
    most, many = apart_by(looks["layer"][1][1], looks["effect"][1][1])
    says("and with PLAY chosen, in the accent with its bar, the layer draws PLAY again to match",
         focused and most <= 2, (focused, most, many))

    crowd_games = ["Game %02d" % n for n in range(1, 14)]
    looks = {}
    for name, patch in (("layer", None), ("effect", as_before)):
        _mod, crowd = open_menu(os.path.join(work, "crowd-" + name), crowd_games, own_art=True, picture=still,
                                patch=patch)
        bar = crowd.quick_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        settle()
        looks[name] = (bar.maximum(), crowd.grab())
        crowd.close()
    most, many = apart_by(looks["layer"][1], looks["effect"][1])
    says("a long list scrolled to its foot: the lines scrolled away stay out of sight, as they did",
         looks["layer"][0] > 0 and most <= 2, (looks["layer"][0], most, many))

    from PIL import Image
    base = Image.open(still).convert("RGB")
    gif = os.path.join(work, "moving.gif")
    base.save(gif, save_all=True, append_images=[base.transpose(Image.FLIP_LEFT_RIGHT), base.rotate(180)],
              duration=100, loop=0)
    costs = {}
    for name, patch in (("layer", None), ("effect", as_before), ("plain labels", no_edge)):
        _mod, moving = open_menu(os.path.join(work, "gif-" + name), games, own_art=True, theme=CLIENT, font=FONT,
                                 picture=gif, patch=patch)
        moving.movie.setPaused(True)
        for _ in range(3):
            moving.movie.jumpToNextFrame()
            moving.repaint()
        made = []
        layer = moving.letter_edges
        if name == "layer":
            drawn = layer.picture
            layer.picture = lambda widget, drawn=drawn: made.append(widget) or drawn(widget)
        spent = []
        for _ in range(30):
            moving.movie.jumpToNextFrame()
            started = time.perf_counter()
            moving.repaint()
            spent.append((time.perf_counter() - started) * 1000)
        costs[name] = sorted(spent)[15]
        if name == "layer":
            says("over 30 frames of a moving GIF no label is drawn again: each frame draws the kept pictures",
                 made == [], len(made))
        moving.close()
    print("     a frame of the GIF, the whole window repainted off screen (median of 30): the layer %.2f ms, "
          "an effect per label %.2f ms, plain labels %.2f ms" % (costs["layer"], costs["effect"], costs["plain labels"]))
finally:
    shutil.rmtree(work, ignore_errors=True)
print()

shutil.rmtree(APPDATA, ignore_errors=True)
if failures:
    print("FAILED: %d check(s)" % len(failures))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("All title-in-the-art and menu theme checks passed.")
