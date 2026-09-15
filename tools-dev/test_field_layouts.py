"""Four field layouts Rialto once handled quietly, each pinned so it stays fixed.

Developers name folders their own way: a mod tool in mod-maker/, the executable
two folders down in game/Windows x86_64 Portable/, a profile saved against a
different input root. Every case below is a thing the build used to do
quietly rather than loudly.

  1. detect_mod_launcher_exe invented "mods/ModLauncher.exe" when it found
     nothing, and that path could end up in a disc's menu_config.json. The
     MODS button was switched on in the config pointing at a file that had
     never existed anywhere.
  2. The profile's LinuxBuild pointed at an input root the author had moved
     away from, so the Linux build was passed over with one warning line and
     a "universal disc" came out Windows-only.
  3. The generated compatibility test globbed *.exe at the top level only, so
     a game in a subfolder was reported as CRITICAL ERRORS on a good disc -
     and the same miss was counted twice.
  4. The disc-root menu offered PLAY on an install-first disc, where the game
     exists only inside setup.exe. The player got "Game executable not found".

Source-extracted and exec'd on stub objects: no tkinter, no PyQt5.
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap

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
    good = got == want
    print(f"  [{'OK  ' if good else 'FAIL'}] {label}: {got!r}")
    if not good:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def ok(label, cond):
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def extract(src, class_name, names):
    tree = ast.parse(src)
    out, got = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.name)
                elif isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.targets[0].id)
    missing = set(names) - got
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


def host(method_src, globals_=None, **attrs):
    ns = {"os": os, "sys": sys, "shutil": shutil}
    ns.update(globals_ or {})
    exec(f"class Host:\n{textwrap.indent(method_src, '    ')}", ns)
    obj = ns["Host"]()
    obj.update_status = lambda msg: None
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


class Flag:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v

    def set(self, value):
        self._v = value


def touch(*parts):
    p = os.path.join(*parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write("x")
    return p


def real_game_tree(base):
    """A developer-shaped input folder."""
    game = os.path.join(base, "input", "MyGame")
    touch(game, "game", "Windows x86_64 Portable", "MyGame.exe")
    os.makedirs(os.path.join(game, "game", "Linux x86_64 Portable"), exist_ok=True)
    touch(game, "mod-maker", "Windows x86_64", "MyGame Mod Maker.exe")
    touch(game, "bonus", "wallpapers", "one.png")
    touch(game, "soundtrack", "01.mp3")
    return game


def main():
    src = open(RIALTO, encoding="utf-8").read()
    menu_src = extract_menu_source(RIALTO)
    base = tempfile.mkdtemp(prefix="rialto_realdisc_")
    try:
        game = real_game_tree(base)

        # --------------------------------------------------------------
        print("1. the mod tool is found where the author actually put it")
        mod_src = extract(src, "RialtoApp",
                          ["detect_mod_launcher_exe", "default_mod_dir",
                           "resolved_mod_dir", "staged_mod_dir_name"])

        # The output folder is what copy_game_files_to_output produces: the
        # game folder's contents, so mod-maker/ is already sitting there.
        output = os.path.join(base, "output", "MyGame")
        os.makedirs(output, exist_ok=True)
        for name in ("game", "mod-maker", "bonus", "soundtrack"):
            shutil.copytree(os.path.join(game, name), os.path.join(output, name))

        picked = host(mod_src, mod_folder_var=Flag(os.path.join(game, "mod-maker")),
                      current_game_path=game)
        check("an author-named folder is found",
              picked.detect_mod_launcher_exe(output),
              "mod-maker/Windows x86_64/MyGame Mod Maker.exe")

        # The bug: this used to answer "mods/ModLauncher.exe" regardless.
        nothing = host(mod_src, mod_folder_var=Flag(""), current_game_path=game)
        check("nothing configured and no mods folder -> nothing invented",
              nothing.detect_mod_launcher_exe(output), "")
        # It survives in a docstring explaining the bug, which is fine.
        # What matters is that no code path returns it any more.
        returns = [ast.literal_eval(n.value)
                   for fn in ast.walk(ast.parse(src))
                   if isinstance(fn, ast.FunctionDef) and fn.name == "detect_mod_launcher_exe"
                   for n in ast.walk(fn)
                   if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)]
        ok("no code path returns an invented mod path",
           all(r == "" for r in returns) and returns)

        print("   and the config never claims a button it cannot back")
        cfg_src = extract(src, "RialtoApp", ["build_menu_config"]) + "\n\n" + mod_src
        cfg = host(cfg_src,
                   {"strip_wti_mentions": lambda s: s,
                    "sanitize_text": lambda v: str(v or ""),
                    "split_launch_args": lambda v, **k: []},
                   entries={"Title": Flag("MyGame")},
                   company_logo_var=Flag(""), publisher_text_var=Flag(""),
                   remove_wti_branding=Flag(False), steam_button_var=Flag(True),
                   mod_launcher_var=Flag(True), mod_folder_var=Flag(""),
                   compat_mode_var=Flag(False), compat_args_var=Flag(""),
                   compat_hint_var=Flag(""), current_game_path=game)
        cfg.validated_game_executables = lambda: []
        cfg.detect_primary_game_exe = lambda root: "game/Windows x86_64 Portable/MyGame.exe"
        built = cfg.build_menu_config(output)
        check("ticked but nothing found -> the flag goes back off",
              built["mod_launcher"], False)
        check("and no path is written", built["mod_exe"], "")

        cfg.mod_folder_var = Flag(os.path.join(game, "mod-maker"))
        found = cfg.build_menu_config(output)
        check("pointed at mod-maker -> the flag stands",
              found["mod_launcher"], True)
        check("and the real tool is named",
              found["mod_exe"], "mod-maker/Windows x86_64/MyGame Mod Maker.exe")

        print("   and the disc root carries that folder, not one called mods")
        fileset_src = extract(src, "RialtoApp", ["_collect_disc_fileset"]) + "\n\n" + mod_src
        fs = host(fileset_src, mod_launcher_var=Flag(True),
                  mod_folder_var=Flag(os.path.join(game, "mod-maker")),
                  current_game_path=game)
        touch(output, "setup.exe")
        items = fs._collect_disc_fileset(output)
        ok("mod-maker is on the disc", "mod-maker" in items)

        # --------------------------------------------------------------
        print("2. a profile path from another input root is found again")
        rebase_src = extract(src, "RialtoApp",
                             ["rebase_under_game", "rebase_stale_paths",
                              "missing_configured_extras", "REBASEABLE_PATHS"])
        stale = "C:/Rialto/input/MyGame/game/Linux x86_64 Portable"
        r = host(rebase_src, current_game_path=game,
                 mac_build_var=Flag(""), linux_build_var=Flag(stale),
                 bonus_folder_var=Flag("C:/Rialto/input/MyGame/bonus"),
                 mod_folder_var=Flag(""))
        check("the Linux build is re-pointed at the game folder in use",
              r.rebase_under_game(stale),
              os.path.join(game, "game", "Linux x86_64 Portable"))
        check("rebasing fixes every stale path it can", r.rebase_stale_paths(), 2)
        check("and the Linux var now resolves",
              os.path.isdir(r.linux_build_var.get()), True)
        check("nothing is left missing", r.missing_configured_extras(), [])

        # A path that is genuinely gone must NOT be guessed at.
        gone = host(rebase_src, current_game_path=game,
                    mac_build_var=Flag("D:/somewhere/Mac Build"),
                    linux_build_var=Flag(""), bonus_folder_var=Flag(""),
                    mod_folder_var=Flag(""))
        check("a folder that exists nowhere is not invented",
              gone.rebase_under_game("D:/somewhere/Mac Build"), "")
        check("it is reported as missing instead",
              gone.missing_configured_extras(), [("Mac build", "D:/somewhere/Mac Build")])
        check("a path that still resolves is left alone",
              r.rebase_under_game(game), "")

        # --------------------------------------------------------------
        print("3. the compatibility test finds a game in a subfolder")
        test_src = extract(src, "RialtoApp", ["create_compatibility_test_script"])
        t = host(test_src, {"escape_batch": lambda v: str(v)},
                 entries={"Title": Flag("MyGame")})
        t.detect_primary_game_exe = lambda root: "game/Windows x86_64 Portable/MyGame.exe"
        t.create_compatibility_test_script(output)
        script = open(os.path.join(output, "compatibility_test.bat"), encoding="utf-8",
                      errors="replace").read()
        ok("the detected exe is checked by path",
           r"game\Windows x86_64 Portable\MyGame.exe" in script)
        ok("an install-first disc counts setup.exe as the game",
           "Game ships inside the installer" in script)
        ok("the top-level glob only runs if nothing was found yet",
           "if %GAME_EXE_FOUND%==0 for %%f in (*.exe)" in script)
        # Two [X] lines for one missing exe read as "2 CRITICAL ERRORS".
        test4 = script.split("[TEST 4]")[1].split("[TEST 5]")[0]
        ok("test 4 points back at test 1 rather than counting again",
           "see Test 1" in test4 and "set /a ERRORS+=1" not in test4)

        # --------------------------------------------------------------
        print("4. an install-first disc offers INSTALL, not a PLAY that cannot work")
        menu_bits = extract(menu_src, "GameMenu",
                            ["disc_installer", "_configured_exe", "_inside_game_dir",
                             "_is_helper_exe", "_is_reparse_point", "find_game_exe",
                             "HELPER_EXES"])
        disc = os.path.join(base, "disc")
        os.makedirs(os.path.join(disc, "menu"), exist_ok=True)
        touch(disc, "setup.exe")

        m = host(menu_bits, game_dir=disc, games=[], preview_mode=False,
                 menu_config={"game_exe": "game/Windows x86_64 Portable/MyGame.exe"})
        check("on the disc, the installer is offered",
              os.path.basename(m.disc_installer()), "setup.exe")

        # Once installed the game is right there, so PLAY means PLAY again.
        installed = os.path.join(base, "installed")
        touch(installed, "game", "Windows x86_64 Portable", "MyGame.exe")
        touch(installed, "setup.exe")
        m2 = host(menu_bits, game_dir=installed, games=[], preview_mode=False,
                  menu_config={"game_exe": "game/Windows x86_64 Portable/MyGame.exe"})
        check("with the game present, no installer button",
              m2.disc_installer(), "")

        # No setup.exe anywhere: report honestly rather than inventing a button.
        bare = os.path.join(base, "bare")
        os.makedirs(os.path.join(bare, "menu"), exist_ok=True)
        m3 = host(menu_bits, game_dir=bare, games=[], preview_mode=False,
                  menu_config={"game_exe": "nope.exe"})
        check("no game and no installer -> no button", m3.disc_installer(), "")

        m4 = host(menu_bits, game_dir=disc, games=[], preview_mode=True,
                  menu_config={"game_exe": "nope.exe"})
        check("preview never turns into an installer", m4.disc_installer(), "")

        ok("every language can say INSTALL", menu_src.count('"install": "') == 34)
        ok("and explain it", menu_src.count('"tip_install": "') == 34)

        # --------------------------------------------------------------
        print("5. the mod tool is never mistaken for the game")
        # Caused by fixing 1: once mod-maker/ reached the disc root, the
        # fallback scan picked "MyGame Mod Maker.exe" as the biggest candidate,
        # so PLAY - and Compatibility Mode - would have started the mod tool,
        # and the INSTALL button never appeared because a "game" was found.
        discroot = os.path.join(base, "discroot")
        os.makedirs(os.path.join(discroot, "menu"), exist_ok=True)
        touch(discroot, "setup.exe")
        touch(discroot, "mod-maker", "Windows x86_64", "MyGame Mod Maker.exe")
        touch(discroot, "bonus", "wallpapers", "one.png")

        cfg = {"game_exe": "game/Windows x86_64 Portable/MyGame.exe",
               "mod_exe": "mod-maker/Windows x86_64/MyGame Mod Maker.exe",
               "mod_launcher": True}
        m5 = host(menu_bits, game_dir=discroot, games=[], preview_mode=False,
                  menu_config=cfg)
        found, _ = m5.find_game_exe()
        check("the mod tool is not offered as the game", found, None)
        check("so the disc offers INSTALL instead",
              os.path.basename(m5.disc_installer()), "setup.exe")

        # A folder genuinely called mods was always skipped; keep it that way,
        # on its own root so the mod-maker case above cannot answer for it.
        plain = os.path.join(base, "plainmods")
        os.makedirs(plain, exist_ok=True)
        touch(plain, "mods", "ModOrganizer.exe")
        m6 = host(menu_bits, game_dir=plain, games=[], preview_mode=False,
                  menu_config={"game_exe": "nope.exe"})
        check("a folder called mods is skipped even with no config",
              m6.find_game_exe()[0], None)

        # And the real game still wins once it is actually there.
        touch(discroot, "game", "Windows x86_64 Portable", "MyGame.exe")
        m7 = host(menu_bits, game_dir=discroot, games=[], preview_mode=False,
                  menu_config=cfg)
        check("the real game is found when present",
              os.path.basename(m7.find_game_exe()[0]), "MyGame.exe")
        check("and then there is no installer button", m7.disc_installer(), "")

        # Multi-game disc, install-first: a chooser onto games that are all
        # missing is worse than an INSTALL button.
        multi = os.path.join(base, "multi")
        os.makedirs(multi, exist_ok=True)
        touch(multi, "setup.exe")
        m8 = host(menu_bits, game_dir=multi, preview_mode=False,
                  games=[{"name": "One", "exe": "one.exe"},
                         {"name": "Two", "exe": "two.exe"}],
                  menu_config={})
        check("a multi-game disc with nothing installed offers INSTALL",
              os.path.basename(m8.disc_installer()), "setup.exe")
        touch(multi, "one.exe")
        m9 = host(menu_bits, game_dir=multi, preview_mode=False,
                  games=[{"name": "One", "exe": "one.exe"},
                         {"name": "Two", "exe": "two.exe"}],
                  menu_config={})
        check("but one that resolves keeps the chooser", m9.disc_installer(), "")

    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    if failures:
        print("FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("all real-disc findings pinned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
