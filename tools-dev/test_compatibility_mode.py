"""Exercise the compatibility-mode launch button on both sides.

Build side:  split_launch_args + RialtoApp.build_menu_config (Rialto.pyw)
Menu side:   clean_launch_args + GameMenu.compatibility_args /
             compatibility_label / launch_game / launch_configured_exe
             (all inside MENU_TEMPLATE_SOURCE)

For a game that switches from Vulkan to OpenGL on a launch argument: the
player should get a button, not an instruction to edit
a shortcut. The argument line the author types has to survive the trip into
menu_config.json, and the menu has to refuse a config that was tampered with
on the way - so both halves are tested, and the argv the game would actually
receive is asserted rather than assumed.

Source-extracted and exec'd on stub objects, so no tkinter and no PyQt5.
"""
import ast
import os
import sys
import textwrap

# This one prints translated button labels, so it has to survive a cp1252
# console when run on its own rather than through run_all.py.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_source import extract_menu_source  # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def ok(label, condition):
    print(f"  [{'OK  ' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


def module_bits(src, names):
    """Module-level functions and assignments, by name."""
    tree = ast.parse(src)
    out, got = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            got.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    out.append(ast.get_source_segment(src, node))
                    got.add(target.id)
    missing = set(names) - got
    if missing:
        raise SystemExit(f"could not extract {sorted(missing)}")
    return "\n\n".join(out)


def methods(src, class_name, names):
    tree = ast.parse(src)
    out, got = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.name)
    missing = set(names) - got
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


def make_host(method_src, globals_=None, **attrs):
    ns = {"os": os, "sys": sys}
    ns.update(globals_ or {})
    exec(f"class Host:\n{textwrap.indent(method_src, '    ')}", ns)
    host = ns["Host"]()
    for k, v in attrs.items():
        setattr(host, k, v)
    return host


class Flag:
    """Stands in for a tk.StringVar / BooleanVar."""
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


class FakePopen:
    """Records the argv the menu would have handed to Windows."""
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return None


