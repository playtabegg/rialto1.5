"""The main window keeps Step 4 and the log in view on a short screen (1.5.1).

The window is 700 wide and as tall as the work area of its monitor allows, up
to 1200. It is placed inside that work area and never resized after. Until
B13.1 it was the screen's height less 80 with a floor of 900 lines, which made
it taller than a 1080p laptop's screen at 125 percent, and it was given no
position. 1.5.0's page asked for 1128 lines, so at 1080p the Disc Icon row and
the whole log sat under the build bar. Now, when the page asks for more than
the window holds, the three-steps card folds to its title line with Show
beside it: 1005 lines folded, 1128 open.

Where even the folded page is more than the window holds (a 1080p laptop at 125
percent has 816 lines), the same page is laid out tighter, a level at a time,
until it fits (B13.2, the candidate "a tighter page"): held here as the levels
themselves and as the rule that chooses one, with the page pretended.

Source-extracted: no window is opened. This keeps the rule itself, as written
and as arithmetic: for the main window, for a tooltip, and for a PC where
Windows will not give the work area. Windows is asked for the work area three
times, to hold that asking declares nothing twice. What the real window does
on each screen, and what is still cut on a short one, is
tools-dev/test_fits_every_screen.py's to say.
"""
import ast
import os
import re
import sys
import textwrap
import tkinter  # for tk.TclError alone: no window is opened

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
failures = []


def ok(label, cond):
    print("  [%s] %s" % ("OK  " if cond else "FAIL", label))
    if not cond:
        failures.append(label)


