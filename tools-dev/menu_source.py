"""Pull the disc-menu source out of Rialto.pyw without importing it.

`MENU_TEMPLATE_SOURCE` in Rialto.pyw is the single copy of the disc menu. The
pre-built menu.exe is frozen from it (menu.spec) and the harnesses check it
(validate_menu_template.py), so both read it straight out of the file rather
than keeping a second copy that could drift.

Importing Rialto.pyw instead would drag in tkinter and the first-run pip
bootstrap, neither of which belongs in a build step.
"""
import ast
import os

DEFAULT_RIALTO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Rialto.pyw")

TEMPLATE_NAME = "MENU_TEMPLATE_SOURCE"


def _flatten(node):
    """Concatenate a constant string, or a BinOp(+) tree of them."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten(node.left) + _flatten(node.right)
    raise ValueError(
        f"{TEMPLATE_NAME} is no longer a plain string constant "
        f"({type(node).__name__} found). The disc menu must stay title-agnostic: "
        "anything per-title belongs in menu_config.json, not spliced into the source."
    )


def extract_menu_source(rialto_path=None):
    """Return the disc menu source as a string."""
    path = rialto_path or DEFAULT_RIALTO
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == TEMPLATE_NAME:
                    return _flatten(node.value)
    raise ValueError(f"{TEMPLATE_NAME} not found in {path}")


def write_menu_source(dest_dir, rialto_path=None, filename="menu_launcher.py"):
    """Write the disc menu source to `dest_dir` and return the path."""
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, filename)
    with open(out, "w", encoding="utf-8") as f:
        f.write(extract_menu_source(rialto_path))
    return out


if __name__ == "__main__":
    import sys
    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(DEFAULT_RIALTO), "build", "menu_src")
    print(write_menu_source(dest))