def main():
    rialto_src = open(RIALTO, encoding="utf-8").read()
    menu_src = extract_menu_source(RIALTO)

    # ------------------------------------------------------------------
    print("1. the author's argument line becomes a list")
    build_ns = {}
    exec(module_bits(rialto_src, ["_CONTROL_CHARS", "sanitize_text", "split_launch_args"]),
         build_ns)
    split = build_ns["split_launch_args"]

    check("a single flag", split("-opengl"), ["-opengl"])
    check("two arguments", split("-force-gl -windowed"), ["-force-gl", "-windowed"])
    check("extra spaces collapse", split("  -a    -b  "), ["-a", "-b"])
    check("quotes hold one argument together",
          split('--mode "high end"'), ["--mode", "high end"])
    # shlex's POSIX mode would have eaten these backslashes.
    check("a Windows path survives intact",
          split(r'-config C:\Users\Dev\my.cfg'), ["-config", r"C:\Users\Dev\my.cfg"])
    check("nothing typed means nothing passed", split(""), [])
    check("only spaces means nothing passed", split("   "), [])

    # The trust boundary: profile JSON is shared between authors and loaded at
    # startup. A newline here would otherwise ride into menu_config.json.
    check("a newline in the argument line is stripped, not split on",
          split("-opengl\n-cheats"), ["-opengl-cheats"])
    check("a NUL is stripped too", split("-open\x00gl"), ["-opengl"])

    check("the argument count is capped",
          len(split(" ".join("-a%d" % i for i in range(40)))), 16)
    check("a single argument is capped in length",
          len(split("-" + "x" * 500)[0]), 256)

    # ------------------------------------------------------------------
    print("2. what build_menu_config writes into menu_config.json")

    def config_host(mode, args, hint=""):
        host = make_host(
            methods(rialto_src, "RialtoApp", ["build_menu_config"]),
            {"strip_wti_mentions": lambda s: s,
             "sanitize_text": build_ns["sanitize_text"],
             "split_launch_args": split},
            entries={"Title": Flag("Mock Game")},
            company_logo_var=Flag(""),
            publisher_text_var=Flag("(c) 2026"),
            remove_wti_branding=Flag(False),
            steam_button_var=Flag(True),
            mod_launcher_var=Flag(False),
            compat_mode_var=Flag(mode),
            compat_args_var=Flag(args),
            compat_hint_var=Flag(hint),
        )
        host.validated_game_executables = lambda: []
        host.detect_primary_game_exe = lambda root: "game.exe"
        host.update_status = lambda msg: None
        return host.build_menu_config("C:\\nowhere")

    off = config_host(False, "-opengl")
    check("off: the flag is off", off["compat_mode"], False)
    check("off: and the argument does not ride along anyway", off["compat_args"], [])

    on = config_host(True, "-opengl")
    check("on: the flag is on", on["compat_mode"], True)
    check("on: the argument is a list", on["compat_args"], ["-opengl"])
    ok("the config carries no button name at all", "compat_label" not in on)

    # Ticked but empty is the state an author lands in halfway through typing.
    # The disc must not ship a button that adds nothing.
    empty = config_host(True, "   ")
    check("ticked with no argument does not enable the button", empty["compat_mode"], False)
    check("and writes no arguments", empty["compat_args"], [])

    check("the author's hint rides along", on["compat_hint"], "")
    check("and is written when there is one",
          config_host(True, "-opengl", "Runs on OpenGL.")["compat_hint"],
          "Runs on OpenGL.")

    # A Godot game. Godot 4's OpenGL renderer flag
    # is two tokens, which is exactly the case the hand-written splitter exists
    # for - one token would have been a different, wrong command line.
    godot = config_host(True, "--rendering-method gl_compatibility")
    check("a real Godot 4 argument survives as two tokens",
          godot["compat_args"], ["--rendering-method", "gl_compatibility"])

    # ------------------------------------------------------------------
    print("3. the menu re-checks the config before it uses it")
    menu_ns = {}
    exec(module_bits(menu_src, ["MAX_LAUNCH_ARGS", "MAX_LAUNCH_ARG_LEN", "clean_launch_args"]),
         menu_ns)
    clean = menu_ns["clean_launch_args"]

    check("a normal list passes", clean(["-opengl"]), ["-opengl"])
    check("two arguments pass", clean(["--mode", "high end"]), ["--mode", "high end"])
    check("a missing key is not a list", clean(None), [])
    check("a bare string is refused, not iterated into characters",
          clean("-opengl"), [])
    check("an empty list is refused", clean([]), [])
    check("a dict is refused", clean({"a": "b"}), [])
    check("a non-string member refuses the whole set", clean(["-opengl", 7]), [])
    check("an empty member refuses the whole set", clean(["-opengl", ""]), [])
    check("too many arguments refuses the whole set",
          clean(["-a%d" % i for i in range(17)]), [])
    check("an over-long argument refuses the whole set",
          clean(["-" + "x" * 300]), [])
    # Refusing the set, not the member: dropping "opengl" out of
    # ("-mode", "opengl") would launch a different mode than the author meant.
    check("a control character refuses the whole set, it is not repaired",
          clean(["-mode", "open\ngl"]), [])
    check("a NUL refuses the whole set", clean(["-mode", "open\x00gl"]), [])
    check("DEL refuses the whole set", clean(["-mode", "open\x7fgl"]), [])

    # ------------------------------------------------------------------
    print("4. the menu only offers the button when it should")
    menu_methods = methods(menu_src, "GameMenu",
                           ["compatibility_args", "compatibility_label",
                            "compatibility_hint"])
    trans = {"English": {
                 "compat": "Compatibility Mode",
                 "tip_compat": "Starts the game with settings for older or "
                               "unsupported graphics hardware."},
             "German": {
                 "compat": "Kompatibilitätsmodus",
                 "tip_compat": "Startet das Spiel mit Einstellungen für ältere Grafik."}}

    def menu_host(config, lang="English"):
        return make_host(menu_methods, {"clean_launch_args": clean},
                         menu_config=config, translations=trans, current_lang=lang)

    check("configured and enabled -> arguments",
          menu_host({"compat_mode": True, "compat_args": ["-opengl"]}).compatibility_args(),
          ["-opengl"])
    check("no config at all -> nothing",
          menu_host({}).compatibility_args(), [])
    check("arguments present but the flag is off -> nothing",
          menu_host({"compat_mode": False, "compat_args": ["-opengl"]}).compatibility_args(),
          [])
    # A swapped menu_config.json is the case the whole check exists for.
    check("flag on but the arguments were tampered with -> nothing",
          menu_host({"compat_mode": True, "compat_args": ["-x\n-y"]}).compatibility_args(),
          [])

    check("no author label -> the player's own language",
          menu_host({"compat_mode": True}).compatibility_label(), "Compatibility Mode")
    check("and it follows the language the player picked",
          menu_host({"compat_mode": True}, "German").compatibility_label(),
          "Kompatibilitätsmodus")
    # A game-flavoured name like "Legacy Graphics" reads as something the game
    # offers rather than a way to start it, and the words should mean the same
    # thing on every disc a player owns. The tooltip carries what is specific.
    check("a config trying to rename the button is ignored",
          menu_host({"compat_mode": True, "compat_label": "Legacy Graphics"},
                    "English").compatibility_label(), "Compatibility Mode")
    # Every other button shouts; this one does not, because it is a line
    # under PLAY rather than a heading beside it.
    ok("the label is not upper-cased",
       menu_host({"compat_mode": True}).compatibility_label() != "COMPATIBILITY MODE")
    ok("the menu never reads a button name from the config",
       "compat_label" not in menu_src)

    print("4b. the tooltip that says what the mode actually does")
    check("no author hint -> the generic wording, in the player's language",
          menu_host({"compat_mode": True}).compatibility_hint(),
          "Starts the game with settings for older or unsupported graphics hardware.")
    check("and it follows the language too",
          menu_host({"compat_mode": True}, "German").compatibility_hint(),
          "Startet das Spiel mit Einstellungen für ältere Grafik.")
    check("the author's own sentence wins",
          menu_host({"compat_mode": True,
                     "compat_hint": "Runs on OpenGL instead of Vulkan."}).compatibility_hint(),
          "Runs on OpenGL instead of Vulkan.")
    check("a control character never reaches the tooltip",
          menu_host({"compat_mode": True,
                     "compat_hint": "Runs on\nOpenGL."}).compatibility_hint(),
          "Runs on OpenGL.")
    check("the tooltip is capped",
          len(menu_host({"compat_mode": True,
                         "compat_hint": "x" * 400}).compatibility_hint()), 200)

    # ------------------------------------------------------------------
    print("5. the argv the game actually receives")
    launch_src = methods(menu_src, "GameMenu",
                         ["launch_game", "launch_configured_exe", "compatibility_args",
                          "launch_compatibility_mode"])
    fake_popen = FakePopen()

    class FakeApp:
        @staticmethod
        def instance():
            class _Q:
                @staticmethod
                def quit():
                    return None
            return _Q()

    exe = os.path.join(REPO, "tools-dev", "test_compatibility_mode.py")  # any real file

    def launch_host(games, config):
        host = make_host(
            launch_src,
            {"subprocess": type("S", (), {"Popen": fake_popen}),
             "QtWidgets": type("W", (), {"QApplication": FakeApp}),
             "clean_launch_args": clean},
            preview_mode=False, games=games, menu_config=config,
            translations=trans, current_lang="English")
        host.find_game_exe = lambda: (exe, [])
        host._configured_exe = lambda rel: exe
        return host

    cfg = {"compat_mode": True, "compat_args": ["-opengl"]}

    fake_popen.calls.clear()
    launch_host([], cfg).launch_game()
    check("plain PLAY passes no arguments", fake_popen.calls[0][0], [exe])

    fake_popen.calls.clear()
    launch_host([], cfg).launch_compatibility_mode()
    check("the compatibility button appends the argument, exe first",
          fake_popen.calls[0][0], [exe, "-opengl"])

    # List-form Popen with a path we resolved ourselves: an argument can tell
    # the game something, but it can never become the program that runs.
    fake_popen.calls.clear()
    host = launch_host([], {"compat_mode": True,
                            "compat_args": ["&", "calc.exe", "|", "whoami"]})
    host.launch_compatibility_mode()
    check("shell metacharacters stay arguments, they do not become commands",
          fake_popen.calls[0][0], [exe, "&", "calc.exe", "|", "whoami"])
    ok("and no shell was asked for", all("shell" not in kw for _a, kw in fake_popen.calls))

    fake_popen.calls.clear()
    launch_host([{"name": "One", "exe": "one.exe"}], cfg).launch_compatibility_mode()
    check("a one-game configured disc gets the argument too",
          fake_popen.calls[0][0], [exe, "-opengl"])

    # ------------------------------------------------------------------
    print("6. the button is wired into the menu the same way the others are")
    tree = ast.parse(menu_src)
    sources = [ast.unparse(n) for n in ast.walk(tree)]
    ok("the button only appears behind compatibility_args()",
       "if self.compatibility_args() and not self.installer_path:" in menu_src)
    ok("it is added to the button column",
       "buttons_to_add.append(self.compat_btn)" in menu_src)
    ok("it re-labels when the player changes language",
       "self.compat_btn.setText(self.compatibility_label())" in menu_src)
    ok("every language carries the wording",
       menu_src.count('"compat": "') == menu_src.count('"mods": "'))
    ok("nothing per-title is spliced into the menu source",
       "-opengl" not in menu_src)

    print("7. the tooltips that say what the buttons mean")
    languages = menu_src.count('"mods": "')
    for key in ("tip_compat", "tip_bonus", "tip_mods", "tip_steam", "tip_uninstall"):
        ok("every language carries %s" % key, menu_src.count('"%s": "' % key) == languages)
    ok("the compatibility button gets one",
       "self.compat_btn.setToolTip(self.compatibility_hint())" in menu_src)
    for button, key in (("bonus_btn", "tip_bonus"), ("mods_btn", "tip_mods"),
                        ("steam_btn", "tip_steam"), ("uninstall_btn", "tip_uninstall")):
        ok("%s gets one" % button,
           'self.%s.setToolTip(' % button in menu_src and key in menu_src)
    # A tooltip that restates the button is noise, so these two have none.
    # PLAY earns a tooltip only when it is really an INSTALL button - then
    # the word has changed and the player deserves to know what it will run.
    ok("PLAY is only explained when it installs",
       menu_src.count("self.play_btn.setToolTip") == 2
       and 'trans["tip_install"]' in menu_src)
    ok("EXIT has no tooltip", "self.exit_btn.setToolTip" not in menu_src)
    # The stock Windows tooltip is a pale yellow slab; on this menu that reads
    # as a bug, so the dark styling has to actually be applied.
    ok("the dark tooltip style is defined", "QToolTip {" in menu_src)
    ok("and applied to the window", "self.setStyleSheet(self.TOOLTIP_STYLE)" in menu_src)
    ok("switching language re-labels the tooltips too",
       menu_src.count("setToolTip") >= 10)

    print()
    if failures:
        print("FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("compatibility mode: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
