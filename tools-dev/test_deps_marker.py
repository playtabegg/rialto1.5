"""Exercise the first-run / upgrade dependency check at the top of Rialto.pyw.

"Are the dependencies installed?" used to mean "does Pillow import?", which
answers the first-run question and gets the upgrade one wrong: adding a package
to requirements.txt left every existing copy of Rialto starting happily without
it. The check now keys on a hash of requirements.txt.

The whole block runs here for real - the module-level helpers and the branching
around them are pulled straight out of Rialto.pyw and executed against temp
folders, with pip and the tkinter dialogs replaced by recorders. Nothing is
paraphrased, so a change to the real logic shows up as a failure here.

Usage: python tools-dev/test_deps_marker.py [path-to-rialto1.5]
"""
import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
import types

REPO = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = os.path.join(REPO, "Rialto.pyw")

failures = []


def check(label, got, want):
    good = got == want
    print(f"  [{'OK  ' if good else 'FAIL'}] {label}: {got!r}")
    if not good:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def ok(label, cond, detail=""):
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}{(' -> ' + detail) if detail else ''}")
    if not cond:
        failures.append(label)


SRC = open(RIALTO, encoding="utf-8").read()
TREE = ast.parse(SRC)

HELPERS = ["_requirements_fingerprint", "_deps_already_attempted",
           "_write_deps_marker", "_install_requirements"]


def helper_source():
    out, seen = [], set()
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name in HELPERS:
            out.append(ast.get_source_segment(SRC, node))
            seen.add(node.name)
    missing = set(HELPERS) - seen
    if missing:
        raise SystemExit(f"could not extract {sorted(missing)}")
    return "\n\n".join(out)


def branch_source():
    """The `if _FROZEN: ... else: ...` block that drives the helpers."""
    for node in TREE.body:
        if isinstance(node, ast.If) and ast.unparse(node.test) == "_FROZEN":
            return ast.get_source_segment(SRC, node)
    raise SystemExit("the frozen/source dependency branch is gone")


HELPER_SRC = helper_source()
BRANCH_SRC = branch_source()


