"""The 1.5.1 interface review stays fixed (18 October 2026).

A read-only review of Rialto 1.5.1's interface found words that disagreed,
tooltips that were wrong or missing, a Help Guide that had fallen behind the
window, British spellings, and a version nobody could read without a build.
This reads the strings a person sees (every string in Rialto.pyw that is not
a docstring and not the disc menu's own source), the Help Guide, the signing
guide, README.md and SIGNING.md, and runs doc_path for real against a pretend
frozen Rialto. Nothing here opens a window; test_fits_every_screen.py measures
the page and the dialogs.
"""
import ast
import html
import os
import re
import shutil
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


src = read("Rialto.pyw")
flat = src.replace("\r\n", "\n")
tree = ast.parse(src)
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
guide = read(os.path.join("docs", "rialto-guide.html")).replace("\r\n", "\n")
signing_guide = read(os.path.join("docs", "signing-guide.html")).replace("\r\n", "\n")
readme = read("README.md")
signing_md = read("SIGNING.md")
version = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
               and getattr(n.targets[0], "id", "") == "__version__")


def method(name, owner=app):
    node = next(i for i in owner.body if isinstance(i, ast.FunctionDef) and i.name == name)
    return node, textwrap.dedent(ast.get_source_segment(src, node))


# The strings a person can see: not docstrings, not the disc menu's source.
skip = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
            skip.add(id(body[0].value))
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE":
        skip.add(id(node.value))
seen = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in skip]
words = "\n".join(seen)


