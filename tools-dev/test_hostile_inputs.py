"""Hand Rialto the worst game folder and the worst title a stranger could have.

Rialto is an open-source tool: the next folder it is pointed at belongs to
somebody nobody here has met, and the title in the box is whatever they typed.
Neither has to be reasonable. This harness feeds both the shapes that are
merely awkward (empty folder, no exe at all, one file 40 GB long) and the ones
that are actively hostile (a title that is "..", a title that is a device name,
a title in Hebrew, a title 400 characters long).

The bar is not "produces something pretty". It is:

  * never raise out of a build helper,
  * never produce a path that leaves the folder it was given,
  * never emit a script line the author did not write,
  * and where the input genuinely cannot be used, say so with a value the
    caller can act on rather than a crash or a silent empty disc.

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


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label,
                           (" -> " + detail) if detail else ""))
    if not cond:
        failures.append(label + ((" -> " + detail) if detail else ""))


def module_bits(src, names):
    out, got = [], set()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            got.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out.append(ast.get_source_segment(src, node))
                    got.add(t.id)
    missing = set(names) - got
    if missing:
        raise SystemExit("could not extract %s" % sorted(missing))
    return "\n\n".join(out)


def methods(src, cls, names):
    out, got = [], set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                nm = getattr(item, "name", None)
                if nm is None and isinstance(item, ast.Assign):
                    nm = getattr(item.targets[0], "id", None)
                if nm in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(nm)
    missing = set(names) - got
    if missing:
        raise SystemExit("could not extract %s.%s" % (cls, sorted(missing)))
    return "\n\n".join(out)


def host(method_src, globals_=None, **attrs):
    ns = {"os": os, "sys": sys, "shutil": shutil, "json": __import__("json")}
    ns.update(globals_ or {})
    exec("class Host:\n" + textwrap.indent(method_src, "    "), ns)
    h = ns["Host"]()
    h.update_status = lambda m: None
    for k, v in attrs.items():
        setattr(h, k, v)
    return h


class Flag:
    def __init__(self, v):
        self._v = v

    def get(self):
        return self._v


# Every one of these has bitten a real Windows program at some point.
HOSTILE_TITLES = [
    ("empty", ""),
    ("only spaces", "     "),
    ("a single dot", "."),
    ("parent directory", ".."),
    ("traversal", "../../Windows/System32"),
    ("absolute path", "C:\\Windows\\System32"),
    ("UNC path", "\\\\evil-server\\share"),
    ("device name CON", "CON"),
    ("device name NUL", "NUL"),
    ("device name COM1", "COM1"),
    ("device with extension", "PRN.txt"),
    ("filename metacharacters", 'a<b>c:d"e/f\\g|h?i*j'),
    ("trailing dot", "Game."),
    ("trailing space", "Game "),
    ("batch metacharacters", "a&b|c>d<e^f(g)h"),
    ("percent expansion", "%USERPROFILE%"),
    ("delayed expansion", "!USERPROFILE!"),
    ("newline", "Game\r\nformat C:"),
    ("NUL byte", "Game\x00hidden"),
    ("tab", "Game\tTabbed"),
    ("Japanese", "\u30b2\u30fc\u30e0"),
    ("Hebrew (RTL)", "\u05de\u05e9\u05d7\u05e7"),
    ("Arabic (RTL)", "\u0644\u0639\u0628\u0629"),
    ("emoji", "Game \U0001f680\U0001f3ae"),
    ("combining marks", "Ame\u0301lie"),
    ("zero width", "Ga\u200bme"),
    ("right-to-left override", "Game\u202eexe.txt"),
    ("400 characters", "L" * 400),
    ("quotes", 'He said "hi" and \'bye\''),
    ("only punctuation", "!@#$%^&*()"),
    ("SQL-ish", "'; DROP TABLE games;--"),
    ("html", "<script>alert(1)</script>"),
]


def main():
    src = open(RIALTO, encoding="utf-8").read()
    menu_src = extract_menu_source(RIALTO)
    base = tempfile.mkdtemp(prefix="rialto_hostile_")
    try:
        # ==============================================================
        print("1. a hostile title never becomes a hostile path or script")
        ns = {"os": os, "sys": sys, "re": __import__("re")}
        exec(module_bits(src, ["_CONTROL_CHARS", "_ISS_META", "_ISS_PATH_META",
                               "_WINDOWS_RESERVED", "sanitize_text", "iss_value",
                               "escape_batch", "split_launch_args"]), ns)
        sanitize, iss_value = ns["sanitize_text"], ns["iss_value"]
        escape_batch = ns["escape_batch"]

        bad_path_chars = set('<>:"/\\|?*')
        devices = {"con", "prn", "aux", "nul", "com1", "com2", "lpt1", "lpt2"}

        for label, title in HOSTILE_TITLES:
            # sanitize_text: no control characters survive, ever.
            clean = sanitize(title)
            ok("%-24s | no control chars survive sanitising" % label,
               not any(c < " " or c == "\x7f" for c in clean))

            # iss_value for a PATH must be usable as a folder name: no
            # separators, no device names, never empty, never "." or "..".
            path_value = iss_value(title, for_path=True)
            ok("%-24s | path value is a safe folder name" % label,
               bool(path_value)
               and not (bad_path_chars & set(path_value))
               and path_value not in (".", "..")
               and path_value.split(".")[0].lower() not in devices
               and not path_value.endswith((".", " ")),
               repr(path_value[:40]))

            # iss_value for a plain field must not break out of its line.
            field = iss_value(title)
            ok("%-24s | .iss field stays on one line" % label,
               "\n" not in field and "\r" not in field and bool(field))

            # A batch file must gain no new lines and no live expansion.
            batched = escape_batch(title)
            ok("%-24s | batch value injects nothing" % label,
               "\n" not in batched and "\r" not in batched
               and "%" not in batched.replace("%%", "")
               and "!" not in batched,
               repr(batched[:40]))

        # The two that actually reached a disc before the hardening fixed them.
        ok("a title of '..' cannot redirect the install folder",
           iss_value("..", for_path=True) not in ("", ".", ".."))
        ok("a title of '.' cannot either",
           iss_value(".", for_path=True) not in ("", ".", ".."))

        # ==============================================================
        print("2. the disc menu survives the same titles")
        # MENU_TITLE is computed at import from whatever the config holds.
        title_src = []
        for node in ast.parse(menu_src).body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if names and names[0] in ("_raw_title", "MENU_TITLE"):
                    title_src.append(ast.get_source_segment(menu_src, node))
        for label, title in HOSTILE_TITLES:
            tns = {"MENU_CONFIG": {"title": title}}
            exec("\n".join(title_src), tns)
            shown = tns["MENU_TITLE"]
            ok("%-24s | menu title is printable and bounded" % label,
               isinstance(shown, str) and shown
               and not any(c < " " or c == "\x7f" for c in shown)
               and len(shown) <= 200,
               repr(shown[:30]))

        # ==============================================================
        print("3. degenerate game folders are refused, not crashed on")
        detect_src = methods(src, "RialtoApp",
                             ["detect_primary_game_exe", "HELPER_EXE_NAMES",
                              "NON_GAME_DIRS", "_name_key", "_title_key"])
        menu_scan = methods(menu_src, "GameMenu",
                            ["find_game_exe", "_configured_exe", "_inside_game_dir",
                             "_is_helper_exe", "_is_reparse_point", "HELPER_EXES"])

        def make(name, build):
            """Build a fixture, or None if Windows itself will not have it."""
            root = os.path.join(base, name)
            os.makedirs(root, exist_ok=True)
            try:
                build(root)
            except OSError as e:
                print("  [SKIP] %-20s | Windows refuses this shape: %s" % (name, e))
                return None
            return root

        def touch(root, rel, data=b"x"):
            p = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)

        shapes = {
            "empty folder": lambda r: None,
            "no exe anywhere": lambda r: (touch(r, "readme.txt"), touch(r, "data/pack.bin")),
            "only helper exes": lambda r: (touch(r, "vcredist_x64.exe"),
                                           touch(r, "unins000.exe"),
                                           touch(r, "UnityCrashHandler64.exe")),
            "zero byte exe": lambda r: touch(r, "Game.exe", b""),
            "exe in a deep tree": lambda r: touch(r, "a/b/c/d/e/f/g/Deep.exe"),
            "unicode filenames": lambda r: touch(r, "\u30b2\u30fc\u30e0.exe"),
            "spaces in names": lambda r: touch(r, "odd folder/My  Game .exe"),
            "case collision": lambda r: (touch(r, "Game.exe"), touch(r, "data/GAME.EXE")),
            "dot folders": lambda r: touch(r, ".hidden/Secret.exe"),
            "very long name": lambda r: touch(r, ("n" * 120) + ".exe"),
        }

        for name, build in shapes.items():
            root = make(name.replace(" ", "_"), build)
            if root is None:
                continue
            try:
                b = host(detect_src, entries={"Title": Flag("Whatever")})
                detected = b.detect_primary_game_exe(root)
                raised = ""
            except Exception as e:
                detected, raised = None, "%s: %s" % (type(e).__name__, e)
            ok("%-20s | detection does not raise" % name, not raised, raised)
            if not raised:
                ok("%-20s | returns a string, never None" % name,
                   isinstance(detected, str), repr(detected))
                if detected:
                    full = os.path.realpath(os.path.join(root, detected))
                    ok("%-20s | stays inside the game folder" % name,
                       os.path.commonpath([os.path.realpath(root), full])
                       == os.path.realpath(root))

            try:
                m = host(menu_scan, game_dir=root, games=[],
                         menu_config={"game_exe": detected or ""})
                found, searched = m.find_game_exe()
                raised = ""
            except Exception as e:
                found, raised = None, "%s: %s" % (type(e).__name__, e)
            ok("%-20s | the menu's scan does not raise" % name, not raised, raised)
            if not raised and found:
                ok("%-20s | menu pick stays inside too" % name,
                   os.path.commonpath([os.path.realpath(root),
                                       os.path.realpath(found)])
                   == os.path.realpath(root))

        # A folder that is not a folder at all.
        not_a_dir = os.path.join(base, "actually_a_file")
        with open(not_a_dir, "wb") as f:
            f.write(b"x")
        b = host(detect_src, entries={"Title": Flag("X")})
        ok("a file where a folder should be is refused",
           b.detect_primary_game_exe(not_a_dir) == "")
        ok("a path that does not exist is refused",
           b.detect_primary_game_exe(os.path.join(base, "nope")) == "")
        ok("an empty path is refused", b.detect_primary_game_exe("") == "")

        # ==============================================================
        print("4. the fileset and the mod scan hold up too")
        fileset_src = methods(src, "RialtoApp",
                              ["_collect_disc_fileset", "default_mod_dir",
                               "resolved_mod_dir", "staged_mod_dir_name"])
        for name in list(shapes) + ["empty folder"]:
            root = os.path.join(base, name.replace(" ", "_"))
            if not os.path.isdir(root):
                continue
            try:
                f = host(fileset_src, mod_launcher_var=Flag(True),
                         mod_folder_var=Flag(""), current_game_path=root)
                items = f._collect_disc_fileset(root)
                raised = ""
            except Exception as e:
                items, raised = None, "%s: %s" % (type(e).__name__, e)
            ok("%-20s | fileset does not raise" % name, not raised, raised)
            if not raised:
                ok("%-20s | every item really exists" % name,
                   all(os.path.exists(os.path.join(root, i)) for i in items))

        mod_src = methods(src, "RialtoApp",
                          ["detect_mod_launcher_exe", "default_mod_dir",
                           "resolved_mod_dir", "staged_mod_dir_name"])
        empty = os.path.join(base, "empty_folder")
        m = host(mod_src, mod_folder_var=Flag(""), current_game_path=empty)
        ok("no mod folder anywhere returns nothing, not a guess",
           m.detect_mod_launcher_exe(empty) == "")
        m2 = host(mod_src, mod_folder_var=Flag(os.path.join(base, "does-not-exist")),
                  current_game_path=empty)
        ok("a mod folder that vanished returns nothing",
           m2.detect_mod_launcher_exe(empty) == "")

    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    if failures:
        print("FAILED (%d):" % len(failures))
        for f in failures[:40]:
            print("  - " + f)
        return 1
    print("every hostile title and degenerate folder handled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
