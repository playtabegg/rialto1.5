"""No time limit (1.5.2, issue #4 on rialto1.5: "Need option to disable ISCC 1-hour stop timer").

A 30 GB game's installer took ISCC past the hour Rialto gives it, and the
build was stopped with nothing on the screen saying the limit could be lifted.
The "No time limit" box, beside Sign Final Build, lifts the limits of the long
tools: ISCC (an hour), the disc image, one disc or a set (30 minutes), a GOG
unpack (an hour), MakeAppx (30 minutes) and signtool signing setup.exe or the
.msix (5 minutes: signing hashes every file in a large .msix). Unticked, every
limit stands and every message it ends with says to tick No time limit.

Ticked means a timeout of None. run_tool_watched has no other watchdog (ISCC
prints nothing while it packs one big file, so a rule about silence would stop
working builds); a stuck tool shows as a clock that keeps counting, and
closing Rialto still stops it. The GOG unpack and MakeAppx used to block the
window for their whole run; they now run held and watched (run_tool_held), so
that a run of hours can still be watched and closed.

Driven here with the real methods pulled out of Rialto.pyw, real fake tools
(Python one-liners) and stand-ins for the window: no tkinter window opens.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
PY = sys.executable
HINT = "Tick No time limit and %s again"
failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


src = open(RIALTO, encoding="utf-8").read()
flat = src.replace("\r\n", "\n")
tree = ast.parse(src)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
app_methods = {i.name: i for i in app.body if isinstance(i, ast.FunctionDef)}


def methods(*names):
    missing = [n for n in names if n not in app_methods]
    if missing:
        raise SystemExit("could not extract " + ", ".join(missing))
    return "\n\n".join(textwrap.dedent(ast.get_source_segment(src, app_methods[n])) for n in names)


def module_function(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(src, node)


def host_class(names, ns, base="object"):
    exec("class Host(%s):\n" % base + textwrap.indent(methods(*names), "    "), ns)
    return ns["Host"]


class Var:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


hint_ns = {}
exec(module_function("no_time_limit_hint"), hint_ns)
no_time_limit_hint = hint_ns["no_time_limit_hint"]


print("1. the box: beside Sign Final Build, saved with the other build switches")
sign_at = flat.find('themed_check(check_row, "Sign Final Build"')
box_at = flat.find('themed_check(check_row, "No time limit", self.no_time_limit,')
brand_at = flat.find('themed_check(check_row, "Remove WTI Branding"')
ok("a tick box called No time limit, on the check row", box_at > 0)
ok("right after Sign Final Build, before Remove WTI Branding", 0 < sign_at < box_at < brand_at,
   (sign_at, box_at, brand_at))
box = flat[box_at:brand_at]
ok("ticking it saves it, as Sign Final Build does", "command=self.save_signing_settings" in box)
tip = box[box.find("ToolTip(time_check,"):]
words = " ".join(part for part in tip.split('"')[1::2])
ok("it has a tooltip", "ToolTip(time_check," in box)
ok("the tooltip says what it lifts", all(w in words for w in ("an hour", "30 minutes", "installer", "disc image",
                                                              "GOG", ".msix", "signing setup.exe", "5 minutes")),
   words)
ok("and that it starts ticked (his word, 4 Nov 2026)", "It starts ticked" in words, words)
ok("and that closing Rialto still stops a step", "Closing Rialto still stops" in words, words)
ok("no em dash, no exclamation, no We The Indies", not any(c in words for c in ("\u2014", "!")) and "Indies" not in words)
ok("it starts ticked (his word, 4 Nov 2026: on by default)", "self.no_time_limit = tk.BooleanVar(value=True)" in flat)
ok("Restore page leaves it as it is, a setting kept on this PC (his word, 4 Nov 2026)",
   "no_time_limit" not in methods("restore_page"))
profile = methods("current_profile_data", "apply_profile_file", "put_profile_on_form")
ok("a machine setting like Sign Final Build: no profile carries either",
   "no_time_limit" not in profile and "sign_final_build" not in profile and "NoTimeLimit" not in profile)
guide = open(os.path.join(REPO, "docs", "rialto-guide.html"), encoding="utf-8").read()
row = guide[guide.find("A step stopped after an hour"):]
row = row[:row.find("</tr>")]
ok("the Help Guide has its row, in When it goes wrong", "<b>No time limit</b>" in row and "<b>Sign Final Build</b>" in row
   and guide.find('id="trouble"') < guide.find("A step stopped after an hour"), row[:200])
ok("the guide row says what it lifts and that closing still stops it",
   all(w in row for w in ("an hour", "30 minutes", "very large game", "closing Rialto still stops",
                          "signing setup.exe, menu.exe or an .msix after 5 minutes")), row)
print()

print("2. the setting round-trips through config.json")
temp = tempfile.mkdtemp(prefix="rialto_time_limit_")
try:
    config_file = os.path.join(temp, "config.json")
    Config = host_class(["load_config", "save_signing_settings"], {"os": os, "json": json, "CONFIG_FILE": config_file})

    def fresh():
        h = Config()
        h.sign_final_build, h.remove_wti_branding = Var(False), Var(False)
        h.mod_launcher_var, h.no_time_limit = Var(False), Var(False)
        return h

    def written():
        with open(config_file, encoding="utf-8") as fh:
            return json.load(fh)

    h = fresh()
    h.config = {}
    h.no_time_limit.set(True)
    h.save_signing_settings()
    ok("ticked and saved: config.json says no_time_limit true", written().get("no_time_limit") is True, written())
    h = fresh()
    h.load_config()
    ok("and the next Rialto opens with it ticked", h.no_time_limit.get() is True)
    h.no_time_limit.set(False)
    h.save_signing_settings()
    ok("unticked and saved: false", written().get("no_time_limit") is False, written())
    h = fresh()
    h.load_config()
    ok("and the next Rialto opens with it unticked", h.no_time_limit.get() is False)
    with open(config_file, "w", encoding="utf-8") as fh:
        json.dump({"sign_final_build": True}, fh)
    h = fresh()
    h.no_time_limit.set(False)
    h.load_config()
    ok("a config.json from before 1.5.2 (no key): ticked, on by default", h.no_time_limit.get() is True)
    for odd in ("yes", 1, 0, "false", [False], {"on": False}, None):
        with open(config_file, "w", encoding="utf-8") as fh:
            json.dump({"no_time_limit": odd}, fh)
        h = fresh()
        h.no_time_limit.set(False)
        h.load_config()
        ok("no_time_limit %s is not false: ticked" % json.dumps(odd), h.no_time_limit.get() is True)
    with open(config_file, "w", encoding="utf-8") as fh:
        json.dump({"no_time_limit": False}, fh)
    h = fresh()
    h.load_config()
    ok("only this PC's own false unticks it", h.no_time_limit.get() is False)
    print()

    print("3. each limit: lifted when ticked, the old one when not")
    Limits = host_class(["tool_time_limit"], {})
    h = Limits()
    ok("no box (a host without one): the limit stands", h.tool_time_limit(3600) == 3600)
    h.no_time_limit = Var(False)
    ok("unticked: an hour stays an hour, 30 minutes stay 30 minutes",
       h.tool_time_limit(3600) == 3600 and h.tool_time_limit(1800) == 1800)
    h.no_time_limit = Var(True)
    ok("ticked: no limit (None)", h.tool_time_limit(3600) is None and h.tool_time_limit(1800) is None)

    def limit_at(method, callee, position=2, keyword=None):
        """The timeout expression `method` hands `callee`, as source text."""
        for node in ast.walk(app_methods[method]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == callee:
                if keyword:
                    found = [k.value for k in node.keywords if k.arg == keyword]
                    if found:
                        return ast.unparse(found[0])
                elif len(node.args) > position:
                    return ast.unparse(node.args[position])
        return None

    for method, callee, seconds, what, kw in (
            ("compile_installer_with_iscc", "run_tool_watched", 3600, "ISCC", None),
            ("_write_one_image", "run_tool_watched", 1800, "the disc image, one disc or each disc of a set", None),
            ("import_gog_installer", "run_tool_held", 3600, "the GOG unpack", None),
            ("export_msix", "build_msix", 1800, "MakeAppx", "timeout")):
        got = limit_at(method, callee, keyword=kw)
        ok("%s runs under self.tool_time_limit(%d)" % (what, seconds), got == "self.tool_time_limit(%d)" % seconds, got)
    ok("one disc and a set both write through _write_one_image", flat.count("self._write_one_image(") == 2)

    literal = []
    for node in ast.walk(app):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in (
                "run_tool_watched", "run_tool_held", "run", "build_msix"):
            given = [k.value for k in node.keywords if k.arg == "timeout"]
            if node.func.attr in ("run_tool_watched", "run_tool_held") and len(node.args) > 2:
                given.append(node.args[2])
            literal += [ast.unparse(node) for g in given if isinstance(g, ast.Constant) and g.value in (1800, 3600)]
    ok("no long tool keeps a fixed hour or half hour of its own", literal == [], literal)
    msix_tree = ast.parse(open(os.path.join(REPO, "rialto", "msix_export.py"), encoding="utf-8").read())
    makeappx = [node for node in ast.walk(msix_tree) if isinstance(node, ast.Call)
                and ast.unparse(node.func) == "subprocess.run"]
    ok("msix_export runs MakeAppx under the timeout it is given",
       len(makeappx) == 1 and [ast.unparse(k.value) for k in makeappx[0].keywords if k.arg == "timeout"] == ["timeout"],
       [ast.unparse(node) for node in makeappx])
    print()

    print("4. run_tool_watched with no limit: the tool runs until it ends, and closing still stops it")
    progress_ns = {"os": os, "subprocess": subprocess, "time": time}
    exec(module_function("progress_text"), progress_ns)
    Watched = host_class(["run_tool_watched"], progress_ns)

    class Watch(Watched):
        def __init__(self):
            self.lines, self.alive = [], 0

        def show_progress(self, step, fraction=None, seconds=0.0, detail=""):
            self.lines.append(progress_ns["progress_text"](step, fraction, seconds, detail))

        def keep_window_alive(self):
            self.alive += 1

    quiet = [PY, "-c", "import time; time.sleep(2.5); print('done', flush=True)"]
    h = Watch()
    try:
        h.run_tool_watched(quiet, None, 1, "Testing")
        stopped = False
    except subprocess.TimeoutExpired:
        stopped = True
    ok("with a limit (1 s) a tool silent for 2.5 s is stopped, as before", stopped)
    h = Watch()
    started = time.monotonic()
    result = h.run_tool_watched(quiet, None, None, "Testing")
    ok("with None the same silent tool runs past where the limit was, to its end",
       result.returncode == 0 and "done" in result.stdout and time.monotonic() - started >= 2.4, result)
    ok("nothing else stopped it: no watchdog for silence", h.alive >= 20, h.alive)
    ok("and the line kept counting its seconds", any(line.endswith(" 2 s") for line in h.lines), h.lines[-3:])

    h = Watch()
    calls = {"n": 0}

    def closed():
        calls["n"] += 1
        if calls["n"] == 10:
            raise RuntimeError("Rialto was closed during the build")
    h.keep_window_alive = closed
    started = time.monotonic()
    try:
        h.run_tool_watched([PY, "-c", "import time; time.sleep(60)"], None, None, "Testing")
        stopped = False
    except RuntimeError:
        stopped = True
    ok("with None, closing Rialto still stops the tool, at once", stopped and time.monotonic() - started < 15,
       time.monotonic() - started)
    print()

    print("5. ISCC: the limit handed over, and the message that names the box")
    iscc_ns = {"os": os, "subprocess": subprocess, "INNO_SETUP_DOWNLOAD": "https://jrsoftware.org/isdl.php",
               "installer_compiler": lambda: (r"C:\Inno Setup 6\ISCC.exe", False),
               "_inno_setup_major": lambda path: 6, "tool_words": lambda kind, path, carried: "your Inno Setup",
               "no_time_limit_hint": no_time_limit_hint}
    exec(module_function("iscc_compressing_path"), iscc_ns)
    Iscc = host_class(["compile_installer_with_iscc", "tool_time_limit"], iscc_ns)

    def compile_with(ticked, behave):
        h = Iscc()
        h.log, h.given = [], []
        h.update_status = h.log.append
        h.sign_final_build, h.no_time_limit = Var(False), Var(ticked)
        h.tree_size = lambda path, skip_ext=(".iso",): (0, 0)

        def run(command, cwd, timeout, step, on_line=None, watch=None):
            h.given.append(timeout)
            if behave == "timeout":
                raise subprocess.TimeoutExpired(command, timeout)
            return subprocess.CompletedProcess(command, 2, "", "Error on line 12")
        h.run_tool_watched = run
        out = os.path.join(temp, "iscc-%s-%s" % (ticked, behave))
        os.makedirs(out, exist_ok=True)
        try:
            h.compile_installer_with_iscc(out)
            return h, None
        except RuntimeError as error:
            return h, str(error)

    h, raised = compile_with(False, "timeout")
    ok("unticked: ISCC is given its hour", h.given == [3600], h.given)
    ok("the build stops with the reason, and the reason names No time limit",
       raised and "ISCC ran for an hour without finishing" in raised and HINT % "build" in raised, raised)
    ok("said once: the log line before the stop does not repeat it (build_all logs the reason)",
       "❌ ISCC ran for an hour without finishing" in h.log and not any(HINT % "build" in line for line in h.log), h.log)
    h, raised = compile_with(True, "fails")
    ok("ticked: ISCC is given no limit", h.given == [None], h.given)
    ok("an ISCC that fails says so, without the time limit's words",
       raised and "ISCC failed" in raised and "No time limit" not in raised, raised)
    print()

    print("6. a GOG unpack: held and watched, its limit, and its message")
    picked = os.path.join(temp, "setup_sky_quest_1.0.2_(64bit).exe")
    open(picked, "wb").close()
    input_dir = os.path.join(temp, "input")
    gog_ns = {"os": os, "re": __import__("re"), "shutil": shutil, "subprocess": subprocess,
              "filedialog": type("Pick", (), {"askopenfilename": staticmethod(lambda **kw: picked)}),
              "safe": lambda path: path, "INPUT_DIR": input_dir, "no_time_limit_hint": no_time_limit_hint}
    Gog = host_class(["import_gog_installer", "tool_time_limit"], gog_ns)

    def unpack_with(ticked):
        h = Gog()
        h.log, h.held = [], []
        h.update_status = h.log.append
        h.no_time_limit = Var(ticked)
        h.root = type("Root", (), {"update": lambda self: None})()
        h._ensure_innoextract = lambda: r"C:\tools\innoextract.exe"

        def held(command, cwd, timeout, step, doing):
            h.held.append((command[0], timeout, step, doing))
            if not ticked:
                raise subprocess.TimeoutExpired(command, timeout)
            return subprocess.CompletedProcess(command, 1, "", "Stream error")
        h.run_tool_held = held
        h.import_gog_installer()
        return h

    h = unpack_with(False)
    ok("innoextract runs held, with the window's words for closing",
       h.held and h.held[0][0].endswith("innoextract.exe") and h.held[0][3] == "unpacking your GOG installer", h.held)
    ok("the live line names the installer", h.held and h.held[0][2] == "Unpacking " + os.path.basename(picked), h.held)
    ok("unticked: an hour", h.held and h.held[0][1] == 3600, h.held)
    ok("and when the hour runs out the log names No time limit",
       any("Unpacking took over an hour" in line and HINT % "import" in line for line in h.log), h.log)
    h = unpack_with(True)
    ok("ticked: no limit", h.held and h.held[0][1] is None, h.held)
    ok("an unpack that fails says so", any("Unpack failed: Stream error" in line for line in h.log), h.log)
    print()

    print("7. an .msix: MakeAppx's limit, and its message")
    sys.path.insert(0, REPO)
    from rialto import msix_export
    game = os.path.join(temp, "msix-game")
    os.makedirs(game)
    open(os.path.join(game, "Game.exe"), "wb").close()
    real_find, real_run = msix_export.find_makeappx, subprocess.run
    msix_export.find_makeappx = lambda: r"C:\SDK\makeappx.exe"
    seen = []
    try:
        def run_here(command, timeout):
            seen.append((command[:2], timeout))
            raise subprocess.TimeoutExpired(command, timeout)
        done, message = msix_export.build_msix(game, "Sky Quest", "CN=Jane Smith", "Jane Smith", "1.0.0.0", "Game.exe",
                                               None, os.path.join(temp, "a.msix"), status=lambda line: None,
                                               timeout=1800, run=run_here)
        ok("Rialto's own runner is used, and handed the limit", seen == [([r"C:\SDK\makeappx.exe", "pack"], 1800)], seen)
        ok("30 minutes out: the message says so and names No time limit",
           done is False and "30 minutes" in message and HINT % "export" in message, message)

        seen[:] = []

        def run_ticked(command, timeout):
            seen.append(timeout)
            return subprocess.CompletedProcess(command, 1, "", "MakeAppx : error: 0x80080204")
        done, message = msix_export.build_msix(game, "Sky Quest", "CN=Jane Smith", "Jane Smith", "1.0.0.0", "Game.exe",
                                               None, os.path.join(temp, "b.msix"), status=lambda line: None,
                                               timeout=None, run=run_ticked)
        ok("ticked: MakeAppx is given no limit", seen == [None], seen)
        ok("a MakeAppx that fails says so, without the time limit's words",
           done is False and "MakeAppx failed" in message and "No time limit" not in message, message)

        def plain_run(command, **kw):
            seen.append(("run", kw.get("timeout")))
            return subprocess.CompletedProcess(command, 1, "", "error")
        subprocess.run = plain_run
        seen[:] = []
        msix_export.build_msix(game, "Sky Quest", "CN=Jane Smith", "Jane Smith", "1.0.0.0", "Game.exe", None,
                               os.path.join(temp, "c.msix"), status=lambda line: None)
        ok("with no runner and no timeout given: subprocess.run and 30 minutes, as before", seen == [("run", 1800)], seen)
    finally:
        msix_export.find_makeappx, subprocess.run = real_find, real_run
    export = methods("export_msix")
    ok("Export .msix hands MakeAppx to run_tool_held, with the window's words for closing",
       'self.run_tool_held(command, None, limit, "Packing the .msix",' in export and '"packing your .msix"' in export)
    print()

    print("7b. signing: the .msix and setup.exe under the same box, and the message that names it")
    from rialto import trusted_signing, ssl_signing
    payload = os.path.join(temp, "Sky Quest.msix")
    with open(payload, "wb") as fh:
        fh.write(b"PK")
    config_path = os.path.join(temp, "signing_config.json")
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump({"provider": "azure_trusted_signing", "endpoint": "https://eus.codesigning.azure.net",
                   "account_name": "sky-quest", "certificate_profile": "public"}, fh)
    saved = (trusted_signing.CONFIG_FILE, trusted_signing.find_signtool, trusted_signing.ensure_dlib,
             ssl_signing.is_signed, subprocess.run)
    trusted_signing.CONFIG_FILE = config_path
    trusted_signing.find_signtool = lambda: r"C:\SDK\signtool.exe"
    trusted_signing.ensure_dlib = lambda status: r"C:\SDK\Azure.CodeSigning.Dlib.dll"
    read_back = []
    ssl_signing.is_signed = lambda path, timeout=60, run=None: read_back.append((timeout, run)) or True
    try:
        seen[:] = []

        def sign_timeout(command, timeout):
            seen.append((os.path.basename(command[0]), command[1], timeout))
            raise subprocess.TimeoutExpired(command, timeout)
        done, message = trusted_signing.sign_file(payload, status=lambda line: None, timeout=300, run=sign_timeout,
                                                  again="export")
        ok("Rialto's own runner signs, and is handed the limit", seen == [("signtool.exe", "sign", 300)], seen)
        ok("5 minutes out: the message says so and names No time limit",
           done is False and "5 minutes" in message and HINT % "export" in message, message)
        seen[:] = []

        def sign_ticked(command, timeout):
            seen.append(timeout)
            return subprocess.CompletedProcess(command, 0, "Successfully signed", "")
        done, message = trusted_signing.sign_file(payload, status=lambda line: None, timeout=None, run=sign_ticked,
                                                  again="export")
        ok("ticked: signtool is given no limit, and neither is reading the signature back",
           done is True and seen == [None] and [t for t, _r in read_back] == [None], (done, seen, read_back))
        ok("and the read-back goes through Rialto's own runner too, so closing still stops it",
           [r for _t, r in read_back] == [sign_ticked], read_back)

        def plain_sign(command, **kw):
            seen.append(("run", kw.get("timeout")))
            raise subprocess.TimeoutExpired(command, kw.get("timeout"))
        subprocess.run = plain_sign
        seen[:] = []
        done, message = trusted_signing.sign_file(payload, status=lambda line: None)
        ok("with no runner and no timeout given: subprocess.run and 5 minutes, as before", seen == [("run", 300)], seen)
        ok("and its message names the box, to build again", HINT % "build" in message, message)
    finally:
        (trusted_signing.CONFIG_FILE, trusted_signing.find_signtool, trusted_signing.ensure_dlib,
         ssl_signing.is_signed, subprocess.run) = saved
    export = methods("export_msix")
    ok("Export .msix signs under self.tool_time_limit(300), held, and says to export again",
       "timeout=self.tool_time_limit(300)" in export and '"Signing the .msix",' in export
       and '"signing your .msix"' in export and 'again="export"' in export)
    setup_signing = next(ast.unparse(node) for node in ast.walk(app) if isinstance(node, ast.Call)
                         and ast.unparse(node).startswith("self.run_watched_call('Signing setup.exe'"))
    ok("signing setup.exe in a build runs under the same box", "sign_file(setup_path, log, timeout=limit)"
       in setup_signing and "limit = self.tool_time_limit(300)" in flat, setup_signing)
    ssl_tree = ast.parse(open(os.path.join(REPO, "rialto", "ssl_signing.py"), encoding="utf-8").read())
    is_signed = next(n for n in ssl_tree.body if isinstance(n, ast.FunctionDef) and n.name == "is_signed")
    ok("is_signed reads the signature back under the limit it is given, 60 s as before",
       [ast.unparse(d) for d in is_signed.args.defaults] == ["60", "None"] and "timeout=timeout" in ast.unparse(is_signed))
    real_run, real_signtool = subprocess.run, ssl_signing._signtool
    try:
        subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("subprocess.run used"))
        ssl_signing._signtool = lambda: r"C:\SDK\signtool.exe"
        handed = []
        got = ssl_signing.is_signed(payload, timeout=None,
                                    run=lambda command, limit: handed.append((command[1], limit))
                                    or subprocess.CompletedProcess(command, 0, "", ""))
        ok("is_signed hands signtool verify to the runner it is given", got is True
           and handed == [("verify", None)], (got, handed))
    finally:
        subprocess.run, ssl_signing._signtool = real_run, real_signtool
    print()

    print("8. run_tool_held: the page held, closing asks in the step's own words and stops the tool")
    import tkinter as tk
    close_ns = {"os": os, "tk": tk, "time": time, "subprocess": subprocess,
                "progress_text": progress_ns["progress_text"]}
    Held = host_class(["on_exit", "close_now", "close_if_asked", "keep_window_alive", "run_tool_watched",
                       "run_tool_held", "tool_time_limit"], close_ns)

    class FakeRoot:
        def __init__(self, host, close_at=None):
            self.host, self.close_at, self.updates = host, close_at, 0

        def update(self):
            self.updates += 1
            if self.updates == self.close_at:
                self.host.on_exit()  # the X, clicked while the window answers

        def withdraw(self):
            self.host.events.append("withdraw")

        def destroy(self):
            self.host.events.append("destroy")

        def winfo_children(self):
            return []

    class Window(Held):
        def __init__(self, close_at=None, answer=True):
            self.events, self.asked, self.answer = [], [], answer
            self.root = FakeRoot(self, close_at)
            self.no_time_limit = Var(True)

        def show_centered_popup(self, title, message, kind="info"):
            if getattr(self, "_close_when_stopped", False):
                return False if kind == "yesno" else None
            self.asked.append((title, message))
            return self.answer if kind == "yesno" else None

        def show_progress(self, step, fraction=None, seconds=0.0, detail=""):
            pass

        def hold_page(self, hold):
            self.events.append("hold" if hold else "let go")

        def refresh_disc_meter(self):
            pass

        def save_last_session(self):
            self.events.append("save")

    h = Window()
    result = h.run_tool_held([PY, "-c", "print('unpacked')"], None, h.tool_time_limit(3600), "Unpacking",
                             "unpacking your GOG installer")
    ok("a tool that finishes: what subprocess.run would hand back", result.returncode == 0 and "unpacked" in result.stdout)
    ok("the page held while it ran, and let go after", h.events == ["hold", "let go"], h.events)
    ok("and Rialto is no longer busy", h._building is False and h._held_doing is None and h._running_tool is None)

    h = Window(close_at=8, answer=True)
    started = time.monotonic()
    try:
        h.run_tool_held([PY, "-c", "import time; time.sleep(60)"], None, h.tool_time_limit(3600), "Unpacking",
                        "unpacking your GOG installer")
        stopped = None
    except RuntimeError as error:
        stopped = str(error)
    ok("no limit, closed mid-unpack: asked once, in the unpack's own words",
       [t for t, _m in h.asked] == ["Rialto is still working"]
       and "Rialto is still unpacking your GOG installer. Stop it and close Rialto?" in h.asked[0][1], h.asked)
    ok("the answer Yes stops the tool at once", stopped and time.monotonic() - started < 15,
       (stopped, time.monotonic() - started))
    ok("the window hides, the page is let go, the session saved, then the window destroyed, once",
       h.events == ["hold", "withdraw", "let go", "save", "destroy"], h.events)

    h = Window(close_at=8, answer=False)
    result = h.run_tool_held([PY, "-c", "import time; time.sleep(1.5); print('unpacked')"], None, None, "Unpacking",
                             "unpacking your GOG installer")
    ok("the answer No: the unpack carries on to its end, and Rialto stays open",
       result.returncode == 0 and "destroy" not in h.events and len(h.asked) == 1, (h.events, h.asked))

    h = Window()
    h._building = True  # inside a build: the build holds the page already
    h.run_tool_held([PY, "-c", "pass"], None, None, "Unpacking", "unpacking your GOG installer")
    ok("inside a build it runs watched and leaves the build's hold alone", h.events == [] and h._building is True,
       h.events)

    h = Window(answer=False)
    h._building = True
    h.on_exit()
    ok("a build's own question is unchanged", [t for t, _m in h.asked] == ["A build is running"], h.asked)
    print()

    print("9. every limit's message names No time limit")
    ok("the words name the limit and the step (his word, 4 Nov 2026: no bare 'that')",
       no_time_limit_hint("an hour", "to make its installer") == "A very large game can need more than an hour to "
       "make its installer. Tick No time limit and build again"
       and no_time_limit_hint("an hour", "to unpack its GOG installer", "import").endswith(HINT % "import"))
    ok("ISCC's stop names it once the hour ran out, and only then (driven in 5.)",
       '+ (" " + no_time_limit_hint("an hour", "to make its installer") if timed_out else ""))'
       in methods("compile_installer_with_iscc"))
    ok("no message says 'longer than that' any more",
       all("that: tick No time limit" not in open(os.path.join(REPO, *rel), encoding="utf-8").read()
           for rel in (("Rialto.pyw",), ("rialto", "msix_export.py"), ("rialto", "trusted_signing.py"),
                       ("docs", "rialto-guide.html"))))
    for method in ("create_iso", "_build_single_iso", "import_gog_installer"):
        handlers = [node for node in ast.walk(app_methods[method]) if isinstance(node, ast.ExceptHandler)
                    and node.type is not None and ast.unparse(node.type) == "subprocess.TimeoutExpired"]
        ok("%s: its timeout says to tick No time limit" % method,
           handlers and all("no_time_limit_hint(" in ast.unparse(node) for node in handlers),
           [ast.unparse(node)[:160] for node in handlers])
    ok("the disc image's own messages, one disc and a set, are driven in test_image_tool_chain.py",
       "Tick No time limit and build again" in open(os.path.join(REPO, "tools-dev", "test_image_tool_chain.py"),
                                                    encoding="utf-8").read())
finally:
    shutil.rmtree(temp, ignore_errors=True)

print()
if failures:
    print("FAILED: %d check(s)" % len(failures))
    for label in failures:
        print("  - " + label)
    sys.exit(1)
print("All No time limit checks passed.")
