"""The Build Queue (1.5.1, B1), driven without the window.

run_build_queue is lifted out of Rialto.pyw onto a stub whose "build" is a
recorded call, so the queue's own rules are what is tested: unticked rows are
passed over, a missing profile or game folder fails that row with a reason, two
rows that would build into the same output folder cannot both run, Stop After
This One leaves the rest unstarted, a failed build carries its last error into
the summary, the author's form comes back, and the queue's popup mode is
always switched off again, even when a build throws.
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
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


src = open(RIALTO, encoding="utf-8").read()
app = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
wanted = ("run_build_queue", "batch_answer", "queue_row_result", "queue_summary", "close_if_asked")
body = "\n\n".join(textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
                   if isinstance(i, ast.FunctionDef) and i.name in wanted)
work = tempfile.mkdtemp(prefix="rialto_queue_")
# The tools a queue needs (1.5.1, B12.2): present unless a check below takes them away.
TOOLS = {"missing": []}
ns = {"os": os, "glob": __import__("glob"), "OUTPUT_DIR": os.path.join(work, "output"),
      "missing_tool_refusals": lambda pressed, image_needed=True: list(TOOLS["missing"]) if image_needed
      else [line for line in TOOLS["missing"] if line.startswith("No installer")]}
exec("class Host:\n" + textwrap.indent(body, "    "), ns)


class Queue(ns["Host"]):
    def __init__(self, fail=(), throw=()):
        self.current_game_path = "author's own folder"
        self.log, self.applied, self.built, self.restored = [], [], [], None
        self.fail, self.throw = set(fail), set(throw)
        self._batch = None

    def update_status(self, message):
        if self._batch is not None:
            self._batch["lines"].append(message)
        self.log.append(message)

    def current_profile_data(self):
        return {"Title": "the author's own form"}

    def restore_form(self, data, game):
        self.restored = (data, game)

    def apply_profile_file(self, path, remember=True):
        self.applied.append((path, remember, self.current_game_path))
        return True

    def run_build_process(self):
        folder = self.current_game_path
        self.built.append(folder)
        if folder in self.throw:
            raise RuntimeError("Rialto was closed during the build")
        if folder in self.fail:
            self.update_status("❌ Build failed: The game files could not all be copied")
            return False
        name = os.path.basename(folder)
        os.makedirs(os.path.join(ns["OUTPUT_DIR"], name), exist_ok=True)
        open(os.path.join(ns["OUTPUT_DIR"], name, name + ".iso"), "wb").write(b"x" * 2048)
        return True

    def keep_window_alive(self):
        pass


try:
    games = {}
    for name in ("Alpha", "Beta", "Gamma", "Delta"):
        games[name] = os.path.join(work, "input", name)
        os.makedirs(games[name])
    os.makedirs(os.path.join(work, "elsewhere", "Alpha"))
    profile = os.path.join(work, "p.json")
    open(profile, "w").write("{}")

    print("1. a queue of rows")
    q = Queue(fail={games["Gamma"]})
    rows = [{"profile": profile, "folder": games["Alpha"], "title": "Alpha"},
            {"profile": profile, "folder": games["Beta"], "title": "Beta", "run": False},
            {"profile": os.path.join(work, "gone.json"), "folder": games["Beta"], "title": "No profile"},
            {"profile": profile, "folder": os.path.join(work, "nowhere"), "title": "No folder"},
            {"profile": profile, "folder": os.path.join(work, "elsewhere", "Alpha"), "title": "Same name"},
            {"profile": profile, "folder": games["Gamma"], "title": "Gamma"},
            {"profile": profile, "folder": games["Delta"], "title": "Delta"}]
    seen = []
    results = q.run_build_queue(rows, on_row=lambda row, state, detail: seen.append((row["title"], state)))
    by = {row["title"]: (state, detail) for row, state, detail in results}
    ok("each ticked row built in order, the unticked one passed over",
       q.built == [games["Alpha"], games["Gamma"], games["Delta"]] and "Beta" not in by, q.built)
    ok("a profile that is gone fails its row", by["No profile"] == (False, "the profile file is not there any more"))
    ok("a game folder that is gone fails its row", by["No folder"] == (False, "the game folder is not there any more"))
    ok("two rows into one output folder: the second is refused before it builds",
       by["Same name"][0] is False and "same name as row 1" in by["Same name"][1], by["Same name"])
    ok("a failed build says why", by["Gamma"] == (False, "Build failed: The game files could not all be copied"), by["Gamma"])
    ok("a good row names its disc and size", by["Delta"] == (True, "Delta.iso (0.00 GB)"), by["Delta"])
    ok("each profile went on the form after its game folder, without changing the last profile",
       all(remember is False for _p, remember, _g in q.applied) and q.applied[0][2] == games["Alpha"])
    ok("the window heard about each row as it started", ("Alpha", "building") in seen and ("Alpha", True) in seen)
    ok("the author's form came back", q.restored == ({"Title": "the author's own form"}, "author's own folder"))
    ok("popups are back to normal", q._batch is None and q._queue_running is False)
    summary = q.queue_summary(results)
    ok("the summary counts what was made", summary[0] == "Build Queue: 2 of 6 made.", summary[0])
    ok("and gives a line per row", len(summary) == 7 and summary[-1].startswith("✅ Delta: Delta.iso"), summary)
    print()

    print("1b. no tools: said once for the run, not once a row (1.5.1, B12.2)")
    TOOLS["missing"] = ["No disc image tool: there is no mkisofs or oscdimg on this PC and this copy of Rialto does not carry one."]
    q = Queue()
    results = q.run_build_queue(rows)
    ok("nothing is built", q.built == [], q.built)
    ok("the log says it once", sum("No disc image tool" in line for line in q.log) == 1, q.log)
    ok("every ticked row is marked with the short reason, the unticked one passed over",
       [detail for _r, _s, detail in results] == ["not built: no disc image tool (see the log)"] * 6, results)
    ok("the form still comes back", q.restored is not None and q._batch is None)
    q = Queue()
    results = q.run_build_queue(rows[:1], installers_only=True)
    ok("installers only needs no disc image tool, so it builds", q.built == [games["Alpha"]], results)
    TOOLS["missing"] = []
    print()

    print("2. Stop After This One")
    q = Queue()
    stops = iter([False, True, True])
    results = q.run_build_queue(rows[:1] + rows[5:], should_stop=lambda: next(stops))
    ok("the row running finishes, the rest are not started",
       [state for _r, state, _d in results] == [True, None, None] and len(q.built) == 1, results)
    print()

    print("3. a build that throws (Rialto closed mid-row)")
    q = Queue(throw={games["Alpha"]})
    try:
        q.run_build_queue(rows[:1])
        raised = False
    except RuntimeError:
        raised = True
    ok("the reason reaches the caller", raised)
    ok("and the queue still lets go of the popups and puts the form back", q._batch is None and q.restored is not None)
    print()

    print("4. popups in a queue")
    q = Queue()
    q._batch = {"skip_missing": True, "lines": []}
    ok("Something is missing: built without it, as set", q.batch_answer("Something is missing", "1 folder\n...", "yesno") is True)
    q._batch["skip_missing"] = False
    ok("or the row fails, as set", q.batch_answer("Something is missing", "1 folder", "yesno") is False)
    ok("any other question is a no", q.batch_answer("Anything else", "Proceed?", "yesno") is False)
    ok("a notice is a log line", q.batch_answer("Done", "Build complete for X", "info") is True and q.log[-1] == "📋 Done: Build complete for X")
    q.batch_answer("Preflight Check Passed", "All required files and metadata are present.\n\nSign Final Build is off. "
                   "Once the plant has the image, the disc cannot be re-signed.", "info")
    ok("the whole popup is logged, so a pressed disc's signing warning is kept (1.5.1)",
       q.log[-1] == "📋 Preflight Check Passed: All required files and metadata are present. Sign Final Build is off. "
                    "Once the plant has the image, the disc cannot be re-signed.", q.log[-1])
    print()

    print("5. wired into the real build")
    flat = src.replace("\r\n", "\n")
    ok("every popup goes to the queue while it runs",
       'if getattr(self, "_batch", None) is not None:\n            return self.batch_answer(title, message, kind)' in flat)
    ok("the hand-signing pause is never offered in a queue",
       'result = False if getattr(self, "_batch", None) is not None else msgbox.askokcancel(' in flat)
    ok("the jingle plays once, at the end", 'if getattr(self, "_batch", None) is None:\n                self.play_completion_jingle()' in flat)
    ok("build_all and run_build_process say whether they made the disc",
       "            return True\n\n        except RuntimeError as e:" in flat
       and flat.count("            return False\n        except Exception as e:\n            self.update_status(f\"❌ Build failed: {e}\")") == 1
       and "return self.build_all()" in flat)
    ok("Load Profile and the queue apply a profile the same way", "self.apply_profile_file(file_path)" in flat
       and 'self.apply_profile_file(row["profile"], remember=False)' in flat)
finally:
    shutil.rmtree(work, ignore_errors=True)

if failures:
    print("\nFAILED: %d check(s)" % len(failures))
    sys.exit(1)
print("\nAll Build Queue checks passed.")
