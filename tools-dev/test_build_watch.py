"""A build you can watch (1.5.1, B6).

The long steps used to block the window, which turned Not Responding with
nothing moving. They now run through run_tool_watched: the tool's output is
read on small threads, and the window's own thread moves the live line and
lets the window answer between reads. It hands back what subprocess.run did,
and stops a tool at the same timeouts.

Driven here with real fake tools (Python one-liners): one that prints slowly,
one that fails, one that hangs past its timeout. Also: the ISCC line parser,
written from what ISCC 6.5.4 actually printed; the live line's wording; the
guard against a second build; and no method defined twice in a class (B6's
first draft shadowed an older folder_bytes, and only a harness caught it).
"""
import ast
import collections
import os
import queue  # noqa: F401  (run_tool_watched imports it itself)
import shutil
import subprocess
import sys
import textwrap
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


src = open(RIALTO, encoding="utf-8").read()
tree = ast.parse(src)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
ns = {"os": os, "subprocess": subprocess, "time": time, "shutil": shutil, "re": __import__("re")}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in ("progress_text", "iscc_compressing_path"):
        exec(ast.get_source_segment(src, node), ns)
body = "\n\n".join(textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
                   if isinstance(i, ast.FunctionDef) and i.name in ("run_tool_watched", "counting_copy", "build_ticker",
                                                                     "watched_copytree", "run_watched_call", "tree_size"))
exec("class Host:\n" + textwrap.indent(body, "    "), ns)


class Watch(ns["Host"]):
    def __init__(self):
        self.lines, self.alive = [], 0

    def show_progress(self, step, fraction=None, seconds=0.0, detail=""):
        self.lines.append(ns["progress_text"](step, fraction, seconds, detail))

    def keep_window_alive(self):
        self.alive += 1

    def update_status(self, line):
        pass


PY = sys.executable

print("1. a tool that prints slowly: the window answers and the line moves")
h = Watch()
seen = []
slow = "import time\nfor i in range(5):\n    print('step', i, flush=True)\n    time.sleep(0.3)\n"
started = time.monotonic()
result = h.run_tool_watched([PY, "-c", slow], None, 30, "Testing",
                            on_line=lambda line: seen.append(line) or ((len(seen) / 5), "%d of 5" % len(seen)))
ok("hands back what subprocess.run would", result.returncode == 0 and result.stdout.count("step") == 5, result)
ok("every line reached on_line, in order", seen == ["step %d" % i for i in range(5)], seen)
ok("the window answered many times while it ran", h.alive >= 10, h.alive)
ok("the line moved with it", len(set(h.lines)) >= 3 and h.lines[-1].startswith("Testing: 5 of 5, 100%"), h.lines[-3:])
ok("and took about as long as the tool", time.monotonic() - started < 10)
print()

print("2. a tool that fails: its exit code and its words come back")
h = Watch()
result = h.run_tool_watched([PY, "-c", "import sys; sys.stderr.write('Error on line 12\\n'); sys.exit(2)"], None, 30, "Testing")
ok("exit code 2", result.returncode == 2, result.returncode)
ok("stderr kept for the log", "Error on line 12" in result.stderr, result.stderr)
print()

print("3. a tool that hangs: stopped at its timeout, as subprocess.run would")
h = Watch()
started = time.monotonic()
try:
    h.run_tool_watched([PY, "-c", "import time; time.sleep(60)"], None, 1.5, "Testing")
    raised = None
except subprocess.TimeoutExpired as error:
    raised = error
ok("TimeoutExpired raised", raised is not None)
ok("after the timeout, not the sleep", time.monotonic() - started < 15, time.monotonic() - started)
ok("the line counted its seconds while it waited", any(" s" in line for line in h.lines))
print()

print("4. closing Rialto mid-tool stops the tool")
h = Watch()
h.keep_window_alive = lambda: (_ for _ in ()).throw(RuntimeError("Rialto was closed during the build"))
try:
    h.run_tool_watched([PY, "-c", "import time; time.sleep(60)"], None, 30, "Testing")
    stopped = False
except RuntimeError:
    stopped = True
ok("the build stops with its reason", stopped)
print()

