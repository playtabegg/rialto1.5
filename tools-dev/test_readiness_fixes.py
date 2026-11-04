"""The 1.5.2 readiness review and e2e run (4 Nov 2026): each finding fixed at the root, and kept fixed.

One section per finding. Every check here failed on build/1.5.2-own-art at 8ed1439
(run this file with that Rialto.pyw as its argument to see it), and passes now.

1. A title typed without its store format still finds the 1.5.1 install made under it.
2. A font's license is a short text file, and the build log names where it came from.
3. No time limit reaches menu.exe signing, and compiling the disc menu.
4. A float WAV is called a float WAV, not a compressed one.
5. The Help Guide says truly what Menu Music adds to each install type.
6. Saving Font and Colors names only what was set.
7. The Library Hero's words say Steam crops any edge, not only the sides.
8. One name for the dialog: Font and Colors.
9. The disc meter counts a full-size set as the build packs it.
10. A profile saved with a byte order mark loads.
11. An upgrade keeps the player's stars and menu language from a disc named with the format.
12. The start puts back every setting the last profile keeps, but this PC's own ticks and no advice.

(ADD TO STEAM's backup, written only when a press changes the list, is in test_steam_shortcuts.py.)

Source-extracted and run on stubs, as the other harnesses are: no window, no disc tool, no signing.

Usage: python tools-dev/test_readiness_fixes.py [path-to-Rialto.pyw]
"""
import ast
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import textwrap
import wave

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
import test_mini_discs as tmd  # noqa: E402
import test_store_format as tsf  # noqa: E402

RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
GUIDE = os.path.join(REPO, "docs", "rialto-guide.html")
failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def module(src, names):
    """The module-level functions and constants `names` lean on, exec'd: a namespace, or None if one is missing."""
    defined = {getattr(n, "name", None) for n in ast.parse(src).body} | {
        t.id for n in ast.parse(src).body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    if not set(names) <= defined:
        return None
    ns = {"os": os, "re": re, "json": json, "struct": struct, "wave": wave, "sys": sys}
    exec(tsf.module_closure(src, names), ns)
    return ns


def method(src, name, cls="RialtoApp"):
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(src, item))
    return ""


def visible_strings(src):
    """Every string literal in Rialto.pyw that is not a docstring: the words Rialto can show or log."""
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def guide_row(guide, name):
    match = re.search(r"<tr><td>%s</td><td>(.*?)</td></tr>" % re.escape(name), guide, re.S)
    return match.group(1) if match else ""


