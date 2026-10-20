"""Disc Extras fits the screen (1.5.1, B11 and B13.4).

1.5.0 opened Disc Extras at a fixed 680 by 990 and packed five sections one
under another, so on a 1080-line screen less the taskbar the lowest controls
fell under the bottom edge ("expand the bottom of your window pane to see all
controls! This will be fixed in 1.5.1"). It now lays the sections in two
columns and sizes itself to what it holds, with no scrolling, and never
taller than the work area less its title bar. Until B13.4 the limit was the
whole screen less 80, which let it run under the taskbar on a short screen.

Source-extracted: no tkinter window is opened. The real dialog is opened and
measured by tools-dev/test_fits_every_screen.py: 636 lines tall at 100
percent (652 before B13.4 took 16 lines of padding), inside the 640 that a
720-line screen leaves under its taskbar and the dialog's title bar.
"""
import ast
import os
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

failures = []


def ok(label, cond, detail=""):
    shown = (" -> " + ascii(detail)) if (detail and not cond) else ""
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, shown))
    if not cond:
        failures.append(label)


def method(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(src, item))
    return None


src = open(RIALTO, encoding="utf-8").read()
extras = method(src, "configure_disc_extras") or ""

print("Disc Extras: two columns, sized to what they hold")
ok("no fixed 990-pixel height any more", "height=990" not in extras)
ok("it measures itself once built", "self.fit_dialog_to_screen(dialog" in extras)
ok("two columns, left and right", "left = tk.Frame(columns" in extras and "right = tk.Frame(columns" in extras)
for title, side in (("Bonus content", "left"), ("Mods", "left"), ("Steam", "left"),
                    ("Compatibility mode", "right"), ("Mac and Linux on the same disc", "right")):
    at = extras.find('section("%s' % title)
    before = extras[:at]
    last_left, last_right = before.rfind("col = left"), before.rfind("col = right")
    ok("%s sits in the %s column" % (title, side), at > 0 and ((last_left > last_right) == (side == "left")))
ok("Files to Place on the PC opens from the Done row, which costs no height",
   'placed_btn = ttk.Button(button_row,' in extras and 'placed_btn.pack(side="left")' in extras)
ok("nothing but the Done row, the lead line and the columns is packed straight into the body",
   extras.count("(body,") == 3 and "\n            body, " not in extras)

ns = {}
exec(method(src, "dialog_height_for"), ns)
height = lambda req, area, bar=32: ns["dialog_height_for"](None, req, area, bar)  # noqa: E731

print("never taller than the work area less its title bar")
ok("the screen less 80 is gone from the rule", "- 80" not in (method(src, "dialog_height_for") or "- 80"))
ok("fits as asked on a 1080-line screen (work area 1032)", height(636, 1032) == 636)
ok("1366 by 768 (work area 720) holds the measured dialog", height(636, 720) == 636)
ok("so does 1080p at 150 percent (work area 672, 640 under the title bar)", height(636, 672) == 636)
ok("a taller ask is held to the work area less the title bar", height(900, 720) == 688 and height(652, 672) == 640)
ok("never smaller than a usable minimum", height(50, 1032) == 200)
ok("and never the minimum where the work area cannot hold it", height(50, 220) == 188)

fitting = method(src, "fit_dialog_to_screen") or ""
print("every dialog is sized and placed by the one rule")
ok("the height comes from the work area and the frame Windows adds, not from the screen",
   "self.available_space(parent)[3]" in fitting and "self.window_frame()" in fitting
   and "winfo_screenheight" not in fitting)
ok("the place is the one rule's, through centre_on",
   "self.centre_on(dialog, width, height, parent)" in fitting
   and "self.place_window(window, width, height, over=over, near=parent)" in (method(src, "centre_on") or ""))

exec(method(src, "fit_in_work_area"), ns)
rule = lambda *args, **kwargs: ns["fit_in_work_area"](None, *args, **kwargs)  # noqa: E731
frame = (31, 1, 7)  # Windows 10 and 11 at 100 percent: title bar, border seen, border unseen
print("the one rule, for a titled dialog over the main window: (width, height, x, y)")
ok("Disc Extras at 1080p at 150 percent: whole, 4 lines from the top of the work area",
   rule(1180, 636, (0, 0, 1280, 672), frame, over=(290, 0, 700, 672)) == (1180, 636, 50, 4))
ok("a dialog that asks for more than the work area is held to it, title bar and border included",
   rule(2000, 2000, (0, 0, 1280, 672), frame) == (1278, 640, -7, 0))
ok("a dialog over a main window at the screen's edge is brought inside the work area",
   rule(640, 500, (0, 0, 1536, 816), frame, over=(1300, 600, 700, 816)) == (640, 500, 887, 284))
ok("a work area whose corner is not 0, 0",
   rule(640, 740, (-1536, 48, 1536, 816), frame, over=(-1118, 48, 700, 816)) == (640, 740, -1088, 73))

if failures:
    print("\nFAILED: %d check(s)" % len(failures))
    sys.exit(1)
print("\nAll Disc Extras checks passed.")
