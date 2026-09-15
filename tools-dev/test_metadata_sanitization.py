"""profile JSON cannot inject commands into generated scripts.

A Title carrying CR/LF/%/!/& used to become extra batch lines (RCE on the
author's machine via the auto-run compatibility test, and on every player's
machine via menu.bat) and a raw autorun.inf Label=. sanitize_text strips
controls at load and at each generator; the two batch writers also neutralize
% and ! and caret-escape the rest.
"""
import ast
import os
import re
import shutil
import sys
import tempfile
import textwrap

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def says(label, condition, detail=""):
    print(f"  [{'OK  ' if condition else 'FAIL'}] {label}{(' -> ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


def extract_funcs(src, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            seen.add(node.name)
        elif isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in names:
            out.append(ast.get_source_segment(src, node))
            seen.add(node.targets[0].id)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract {sorted(missing)}")
    return "\n\n".join(out)


def extract_methods(src, class_name, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    seen.add(item.name)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


class Box:
    """Stands in for a tk.Entry / StringVar."""
    def __init__(self, value=""):
        self._v = value

    def get(self):
        return self._v

    def set(self, value):
        self._v = value

    def delete(self, *a, **k):
        self._v = ""

    def insert(self, index, value):
        self._v = value


def make_host(src, extra_globals=None, **attrs):
    helpers = extract_funcs(src, [
        "_CONTROL_CHARS", "sanitize_text", "sanitize_profile_data", "escape_batch",
    ])
    methods = extract_methods(src, "RialtoApp", [
        "create_compatibility_test_script", "create_batch_menu_fallback",
        "detect_primary_game_exe",
        "generate_autorun", "generate_readme",
    ])
    ns = {"os": os, "sys": sys, "shutil": shutil, "re": __import__("re")}
    ns.update(extra_globals or {})
    exec(helpers, ns)
    exec("class Host:\n" + textwrap.indent(methods, "    "), ns)
    host = ns["Host"]()
    for k, v in attrs.items():
        setattr(host, k, v)
    host.update_status = lambda msg: None
    host.run_compatibility_test = lambda *a, **k: None
    return host, ns


def calls_name(func_src, name):
    tree = ast.parse(func_src)
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
               for n in ast.walk(tree))


def main():
    src = open(RIALTO, encoding="utf-8").read()
    host, ns = make_host(src)
    sanitize_text = ns["sanitize_text"]
    sanitize_profile_data = ns["sanitize_profile_data"]
    escape_batch = ns["escape_batch"]

    print("1. sanitize_text strips C0/C1/DEL, keeps the rest")
    check("CR/LF/TAB gone", sanitize_text("A\r\n\tB"), "AB")
    check("NUL and BEL gone", sanitize_text("A\x00\x07B"), "AB")
    check("DEL gone", sanitize_text("A\x7fB"), "AB")
    check("C1 gone", sanitize_text("A\x9bB"), "AB")
    check("ordinary text kept", sanitize_text("Mock & Co"), "Mock & Co")
    check("None becomes empty", sanitize_text(None), "")
    print()

    print("2. escape_batch: %, !, and caret-escaped metacharacters")
    escaped = escape_batch("x%USERNAME%! & y")
    says("no CR/LF", "\r" not in escaped and "\n" not in escaped)
    says("no unescaped %USERNAME%", re.search(r"(?<!%)%USERNAME%(?!%)", escaped) is None)
    says("% doubled", "%%USERNAME%%" in escaped)
    says("! stripped", "!" not in escaped)
    says("& caret-escaped", "^&" in escaped)
    print()

    print("3. load boundary: profile JSON strings are sanitized")
    poison_title = "Game\r\ncalc.exe\n%USERNAME%! & Boom"
    profile = {
        "Title": poison_title,
        "Developer": "Studio\nX",
        "GameExecutables": ["play\nme.exe"],
        "SteamButton": True,
    }
    loaded = sanitize_profile_data(profile)
    check("Title has no CR/LF", loaded["Title"], "Gamecalc.exe%USERNAME%! & Boom")
    check("Developer has no newline", loaded["Developer"], "StudioX")
    check("nested list string sanitized", loaded["GameExecutables"], ["playme.exe"])
    check("non-strings pass through", loaded["SteamButton"], True)
    says("load_profile calls sanitize_profile_data",
         calls_name(extract_methods(src, "RialtoApp", ["load_profile"]),
                    "sanitize_profile_data"))
    says("load_last_used_profile calls sanitize_profile_data",
         calls_name(extract_methods(src, "RialtoApp", ["load_last_used_profile"]),
                    "sanitize_profile_data"))
    print()

    print("4. the three generators against a poisoned Title")
    base = tempfile.mkdtemp(prefix="rialto_sanitize_")
    try:
        clean_dir = os.path.join(base, "clean")
        poison_dir = os.path.join(base, "poison")
        os.makedirs(clean_dir)
        os.makedirs(poison_dir)

        host.entries = {"Title": Box("Safe Title")}
        host.disc_name_var = Box("")
        host.disc_icon_var = Box("")
        host.remove_wti_branding = Box(True)
        host.remove_wti_branding.get = lambda: True
        host.create_compatibility_test_script(clean_dir)
        host.create_batch_menu_fallback(clean_dir)
        host.generate_autorun(clean_dir)
        host.generate_readme(clean_dir, {"Title": "Safe Title"})
        clean_compat = open(os.path.join(clean_dir, "compatibility_test.bat"),
                            encoding="utf-8").read()
        clean_lines = len(clean_compat.splitlines())

        host.entries = {"Title": Box(loaded["Title"])}
        host.disc_name_var = Box(loaded["Title"])
        host.create_compatibility_test_script(poison_dir)
        host.create_batch_menu_fallback(poison_dir)
        host.generate_autorun(poison_dir)
        host.generate_readme(poison_dir, {"Title": loaded["Title"]})

        compat = open(os.path.join(poison_dir, "compatibility_test.bat"),
                      encoding="utf-8").read()
        menu = open(os.path.join(poison_dir, "menu.bat"), encoding="utf-8").read()
        autorun = open(os.path.join(poison_dir, "autorun.inf"),
                       encoding="cp1252").read()
        readme = open(os.path.join(poison_dir, "README.txt"), encoding="utf-8").read()

        says("compatibility_test.bat line count unchanged (no injected lines)",
             len(compat.splitlines()) == clean_lines,
             f"{len(compat.splitlines())} vs {clean_lines}")
        says("no standalone calc.exe line in the test script",
             not any(line.strip().lower() == "calc.exe" for line in compat.splitlines()))

        title_lines = [l for l in compat.splitlines() if "Compatibility Test" in l]
        says("compatibility title line exists", bool(title_lines))
        if title_lines:
            line = title_lines[0]
            says("compat title has no CR/LF", "\r" not in line and "\n" not in line)
            says("compat title has no unescaped %USERNAME%",
                 re.search(r"(?<!%)%USERNAME%(?!%)", line) is None)
            says("compat title has %%USERNAME%%", "%%USERNAME%%" in line)
            says("compat title has no !", "!" not in line)
            says("compat title has ^&", "^&" in line)

        menu_title_lines = [l for l in menu.splitlines()
                            if l.lower().lstrip().startswith("title ")]
        says("menu.bat title line exists", bool(menu_title_lines))
        if menu_title_lines:
            line = menu_title_lines[0]
            says("menu.bat title has no CR/LF", "\r" not in line and "\n" not in line)
            says("menu.bat title has no unescaped %USERNAME%",
                 re.search(r"(?<!%)%USERNAME%(?!%)", line) is None)
            says("menu.bat title has no !", "!" not in line)
            says("menu.bat title has ^&", "^&" in line)

        labels = [l for l in autorun.replace("\r\n", "\n").splitlines()
                  if l.lstrip().startswith("Label=")]
        says("autorun Label= is one line", len(labels) == 1, repr(labels))
        if labels:
            value = labels[0].split("=", 1)[1]
            says("autorun Label has no CR/LF", "\r" not in value and "\n" not in value)
            says("autorun Label is not a new INF section", "[" not in value)

        # The wording moved from "thank you for installing" to "thank you for
        # buying" when the disc's three read-me files became one. What is being
        # checked has not moved: a poisoned title must not break that line.
        greeting = "thank you for buying"
        says("README title has no CR/LF injected section",
             "calc.exe" not in readme.split(greeting, 1)[-1].split("!", 1)[0]
             or "\n" not in readme.split(greeting, 1)[-1].split("!", 1)[0])
        thanks = [l for l in readme.splitlines() if greeting in l]
        says("README greeting is one line", len(thanks) == 1, repr(thanks))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print()

    print("5. create_iso volume label and generate_readme call sanitize_text")
    create_iso = extract_methods(src, "RialtoApp", ["create_iso"])
    generate_readme = extract_methods(src, "RialtoApp", ["generate_readme"])
    says("create_iso calls sanitize_text", calls_name(create_iso, "sanitize_text"))
    says("generate_readme calls sanitize_text", calls_name(generate_readme, "sanitize_text"))
    print()

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all metadata-sanitization checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