def wav(path, tag, extensible=False):
    """A one-second mono WAV whose fmt chunk carries `tag` (as the sub-format when `extensible`)."""
    bits = 32 if tag == 3 else 16
    data = b"\x00" * (8000 * bits // 8)
    if extensible:
        fmt = struct.pack("<HHIIHH", 0xFFFE, 1, 8000, 8000 * bits // 8, bits // 8, bits)
        fmt += struct.pack("<HHI", 22, bits, 4) + struct.pack("<H", tag) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    else:
        fmt = struct.pack("<HHIIHH", tag, 1, 8000, 8000 * bits // 8, bits // 8, bits)
        if tag != 1:
            fmt += b"\x00\x00"
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def main():
    src = open(RIALTO, encoding="utf-8").read()
    guide = open(GUIDE, encoding="utf-8").read()
    strings = visible_strings(src)
    work = tempfile.mkdtemp(prefix="readiness_")
    try:
        print("1. a Game Title typed as the game's name finds the disc from before under the store's format")
        ns = module(src, ["earlier_installs"])
        earlier = [identity for identity, _shortcut in ns["earlier_installs"]("Moth Lamp", "Moth Lamp")]
        says("earlier_installs('Moth Lamp', 'Moth Lamp') looks for Moth Lamp (PC CD) and every other format",
             earlier == ["Moth Lamp (PC CD)", "Moth Lamp (PC DVD)", "Moth Lamp (PC CD+Soundtrack CD)",
                         "Moth Lamp (PC DVD+Soundtrack CD)"], earlier)
        says("and never for this disc's own identity", "Moth Lamp" not in earlier)
        says("the build writes AppId={code:InstallIdentity} whenever an earlier disc could be there",
             "own_identity = not earlier" in method(src, "generate_enhanced_installer_script"))
        print()

        print("2. a font's license: a short text file, named in the build log")
        ns = module(src, ["menu_font_check"])
        fonts = os.path.join(work, "fonts")
        os.makedirs(fonts)
        arial = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")
        font = os.path.join(fonts, "Arial.ttf")
        shutil.copyfile(arial, font)
        check = ns["menu_font_check"]
        config = os.path.join(work, "private-config.json")
        with open(config, "w", encoding="utf-8") as f:
            f.write('{"token": "not a license"}')
        _f, _l, _fam, problem = check(font, config)
        says("a license that is not a .txt or .md file is refused", problem.startswith(
            "its license, private-config.json, is not a text file"), problem)
        big = os.path.join(work, "LICENSE.txt")
        with open(big, "wb") as f:
            f.write(b"x" * (1024 * 1024 + 1))
        _f, _l, _fam, problem = check(font, big)
        says("a license past 1 MB is refused", "1 MB at most" in problem, problem)
        binary = os.path.join(work, "OFL")
        with open(binary, "wb") as f:
            f.write(b"MZ\x90\x00\x03\x00\x00\x00")
        _f, _l, _fam, problem = check(font, binary)
        says("a license that is not text is refused", "is not text" in problem, problem)
        ofl = os.path.join(fonts, "OFL.txt")
        with open(ofl, "w", encoding="utf-8") as f:
            f.write("SIL OPEN FONT LICENSE Version 1.1\n")
        got = check(font, "")
        says("the OFL.txt beside the font is taken", got[:2] == (font, ofl) and not got[3], got)
        utf16 = os.path.join(work, "license-utf16.txt")
        with open(utf16, "w", encoding="utf-16") as f:
            f.write("SIL OPEN FONT LICENSE Version 1.1\n")
        says("and a license saved as UTF-16 is text", not check(font, utf16)[3], check(font, utf16)[3])
        stage = method(src, "stage_menu_artwork")
        says("the build log names the font and the license it copied",
             'self.update_status(f"✅ Copied the menu\'s font, {font}, and its license, {licence}")' in stage)
        print()

        print("3. No time limit reaches menu.exe signing and the disc menu's compile")
        import rialto.trusted_signing as ts
        menu_dir = os.path.join(work, "menu")
        os.makedirs(menu_dir)
        with open(os.path.join(menu_dir, "menu.exe"), "wb") as f:
            f.write(b"MZ")
        saved = ts.is_configured, ts.sign_file
        try:
            ts.is_configured = lambda: True
            ts.sign_file = lambda path, status=print, timeout=300, run=None, again="build": (True, timeout)
            try:
                answer = ts.sign_staged_menu(menu_dir, lambda message: None, timeout=None)
            except TypeError as e:
                answer = ("TypeError", str(e))
            says("sign_staged_menu hands sign_file the time limit it is given (None: no limit)",
                 answer == (True, None), answer)
            says("and 5 minutes when it is given none", ts.sign_staged_menu(menu_dir, lambda m: None)[1] == 300)
        finally:
            ts.is_configured, ts.sign_file = saved
        signing = method(src, "sign_staged_menu_exe")
        says("Rialto passes it the No time limit box's answer",
             "trusted_signing.sign_staged_menu(\n                    menu_dir, log, timeout=self.tool_time_limit(300))" in signing,
             signing[-600:])
        says("compiling the disc menu takes the box's answer too",
             "self.run_tool_watched(build_cmd, menu_dir, self.tool_time_limit(300), \"Compiling the disc menu\")"
             in method(src, "compile_pyqt5_menu"))
        print()

        print("4. Menu Music: a float WAV is not called compressed")
        ns = module(src, ["menu_music_check"])
        music = ns["menu_music_check"]
        _s, _z, problem = music(wav(os.path.join(work, "float.wav"), 3))
        says("a 32-bit float WAV is called a float WAV", "float WAV" in problem and "compressed" not in problem,
             problem)
        _s, _z, problem = music(wav(os.path.join(work, "float-ext.wav"), 3, extensible=True))
        says("and so is one in the extensible format", "float WAV" in problem and "compressed" not in problem,
             problem)
        _s, _z, problem = music(wav(os.path.join(work, "adpcm.wav"), 2))
        says("an ADPCM WAV is still called compressed", "compressed WAV" in problem, problem)
        seconds, _z, problem = music(wav(os.path.join(work, "pcm.wav"), 1))
        says("and a 16-bit PCM WAV is taken", not problem and round(seconds) == 1, problem)
        print()

        print("5. the Help Guide on what Menu Music adds")
        row = guide_row(guide, "Menu Music")
        says("it no longer says the WAV is never compressed, and never says squeezed",
             "A WAV is not squeezed" not in row and "squeez" not in row, row)
        says("it says the installer compresses its copy except on Fastest install",
             "The installer compresses its copy on Balanced and Smallest disc, and keeps it as it is on Fastest "
             "install" in row, row)
        says("and that Rialto names a float WAV", "float" in row, row)
        print()

        print("6. Save in Font and Colors names only what was set")
        ns = module(src, ["menu_theme_saved_line"])
        line = ns["menu_theme_saved_line"] if ns else (lambda theme: "")
        got = line({"Top": 300})
        says("Top line only: the top line is set", got == "🎨 The menu's top line is set. Save Profile keeps it "
                                                          "with this game.", got)
        got = line({"Font": "a.ttf", "Text": "#ffffff"})
        says("a font and a color: the font and colors are set",
             got == "🎨 The menu's font and colors are set. Save Profile keeps them with this game.", got)
        got = line({"Scale": 1.2, "Top": 100})
        says("size and top line", got == "🎨 The menu's size and top line are set. Save Profile keeps them with "
                                         "this game.", got)
        says("nothing set: the menu keeps its own", line({}) == "🎨 The menu keeps its own font and colors.")
        def refused(theme):
            try:
                return line(theme, font_refused=True)
            except TypeError as e:  # a Rialto from before the re-run: no font_refused
                return str(e)
        got = refused({"Font": "a.ttf", "License": "b.json"})
        says("a font refused for its license is not called set", got == "🎨 The menu keeps its own font and colors.", got)
        got = refused({"Font": "a.ttf", "License": "b.json", "Text": "#ffffff"})
        says("and the colors set with it still are", got == "🎨 The menu's colors are set. Save Profile keeps them "
                                                           "with this game.", got)
        says("Save logs that line, told whether the font was refused",
             "self.update_status(menu_theme_saved_line(kept, font_refused=bool(problem)))"
             in method(src, "configure_menu_theme"))
        print()

        print("7. the Library Hero: Steam crops any edge")
        hero = [s for s in strings if "860 x 380" in s]
        says("the tooltip no longer says only its sides", hero and not any("crops its sides" in s for s in hero),
             hero)
        says("it says the top and bottom go too", any("top" in s and "bottom" in s for s in hero), hero)
        row = guide_row(guide, "Library Hero")
        says("and so does the Help Guide", "crops its sides" not in row and "top and bottom" in row, row)
        print()

        print("8. one name for the dialog: Font and Colors")
        named = [s for s in strings if "Menu Font and Colors" in s]
        says("no word Rialto shows says Menu Font and Colors", not named, named)
        says("the dialog's title is Font and Colors", '"Font and Colors",\n            "The words on your disc' in
             method(src, "configure_menu_theme"))
        says("the button is Font and Colors…", any(s == "Font and Colors…" for s in strings))
        says("and the Help Guide has none", "Menu Font and Colors" not in guide)
        print()

        print("9. the disc meter counts a set as the build packs it")
        tree = ast.parse(src)
        meter_ns = tmd.module_names(src, tree, ["MINI_DISC_MEDIA", "spanned_disc_count"])
        theme = {k: k for k in ("meter_fill", "meter_warn", "meter_over", "meter_track", "header_bg", "button_bg")}

        def meter(media, total, disc1):
            host = tmd.media_host(src, meter_ns, ["get_target_media_capacity", "draw_disc_meter"], media,
                                  disc_bar=tmd.Canvas(), disc_meter=tmd.Canvas(), theme_mode=tmd.Var("dark"),
                                  dark_theme=theme, light_theme=theme, disc_fill_var=tmd.Var(""),
                                  _fill_bytes=total, _disc1_bytes=disc1)
            host.draw_disc_meter()
            return host.disc_fill_var.get(), host

        line, host = meter("CD 700 MB", 1_980_000_000, 60_000_000)
        capacity = host.get_target_media_capacity()
        want = meter_ns["spanned_disc_count"](60_000_000, 1_920_000_000, capacity, host.MEDIA_RESERVE,
                                              host.SPAN_MARGIN)
        says("Hollow Pines on CD 700 MB: the build makes 3, and the meter says about 3",
             want == 3 and line.endswith(" - about 3 discs, fewer once compressed"), (want, line))
        line, host = meter("DVD 4.7 GB", 9_000_000_000, 100_000_000)
        want = meter_ns["spanned_disc_count"](100_000_000, 8_900_000_000, host.get_target_media_capacity(),
                                              host.MEDIA_RESERVE, host.SPAN_MARGIN)
        says("a DVD set: the meter's count is the build's",
             line.endswith(" - about %d discs, fewer once compressed" % want), (want, line))
        fit = capacity - host.SPAN_MARGIN - 1_000_000
        line, _host = meter("CD 700 MB", fit, 50_000_000)
        says("over the usable line but one disc for the build: no count of discs", "discs" not in line, line)
        print()

        print("10. a profile saved with a byte order mark loads")
        opens = re.findall(r'with open\([^\n]*encoding="([^"]+)"\) as (\w+):\n\s+\w+ = sanitize_profile_data\('
                           r'json\.load\(\2\)\)', src)
        says("every profile and queue read takes a byte order mark (4 of them)",
             len(opens) == 4 and all(enc == "utf-8-sig" for enc, _f in opens), opens)
        bom = os.path.join(work, "bom-profile.json")
        with open(bom, "w", encoding="utf-8-sig") as f:
            json.dump({"Title": "Hollow Pines"}, f)
        try:
            with open(bom, encoding=opens[0][0] if opens else "utf-8") as f:
                loaded = json.load(f)
        except ValueError as e:
            loaded = str(e)
        says("Load Profile reads it as written", loaded == {"Title": "Hollow Pines"}, loaded)
        print()

        print("11. an upgrade keeps the player's stars and menu language")
        ns = module(src, ["earlier_menu_titles"])
        titles = ns["earlier_menu_titles"]("Moth Lamp", "Moth Lamp") if ns else []
        says("the disc names the titles a disc from before kept them under",
             titles == ["Moth Lamp (PC CD)", "Moth Lamp (PC DVD)", "Moth Lamp (PC CD+Soundtrack CD)",
                        "Moth Lamp (PC DVD+Soundtrack CD)"], titles)
        titles = ns["earlier_menu_titles"]("Moth Lamp (PC DVD)", "Moth Lamp") if ns else []
        says("the title as typed first, never the game's own name",
             titles[:1] == ["Moth Lamp (PC DVD)"] and "Moth Lamp" not in titles and len(set(titles)) == len(titles),
             titles)
        says("menu_config.json carries them", '"earlier_titles": earlier_menu_titles(' in method(src, "build_menu_config"))
        menu_src = ast.literal_eval(next(n.value for n in ast.parse(src).body if isinstance(n, ast.Assign)
                                         and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))
        menu_tree = ast.parse(menu_src)
        wanted = [ast.get_source_segment(menu_src, n) for n in menu_tree.body
                  if isinstance(n, ast.FunctionDef) and n.name in ("player_prefs_path", "read_player_prefs",
                                                                     "write_player_prefs", "menu_earlier_titles")]
        local = os.path.join(work, "LocalAppData")
        os.makedirs(local)
        saved_env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = local
        try:
            mns = {"os": os, "json": json, "MENU_TITLE": "Moth Lamp", "MAX_STARS": 200}
            exec("\n\n".join(wanted), mns)
            old = mns["player_prefs_path"]("Moth Lamp (PC CD)")
            os.makedirs(os.path.dirname(old))
            with open(old, "w", encoding="utf-8") as f:
                json.dump({"stars": ["Moth Lamp"], "sort": "az", "lang": "Japanese"}, f)
            says("the 1.5.1 disc kept them in Moth Lamp PC CD", os.path.basename(os.path.dirname(old))
                 == "Moth Lamp PC CD")
            earlier = mns["menu_earlier_titles"](["Moth Lamp (PC CD)", "Moth Lamp", 7, "x" * 300]) \
                if "menu_earlier_titles" in mns else []
            says("the menu reads the list with suspicion: strings only, never its own title, each cut to 200",
                 earlier == ["Moth Lamp (PC CD)", "x" * 200], earlier)
            try:
                prefs = mns["read_player_prefs"]("Moth Lamp", earlier)
            except TypeError as e:
                prefs = str(e)
            says("the 1.5.2 menu reads them there when its own folder has none",
                 isinstance(prefs, dict) and prefs.get("stars") == ["Moth Lamp"] and prefs.get("lang") == "Japanese",
                 prefs)
            if isinstance(prefs, dict):
                prefs["lang"] = "French"
                mns["write_player_prefs"]("Moth Lamp", prefs)
                says("then keeps them under the game's name, which it reads first from then on",
                     mns["read_player_prefs"]("Moth Lamp", earlier)["lang"] == "French")
            says("the menu asks with its earlier titles",
                 "self.player_prefs = read_player_prefs(MENU_TITLE, EARLIER_TITLES)" in menu_src)
        finally:
            if saved_env is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = saved_env
        print()

        print("12. the start puts back the last profile's settings, but this PC's own ticks and no advice")
        ns = module(src, ["sanitize_profile_data", "COMPRESSION_CHOICES"])
        start_ns = dict(ns or {})
        start_ns.update({"tk": type("tk", (), {"END": "end"}), "APP_ROOT": os.path.join(work, "app"),
                         "TEMPLATES_DIR": os.path.join(work, "app", "templates"),
                         "LAST_PROFILE_FILE": os.path.join(work, "app", "last_profile.json")})
        code = "class Start:\n" + textwrap.indent(method(src, "put_profile_on_form") + "\n\n"
                                                  + method(src, "load_last_used_profile"), "    ")
        try:
            exec(code, start_ns)
        except SyntaxError as e:
            start_ns["Start"] = None
            says("the start's methods compile", False, e)

        class Var:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Entry(Var):
            def delete(self, _first, _last):
                self.value = ""

            def insert(self, _at, value):
                self.value = value

        def host_for(cls):
            class Host(cls):
                def __init__(self):
                    self.entries = {"Title": Entry()}
                    self.log = []
                    self.steam_art = None
                    self.menu_theme = None
                    self.meter_refreshed = 0

                def __getattr__(self, name):
                    if name.endswith("_var") or name == "remove_wti_branding":
                        var = Var("")
                        setattr(self, name, var)
                        return var
                    raise AttributeError(name)

                def update_status(self, line):
                    self.log.append(line)

                def refresh_game_exes_summary(self):
                    pass

                def _regenerate_copyright(self):
                    pass

                def set_steam_art(self, art):
                    self.steam_art = art

                def refresh_disc_meter(self):
                    self.meter_refreshed += 1

                def rebase_stale_paths(self):
                    self.log.append("rebased")
            return Host()

        if start_ns.get("Start"):
            os.makedirs(start_ns["TEMPLATES_DIR"], exist_ok=True)
            profile = {"Title": "Hollow Pines (PC CD)", "TargetMedia": "CD 700 MB", "Compression": "Fastest install",
                       "PressedDisc": True, "MacBuild": "C:/games/hp/mac", "LinuxBuild": "C:/games/hp/linux",
                       "BonusFolder": "C:/games/hp/bonus", "ModFolder": "C:/games/hp/mods", "SteamButton": False,
                       "CompanyLogo": "C:/games/hp/co.png", "PublisherText": "(c) 2026 Larkin",
                       "CompatibilityMode": True, "CompatibilityArgs": "--opengl", "Logo": "C:/games/hp/old_logo.png",
                       "RemoveWTIBranding": False, "SteamArt": {"Capsule": "C:/games/hp/cap.png"},
                       "MenuMusic": "C:/games/hp/loop.wav", "MenuTheme": {"Text": "#ffffff"}, "BackgroundHasTitle": True}
            # Saved by Load Profile's folder, with a byte order mark, as PowerShell 5.1 writes one.
            with open(os.path.join(start_ns["TEMPLATES_DIR"], "HP.json"), "w", encoding="utf-8-sig") as f:
                json.dump(profile, f)
            with open(start_ns["LAST_PROFILE_FILE"], "w", encoding="utf-8") as f:
                json.dump({"last_profile": "HP.json"}, f)

            h = host_for(start_ns["Start"])
            # What load_config and the last session put back before the profile.
            h.remove_wti_branding = Var(True)
            h.mod_launcher_var = Var(True)
            h.logo_path_var = Var("C:/games/hp/new_logo.png")
            h.load_last_used_profile()
            says("a profile kept in templates/ is found at start", "✅ Restored session from HP.json" in h.log, h.log)
            for name, want in (("target_media_var", "CD 700 MB"), ("compression_var", "Fastest install"),
                               ("pressed_disc_var", True), ("mac_build_var", "C:/games/hp/mac"),
                               ("linux_build_var", "C:/games/hp/linux"), ("bonus_folder_var", "C:/games/hp/bonus"),
                               ("mod_folder_var", "C:/games/hp/mods"), ("steam_button_var", False),
                               ("company_logo_var", "C:/games/hp/co.png"), ("publisher_text_var", "(c) 2026 Larkin"),
                               ("compat_mode_var", True), ("compat_args_var", "--opengl"),
                               ("menu_music_var", "C:/games/hp/loop.wav"), ("bg_has_title_var", True)):
                says("the start puts back %s" % name, getattr(h, name).get() == want, getattr(h, name).get())
            says("and the title, the menu's look and the Steam art", h.entries["Title"].get() == "Hollow Pines (PC CD)"
                 and h.menu_theme == {"Text": "#ffffff"} and h.steam_art == {"Capsule": "C:/games/hp/cap.png"},
                 (h.entries["Title"].get(), h.menu_theme, h.steam_art))
            says("this PC's Remove WTI Branding tick stays as config.json has it", h.remove_wti_branding.get() is True)
            says("and its MODS tick", h.mod_launcher_var.get() is True)
            says("the last session's Game Logo stays, as the start always kept it",
                 h.logo_path_var.get() == "C:/games/hp/new_logo.png", h.logo_path_var.get())
            says("no rebase and no 'pick again' advice before a game folder is chosen",
                 "rebased" not in h.log and not any("no longer exists" in line or "Pick " in line for line in h.log), h.log)
            says("the meter is told once", h.meter_refreshed == 1, h.meter_refreshed)

            # Rialto's own folder still comes first, as before.
            with open(os.path.join(start_ns["APP_ROOT"], "HP.json"), "w", encoding="utf-8") as f:
                json.dump(dict(profile, TargetMedia="DVD 4.7 GB"), f)
            h = host_for(start_ns["Start"])
            h.load_last_used_profile()
            says("a profile beside Rialto wins over one of the same name in templates/",
                 h.target_media_var.get() == "DVD 4.7 GB", h.target_media_var.get())

            # Load Profile itself still takes the profile's ticks and Game Logo.
            h = host_for(start_ns["Start"])
            h.remove_wti_branding = Var(True)
            h.mod_launcher_var = Var(True)
            if hasattr(type(h), "put_profile_on_form"):
                h.put_profile_on_form(start_ns["sanitize_profile_data"](profile))
            says("Load Profile takes the profile's Remove WTI Branding, MODS and Game Logo, as before",
                 h.remove_wti_branding.get() is False and h.mod_launcher_var.get() is False
                 and h.logo_path_var.get() == "C:/games/hp/old_logo.png",
                 (h.remove_wti_branding.get(), h.mod_launcher_var.get(), h.logo_path_var.get()))
        loading = method(src, "apply_profile_file")
        says("Load Profile still re-points moved paths after the fields are on the form",
             0 <= loading.find("self.put_profile_on_form(profile_data)") < loading.find("self.rebase_stale_paths()"))
        print()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        return 1
    print("Every readiness finding stays fixed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
