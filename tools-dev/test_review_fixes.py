"""The 1.5.1 reviews' findings stay fixed.

Two independent read-only reviews of 48e3f93..release/1.5.1 (security, and
bugs) found these; each is held here, by running the code where that is
cheap and by its shape where it needs a window. The B10 placement rules have
their own checks in test_placed_files.py.
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


src = open(RIALTO, encoding="utf-8").read().replace("\r\n", "\n")
tree = ast.parse(src)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")


def method(name):
    return textwrap.dedent(ast.get_source_segment(src, next(
        i for i in app.body if isinstance(i, ast.FunctionDef) and i.name == name)))


template = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
                                 and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE"))

print("security review")
ok("a queue never calls an unsigned disc Done",
   "unsigned_in_queue = True" in method("compile_installer_with_iscc")
   and __import__("re").search(r"if unsigned_in_queue:\n\s+raise RuntimeError", method("compile_installer_with_iscc")))
ok("a queue row on a network share is never opened or built",
   'startswith(("\\\\\\\\", "//"))' in method("configure_build_queue")
   and "a row on a network share is not built" in method("run_build_queue"))
ok("closing mid-queue asks a real question, not the queue's",
   "batch, self._batch = getattr(self, \"_batch\", None), None" in method("on_exit"))
ok("the held page takes no keys", '"RialtoBuilding"' in method("hold_page") and "self.status_text.focus_set()" in method("hold_page"))
ok("a game folder named like the staging folder is refused", "game_name == PLACED_FILES_DIR" in method("build_all"))
ok("the staging manifest is always written", "if not rows:\n    return []" not in method("stage_placed_files"))
ok("the disc menu shows config text as plain text",
   template.count("title_label.setTextFormat(QtCore.Qt.PlainText)") == 2
   and "copyright_label.setTextFormat(QtCore.Qt.PlainText)" in template
   and "box.setTextFormat(QtCore.Qt.PlainText)" in template)
ok("the compatibility hint's tooltip never reads config markup",
   'return raw[:200].replace("<", "‹").replace(">", "›")' in template)
ok("rarer launchers are refused outside the install folder too",
   all(ext in src for ext in (".scf", ".docm", ".msix", ".vhdx")))
ok("Chksum.md5 takes any title", '"Chksum.md5"), "w", encoding="utf-8"' in method("write_pressing_files"))
print()

print("bugs review")
iso = method("create_iso")
ok("closing during the image stops the build, and removes the half-made image",
   __import__("re").search(r'if getattr\(self, "_abandon_build", False\):\n\s+self\._remove_partial_iso\(iso_path\)\n\s+raise', iso))
ok("one threshold for one disc or a set", "if total_size > capacity - self.SPAN_MARGIN:" in iso)
queue = method("configure_build_queue")
ok("the queue window's X stops after this disc instead of killing the queue",
   'dialog.protocol("WM_DELETE_WINDOW", close_window)' in queue and "if tree.winfo_exists():" in queue)
ok("a pressed set missing a disc never goes to the plant",
   "a plant needs the whole set" in method("create_spanned_isos"))
ok("a game folder inside output\\ is refused before step 0 empties it",
   "inside_output" in method("build_all") and "in_output" in method("run_preflight_check"))
ok("a queue never waits at the USB folder picker", "is skipped in a Build Queue" in method("build_all"))
ok("the copyright line keeps following Developer after a queue", "snapshot_auto_copyright" in method("run_build_queue"))
init_ui = template[template.index("    def init_ui(self):"):template.index("    def change_language(self, lang):")]
ok("the quick starts are filled after their box has its place",
   init_ui.index("self.refresh_quick_starts()") > init_ui.index("for btn in buttons_to_add:"))

ns = {"os": os, "re": __import__("re")}
exec(ast.get_source_segment(src, next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                                       and n.name == "iscc_compressing_path")), ns)
ok("ISCC's version suffix is not part of the path",
   ns["iscc_compressing_path"](r"   Compressing: C:\out\game.exe   (3.12.10150.1013)") == r"C:\out\game.exe")
ok("a path with brackets of its own is kept", ns["iscc_compressing_path"](r"   Compressing: C:\out\a (1).dat")
   == r"C:\out\a (1).dat")

exec("class Host:\n" + textwrap.indent(method("_fileset_disc_bytes"), "    "), ns)
work = tempfile.mkdtemp(prefix="rialto_rf_")
try:
    os.makedirs(os.path.join(work, "bonus"))
    for i in range(10):
        open(os.path.join(work, "bonus", "f%d.txt" % i), "wb").write(b"x")
    open(os.path.join(work, "setup.exe"), "wb").write(b"x" * 5000)
    size = ns["Host"]()._fileset_disc_bytes(work, ["bonus", "setup.exe"])
    ok("Disc 1's base is weighed in whole sectors and records",
       size == 2048 + 10 * 2 * 2048 + (3 + 1) * 2048, size)
finally:
    shutil.rmtree(work, ignore_errors=True)

if failures:
    print("\nFAILED: %d check(s)" % len(failures))
    sys.exit(1)
print("\nAll review fixes hold.")