print("5. ISCC's own lines, and the live line's words")
parse = ns["iscc_compressing_path"]
ok("a file ISCC is compressing", parse("   Compressing: C:\\out\\Data\\Levels\\level0.dat") == "C:\\out\\Data\\Levels\\level0.dat")
ok("not the Setup program line", parse("   Compressing Setup program executable") is None)
ok("not anything else", parse("Successful compile (2.000 sec).") is None and parse(None) is None)
text = ns["progress_text"]
ok("the plan's example", text("Compressing the installer", 0.41, 372, "812 of 3,140 files")
   == "Compressing the installer: 812 of 3,140 files, 41%, 6 min 12 s")
ok("no percentage, still a clock", text("Writing the disc image", None, 9) == "Writing the disc image: 9 s")
print()

print("6. one build at a time, the page held while it runs")
flat = src.replace("\r\n", "\n")
run = textwrap.dedent(ast.get_source_segment(src, next(i for i in app.body if isinstance(i, ast.FunctionDef)
                                                         and i.name == "run_build_process")))
ok("a second BUILD while one runs does nothing", run.index('if getattr(self, "_building", False):') < run.index("self.hold_page(True)"))
ok("the page is let go however the build ends", "finally:" in run and "self.hold_page(False)" in run.split("finally:")[1])
ok("the log is never held", "if w is not getattr(self, \"status_text\", None)" in flat)
ok("closing mid-build asks first", '"A build is running"' in flat)
# Since 1.5.1 one disc and each disc of a set both write through _write_one_image (its one watched call), and
# the menu compile runs watched too: ISCC, the image writer and the menu compile are the three.
ok("ISCC, the disc image, multi-disc images and a menu compile all run watched",
   flat.count("self.run_tool_watched(") == 3
   and flat.count("self._write_one_image(") == 2 and "subprocess.run(command, cwd=output_path, capture_output=True, text=True, timeout=3600)" not in flat)
print()

print("7. closing Rialto: every way asks during a build, saves the session, and stops cleanly")
import tkinter as tk
names = ("on_exit", "close_now", "close_if_asked", "run_build_process", "keep_window_alive", "run_build_queue")
body = "\n\n".join(textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
                   if isinstance(i, ast.FunctionDef) and i.name in names)
# run_build_queue checks the tools once before its rows (1.5.1, carried tools): here every tool is found.
cns = {"os": os, "tk": tk, "time": time, "subprocess": subprocess,
       "missing_tool_refusals": lambda pressed=False, image_needed=True: []}
exec("class CloseHost:\n" + textwrap.indent(body, "    "), cns)


class FakeRoot:
    def __init__(self, events):
        self.events = events

    def update(self):
        pass

    def withdraw(self):
        self.events.append("withdraw")

    def destroy(self):
        self.events.append("destroy")

    def winfo_children(self):
        return []


class FakeTool:
    def __init__(self):
        self.killed = False

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True


class Closer(cns["CloseHost"]):
    def __init__(self, answer):
        self.events, self.answer, self.asked = [], answer, []
        self.root = FakeRoot(self.events)
        self.log = []

    def show_centered_popup(self, title, message, kind="info"):
        # The real method's first lines: once Rialto is closing it asks nothing.
        if getattr(self, "_close_when_stopped", False):
            return False if kind == "yesno" else None
        self.asked.append(title)
        return self.answer if kind == "yesno" else None

    def save_last_session(self):
        self.events.append("save")

    def hold_page(self, hold):
        self.events.append("hold" if hold else "let go")

    def refresh_disc_meter(self):
        pass

    def update_status(self, message):
        self.log.append(message)


h = Closer(answer=True)
h.on_exit()
ok("not building: the X saves the session and closes, asking nothing",
   h.events == ["save", "destroy"] and not h.asked, (h.events, h.asked))

h = Closer(answer=False)
h._building = True
h.on_exit()
ok("building, the answer is No: the question was asked and nothing else happened",
   h.asked == ["A build is running"] and h.events == [] and not getattr(h, "_abandon_build", False),
   (h.asked, h.events))

h = Closer(answer=True)
mid = {}


def a_build_that_is_closed(self=h):
    self._running_tool = FakeTool()
    tool = self._running_tool
    self.on_exit()  # the X, clicked while keep_window_alive let the window answer
    mid["tool killed"] = tool.killed
    mid["events"] = list(self.events)
    try:
        self.keep_window_alive()
        mid["stopped"] = False
    except RuntimeError as error:
        mid["stopped"] = "closed during the build" in str(error)
    self.update_status("Build failed")  # what build_all does with the RuntimeError
    mid["popup"] = self.show_centered_popup("Done", "Build complete")
    return False


