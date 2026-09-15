"""A title outside Western European letters builds without a crash.

menu.bat and the other helper scripts were written in the PC's own code page
with no error handling, so a Polish, Japanese or Hebrew title stopped the whole
build with a codec error. autorun.inf is written in Windows-1252 on purpose,
and a title outside it used to leave the disc with no autorun.inf at all. Both
now write a replacement character where the code page has no letter, so the
build carries on and the disc keeps its autorun.inf.

Source-extracted and exec'd on a stub object: no tkinter, no PyQt5.
"""
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
TITLES = ["Łódź Nights", "日本語のゲーム", "עברית בדיסק", "Ça va ★ 2"]

failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + detail) if detail else ""))
    if not cond:
        failures.append(label)


def methods(src, names):
    found = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names and item.name not in found:
                    found[item.name] = textwrap.dedent(ast.get_source_segment(src, item))
    missing = set(names) - set(found)
    if missing:
        raise SystemExit("could not extract %s" % sorted(missing))
    return [found[n] for n in names]


def module_closure(src, used_names):
    """Module-level functions and constants the methods lean on, and theirs in turn."""
    tree = ast.parse(src)
    defs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defs[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defs[target.id] = node
    wanted, queue, seen = [], [n for n in used_names if n in defs], set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        node = defs[name]
        if node not in wanted:
            wanted.append(node)
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and inner.id in defs and inner.id not in seen:
                queue.append(inner.id)
    wanted.sort(key=lambda n: n.lineno)
    return "\n\n".join(ast.get_source_segment(src, n) for n in wanted)


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def main():
    with open(RIALTO, encoding="utf-8") as fh:
        src = fh.read()
    bodies = methods(src, ["create_batch_menu_fallback", "generate_autorun"])
    used = {n.id for body in bodies for n in ast.walk(ast.parse(body)) if isinstance(n, ast.Name)}
    ns = {"os": os, "sys": sys, "shutil": shutil, "re": re, "json": json, "unicodedata": unicodedata}
    exec(module_closure(src, used), ns)
    exec("class Host:\n" + textwrap.indent("\n\n".join(bodies), "    "), ns)

    for title in TITLES:
        base = tempfile.mkdtemp(prefix="rialto_titles_")
        try:
            h = ns["Host"]()
            h.log = []
            h.update_status = h.log.append
            h.entries = {"Title": Var(title), "Developer": Var("Studio"), "Publisher": Var(""),
                         "Start Menu Name": Var(title)}
            h.disc_name_var = Var(title)
            h.disc_icon_var = Var("")
            crashed = None
            try:
                h.create_batch_menu_fallback(base)
                h.generate_autorun(base)
            except Exception as error:  # the behaviour under test
                crashed = error
            ok("%s: the helper files are written without a crash" % title, crashed is None, repr(crashed))
            ok("%s: menu.bat exists" % title, os.path.isfile(os.path.join(base, "menu.bat")))
            autorun = os.path.join(base, "autorun.inf")
            text = open(autorun, encoding="cp1252").read() if os.path.isfile(autorun) else ""
            ok("%s: autorun.inf exists and still opens setup.exe" % title,
               "[AutoRun]" in text and "Open=setup.exe" in text)
            ok("%s: nothing was logged as a failure" % title, not any("Failed" in line for line in h.log),
               "; ".join(h.log))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        sys.exit(1)
    print("every title builds its helper files.")


if __name__ == "__main__":
    main()