def page_text(markup):
    """A page's words: no style block, no tags."""
    body = re.sub(r"<style.*?</style>", " ", markup, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


guide_words = page_text(guide)

print("1-3. closing, the live line and Preview are proved in test_build_watch.py and test_bonus_staging.py")
ok("Preview's tooltip says where a disc of several games shows its page",
   "On a disc of several games, Play \"\n                             \"Games opens the Choose Your Game page." in flat)
ok("and no longer says Play is switched off", "Play and Uninstall are switched off" not in flat)
print()

print("4. one name for the page of games: the Choose Your Game page")
bad = [s for s in seen if re.search(r"Play page|Choose Your Game screen|Choose your game(?! folder)", s)]
ok("no string a person sees calls it anything else", not bad, bad)
ok("nor the Help Guide", not re.search(r"Play page|Choose Your Game screen|a Choose Your Game page", guide_words),
   re.findall(r".{30}(?:Play page|Choose Your Game screen|a Choose Your Game page).{30}", guide_words))
ok("nor the README", "Choose Your Game screen" not in readme and "Play page" not in readme)
ok("and the dialog, its tooltips and the guide use the name",
   words.count("Choose Your Game page") >= 6 and "the Choose Your Game page" in guide_words)
print()

print("5. the Compression box has a visible label on the Target Media row")
row = flat[flat.index('media_row = ttk.Frame(self.disc_frame)'):flat.index('# === Artwork ===')]
ok("a Compression: label, made just before its box, in the same row",
   'ttk.Label(media_row, text="Compression:")' in row
   and row.index('text="Compression:"') < row.index("compression_combo = ttk.Combobox(media_row"))
ok("the label carries the box's tooltip", "ToolTip(compression_label, compression_tip)" in row
   and "ToolTip(compression_combo, compression_tip)" in row)
print()

print("6. tooltips that teach, not ones that are wrong or read like a changelog")
# Every tooltip's words, and every *_tip string a tooltip is handed by name.
tips = "\n".join(ast.unparse(c.args[1]) for c in ast.walk(app) if isinstance(c, ast.Call)
                 and getattr(c.func, "id", "") == "ToolTip" and len(c.args) > 1)
tips += "\n" + "\n".join(ast.unparse(a.value) for a in ast.walk(app) if isinstance(a, ast.Assign)
                         and ast.unparse(a.targets[0]).endswith("tip"))
for stale in ("usually smaller", "every earlier Rialto", "takes longer to install",
              "about the same install time", "check each game"):
    ok("nothing says %r" % stale, stale not in words and stale not in guide_words)
ok("no tooltip and no part of the guide says 'for now'", "for now" not in tips and "for now" not in guide_words)
ok("the meter tells Fastest install apart", "with Fastest install about the same" in flat.replace('"\n                     "', ""))
ok("BUILD's tooltip names the live line", "says how far it has got and for how long" in flat.replace('"\n                           "', ""))
ok("the Games on Disc row teaches the per-folder scan", "Find a game in each folder do it" in flat.replace('"\n                   "', ""))
print()

print("7. every control in the Build Queue, Files to Place and Games on Disc teaches what it does")
for name in ("configure_build_queue", "configure_placed_files", "configure_game_exes"):
    node, body = method(name)
    tipped = {ast.unparse(c.args[0]) for c in ast.walk(node) if isinstance(c, ast.Call)
              and getattr(c.func, "id", "") == "ToolTip" and c.args}
    untaught = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and ast.unparse(sub.func) in ("ttk.Button", "ttk.Combobox", "ttk.Entry", "ttk.Treeview"):
            text = next((ast.unparse(k.value) for k in sub.keywords if k.arg == "text"), "")
            if text.strip("'\"") in ("Save", "Cancel", "Close"):
                continue
            parent = next((a for a in ast.walk(node) if isinstance(a, ast.Assign) and a.value is sub), None)
            target = ast.unparse(parent.targets[0]) if parent else None
            if target not in tipped:
                untaught.append(text or ast.unparse(sub)[:60])
    ok("%s: every button, box and list has a tooltip" % name, not untaught, untaught)
ok("the three-steps card's Show / Hide has one", "ToolTip(self.tutorial_toggle," in flat)
print()

print("8. a menu and a button for the same thing use the same words")
menu_labels = set(re.findall(r'\("([^"]+?)…?", self\.(?:import_gog_installer|export_msix|toggle_theme)\)', flat))
ok("Import GOG, Export .msix and Dark / Light read the same in the menu and on the button",
   menu_labels == {"Import GOG", "Export .msix", "Dark / Light"}
   and all('"%s", self.%s' % (label, fn) in flat for label, fn in
           (("Import GOG", "import_gog_installer"), ("Export .msix", "export_msix"), ("Dark / Light", "toggle_theme"))),
   menu_labels)
ok("the Build Queue names BUILD GAME INSTALLER as the button reads", "exactly as\\nBUILD GAME INSTALLER would" in flat)
ok("Files to Place: the column and the tick box are both Remove on uninstall",
   '("remove", "Remove on uninstall", 130)' in flat and '"Remove on uninstall", remove_var' in flat)
ok("the guide never asks for a tick box Games on Disc does not have", "Tick two or more games" not in guide)
print()

print("9. the Help Guide: its contents, The Build Queue, Windows 7, a short screen, the media names")
nav = guide[guide.index('<nav class="contents">'):guide.index("</nav>")]
for anchor, heading in (("games", "Games on Disc"), ("compression", "Compression"), ("queue", "The Build Queue"),
                        ("pressing", "Pressing your disc")):
    ok("the contents link to %s" % heading, '<a href="#%s">%s</a>' % (anchor, heading) in nav
       and ('id="%s"' % anchor) in guide)
ok("Many games, one run is now The Build Queue", "Many games, one run" not in guide and "<h3 id=\"queue\">The Build Queue</h3>" in guide)
ok("a part for Windows 7 and 8 that says how it was checked",
   'id="windows7"' in guide and "not on a Windows 7 PC" in guide_words and "compatibility mode" in guide_words)
ok("a part for how Rialto fits a short screen", 'id="short-screen"' in guide and "nothing scrolls" in guide_words)
media_names = [ast.literal_eval(e.elts[0]) for e in next(
    n for n in app.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MEDIA_TYPES").value.elts]
table = guide[guide.index('<h2 id="media">'):guide.index("</table>", guide.index('<h2 id="media">'))]
rows = [html.unescape(m) for m in re.findall(r"<tr><td>([^<]+)</td>", table)]
ours = [m for m in media_names if not m.startswith("Mini")]
ok("every Target Media choice has its row in the guide, by the name the box shows",
   all(m in rows for m in ours), [m for m in ours if m not in rows])
ok("and every row is a name the box shows", all(r in media_names for r in rows), [r for r in rows if r not in media_names])
print()

print("10. a frozen Rialto shows the guide it carries, not an older copy beside it")
node, doc_src = method("doc_path")
work = tempfile.mkdtemp(prefix="rialto_docpath_")
try:
    app_root, bundle = os.path.join(work, "Rialto"), os.path.join(work, "_MEI1234")
    for folder in (os.path.join(app_root, "docs"), os.path.join(bundle, "docs")):
        os.makedirs(folder)
    with open(os.path.join(app_root, "docs", "rialto-guide.html"), "w") as f:
        f.write("the 1.5.0 guide an older Rialto left here")
    with open(os.path.join(bundle, "docs", "rialto-guide.html"), "w") as f:
        f.write("the guide this Rialto carries")
    fake_sys = type("FakeSys", (), {"_MEIPASS": bundle})()
    ns = {"os": os, "shutil": shutil, "sys": fake_sys, "APP_ROOT": app_root, "tempfile": tempfile}
    exec(next(ast.get_source_segment(src, n) for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "same_file_bytes"), ns)
    exec("class Host:\n" + textwrap.indent(doc_src, "    "), ns)
    got = ns["Host"]().doc_path("rialto-guide.html")
    ok("frozen: the bundled guide wins over the older copy",
       got and open(got).read() == "the guide this Rialto carries", got and open(got).read())
    ok("and is copied out beside Rialto, where the browser can keep it",
       os.path.normcase(got or "") == os.path.normcase(os.path.join(app_root, "docs", "rialto-guide.html")))
    ns["sys"] = type("FakeSys", (), {})()
    with open(os.path.join(app_root, "docs", "rialto-guide.html"), "w") as f:
        f.write("the repo's guide")
    got = ns["Host"]().doc_path("rialto-guide.html")
    ok("a source run reads the repo's docs/", got and open(got).read() == "the repo's guide")
finally:
    shutil.rmtree(work, ignore_errors=True)
print()

print("11. every build starts clean, and says so first")
_n, build_src = method("build_all")
ok("one line before the clearing names it",
   build_src.index('self.update_status(f"🧹 Clearing the last build of {game_name} to start fresh: "')
   < build_src.index("for stale in os.listdir(output_path):"))
ok("and the guide says so", "Every build starts clean" in guide_words and "earlier disc images included" in guide_words)
print()

print("12. American spelling in what a person reads")
british = r"\b(cancell\w*|favourit\w*|organis\w*|labelled|recognis\w*|centre|colour\w*|behaviour\w*)\b"
ok("Rialto.pyw's strings", not re.findall(british, words, re.I), re.findall(british, words, re.I))
for label, text in (("the Help Guide", guide_words), ("the signing guide", page_text(signing_guide)),
                    ("README.md", readme), ("SIGNING.md", signing_md)):
    ok(label, not re.findall(british, text, re.I), re.findall(british, text, re.I))
prompt = next(n.value for n in app.body if isinstance(n, ast.Assign)
              and getattr(n.targets[0], "id", "") == "SIGNING_AI_PROMPT")
prompt_text = ast.literal_eval(prompt) if isinstance(prompt, ast.Constant) else ast.unparse(prompt)
ok("the AI prompt and its copy in the signing guide agree on the words fixed",
   all(w in prompt_text and w in signing_guide for w in ("organization path", "labeled list")))
print()

print("12b. a bare Alt never freezes a build (launch day: the Build Queue sat in Windows' menu mode)")
ok("every themed dialog and every popup ignores a bare Alt or F10",
   flat.count("quiet_alt_tap(dialog)") == 1 and flat.count("quiet_alt_tap(popup)") == 1)
ok("the main window ignores it only while a build runs, so its menus stay a keypress away otherwise",
   'quiet_alt_tap(root, when=lambda: getattr(app, "_building", False))' in flat)
ok("only a bare Alt or F10 (SC_KEYMENU with no key) is swallowed: Alt+Space and Alt+letter pass on",
   "(wparam & 0xFFF0) == 0xF100 and lparam == 0" in flat and "_QUIET_ALT_HOOKS.append" in flat)
print()

print("12c. an update asks for Rialto to be closed (launch day: Restart Manager left Rialto.exe held)")
_iss = read(os.path.join("packaging", "rialto-setup.iss"))
_names = re.findall(r'CreateMutexW\(None, False, "([^"]+)"\)', flat)
ok("Rialto holds one named mutex while it runs, and Rialto's Setup watches the same name",
   len(_names) == 1 and ("AppMutex=" + _names[0]) in _iss, (_names, re.findall(r"AppMutex=\S+", _iss)))
print()

print("13. the version, where a person can read it without a build")
_n, check_src = method("check_for_new_rialto")
ok("Help > Check for a New Rialto says which Rialto this is before it asks anything",
   'f"You have Rialto {__version__}.\\n\\n"' in check_src
   and check_src.index("You have Rialto") < check_src.index("threading.Thread("))
_n, answer_src = method("_on_new_rialto_checked")
ok("and in each answer (no feed published yet, any other; a newer one says it in its own sentence: "
   "\"Rialto 1.5.2 is out. You have 1.5.1.\")",
   answer_src.count("You have Rialto {__version__}") == 2 and "outcome.sentence" in answer_src
   and '"Rialto %s is out. You have %s."' in read(os.path.join("rialto", "update", "check.py")))
ok("a newer Rialto is one click away: the signed feed's download, handed to the browser only on github.com",
   "browser_url(outcome.release.url)" in answer_src and "Rialto.exe and \"" not in answer_src)
ok("the Help Guide's footer and masthead carry %s" % version,
   "<strong>Rialto %s</strong> &middot; Built by Chandler" % version in guide
   and "Version %s</p>" % version in guide)
ok("the window's own title strip names the version it is: Rialto 1.5.1, from __version__",
   'text=f"Rialto {__version__}"' in flat and 'f"{APP_NAME} {__version__} - Disc Builder"' in flat)
print()

print("14. the Choose Your Game page keeps every star in view, and Preview never writes through to the game folder")
menu_src = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE")
menu_tree = ast.parse(menu_src)
chooser = next(n for n in ast.walk(menu_tree) if isinstance(n, ast.FunctionDef) and n.name == "show_game_chooser")
breakable_node = next(n for n in ast.walk(chooser) if isinstance(n, ast.FunctionDef) and n.name == "breakable")
breakable_ns = {}
exec(textwrap.dedent(ast.get_source_segment(menu_src, breakable_node)), breakable_ns)
broken = breakable_ns["breakable"]("Sky_Quest_Definitive_Remastered_Edition_2026")
ok("a long name with no space gets places to wrap, and reads the same",
   broken.count("​") >= 3 and broken.replace("​", "") == "Sky_Quest_Definitive_Remastered_Edition_2026")
ok("an ordinary name is left exactly as it is", breakable_ns["breakable"]("BRINE") == "BRINE")
chooser_src = ast.get_source_segment(menu_src, chooser)
ok("each name and line on the page goes through it", "QtWidgets.QLabel(breakable(text))" in chooser_src)
ok("and if a row is ever wider than the page, it scrolls rather than hiding the stars",
   "ScrollBarAsNeeded" in chooser_src and "ScrollBarAlwaysOff" not in chooser_src)
_n, preview_src = method("preview_disc_menu")
ok("Preview removes a hard-linked game_icon.ico before copying the window icon over it",
   "os.remove(icon_dest)" in preview_src
   and preview_src.index("os.remove(icon_dest)") < preview_src.index("shutil.copy2(self.ico_path_var.get(), icon_dest)"))
print()

print("15. nothing hidden in a menu (his word, 19 Oct 2026, evening)")
_n, widgets_src = method("create_widgets")
ok("Build Queue sits beside Browse in Step 1, after an \"or\", and teaches on hover",
   re.search(r'self\.queue_btn\s*=\s*self\.icon_button\(\s*step_row,\s*"queue",\s*"Build Queue",\s*'
             r'self\.configure_build_queue', widgets_src) is not None
   and "ToolTip(self.queue_btn," in widgets_src
   and widgets_src.index("self.select_btn = self.icon_button(") < widgets_src.index('ttk.Label(step_row, text="or"')
   < widgets_src.index("self.queue_btn = self.icon_button(") < widgets_src.index("self.game_path_label = ttk.Label("))
ok("and the row shows a long path from its end, so the game's own folder stays in view",
   "self.game_path_var.trace_add(\"write\", show_game_path)" in widgets_src
   and "textvariable=self.game_path_shown" in widgets_src
   and "text = text[1:]" in widgets_src and 'text = "\\u2026" + text' in widgets_src)
_n, extras_src = method("configure_disc_extras")
ok("Disc Extras opens Files to Place on the PC from a button beside Done, which costs it no height",
   'placed_btn = ttk.Button(button_row, text="Files to Place on the PC\\u2026"' in extras_src
   and "child = self.configure_placed_files()" in extras_src and "ToolTip(placed_btn," in extras_src)
_n, placed_src = method("configure_placed_files")
_placed_last = ast.parse(textwrap.dedent(placed_src)).body[0].body[-1]
ok("and takes its grab back when Files to Place on the PC closes",
   isinstance(_placed_last, ast.Return) and getattr(_placed_last.value, "id", "") == "dialog"
   and 'child.bind("<Destroy>", back, add="+")' in extras_src and "event.widget is child" in extras_src
   and "dialog.grab_set()" in extras_src)
ok("the games list opens from Add Games, not Configure",
   'text="Add Games\\u2026", command=self.configure_game_exes' in widgets_src and 'text="Configure"' not in flat)
ok("the Disc menu still carries all four", all(entry in widgets_src for entry in (
    '("Games on Disc…", self.configure_game_exes)', '("Disc Extras…", self.configure_disc_extras)',
    '("Files to Place on the PC…", self.configure_placed_files)', '("Build Queue…", self.configure_build_queue)')))
_n, shortcut_src = method("create_desktop_shortcut")
ok("Put Rialto on the Desktop names the shortcut for the version, like the Setup's",
   'name = "%s %s.lnk" % (APP_NAME, __version__)' in shortcut_src and "'Rialto.lnk'))" not in shortcut_src
   and '"$new = Join-Path $desktop %s" % ps_quote(name)' in shortcut_src
   and '"$s = $ws.CreateShortcut($new)"' in shortcut_src)
ok("and an older plain \"Rialto\" shortcut is renamed only when it starts this same Rialto",
   "TargetPath -eq" in shortcut_src and "-not (Test-Path -LiteralPath $new)" in shortcut_src
   and "Arguments -eq" in shortcut_src)
ok("the three-steps card starts folded, with Show beside its title",
   'self.tutorial_toggle.pack(side="right")' in widgets_src and "more.pack(" not in widgets_src)
ok("the guide names the games window's fields as the window does",
   "under <b>About</b>" not in guide and "<b>Configure</b>" not in guide and "Keep theirs" not in guide)

if failures:
    print("\nFAILED: %d check(s)" % len(failures))
    sys.exit(1)
print("\nAll interface review checks passed.")
