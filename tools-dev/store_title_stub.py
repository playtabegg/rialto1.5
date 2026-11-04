"""player_title and its rule, for harnesses that build a stub host (4 Nov 2026).

Every name the player sees goes through player_title, so a stub that runs the
installer, menu config, README, autorun, disc image or Unix packaging steps
needs it, and the installer's step needs install_identity_code and its helpers
too, the menu config's earlier_menu_titles, and the disc image's step volume_label. These are
the real functions, pulled from Rialto.pyw with whatever module-level code they
read; namespace(src) is what to add to the stub's exec namespace.
"""
import ast
import re

NAMES = ("player_title", "is_store_format", "store_format_note", "install_identity_code", "earlier_installs",
         "install_delete_lines", "inno_uninstall_key", "volume_label", "earlier_menu_titles")


def namespace(src):
    """The real functions NAMES lists, and the module code they read."""
    tree = ast.parse(src)
    defs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defs[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defs[target.id] = node
    missing = [n for n in NAMES if n not in defs]
    if missing:
        raise SystemExit("could not extract %s" % ", ".join(missing))
    wanted, queue, seen = [], list(NAMES), set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        if defs[name] not in wanted:
            wanted.append(defs[name])
        queue += [n.id for n in ast.walk(defs[name]) if isinstance(n, ast.Name) and n.id in defs]
    wanted.sort(key=lambda n: n.lineno)
    # The functions keep their own module namespace, so nothing else the stub
    # chose (a stand-in sanitize_text, say) is replaced.
    ns = {"re": re}
    exec("\n\n".join(ast.get_source_segment(src, n) for n in wanted), ns)
    return {name: ns[name] for name in NAMES}
