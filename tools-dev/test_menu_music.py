"""Menu Music: a WAV that loops under the disc menu (1.5.2, a developer's ask; his choice of 3 November 2026).

Rialto, Step 4, under Menu Background: Menu Music [Browse]. Its tooltip, his
words: "A WAV file that loops under the menu. It stops while the game or Setup
runs. Players can turn it off with the Sound button." On the disc menu a small
"Sound: On" / "Sound: Off" button in the top corner, beside the close button,
and the player's choice is remembered beside their stars and language.

Windows plays the music itself (the standard library's winsound, PlaySound),
so the menu needs no codec and menu.exe carries nothing of Qt's multimedia.
That is why the file must be a PCM WAV, and why Rialto checks it with the
standard library's wave module before it goes on a disc.

The build half runs Rialto's own check, Browse, staging, config and meter code
against temp folders. The menu half opens the real disc menu off screen (the
Windows fonts, as test_play_games_menu.py does) with winsound faked: nothing is
ever played aloud, and every PlaySound the menu asks for is recorded. The
player's file lives under a temp LOCALAPPDATA, never a real disc's.
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
import types
import wave

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ.pop("RIALTO_PREVIEW", None)
# The menu keeps a player's choices under %LOCALAPPDATA%, by title: a probe titled like a real disc
# would rewrite that disc's file on this PC.
APPDATA = tempfile.mkdtemp(prefix="rialto_menu_music_appdata_")
os.environ["LOCALAPPDATA"] = APPDATA

# winsound faked before the menu is loaded: the menu imports it, and is handed this.
import winsound as _real_winsound  # noqa: E402 (only its four flags are read; nothing is played)

PLAYED = []   # every PlaySound the menu asks for: (sound, flags)
EVENTS = []   # "play", "stop" and "popen", in the order they happened
fake_winsound = types.ModuleType("winsound")
for _flag in ("SND_FILENAME", "SND_ASYNC", "SND_LOOP", "SND_NODEFAULT"):
    setattr(fake_winsound, _flag, getattr(_real_winsound, _flag))


def _play_sound(sound, flags):
    PLAYED.append((sound, flags))
    EVENTS.append("play" if sound else "stop")


fake_winsound.PlaySound = _play_sound
sys.modules["winsound"] = fake_winsound
LOOPED = (_real_winsound.SND_FILENAME | _real_winsound.SND_ASYNC | _real_winsound.SND_LOOP
          | _real_winsound.SND_NODEFAULT)

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


SRC = open(RIALTO, encoding="utf-8").read().replace("\r\n", "\n")
TREE = ast.parse(SRC)
TEMPLATE = ast.literal_eval(next(
    n.value for n in TREE.body
    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "georgia.ttf")


def make_wav(path, seconds=1.0, rate=22050, channels=2):
    with wave.open(path, "wb") as sound:
        sound.setnchannels(channels)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(b"\0" * int(seconds * rate) * channels * 2)
    return path


def make_coded_wav(path, tag):
    """A WAV whose format tag is not PCM: 2 is ADPCM, 3 IEEE float, 85 MP3 inside a WAV."""
    data = b"\0" * 400
    fmt = struct.pack("<HHIIHH", tag, 2, 44100, 44100 * 4, 4, 16)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE"
                + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data)
    return path


class Flag:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v

    def set(self, value):
        self._v = value


def module_code(names):
    out = []
    for n in TREE.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            out.append(ast.get_source_segment(SRC, n))
        elif isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in names:
            out.append(ast.get_source_segment(SRC, n))
    return "\n\n".join(out)


def method_src(name, cls="RialtoApp"):
    app_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == cls)
    for item in app_class.body:
        if isinstance(item, ast.FunctionDef) and item.name == name:
            return textwrap.dedent(ast.get_source_segment(SRC, item))
        if isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") == name:
            return textwrap.dedent(ast.get_source_segment(SRC, item))
    raise SystemExit("could not extract %s.%s" % (cls, name))


def rialto_host(methods, **attrs):
    ns = {"os": os, "re": __import__("re"), "json": json, "shutil": shutil, "wave": wave}
    exec(module_code({"menu_music_check", "format_megabytes", "format_length", "MENU_MUSIC_MAX_BYTES",
                      "MENU_MUSIC_LARGE_BYTES", "_CONTROL_CHARS", "VIDEO_EXTENSIONS", "MENU_DEFAULT_FONT_FACTS",
                      "strip_wti_mentions", "sanitize_text", "split_launch_args", "font_facts",
                      "menu_font_family_ok", "font_license_beside", "menu_font_check", "image_has_transparency",
                      "asset_path", "wav_format_tag", "WAVE_FORMAT_IEEE_FLOAT", "WAVE_FORMAT_EXTENSIBLE",
                      "font_license_problem", "MENU_FONT_LICENSE_MAX_BYTES", "MENU_FONT_LICENSE_TYPES"}), ns)
    sys.path.insert(0, HERE)
    import store_title_stub
    ns.update(store_title_stub.namespace(SRC))  # the menu's title names the game (4 Nov 2026)
    body = "\n\n".join(method_src(m) for m in methods) or "pass"
    exec("class Host:\n" + textwrap.indent(body, "    "), ns)
    host = ns["Host"]()
    host.said = []
    host.update_status = host.said.append
    for key, value in attrs.items():
        setattr(host, key, value)
    return host, ns


def settle():
    app = QtWidgets.QApplication.instance()
    for _ in range(6):
        app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def open_menu(root, title="MUSIC PROBE", music=True, own_art=False, theme=None, extra=None, show=True):
    """A staged install folder with its menu, opened off screen: (module globals, window)."""
    menu = os.path.join(root, "menu")
    os.makedirs(menu, exist_ok=True)
    script = os.path.join(menu, "menu_launcher.pyw")
    with open(script, "w", encoding="utf-8") as f:
        f.write(TEMPLATE)
    picture = QtGui.QImage(1280, 720, QtGui.QImage.Format_RGB32)
    picture.fill(QtGui.QColor(36, 52, 80))
    picture.save(os.path.join(menu, "background.jpg"))
    if theme is not None:
        shutil.copy2(FONT, os.path.join(menu, "menu_font.ttf"))
    os.makedirs(os.path.join(root, "Game"), exist_ok=True)
    open(os.path.join(root, "Game", "Game.exe"), "wb").close()
    open(os.path.join(root, "unins000.exe"), "wb").close()
    config = {"title": title, "game_exe": "Game/Game.exe", "remove_wti_branding": True,
              "copyright_text": "Published by Owlbright.", "language": "English"}
    if music:
        make_wav(os.path.join(menu, "menu_music.wav"))
        config["music"] = "menu_music.wav"
    if own_art:
        config["background_has_title"] = True
    if theme is not None:
        config["theme"] = theme
    config.update(extra or {})
    with open(os.path.join(menu, "menu_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)
    mod = runpy.run_path(script, run_name="menu_under_test")
    window = mod["GameMenu"]()
    if show:
        window.show()
        settle()
    return mod, window


def part_rialto(work):
    print("1. Rialto checks a WAV as the menu's Windows will play it (menu_music_check)")
    host, ns = rialto_host([])
    check = ns["menu_music_check"]
    pcm = make_wav(os.path.join(work, "theme.wav"), seconds=125.0, rate=8000, channels=1)
    seconds, size, problem = check(pcm)
    says("a PCM WAV is taken, its length read", problem == "" and round(seconds) == 125 and size > 0,
         (seconds, size, problem))
    says("its length reads as a person reads it", ns["format_length"](seconds) == "2:05", ns["format_length"](seconds))
    for tag, name in ((2, "ADPCM"), (85, "MP3 inside a WAV")):
        problem = check(make_coded_wav(os.path.join(work, "coded%d.wav" % tag), tag))[2]
        says("a compressed WAV (%s) is refused, and told to export as PCM WAV" % name,
             "compressed" in problem and "export the music as a PCM WAV" in problem, problem)
    # A float WAV is not compressed (readiness, 4 Nov): it is refused in words that say what it is.
    problem = check(make_coded_wav(os.path.join(work, "coded3.wav"), 3))[2]
    says("a float WAV is refused as a float WAV, and told to export as a 16-bit PCM WAV",
         "float WAV" in problem and "compressed" not in problem
         and "export the music as a 16-bit PCM WAV" in problem, problem)
    mp3 = os.path.join(work, "theme.mp3")
    shutil.copy2(pcm, mp3)
    says("a file that is not a .wav is refused", check(mp3)[2] == "it is not a .wav file", check(mp3)[2])
    says("a missing file is refused", check(os.path.join(work, "gone.wav"))[2] == "the file is not there")
    junk = os.path.join(work, "junk.wav")
    with open(junk, "wb") as f:
        f.write(b"not a riff file at all" * 4)
    says("a file that is not a WAV inside is refused plainly",
         check(junk)[2].startswith("it is not a WAV file Rialto can read"), check(junk)[2])
    silent = make_wav(os.path.join(work, "silent.wav"), seconds=0)
    says("a WAV with no sound in it is refused", check(silent)[2] == "it holds no sound", check(silent)[2])
    ns["MENU_MUSIC_MAX_BYTES"] = 1000
    says("a WAV larger than the menu holds in memory is refused, with the most it takes",
         "256 MB" not in check(pcm)[2] and "MB at most" in check(pcm)[2], check(pcm)[2])
    ns["MENU_MUSIC_MAX_BYTES"] = 256 * 1024 * 1024
    says("the menu and Rialto hold a WAV to the same most it may weigh",
         "MENU_MUSIC_MAX_BYTES = 256 * 1024 * 1024" in SRC and "MENU_MUSIC_MAX_BYTES = 256 * 1024 * 1024" in TEMPLATE)

    print("2. Step 4: the Menu Music row under Menu Background")
    create = method_src("create_widgets")
    tip = ('"A WAV file that loops under the menu. It stops while the game or Setup runs. Players can "\n'
           '                     "turn it off with the Sound button."')
    says("the row's label, its box and Browse", 'text="Menu Music:"' in create and "self.menu_music_var = tk.StringVar()" in create
         and "command=self.browse_menu_music" in create)
    says("the tooltip is his, word for word", tip in create)
    says("it sits right under Menu Background, before Game Logo",
         create.index('text="Menu Background:"') < create.index('text="Menu Music:"') < create.index('text="Game Logo (.png):"'))
    says("Browse teaches what to give it", 'ToolTip(music_browse, "Pick a WAV file from your files.")' in create)
    pair = method_src("pair_artwork_rows")
    says("the tighter page keeps it under Menu Background, across the row",
         "background, music, game_logo, company_logo, game_icon, disc_icon = fields" in pair
         and "music.grid(row=1, column=0, columnspan=2" in pair)
    says("Step 4's buttons are as tall as their boxes, so the sixth row fits every screen",
         "widget.configure(padding=(6, 3))" in create and "widget.pack_configure(pady=0)" in create)

    print("3. Browse: a .wav picked, checked, and said")
    browse, ns = rialto_host(["browse_menu_music", "warn_menu_music_large"], menu_music_var=Flag(""))
    popups, picked = [], []
    browse.show_centered_popup = lambda title, message, kind="info": popups.append(message)
    browse.art_start_dir = lambda: work
    browse.refresh_disc_meter = lambda: None

    def pick(path):
        picked.clear()
        popups.clear()
        browse.said.clear()
        ns["filedialog"] = types.SimpleNamespace(askopenfilename=lambda **kw: (picked.append(kw), path)[1])
        browse.browse_menu_music()

    pick(pcm)
    says("the file dialog asks for a .wav", picked and picked[0].get("filetypes") == [("WAV audio", "*.wav")],
         picked and picked[0].get("filetypes"))
    says("a PCM WAV fills the box", browse.menu_music_var.get() == pcm)
    says("and the log says its name, length and size",
         any("Selected menu music: theme.wav (2:05," in line for line in browse.said), browse.said)
    pick(os.path.join(work, "coded2.wav"))
    says("a compressed WAV leaves the box as it was and says to export a PCM WAV",
         browse.menu_music_var.get() == pcm and popups and "export the music as a PCM WAV" in popups[0], popups)
    pick("")
    says("Cancel changes nothing", browse.menu_music_var.get() == pcm and not popups and not browse.said)
    ns["MENU_MUSIC_LARGE_BYTES"] = 1000
    pick(pcm)
    says("a very large WAV is said plainly, with what it adds to the disc",
         any("The disc carries it twice" in line and "adds up to" in line for line in browse.said), browse.said)
    ns["MENU_MUSIC_LARGE_BYTES"] = 50 * 1024 * 1024

    print("4. saved and loaded: profile, Load Profile, the startup profile, last session, Restore page")
    says("a profile keeps it as MenuMusic", 'profile_data["MenuMusic"] = self.menu_music_var.get()'
         in method_src("current_profile_data"))
    # Load Profile and the start put a profile on the form through one list (readiness, 4 Nov).
    says("Load Profile reads it back", 'self.menu_music_var.set(profile_data.get("MenuMusic", "") or "")'
         in method_src("put_profile_on_form") and "self.put_profile_on_form(profile_data)" in method_src("apply_profile_file"))
    says("the startup profile reads it back too",
         "self.put_profile_on_form(profile_data, at_start=True)" in method_src("load_last_used_profile"))
    says("a profile's missing music is said on load, and the disc is built without it",
         '("Menu Music", self.menu_music_var.get().strip()),' in method_src("apply_profile_file"))
    says("a moved game folder finds it again, as it finds the art",
         ("menu_music_var", "Menu Music") in ast.literal_eval(method_src("REBASEABLE_FILES").split("=", 1)[1].strip()))
    says("the last session keeps it", 'session_data["MenuMusic"] = self.menu_music_var.get()' in method_src("save_last_session")
         and 'elif key == "MenuMusic":' in method_src("load_last_session"))
    says("Restore page clears it", "self.bg_path_var, self.menu_music_var," in SRC)

    print("5. the build: staged as menu/menu_music.wav, named in menu_config.json, counted by the meter")
    stage, ns = rialto_host(["stage_menu_artwork", "warn_menu_music_large", "menu_font_choice", "menu_theme_path",
                             "build_menu_config", "menu_theme_config", "menu_theme_font", "menu_music_source",
                             "menu_staging_bytes", "menu_inside_bytes", "RUNTIME_ALLOWANCE"],
                            menu_music_var=Flag(pcm), bg_path_var=Flag(""), logo_path_var=Flag(""),
                            current_game_path="", remove_wti_branding=Flag(True), menu_theme={},
                            entries={"Title": Flag("Music Disc")}, company_logo_var=Flag(""),
                            publisher_text_var=Flag(""), steam_button_var=Flag(False), mod_launcher_var=Flag(False),
                            compat_mode_var=Flag(False), compat_args_var=Flag(""), compat_hint_var=Flag(""),
                            bg_has_title_var=Flag(False))
    stage.validated_game_executables = lambda: []
    stage.detect_primary_game_exe = lambda root: "game.exe"
    ns["prebuilt_menu_exe"] = lambda: None
    root = os.path.join(work, "build")
    menu = os.path.join(root, "menu")
    os.makedirs(menu)
    stage.stage_menu_artwork(menu)
    staged = os.path.join(menu, "menu_music.wav")
    says("the WAV is staged as menu_music.wav, as it was", os.path.isfile(staged)
         and open(staged, "rb").read() == open(pcm, "rb").read())
    says("and menu_config.json names it", stage.build_menu_config(root).get("music") == "menu_music.wav")
    with_music = stage.menu_staging_bytes()
    stage.menu_music_var = Flag("")
    stage.stage_menu_artwork(menu)
    says("with none picked, an earlier build's copy is cleared", not os.path.exists(staged))
    says("and the config has no music key, as every disc before 1.5.2", "music" not in stage.build_menu_config(root))
    says("the meter counts the WAV in the menu folder", with_music - stage.menu_staging_bytes() == os.path.getsize(pcm),
         (with_music, stage.menu_staging_bytes()))
    meter_by_what_the_build_makes(work, pcm)
    stage.menu_music_var = Flag(os.path.join(work, "coded3.wav"))
    stage.said.clear()
    stage.stage_menu_artwork(menu)
    says("a WAV that fails the check is left out, the build says why, and the menu is quiet",
         not os.path.exists(staged) and any("float WAV" in line for line in stage.said)
         and "music" not in stage.build_menu_config(root), stage.said)
    says("nor does the meter count it", stage.menu_music_source() == "")
    stage.menu_music_var = Flag(os.path.join(work, "moved.wav"))
    stage.said.clear()
    stage.stage_menu_artwork(menu)
    says("a WAV that is no longer there is said, and the build goes on without it",
         any("Menu music not found, building without it" in line for line in stage.said), stage.said)
    says("the preview stages it the same way (it stages its menu with stage_menu_artwork)",
         "self.stage_menu_artwork(menu_dir)" in method_src("preview_disc_menu"))

    print("6. the Help Guide and menu.spec")
    guide = open(os.path.join(REPO, "docs", "rialto-guide.html"), encoding="utf-8").read()
    says("the Help Guide has a Menu Music row", "<tr><td>Menu Music</td><td>Under Menu Background. A WAV file that "
         "loops under the menu." in guide)
    spec = open(os.path.join(REPO, "packaging", "menu.spec"), encoding="utf-8").read()
    says("menu.spec names winsound, and still leaves QtMultimedia out",
         "'winsound'," in spec and "'PyQt5.QtMultimedia'" in spec.split("excludes=")[1].split("]")[0])
    says("the menu never imports Qt's multimedia", "QtMultimedia" not in TEMPLATE.replace(
        "nothing of Qt's multimedia", ""))


def meter_by_what_the_build_makes(work, wav):
    """The meter's own disc_weights against the copies of the WAV and the font the build really makes.

    menu/ rides on the disc root and inside the installer, so the staged WAV is on the disc twice more than
    wherever its source sits: once more again when that source is in the game folder or the bonus folder,
    which the installer carries too. Fastest install already counts the whole menu twice.
    """
    meter, ns = rialto_host(["disc_weights", "menu_staging_bytes", "menu_inside_bytes", "menu_music_source",
                             "menu_font_choice", "menu_theme_path", "RUNTIME_ALLOWANCE", "RUNTIME_STORED",
                             "DISC1_FILES_ALLOWANCE"],
                            bg_path_var=Flag(""), steam_button_var=Flag(False), menu_theme={}, current_game_path="")
    ns["prebuilt_menu_exe"] = lambda: None
    size = os.path.getsize(wav)
    game = os.path.join(work, "meter", "Game")
    bonus = os.path.join(work, "meter", "Bonus")
    for folder in (game, bonus):
        os.makedirs(folder)
    with open(os.path.join(game, "Game.exe"), "wb") as f:
        f.write(b"\0" * 5000)
    with open(os.path.join(bonus, "artbook.pdf"), "wb") as f:
        f.write(b"\0" * 7000)
    in_game = os.path.join(game, "audio", "theme.wav")
    os.makedirs(os.path.dirname(in_game))
    shutil.copy2(wav, in_game)
    in_bonus = os.path.join(bonus, "theme.wav")
    shutil.copy2(wav, in_bonus)

    def weigh(music, with_bonus=False, stored=False):
        meter.menu_music_var = Flag(music)
        meter.current_game_path = game
        extras = ["", "", "", "", "", "", "", bonus if with_bonus else ""]
        duplicated = [bonus] if with_bonus else []
        return meter.disc_weights(game, extras, duplicated, meter.menu_staging_bytes(), [], stored,
                                  meter.menu_inside_bytes())

    def added(music, **kw):
        return weigh(music, **kw)[0] - weigh("", **kw)[0]

    says("the meter takes the installer's copy from menu_inside_bytes, not from the extras",
         "menu_music_source()" not in method_src("refresh_disc_meter")
         and "menu_inside = self.menu_inside_bytes()" in method_src("refresh_disc_meter"))
    got = added(wav)
    says("a WAV beside the game, Balanced: counted twice, menu/ on the disc and inside the installer",
         got == 2 * size, (got, size))
    got = weigh(in_game)[0] - weigh("")[0]
    says("a WAV picked from the game folder: twice more than the game's own copy, three in all",
         got == 2 * size, (got, size))
    got = added(in_bonus, with_bonus=True)
    says("a soundtrack WAV from the bonus folder picked as the Menu Music: twice more than the bonus copies",
         got == 2 * size, (got, size))
    got = added(wav, stored=True)
    says("Fastest install: twice, as the menu is counted twice there, never three times",
         got == 2 * size, (got, size))
    _fill, disc1 = weigh(wav)
    says("Disc 1 carries the menu/ copy on the disc root", disc1 - weigh("")[1] == size, (disc1, size))

    font = os.path.join(work, "meter", "fonts", "Menu.ttf")
    os.makedirs(os.path.dirname(font))
    shutil.copy2(FONT, font)
    licence = os.path.join(os.path.dirname(font), "OFL.txt")
    with open(licence, "w", encoding="utf-8") as f:
        f.write("SIL Open Font License, Version 1.1\n" * 40)
    both = os.path.getsize(font) + os.path.getsize(licence)
    plain_fill, plain_disc1 = weigh("")
    meter.menu_theme = {"Font": font}
    themed_fill, themed_disc1 = weigh("")
    says("the menu's font and its license are counted in menu/ on the disc root and inside the installer",
         themed_fill - plain_fill == 2 * both, (themed_fill - plain_fill, both))
    says("and on Disc 1", themed_disc1 - plain_disc1 == both, (themed_disc1 - plain_disc1, both))
    stored_added = weigh("", stored=True)[0]
    meter.menu_theme = {}
    stored_added -= weigh("", stored=True)[0]
    says("Fastest install: the font twice too", stored_added == 2 * both, (stored_added, both))
    meter.menu_theme = {"Font": os.path.join(work, "meter", "fonts", "Gone.ttf")}
    says("a font the build leaves out weighs nothing", weigh("")[0] == plain_fill)
    says("Save in Menu Font and Colors weighs the disc again", "self.refresh_disc_meter()"
         in method_src("configure_menu_theme"))
    meter.menu_theme = {}


def popups_and_the_front(work):
    """Windows' alert sound for a message box ends the music's loop; a menu that opens behind stays quiet."""
    app = QtWidgets.QApplication.instance()
    print("16. a message box while the music plays leaves it playing")
    PLAYED.clear()
    mod, window = open_menu(os.path.join(work, "popups"), title="MUSIC POPUPS")
    boxes = []
    real_box = window._message_box

    def capture(*args):
        box = real_box(*args)
        box.exec_ = lambda: 0  # nothing waits for a click off screen
        boxes.append(box)
        return box
    window._message_box = capture
    says("the music is playing", window.music_playing and PLAYED == [(window.music_path, LOOPED)], PLAYED)
    window._menu_message("Steam", "Added to your Steam library.")
    box = boxes[-1]
    # Qt's Windows plugin plays SystemAsterisk in the menu's process for a box whose icon() is Information,
    # which ends a SND_LOOP PlaySound (seen on the hidden desktop); a box whose icon is a picture plays none.
    says("an information box: its icon a picture, so Windows plays no alert sound over the music",
         box.icon() == QtWidgets.QMessageBox.NoIcon and not box.iconPixmap().isNull(), box.icon())
    window._menu_confirm("Uninstall", "Remove the game?")
    says("a question box too", boxes[-1].icon() == QtWidgets.QMessageBox.NoIcon
         and not boxes[-1].iconPixmap().isNull(), boxes[-1].icon())
    says("and the music was never stopped or started again", PLAYED == [(window.music_path, LOOPED)], PLAYED)
    window.sound_btn.click()
    window._menu_message("Steam", "Added to your Steam library.")
    says("with Sound: Off, the box keeps its own icon and its sound, as on every disc before",
         boxes[-1].icon() == QtWidgets.QMessageBox.Information, boxes[-1].icon())
    window.sound_btn.click()
    window.close()
    _m, quiet = open_menu(os.path.join(work, "popups-quiet"), title="MUSIC POPUPS QUIET", music=False)
    shown = []
    real_quiet = quiet._message_box

    def capture_quiet(*args):
        box = real_quiet(*args)
        box.exec_ = lambda: 0
        shown.append(box)
        return box
    quiet._message_box = capture_quiet
    quiet._menu_message("Steam", "Added to your Steam library.")
    says("a disc without music: the box as it was", shown[-1].icon() == QtWidgets.QMessageBox.Information)
    quiet.close()

    print("17. a menu that opens behind another program's window stays quiet until it is in front")
    PLAYED.clear()
    # The window the player clicked into keeps the front: Qt's state stays Inactive and no change is signalled.
    app.applicationState = lambda: QtCore.Qt.ApplicationInactive
    try:
        mod, behind = open_menu(os.path.join(work, "behind"), title="MUSIC BEHIND", show=False)
        app.blockSignals(True)
        behind.show()
        settle()
    finally:
        app.blockSignals(False)
        del app.applicationState
    says("shown, but not in front: nothing plays", behind.isVisible() and behind.music_away and PLAYED == [],
         (behind.music_away, PLAYED))
    app.applicationStateChanged.emit(QtCore.Qt.ApplicationActive)
    says("the player clicks into it: the music starts", PLAYED == [(behind.music_path, LOOPED)], PLAYED)
    behind.close()
    PLAYED.clear()
    mod, front = open_menu(os.path.join(work, "front"), title="MUSIC FRONT")
    says("a menu that opens in front plays at once, as before", PLAYED == [(front.music_path, LOOPED)], PLAYED)
    front.close()


def part_menu(work):
    app = QtWidgets.QApplication.instance()
    print("7. the menu holds menu_config.json's \"music\" to the menu's own folder (menu_music_path)")
    mod, window = open_menu(os.path.join(work, "paths"), show=False)
    menu = os.path.join(work, "paths", "menu")
    path_of = mod["menu_music_path"]
    make_wav(os.path.join(work, "paths", "outside.wav"))
    os.makedirs(os.path.join(menu, "sub"))
    make_wav(os.path.join(menu, "sub", "inner.wav"))
    shutil.copy2(os.path.join(menu, "menu_music.wav"), os.path.join(menu, "menu_music.mp3"))
    open(os.path.join(menu, "empty.wav"), "wb").close()
    says("the staged WAV is taken", path_of({"music": "menu_music.wav"}) == os.path.join(menu, "menu_music.wav"))
    for value, why in (("../outside.wav", "a parent folder"), ("sub/inner.wav", "a folder in the name"),
                       ("sub\\inner.wav", "a folder, written the Windows way"),
                       (os.path.join(work, "paths", "outside.wav"), "a whole path"),
                       ("menu_music.mp3", "not a .wav"), ("evil:menu_music.wav", "a stream in the name"),
                       ("missing.wav", "a file that is not there"), ("empty.wav", "an empty file"),
                       ("", "nothing"), (5, "a number"), (["menu_music.wav"], "a list"), (None, "null"),
                       ("menu_music.wav\x00", "a NUL"), ("x" * 200 + ".wav", "a name too long")):
        says("refused: %s" % why, path_of({"music": value}) == "", path_of({"music": value}))
    path_of.__globals__["MENU_MUSIC_MAX_BYTES"] = 100
    says("refused: larger than PlaySound may hold", path_of({"music": "menu_music.wav"}) == "")
    path_of.__globals__["MENU_MUSIC_MAX_BYTES"] = 256 * 1024 * 1024
    link = os.path.join(menu, "linked.wav")
    try:
        os.symlink(os.path.join(work, "paths", "outside.wav"), link)
    except (OSError, NotImplementedError):
        link = None
    if link:
        says("refused: a link out of the menu folder", path_of({"music": "linked.wav"}) == "")
    else:
        print("  [--  ] a link out of the menu folder: this PC lets no test make one (needs Developer Mode)")
    window.deleteLater()
    settle()

    print("8. a disc with music: it loops from the start, and the Sound button sits in the corner")
    PLAYED.clear()
    EVENTS.clear()
    mod, window = open_menu(os.path.join(work, "plain"))
    wav = os.path.join(work, "plain", "menu", "menu_music.wav")
    says("the music starts once the menu shows, looped, from the file, by Windows itself",
         PLAYED == [(wav, LOOPED)], PLAYED)
    sound = window.sound_btn
    says("the button says Sound: On", sound is not None and sound.text() == "Sound: On", sound and sound.text())
    corner = sound.geometry()
    sf = window.scale_factor
    says("in the top right corner, short of the close button and clear of the menu column",
         corner.right() < int(1225 * sf) and corner.top() >= int(15 * sf) and corner.bottom() <= int(55 * sf)
         and corner.left() > int(480 * sf), corner)
    says("its words fit it", sound.sizeHint().width() <= corner.width(), (sound.sizeHint(), corner))
    says("it is the last stop for the keyboard and a controller", window.nav_buttons()[-1] is sound)
    PLAYED.clear()
    sound.click()
    prefs = json.load(open(mod["player_prefs_path"]("MUSIC PROBE"), encoding="utf-8"))
    says("pressed: Sound: Off, the music stops, and the choice is kept in player.json",
         sound.text() == "Sound: Off" and PLAYED == [(None, 0)] and prefs.get("sound") is False, (sound.text(), PLAYED, prefs))
    says("player.json is the one beside the stars and the language, under this test's LOCALAPPDATA",
         mod["player_prefs_path"]("MUSIC PROBE").startswith(APPDATA))
    window.close()
    PLAYED.clear()
    mod, again = open_menu(os.path.join(work, "plain"))
    says("opened again: Sound: Off, and nothing plays", again.sound_btn.text() == "Sound: Off" and PLAYED == [], PLAYED)
    again.sound_btn.click()
    says("pressed again: Sound: On, the music plays, and that is kept",
         again.sound_btn.text() == "Sound: On" and PLAYED == [(wav, LOOPED)]
         and json.load(open(mod["player_prefs_path"]("MUSIC PROBE"), encoding="utf-8")).get("sound") is True, PLAYED)

    print("9. it stops whenever another window is in front (the bonus folder, the game), and comes back")
    PLAYED.clear()
    app.applicationStateChanged.emit(QtCore.Qt.ApplicationInactive)
    says("another program in front: the music stops", PLAYED == [(None, 0)], PLAYED)
    app.applicationStateChanged.emit(QtCore.Qt.ApplicationInactive)
    says("and is not stopped twice", PLAYED == [(None, 0)], PLAYED)
    app.applicationStateChanged.emit(QtCore.Qt.ApplicationActive)
    says("the player back at the menu: it plays again", PLAYED[-1] == (wav, LOOPED), PLAYED)
    says("BONUS CONTENT opens a folder with Windows, and the menu follows Windows' word for what is in front",
         "os.startfile(bonus_dir)" in TEMPLATE and "app.applicationStateChanged.connect(self.music_follow_state)" in TEMPLATE)

    print("10. every program the menu starts: the music stops first, and the menu then closes")
    lines = TEMPLATE.split("\n")
    popens = [i for i, line in enumerate(lines) if "subprocess.Popen(" in line and not line.lstrip().startswith("#")]
    says("five places start a program: a game of several, Setup, the game, a mod tool, the uninstaller",
         len(popens) == 5, len(popens))
    says("each one stops the music on the line before it",
         all(lines[i - 1].strip() == "self.stop_music_for_good()" for i in popens),
         [lines[i - 1].strip() for i in popens])
    import subprocess
    real_popen, real_instance = subprocess.Popen, QtWidgets.QApplication.instance
    exe = os.path.join(work, "plain", "Game", "Game.exe")
    quits = []

    def fake_popen(argv, **kwargs):
        EVENTS.append("popen")

    subprocess.Popen = fake_popen
    QtWidgets.QApplication.instance = staticmethod(lambda: types.SimpleNamespace(quit=lambda: quits.append(1)))
    try:
        again.games = []
        again.find_game_exe = lambda: (exe, [])
        again._configured_exe = lambda rel: exe
        again._resolve_mod_exe = lambda: exe
        again.disc_installer = lambda: exe
        again._menu_confirm = lambda *a: True
        for name, press in (("PLAY", again.launch_game), ("a game of several", lambda: again.launch_configured_exe("Game/Game.exe")),
                            ("INSTALL (Setup)", again.run_disc_installer), ("MODS", again.launch_mods),
                            ("UNINSTALL", again.uninstall_game)):
            again.music_done = False
            QtWidgets.QApplication.instance = real_instance
            again.refresh_music()
            QtWidgets.QApplication.instance = staticmethod(lambda: types.SimpleNamespace(quit=lambda: quits.append(1)))
            EVENTS.clear()
            press()
            says("%s: the music stops, then the program starts" % name, EVENTS == ["stop", "popen"], EVENTS)
    finally:
        subprocess.Popen = real_popen
        QtWidgets.QApplication.instance = real_instance
    says("and the menu closes after each, as it always did", len(quits) == 5, quits)
    again.music_done = False
    again.refresh_music()
    PLAYED.clear()
    again.close()
    says("EXIT (or the close button): the music stops", PLAYED == [(None, 0)], PLAYED)
    app.applicationStateChanged.emit(QtCore.Qt.ApplicationActive)
    says("and nothing starts it again once the menu has closed", PLAYED == [(None, 0)], PLAYED)
    says("the menu stops it as Qt quits, too", "app.aboutToQuit.connect(self.stop_music_for_good)" in TEMPLATE)

    print("11. the keyboard and a controller reach the Sound button like every other")
    mod, keys = open_menu(os.path.join(work, "keys"), title="MUSIC KEYS")
    keys.activateWindow()
    keys.exit_btn.setFocus()
    settle()
    QTest.keyClick(keys.exit_btn, QtCore.Qt.Key_Down)
    settle()
    says("Down from EXIT reaches it", QtWidgets.QApplication.focusWidget() is keys.sound_btn,
         getattr(QtWidgets.QApplication.focusWidget(), "text", lambda: None)())
    QTest.keyClick(keys.sound_btn, QtCore.Qt.Key_Return)
    settle()
    says("Enter presses it", keys.sound_btn.text() == "Sound: Off", keys.sound_btn.text())
    keys.pad_act(mod["PAD_A"])
    settle()
    says("A on a controller presses it", keys.sound_btn.text() == "Sound: On", keys.sound_btn.text())
    keys.pad_act(mod["PAD_DOWN"])
    settle()
    says("Down goes on round to the top", QtWidgets.QApplication.focusWidget() is keys.play_btn)
    keys.close()

    print("12. the Sound button in all 34 languages, in the menu's own look")
    trans = keys.translations
    says("34 languages, each with both words", len(trans) == 34
         and all(t.get("sound_on") and t.get("sound_off") and t["sound_on"] != t["sound_off"] for t in trans.values()))
    theme = {"font": "menu_font.ttf", "text": "#f1e4cf", "accent": "#e8c25b", "quiet": "#dccfb8", "scale": 1.5}
    mod, themed = open_menu(os.path.join(work, "themed"), title="MUSIC THEMED", theme=theme)
    sheet = themed.sound_btn.styleSheet()
    says("a themed disc: the Sound button in its font, its quiet color and its accent",
         'font-family: "Georgia"' in sheet and "#dccfb8" in sheet and "#e8c25b" in sheet, sheet[:200])
    cut = []
    for lang in sorted(trans):
        for pressed in (False, True):
            themed.change_language(lang)
            settle()
            btn = themed.sound_btn
            room = btn.geometry()
            if (btn.sizeHint().width() > room.width() or room.left() <= int(480 * themed.scale_factor)
                    or room.right() >= int(1225 * themed.scale_factor)):
                cut.append((lang, btn.text(), btn.sizeHint().width(), room.width()))
            btn.click()
            settle()
    says("every language's words fit the corner at the largest Size, both On and Off", not cut, cut)
    themed.change_language("German")
    says("and it follows the language", themed.sound_btn.text() in ("Ton: An", "Ton: Aus"), themed.sound_btn.text())
    themed.close()
    mod, own = open_menu(os.path.join(work, "own"), title="MUSIC OWN ART", own_art=True)
    says("on art with its own title, its words get the soft dark edge like the column's",
         id(own.sound_btn) in own.letter_edges.labels)
    own.close()

    print("13. a preview plays the music, and keeps nothing the author presses")
    os.environ["RIALTO_PREVIEW"] = "1"
    try:
        PLAYED.clear()
        mod, preview = open_menu(os.path.join(work, "preview"), title="MUSIC PREVIEW")
        preview_wav = os.path.join(work, "preview", "menu", "menu_music.wav")
        says("the preview plays it, so the author hears the disc", PLAYED == [(preview_wav, LOOPED)], PLAYED)
        preview.sound_btn.click()
        says("Sound: Off in a preview is not written to this PC",
             preview.sound_btn.text() == "Sound: Off"
             and not os.path.exists(mod["player_prefs_path"]("MUSIC PREVIEW")))
        preview.close()
    finally:
        os.environ.pop("RIALTO_PREVIEW", None)

    print("14. a disc without music is as it was: no button, nothing played, player.json as before")
    PLAYED.clear()
    mod, quiet = open_menu(os.path.join(work, "quiet"), title="MUSIC QUIET", music=False)
    says("no Sound button", quiet.sound_btn is None and not [b for b in quiet.findChildren(QtWidgets.QPushButton)
                                                             if b.text().startswith("Sound")])
    says("nothing played", PLAYED == [], PLAYED)
    says("the keyboard's stops end at EXIT, as before", quiet.nav_buttons()[-1] is quiet.exit_btn)
    quiet.change_language("French")
    quiet.change_language("English")
    saved = json.load(open(mod["player_prefs_path"]("MUSIC QUIET"), encoding="utf-8"))
    says("a language change writes player.json with no sound key, as every disc before 1.5.2",
         sorted(saved) == ["lang", "sort", "stars"], saved)
    with open(mod["player_prefs_path"]("MUSIC QUIET"), "w", encoding="utf-8") as f:
        json.dump({"stars": [], "sort": "disc", "lang": "", "sound": "no"}, f)
    says("a rewritten player.json's sound that is not true or false is not read",
         "sound" not in mod["read_player_prefs"]("MUSIC QUIET"))
    quiet.close()

    print("15. the picture: a disc with music differs from one without only where the Sound button is")
    for label, kwargs in (("plain", {}), ("themed", {"theme": theme}), ("hide the title", {"own_art": True})):
        _m, without = open_menu(os.path.join(work, "look-a-" + label), title="MUSIC LOOK", music=False, **kwargs)
        _m, with_music = open_menu(os.path.join(work, "look-b-" + label), title="MUSIC LOOK", **kwargs)
        shots = []
        for window in (without, with_music):  # each as the window in front, PLAY chosen, as a player first sees it
            window.activateWindow()
            window.play_btn.setFocus()
            settle()
            shots.append(window.grab().toImage())
        a, b = shots
        spot = with_music.sound_btn.geometry().adjusted(-20, -20, 20, 20)
        stray = []
        for y in range(0, a.height(), 2):
            for x in range(0, a.width(), 2):
                if not spot.contains(x, y) and a.pixel(x, y) != b.pixel(x, y):
                    stray.append((x, y))
        where = (min(p[0] for p in stray), min(p[1] for p in stray), max(p[0] for p in stray),
                 max(p[1] for p in stray)) if stray else ()
        says("%s disc: the same picture outside the button" % label, a.size() == b.size() and not stray,
             (len(stray), where))
        drawn = sum(1 for y in range(spot.top(), spot.bottom()) for x in range(spot.left(), spot.right())
                    if a.pixel(x, y) != b.pixel(x, y))
        says("%s disc: and the button is drawn there" % label, drawn > 100, drawn)
        without.close()
        with_music.close()


def main():
    app = QtWidgets.QApplication(sys.argv)  # noqa: F841 (kept alive for every window below)
    app.setFont(QtGui.QFont("Segoe UI", 9))  # what Windows gives a Qt program
    work = tempfile.mkdtemp(prefix="rialto_menu_music_")
    try:
        part_rialto(work)
        part_menu(work)
        popups_and_the_front(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(APPDATA, ignore_errors=True)
    says("winsound was the fake throughout: nothing was played aloud", sys.modules["winsound"] is fake_winsound)
    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll Menu Music checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
