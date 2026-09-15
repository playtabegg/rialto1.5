"""Check the Inno Setup script Rialto writes, against real metadata.

installer.iss is the highest-consequence thing Rialto produces: ISCC compiles
it into setup.exe, Rialto signs that with the author's certificate, and it goes
out to every buyer. A title that can add its own directives is arbitrary code
running on a player's machine under a signature they have reason to trust.

generate_enhanced_installer_script is pulled out by source extraction and run
on a stub, so no tkinter and no ISCC are needed.
"""
import ast
import re
import os
import shutil
import sys
import tempfile
import textwrap

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


def build_host(src):
    """A stub carrying just what generate_enhanced_installer_script touches."""
    tree = ast.parse(src)
    wanted = {"generate_enhanced_installer_script"}
    methods = [textwrap.dedent(ast.get_source_segment(src, item))
               for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
               for item in node.body
               if isinstance(item, ast.FunctionDef) and item.name in wanted]
    if not methods:
        raise SystemExit("could not extract generate_enhanced_installer_script")

    # iss_value leans on module-level constants. Rather than naming them here
    # and letting the list rot, take whatever globals it actually reads.
    helper = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "iss_value")
    reads = {n.id for n in ast.walk(helper)
             if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    constants = [ast.get_source_segment(src, node) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and getattr(node.targets[0], "id", "") in reads]
    module = constants + [ast.get_source_segment(src, helper)]

    ns = {"os": os, "re": __import__("re"), "shutil": shutil}
    exec("\n\n".join(module), ns)
    exec("class Host:\n" + textwrap.indent("\n\n".join(methods), "    "), ns)
    host = ns["Host"]()
    host.update_status = lambda message: None
    host.get_disk_slice_size = lambda: None
    return host, ns


def generate(host, meta):
    out = tempfile.mkdtemp(prefix="rialto_iss_")
    host.generate_enhanced_installer_script(out, meta)
    path = os.path.join(out, "installer.iss")
    with open(path, encoding="utf-8") as f:
        return f.read(), out


def directives(script, section):
    """The lines of one [Section], excluding the header."""
    lines, collecting = [], False
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            collecting = stripped.lower() == "[" + section.lower() + "]"
            continue
        if collecting and stripped:
            lines.append(stripped)
    return lines


def in_root_save_patterns(src):
    """`in_root_saves` as the generator declares it: [(pattern, dest), ...].

    Player data that lives inside the install root. The wildcard must not
    sweep it up (a reinstall would overwrite the save), so each pattern
    gets its own `onlyifdoesntexist uninsneveruninstall` entry - which
    means each also appears as a `Source:` line, and any assertion about
    [Files] has to know that.
    """
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_enhanced_installer_script":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) \
                        and getattr(sub.targets[0], "id", "") == "in_root_saves":
                    return ast.literal_eval(sub.value)
    raise SystemExit("`in_root_saves` not found in generate_enhanced_installer_script")


def main():
    src = open(RIALTO, encoding="utf-8").read()
    host, ns = build_host(src)
    iss_value = ns["iss_value"]

    print("1. an ordinary title")
    script, out = generate(host, {"Title": "My Robot Game",
                                  "Developer": "Jane Smith"})
    says("AppName is the title verbatim",
         "AppName=My Robot Game" in script)
    says("AppPublisher is the developer",
         "AppPublisher=Jane Smith" in script)
    says("installs under C:\\Games",
         "DefaultDirName=C:\\Games\\My Robot Game" in script)
    says("the menu is what the shortcuts point at",
         all("menu\\menu.exe" in line for line in directives(script, "Icons")))
    shutil.rmtree(out, ignore_errors=True)
    print()

    print("2. punctuation a real title might carry survives where it is shown")
    script, out = generate(host, {"Title": "Game: The Sequel", "Developer": "A & B"})
    says("a colon survives in the displayed name", "AppName=Game: The Sequel" in script)
    says("but not in the folder name",
         "DefaultDirName=C:\\Games\\Game The Sequel" in script)
    says("an ampersand is left alone", "AppPublisher=A & B" in script)
    shutil.rmtree(out, ignore_errors=True)
    print()

    print("3. a title that tries to add its own directives")
    hostile = 'Game\n[Run]\nFilename: "cmd.exe"; Parameters: "/c calc"'
    script, out = generate(host, {"Title": hostile, "Developer": "X"})
    runs = directives(script, "Run")
    says("only the one [Run] line Rialto writes", len(runs) == 1, repr(runs))
    says("and it starts the menu, not cmd", runs and runs[0].startswith('Filename: "{app}\\menu\\menu.exe"'))
    # cmd.exe does survive as text - inside AppName's value, which Inno reads to
    # end of line, and inside the shortcut's display name. Neither is a target.
    # The invariant that matters is what actually gets executed or installed:
    # every Filename: and every Source: in the whole script.
    # the lookbehind keeps IconFilename: out of it
    targets = re.findall(r'(?<![A-Za-z])Filename:\s*"([^"]*)"', script)
    sources = re.findall(r'Source:\s*"([^"]*)"', script)
    says("every Filename: is the disc menu",
         targets and set(targets) == {"{app}\\menu\\menu.exe"}, repr(sorted(set(targets))))
    # The save patterns are Source: lines Rialto writes on every build, so
    # the question is whether the TITLE added one, not how many there are.
    injected = set(sources) - {p for p, _dest in in_root_save_patterns(src)}
    says("no Source: was injected", injected == {"*"}, repr(sorted(injected)))
    says("no [Code] section was injected", script.count("[Code]") == 0)
    says("generated installer.iss contains no function IsWin64",
         "function IsWin64" not in script)
    shutil.rmtree(out, ignore_errors=True)
    print()

    print("4. titles that are really paths")
    # Taking the separators out is not enough - a component of only dots is
    # still navigation, and Windows resolves device names at any depth.
    for title, why in [(r"..\..\Windows\System32", "traversal"),
                       ("..", "parent folder"),
                       (".", "the Games folder itself"),
                       ("  ..  ", "padded parent"),
                       ("NUL", "device name"),
                       ("COM1", "device name"),
                       ("trailing.", "trailing dot Windows would drop")]:
        script, out = generate(host, {"Title": title, "Developer": "X"})
        line = [l for l in script.splitlines() if l.startswith("DefaultDirName=")][0]
        tail = line.split("=", 1)[1]
        resolved = os.path.abspath(tail)
        contained = (resolved.lower().startswith("c:\\games\\")
                     and resolved.lower() != "c:\\games\\"
                     and "\\" not in tail.split("C:\\Games\\", 1)[1])
        says(f"{why}: {title!r} stays inside C:\\Games", contained, resolved)
        shutil.rmtree(out, ignore_errors=True)
    print()

    print("5. every [Setup] value stays on its own line")
    script, out = generate(host, {"Title": "A\r\nB\x00C", "Developer": "D\nE"})
    setup = directives(script, "Setup")
    says("no directive line is empty or orphaned", all("=" in line for line in setup))
    check("AppName survived as one line",
          [l for l in setup if l.startswith("AppName=")], ["AppName=ABC"])
    shutil.rmtree(out, ignore_errors=True)
    print()

    print("6. no hand-written [Registry] section")
    # Inno's own CreateUninstallRegKey=yes writes <AppName>_is1 with everything
    # Windows needs. The section that used to be here duplicated four of those
    # values with an unquoted UninstallString and no uninsdeletekey, so it broke
    # on any path with a space and was orphaned on every uninstall.
    script, out = generate(host, {"Title": "My Game", "Developer": "X"})
    says("no [Registry] section", "[Registry]" not in script)
    says("Inno is asked to make the uninstall key", "CreateUninstallRegKey=yes" in script)
    says("with a display icon", "UninstallDisplayIcon=" in script)
    says("and a display name", "UninstallDisplayName=" in script)
    shutil.rmtree(out, ignore_errors=True)
    print()

    print("7. iss_value on its own")
    check("empty falls back", iss_value(""), "Game")
    check("None falls back", iss_value(None, "Indie Developer"), "Indie Developer")
    check("all-metacharacter falls back", iss_value('{{{";'), "Game")
    check("length capped", len(iss_value("A" * 400)), 120)
    print()

    print("8. vcredist Source lines only when the files exist")
    # The in-root save patterns each get their own Source: line, so this
    # asks about the RUNTIME entries specifically rather than about the
    # whole [Files] section. Written as a subtraction against the same
    # list the generator declares, so adding an engine to `in_root_saves`
    # does not make this harness fail for the wrong reason - which is
    # exactly what an earlier version of this check did.
    saves = {pattern for pattern, _dest in in_root_save_patterns(src)}
    out = tempfile.mkdtemp(prefix="rialto_iss_rt_")
    try:
        host.generate_enhanced_installer_script(out, {"Title": "T", "Developer": "D"})
        script = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        sources = set(re.findall(r'Source:\s*"([^"]*)"', script))
        says("every save pattern gets its own [Files] entry",
             saves <= sources, repr(sorted(saves - sources)))
        says("absent runtimes are not listed in [Files]",
             sources - saves == {"*"}, repr(sorted(sources - saves)))
        open(os.path.join(out, "vcredist_x86.exe"), "wb").write(b"MZ")
        open(os.path.join(out, "vcredist_x64.exe"), "wb").write(b"MZ")
        host.generate_enhanced_installer_script(out, {"Title": "T", "Developer": "D"})
        script = open(os.path.join(out, "installer.iss"), encoding="utf-8").read()
        sources = set(re.findall(r'Source:\s*"([^"]*)"', script))
        says("verified runtimes that are on disk are packaged",
             sources - saves == {"*", "vcredist_x86.exe", "vcredist_x64.exe"},
             repr(sorted(sources - saves)))
    finally:
        shutil.rmtree(out, ignore_errors=True)
    print()

    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  " + f)
        return 1
    print("all installer-script checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
