"""B6's helpers, for harnesses that build a stub host (1.5.1).

The build now copies through counting_copy and sizes folders with tree_size,
and its other slow steps tick a build_ticker or run through run_watched_call, so
a stub that runs them needs these. They are the real methods, pulled from
Rialto.pyw; only the window parts (the live line and keeping the window
answering) are no-ops, because a stub has no window. namespace() is what the
real methods read from the module.
"""
import ast
import textwrap

NAMES = ("tree_size", "counting_copy", "build_ticker", "watched_copytree", "run_watched_call")


def namespace():
    """The modules the helpers read, for the stub's exec namespace."""
    import glob
    import os
    import shutil
    import time
    return {"glob": glob, "os": os, "shutil": shutil, "time": time}


def methods(src):
    """Class-body source: the real tree_size and counting_copy, and no-op window parts."""
    out = []
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == "RialtoApp":
            out += [textwrap.dedent(ast.get_source_segment(src, item)) for item in node.body
                    if isinstance(item, ast.FunctionDef) and item.name in NAMES]
    if len(out) != len(NAMES):
        raise SystemExit("could not extract %s" % ", ".join(NAMES))
    out.append("def show_progress(self, *args, **kwargs):\n    pass")
    out.append("def keep_window_alive(self):\n    pass")
    return "\n\n".join(out)
