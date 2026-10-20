"""No console window, ever (1.5.1, launch day).

Rialto.exe is a windowed program. A console program it starts (ISCC, oscdimg, mkisofs, cmd,
PowerShell, signtool) opens a black window of its own unless it is started with
CREATE_NO_WINDOW: in 1.5.0 ISCC sat in one for a whole build, and in 1.5.1 a "cmd /c ie4uinit"
flashed one at the end of every build. This reads every call that starts a process in
Rialto.pyw (outside the disc menu's source) and in rialto/, and holds each to the flag, except
the few that start a windowed program, which are named here with the reason.

Source-extracted: nothing is run.
"""
import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

STARTERS = {"run", "Popen", "call", "check_call", "check_output"}
# (file, function): why a call there may start without the flag
WINDOWED = {
    ("Rialto.pyw", "preview_disc_menu"): "starts menu.exe (a windowed program), or the menu's source with this Python",
    ("Rialto.pyw", "burn_to_master"): "starts ImgBurn, a windowed program",
}
# (file, function, call): one named call, where a whole function would hide too much
NAMED_CALLS = {
    ("Rialto.pyw", "<module>", "os.execv"): "a source checkout restarting itself after its first-run install; "
                                             "never reached in Rialto.exe",
}


def calls(path, label):
    tree = ast.parse(open(path, encoding="utf-8").read())
    found = []
    assigned = {t.id: n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}

    def visit(node, function):
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.Call):
                f = child.func
                attr = f.attr if isinstance(f, ast.Attribute) else None
                owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
                if attr in STARTERS and owner == "subprocess":
                    flags = next((k.value for k in child.keywords if k.arg == "creationflags"), None)
                    if isinstance(flags, ast.Name):
                        # creationflags=flags: the name's own assignment in this file decides
                        flags = assigned.get(flags.id, flags)
                    flagged = flags is not None and "CREATE_NO_WINDOW" in ast.dump(flags)
                    found.append((label, function or "<module>", child.lineno, attr, flagged))
                if isinstance(f, ast.Attribute) and owner == "os" and (
                        f.attr in ("system", "popen") or f.attr.startswith(("spawn", "exec"))):
                    found.append((label, function or "<module>", child.lineno, "os." + f.attr, False))
            if isinstance(child, ast.ImportFrom) and child.module == "subprocess":
                # "from subprocess import Popen" would hide a call from the check above
                found.append((label, function or "<module>", child.lineno, "from subprocess import", False))
            visit(child, name)

    visit(tree, None)
    return found


def main():
    found = calls(RIALTO, "Rialto.pyw")
    for path in sorted(glob.glob(os.path.join(REPO, "rialto", "**", "*.py"), recursive=True)):
        found += calls(path, os.path.relpath(path, REPO).replace("\\", "/"))
    bad = [c for c in found if not c[4] and (c[0], c[1]) not in WINDOWED and (c[0], c[1], c[3]) not in NAMED_CALLS]
    print("every call that starts a process: %d, with CREATE_NO_WINDOW: %d, windowed by name: %d"
          % (len(found), sum(1 for c in found if c[4]), sum(1 for c in found if not c[4] and (c[0], c[1]) in WINDOWED)))
    for label, function, line, how, _flagged in bad:
        print("  [FAIL] %s:%d in %s(): subprocess.%s without CREATE_NO_WINDOW (a console program opens a black window)"
              % (label, line, function, how))
    unused = [key for key in WINDOWED if not any((c[0], c[1]) == key for c in found)]
    for key in unused:
        print("  [FAIL] the windowed exception %s:%s() no longer starts anything: take it off the list" % key)
    src = open(RIALTO, encoding="utf-8").read()
    ok_ie = '"cmd", "/c"' not in src.split("MENU_TEMPLATE_SOURCE = '''")[0] and "ie4uinit.exe\", \"-show\"" not in src
    print("  [%s] the icon refresh runs ie4uinit.exe itself, never through cmd" % ("OK  " if ok_ie else "FAIL"))
    if bad or unused or not ok_ie:
        print("\nFAILED")
        return 1
    print("\nNo console window: every console program Rialto starts is started hidden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
