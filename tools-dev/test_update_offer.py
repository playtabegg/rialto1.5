"""Check for a New Rialto offers the download (1.5.1, launch day).

The real _on_new_rialto_checked, lifted out of Rialto.pyw and run on a stand-in window: when the signed
feed names a newer Rialto, the person is asked once and the browser gets the download itself. A portable
copy (no uninstaller beside it) is offered the zip; a copy installed by Rialto's Setup (its
unins000.dat beside it) is offered the new version's Setup, Rialto-X.Y.Z-Setup.exe, from the same release; an address the browser may not have
(not https, not github.com or updates.wetheindies.com) falls back to the release page. The words never
name "Rialto.exe and menu.exe" again: the release page offers neither.

Source-extracted: no window opens, nothing is fetched.
"""
import ast
import os
import sys
import tempfile
import types
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, os.path.dirname(RIALTO))

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def handler():
    src = open(RIALTO, encoding="utf-8").read()
    tree = ast.parse(src)
    app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    fn = next(n for n in app.body if isinstance(n, ast.FunctionDef) and n.name == "_on_new_rialto_checked")
    return ast.get_source_segment(src, fn)


def run(url, installed, notes="https://github.com/playtabegg/rialto1.5/releases/tag/v1.5.2"):
    root = tempfile.mkdtemp(prefix="rialto_offer_")
    if installed:
        open(os.path.join(root, "unins000.dat"), "wb").close()
    ns = {"os": os, "__version__": "1.5.1", "APP_ROOT": root}
    exec("class Stub:\n" + "\n".join("    " + line for line in handler().splitlines()), ns)
    stub = ns["Stub"]()
    asked, opened = [], []
    stub.update_status = lambda text: None
    stub.show_centered_popup = lambda title, text, kind="ok": asked.append(text) or True
    real_open = webbrowser.open
    webbrowser.open = lambda target, *a, **k: opened.append(target)
    try:
        release = types.SimpleNamespace(url=url, notes_url=notes, version="1.5.2")
        outcome = types.SimpleNamespace(release=release, sentence="Rialto 1.5.2 is out. You have 1.5.1.",
                                        look_yourself=False)
        stub._on_new_rialto_checked(outcome)
    finally:
        webbrowser.open = real_open
    return asked, opened


ZIP = "https://github.com/playtabegg/rialto1.5/releases/download/v1.5.2/Rialto-1.5.2-Disc-Maker.zip"
SETUP = "https://github.com/playtabegg/rialto1.5/releases/download/v1.5.2/Rialto-1.5.2-Setup.exe"
# 1.5.0's stable zip name: an installed copy still gets the Setup named for the feed's version.
OLD_ZIP = "https://github.com/playtabegg/rialto1.5/releases/download/v1.5.2/Rialto-1.5-Disc-Maker.zip"


def main():
    print("Check for a New Rialto, when a newer one is out")
    asked, opened = run(ZIP, installed=False)
    says("a portable copy is asked once and handed the zip", opened == [ZIP] and len(asked) == 1, (asked, opened))
    says("and told to unzip it somewhere new", asked and "Unzip the whole folder" in asked[0], asked)
    says("the question says which Rialto is out and which one this is", asked and asked[0].startswith(
        "Rialto 1.5.2 is out. You have 1.5.1."), asked)
    asked, opened = run(SETUP, installed=False)
    says("a portable copy offered a Setup is told it installs a new copy, its own settings left where they are",
         opened == [SETUP] and asked and "this copy and its settings stay where they are" in asked[0], (asked, opened))
    asked, opened = run(ZIP, installed=True)
    says("an installed copy is handed the Setup from the same release", opened == [SETUP], opened)
    says("and told its settings and profiles stay", asked and "settings and profiles stay" in asked[0], asked)
    says("and the Setup is named for the feed's version, Rialto-1.5.2-Setup.exe",
         asked and "Rialto-1.5.2-Setup.exe" in asked[0], asked)
    asked, opened = run(OLD_ZIP, installed=True)
    says("a zip with the old stable name still leads an installed copy to the version's Setup",
         opened == [SETUP], opened)
    for bad in ("http://github.com/x/Rialto-1.5.2-Disc-Maker.zip", "https://objects.githubusercontent.com/x.zip",
                "https://example.com/Rialto-1.5.2-Disc-Maker.zip", "", r"https://evil.example\@github.com/x.zip",
                "https://github.com:8443/x.zip", "https://github.com/x/notes.html"):
        asked, opened = run(bad, installed=False)
        says("a download address the browser may not have falls back to the release page: %r" % bad,
             opened == ["https://github.com/playtabegg/rialto1.5/releases/tag/v1.5.2"]
             and asked and "release page" in asked[0], (asked, opened))
    asked, opened = run("", installed=False, notes="https://evil.example/notes")
    says("and a notes page the browser may not have falls back to the releases page",
         opened == ["https://github.com/playtabegg/rialto1.5/releases/latest"], opened)
    words = [n.value for n in ast.walk(ast.parse("class Stub:\n" + "\n".join("    " + line for line in handler().splitlines())))
             if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    says("the words a person sees never name menu.exe", not any("menu.exe" in w for w in words), words)
    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll update-offer checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
