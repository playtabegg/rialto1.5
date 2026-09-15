"""A game copy that fails halfway stops the build instead of making a disc from part of a game.

copy_game_files_to_output used to catch the error, log one line and return
False, and build_all carried on: the installer and the ISO were built from
whatever had been copied so far, and the run still ended in Build complete.
Now the error is raised, and build_all's own failure path stops the build.

Source-extracted and exec'd on a stub object: no tkinter, no PyQt5.
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + detail) if detail else ""))
    if not cond:
        failures.append(label)


def method(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(src, item))
    raise SystemExit("could not extract " + name)


def host(method_src, shutil_module):
    ns = {"os": os, "shutil": shutil_module}
    exec("class Host:\n" + textwrap.indent(method_src, "    "), ns)
    h = ns["Host"]()
    h.log = []
    h.update_status = h.log.append
    return h


class FullDiskShutil:
    """shutil as it behaves when the drive fills up in the middle of a folder."""

    copy2 = staticmethod(shutil.copy2)

    @staticmethod
    def copytree(*args, **kwargs):
        raise OSError(28, "No space left on device")


def main():
    with open(RIALTO, encoding="utf-8") as fh:
        src = fh.read()
    copy_src = method(src, "copy_game_files_to_output")

    base = tempfile.mkdtemp(prefix="rialto_copyfail_")
    try:
        game = os.path.join(base, "input", "MyGame")
        os.makedirs(os.path.join(game, "Data"))
        with open(os.path.join(game, "MyGame.exe"), "wb") as fh:
            fh.write(b"MZ" + b"\0" * 64)
        with open(os.path.join(game, "Data", "level1.pak"), "wb") as fh:
            fh.write(b"\1" * 128)

        good_out = os.path.join(base, "output", "good")
        os.makedirs(good_out)
        h = host(copy_src, shutil)
        ok("a clean copy still returns True", h.copy_game_files_to_output(game, good_out) is True)
        ok("and copies every file",
           os.path.isfile(os.path.join(good_out, "MyGame.exe"))
           and os.path.isfile(os.path.join(good_out, "Data", "level1.pak")))

        bad_out = os.path.join(base, "output", "bad")
        os.makedirs(bad_out)
        h = host(copy_src, FullDiskShutil)
        raised = None
        try:
            h.copy_game_files_to_output(game, bad_out)
        except Exception as error:  # the behaviour under test
            raised = error
        ok("a copy that fails halfway raises instead of returning False", raised is not None, repr(raised))
        ok("the error says the build was stopped", raised is not None and "build was stopped" in str(raised), str(raised))
        ok("the status log still says what failed", any("Failed to copy game files" in line for line in h.log))

        build = ast.parse(method(src, "build_all"))
        guarded = False
        for node in ast.walk(build):
            if isinstance(node, ast.Try) and node.handlers:
                body = ast.Module(body=node.body, type_ignores=[])
                if any(isinstance(inner, ast.Attribute) and inner.attr == "copy_game_files_to_output"
                       for inner in ast.walk(body)):
                    guarded = True
        ok("build_all makes the copy inside the try that reports Build failed", guarded)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        sys.exit(1)
    print("a failed game copy stops the build.")


if __name__ == "__main__":
    main()