h._run_build_process = a_build_that_is_closed
returned = h.run_build_process()
ok("building, the answer is Yes: the running tool is stopped", mid.get("tool killed") is True)
ok("the window hides at once but is not destroyed under the build",
   mid.get("events") == ["hold", "withdraw"], mid.get("events"))
ok("the build stops at its next check", mid.get("stopped") is True)
ok("no popup asks anything after the person chose to close", mid.get("popup") is None and h.asked == ["A build is running"],
   (mid.get("popup"), h.asked))
ok("once the build has unwound: the page let go, the session saved, then the window destroyed",
   returned is False and h.events == ["hold", "withdraw", "let go", "save", "destroy"], h.events)
ok("and only once", h.events.count("destroy") == 1 and not h._building)

tmp = __import__("tempfile").mkdtemp(prefix="rialto_close_")
rows = []
for n in (1, 2):
    folder = os.path.join(tmp, "Game%d" % n)
    os.makedirs(folder)
    profile = os.path.join(tmp, "game%d.json" % n)
    open(profile, "w").write("{}")
    rows.append({"profile": profile, "folder": folder, "run": True})
h = Closer(answer=True)
built = []
h.current_profile_data = lambda: {"Title": "the author's own form"}
h.current_game_path = "the author's game"
h.apply_profile_file = lambda path, remember=True: True
h.queue_row_result = lambda name, installers_only: "made"
h.restore_form = lambda data, game: h.events.append("form back")


def queued_build(self=h):
    built.append(self.current_game_path)
    if len(built) == 1:
        self.on_exit()
        try:
            self.keep_window_alive()
        except RuntimeError:
            return False
    return True


h._run_build_process = queued_build
try:
    h.run_build_queue(rows)
    queue_stopped = False
except RuntimeError:
    queue_stopped = True
ok("closing mid-queue asks once and stops the queue", queue_stopped and h.asked == ["A build is running"], h.asked)
ok("the next row never starts", len(built) == 1, built)
ok("the author's form comes back before the session is saved, then the window closes",
   h.events[-3:] == ["form back", "save", "destroy"] and h.events.count("destroy") == 1, h.events)
shutil.rmtree(tmp, ignore_errors=True)

bar = flat[flat.index("self.close_btn = tk.Button("):]
bar = bar[:bar.index("self.close_btn.pack(")]
ok("the title bar's X goes through on_exit", "command=self.on_exit" in bar, bar)
ok("nothing else destroys the main window", flat.count("self.root.destroy()") == 1
   and "command=self.root.destroy" not in flat and 'protocol("WM_DELETE_WINDOW", self.on_exit)' in flat)
popup = textwrap.dedent(ast.get_source_segment(src, next(i for i in app.body if isinstance(i, ast.FunctionDef)
                                                           and i.name == "show_centered_popup")))
ok("the real show_centered_popup asks nothing once Rialto is closing",
   popup.index('if getattr(self, "_close_when_stopped", False):') < popup.index("theme = self.current_theme()"))
print()

print("8. every other long step keeps the window answering and the line moving")
import tempfile
import threading


def method_src(name):
    return textwrap.dedent(ast.get_source_segment(src, next(i for i in app.body if isinstance(i, ast.FunctionDef)
                                                             and i.name == name)))


h = Watch()
tick = h.build_ticker("Checksumming Game.iso", 4e9)
for _ in range(8):
    tick(5e8)
    time.sleep(0.25)
ok("a byte count where there is one", h.lines[-1].startswith("Checksumming Game.iso: 4.0 of 4.0 GB, 100%"), h.lines[-2:])
ok("the window answered as it went", h.alive >= 6, h.alive)
h = Watch()
tick = h.build_ticker("Signing setup.exe")
tick()
ok("a seconds counter where there is none", h.lines == ["Signing setup.exe: 0 s"], h.lines)

h = Watch()
heard = []
h.update_status = lambda line: heard.append((line, threading.current_thread() is threading.main_thread()))


def slow_work(log):
    log("first line")
    time.sleep(0.8)
    log("second line")
    return ("done", 1)


started = time.monotonic()
got = h.run_watched_call("Downloading vcredist_x64.exe", slow_work, watch=lambda: (None, "3.0 MB"))
ok("run_watched_call hands back what the work returned", got == ("done", 1), got)
ok("its log lines reach the log in order, on the window's own thread",
   heard == [("first line", True), ("second line", True)], heard)