class Run:
    """One simulated Rialto startup."""

    def __init__(self, folder, requirements, frozen=False, pillow=True,
                 pip_succeeds=True, answer_yes=True, pip_unstartable=False):
        self.folder = folder
        self.pip_calls = []
        self.dialogs = []
        self.execv = []
        self.pip_succeeds = pip_succeeds
        self.pip_unstartable = pip_unstartable
        self.requirements = requirements

        if requirements is not None:
            # newline="" so Windows does not silently turn the \n into \r\n and
            # change the bytes the fingerprint is taken over.
            with open(os.path.join(folder, "requirements.txt"), "w",
                      encoding="utf-8", newline="") as f:
                f.write(requirements)

        pil = types.ModuleType("PIL")
        pil.Image = object()
        pil.ImageTk = object()

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "PIL":
                if not pillow:
                    raise ImportError("no PIL here")
                return pil
            return __import__(name, globals, locals, fromlist, level)

        def fake_run(argv, **kwargs):
            self.pip_calls.append(list(argv))
            if self.pip_unstartable:
                # CreateProcess refused outright. An antivirus or EDR policy that
                # will not let Python spawn children is the everyday version.
                raise OSError(5, "Access is denied")
            return types.SimpleNamespace(
                returncode=0 if self.pip_succeeds else 1, stdout="", stderr="boom")

        messagebox = types.SimpleNamespace(
            askyesno=lambda *a: (self.dialogs.append(("ask", a[0])), answer_yes)[1],
            showinfo=lambda *a: self.dialogs.append(("info", a[0])),
            showerror=lambda *a: self.dialogs.append(("error", a[0])),
        )
        tk = types.SimpleNamespace(
            Tk=lambda: types.SimpleNamespace(withdraw=lambda: None,
                                             destroy=lambda: None))

        fake_sys = types.SimpleNamespace(executable="C:\\Python\\python.exe",
                                         argv=["Rialto.pyw"])
        if frozen:
            fake_sys.frozen = True

        fake_os = types.SimpleNamespace(
            path=os.path, sep=os.sep,
            execv=lambda exe, argv: self.execv.append((exe, list(argv))))

        self.ns = {
            "os": fake_os, "sys": fake_sys, "json": json, "hashlib": hashlib,
            "subprocess": types.SimpleNamespace(run=fake_run, CREATE_NO_WINDOW=0x08000000),
            "tk": tk, "messagebox": messagebox,
            "__file__": os.path.join(folder, "Rialto.pyw"),
            "__import__": fake_import,
            "__builtins__": dict(vars(__builtins__) if not isinstance(__builtins__, dict)
                                 else __builtins__, __import__=fake_import),
        }

    def start(self):
        preamble = (
            "_FROZEN = getattr(sys, 'frozen', False)\n"
            "_APP_DIR = os.path.dirname(os.path.abspath(__file__))\n"
            "_requirements = os.path.join(_APP_DIR, 'requirements.txt')\n"
            "_DEPS_MARKER = os.path.join(_APP_DIR, '.deps_installed')\n"
        )
        self.escaped = None
        try:
            exec(preamble + HELPER_SRC + "\n" + BRANCH_SRC, self.ns)
        except SystemExit as e:
            self.exit_code = e.code
        except Exception as e:
            # Anything other than a deliberate SystemExit escaping here is a
            # windowless Rialto that simply never opens. Recorded, not raised,
            # so the assertion below reads as a failure instead of a traceback.
            self.exit_code = None
            self.escaped = e
        else:
            self.exit_code = None
        return self

    @property
    def marker(self):
        try:
            with open(os.path.join(self.folder, ".deps_installed"),
                      encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None


def fresh(**kwargs):
    folder = tempfile.mkdtemp(prefix="rialto_deps_")
    return Run(folder, **kwargs), folder


REQ_A = "pillow\nPyQt5\n"
REQ_B = "pillow\nPyQt5\npywin32\n"
SHA_A = hashlib.sha256(REQ_A.encode()).hexdigest()
SHA_B = hashlib.sha256(REQ_B.encode()).hexdigest()

stages = []
try:
    print("the upgrade case - the one that used to be silently wrong")
    run, folder = fresh(requirements=REQ_A)
    stages.append(folder)
    run.start()
    check("everything imports but no marker yet -> pip runs once",
          len(run.pip_calls), 1)
    check("and the marker records what was installed",
          run.marker, {"requirements_sha256": SHA_A, "installed": True})
    check("no dialog: this is a sync, not a first run", run.dialogs, [])

    run2 = Run(folder, requirements=REQ_A).start()
    check("second start with the same requirements -> pip is not run again",
          run2.pip_calls, [])

    run3 = Run(folder, requirements=REQ_B).start()
    check("a new package in requirements.txt -> pip runs", len(run3.pip_calls), 1)
    check("pip is pointed at the real requirements.txt",
          run3.pip_calls[0][-1], os.path.join(folder, "requirements.txt"))
    check("the marker follows the new hash", run3.marker["requirements_sha256"], SHA_B)

    run4 = Run(folder, requirements=REQ_B).start()
    check("and settles again", run4.pip_calls, [])
    print()

    print("a failed sync must not hang every future launch")
    run, folder = fresh(requirements=REQ_A, pip_succeeds=False)
    stages.append(folder)
    run.start()
    check("the failure is recorded, not swallowed",
          run.marker, {"requirements_sha256": SHA_A, "installed": False})
    check("Rialto still starts - it has what it needs to run", run.exit_code, None)
    again = Run(folder, requirements=REQ_A).start()
    check("offline, the next launch does not retry and does not stall",
          again.pip_calls, [])
    moved_on = Run(folder, requirements=REQ_B).start()
    check("but a further change to requirements.txt does try again",
          len(moved_on.pip_calls), 1)
    print()

    print("a sync that cannot even start pip must not stop Rialto opening")
    # The quiet sync runs at module import in a windowless .pyw. Anything that
    # escapes it is a double-click that does nothing at all, with no error
    # anywhere - which is the exact failure mode the whole launcher work was
    # about. An antivirus policy refusing to let Python spawn children is the
    # everyday way subprocess.run raises rather than returning a bad code.
    run, folder = fresh(requirements=REQ_A, pip_unstartable=True)
    stages.append(folder)
    run.start()
    check("nothing escapes module import", run.escaped, None)
    check("Rialto starts anyway", run.exit_code, None)
    check("pip was attempted", len(run.pip_calls), 1)
    check("and the attempt is recorded, so it is not retried every launch",
          run.marker, {"requirements_sha256": SHA_A, "installed": False})
    again = Run(folder, requirements=REQ_A).start()
    check("the next launch is quiet", again.pip_calls, [])
    print()

    print("first run - nothing installed at all")
    run, folder = fresh(requirements=REQ_A, pillow=False)
    stages.append(folder)
    run.start()
    check("the user is asked before anything is installed",
          [kind for kind, _ in run.dialogs][0], "ask")
    check("pip runs", len(run.pip_calls), 1)
    check("the marker is written so the next start is quiet",
          run.marker, {"requirements_sha256": SHA_A, "installed": True})
    check("and Rialto restarts itself into the new packages", len(run.execv), 1)

    run, folder = fresh(requirements=REQ_A, pillow=False, answer_yes=False)
    stages.append(folder)
    run.start()
    check("declining installs nothing", run.pip_calls, [])
    check("declining leaves no marker behind", run.marker, None)
    check("and stops rather than crashing later", run.exit_code, 1)

    run, folder = fresh(requirements=REQ_A, pillow=False, pip_succeeds=False)
    stages.append(folder)
    run.start()
    check("a failed first-run install reports the error",
          [kind for kind, _ in run.dialogs][-1], "error")
    check("no marker claims success", run.marker, None)
    check("and Rialto stops", run.exit_code, 1)
    print()

    print("edge cases")
    run, folder = fresh(requirements=None)
    stages.append(folder)
    run.start()
    check("no requirements.txt at all -> nothing runs, nothing breaks",
          (run.pip_calls, run.marker, run.exit_code), ([], None, None))

    run, folder = fresh(requirements=REQ_A)
    stages.append(folder)
    with open(os.path.join(folder, ".deps_installed"), "w", encoding="utf-8") as f:
        f.write("this is not json")
    run.start()
    check("a corrupt marker is treated as absent, not fatal", len(run.pip_calls), 1)
    check("and is replaced with a good one",
          run.marker["requirements_sha256"], SHA_A)

    run, folder = fresh(requirements=REQ_A, frozen=True)
    stages.append(folder)
    run.start()
    check("a frozen build never runs pip - sys.executable there is Rialto.exe",
          run.pip_calls, [])
    check("and writes no marker into the bundle", run.marker, None)
    print()
finally:
    for folder in stages:
        shutil.rmtree(folder, ignore_errors=True)

print("wiring")
ok("hashlib is imported at the top of Rialto.pyw",
   any(isinstance(n, ast.Import) and any(a.name == "hashlib" for a in n.names)
       for n in TREE.body))
ok("the marker is hidden and lives beside Rialto",
   "_DEPS_MARKER = os.path.join(_APP_DIR, \".deps_installed\")" in SRC)
ok(".deps_installed is gitignored",
   ".deps_installed" in open(os.path.join(REPO, ".gitignore"), encoding="utf-8").read())
print()

if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print("All dependency-marker assertions passed.")
