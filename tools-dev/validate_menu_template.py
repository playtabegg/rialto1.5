"""Validate the disc-menu source inside Rialto.pyw.

`MENU_TEMPLATE_SOURCE` is the whole disc menu, and since 1.5 it is a plain
string constant with no splices at all: one pre-built menu.exe is frozen from it
and serves every title, driven entirely by menu_config.json. Extracting it is
therefore also the genericity test - menu_source.extract_menu_source refuses
anything that is not a constant, so re-baking a game title into the source fails
this harness rather than shipping.

The batch fallback menu (still a .format() template) is checked the old way; the
Inno script is checked by test_installer_script.py.

Usage: python validate_menu_template.py [path-to-Rialto.pyw]
"""
import ast
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_source import extract_menu_source, TEMPLATE_NAME

MOCK_TITLE = "MockGame"


def find_string_assign(tree, name):
    """Return the value node of the last `name = ...` assignment found."""
    found = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    found = node.value
    return found


def flatten(node):
    """Concatenate a BinOp(+) tree of string constants; mock out expressions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return flatten(node.left) + flatten(node.right)
    if isinstance(node, ast.JoinedStr):
        raise SystemExit("template is an f-string; this validator assumes plain concat")
    # Anything else is a runtime splice (safe_title.replace(...) etc.)
    return MOCK_TITLE


def check(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    print(f"[OK]  Rialto.pyw parses ({len(src.splitlines())} lines)")

    ok = True

    # --- 1. the disc menu source, which must be title-agnostic ---
    try:
        menu_src = extract_menu_source(path)
    except ValueError as e:
        print(f"[FAIL] {e}")
        return False
    print(f"[OK]  {TEMPLATE_NAME} is a plain constant (no per-title splices)")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_menu_launcher.py")
    open(out, "w", encoding="utf-8").write(menu_src)
    try:
        menu_tree = ast.parse(menu_src)
        print(f"[OK]  generated menu parses ({len(menu_src.splitlines())} lines) -> {out}")
    except SyntaxError as e:
        print(f"[FAIL] generated menu SyntaxError line {e.lineno}: {e.msg}")
        lines = menu_src.splitlines()
        for i in range(max(0, (e.lineno or 1) - 4), min(len(lines), (e.lineno or 1) + 3)):
            print(f"   {i+1:5d} | {lines[i]}")
        return False

    # --- 2. structural checks on the generated menu ---
    methods = {}
    for n in ast.walk(menu_tree):
        if isinstance(n, ast.ClassDef) and n.name == "GameMenu":
            for item in n.body:
                if isinstance(item, ast.FunctionDef):
                    methods[item.name] = item.lineno
    print(f"[OK]  GameMenu methods: {len(methods)}")
    for required in ("launch_game", "open_bonus", "launch_mods", "uninstall_game",
                     "show_game_chooser", "launch_configured_exe", "change_language",
                     "check_gamepad_input", "keyPressEvent"):
        if required in methods:
            print(f"       - {required} (menu line {methods[required]})")
        else:
            print(f"[FAIL] GameMenu.{required} is missing")
            ok = False

    # --- 3. translations completeness ---
    trans_node = None
    for n in ast.walk(menu_tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Attribute) and t.attr == "translations":
                    trans_node = n.value
    if trans_node is None or not isinstance(trans_node, ast.Dict):
        print("[FAIL] self.translations dict not found in generated menu")
        return False
    langs = {}
    for k, v in zip(trans_node.keys, trans_node.values):
        if not isinstance(k, ast.Constant) or not isinstance(v, ast.Dict):
            print("[FAIL] unexpected translations entry shape")
            ok = False
            continue
        langs[k.value] = [kk.value for kk in v.keys if isinstance(kk, ast.Constant)]
    print(f"[OK]  translations: {len(langs)} languages")
    if "English" not in langs:
        print("[FAIL] English missing from translations")
        return False
    base = set(langs["English"])
    print(f"       English keys ({len(base)}): {sorted(base)}")
    for required in ("play", "bonus", "mods", "mods_not_found", "bonus_not_found",
                     "uninstall", "exit", "game_not_found"):
        if required not in base:
            print(f"[FAIL] English translation missing key '{required}'")
            ok = False
    bad = []
    for lang, keys in sorted(langs.items()):
        missing = base - set(keys)
        extra = set(keys) - base
        if missing or extra:
            bad.append((lang, sorted(missing), sorted(extra)))
    if bad:
        for lang, missing, extra in bad:
            print(f"[FAIL] {lang}: missing={missing} extra={extra}")
        ok = False
    else:
        print(f"[OK]  all {len(langs)} languages have identical key sets")

    # --- 4. batch fallback menu: .format() placeholders must resolve ---
    batch_node = find_string_assign(tree, "batch_content")
    if batch_node is None:
        print("[WARN] batch_content not found")
    else:
        batch = flatten(batch_node)
        try:
            rendered = batch.format(game_title="MockGame", game_title_upper="MOCKGAME")
            labels = [ln.strip() for ln in rendered.splitlines() if ln.strip().startswith(":")]
            gotos = set()
            for ln in rendered.splitlines():
                s = ln.strip().lower()
                if " goto " in s or s.startswith("goto "):
                    gotos.add(s.rsplit("goto ", 1)[1].split()[0])
            declared = {l[1:].lower() for l in labels}
            missing = gotos - declared
            print(f"[OK]  batch fallback renders; labels={sorted(declared)}")
            if missing:
                print(f"[FAIL] batch menu jumps to undefined labels: {sorted(missing)}")
                ok = False
            for required in ("mods", "bonus", "playgame", "uninstall", "exit"):
                if required not in declared:
                    print(f"[FAIL] batch menu missing :{required} label")
                    ok = False
        except (KeyError, IndexError, ValueError) as e:
            print(f"[FAIL] batch_content.format() failed: {e!r}")
            ok = False

    # --- 5. mods button block + white-label gating ---
    if not check_mods_button(menu_tree, menu_src, langs):
        ok = False

    # --- 6. nothing is called on self that does not exist ---
    if not check_self_references(menu_tree):
        ok = False

    return ok


def check_self_references(menu_tree):
    """Every self.X the menu touches has to exist somewhere.

    _menu_message was called from fourteen places and defined in none - lost in
    an edit - and _menu_confirm and _dark_frame were called for and never
    written at all. PyQt5 turns an unhandled exception in a slot into an abort,
    so every one of those call sites did not show a message, it killed the
    menu: PLAY with no exe, BONUS and MODS not found, UNINSTALL, the preview
    notice, and every ADD TO STEAM outcome including the successful one.

    Nothing in the menu imports, so this is the only thing that would have
    caught it short of clicking every button on a finished disc.
    """
    ok = True
    cls = next((n for n in menu_tree.body
                if isinstance(n, ast.ClassDef) and n.name == "GameMenu"), None)
    if cls is None:
        print("[FAIL] GameMenu class not found")
        return False

    defined = {i.name for i in cls.body if isinstance(i, ast.FunctionDef)}
    defined |= {t.id for i in cls.body if isinstance(i, ast.Assign)
                for t in i.targets if isinstance(t, ast.Name)}
    # anything assigned as self.x = ... anywhere in the class
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                        and t.value.id == "self":
                    defined.add(t.attr)

    try:
        from PyQt5 import QtWidgets
        inherited = set(dir(QtWidgets.QWidget))
    except ImportError:
        # No PyQt5 on this machine: skip rather than report every Qt call as
        # missing. The harness still runs everywhere else.
        print("[OK]  self-reference check skipped (PyQt5 not installed)")
        return True

    used = {n.attr for n in ast.walk(cls)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "self"}
    missing = sorted(a for a in used if a not in defined and a not in inherited)
    if missing:
        for name in missing:
            print(f"[FAIL] self.{name} is used but never defined - "
                  f"calling it aborts the menu")
        ok = False
    else:
        print(f"[OK]  every self.X the menu uses exists ({len(used)} checked)")
    return ok


# ---------------------------------------------------------------------------
# Section 5: the Enable Mod Launcher additions and the Remove WTI Branding flag.
# Everything below reads the REAL template source (never a paraphrase) and, where
# a claim is behavioural, execs the extracted block on a stub object.
# ---------------------------------------------------------------------------

def _find_method(tree, cls, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls:
            for item in n.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
    return None


def _class_attr_source(tree, cls, name):
    """Source for a class-level assignment, so a stub gets the real list."""
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls:
            for item in n.body:
                if isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") == name:
                    return ast.unparse(item)
    return ""


def _exec_block(src, ns):
    exec(compile(ast.parse(src), "<template-block>", "exec"), ns)
    return ns


def check_mods_button(menu_tree, menu_src, langs):
    import textwrap
    ok = True

    def say(good, label, detail=""):
        nonlocal ok
        print(f"[{'OK' if good else 'FAIL'}]  {label}{(' -> ' + detail) if detail else ''}")
        if not good:
            ok = False

    # 5a. every language dict carries the two mods strings, individually checked
    missing = sorted(l for l, keys in langs.items()
                     if "mods" not in keys or "mods_not_found" not in keys)
    say(not missing, f"'mods'+'mods_not_found' in all {len(langs)} language dicts",
        f"missing in {missing}" if missing else f"{len(langs)}/{len(langs)}")
    blank = sorted(l for l, keys in langs.items() if not keys)
    say(not blank, "no empty language dict", str(blank))

    # 5b. mods_btn / bonus_btn are created conditionally (`if mods_exists:`), so
    #     EVERY read of them must sit under a guard, or the menu raises
    #     AttributeError on a disc that carries no mods folder. Two guard styles
    #     are legitimate: `hasattr(self,'mods_btn')` for reads in other methods,
    #     and the local `mods_exists` flag for reads in the creating method.
    parent = {}
    for n in ast.walk(menu_tree):
        for child in ast.iter_child_nodes(n):
            parent[child] = n

    def guards_for(node, attr, flag):
        """Walk up the tree; report which enclosing If-tests protect this read."""
        found = []
        cur, prev = parent.get(node), node
        while cur is not None:
            if isinstance(cur, ast.If) and prev in cur.body:  # the True branch only
                test = ast.unparse(cur.test)
                if (f"'{attr}'" in test and ("hasattr" in test or "getattr" in test)) \
                        or flag in test:
                    found.append(test)
            prev, cur = cur, parent.get(cur)
        return found

    for attr, flag in (("mods_btn", "mods_exists"), ("bonus_btn", "bonus_exists")):
        created = [n.lineno for n in ast.walk(menu_tree) if isinstance(n, ast.Assign)
                   for t in n.targets
                   if isinstance(t, ast.Attribute) and t.attr == attr]
        reads, unguarded, styles = 0, [], set()
        for n in ast.walk(menu_tree):
            if isinstance(n, ast.Attribute) and n.attr == attr \
                    and isinstance(n.ctx, ast.Load):
                reads += 1
                g = guards_for(n, attr, flag)
                if g:
                    styles.update("hasattr" if "attr(" in x else flag for x in g)
                else:
                    unguarded.append(n.lineno)
        say(not unguarded,
            f"all {reads} reads of self.{attr} sit under a guard",
            f"UNGUARDED at menu lines {unguarded}" if unguarded
            else f"created at {created}, guard styles={sorted(styles)}")

    # 5c. launch_mods: preview gate first, config-then-scan resolution
    lm = _find_method(menu_tree, "GameMenu", "launch_mods")
    say(lm is not None, "GameMenu.launch_mods exists")
    if lm:
        first = lm.body[0]
        gated = isinstance(first, ast.If) and "preview_mode" in ast.unparse(first.test)
        say(gated, "launch_mods gates on self.preview_mode before doing anything",
            ast.unparse(first.test) if isinstance(first, ast.If) else type(first).__name__)
        say("_resolve_mod_exe" in ast.unparse(lm),
            "launch_mods delegates to _resolve_mod_exe")
        say("mods_not_found" in ast.unparse(lm),
            "launch_mods shows the translated not-found message on failure")

    rme = _find_method(menu_tree, "GameMenu", "_resolve_mod_exe")
    say(rme is not None, "GameMenu._resolve_mod_exe exists")
    if rme:
        body = ast.unparse(rme)
        say("menu_config" in body and "mod_exe" in body,
            "_resolve_mod_exe consults menu_config['mod_exe'] first")
        say("listdir" in body, "_resolve_mod_exe falls back to scanning the mods folder")

    # 5d. no shell=True anywhere, and every Popen gets a LIST (space-safe argv)
    def is_list_argv(node):
        """A list literal, or a list literal with more list appended to it.

        `[exe] + args` is what the compatibility-mode launch builds, and it is
        still list form: the executable is a literal first element and Windows
        never sees a command line we assembled by hand. A bare name or a
        string is still refused - that is the whole point of the check.
        """
        if isinstance(node, ast.List):
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return is_list_argv(node.left)
        return False

    bad_shell, bad_popen = [], []
    for n in ast.walk(menu_tree):
        if isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    bad_shell.append(n.lineno)
            if ast.unparse(n.func).endswith("Popen"):
                if not n.args or not is_list_argv(n.args[0]):
                    bad_popen.append((n.lineno, ast.unparse(n)[:70]))
    say(not bad_shell, "no shell=True in the generated menu", str(bad_shell))
    say(not bad_popen, "every subprocess.Popen uses list form (spaces safe)",
        str(bad_popen))

    # 5e. BEHAVIOURAL: remove_wti_branding wins even when the logo file exists.
    branding_if = None
    for n in ast.walk(menu_tree):
        if isinstance(n, ast.If) and "remove_wti_branding" in ast.unparse(n.test):
            branding_if = n
    say(branding_if is not None, "bird-logo block is gated on remove_wti_branding")
    if branding_if:
        import tempfile
        stage = tempfile.mkdtemp(prefix="rialto_brand_")
        logo = os.path.join(stage, "bird_logo.PNG")
        open(logo, "wb").write(b"PNG")           # the stale file really is there
        fake_file = os.path.join(stage, "menu_launcher.py")

        block = "def _resolve(self):\n    bird_logo_path = None\n" + \
                textwrap.indent(ast.unparse(branding_if), "    ") + \
                "\n    return bird_logo_path\n"

        class FakeSys:
            executable = os.path.join(stage, "menu.exe")
        class Cfg:
            def __init__(self, flag): self.menu_config = {"remove_wti_branding": flag}

        for frozen in (False, True):
            fs = FakeSys()
            if frozen:
                fs.frozen = True
            ns = {"os": os, "sys": fs, "__file__": fake_file}
            _exec_block(block, ns)
            on = ns["_resolve"](Cfg(True))
            off = ns["_resolve"](Cfg(False))
            mode = "frozen" if frozen else "source"
            say(on is None,
                f"[{mode}] white-label ON -> logo skipped though the file exists",
                repr(on))
            say(off == logo,
                f"[{mode}] white-label OFF -> the same file IS used", repr(off))
        shutil_rmtree(stage)

    # 5f. BEHAVIOURAL: mods dir present but EMPTY at menu runtime.
    if rme:
        import tempfile
        rmd = _find_method(menu_tree, "GameMenu", "_resolve_mods_dir")
        say(rmd is not None, "GameMenu._resolve_mods_dir exists")
        if rmd:
            # _resolve_mod_exe screens the configured path through
            # _configured_exe, which needs _inside_game_dir, _is_helper_exe and
            # the HELPER_EXES list, so the stub carries all of them.
            helpers = [rmd, rme]
            for name in ("_configured_exe", "_inside_game_dir", "_is_helper_exe"):
                found = _find_method(menu_tree, "GameMenu", name)
                say(found is not None, f"GameMenu.{name} exists")
                if found:
                    helpers.append(found)
            src = "\n".join(textwrap.dedent(ast.unparse(h)) for h in helpers)
            src += "\n" + _class_attr_source(menu_tree, "GameMenu", "HELPER_EXES")
            ns = {"os": os, "sys": sys}
            exec(f"class H:\n{textwrap.indent(src, '    ')}", ns)
            root = tempfile.mkdtemp(prefix="rialto_emptymods_")
            os.makedirs(os.path.join(root, "mods"))
            h = ns["H"]()
            h.game_dir = root
            # build-side default when nothing was detected
            h.menu_config = {"mod_exe": "mods/ModLauncher.exe"}
            say(h._resolve_mod_exe() is None,
                "empty mods/ + stale configured exe -> None (menu shows not-found, no crash)")
            h.menu_config = {}
            say(h._resolve_mod_exe() is None, "empty mods/ + no config -> None")
            # and a real exe whose path contains spaces resolves intact
            spaced = os.path.join(root, "mods", "Mod Organizer 2.exe")
            open(spaced, "wb").write(b"MZ")
            h.menu_config = {}
            got = h._resolve_mod_exe()
            say(got == spaced, "exe path with spaces resolves intact (list-form Popen argv)",
                repr(got))
            shutil_rmtree(root)

    return ok


def shutil_rmtree(p):
    import shutil
    shutil.rmtree(p, ignore_errors=True)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Rialto.pyw")
    sys.exit(0 if check(target) else 1)
