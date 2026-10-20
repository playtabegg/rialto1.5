"""Rialto fits every screen (1.5.1, B13.5): the real windows, under a pretended work area.

A developer on a 1080p laptop with Windows scaling at 125 percent saw the main
window cut off after Step 4's Game Logo row, and Disc Extras stop at Mac and
Linux. The two older fit harnesses read the source text and never open a
window, so nothing tested a short screen. This one builds the real RialtoApp
main window and each real dialog, tells Rialto the screen is one this PC does
not have (RialtoApp.PRETEND_MONITOR, the one place the sizing code asks), lets
Tk lay everything out, and reads the geometry back from Tk and from Windows.

For every window at every work area it answers two questions:
  1. Is the whole window, title bar included, inside the work area, at a
     place Rialto chose? A window Rialto gives no position fails: Windows
     drops it somewhere else on every start.
  2. Is every widget whole? A widget is cut when the layout gave it no room
     (not shown), less room than it asks for (squeezed), or when an edge lies
     outside its window. A scrolling box (the log, a list, a table) may give
     up room down to half of what it asks for; that is noted, not failed. An
     entry may be narrower than it asks. A scrolling area (a page of widgets
     behind a scroll bar, as Configure Code Signing has) must show 200 lines
     of its page or all of it; what sits inside it is not judged.

The main page is held to more than that. Every named part of it (the title
strip, the menu strip, the three-steps card, the quick-action row, Steps 1 to
4, the log, the export bar) must be on the page at every work area, and so
must every widget that is on it on the tall screen: taking a part off the
page, or putting the page behind a scroll bar, is not fitting. Only the
three-steps card's own fold may put widgets away. Nothing on the main page
may scroll (the owner's word of 3 October: the window stays tall, the wide
page and the scroll net were both refused).

Where the folded page is still more than the window holds, Rialto lays the
same page out in fewer lines (B13.2, the candidate "a tighter page": short
fields two to a row, the paddings drawn in, the log asking for fewer lines; up
to three levels, the first that fits). The harness had these to learn about
two fields in one row, and holds the main page to them at every work area:
  a. A box may not be squeezed to nothing. An entry was allowed to be narrower
     than it asks, down to 40 across, because one field to a row never came
     near that. A box on the main page must now show 100 across, and the
     narrowest is named in the table.
  b. A label can cut its own words and still be given all it asks: a label
     told to be so many characters wide asks for that width whatever its words
     are. So the words of every label, button and tick box of the page are
     measured in the widget's own font against the room it was given.
  c. The log must show two whole lines. "Half of what it asks" was the floor,
     which is two lines of a log that asks for four and one of a log that asks
     for two.
  d. The same widgets, read as before. Every widget of the tall page must be
     on the short one under the same Tk name (the standard run measures both),
     not one made in its place. A word is then typed in the box beside each
     label, as a person would, and must come back from a profile under that
     field's own name and from what the build reads; each box must still
     carry its own tooltip; each list and tick box must still be on its own
     variable.
  e. Dark / Light, pressed twice, must leave every widget where it was and the
     page asking for the same lines: a theme change styles every widget again.
  f. What Rialto says as it fits its page is heard. A page that is cut with
     nothing said fails, and so does "could not be laid out tighter".
With --shots the main window is also drawn with a game's details filled in,
which is when a narrow box shows what it costs.

Three things more are asked of the other windows (B13.4):
  3. Is a dialog's title bar dark, where Rialto asks Windows for a dark one?
     In the dark theme, which is what Rialto starts in, that is every themed
     dialog and Rialto's own message box. Windows is asked what the window's
     frame was told (DwmGetWindowAttribute, the same attribute Rialto sets).
     Tk makes a window's frame again when "wm resizable" or "wm transient" is
     called, and the new frame has a light title bar until it is asked again:
     that is how the six fitted dialogs lost theirs. With --shots the picture
     is looked at too, and a title bar drawn light under a frame told "dark"
     fails (Windows 11 fades a title bar to dark over about a third of a
     second; the picture waits for that). Export .msix and the Restore popup
     are plain windows that Rialto asks nothing for; light is not a failure
     there.
  4. When a dialog was given fewer lines than it holds, did Rialto say so in
     its log? Nothing scrolls to make up for it, so what does not fit is cut,
     and a cut with nothing said fails. So does the line when nothing was
     cut. No standard work area is that small: --work-area 1024x552 is.
  5. Two tooltips of the main page are opened as well, the highest and the
     lowest, with the pointer pretended on each one's widget (the real pointer
     is not listened to). A tooltip must be inside the work area, must not
     open under the pointer (it would close itself), and must open below the
     pointer wherever there is room, as it always did.

The checks are kept in four groups, one for each step of B13:
  "window inside the work area"                   the main window (B13.1)
  "every dialog fits"                             each dialog and the two tooltips, every question (B13.4)
  "the main page fits its window"                 the main window's widgets and parts (B13.2)
  "the tall layout is unchanged at 1440 lines"    the pinned numbers below: the window, what the page asks,
                                                  every widget of the page, and each dialog's size

Four ways to run it:
  python tools-dev/test_fits_every_screen.py              the gate: exit 0 only when every group passes
  python tools-dev/test_fits_every_screen.py --expect-red "the main page fits its window"
                                                          the gate while a group is red by design: exit 0 when
                                                          every other group passes AND the named one is red.
                                                          A named group that is not red fails the gate, so the
                                                          name comes off the day it is fixed: while a group is
                                                          named, nothing fails when it breaks. Any part of the
                                                          name that fits one group will do ("main page").
  python tools-dev/test_fits_every_screen.py --report     the same table, always exit 0
  python tools-dev/test_fits_every_screen.py --shots DIR  the table and pictures: each window as drawn, and the
                                                          same window on a screen of that size with its taskbar.
                                                          Exit 0 when every picture was saved.
The standard run pretends six work areas and then measures this PC's own
screen with nothing pretended (--this-pc measures only that): the pretended
ones never run the code that asks Windows for the work area, and a user's PC
runs nothing else. Each window is then judged against what Windows says of
the monitor the main window opened on. Which monitor that is, is Windows'
choice, and what fits depends on the PC: it is the one part of the run whose
numbers are this PC's own.
The work area and Tk's scaling are parameters:
  --work-area 1536x816 --dpi 96      Rialto is handed a 1536 x 864 screen, Tk starts at 96 DPI
  --taskbar-side top --origin=-1536,0   the taskbar along another edge, the screen's corner somewhere else
  --screen 1920x1080 --percent 125   what Windows hands a program that is not DPI-aware (1536 x 864, 96 DPI)
  --screen 1920x1080 --percent 125 --dpi-aware   the real 1920 x 1080 with Tk started at 120 DPI
--dpi and --dpi-aware change Tk's scaling only. The title bar and border
Windows draws stay this PC's own, so a titled window is counted a few lines
shorter than a truly DPI-aware Rialto would show it at 125 percent (about 8).
  --pins   print what the tall layout measures now, in the form PINNED holds, and stop

Each work area is measured in a process of its own, with a time limit, in a
temp folder that stands in for Rialto's own: no config.json of Rialto's is
read or written, no mainloop runs, and anything that would reach the network,
start a program or open a file with Windows is refused and reported. An
exception raised by Rialto's own code while it is measured fails the run.

It is not in run_all.py yet. With B13.1 and B13.4 built, "window inside the
work area", "every dialog fits" and "the tall layout is unchanged" pass at
every work area. "The main page fits its window" failed on the short ones
until a tall design that fits was built (B13.2). On this branch, the
candidate "a tighter page", it passes at every standard work area, so the
gate is the plain run with no group named red. The candidate is one of three
and is not chosen: this harness joins run_all.py when one is. Put the 900
floor back and the first group fails again, and the gate exits 1.
test_main_window_fits.py, which is in run_all.py, no longer asserts that
floor in the source text: it holds the one rule as arithmetic. This harness
opens real windows, so run it alone, never beside another suite.

What depends on this PC's real screen, said plainly:
  - A window Rialto gives no position is placed by Windows on the real screen,
    so where it lands says nothing about another PC. The table marks it with
    a star, and that alone fails it.
  - Windows holds a resizable titled window to the real desktop (Tk's "wm
    maxsize"; 7284 x 1421 on the PC this was written on). The harness raises
    that limit to the pretended screen for every window Rialto opens, so a
    small real screen can measure a large pretended one. A window still held
    is reported as not measured, never as a pass, and has its own line under
    THE HARNESS ITSELF so it is not read as Rialto's failure.
  - Windows draws only the part of a window that is on the real screen. For a
    picture, a window that is partly off it is moved onto it and moved back;
    one too large for the real screen is drawn in part, and the picture says so.
  - A window's size as a person sees it is asked of the desktop compositor.
    When that answer cannot be used, the table says which rectangle was used
    instead, and a titled window measured by Tk's client area alone is not
    measured at all. On a PC whose own display scaling is not 100 percent the
    compositor answers in real pixels; they are scaled back first. That path
    was not run: the PC this was written on is at 100 percent.
  - Whether a title bar is dark is asked of the compositor too. It answers
    on Windows 11 (the PC this was written on); a Windows that will not say
    has the check reported as not measured, never as a pass.
  - Everything else (sizes, what each window asks for, which widgets are cut)
    comes from the layout alone and is the same on any Windows PC at the same
    DPI and fonts. The pretended screen's corner is where --origin puts it:
    the real primary screen's unless said otherwise.
  - Each window is measured in the state named beside it in DIALOGS. The main
    window is measured as Rialto opens, before a game is chosen. In the light
    theme only what the page asks for is measured, not each widget.
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# What the taskbar takes from the bottom of the screen at 100 percent.
TASKBAR = 48

# (work area, what it is, the edge its taskbar is along, the screen's top left corner).
# The first is the tall screen the pinned layout is measured on. The last has a
# work area whose corner is not 0, 0: a taskbar can sit along the top or the
# left, and a monitor left of the main one has negative coordinates.
TALL_WORK_AREA = (2560, 1392)
STANDARD_WORK_AREAS = [
    (TALL_WORK_AREA, "a 1440-line screen at 100 percent", "bottom", (0, 0)),
    ((1920, 1032), "1080p at 100 percent", "bottom", (0, 0)),
    ((1536, 816), "1080p at 125 percent, most laptops", "bottom", (0, 0)),
    ((1366, 720), "1366 x 768", "bottom", (0, 0)),
    ((1280, 672), "1080p at 150 percent", "bottom", (0, 0)),
    ((1536, 816), "a monitor left of the main one, its taskbar along the top", "top", (-1536, 0)),
]

# A scrolling area must show this many lines of its page at 96 DPI, or all of it.
SCROLLING_AREA_SHOWS = 200

# B13.1: "The window is given a position: centred, top and bottom inside the
# work area." A window that Windows places lands somewhere else on every start,
# so every window is asked to have a position Rialto chose.
EVERY_WINDOW_MUST_BE_PLACED = True

GROUPS = ("window inside the work area", "every dialog fits",
          "the main page fits its window", "the tall layout is unchanged at 1440 lines")

# The plain name of each part of the main page, by the attribute RialtoApp keeps it in.
PART_NAMES = {
    "title_bar": "the title strip",
    "menu_bar": "the menu strip",
    "tutorial_box": "the three-steps card",
    "quick_row": "the quick-action row",
    "step_frame": "Step 1",
    "meta_frame": "Step 2",
    "disc_frame": "Step 3",
    "art_frame": "Step 4",
    "status_text": "the log",
    "export_bar": "the export bar",
}
ROLES = dict(PART_NAMES, main_content="the page and the export bar", page_frame="the page",
             disc_bar="the disc fill bar", disc_meter="the disc meter", disc_fill_label="the disc fill line")
for _named_by_its_text in ("step_frame", "meta_frame", "disc_frame", "art_frame"):
    del ROLES[_named_by_its_text]

# Every window Rialto opens itself, each in the state named here: as a
# first-time user opens it, with a one-exe sample game chosen. "open" is the
# RialtoApp method, "expect" is text the window must carry (so a "pick a game
# first" message is never mistaken for the dialog), "over" opens another dialog
# first and makes it the active one, as when Check My Setup is pressed inside
# Configure Code Signing. "dark" is set where Rialto asks Windows for a dark
# title bar in its dark theme (themed_dialog and show_centered_popup do): the
# window must still have one when it is measured.
DIALOGS = [
    {"name": "Games on Disc", "open": "configure_game_exes", "expect": "Games on Disc", "dark": True},
    {"name": "Disc Extras", "open": "configure_disc_extras", "expect": "Disc Extras", "dark": True},
    {"name": "Files to Place on the PC", "open": "configure_placed_files", "expect": "Files to Place on the PC",
     "dark": True},
    {"name": "Build Queue", "open": "configure_build_queue", "expect": "Build Queue", "dark": True},
    {"name": "Configure Code Signing", "open": "configure_signing", "expect": "Configure Code Signing", "dark": True},
    {"name": "Check My Setup", "open": "show_setup_report", "args": "setup report",
     "over": "configure_signing", "expect": "Check My Setup", "dark": True},
    {"name": "Check My Setup, long answers", "open": "show_setup_report", "args": "setup report, long answers",
     "over": "configure_signing", "expect": "Check My Setup", "dark": True},
    {"name": "Export .msix", "open": "export_msix", "expect": "Export .msix"},
    {"name": "Rialto's own message box", "open": "confirm_open_offline_page", "args": ["the Rialto guide"],
     "expect": "Open the Rialto guide", "dark": True},
    {"name": "Rialto's message box, its tallest", "open": "show_centered_popup", "args": "tallest message",
     "expect": "Before the build can start", "dark": True},
    {"name": "Restore Rialto (after minimise)", "open": "_create_restore_listener", "expect": "Restore Rialto"},
]
# The two tooltips opened on the main page, by where their widget is: (name, the lowest or the highest).
TOOLTIPS = [("Tooltip, the highest on the page", False), ("Tooltip, the lowest on the page", True)]
NOT_OPENED = ("every tooltip but the highest and the lowest of the main page; the menus under File, Disc, Tools, "
              "View and Help (Windows places them); Windows' own file pickers and message boxes; the drive picker "
              "in burn_to_master, which no menu or button reaches")

# The words Rialto's log carries when a dialog was given less room than it holds (fit_dialog_to_screen), or
# the main page less than it asks for at its tightest (tighten_to_fit).
SAID_WHEN_CUT = "does not fit this screen"
# The words it carries when laying the main page out tighter raised an error (tighten_to_fit).
SAID_NOT_TIGHTENED = "could not be laid out tighter"

# A box of the main page must show this many pixels across at 96 DPI: about fourteen characters. With one field
# to a row no box came near it; with two to a row a box can be squeezed to nothing and ask for nothing more.
BOX_SHOWS = 100

# Every box of the main page a person types in: the label beside it, the name a profile keeps it under (the
# build reads the same entries and variables), what is typed in it here, and words its tooltip must carry.
# The values are a likely game's, so the picture of the page filled in shows what a narrow box costs.
_ART = "C:/Users/Jane/Documents/Games/Lanterns of the Deep/art/"
READ_FROM = [
    ("Game Title:", "Title", "Lanterns of the Deep", "Your game's title"),
    ("Developer:", "Developer", "Jane Smith Games", "Who made the game"),
    ("Publisher:", "Publisher", "Mock Publishing", "Who is publishing the game"),
    ("Start Menu Name:", "Start Menu Name", "Lanterns of the Deep (Disc)", "Windows Start Menu"),
    ("Copyright Text:", "PublisherText",
     "Developed by Jane Smith Games 2026. Published by Mock Publishing. All rights reserved.", "The copyright line"),
    ("Disc Name:", "DiscName", "LANTERNS_DEEP", "The label players see in File Explorer"),
    ("Menu Background:", "Background", _ART + "menu_background.gif", "The background for your disc's menu"),
    ("Game Logo (.png):", "Logo", _ART + "lanterns_logo.png", "Your game's logo"),
    ("Company Logo (.png):", "CompanyLogo", _ART + "jane_smith_games.png", "Your studio or company logo"),
    ("Game Icon (.ico):", "Icon", _ART + "lanterns.ico", "The icon for your installer"),
    ("Disc Icon (.ico):", "DiscIcon", _ART + "disc.ico", "The icon shown in File Explorer"),
]
# The boxes nobody types in, by the label beside them and their place in its row, and the tick boxes by their
# words: each with the variable of RialtoApp's it must still be on.
PICKED_FROM = [("Games on Disc:", 0, "game_exes_summary_var"), ("Target Media:", 0, "target_media_var"),
               ("Target Media:", 1, "compression_var")]
TICKED = [("Pressed", "pressed_disc_var"), ("Also export for USB", "usb_export_var"),
          ("Sign Final Build", "sign_final_build"), ("Remove WTI Branding", "remove_wti_branding")]

# Every function in Rialto.pyw that makes a window (tk.Toplevel or themed_dialog)
# must be the "open" or "over" of a row above, be opened as a tooltip, or be
# named here with the reason it is not opened. A window added to Rialto later
# fails the run until it is measured or declared.
OPENED_AS_A_TOOLTIP = "ToolTip.show"
DECLARED_NOT_OPENED = {
    "RialtoApp.themed_dialog": "the frame every themed dialog is built in, measured through each of them",
    "RialtoApp.burn_to_master": "its drive picker is reached by no menu or button",
}

CONTAINERS = {"Frame", "TFrame", "Labelframe", "TLabelframe", "Toplevel", "Tk", "Panedwindow", "TPanedwindow"}
SCROLLING_BOXES = {"Text", "Listbox", "Treeview"}  # and a Canvas that has a scroll bar: see scrolling_box
SCROLLS_ACROSS = {"Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox"}

# Pinned on release/1.5.1 after 804bac1 (19 Oct 2026, evening: the three-steps card folded on every
# screen, Build Queue beside Browse, Add Games) by this harness (--pins), at 96 DPI on a
# 1440-line screen: the window, what the page asks for with the three-steps
# card open and folded, where each part of the page sits (top, height), every
# widget of the page (name, the box it is in, left, top, width, height, and 1
# when it is under the three-steps card's fold), and the size of each dialog
# as a person sees it, title bar included.
PINNED = {
    "window": [700, 1200],
    "page_open": 1128,
    "page_folded": 1005,
    "parts": {
        "title_bar": [0, 26],
        "menu_bar": [26, 25],
        "tutorial_box": [59, 31],
        "quick_row": [98, 30],
        "step_frame": [136, 64],
        "meta_frame": [208, 227],
        "disc_frame": [443, 97],
        "art_frame": [548, 217],
        "status_text": [775, 267],
        "export_bar": [1050, 150],
    },
    "dialogs": {
        "Games on Disc": [822, 586],
        "Disc Extras": [1182, 668],
        "Files to Place on the PC": [802, 515],
        "Build Queue": [862, 507],
        "Configure Code Signing": [642, 772],
        "Check My Setup": [662, 766],
        "Check My Setup, long answers": [662, 766],
        "Export .msix": [602, 362],
        "Rialto's own message box": [422, 292],
        "Rialto's message box, its tallest": [422, 492],
        "Restore Rialto (after minimise)": [202, 105],
    },
    "census": [
        ('the title strip', '', 0, 0, 700, 26, 0),
        ('a picture or an empty label', '', 6, 3, 20, 20, 0),
        ('the words "Rialto 1.5.1"', '', 42, 1, 75, 23, 0),
        ('the "X" button beside "Rialto 1.5.1"', '', 675, 0, 17, 26, 0),
        ('the "?" button beside "Rialto 1.5.1"', '', 656, 0, 15, 26, 0),
        ('the menu strip', '', 0, 26, 700, 25, 0),
        ('the "File" button', '', 0, 26, 43, 25, 0),
        ('the "Disc" button', '', 43, 26, 48, 25, 0),
        ('the "Tools" button', '', 91, 26, 56, 25, 0),
        ('the "View" button', '', 147, 26, 51, 25, 0),
        ('the "Help" button', '', 198, 26, 51, 25, 0),
        ('the page and the export bar', '', 0, 51, 700, 1149, 0),
        ('the export bar', '', 0, 1050, 700, 150, 0),
        ('an empty frame', '', 0, 1050, 700, 1, 0),
        ('the "No game folder chosen yet" row', '', 14, 1059, 672, 129, 0),
        ('the "No game folder chosen yet" row', '', 14, 1059, 672, 34, 0),
        ('the disc meter', '', 14, 1059, 34, 34, 0),
        ('the "No game folder chosen yet" row', '', 58, 1059, 628, 34, 0),
        ('the disc fill line', '', 58, 1059, 628, 23, 0),
        ('the disc fill bar', '', 58, 1085, 628, 8, 0),
        ('the "BUILD GAME INSTALLER" row', '', 14, 1103, 672, 47, 0),
        ('the "BUILD GAME INSTALLER" button', '', 14, 1103, 277, 47, 0),
        ('the "Disc Extras" button', '', 299, 1105, 95, 42, 0),
        ('the "Preview Disc Menu" button', '', 402, 1105, 140, 42, 0),
        ('the "Configure Signing" button', '', 550, 1105, 136, 42, 0),
        ('the "Also export for USB" row', '', 14, 1158, 672, 30, 0),
        ('the "Also export for USB" tick box', '', 14, 1162, 126, 21, 0),
        ('the "Sign Final Build" tick box', '', 158, 1162, 106, 21, 0),
        ('the "Remove WTI Branding" tick box', '', 282, 1162, 143, 21, 0),
        ('the "Restore page" button', '', 579, 1158, 107, 30, 0),
        ('the page', '', 10, 59, 680, 991, 0),
        ('the three-steps card', '', 10, 59, 680, 31, 0),
        ('the "Three steps to a disc." row', '', 22, 67, 656, 17, 0),
        ('a picture or an empty label', '', 22, 67, 16, 16, 0),
        ('the words "Three steps to a disc."', '', 47, 67, 602, 17, 0),
        ('the words "Show"', '', 649, 68, 29, 15, 0),
        ('the quick-action row', '', 10, 98, 680, 30, 0),
        ('the "Load Profile" button', '', 10, 98, 113, 30, 0),
        ('the "Save Profile" button', '', 127, 98, 109, 30, 0),
        ('the "Import GOG" button', '', 240, 98, 110, 30, 0),
        ('the "Export .msix" button', '', 354, 98, 109, 30, 0),
        ('the "Dark / Light" button', '', 467, 98, 109, 30, 0),
        ('the "Help Guide" button', '', 580, 98, 110, 30, 0),
        ('"Step 1: your game folder"', '', 10, 136, 680, 64, 0),
        ('the "Browse for your game folder" row', '"Step 1: your game folder"', 17, 158, 666, 35, 0),
        ('the "Browse for your game folder" button beside "or"', '"Step 1: your game folder"', 17, 158, 234, 35, 0),
        ('the words "or"', '"Step 1: your game folder"', 259, 166, 15, 19, 0),
        ('the "Build Queue" button beside "or"', '"Step 1: your game folder"', 282, 159, 108, 33, 0),
        ('the words "No folder chosen yet"', '"Step 1: your game folder"', 400, 166, 279, 19, 0),
        ('"Step 2: metadata"', '', 10, 208, 680, 227, 0),
        ('the "Game Title:" row', '"Step 2: metadata"', 15, 228, 670, 27, 0),
        ('the words "Game Title:"', '"Step 2: metadata"', 15, 232, 142, 19, 0),
        ('the box beside "Game Title:"', '"Step 2: metadata"', 165, 230, 516, 23, 0),
        ('the words "What the game is called"', '"Step 2: metadata"', 172, 233, 142, 19, 0),
        ('the "Developer:" row', '"Step 2: metadata"', 15, 263, 670, 27, 0),
        ('the words "Developer:"', '"Step 2: metadata"', 15, 267, 142, 19, 0),
        ('the box beside "Developer:"', '"Step 2: metadata"', 165, 265, 516, 23, 0),
        ('the words "Who made it: you, your studio, or your team"', '"Step 2: metadata"', 172, 268, 261, 19, 0),
        ('the "Publisher:" row', '"Step 2: metadata"', 15, 298, 670, 27, 0),
        ('the words "Publisher:"', '"Step 2: metadata"', 15, 302, 142, 19, 0),
        ('the box beside "Publisher:"', '"Step 2: metadata"', 165, 300, 516, 23, 0),
        ('the words "Only if someone else is publishing it"', '"Step 2: metadata"', 172, 303, 212, 19, 0),
        ('the "Start Menu Name:" row', '"Step 2: metadata"', 15, 333, 670, 27, 0),
        ('the words "Start Menu Name:"', '"Step 2: metadata"', 15, 337, 142, 19, 0),
        ('the box beside "Start Menu Name:"', '"Step 2: metadata"', 165, 335, 516, 23, 0),
        ('the "Copyright Text:" row', '"Step 2: metadata"', 15, 368, 670, 27, 0),
        ('the words "Copyright Text:"', '"Step 2: metadata"', 15, 372, 142, 19, 0),
        ('the box beside "Copyright Text:"', '"Step 2: metadata"', 165, 370, 516, 23, 0),
        ('the "Disc Name:" row', '"Step 2: metadata"', 15, 403, 670, 27, 0),
        ('the words "Disc Name:"', '"Step 2: metadata"', 15, 407, 142, 19, 0),
        ('the box beside "Disc Name:"', '"Step 2: metadata"', 165, 405, 516, 23, 0),
        ('"Step 3: the disc"', '', 10, 443, 680, 97, 0),
        ('the "Games on Disc:" row', '"Step 3: the disc"', 15, 463, 670, 32, 0),
        ('the words "Games on Disc:"', '"Step 3: the disc"', 15, 469, 142, 19, 0),
        ('the box beside "Games on Disc:"', '"Step 3: the disc"', 161, 467, 423, 23, 0),
        ('the "Add Games..." button beside "Games on Disc:"', '"Step 3: the disc"', 590, 465, 91, 28, 0),
        ('the "Target Media:" row', '"Step 3: the disc"', 15, 503, 670, 32, 0),
        ('the words "Target Media:"', '"Step 3: the disc"', 15, 509, 142, 19, 0),
        ('the box beside "Target Media:"', '"Step 3: the disc"', 161, 508, 172, 21, 0),
        ('the words "Compression:"', '"Step 3: the disc"', 339, 509, 82, 19, 0),
        ('the box beside "Target Media:"', '"Step 3: the disc"', 425, 508, 101, 21, 0),
        ('the "Pressed" tick box', '"Step 3: the disc"', 534, 508, 65, 21, 0),
        ('the "Disc Extras" button beside "Target Media:"', '"Step 3: the disc"', 605, 505, 76, 28, 0),
        ('"Step 4: artwork"', '', 10, 548, 680, 217, 0),
        ('the "Menu Background:" row', '"Step 4: artwork"', 15, 568, 670, 32, 0),
        ('the words "Menu Background:"', '"Step 4: artwork"', 15, 574, 142, 19, 0),
        ('the box beside "Menu Background:"', '"Step 4: artwork"', 161, 572, 445, 23, 0),
        ('the "Browse" button beside "Menu Background:"', '"Step 4: artwork"', 606, 570, 75, 28, 0),
        ('the "Game Logo (.png):" row', '"Step 4: artwork"', 15, 608, 670, 32, 0),
        ('the words "Game Logo (.png):"', '"Step 4: artwork"', 15, 614, 142, 19, 0),
        ('the box beside "Game Logo (.png):"', '"Step 4: artwork"', 161, 612, 445, 23, 0),
        ('the "Browse" button beside "Game Logo (.png):"', '"Step 4: artwork"', 606, 610, 75, 28, 0),
        ('the "Company Logo (.png):" row', '"Step 4: artwork"', 15, 648, 670, 32, 0),
        ('the words "Company Logo (.png):"', '"Step 4: artwork"', 15, 654, 142, 19, 0),
        ('the box beside "Company Logo (.png):"', '"Step 4: artwork"', 161, 652, 445, 23, 0),
        ('the "Browse" button beside "Company Logo (.png):"', '"Step 4: artwork"', 606, 650, 75, 28, 0),
        ('the "Game Icon (.ico):" row', '"Step 4: artwork"', 15, 688, 670, 32, 0),
        ('the words "Game Icon (.ico):"', '"Step 4: artwork"', 15, 694, 142, 19, 0),
        ('the box beside "Game Icon (.ico):"', '"Step 4: artwork"', 161, 692, 445, 23, 0),
        ('the "Browse" button beside "Game Icon (.ico):"', '"Step 4: artwork"', 606, 690, 75, 28, 0),
        ('the "Disc Icon (.ico):" row', '"Step 4: artwork"', 15, 728, 670, 32, 0),
        ('the words "Disc Icon (.ico):"', '"Step 4: artwork"', 15, 734, 142, 19, 0),
        ('the box beside "Disc Icon (.ico):"', '"Step 4: artwork"', 161, 732, 445, 23, 0),
        ('the "Browse" button beside "Disc Icon (.ico):"', '"Step 4: artwork"', 606, 730, 75, 28, 0),
        ('the log', '', 12, 775, 676, 267, 0),
    ],
}


# ======================================================================
# The child: one work area, measured in a process of its own
# ======================================================================

def short(value, limit=60):
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def install_guards(result):
    """Nothing Rialto does while it is measured may leave this PC, start a program or block on a question."""
    import socket
    import urllib.request
    import webbrowser
    import winsound
    from tkinter import filedialog, messagebox

    def refuse(what):
        def refused(*args, **kwargs):
            result["refused"].append("%s %s" % (what, short(args[:1])))
            raise RuntimeError("test_fits_every_screen refuses to %s" % what)
        return refused

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        setattr(subprocess, name, refuse("start a program:"))
    os.startfile = refuse("open with Windows:")
    for name in ("system", "execv", "execve", "spawnv", "spawnve"):
        setattr(os, name, refuse("start a program:"))
    urllib.request.urlopen = refuse("reach the network:")
    urllib.request.urlretrieve = refuse("reach the network:")
    socket.create_connection = refuse("reach the network:")
    socket.getaddrinfo = refuse("reach the network:")
    socket.socket.connect = refuse("reach the network:")
    socket.socket.connect_ex = refuse("reach the network:")
    webbrowser.open = refuse("open a browser:")
    winsound.PlaySound = lambda *args, **kwargs: None

    def answer(name, value):
        def answered(*args, **kwargs):
            result["asked"].append("%s: %s" % (name, short(kwargs.get("title") or args[:1])))
            return value
        return answered

    for name in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, name, answer("messagebox." + name, "ok"))
    for name in ("askyesno", "askokcancel", "askretrycancel", "askquestion", "askyesnocancel"):
        setattr(messagebox, name, answer("messagebox." + name, False))
    for name in ("askdirectory", "askopenfilename", "askopenfilenames", "asksaveasfilename"):
        setattr(filedialog, name, answer("filedialog." + name, ""))


def load_rialto(rialto_path, app_root, result):
    """The real Rialto.pyw, run as a module whose own folder is `app_root`.

    Rialto keeps config.json, last_session.json, input and output beside
    itself, and its first-run step installs from the requirements.txt beside
    itself. Told it lives in an empty temp folder, it finds no requirements to
    install, reads nobody's settings and writes none of its own. Only the
    bundled assets are pointed back at the real ones.
    """
    import types
    # The assets and the modules a dialog imports (rialto.msix_export, rialto.trusted_signing) come from beside the
    # Rialto.pyw being measured, or from this checkout when a lone copy of the file is measured.
    source_dir = os.path.dirname(os.path.abspath(rialto_path))
    if not os.path.isdir(os.path.join(source_dir, "assets")):
        source_dir = REPO
    sys.path.insert(0, source_dir)
    module = types.ModuleType("rialto_under_test")
    module.__file__ = os.path.join(app_root, "Rialto.pyw")
    with open(rialto_path, encoding="utf-8") as f:
        source = f.read()
    exec(compile(source, rialto_path, "exec"), module.__dict__)

    assets = os.path.join(source_dir, "assets")
    module.asset_path = lambda filename: os.path.join(assets, filename)
    # The real pointer is wherever it is, and a tooltip it opened would be taken for the dialog being
    # measured. So a tooltip opens only where the harness says the pointer is (a Pointer) and closes only on
    # the harness's word, and every ToolTip Rialto makes is kept, to find the ones on the main page.
    tooltip = module.ToolTip
    make, show, hide = tooltip.__init__, tooltip.show, tooltip.hide
    module.tooltips_made = []

    def kept(self, *args, **kwargs):
        make(self, *args, **kwargs)
        module.tooltips_made.append(self)
    tooltip.__init__ = kept
    tooltip.show = lambda self, event=None: show(self, event) if isinstance(event, Pointer) else None
    tooltip.hide = lambda self, event=None: hide(self) if event is None else None
    try:
        # The signing details live beside Rialto.pyw (trusted_signing.BASE_DIR). They are never read here.
        from rialto import trusted_signing
        trusted_signing.BASE_DIR = app_root
        trusted_signing.CONFIG_FILE = os.path.join(app_root, "signing_config.json")
        trusted_signing.DLIB_CACHE_DIR = os.path.join(app_root, "tools", "TrustedSigning")
    except Exception as e:
        result["problems"].append("trusted_signing could not be loaded: %s" % e)
    return module


class Pointer:
    """Where the harness says the pointer is, in place of the event Tk sends when the real one enters a widget."""

    def __init__(self, x, y):
        self.x_root, self.y_root = x, y


def tooltip_on_the_page(tips, root, lowest):
    """The ToolTip of the lowest widget on the main page that has one, or of the highest.

    Of the widgets on that row, the one whose words run longest: its tooltip
    is the tallest, and reaches furthest past an edge.
    """
    here = []
    for tip in tips:
        try:
            widget = tip.widget
            if tip.text and widget.winfo_toplevel() is root and widget.winfo_ismapped():
                here.append((widget.winfo_rooty(), widget.winfo_rooty() + widget.winfo_height(), tip))
        except Exception:
            pass
    if not here:
        return None
    end = max(here, key=lambda item: item[1]) if lowest else min(here, key=lambda item: item[0])
    row = [tip for top, bottom, tip in here if top < end[1] and bottom > end[0]]
    return max(row, key=lambda tip: len(tip.text))


def tallest_message():
    """A message that takes Rialto's own box to the tallest it goes (460 lines): seventeen short lines.

    The pre-build check and the Build Queue's summary both show a list, one
    thing to a line, and the box grows 20 lines for each up to that limit.
    """
    return "\n".join(["These need fixing before the build can start:", ""]
                     + ["%2d. A file or a field the build needs is missing." % n for n in range(1, 16)])


def setup_report_long_rows():
    """Check My Setup with seven rows whose answers are as long as trusted_signing.check_environment writes them.

    A found tool is answered with its whole path, and the add-on's refusal
    names two paths, so these wrap to two and three lines where the "not
    found" answers below are one line each. Written out here, not looked up:
    nothing on this PC is read.
    """
    home = "C:\\Users\\A Developer With A Long Name\\Documents\\Rialto 1.5\\tools\\TrustedSigning"
    return [
        ("Signing details", True, "Account 'MyStudioSigningAccount', profile 'MyStudioPublicTrustProfile' - "
                                  "checked from what is on screen; click Save to keep it"),
        ("signtool (Windows SDK)", True,
         "C:\\Program Files (x86)\\Windows Kits\\10\\bin\\10.0.26100.0\\x64\\signtool.exe"),
        ("Microsoft signing add-on", False,
         "%s\\bin\\x64\\Azure.CodeSigning.Dlib.dll is not Microsoft-signed and will not be used. "
         "Delete %s and Rialto will fetch it again." % (home, home)),
        ("Endpoint looks like a real region", False,
         "https://eus.codesigning.azure.net.example.invalid is not an Artifact Signing endpoint - pick your "
         "region from the dropdown to fill it in"),
        ("Azure CLI installed", False, "Install from https://aka.ms/azure-cli then run: az login"),
        ("Signed in to Azure", False, "Install the Azure CLI first"),
        (".NET 8 runtime", False, "only found .NET 6. Install the .NET 8 runtime: "
                                  "https://dotnet.microsoft.com/download/dotnet/8.0"),
    ]


def setup_report_rows():
    """What Check My Setup lists on a PC with the three boxes filled in and nothing installed: seven short rows.

    The real check, with every look at this PC answered "not found", so it
    starts no program and reads no saved details. Its answers are one line
    each; setup_report_long_rows is the same window with the long ones.
    """
    fallback = [(label, False, "Not found on this PC. The signing guide says where to get it.")
                for label in ("Signing details", "signtool (Windows SDK)", "Microsoft signing add-on",
                              "Endpoint looks like a real region", "Azure CLI installed", "Signed in to Azure",
                              ".NET 8 runtime")]
    try:
        from rialto import trusted_signing
        which = shutil.which
        shutil.which = lambda *args, **kwargs: None
        trusted_signing.find_signtool = lambda: None
        trusted_signing.find_dlib = lambda: None
        try:
            rows = trusted_signing.check_environment({
                "endpoint": "https://eus.codesigning.azure.net",
                "account_name": "MyStudioSigning",
                "certificate_profile": "MyStudioPublicTrust"})
        finally:
            shutil.which = which
        return list(rows) or fallback
    except Exception:
        return fallback


# ---- Windows: where a window really is, and what it looks like ----

def windows_api():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")
    gdi32 = ctypes.WinDLL("gdi32")
    dwmapi = ctypes.WinDLL("dwmapi")
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    return ctypes, wintypes, user32, gdi32, dwmapi


def window_boxes(top):
    """(the frame a person sees, Windows' own rectangle for it, how the frame was found), as left, top, width, height.

    Tk knows the client area. The title bar and border are Windows', and its
    rectangle for a titled window includes a resize border nobody can see, so
    the visible frame is asked of the desktop compositor. The compositor
    answers in real pixels; a process that is not DPI-aware on a display
    scaled past 100 percent is handed fewer lines than that, so its answer is
    scaled back to the lines this process is handed before it is compared.
    """
    client = [top.winfo_rootx(), top.winfo_rooty(), top.winfo_width(), top.winfo_height()]
    try:
        ctypes, wintypes, user32, gdi32, dwmapi = windows_api()
        handle = int(top.wm_frame(), 16)
        outer = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(outer)):
            return client, client, "Tk's client area"
        whole = [outer.left, outer.top, outer.right - outer.left, outer.bottom - outer.top]

        def holds(big, small, slack=0):
            return (big[0] - slack <= small[0] and big[1] - slack <= small[1]
                    and small[0] + small[2] <= big[0] + big[2] + slack
                    and small[1] + small[3] <= big[1] + big[3] + slack)

        scale = 1.0
        try:
            screen = user32.GetDC(None)
            handed, real = gdi32.GetDeviceCaps(screen, 10), gdi32.GetDeviceCaps(screen, 117)  # VERTRES, DESKTOPVERTRES
            user32.ReleaseDC(None, screen)
            if handed > 0 and real > handed:
                scale = real / float(handed)
        except Exception:
            pass
        seen = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(handle, 9, ctypes.byref(seen), ctypes.sizeof(seen)) == 0:
            frame = [int(round(edge / scale)) for edge in (seen.left, seen.top, seen.right, seen.bottom)]
            frame = [frame[0], frame[1], frame[2] - frame[0], frame[3] - frame[1]]
            slack = 0 if scale == 1.0 else 1
            if holds(frame, client, slack) and holds(whole, frame, 1):
                return frame, whole, "the visible frame"
        if holds(whole, client):
            return whole, whole, "Windows' rectangle, unseen resize border included"
    except Exception:
        pass
    return client, client, "Tk's client area"


def monitor_of(top):
    """The monitor a window is on, as Windows gives it: its screen and its work area, or None."""
    try:
        ctypes, wintypes, user32, _gdi32, _dwmapi = windows_api()

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
        monitor = user32.MonitorFromWindow(int(top.wm_frame(), 16), 2)  # the nearest, if it straddles two
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        whole, work = info.rcMonitor, info.rcWork
        return {"screen": [whole.left, whole.top, whole.right - whole.left, whole.bottom - whole.top],
                "work_area": [work.left, work.top, work.right - work.left, work.bottom - work.top]}
    except Exception:
        return None


def title_bar_of(top):
    """"dark" or "light": what Windows says this window's frame was told about its title bar.

    None for a window with no title bar, "not said" where Windows will not
    answer. The attribute is the one Rialto sets (DWMWA_USE_IMMERSIVE_DARK_MODE:
    20, and 19 on Windows 10 before version 2004). It belongs to the frame, not
    to the window Tk knows: a frame Tk has made again answers "light" until it
    is asked again.
    """
    if top.wm_overrideredirect():
        return None
    try:
        ctypes, _wintypes, _user32, _gdi32, dwmapi = windows_api()
        handle = int(top.wm_frame(), 16)
        for attribute in (20, 19):
            told = ctypes.c_int(0)
            if dwmapi.DwmGetWindowAttribute(handle, attribute, ctypes.byref(told), ctypes.sizeof(told)) == 0:
                return "dark" if told.value else "light"
    except Exception:
        pass
    return "not said"


def title_bar_drawn(image, lines):
    """"dark" or "light": the title bar as it is in a picture of the window, by the brightness of its top `lines`.

    A dark title bar is near black and a light one near white, whether or not
    the window is the active one, so the middle of the range tells them apart.
    The corners (the icon, the three buttons) and the top edge are left out.
    """
    if lines < 8 or image.width < 32:
        return None
    left = image.width // 4
    strip = image.crop((left, 3, max(left + 8, image.width - 160), lines - 3)).convert("L")
    values = sorted(strip.getdata())
    return "dark" if values[len(values) // 2] < 128 else "light"


def draw_window(top):
    """The whole window as Windows has drawn it, title bar included, as an image of its visible frame.

    Returns (image, note). Windows keeps a picture of every window whether or
    not another window covers it, but only of the part on the real screen.
    """
    from PIL import Image
    ctypes, wintypes, user32, gdi32, _dwmapi = windows_api()

    class BitmapHeader(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    note = ""
    frame, whole, _how = window_boxes(top)
    real_w, real_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    on_screen = (whole[0] >= 0 and whole[1] >= 0
                 and whole[0] + whole[2] <= real_w and whole[1] + whole[3] <= real_h)
    came_from = None
    if not on_screen:
        if whole[2] <= real_w and whole[3] <= real_h:
            came_from = (top.winfo_x(), top.winfo_y())
            top.wm_geometry("+0+0")
            settle(top, 1.0)
            frame, whole, _how = window_boxes(top)
        else:
            note = "larger than this PC's own screen (%d x %d): the part beyond it could not be drawn" % (real_w, real_h)
    try:
        handle = int(top.wm_frame(), 16)
        width, height = whole[2], whole[3]
        window_dc = user32.GetWindowDC(handle)
        memory_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        before = gdi32.SelectObject(memory_dc, bitmap)
        drawn = user32.PrintWindow(handle, memory_dc, 2)  # 2: as the compositor has it
        gdi32.SelectObject(memory_dc, before)
        header = BitmapHeader()
        header.biSize = ctypes.sizeof(header)
        header.biWidth, header.biHeight = width, -height
        header.biPlanes, header.biBitCount = 1, 32
        pixels = ctypes.create_string_buffer(width * height * 4)
        rows = gdi32.GetDIBits(memory_dc, bitmap, 0, height, pixels, ctypes.byref(header), 0)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(handle, window_dc)
        if not drawn or rows != height:
            raise OSError("Windows did not draw the window")
        image = Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1)
        image = image.crop((frame[0] - whole[0], frame[1] - whole[1],
                            frame[0] - whole[0] + frame[2], frame[1] - whole[1] + frame[3]))
    finally:
        if came_from is not None:
            top.wm_geometry("+%d+%d" % came_from)
            settle(top, 1.0)
    return image, note


def on_a_screen(spec, layers, legend):
    """The pretended screen, with the windows where they are and the taskbar over whatever it covers."""
    from PIL import Image, ImageDraw, ImageFont
    corner_x, corner_y, screen_w, screen_h = spec["screen"]
    left, top, width, height = spec["work_area"]
    left, top = left - corner_x, top - corner_y  # the picture's own corner is the screen's
    picture = Image.new("RGB", (screen_w, screen_h), (52, 73, 99))
    for image, (x, y) in layers:
        picture.paste(image, (x - corner_x, y - corner_y))
    draw = ImageDraw.Draw(picture)
    bar = (28, 28, 30)
    # Whatever of the screen is not work area is taskbar. At the bottom, unless the work area says otherwise.
    for box in ((0, top + height, screen_w, screen_h), (0, 0, screen_w, top),
                (0, 0, left, screen_h), (left + width, 0, screen_w, screen_h)):
        if box[2] > box[0] and box[3] > box[1]:
            draw.rectangle(box, fill=bar)
    try:
        font = ImageFont.load_default(size=13)
    except Exception:
        font = ImageFont.load_default()
    strip, strip_top = screen_h - (top + height), top + height
    if strip < 16 and top >= 16:  # the taskbar is along the top
        strip, strip_top = top, 0
    if strip >= 16:
        y = strip_top + max(2, (strip - 34) // 2)
        for line in legend[:2 if strip >= 40 else 1]:
            draw.text((12, y), short(line, 260), fill=(214, 214, 214), font=font)
            y += 17
    return picture


# ---- Tk: laying out, describing and judging ----

def settle(window, seconds=2.5):
    """Run Tk's own events until the window stops changing. No mainloop."""
    last, same, deadline = None, 0, time.time() + seconds
    while time.time() < deadline:
        window.update()
        now = (window.winfo_geometry(), window.winfo_reqwidth(), window.winfo_reqheight(), window.winfo_viewable())
        same = same + 1 if now == last else 0
        last = now
        if same >= 3 and window.winfo_viewable():
            return True
        time.sleep(0.03)
    return False


def own_text(widget):
    try:
        return " ".join(str(widget.cget("text") or "").split())
    except Exception:
        return ""


def managed_children(widget):
    """The children a geometry manager is responsible for. One put away on purpose (pack_forget) is not judged."""
    found = []
    for child in widget.winfo_children():
        try:
            if child.winfo_class() in ("Toplevel", "Menu"):
                continue
            manager = child.winfo_manager()
        except Exception:
            continue
        if manager:
            found.append((child, manager))
    return found


def first_text(widget, depth=4):
    text = own_text(widget)
    if text or depth <= 0:
        return text
    for child, _manager in managed_children(widget):
        text = first_text(child, depth - 1)
        if text:
            return text
    return ""


def all_texts(widget):
    texts = [own_text(widget)]
    for child in widget.winfo_children():
        if child.winfo_class() not in ("Toplevel", "Menu"):
            texts.extend(all_texts(child))
    return [t for t in texts if t]


def count_inside(widget):
    return sum(1 + count_inside(child) for child, _manager in managed_children(widget))


def scrolling_area(widget):
    """Is this a canvas with a scroll bar? The widgets it holds are then a page that scrolls."""
    try:
        return widget.winfo_class() == "Canvas" and bool(
            str(widget.cget("yscrollcommand")) or str(widget.cget("xscrollcommand")))
    except Exception:
        return False


def scrolling_box(widget, kind):
    """A box whose own contents scroll: the log, a list, a table. A canvas that only draws a picture is not one."""
    return kind in SCROLLING_BOXES or (kind == "Canvas" and scrolling_area(widget))


def census(top, roles, fold=None, paths=None):
    """Every widget a geometry manager holds in this window, in the order it was made.

    One row each: [name, the box it is in, left, top, width, height, folds].
    The place is None for a widget the layout gave no room. "folds" is 1 for
    what sits under the three-steps card's fold. A widget put away
    (pack_forget) or behind a scroll bar is not in the list, which is how the
    parent tells that a part of the page has been taken off it. Given a list
    as `paths`, each widget's Tk name goes on it beside its "folds": the name
    Tk gave the widget when it was made, which a widget made in its place
    would not have.
    """
    origin_x, origin_y = top.winfo_rootx(), top.winfo_rooty()
    fold_path = str(fold) if fold is not None else None
    rows = []

    def walk(widget, context, folds):
        for child, manager in managed_children(widget):
            if manager == "canvas" and scrolling_area(widget):
                continue
            name = describe(child, roles)
            in_fold = folds or str(child) == fold_path
            box = [None, None, None, None]
            if child.winfo_ismapped():
                box = [child.winfo_rootx() - origin_x, child.winfo_rooty() - origin_y,
                       child.winfo_width(), child.winfo_height()]
            rows.append([plain(name), plain(context if context != name else "")] + box + [1 if in_fold else 0])
            if paths is not None:
                paths.append([str(child), 1 if in_fold else 0])
            walk(child, name if child.winfo_class() in ("Labelframe", "TLabelframe") else context, in_fold)

    walk(top, "", False)
    return rows


def words_need(widget):
    """The pixels across this widget's own words need, in its own font. None where that cannot be told.

    A label told to be so many characters wide asks for that width whatever
    its words are, so one made narrower to put two fields in a row can cut its
    own words and still be given all it asks. Words that wrap, or run to more
    than one line, are not measured.
    """
    try:
        text = str(widget.cget("text") or "")
        if not text.strip() or "\n" in text:
            return None
        try:
            if int(float(str(widget.cget("wraplength") or 0))) > 0:
                return None
        except Exception:
            pass
        font = ""
        try:
            font = str(widget.cget("font") or "")
        except Exception:
            pass  # a ttk button has no font of its own: its style has
        if not font:
            from tkinter import ttk
            style = ""
            try:
                style = str(widget.cget("style") or "")
            except Exception:
                pass
            font = str(ttk.Style(widget).lookup(style or widget.winfo_class(), "font") or "TkDefaultFont")
        return int(widget.tk.call("font", "measure", font, text))
    except Exception:
        return None


def two_lines_of(widget, asks):
    """The lines of the screen a text box needs to show two whole lines of its words, its own border included."""
    try:
        line = int(widget.tk.call("font", "metrics", widget.cget("font"), "-linespace"))
        return 2 * line + max(0, asks - int(widget.cget("height")) * line)
    except Exception:
        return asks


def log_shows(widget):
    """[the lines of the screen the log was given, the whole lines of its words that is]."""
    try:
        line = int(widget.tk.call("font", "metrics", widget.cget("font"), "-linespace"))
        border = max(0, widget.winfo_reqheight() - int(widget.cget("height")) * line)
        given = widget.winfo_height() if widget.winfo_ismapped() else 0
        return [given, max(0, given - border) // line]
    except Exception:
        return [0, 0]


def boxes_beside(top):
    """{the words of a label: the boxes beside it, in the order they were made}, for every box in this window.

    The same rule describe() names a box by: the first label that shares its
    row. A box put in another field's row would be found beside the wrong label.
    """
    found = {}

    def walk(widget):
        for child in widget.winfo_children():
            kind = child.winfo_class()
            if kind in ("Toplevel", "Menu"):
                continue
            if kind in SCROLLS_ACROSS:
                for sibling in child.master.winfo_children():
                    if sibling is not child and sibling.winfo_class() in ("Label", "TLabel") and own_text(sibling):
                        found.setdefault(own_text(sibling), []).append(child)
                        break
            walk(child)

    walk(top)
    return found


def fields_read(app, module, root):
    """Type a word in the box beside each label, as a person would, and say where Rialto then reads it.

    Returns {"typed": boxes typed in, "others": lists and tick boxes looked
    at, "problems": [...]}. A profile is written from the same entries and
    variables the build reads, so a word that comes back from a profile under
    its own field's name is a word the build would have read. Run last: it
    leaves the page filled in.
    """
    problems = []
    beside = boxes_beside(root)
    tips = getattr(module, "tooltips_made", [])
    typed = 0
    for label, _key, value, tip_words in READ_FROM:
        boxes = beside.get(label) or []
        if len(boxes) != 1:
            problems.append('%d boxes are beside "%s", not one' % (len(boxes), label))
            continue
        box = boxes[0]
        if not box.winfo_ismapped():
            problems.append('the box beside "%s" is not shown' % label)
        try:
            box.delete(0, "end")
            box.insert(0, value)
            typed += 1
        except Exception as e:
            problems.append('the box beside "%s" could not be typed in: %s' % (label, short(e, 80)))
        if not any(tip.widget is box and tip_words in (tip.text or "") for tip in tips):
            problems.append('the box beside "%s" no longer carries its tooltip ("%s...")' % (label, tip_words))
    root.update()
    kept = app.current_profile_data()
    built = {key: entry.get().strip() for key, entry in app.entries.items()}  # as the build reads its four entries
    for label, key, value, _tip_words in READ_FROM:
        if kept.get(key) != value:
            problems.append('what was typed beside "%s" is not what a profile keeps as %s: it keeps "%s"' % (
                label, key, short(kept.get(key), 40)))
        if key in built and built[key] != value:
            problems.append('what was typed beside "%s" is not what the build reads as %s' % (label, key))
    others = 0
    for label, place, attribute in PICKED_FROM:
        boxes = beside.get(label) or []
        others += 1
        if place >= len(boxes) or str(boxes[place].cget("textvariable")) != str(getattr(app, attribute, "")):
            problems.append('box %d beside "%s" is not on RialtoApp.%s' % (place + 1, label, attribute))
    ticks = {}

    def walk(widget):
        for child in widget.winfo_children():
            if child.winfo_class() in ("Checkbutton", "TCheckbutton"):
                ticks[own_text(child)] = child
            if child.winfo_class() not in ("Toplevel", "Menu"):
                walk(child)

    walk(root)
    for words, attribute in TICKED:
        others += 1
        tick = ticks.get(words)
        if tick is None or not tick.winfo_ismapped():
            problems.append('the "%s" tick box is not on the page' % words)
        elif str(tick.cget("variable")) != str(getattr(app, attribute, "")):
            problems.append('the "%s" tick box is not on RialtoApp.%s' % (words, attribute))
    return {"typed": typed, "others": others, "problems": [plain(problem) for problem in problems]}


def theme_twice(app, root, roles, fold):
    """Press Dark / Light twice and say what moved.

    A theme change sets every style again and styles every widget again. The
    page must ask for the same lines in the other theme and after coming
    back, and every widget must be where it was.
    """
    before, asks = census(root, roles, fold=fold), [root.winfo_reqheight()]
    for _press in (1, 2):
        app.toggle_theme()
        settle(root, 1.0)
        asks.append(root.winfo_reqheight())
    after = census(root, roles, fold=fold)
    moved = [index for index in range(max(len(before), len(after)))
             if (before[index] if index < len(before) else None) != (after[index] if index < len(after) else None)]
    return {"asks": asks, "moved": len(moved),
            "first": row_words(after[moved[0]] if moved and moved[0] < len(after) else None) if moved else ""}


def page_parts(app, root):
    """Where each named part of the main page is: on the page, put away, or behind a scroll bar."""
    parts = {}
    for attribute in PART_NAMES:
        widget = getattr(app, attribute, None)
        record = {"exists": False}
        parts[attribute] = record
        try:
            if widget is None or not widget.winfo_exists():
                continue
            put_away, scrolls, node = False, False, widget
            while node is not None and node is not root:
                manager = node.winfo_manager()
                if not manager:
                    put_away = True
                if manager == "canvas" and (node.master.winfo_class() != "Canvas" or scrolling_area(node.master)):
                    scrolls = True  # held by a canvas that scrolls (or by one that cannot be asked)
                node = node.master
            record.update(exists=True, put_away=put_away, scrolls=scrolls, shown=bool(widget.winfo_ismapped()),
                          got=[widget.winfo_width(), widget.winfo_height()],
                          asks=[widget.winfo_reqwidth(), widget.winfo_reqheight()])
        except Exception:
            pass
    return parts


def describe(widget, roles):
    """A widget by its text or its role, the way a person would point at it."""
    path = str(widget)
    if path in roles:
        return roles[path]
    kind = widget.winfo_class()
    text = short(own_text(widget), 48)
    if kind in ("Labelframe", "TLabelframe") and text:
        return '"%s"' % text
    if kind in ("Label", "TLabel", "Message"):
        return 'the words "%s"' % text if text else "a picture or an empty label"
    beside = ""
    try:
        for sibling in widget.master.winfo_children():
            if sibling is not widget and sibling.winfo_class() in ("Label", "TLabel") and own_text(sibling):
                beside = short(own_text(sibling), 48)
                break
    except Exception:
        pass
    # "Browse" is on five buttons: the label of its row says which.
    if kind in ("Button", "TButton", "Menubutton", "TMenubutton") and text:
        return 'the "%s" button%s' % (text, ' beside "%s"' % beside if beside else "")
    if kind in ("Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton") and text:
        return 'the "%s" tick box' % text
    if kind in SCROLLS_ACROSS:
        return 'the box beside "%s"' % beside if beside else "a box to type in"
    if kind == "Text":
        return "a text box"
    if kind in ("Treeview", "Listbox"):
        return "the list"
    if kind in CONTAINERS:
        inside = short(first_text(widget), 48)
        return 'the "%s" row' % inside if inside else "an empty frame"
    return "%s %s" % (kind, path.rsplit(".", 1)[-1])


def audit(top, roles, spec, frame, client, page=False):
    """Every widget of one window: which are cut, and which scrolling boxes gave up room.

    The packer never lets a widget hang out of its window. When room runs out
    it squeezes the last ones and leaves the rest unmapped, so "cut" is read
    from what each widget asks for against what it was given, as well as from
    its edges. `page` is set for the main page, which is held to three things
    more now that it may put two fields in one row: a box shows BOX_SHOWS
    across, a text box shows two whole lines, and every widget's own words
    fit the room it was given.
    """
    line = max(1, int(round(20 * spec["dpi"] / 96.0)))  # one line of a scrolling box
    area_shows = int(round(SCROLLING_AREA_SHOWS * spec["dpi"] / 96.0))
    box_shows = int(round(BOX_SHOWS * spec["dpi"] / 96.0))
    origin_x, origin_y = top.winfo_rootx(), top.winfo_rooty()
    cut, notes, counts = [], [], {"judged": 0, "inside_scrolling_areas": 0}
    lowest = []  # (bottom edge, left edge, name) of every widget with words on it, for "what the screen hides"
    boxes = []   # (width, name) of every box to type in that is shown, for "the narrowest box"

    def shortfall(widget, kind, got_w, got_h, ask_w, ask_h):
        """Why this widget is cut, or None. A scrolling box may give up room down to half of what it asks."""
        if scrolling_box(widget, kind):
            floor = min(ask_h, max(line, (ask_h + 1) // 2))
            if page and kind == "Text":
                floor = max(floor, two_lines_of(widget, ask_h))  # whatever it asks for: a log that asks for one line too
            if got_h < floor:
                return "shows %d of its %d lines%s" % (got_h, ask_h, ", and must show %d" % floor if page else "")
            if got_w < min(ask_w, 2 * line):
                return "shows %d of its %d across" % (got_w, ask_w)
            return None
        if kind in SCROLLS_ACROSS:
            if got_h < ask_h:
                return "shows %d of its %d lines" % (got_h, ask_h)
            if page and got_w < box_shows:
                return "shows %d across, and a box of the main page must show %d" % (got_w, box_shows)
            if got_w < min(ask_w, 2 * line):
                return "shows %d of its %d across" % (got_w, ask_w)
            return None
        problems = []
        if got_h < ask_h:
            problems.append("shows %d of its %d lines" % (got_h, ask_h))
        if got_w < ask_w:
            problems.append("shows %d of its %d across" % (got_w, ask_w))
        elif page:
            need = words_need(widget)
            if need is not None and need > got_w:
                problems.append("shows %d across and its words need %d" % (got_w, need))
        return ", ".join(problems) or None

    def walk(widget, clip, context):
        for child, manager in managed_children(widget):
            kind = child.winfo_class()
            if manager == "canvas" and scrolling_area(widget):
                # A page behind a scroll bar. What is on it is not judged, but enough of it must show.
                counts["inside_scrolling_areas"] += 1 + count_inside(child)
                page, shows = child.winfo_reqheight(), widget.winfo_height()
                if not widget.winfo_ismapped():
                    shows = 0
                if shows < min(page, area_shows):
                    cut.append({"what": "the scrolling area", "in": context,
                                "how": "shows %d lines of a page of %d (it must show %d)" % (
                                    shows, page, min(page, area_shows)),
                                "lines": min(page, area_shows) - shows, "path": str(widget)})
                continue
            counts["judged"] += 1
            name = describe(child, roles)
            where = context if context and context != name else ""
            ask_w, ask_h = child.winfo_reqwidth(), child.winfo_reqheight()

            def report(how, lines):
                cut.append({"what": name, "in": where, "how": how, "lines": lines, "path": str(child)})

            if not child.winfo_ismapped():
                report("is not shown: no room was left for its %d lines" % ask_h, ask_h)
                continue
            x, y = child.winfo_rootx() - origin_x, child.winfo_rooty() - origin_y
            got_w, got_h = child.winfo_width(), child.winfo_height()
            if kind not in CONTAINERS and own_text(child):
                lowest.append((y + got_h, x, name))
            if kind in ("Entry", "TEntry"):
                boxes.append((got_w, name))

            below, past = (y + got_h) - clip[3], (x + got_w) - clip[2]
            above, before = clip[1] - y, clip[0] - x
            if below > 0 or past > 0 or above > 0 or before > 0:
                sides = [text % amount for amount, text in (
                    (below, "%d lines below the edge of what holds it"), (past, "%d past its right edge"),
                    (above, "%d lines above its top edge"), (before, "%d before its left edge")) if amount > 0]
                report("lies " + ", ".join(sides), max(below, past, above, before))
                continue

            children = managed_children(child)
            if kind in CONTAINERS:
                squeezed = got_h < ask_h or got_w < ask_w
                plain_row = children and all(c.winfo_class() not in CONTAINERS for c, _m in children)
                if squeezed and plain_row and any(
                        (not c.winfo_ismapped()) or shortfall(c, c.winfo_class(), c.winfo_width(), c.winfo_height(),
                                                             c.winfo_reqwidth(), c.winfo_reqheight())
                        for c, _m in children):
                    # One row, said once, rather than its label, its box and its button.
                    how = []
                    if got_h < ask_h:
                        how.append("shows %d of its %d lines" % (got_h, ask_h))
                    if got_w < ask_w:
                        how.append("shows %d of its %d across" % (got_w, ask_w))
                    report(", ".join(how), max(ask_h - got_h, ask_w - got_w))
                    continue
            else:
                problem = shortfall(child, kind, got_w, got_h, ask_w, ask_h)
                if problem:
                    report(problem, max(ask_h - got_h, ask_w - got_w))
                    continue
                if scrolling_box(child, kind) and got_h < ask_h:
                    notes.append("%s gives up %d of its %d lines" % (name, ask_h - got_h, ask_h))
            if children:
                inner = (max(clip[0], x), max(clip[1], y), min(clip[2], x + got_w), min(clip[3], y + got_h))
                walk(child, inner, name if kind in ("Labelframe", "TLabelframe") else context)

    walk(top, (0, 0, top.winfo_width(), top.winfo_height()), "")

    # Moved as high as it will go, what would still lie below the work area?
    title_bar = client[1] - frame[1]
    reach = spec["work_area"][3] - title_bar
    hidden = [name for bottom, _x, name in sorted(lowest) if bottom > reach]
    return {"cut": cut, "notes": notes, "judged": counts["judged"],
            "inside_scrolling_areas": counts["inside_scrolling_areas"],
            "below_the_work_area_at_best": hidden,
            "narrowest_box": list(min(boxes)) if boxes else None}


def measure(top, name, kind, spec, roles, asked):
    client = [top.winfo_rootx(), top.winfo_rooty(), top.winfo_width(), top.winfo_height()]
    frame, _whole, how = window_boxes(top)
    wanted = asked.get(str(top))
    record = {
        "name": name, "kind": kind, "opened": True,
        "frame": frame, "frame_from": how, "client": client,
        "asks": [top.winfo_reqwidth(), top.winfo_reqheight()],
        "titled": not bool(top.wm_overrideredirect()),
        "title_bar": title_bar_of(top),
        "placed_by_rialto": bool(top.wm_positionfrom()),
        "asked_size": wanted,
        "held": bool(wanted) and list(wanted) != client[2:],
    }
    record.update(audit(top, roles, spec, frame, client, page=(kind == "main")))
    return record


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def where_in_rialto(trace, rialto_path):
    """' (Rialto.pyw line N, in function)': the innermost place in the file under test that a traceback passes through."""
    try:
        wanted = os.path.normcase(os.path.abspath(rialto_path))
        for frame in reversed(traceback.extract_tb(trace)):
            if os.path.normcase(os.path.abspath(frame.filename)) == wanted:
                return " (%s line %d, in %s)" % (os.path.basename(rialto_path), frame.lineno, frame.name)
    except Exception:
        pass
    return ""


def measure_work_area(spec, result):
    import tkinter as tk

    app_root = spec["app_root"]
    module = load_rialto(spec["rialto"], app_root, result)
    if not hasattr(module.RialtoApp, "PRETEND_MONITOR") or not hasattr(module.RialtoApp, "available_space"):
        raise RuntimeError("this Rialto.pyw has no RialtoApp.PRETEND_MONITOR / available_space: "
                           "the sizing code cannot be told about a pretended screen")
    real = bool(spec.get("real"))  # this PC's own screen: Rialto asks Windows itself, as it does for a user
    screen_w, screen_h = spec["screen"][2:]
    if not real:
        module.RialtoApp.PRETEND_MONITOR = {"screen": tuple(spec["screen"]),
                                            "work_area": tuple(spec["work_area"])}

    created = []
    make_toplevel = tk.Toplevel.__init__

    def tracked_toplevel(self, *args, **kwargs):
        make_toplevel(self, *args, **kwargs)
        created.append(self)
        # Windows holds a titled window to this PC's own desktop. The pretended screen may be larger.
        try:
            limit_w, limit_h = self.wm_maxsize()
            self.wm_maxsize(max(limit_w, screen_w), max(limit_h, screen_h))
        except Exception:
            pass
    tk.Toplevel.__init__ = tracked_toplevel

    asked = {}  # the size Rialto last asked for each window, to tell when this PC held it smaller
    set_geometry = tk.Wm.wm_geometry

    def tracked_geometry(self, newGeometry=None):
        size = re.match(r"=?(\d+)x(\d+)", str(newGeometry or ""))
        if size:
            asked[str(self)] = [int(size.group(1)), int(size.group(2))]
        return set_geometry(self, newGeometry)
    tk.Wm.wm_geometry = tk.Wm.geometry = tracked_geometry

    waiting = {"now": 0}  # above 0 while a dialog of Rialto's is inside its own wait_window
    wait_for_window = tk.Misc.wait_window

    def tracked_wait(self, window=None):
        waiting["now"] += 1
        try:
            return wait_for_window(self, window)
        finally:
            waiting["now"] -= 1
    tk.Misc.wait_window = tracked_wait

    def alive(windows):
        kept = []
        for window in windows:
            try:
                if window.winfo_exists():
                    kept.append(window)
            except Exception:
                pass
        return kept

    shots = spec.get("shots")
    pictures = result["pictures"]

    def save_pictures(number, record, top, behind, frame=None):
        if not shots:
            return None
        try:
            image, note = draw_window(top)
            if record.get("titled"):
                # Windows 11 fades a title bar to dark over about a third of a second once it is asked, and a
                # picture taken in the fade is grey. It is waited out, two seconds at most, before it is called light.
                lines, began = record["client"][1] - record["frame"][1], time.time()
                drawn = title_bar_drawn(image, lines)
                while record.get("title_bar") == "dark" and drawn == "light" and time.time() - began < 2:
                    top.update()
                    time.sleep(0.1)
                    image, note = draw_window(top)
                    drawn = title_bar_drawn(image, lines)
                record["title_bar_drawn"] = drawn
            base = os.path.join(shots, "%02d-%s" % (number, slug(record["name"])))
            image.save(base + ".png")
            frame = frame or record["frame"]
            legend = ["%s: %d x %d at +%d+%d%s" % (
                          record["name"], frame[2], frame[3], frame[0], frame[1],
                          "" if record["placed_by_rialto"] or record["kind"] != "main" else
                          " (Rialto gives it no position: drawn at the top centre of the work area)"),
                      "%s. %s" % (spec["label"], note)]
            on_a_screen(spec, behind + [(image, (frame[0], frame[1]))], legend).save(base + ".on-screen.png")
            pictures.append(base + ".png")
            pictures.append(base + ".on-screen.png")
            if note:
                record["picture_note"] = note
            return image
        except Exception as e:
            result["picture_problems"].append("%s: %s" % (record["name"], e))
            return None

    root = None
    try:
        module.ensure_structure()
        root = tk.Tk()
        result["this_pc"] = {"screen": [root.winfo_screenwidth(), root.winfo_screenheight()],
                             "dpi": round(root.winfo_fpixels("1i"), 1)}
        if real:
            spec["dpi"] = result["this_pc"]["dpi"]
        else:
            root.tk.call("tk", "scaling", spec["dpi"] / 72.0)

        def callback_raised(kind, value, trace):
            # Rialto's own code raised inside Tk's event loop. Tk would print it and carry on; here it fails the run.
            result["problems"].append("a Tk callback raised %s: %s%s" % (
                getattr(kind, "__name__", kind), short(value, 200), where_in_rialto(trace, spec["rialto"])))
        root.report_callback_exception = callback_raised
        app = module.RialtoApp(root)
        said = []  # every line Rialto writes to its log from here on, to tell what it said as each dialog opened
        write_to_log = app.update_status

        def heard(message):
            # Its words, without the sign Rialto puts in front of a warning (not ASCII, and the report is).
            said.append(short(str(message).encode("ascii", "ignore").decode("ascii"), 400))
            return write_to_log(message)
        app.update_status = heard
        dark_theme = app.theme_mode.get() == "dark"
        settle(root)
        result["tk_dpi"] = round(root.winfo_fpixels("1i"), 1)
        if real:
            # Judged against what Windows says of the monitor the main window is on, asked here by the
            # harness's own call, not through Rialto's.
            monitor = monitor_of(root)
            if monitor is None:
                raise RuntimeError("Windows would not say which monitor Rialto opened on")
            spec.update(monitor)
            result["monitor"] = monitor

        roles = {}
        for attribute, role in ROLES.items():
            widget = getattr(app, attribute, None)
            if widget is not None:
                roles[str(widget)] = role

        # ---- the main window, as Rialto opened it ----
        main = measure(root, "Main window", "main", spec, roles, asked)
        more = getattr(app, "tutorial_more", None)
        if more is not None:
            main["card"] = "open" if more.winfo_manager() else "folded"
        main["parts"] = page_parts(app, root)
        main["paths"] = []
        main["census"] = census(root, roles, fold=more, paths=main["paths"])
        # How far Rialto drew its page in to fit this window (B13.2), what it said as it did, and what the log got.
        main["level"] = int(getattr(app, "page_level", 0) or 0)
        main["levels"] = len(getattr(app, "PAGE_LEVELS", ()) or ())
        main["said"] = list(said)
        main["log"] = log_shows(app.status_text)
        result["windows"].append(main)

        if spec.get("tall"):
            # The pinned layout: read here, as Rialto opened. The fold comes last, after every other measure.
            tall = {"window": main["client"][2:], "card_at_start": main.get("card"), "parts": {},
                    "page_as_opened": main["asks"][1]}
            for attribute in PINNED["parts"]:
                widget = getattr(app, attribute, None)
                if widget is not None and widget.winfo_ismapped():
                    tall["parts"][attribute] = [widget.winfo_rooty() - root.winfo_rooty(), widget.winfo_height()]
            result["tall"] = tall

        # ---- the dialogs, over a main window that stays put ----
        if not main["placed_by_rialto"]:
            # Windows chose the spot, and every dialog is centred on the main
            # window. So the dialogs can be measured twice and agree, the main
            # window goes to the top centre of the work area: as far inside
            # as it can be.
            left, top_edge, width, _height = spec["work_area"]
            spot = (left + max(0, (width - main["frame"][2]) // 2), top_edge)
            root.wm_geometry("+%d+%d" % spot)
            settle(root, 1.5)
            main["moved_for_the_dialogs"] = list(spot)
            main["frame_for_the_dialogs"] = window_boxes(root)[0]
        shown_frame = main.get("frame_for_the_dialogs", main["frame"])
        main_picture = save_pictures(0, main, root, [], frame=shown_frame)
        behind_all = [(main_picture, (shown_frame[0], shown_frame[1]))] if main_picture is not None else []

        # ---- two tooltips of the main page, the pointer pretended on each one's widget ----
        # The lowest is the one that ran under the taskbar: the pointer goes on its widget's last line. The
        # highest has room below it on every screen, and must open where it always did.
        for number, (name, lowest) in enumerate(TOOLTIPS, start=len(DIALOGS) + 1):
            record = {"name": name, "kind": "tooltip", "opened": False}
            result["windows"].append(record)
            tip, mark = None, len(created)
            try:
                tip = tooltip_on_the_page(getattr(module, "tooltips_made", []), root, lowest)
                if tip is None:
                    raise RuntimeError("no widget on the main page has a tooltip")
                widget = tip.widget
                pointer = [widget.winfo_rootx() + widget.winfo_width() // 2,
                           widget.winfo_rooty() + (widget.winfo_height() - 1 if lowest else 0)]
                tip.show(Pointer(*pointer))
                opened = alive(created[mark:])
                if not opened:
                    raise RuntimeError("it opened no window")
                settle(opened[-1], 1.5)
                record.update(measure(opened[-1], name, "tooltip", spec, roles, asked))
                record["pointer"], record["of"] = pointer, plain(describe(widget, roles))
                save_pictures(number, record, opened[-1], list(behind_all))
            except Exception as e:
                record["problem"] = "it could not be opened and measured: %s" % short(e, 200)
            finally:
                try:
                    if tip is not None:
                        tip.hide()
                except Exception:
                    pass
                for window in alive(created[mark:]):
                    try:
                        window.destroy()
                    except Exception:
                        pass
                root.update()

        game = os.path.join(app_root, "input", "Sample Game")
        os.makedirs(game, exist_ok=True)
        with open(os.path.join(game, "SampleGame.exe"), "wb") as f:
            f.write(b"MZ")
        app.current_game_path = game
        app.game_path_var.set(game)
        root.update()

        for number, recipe in enumerate(DIALOGS, start=1):
            record = {"name": recipe["name"], "kind": "dialog", "opened": False,
                      "wants_dark": bool(recipe.get("dark")) and dark_theme}
            result["windows"].append(record)
            opener = getattr(app, recipe["open"], None)
            if opener is None:
                record["problem"] = "RialtoApp has no %s any more" % recipe["open"]
                continue
            args = recipe.get("args", [])
            if args == "setup report":
                args = [setup_report_rows()]
            elif args == "setup report, long answers":
                args = [setup_report_long_rows()]
            elif args == "tallest message":
                args = ["Before the build can start", tallest_message()]

            behind = list(behind_all)
            parent_window = None
            try:
                if recipe.get("over"):
                    mark = len(created)
                    getattr(app, recipe["over"])()
                    opened = alive(created[mark:])
                    if not opened:
                        raise RuntimeError("%s opened no window to stand over" % recipe["over"])
                    parent_window = opened[-1]
                    settle(parent_window)
                    app.active_parent = lambda parent_window=parent_window: parent_window
                    if shots:
                        try:
                            image, _note = draw_window(parent_window)
                            box = window_boxes(parent_window)[0]
                            behind.append((image, (box[0], box[1])))
                        except Exception:
                            pass

                mark = len(created)
                state = {"tries": 0, "said_before": len(said)}

                def look(mark=mark, state=state, record=record, recipe=recipe, number=number, behind=behind):
                    # Runs from Tk's own event loop: inside the dialog's wait if it waits, after it returns if not.
                    # Never while the dialog is still being built.
                    opened = alive(created[mark:])
                    ready = opened and (state.get("returned") or waiting["now"])
                    state["tries"] += 1
                    if not ready and state["tries"] < 40:
                        root.after(100, look)
                        return
                    try:
                        if not ready:
                            record["problem"] = "it opened no window" if not opened else "it never finished opening"
                        else:
                            window = opened[-1]
                            settle(window)
                            carried = [window.wm_title()] + all_texts(window)
                            if not any(recipe["expect"] in text for text in carried):
                                record["problem"] = "it opened something else: %s" % short(
                                    " / ".join(carried[:3]), 120)
                            else:
                                record.update(measure(window, recipe["name"], "dialog", spec, roles, asked))
                                record["said"] = said[state["said_before"]:]
                                save_pictures(number, record, window, behind)
                    except Exception as e:
                        record["problem"] = "it could not be measured: %s" % short(e, 200)
                    finally:
                        for window in alive(created[mark:]):
                            try:
                                window.destroy()
                            except Exception:
                                pass
                        state["done"] = True

                root.after(150, look)
                try:
                    opener(*args)
                except Exception as e:
                    record.setdefault("problem", "opening it raised %s: %s" % (type(e).__name__, short(e, 200)))
                state["returned"] = True
                deadline = time.time() + 12
                while not state.get("done") and time.time() < deadline:
                    root.update()
                    time.sleep(0.02)
                if not state.get("done"):
                    record.setdefault("problem", "it did not open within 12 seconds")
            except Exception as e:
                record.setdefault("problem", "%s: %s" % (type(e).__name__, short(e, 200)))
            finally:
                if "active_parent" in vars(app):
                    del app.active_parent
                for window in alive(created):
                    try:
                        window.destroy()
                    except Exception:
                        pass
                root.update()

        # What the page asks for with the three-steps card open and folded, by Rialto's own fold, at every
        # work area: the next design is drawn from these. Last, after every other measure, and then put back.
        try:
            app.fold_tutorial(False)
            root.update_idletasks()
            main["page_open"] = root.winfo_reqheight()
            if spec.get("tall"):
                # The card starts folded on every screen since 19 Oct 2026, so the census never sees its
                # own lines: judged here instead, opened on the tall screen, each line's words against the
                # room it is given.
                over, stack = [], [app.tutorial_more]
                while stack:
                    widget = stack.pop()
                    stack.extend(widget.winfo_children())
                    need = words_need(widget)
                    if need is not None and need > widget.winfo_width():
                        over.append("%s needs %d across and has %d" % (
                            short(str(widget.cget("text")), 48), need, widget.winfo_width()))
                main["card_open_over"] = over
            app.fold_tutorial(True)
            root.update_idletasks()
            main["page_folded"] = root.winfo_reqheight()
            app.fold_tutorial(main.get("card") == "folded")
            root.update_idletasks()
        except Exception as e:
            main["page_problem"] = "the three-steps card could not be folded and opened: %s" % e
        if spec.get("tall"):
            result["tall"]["page_open"] = main.get("page_open")
            result["tall"]["card_open_over"] = main.get("card_open_over")
            result["tall"]["page_folded"] = main.get("page_folded")
            if main.get("page_problem"):
                result["tall"]["problem"] = main["page_problem"]

        # ---- the page is still the same page, however it was laid out (B13.2) ----
        # Last of all: the second leaves the page filled in, and the picture of that is the last one taken.
        try:
            main["theme_twice"] = theme_twice(app, root, roles, more)
        except Exception as e:
            main["theme_twice"] = {"problem": "Dark / Light could not be pressed twice: %s" % short(e, 160)}
        try:
            main["fields"] = fields_read(app, module, root)
            # The rest of what a person sees once a game is chosen, in the words Rialto itself logs.
            chosen = _ART.rsplit("/", 2)[0]
            app.game_path_var.set(chosen)
            app.update_status("\U0001F4C1 Game folder: %s" % chosen)
            app.update_status("✅ Selected animated GIF background: menu_background.gif")
            app.update_status("✅ Selected game logo: lanterns_logo.png")
            app._fill_bytes = 3400000000  # the disc meter's line for a game of that size, with no folder walked
            app.draw_disc_meter()
            settle(root, 1.0)
            main["filled_asks"] = root.winfo_reqheight()
            save_pictures(len(DIALOGS) + len(TOOLTIPS) + 1, dict(main, name="Main window, a game's details filled in"),
                          root, [], frame=shown_frame)
        except Exception as e:
            main["fields"] = {"typed": 0, "others": 0,
                              "problems": ["the page could not be filled in: %s" % plain(short(e, 160))]}
    finally:
        left_open = len(alive(created))
        for window in alive(created):
            try:
                window.destroy()
            except Exception:
                pass
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        result["windows_left_open"] = left_open


def child_main(spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    result = {"measured": False, "windows": [], "refused": [], "asked": [], "problems": [],
              "pictures": [], "picture_problems": []}

    def write():
        with open(spec["out"], "w", encoding="utf-8") as f:
            json.dump(result, f)

    # Out of time: stop at once, windows and all. The parent reads exit code 3 as "stopped at the time limit".
    import threading
    limit = threading.Timer(spec["time_limit"], lambda: os._exit(3))
    limit.daemon = True
    limit.start()
    code = 0
    try:
        sys.dont_write_bytecode = True
        install_guards(result)
        measure_work_area(spec, result)
        result["measured"] = True
    except BaseException:
        result["crash"] = traceback.format_exc()
        result["crash_at"] = where_in_rialto(sys.exc_info()[2], spec["rialto"])
        code = 1
    limit.cancel()
    write()
    return code


# ======================================================================
# The parent: pretend each screen, judge, print one table
# ======================================================================

def machine(work_area, what, dpi, taskbar=TASKBAR, tall=False, side="bottom", origin=(0, 0)):
    """One pretended monitor: its screen and its work area as (left, top, width, height), and how to name it."""
    width, height = work_area
    corner_x, corner_y = origin
    across = side in ("left", "right")
    screen = [corner_x, corner_y, width + (taskbar if across else 0), height + (0 if across else taskbar)]
    area = [corner_x + (taskbar if side == "left" else 0), corner_y + (taskbar if side == "top" else 0),
            width, height]
    moved = area[0] != 0 or area[1] != 0
    column = "%d x %d" % (width, height) + (" at %d,%d" % (area[0], area[1]) if moved else "")
    return {
        "screen": screen,
        "work_area": area,
        "dpi": float(dpi),
        "tall": tall,
        "what": what,
        "column": column,
        "label": "%s work area (%s; a %d x %d screen to Rialto%s, taskbar %d%s), Tk at %g DPI" % (
            column, what, screen[2], screen[3],
            " whose corner is at %d,%d" % (corner_x, corner_y) if (corner_x or corner_y) else "",
            taskbar, "" if side == "bottom" else " along the %s" % side, dpi),
        "folder": "%dx%d-%gdpi%s" % (width, height, dpi, "-at%d_%d" % (area[0], area[1]) if moved else ""),
    }


def this_pc():
    """This PC's own screen, not pretended: Rialto asks Windows for the work area, as it does on a user's PC.

    The pretended screens never run the code that asks Windows. This one does,
    and each window is judged against what Windows says of the monitor the
    main window opened on. Which monitor that is, is Windows' choice, and what
    fits depends on the PC, so it is the one part of the standard run whose
    numbers are this PC's own.
    """
    return {"real": True, "screen": [0, 0, 0, 0], "work_area": [0, 0, 0, 0], "dpi": 96.0, "tall": False,
            "what": "this PC's own screen", "column": "this PC",
            "label": "this PC's own screen, not pretended: Rialto asks Windows for the work area",
            "folder": "this-pc"}


def size_of(text):
    found = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", text)
    if not found:
        raise argparse.ArgumentTypeError("%r is not a size like 1536x816" % text)
    return int(found.group(1)), int(found.group(2))


def corner_of(text):
    found = re.fullmatch(r"\s*(-?\d+)\s*,\s*(-?\d+)\s*", text)
    if not found:
        raise argparse.ArgumentTypeError("%r is not a corner like -1536,0" % text)
    return int(found.group(1)), int(found.group(2))


def group_named(text):
    """The one group `text` names: its whole name, or any part of it that fits no other group."""
    wanted = " ".join(text.lower().split())
    found = [name for name in GROUPS if name == wanted] or [name for name in GROUPS if wanted and wanted in name]
    if len(found) != 1:
        raise argparse.ArgumentTypeError("%r names %s. The groups are: %s" % (
            text, "no group" if not found else "%d groups" % len(found), "; ".join('"%s"' % name for name in GROUPS)))
    return found[0]


def machines_from(options):
    dpi = options.dpi if options.dpi else 96.0
    side, origin = options.taskbar_side, options.origin
    if options.screen:
        factor = options.percent / 100.0
        width, height = options.screen
        if options.dpi_aware:
            bar = int(round(options.taskbar * factor))
            return [machine((width, height - bar),
                            "a %d x %d screen at %g percent, as a DPI-aware program is handed it" % (
                                width, height, options.percent),
                            options.dpi or 96.0 * factor, bar, side=side or "bottom", origin=origin or (0, 0))]
        seen_w, seen_h = int(round(width / factor)), int(round(height / factor))
        return [machine((seen_w, seen_h - options.taskbar),
                        "a %d x %d screen at %g percent, as a program that is not DPI-aware is handed it" % (
                            width, height, options.percent), dpi, options.taskbar,
                        side=side or "bottom", origin=origin or (0, 0))]
    if options.work_area:
        return [machine(area, "asked for", dpi, options.taskbar, side=side or "bottom", origin=origin or (0, 0))
                for area in options.work_area]
    if options.this_pc:
        return [this_pc()]
    # The standard run: each with its own taskbar edge and corner, unless the command line names them for all.
    # Last, when nothing about the screens was changed on the command line, this PC's own.
    standard = [machine(area, what, dpi, options.taskbar, side=side or its_side, origin=origin or its_corner,
                        tall=(area == TALL_WORK_AREA and dpi == 96.0 and options.taskbar == TASKBAR
                              and (side or its_side) == "bottom" and (origin or its_corner) == (0, 0)))
                for area, what, its_side, its_corner in STANDARD_WORK_AREAS]
    if not (options.dpi or side or origin or options.taskbar != TASKBAR):
        standard.append(this_pc())
    return standard


def worktree_listing(skip):
    """Every file in the worktree with its size and time, to show the run left nothing behind.

    Rialto's own settings (config.json, last_session.json, .deps_installed,
    signing_config.json) and any __pycache__ would show up here. Git's folder,
    a virtual environment and the game folders are not Rialto's settings and
    are not walked.
    """
    listing = {}
    skip = os.path.normcase(os.path.abspath(skip)) if skip else None
    for folder, folders, files in os.walk(REPO):
        if folder == REPO:
            folders[:] = [f for f in folders if f not in (".git", "venv", "input", "output", "build", "dist")]
        folders[:] = [f for f in folders
                      if os.path.normcase(os.path.abspath(os.path.join(folder, f))) != skip]
        for name in files:
            path = os.path.join(folder, name)
            try:
                status = os.stat(path)
                listing[os.path.relpath(path, REPO)] = (status.st_size, status.st_mtime_ns)
            except OSError:
                pass
    return listing


def run_child(spec, time_limit):
    """Measure one work area in a process of its own. Returns its result, measured or not."""
    spec_path = spec["app_root"] + ".spec.json"
    spec["out"] = spec["app_root"] + ".result.json"
    spec["time_limit"] = time_limit
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    stderr, out_of_time = "", False
    try:
        # The child stops itself at the time limit. If it cannot, it is killed 20 seconds later.
        proc = subprocess.run([sys.executable, "-B", os.path.abspath(__file__), "--child", spec_path],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=env, timeout=time_limit + 20)
        stderr, out_of_time = proc.stderr or "", proc.returncode == 3
    except subprocess.TimeoutExpired:
        out_of_time = True
    try:
        with open(spec["out"], encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError):
        result = {"measured": False, "windows": [], "refused": [], "asked": [], "problems": [],
                  "pictures": [], "picture_problems": []}
    if out_of_time:
        result["measured"] = False
        result["problems"] = ["stopped: it ran past its time limit of %d seconds" % time_limit]
    elif not result.get("measured"):
        result.setdefault("crash", stderr.strip()[-1500:] or "the measuring process ended without a result")
    return result


def judge_inside(window, work_area):
    """Is the whole window inside the work area, where Rialto put it? Returns (ok, a few words, the full reasons)."""
    x, y, width, height = window["frame"]
    left, top, area_w, area_h = work_area
    words, reasons = [], []
    too_tall, too_wide = height - area_h, width - area_w
    if too_tall > 0:
        words.append("%d too tall" % too_tall)
        reasons.append("it is %d lines tall%s and the work area has %d: %d too many" % (
            height, " with its title bar" if window.get("titled") else "", area_h, too_tall))
    if too_wide > 0:
        words.append("%d too wide" % too_wide)
        reasons.append("it is %d across and the work area has %d: %d too many" % (width, area_w, too_wide))
    edge_words, edge_reasons = [], []
    for amount, word, reason in (
            ((y + height) - (top + area_h), "%d below", "its bottom edge is %d lines below the work area"),
            ((x + width) - (left + area_w), "%d past the right", "its right edge is %d past the work area"),
            (top - y, "%d above", "its top edge is %d lines above the work area"),
            (left - x, "%d off the left", "its left edge is %d before the work area")):
        if amount > 0:
            edge_reasons.append(reason % amount)
            if not (too_tall > 0 and "below" in word) and not (too_wide > 0 and "right" in word):
                edge_words.append(word % amount)
    if EVERY_WINDOW_MUST_BE_PLACED and not window.get("placed_by_rialto"):
        # Where Windows dropped it on this PC is no measure of another PC: said, not counted in lines.
        words.append("no position")
        reasons.append("Rialto gives it no position: Windows put it at +%d+%d on this PC this run (%s) "
                       "and will put it somewhere else on the next" % (
                           x, y, ", ".join(edge_reasons) or "inside the work area, this once"))
    else:
        words += edge_words
        reasons += edge_reasons
    ok = not reasons
    if window.get("held"):
        ok = False
        words.append("held by this PC")
        reasons.append("NOT MEASURED: Rialto asked for %d x %d and this PC's own screen held it to %d x %d" % (
            window["asked_size"][0], window["asked_size"][1], window["client"][2], window["client"][3]))
    if window.get("titled") and window.get("frame_from") == "Tk's client area":
        ok = False
        words.append("frame not measured")
        reasons.append("NOT MEASURED: Windows would not say where this window's title bar and border are, so only "
                       "what it holds was measured and its title bar could lie outside the work area unseen")
    return ok, ", ".join(words), reasons


def judge_widgets(window):
    """Is every widget whole? Returns (ok, a few words, the full reasons)."""
    cut = window.get("cut", [])
    asks, holds = window["asks"][1], window["client"][3]
    over = asks - holds
    words, reasons = [], []
    if cut:
        words.append("%d cut" % len(cut))
        if over > 0 and not window.get("inside_scrolling_areas"):
            words.append("%d over" % over)
            reasons.append("its contents ask for %d lines and the window holds %d: %d over" % (asks, holds, over))
        shown = ["%s%s %s" % (c["what"], ' in %s' % c["in"] if c.get("in") else "", c["how"]) for c in cut[:5]]
        if len(cut) > 5:
            shown.append("and %d more" % (len(cut) - 5))
        reasons.append("cut: " + "; ".join(shown))
    return not cut, ", ".join(words), reasons


def judge_title_bar(window):
    """Is the title bar dark where Rialto asks for a dark one? Returns (ok, a few words, the full reasons)."""
    if not window.get("wants_dark"):
        return True, "", []
    told, drawn = window.get("title_bar"), window.get("title_bar_drawn")
    if told == "dark" and drawn != "light":
        return True, "", []
    if told == "dark":
        return False, "title bar drawn light", [
            "Windows says this window's frame was told to draw a dark title bar, and in the picture it is still "
            "light two seconds on (a picture cannot tell light from a bright accent colour, if Windows is set to "
            "put its accent colour on title bars and this window was the active one)"]
    if told == "light":
        return False, "title bar not dark", [
            "Rialto asks Windows for a dark title bar on this window, and the frame it has when it is measured was "
            "not told: it was never asked, or the frame was made again after it was (Tk makes one again for "
            "\"wm resizable\" and \"wm transient\")"]
    return False, "title bar not measured", [
        "NOT MEASURED: Windows would not say whether this window's title bar is dark, so the picture is the only "
        "witness (--shots)"]


def judge_said(window):
    """Given less room than it holds, did Rialto say so in its log? Returns (ok, a few words, the full reasons).

    Nothing scrolls to make up for a screen that is too small, so what does
    not fit is cut. Saying nothing of it fails, and so does saying it of a
    dialog that was given all it holds. Less width than the widgets ask is
    Rialto's own choice on a screen that has more, and is judged by the
    widgets alone.
    """
    spoke = [line for line in window.get("said") or [] if SAID_WHEN_CUT in line]
    short = window["asks"][1] - window["client"][3]
    if short > 0 and not spoke:
        return False, "nothing said", ["it was given %d lines fewer than it holds and Rialto's log says nothing of it"
                                       % short]
    if spoke and short <= 0 and window["asks"][0] <= window["client"][2]:
        return False, "said cut, and is not", ["Rialto's log says it does not fit, and it was given all it holds"]
    return True, "", []


def judge_tooltip(window, work_area):
    """A tooltip, beyond being inside the work area. Returns (ok, a few words, the full reasons, where it opened).

    Under the pointer it takes the pointer from its widget and closes itself,
    so it must be clear of it. And where there is room below the pointer it
    opens there, 10 lines under it, as it always did.
    """
    x, y, width, height = window["frame"]
    pointer_x, pointer_y = window["pointer"]
    words, reasons = [], []
    where = "below the pointer" if y > pointer_y else "above the pointer" if y + height <= pointer_y else "over it"
    if x <= pointer_x < x + width and y <= pointer_y < y + height:
        words.append("under the pointer")
        reasons.append("it opened under the pointer, which takes the pointer from its widget and closes it")
    room_below = pointer_y + 10 + height <= work_area[1] + work_area[3]
    if room_below and y != pointer_y + 10:
        words.append("not where it always opened")
        reasons.append("there was room below the pointer and it opened %d lines from it, not 10 below" % (y - pointer_y))
    return not reasons, ", ".join(words), reasons, where


def judge_page(window, tall_paths=None):
    """The main page, beyond its widgets being whole. Returns (ok, a few words, the full reasons).

    Every named part is on the page, every widget that is on it on the tall
    screen is on it here (the three-steps card's own fold aside), and nothing
    scrolls. Without this a page "fits" when the parts that do not fit are
    taken off it or put behind a scroll bar. And however Rialto laid the page
    out to fit (B13.2), it is the same page: the same widgets under the same
    Tk names as on the tall screen (`tall_paths`, when the tall screen was
    measured in this run), each read as before, the same after Dark / Light.
    """
    words, reasons = [], []
    folded = window.get("card") == "folded"

    said = window.get("said") or []
    over = window["asks"][1] - window["client"][3]
    if any(SAID_NOT_TIGHTENED in line for line in said):
        words.append("not laid out tighter")
        reasons.append("Rialto's log says its page could not be laid out tighter: %s" % next(
            line for line in said if SAID_NOT_TIGHTENED in line))
    spoke = any(SAID_WHEN_CUT in line for line in said)
    if over > 0 and not spoke:
        words.append("nothing said")
        reasons.append("the page asks for %d lines more than the window holds and Rialto's log says nothing of it" % over)
    if spoke and over <= 0:
        words.append("said cut, and is not")
        reasons.append("Rialto's log says its page does not fit, and the window holds all the page asks for")

    if tall_paths is not None:
        here_paths = set(path for path, _folds in window.get("paths") or [])
        other = [path for path, folds in tall_paths if path not in here_paths and not (folds and folded)]
        if other:
            words.append("%d not the same widget" % len(other))
            reasons.append("%d widget%s of the tall page %s not on this page under the name Tk gave %s: %s%s" % (
                len(other), "" if len(other) == 1 else "s", "is" if len(other) == 1 else "are",
                "it" if len(other) == 1 else "them", ", ".join(other[:4]),
                ", and %d more" % (len(other) - 4) if len(other) > 4 else ""))

    theme = window.get("theme_twice")
    if theme is not None:
        asks = theme.get("asks") or []
        if theme.get("problem"):
            words.append("Dark / Light not pressed")
            reasons.append(theme["problem"])
        elif len(set(asks)) > 1 or theme.get("moved"):
            words.append("moved by Dark / Light")
            reasons.append("Dark / Light pressed twice: the page asked for %s lines (before, in the other theme, back "
                           "again) and %d widgets are not where they were%s" % (
                               ", ".join(str(n) for n in asks), theme.get("moved", 0),
                               ", the first: %s" % theme["first"] if theme.get("first") else ""))

    fields = window.get("fields")
    if fields is not None and fields.get("problems"):
        words.append("%d not read as before" % len(fields["problems"]))
        reasons.append("; ".join(fields["problems"][:6]) + (
            "; and %d more" % (len(fields["problems"]) - 6) if len(fields["problems"]) > 6 else ""))
    filled, asked_empty = window.get("filled_asks"), (window.get("theme_twice") or {}).get("asks") or []
    if filled is not None and asked_empty and filled > asked_empty[0]:
        words.append("taller when filled in")
        reasons.append("with a game's details typed in the page asks for %d lines, and %d before" % (
            filled, asked_empty[0]))

    absent = []
    for attribute, name in PART_NAMES.items():
        part = (window.get("parts") or {}).get(attribute)
        if part is None:
            absent.append("%s was not looked for" % name)
        elif not part.get("exists"):
            absent.append("%s is gone from the page" % name)
        elif part.get("scrolls"):
            absent.append("%s sits behind a scroll bar" % name)
        elif part.get("put_away"):
            absent.append("%s is not on the page: Rialto put it away" % name)
    if absent:
        words.append("%d part%s not on the page" % (len(absent), "" if len(absent) == 1 else "s"))
        reasons.append("; ".join(absent))
    scrolling = window.get("inside_scrolling_areas", 0)
    if scrolling:
        words.append("the page scrolls")
        reasons.append("%d widgets of the main page sit in a scrolling area, and nothing on the main page may scroll"
                       % scrolling)

    here = {}
    for row in window.get("census") or []:
        here[(row[0], row[1])] = here.get((row[0], row[1]), 0) + 1
    folded = window.get("card") == "folded"
    missing = []
    for row in PINNED["census"]:
        key = (row[0], row[1])
        if here.get(key, 0) > 0:
            here[key] -= 1
        elif not (row[6] and folded):  # the three-steps card's own fold is the one way a widget may be put away
            missing.append(row[0] + (" in %s" % row[1] if row[1] else ""))
    if missing:
        words.append("%d missing" % len(missing))
        reasons.append("%d widget%s on the page on the tall screen %s not on it here: %s%s" % (
            len(missing), "" if len(missing) == 1 else "s", "is" if len(missing) == 1 else "are",
            ", ".join(missing[:6]), ", and %d more" % (len(missing) - 6) if len(missing) > 6 else ""))
    return not reasons, ", ".join(words), reasons


def window_makers(rialto_path):
    """{function: line} for every function in the file under test that makes a window.

    A window is made by tk.Toplevel(...) or by themed_dialog(...). The function
    is named as Class.method; what a method's inner functions do is the
    method's.
    """
    with open(rialto_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    makers = {}

    def walk(node, owner):
        for child in ast.iter_child_nodes(node):
            inside = owner
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                inside = owner + [child.name]
            if isinstance(child, ast.Call):
                called = child.func.attr if isinstance(child.func, ast.Attribute) else getattr(child.func, "id", "")
                if called in ("Toplevel", "themed_dialog"):
                    makers.setdefault(".".join(owner[:2]) or "the top of the file", child.lineno)
            walk(child, inside)

    walk(tree, [])
    return makers


def unaccounted_windows(rialto_path):
    """Every place Rialto makes a window that DIALOGS does not open and DECLARED_NOT_OPENED does not name."""
    try:
        makers = window_makers(rialto_path)
    except (OSError, SyntaxError, ValueError) as e:
        return 0, ["the file could not be read for its windows: %s" % short(e, 120)]
    accounted = set(DECLARED_NOT_OPENED) | {OPENED_AS_A_TOOLTIP}
    for recipe in DIALOGS:
        accounted.add("RialtoApp." + recipe["open"])
        if recipe.get("over"):
            accounted.add("RialtoApp." + recipe["over"])
    return len(makers), ["%s (line %d)" % (name, line) for name, line in sorted(makers.items(), key=lambda m: m[1])
                         if name not in accounted]


def plain(text):
    return str(text).replace(chr(0x2026), "...").encode("ascii", "replace").decode("ascii")


def row_words(row):
    if row is None:
        return "nothing"
    name = row[0] + (" in %s" % row[1] if row[1] else "")
    if row[2] is None:
        return "%s, given no room" % name
    return "%s at %d, %d, %d x %d" % (name, row[2], row[3], row[4], row[5])


def over_words(asks, holds):
    if asks is None:
        return "not measured"
    return "%d (%s)" % (asks, "fits" if asks <= holds else "%d over" % (asks - holds))


def report(machines, results, options, leftovers, temp_gone, took):
    """Print the one table and the groups. Returns the groups as {name: (passed, why)}."""
    lines = []
    say = lines.append
    this_pc = next((r.get("this_pc") for r in results if r.get("this_pc")), None)
    say("Rialto fits every screen (B13.5). The real windows, laid out by Tk under a pretended work area.")
    say("Rialto.pyw: %s" % options.rialto)
    if this_pc:
        say("This PC's own screen: %d x %d, %g DPI to Tk. Windows holds a titled window to the real desktop; the "
            "harness raises that limit to the pretended screen for each window Rialto opens." % (
                this_pc["screen"][0], this_pc["screen"][1], this_pc["dpi"]))
    say("Sizes are the window as a person sees it, title bar included, in lines of the screen Rialto is handed.")
    say("")

    failing = {name: [] for name in GROUPS}
    unmeasured, held, pages, same = [], [], [], []
    matrix = {}  # window -> one mark per work area, for the summary
    bars = {}    # titled window -> (does Rialto ask for a dark title bar, {work area: what its frame was told})
    # The Tk name of every widget of the tall page, when the tall screen is in this run: a short page must be
    # made of the same widgets, not of ones made in their place.
    tall_paths = next((r["windows"][0].get("paths") for s, r in zip(machines, results)
                       if s.get("tall") and r.get("measured") and r.get("windows")), None)
    for spec, result in zip(machines, results):
        say("== %s ==" % spec["label"])
        area = spec["column"]
        if not result.get("measured"):
            unmeasured.append(spec["label"])
            crash = (result.get("crash") or "").strip().splitlines()
            say("  NOT MEASURED. %s" % plain("; ".join(result.get("problems", []))
                                             or short(crash[-1] if crash else "", 400) + result.get("crash_at", "")))
            say("")
            for name in GROUPS[:3]:
                failing[name].append("%s: not measured" % area)
            continue
        say("  %-34s %-12s %-12s %-34s %s" % ("window", "size", "at", "inside the work area", "every widget whole"))
        details, starred = [], False
        for window in result["windows"]:
            name = window["name"]
            is_main = window["kind"] == "main"
            if not window.get("opened") or window.get("problem"):
                say("  %-34s %s" % (name, "NOT MEASURED: " + plain(window.get("problem", "it did not open"))))
                failing["every dialog fits"].append("%s at %s: not measured" % (name, area))
                matrix.setdefault(name, {})[area] = "not measured"
                continue
            inside_ok, inside_words, inside_why = judge_inside(window, spec["work_area"])
            whole_ok, whole_words, whole_why = judge_widgets(window)
            more_ok, more_words, more_why, opened_where = True, "", [], ""  # what only a dialog or a tooltip is asked
            if is_main:
                page_ok, page_words, page_why = judge_page(window, tall_paths)
                whole_ok = whole_ok and page_ok
                whole_words = ", ".join(w for w in (whole_words, page_words) if w)
                whole_why = whole_why + page_why
            elif window["kind"] == "tooltip":
                more_ok, more_words, more_why, opened_where = judge_tooltip(window, spec["work_area"])
                more_why = ["the pointer: " + why for why in more_why]
            else:
                bar_ok, bar_words, bar_why = judge_title_bar(window)
                said_ok, said_words, said_why = judge_said(window)
                more_ok = bar_ok and said_ok
                more_words = ", ".join(w for w in (bar_words, said_words) if w)
                more_why = ["title bar: " + why for why in bar_why] + ["the log: " + why for why in said_why]
            if window.get("title_bar"):
                bars.setdefault(name, (bool(window.get("wants_dark")), {}))[1][area] = window["title_bar"] + (
                    ", drawn light" if window["title_bar"] == "dark" and window.get("title_bar_drawn") == "light"
                    else "")
            if window.get("held"):
                held.append("%s at %s" % (name, area))
            x, y, width, height = window["frame"]
            star = "" if window["placed_by_rialto"] else " *"
            starred = starred or bool(star)
            say("  %-34s %-12s %-12s %-34s %s" % (
                name, "%d x %d" % (width, height), "+%d+%d%s" % (x, y, star),
                "ok" if inside_ok else "FAIL " + inside_words,
                ("ok" if whole_ok else "FAIL " + whole_words) + " (%d judged)" % window.get("judged", 0)
                + ("" if more_ok else "; FAIL " + more_words)))
            for why in more_why:
                details.append("  %s, %s." % (name, plain(why)))
            for line in window.get("said") or []:
                if SAID_WHEN_CUT in line:
                    details.append("  %s, said in Rialto's log: %s" % (name, plain(line)))
            if opened_where:
                details.append("  %s, noted: of %s, the pointer pretended at +%d+%d: it opened %s." % (
                    name, window.get("of", "a widget"), window["pointer"][0], window["pointer"][1], opened_where))
            if not inside_ok:
                details.append("  %s, inside the work area: %s." % (name, plain("; ".join(inside_why))))
                hidden = window.get("below_the_work_area_at_best") or []
                if hidden and height > spec["work_area"][3]:
                    details.append("      Moved as high as it will go, these are still below the work area: %s%s." % (
                        plain(", ".join(hidden[:8])), ", and %d more" % (len(hidden) - 8) if len(hidden) > 8 else ""))
            if not whole_ok:
                for why in whole_why:
                    details.append("  %s, widgets: %s." % (name, plain(why)))
            for note in window.get("notes", []):
                details.append("  %s, noted: %s (a scrolling box: not a failure)." % (name, plain(note)))
            if window.get("inside_scrolling_areas") and not is_main:
                details.append("  %s, noted: %d widgets sit in a scrolling area and are not judged." % (
                    name, window["inside_scrolling_areas"]))
            if window.get("frame_from") and window["frame_from"] != "the visible frame":
                details.append("  %s, measured from %s, not from the frame a person sees." % (name, window["frame_from"]))
            if window.get("picture_note"):
                details.append("  %s, picture: %s." % (name, plain(window["picture_note"])))
            matrix.setdefault(name, {})[area] = "%s / %s" % ("ok" if inside_ok else "FAIL",
                                                           "ok" if whole_ok and more_ok else "FAIL")
            if is_main:
                if not inside_ok:
                    failing["window inside the work area"].append("%s (%s)" % (area, inside_words))
                if not whole_ok:
                    failing["the main page fits its window"].append("%s (%s)" % (area, whole_words))
            elif not (inside_ok and whole_ok and more_ok):
                failing["every dialog fits"].append("%s at %s (%s)" % (
                    name, area, "; ".join(w for w in (inside_words, whole_words, more_words) if w)))
        main = result["windows"][0] if result["windows"] else {}
        if starred:
            say("  * Rialto gave this window no position. Windows chose it, on this PC's real screen.")
        if main.get("moved_for_the_dialogs"):
            say("  The dialogs were opened with the main window moved to +%d+%d (top centre of the work area), "
                "so they land in the same place every run." % tuple(main["moved_for_the_dialogs"]))
        if main.get("card"):
            holds = main["client"][3]
            log, box = main.get("log") or [0, 0], main.get("narrowest_box")
            pages.append((area, holds, main.get("page_folded"), main.get("page_open"), main["card"],
                          main.get("level", 0), log, box))
            say("  Main window: Rialto opened with the three-steps card %s. The window holds %d lines; the page asks "
                "for %s with the card folded and %s with it open." % (
                    main["card"], holds, over_words(main.get("page_folded"), holds),
                    over_words(main.get("page_open"), holds)))
            if main.get("page_problem"):
                say("  Main window: %s." % plain(main["page_problem"]))
            say("  Main window: the page is laid out at level %d of %d (0 is the page as it always was). The log "
                "shows %d whole line%s of its words (%d lines of the screen).%s" % (
                    main.get("level", 0), main.get("levels", 0), log[1], "" if log[1] == 1 else "s", log[0],
                    " The narrowest box to type in is %d across: %s." % (box[0], plain(box[1])) if box else ""))
            for line in main.get("said") or []:
                if SAID_NOT_TIGHTENED in line:  # what it says when the page is cut is printed with its other details
                    say("  Main window, said in Rialto's log: %s" % plain(line))
            # The same page: the same widgets, read as before, the same after Dark / Light.
            theme, fields = main.get("theme_twice") or {}, main.get("fields") or {}
            folded_here = main["card"] == "folded"
            names = None
            if tall_paths is not None:
                wanted = [path for path, folds in tall_paths if not (folds and folded_here)]
                here_paths = set(path for path, _folds in main.get("paths") or [])
                names = (sum(1 for path in wanted if path in here_paths), len(wanted))
            same.append((area, main.get("level", 0), names, fields, theme, main.get("filled_asks")))
        if abs(result.get("tk_dpi", spec["dpi"]) - spec["dpi"]) > 1:
            say("  Tk was started at %g DPI and Rialto left it at %g." % (spec["dpi"], result["tk_dpi"]))
        if this_pc and abs(spec["dpi"] - this_pc["dpi"]) > 1:
            say("  Tk's scaling only: the title bar and border Windows draws stay this PC's own (%g DPI), so a titled "
                "window is counted a few lines shorter than it would be on a PC really at %g DPI." % (
                    this_pc["dpi"], spec["dpi"]))
        for line in details:
            say(line)
        for problem in result.get("problems", []):
            say("  PROBLEM: %s" % plain(problem))
        say("")

    # ---- every window at every work area, at a glance ----
    areas = [spec["column"] for spec in machines]
    say("EVERY WINDOW AT EVERY WORK AREA (inside the work area / every widget whole; for a dialog also its title "
        "bar and what the log said, for a tooltip also where it opened)")
    say("  %-34s %s" % ("window", " ".join(area.ljust(max(13, len(area))) for area in areas)))
    for name, marks in matrix.items():
        say("  %-34s %s" % (name, " ".join(marks.get(area, "not measured").ljust(max(13, len(area)))
                                         for area in areas)))
    say("")

    # ---- the title bars: one line a window, since the work area does not change what a frame is told ----
    say("THE TITLE BARS (what Windows says each window's frame was told, in Rialto's dark theme%s)" % (
        "; and the picture, where it differs" if options.shots else ""))
    for name, (wants_dark, told) in bars.items():
        kinds = sorted(set(told.values()))
        if len(kinds) == 1 and len(told) == len(areas):
            words = "%s at every work area" % kinds[0]
        else:
            words = "; ".join("%s at %s" % (kind, ", ".join(a for a in areas if told.get(a) == kind)) for kind in kinds)
        say("  [%s] %-34s %s%s" % (
            "--  " if not wants_dark else "OK  " if kinds == ["dark"] else "FAIL", name, words,
            "" if wants_dark else " (a plain window: Rialto asks Windows for no dark one)"))
    say("")

    # ---- what the main page asks of its window: the numbers the next design is drawn from ----
    say("THE MAIN PAGE AGAINST ITS WINDOW (lines the page asks for; over is how many more than the window holds)")
    say("  %-24s %-14s %-18s %-18s %-16s %-7s %-14s %s" % (
        "work area", "window holds", "card folded", "card open", "as Rialto opens", "level", "the log shows",
        "the narrowest box to type in"))
    for area, holds, folded, opened, card, level, log, box in pages:
        say("  %-24s %-14d %-18s %-18s %-16s %-7d %-14s %s" % (
            area, holds, over_words(folded, holds), over_words(opened, holds), card, level,
            "%d line%s (%d)" % (log[1], "" if log[1] == 1 else "s", log[0]),
            "%d across, %s" % (box[0], plain(box[1])) if box else "none"))
    say("  Widgets are judged as Rialto opens, with the three-steps card folded: it starts folded on every screen")
    say("  (19 Oct 2026). Show opens it, and the page then asks the \"card open\" figure.")
    say("  Level: how far Rialto drew the page in to fit (B13.2). 0 is the page as it always was; at 1 Step 2 is two")
    say("  fields to a row and the paddings are drawn in; at 2 Step 4's logos and icons are two to a row as well; 3")
    say("  is as tight as it goes. The log: whole lines of its words, and the lines of the screen it was given.")
    say("")

    # ---- the same page, however it was laid out ----
    say("THE SAME PAGE, HOWEVER IT IS LAID OUT (the same widgets, read as before, the same after Dark / Light)")
    for area, level, names, fields, theme, filled in same:
        asks = theme.get("asks") or []
        marks = [
            "not compared with the tall page (it is measured with the standard work areas)" if names is None else
            "%d of the tall page's %d widgets are here under the same Tk name" % names,
            "the fields could not be typed in" if not fields else
            "%d boxes typed in and %d lists and tick boxes looked at: %s" % (
                fields.get("typed", 0), fields.get("others", 0),
                "each read as before, each box with its own tooltip" if not fields.get("problems")
                else "%d NOT as before" % len(fields["problems"])),
            plain(theme["problem"]) if theme.get("problem") else "Dark / Light not pressed" if not asks else
            "Dark / Light twice: the page asks %s, %s" % (
                " then ".join(str(n) for n in asks),
                "nothing moved" if not theme.get("moved") else "%d widgets MOVED" % theme["moved"]),
            "" if filled is None else "filled in, the page asks %d" % filled,
        ]
        say("  %-24s level %d: %s." % (area, level, "; ".join(mark for mark in marks if mark)))
    say("")

    # ---- the tall layout ----
    tall_spec = next(((s, r) for s, r in zip(machines, results) if s.get("tall")), None)
    tall_why = []
    say("THE TALL LAYOUT AT 1440 LINES (pinned on release/1.5.1 after 804bac1, 19 Oct 2026, 96 DPI)")
    if tall_spec is None:
        say("  not asked for in this run (it is measured with the standard work areas at 96 DPI)")
    elif not tall_spec[1].get("tall"):
        tall_why.append("not measured")
        say("  NOT MEASURED")
    else:
        tall = tall_spec[1]["tall"]
        rows = [("the window", "%d x %d" % tuple(tall.get("window", [0, 0])), "%d x %d" % tuple(PINNED["window"])),
                ("the page asks, card open", str(tall.get("page_open")), str(PINNED["page_open"])),
                ("the page asks, card folded", str(tall.get("page_folded")), str(PINNED["page_folded"])),
                ("the card as Rialto opens", str(tall.get("card_at_start")), "folded"),
                ("the card's lines, opened: words cut",
                 "; ".join(tall["card_open_over"]) if tall.get("card_open_over") else
                 ("none" if tall.get("card_open_over") == [] else "not measured"), "none")]
        for attribute, pinned in PINNED["parts"].items():
            got = tall.get("parts", {}).get(attribute)
            rows.append(("%s (top, height)" % PART_NAMES[attribute],
                         "%d, %d" % tuple(got) if got else "not shown", "%d, %d" % tuple(pinned)))
        windows = tall_spec[1].get("windows", [])
        sizes = {w["name"]: w["frame"][2:] for w in windows[1:]
                 if w["kind"] == "dialog" and w.get("opened") and not w.get("problem")}
        for name in list(PINNED["dialogs"]) + [name for name in sizes if name not in PINNED["dialogs"]]:
            pinned = PINNED["dialogs"].get(name)
            rows.append(("%s (size)" % name, "%d x %d" % tuple(sizes[name]) if name in sizes else "not measured",
                         "%d x %d" % tuple(pinned) if pinned else "nothing: not pinned"))
        for label, got, pinned in rows:
            same = got == pinned
            if not same:
                tall_why.append("%s is %s, pinned %s" % (label, got, pinned))
            say("  [%s] %-42s %-12s pinned %s" % ("OK  " if same else "FAIL", label, got, pinned))
        # Every widget of the page: its name, the box it is in, where it is and how large.
        measured = [list(row) for row in (windows[0].get("census") if windows else None) or []]
        pinned = [list(row) for row in PINNED["census"]]
        differ = [index for index in range(max(len(measured), len(pinned)))
                  if (measured[index] if index < len(measured) else None)
                  != (pinned[index] if index < len(pinned) else None)]
        say("  [%s] %-42s %-12s pinned %d" % ("OK  " if not differ else "FAIL",
                                               "every widget of the page (place and size)", len(measured), len(pinned)))
        if differ:
            tall_why.append("%d of the page's widgets are not as pinned (%d measured, %d pinned)" % (
                len(differ), len(measured), len(pinned)))
            for index in differ[:6]:
                say("           widget %d: %s; pinned: %s" % (
                    index + 1, plain(row_words(measured[index] if index < len(measured) else None)),
                    plain(row_words(pinned[index] if index < len(pinned) else None))))
            if len(differ) > 6:
                say("           and %d more" % (len(differ) - 6))
        if tall.get("problem"):
            tall_why.append(tall["problem"])
            say("  [FAIL] %s" % plain(tall["problem"]))
    say("")

    # ---- the harness itself ----
    refused = [item for r in results for item in r.get("refused", [])]
    asked = [item for r in results for item in r.get("asked", [])]
    raised = ["%s: %s" % (spec["column"], problem) for spec, r in zip(machines, results) if r.get("measured")
              for problem in r.get("problems", [])]
    left_open = sum(r.get("windows_left_open", 0) for r in results)
    makers, unaccounted = unaccounted_windows(options.rialto)
    harness = [
        ("every work area was measured inside its time limit (%d seconds each; the run took %d)" % (
            options.time_limit, took), not unmeasured, "; ".join(unmeasured)),
        ("nothing of Rialto's own raised an error while it was measured", not raised, plain("; ".join(raised[:6]))),
        ("Rialto reached for no network, started no program and no build", not refused, plain("; ".join(refused[:6]))),
        ("Rialto asked Windows no question that would have waited for an answer", not asked, plain("; ".join(asked[:6]))),
        ("every window Rialto opened was destroyed, each dialog as soon as it was measured", not left_open,
         "%d were still open when a work area finished, and were destroyed then" % left_open),
        ("every place Rialto.pyw makes a window (%d) is opened here or declared not opened" % makers, not unaccounted,
         plain("; ".join(unaccounted[:8])) + ": add it to DIALOGS, or to DECLARED_NOT_OPENED with the reason"),
        ("this PC's own screen held no window smaller than Rialto asked", not held,
         plain("; ".join(held[:8])) + ": not measured, and not Rialto's failure"),
        ("nothing was added or changed in the worktree, and the temp folder is gone",
         not leftovers and temp_gone, plain("; ".join(leftovers[:8]) or "the temp folder could not be removed")),
    ]
    say("THE HARNESS ITSELF")
    for label, good, why in harness:
        say("  [%s] %s%s" % ("OK  " if good else "FAIL", label, "" if good else " -> " + why))
    say("  Not opened, because nothing of theirs is a window to fit: %s." % NOT_OPENED)
    say("")

    groups = {}
    for name in GROUPS[:3]:
        groups[name] = (not failing[name], failing[name])
    if tall_spec is None:
        groups[GROUPS[3]] = (None, ["not asked for in this run"])
    else:
        groups[GROUPS[3]] = (not tall_why, tall_why)
    say("GROUPS")
    for name in GROUPS:
        passed, why = groups[name]
        say("  [%s] %s%s" % ({True: "OK  ", False: "FAIL", None: "--  "}[passed], name,
                             "   (named as expected red: --expect-red)" if name in options.expect_red else ""))
        for item in why:
            say("           %s" % plain(item))
    if not all(good for _label, good, _why in harness):
        groups["the harness itself"] = (False, [label for label, good, _why in harness if not good])
    print("\n".join(line.rstrip() for line in lines))
    return groups


def print_pins(result):
    """What the tall layout measures now, in the form PINNED holds it: to paste, after reading what changed."""
    windows = result.get("windows", [])
    tall = result.get("tall") or {}
    if not result.get("measured") or not windows:
        print("NOT MEASURED: nothing to pin.")
        return 1
    print('    "window": %s,' % json.dumps(tall.get("window")))
    print('    "page_open": %s,' % json.dumps(tall.get("page_open")))
    print('    "page_folded": %s,' % json.dumps(tall.get("page_folded")))
    print('    "parts": {')
    for attribute in PINNED["parts"]:
        print('        "%s": %s,' % (attribute, json.dumps(tall.get("parts", {}).get(attribute))))
    print("    },")
    print('    "dialogs": {')
    for window in windows[1:]:
        if window["kind"] == "dialog" and window.get("opened") and not window.get("problem"):
            print("        %s: %s," % (json.dumps(window["name"]), json.dumps(window["frame"][2:])))
    print("    },")
    print('    "census": [')
    for row in windows[0].get("census") or []:
        print("        (%s)," % ", ".join(repr(item) for item in row))
    print("    ],")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Rialto fits every screen: the real windows under a pretended work area.")
    parser.add_argument("--report", action="store_true", help="print the table and exit 0 whatever it says")
    parser.add_argument("--expect-red", metavar="GROUP", type=group_named, action="append", default=[],
                        help="a group that is red by design today, by its name or a part of it: the gate exits 0 "
                             "when every other group passes and this one is red, and 1 if this one is not red")
    parser.add_argument("--shots", metavar="DIR", help="also save a picture of each window, alone and on its screen")
    parser.add_argument("--work-area", metavar="WxH", type=size_of, action="append",
                        help="pretend this work area instead of the standard ones (may be given more than once)")
    parser.add_argument("--taskbar-side", choices=("bottom", "top", "left", "right"), default=None,
                        help="the edge of the screen the taskbar is along (default bottom)")
    parser.add_argument("--origin", metavar="X,Y", type=corner_of, default=None,
                        help="the screen's top left corner, as for a monitor left of the main one: "
                             "--origin=-1536,0 (default 0,0)")
    parser.add_argument("--this-pc", action="store_true",
                        help="measure only this PC's own screen, not pretended: Rialto asks Windows itself")
    parser.add_argument("--screen", metavar="WxH", type=size_of, help="a real screen, with --percent")
    parser.add_argument("--percent", type=float, default=100.0, help="Windows' display scaling of --screen (default 100)")
    parser.add_argument("--dpi-aware", action="store_true",
                        help="with --screen: Rialto is handed the real pixels and Tk starts at the real DPI")
    parser.add_argument("--dpi", type=float, default=None, help="the DPI Tk starts at (default 96)")
    parser.add_argument("--taskbar", type=int, default=TASKBAR, help="lines the taskbar takes at 100 percent (default 48)")
    parser.add_argument("--time-limit", type=int, default=90, help="seconds each work area may take (default 90)")
    parser.add_argument("--rialto", default=os.path.join(REPO, "Rialto.pyw"), help="the Rialto.pyw to measure")
    parser.add_argument("--pins", action="store_true",
                        help="print what the tall layout measures now, in the form PINNED holds, and stop")
    parser.add_argument("--child", metavar="SPEC", help=argparse.SUPPRESS)
    options = parser.parse_args()

    if options.child:
        return child_main(options.child)
    if sum(1 for chosen in (options.screen, options.work_area, options.this_pc) if chosen) > 1:
        parser.error("give one of --screen, --work-area and --this-pc")
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass
    if sys.platform != "win32":
        print("Rialto is a Windows program and so is this harness: nothing measured.")
        return 2
    options.rialto = os.path.abspath(options.rialto)
    machines = machines_from(options)
    if options.pins:
        machines = [spec for spec in machines if spec.get("tall")]
        if not machines:
            parser.error("--pins measures the tall layout: give it no work area, DPI, taskbar or corner of your own")
    shots = os.path.abspath(options.shots) if options.shots else None

    before = worktree_listing(shots)
    temp = tempfile.mkdtemp(prefix="rialto_fits_")
    results, started = [], time.time()
    try:
        for number, spec in enumerate(machines):
            spec["rialto"] = options.rialto
            spec["app_root"] = os.path.join(temp, "pc%d" % number)
            os.makedirs(spec["app_root"])
            if shots:
                spec["shots"] = os.path.join(shots, spec["folder"])
                os.makedirs(spec["shots"], exist_ok=True)
            results.append(run_child(spec, options.time_limit))
            if spec.get("real") and results[-1].get("monitor"):
                spec.update(results[-1]["monitor"])
                spec["dpi"] = results[-1].get("tk_dpi", spec["dpi"])
                spec["label"] = ("this PC's own screen, not pretended: Rialto asked Windows and opened on a "
                                 "%d x %d monitor at %d,%d whose work area is %d x %d at %d,%d; Tk at %g DPI" % (
                                     spec["screen"][2], spec["screen"][3], spec["screen"][0], spec["screen"][1],
                                     spec["work_area"][2], spec["work_area"][3], spec["work_area"][0],
                                     spec["work_area"][1], spec["dpi"]))
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    after = worktree_listing(shots)
    leftovers = sorted(path for path in after if after[path] != before.get(path))
    leftovers += sorted("%s (gone)" % path for path in before if path not in after)

    if options.pins:
        return print_pins(results[0])
    groups = report(machines, results, options, leftovers, not os.path.exists(temp), int(time.time() - started))
    failed = [name for name, (passed, _why) in groups.items() if passed is False]
    # A group named as expected red is not counted against the gate while it is red. One that is named and
    # is not red is: it passed, or was not asked for, and the name has to come off.
    expected = [name for name in GROUPS if name in options.expect_red]
    broken = [name for name in failed if name not in expected]
    not_red = [name for name in expected if groups[name][0] is not False]

    if shots:
        pictures = [p for r in results for p in r.get("pictures", [])]
        problems = [p for r in results for p in r.get("picture_problems", [])]
        missing = [s["label"] for s, r in zip(machines, results) if not r.get("measured")]
        missing += ["%s at %s" % (w["name"], s["label"]) for s, r in zip(machines, results)
                    for w in r.get("windows", []) if w.get("problem") or not w.get("opened")]
        print("\nPICTURES: %d saved under %s (each window as drawn, and *.on-screen.png on its screen)." % (
            len(pictures), shots))
        for problem in problems + ["no pictures for %s" % label for label in missing]:
            print("  [FAIL] %s" % plain(problem))
        print("The groups above: %s. This run's exit code says only whether the pictures were saved." % (
            "%d of %d FAILED" % (len(failed), len(groups)) if failed else "all passed"))
        return 1 if (problems or missing or not pictures) else 0
    if expected:
        for name in expected:
            passed = groups[name][0]
            print("\nEXPECTED RED: \"%s\" %s" % (name, {
                False: "is red, as expected. It is not counted against this gate.",
                True: "PASSED. Take --expect-red off it: while it is named, nothing fails when it breaks.",
                None: "was not asked for in this run, so it cannot be told whether it is red."}[passed]))
        if broken or not_red:
            if broken:
                print("\nFAILED: %d of the %d groups that should pass (%s)" % (
                    len(broken), len(groups) - len(expected), "; ".join(broken)))
            if not_red:
                print("\nFAILED: %d group%s named as expected red %s not red (%s)" % (
                    len(not_red), "" if len(not_red) == 1 else "s", "is" if len(not_red) == 1 else "are",
                    "; ".join(not_red)))
            if options.report:
                print("--report: exit code 0 whatever the table says.")
                return 0
            return 1
        passing = sum(1 for passed, _why in groups.values() if passed is True)
        print("\nEvery group that should pass passed (%d of %d); %d %s red as expected%s." % (
            passing, len(groups), len(expected), "is" if len(expected) == 1 else "are",
            "" if passing + len(expected) == len(groups) else "; a group marked -- was not asked for in this run"))
        return 0
    if failed:
        print("\nFAILED: %d of %d groups (%s)" % (len(failed), len(groups), "; ".join(failed)))
        if options.report:
            print("--report: exit code 0 whatever the table says.")
            return 0
        return 1
    print("\nAll fits-every-screen groups passed." if all(p for p, _w in groups.values())
          else "\nNo group failed; a group marked -- was not asked for in this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
