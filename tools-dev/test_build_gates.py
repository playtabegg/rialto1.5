"""The build's two gates: where the game may live, and what happens with no installer.

run_preflight_check used to insist the game sat in input\\<title without
spaces>, so a game Browsed to anywhere else, or imported from GOG under a
different folder name, could not be built, although Rialto says a game can
live anywhere. It now checks the folder Browse picked.

compile_installer_with_iscc used to log "ISCC.exe not found" and carry on, so
the build ended in Build complete with a disc that had no installer on it. It
now raises, and build_all's own failure path stops the build.

Source-extracted and exec'd on a stub object: no tkinter, no PyQt5, no ISCC.
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

failures = []


def ok(label, cond, detail=""):
    shown = (" -> " + ascii(detail)) if (detail and not cond) else ""
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, shown))
    if not cond:
        failures.append(label)


def method(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(src, item))
    raise SystemExit("could not extract " + name)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def host(method_src, **names):
    ns = {"os": os, "INNO_SETUP_DOWNLOAD": "https://jrsoftware.org/isdl.php",
          "missing_tool_refusals": lambda pressed, image_needed=True: [],
          "OUTPUT_DIR": os.path.join(tempfile.gettempdir(), "rialto_gates_never_here")}
    ns.update(names)
    exec("class Host:\n" + textwrap.indent(method_src, "    "), ns)
    h = ns["Host"]()
    h.log = []
    h.popups = []
    h.update_status = h.log.append
    h.show_centered_popup = lambda title, message, **kw: h.popups.append((title, message)) or True
    # An ordinary disc; the pressed checks have their own harness (test_pressed_disc.py).
    h.pressed_disc_on = lambda: False
    return h


def main():
    with open(RIALTO, encoding="utf-8") as fh:
        src = fh.read()

    base = tempfile.mkdtemp(prefix="rialto_gates_")
    try:
        print("1. the pre-build check")
        preflight = method(src, "run_preflight_check")
        elsewhere = os.path.join(base, "D", "My Projects", "sky-quest-build")
        os.makedirs(elsewhere)
        art = os.path.join(base, "art")
        os.makedirs(art)
        background = os.path.join(art, "background.gif")
        icon = os.path.join(art, "game_icon.ico")
        for path in (background, icon):
            with open(path, "wb") as fh:
                fh.write(b"x")
        entries = {"Title": Var("Sky Quest"), "Developer": Var("Your Studio"), "Start Menu Name": Var("Sky Quest")}
        input_dir = os.path.join(base, "Rialto", "input")
        os.makedirs(input_dir)

        h = host(preflight, INPUT_DIR=input_dir)
        h.entries, h.bg_path_var, h.ico_path_var = entries, Var(background), Var(icon)
        h.current_game_path = elsewhere
        ok("a game folder outside input\\ and not named after the title passes", h.run_preflight_check() is True,
           h.popups[-1] if h.popups else "")

        h = host(preflight, INPUT_DIR=input_dir)
        h.entries, h.bg_path_var, h.ico_path_var = entries, Var(background), Var(icon)
        h.current_game_path = None
        ok("no game folder chosen fails", h.run_preflight_check() is False)
        ok("and says to choose one", bool(h.popups) and "Choose your game folder" in h.popups[-1][1],
           h.popups[-1] if h.popups else "")

        # 1.5.1: a drive root has no name, so its build folder would be output\
        # itself, and the clean-up would take every other game's build with it.
        h = host(preflight, INPUT_DIR=input_dir)
        h.entries, h.bg_path_var, h.ico_path_var = entries, Var(background), Var(icon)
        h.current_game_path = os.path.splitdrive(base)[0] + "\\"
        ok("a drive root as the game folder fails", h.run_preflight_check() is False)
        ok("and says to give the game a folder of its own",
           bool(h.popups) and "folder of its own" in h.popups[-1][1], h.popups[-1] if h.popups else "")

        h = host(preflight, INPUT_DIR=input_dir)
        h.entries, h.bg_path_var, h.ico_path_var = entries, Var(os.path.join(art, "gone.gif")), Var(icon)
        h.current_game_path = elsewhere
        ok("a missing background still fails", h.run_preflight_check() is False)
        ok("and names it plainly, not background.jpg",
           bool(h.popups) and "Missing menu background" in h.popups[-1][1] and "background.jpg" not in h.popups[-1][1],
           h.popups[-1] if h.popups else "")

        # 1.5.1 (B12.2): a missing tool is refused here, before anything is copied, in one sentence.
        refusal = "No installer compiler: Inno Setup is not on this PC and this copy of Rialto does not carry one."
        h = host(preflight, INPUT_DIR=input_dir, missing_tool_refusals=lambda pressed, image_needed=True: [refusal])
        h.entries, h.bg_path_var, h.ico_path_var = entries, Var(background), Var(icon)
        h.current_game_path = elsewhere
        ok("no installer compiler, installed or carried: refused before the build", h.run_preflight_check() is False)
        ok("and says what to do, in its own sentence", bool(h.popups) and refusal in h.popups[-1][1],
           h.popups[-1] if h.popups else "")

        print("2. no installer, no disc")
        compile_src = method(src, "compile_installer_with_iscc")

        words_src = ast.get_source_segment(src, next(n for n in ast.parse(src).body
                                                     if isinstance(n, ast.FunctionDef) and n.name == 'tool_words'))
        words_ns = {'CARRIED_INNO_VERSION': '6.5.4'}
        exec(words_src, words_ns)

        def run_compile(iscc, seven_only, runner=None, carried=False):
            out = os.path.join(base, "out-%d" % len(os.listdir(base)))
            os.makedirs(out)
            fake_subprocess = types.SimpleNamespace(run=runner or (lambda *a, **k: None),
                                                    TimeoutExpired=TimeoutError)
            h = host(compile_src, subprocess=fake_subprocess,
                     find_inno_compiler=lambda: iscc, inno_setup_7_only=lambda: seven_only,
                     installer_compiler=lambda: (iscc, carried), tool_words=words_ns['tool_words'],
                     _inno_setup_major=lambda path: 7 if "Inno Setup 7" in str(path) else 6)
            h.sign_final_build = Var(False)
            # ISCC runs watched since 1.5.1 (B6); here the watch is the fake run itself.
            h.tree_size = lambda path, skip_ext=(".iso",): (0, 0)
            h.run_tool_watched = lambda command, cwd, timeout, step, on_line=None, watch=None: \
                fake_subprocess.run(command, cwd=cwd)
            raised = None
            try:
                h.compile_installer_with_iscc(out)
            except RuntimeError as error:
                raised = error
            return h, raised, out

        h, raised, _ = run_compile(None, False)
        ok("no Inno Setup 6: the build is stopped", raised is not None and "build was stopped" in str(raised), raised)
        ok("and the log says ISCC.exe not found", any("ISCC.exe not found" in line for line in h.log), h.log)


        def failing(command, cwd=None, **kwargs):
            return types.SimpleNamespace(returncode=2, stderr="Error on line 12", stdout="")

        h, raised, _ = run_compile(r"C:\Inno Setup 6\ISCC.exe", False, failing)
        ok("ISCC fails: the build is stopped", raised is not None, raised)
        ok("and the log carries ISCC's error", any("ISCC failed" in line for line in h.log), h.log)

        def working(command, cwd=None, **kwargs):
            with open(os.path.join(cwd, "setup.exe"), "wb") as fh:
                fh.write(b"MZ")
            return types.SimpleNamespace(returncode=0, stderr="", stdout="")

        h, raised, out = run_compile(r"C:\Inno Setup 6\ISCC.exe", False, working)
        ok("ISCC makes setup.exe: the build carries on", raised is None, raised)
        ok("and the installer step is reported done", any("Installer step done" in line for line in h.log), h.log)

        # 1.5.1 (B4): with only Inno Setup 7 installed, find_inno_compiler hands
        # back its ISCC and the build goes on, saying which compiler it used.
        h, raised, out = run_compile(r"C:\Program Files\Inno Setup 7\ISCC.exe", True, working)
        ok("only Inno Setup 7: the build carries on with it", raised is None, raised)
        ok("and says so", any("with Inno Setup 7" in line for line in h.log), h.log)

        # 1.5.1: with no Inno Setup on the PC, the one Rialto carries builds the installer, and the log says so.
        h, raised, out = run_compile('C:/Temp/_MEI42/helpers/inno/ISCC.exe', False, working, carried=True)
        ok('no Inno Setup on the PC: the carried one builds the installer', raised is None, raised)
        ok('and the log names it plainly',
           any('with the Inno Setup 6.5.4 that comes with Rialto' in line for line in h.log), h.log)

        build = ast.parse(method(src, "build_all"))
        guarded = False
        for node in ast.walk(build):
            if isinstance(node, ast.Try) and node.handlers:
                body = ast.Module(body=node.body, type_ignores=[])
                if any(isinstance(inner, ast.Attribute) and inner.attr == "compile_installer_with_iscc"
                       for inner in ast.walk(body)):
                    handler = ast.unparse(node.handlers[0])
                    guarded = "Build failed" in handler
        ok("build_all compiles the installer inside the try that reports Build failed", guarded)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        sys.exit(1)
    print("the game folder can live anywhere, and a build with no installer stops.")


if __name__ == "__main__":
    main()
