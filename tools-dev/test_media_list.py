"""The Target Media list opens wide enough to read every choice (1.5.1, bugs review finding 4).

The box shares its row with Compression, so the longest Blu-ray XL names are
cut in it, and a ttk list opens only as wide as its box. This builds the real
main window (as test_fits_every_screen.py does), opens the list the way a click
does (ttk::combobox::Post), and measures the open list against every name in
the list's own font. The open list must stay inside the work area too.
With --shot DIR it also saves a picture of the open list.
"""
import argparse
import os
import shutil
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_fits_every_screen as fits  # noqa: E402

failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


def widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from widgets(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shot", metavar="DIR")
    args = parser.parse_args()
    app_root = tempfile.mkdtemp(prefix="rialto_media_list_")
    root = None
    try:
        result = {"problems": []}
        module = fits.load_rialto(fits.RIALTO if hasattr(fits, "RIALTO") else os.path.join(fits.REPO, "Rialto.pyw"),
                                  app_root, result)
        module.ensure_structure()
        root = tk.Tk()
        app = module.RialtoApp(root)
        root.update()
        combo = next(w for w in widgets(root) if isinstance(w, ttk.Combobox)
                     and str(w.cget("textvariable")) == str(app.target_media_var))
        names = [str(n) for n in combo.cget("values")]
        longest = max(names, key=len)
        for choice in ("Blu-ray XL 128 GB (BD-R quad layer)", "Mini DVD 1.4 GB (8 cm)"):
            app.target_media_var.set(choice)
            combo.tk.call("ttk::combobox::Post", combo)
            root.update()
            popdown = combo.tk.eval("ttk::combobox::PopdownWindow %s" % combo)
            listbox = popdown + ".f.l"
            font = tkfont.Font(root=root, font=combo.tk.call(listbox, "cget", "-font"))
            inner = int(combo.tk.call("winfo", "width", listbox))
            need = max(font.measure(n) for n in names)
            ok("with %s chosen, the open list (%d px) holds the longest name (%d px): %s"
               % (choice, inner, need, max(names, key=font.measure)), inner >= need, (inner, need))
            x = int(combo.tk.call("winfo", "rootx", popdown))
            w = int(combo.tk.call("winfo", "width", popdown))
            left, _top, width, _height = app.available_space()
            ok("and stays inside the work area", left <= x and x + w <= left + width, (x, w, left, width))
            ok("every choice is listed, none renamed", names == [n for n, _c in app.MEDIA_TYPES])
            if args.shot:
                from PIL import ImageGrab
                os.makedirs(args.shot, exist_ok=True)
                y = combo.winfo_rooty()
                h = int(combo.tk.call("winfo", "height", popdown)) + combo.winfo_height()
                shot = os.path.join(args.shot, "media-list-open-%s.png" % ("128GB" if "128" in choice else "minidvd"))
                ImageGrab.grab(bbox=(min(x, combo.winfo_rootx()) - 10, y - 10,
                                     max(x + w, combo.winfo_rootx() + combo.winfo_width()) + 10, y + h + 10),
                               all_screens=True).save(shot)
                print("  picture: " + shot)
            combo.tk.call("ttk::combobox::Unpost", combo)
            root.update()
        ok("the longest name is the 128 GB Blu-ray XL", longest == "Blu-ray XL 128 GB (BD-R quad layer)", longest)
        ok("Rialto loaded without a problem", not result["problems"], result["problems"])
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        shutil.rmtree(app_root, ignore_errors=True)
    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nThe Target Media list opens wide enough to read every choice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