def method(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return textwrap.dedent(ast.get_source_segment(src, node))
    return ""


src = open(RIALTO, encoding="utf-8").read().replace("\r\n", "\n")
widgets = method(src, "create_widgets")
fit = method(src, "fit_main_window")
space = method(src, "available_space")
ask = method(src, "work_area_of_monitor")
place = method(src, "place_window")

print("the window is sized and placed once, by the one rule, and never resized")
ok("700 wide and up to 1200 tall, through place_window",
   "self.window_height = self.place_window(self.root, 700, 1200)[1]" in src)
ok("no floor: nothing holds it at 900 lines on a shorter screen", "max(900" not in src)
ok("place_window asks for the work area and applies the one rule, then sets size and position together",
   "self.available_space(near)" in place and "self.fit_in_work_area(" in place
   and 'window.geometry(f"{width}x{height}+{x}+{y}")' in place)
ok("fitting never touches the geometry", "geometry" not in fit and "geometry" not in method(src, "fold_tutorial"))

print("the work area is asked of Windows, and Rialto opens whatever the answer")
ok("the monitor's work area, not its whole screen", "rcWork" in ask and "GetMonitorInfoW" in ask)
ok("the main monitor's work area when the monitor meant cannot be asked", "SystemParametersInfoW(0x0030" in ask)
ok("it never raises: None, and the caller falls back",
   ask.rstrip().endswith("except Exception:\n        return None"))

calls = method(src, "monitor_calls")
ok("the monitor's structure and the calls' argument types are declared in one place, not where Windows is asked",
   "class MONITORINFO" in calls and "argtypes" in calls and "_MONITOR_CALLS = (user32, MONITORINFO)" in calls
   and "class MONITORINFO" not in ask and "argtypes" not in ask and "monitor_calls()" in ask)
if sys.platform == "win32" and calls:
    import ctypes
    asking = {"sys": sys, "_MONITOR_CALLS": None}
    exec(calls, asking)
    exec(ask, asking)
    corner = (0, 0, 100, 100)  # a window at the main monitor's corner: the same monitor every time it is asked
    first = asking["work_area_of_monitor"](corner)
    declared, kept = asking["monitor_calls"](), len(getattr(ctypes, "_pointer_type_cache", ()))
    again = [asking["work_area_of_monitor"](corner) for _ in range(3)]
    ok("asked three times more, Windows gives the same work area and nothing is declared again",
       bool(first) and again == [first] * 3 and asking["monitor_calls"]() is declared
       and len(getattr(ctypes, "_pointer_type_cache", ())) == kept)

ns = {}
exec(method(src, "fit_in_work_area"), ns)
rule = lambda *args, **kwargs: ns["fit_in_work_area"](None, *args, **kwargs)  # noqa: E731


class Screen:
    """A window on a 1536 by 864 screen, and the main window of a Rialto that pretends no monitor."""
    PRETEND_MONITOR = None

    def __init__(self):
        self.root = self

    def winfo_width(self):
        return 700

    def winfo_height(self):
        return 864

    def winfo_rootx(self):
        return 418

    def winfo_rooty(self):
        return 0

    def winfo_screenwidth(self):
        return 1536

    def winfo_screenheight(self):
        return 864


silent = {"tk": tkinter, "work_area_of_monitor": lambda box=None: None}
exec(space, silent)
print("if Windows will not give the work area")
ok("it is the screen as Tk measures it less 80 lines of height, the allowance 1.5.0 made for the taskbar",
   silent["available_space"](Screen()) == (0, 0, 1536, 784)
   and "work_area_of_monitor(box) or (0, 0, window.winfo_screenwidth(), window.winfo_screenheight() - 80)" in space)
ok("so the main window is 784 lines tall on an 864-line screen, and not the whole 864 with its foot under the taskbar",
   rule(700, 1200, silent["available_space"](Screen())) == (700, 784, 418, 0))

print("the one rule, for a window with no title bar: (width, height, x, y) in each work area")
ok("a 1440-line screen: 700 by 1200, centred", rule(700, 1200, (0, 0, 2560, 1392)) == (700, 1200, 930, 96))
ok("1080p: as tall as the work area", rule(700, 1200, (0, 0, 1920, 1032)) == (700, 1032, 610, 0))
ok("1080p at 125 percent: 816 lines, not 900", rule(700, 1200, (0, 0, 1536, 816)) == (700, 816, 418, 0))
ok("1366 by 768, and 1080p at 150 percent",
   rule(700, 1200, (0, 0, 1366, 720)) == (700, 720, 333, 0)
   and rule(700, 1200, (0, 0, 1280, 672)) == (700, 672, 290, 0))
ok("a work area whose corner is not 0, 0", rule(700, 1200, (-1536, 48, 1536, 816)) == (700, 816, -1118, 48))
ok("never wider than a narrow work area", rule(700, 1200, (0, 0, 600, 500)) == (600, 500, 0, 0))
ok("a place asked for outside the work area is brought inside it",
   rule(700, 816, (0, 0, 1536, 816), x=2000, y=-300) == (700, 816, 836, 0))

class OneRule:
    """The one rule and a work area, with no Rialto and no window behind them."""

    def __init__(self, work_area):
        self.work_area = work_area

    def available_space(self, window=None):
        return self.work_area

    def fit_in_work_area(self, *args, **kwargs):
        return rule(*args, **kwargs)

    def winfo_toplevel(self):
        return self


exec(method(src, "tooltip_place"), ns)
place = ns.get("tooltip_place") or (lambda *args: None)  # a Rialto with no such rule fails each line below
laptop = OneRule((0, 0, 1536, 816))
tip = lambda *args: place(laptop, laptop, *args)  # noqa: E731
shown = method(src, "show")
print("a tooltip takes its place from the same rule: (x, y) for one 315 by 93, the pointer at x - 15, y - 10")
ok("ToolTip asks the rule where to go, before the window is given a place",
   "ToolTip.place = self.tooltip_place" in src and "ToolTip.place(self.widget" in shown
   and shown.find("ToolTip.place(self.widget") < shown.find("tw.wm_geometry("))
ok("room below the pointer: below and right of it, where it always opened",
   tip(315, 93, 644, 410, 390) == (644, 410))
ok("no room below (the export bar's last row): above the pointer, its bottom edge 10 lines over it",
   tip(315, 93, 644, 808, 788) == (644, 695))
ok("at the right edge it is brought inside, and stays clear of the pointer",
   tip(315, 93, 1500, 410, 390) == (1221, 410) and tip(315, 93, 1500, 808, 788) == (1221, 695))
ok("a work area whose corner is not 0, 0",
   place(OneRule((-1536, 48, 1536, 816)), laptop, 315, 93, -892, 856, 836) == (-892, 743))

print("the card starts folded on every screen; the page is drawn in only when it asks for more than the window")
ok("compares what the page asks for with the window's height",
   "self.root.winfo_reqheight() > getattr(self, \"window_height\"" in fit)
ok("runs once the page and the profile are in", "self.load_last_used_profile()\n        self.root.after_idle(self.fit_main_window)" in src)
ok("Show is there on every screen, and the card starts folded (his word, 19 Oct 2026)",
   "self.tutorial_toggle.pack(side=\"right\")" in widgets and "self.tutorial_toggle.pack(" not in fit
   and "self.tutorial_more.pack(" not in widgets)

print("what folds")
ok("the title line stays", 'title_row = tutorial_line("disc", "Three steps to a disc."' in widgets
   and 'Three steps to a disc.", bold=True, pad=(8, 2))' in widgets)
ok("the six lines under it sit in the part that folds",
   widgets.count("tutorial_line(") - widgets.count("def tutorial_line(") == 7
   and widgets.count("parent=more)") == 6)
ok("Show and Hide open and close it", "self.fold_tutorial(\n            bool(self.tutorial_more.winfo_manager()))" in widgets)

# ---- the tighter page (B13.2, a candidate) ----
TREE = ast.parse(src)


def code(name):
    """A method's code as Python writes it back: no docstring, no comments."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = node.body[1:] if ast.get_docstring(node) is not None else node.body
            return "\n".join(ast.unparse(statement) for statement in body)
    return ""


def class_value(name):
    """A value RialtoApp is given by name, as written in the source: PAGE_LEVELS."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.Assign) and any(getattr(target, "id", "") == name for target in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


TIGHTER = ("tighten_to_fit", "tighten_page", "align_row_labels", "pair_metadata_rows", "pair_artwork_rows",
           "show_path_end")
tighter = {name: code(name) for name in TIGHTER}
every = "\n".join(tighter.values())
levels = class_value("PAGE_LEVELS") or ()
ALWAYS = {"gap": 8, "row": 4, "log": 4, "bar": (8, 10, 8, 12), "button": 6}  # the page as it always was


def no_looser(tight, than):
    return all(tight[key] <= than[key] if key != "bar" else all(a <= b for a, b in zip(tight[key], than[key]))
               for key in ALWAYS)


print("where the folded page is still too tall, the same page is laid out tighter")
ok("only on a short screen", "if short:\n            self.tighten_to_fit()" in fit
   and "fold_tutorial" not in fit)
ok("every part of it is there", all(tighter.values()))
ok("three levels, each drawn in no less than the one before, and none looser than the page as it always was",
   len(levels) == 3 and all(set(level) == set(ALWAYS) for level in levels)
   and all(no_looser(level, before) for level, before in zip(levels, (ALWAYS,) + tuple(levels))))
ok("the log never asks for fewer than two lines, and no space is drawn in to nothing",
   bool(levels) and all(level["log"] >= 2 and level["gap"] >= 1 and level["row"] >= 1 and level["button"] >= 1
                        and min(level["bar"]) >= 1 for level in levels))
ok("no text is made smaller: no font is named in any of it", "font" not in every)
ok("the window is never resized by it", "geometry" not in "".join(method(src, name) for name in TIGHTER))
ok("no widget is made and none destroyed: the same widgets, read through the same variables",
   not re.search(r"\b(tk|ttk)\.[A-Z]\w*\(", every) and "destroy" not in every)
ok("rows taken out of their column are put back in a grid by the same method",
   all(tighter[name].count("pack_forget()") == 1 and ".grid(" in tighter[name]
       for name in ("pair_metadata_rows", "pair_artwork_rows"))
   and "pack_forget" not in tighter["tighten_to_fit"] + tighter["tighten_page"] + tighter["align_row_labels"])
ok("chosen by laying a level out and asking Tk, not from a list of screens",
   "for level in range(1, len(self.PAGE_LEVELS) + 1):" in tighter["tighten_to_fit"]
   and "self.root.winfo_reqheight() <= self.window_height" in tighter["tighten_to_fit"]
   and not re.search(r"\b(1080|864|816|768|720|672)\b|screenheight|PRETEND", every))


class Page:
    """A page that asks for these lines at each level, in a window that holds so many: no Rialto, no window."""
    PAGE_LEVELS = levels
    page_level = 0

    def __init__(self, holds, asks, breaks_at=None):
        self.root, self.window_height, self.asks, self.breaks_at = self, holds, asks, breaks_at
        self.drawn, self.said = [], []

    def update_idletasks(self):
        pass

    def winfo_reqheight(self):
        return self.asks[self.page_level]

    def tighten_page(self, level):
        if level == self.breaks_at:
            raise tkinter.TclError("pretended")
        self.drawn.append(level)

    def update_status(self, message):
        self.said.append(message)


exec(method(src, "tighten_to_fit"), ns)
MEASURED = [1005, 810, 703, 655]  # what the folded page asks as it always was, and at levels 1, 2 and 3 (96 DPI)


def chosen(holds, breaks_at=None):
    page = Page(holds, MEASURED, breaks_at)
    (ns.get("tighten_to_fit") or (lambda page: None))(page)
    return page.page_level, page.drawn, len(page.said), " ".join(page.said)


print("the level, for a page that asks 1005 lines folded and 810, 703 and 655 at levels 1, 2 and 3")
ok("a window that holds the folded page is left as it always was (1080p at 100 percent: 1032 lines)",
   chosen(1032)[:3] == (0, [], 0) and chosen(1005)[:3] == (0, [], 0))
ok("a 1080p laptop at 125 percent (816 lines): level 1, and nothing said",
   chosen(816)[:3] == (1, [1], 0) and chosen(810)[:3] == (1, [1], 0))
ok("1366 by 768 (720 lines): level 2, by way of level 1",
   chosen(809)[:3] == (2, [1, 2], 0) and chosen(720)[:3] == (2, [1, 2], 0))
ok("1080p at 150 percent (672 lines): level 3", chosen(702)[:3] == (3, [1, 2, 3], 0) and chosen(672)[:3] == (3, [1, 2, 3], 0)
   and chosen(655)[:3] == (3, [1, 2, 3], 0))
ok("a window that holds less than the tightest page: level 3, and one line in the log says what is cut",
   chosen(654)[:3] == (3, [1, 2, 3], 1) and "does not fit this screen" in chosen(654)[3]
   and "655 pixels tall with room for 654" in chosen(654)[3])
ok("if laying a level out raises, Rialto says so once and stays at the level it had",
   chosen(720, breaks_at=2)[:3] == (1, [1], 1) and "could not be laid out tighter" in chosen(720, breaks_at=2)[3])

if failures:
    print("\nFAILED: %d check(s)" % len(failures))
    sys.exit(1)
print("\nAll main-window checks passed.")