ok("the window answered while the work ran", h.alive >= 8, h.alive)
ok("the line counts what watch hands back", h.lines[-1].startswith("Downloading vcredist_x64.exe: 3.0 MB,"), h.lines[-1:])
try:
    h.run_watched_call("Signing", lambda log: 1 / 0)
    raised = None
except ZeroDivisionError as error:
    raised = error
ok("and raises what the work raised", raised is not None)
h = Watch()
h.keep_window_alive = lambda: (_ for _ in ()).throw(RuntimeError("Rialto was closed during the build"))
started = time.monotonic()
try:
    h.run_watched_call("Signing", lambda log: time.sleep(30))
    stopped = False
except RuntimeError:
    stopped = True
ok("closing Rialto stops the wait at once", stopped and time.monotonic() - started < 5, time.monotonic() - started)

tmp = tempfile.mkdtemp(prefix="rialto_watch_")
bonus_tree = os.path.join(tmp, "bonus")
os.makedirs(os.path.join(bonus_tree, "art"))
for n in range(30):
    open(os.path.join(bonus_tree, "art", "page%02d.png" % n), "wb").write(b"x" * 1000)
h = Watch()
h.watched_copytree(bonus_tree, os.path.join(tmp, "copy"), "Copying the bonus folder")
ok("watched_copytree copies every file", len(os.listdir(os.path.join(tmp, "copy", "art"))) == 30)
ok("and moves the line as it goes", h.lines and h.lines[0].startswith("Copying the bonus folder"), h.lines[:1])

fns = {}
exec(ast.get_source_segment(src, next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "file_md5")), fns)
big = os.path.join(tmp, "Game.iso")
open(big, "wb").write(os.urandom(3 * 1024 * 1024 + 7))
counted = []
digest = fns["file_md5"](big, chunk=1024 * 1024, progress=counted.append)
ok("the pressed MD5 counts every byte it reads", sum(counted) == os.path.getsize(big) and len(counted) == 4, counted)
ok("and still gives the same checksum", digest == __import__("hashlib").md5(open(big, "rb").read()).hexdigest())


class Stopping(Watch):
    """A build the person has just chosen to close."""
    _abandon_build = True

    def keep_window_alive(self):
        raise RuntimeError("Rialto was closed during the build")

    def update_status(self, line):
        pass


for name, run in (("build_bonus_gallery", lambda s: s.build_bonus_gallery(tmp, os.path.join(tmp, "out"), bonus_tree)),):
    exec("class Step:\n" + textwrap.indent(method_src(name), "    "), ns)
    step = type("S", (ns["Step"], Stopping), {})()
    try:
        run(step)
        stopped = False
    except RuntimeError:
        stopped = True
    ok("%s: a close mid-copy stops the build, not swallowed as a warning" % name, stopped)
shutil.rmtree(tmp, ignore_errors=True)

for name, needs in (("build_bonus_gallery", "self.watched_copytree("),
                    ("stage_mod_launcher", "self.watched_copytree("),
                    ("stage_universal_builds", "self.watched_copytree("),
                    ("package_unix_build", "tick(info.size"),
                    ("write_pressing_files", "file_md5(path, progress=tick)"),
                    ("download_essential_runtimes", "self.run_watched_call("),
                    ("sign_staged_menu_exe", "self.run_watched_call("),
                    ("export_usb_fileset", "self.counting_copy("),
                    ("compile_pyqt5_menu", "self.run_tool_watched(")):
    body = method_src(name)
    ok("%s runs watched" % name, needs in body and "shutil.copytree(path, dest)" not in body
       and "subprocess.run(" not in body, name)
    if "except Exception" in body:
        ok("%s: a close is never swallowed by its except" % name,
           body.count('if getattr(self, "_abandon_build", False):') >= 1, name)
ok("setup.exe is signed with the window answering",
   'self.run_watched_call(\n                                        "Signing setup.exe"' in flat)
print()

print("9. no method is defined twice in a class")
classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
template = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE")
classes += [n for n in ast.walk(ast.parse(template)) if isinstance(n, ast.ClassDef)]
twice = {c.name: [k for k, v in collections.Counter(i.name for i in c.body if isinstance(i, ast.FunctionDef)).items() if v > 1]
         for c in classes}
ok("Rialto.pyw and the disc menu", not any(twice.values()), {k: v for k, v in twice.items() if v})

if failures:
    print("\nFAILED: %d check(s)" % len(failures))
    sys.exit(1)
print("\nAll build-watch checks passed.")
