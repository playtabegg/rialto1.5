# Rialto 1.5 - game disc builder by We The Indies (MIT License)
# Single-file app: the UI, the build pipeline and the disc menu source
# Includes: UI, Automation, Validation, ISO, Bonus Gallery, Batch, Live Preview

import os
import sys
import json
import hashlib
import shutil
import subprocess
import traceback
import glob
import re
import zipfile

# Status messages use emoji; older Windows consoles crash printing them.
# Harmless under pythonw (no console), essential for debug runs and logs.
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
# First-run friendliness: if dependencies are missing, offer to install them
# automatically instead of crashing silently (Rialto.pyw runs windowless).
#
# "Are the dependencies installed?" used to mean "does Pillow import?". That
# answers the first-run question but not the upgrade one: add a package to
# requirements.txt and every existing copy of Rialto keeps starting happily
# without it, until whatever needs it fails in the middle of a build. So the
# marker keys on a hash of requirements.txt instead - change the file, and the
# next start reinstalls.
#
# A frozen build skips all of this. Its dependencies are inside the bundle, and
# sys.executable there is Rialto.exe, not a python that could run pip.
_FROZEN = getattr(sys, "frozen", False)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_requirements = os.path.join(_APP_DIR, "requirements.txt")
# Hidden, and named for what it is: a record of which requirements.txt was
# last installed, not a lockfile anyone should edit.
_DEPS_MARKER = os.path.join(_APP_DIR, ".deps_installed")


def _requirements_fingerprint():
    """Hash of requirements.txt, or None if there isn't one to read."""
    try:
        with open(_requirements, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _deps_already_attempted(fingerprint):
    """True if this exact requirements.txt has already been installed from.

    Or has already failed to install once, which counts the same on purpose.
    Retrying on every launch would hang startup for minutes for anyone offline,
    and reaching this check at all means Rialto can already run - what is missing
    is whatever the new requirement was for, and the feature that needs it says
    so when it is used.
    """
    if not fingerprint:
        return True  # nothing to compare against; never block startup over it
    try:
        with open(_DEPS_MARKER, encoding="utf-8") as f:
            marker = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(marker, dict) \
        and marker.get("requirements_sha256") == fingerprint


def _write_deps_marker(fingerprint, installed):
    if not fingerprint:
        return
    try:
        with open(_DEPS_MARKER, "w", encoding="utf-8") as f:
            json.dump({"requirements_sha256": fingerprint,
                       "installed": bool(installed)}, f, indent=2)
    except OSError:
        pass  # a read-only folder just means the check runs again next time


def _install_requirements():
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", _requirements],
        capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


if _FROZEN:
    from PIL import Image, ImageTk
else:
    _fingerprint = _requirements_fingerprint()
    try:
        from PIL import Image, ImageTk
        _core_present = True
    except ImportError:
        _core_present = False

    if _core_present and not _deps_already_attempted(_fingerprint):
        # Rialto can start, but requirements.txt is not the one these packages
        # came from. That is an upgrade, not a first run, so sync quietly rather
        # than interrupting with a dialog nobody asked for. Either way the
        # attempt is recorded, so this costs one pip run per change to
        # requirements.txt and never more.
        #
        # And it cannot be allowed to stop the launch. Reaching here means
        # Rialto already has everything it needs to run; if pip cannot even be
        # started - an antivirus policy refusing to let Python spawn children
        # is the everyday version - the exception would escape module import,
        # and Rialto.pyw is windowless: double-clicking it would do nothing at
        # all, with no error anywhere. Record the attempt and start.
        try:
            _synced = _install_requirements().returncode == 0
        except Exception:
            _synced = False
        _write_deps_marker(_fingerprint, _synced)

    if not _core_present:
        _root = tk.Tk()
        _root.withdraw()
        if messagebox.askyesno(
            "Rialto - First Run Setup",
            "Rialto needs a few Python packages that aren't installed yet.\n\n"
            "Install them now automatically?\n(This runs: pip install -r requirements.txt)"
        ):
            _result = _install_requirements()
            if _result.returncode == 0:
                _write_deps_marker(_fingerprint, True)
                messagebox.showinfo("Rialto", "All set! Rialto will now start.")
                _root.destroy()
                os.execv(sys.executable, [sys.executable] + sys.argv)
            else:
                messagebox.showerror(
                    "Rialto",
                    "Automatic install failed. Please run this in a terminal:\n\n"
                    f"pip install -r \"{_requirements}\"\n\n"
                    f"Details: {(_result.stderr or '').strip()[-500:]}"
                )
                raise SystemExit(1)
        else:
            messagebox.showinfo("Rialto", "Setup cancelled. Run 'pip install -r requirements.txt' manually, then start Rialto again.")
            raise SystemExit(1)
import atexit
import threading
import winsound  # For WAV playback on Windows
import tempfile
import time
import datetime
import platform
import urllib.request





# The disc menu lives in MENU_TEMPLATE_SOURCE, further down this file. It is
# built once into a generic menu.exe (menu.spec) and staged per title by
# stage_menu_executable() alongside the menu_config.json that drives it.




APP_NAME = "Rialto"
#: The one place the version lives. rialto.spec and menu.spec read it from
#: this line (tools-dev/test_version_agreement.py pins that), the release
#: feed compares against it, and the About/Help text shows it.
__version__ = "1.5.0"

# GOG import unpacks Inno Setup installers with innoextract, downloaded on
# first use. Version and checksum are pinned together: bump both, never one.
INNOEXTRACT_URL = "https://constexpr.org/innoextract/files/innoextract-1.9-windows.zip"
INNOEXTRACT_SHA256 = "6989342c9b026a00a72a38f23b62a8e6a22cc5de69805cf47d68ac2fec993065"


def link_or_copy_tree(source, dest):
    """Make `dest` show what `source` holds, without duplicating it.

    Used to stage bonus/ and mods/ into the disc menu preview. A bonus folder is
    routinely gigabytes of video and artwork, the preview only ever reads it, and
    the whole staging folder is thrown away afterwards - so copying it is pure
    waiting. A directory junction is instant, costs no disk, needs no elevation
    (unlike a symlink), and deleting it never touches the original.

    Junctions are an NTFS feature, so the copy stays as the fallback for a temp
    folder that landed on a FAT32 or exFAT drive, or for anything else that
    refuses. Returns "junction", "copy", or None if neither worked.

    Made directly, not through `cmd /c mklink`. `source` is the author's game
    or bonus folder - third-party input, which is the whole point of this tool
    - and cmd re-parses its command line after Python has quoted it. Python
    only quotes an argument that contains whitespace, so a folder named
    `Game&calc` arrived at cmd unquoted, and cmd read the `&` as "now run
    calc". A folder called `My Game&calc` was safe purely because the space
    forced the quotes. CreateJunction takes the path as a path.
    """
    try:
        import _winapi
        # CreateJunction makes the destination folder itself, and fails if one
        # is already there. It does not clean up after a partial failure, so
        # the empty folder is removed here - copytree below refuses to run
        # into an existing destination.
        _winapi.CreateJunction(os.path.abspath(source), os.path.abspath(dest))
        return "junction"
    except (ImportError, AttributeError, OSError, ValueError):
        try:
            os.rmdir(dest)
        except OSError:
            pass
    try:
        shutil.copytree(source, dest)
        return "copy"
    except OSError:
        return None


# Preview Disc Menu stages into a temp folder named with this prefix. The
# creating and the sweeping both read it from here, so they cannot drift.
PREVIEW_PREFIX = "rialto_preview_"

# Anything older than the moment this Rialto started belongs to a run that has
# ended. A preview another Rialto is still showing is newer than that and is
# left alone.
_STARTED_AT = time.time()


def remove_preview_dir(path):
    """Delete one preview staging folder. Never reaches through a junction.

    shutil.rmtree unlinks a junction and stops there rather than descending into
    what it points at - proven against a real junction and a real file on the
    other side of it in tools-dev/test_bonus_staging.py. That is the whole
    reason this is safe to do at all: a preview folder holds junctions straight
    into the author's bonus/ and mods/.

    ignore_errors, because the usual reason a preview will not delete is that
    its menu.exe is still open. Stripping everything that will go still clears
    the junctions, and the next sweep finishes the job.
    """
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.exists(path)


def sweep_stale_previews(root=None, older_than=None):
    """Remove preview folders left behind by earlier runs. Returns how many.

    Preview stages into a temp folder and leaves it: the menu it just launched
    is still reading from it, and Rialto never learns when the author closes it.
    One folder per click, each holding live junctions into that author's game
    folder, kept until Windows feels like clearing %TEMP%.

    Quiet by design - a folder that will not delete is one to try again later,
    not something to interrupt an author over.
    """
    root = root or tempfile.gettempdir()
    cutoff = _STARTED_AT if older_than is None else older_than
    removed = 0
    try:
        names = os.listdir(root)
    except OSError:
        return 0
    for name in names:
        if not name.startswith(PREVIEW_PREFIX):
            continue
        stale = os.path.join(root, name)
        try:
            if not os.path.isdir(stale) or os.path.getmtime(stale) >= cutoff:
                continue
        except OSError:
            continue
        if remove_preview_dir(stale):
            removed += 1
    return removed


def app_root():
    """The folder Rialto keeps its own working files in.

    Frozen: next to Rialto.exe. Never sys._MEIPASS, which is a temp folder the
    bootloader deletes on exit - config.json and the input/output folders have
    to outlive the process.

    Source: the folder holding this script, not the current directory, so a
    shortcut with a different "Start in" can't scatter input/, output/ and
    config.json somewhere the user never looks. Identical to the old behaviour
    for anyone launching Rialto from the folder it lives in.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_ROOT = app_root()
CONFIG_FILE = os.path.join(APP_ROOT, "config.json")
INPUT_DIR = os.path.join(APP_ROOT, "input")
OUTPUT_DIR = os.path.join(APP_ROOT, "output")
TEMPLATES_DIR = os.path.join(APP_ROOT, "templates")
REQUIRED_TOOLS = ["AutoIt3.exe", "ISCC.exe"]
ISO_TOOLS = ["mkisofs.exe", "oscdimg.exe"]
LAST_PROFILE_FILE = os.path.join(APP_ROOT, "last_profile.json")
LAST_SESSION_FILE = os.path.join(APP_ROOT, "last_session.json")

INNO_SETUP_DOWNLOAD = "https://jrsoftware.org/isdl.php"


def _registry_string(root, subkey, value):
    """One string value from the registry, or "" when it is not there."""
    try:
        import winreg
        with winreg.OpenKey(getattr(winreg, root), subkey) as key:
            found, _kind = winreg.QueryValueEx(key, value)
        return found if isinstance(found, str) else ""
    except (ImportError, OSError, AttributeError):
        return ""


def _inno_setup_folders(major):
    """Every folder an Inno Setup installer of this major version may be in.

    The installer records its folder under the uninstall key named after its
    AppId ("Inno Setup 6_is1"): in the machine hive for Install for all users,
    in the user hive for Install for me only. The default folders for both
    modes are checked too, in case the uninstall entry is gone.
    """
    name = "Inno Setup %d" % major
    uninstall = "Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s_is1" % name
    folders = [
        _registry_string("HKEY_LOCAL_MACHINE", "SOFTWARE\\WOW6432Node\\" + uninstall, "InstallLocation"),
        _registry_string("HKEY_LOCAL_MACHINE", "SOFTWARE\\" + uninstall, "InstallLocation"),
        _registry_string("HKEY_CURRENT_USER", "Software\\" + uninstall, "InstallLocation"),
    ]
    for variable, parts in (("ProgramFiles(x86)", (name,)), ("ProgramFiles", (name,)),
                            ("LOCALAPPDATA", ("Programs", name))):
        base = os.environ.get(variable)
        if base:
            folders.append(os.path.join(base, *parts))
    return [folder for folder in folders if folder]


def _inno_setup_major(iscc_path):
    """6 for ...\\Inno Setup 6\\ISCC.exe, 7 for Inno Setup 7, None when the folder does not say."""
    folder = os.path.basename(os.path.dirname(iscc_path)).strip().lower()
    prefix = "inno setup "
    if folder.startswith(prefix) and folder[len(prefix):].isdigit():
        return int(folder[len(prefix):])
    return None


def find_inno_compiler():
    """ISCC.exe from Inno Setup 6, or None.

    PATH first, as before, unless that ISCC.exe sits in the folder of another
    Inno Setup version; then wherever the Inno Setup 6 installer put itself,
    in either install mode.
    """
    found = shutil.which("ISCC.exe")
    if found and _inno_setup_major(found) in (None, 6):
        return found
    for folder in _inno_setup_folders(6):
        candidate = os.path.join(folder, "ISCC.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def inno_setup_7_only():
    """True when Inno Setup 7 is installed and Inno Setup 6 is not.

    Rialto 1.5 builds its installers with Inno Setup 6 and has not been tested
    with 7, so the build names the problem instead of saying nothing was found.
    """
    if find_inno_compiler():
        return False
    on_path = shutil.which("ISCC.exe")
    if on_path and _inno_setup_major(on_path) == 7:
        return True
    return any(os.path.isfile(os.path.join(folder, "ISCC.exe")) for folder in _inno_setup_folders(7))


def find_iso_tools():
    """(mkisofs, oscdimg): each a path, or None.

    Both are looked up on PATH, as before. The Windows ADK does not add oscdimg
    to PATH, so it is also found where the ADK installs it: under the Kits root
    the ADK records in the registry (or the default Windows Kits folder), in
    Assessment and Deployment Kit\\Deployment Tools\\<architecture>\\Oscdimg.
    """
    mkisofs = shutil.which("mkisofs")
    oscdimg = shutil.which("oscdimg")
    if oscdimg:
        return mkisofs, oscdimg
    installed_roots = "Microsoft\\Windows Kits\\Installed Roots"
    roots = [
        _registry_string("HKEY_LOCAL_MACHINE", "SOFTWARE\\WOW6432Node\\" + installed_roots, "KitsRoot10"),
        _registry_string("HKEY_LOCAL_MACHINE", "SOFTWARE\\" + installed_roots, "KitsRoot10"),
    ]
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(variable)
        if base:
            roots.append(os.path.join(base, "Windows Kits", "10"))
    machine = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or "").upper()
    architectures = {"ARM64": ["arm64", "amd64"], "X86": ["x86"]}.get(machine, ["amd64", "x86"])
    for root in roots:
        if not root:
            continue
        for architecture in architectures:
            candidate = os.path.join(root, "Assessment and Deployment Kit", "Deployment Tools",
                                     architecture, "Oscdimg", "oscdimg.exe")
            if os.path.isfile(candidate):
                return mkisofs, candidate
    return mkisofs, None


# Helper: Safe path for Windows
safe = lambda p: os.path.normpath(os.path.abspath(p))

def asset_path(filename):
    """Resolve path to a bundled asset file."""
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, 'assets', filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', filename)

# Ensure folders exist
def ensure_structure():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)


class ToolTip:
    def __init__(self, widget, text, bg=None, fg=None):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        if event:
            x = event.x_root + 15
            y = event.y_root + 10
        else:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tip_bg = self.bg or "#2d2d2d"
        tip_fg = self.fg or "#e0e0e0"
        label = tk.Label(tw, text=self.text, justify='left',
                         background=tip_bg, foreground=tip_fg,
                         relief='solid', borderwidth=1,
                         font=("Segoe UI", 10),
                         wraplength=320)
        label.pack(ipadx=4, ipady=2)

    def hide(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()


# === Button and checkbox icons ===
#
# Emoji in a Tk button label are drawn by whichever font Windows falls back to,
# and that font's baseline does not match Segoe UI's - which is why every icon
# in the tool boxes sat a few pixels low. These are drawn instead: real images,
# vertically centred by the widget, at whatever colour the theme is using.
#
# Everything is painted at 4x and resized down, which is the cheap way to get
# antialiased diagonals out of ImageDraw.
_ICON_CACHE = {}
_ICON_SUPERSAMPLE = 4


def ui_icon(name, color="#ffffff", size=16):
    """A themed glyph as a PhotoImage, cached per (name, colour, size).

    Drawn as solid masses with transparent bites taken out of them, not as thin
    outlines. The first pass used outlines and they collapsed at 15px: the
    folder read as a box with a stray line over it, the puzzle piece and the
    open book turned to mush, and three of the six buttons in the quick row
    came out unrecognisable. A filled shape with a hole in it survives being
    shrunk; a 1px stroke does not.
    """
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    from PIL import ImageDraw

    s = size * _ICON_SUPERSAMPLE
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stroke = max(3, int(s * 0.11))
    CLEAR = (0, 0, 0, 0)

    def box(x0, y0, x1, y1, fill=color, radius=0):
        # ImageDraw writes pixels straight through, so filling with a fully
        # transparent colour punches a hole rather than compositing onto one.
        coords = [x0 * s, y0 * s, x1 * s, y1 * s]
        if radius:
            draw.rounded_rectangle(coords, radius=radius * s, fill=fill)
        else:
            draw.rectangle(coords, fill=fill)

    def circle(cx, cy, r, fill=color):
        draw.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=fill)

    def ring(cx, cy, outer, inner):
        circle(cx, cy, outer)
        circle(cx, cy, inner, CLEAR)

    def poly(points, fill=color):
        draw.polygon([(x * s, y * s) for x, y in points], fill=fill)

    def line(points, width=None, fill=color):
        draw.line([(x * s, y * s) for x, y in points], fill=fill,
                  width=width or stroke, joint="curve")

    def folder_body(top=0.30, bottom=0.84):
        poly([(0.08, top), (0.40, top), (0.47, top + 0.10), (0.92, top + 0.10),
              (0.92, bottom), (0.08, bottom)])

    if name == "folder":
        folder_body()
    elif name == "load":
        # A folder with something coming down into it
        folder_body(top=0.46, bottom=0.90)
        box(0.44, 0.06, 0.56, 0.30)
        poly([(0.32, 0.26), (0.68, 0.26), (0.50, 0.46)])
    elif name == "save":
        # Floppy disk: solid body, shutter and label bitten out
        box(0.10, 0.12, 0.90, 0.88, radius=0.06)
        box(0.32, 0.12, 0.68, 0.40, CLEAR)
        box(0.44, 0.16, 0.60, 0.36)
        box(0.26, 0.56, 0.74, 0.88, CLEAR)
        box(0.32, 0.62, 0.68, 0.82)
        box(0.40, 0.68, 0.60, 0.76, CLEAR)
    elif name == "monitor":
        box(0.06, 0.16, 0.94, 0.68, radius=0.05)
        box(0.16, 0.26, 0.84, 0.58, CLEAR)
        box(0.42, 0.68, 0.58, 0.82)
        box(0.28, 0.82, 0.72, 0.90, radius=0.03)
    elif name == "theme":
        # Half light, half dark: the toggle between the two
        circle(0.50, 0.50, 0.42)
        draw.pieslice([0.08 * s, 0.08 * s, 0.92 * s, 0.92 * s], -90, 90, fill=CLEAR)
        draw.arc([0.08 * s, 0.08 * s, 0.92 * s, 0.92 * s], -90, 90,
                 fill=color, width=stroke)
    elif name == "book":
        # A page with lines on it. An open book needed a spine and two covers
        # and none of it survived being 15 pixels wide.
        poly([(0.18, 0.08), (0.64, 0.08), (0.84, 0.28), (0.84, 0.92), (0.18, 0.92)])
        poly([(0.64, 0.08), (0.84, 0.28), (0.64, 0.28)], CLEAR)
        for y in (0.42, 0.56, 0.70):
            box(0.30, y, 0.72, y + 0.075, CLEAR)
    elif name == "gear":
        import math
        cx = cy = 0.50
        teeth = []
        for step in range(16):
            angle = math.radians(step * 22.5)
            radius = 0.47 if (step // 2) % 2 == 0 else 0.33
            teeth.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        poly(teeth)
        circle(cx, cy, 0.14, CLEAR)
    elif name == "disc":
        ring(0.50, 0.50, 0.46, 0.13)
        circle(0.50, 0.50, 0.05)
    elif name == "package":
        # A box seen from the corner. Punching a strap and a band through a
        # flat rectangle just produced four squares in a grid.
        poly([(0.50, 0.06), (0.95, 0.30), (0.50, 0.54), (0.05, 0.30)])
        poly([(0.05, 0.30), (0.50, 0.54), (0.50, 0.96), (0.05, 0.72)])
        poly([(0.95, 0.30), (0.50, 0.54), (0.50, 0.96), (0.95, 0.72)])
        line([(0.05, 0.30), (0.50, 0.54), (0.95, 0.30)], width=max(2, int(s * 0.05)), fill=CLEAR)
        line([(0.50, 0.54), (0.50, 0.96)], width=max(2, int(s * 0.05)), fill=CLEAR)
    elif name == "download":
        box(0.42, 0.08, 0.58, 0.50)
        poly([(0.26, 0.44), (0.74, 0.44), (0.50, 0.72)])
        box(0.14, 0.84, 0.86, 0.94, radius=0.03)
    elif name == "gift":
        # Ribbon punched through the body only. Cutting it through the lid as
        # well split the whole thing into two disconnected blocks.
        box(0.12, 0.44, 0.88, 0.92, radius=0.03)
        box(0.04, 0.26, 0.96, 0.46, radius=0.03)
        box(0.45, 0.46, 0.55, 0.92, CLEAR)
        circle(0.36, 0.18, 0.13)
        circle(0.36, 0.18, 0.05, CLEAR)
        circle(0.64, 0.18, 0.13)
        circle(0.64, 0.18, 0.05, CLEAR)
    elif name == "mods":
        # A wrench. The puzzle piece it replaced was unreadable at this size.
        line([(0.22, 0.84), (0.66, 0.38)], width=int(s * 0.17))
        circle(0.71, 0.30, 0.22)
        circle(0.79, 0.20, 0.13, CLEAR)
    elif name == "steam":
        ring(0.50, 0.50, 0.46, 0.34)
        circle(0.64, 0.36, 0.17)
        circle(0.64, 0.36, 0.07, CLEAR)
        circle(0.30, 0.68, 0.11)
    elif name == "image":
        # A picture: frame, a sun and a hill inside it
        box(0.06, 0.16, 0.94, 0.84, radius=0.05)
        box(0.15, 0.25, 0.85, 0.75, CLEAR)
        circle(0.32, 0.38, 0.08)
        poly([(0.17, 0.74), (0.42, 0.44), (0.60, 0.66), (0.70, 0.56), (0.84, 0.74)])
    elif name == "tile":
        # An app icon: rounded tile with a shape sitting in it
        box(0.10, 0.10, 0.90, 0.90, radius=0.20)
        box(0.22, 0.22, 0.78, 0.78, CLEAR)
        circle(0.50, 0.50, 0.17)
    elif name == "reset":
        # Circular arrow: back to how it started
        import math
        ring(0.50, 0.52, 0.40, 0.24)
        draw.pieslice([0.10 * s, 0.12 * s, 0.90 * s, 0.92 * s], -80, 10, fill=CLEAR)
        poly([(0.52, 0.02), (0.52, 0.34), (0.86, 0.18)])
    elif name == "play":
        poly([(0.26, 0.10), (0.86, 0.50), (0.26, 0.90)])
    elif name == "eye":
        poly([(0.04, 0.50), (0.32, 0.20), (0.68, 0.20), (0.96, 0.50),
              (0.68, 0.80), (0.32, 0.80)])
        circle(0.50, 0.50, 0.19, CLEAR)
        circle(0.50, 0.50, 0.10)
    elif name == "exit":
        box(0.08, 0.10, 0.52, 0.90, radius=0.04)
        box(0.18, 0.20, 0.52, 0.80, CLEAR)
        box(0.46, 0.44, 0.80, 0.56)
        poly([(0.72, 0.30), (0.72, 0.70), (0.98, 0.50)])
    elif name == "check":
        line([(0.16, 0.52), (0.42, 0.78), (0.86, 0.20)], width=int(s * 0.16))
    else:
        ring(0.50, 0.50, 0.40, 0.24)

    icon = ImageTk.PhotoImage(image.resize((size, size), Image.LANCZOS))
    _ICON_CACHE[key] = icon
    return icon


# Checkbutton indicators. ttk's 'default' theme draws a plain filled square when
# a box is ticked - no tick in it, which reads as "shaded" rather than "on".
# These replace the indicator element outright with drawn images, so a ticked
# box shows an actual checkmark in both themes.
_CHECK_ELEMENTS = {}


def _check_indicator_images(theme_name, colors):
    from PIL import ImageDraw

    size, scale = 15, 4
    s = size * scale
    images = {}
    for state in ("off", "on"):
        image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        border = colors["fg"] if state == "on" else colors["disabled_fg"]
        fill = colors["accent"] if state == "on" else colors["entry_bg"]
        draw.rounded_rectangle([scale, scale, s - scale, s - scale],
                               radius=scale * 2, fill=fill, outline=border,
                               width=max(2, scale))
        if state == "on":
            draw.line([(0.26 * s, 0.52 * s), (0.44 * s, 0.72 * s),
                       (0.76 * s, 0.30 * s)],
                      fill=colors["check_fg"], width=int(scale * 1.9), joint="curve")
        images[state] = ImageTk.PhotoImage(image.resize((size, size), Image.LANCZOS))
    return images


def install_check_style(style, theme_name, colors):
    """Register (once) two Checkbutton styles whose tick is a drawn image.

    `Dark.TCheckbutton` sits on the page background; `DarkHeader.TCheckbutton`
    sits on the export bar. Elements cannot be created twice under one name, so
    each theme registers on first use and the app switches style names when the
    theme flips.
    """
    prefix = theme_name.capitalize()
    page_style = f"{prefix}.TCheckbutton"
    header_style = f"{prefix}Header.TCheckbutton"

    if theme_name not in _CHECK_ELEMENTS:
        images = _check_indicator_images(theme_name, colors)
        _CHECK_ELEMENTS[theme_name] = images  # keeps the PhotoImages alive
        element = f"rialto{theme_name}.indicator"
        try:
            style.element_create(element, "image", images["off"],
                                 ("selected", images["on"]),
                                 ("alternate", images["on"]),
                                 border=0, sticky="")
            layout = [
                ("Checkbutton.padding", {"sticky": "nswe", "children": [
                    (element, {"side": "left", "sticky": ""}),
                    ("Checkbutton.focus", {"side": "left", "sticky": "w",
                                           "children": [
                                               ("Checkbutton.label", {"sticky": "nswe"})]}),
                ]}),
            ]
            style.layout(page_style, layout)
            style.layout(header_style, layout)
        except tk.TclError:
            # Already registered, or this Tk build will not take an image
            # element. The stock indicator still works, it is only less legible.
            pass

    for name, background in ((page_style, colors["bg"]), (header_style, colors["header_bg"])):
        style.configure(name, background=background, foreground=colors["fg"],
                        padding=(0, 2, 8, 2))
        style.map(name,
                  background=[("active", background)],
                  foreground=[("disabled", colors["disabled_fg"]), ("active", colors["fg"])])
    return page_style


def strip_wti_mentions(text):
    """Take every mention of We the Indies out of a line of copy.

    White label has to mean white label. The bird and the wordmark were already
    removed, but an author who had typed "Distributed by We the Indies." into
    the copyright box - or loaded a profile that carried it - still had it
    printed across the bottom of a disc that was supposed to carry only their
    own branding.

    Sentence-granular, so "Published by X. Distributed by We the Indies." keeps
    the first half and drops the second.
    """
    if not text:
        return ""
    needles = ("we the indies", "wetheindies", "we-the-indies")
    kept = []
    for chunk in re.split(r"(?<=[.!?])\s+|\n+", text):
        if not chunk.strip():
            continue
        if any(needle in chunk.lower() for needle in needles):
            continue
        kept.append(chunk.strip())
    return " ".join(kept)


# Characters that mean something to Inno Setup rather than reading as text.
#   \r \n  - end the directive, so the rest of the value becomes a new one
#   "      - close the quoted Name:/ValueData: fields in [Icons] and [Registry]
#   ;      - separate parameters on those same lines, and start a comment
#   { }    - delimit Inno's constants ({app}, {group}, {cm:...})
_ISS_META = re.compile(r'[\x00-\x1f\x7f"{};]')
# Also stripped when the value becomes part of a path: DefaultDirName is built
# as C:\Games\<title>, and a title carrying ..\ would move the install folder.
_ISS_PATH_META = re.compile(r'[\x00-\x1f\x7f"{};\\/:*?<>|]')
# Device names, which Windows resolves at any depth: C:\Games\NUL is the null
# device, not a folder. Reserved with or without an extension.
_WINDOWS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM%d" % n for n in range(1, 10)]
    + ["LPT%d" % n for n in range(1, 10)])


def iss_value(value, fallback="Game", for_path=False):
    """Make a metadata value safe to write into installer.iss.

    The .iss is assembled by string concatenation and handed to ISCC, which
    compiles whatever it finds into setup.exe - and Rialto then signs that
    setup.exe with the developer's real certificate and ships it to every
    buyer. So a title is not decoration here; it is input to a compiler.

    Titles reach this from templates/*.json, which are shared between authors
    and auto-loaded at startup from last_profile.json without anybody clicking
    anything. .strip() only removes whitespace at the ends, so a title of

        Game\\n[Run]\\nFilename: "cmd.exe"; Parameters: "/c ..."

    survived intact and added a [Run] section to the compiled installer. That
    is arbitrary code on the player's machine, carried by a trusted signature.

    Stripping rather than escaping: Inno's escaping rules differ per section
    and per field, one universal escape does not exist, and no real game title
    needs any of these characters. The cap is for ISCC's line limits.

    for_path also has to deal with names that are paths in disguise. Taking the
    separators out is not enough, because a component made only of dots is
    still navigation: a title of ".." put DefaultDirName at C:\\, and a title of
    "." put it at C:\\Games itself - so the installer wrote its files loose into
    the player's whole Games folder, and its uninstaller then went looking for
    them there. ([UninstallDelete] used to make that far worse by removing the
    directory outright; that section is gone now, but a DefaultDirName pointing
    somewhere it should not is still the bug this prevents.) Windows drops
    trailing dots and spaces from a name too, and resolves CON, NUL, COM1 and
    the rest as devices at any depth.
    """
    pattern = _ISS_PATH_META if for_path else _ISS_META
    cleaned = pattern.sub("", str(value or "")).strip()
    if for_path:
        cleaned = cleaned.strip(". ")
    cleaned = cleaned[:120]
    if for_path:
        # Again after the cap, which can uncover a new trailing dot.
        cleaned = cleaned.strip(". ")
        if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
            cleaned = ""
    return cleaned or fallback


# C0 (0x00-0x1F), DEL (0x7F), and C1 (0x80-0x9F). A newline in a Title becomes
# a new batch line; a CR in autorun.inf's Label= becomes a new INF key. No
# real game title needs any of these, so they are stripped rather than escaped.
_CONTROL_CHARS = dict.fromkeys(list(range(0x20)) + [0x7F] + list(range(0x80, 0xA0)))


def sanitize_text(value):
    """Strip every C0/C1 control character (including CR/LF/TAB/DEL) from text.

    Profile JSON is shared between authors and auto-loaded at startup. Values
    from it are copied into batch files, autorun.inf, README.txt and ISO
    volume labels. .strip() only trims the ends, so a newline in the middle
    of a Title was a new command. Called at load AND at each generator.
    """
    return str(value or "").translate(_CONTROL_CHARS)


def split_launch_args(value, max_args=16, max_len=256):
    """Split an author's launch-argument line into a list for the disc menu.

    Whitespace separates arguments; double quotes hold one together. Written
    by hand rather than with shlex because shlex's POSIX mode eats the
    backslashes in a Windows path and its non-POSIX mode keeps the quote
    characters in the token - both wrong for a list handed to Popen.

    Control characters are stripped first (the same trust boundary as every
    other profile value), and the result is capped, because this ends up in
    menu_config.json where the disc menu checks it again before use.
    """
    text = sanitize_text(value)
    args, current, quoted, opened = [], [], False, False
    for ch in text:
        if ch == '"':
            quoted = not quoted
            opened = True
        elif ch.isspace() and not quoted:
            if current or opened:
                args.append(''.join(current))
                current, opened = [], False
        else:
            current.append(ch)
    if current or opened:
        args.append(''.join(current))
    return [a[:max_len] for a in args if a][:max_args]


def sanitize_profile_data(data):
    """Walk a loaded profile JSON and sanitize every string value."""
    if isinstance(data, str):
        return sanitize_text(data)
    if isinstance(data, list):
        return [sanitize_profile_data(v) for v in data]
    if isinstance(data, dict):
        return {k: sanitize_profile_data(v) for k, v in data.items()}
    return data


def escape_batch(value):
    """Make a metadata string safe to splice into a generated .bat file.

    Control characters are stripped first. % is doubled so %USERNAME% cannot
    expand, ! is removed so delayed expansion cannot substitute, then the
    cmd metacharacters & | > < ^ ( ) are caret-escaped. ^ is escaped first
    so the carets added for the others are not themselves doubled.
    """
    text = sanitize_text(value)
    text = text.replace("%", "%%")
    text = text.replace("!", "")
    for ch in ("^", "&", "|", ">", "<", "(", ")"):
        text = text.replace(ch, "^" + ch)
    return text


def oversized_disc_warnings(disc_sizes, budget, media_label):
    """Status lines for every disc of a spanned set that overflows the media.

    Disc 1 always carries the base fileset - menu, setup stub, bonus/ and
    mods/ - however big that is, so a fat bonus folder can push it past the
    chosen Target Media. Rialto warns and keeps building: the author decides
    whether to move to bigger media or trim the extras.

    Pure on purpose (byte totals in, status lines out) so it can be checked
    without a disc, a build or a GUI. Sizes and budget are in bytes.
    """
    lines = []
    for number, size in enumerate(disc_sizes, start=1):
        if size <= budget:
            continue
        lines.append(
            f"⚠️ Disc {number} is {size / 1e9:.2f} GB - larger than the "
            f"{budget / 1e9:.2f} GB usable on the {media_label} target media."
        )
        lines.append(
            "   The build will continue, but this disc will not fit. "
            "Consider a larger Target Media or trimming the bonus folder."
        )
    return lines


# GUI class begins
class RialtoApp:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.root.title(f"{APP_NAME} 1.5 - Disc Builder")
        
        # Set favicon for main window
        try:
            icon_path = asset_path("bird_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass
        



        self.root.overrideredirect(True)  # Hide native title bar

        # Fit the window to the screen: tall screens get the full layout,
        # 1080p screens get a slightly compressed one instead of clipping
        screen_height = self.root.winfo_screenheight()
        window_height = min(1200, max(900, screen_height - 80))
        self.root.geometry(f"700x{window_height}")
        self.current_game_path = None

        default_font = ("Segoe UI", 10)
        self.root.option_add("*Font", default_font)

        self.dark_theme = {
            "bg": "#222222",
            "fg": "#ffffff",
            "entry_bg": "#333333",
            "button_bg": "#444444",
            "button_fg": "#ffffff",
            "button_active": "#555555",
            "disabled_fg": "#888888",
            # Header strip behind the bird on dialogs, and the ticked checkbox
            "header_bg": "#1a1a1a",
            "accent": "#4a9eff",
            "check_fg": "#0b1b2b",
            "icon": "#e8e8e8",
            "meter_track": "#1a1a1a",
            "meter_fill": "#4a9eff",
            "meter_warn": "#e8a33d",
            "meter_over": "#e05252",
        }
        self.light_theme = {
            "bg": "#f0f0f0",
            "fg": "#000000",
            "entry_bg": "#ffffff",
            "button_bg": "#e0e0e0",
            "button_fg": "#000000",
            "button_active": "#d0d0d0",
            "disabled_fg": "#a0a0a0",
            "header_bg": "#e2e6ea",
            "accent": "#1668c4",
            "check_fg": "#ffffff",
            "icon": "#333333",
            "meter_track": "#dcdcdc",
            "meter_fill": "#1668c4",
            "meter_warn": "#b8721a",
            "meter_over": "#c0392b",
        }

        # UI Elements
        self.theme_mode = tk.StringVar(value="dark")  # Default is dark mode
        
        # Code Signing settings
        self.sign_final_build = tk.BooleanVar(value=False)
        self.remove_wti_branding = tk.BooleanVar(value=False)

        # Multi-game disc support: list of {"name": display name, "exe": path
        # relative to the game folder}. Empty list = classic auto-detect.
        self.game_executables = []

        # Disc target and extras (Rialto 1.5)
        self.target_media_var = tk.StringVar(value="Auto (single disc)")
        self.usb_export_var = tk.BooleanVar(value=False)
        self.steam_button_var = tk.BooleanVar(value=True)
        self.mod_launcher_var = tk.BooleanVar(value=False)
        # The folder holding the mod tool. Empty means "use <game>/mods if
        # it is there", which is how every disc built before the picker
        # existed still builds.
        self.mod_folder_var = tk.StringVar(value="")
        # A second PLAY button that starts the game with the author's own
        # launch argument - the OpenGL fallback a Vulkan game ships for older
        # hardware, most often. Off unless the author says otherwise, because
        # only they know whether their game has such a mode.
        self.compat_mode_var = tk.BooleanVar(value=False)
        self.compat_args_var = tk.StringVar(value="")
        # The player-facing sentence explaining what the mode changes. Only
        # the author knows that; the generic wording can only guess the
        # common case.
        self.compat_hint_var = tk.StringVar(value="")
        self.mac_build_var = tk.StringVar(value="")
        self.linux_build_var = tk.StringVar(value="")
        # A bonus folder picked from Disc Extras. Empty means "use
        # input\<Game>\bonus if it happens to be there", which is the old
        # behaviour and still works.
        self.bonus_folder_var = tk.StringVar(value="")
        # Live disc-fill estimate, recalculated off the UI thread
        self._fill_job = None
        self._fill_bytes = 0
        # Checkbuttons that need their style swapped when the theme flips
        self._themed_checks = []
        # Icon images are held here so Tk cannot garbage-collect them
        self._button_icons = {}
        self.create_widgets()
        self.load_last_session()
        self.load_config()
        self.load_last_used_profile()







    def active_parent(self):
        """The window a new dialog should sit on top of.

        Usually the main window, but a popup raised from inside a dialog
        belongs over that dialog, not behind it.
        """
        try:
            focused = self.root.focus_displayof()
            if focused is not None:
                top = focused.winfo_toplevel()
                if top is not self.root and top.winfo_exists() and top.winfo_viewable():
                    return top
        except (tk.TclError, KeyError):
            pass
        return self.root

    def centre_on(self, window, width, height, parent=None):
        """Put `window` in the middle of `parent`, kept on screen.

        Two things went wrong before. Geometry was read before Tk had laid the
        parent out, so winfo_x/winfo_width answered 1 and 200 and the popup
        landed in the top-left corner of the monitor rather than over Rialto.
        And nothing clamped the result, so a Rialto window near the edge of a
        screen could put its own dialog half off it.
        """
        parent = parent or self.active_parent()
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            if pw <= 1 or ph <= 1:  # not laid out yet: fall back to the screen
                px = py = 0
                pw, ph = parent.winfo_screenwidth(), parent.winfo_screenheight()

            x = px + (pw - width) // 2
            y = py + (ph - height) // 3  # a third down reads better than dead centre

            # Keep it on the monitor the parent is on, near enough.
            screen_w = parent.winfo_screenwidth()
            screen_h = parent.winfo_screenheight()
            left_limit = min(px, 0)
            right_limit = max(px + pw, screen_w) - width
            x = max(left_limit, min(x, right_limit))
            y = max(0, min(y, max(py + ph, screen_h) - height))

            window.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        except tk.TclError:
            window.geometry(f"{width}x{height}")

    def darken_title_bar(self, window):
        """Ask Windows to draw this window's own title bar dark, in dark mode.

        The main window hides its title bar entirely, but a Toplevel keeps the
        native one, and a white caption above a black dialog is the first thing
        anyone notices. DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on Windows 10 2004
        and later, and was 19 on the 1809 to 1909 builds; both are tried and
        both are harmless if the OS does not know the attribute.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            window.update_idletasks()
            handle = ctypes.windll.user32.GetParent(window.winfo_id())
            if not handle:
                handle = window.winfo_id()
            dark = ctypes.c_int(1 if self.theme_mode.get() == "dark" else 0)
            for attribute in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle, attribute, ctypes.byref(dark), ctypes.sizeof(dark))
        except Exception:
            pass  # cosmetic only, and older Windows simply has no such thing

    def themed_dialog(self, title, subtitle=None, width=620, height=440):
        """A Toplevel that looks like the rest of Rialto.

        Every dialog gets the bird in the corner, a header strip in the theme's
        header colour, and the same body background - which is what the stock
        Toplevels were missing, and why Games on Disc came out white.

        Returns (dialog, body). Pack into `body`, never into `dialog`.
        """
        theme = self.current_theme()
        parent = self.active_parent()
        dialog = tk.Toplevel(parent)
        # The caption says Rialto, the header inside says what this dialog is.
        # Both saying "Disc Extras" put the same words on the screen twice.
        dialog.title(APP_NAME)
        dialog.configure(bg=theme["bg"])
        self.centre_on(dialog, width, height, parent)
        dialog.transient(parent)
        dialog.grab_set()

        icon_path = asset_path("bird_icon.ico")
        if os.path.exists(icon_path):
            try:
                dialog.iconbitmap(icon_path)
            except tk.TclError:
                pass

        self.darken_title_bar(dialog)

        header = tk.Frame(dialog, bg=theme["header_bg"])
        header.pack(fill="x")

        try:
            logo = Image.open(asset_path("bird_icon.ico")).convert("RGBA").resize((26, 26), Image.LANCZOS)
            image = ImageTk.PhotoImage(logo)
            badge = tk.Label(header, image=image, bg=theme["header_bg"])
            badge.image = image  # Tk keeps only a weak reference
            badge.pack(side="left", padx=(12, 10), pady=10)
        except Exception:
            pass

        text_wrap = tk.Frame(header, bg=theme["header_bg"])
        text_wrap.pack(side="left", pady=8)
        tk.Label(text_wrap, text=title, bg=theme["header_bg"], fg=theme["fg"],
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(anchor="w")
        if subtitle:
            tk.Label(text_wrap, text=subtitle, bg=theme["header_bg"], fg=theme["disabled_fg"],
                     font=("Segoe UI", 9), anchor="w", justify="left").pack(anchor="w")

        tk.Frame(dialog, bg=theme["button_bg"], height=1).pack(fill="x")

        body = tk.Frame(dialog, bg=theme["bg"])
        body.pack(fill="both", expand=True)
        return dialog, body

    def show_centered_popup(self, title, message, kind="info"):
        """Rialto's own message box: themed, bird in the corner, yes/no or OK.

        Sized from the message rather than fixed at 360x180, because the
        offline-page confirmation is three short paragraphs and the old fixed
        box cropped anything past two lines.
        """
        theme = self.current_theme()

        lines = sum(max(1, len(part) // 52 + 1) for part in message.split("\n"))
        height = min(460, max(190, 120 + lines * 20))
        width = 420

        parent = self.active_parent()
        popup = tk.Toplevel(parent)
        popup.title(APP_NAME)
        popup.configure(bg=theme["bg"])
        self.centre_on(popup, width, height, parent)
        popup.resizable(False, False)
        popup.transient(parent)
        popup.grab_set()

        icon_path = asset_path("bird_icon.ico")
        if os.path.exists(icon_path):
            try:
                popup.iconbitmap(icon_path)
            except tk.TclError:
                pass

        self.darken_title_bar(popup)

        header = tk.Frame(popup, bg=theme["header_bg"])
        header.pack(fill="x")
        try:
            logo = Image.open(icon_path).convert("RGBA").resize((22, 22), Image.LANCZOS)
            badge_image = ImageTk.PhotoImage(logo)
            badge = tk.Label(header, image=badge_image, bg=theme["header_bg"])
            badge.image = badge_image
            badge.pack(side="left", padx=(12, 8), pady=8)
        except Exception:
            pass
        tk.Label(header, text=title, bg=theme["header_bg"], fg=theme["fg"],
                 font=("Segoe UI", 11, "bold")).pack(side="left", pady=8)
        tk.Frame(popup, bg=theme["button_bg"], height=1).pack(fill="x")

        tk.Label(
            popup,
            text=message,
            wraplength=width - 48,
            justify="left",
            anchor="w",
            background=theme["bg"],
            foreground=theme["fg"],
            font=("Segoe UI", 10)
        ).pack(fill="both", expand=True, padx=20, pady=(14, 8))

        result = [False]

        button_frame = tk.Frame(popup, bg=theme["bg"])
        button_frame.pack(pady=(0, 14))

        if kind == "yesno":
            def yes_clicked():
                result[0] = True
                popup.destroy()

            def no_clicked():
                result[0] = False
                popup.destroy()

            ttk.Button(button_frame, text="Yes", command=yes_clicked,
                       style="Primary.TButton").pack(side="left", padx=8)
            ttk.Button(button_frame, text="No", command=no_clicked,
                       style="Rounded.TButton").pack(side="left", padx=8)
            popup.bind("<Return>", lambda _e: yes_clicked())
            popup.bind("<Escape>", lambda _e: no_clicked())
        else:
            ttk.Button(button_frame, text="OK", command=popup.destroy,
                       style="Primary.TButton").pack(padx=8)
            popup.bind("<Return>", lambda _e: popup.destroy())
            popup.bind("<Escape>", lambda _e: popup.destroy())

        self.root.wait_window(popup)
        return result[0] if kind == "yesno" else None







    def on_exit(self):
        self.save_last_session()
        self.root.destroy()




    def load_last_used_profile(self):
        if not os.path.exists(LAST_PROFILE_FILE):
            return

        try:
            with open(LAST_PROFILE_FILE, "r", encoding="utf-8") as f:
                last_data = json.load(f)
                profile_name = last_data.get("last_profile")
                if not profile_name:
                    return

                profile_path = os.path.join(APP_ROOT, profile_name)
                if not os.path.exists(profile_path):
                    return

                with open(profile_path, "r", encoding="utf-8") as pf:
                    profile_data = sanitize_profile_data(json.load(pf))
                    for k, v in profile_data.items():
                        if k in self.entries:
                            self.entries[k].delete(0, tk.END)
                            self.entries[k].insert(0, v)
                    self.bg_path_var.set(profile_data.get("Background", ""))
                    self.ico_path_var.set(profile_data.get("Icon", ""))
                    self.disc_icon_var.set(profile_data.get("DiscIcon", ""))
                    self.disc_name_var.set(profile_data.get("DiscName", ""))
                    self.game_executables = profile_data.get("GameExecutables", []) or []
                    self.refresh_game_exes_summary()


                self.update_status(f"✅ Restored session from {profile_name}")

        except Exception as e:
            self.update_status(f"[!] Failed to load last session: {e}")









    def create_widgets(self):
        # Custom Title Bar
        self.title_bar = tk.Frame(self.root, bg=self.dark_theme["bg"], relief="raised", bd=0, height=30)
        self.title_bar.pack(fill="x")


        try:
            icon_path = asset_path("bird_icon.ico")
            icon_img = Image.open(icon_path).convert("RGBA").resize((16, 16), Image.LANCZOS)
            self.toolbar_icon = ImageTk.PhotoImage(icon_img)
            icon_label = tk.Label(self.title_bar, image=self.toolbar_icon, bg=self.dark_theme["bg"])
            icon_label.pack(side="left", padx=6)
        except Exception:
            pass


        self.title_label = tk.Label(self.title_bar, text="Rialto 1.5", bg=self.dark_theme["bg"], fg=self.dark_theme["fg"], font=("Segoe UI", 10, "bold"))
        self.title_label.pack(side="left", padx=10)

        # Close Button
        self.close_btn = tk.Button(
            self.title_bar, text="X",
            bg=self.dark_theme["bg"],
            fg=self.dark_theme["fg"],
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            command=self.root.destroy
        )
        self.close_btn.pack(side="right", padx=(2, 8))
        ToolTip(self.close_btn, "Close")

        # Minimize Button
        self.minimize_btn = tk.Button(
            self.title_bar, text="–",
            bg=self.dark_theme["bg"],
            fg=self.dark_theme["fg"],
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            command=self.minimize_window
        )
        self.minimize_btn.pack(side="right", padx=(0, 2))
        ToolTip(self.minimize_btn, "Minimize")

        # Enable drag
        self.title_bar.bind("<B1-Motion>", self._move_window)
        self.title_bar.bind("<Button-1>", self._click_window)

        style = ttk.Style()
        style.theme_use('default')  # Ensures consistency across platforms

        # === Menu strip ===
        # Custom Menubuttons rather than a real menubar: the window is
        # overrideredirect (its title bar is drawn above), so a native menubar
        # has nowhere to attach and could not be themed with the rest anyway.
        self.menu_bar = tk.Frame(self.root, bg=self.dark_theme["header_bg"], height=28)
        self.menu_bar._rialto_surface = "header"
        self.menu_bar.pack(fill="x")
        self.menu_buttons = []
        self.menus = []

        def add_menu(label, entries):
            button = tk.Menubutton(
                self.menu_bar, text=label, relief="flat", bd=0,
                bg=self.dark_theme["header_bg"], fg=self.dark_theme["fg"],
                activebackground=self.dark_theme["button_active"],
                activeforeground=self.dark_theme["fg"],
                padx=12, pady=4, font=("Segoe UI", 10)
            )
            menu = tk.Menu(button, tearoff=0,
                           bg=self.dark_theme["entry_bg"], fg=self.dark_theme["fg"],
                           activebackground=self.dark_theme["accent"],
                           activeforeground="#ffffff",
                           bd=0, font=("Segoe UI", 10))
            for entry in entries:
                if entry is None:
                    menu.add_separator()
                else:
                    text, command = entry
                    menu.add_command(label=text, command=command)
            button.configure(menu=menu)
            button._rialto_surface = "header"
            button.pack(side="left")
            self.menu_buttons.append(button)
            self.menus.append(menu)
            return menu

        add_menu("File", [
            ("Save Profile…", self.save_profile),
            ("Load Profile…", self.load_profile),
            None,
            ("Put Rialto on the Desktop", self.create_desktop_shortcut),
            None,
            ("Exit", self.on_exit),
        ])
        add_menu("Disc", [
            ("Games on Disc…", self.configure_game_exes),
            ("Disc Extras…", self.configure_disc_extras),
            None,
            ("Configure Signing…", self.configure_signing),
        ])
        add_menu("Tools", [
            ("Import a GOG Installer…", self.import_gog_installer),
            ("Export an .msix Package…", self.export_msix),
        ])
        add_menu("View", [
            ("Switch Between Dark and Light", self.toggle_theme),
        ])
        add_menu("Help", [
            ("Help Guide", self.open_help_guide),
            ("Signing Guide", self.open_signing_guide),
            ("Check for a New Rialto…", self.check_for_new_rialto),
        ])

        # Main content container (everything below the menu strip)
        self.main_content = tk.Frame(self.root, bg=self.dark_theme["bg"])
        self.main_content.pack(fill="both", expand=True)

        # The export bar is packed first, against the bottom, so it always has
        # its space. Everything above it competes for what is left - which is
        # why Configure Signing used to fall off the bottom of the window on a
        # 1080p screen.
        self.build_export_bar()

        frame = ttk.Frame(self.main_content)

        # Set global font and padding
        default_font = ("Segoe UI", 10)
        self.root.option_add("*Font", default_font)
        self.root.option_add("*Label.Padding", 2)
        self.root.option_add("*Entry.Padding", 2)
        self.root.option_add("*Button.Padding", 4)


        style.configure("TButton",
            background="#e0e0e0",
            foreground="#000000",
            borderwidth=1,
            focusthickness=3,
            focuscolor="none",
            padding=(8, 4)
        )

        style.map("TButton",
            background=[('active', '#d0d0d0')],
            foreground=[('disabled', '#a0a0a0')],
            relief=[('pressed', 'flat'), ('!pressed', 'flat')]
        )
        style.configure("Rounded.TButton",
            background="#e0e0e0",
            foreground="#000000",
            borderwidth=1,
            focusthickness=0,
            padding=6,
            relief="flat"
        )



        # How this works, in the order you actually do it.
        #
        # The icons are drawn, not emoji. Tk renders an emoji in a Message
        # widget out of whatever monochrome symbol font Windows falls back to,
        # which turns 💿 into an empty box - and the ones that do render sit
        # off the baseline, the same problem the buttons had.
        self.tutorial_box = ttk.Frame(frame, style="Tutorial.TFrame")
        self.tutorial_box._rialto_style = "Tutorial.TFrame"
        self.tutorial_box.pack(pady=(0, 8), fill="x", ipady=2)

        def tutorial_line(icon_name, text, bold=False, pad=(0, 1)):
            # TutorialRow, not Tutorial: the card carries the groove border and
            # a row that inherited it drew a light bar under every icon.
            row = ttk.Frame(self.tutorial_box, style="TutorialRow.TFrame")
            row._rialto_style = "TutorialRow.TFrame"
            row.pack(fill="x", padx=12, pady=pad)

            gutter = ttk.Label(row, style="Tutorial.TLabel")
            gutter._rialto_style = "Tutorial.TLabel"
            if icon_name:
                image = ui_icon(icon_name, self.current_theme()["icon"], 16)
                self._button_icons["tut:%s@16" % icon_name] = image
                gutter.configure(image=image)
                gutter._rialto_icon = icon_name
                gutter._rialto_icon_size = 16
            else:
                gutter.configure(text=" ", width=2)
            gutter.pack(side="left", padx=(0, 9))

            label = ttk.Label(row, text=text, style="Tutorial.TLabel",
                              font=("Segoe UI", 10, "bold" if bold else "normal"))
            label._rialto_style = "Tutorial.TLabel"
            label.pack(side="left", fill="x", expand=True)

        tutorial_line("disc", "Three steps to a disc.", bold=True, pad=(8, 2))
        tutorial_line(None, "1.  Put your game in its own folder, then browse to it below.")
        tutorial_line(None, "2.  Fill in the name and art. Hover any field for what it wants.")
        tutorial_line(None, "3.  Preview the menu, then build. Your ISO lands in the output folder.")
        tutorial_line("image", "Background: an animated GIF or a still JPG, at 1280x720.",
                      pad=(8, 1))
        tutorial_line("tile", "Icons: .ico files at 256x256. icoconvert.com turns a PNG into one.")
        tutorial_line("gift", "Extras: bonus material, a mod tool, Mac and Linux builds all live "
                              "under Disc, Disc Extras.", pad=(0, 8))

        frame.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        # === Quick actions ===
        # The handful of things reached often enough that going into a menu for
        # them is a nuisance. One row, edge to edge, above Step 1. The menu
        # strip still carries everything, this is the shortcut.
        self.quick_row = ttk.Frame(frame)
        self.quick_row.pack(fill="x", pady=(0, 8))
        quick = [
            ("load", "Load Profile", self.load_profile,
             "Reload settings you saved earlier, so building the same game again is two clicks."),
            ("save", "Save Profile", self.save_profile,
             "Save everything on this screen to a file in templates, to pick up again later."),
            ("download", "Import GOG", self.import_gog_installer,
             "Unpack a GOG offline installer into a ready-to-use game folder. GOG games are "
             "DRM-free, which is what makes them work on a disc."),
            ("package", "Export .msix", self.export_msix,
             "Package the game as a modern Windows installer with a Start Menu entry and a "
             "clean uninstall. Windows only installs signed .msix files."),
            ("theme", "Dark / Light", self.toggle_theme,
             "Switch Rialto between dark and light. Your choice is remembered."),
            ("book", "Help Guide", self.open_help_guide,
             "Open the Rialto manual: every field, every option, and what to do when "
             "something goes wrong."),
        ]
        for index, (icon_name, label, command, tip) in enumerate(quick):
            self.quick_row.grid_columnconfigure(index, weight=1, uniform="quick")
            button = self.icon_button(self.quick_row, icon_name, label, command, size=15)
            button.grid(row=0, column=index, sticky="ew",
                        padx=(0 if index == 0 else 4, 0))
            ToolTip(button, tip)

        # === Step 1: the game folder ===
        # This is the one thing nothing else works without, so it gets its own
        # panel at the top instead of a small button halfway down the window.
        self.step_frame = ttk.LabelFrame(frame, text="Step 1: your game folder")
        self.step_frame.pack(fill="x", pady=(0, 8))

        step_row = ttk.Frame(self.step_frame)
        step_row.pack(fill="x", padx=6, pady=6)

        self.select_btn = self.icon_button(
            step_row, "folder", "Browse for your game folder",
            self.select_game_folder, style="Primary.TButton", size=18, side="left")
        ToolTip(self.select_btn,
                "Pick the folder holding your game. Rialto opens in its own input folder, "
                "but the game can live anywhere on your PC.")

        self.game_path_var = tk.StringVar(value="No folder chosen yet")
        self.game_path_label = ttk.Label(step_row, textvariable=self.game_path_var,
                                         style="Path.TLabel")
        self.game_path_label._rialto_style = "Path.TLabel"
        self.game_path_label.pack(side="left", padx=(10, 4), fill="x", expand=True)

        self.meta_frame = ttk.LabelFrame(frame, text="Step 2: metadata")
        self.meta_frame.pack(fill="x", pady=(0, 8))





        self.entries = {}

        # Essential metadata fields with display label mapping.
        # Publisher sits under Developer and may be left empty: plenty of indies
        # are their own publisher. When it is filled in it is the name that goes
        # on the copyright line, because that is who holds the copyright.
        essential_fields = ["Title", "Developer", "Publisher", "Start Menu Name"]
        display_labels = {"Title": "Game Title", "Developer": "Developer",
                          "Publisher": "Publisher", "Start Menu Name": "Start Menu Name"}

        for key in essential_fields:
            row = ttk.Frame(self.meta_frame)
            row.pack(fill="x", padx=4, pady=4)
            ttk.Label(row, text=display_labels[key] + ":", width=20).pack(side="left", padx=(0, 4), pady=2)
            entry = ttk.Entry(row)
            entry.pack(fill="x", expand=True, padx=4, pady=2)
            self.entries[key] = entry

            if key == "Title":
                ToolTip(entry, "Your game's title. This is what players see in the installer and disc menu.")
            elif key == "Developer":
                ToolTip(entry, "Who made the game: your name, your studio, or your team.")
            elif key == "Publisher":
                ToolTip(entry, "Who is publishing the game, if that is somebody other than you. "
                               "Leave it empty and the copyright line follows Developer instead.")
            elif key == "Start Menu Name":
                ToolTip(entry, "The name players see in their Windows Start Menu. Fills in from Game Title until you type your own.")

        # Copyright Text (inside Metadata frame, follows Publisher or Developer)
        copyright_row = ttk.Frame(self.meta_frame)
        copyright_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(copyright_row, text="Copyright Text:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.publisher_text_var = tk.StringVar()
        publisher_entry = ttk.Entry(copyright_row, textvariable=self.publisher_text_var)
        publisher_entry.pack(fill="x", expand=True, padx=4, pady=2)
        ToolTip(publisher_entry, "The copyright line on your installer, like '\u00a9 2026 Your Name.' "
                                 "Fills in from Publisher, or from Developer when Publisher is empty. "
                                 "Edit it any time.")

        # Disc Name (inside Metadata frame, auto-populated from Game Title)
        disc_name_row = ttk.Frame(self.meta_frame)
        disc_name_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(disc_name_row, text="Disc Name:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.disc_name_var = tk.StringVar()
        self.disc_label_entry = ttk.Entry(disc_name_row, textvariable=self.disc_name_var)
        self.disc_label_entry.pack(fill="x", expand=True, padx=4, pady=2)
        ToolTip(self.disc_label_entry, "The label players see in File Explorer when the disc is inserted, like a DVD name. Fills in from Game Title.")

        # Auto-populate tracking flags. Game Icon no longer fills in Disc Icon:
        # the two are usually the same file, but a disc is allowed its own art
        # and there was no way to say so once the copy had already happened.
        self._auto_start_menu = True
        self._auto_disc_name = True
        self._auto_copyright = True

        # StringVar traces for auto-populate
        self._title_var = tk.StringVar()
        self.entries["Title"].configure(textvariable=self._title_var)
        self._developer_var = tk.StringVar()
        self.entries["Developer"].configure(textvariable=self._developer_var)
        self._publisher_var = tk.StringVar()
        self.entries["Publisher"].configure(textvariable=self._publisher_var)

        # Hints, on the three fields somebody has to answer for themselves.
        # Everything below them fills itself in from these, so they are the
        # only ones worth explaining inside the box.
        self.add_placeholder(self.entries["Title"], self._title_var,
                             "What the game is called")
        self.add_placeholder(self.entries["Developer"], self._developer_var,
                             "Who made it: you, your studio, or your team")
        self.add_placeholder(self.entries["Publisher"], self._publisher_var,
                             "Only if someone else is publishing it")

        def _on_title_changed(*args):
            title = self._title_var.get()
            if self._auto_start_menu:
                self.entries["Start Menu Name"].delete(0, tk.END)
                self.entries["Start Menu Name"].insert(0, title)
            if self._auto_disc_name:
                self.disc_name_var.set(title)

        def _on_rights_holder_changed(*args):
            # "Published by Mock Publishing. Developed by Jane Smith 2026.
            # All rights reserved." Either half can be missing; the year rides
            # with the developer, because that is who made it and when.
            if not self._auto_copyright:
                return
            publisher = self._publisher_var.get().strip()
            developer = self._developer_var.get().strip()
            parts = []
            if developer:
                parts.append(f"Developed by {developer} {datetime.datetime.now().year}.")
            if publisher:
                parts.append(f"Published by {publisher}.")
            if parts:
                parts.append("All rights reserved.")
            self.publisher_text_var.set(" ".join(parts))

        self._regenerate_copyright = _on_rights_holder_changed

        self._title_var.trace_add("write", _on_title_changed)
        self._developer_var.trace_add("write", _on_rights_holder_changed)
        self._publisher_var.trace_add("write", _on_rights_holder_changed)

        # Manual edit detection: stop auto-populating when user types directly
        def _on_start_menu_key(event):
            self._auto_start_menu = False
        self.entries["Start Menu Name"].bind("<Key>", _on_start_menu_key)

        def _on_copyright_key(event):
            self._auto_copyright = False
        publisher_entry.bind("<Key>", _on_copyright_key)

        def _on_disc_name_key(event):
            self._auto_disc_name = False
        self.disc_label_entry.bind("<Key>", _on_disc_name_key)







        # === The disc itself ===
        self.disc_frame = ttk.LabelFrame(frame, text="Step 3: the disc")
        self.disc_frame.pack(fill="x", pady=(0, 8))

        # games on disc (multi-game support)
        exe_row = ttk.Frame(self.disc_frame)
        exe_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(exe_row, text="Games on Disc:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.game_exes_summary_var = tk.StringVar(value="Auto-detect (single game)")
        exe_summary = ttk.Entry(exe_row, textvariable=self.game_exes_summary_var, state="readonly")
        exe_summary.pack(side="left", fill="x", expand=True)
        exe_btn = ttk.Button(exe_row, text="Configure", command=self.configure_game_exes, style="Rounded.TButton")
        exe_btn.pack(side="left", padx=(6, 4), pady=2)
        exe_tip = "Want more than one game on the disc? Click Configure and check each game. Players get a Choose Your Game screen. Leave on auto-detect for a normal single-game disc."
        ToolTip(exe_summary, exe_tip)
        ToolTip(exe_btn, exe_tip)

        # target media + disc extras
        media_row = ttk.Frame(self.disc_frame)
        media_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(media_row, text="Target Media:", width=20).pack(side="left", padx=(0, 4), pady=2)
        media_combo = ttk.Combobox(media_row, textvariable=self.target_media_var, state="readonly",
                                   values=[name for name, _cap in self.MEDIA_TYPES])
        media_combo.pack(side="left", fill="x", expand=True)
        media_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_disc_meter())
        extras_btn = ttk.Button(media_row, text="Disc Extras", command=self.configure_disc_extras, style="Rounded.TButton")
        extras_btn.pack(side="left", padx=(6, 4), pady=2)
        ToolTip(media_combo, "Pick the disc you plan to burn. If your game is too big for one disc, Rialto builds a numbered multi-disc set automatically. Auto means one disc, any size.")
        ToolTip(extras_btn, "Bonus material, a mod tool, an ADD TO STEAM button for players, and Mac or Linux builds riding along on the same disc.")

        # === Artwork ===
        self.art_frame = ttk.LabelFrame(frame, text="Step 4: artwork")
        self.art_frame.pack(fill="x", pady=(0, 8))

        # background jpg/video
        img_row = ttk.Frame(self.art_frame)
        img_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(img_row, text="Menu Background:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.bg_path_var = tk.StringVar()
        bg_entry = ttk.Entry(img_row, textvariable=self.bg_path_var)
        bg_entry.pack(side="left", fill="x", expand=True)
        bg_browse = ttk.Button(img_row, text="Browse", command=self.browse_bg, style="Rounded.TButton")
        bg_browse.pack(side="left", padx=(0, 4), pady=2)
        bg_tip = "The background for your disc's menu: an animated GIF or a still JPG, at 1280x720. GIFs are recommended, and ezgif.com makes one from a video clip."
        ToolTip(img_row, bg_tip)
        ToolTip(bg_entry, bg_tip)
        ToolTip(bg_browse, "Pick a background GIF or JPG from your files.")


        # game logo
        logo_row = ttk.Frame(self.art_frame)
        logo_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(logo_row, text="Game Logo (.png):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.logo_path_var = tk.StringVar()
        logo_entry = ttk.Entry(logo_row, textvariable=self.logo_path_var)
        logo_entry.pack(side="left", fill="x", expand=True)
        logo_browse = ttk.Button(logo_row, text="Browse", command=self.browse_logo, style="Rounded.TButton")
        logo_browse.pack(side="left", padx=(0, 4), pady=2)
        logo_tip = "Your game's logo, shown front-and-center on the disc menu. Use a PNG with a transparent background, ideally 400x150 pixels or smaller."
        ToolTip(logo_row, logo_tip)
        ToolTip(logo_entry, logo_tip)
        ToolTip(logo_browse, "Pick your game logo image (PNG).")

        # company logo (bottom corner of the menu)
        company_logo_row = ttk.Frame(self.art_frame)
        company_logo_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(company_logo_row, text="Company Logo (.png):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.company_logo_var = tk.StringVar()
        cl_entry = ttk.Entry(company_logo_row, textvariable=self.company_logo_var)
        cl_entry.pack(side="left", fill="x", expand=True)
        cl_browse = ttk.Button(company_logo_row, text="Browse", command=self.browse_company_logo, style="Rounded.TButton")
        cl_browse.pack(side="left", padx=(0, 4), pady=2)
        cl_tip = "Your studio or company logo, shown in the bottom-right of the disc menu. Use a small transparent PNG, around 150x75 pixels."
        ToolTip(company_logo_row, cl_tip)
        ToolTip(cl_entry, cl_tip)
        ToolTip(cl_browse, "Pick your company or studio logo (PNG).")

        # game icon
        ico_row = ttk.Frame(self.art_frame)
        ico_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(ico_row, text="Game Icon (.ico):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.ico_path_var = tk.StringVar()
        ico_entry = ttk.Entry(ico_row, textvariable=self.ico_path_var)
        ico_entry.pack(side="left", fill="x", expand=True)
        ico_browse = ttk.Button(ico_row, text="Browse", command=self.browse_ico, style="Rounded.TButton")
        ico_browse.pack(side="left", padx=(0, 4), pady=2)
        ico_tip = "The icon for your installer and desktop shortcut: the small image players see in their Start Menu and taskbar. Needs to be a 256x256 .ico file. You can convert a PNG at icoconvert.com."
        ToolTip(ico_row, ico_tip)
        ToolTip(ico_entry, ico_tip)
        ToolTip(ico_browse, "Pick your game's icon file (.ico format).")


        # disc icon
        disc_icon_row = ttk.Frame(self.art_frame)
        disc_icon_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(disc_icon_row, text="Disc Icon (.ico):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.disc_icon_var = tk.StringVar()
        di_entry = ttk.Entry(disc_icon_row, textvariable=self.disc_icon_var)
        di_entry.pack(side="left", fill="x", expand=True)
        di_browse = ttk.Button(disc_icon_row, text="Browse", command=self.browse_disc_icon, style="Rounded.TButton")
        di_browse.pack(side="left", padx=(0, 4), pady=2)
        di_tip = "The icon shown in File Explorer when the disc is inserted, like the small picture on a DVD drive. Must be .ico format. Often the same file as Game Icon, but it does not have to be."
        ToolTip(disc_icon_row, di_tip)
        ToolTip(di_entry, di_tip)
        ToolTip(di_browse, "Pick a disc icon file (.ico format).")









        # Live status box. Packed last and set to expand, so when the window is
        # short this is what gives up room - never the export bar.
        self.status_text = tk.Text(frame, height=4, wrap="word", state="disabled", bg="#1e1e1e", fg="#00FF00", font=("Segoe UI", 10))
        self.status_text.pack(fill="both", expand=True, padx=2, pady=(2, 8))
        self.status_text.tag_config("success", foreground="#00FF00")
        self.status_text.tag_config("error", foreground="#FF0000")
        self.status_text.tag_config("warning", foreground="#FFA500")
        self.status_text.tag_config("processing", foreground="#00FFFF")
        self.status_text.tag_config("signing", foreground="#FF00FF")
        self.status_text.tag_config("burn", foreground="#FF8C00")
        self.status_text.tag_config("disc", foreground="#87CEEB")

        self.update_status("Ready.")





        self.apply_dark_theme()
        self.refresh_disc_meter()

    # === The export bar ===

    def build_export_bar(self):
        """The strip along the bottom: what you are making, and the button that makes it.

        Pinned to the bottom of main_content before anything else is packed, so
        it cannot be pushed off the window the way Configure Signing was on a
        1080p screen.
        """
        theme = self.dark_theme

        def surface(widget):
            widget._rialto_surface = "header"
            return widget

        self.export_bar = surface(tk.Frame(self.main_content, bg=theme["header_bg"],
                                           highlightthickness=0, bd=0))
        self.export_bar.pack(side="bottom", fill="x")

        # A hairline so the bar reads as its own surface in both themes
        self.export_rule = tk.Frame(self.export_bar, bg=theme["button_bg"], height=1)
        self.export_rule.pack(fill="x")

        inner = surface(tk.Frame(self.export_bar, bg=theme["header_bg"]))
        inner.pack(fill="x", padx=14, pady=(8, 12))
        self.export_inner = inner

        # --- Row 1: the disc filling up ---
        meter_row = surface(tk.Frame(inner, bg=theme["header_bg"]))
        meter_row.pack(fill="x")

        self.disc_meter = surface(tk.Canvas(meter_row, width=34, height=34,
                                            highlightthickness=0, bg=theme["header_bg"], bd=0))
        self.disc_meter.pack(side="left", padx=(0, 10))

        meter_text = surface(tk.Frame(meter_row, bg=theme["header_bg"]))
        meter_text.pack(side="left", fill="x", expand=True)

        self.disc_fill_var = tk.StringVar(value="No game folder chosen yet")
        self.disc_fill_label = surface(tk.Label(meter_text, textvariable=self.disc_fill_var,
                                                bg=theme["header_bg"], fg=theme["fg"],
                                                anchor="w", font=("Segoe UI", 10)))
        self.disc_fill_label.pack(fill="x")

        self.disc_bar = tk.Canvas(meter_text, height=8, highlightthickness=0,
                                  bg=theme["meter_track"], bd=0)
        self.disc_bar.pack(fill="x", pady=(3, 0))
        self.disc_bar.bind("<Configure>", lambda _e: self.draw_disc_meter())

        meter_tip = ("Roughly how much of the disc your game fills. Measured from your game "
                     "folder and artwork before compression, so the finished ISO is usually "
                     "smaller. Change Target Media to see it against a different disc.")
        ToolTip(self.disc_meter, meter_tip)
        ToolTip(self.disc_fill_label, meter_tip)

        # --- Row 2: build and preview ---
        action_row = surface(tk.Frame(inner, bg=theme["header_bg"]))
        action_row.pack(fill="x", pady=(10, 0))

        build_btn = self.icon_button(action_row, "play", "BUILD GAME INSTALLER",
                                     self.run_build_process, style="Build.TButton", size=15)
        build_btn.pack(side="left", ipady=6, fill="x", expand=True)
        ToolTip(build_btn, "Makes the whole disc: installer, disc menu, artwork and the final ISO, "
                           "in one pass. The log above says what it is doing at each step.")

        # Disc Extras sits here as well as beside Target Media. It is where
        # bonus content, mods, Steam and the Mac and Linux builds live, and up
        # in the form on its own it is easy to walk straight past.
        extras_btn = self.icon_button(action_row, "gift", "Disc Extras",
                                      self.configure_disc_extras, size=15)
        extras_btn.pack(side="left", padx=(8, 0), ipady=6)
        ToolTip(extras_btn, "Bonus content, a mod tool, the ADD TO STEAM button, and Mac or Linux "
                            "builds riding along on the same disc. All optional.")

        preview_btn = self.icon_button(action_row, "eye", "Preview Disc Menu",
                                       self.preview_disc_menu, size=15)
        preview_btn.pack(side="left", padx=(8, 0), ipady=6)
        ToolTip(preview_btn, "Opens your disc menu exactly as players will see it, in a few seconds. "
                             "Nothing is built or burned, and Play and Uninstall are switched off "
                             "so you can click around freely.")

        signing_btn = self.icon_button(action_row, "gear", "Configure Signing",
                                       self.configure_signing, size=15)
        signing_btn.pack(side="left", padx=(8, 0), ipady=6)
        ToolTip(signing_btn, "One-time setup that puts your own name on the Windows install prompt "
                             "instead of Unknown Publisher. The dialog checks your setup and links "
                             "the full guide.")

        # --- Row 3: the switches that change what gets built ---
        check_row = surface(tk.Frame(inner, bg=theme["header_bg"]))
        check_row.pack(fill="x", pady=(8, 0))
        self.export_check_row = check_row

        install_check_style(ttk.Style(), "light", self.light_theme)

        usb_check = self.themed_check(check_row, "Also export for USB", self.usb_export_var,
                                      surface="header", side="left", padx=(0, 18))
        ToolTip(usb_check, "Copies the finished disc files to a USB stick, or any folder you pick, "
                           "as well as making the ISO. USB sticks cannot auto-run, so a Start Here "
                           "file goes with them.")

        sign_check = self.themed_check(check_row, "Sign Final Build", self.sign_final_build,
                                       surface="header", command=self.save_signing_settings,
                                       side="left", padx=(0, 18))
        ToolTip(sign_check, "Signs your installer and this disc's copy of menu.exe with your own "
                            "certificate, so Windows names you instead of showing Unknown Publisher. "
                            "Set it up under Configure Signing; without it the build pauses so you "
                            "can sign by hand.")

        branding_check = self.themed_check(check_row, "Remove WTI Branding", self.remove_wti_branding,
                                           surface="header", command=self.save_signing_settings,
                                           side="left", padx=(0, 18))
        ToolTip(branding_check, "Takes the We the Indies bird and wordmark off your disc menu, so "
                                "the disc carries only your own branding. It comes out of the "
                                "copyright line too.")

        reset_btn = self.icon_button(check_row, "reset", "Restore page",
                                     self.restore_page, size=14)
        reset_btn.pack(side="right")
        ToolTip(reset_btn, "Returns all values on the page to original defaults. "
                           "Save your work first!")

    def restore_page(self):
        """Put every field back to the state a fresh Rialto starts in.

        Touches only what is on this screen. Saved profiles, the signing
        details and anything already built are all left alone, which is why the
        warning says to save first rather than saying it is destructive.
        """
        if not self.show_centered_popup(
                "Restore page",
                "Clear every field on this page and start again?\n\n"
                "Saved profiles, your signing setup and anything already built are "
                "not touched. Anything typed here and not saved is lost.",
                kind="yesno"):
            return

        self.current_game_path = None
        self.game_path_var.set("No folder chosen yet")

        # Auto-fill goes back on: the whole point is a blank slate.
        self._auto_start_menu = True
        self._auto_disc_name = True
        self._auto_copyright = True

        for entry in self.entries.values():
            entry.delete(0, tk.END)
        for var in (self.publisher_text_var, self.disc_name_var, self.bg_path_var,
                    self.logo_path_var, self.company_logo_var, self.ico_path_var,
                    self.disc_icon_var, self.mac_build_var, self.linux_build_var,
                    self.bonus_folder_var):
            var.set("")

        self.game_executables = []
        self.refresh_game_exes_summary()
        self.target_media_var.set("Auto (single disc)")
        self.usb_export_var.set(False)
        self.sign_final_build.set(False)
        self.remove_wti_branding.set(False)
        self.mod_launcher_var.set(False)
        self.mod_folder_var.set("")
        self.steam_button_var.set(True)
        self.compat_mode_var.set(False)
        self.compat_args_var.set("")
        self.compat_hint_var.set("")
        self.save_signing_settings()

        self.refresh_disc_meter()
        self.update_status("↺ Page restored to defaults")

    # === Disc fill meter ===

    # The Visual C++ redistributables are fetched at build time and packed into
    # setup.exe. They are not on disk yet when the meter runs, so their weight
    # is allowed for rather than measured.
    RUNTIME_ALLOWANCE = 26 * 1024 * 1024

    def menu_staging_bytes(self):
        """Weight of the menu folder the build will stage, in bytes.

        menu.exe alone is nearly 40 MB and the background is copied in beside
        it, so leaving this out understated a disc by a tenth of a gigabyte.
        Measured from the real prebuilt binary where it can be found, so the
        number tracks the artifact instead of a guess about it.
        """
        total = self.RUNTIME_ALLOWANCE
        prebuilt = prebuilt_menu_exe()
        if prebuilt and os.path.isfile(prebuilt):
            try:
                total += os.path.getsize(prebuilt)
            except OSError:
                total += 40 * 1024 * 1024
        else:
            total += 40 * 1024 * 1024
        background = self.bg_path_var.get().strip()
        if background and os.path.isfile(background):
            try:
                total += os.path.getsize(background)
            except OSError:
                pass
        # Steam art, logos and the runtime DLLs beside the menu.
        total += 4 * 1024 * 1024
        return total

    def refresh_disc_meter(self):
        """Re-measure the game folder and redraw the fill, off the UI thread.

        Sizing a folder means walking it, which is instant on an SSD and is not
        instant on a spinning disk holding a 40 GB game, so the walk happens on
        a worker thread and the drawing comes back to Tk.
        """
        if not hasattr(self, "disc_bar"):
            return
        path = self.current_game_path
        if not path or not os.path.isdir(path):
            self._fill_bytes = 0
            self.draw_disc_meter()
            return

        extras = [v.get().strip() for v in
                  (self.bg_path_var, self.logo_path_var, self.company_logo_var,
                   self.ico_path_var, self.disc_icon_var, self.mac_build_var,
                   self.linux_build_var, self.bonus_folder_var)]

        def folder_size(folder):
            total = 0
            for root_dir, _dirs, files in os.walk(folder):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root_dir, name))
                    except OSError:
                        pass
            return total

        # What the disc carries beyond the game folder, and what it carries
        # twice. The meter used to weigh the source folder and stop there,
        # which could read well under the finished disc - the author
        # is told it fits on a CD when it needs a DVD.
        duplicated = []
        if self.mod_launcher_var.get():
            duplicated.append(self.resolved_mod_dir())
        duplicated.append(self.resolved_bonus_dir())
        duplicated.extend([self.mac_build_var.get().strip(),
                           self.linux_build_var.get().strip()])
        menu_extra = self.menu_staging_bytes()

        def measure():
            total = folder_size(path)
            for extra in extras:
                # Art already inside the game folder is counted once, not twice
                if not extra or extra.startswith(path):
                    continue
                if os.path.isfile(extra):
                    try:
                        total += os.path.getsize(extra)
                    except OSError:
                        pass
                elif os.path.isdir(extra):
                    total += folder_size(extra)

            # These ride on the disc root AND inside the installer, so they
            # land on the media twice however they were counted above.
            for folder in duplicated:
                if folder and os.path.isdir(folder):
                    total += folder_size(folder)

            self._fill_bytes = total + menu_extra
            try:
                self.root.after(0, self.draw_disc_meter)
            except (RuntimeError, tk.TclError):
                pass  # window closed while the walk was still running

        threading.Thread(target=measure, daemon=True).start()

    def draw_disc_meter(self):
        """Paint the little disc and the bar beside it from self._fill_bytes."""
        if not hasattr(self, "disc_bar"):
            return
        theme = self.dark_theme if self.theme_mode.get() == "dark" else self.light_theme
        total = self._fill_bytes
        capacity = self.get_target_media_capacity()
        usable = (capacity - self.MEDIA_RESERVE) if capacity else 0

        if not total:
            fraction = 0.0
            text = "No game folder chosen yet"
            color = theme["meter_fill"]
        elif not capacity:
            fraction = 0.0
            text = "%.2f GB of content - pick a Target Media to see how it fits" % (total / 1e9)
            color = theme["meter_fill"]
        else:
            fraction = (total / usable) if usable else 0.0
            percent = int(round(min(fraction, 9.99) * 100))
            label = self.target_media_var.get()
            if fraction <= 0.9:
                color = theme["meter_fill"]
            elif fraction <= 1.0:
                color = theme["meter_warn"]
            else:
                color = theme["meter_over"]
            text = "%.2f GB of %.2f GB usable on %s - %d%%" % (
                total / 1e9, usable / 1e9, label, percent)
            if fraction > 1.0:
                discs = int(total // usable) + 1
                text += " - about %d discs" % discs

        self.disc_fill_var.set(text)

        # The bar
        bar = self.disc_bar
        bar.delete("all")
        width = max(bar.winfo_width(), 1)
        bar.configure(bg=theme["meter_track"])
        filled = int(width * min(fraction, 1.0))
        if filled > 0:
            bar.create_rectangle(0, 0, filled, 12, fill=color, outline=color)

        # The disc: a ring that fills clockwise from twelve o'clock
        disc = self.disc_meter
        disc.delete("all")
        disc.configure(bg=theme["header_bg"])
        pad = 3
        size = 34 - pad * 2
        # The empty ring reads against the bar's own background, so it uses the
        # button colour rather than the (identical) track colour.
        ring = theme["button_bg"]
        disc.create_oval(pad, pad, pad + size, pad + size, outline=ring, width=4)
        if fraction > 0:
            disc.create_arc(pad, pad, pad + size, pad + size,
                            start=90, extent=-359.9 * min(fraction, 1.0),
                            style="arc", outline=color, width=4)
        disc.create_oval(15, 15, 19, 19, outline=ring, width=1)

    def toggle_theme(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure(".", background="", foreground="")  # Clear inherited ttk styling

        new_mode = "light" if self.theme_mode.get() == "dark" else "dark"
        self.theme_mode.set(new_mode)

        if new_mode == "dark":
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

        theme_colors = self.dark_theme if new_mode == "dark" else self.light_theme
        try:
            self.root.configure(bg=theme_colors["bg"])
        except tk.TclError:
            pass
        self._force_theme_refresh(theme_colors)







    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}
        
        # Load signing settings
        self.sign_final_build.set(self.config.get("sign_final_build", False))
        self.remove_wti_branding.set(self.config.get("remove_wti_branding", False))
        self.mod_launcher_var.set(self.config.get("mod_launcher", False))


    def save_profile(self):
        """Save profile data"""
        # Only save the essential fields (cleaned up)
        profile_data = {k: entry.get() for k, entry in self.entries.items()}
        
        # Add the additional settings
        profile_data["Background"] = self.bg_path_var.get()
        profile_data["Logo"] = self.logo_path_var.get()
        profile_data["CompanyLogo"] = self.company_logo_var.get()
        profile_data["PublisherText"] = self.publisher_text_var.get()
        profile_data["Icon"] = self.ico_path_var.get()
        profile_data["DiscIcon"] = self.disc_icon_var.get()
        profile_data["DiscName"] = self.disc_name_var.get()
        profile_data["RemoveWTIBranding"] = self.remove_wti_branding.get()
        profile_data["GameExecutables"] = self.game_executables
        profile_data["TargetMedia"] = self.target_media_var.get()
        profile_data["MacBuild"] = self.mac_build_var.get()
        profile_data["LinuxBuild"] = self.linux_build_var.get()
        profile_data["SteamButton"] = bool(self.steam_button_var.get())
        profile_data["ModLauncher"] = bool(self.mod_launcher_var.get())
        profile_data["ModFolder"] = self.mod_folder_var.get()
        profile_data["CompatibilityMode"] = bool(self.compat_mode_var.get())
        profile_data["CompatibilityArgs"] = self.compat_args_var.get()
        profile_data["CompatibilityHint"] = self.compat_hint_var.get()
        profile_data["BonusFolder"] = self.bonus_folder_var.get()

        # Add metadata for profile version (for future compatibility)
        profile_data["_ProfileVersion"] = "2.2"
        profile_data["_CreatedBy"] = f"{APP_NAME} {__version__}"

        # Default to templates folder
        templates_dir = TEMPLATES_DIR
        os.makedirs(templates_dir, exist_ok=True)

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json", 
            filetypes=[("JSON Files", "*.json")],
            title="Save Rialto Profile",
            initialdir=templates_dir
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(profile_data, f, indent=4)
                self.update_status(f"✅ Profile saved: {os.path.basename(file_path)}")
            except Exception as e:
                self.update_status(f"❌ Failed to save profile: {e}")

    def load_profile(self):
        """Load profile data"""

        # Default to templates folder
        templates_dir = TEMPLATES_DIR
        os.makedirs(templates_dir, exist_ok=True)

        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="Load Rialto Profile",
            initialdir=templates_dir
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    profile_data = sanitize_profile_data(json.load(f))
                
                # Load the essential fields
                for k, v in profile_data.items():
                    if k in self.entries:
                        self.entries[k].delete(0, tk.END)
                        self.entries[k].insert(0, v)
                
                # Load additional settings
                self.bg_path_var.set(profile_data.get("Background", ""))
                self.logo_path_var.set(profile_data.get("Logo", ""))
                self.company_logo_var.set(profile_data.get("CompanyLogo", ""))
                # A stored copyright line wins and stops auto-filling. An empty
                # one does not: writing "" over the line the Developer field
                # had just generated left the box blank with a developer named
                # right above it.
                stored_copyright = (profile_data.get("PublisherText") or "").strip()
                if stored_copyright:
                    self.publisher_text_var.set(stored_copyright)
                    self._auto_copyright = False
                else:
                    self._auto_copyright = True
                    self._regenerate_copyright()
                self.ico_path_var.set(profile_data.get("Icon", ""))
                self.disc_icon_var.set(profile_data.get("DiscIcon", ""))
                self.disc_name_var.set(profile_data.get("DiscName", ""))
                self.remove_wti_branding.set(profile_data.get("RemoveWTIBranding", False))
                self.game_executables = profile_data.get("GameExecutables", []) or []
                self.refresh_game_exes_summary()
                self.target_media_var.set(profile_data.get("TargetMedia", "Auto (single disc)"))
                self.mac_build_var.set(profile_data.get("MacBuild", ""))
                self.linux_build_var.set(profile_data.get("LinuxBuild", ""))
                self.steam_button_var.set(profile_data.get("SteamButton", True))
                self.mod_launcher_var.set(profile_data.get("ModLauncher", False))
                self.mod_folder_var.set(profile_data.get("ModFolder", ""))
                self.compat_mode_var.set(profile_data.get("CompatibilityMode", False))
                self.compat_args_var.set(profile_data.get("CompatibilityArgs", ""))
                self.compat_hint_var.set(profile_data.get("CompatibilityHint", ""))
                # A profile written against a different input root brings
                # absolute paths with it. Re-point them at the game folder
                # in use now, rather than passing over them at build time.
                self.rebase_stale_paths()
                self.bonus_folder_var.set(profile_data.get("BonusFolder", ""))
                self.refresh_disc_meter()

                self.update_status(f"✅ Profile loaded: {os.path.basename(file_path)}")

                # A profile stores absolute paths, so one saved before the game
                # moved will quietly point at art that is no longer there. Say
                # so on load rather than at the end of a build.
                stale = [(label, var.get().strip()) for label, var in (
                    ("Menu Background", self.bg_path_var),
                    ("Game Logo", self.logo_path_var),
                    ("Company Logo", self.company_logo_var),
                    ("Game Icon", self.ico_path_var),
                    ("Disc Icon", self.disc_icon_var),
                ) if var.get().strip() and not os.path.exists(var.get().strip())]
                for label, path in stale:
                    self.update_status(f"⚠️ {label} in this profile no longer exists: {path}")
                if stale:
                    self.update_status("   Pick the file again, or the disc is built without it.")
                
                # Save as last used profile
                profile_name = Path(file_path).name
                with open(LAST_PROFILE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"last_profile": profile_name}, f)
                    
            except Exception as e:
                self.update_status(f"❌ Failed to load profile: {e}")






    # === Rialto 1.5: multi-game disc support ===

    HELPER_EXE_NAMES = {'setup.exe', 'unins000.exe', 'unins001.exe', 'menu.exe',
                        'unitycrashhandler64.exe', 'unitycrashhandler32.exe',
                        'createdump.exe', 'crashpad_handler.exe',
                        'vcredist_x64.exe', 'vcredist_x86.exe', 'dotnet.exe'}

    # (display name, capacity in bytes). None = no limit, single disc.
    #
    # M-DISC is ordinary DVD/BD geometry written into a rock-like inorganic
    # layer rated for centuries rather than a dye rated for years, so the
    # capacities are identical to their normal counterparts - it is listed
    # separately because archival buyers shop for the name, and because a
    # printed disc label should say which one it is.
    #
    # 4K UHD Blu-ray discs are BDXL-family media: 66 GB dual layer and 100 GB
    # triple layer. Burnable BD-R versions exist and hold the same data as any
    # other BD-R; what makes a retail UHD movie disc special is AACS 2.0, which
    # nothing here touches.
    MEDIA_TYPES = [
        ("Auto (single disc)", None),
        ("CD 700 MB", 737_280_000),
        ("DVD 4.7 GB", 4_700_000_000),
        ("DVD DL 8.5 GB", 8_540_000_000),
        ("M-DISC DVD 4.7 GB", 4_700_000_000),
        ("Blu-ray 25 GB", 25_000_000_000),
        ("Blu-ray DL 50 GB", 50_000_000_000),
        ("M-DISC Blu-ray 25 GB", 25_000_000_000),
        ("M-DISC Blu-ray DL 50 GB", 50_000_000_000),
        ("Blu-ray XL 66 GB (4K UHD)", 66_000_000_000),
        ("Blu-ray XL 100 GB", 100_000_000_000),
        ("M-DISC Blu-ray XL 100 GB", 100_000_000_000),
        ("Blu-ray XL 128 GB (BD-R quad layer)", 128_000_000_000),
    ]
    # Room kept free on each disc for the menu, setup stub, art and filesystem
    MEDIA_RESERVE = 96 * 1024 * 1024

    def get_target_media_capacity(self):
        selected = self.target_media_var.get() if hasattr(self, "target_media_var") else ""
        for name, capacity in self.MEDIA_TYPES:
            if name == selected:
                return capacity
        return None

    def get_disk_slice_size(self):
        """Inno Setup slice size for the chosen disc, so slices always fit."""
        capacity = self.get_target_media_capacity()
        if not capacity:
            return None
        budget = capacity - self.MEDIA_RESERVE
        # Inno Setup allows slices between 262144 and 2100000000 bytes
        return max(262_144, min(budget, 2_100_000_000))

    def refresh_game_exes_summary(self):
        """Keep the 'Games on Disc' summary field in sync with configuration."""
        if not hasattr(self, "game_exes_summary_var"):
            return
        games = self.game_executables
        if not games:
            self.game_exes_summary_var.set("Auto-detect (single game)")
        elif len(games) == 1:
            self.game_exes_summary_var.set(f"1 game: {games[0].get('name', games[0].get('exe', '?'))}")
        else:
            names = ", ".join(g.get("name", g.get("exe", "?")) for g in games)
            self.game_exes_summary_var.set(f"{len(games)} games: {names}")

    def validated_game_executables(self):
        """Return configured games whose EXE actually exists in the game folder."""
        valid = []
        for game in self.game_executables:
            exe = (game.get("exe") or "").strip().replace("\\", "/")
            if not exe:
                continue
            name = (game.get("name") or os.path.splitext(os.path.basename(exe))[0]).strip()
            if self.current_game_path and not os.path.exists(os.path.join(self.current_game_path, exe)):
                self.update_status(f"⚠️ Games on Disc: '{exe}' not found in game folder - skipped")
                continue
            valid.append({"name": name, "exe": exe})
        return valid

    def discover_game_exes(self):
        """Scan the selected game folder for launchable EXEs.

        Three folders deep, not two: an Unreal game's real binary lives at
        <Project>/Binaries/Win64/<Project>-Win64-Shipping.exe, and a two-level
        scan only ever found the small shim at the root. Folders that hold
        executables which are never the game are skipped outright.
        """
        results = []
        base = self.current_game_path
        if not base or not os.path.isdir(base):
            return results
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = os.path.relpath(dirpath, base)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth >= 3:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d.lower() not in self.NON_GAME_DIRS]
            for filename in filenames:
                low = filename.lower()
                if not low.endswith('.exe'):
                    continue
                if low in self.HELPER_EXE_NAMES:
                    continue
                if 'browsersubprocess' in low or low.startswith(('cefsharp', 'unitycrashhandler', 'vcredist', 'unins')):
                    continue
                rel_path = filename if rel_dir == "." else os.path.join(rel_dir, filename)
                results.append(rel_path.replace("\\", "/"))
        return results

    def configure_game_exes(self):
        """Dialog to pick which game EXEs appear in the disc menu (multi-game discs)."""
        if not self.current_game_path:
            self.show_centered_popup("Select Game Folder", "Browse to your game folder first, then configure the games on the disc.")
            return

        discovered = self.discover_game_exes()
        configured = {g.get("exe", "").replace("\\", "/"): g.get("name", "") for g in self.game_executables}
        # Keep configured entries even if the scan missed them
        all_exes = list(dict.fromkeys(list(configured.keys()) + discovered))
        all_exes = [e for e in all_exes if e]

        theme = self.current_theme()
        dialog, body = self.themed_dialog(
            "Games on Disc",
            "One disc, as many games as you like",
            width=680, height=560)

        # Packed first, against the bottom, so a long list of executables cannot
        # push Save off the window.
        button_row = tk.Frame(body, bg=theme["bg"])
        button_row.pack(side="bottom", fill="x", padx=12, pady=(4, 12))

        tk.Label(body, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w",
                 text=("Double-click a row to put that game on the disc. Pick two or more and players\n"
                       "get a 'choose your game' screen. Leave everything unchecked and Rialto finds\n"
                       "the game by itself, which is what a normal single-game disc wants."),
                 font=("Segoe UI", 10)).pack(fill="x", padx=12, pady=(10, 6))

        self.style_treeview(theme)
        columns = ("include", "name", "exe")
        tree = ttk.Treeview(body, columns=columns, show="headings", height=10,
                            style="Rialto.Treeview")
        tree.heading("include", text="On Disc?")
        tree.heading("name", text="Menu Label (double-click ✔ to toggle)")
        tree.heading("exe", text="Executable")
        tree.column("include", width=70, anchor="center")
        tree.column("name", width=220)
        tree.column("exe", width=280)
        tree.pack(fill="both", expand=True, padx=12, pady=4)

        row_state = {}
        for exe in all_exes:
            included = exe in configured
            name = configured.get(exe) or os.path.splitext(os.path.basename(exe))[0]
            item = tree.insert("", "end", values=("✔" if included else "", name, exe))
            row_state[item] = included

        def toggle(event=None):
            item = tree.focus()
            if not item:
                return
            row_state[item] = not row_state[item]
            values = list(tree.item(item, "values"))
            values[0] = "✔" if row_state[item] else ""
            tree.item(item, values=values)

        tree.bind("<Double-1>", toggle)
        tree.bind("<space>", toggle)

        # Rename selected entry
        rename_row = tk.Frame(body, bg=theme["bg"])
        rename_row.pack(fill="x", padx=12, pady=4)
        tk.Label(rename_row, text="Menu label:", bg=theme["bg"], fg=theme["fg"]).pack(side="left")
        rename_var = tk.StringVar()
        rename_entry = ttk.Entry(rename_row, textvariable=rename_var)
        rename_entry.pack(side="left", fill="x", expand=True, padx=6)

        def load_selected_name(event=None):
            item = tree.focus()
            if item:
                rename_var.set(tree.item(item, "values")[1])

        def apply_name():
            item = tree.focus()
            if item and rename_var.get().strip():
                values = list(tree.item(item, "values"))
                values[1] = rename_var.get().strip()
                tree.item(item, values=values)

        tree.bind("<<TreeviewSelect>>", load_selected_name)
        ttk.Button(rename_row, text="Apply", command=apply_name, style="Rounded.TButton").pack(side="left")

        def save_and_close():
            games = []
            for item in tree.get_children():
                if row_state.get(item):
                    _include, name, exe = tree.item(item, "values")
                    games.append({"name": name, "exe": exe})
            self.game_executables = games
            self.refresh_game_exes_summary()
            if games:
                self.update_status(f"🎮 Games on Disc: {len(games)} configured")
            else:
                self.update_status("🎮 Games on Disc: auto-detect (single game)")
            dialog.destroy()

        def clear_and_close():
            self.game_executables = []
            self.refresh_game_exes_summary()
            self.update_status("🎮 Games on Disc: auto-detect (single game)")
            dialog.destroy()

        ttk.Button(button_row, text="Save", command=save_and_close, style="Primary.TButton").pack(side="right", padx=4)
        ttk.Button(button_row, text="Use Auto-Detect", command=clear_and_close, style="Rounded.TButton").pack(side="right", padx=4)
        ttk.Button(button_row, text="Cancel", command=dialog.destroy, style="Rounded.TButton").pack(side="right", padx=4)

    # === Rialto 1.5: disc extras (bonus, mods, Steam button, Mac and Linux) ===

    def style_treeview(self, theme):
        """Make ttk's Treeview follow the theme instead of staying Windows-white."""
        style = ttk.Style()
        style.configure("Rialto.Treeview",
                        background=theme["entry_bg"],
                        fieldbackground=theme["entry_bg"],
                        foreground=theme["fg"],
                        borderwidth=0,
                        rowheight=24)
        style.map("Rialto.Treeview",
                  background=[("selected", theme["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.configure("Rialto.Treeview.Heading",
                        background=theme["header_bg"],
                        foreground=theme["fg"],
                        relief="flat",
                        font=("Segoe UI", 9, "bold"))
        style.map("Rialto.Treeview.Heading",
                  background=[("active", theme["button_active"])])

    def default_bonus_dir(self):
        """input\\<Game>\\bonus for the chosen game, whether or not it exists yet."""
        if not self.current_game_path:
            return ""
        return os.path.join(self.current_game_path, "bonus")

    def resolved_bonus_dir(self):
        """The bonus folder this build should use, or "" for none.

        An explicit pick from Disc Extras wins. Failing that, a bonus/ folder
        sitting inside the game folder is used exactly as it always has been,
        so discs built before the button existed keep building the same way.
        """
        chosen = self.bonus_folder_var.get().strip()
        if chosen and os.path.isdir(chosen):
            return chosen
        default = self.default_bonus_dir()
        return default if default and os.path.isdir(default) else ""

    def configure_disc_extras(self):
        """Everything a disc can carry beyond the game: bonus, mods, Steam, Mac, Linux."""
        theme = self.current_theme()
        dialog, body = self.themed_dialog(
            "Disc Extras",
            "Everything the disc can carry besides the game itself",
            width=680, height=990)

        # Packed first, against the bottom, so Done keeps its space no matter
        # how tall the sections below turn out to be.
        button_row = tk.Frame(body, bg=theme["bg"])
        button_row.pack(side="bottom", fill="x", padx=14, pady=12)
        ttk.Button(button_row, text="Done", command=dialog.destroy,
                   style="Primary.TButton").pack(side="right")

        tk.Label(body, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w",
                 font=("Segoe UI", 10), wraplength=620,
                 text=("All of this is optional. Leave it alone and your disc still builds "
                       "exactly as it would have.")).pack(fill="x", padx=14, pady=(12, 6))

        def section(title):
            tk.Frame(body, bg=theme["button_bg"], height=1).pack(fill="x", padx=14, pady=(10, 0))
            tk.Label(body, text=title, bg=theme["bg"], fg=theme["fg"], anchor="w",
                     font=("Segoe UI", 10, "bold")).pack(fill="x", padx=14, pady=(8, 2))

        def path_row(parent, label, var, tip, browse_command):
            row = tk.Frame(parent, bg=theme["bg"])
            row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=label, bg=theme["bg"], fg=theme["fg"],
                     width=16, anchor="w").pack(side="left")
            entry = ttk.Entry(row, textvariable=var)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ttk.Button(row, text="Browse", command=browse_command,
                       style="Rounded.TButton").pack(side="left")
            ToolTip(entry, tip)
            return row

        def pick_dir(var, title, on_done=None):
            def handler():
                start = self.current_game_path or INPUT_DIR
                path = filedialog.askdirectory(title=title, initialdir=start)
                if path:
                    var.set(path)
                    if on_done:
                        on_done()
                    self.refresh_disc_meter()
            return handler

        # --- Bonus content ---
        section("Bonus content")
        tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=620,
                 text=("Soundtracks, art, wallpapers, the design doc, anything at all. It gets a "
                       "BONUS button on the disc menu that opens the folder.")
                 ).pack(fill="x", padx=14, pady=(0, 4))

        bonus_row = path_row(body, "Bonus folder:", self.bonus_folder_var,
                             "The folder whose contents become the disc's bonus material. "
                             "Leave it empty and Rialto uses a bonus folder inside your game "
                             "folder if there is one.",
                             pick_dir(self.bonus_folder_var, "Pick your bonus content folder"))

        bonus_note = tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                              anchor="w", font=("Segoe UI", 9), wraplength=620)
        bonus_note.pack(fill="x", padx=14, pady=(2, 0))

        def refresh_bonus_note():
            resolved = self.resolved_bonus_dir()
            if not self.current_game_path:
                bonus_note.configure(text="Choose a game folder first and Rialto can make one for you.")
            elif resolved:
                count = 0
                for _root, _dirs, files in os.walk(resolved):
                    count += len(files)
                bonus_note.configure(text="Using %s (%d files)." % (resolved, count))
            else:
                bonus_note.configure(text="No bonus content yet. Create Bonus Folder makes one and opens it.")

        def create_bonus_folder():
            if not self.current_game_path:
                self.show_centered_popup("Pick your game first",
                                         "Choose your game folder, then Rialto can make the bonus "
                                         "folder in the right place.")
                return
            target = self.default_bonus_dir()
            try:
                os.makedirs(target, exist_ok=True)
                self.bonus_folder_var.set(target)
                os.startfile(target)
                self.update_status("🎁 Bonus folder ready: %s" % target)
            except OSError as e:
                self.update_status("⚠️ Could not create the bonus folder: %s" % e)
            refresh_bonus_note()
            self.refresh_disc_meter()

        bonus_buttons = tk.Frame(body, bg=theme["bg"])
        bonus_buttons.pack(fill="x", padx=14, pady=(6, 0))
        create_btn = self.icon_button(bonus_buttons, "gift", "Create Bonus Folder",
                                      create_bonus_folder, side="left")
        ToolTip(create_btn, "Makes a bonus folder inside your game folder and opens it in Explorer. "
                            "Drop anything in there; whatever is inside ends up on the disc.")
        refresh_bonus_note()

        # --- Mods ---
        section("Mods")
        mods_check = self.themed_check(
            body, "Add a MODS button to the disc menu", self.mod_launcher_var,
            command=self.save_signing_settings, anchor="w", padx=14, pady=2)
        ToolTip(mods_check, "Puts your mods folder on the disc and adds a MODS button to the menu "
                            "that runs the tool inside it. Works from the disc and after installing.")
        tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=620,
                 text=("Point at the folder holding your mod manager or loader. Rialto finds the "
                       ".exe inside it on its own. Leave it empty and a folder called mods inside "
                       "your game folder is used.")
                 ).pack(fill="x", padx=14, pady=(0, 2))

        mods_row = path_row(body, "Mod folder:", self.mod_folder_var,
                            "The folder your mod tool lives in - it does not have to be called "
                            "mods. A folder already inside your game folder is used where it is, "
                            "not copied twice.",
                            pick_dir(self.mod_folder_var, "Pick the folder holding your mod tool"))

        mods_note = tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                             anchor="w", font=("Segoe UI", 9), wraplength=620)
        mods_note.pack(fill="x", padx=14, pady=(2, 0))

        def refresh_mods_note(*_args):
            """Say whether a mod tool will actually be found, before the build.

            A disc shipped with the MODS button switched on and no tool behind
            it, and the only warning was one line in the log.
            """
            if not self.mod_launcher_var.get():
                mods_note.configure(text="Off. The disc menu shows no MODS button.")
                return
            resolved = self.resolved_mod_dir()
            if not resolved:
                mods_note.configure(
                    text="No mod folder found yet, so the MODS button will not appear.")
                return
            found = ""
            for root, _dirs, files in os.walk(resolved):
                for name in sorted(files):
                    if name.lower().endswith(".exe"):
                        found = os.path.join(root, name)
                        break
                if found:
                    break
            if found:
                mods_note.configure(text="MODS will run: %s" % os.path.basename(found))
            else:
                mods_note.configure(
                    text="No .exe inside %s, so the MODS button will not appear."
                         % os.path.basename(os.path.normpath(resolved)))

        mods_check.configure(command=lambda: (self.save_signing_settings(), refresh_mods_note()))
        refresh_mods_note()
        mods_trace = self.mod_folder_var.trace_add("write", refresh_mods_note)

        def drop_mods_trace(event):
            if event.widget is dialog:
                try:
                    self.mod_folder_var.trace_remove("write", mods_trace)
                except (tk.TclError, ValueError):
                    pass

        dialog.bind("<Destroy>", drop_mods_trace, add="+")

        def open_mods_folder():
            if not self.current_game_path:
                self.show_centered_popup("Pick your game first",
                                         "Choose your game folder, then Rialto can make the mods "
                                         "folder in the right place.")
                return
            target = os.path.join(self.current_game_path, "mods")
            try:
                os.makedirs(target, exist_ok=True)
                os.startfile(target)
                self.update_status("🧩 Mods folder ready: %s" % target)
            except OSError as e:
                self.update_status("⚠️ Could not create the mods folder: %s" % e)

        mods_buttons = tk.Frame(body, bg=theme["bg"])
        mods_buttons.pack(fill="x", padx=14, pady=(4, 0))
        mods_btn = self.icon_button(mods_buttons, "mods", "Create Mods Folder",
                                    open_mods_folder, side="left")
        ToolTip(mods_btn, "Makes a mods folder inside your game folder and opens it in Explorer.")

        # --- Compatibility mode ---
        section("Compatibility mode")
        compat_check = self.themed_check(
            body, "Add a compatibility button to the disc menu", self.compat_mode_var,
            anchor="w", padx=14, pady=2)
        ToolTip(compat_check, "Puts a second play button on the menu that starts your game with a "
                              "launch argument already set, so a player on older hardware does not "
                              "have to type one.")
        tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=620,
                 text=("For a game that can fall back to older graphics - OpenGL instead of Vulkan, "
                       "windowed instead of fullscreen - if it already reads a launch argument.")
                 ).pack(fill="x", padx=14, pady=(0, 2))

        compat_row = tk.Frame(body, bg=theme["bg"])
        compat_row.pack(fill="x", padx=14, pady=3)
        tk.Label(compat_row, text="Launch argument:", bg=theme["bg"], fg=theme["fg"],
                 width=16, anchor="w").pack(side="left")
        compat_entry = ttk.Entry(compat_row, textvariable=self.compat_args_var)
        compat_entry.pack(side="left", fill="x", expand=True)
        ToolTip(compat_entry, "Exactly what you would type after the .exe, such as -opengl. Spaces "
                              "separate two arguments; put quotes around one that contains a space.")

        hint_row = tk.Frame(body, bg=theme["bg"])
        hint_row.pack(fill="x", padx=14, pady=3)
        tk.Label(hint_row, text="What it does:", bg=theme["bg"], fg=theme["fg"],
                 width=16, anchor="w").pack(side="left")
        hint_entry = ttk.Entry(hint_row, textvariable=self.compat_hint_var)
        hint_entry.pack(side="left", fill="x", expand=True)
        ToolTip(hint_entry, "One sentence, shown to the player when they hover the button. "
                            "Say what changes, in their words: \"Runs the game on OpenGL "
                            "instead of Vulkan, for older graphics cards.\" Leave it empty "
                            "and the menu explains it in general terms, in their language.")

        compat_note = tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                               anchor="w", font=("Segoe UI", 9), wraplength=620)
        compat_note.pack(fill="x", padx=14, pady=(2, 0))

        def refresh_compat_note(*_args):
            """Show what the player's button will actually pass to the game.

            The argument line is split here exactly the way the build splits
            it, so a quoting mistake shows up in this window rather than on a
            finished disc.
            """
            if not self.compat_mode_var.get():
                compat_note.configure(text="Off. The menu shows the usual PLAY button and nothing else.")
                return
            parts = split_launch_args(self.compat_args_var.get())
            if not parts:
                compat_note.configure(
                    text="No argument yet, so the button stays hidden until there is one.")
                return
            compat_note.configure(
                text="The button starts your game with: %s" % " ".join(parts))

        compat_check.configure(command=refresh_compat_note)
        refresh_compat_note()

        # The trace lives on a variable that outlives this window, so it has to
        # come off when the window goes. Left behind, the next edit to the
        # argument line would call configure() on a destroyed label.
        compat_trace = self.compat_args_var.trace_add("write", refresh_compat_note)

        def drop_compat_trace(event):
            if event.widget is dialog:
                try:
                    self.compat_args_var.trace_remove("write", compat_trace)
                except (tk.TclError, ValueError):
                    pass

        dialog.bind("<Destroy>", drop_compat_trace, add="+")

        # --- Steam ---
        section("Steam")
        steam_check = self.themed_check(
            body, "Show an ADD TO STEAM button after install", self.steam_button_var,
            anchor="w", padx=14, pady=2)
        ToolTip(steam_check, "After players install from your disc, the menu offers one click to put "
                             "the game in their Steam library as a non-Steam game. Steam has to be "
                             "closed first, and the menu tells them so.")
        tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=620,
                 text=("Nothing is uploaded and nothing is sold through Steam - it only makes a "
                       "shortcut in the player's own library, so the game they bought on a disc "
                       "sits beside the rest of what they play.")
                 ).pack(fill="x", padx=14, pady=(0, 2))

        # --- Mac and Linux ---
        # The explainer sits above the boxes here, not below them, because the
        # thing worth knowing is what Rialto does to a build folder - and an
        # author who reads that first stops hunting for a .dmg they do not need
        # to make.
        section("Mac and Linux on the same disc (only if you built them)")
        tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=620,
                 text=("Point at a plain build folder - the one you would have zipped up yourself "
                       "- and Rialto packs it so the game comes off the disc ready to run. No "
                       "Terminal, nothing to type. The disc's README then spells out the real "
                       "steps for all three - run setup.exe, or open the Mac or Linux folder and "
                       "what to do once you are in it - so nobody has to open a second file to "
                       "find out which buttons to press.")
                 ).pack(fill="x", padx=14, pady=(0, 4))

        unix_notes = {}
        for unix_var, unix_label, unix_tip in (
                (self.mac_build_var, "Mac",
                 "Your game's Mac build. A plain folder is fine - Rialto packs it into an "
                 "archive that carries Mac file permissions, so the app opens with a "
                 "double-click. Already made a .dmg or a .zip? Point at the folder holding "
                 "it and Rialto ships it exactly as it is."),
                (self.linux_build_var, "Linux",
                 "Your game's Linux build. A plain folder is fine - Rialto packs it into an "
                 "archive that carries the executable bit, so the game runs straight out of "
                 "it with no chmod and no Terminal. Already made an .AppImage or a .tar.gz? "
                 "Point at the folder holding it and Rialto ships it exactly as it is.")):
            path_row(body, "%s build:" % unix_label, unix_var, unix_tip,
                     pick_dir(unix_var, "Pick your %s build folder" % unix_label))
            unix_note = tk.Label(body, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                                 anchor="w", font=("Segoe UI", 9), wraplength=620)
            unix_note.pack(fill="x", padx=14, pady=(0, 2))
            unix_notes[unix_label] = (unix_var, unix_note)

        def refresh_unix_notes(*_args):
            """Say what each build will become, before the disc is burnt.

            This is the one extra where Rialto does invisible work - repacking
            a folder so the executable bit survives a read-only disc - so it
            has to say out loud which of the two routes a folder is taking.
            """
            for note_label, (note_var, note) in unix_notes.items():
                path = note_var.get().strip()
                if not path:
                    note.configure(text="No %s build set. Leave it empty if you did not make "
                                        "one." % note_label)
                elif not os.path.isdir(path):
                    note.configure(text="Rialto cannot find that folder, so the %s build would "
                                        "be skipped." % note_label)
                elif self.folder_is_already_packaged(path):
                    note.configure(text="Your %s archive ships exactly as it is, with a Read Me "
                                        "First beside it." % note_label)
                else:
                    note.configure(text="Rialto packs this into an archive that opens ready to "
                                        "run - your %s players never touch a Terminal."
                                        % note_label)

        refresh_unix_notes()
        unix_traces = [(var, var.trace_add("write", refresh_unix_notes))
                       for var, _note in unix_notes.values()]

        def drop_unix_traces(event):
            if event.widget is dialog:
                for traced_var, handle in unix_traces:
                    try:
                        traced_var.trace_remove("write", handle)
                    except (tk.TclError, ValueError):
                        pass

        dialog.bind("<Destroy>", drop_unix_traces, add="+")

    # Files that have to come out of the archive runnable. Anything starting
    # with the ELF magic is a Linux executable whatever it is called, which is
    # the only rule that holds for every engine.
    UNIX_EXEC_SUFFIXES = ('.x86_64', '.x86', '.appimage', '.sh', '.run', '.bin')
    UNIX_ARCHIVE_SUFFIXES = ('.tar.gz', '.tgz', '.tar.xz', '.zip', '.dmg', '.appimage')

    def _is_unix_executable(self, path, name):
        if name.lower().endswith(self.UNIX_EXEC_SUFFIXES):
            return True
        try:
            with open(path, 'rb') as f:
                return f.read(4) == b'\x7fELF'
        except OSError:
            return False

    # Ordered best guess at "the file the player is meant to double-click".
    UNIX_LAUNCH_PRIORITY = ('.appimage', '.x86_64', '.x86', '.sh', '.run', '.bin')

    def _unix_launch_target(self, folder):
        """The file a start.sh should run, relative to `folder`, or "".

        Shallowest wins. Engines put the launcher at the root of a build and
        their own helper binaries down inside the data folders, so a deep
        match is nearly always the wrong one.
        """
        best = None
        for dirpath, _dirs, files in os.walk(folder):
            for name in sorted(files):
                lower = name.lower()
                if lower == "start.sh":
                    continue
                if lower.endswith(".so") or ".so." in lower:
                    continue        # a library is loaded, never launched
                full = os.path.join(dirpath, name)
                if lower.endswith(self.UNIX_LAUNCH_PRIORITY):
                    rank = min(i for i, suffix in enumerate(self.UNIX_LAUNCH_PRIORITY)
                               if lower.endswith(suffix))
                elif self._is_unix_executable(full, name):
                    rank = len(self.UNIX_LAUNCH_PRIORITY)
                else:
                    continue
                rel = os.path.relpath(full, folder).replace(os.sep, "/")
                # Whatever the shell script wraps has to be a plain name.
                # A quote, a backtick or a newline in a filename would
                # break straight out of it, so only the safe set is taken.
                if not all(c.isalnum() or c in " ._-/" for c in rel):
                    continue
                key = (rel.count("/"), rank, rel.lower())
                if best is None or key < best[0]:
                    best = (key, rel)
        return best[1] if best else ""

    def unix_launcher_script(self, target):
        """A start.sh that runs `target` from wherever the folder ends up."""
        return "\n".join([
            "#!/bin/sh",
            "# Written by Rialto. Try double-clicking the game first - this is",
            "# here for when the file manager will not launch it.",
            'cd "$(dirname "$0")" || exit 1',
            'GAME="%s"' % target,
            'chmod +x "$GAME" 2>/dev/null',
            'exec "./$GAME" "$@"',
            "",
        ])

    def write_unix_launcher(self, folder, label):
        """Drop a start.sh beside a Linux build. Returns what it runs, or "".

        Only Linux gets one. A Mac app is opened from Finder and a shell
        script sitting next to it would only be one more thing to explain.
        """
        if label != "Linux":
            return ""
        target = self._unix_launch_target(folder)
        if not target:
            return ""
        try:
            with open(os.path.join(folder, "start.sh"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(self.unix_launcher_script(target))
        except OSError as e:
            self.update_status(f"⚠️ Could not write the Linux start.sh: {e}")
            return ""
        return target

    def folder_bytes(self, folder):
        """Total size of everything under `folder`, in bytes."""
        total = 0
        for dirpath, _dirs, files in os.walk(folder):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    pass
        return total

    def folder_is_already_packaged(self, folder):
        """True when the author already supplied archives rather than a raw tree."""
        try:
            entries = [n for n in os.listdir(folder) if not n.startswith('.')]
        except OSError:
            return False
        if not entries:
            return False
        return all(os.path.isfile(os.path.join(folder, n))
                   and n.lower().endswith(self.UNIX_ARCHIVE_SUFFIXES)
                   for n in entries)

    def package_unix_build(self, source, dest_folder, label, launcher=""):
        """Pack a raw Mac/Linux tree into a .tar.gz that keeps its permissions.

        This is what saves the player from a terminal. A disc cannot carry an
        executable bit, but a tar archive carries the mode of every file inside
        it - so the game comes out of the archive already runnable and the
        whole business becomes: double-click the archive, extract, double-click
        the game. Nothing typed, nothing chmod-ed.

        Compressing also tends to halve a Linux build, which the disc notices.

        Returns the archive's filename, or "" if it could not be written.
        """
        import io
        import tarfile

        title = (self.entries["Title"].get().strip() if "Title" in self.entries else "")
        stem = sanitize_text(title).strip() or "Game"
        stem = "".join(c for c in stem if c.isalnum() or c in " -_").strip() or "Game"
        archive_name = f"{stem}-{label}.tar.gz"
        archive_path = os.path.join(dest_folder, archive_name)
        root_name = f"{stem}-{label}"

        def add_filter(info):
            # Directories and anything executable get the bits that make the
            # extracted copy usable; everything else stays plain readable.
            if info.isdir():
                info.mode = 0o755
            else:
                info.mode = 0o755 if info.name in executables else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            return info

        executables = set()
        for dirpath, _dirs, files in os.walk(source):
            for name in files:
                full = os.path.join(dirpath, name)
                if self._is_unix_executable(full, name):
                    rel = os.path.relpath(full, source).replace(os.sep, "/")
                    executables.add(f"{root_name}/{rel}")

        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(source, arcname=root_name, filter=add_filter)
                if launcher:
                    # Synthesised rather than written into the author's own
                    # build folder, which is theirs and stays untouched.
                    script = self.unix_launcher_script(launcher).encode("utf-8")
                    info = tarfile.TarInfo("%s/start.sh" % root_name)
                    info.size = len(script)
                    info.mode = 0o755
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    tar.addfile(info, io.BytesIO(script))
        except (OSError, tarfile.TarError) as e:
            self.update_status(f"⚠️ Could not package the {label} build: {e}")
            return ""
        return archive_name

    def write_unix_instructions(self, folder, label, archive="", launcher=""):
        """Put a START HERE inside the Mac or Linux folder, matching what is there.

        Two different sets of steps, because there are two different situations.
        With an archive the player never opens a terminal: the executable bit
        travels inside the tar, so extracting is enough. Without one they are
        back to chmod, which is why the archive is the default.

        `launcher` is what a start.sh next to the build runs. It is only
        mentioned when one was actually written - pointing a player at a file
        that is not there is worse than saying nothing.

        Mac and Linux get the same amount of hand-holding on purpose. An author
        who ships both should not find one platform walked through the door and
        the other left on the step.
        """
        game = (self.entries["Title"].get().strip() if "Title" in self.entries else "") or "the game"
        try:
            if label == "Linux":
                if archive:
                    text = [
                        "%s on Linux" % game,
                        "",
                        "  1. Copy %s off this disc." % archive,
                        "  2. Double-click it and extract it (or: tar -xzf %s)." % archive,
                        "  3. Open the folder it makes and double-click the game.",
                        "",
                        "That is all. The archive keeps the file permissions a disc",
                        "cannot, so the game comes out ready to run - nothing to chmod",
                        "and nothing to type.",
                        "",
                    ]
                    if launcher:
                        text += [
                            "If your file manager will not launch it, open a terminal",
                            "in that folder and run:  bash start.sh",
                            "",
                        ]
                    text = "\n".join(text)
                else:
                    binary = launcher
                    if not binary:
                        for name in sorted(os.listdir(folder)):
                            if name.lower().endswith((".x86_64", ".appimage", ".sh", ".run")):
                                binary = name
                                break
                    target = binary or "the game file"
                    steps = ["  1. Copy this whole Linux folder into your home directory.",
                             "  2. Open a terminal in the copy."]
                    if launcher:
                        steps.append("  3. Run:   bash start.sh")
                        by_hand = ["", "Or by hand:", "",
                                   "  chmod +x %s" % target, "  ./%s" % target]
                    else:
                        steps.append("  3. Run:   chmod +x %s" % target)
                        steps.append("  4. Then:  ./%s" % target)
                        by_hand = []
                    text = "\n".join([
                        "%s on Linux" % game,
                        "",
                        "A disc cannot carry Linux file permissions, so copy this",
                        "folder off the disc before running anything.",
                        "",
                    ] + steps + by_hand + [
                        "",
                        "Running from the mounted disc will not work: it is read-only,",
                        "so the executable bit cannot be set there.",
                        "",
                    ])
            else:
                if archive:
                    text = "\n".join([
                        "%s on Mac" % game,
                        "",
                        "  1. Copy %s off this disc." % archive,
                        "  2. Double-click it to unpack it.",
                        "  3. Drag the app inside to your Applications folder, then open it.",
                        "",
                        "That is all. The archive keeps the file permissions a disc",
                        "cannot, so the app comes out ready to open - nothing to type.",
                        "",
                        "The first time you open it, macOS may say it is from an",
                        "unidentified developer, because it came from a disc rather",
                        "than the App Store. Right-click the app, choose Open, then",
                        "confirm. You only have to do that once.",
                        "",
                    ])
                else:
                    text = "\n".join([
                        "%s on Mac" % game,
                        "",
                        "  1. Copy this whole Mac folder somewhere on your Mac.",
                        "  2. Open the .dmg or .zip inside it.",
                        "  3. Drag the app to your Applications folder, then open it.",
                        "",
                        "Copy it off the disc first. A disc is read-only, and an app",
                        "run straight from one cannot always write the files it needs",
                        "on its first launch.",
                        "",
                        "The first time you open it, macOS may say it is from an",
                        "unidentified developer, because it came from a disc rather",
                        "than the App Store. Right-click the app, choose Open, then",
                        "confirm. You only have to do that once.",
                        "",
                    ])

            with open(os.path.join(folder, "START HERE.txt"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(text)
        except OSError as e:
            self.update_status(f"⚠️ Could not write the {label} instructions: {e}")


    def unix_readme_steps(self, label, primary):
        """The two or three things a Mac or Linux player actually does.

        These go in the disc's own README, beside the Windows line, because
        "open the Mac folder and read START HERE.txt" is not an instruction,
        it is an errand. A player should not have to open a second file to
        find out which buttons to press.

        `primary` is the one file they touch - the archive Rialto packed, or
        the .dmg or .AppImage the author supplied. Empty means the build is
        loose in the folder and the whole folder gets copied instead.
        """
        import textwrap
        if label == "Mac":
            if primary:
                sentence = ("open the Mac folder, copy %s off the disc, open it, "
                            "and drag the app into Applications." % primary)
            else:
                sentence = ("copy the whole Mac folder off the disc, open the disk image "
                            "inside it, and drag the app into Applications.")
        elif primary.lower().endswith((".tar.gz", ".tgz", ".tar.xz", ".zip")):
            sentence = ("open the Linux folder, copy %s off the disc, extract it, "
                        "and double-click the game." % primary)
        elif primary:
            sentence = ("open the Linux folder, copy %s off the disc, right-click it, "
                        "allow running as a program, and open it." % primary)
        else:
            sentence = ("copy the whole Linux folder off the disc, open a terminal in it, "
                        "and run:  bash start.sh")
        # 13 is the width of "    WINDOWS: ", which every platform lines up under.
        # A long filename is never broken across lines - a player who retypes
        # half of one gets nowhere - so a long enough title can still overhang.
        wrapped = textwrap.wrap(sentence, width=72 - 13, break_long_words=False) or [""]
        return (["    %-8s %s" % (label.upper() + ":", wrapped[0])]
                + [" " * 13 + line for line in wrapped[1:]])

    def stage_universal_builds(self, output_path):
        """Copy Mac and Linux builds into the output so they ride along on the disc."""
        staged = {}
        for var, label in ((self.mac_build_var, "Mac"), (self.linux_build_var, "Linux")):
            path = var.get().strip()
            if not path:
                continue
            if not os.path.isdir(path):
                self.update_status(f"⚠️ {label} build folder not found, skipping: {path}")
                continue
            dest = os.path.join(output_path, label)
            try:
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                if self.folder_is_already_packaged(path):
                    # The author did the packaging themselves. Their archive
                    # carries its own permissions; leave it exactly alone.
                    self.update_status(f"Copying {label} build onto the disc...")
                    shutil.copytree(path, dest)
                    launcher = self.write_unix_launcher(dest, label)
                    self.write_unix_instructions(dest, label, archive="", launcher=launcher)
                    supplied = [n for n in sorted(os.listdir(dest))
                                if n.lower().endswith(self.UNIX_ARCHIVE_SUFFIXES)]
                    primary = supplied[0] if supplied else ""
                else:
                    self.update_status(f"Packaging {label} build so it stays runnable...")
                    os.makedirs(dest, exist_ok=True)
                    # Worked out from the author's folder, then written into the
                    # archive - their own build folder is never touched.
                    launcher = self._unix_launch_target(path) if label == "Linux" else ""
                    archive = self.package_unix_build(path, dest, label, launcher=launcher)
                    if not archive:
                        # Packing failed; ship the tree so nothing is lost, and
                        # the instructions fall back to the chmod route.
                        shutil.copytree(path, dest, dirs_exist_ok=True)
                        launcher = self.write_unix_launcher(dest, label)
                    self.write_unix_instructions(dest, label, archive=archive,
                                                 launcher=launcher)
                    primary = archive
                    if archive:
                        raw = self.folder_bytes(path)
                        packed = os.path.getsize(os.path.join(dest, archive))
                        self.update_status(
                            "✅ %s build packaged as %s (%.0f MB, from %.0f MB) - it comes "
                            "out of the archive ready to run, no terminal needed"
                            % (label, archive, packed / 1e6, raw / 1e6))
                staged[label] = primary
                self.update_status(f"✅ {label} build added to the disc")
            except Exception as e:
                self.update_status(f"⚠️ Could not add {label} build: {e}")
        if staged:
            # One README, and every platform's real steps in it. A disc that
            # greets a player with three different read-me files, each one
            # pointing at the next, has already failed to tell them anything.
            signpost = ["    WINDOWS: run 'setup.exe', here at the top of the disc, then",
                        "             launch the game from your Start Menu."]
            for label in ("Mac", "Linux"):
                if label in staged:
                    signpost += self.unix_readme_steps(label, staged[label])
            if "Mac" in staged:
                # The one thing that stops a Mac player dead, and it looks like
                # the disc is broken rather than like a setting.
                signpost += ["",
                             "    On a Mac, the first time you open the app, macOS may say it",
                             "    is from an unidentified developer. Right-click it, choose",
                             "    Open, then confirm. Once only."]

            # What generate_readme wrote when it only had Windows to think
            # about. Matched rather than rebuilt, so an edit there that this
            # misses leaves the README intact instead of half-rewritten.
            windows_only = "\n".join([
                "    If the installer doesn't start on its own:",
                "    1. Open this disc in File Explorer.",
                "    2. Run 'setup.exe' to install the game.",
                "    3. Once installed, launch it from your Start Menu.",
            ])

            try:
                readme_path = os.path.join(output_path, "README.txt")
                with open(readme_path, "r", encoding="utf-8") as f:
                    readme = f.read()
                if windows_only in readme:
                    readme = readme.replace(windows_only, "\n".join(signpost))
                else:
                    # Nothing to swap, so put the steps where they will still be
                    # read rather than dropping them.
                    readme = "\n".join(signpost) + "\n\n" + readme
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(readme)
            except OSError as e:
                self.update_status(f"⚠️ Could not add the Mac/Linux notes: {e}")

    # === Rialto 1.5: disc fileset, USB export, multi-disc spanning ===

    def _collect_disc_fileset(self, output_path):
        """The exact set of files that belongs on the disc, existence-checked."""
        items = ["setup.exe", "autorun.inf", "README.txt"]
        for file in sorted(os.listdir(output_path)):
            if file.startswith("setup-") and file.endswith(".bin"):
                items.append(file)
            elif file.lower().endswith(".ico"):
                items.append(file)
        for extra in ("start_menu.bat", "menu.bat", "menu", "Mac", "Linux"):
            items.append(extra)
        # Bonus content: the installed copy already gets it (step 2 copies the
        # game's bonus folder into the output folder and Inno's wildcard sweeps
        # it into {app}), but the disc root only gets what is named here. The
        # trailing existence filter keeps this a no-op for games without one.
        items.append("bonus")
        # Mod launcher: without this the mod folder never reaches the disc root.
        # The name is whatever the author's folder is called, not always "mods".
        if self.mod_launcher_var.get():
            items.append(self.staged_mod_dir_name(output_path) or "mods")
        seen = set()
        existing = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            if os.path.exists(os.path.join(output_path, item)):
                existing.append(item)
        return existing

    def _fileset_size(self, output_path, items):
        total = 0
        for item in items:
            path = os.path.join(output_path, item)
            if os.path.isdir(path):
                for dirpath, _dirs, files in os.walk(path):
                    for f in files:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
            else:
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
        return total

    def _fileset_needs_udf(self, output_path, items):
        """Plain disc format tops out at 4 GB per file; bigger files need UDF."""
        limit = 4 * 1024 * 1024 * 1024 - 1
        for item in items:
            path = os.path.join(output_path, item)
            if os.path.isdir(path):
                for dirpath, _dirs, files in os.walk(path):
                    for f in files:
                        try:
                            if os.path.getsize(os.path.join(dirpath, f)) > limit:
                                return True
                        except OSError:
                            pass
            else:
                try:
                    if os.path.getsize(path) > limit:
                        return True
                except OSError:
                    pass
        return False

    def export_usb_fileset(self, output_path, meta):
        """Copy the finished disc files onto a USB stick or folder of choice."""
        try:
            self.update_status("💾 USB export: pick where to copy the files...")
            dest = filedialog.askdirectory(title="Pick your USB drive (or any folder)")
            if not dest:
                self.update_status("💾 USB export skipped")
                return
            files = self._collect_disc_fileset(output_path)
            for item in files:
                src = os.path.join(output_path, item)
                target = os.path.join(dest, item)
                if os.path.isdir(src):
                    if os.path.exists(target):
                        shutil.rmtree(target)
                    shutil.copytree(src, target)
                else:
                    shutil.copy2(src, target)
            hint_path = os.path.join(dest, "START HERE - double click setup.txt")
            with open(hint_path, "w", encoding="utf-8") as f:
                f.write(
                    f"Thanks for grabbing {meta.get('Title', 'this game')}!\n\n"
                    "USB sticks don't start by themselves like discs do.\n"
                    "Just double-click setup.exe and you're on your way.\n"
                )
            self.update_status(f"✅ USB export done: {len(files)} items copied to {dest}")
        except Exception as e:
            self.update_status(f"❌ USB export failed: {e}")

    def _remove_partial_iso(self, iso_path):
        """Delete a disc image a failed tool left half-written, so nobody burns it."""
        try:
            if os.path.exists(iso_path):
                os.remove(iso_path)
                self.update_status(f"🧹 Removed the unfinished {os.path.basename(iso_path)}")
        except OSError:
            self.update_status(f"⚠️ {os.path.basename(iso_path)} is unfinished; delete it before burning")

    def _build_single_iso(self, output_path, iso_path, items, disc_label, needs_udf):
        """Build one ISO from a list of items. Used by multi-disc sets."""
        mkisofs, oscdimg = find_iso_tools()
        temp_folder = os.path.join(output_path, "temp_span_build")
        try:
            if mkisofs:
                tool = [mkisofs, "-o", iso_path, "-J", "-R", "-V", disc_label]
                if needs_udf:
                    tool += ["-udf", "-iso-level", "3"]
                tool += items
            elif oscdimg:
                if os.path.exists(temp_folder):
                    shutil.rmtree(temp_folder)
                os.makedirs(temp_folder)
                for item in items:
                    src = os.path.join(output_path, item)
                    dst = os.path.join(temp_folder, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                fs_flag = "-u2" if needs_udf else "-j1"
                tool = [oscdimg, "-m", fs_flag, f"-l{disc_label}", temp_folder, iso_path]
            else:
                self.update_status("❌ Multi-disc sets need mkisofs or oscdimg installed")
                return False
            try:
                result = subprocess.run(tool, cwd=output_path, capture_output=True, text=True,
                                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=1800)
            except subprocess.TimeoutExpired:
                self.update_status("❌ Disc image stopped after 30 minutes without finishing")
                self._remove_partial_iso(iso_path)
                return False
            if result.returncode != 0 or not os.path.exists(iso_path):
                error_tail = (result.stderr or result.stdout or "").strip().splitlines()
                self.update_status(f"❌ Disc image failed: {error_tail[-1] if error_tail else 'unknown error'}")
                self._remove_partial_iso(iso_path)
                return False
            return True
        finally:
            if os.path.exists(temp_folder):
                try:
                    shutil.rmtree(temp_folder)
                except Exception:
                    pass

    def create_spanned_isos(self, output_path, meta, disc_label, capacity):
        """Split the build across numbered discs when it can't fit on one."""
        game_name = meta["GameName"]
        all_items = self._collect_disc_fileset(output_path)
        bins = [i for i in all_items if i.startswith("setup-") and i.endswith(".bin")]
        base_items = [i for i in all_items if i not in bins]

        def bin_number(name):
            digits = "".join(ch for ch in name if ch.isdigit())
            return int(digits) if digits else 0
        bins.sort(key=bin_number)

        budget = capacity - self.MEDIA_RESERVE
        base_size = self._fileset_size(output_path, base_items)
        if base_size > budget:
            # Warn, never refuse. The base fileset rides on disc 1 whatever it
            # weighs, so this only means disc 1 will be oversized - the set is
            # still worth building, and the per-disc check further down spells
            # out the real numbers.
            self.update_status("⚠️ The menu, setup and extras alone are bigger than the chosen disc.")
        if not bins:
            self.update_status("❌ The game is too big for one disc but wasn't split into parts.")
            self.update_status("   Rebuild with this Target Media selected so the installer splits itself.")
            return

        # Note for players, included on disc 1
        note_path = os.path.join(output_path, "MULTI-DISC README.txt")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                f"{meta.get('Title', game_name)} comes on more than one disc!\n\n"
                "1. Start with Disc 1. Setup begins like normal.\n"
                "2. When Setup asks for the next file, swap in the next disc\n"
                "   and point it at your disc drive.\n"
                "3. That's it. The game installs once the last disc is read.\n"
            )

        discs = []
        current = base_items + ["MULTI-DISC README.txt"]
        current_size = base_size + os.path.getsize(note_path)
        for bin_file in bins:
            size = os.path.getsize(os.path.join(output_path, bin_file))
            if current and current_size + size > budget:
                discs.append(current)
                current, current_size = [], 0
            current.append(bin_file)
            current_size += size
        if current:
            discs.append(current)

        # Only the setup-*.bin parts are packed to fit; everything else is
        # seeded onto disc 1 as-is. Weigh each finished disc and say so out
        # loud when one overflows - warn only, the set still gets built.
        disc_sizes = [self._fileset_size(output_path, items) for items in discs]
        self.disc_overflow_warnings = oversized_disc_warnings(
            disc_sizes, budget, self.target_media_var.get()
        )
        for line in self.disc_overflow_warnings:
            self.update_status(line)

        self.update_status(f"📀 This build needs {len(discs)} discs. Creating the set...")
        needs_udf = self._fileset_needs_udf(output_path, all_items)
        made = 0
        for number, items in enumerate(discs, start=1):
            iso_path = os.path.join(output_path, f"{game_name} Disc {number}.iso")
            label = f"{disc_label[:13]} D{number}"
            self.update_status(f"🔄 Creating Disc {number} of {len(discs)}...")
            if self._build_single_iso(output_path, iso_path, items, label, needs_udf):
                size_mb = os.path.getsize(iso_path) / (1024 * 1024)
                self.update_status(f"✅ Disc {number}: {os.path.basename(iso_path)} ({size_mb:.0f} MB)")
                made += 1
        if made == len(discs):
            self.update_status(f"✅ Multi-disc set complete: {made} ISOs ready to burn")
            self.refresh_windows_icon_cache()
        else:
            self.update_status(f"⚠️ Only {made} of {len(discs)} discs were created")

    # === Rialto 1.5: GOG import ===

    def _ensure_innoextract(self):
        """Find innoextract, offering a one-time automatic download if missing."""
        found = shutil.which("innoextract")
        if found:
            return found
        # Beside Rialto itself: a frozen Rialto.exe unpacks to a temp folder
        # that is deleted on exit, so __file__ would mean a download every session.
        cached = os.path.join(APP_ROOT, "tools", "innoextract", "innoextract.exe")
        if os.path.exists(cached):
            return cached
        want = messagebox.askyesno(
            "One small helper needed",
            "Unpacking GOG installers uses a free open-source tool called innoextract.\n\n"
            "Download it now automatically? (about 2 MB, one time only)"
        )
        if not want:
            self.update_status("ℹ️ GOG import needs innoextract: https://constexpr.org/innoextract/")
            return None
        try:
            self.update_status("⬇️ Downloading innoextract (one time)...")
            import zipfile
            cache_dir = os.path.dirname(cached)
            os.makedirs(cache_dir, exist_ok=True)
            zip_path = os.path.join(cache_dir, "innoextract.zip")
            # The download is an executable that then gets run, and TLS to a
            # one-maintainer site was the only thing vouching for it. The hash
            # is of the 1.9 Windows zip as published, taken on 2026-08-14; it
            # pins that exact file, so a substituted or truncated download
            # stops in fetch_to_file instead of being unpacked and executed.
            from update.fetch import FetchProblem, fetch_to_file
            try:
                fetch_to_file(INNOEXTRACT_URL, zip_path, hosts={"constexpr.org"},
                              cap=16 * 1024 * 1024, sha256=INNOEXTRACT_SHA256)
            except FetchProblem as problem:
                self.update_status(
                    "❌ innoextract: " + str(problem) + " Install it yourself from "
                    "https://constexpr.org/innoextract/ if you need GOG import.")
                return None
            with zipfile.ZipFile(zip_path) as archive:
                from trusted_signing import safe_extract_all
                safe_extract_all(archive, cache_dir, status=self.update_status)
            os.remove(zip_path)
            if os.path.exists(cached):
                self.update_status("✅ innoextract ready")
                return cached
            for dirpath, _dirs, files in os.walk(cache_dir):
                for f in files:
                    if f.lower() == "innoextract.exe":
                        return os.path.join(dirpath, f)
            self.update_status("❌ Download finished but innoextract.exe wasn't inside")
            return None
        except Exception as e:
            self.update_status(f"❌ Could not download innoextract: {e}")
            return None

    def import_gog_installer(self):
        """Unpack a GOG offline installer into a ready-to-build game folder."""
        import re
        installer = filedialog.askopenfilename(
            title="Pick your GOG offline installer",
            filetypes=[("GOG installer", "*.exe"), ("All files", "*.*")])
        if not installer:
            return
        innoextract = self._ensure_innoextract()
        if not innoextract:
            return

        base = os.path.splitext(os.path.basename(installer))[0]
        base = re.sub(r"^setup[_ ]*", "", base, flags=re.IGNORECASE)
        # Drop trailing version/build junk: 1.6.15, (64bit), (78474), v2, gog
        words = base.split("_")
        junk = re.compile(r"^(?:[\d.\-]+|\(.*\)|v[\d.]+|\d*bit|gog)$", re.IGNORECASE)
        while len(words) > 1 and junk.match(words[-1].strip()):
            words.pop()
        pretty = " ".join(words).replace("_", " ").strip().title() or "Imported Game"
        folder_name = "".join(ch for ch in pretty if ch.isalnum()) or "ImportedGame"
        dest = safe(os.path.join(INPUT_DIR, folder_name))

        self.update_status(f"📦 Unpacking {os.path.basename(installer)}...")
        self.update_status("   Big games take a few minutes. Rialto will tell you when it's done.")
        self.root.update()
        try:
            os.makedirs(dest, exist_ok=True)
            result = subprocess.run(
                [innoextract, "--extract", "--exclude-temp", "--output-dir", dest, installer],
                capture_output=True, text=True, timeout=3600,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip().splitlines()
                self.update_status(f"❌ Unpack failed: {tail[-1] if tail else 'unknown error'}")
                return
            # GOG installers keep the game inside an 'app' folder; lift it out
            app_dir = os.path.join(dest, "app")
            if os.path.isdir(app_dir):
                for item in os.listdir(app_dir):
                    shutil.move(os.path.join(app_dir, item), os.path.join(dest, item))
                os.rmdir(app_dir)
            self.current_game_path = dest
            if hasattr(self, "game_path_var"):
                self.game_path_var.set(dest)
            self.refresh_disc_meter()
            title_entry = self.entries.get("Title")
            if title_entry is not None and not title_entry.get().strip():
                title_entry.insert(0, pretty)
            self.update_status(f"✅ {pretty} unpacked into input/{folder_name}")
            self.update_status("   Add your art and icons above, then Preview and Build!")
        except subprocess.TimeoutExpired:
            self.update_status("❌ Unpacking took over an hour and was stopped")
        except Exception as e:
            self.update_status(f"❌ GOG import failed: {e}")

    # === Rialto 1.5: MSIX export ===

    def export_msix(self):
        """Package the selected game as a modern .msix installer."""
        import msix_export
        import trusted_signing

        if not self.current_game_path:
            self.show_centered_popup("Pick a game first", "Browse to your game folder, then export the .msix.")
            return
        title = self.entries["Title"].get().strip() or os.path.basename(self.current_game_path)
        games = self.validated_game_executables()
        if games:
            exe_rel = games[0]["exe"]
        else:
            discovered = self.discover_game_exes()
            if not discovered:
                self.show_centered_popup("No game exe found", "Rialto couldn't find your game's exe. Set it under Games on Disc, then try again.")
                return
            exe_rel = discovered[0]

        config = trusted_signing.load_config()
        theme = self.dark_theme if self.theme_mode.get() == "dark" else self.light_theme
        dialog = tk.Toplevel(self.root)
        dialog.title("Export .msix")
        dialog.configure(bg=theme["bg"])
        dialog.geometry("600x330")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w",
                 font=("Segoe UI", 10), wraplength=570,
                 text=(f"Packaging: {title}  (runs {exe_rel})\n\n"
                       "Heads up: Windows only installs SIGNED .msix files. If signing is set up, "
                       "Rialto signs it for you, and the publisher line below must match your "
                       "certificate's subject exactly (for Azure Artifact Signing that's your "
                       "verified legal name, like CN=Jane Smith).")).pack(fill="x", padx=12, pady=(12, 8))

        form = tk.Frame(dialog, bg=theme["bg"])
        form.pack(fill="x", padx=12)
        tk.Label(form, text="Publisher:", bg=theme["bg"], fg=theme["fg"], width=16, anchor="w").grid(row=0, column=0, pady=4)
        publisher_var = tk.StringVar(value=config.get("msix_publisher", "CN=" + (self.entries["Developer"].get().strip() or "My Studio")))
        ttk.Entry(form, textvariable=publisher_var).grid(row=0, column=1, sticky="ew", pady=4)
        tk.Label(form, text="Shown as:", bg=theme["bg"], fg=theme["fg"], width=16, anchor="w").grid(row=1, column=0, pady=4)
        display_var = tk.StringVar(value=self.entries["Developer"].get().strip() or "My Studio")
        ttk.Entry(form, textvariable=display_var).grid(row=1, column=1, sticky="ew", pady=4)
        tk.Label(form, text="Version:", bg=theme["bg"], fg=theme["fg"], width=16, anchor="w").grid(row=2, column=0, pady=4)
        version_var = tk.StringVar(value="1.0.0.0")
        ttk.Entry(form, textvariable=version_var).grid(row=2, column=1, sticky="ew", pady=4)
        form.grid_columnconfigure(1, weight=1)

        def run_export():
            dialog.destroy()
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            out_path = safe(os.path.join(OUTPUT_DIR, f"{os.path.basename(self.current_game_path)}.msix"))
            art = self.logo_path_var.get() or self.ico_path_var.get()
            self.update_status("📦 Building .msix package...")
            self.root.update()
            ok, message = msix_export.build_msix(
                self.current_game_path, title, publisher_var.get().strip(),
                display_var.get().strip(), version_var.get().strip() or "1.0.0.0",
                exe_rel, art, out_path, self.update_status)
            self.update_status(("✅ " if ok else "❌ ") + message)
            if not ok:
                return
            # Remember the publisher for next time
            try:
                cfg = trusted_signing.load_config()
                cfg["msix_publisher"] = publisher_var.get().strip()
                with open(trusted_signing.CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
            except Exception:
                pass
            if trusted_signing.is_configured():
                ok_sign, sign_message = trusted_signing.sign_file(out_path, self.update_status)
                self.update_status(("✅ " if ok_sign else "⚠️ ") + sign_message)
                if not ok_sign:
                    self.update_status("   The .msix was still created. Sign it before sharing: unsigned .msix files won't install.")
            else:
                self.update_status("ℹ️ Not signed yet. Windows won't install unsigned .msix files, so set up Configure Signing and export again, or sign it yourself.")
            self.update_status(f"📦 Saved to {out_path}")

        button_row = tk.Frame(dialog, bg=theme["bg"])
        button_row.pack(fill="x", padx=12, pady=12)
        ttk.Button(button_row, text="Export", command=run_export, style="Rounded.TButton").pack(side="right", padx=4)
        ttk.Button(button_row, text="Cancel", command=dialog.destroy, style="Rounded.TButton").pack(side="right", padx=4)

    # === Rialto 1.5: disc menu preview (no build required) ===

    def preview_disc_menu(self):
        """Stage the real disc menu into a temp folder and run it in preview mode."""
        prebuilt = prebuilt_menu_exe()
        if not prebuilt:
            # No pre-built menu.exe: the preview has to run the menu source, and
            # that needs PyQt5 and a real python.exe (a frozen Rialto has neither).
            if getattr(sys, "frozen", False):
                self.show_centered_popup(
                    "Menu preview unavailable",
                    "Rialto could not find menu.exe next to it.\n"
                    "Reinstall Rialto so menu.exe sits in the same folder.")
                return
            try:
                import PyQt5  # noqa: F401 - just checking availability
            except ImportError:
                self.show_centered_popup("Missing PyQt5", "PyQt5 is required for the menu preview.\nRun: pip install -r requirements.txt")
                return

        try:
            # Clear out previews from earlier runs before adding another. Each
            # one holds junctions into this author's game folder, and nothing
            # else was ever going to remove them.
            swept = sweep_stale_previews()
            if swept:
                self.update_status(f"🧹 Cleared {swept} leftover menu preview(s) from earlier runs")

            temp_root = tempfile.mkdtemp(prefix=PREVIEW_PREFIX)
            # And this one on the way out, for the ordinary case where Rialto is
            # closed after the author has finished looking at the preview.
            atexit.register(remove_preview_dir, temp_root)
            menu_dir = os.path.join(temp_root, "menu")
            os.makedirs(menu_dir, exist_ok=True)

            self.update_status("👀 Generating disc menu preview...")
            self.stage_menu_artwork(menu_dir)

            # Stage the mods folder into the preview root so the MODS button
            # shows up here exactly as it will on the finished disc. Junctioned
            # rather than copied - see link_or_copy_tree.
            if self.mod_launcher_var.get() and self.current_game_path:
                mods_source = os.path.join(self.current_game_path, "mods")
                if os.path.isdir(mods_source):
                    link_or_copy_tree(mods_source, os.path.join(temp_root, "mods"))

            # And the bonus folder, for the same reason: the menu looks for
            # bonus/ beside its own folder, so without this the preview hides
            # the BONUS CONTENT button on games that do have one. No option
            # gates it - a bonus folder in the game folder is the whole switch.
            # This is the one that gets big: an hour of behind-the-scenes video
            # used to be copied in full every time anyone hit Preview.
            bonus_source = self.resolved_bonus_dir()
            if bonus_source:
                link_or_copy_tree(bonus_source, os.path.join(temp_root, "bonus"))

            # Exactly the config the real build writes - same function, so the
            # preview cannot drift away from what ends up on the disc.
            company_logo_path = self.company_logo_var.get().strip()
            if company_logo_path and os.path.exists(company_logo_path):
                try:
                    shutil.copy2(company_logo_path, os.path.join(menu_dir, "company_logo.png"))
                except Exception:
                    pass
            self.write_menu_config(menu_dir, temp_root)

            # Window icon lives two levels up from the launcher (the install root)
            if self.ico_path_var.get() and os.path.exists(self.ico_path_var.get()):
                try:
                    shutil.copy2(self.ico_path_var.get(), os.path.join(temp_root, "game_icon.ico"))
                except Exception:
                    pass

            env = os.environ.copy()
            env["RIALTO_PREVIEW"] = "1"

            if prebuilt:
                # The same executable the disc gets, reading the same config.
                shutil.copy2(prebuilt, os.path.join(menu_dir, "menu.exe"))
                command = [os.path.join(menu_dir, "menu.exe")]
            else:
                launcher = write_menu_source(menu_dir)
                if not launcher:
                    self.update_status("❌ Preview failed: menu launcher was not generated")
                    return
                command = [sys.executable, launcher]

            subprocess.Popen(command, cwd=menu_dir, env=env)
            self.update_status("✅ Preview launched - PLAY/UNINSTALL are disabled in preview mode")
        except Exception as e:
            self.update_status(f"❌ Preview failed: {e}")

    # === Rialto 1.5: desktop shortcut (launch like a normal app) ===

    def shortcut_icon_path(self):
        """A real .ico for the desktop shortcut, guaranteed to be there next run.

        Two things were wrong before. The icon was looked for beside Rialto.pyw
        when it actually lives in assets/, so every shortcut came out with the
        blank default document icon. And in a frozen build assets/ is inside the
        bundle's temp folder, which is deleted the moment Rialto closes - so
        even the right path would have pointed at nothing by the time Windows
        drew the icon.

        A frozen build therefore uses Rialto.exe itself, which already carries
        the bird as its own icon resource and is never going anywhere. A source
        checkout uses assets/bird_icon.ico, which is equally permanent.
        """
        if getattr(sys, "frozen", False):
            return os.path.abspath(sys.executable)
        icon = asset_path("bird_icon.ico")
        return icon if os.path.exists(icon) else ""

    def create_desktop_shortcut(self):
        """Put a Rialto shortcut on the desktop, with the bird on it."""
        try:
            app_dir = APP_ROOT
            if getattr(sys, "frozen", False):
                # A frozen build launches itself; there is no interpreter and no
                # .pyw to hand to one.
                target = os.path.abspath(sys.executable)
                arguments = ""
            else:
                target = sys.executable
                if target.lower().endswith("python.exe"):
                    candidate = os.path.join(os.path.dirname(target), "pythonw.exe")
                    if os.path.exists(candidate):
                        target = candidate
                arguments = '"%s"' % os.path.join(app_dir, "Rialto.pyw")

            icon = self.shortcut_icon_path()

            # Single quotes double up inside a PowerShell single-quoted string;
            # a path with an apostrophe in it would otherwise end the string
            # early and take the rest of the script with it.
            def ps_quote(value):
                return "'" + str(value).replace("'", "''") + "'"

            script_lines = [
                "$ws = New-Object -ComObject WScript.Shell",
                "$desktop = [Environment]::GetFolderPath('Desktop')",
                "$s = $ws.CreateShortcut((Join-Path $desktop 'Rialto.lnk'))",
                "$s.TargetPath = %s" % ps_quote(target),
                "$s.Arguments = %s" % ps_quote(arguments),
                "$s.WorkingDirectory = %s" % ps_quote(app_dir),
                "$s.Description = 'Rialto Disc Builder'",
            ]
            if icon:
                # ",0" names the first icon resource, which is what Explorer
                # wants when the target is an exe rather than an .ico file.
                script_lines.append("$s.IconLocation = %s" % ps_quote(icon + ",0"))
            script_lines.append("$s.Save()")

            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "; ".join(script_lines)],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if result.returncode == 0:
                self.update_status("✅ Rialto is on your desktop")
                self.show_centered_popup(
                    "Shortcut Created",
                    "Rialto is on your desktop. Double-click the bird to open it.")
                # Explorer caches shortcut icons aggressively; without this the
                # new one can keep showing the old blank page until logout.
                self.refresh_windows_icon_cache()
            else:
                self.update_status(f"❌ Shortcut failed: {result.stderr.strip()}")
        except Exception as e:
            self.update_status(f"❌ Shortcut failed: {e}")

    # === Rialto 1.5: Azure Artifact Signing configuration (BYO account) ===

    # Pasted into an AI assistant by anyone who would rather be walked through
    # the Azure portal than read a page about it. Deliberately says what Rialto
    # needs back, so the conversation ends with the three values this dialog
    # asks for rather than with general advice.
    SIGNING_AI_PROMPT = (
        "I am an indie game developer on Windows. I want to code-sign my game's "
        "installer with Azure Artifact Signing (Microsoft renamed it from Azure "
        "Trusted Signing in January 2026 - the portal now says \"Artifact Signing "
        "Accounts\"). I have never signed anything before and I am not an Azure "
        "person.\n\n"
        "Walk me through it one step at a time, waiting for me to say done "
        "before moving on. Assume I know nothing about Azure. Tell me exactly "
        "what to click.\n\n"
        "Cover, in this order:\n"
        "1. Creating an Azure account with a pay-as-you-go subscription (a free "
        "trial subscription does not work for this service).\n"
        "2. Registering the Microsoft.CodeSigning resource provider on that "
        "subscription.\n"
        "3. Creating an Artifact Signing account on the Basic plan (about "
        "$9.99/month, 5,000 signatures), and how to pick the right region.\n"
        "4. Identity validation. I am an INDIVIDUAL developer, not a company - "
        "tell me what ID I need, warn me about the parts people get wrong, and "
        "tell me how long it usually takes. If I say I am a company instead, "
        "switch to the organisation path.\n"
        "5. Creating a Public Trust certificate profile once validation passes.\n"
        "6. Giving my own user the \"Artifact Signing Certificate Profile "
        "Signer\" role, and explaining why signing fails without it.\n"
        "7. Installing the Azure CLI and running az login.\n"
        "8. Finding the three values I have to type into my build tool: the "
        "region endpoint URL, the account name, and the certificate profile "
        "name. Tell me exactly where in the portal each one is.\n\n"
        "At the end, print those three values back to me as a labelled list so "
        "I can copy them across. If a step fails, help me diagnose it before we "
        "move on."
    )

    def configure_signing(self):
        """Dialog for the user's own Azure Artifact Signing account details."""
        import trusted_signing

        config = trusted_signing.load_config()
        theme = self.current_theme()

        dialog, body = self.themed_dialog(
            "Configure Code Signing",
            "Optional. Put your own studio's name on the Windows install prompt",
            width=640, height=740)

        # Scrolling, because this is the one dialog with real reading in it and
        # a 1080p screen has less room than it looks like it has.
        canvas = tk.Canvas(body, bg=theme["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        page = tk.Frame(canvas, bg=theme["bg"])
        page_window = canvas.create_window((0, 0), window=page, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def on_page_resize(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        page.bind("<Configure>", on_page_resize)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(page_window, width=e.width))

        def on_wheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", on_wheel)
        dialog.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>")
                    if e.widget is dialog else None)

        def para(text, size=10, bold=False, muted=False, pad=(0, 6)):
            tk.Label(page, text=text, bg=theme["bg"],
                     fg=theme["disabled_fg"] if muted else theme["fg"],
                     justify="left", anchor="w", wraplength=560,
                     font=("Segoe UI", size, "bold" if bold else "normal")
                     ).pack(fill="x", padx=16, pady=pad)

        def rule():
            tk.Frame(page, bg=theme["button_bg"], height=1).pack(fill="x", padx=16, pady=(10, 2))

        para("What signing is for", bold=True, pad=(12, 2))
        para("Windows keeps a list of publishers it trusts. A signed program "
             "carries your studio's name from that list, so the install prompt "
             "says who made it instead of showing a yellow \"Unknown Publisher\" "
             "warning, and antivirus engines stop treating every new build as a "
             "stranger they have never met.", muted=True)
        para("The honest part about discs: the big SmartScreen block only fires "
             "on files downloaded from the internet, and a file on a disc cannot "
             "carry the marker that says it was downloaded. So a disc player "
             "never sees SmartScreen, signed or not. On a disc, signing is about "
             "the name on the prompt and about antivirus. If you also sell "
             "downloads, it matters a great deal more.", muted=True)

        rule()
        para("You do not have to do this", bold=True)
        para("Bringing your own signing account is optional. Unsigned discs work "
             "perfectly and plenty of people ship them. Leave everything below "
             "empty and Rialto builds exactly as it always did; if you tick Sign "
             "Final Build with nothing set up, the build pauses once the "
             "installer exists so you can sign it with whatever you use, and "
             "carries on to the ISO when you click OK. Your disc's copy of "
             "menu.exe simply stays unsigned. Nothing breaks.", muted=True)
        para("Rialto is a tool, not a signing service. Everybody signs with their "
             "own Microsoft account and their own name. Nothing you sign leaves "
             "this PC: only a fingerprint of the file goes to Microsoft, and the "
             "signature comes back.", muted=True)

        rule()
        para("The Azure route, in three steps", bold=True)
        para("Microsoft's own service is Azure Artifact Signing, and it is the "
             "one Rialto is built around. It was called Azure Trusted Signing "
             "until Microsoft renamed it in January 2026, so older guides use "
             "that name. The Basic plan is $9.99 a month for 5,000 signatures.",
             muted=True)
        for step in (
            "1.  Open an account. An Azure subscription that is pay-as-you-go, "
            "the Microsoft.CodeSigning provider registered on it, and an Artifact "
            "Signing account on the Basic plan. Note the region you pick.",
            "2.  Prove who you are, then make a certificate. Identity validation "
            "is the long pole: Microsoft puts it at 1 to 20 business days. When "
            "it passes, create a Public Trust certificate profile and give your "
            "own user the signer role on the account.",
            "3.  Tell Rialto. Install the Azure CLI, run az login once, then fill "
            "in the three boxes below and press Check My Setup until every line "
            "reads OK.",
        ):
            tk.Label(page, text=step, bg=theme["bg"], fg=theme["fg"], justify="left",
                     anchor="w", wraplength=540, font=("Segoe UI", 10)
                     ).pack(fill="x", padx=(28, 16), pady=2)
        para("Start step 2 before you need it. Everything else is about half an "
             "hour of clicking.", muted=True)

        rule()
        para("The same three steps, one click at a time", bold=True)
        for step in (
            "1.  Sign up at portal.azure.com and put a pay-as-you-go subscription "
            "on the account. A free trial subscription will not work with this "
            "service.",
            "2.  Register the Microsoft.CodeSigning resource provider on that "
            "subscription: Subscriptions, your subscription, Resource providers, "
            "search for it, Register. This is the step people skip.",
            "3.  Search the portal for \"Artifact Signing Accounts\", press "
            "Create, choose the Basic plan and a region near you. Write the "
            "region down; Rialto asks for it.",
            "4.  Identity validations, New identity, Public. An individual in the "
            "US or Canada verifies with a government photo ID; a company in a "
            "wider list of countries verifies business records, and a named "
            "person there still does the photo ID step. The name you enter is the "
            "name players will see, so enter it exactly.",
            "5.  Once validation passes: Certificate profiles, Create, type "
            "Public Trust. Write the profile name down too.",
            "6.  On the account, open Access control (IAM) and give your own user "
            "the \"Artifact Signing Certificate Profile Signer\" role. Creating "
            "the account does not grant it, and without it everything looks "
            "correct while signing fails at the last second.",
            "7.  Install the Azure CLI (aka.ms/azure-cli) and the .NET 8 runtime, "
            "then run:  az login",
            "8.  Fill in the three boxes below, press Save, then Check My Setup.",
            "9.  Tick Sign Final Build and build. Rialto signs your installer and "
            "this disc's own copy of menu.exe, both with your account.",
        ):
            tk.Label(page, text=step, bg=theme["bg"], fg=theme["fg"], justify="left",
                     anchor="w", wraplength=540, font=("Segoe UI", 10)
                     ).pack(fill="x", padx=(28, 16), pady=2)

        rule()
        para("Why your disc's menu.exe gets signed too", bold=True)
        para("Rialto is open source, and the menu.exe on its release page is the "
             "same generic file on every disc anybody builds. If it arrived "
             "already signed, somebody else's name would be sitting on your disc "
             "and yours would be sitting on discs made by people you have never "
             "met. So the shared copy ships unsigned on purpose, and Rialto signs "
             "your copy, on your disc, with your account. The original is never "
             "touched.", muted=True)

        rule()
        para("Your account details", bold=True)
        para("Three values, all from the Azure portal, all required together: "
             "fill in none of them or all of them. Region has to match the region "
             "your account and your certificate profile actually live in, and a "
             "mismatch is the usual cause of a 403 at signing time.", muted=True)

        form = tk.Frame(page, bg=theme["bg"])
        form.pack(fill="x", padx=16, pady=(2, 8))

        def field_help(row, text):
            """One line under a box saying what goes in it."""
            tk.Label(form, text=text, bg=theme["bg"], fg=theme["disabled_fg"],
                     anchor="w", justify="left", wraplength=380,
                     font=("Segoe UI", 8)).grid(row=row, column=1, sticky="ew", pady=(0, 6))

        tk.Label(form, text="Region:", bg=theme["bg"], fg=theme["fg"], width=18, anchor="w").grid(row=0, column=0, pady=4)
        region_var = tk.StringVar()
        region_combo = ttk.Combobox(form, textvariable=region_var,
                                    values=list(trusted_signing.ENDPOINTS.keys()), state="readonly")
        region_combo.grid(row=0, column=1, sticky="ew", pady=4)
        ToolTip(region_combo, "The Azure region your Artifact Signing account was created "
                              "in. Picking it fills in the endpoint for you.")
        field_help(1, "Required. Where your signing account lives. Picking it fills in "
                      "the endpoint below, which is the safe way to get that right.")

        tk.Label(form, text="Endpoint URL:", bg=theme["bg"], fg=theme["fg"], width=18, anchor="w").grid(row=2, column=0, pady=4)
        endpoint_var = tk.StringVar(value=config.get("endpoint", ""))
        endpoint_entry = ttk.Entry(form, textvariable=endpoint_var)
        endpoint_entry.grid(row=2, column=1, sticky="ew", pady=4)
        ToolTip(endpoint_entry, "The address Rialto asks for a signing certificate. It "
                                "follows the region, so you rarely type here.")
        field_help(3, "Required, and filled in by the region above. The one address "
                      "Rialto asks for a certificate. If it points at a different "
                      "region from your account, signing fails with a 403.")

        # Show the saved endpoint's region on open, so an existing setup reads back
        saved_region = next((name for name, url in trusted_signing.ENDPOINTS.items()
                             if url == config.get("endpoint", "").rstrip("/")), "")
        if saved_region:
            region_var.set(saved_region)

        def on_region_selected(event=None):
            endpoint_var.set(trusted_signing.ENDPOINTS.get(region_var.get(), ""))
        region_combo.bind("<<ComboboxSelected>>", on_region_selected)

        tk.Label(form, text="Account Name:", bg=theme["bg"], fg=theme["fg"], width=18, anchor="w").grid(row=4, column=0, pady=4)
        account_var = tk.StringVar(value=config.get("account_name", ""))
        account_entry = ttk.Entry(form, textvariable=account_var)
        account_entry.grid(row=4, column=1, sticky="ew", pady=4)
        ToolTip(account_entry, "The name of your Artifact Signing account, exactly as the "
                               "portal spells it. Found on the account's Overview page.")
        field_help(5, "Required. Your Artifact Signing account's name, spelled exactly "
                      "as the portal spells it. It is on the account's Overview page.")

        tk.Label(form, text="Certificate Profile:", bg=theme["bg"], fg=theme["fg"], width=18, anchor="w").grid(row=6, column=0, pady=4)
        profile_var = tk.StringVar(value=config.get("certificate_profile", ""))
        profile_entry = ttk.Entry(form, textvariable=profile_var)
        profile_entry.grid(row=6, column=1, sticky="ew", pady=4)
        ToolTip(profile_entry, "The name of the certificate profile inside that account. "
                               "Under Objects, Certificate profiles.")
        field_help(7, "Required. The Public Trust profile you made inside that account. "
                      "In the portal it is under Objects, Certificate profiles.")

        form.grid_columnconfigure(1, weight=1)

        rule()
        para("If you skip all of this", bold=True)
        para("Leave the three boxes empty and nothing changes: the build runs, the "
             "ISO comes out, and players see \"Unknown Publisher\" on the install "
             "prompt. Tick Sign Final Build anyway and the build pauses right "
             "after the installer is made so you can sign it however you like, "
             "then finishes the ISO when you click OK. You can come back and fill "
             "this in at any time; nothing you have already built changes.",
             muted=True)
        para("There is one free route worth knowing about: SignPath Foundation, "
             "for open source projects with public builds, though the publisher "
             "line then reads SignPath Foundation rather than your name. The "
             "guide has the full comparison.", muted=True)

        rule()
        para("Would you rather be walked through it?", bold=True)
        para("Copy the prompt below and paste it into a desktop AI assistant, "
             "such as Claude, ChatGPT, Grok or Kimi. It takes you through the "
             "Azure portal one step at a time, waits at each one, and finishes by "
             "handing you the three values this dialog wants. Nothing about your "
             "game is in it.", muted=True)
        prompt_box = tk.Text(page, height=6, wrap="word", bg=theme["entry_bg"],
                             fg=theme["fg"], font=("Consolas", 9), relief="flat",
                             padx=8, pady=6, insertbackground=theme["fg"])
        prompt_box.insert("1.0", self.SIGNING_AI_PROMPT)
        prompt_box.configure(state="disabled")
        prompt_box.pack(fill="x", padx=16, pady=(2, 6))

        def copy_prompt():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.SIGNING_AI_PROMPT)
            self.update_status("📋 Copied the signing walkthrough prompt to your clipboard")
            copy_btn.configure(text="  Copied to clipboard")
            dialog.after(2200, lambda: copy_btn.configure(text="  Copy the AI prompt"))

        prompt_row = tk.Frame(page, bg=theme["bg"])
        prompt_row.pack(fill="x", padx=16, pady=(0, 14))
        copy_btn = self.icon_button(prompt_row, "book", "Copy the AI prompt",
                                    copy_prompt, side="left")
        ToolTip(copy_btn, "Copies the whole prompt. Paste it into any AI assistant and "
                          "answer its questions as they come.")

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- Buttons, outside the scroll area so they are always reachable ---
        button_row = tk.Frame(dialog, bg=theme["header_bg"])
        button_row.pack(side="bottom", fill="x")
        button_row._rialto_surface = "header"
        tk.Frame(button_row, bg=theme["button_bg"], height=1).pack(fill="x")
        button_inner = tk.Frame(button_row, bg=theme["header_bg"])
        button_inner._rialto_surface = "header"
        button_inner.pack(fill="x", padx=14, pady=10)

        def save_and_close():
            if not (endpoint_var.get().strip() and account_var.get().strip() and profile_var.get().strip()):
                self.show_centered_popup(
                    "One of the three is missing",
                    "Signing needs the endpoint, the account name and the certificate "
                    "profile together. Fill in all three, or press Cancel and leave "
                    "signing set up later. Your builds work either way.")
                return
            try:
                trusted_signing.save_config(endpoint_var.get(), account_var.get(), profile_var.get())
            except ValueError as e:
                # The endpoint is where the signing token is fetched from, so a
                # wrong one is worth stopping for rather than saving quietly.
                self.show_centered_popup("Check the endpoint", str(e))
                return
            signtool = trusted_signing.find_signtool()
            if signtool:
                self.update_status(f"✅ Signing configured (signtool: {signtool})")
            else:
                self.update_status("⚠️ Signing saved, but signtool.exe was not found. Install the Windows SDK from aka.ms/windowssdk, then press Check My Setup again.")
            dialog.destroy()

        def check_setup():
            self.update_status("🔍 Checking your signing setup...")
            dialog.config(cursor="watch")
            dialog.update()
            try:
                # What is on screen right now, not only what has been saved.
                results = trusted_signing.check_environment({
                    "endpoint": endpoint_var.get(),
                    "account_name": account_var.get(),
                    "certificate_profile": profile_var.get(),
                })
            finally:
                dialog.config(cursor="")
            self.show_setup_report(results)

        ttk.Button(button_inner, text="Save", command=save_and_close,
                   style="Primary.TButton").pack(side="right", padx=4)
        ttk.Button(button_inner, text="Check My Setup", command=check_setup,
                   style="Rounded.TButton").pack(side="right", padx=4)
        ttk.Button(button_inner, text="Cancel", command=dialog.destroy,
                   style="Rounded.TButton").pack(side="right", padx=4)
        guide_btn = self.icon_button(button_inner, "book", "Read the Guide",
                                     self.open_signing_guide, side="left")
        ToolTip(guide_btn, "Opens the full signing guide as an offline page in your browser.")

    def show_setup_report(self, results):
        """The Check My Setup readout, in Rialto's own dressing.

        Was a bare messagebox: white, cramped, and its closing line said things
        still needed doing even when every check had passed. This one is themed
        like the rest, has room to breathe, and when the list is all green it
        says so and nothing else.
        """
        theme = self.current_theme()
        all_ok = all(ok for _label, ok, _hint in results)
        rows = len(results)

        dialog, body = self.themed_dialog(
            "Check My Setup",
            "Everything signing needs, one line at a time",
            width=660, height=min(760, 300 + rows * 62))

        close_row = tk.Frame(body, bg=theme["bg"])
        close_row.pack(side="bottom", fill="x", padx=16, pady=(4, 14))
        ttk.Button(close_row, text="Close", command=dialog.destroy,
                   style="Primary.TButton").pack(side="right")

        # The verdict goes at the top, because it is the answer to the question
        # that was actually asked.
        verdict = tk.Frame(body, bg=theme["accent"] if all_ok else theme["header_bg"])
        verdict.pack(fill="x", padx=16, pady=(14, 6))
        if all_ok:
            headline = "You are ready to sign."
            detail = ("Tick Sign Final Build and press Build. Rialto signs your installer "
                      "and this disc's copy of menu.exe with your own certificate.")
            fg, sub = "#ffffff", "#e8f1ff"
        else:
            outstanding = sum(1 for _l, ok, _h in results if not ok)
            headline = "%d thing%s still to do." % (outstanding, "" if outstanding == 1 else "s")
            detail = ("Each one is marked below with what to do about it. The signing guide "
                      "walks through the whole setup step by step.")
            fg, sub = theme["fg"], theme["disabled_fg"]
        tk.Label(verdict, text=headline, bg=verdict["bg"], fg=fg, anchor="w",
                 font=("Segoe UI", 12, "bold")).pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(verdict, text=detail, bg=verdict["bg"], fg=sub, anchor="w", justify="left",
                 wraplength=580, font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(2, 11))

        for label, ok, hint in results:
            row = tk.Frame(body, bg=theme["bg"])
            row.pack(fill="x", padx=16, pady=3)

            mark = tk.Label(row, text="✓" if ok else "•",
                            bg=theme["bg"],
                            fg="#4ec97f" if ok else theme["meter_warn"],
                            font=("Segoe UI", 13, "bold"), width=2)
            mark.pack(side="left", anchor="n")

            text = tk.Frame(row, bg=theme["bg"])
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=label, bg=theme["bg"], fg=theme["fg"], anchor="w",
                     font=("Segoe UI", 10, "bold")).pack(fill="x")
            tk.Label(text, text=hint, bg=theme["bg"], fg=theme["disabled_fg"], anchor="w",
                     justify="left", wraplength=560,
                     font=("Segoe UI", 9)).pack(fill="x")

        self.root.wait_window(dialog)

    # === Documentation ===

    def doc_path(self, filename):
        """Locate a shipped doc, preferring a copy the author can edit.

        Beside Rialto first (APP_ROOT/docs, then APP_ROOT), then inside the
        frozen bundle. A bundled copy lives in a temp folder the PyInstaller
        bootloader deletes on exit, so it is copied out to APP_ROOT/docs before
        the browser is pointed at it - otherwise the page would vanish from
        under the browser the moment Rialto closed.
        """
        local = [
            os.path.join(APP_ROOT, "docs", filename),
            os.path.join(APP_ROOT, filename),
        ]
        for candidate in local:
            if os.path.isfile(candidate):
                return candidate

        meipass = getattr(sys, "_MEIPASS", None)
        for bundled in ([os.path.join(meipass, "docs", filename),
                         os.path.join(meipass, filename)] if meipass else []):
            if os.path.isfile(bundled):
                target = os.path.join(APP_ROOT, "docs", filename)
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copy2(bundled, target)
                    return target
                except OSError:
                    return bundled  # read-only install: temp copy is better than nothing
        return None

    def confirm_open_offline_page(self, title):
        """Ask before handing a local page to the browser. Returns True to go ahead."""
        return self.show_centered_popup(
            "Open " + title,
            "This opens " + title + " in your web browser.\n\n"
            "The page is an offline file on this PC. Nothing is sent anywhere "
            "and it works with no internet connection.\n\n"
            "Open it?",
            kind="yesno")

    def open_doc(self, filename, title):
        """Confirm, then open one of Rialto's offline HTML pages."""
        page = self.doc_path(filename)
        if not page:
            self.update_status(f"⚠️ {filename} not found - it ships beside Rialto")
            return
        if not self.confirm_open_offline_page(title):
            return
        try:
            os.startfile(page)
            self.update_status(f"📖 Opened {title}: {page}")
        except Exception as e:
            self.update_status(f"⚠️ Could not open {title} ({e}): {page}")

    def open_help_guide(self):
        self.open_doc("rialto-guide.html", "the Rialto guide")

    def check_for_new_rialto(self):
        """Help > Check for a New Rialto. One request, when asked; one sentence back.

        Runs the check on a thread so the window keeps painting, then says
        what it found in Rialto's own popup. A newer release is offered as a
        link to the release page in the browser; nothing is downloaded or
        installed from here (by design: check and open, no
        in-place apply in this version). Nothing is remembered between checks.
        """
        if getattr(self, "_update_check_running", False):
            return
        if not self.show_centered_popup(
                "Check for a New Rialto",
                "This asks the release server whether a newer Rialto exists.\n\n"
                "One request, now, with nothing about you in it. Rialto keeps "
                "nothing about the answer.\n\n"
                "Ask?",
                kind="yesno"):
            return
        self._update_check_running = True
        self.update_status("🔎 Asking the release server…")

        class _Said:
            """A stand-in outcome when the update package itself is missing."""
            release = None

            def __init__(self, sentence):
                self.sentence = sentence

        def work():
            outcome = _Said("The check did not finish. Nothing was changed.")
            try:
                from update.check import check_for_update
                outcome = check_for_update(__version__)
            except Exception:
                pass
            finally:
                self.root.after(0, lambda: self._on_new_rialto_checked(outcome))

        threading.Thread(target=work, name="rialto-update-check", daemon=True).start()

    def _on_new_rialto_checked(self, outcome):
        self._update_check_running = False
        self.update_status("ℹ️ " + outcome.sentence)
        if outcome.release is None:
            self.show_centered_popup("Check for a New Rialto", outcome.sentence)
            return
        from update.keys import RELEASE_PAGE
        page = outcome.release.notes_url or RELEASE_PAGE
        if self.show_centered_popup(
                "Check for a New Rialto",
                outcome.sentence + "\n\n"
                "Open the release page in your web browser? Download Rialto.exe and "
                "menu.exe from there and keep them together, as before.\n\n"
                "Open it?",
                kind="yesno"):
            import webbrowser
            webbrowser.open(page)

    def open_signing_guide(self):
        self.open_doc("signing-guide.html", "the signing guide")


    def save_last_session(self):
        """Save current session"""
        session_data = {
            "last_used_game": self.current_game_path,
            "theme_mode": self.theme_mode.get()
        }

        # Save essential fields only
        for key, entry in self.entries.items():
            session_data[key] = entry.get()

        # Save additional settings
        session_data["Background"] = self.bg_path_var.get()
        session_data["Logo"] = self.logo_path_var.get()
        session_data["Icon"] = self.ico_path_var.get()
        session_data["DiscIcon"] = self.disc_icon_var.get()
        session_data["DiscName"] = self.disc_name_var.get()

        try:
            with open(LAST_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=4)
        except Exception:
            pass

    def load_last_session(self):
        """Load previous session"""
        try:
            if os.path.exists(LAST_SESSION_FILE):
                with open(LAST_SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Load theme
                theme = data.get("theme_mode", "dark")
                self.theme_mode.set(theme)
                if theme == "dark":
                    self.apply_dark_theme()
                else:
                    self.apply_light_theme()

                # Load essential fields
                for key, value in data.items():
                    if key in self.entries:
                        self.entries[key].delete(0, tk.END)
                        self.entries[key].insert(0, value)
                    elif key == "Background":
                        self.bg_path_var.set(value)
                    elif key == "Logo":
                        self.logo_path_var.set(value)
                    elif key == "Icon":
                        self.ico_path_var.set(value)
                    elif key == "DiscIcon":
                        self.disc_icon_var.set(value)
                    elif key == "DiscName":
                        self.disc_name_var.set(value)
                        
        except Exception:
            pass





    def _apply_theme(self, theme_colors, status_bg=None, status_fg=None, labelframe_label_bg=None):
        """Shared theme application logic for both dark and light modes"""
        bg = theme_colors["bg"]
        fg = theme_colors["fg"]
        entry_bg = theme_colors["entry_bg"]
        button_bg = theme_colors["button_bg"]
        button_fg = theme_colors["button_fg"]
        button_active = theme_colors["button_active"]
        disabled_fg = theme_colors["disabled_fg"]
        frame_bg = bg

        # Apply to title bar
        self.title_bar.configure(bg=bg)
        self.title_label.configure(bg=bg, fg=fg)
        self.close_btn.configure(bg=bg, fg=fg)
        self.minimize_btn.configure(bg=bg, fg=fg)

        # Apply to manually colored frames
        self.main_content.configure(bg=bg)

        header_bg = theme_colors["header_bg"]
        for widget in (getattr(self, "menu_bar", None), getattr(self, "export_bar", None),
                       getattr(self, "export_inner", None), getattr(self, "export_check_row", None)):
            if widget is not None:
                try:
                    widget.configure(bg=header_bg)
                except tk.TclError:
                    pass
        for button in getattr(self, "menu_buttons", []):
            button.configure(bg=header_bg, fg=fg,
                             activebackground=theme_colors["button_active"], activeforeground=fg)
        for menu in getattr(self, "menus", []):
            menu.configure(bg=entry_bg, fg=fg,
                           activebackground=theme_colors["accent"], activeforeground="#ffffff")
        if hasattr(self, "export_rule"):
            self.export_rule.configure(bg=button_bg)

        self.status_text.configure(bg=bg, fg=status_fg or fg)

        style = ttk.Style()
        style.theme_use('default')

        self.root.configure(bg=bg)

        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelFrame", background=bg, foreground=fg)
        style.configure("TLabelFrame.Label", background=labelframe_label_bg or bg, foreground=fg)
        style.configure("TMenubutton", background=bg, foreground=fg)
        style.configure("Toggle.TButton", background=button_bg, foreground=fg)
        style.configure("Popup.TButton",
            background=button_bg,
            foreground=button_fg,
            padding=(14, 6),
            relief="flat",
            font=("Segoe UI", 10, "bold")
        )

        style.configure("TLabelframe",
            background=frame_bg,
            borderwidth=1,
            relief="groove"
        )
        style.configure("TLabelframe.Label",
            background=frame_bg,
            foreground=fg,
            font=("Segoe UI", 9, "bold")
        )

        style.configure("TEntry",
            fieldbackground=entry_bg,
            foreground=fg)
        style.map("TEntry",
            fieldbackground=[("readonly", entry_bg)],
            foreground=[("readonly", fg)])

        style.configure("TCombobox",
            fieldbackground=entry_bg,
            background=button_bg,
            foreground=fg,
            arrowcolor=fg,
            selectbackground=entry_bg,
            selectforeground=fg)
        style.map("TCombobox",
            fieldbackground=[("readonly", entry_bg), ("disabled", bg)],
            foreground=[("readonly", fg), ("disabled", disabled_fg)],
            selectbackground=[("readonly", entry_bg)],
            selectforeground=[("readonly", fg)],
            background=[("active", button_active)],
            arrowcolor=[("disabled", disabled_fg)])
        # The dropdown list itself is a plain Listbox and needs matching colors
        self.root.option_add("*TCombobox*Listbox.background", entry_bg)
        self.root.option_add("*TCombobox*Listbox.foreground", fg)
        self.root.option_add("*TCombobox*Listbox.selectBackground", button_active)
        self.root.option_add("*TCombobox*Listbox.selectForeground", fg)

        style.configure("TButton",
            background=button_bg,
            foreground=button_fg,
            borderwidth=1,
            focusthickness=1,
            focuscolor=frame_bg,
            relief="flat"
        )

        style.map("TButton",
            background=[('active', button_active)],
            foreground=[('disabled', disabled_fg)]
        )

        style.configure("TMenubutton",
            background=button_bg,
            foreground=button_fg,
            arrowcolor=button_fg,
            borderwidth=1
        )

        style.map("TMenubutton",
            background=[("active", button_active)],
            foreground=[("disabled", disabled_fg)],
            arrowcolor=[("active", button_fg)]
        )

        style.configure("Rounded.TButton",
            background=button_bg,
            foreground=button_fg,
            borderwidth=1,
            focusthickness=0,
            padding=6,
            relief="flat"
        )
        style.map("Rounded.TButton",
            background=[('active', button_active)],
            foreground=[('disabled', disabled_fg)],
            relief=[('pressed', 'flat'), ('!pressed', 'flat')]
        )

        style.configure("TCheckbutton",
            background=bg,
            foreground=fg,
            indicatorbackground=entry_bg,
            indicatorforeground=fg,
            focuscolor=bg
        )
        style.map("TCheckbutton",
            background=[("active", bg)],
            foreground=[("active", fg)],
            indicatorbackground=[("selected", button_active), ("active", entry_bg)]
        )

        style.map("Popup.TButton",
            background=[("active", button_active)],
            foreground=[("disabled", disabled_fg)]
        )

        # The two buttons that carry the most weight: Step 1 and BUILD.
        style.configure("Primary.TButton",
            background=button_bg, foreground=button_fg,
            borderwidth=1, focusthickness=0, relief="flat",
            padding=(12, 7), font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton",
            background=[("active", button_active)],
            foreground=[("disabled", disabled_fg)])

        style.configure("Build.TButton",
            background=theme_colors["accent"], foreground="#ffffff",
            borderwidth=0, focusthickness=0, relief="flat",
            padding=(14, 7), font=("Segoe UI", 11, "bold"))
        style.map("Build.TButton",
            background=[("active", theme_colors["meter_warn"])],
            foreground=[("disabled", disabled_fg)])

        # Grey, smaller, for the folder path beside Step 1
        style.configure("Path.TLabel", background=bg, foreground=disabled_fg,
                        font=("Segoe UI", 9))

        # The panel of instructions at the top, which reads as a card rather
        # than as part of the form.
        style.configure("Tutorial.TFrame", background=theme_colors["header_bg"],
                        relief="groove", borderwidth=1)
        # The rows inside it: same colour, no border of their own.
        style.configure("TutorialRow.TFrame", background=theme_colors["header_bg"],
                        relief="flat", borderwidth=0)
        style.configure("Tutorial.TLabel", background=theme_colors["header_bg"],
                        foreground=fg, borderwidth=0, relief="flat")

        # The hint that floats inside an empty Game Title / Developer /
        # Publisher field. Sits on the entry, so it takes the entry's colour.
        style.configure("Placeholder.TLabel", background=entry_bg,
                        foreground=disabled_fg, font=("Segoe UI", 9, "italic"))

        # The signing dialog scrolls, and a stock white scrollbar down the side
        # of a black dialog is the first thing anyone notices.
        style.configure("Vertical.TScrollbar",
                        background=button_bg, troughcolor=theme_colors["header_bg"],
                        bordercolor=theme_colors["header_bg"],
                        arrowcolor=fg, borderwidth=0, relief="flat")
        style.map("Vertical.TScrollbar",
                  background=[("active", button_active), ("pressed", button_active)])

        # Icons are drawn in a flat colour, so they need repainting per theme
        self._repaint_icon_buttons(self.root, theme_colors["icon"])

        # Checkbuttons draw their tick from a per-theme image element
        theme_name = "dark" if theme_colors is self.dark_theme else "light"
        install_check_style(style, theme_name, theme_colors)
        prefix = theme_name.capitalize()
        for check in list(getattr(self, "_themed_checks", [])):
            surface = getattr(check, "_rialto_check_surface", "page")
            name = f"{prefix}Header.TCheckbutton" if surface == "header" else f"{prefix}.TCheckbutton"
            try:
                check.configure(style=name)
            except tk.TclError:
                self._themed_checks.remove(check)  # its dialog has been closed

        if status_bg:
            self._status_colors = (status_bg, status_fg or fg)
            self.status_text.configure(bg=status_bg, fg=status_fg or fg)

        self._update_all_widgets_recursive(self.root, bg=bg, fg=fg)
        self._force_theme_refresh(theme_colors)

    def icon_button(self, parent, name, text, command, style="Rounded.TButton", size=16, **pack_kw):
        """A ttk.Button whose glyph is a drawn image rather than an emoji.

        Tagged with the icon it wants so a theme change can repaint it, and the
        image is kept in self._button_icons because Tk holds only a weak
        reference to PhotoImages handed to widgets.
        """
        image = ui_icon(name, self.current_theme()["icon"], size)
        key = "%s@%d" % (name, size)
        self._button_icons[key] = image
        button = ttk.Button(parent, text="  " + text, image=image, compound="left",
                            command=command, style=style)
        button._rialto_icon = name
        button._rialto_icon_size = size
        button._rialto_style = style
        if pack_kw:
            button.pack(**pack_kw)
        return button

    def current_theme(self):
        return self.dark_theme if self.theme_mode.get() == "dark" else self.light_theme

    def add_placeholder(self, entry, variable, text):
        """Grey italic hint inside an empty field.

        A ttk.Entry has no placeholder, and the usual trick of writing the hint
        into the widget and clearing it on focus is not usable here: Game
        Title, Developer and Publisher all drive other fields through traces,
        so a hint written into the variable would end up in the copyright line
        and the Start Menu name. This floats a label over the entry instead, so
        the value stays genuinely empty.
        """
        hint = ttk.Label(entry, text=text, style="Placeholder.TLabel")
        hint._rialto_style = "Placeholder.TLabel"
        hint.bind("<Button-1>", lambda _e: entry.focus_set())

        def refresh(*_args):
            try:
                if variable.get():
                    hint.place_forget()
                else:
                    hint.place(x=7, rely=0.5, anchor="w")
            except tk.TclError:
                pass

        variable.trace_add("write", refresh)
        refresh()
        return hint

    def check_style(self, surface="page"):
        """Style name for a checkbutton with a real tick, on the given surface."""
        theme_name = "dark" if self.theme_mode.get() == "dark" else "light"
        install_check_style(ttk.Style(), theme_name, self.current_theme())
        prefix = theme_name.capitalize()
        return f"{prefix}Header.TCheckbutton" if surface == "header" else f"{prefix}.TCheckbutton"

    def themed_check(self, parent, text, variable, surface="page", command=None, **pack_kw):
        """A checkbutton that repaints itself when the theme changes."""
        check = ttk.Checkbutton(parent, text=text, variable=variable, command=command,
                                style=self.check_style(surface))
        check._rialto_check_surface = surface
        self._themed_checks.append(check)
        if pack_kw:
            check.pack(**pack_kw)
        return check

    def _repaint_icon_buttons(self, parent, icon_color):
        """Point every icon button at the freshly recoloured image."""
        for widget in parent.winfo_children():
            name = getattr(widget, "_rialto_icon", None)
            if name:
                size = getattr(widget, "_rialto_icon_size", 16)
                image = ui_icon(name, icon_color, size)
                self._button_icons["%s@%d" % (name, size)] = image
                try:
                    widget.configure(image=image)
                except tk.TclError:
                    pass
            self._repaint_icon_buttons(widget, icon_color)

    def apply_dark_theme(self):
        self._apply_theme(self.dark_theme, status_bg="#111111", status_fg="#00FF00", labelframe_label_bg="#1e1e1e")





    def apply_light_theme(self):
        self._apply_theme(self.light_theme, status_bg="#f5f5f5", status_fg="#1a6b1a", labelframe_label_bg="#e8e8e8")







    def _update_button_colors(self, widget, bg, fg):
        try:
            widget_type = widget.winfo_class()
            if widget_type in ["Button", "TButton", "Menubutton"]:
                widget.configure(background=bg, foreground=fg)
            elif widget_type == "Frame" or widget_type == "LabelFrame":
                widget.configure(background=bg)
            elif widget_type == "Label":
                widget.configure(background=bg, foreground=fg)
            elif widget_type == "Entry":
                widget.configure(background=bg, foreground=fg)
            elif widget_type == "Text":
                widget.configure(bg=bg, fg=fg)
            elif widget_type == "TMenubutton":
                widget.configure(background=bg, foreground=fg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._update_button_colors(child, bg, fg)




    def _update_misc_widget_colors(self, widget, bg, fg):
        # Apply styles to tk.Button and OptionMenu menu elements
        if isinstance(widget, tk.Button):
            widget.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
        elif isinstance(widget, tk.OptionMenu):
            widget.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
            menu = widget["menu"]
            menu.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)




    def _force_theme_refresh(self, theme_colors):
        """Ensures all visible widgets follow the active theme."""
        bg = theme_colors["bg"]
        fg = theme_colors["fg"]

        try:
            self.status_text.configure(bg=bg, fg=fg)
        except (tk.TclError, AttributeError):
            pass

        # tutorial_box is a ttk card now; its colours come from Tutorial.TFrame
        # and Tutorial.TLabel, reapplied by the style pass above.

        try:
            self.title_bar.configure(bg=bg)
        except (tk.TclError, AttributeError):
            pass

        for widget in (getattr(self, "menu_bar", None), getattr(self, "export_bar", None),
                       getattr(self, "export_inner", None), getattr(self, "export_check_row", None)):
            if widget is not None:
                try:
                    widget.configure(bg=theme_colors["header_bg"])
                except tk.TclError:
                    pass

        self._update_all_widgets_recursive(self.root, bg=bg, fg=fg)
        self._paint_surfaces(theme_colors)

        # The log is a console, not a form field: it keeps the near-black
        # background the coloured status tags were chosen against. Set last,
        # because the blanket repaint above paints every tk.Text the page bg.
        log_bg, log_fg = getattr(self, "_status_colors", (None, None))
        if log_bg:
            try:
                self.status_text.configure(bg=log_bg, fg=log_fg)
            except (tk.TclError, AttributeError):
                pass

        self.draw_disc_meter()





    def _paint_surfaces(self, theme_colors):
        """Repaint widgets that live on the header/export surface, not the page.

        The recursive repaint below is a blunt instrument: it paints every tk
        widget the page background. Anything tagged _rialto_surface owns its own
        colour and is put back afterwards.
        """
        header_bg = theme_colors["header_bg"]
        fg = theme_colors["fg"]

        def walk(parent):
            for widget in parent.winfo_children():
                if getattr(widget, "_rialto_surface", None) == "header":
                    try:
                        if isinstance(widget, (tk.Label, tk.Menubutton)):
                            widget.configure(bg=header_bg, fg=fg)
                        else:
                            widget.configure(bg=header_bg)
                    except tk.TclError:
                        pass
                walk(widget)

        walk(self.root)

    def _update_all_widgets_recursive(self, parent, bg, fg):
        for widget in parent.winfo_children():
            try:
                widget_type = widget.winfo_class()
                kept = getattr(widget, "_rialto_style", None)
                if kept:
                    # Deliberately styled - BUILD, Step 1, the path label. The
                    # blanket reset below used to strip these back to plain
                    # TButton, which is why BUILD came out grey.
                    widget.configure(style=kept)
                elif widget_type in ["TButton", "TEntry", "TLabel", "TFrame", "TLabelFrame"]:
                    widget.configure(style="")  # Reset any previously applied style
                elif isinstance(widget, tk.Button) or isinstance(widget, tk.Label):
                    widget.configure(bg=bg, fg=fg)
                elif isinstance(widget, tk.Entry):
                    widget.configure(bg=bg, fg=fg, insertbackground=fg)
                elif isinstance(widget, tk.Text):
                    widget.configure(bg=bg, fg=fg)
                elif isinstance(widget, tk.OptionMenu):
                    widget.configure(bg=bg, fg=fg)
                    try:
                        widget["menu"].configure(bg=bg, fg=fg)
                    except tk.TclError:
                        pass
            except tk.TclError:
                pass
            self._update_all_widgets_recursive(widget, bg, fg)





    def art_start_dir(self):
        """Where a Browse dialog should open.

        The game folder once one is chosen - art almost always lives beside the
        game - then Rialto's own input folder, then Rialto's folder. Only a
        starting point: every dialog can still go anywhere on the PC.
        """
        if self.current_game_path and os.path.isdir(self.current_game_path):
            return self.current_game_path
        return INPUT_DIR if os.path.exists(INPUT_DIR) else APP_ROOT

    def select_game_folder(self):
        path = filedialog.askdirectory(initialdir=self.art_start_dir() or INPUT_DIR)
        if path:
            self.current_game_path = path
            if hasattr(self, "game_path_var"):
                self.game_path_var.set(path)
            self.update_status(f"📁 Game folder: {path}")
            # Paths chosen against the old game folder follow it here.
            self.rebase_stale_paths()
            self.refresh_disc_meter()


    def browse_bg(self):
        initial_dir = self.art_start_dir()

        # Video is not offered: see VIDEO_EXTENSIONS for why the disc menu
        # refuses it. Someone can still type a path to one, so the choice is
        # checked below as well as filtered here.
        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[
                ("Backgrounds", "*.gif;*.jpg;*.jpeg;*.png"),
                ("Animated GIF", "*.gif"),
                ("Still image", "*.jpg;*.jpeg;*.png"),
                ("All Files", "*.*")
            ]
        )
        if file:
            ext = os.path.splitext(file)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                self.show_centered_popup(
                    "Video backgrounds are not supported",
                    "A video only plays where the player's own copy of Windows can "
                    "decode it, and a disc cannot be fixed once it is made.\n\n"
                    "An animated GIF is decoded by the menu itself, so it looks the "
                    "same on every machine. A still JPG works too.")
                return
            self.bg_path_var.set(file)
            if ext == '.gif':
                self.update_status(f"✅ Selected animated GIF background: {os.path.basename(file)}")
            else:
                self.update_status(f"✅ Selected image background: {os.path.basename(file)}")
            self.refresh_disc_meter()

    def browse_logo(self):
        """Browse for game logo PNG file"""
        initial_dir = self.art_start_dir()

        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[
                ("PNG Images", "*.png"),
                ("All Files", "*.*")
            ]
        )
        if file:
            self.logo_path_var.set(file)
            self.update_status(f"✅ Selected game logo: {os.path.basename(file)}")

    def browse_company_logo(self):
        """Browse for company logo PNG file"""
        initial_dir = self.art_start_dir()

        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[
                ("PNG Images", "*.png"),
                ("All Files", "*.*")
            ]
        )
        if file:
            self.company_logo_var.set(file)
            self.update_status(f"✅ Selected company logo: {os.path.basename(file)}")

    def browse_ico(self):
        file = filedialog.askopenfilename(
            title="Select Game Icon",
            initialdir=self.art_start_dir(),
            filetypes=[("Icon", "*.ico")]
        )
        if file:
            # Deliberately does not fill in Disc Icon. The two are usually the
            # same file and it is one extra click to say so, but a disc that
            # wants its own art had no way to ask for it once the copy had
            # already happened.
            self.ico_path_var.set(file)
            self.update_status(f"✅ Selected game icon: {os.path.basename(file)}")
            self.refresh_disc_meter()

    def browse_disc_icon(self):
        file = filedialog.askopenfilename(
            title="Select Disc Icon",
            initialdir=self.art_start_dir(),
            filetypes=[("Icon", "*.ico")]
        )
        if file:
            self.disc_icon_var.set(file)
            self.update_status(f"✅ Selected disc icon: {os.path.basename(file)}")
            self.refresh_disc_meter()

    def save_signing_settings(self):
        """Save signing settings to config"""
        if not hasattr(self, 'config'):
            self.config = {}
        
        self.config["sign_final_build"] = self.sign_final_build.get()
        self.config["remove_wti_branding"] = self.remove_wti_branding.get()
        self.config["mod_launcher"] = self.mod_launcher_var.get()

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def build_all(self):
        """Every build step, from copying the game to the finished ISO."""
        if not self.current_game_path:
            self.update_status("❌ Error: Game path not selected.")
            return

        game_name = os.path.basename(self.current_game_path)
        output_path = safe(os.path.abspath(os.path.join(OUTPUT_DIR, game_name)))
        os.makedirs(output_path, exist_ok=True)

        # Cleared per build so a warning from an earlier one never haunts this
        # summary; create_spanned_isos refills it if a disc comes out oversized.
        self.disc_overflow_warnings = []

        try:
            # 0. Clear the previous run's disc image out of the way. Inno now
            # excludes *.iso from the payload, but leaving a 900 MB file from
            # last time sitting in the build folder helps nobody.
            for stale in glob.glob(os.path.join(output_path, "*.iso")):
                try:
                    os.remove(stale)
                    self.update_status(f"🧹 Cleared the previous disc image: {os.path.basename(stale)}")
                except OSError:
                    pass

            # 1. Copy runtime dependencies
            self.update_status("Copying runtime dependencies...")
            self.copy_runtime_dependencies(output_path)
            self.create_runtime_installer_helper(output_path)
        
            # 2. Copy game files
            self.update_status("Copying game files...")
            game_files_copied = self.copy_game_files_to_output(self.current_game_path, output_path)
            if not game_files_copied:
                self.update_status("⚠️ Warning: No game files copied")

            # 3. Collect metadata
            meta = {k: self.entries[k].get().strip() for k in self.entries}
            meta["GameName"] = game_name
            meta["Background"] = self.bg_path_var.get()
            meta["Logo"] = self.logo_path_var.get()
            meta["CompanyLogo"] = self.company_logo_var.get()
            meta["PublisherText"] = self.publisher_text_var.get()
            meta["Icon"] = self.ico_path_var.get()
            meta["InstallPath"] = f"C:\\Games\\{game_name}"

            # 3.5. Stage the mods folder (optional) - must happen before the menu
            # config is written and before ISCC snapshots the folder for {app}
            self.stage_mod_launcher(self.current_game_path, output_path)

            # 3.6. Stage bonus content, for the same reason: a bonus folder
            # picked in Disc Extras can live anywhere, and ISCC only sees what
            # is in the output folder when it runs.
            self.update_status("Copying bonus content...")
            self.build_bonus_gallery(self.current_game_path, output_path,
                                     self.resolved_bonus_dir() or None)

            # 4. Stage the disc menu
            self.update_status("Compiling menu systems...")
            self.compile_menu_launcher(output_path)

            # 5. Write installer script
            self.update_status("Writing installer script...")
            self.generate_enhanced_installer_script(output_path, meta)

            # 6. Compile the installer (stops the build if none is made)
            self.update_status("Compiling installer with ISCC...")
            self.compile_installer_with_iscc(output_path)
            
            # 6.1. Add security attributes to reduce false positives
            self.enhance_installer_security(output_path)

            # 7. Build extras
            self.generate_readme(output_path, meta)
            
            # 8. Create autorun.inf with proper disc icon
            # (generate_autorun logs the step itself; saying it twice was noise)
            self.generate_autorun(output_path)
        
            # 9. Create compatibility test
            self.update_status("Creating compatibility test...")
            self.create_compatibility_test_script(output_path)

            # 9.5. Universal Disc: stage Mac and Linux builds for the disc (optional)
            self.stage_universal_builds(output_path)

            # 10. Create ISO
            self.update_status("Creating ISO image...")
            self.create_iso(output_path, meta)

            # 10.5. USB export (optional) - must run before cleanup deletes the disc files
            if self.usb_export_var.get():
                self.export_usb_fileset(output_path, meta)

            # 11. Clean output folder
            self.update_status("Cleaning output folder...")
            self.clean_output_folder_final(output_path, keep_mode="iso")

            # 12. Complete
            self.log_build_event(meta, output_path, success=True)
            self.update_status("✅ Build complete!")
            # Repeat any oversized-disc warning here: the ISO step may have
            # scrolled far up the status log by now, and this is the last thing
            # the author reads before they go and burn the set.
            overflow = getattr(self, "disc_overflow_warnings", [])
            for line in overflow:
                self.update_status(line)
            self.play_completion_jingle()
            done_message = f"Build complete for {game_name}"
            if overflow:
                # The popup stays short, so it points at the log
                # rather than trying to hold the full per-disc breakdown.
                done_message += "\n\n⚠️ At least one disc is larger than your target media - see the status log."
            self.show_centered_popup("Done", done_message)

        except Exception as e:
            self.update_status(f"❌ Build failed: {e}")
            self.update_status(f"Traceback: {traceback.format_exc()}")








    def run_preflight_check(self):
        issues = []

        # The game folder is the one Browse picked. It can live anywhere;
        # this used to insist on input\\<title without spaces>.
        game_path = getattr(self, "current_game_path", "") or ""
        background_path = self.bg_path_var.get().strip()
        icon_path = self.ico_path_var.get().strip()

        if not os.path.isdir(game_path):
            issues.append("Choose your game folder first (Browse for your game folder).")

        # Check files
        if not os.path.isfile(background_path):
            issues.append("Missing menu background: pick an animated GIF or a still image.")
        if not os.path.isfile(icon_path):
            issues.append("Missing game icon: pick an .ico file.")

        # Check metadata fields
        missing_fields = []
        if not self.entries["Title"].get().strip():
            missing_fields.append("Game Title")
        if not self.entries["Developer"].get().strip():
            missing_fields.append("Developer")
        if not self.entries["Start Menu Name"].get().strip():
            missing_fields.append("Start Menu Name")

        if missing_fields:
            issues.append("Missing metadata fields: " + ", ".join(missing_fields))

        if issues:
            self.show_centered_popup("Preflight Check Failed", "\n".join(issues))
            return False
        else:
            self.show_centered_popup("Preflight Check Passed", "All required files and metadata are present.")
            return True








    # Folders under the install root that hold executables which are never the
    # game. Kept beside HELPER_EXE_NAMES because they answer the same question.
    NON_GAME_DIRS = {"menu", "bonus", "mods", "runtime", "redist", "redistributables",
                     "_commonredist", "directx", "dotnet"}

    @staticmethod
    def _name_key(value):
        """A filename or title reduced to just its letters and digits."""
        return "".join(c for c in str(value or "").lower() if c.isalnum())

    def _title_key(self):
        """The game's title in comparable form, or "" if there isn't one yet."""
        try:
            return self._name_key(self.entries["Title"].get())
        except (AttributeError, KeyError, TypeError):
            return ""

    def detect_primary_game_exe(self, root_path):
        """The exe PLAY should start, as a path relative to the install root.

        Decided at build time, on the machine that has the whole staged folder
        in front of it, and written into menu_config.json. The disc menu still
        has a runtime fallback, but it should never need it - and a menu that
        has to guess is what produced a "Game executable not found!" report
        that could not be reproduced afterwards.

        game.exe at the root wins if it is there, then any other real exe at
        the root, then the biggest exe within three folders. That last rule is
        what finds an Unreal game, whose root game.exe is a small shim and
        whose actual binary lives four levels down in Binaries/Win64 - and if
        the shim is present it is preferred anyway, because it is the entry
        point the engine expects to be launched.
        """
        if not root_path or not os.path.isdir(root_path):
            return ""

        def is_helper(name):
            low = name.lower()
            if not low.endswith(".exe"):
                return True
            if low in self.HELPER_EXE_NAMES:
                return True
            return ('browsersubprocess' in low
                    or low.startswith(('cefsharp', 'unitycrashhandler', 'vcredist',
                                       'vc_redist', 'unins')))

        try:
            entries = sorted(os.listdir(root_path))
        except OSError:
            return ""

        for name in entries:
            # The real filename, not the literal "game.exe": RPG Maker ships
            # Game.exe, and writing a name the folder does not contain works
            # only for as long as nobody reads the config on a case-sensitive
            # filesystem.
            if name.lower() == "game.exe" and os.path.isfile(os.path.join(root_path, name)):
                return name

        # More than one exe at the root is normal - a launcher, the game, a
        # level editor. Alphabetical order used to decide it, which picked
        # "Launcher.exe" over a 120 MB "MyGame.exe" for no better reason than
        # L before M. The title the author typed is a far better signal, and
        # size breaks the tie after that.
        candidates = [n for n in entries
                      if not is_helper(n) and os.path.isfile(os.path.join(root_path, n))]
        if candidates:
            wanted = self._title_key()
            if wanted:
                for name in candidates:
                    if self._name_key(os.path.splitext(name)[0]) == wanted:
                        return name
            if len(candidates) == 1:
                return candidates[0]

            def size_of(name):
                try:
                    return os.path.getsize(os.path.join(root_path, name))
                except OSError:
                    return 0
            return max(candidates, key=size_of)

        best, best_size = "", -1
        for dirpath, dirnames, filenames in os.walk(root_path):
            rel_dir = os.path.relpath(dirpath, root_path)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth >= 3:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d.lower() not in self.NON_GAME_DIRS]
            for name in filenames:
                if is_helper(name):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if size > best_size:
                    best_size = size
                    best = os.path.relpath(full, root_path).replace("\\", "/")
        return best

    def build_menu_config(self, root_path):
        """Everything the disc menu needs to know about this title, as a dict.

        The one description of a per-title menu. menu.exe is generic and reads
        this file at startup, so anything that used to be compiled in has to
        appear here - including the title, which drives the window caption, the
        on-screen title when there is no logo, and the taskbar identity.

        `root_path` is the install root (the folder menu/ sits inside), because
        the mod launcher is detected by looking at what was staged there.
        """
        company_logo_path = self.company_logo_var.get().strip()
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        compat_args = split_launch_args(self.compat_args_var.get()) if self.compat_mode_var.get() else []
        mod_exe = self.detect_mod_launcher_exe(root_path) if self.mod_launcher_var.get() else ""
        return {
            # Window title and the on-screen title. Used to be baked into a
            # per-game menu.exe; now it rides in the config like everything else.
            "title": meta.get("Title", "").strip() or "Game",
            "company_logo": "company_logo.png" if company_logo_path and os.path.exists(company_logo_path) else "",
            # White label takes We the Indies out of the copyright line too,
            # not only off the artwork.
            "copyright_text": (strip_wti_mentions(self.publisher_text_var.get())
                               if self.remove_wti_branding.get()
                               else self.publisher_text_var.get().strip()),
            "language": "English",
            "remove_wti_branding": self.remove_wti_branding.get(),
            # Multi-game disc support: entries the disc menu offers as PLAY choices
            "games": self.validated_game_executables(),
            # Single-game discs: the exe PLAY should start, decided here where
            # the whole staged folder is visible, rather than guessed at by the
            # menu on the player's machine.
            "game_exe": self.detect_primary_game_exe(root_path),
            # Show an ADD TO STEAM button in the installed menu
            "steam_button": bool(self.steam_button_var.get()),
            # MODS button: runs the tool inside the staged mod folder. The flag
            # follows the tool, not the tick box - a disc shipped saying the
            # button was on while pointing at a file that had never existed.
            "mod_launcher": bool(self.mod_launcher_var.get()) and bool(mod_exe),
            "mod_exe": mod_exe,
            # Compatibility mode: a second PLAY that adds the author's own
            # launch argument. The menu shows the button only when there are
            # arguments here that still pass its own checks.
            "compat_mode": bool(self.compat_mode_var.get()) and bool(compat_args),
            "compat_args": compat_args,
            # What the button's tooltip says. Empty means the menu uses its
            # own translated wording instead.
            "compat_hint": sanitize_text(self.compat_hint_var.get()).strip()[:200]
        }

    def write_menu_config(self, menu_dir, root_path):
        """Write menu_config.json into the staged menu folder."""
        config_path = os.path.join(menu_dir, "menu_config.json")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.build_menu_config(root_path), f, indent=2)
            return True
        except OSError as e:
            self.update_status(f"⚠️ Failed to create menu config: {e}")
            return False

    def compile_menu_launcher(self, output_path):
        """Stage the disc menu: artwork, config, the executable, and fallbacks."""
        menu_dir = os.path.join(output_path, "menu")
        os.makedirs(menu_dir, exist_ok=True)

        # 1. Stage the per-title artwork the menu reads at runtime
        self.stage_menu_artwork(menu_dir)
        self.update_status("✅ Staged menu artwork")

        # 1.5. Library art for ADD TO STEAM, if that button is on
        if self.steam_button_var.get():
            self.stage_steam_art(menu_dir)

        # 2. Copy company logo if specified
        company_logo_path = self.company_logo_var.get().strip()
        if company_logo_path and os.path.exists(company_logo_path):
            logo_dest = os.path.join(menu_dir, "company_logo.png")
            try:
                shutil.copy2(company_logo_path, logo_dest)
                self.update_status("✅ Copied company logo")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy company logo: {e}")
        elif company_logo_path:
            self.update_status(f"⚠️ Company logo not found, building without one: {company_logo_path}")

        # 3. Create menu configuration file
        if self.write_menu_config(menu_dir, output_path):
            self.update_status("✅ Created menu configuration")

        # 4. Copy the background (GIF or still image) to the menu folder
        bg_source = self.bg_path_var.get()
        if bg_source and os.path.exists(bg_source):
            ext = os.path.splitext(bg_source)[1].lower()
            if ext == '.gif':
                bg_dest = os.path.join(menu_dir, "background.gif")
            elif ext in VIDEO_EXTENSIONS:
                bg_dest = None  # refused in stage_menu_artwork; never put on a disc
            else:
                bg_dest = os.path.join(menu_dir, "background.jpg")
            try:
                if bg_dest:
                    shutil.copy2(bg_source, bg_dest)
                    self.update_status("✅ Copied background to menu")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy background: {e}")
        
        # 5. Put menu.exe in place
        self.stage_menu_executable(output_path)

        # 6. Create batch file fallback (always works)
        self.create_batch_menu_fallback(output_path)
        
        # 7. Create menu selector script
        self.create_menu_selector(output_path)
        
        return True  # Always return True since we have fallbacks





    def enhance_installer_security(self, output_path):
        """Add security attributes to reduce false positives"""
        setup_path = os.path.join(output_path, "setup.exe")
        
        if os.path.exists(setup_path):
            try:
                # Create security info file
                security_info = os.path.join(output_path, "SECURITY_INFO.txt")
                with open(security_info, "w", encoding="utf-8") as f:
                    f.write("SECURITY INFORMATION\n")
                    f.write("=" * 50 + "\n\n")
                    f.write("This installer was created with Rialto Disc Builder\n")
                    f.write("Installer Type: Inno Setup\n")
                    f.write("Source: Legitimate game distribution\n")
                    f.write("False Positive: Common with unsigned executables\n\n")
                    f.write("To verify authenticity:\n")
                    f.write("1. Check file properties for version info\n")
                    f.write("2. Scan with multiple antivirus engines\n")
                    f.write("3. Consider code signing for production releases\n\n")
                    f.write("For code signing support, use Configure Signing in Rialto (see SIGNING.md)\n")
                
                # Log security enhancement
                self.update_status("✅ Added security documentation")

                # Read the signature back rather than assuming. This line used
                # to say "Installer is unsigned" unconditionally, which meant a
                # build that had just signed setup.exe successfully finished by
                # telling the author it had not.
                try:
                    import ssl_signing
                    signed = ssl_signing.is_signed(setup_path)
                except Exception:
                    signed = None

                if signed is True:
                    self.update_status("✅ setup.exe carries your signature")
                elif signed is False:
                    self.update_status("ℹ️ setup.exe is unsigned. Tick Sign Final Build to sign it.")
                # signed is None: no signtool to ask, so say nothing rather than
                # guess in either direction.

            except Exception as e:
                self.update_status(f"⚠️ Security enhancement failed: {e}")

    def compile_installer_with_iscc(self, output_path):
        """Compile the installer with ISCC, then sign setup.exe if Sign Final Build is ticked.

        Raises when no setup.exe was made: a disc without its installer has
        nothing to install, so the build stops instead of ending in Build complete.
        """
        original_iss_path = os.path.join(output_path, "installer.iss")
        
        # Use original .iss file (signing happens after compilation now)
        iss_path = original_iss_path
        
        if self.sign_final_build.get():
            self.update_status("Compiling installer (signing enabled)...")
        else:
            self.update_status("Compiling installer...")
        
        # ISCC.exe from Inno Setup 6: PATH, then either install mode's folder
        iscc = find_inno_compiler()
        problem = None

        if iscc:
            try:
                command = [iscc, iss_path]
                # An hour: a Blu-ray-sized game can take well over five minutes to
                # compress, and a timeout now stops the build.
                result = subprocess.run(command, cwd=output_path, capture_output=True, text=True, timeout=3600)
                
                if result.returncode == 0:
                    setup_path = os.path.join(output_path, "setup.exe")
                    if os.path.exists(setup_path):
                        self.update_status(f"Installer compiled: {os.path.basename(setup_path)}")
                        
                        # Sign setup.exe if requested (must happen here, before ISO packaging)
                        if self.sign_final_build.get():
                            signed = False
                            try:
                                import trusted_signing
                                if trusted_signing.is_configured():
                                    ok, message = trusted_signing.sign_file(setup_path, self.update_status)
                                    self.update_status(("✅ " if ok else "⚠️ ") + message)
                                    signed = ok
                                else:
                                    self.update_status("ℹ️ Automatic signing not set up yet (see the Configure Signing button)")
                            except Exception as e:
                                self.update_status(f"⚠️ Signing error: {e}")

                            if signed:
                                try:
                                    import ssl_signing
                                    self.update_status(f"🔍 Verification: {ssl_signing.verify_signature(setup_path)}")
                                except Exception:
                                    pass
                            else:
                                # Classic manual pause: sign with any service, then continue
                                self.update_status("🔐 Ready for manual code signing...")
                                self.update_status(f"📁 Files to sign are in: {output_path}")

                                import tkinter.messagebox as msgbox
                                result = msgbox.askokcancel(
                                    "Code Signing Pause",
                                    f"Automatic signing was skipped or failed.\n\n"
                                    f"Files location: {output_path}\n\n"
                                    f"Steps:\n"
                                    f"1. Sign setup.exe with your signing provider\n"
                                    f"2. Replace the original setup.exe in the build folder\n"
                                    f"3. Click OK to continue with ISO packaging\n\n"
                                    f"Click Cancel to skip signing and continue."
                                )

                                if result:
                                    self.update_status("✅ Continuing with signed files...")
                                else:
                                    self.update_status("⏭️ Skipping code signing, continuing build...")
                        
                        # Not the end of the build - only the end of the
                        # installer step. Saying "Build complete" here, with
                        # the ISO still to come, read like the run had finished.
                        self.update_status("✅ Installer step done")
                    else:
                        problem = "ISCC ran but setup.exe is missing"
                        self.update_status("⚠️ ISCC ran but setup.exe is missing.")
                else:
                    problem = "ISCC failed"
                    self.update_status(f"❌ ISCC failed: {result.stderr}")
                    
                    
            except subprocess.TimeoutExpired:
                problem = "ISCC ran for an hour without finishing"
                self.update_status("❌ ISCC ran for an hour without finishing")
            except Exception as e:
                problem = "ISCC could not be run"
                self.update_status(f"❌ Error running ISCC: {e}")
        elif inno_setup_7_only():
            problem = "Rialto 1.5 needs Inno Setup 6"
            self.update_status("⚠️ Found Inno Setup 7, but Rialto 1.5 builds with Inno Setup 6. "
                               "Install Inno Setup 6 as well (the two sit side by side): " + INNO_SETUP_DOWNLOAD)
        else:
            problem = "Inno Setup 6 was not found"
            self.update_status("⚠️ ISCC.exe not found. Cannot create setup.exe. Download Inno Setup 6: " + INNO_SETUP_DOWNLOAD)

        if problem:
            raise RuntimeError(f"No installer was made ({problem}), so the build was stopped.")




    def copy_runtime_dependencies(self, output_path):
        """Copy essential runtime libraries for maximum compatibility"""
        
        # First, try to copy the redistributable installers
        runtime_files = {
            "vcredist_x64.exe": [
                r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x64.exe",
                r"C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x64.exe"
            ],
            "vcredist_x86.exe": [
                r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x86.exe",
                r"C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x86.exe"
            ]
        }
        
        copied_runtimes = 0
        missing = []

        for runtime_name, possible_paths in runtime_files.items():
            runtime_copied = False
            
            for source_path in possible_paths:
                if os.path.exists(source_path):
                    try:
                        dest_path = os.path.join(output_path, runtime_name)
                        shutil.copy2(source_path, dest_path)
                        if not self._accept_microsoft_runtime(dest_path, runtime_name):
                            continue
                        self.update_status(f"✅ Copied runtime: {runtime_name}")
                        copied_runtimes += 1
                        runtime_copied = True
                        break
                    except Exception as e:
                        self.update_status(f"⚠️ Failed to copy {runtime_name}: {e}")
            
            if not runtime_copied:
                missing.append(runtime_name)

        # Also copy the actual DLL files that the game needs
        self.copy_vcruntime_dlls(output_path)

        if copied_runtimes == 0:
            # Not a warning. Not having a copy of the Visual C++ redistributable
            # lying around on your PC is the normal case; Rialto fetches it.
            self.update_status("ℹ️ No local copy of the Visual C++ redistributable, fetching it")
            self.download_essential_runtimes(output_path)
        elif missing:
            self.update_status(f"ℹ️ Not found locally: {', '.join(missing)}")
        
        return copied_runtimes > 0

    def _accept_microsoft_runtime(self, dest_path, filename):
        """Keep a redistributable only if it carries a Microsoft Authenticode signature.

        Returns True if the file is trusted and may be packaged. Otherwise the
        file is deleted and the caller continues without it - never let an
        unverified runtime reach the Inno [Files] stage, because that binary
        is then copied into setup.exe and Authenticode-signed by the author.
        """
        import trusted_signing
        trusted = trusted_signing.signed_by_microsoft(dest_path)
        if trusted is True:
            return True
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        if trusted is None:
            self.update_status(
                f"⚠️ Could not verify {filename}: signtool.exe was not found. "
                f"The file was discarded and the build continues without it. "
                f"Players will be pointed at the official Microsoft download.")
        else:
            self.update_status(
                f"⚠️ {filename} is not a Microsoft-signed binary. "
                f"The file was discarded and the build continues without it. "
                f"Players will be pointed at the official Microsoft download.")
        return False

    def copy_vcruntime_dlls(self, output_path):
        """Copy Visual C++ runtime DLLs directly to output folder"""
        required_dlls = [
            "msvcp140.dll",
            "msvcp140_1.dll",
            "msvcp140_2.dll",
            "vcruntime140.dll",
            "vcruntime140_1.dll",
            "concrt140.dll",
            "vccorlib140.dll"
        ]
        
        # Common locations for VC++ runtime DLLs
        dll_sources = [
            "C:\\Windows\\System32",
            "C:\\Windows\\SysWOW64",
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft Visual Studio\\2019\\Community\\VC\\Redist\\MSVC\\14.29.30133\\x64\\Microsoft.VC142.CRT"),
            os.path.join(sys.prefix, "DLLs"),
            os.path.dirname(sys.executable)
        ]
        
        copied_count = 0
        for dll in required_dlls:
            dll_found = False
            for source in dll_sources:
                source_path = os.path.join(source, dll)
                if os.path.exists(source_path):
                    try:
                        # Copy to main output directory
                        shutil.copy2(source_path, os.path.join(output_path, dll))
                        # Also copy to menu directory
                        menu_dir = os.path.join(output_path, "menu")
                        if os.path.exists(menu_dir):
                            shutil.copy2(source_path, os.path.join(menu_dir, dll))
                        self.update_status(f"✅ Copied {dll}")
                        dll_found = True
                        copied_count += 1
                        break
                    except OSError:
                        pass
            
            if not dll_found:
                self.update_status(f"⚠️ Could not find {dll}")
        
        self.update_status(f"✅ Copied {copied_count} runtime DLLs")





    def download_essential_runtimes(self, output_path):
        """Download essential runtimes if not found locally"""
        downloads = {
            "vcredist_x64.exe": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
            "vcredist_x86.exe": "https://aka.ms/vs/17/release/vc_redist.x86.exe"
        }
        
        for filename, url in downloads.items():
            dest_path = os.path.join(output_path, filename)
            try:
                self.update_status(f"⬇️ Downloading {filename}...")
                
                from update.fetch import FetchProblem, fetch_to_file
                try:
                    fetch_to_file(url, dest_path,
                                  hosts={"aka.ms", "download.visualstudio.microsoft.com",
                                         "download.microsoft.com"},
                                  cap=64 * 1024 * 1024)
                except FetchProblem as problem:
                    self.update_status(f"❌ Download failed: {filename}. {problem}")
                    continue
                
                if not (os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024):
                    self.update_status(f"❌ Download failed: {filename}")
                    try:
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                    except OSError:
                        pass
                    continue

                if self._accept_microsoft_runtime(dest_path, filename):
                    self.update_status(f"✅ Downloaded {filename} (Microsoft-signed)")
                    
            except Exception as e:
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                except OSError:
                    pass
                self.update_status(f"❌ Download error for {filename}: {e}")




    def generate_enhanced_installer_script(self, output_path, meta):
        """Generate the enhanced installer script with maximum compatibility"""
        # Everything here is concatenated into installer.iss, which ISCC
        # compiles into the setup.exe Rialto signs - so it all goes through
        # iss_value() first. Two flavours: app_name is what the installer
        # displays, so it keeps punctuation like the colon in "Game: Subtitle";
        # path_name additionally loses the characters that would move a folder
        # or a registry key, and is used wherever the title becomes one.
        app_name = iss_value(meta.get('Title'), 'Game')
        path_name = iss_value(meta.get('Title'), 'Game', for_path=True)
        app_version = "1.0"
        publisher = iss_value(meta.get('Developer'), 'Indie Developer')
        install_path = f"C:\\Games\\{path_name}"
        start_menu = iss_value(meta.get('Start Menu Name'), path_name, for_path=True)
        output_filename = "setup"
        
        # Copy icon if exists
        icon_file = meta.get("Icon", "")
        copied_icon_path = ""
        if icon_file and os.path.exists(icon_file):
            try:
                copied_icon_path = os.path.join(output_path, "game_icon.ico")
                shutil.copy2(icon_file, copied_icon_path)
                self.update_status("✅ Copied game icon")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy icon: {e}")
        elif icon_file:
            self.update_status(f"⚠️ Game icon not found, the installer will use the default: {icon_file}")

        # Build installer script
        iss_script = "[Setup]\n"
        iss_script += f"AppName={app_name}\n"
        iss_script += f"AppVersion={app_version}\n"
        iss_script += f"AppPublisher={publisher}\n"
        iss_script += f"DefaultDirName={install_path}\n"
        iss_script += f"DefaultGroupName={start_menu}\n"
        iss_script += f"OutputBaseFilename={output_filename}\n"
        iss_script += "OutputDir=.\n"
        iss_script += "SolidCompression=no\n"
        iss_script += "DiskSpanning=yes\n"
        # When a target disc size is chosen, cap installer slices so a too-big
        # game splits into setup-*.bin parts that Rialto can spread across discs
        slice_size = self.get_disk_slice_size()
        if slice_size:
            iss_script += f"DiskSliceSize={slice_size}\n"
        iss_script += "Compression=lzma2/fast\n"
        iss_script += "InternalCompressLevel=fast\n"
        iss_script += "DisableWelcomePage=no\n"
        iss_script += "DisableReadyPage=yes\n"
        iss_script += "UsePreviousAppDir=yes\n"
        iss_script += "ShowLanguageDialog=yes\n"  # Enable language selection dialog
        
        if copied_icon_path:
            iss_script += f"SetupIconFile={copied_icon_path}\n"
        
        iss_script += "UninstallDisplayIcon={app}\\game_icon.ico\n"
        iss_script += "UninstallFilesDir={app}\n"
        iss_script += f"UninstallDisplayName={app_name}\n"
        iss_script += "CreateUninstallRegKey=yes\n"
        iss_script += "PrivilegesRequired=lowest\n"
        iss_script += "PrivilegesRequiredOverridesAllowed=dialog commandline\n"
        iss_script += "MinVersion=6.1\n"
        iss_script += "ArchitecturesAllowed=x86 x64\n"
        iss_script += "DisableDirPage=auto\n"
        iss_script += "DisableProgramGroupPage=no\n"
        iss_script += "ChangesAssociations=no\n"
        iss_script += "RestartIfNeededByRun=no\n"
        
        # Languages section - ONLY languages with official Inno Setup translations
        iss_script += "\n[Languages]\n"
        iss_script += 'Name: "english"; MessagesFile: "compiler:Default.isl"\n'
        iss_script += 'Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\\BrazilianPortuguese.isl"\n'
        iss_script += 'Name: "catalan"; MessagesFile: "compiler:Languages\\Catalan.isl"\n'
        iss_script += 'Name: "czech"; MessagesFile: "compiler:Languages\\Czech.isl"\n'
        iss_script += 'Name: "danish"; MessagesFile: "compiler:Languages\\Danish.isl"\n'
        iss_script += 'Name: "dutch"; MessagesFile: "compiler:Languages\\Dutch.isl"\n'
        iss_script += 'Name: "finnish"; MessagesFile: "compiler:Languages\\Finnish.isl"\n'
        iss_script += 'Name: "french"; MessagesFile: "compiler:Languages\\French.isl"\n'
        iss_script += 'Name: "german"; MessagesFile: "compiler:Languages\\German.isl"\n'
        iss_script += 'Name: "hebrew"; MessagesFile: "compiler:Languages\\Hebrew.isl"\n'
        iss_script += 'Name: "italian"; MessagesFile: "compiler:Languages\\Italian.isl"\n'
        iss_script += 'Name: "japanese"; MessagesFile: "compiler:Languages\\Japanese.isl"\n'
        iss_script += 'Name: "norwegian"; MessagesFile: "compiler:Languages\\Norwegian.isl"\n'
        iss_script += 'Name: "polish"; MessagesFile: "compiler:Languages\\Polish.isl"\n'
        iss_script += 'Name: "portuguese"; MessagesFile: "compiler:Languages\\Portuguese.isl"\n'
        iss_script += 'Name: "russian"; MessagesFile: "compiler:Languages\\Russian.isl"\n'
        iss_script += 'Name: "slovak"; MessagesFile: "compiler:Languages\\Slovak.isl"\n'
        iss_script += 'Name: "slovenian"; MessagesFile: "compiler:Languages\\Slovenian.isl"\n'
        iss_script += 'Name: "spanish"; MessagesFile: "compiler:Languages\\Spanish.isl"\n'
        iss_script += 'Name: "turkish"; MessagesFile: "compiler:Languages\\Turkish.isl"\n'
        iss_script += 'Name: "ukrainian"; MessagesFile: "compiler:Languages\\Ukrainian.isl"\n'
        
        # Custom messages for supported languages
        iss_script += "\n[CustomMessages]\n"
        
        # English
        iss_script += "english.SelectDirLabel=Select the folder where {#SetupSetting(\"AppName\")} should be installed, then click Next.\n"
        iss_script += "english.LaunchProgram=Launch {#SetupSetting(\"AppName\")}\n"
        
        # Brazilian Portuguese
        iss_script += "brazilianportuguese.SelectDirLabel=Selecione a pasta onde {#SetupSetting(\"AppName\")} deve ser instalado e clique em Avançar.\n"
        iss_script += "brazilianportuguese.LaunchProgram=Executar {#SetupSetting(\"AppName\")}\n"
        
        # Catalan
        iss_script += "catalan.SelectDirLabel=Seleccioneu la carpeta on s'ha d'instal·lar {#SetupSetting(\"AppName\")}, després feu clic a Següent.\n"
        iss_script += "catalan.LaunchProgram=Executar {#SetupSetting(\"AppName\")}\n"
        
        # Czech
        iss_script += "czech.SelectDirLabel=Vyberte složku, kam má být {#SetupSetting(\"AppName\")} nainstalován, a klikněte na Další.\n"
        iss_script += "czech.LaunchProgram=Spustit {#SetupSetting(\"AppName\")}\n"
        
        # Danish
        iss_script += "danish.SelectDirLabel=Vælg den mappe, hvor {#SetupSetting(\"AppName\")} skal installeres, og klik på Næste.\n"
        iss_script += "danish.LaunchProgram=Start {#SetupSetting(\"AppName\")}\n"
        
        # Dutch
        iss_script += "dutch.SelectDirLabel=Selecteer de map waarin {#SetupSetting(\"AppName\")} moet worden geïnstalleerd en klik op Volgende.\n"
        iss_script += "dutch.LaunchProgram={#SetupSetting(\"AppName\")} starten\n"
        
        # Finnish
        iss_script += "finnish.SelectDirLabel=Valitse kansio, johon {#SetupSetting(\"AppName\")} asennetaan, ja napsauta Seuraava.\n"
        iss_script += "finnish.LaunchProgram=Käynnistä {#SetupSetting(\"AppName\")}\n"
        
        # French
        iss_script += "french.SelectDirLabel=Sélectionnez le dossier où {#SetupSetting(\"AppName\")} doit être installé, puis cliquez sur Suivant.\n"
        iss_script += "french.LaunchProgram=Lancer {#SetupSetting(\"AppName\")}\n"
        
        # German
        iss_script += "german.SelectDirLabel=Wählen Sie den Ordner aus, in dem {#SetupSetting(\"AppName\")} installiert werden soll, und klicken Sie auf Weiter.\n"
        iss_script += "german.LaunchProgram={#SetupSetting(\"AppName\")} starten\n"
        
        # Hebrew
        iss_script += "hebrew.SelectDirLabel=בחר את התיקייה שבה יותקן {#SetupSetting(\"AppName\")}, ולאחר מכן לחץ על הבא.\n"
        iss_script += "hebrew.LaunchProgram=הפעל את {#SetupSetting(\"AppName\")}\n"
        
        # Italian
        iss_script += "italian.SelectDirLabel=Seleziona la cartella dove {#SetupSetting(\"AppName\")} deve essere installato, quindi clicca Avanti.\n"
        iss_script += "italian.LaunchProgram=Avvia {#SetupSetting(\"AppName\")}\n"
        
        # Japanese
        iss_script += "japanese.SelectDirLabel={#SetupSetting(\"AppName\")} をインストールするフォルダを選択して、次へをクリックしてください。\n"
        iss_script += "japanese.LaunchProgram={#SetupSetting(\"AppName\")} を起動\n"
        
        # Norwegian
        iss_script += "norwegian.SelectDirLabel=Velg mappen hvor {#SetupSetting(\"AppName\")} skal installeres, og klikk på Neste.\n"
        iss_script += "norwegian.LaunchProgram=Start {#SetupSetting(\"AppName\")}\n"
        
        # Polish
        iss_script += "polish.SelectDirLabel=Wybierz folder, w którym ma zostać zainstalowany {#SetupSetting(\"AppName\")}, a następnie kliknij Dalej.\n"
        iss_script += "polish.LaunchProgram=Uruchom {#SetupSetting(\"AppName\")}\n"
        
        # Portuguese
        iss_script += "portuguese.SelectDirLabel=Selecione a pasta onde {#SetupSetting(\"AppName\")} deve ser instalado e clique em Seguinte.\n"
        iss_script += "portuguese.LaunchProgram=Executar {#SetupSetting(\"AppName\")}\n"
        
        # Russian
        iss_script += "russian.SelectDirLabel=Выберите папку, в которую будет установлен {#SetupSetting(\"AppName\")}, затем нажмите Далее.\n"
        iss_script += "russian.LaunchProgram=Запустить {#SetupSetting(\"AppName\")}\n"
        
        # Slovak
        iss_script += "slovak.SelectDirLabel=Vyberte priečinok, kam sa má nainštalovať {#SetupSetting(\"AppName\")}, a potom kliknite na Ďalej.\n"
        iss_script += "slovak.LaunchProgram=Spustiť {#SetupSetting(\"AppName\")}\n"
        
        # Slovenian
        iss_script += "slovenian.SelectDirLabel=Izberite mapo, kamor naj se namesti {#SetupSetting(\"AppName\")}, nato kliknite Naprej.\n"
        iss_script += "slovenian.LaunchProgram=Zaženi {#SetupSetting(\"AppName\")}\n"
        
        # Spanish
        iss_script += "spanish.SelectDirLabel=Seleccione la carpeta donde se instalará {#SetupSetting(\"AppName\")}, luego haga clic en Siguiente.\n"
        iss_script += "spanish.LaunchProgram=Ejecutar {#SetupSetting(\"AppName\")}\n"
        
        # Turkish
        iss_script += "turkish.SelectDirLabel={#SetupSetting(\"AppName\")} programının kurulacağı klasörü seçin ve İleri'ye tıklayın.\n"
        iss_script += "turkish.LaunchProgram={#SetupSetting(\"AppName\")} Başlat\n"
        
        # Ukrainian
        iss_script += "ukrainian.SelectDirLabel=Виберіть папку, куди буде встановлено {#SetupSetting(\"AppName\")}, потім натисніть Далі.\n"
        iss_script += "ukrainian.LaunchProgram=Запустити {#SetupSetting(\"AppName\")}\n"
        
        iss_script += "\n[Files]\n"
        # IMPORTANT: Exclude unnecessary files from being installed
        # *.iso is the one that mattered: the finished disc image is written
        # into this same folder, so a rebuild swept the PREVIOUS build's ISO
        # into the new installer, roughly doubling the disc,
        # and every player would have had a stale disc image dumped into their
        # install folder. Nothing else in the list is new.
        # Save files that live INSIDE the install folder, and why they get
        # their own lines.
        #
        # The wildcard below installs with `ignoreversion`, which overwrites
        # unconditionally. For any engine that keeps saves beside the game -
        # Ren'Py, every RPG Maker, AGS - a REINSTALL therefore wrote the
        # shipped default save straight over the player's own. That is the
        # moment somebody reinstalls to fix a problem and loses their
        # progress doing it, which is the worst possible time for it.
        #
        # Each pattern below is excluded from the wildcard and given its own
        # entry flagged:
        #   onlyifdoesntexist      - never overwrite a save that is there
        #   uninsneveruninstall    - and never delete it on uninstall
        #   skipifsourcedoesntexist - so a title without them still compiles
        #
        # The patterns are the install-rooted save folders of six common
        # engines, applied statically rather than detected per game,
        # because 1.5 does no engine detection. Applying all six to every
        # title is safe: a pattern that matches nothing is skipped, and none
        # of these names collides with ordinary game content.
        in_root_saves = [
            ("game\\saves\\*", "{app}\\game\\saves"),   # Ren'Py
            ("www\\save\\*", "{app}\\www\\save"),       # RPG Maker MV
            ("save\\*", "{app}\\save"),                 # RPG Maker MZ
            ("Save*.rvdata*", "{app}"),                 # RPG Maker VX / VX Ace
            ("Save*.rxdata", "{app}"),                  # RPG Maker XP
            ("agssave.*", "{app}"),                     # Adventure Game Studio
        ]
        save_excludes = "".join(f",{pattern}" for pattern, _dest in in_root_saves)
        iss_script += 'Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "vcredist_*.exe,*.tmp,*.log,*.iso,installer.iss,temp_build,temp_spec,temp_iso_build,setup.exe,setup-*.bin,.*,launch_game.bat,start_menu.bat,menu.bat,check_runtime.bat' + save_excludes + '"\n'
        iss_script += '\n; Player saves kept inside the install folder: installed once,\n'
        iss_script += '; never overwritten by a reinstall, never removed by the uninstaller.\n'
        for pattern, dest in in_root_saves:
            iss_script += (
                f'Source: "{pattern}"; DestDir: "{dest}"; '
                'Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist '
                'uninsneveruninstall skipifsourcedoesntexist\n'
            )
        iss_script += '\n; Runtime redistributables (only files that passed Authenticode checks)\n'
        for redist in ("vcredist_x86.exe", "vcredist_x64.exe"):
            if os.path.isfile(os.path.join(output_path, redist)):
                iss_script += (
                    f'Source: "{redist}"; DestDir: "{{app}}\\runtime"; '
                    f'Flags: ignoreversion\n')
        
        iss_script += "\n[Icons]\n"
        # Direct to menu.exe if it exists, otherwise to game.exe
        iss_script += f'Name: "{{group}}\\{path_name}"; Filename: "{{app}}\\menu\\menu.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\game_icon.ico"\n'
        iss_script += f'Name: "{{userdesktop}}\\{path_name}"; Filename: "{{app}}\\menu\\menu.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\game_icon.ico"; Tasks: desktopicon\n'
        
        iss_script += "\n[Tasks]\n"
        iss_script += 'Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"\n'
        
        iss_script += "\n[Run]\n"
        iss_script += f'Filename: "{{app}}\\menu\\menu.exe"; Description: "{{cm:LaunchProgram}}"; Flags: nowait postinstall skipifsilent\n'
        
        # No [Code] section. Inno already provides IsWin64; a local function of
        # the same name was an infinite-recursion shadow of the built-in.
        
        # No [Registry] section, deliberately.
        #
        # There was one, writing UninstallString, QuietUninstallString,
        # InstallLocation and Publisher into a key named after the title. All
        # four are already written, and written better, by Inno itself:
        # CreateUninstallRegKey=yes above produces <AppName>_is1 carrying those
        # plus DisplayName, DisplayIcon, DisplayVersion, EstimatedSize,
        # InstallDate and NoModify/NoRepair. The _is1 key is the entry players
        # actually see in Add or Remove Programs; the hand-written one had no
        # DisplayName, so it appeared nowhere.
        #
        # It was also wrong twice over. Its UninstallString was unquoted, so it
        # broke on any install path containing a space - which is every default
        # install, C:\Games\<title>. And it carried no uninsdeletekey flag, so
        # Inno's uninstaller had no reason to remove it: every player who
        # installed and later uninstalled was left with a dead key pointing at
        # a unins000.exe that no longer existed, invisible in the UI and so
        # impossible for them to clear.

        # No [UninstallDelete] section, and that is the fix rather than an
        # omission. It used to read:
        #
        #     [UninstallDelete]
        #     Type: filesandordirs; Name: "{app}"
        #
        # which tells Inno to delete the ENTIRE install directory on
        # uninstall - not the files it installed, everything in there. A
        # player's saves live in that directory for any engine that keeps
        # them beside the game (RPG Maker, most Ren'Py builds, a great many
        # GameMaker titles), so uninstalling took their progress with it.
        #
        # The uninstaller UI says, in all 21 languages this script ships,
        # that personal files are not touched. That sentence was false.
        #
        # Inno already removes what it installed and leaves what the player
        # created, which is the correct behaviour and needs no directive.
        # Anything the game wrote after install - saves, settings, screenshots
        # - stays, and an empty directory is tidied by Inno anyway.
        #
        # Do not add the section back: the files a player creates in the
        # install folder must survive an uninstall.

        iss_path = os.path.join(output_path, "installer.iss")
        try:
            with open(iss_path, "w", encoding="utf-8") as f:
                f.write(iss_script)
            self.update_status("✅ Enhanced installer script written with 21 properly supported languages")
            
            # Create a first-run script that installs runtimes
            try:
                if hasattr(self, 'create_first_run_script'):
                    self.create_first_run_script(output_path)
            except Exception as e:
                self.update_status(f"⚠️ Could not create runtime checker: {e}")
                
        except Exception as e:
            self.update_status(f"❌ Failed to write installer script: {e}")





    def create_first_run_script(self, output_path):
        """Create a script that checks and installs runtimes on first run"""
        check_script = '''@echo off
rem Runtime checker - runs silently in background

cd /d "%~dp0"

rem Check if runtimes are already installed
reg query "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64" >nul 2>&1
if %errorlevel% equ 0 (
    rem x64 runtime already installed
    goto check_x86
)

rem Install x64 runtime if present
if exist "runtime\\vcredist_x64.exe" (
    start /wait "" "runtime\\vcredist_x64.exe" /quiet /norestart
)

:check_x86
reg query "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x86" >nul 2>&1
if %errorlevel% equ 0 (
    rem x86 runtime already installed
    exit /b 0
)

rem Install x86 runtime if present
if exist "runtime\\vcredist_x86.exe" (
    start /wait "" "runtime\\vcredist_x86.exe" /quiet /norestart
)

exit /b 0
'''
        
        check_path = os.path.join(output_path, "check_runtime.bat")
        try:
            with open(check_path, "w", errors="replace") as f:
                f.write(check_script)
            self.update_status("✅ Created first-run runtime checker")
        except Exception as e:
            self.update_status(f"⚠️ Could not create runtime checker: {e}")









    def stage_menu_executable(self, output_path):
        """Put menu.exe in the staged menu/ folder.

        The pre-built menu.exe is title-agnostic and byte-identical on every
        disc, so it is signed once alongside Rialto instead of recompiled per
        game. That is what lets a frozen Rialto build a disc on a machine with
        neither Python nor PyInstaller installed - and it takes a couple of
        minutes off every build besides.

        In order: the pre-built exe; failing that, a source checkout with
        PyInstaller can still compile one; failing that, the batch menu the
        caller stages unconditionally.

        Whichever path staged it, the copy that lands in menu/ is offered to
        sign_staged_menu_exe so it can carry the author's own signature rather
        than a stranger's - see that method.
        """
        menu_dir = os.path.join(output_path, "menu")
        os.makedirs(menu_dir, exist_ok=True)

        prebuilt = prebuilt_menu_exe()
        if prebuilt:
            # Copy beside the real name and rename into place. menu.exe is 40 MB;
            # a copy that dies part-way - a full output drive, an external disk
            # unplugged - used to leave the fragment behind under the real name,
            # and the build shipped it. Nothing downstream re-checks: the
            # installer's Start menu shortcut, its desktop shortcut and its
            # post-install Run entry all point at {app}\menu\menu.exe, so the
            # player got a corrupt executable instead of the batch menu that is
            # supposed to cover exactly this. os.replace is atomic within the
            # folder, so menu.exe is either whole or absent.
            staged = os.path.join(menu_dir, "menu.exe")
            partial = staged + ".part"
            try:
                shutil.copy2(prebuilt, partial)
                os.replace(partial, staged)
            except OSError as e:
                # Say which of the two it was. "Not found" and "found it, could
                # not copy it" want opposite things from the author - one is a
                # broken install, the other is a full drive or a locked file -
                # and this used to report both as the first.
                self.update_status(
                    f"⚠️ Found menu.exe at {prebuilt} but could not copy it: {e}")
                try:
                    os.remove(partial)
                except OSError:
                    pass
                self.update_status("ℹ️ Falling back to compiling a menu for this build")
            else:
                # The onefile exe carries its own runtime, but discs have always
                # shipped these beside it for older Windows installs.
                self.copy_vcruntime_dlls(menu_dir)
                self.update_status("✅ Staged pre-built menu.exe")
                self.sign_staged_menu_exe(menu_dir)
                return True

        if not prebuilt:
            self.update_status("ℹ️ No pre-built menu.exe found - compiling one for this build")
        if write_menu_source(menu_dir) and self.compile_pyqt5_menu(output_path):
            self.update_status("✅ PyQt5 menu compiled successfully")
            self.sign_staged_menu_exe(menu_dir)
            return True

        self.update_status("⚠️ No menu.exe - the batch menu fallback will be used")
        # Never leave menu source sitting on the disc when the compile did not run.
        stale_source = os.path.join(menu_dir, "menu_launcher.pyw")
        if os.path.exists(stale_source):
            try:
                os.remove(stale_source)
            except OSError:
                pass
        return False

    def sign_staged_menu_exe(self, menu_dir):
        """Sign this build's own copy of menu.exe with the author's account.

        Rialto is open source, and the menu.exe handed out with it is the same
        generic file on every disc anyone builds. So it ships unsigned on
        purpose: a signature there would put whoever built Rialto onto discs
        they had nothing to do with. Each author signs their own staged copy
        instead, with their own Azure Artifact Signing account, and the disc
        then says who made the disc.

        Runs after staging and long before the ISO is packed, so the signed
        copy is the one that reaches the disc. Signing is skipped - loudly but
        harmlessly - when Sign Final Build is off or no account is set up;
        an unsigned menu is the ordinary do-it-yourself result.
        """
        try:
            wants_signing = self.sign_final_build.get()
        except Exception:
            wants_signing = False
        if not wants_signing:
            self.update_status("ℹ️ Disc menu left unsigned (tick Sign Final Build to sign it with your account)")
            return False

        try:
            import trusted_signing
            signed, message = trusted_signing.sign_staged_menu(menu_dir, self.update_status)
        except Exception as e:
            # Never fail a build over the menu signature - the disc runs either way.
            self.update_status(f"⚠️ Could not sign the staged menu.exe: {e}")
            return False

        if signed:
            self.update_status("✅ Disc menu signed with your own account (this disc's copy of menu.exe)")
            return True
        # An attempt that failed deserves a warning; a deliberate skip does not.
        try:
            configured = trusted_signing.is_configured()
        except Exception:
            configured = False
        self.update_status(("⚠️ " if configured else "ℹ️ ") + message)
        return False

    def compile_pyqt5_menu(self, output_path):
        """Legacy per-title compile: only reached in a source checkout with no
        pre-built menu.exe around. Freezes the same generic menu source."""
        menu_dir = os.path.join(output_path, "menu")
        launcher_pyw = os.path.join(menu_dir, "menu_launcher.pyw")
        
        if not os.path.exists(launcher_pyw):
            self.update_status("❌ menu_launcher.pyw not found for compilation")
            return False
        
        # Copy game icon to menu directory for compilation
        icon_source = os.path.join(output_path, "game_icon.ico")
        icon_dest = os.path.join(menu_dir, "game_icon.ico")
        if os.path.exists(icon_source):
            try:
                shutil.copy2(icon_source, icon_dest)
            except OSError:
                pass
        
        # Copy runtime DLLs to menu directory
        self.copy_vcruntime_dlls(menu_dir)
        
        # Enhanced PyInstaller path detection
        app_dir = os.path.dirname(os.path.abspath(__file__))
        pyinstaller_paths = [
            os.path.join(app_dir, "python39", "venv", "Scripts", "pyinstaller.exe"),
            os.path.join(sys.prefix, "Scripts", "pyinstaller.exe"),
            "pyinstaller.exe",
            os.path.join(os.path.dirname(sys.executable), "pyinstaller.exe"),
            os.path.join(os.path.dirname(sys.executable), "Scripts", "pyinstaller.exe")
        ]
        
        pyinstaller_path = None
        for path in pyinstaller_paths:
            if os.path.exists(path):
                pyinstaller_path = path
                self.update_status(f"✅ Found PyInstaller at: {path}")
                break
            elif shutil.which(path):
                pyinstaller_path = shutil.which(path)
                self.update_status(f"✅ Found PyInstaller in PATH: {pyinstaller_path}")
                break
        
        if not pyinstaller_path:
            self.update_status("⚠️ PyInstaller not found. Batch menu fallback will be used. Install with: pip install pyinstaller")
            return False
        
        # Build command with icon and runtime
        build_cmd = [
            pyinstaller_path,
            "--onefile",
            "--windowed", 
            "--clean",
            "--noupx",
            "--name", "menu",
            "--distpath", menu_dir,
            "--workpath", os.path.join(output_path, "temp_build"),
            "--specpath", os.path.join(output_path, "temp_spec"),
        ]
        
        # Add icon if it exists
        if os.path.exists(icon_dest):
            build_cmd.extend(["--icon", icon_dest])
        
        # Add runtime DLLs
        for dll in ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
            dll_path = os.path.join(menu_dir, dll)
            if os.path.exists(dll_path):
                build_cmd.extend(["--add-binary", f"{dll_path};."])
        
        build_cmd.append(launcher_pyw)
        
        # Add PyQt5 dependencies
        try:
            import PyQt5
            build_cmd.extend([
                "--collect-all", "PyQt5",
                "--hidden-import=PyQt5.QtCore",
                "--hidden-import=PyQt5.QtGui",
                "--hidden-import=PyQt5.QtWidgets"
            ])
            self.update_status("✅ Added PyQt5 dependencies to build")
        except ImportError:
            self.update_status("⚠️ PyQt5 not found, trying basic compilation...")
        
        # Add background image if it exists
        bg_path = os.path.join(menu_dir, "background.jpg")
        if os.path.exists(bg_path):
            build_cmd.extend(["--add-data", f"{bg_path};."])
        
        try:
            self.update_status("🔄 Compiling PyQt5 menu with PyInstaller...")
            result = subprocess.run(
                build_cmd,
                cwd=menu_dir,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=300
            )
            
            menu_exe = os.path.join(menu_dir, "menu.exe")
            
            if result.returncode == 0 and os.path.exists(menu_exe):
                self.update_status("✅ PyQt5 menu compiled successfully with icon!")
                
                # Clean up source files but keep DLLs
                files_to_clean = [
                    "menu_launcher.pyw",  # Generated file, cleaned after compilation
                    "background.jpg",
                    "game_icon.ico"
                ]
                
                cleaned_count = 0
                for file_to_clean in files_to_clean:
                    file_path = os.path.join(menu_dir, file_to_clean)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except OSError:
                            pass
                
                if cleaned_count > 0:
                    self.update_status(f"🧹 Cleaned {cleaned_count} source menu files (kept menu.exe)")
                
                return True
            else:
                self.update_status("❌ PyInstaller compilation failed")
                if result.stderr:
                    self.update_status(f"Error: {result.stderr}")
                return False
                
        except Exception as e:
            self.update_status(f"❌ PyInstaller execution failed: {e}")
            return False
        
        finally:
            # Clean up temp directories
            temp_dirs = [
                os.path.join(output_path, "temp_build"),
                os.path.join(output_path, "temp_spec")
            ]
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                    except OSError:
                        pass




    def create_batch_menu_fallback(self, output_path):
        """Create batch file menu that always works"""
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        game_title = escape_batch(meta.get('Title', 'Game')) or "Game"
        game_title_upper = game_title.upper()

        batch_content = """@echo off
title {game_title} Menu
color 07
cls

:menu
echo.
echo ==========================================
echo           {game_title_upper}
echo ==========================================
echo.
echo 1. Play Game
echo 2. Open Bonus Content
echo 3. Mods
echo 4. Uninstall Game
echo 5. Exit
echo.
set /p choice="Choose an option (1-5): "

if "%choice%"=="1" goto playgame
if "%choice%"=="2" goto bonus
if "%choice%"=="3" goto mods
if "%choice%"=="4" goto uninstall
if "%choice%"=="5" goto exit
echo Invalid choice. Please try again.
timeout /t 2 >nul
goto menu

:playgame
cls
echo Starting {game_title}...
rem Find the main game executable dynamically
for %%f in (*.exe) do (
    if /i not "%%f"=="setup.exe" (
        if /i not "%%f"=="unins000.exe" (
            if /i not "%%f"=="UnityCrashHandler64.exe" (
                start "" "%%f"
                goto exit
            )
        )
    )
)
echo.
echo ERROR: Game executable not found!
echo Please reinstall the game.
echo.
pause
goto menu

:bonus
cls
echo Opening bonus content...
if exist "bonus" (
    start "" "bonus"
    echo Bonus content opened in file explorer.
    timeout /t 2 >nul
    goto menu
) else (
    echo.
    echo WARNING: Bonus content not found!
    echo.
    pause
    goto menu
)

:mods
cls
echo Starting mod launcher...
if not exist "mods" goto mods_missing
rem First .exe at the top of the mods folder, then one level deeper
for %%f in ("mods\\*.exe") do (
    start "" "%%f"
    goto exit
)
for /d %%d in ("mods\\*") do (
    for %%f in ("%%d\\*.exe") do (
        start "" "%%f"
        goto exit
    )
)
:mods_missing
echo.
echo WARNING: Mod launcher not found!
echo.
pause
goto menu

:uninstall
cls
echo.
echo Are you sure you want to uninstall {game_title}? (Y/N)
set /p confirm=""
if /i "%confirm%"=="Y" goto do_uninstall
if /i "%confirm%"=="YES" goto do_uninstall
goto menu

:do_uninstall
if exist "unins000.exe" (
    echo Starting uninstaller...
    start "" "unins000.exe"
    goto exit
) else (
    echo.
    echo WARNING: Uninstaller not found!
    echo You may need to manually remove the game.
    echo.
    pause
    goto menu
)

:exit
exit
"""
        
        batch_path = os.path.join(output_path, "menu.bat")
        with open(batch_path, "w", errors="replace") as f:
            f.write(batch_content.format(game_title=game_title, game_title_upper=game_title_upper))
        
        self.update_status("✅ Created batch menu fallback")





    def create_menu_selector(self, output_path):
        """Create batch file that selects the best menu option"""
        selector_content = """@echo off
rem Priority 1: Try PyQt5 advanced menu (best experience)
if exist "menu\\menu.exe" (
    start "" "menu\\menu.exe"
    exit /b 0
)

rem Priority 2: Find and launch the main game executable
for %%f in (*.exe) do (
    if /i not "%%f"=="setup.exe" (
        if /i not "%%f"=="unins000.exe" (
            if /i not "%%f"=="UnityCrashHandler64.exe" (
                start "" "%%f"
                exit /b 0
            )
        )
    )
)

rem Priority 3: LAST RESORT - Show batch menu
if exist "menu.bat" (
    echo Advanced menu unavailable, starting compatibility mode...
    timeout /t 2 >nul
    call "menu.bat"
    exit /b 0
)

rem Nothing works - show error
echo.
echo ERROR: No menu system or game executable found!
echo Please contact support or reinstall the game.
echo.
pause
exit /b 1
"""
        
        selector_path = os.path.join(output_path, "start_menu.bat")
        with open(selector_path, "w", errors="replace") as f:
            f.write(selector_content)
        
        self.update_status("✅ Created menu selector batch")

        # Create VBScript that checks runtimes first, then runs menu
        vbs_launcher = '''Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Check and install runtimes if needed (silently)
runtimeChecker = strPath & "\\check_runtime.bat"
If objFSO.FileExists(runtimeChecker) Then
    WshShell.Run Chr(34) & runtimeChecker & Chr(34), 0, True
End If

' Check if menu.exe exists and run it directly (no console)
menuPath = strPath & "\\menu\\menu.exe"
If objFSO.FileExists(menuPath) Then
    WshShell.Run Chr(34) & menuPath & Chr(34), 0, False
    WScript.Quit
End If

' Find and launch the main game executable
Set objFolder = objFSO.GetFolder(strPath)
For Each objFile In objFolder.Files
    If LCase(objFSO.GetExtensionName(objFile.Name)) = "exe" Then
        fileName = LCase(objFile.Name)
        If fileName <> "setup.exe" And fileName <> "unins000.exe" And fileName <> "unitycrashhandler64.exe" Then
            WshShell.Run Chr(34) & objFile.Path & Chr(34), 0, False
            WScript.Quit
        End If
    End If
Next

' Nothing found - show error
MsgBox "Game files not found. Please reinstall the game.", vbCritical, "Error"
'''
        
        vbs_path = os.path.join(output_path, "launch_silent.vbs")
        with open(vbs_path, "w", errors="replace") as f:
            f.write(vbs_launcher)
        
        # Create a simple batch launcher
        batch_launcher = '''@echo off
wscript.exe "%~dp0launch_silent.vbs" //B //NoLogo
exit
'''
        
        launcher_path = os.path.join(output_path, "launch_game.bat")
        with open(launcher_path, "w", errors="replace") as f:
            f.write(batch_launcher)
        
        self.update_status("✅ Created silent launcher system")















    # Everything a profile stores as an absolute path that lives, in practice,
    # underneath the game folder. Move the game folder and these go stale.
    REBASEABLE_PATHS = (
        ("mac_build_var", "Mac build"),
        ("linux_build_var", "Linux build"),
        ("bonus_folder_var", "Bonus folder"),
        ("mod_folder_var", "Mod folder"),
    )

    def rebase_under_game(self, stored):
        """A stored path that has gone missing, found again under the game folder.

        Profiles keep absolute paths. Copy a game to a new drive, or load a
        profile written against a different input root, and a path like
        C:/Rialto/input/MyGame/game/Linux stops resolving - while the very
        same folder sits under the new game folder. Left alone, a universal
        disc would quietly ship Windows-only, with one warning line in the log.

        Tries the longest tail of the stored path first, so the most specific
        match wins. Returns "" when nothing matches - a wrong guess would be
        worse than none.
        """
        if not stored or not self.current_game_path:
            return ""
        if os.path.isdir(stored):
            return ""
        parts = [p for p in stored.replace("\\", "/").split("/") if p not in ("", ".")]
        for start in range(len(parts) - 1, -1, -1):
            candidate = os.path.join(self.current_game_path, *parts[start:])
            if os.path.isdir(candidate):
                return candidate
        return ""

    def rebase_stale_paths(self):
        """Re-point every stale profile path that can be found again. Returns the count."""
        fixed = 0
        for attr, label in self.REBASEABLE_PATHS:
            var = getattr(self, attr, None)
            if var is None:
                continue
            found = self.rebase_under_game(var.get().strip())
            if found:
                var.set(found)
                self.update_status(f"🔀 {label} re-pointed at your game folder: {found}")
                fixed += 1
        return fixed

    def missing_configured_extras(self):
        """Configured folders that are still missing after rebasing."""
        missing = []
        for attr, label in self.REBASEABLE_PATHS:
            var = getattr(self, attr, None)
            if var is None:
                continue
            value = var.get().strip()
            if value and not os.path.isdir(value):
                missing.append((label, value))
        return missing

    def run_build_process(self):
        """Check what the build needs, then build."""
        self.update_status("Starting build process...")

        # Before anything is copied: a folder the author configured and cannot
        # be found is asked about, not mentioned in passing. Skipping one
        # silently would turn a universal disc into a Windows-only one.
        self.rebase_stale_paths()
        missing = self.missing_configured_extras()
        if missing:
            detail = "\n".join(f"    {label}: {path}" for label, path in missing)
            plural = "" if len(missing) == 1 else "s"
            if not self.show_centered_popup(
                    "Something is missing",
                    "%d folder%s you chose cannot be found, so %s will not be on the disc:\n\n%s"
                    "\n\nBuild without %s?"
                    % (len(missing), plural, "it" if not plural else "they",
                       detail, "it" if not plural else "them"),
                    kind="yesno"):
                self.update_status("⛔ Build cancelled - fix the folders in Disc Extras")
                return

        if not self.run_preflight_check():
            return
        self.build_all()

    def refresh_windows_icon_cache(self):
        """Refresh Windows icon cache to show updated disc icons"""
        try:
            if sys.platform == "win32":
                # Force Windows to refresh the icon cache
                self.update_status("🔄 Refreshing Windows icon cache...")
                subprocess.run([
                    "cmd", "/c", 
                    "ie4uinit.exe", "-show"
                ], capture_output=True, timeout=10)
                self.update_status("✅ Icon cache refreshed")
        except Exception as e:
            # Silently fail - this is just a nice-to-have
            pass

    def clean_output_folder_final(self, output_path, keep_mode="iso"):
        """Final cleanup - remove everything except ISO file"""
        
        # Files to KEEP (everything else gets deleted)
        keep_files = []
        
        # Add ISO files to keep
        for item in os.listdir(output_path):
            if item.lower().endswith(".iso"):
                keep_files.append(item)
        
        # Don't keep README.txt in the output folder - it's already in the ISO
        
        self.update_status(f"🧹 Final cleanup - keeping only: {', '.join(keep_files) if keep_files else 'ISO files'}")
        
        # Remove EVERYTHING else (since it's all in the installer/ISO now)
        items_to_remove = []
        for item in os.listdir(output_path):
            if item not in keep_files:
                items_to_remove.append(item)
        
        cleaned_count = 0
        for item in items_to_remove:
            item_path = os.path.join(output_path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    self.update_status(f"🧹 Removed: {item}/")
                else:
                    os.remove(item_path)
                    self.update_status(f"🧹 Removed: {item}")
                cleaned_count += 1
            except Exception as e:
                self.update_status(f"⚠️ Cleanup failed on {item}: {e}")
        
        if cleaned_count > 0:
            self.update_status(f"🧹 Final cleanup complete - removed {cleaned_count} items")
            self.update_status("✅ Output folder now contains only ISO file ready for burning")
        
        # Verify final state
        remaining_files = os.listdir(output_path)
        iso_files = [f for f in remaining_files if f.lower().endswith('.iso')]
        
        if iso_files:
            iso_size = os.path.getsize(os.path.join(output_path, iso_files[0])) / (1024 * 1024)
            self.update_status(f"📀 Final result: {iso_files[0]} ({iso_size:.1f} MB) ready for disc burning")
        else:
            self.update_status("❌ Warning: No ISO file found in final output")





    def burn_to_master(self):
        """Enhanced burn to master with better ISO detection and ImgBurn integration"""
        import ctypes
        
        try:
            import win32file
        except ImportError:
            self.show_centered_popup("Missing Module", "pywin32 module required for disc burning.\nInstall with: pip install pywin32")
            return
        
        iso_path = None
        # Auto-select the most recent ISO in the output folder
        iso_files = []
        for subdir in os.listdir(OUTPUT_DIR):
            subpath = os.path.join(OUTPUT_DIR, subdir)
            if os.path.isdir(subpath):
                for f in os.listdir(subpath):
                    if f.endswith(".iso"):
                        full_path = os.path.join(subpath, f)
                        iso_files.append((os.path.getmtime(full_path), full_path))
        
        if iso_files:
            iso_files.sort(reverse=True)
            iso_path = iso_files[0][1]
        
        if not iso_path:
            self.show_centered_popup("Burn Failed", "No ISO file found to burn.")
            return

        # Find ImgBurn installation path
        imgburn_paths = [
            r"C:\Program Files\ImgBurn\ImgBurn.exe",
            r"C:\Program Files (x86)\ImgBurn\ImgBurn.exe",
            os.path.join(os.environ.get("ProgramFiles", ""), "ImgBurn", "ImgBurn.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "ImgBurn", "ImgBurn.exe")
        ]
        
        imgburn_exe = None
        for path in imgburn_paths:
            if os.path.isfile(path):
                imgburn_exe = path
                break
        
        if not imgburn_exe:
            # Try to use Windows built-in disc burning
            self.update_status("ImgBurn not found, using Windows disc burning...")
            try:
                os.startfile(iso_path)
                self.show_centered_popup("Burn Started", "ISO opened with Windows disc burning.\nSelect 'Burn disc image' when prompted.")
                return
            except Exception as e:
                self.show_centered_popup("ImgBurn Not Found", 
                                       "ImgBurn not found. Please install from:\n"
                                       "https://www.imgburn.com/\n\n"
                                       "Or use Windows built-in disc burning.")
                return

        # Auto-detect DVD drive
        dvd_drives = []
        drives = win32file.GetLogicalDrives()
        
        for i in range(26):
            if drives & (1 << i):
                drive_letter = chr(ord('A') + i)
                drive_path = f"{drive_letter}:\\"
                try:
                    drive_type = win32file.GetDriveType(drive_path)
                    if drive_type == win32file.DRIVE_CDROM:  # CD/DVD drive
                        dvd_drives.append(drive_letter)
                except Exception:
                    continue
        
        if not dvd_drives:
            self.show_centered_popup("No DVD Drive", "No DVD/CD drive detected.")
            return
        
        # Select drive
        if len(dvd_drives) == 1:
            dvd_drive = dvd_drives[0]
        else:
            # Multiple drives found, let user choose
            drive_list = ", ".join(dvd_drives)
            drive_dialog = tk.Toplevel(self.root)
            drive_dialog.title("Select DVD Drive")
            drive_dialog.geometry("300x150")
            drive_dialog.transient(self.root)
            drive_dialog.grab_set()
            
            tk.Label(drive_dialog, text=f"Multiple DVD drives found:\n{drive_list}\n\nSelect drive:").pack(pady=10)
            
            drive_var = tk.StringVar(value=dvd_drives[0])
            drive_menu = ttk.Combobox(drive_dialog, textvariable=drive_var, values=dvd_drives, state="readonly")
            drive_menu.pack(pady=10)
            
            selected_drive = [None]
            
            def select_drive():
                selected_drive[0] = drive_var.get()
                drive_dialog.destroy()
            
            tk.Button(drive_dialog, text="Select", command=select_drive).pack(pady=10)
            
            self.root.wait_window(drive_dialog)
            dvd_drive = selected_drive[0]
            
            if not dvd_drive:
                return

        try:
            # Confirm burn operation
            iso_name = os.path.basename(iso_path)
            iso_size_mb = os.path.getsize(iso_path) / (1024 * 1024)
            
            result = self.show_centered_popup("Confirm Burn", 
                f"Ready to burn:\n{iso_name} ({iso_size_mb:.1f} MB)\n\n"
                f"To drive: {dvd_drive}:\n\n"
                f"This will erase any existing data on the disc.\n"
                f"Continue?", kind="yesno")
            
            if not result:
                return
            
            # Build ImgBurn command
            cmd = [
                imgburn_exe,
                "/MODE", "WRITE",
                "/SRC", iso_path,
                "/DEST", f"{dvd_drive}:",
                "/VERIFY", "YES",
                "/CLOSESUCCESS",
                "/START",
                "/COPIES", "1"
            ]
            
            self.update_status(f"🔥 Starting DVD burn to drive {dvd_drive}:...")
            
            # Run ImgBurn
            process = subprocess.Popen(cmd)
            
            self.update_status("📀 ImgBurn launched - burning in progress...")
            self.update_status("⏳ Please wait for ImgBurn to complete the burn...")
            
        except Exception as e:
            self.show_centered_popup("Burn Failed", f"Could not start ImgBurn:\n{e}")
            self.update_status(f"❌ Burn error: {e}")











    def build_bonus_gallery(self, game_path, output_path, bonus_source=None):
        """Put the bonus folder in the output, for the disc and the installer both.

        Runs before ISCC. copy_game_files_to_output (step 2) already brings a
        bonus/ that lives inside the game folder, but Disc Extras can point at a
        folder anywhere on the PC, and that one has nothing else to carry it -
        so this stages it into the output folder where Inno's `Source: "*"`
        sweep and the _collect_disc_fileset whitelist both find it.

        `bonus_source` defaults to <game>/bonus, which is what every disc built
        before Disc Extras had a bonus picker used.
        """
        if bonus_source is None:
            bonus_source = os.path.join(game_path, "bonus")
        bonus_output = os.path.join(output_path, "bonus")

        if not bonus_source or not os.path.exists(bonus_source):
            self.update_status("ℹ️ No bonus folder found - skipping")
            return
        if os.path.abspath(bonus_source) == os.path.abspath(bonus_output):
            return  # already exactly where it needs to be

        try:
            if os.path.exists(bonus_output):
                shutil.rmtree(bonus_output)
            shutil.copytree(bonus_source, bonus_output)
            self.update_status("✅ Bonus content copied")
        except Exception as e:
            self.update_status(f"⚠️ Failed to copy bonus content: {e}")

    def default_mod_dir(self):
        """Where a mod tool lives if the author never picked a folder."""
        if not self.current_game_path:
            return ""
        return os.path.join(self.current_game_path, "mods")

    def resolved_mod_dir(self):
        """The mod folder this build should use, or "" for none.

        An explicit pick from Disc Extras wins; failing that a mods/ folder
        inside the game folder is used exactly as it always was, so discs built
        before the picker existed keep building the same way.

        The picker exists because "mods" was the only name Rialto would accept.
        A mod tool kept in a folder with any other name, such as tools/, meant
        the MODS button silently never appeared.
        """
        chosen = self.mod_folder_var.get().strip()
        if chosen and os.path.isdir(chosen):
            return chosen
        default = self.default_mod_dir()
        return default if default and os.path.isdir(default) else ""

    def staged_mod_dir_name(self, game_path):
        """The mod folder's name once it is sitting in the output folder.

        A folder inside the game folder is already there - step 2 copies the
        whole game folder across - so it keeps its own name and is NOT copied
        again. Re-staging it as mods/ would put a second copy of the mod
        tool on the disc.
        """
        resolved = self.resolved_mod_dir()
        if not resolved:
            return ""
        return os.path.basename(os.path.normpath(resolved))

    def stage_mod_launcher(self, game_path, output_path):
        """Put the mod folder in the output folder if the mod launcher is enabled.

        Runs before the menu config is written and before ISCC compiles the
        installer, so the detected mod exe lands in menu_config.json and the
        folder is swept into {app} by the Inno [Files] wildcard.
        """
        if not self.mod_launcher_var.get():
            return

        mods_source = self.resolved_mod_dir()
        if not mods_source:
            self.update_status(
                "⚠️ Mod Launcher is on but no mod folder was found - the MODS button "
                "will not appear. Pick one in Disc Extras.")
            return

        # Already inside the game folder means already copied to the output.
        try:
            inside_game = os.path.commonpath(
                [os.path.realpath(game_path), os.path.realpath(mods_source)]
            ) == os.path.realpath(game_path)
        except (ValueError, OSError):
            inside_game = False

        staged_name = os.path.basename(os.path.normpath(mods_source))
        mods_output = os.path.join(output_path, staged_name)

        if inside_game and os.path.isdir(mods_output):
            self.update_status(f"✅ Mod folder already on the disc: {staged_name}")
            return

        try:
            if os.path.exists(mods_output):
                shutil.rmtree(mods_output)
            shutil.copytree(mods_source, mods_output)
            self.update_status(f"✅ Mod folder copied: {staged_name}")
        except Exception as e:
            self.update_status(f"⚠️ Failed to copy the mod folder: {e}")

    def detect_mod_launcher_exe(self, output_path):
        """Path of the mod tool the MODS button runs, relative to the disc root.

        Looks at the top level of the staged folder first, then one level deep,
        so both mods/ModOrganizer.exe and mods/MO2/ModOrganizer.exe work.

        Returns "" when there is nothing to run. It used to return a made-up
        "mods/ModLauncher.exe" instead, which could end up in a disc's
        menu_config.json pointing at a file that had never existed.
        """
        staged_name = self.staged_mod_dir_name(output_path) or "mods"
        mods_output = os.path.join(output_path, staged_name)
        if not os.path.isdir(mods_output):
            return ""

        try:
            entries = sorted(os.listdir(mods_output))
        except OSError:
            return ""

        for name in entries:
            if name.lower().endswith(".exe") and os.path.isfile(os.path.join(mods_output, name)):
                return f"{staged_name}/{name}"

        for name in entries:
            sub = os.path.join(mods_output, name)
            if not os.path.isdir(sub):
                continue
            try:
                for child in sorted(os.listdir(sub)):
                    if child.lower().endswith(".exe") and os.path.isfile(os.path.join(sub, child)):
                        return f"{staged_name}/{name}/{child}"
            except OSError:
                continue

        self.update_status(
            f"⚠️ No .exe found in {staged_name} - the MODS button will not appear")
        return ""




    def copy_game_files_to_output(self, source_dir, output_dir):
        """Copy all game files from input folder to output folder"""
        try:
            copied_files = 0
            main_py_file = None
            
            for item in os.listdir(source_dir):
                source_path = os.path.join(source_dir, item)
                dest_path = os.path.join(output_dir, item)
                
                # Skip certain files/folders that shouldn't be in the installer
                skip_items = ["menu", "installer.iss", "setup.exe", "autorun.inf"]
                if item.lower() in skip_items:
                    continue
                
                # Track main .py file for Ren'Py games
                if item.endswith(".py") and os.path.isfile(source_path) and main_py_file is None:
                    main_py_file = item
                
                # Always include game_logo.png
                if item == "game_logo.png":
                    shutil.copy2(source_path, dest_path)
                    copied_files += 1
                    self.update_status(f"📁 Copied: {item} (game logo)")
                elif os.path.isfile(source_path):
                    shutil.copy2(source_path, dest_path)
                    copied_files += 1
                    self.update_status(f"📁 Copied: {item}")
                elif os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                    copied_files += 1
                    self.update_status(f"📁 Copied folder: {item}")
            
            # For Ren'Py games: also copy main .py file as game.py
            if main_py_file and main_py_file != "game.py":
                # Check if this is a Ren'Py game (has renpy folder)
                if os.path.exists(os.path.join(output_dir, "renpy")) or os.path.exists(os.path.join(output_dir, "lib")):
                    game_py_src = os.path.join(output_dir, main_py_file)
                    game_py_dest = os.path.join(output_dir, "game.py")
                    if os.path.exists(game_py_src) and not os.path.exists(game_py_dest):
                        shutil.copy2(game_py_src, game_py_dest)
                        self.update_status(f"📁 Created game.py from {main_py_file} (Ren'Py launcher)")
                        copied_files += 1
            
            self.update_status(f"✅ Copied {copied_files} game files/folders")
            return copied_files > 0
            
        except Exception as e:
            detail = str(e)
            if len(detail) > 300:
                detail = detail[:300] + "..."
            self.update_status(f"❌ Failed to copy game files: {detail}")
            # Stop the build: carrying on would put part of the game on the disc.
            raise RuntimeError(f"The game files could not all be copied ({detail}), so the build was stopped.") from e




    def cleanup_before_installer(self, output_path):
        """Remove unnecessary files before creating installer"""
        cleanup_items = [
            "installer.iss",  # Don't include the script itself
            "menu_launcher.pyw",  # Don't include source file
            "temp_build",
            "temp_spec", 
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "error_log.txt"
        ]
        
        # Don't clean the menu folder - we need those files!
        protected_folders = ["menu", "bonus", "engine", "data"]
        
        for item in cleanup_items:
            if "*" in item:
                # Handle wildcards
                for file_path in glob.glob(os.path.join(output_path, "**", item), recursive=True):
                    # Skip protected folders
                    skip = False
                    for protected in protected_folders:
                        if protected in file_path:
                            skip = True
                            break
                    
                    if not skip:
                        try:
                            os.remove(file_path)
                            self.update_status(f"🧹 Removed: {os.path.basename(file_path)}")
                        except OSError:
                            pass
            else:
                item_path = os.path.join(output_path, item)
                if os.path.exists(item_path):
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                        self.update_status(f"🧹 Removed: {item}")
                    except Exception as e:
                        self.update_status(f"⚠️ Cleanup warning: {e}")










    def report_disc_media_fit(self, size_bytes):
        """Tell the user which physical media the ISO fits on (CD/DVD/Blu-ray)."""
        media_types = [
            ("CD-R (700 MB)", 700 * 1024 * 1024),
            ("DVD-R (4.7 GB)", 4_700_000_000),
            ("DVD-R DL (8.5 GB)", 8_540_000_000),
            ("Blu-ray BD-R (25 GB)", 25_000_000_000),
            ("Blu-ray BD-R DL (50 GB)", 50_000_000_000),
        ]
        fits = [name for name, capacity in media_types if size_bytes <= capacity]
        if fits:
            self.update_status(f"💿 Fits on: {', '.join(fits)}")
        else:
            self.update_status("⚠️ ISO is larger than 50 GB - it won't fit on standard optical media!")
        smallest = next((name for name, capacity in media_types if size_bytes <= capacity), None)
        if smallest and "Blu-ray" in smallest:
            self.update_status("ℹ️ Note: Blu-ray data discs need a BD burner; most game discs target DVD-R.")

    def create_iso(self, output_path, meta):
        """Build the ISO with mkisofs or oscdimg, or fall back to a ZIP"""
        game_name = meta["GameName"]
        iso_path = os.path.join(output_path, f"{game_name}.iso")

        # Volume label: use the Disc Name field (same as autorun.inf) when set,
        # falling back to the folder name. 16 chars for Joliet compatibility.
        disc_label = ""
        if hasattr(self, "disc_name_var"):
            disc_label = sanitize_text(self.disc_name_var.get().strip())
        disc_label = (disc_label or sanitize_text(game_name) or "GAME")[:16]

        self.update_status("Creating the disc image...")
        
        # Clean up temp files before ISO creation
        temp_files_to_remove = ["installer.iss", "compatibility_test.bat"]
        for temp_file in temp_files_to_remove:
            temp_path = os.path.join(output_path, temp_file)
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
        
        # Files to include in ISO (essential files only, existence-checked)
        iso_files = self._collect_disc_fileset(output_path)

        self.update_status(f"📦 ISO will contain {len(iso_files)} items")

        # Too big for the chosen disc? Build a numbered multi-disc set instead.
        capacity = self.get_target_media_capacity()
        if capacity:
            total_size = self._fileset_size(output_path, iso_files)
            if total_size > capacity - self.MEDIA_RESERVE:
                self.update_status(f"📀 Build is {total_size / 1e9:.1f} GB, over the {self.target_media_var.get()} limit")
                self.create_spanned_isos(output_path, meta, disc_label, capacity)
                return

        # Files over 4 GB need the UDF disc format (standard on Blu-ray players)
        needs_udf = self._fileset_needs_udf(output_path, iso_files)
        if needs_udf:
            self.update_status("💿 Large files detected: using the UDF disc format")
        
        # Try to locate mkisofs or oscdimg
        mkisofs, oscdimg = find_iso_tools()
        
        tool = None
        if mkisofs:
            self.update_status("✅ Found mkisofs")
            tool = [mkisofs, "-o", iso_path, "-J", "-R", "-V", disc_label]
            if needs_udf:
                tool += ["-udf", "-iso-level", "3"]
            tool += iso_files

        elif oscdimg:
            # For oscdimg, we need to create a temp folder with only the files we want
            temp_iso_folder = os.path.join(output_path, "temp_iso_build")
            if os.path.exists(temp_iso_folder):
                shutil.rmtree(temp_iso_folder)
            os.makedirs(temp_iso_folder)
    
            # Copy only the files we want to the temp folder
            for item in iso_files:
                src_path = os.path.join(output_path, item)
                if os.path.exists(src_path):
                    dst_path = os.path.join(temp_iso_folder, item)
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
    
            tool = [oscdimg, "-m", "-u2" if needs_udf else "-j1", f"-l{disc_label}", temp_iso_folder, iso_path]
            
        else:
            self.update_status("⚠️ No ISO tool found. Install the Windows ADK with Deployment Tools ticked (oscdimg), or put mkisofs on your PATH")
            # Fallback to Python ZIP method (but still create .iso extension)
            self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)
            return
        
        # Run the ISO creation tool
        try:
            self.update_status("🔄 Running ISO creation...")
            result = subprocess.run(
                tool,
                cwd=output_path,
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                # Thirty minutes, not two. Two minutes does not image a DVD on
                # any real machine: a 4 GB payload on a spinning disk takes
                # longer than that before it has finished reading, so the
                # timeout fired on ordinary discs rather than on stuck ones.
                # A genuinely stuck tool is still stopped after half an hour.
                timeout=1800
            )
            
            # Check if ISO was created successfully
            if os.path.exists(iso_path):
                iso_size = os.path.getsize(iso_path) / (1024 * 1024)  # MB
                self.update_status(f"✅ ISO created successfully: {iso_size:.1f} MB")
                self.report_disc_media_fit(os.path.getsize(iso_path))
                self.refresh_windows_icon_cache()
                
                self.update_status("📀 Ready to burn: Use disc burning software to burn this ISO")
                temp_iso_folder = os.path.join(output_path, "temp_iso_build")
                if os.path.exists(temp_iso_folder):
                    try:
                        shutil.rmtree(temp_iso_folder)
                        self.update_status("🧹 Cleaned temp ISO build folder")
                    except OSError:
                        pass

            else:
                self.update_status("❌ ISO tool ran but no file was generated")
                temp_iso_folder = os.path.join(output_path, "temp_iso_build")
                if os.path.exists(temp_iso_folder):
                    try:
                        shutil.rmtree(temp_iso_folder)
                        self.update_status("🧹 Cleaned temp ISO build folder")
                    except OSError:
                        pass
                self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)
                
        except subprocess.CalledProcessError as e:
            self.update_status(f"❌ ISO creation failed: {e}")
            if e.stderr:
                self.update_status(f"   Error details: {e.stderr.strip()}")
            self.update_status("🔄 Trying Python fallback method...")
            self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)
            
        except subprocess.TimeoutExpired:
            # Its own branch, and it does NOT fall back.
            #
            # A timeout used to land in the bare `except Exception` below and
            # be answered with the ZIP fallback, which writes an archive
            # carrying the .iso extension and reports success. So the one
            # case where the real tool was probably still working correctly
            # produced a file that is not a disc image, named as though it
            # were, announced with a tick.
            #
            # A partial ISO is left where it is: the tool may have been most
            # of the way through, and it is evidence either way.
            self.update_status("❌ ISO creation timed out after 30 minutes")
            self.update_status(
                "   The disc image was NOT created. Any partial file is left in place. "
                "Check free disk space and that no scanner is holding the build folder, "
                "then run the build again."
            )

        except Exception as e:
            self.update_status(f"❌ ISO creation error: {e}")
            self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)

    def create_python_iso_fallback(self, output_path, iso_path, iso_files, meta):
        """Last-resort archive when no ISO tool is available. NOT a disc image.

        This writes a ZIP. It used to write that ZIP to the .iso path and
        report "✅ Python ISO created", which is how a file that no burner
        can use came to be handed to ImgBurn: the extension said ISO, the
        status line said created, and the only hint was a note further down
        suggesting the contents be extracted first.

        Python's standard library cannot author ISO 9660. Rather than
        pretend, the archive now goes to a .zip path under its own name and
        says plainly that it is not burnable. A missing .iso is a build
        somebody has to fix; an .iso that is secretly a ZIP is a coaster,
        and possibly a coaster in a customer's envelope.
        """
        archive_path = os.path.splitext(iso_path)[0] + ".zip"
        try:
            self.update_status("📦 No ISO tool available: writing a ZIP archive instead...")

            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
                files_added = 0
                
                for item in iso_files:
                    item_path = os.path.join(output_path, item)
                    
                    if os.path.isfile(item_path):
                        zipf.write(item_path, item)
                        files_added += 1
                        
                    elif os.path.isdir(item_path):
                        # Add entire directory
                        for root, dirs, files in os.walk(item_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_name = os.path.relpath(file_path, output_path)
                                zipf.write(file_path, arc_name)
                                files_added += 1
                
                self.update_status(f"📦 Added {files_added} files to the archive")

            if os.path.exists(archive_path) and os.path.getsize(archive_path) > 1024:
                size_mb = os.path.getsize(archive_path) / (1024 * 1024)
                self.update_status(
                    f"⚠️ Wrote {os.path.basename(archive_path)} ({size_mb:.1f} MB) "
                    "- this is a ZIP, NOT a disc image"
                )
                self.update_status(
                    "   No disc was made. Do not hand this to a burner: it will produce a "
                    "coaster. Install mkisofs or oscdimg and build again to get a real ISO."
                )
            else:
                self.update_status("❌ Archive creation failed")

        except Exception as e:
            self.update_status(f"❌ Archive fallback failed: {e}")










    def generate_readme(self, output_path, meta):
        readme_path = os.path.join(output_path, "README.txt")
        title = sanitize_text(meta.get("Title") or "") or "Game"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"""=== {title} ===

    Welcome, and thank you for buying {title}!

    If the installer doesn't start on its own:
    1. Open this disc in File Explorer.
    2. Run 'setup.exe' to install the game.
    3. Once installed, launch it from your Start Menu.

    Enjoy!
""")
            if not self.remove_wti_branding.get():
                f.write("    ~ We the Indies\n")
















    def generate_autorun(self, output_path):
        """Create autorun.inf with proper disc icon and label"""
        self.update_status("Creating autorun.inf...")
        
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        disc_label = (sanitize_text(self.disc_name_var.get().strip())
                      or sanitize_text(meta.get("Title", "Game Disc"))
                      or "Game Disc")
        disc_icon_path = self.disc_icon_var.get().strip()
        
        if disc_icon_path and not os.path.exists(disc_icon_path):
            self.update_status(f"⚠️ Disc icon not found, falling back to the game icon: {disc_icon_path}")

        # Copy disc icon if provided. Always use a consistent filename.
        icon_filename = "disc_icon.ico"
        dest_path = os.path.join(output_path, icon_filename)

        # Clear any existing disc_icon.ico first
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass

        if disc_icon_path and os.path.exists(disc_icon_path):
            try:
                shutil.copy(disc_icon_path, dest_path)
                self.update_status(f"✅ Copied disc icon from: {os.path.basename(disc_icon_path)}")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy disc icon: {e}")
                icon_filename = "game_icon.ico"  # Fallback to game icon
        else:
            # Use game icon as fallback - copy it to be the disc icon
            self.update_status("📝 No disc icon specified, using game icon as fallback")
            game_icon_path = os.path.join(output_path, "game_icon.ico")
            if os.path.exists(game_icon_path):
                try:
                    shutil.copy(game_icon_path, dest_path)
                    self.update_status("✅ Copied game icon as disc icon")
                except Exception as e:
                    self.update_status(f"⚠️ Failed to copy game icon as disc icon: {e}")
                    icon_filename = "game_icon.ico"
            else:
                icon_filename = "game_icon.ico"
        
        # Create autorun.inf content (canonical keys; include extra icon directives for robustness)
        autorun_content = f"""[AutoRun]
Open=setup.exe
Icon={icon_filename}
IconFile={icon_filename}
IconResource={icon_filename},0
IconIndex=0
Label={disc_label}
"""
        
        autorun_path = os.path.join(output_path, "autorun.inf")
        try:
            # Use Windows-1252 encoding and CRLF to match Windows INF expectations
            with open(autorun_path, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
                f.write(autorun_content)
            self.update_status("✅ Created autorun.inf")
        except Exception as e:
            self.update_status(f"❌ Failed to create autorun.inf: {e}")












    def create_compatibility_test_script(self, output_path):
        """Create automated compatibility test script"""
        
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        game_title = escape_batch(meta.get('Title', 'Game')) or "Game"

        # The exe Rialto already located while staging, relative to the disc
        # root. Without it the test only globbed *.exe at the top level, so a
        # game living in a subfolder such as game\\Windows\\ was reported as two
        # CRITICAL ERRORS on a disc that was in fact fine.
        detected = (self.detect_primary_game_exe(output_path) or "").replace("/", "\\")
        detected_line = escape_batch(detected)

        test_script = f"""@echo off
echo ================================
echo {game_title} - Compatibility Test
echo ================================
echo.

set ERRORS=0
set GAME_EXE_FOUND=0

rem Test 1: Check required files
echo [TEST 1] Checking required files...

rem The exe Rialto found while building, wherever it lives on the disc. A game
rem in a subfolder is normal - only the top level was ever checked before.
if not "{detected_line}"=="" if exist "{detected_line}" (
    echo [OK] Game executable found: {detected_line}
    set GAME_EXE_FOUND=1
)

rem An install-first disc keeps the game inside setup.exe, so there is no exe
rem on the disc to find and that is not an error.
if %GAME_EXE_FOUND%==0 if exist "setup.exe" (
    echo [OK] Game ships inside the installer
    set GAME_EXE_FOUND=1
)

rem Check for any game executable (not just game.exe). The redistributables are
rem listed separately in Test 3, so they are skipped here - reporting
rem vcredist_x64.exe as "game executable found" read like a bug in the report.
if %GAME_EXE_FOUND%==0 for %%f in (*.exe) do (
    if /i not "%%f"=="setup.exe" if /i not "%%f"=="unins000.exe" if /i not "%%f"=="vcredist_x64.exe" if /i not "%%f"=="vcredist_x86.exe" if /i not "%%f"=="UnityCrashHandler64.exe" (
        echo [OK] Game executable found: %%f
        set GAME_EXE_FOUND=1
    )
)

if %GAME_EXE_FOUND%==0 (
    echo [X] No game executable found
    set /a ERRORS+=1
)

if not exist "setup.exe" (
    echo [X] setup.exe missing
    set /a ERRORS+=1
) else (
    echo [OK] setup.exe found
)

if not exist "autorun.inf" (
    echo [X] autorun.inf missing
    set /a ERRORS+=1
) else (
    echo [OK] autorun.inf found
)

rem Test 2: Check menu systems
echo.
echo [TEST 2] Checking menu systems...
if exist "start_menu.bat" (
    echo [OK] Menu selector found
) else (
    echo [X] Menu selector missing
    set /a ERRORS+=1
)

if exist "menu\\menu.exe" (
    echo [OK] Advanced menu found
) else (
    echo [!] Advanced menu missing (fallbacks available)
)

if exist "menu.bat" (
    echo [OK] Compatibility menu found
) else (
    echo [X] Compatibility menu missing
    set /a ERRORS+=1
)

rem Test 3: Check runtime dependencies
echo.
echo [TEST 3] Checking runtime dependencies...
if exist "vcredist_x64.exe" (
    echo [OK] VC++ x64 runtime included
) else (
    echo [!] VC++ x64 runtime missing
)

if exist "vcredist_x86.exe" (
    echo [OK] VC++ x86 runtime included
) else (
    echo [!] VC++ x86 runtime missing
)

rem Test 4: Check game executable
echo.
echo [TEST 4] Checking game executable...
if %GAME_EXE_FOUND%==1 (
    echo [OK] Game executable is present
) else (
    rem Deliberately not counted again: Test 1 already raised this exact
    rem problem, and counting it twice reported "2 CRITICAL ERRORS" for one.
    echo [X] No valid game executable found ^(see Test 1^)
)

rem Test 5: Check disc structure
echo.
echo [TEST 5] Checking disc structure...
if exist "bonus" (
    echo [OK] Bonus content folder found
) else (
    echo [i] No bonus content on this disc, which is fine
)

if exist "README.txt" (
    echo [OK] README.txt found
) else (
    echo [!] README.txt missing (recommended)
)

rem Results
echo.
echo ================================
if %ERRORS%==0 (
    echo [OK] ALL TESTS PASSED
    echo This disc should work on most systems
    echo ================================
    exit /b 0
) else (
    echo [X] %ERRORS% CRITICAL ERRORS FOUND
    echo This disc may not work on all systems
    echo ================================
    exit /b 1
)
"""
        
        test_path = os.path.join(output_path, "compatibility_test.bat")
        try:
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_script)
            self.update_status("✅ Created compatibility test script")
            
            # Run the test automatically
            self.run_compatibility_test(test_path, output_path)
            
        except Exception as e:
            self.update_status(f"❌ Failed to create test script: {e}")






    def run_compatibility_test(self, test_script_path, output_path):
        """Run the compatibility test and report results"""
        try:
            self.update_status("🧪 Running compatibility test...")
            
            result = subprocess.run(
                [test_script_path],
                cwd=output_path,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=60
            )
            
            # Show test output
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        self.update_status(f"   {line}")
            
            if result.returncode == 0:
                self.update_status("✅ Compatibility test PASSED - disc ready for distribution")
            else:
                self.update_status("❌ Compatibility test FAILED - check errors above")
                
        except Exception as e:
            self.update_status(f"⚠️ Could not run compatibility test: {e}")




    def create_runtime_installer_helper(self, output_path):
        """Create a helper script for runtime installation"""
        helper_content = '''@echo off
title Runtime Installer
color 0A
cls

echo =========================================
echo    Visual C++ Runtime Installer
echo =========================================
echo.

cd /d "%~dp0runtime"

if not exist vcredist_x64.exe if not exist vcredist_x86.exe (
    echo ERROR: Runtime files not found!
    echo.
    echo Please download from:
    echo https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo https://aka.ms/vs/17/release/vc_redist.x86.exe
    echo.
    pause
    exit /b 1
)

echo This will install required runtime components.
echo Administrator privileges may be required.
echo.
pause

if exist vcredist_x64.exe (
    echo.
    echo Installing Visual C++ Runtime x64...
    start /wait vcredist_x64.exe /quiet /norestart
    if errorlevel 1 (
        echo [!] Installation may require admin rights.
        echo [!] Right-click this file and select "Run as administrator"
    ) else (
        echo [OK] x64 runtime installed successfully
    )
)

if exist vcredist_x86.exe (
    echo.
    echo Installing Visual C++ Runtime x86...
    start /wait vcredist_x86.exe /quiet /norestart
    if errorlevel 1 (
        echo [!] Installation may require admin rights.
    ) else (
        echo [OK] x86 runtime installed successfully
    )
)

echo.
echo =========================================
echo Runtime installation complete!
echo You can now run the game.
echo =========================================
echo.
pause
'''
        
        helper_path = os.path.join(output_path, "install_runtimes.bat")
        with open(helper_path, "w", errors="replace") as f:
            f.write(helper_content)
        
        self.update_status("✅ Created runtime installer helper")














    def log_build_event(self, meta, output_path, success=True):
        log_path = os.path.join(APP_ROOT, "build_log.txt")
        from datetime import datetime

        # A log write must never turn a finished build into a reported failure
        # (e.g. Rialto.exe installed under a non-writable Program Files).
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("=== Rialto Build ===\n")
                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Title: {meta.get('Title', 'Unknown')}\n")
                f.write(f"Version: {meta.get('Version', 'N/A')}\n")
                f.write(f"Output: {output_path}\n")
                f.write(f"Success: {'Yes' if success else 'No'}\n")
                f.write(f"Features: menu.exe, setup.exe, gallery, readme, iso\n")
                f.write("\n")
        except OSError:
            pass




    def update_status(self, message):
        """Enhanced status updates with emoji indicators and timestamps"""
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        self.status_text.configure(state="normal")
        self.status_text.insert("end", formatted_message + "\n")
        
        # Color code based on message type
        if "✅" in message or "Success" in message:
            self.status_text.tag_add("success", f"end-2l", f"end-1l")
        elif "❌" in message or "Error" in message or "Failed" in message:
            self.status_text.tag_add("error", f"end-2l", f"end-1l")
        elif "⚠️" in message or "Warning" in message:
            self.status_text.tag_add("warning", f"end-2l", f"end-1l")
        elif "🔄" in message or "Processing" in message:
            self.status_text.tag_add("processing", f"end-2l", f"end-1l")
        elif "🔒" in message or "sign" in message.lower():
            self.status_text.tag_add("signing", f"end-2l", f"end-1l")
        elif "🔥" in message or "burn" in message.lower():
            self.status_text.tag_add("burn", f"end-2l", f"end-1l")
        elif "💿" in message or "disc" in message.lower() or "ISO" in message:
            self.status_text.tag_add("disc", f"end-2l", f"end-1l")
        
        self.status_text.see("end")
        self.status_text.configure(state="disabled")
        self.status_text.update_idletasks()







    def play_completion_jingle(self):
        jingle_path = asset_path("success.wav")
        if os.path.exists(jingle_path):
            try:
                winsound.PlaySound(jingle_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass




    def burn_to_dvd(self):
        import ctypes
        iso_path = None

        # Auto-select the most recent ISO in the output folder
        for subdir in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            subpath = os.path.join(OUTPUT_DIR, subdir)
            if os.path.isdir(subpath):
                for f in os.listdir(subpath):
                    if f.endswith(".iso"):
                        iso_path = os.path.join(subpath, f)
                        break
                if iso_path:
                    break

        if not iso_path:
            messagebox.showerror("Burn Failed", "No ISO file found to burn.")
            return

        try:
            # Launch ISO with the default Windows disc burner
            os.startfile(iso_path)
            messagebox.showinfo("Burn Started", "The ISO was opened with your default burner software.")
        except Exception as e:
            messagebox.showerror("Burn Failed", f"Could not open ISO with default burner:\n{e}")










    def _click_window(self, event):
        self._x_offset = event.x
        self._y_offset = event.y

    def _move_window(self, event):
        x = event.x_root - self._x_offset
        y = event.y_root - self._y_offset
        self.root.geometry(f"+{x}+{y}")


    def minimize_window(self):
        self.root.withdraw()  # Hide the window (simulate minimize)
        self.root.after(200, self._create_restore_listener)

    def _create_restore_listener(self):
        # Create a small listener window to restore Rialto
        restore_popup = tk.Toplevel()
        restore_popup.title("Restore Rialto")
        restore_popup.geometry("200x60+100+100")
        restore_popup.attributes("-topmost", True)
        restore_popup.configure(bg=self.dark_theme["bg"])

        tk.Label(restore_popup, text="Click to restore Rialto",
                 bg=self.dark_theme["bg"],
                 fg=self.dark_theme["fg"]).pack(pady=5)

        tk.Button(restore_popup, text="Restore",
                  bg=self.dark_theme["button_bg"],
                  fg=self.dark_theme["button_fg"],
                  command=lambda: self._restore_window(restore_popup)).pack(pady=5)

    def _restore_window(self, popup):
        popup.destroy()
        self.root.deiconify()







    # Steam's library art, at the sizes Steam actually wants. Written into
    # menu/steam/ at build time and copied into Steam's grid folder by the disc
    # menu when a player presses ADD TO STEAM.
    #
    # It has to happen here rather than there: the disc menu is a PyQt build
    # with Pillow deliberately excluded, so it can copy a PNG but cannot make
    # one. This way the art ships on the disc and the menu is a file copy.
    STEAM_ART = (
        # (filename, width, height, Steam's suffix, does the logo go into it)
        #
        # The hero is the one that does not. Steam draws logo.png over the
        # banner itself, so a hero with the logo already composited in shows
        # the title twice - once baked into the art and once again in Steam's
        # own overlay, at a different size and position.
        ("capsule.png", 600, 900, "p", True),        # library portrait, the big one
        ("wide.png", 920, 430, "", True),            # grid tile
        ("hero.png", 1920, 620, "_hero", False),     # banner behind the library page
    )

    def steam_art_sources(self):
        """The background and logo the Steam art is composed from.

        Nothing here is fetched from anywhere and nothing is per-game. These
        are the two fields Step 4 already asks every disc for: Menu Background
        and Game Logo. Whatever a game puts on its disc menu is what it gets in
        a Steam library.
        """
        background = self.bg_path_var.get().strip()
        if not (background and os.path.exists(background)):
            background = ""

        logo_path = self.logo_path_var.get().strip()
        if not (logo_path and os.path.exists(logo_path)) and self.current_game_path:
            candidate = os.path.join(self.current_game_path, "game_logo.png")
            logo_path = candidate if os.path.exists(candidate) else ""
        elif not os.path.exists(logo_path or ""):
            logo_path = ""
        return background, logo_path

    def _background_still(self, background):
        """One RGB frame out of whatever the author chose as a background.

        JPG, PNG and GIF open directly. A video needs a frame pulled out of it,
        which ffmpeg does if it is on the PATH. If it is not, this returns None
        and the caller falls back to a plain plate - the art still gets made,
        it just has no photograph in it.
        """
        if not background:
            return None
        extension = os.path.splitext(background)[1].lower()

        if extension in (".mp4", ".avi", ".mov", ".webm", ".mkv"):
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                return None
            frame = os.path.join(tempfile.gettempdir(),
                                 "rialto_steam_frame_%d.png" % os.getpid())
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-loglevel", "error", "-ss", "00:00:01",
                     "-i", background, "-frames:v", "1", frame],
                    capture_output=True, timeout=60,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if os.path.exists(frame):
                    still = Image.open(frame).convert("RGB")
                    still.load()
                    os.remove(frame)
                    return still
            except Exception:
                pass
            return None

        try:
            source = Image.open(background)
            if getattr(source, "is_animated", False):
                source.seek(0)
            return source.convert("RGB")
        except Exception:
            return None

    @staticmethod
    def _plate(width, height, logo):
        """A plain backdrop for games whose background cannot be turned into a still.

        Tinted from the logo's own colours when there is one, so it still looks
        like it belongs to the game rather than like a placeholder.
        """
        top, bottom = (26, 26, 32), (12, 12, 16)
        if logo is not None:
            try:
                sample = logo.convert("RGBA").resize((32, 32), Image.LANCZOS)
                pixels = [p for p in sample.getdata() if p[3] > 60]
                if pixels:
                    r = sum(p[0] for p in pixels) // len(pixels)
                    g = sum(p[1] for p in pixels) // len(pixels)
                    b = sum(p[2] for p in pixels) // len(pixels)
                    top = (max(12, r // 3), max(12, g // 3), max(12, b // 3))
                    bottom = (max(6, r // 7), max(6, g // 7), max(6, b // 7))
            except Exception:
                pass
        canvas = Image.new("RGB", (width, height), bottom)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        for y in range(height):
            blend = y / max(1, height - 1)
            draw.line([(0, y), (width, y)], fill=(
                int(top[0] + (bottom[0] - top[0]) * blend),
                int(top[1] + (bottom[1] - top[1]) * blend),
                int(top[2] + (bottom[2] - top[2]) * blend)))
        return canvas

    def stage_steam_art(self, menu_dir):
        """Compose Steam library art from the disc's own background and logo.

        Steam shows a non-Steam game as a grey box with the exe's filename
        under it. Every Rialto disc already has a background and a logo, so
        there is no reason for it to look like that.

        Works the same for every game: no lookup, no download, no per-title
        anything. Background missing or unreadable, a tinted plate stands in;
        logo missing, the background carries it alone; both missing, nothing is
        written and the build carries on exactly as it used to.
        """
        background, logo_path = self.steam_art_sources()

        logo = None
        if logo_path:
            try:
                logo = Image.open(logo_path).convert("RGBA")
                logo.load()
            except Exception:
                logo = None

        still = self._background_still(background)
        if still is None and logo is None:
            return  # nothing at all to work with

        steam_dir = os.path.join(menu_dir, "steam")
        try:
            os.makedirs(steam_dir, exist_ok=True)
            for filename, width, height, _suffix, carries_logo in self.STEAM_ART:
                if still is not None:
                    canvas = self._fill_crop(still, width, height)
                else:
                    canvas = self._plate(width, height, logo)
                if logo is not None and carries_logo:
                    self._overlay_logo(canvas, logo, width, height,
                                       dim=still is not None)
                canvas.save(os.path.join(steam_dir, filename), "PNG")

            # The transparent logo goes across untouched: Steam draws it over
            # the hero art itself and wants the alpha intact.
            if logo is not None:
                logo.save(os.path.join(steam_dir, "logo.png"), "PNG")

            made = "capsule, grid, hero" + (" and logo" if logo is not None else "")
            if still is None:
                made += " (from the logo alone; no usable background image)"
            self.update_status(f"✅ Made Steam library art: {made}")
        except Exception as e:
            # Cosmetic. A disc with no Steam art is the old behaviour.
            self.update_status(f"ℹ️ Skipped Steam library art: {e}")

    @staticmethod
    def _fill_crop(source, width, height):
        """Scale to cover the target box, then crop the overflow off the middle."""
        ratio = max(width / source.width, height / source.height)
        scaled = source.resize((max(1, int(source.width * ratio)),
                                max(1, int(source.height * ratio))), Image.LANCZOS)
        left = (scaled.width - width) // 2
        top = (scaled.height - height) // 3  # a third down keeps faces in frame
        return scaled.crop((left, top, left + width, top + height))

    @staticmethod
    def _overlay_logo(canvas, logo, width, height, dim=True):
        """Sit the logo on the art, darkening a photographic background first.

        `dim` is what the caller already asked for and this signature did not
        accept, so every build since Steam art landed raised TypeError, got
        swallowed by the cosmetic except around it, and reported "Skipped Steam
        library art" instead of making any.

        A frame lifted from the game is dimmed so the logo reads against
        whatever happens to be behind it. The generated plate is not: it is
        already a flat tint mixed from the logo's own colours, and dimming that
        a second time muddies the logo along with it.
        """
        if dim:
            from PIL import ImageEnhance
            darker = ImageEnhance.Brightness(canvas).enhance(0.62)
            canvas.paste(darker)

        target_w = int(width * 0.78)
        scale = min(target_w / logo.width, (height * 0.42) / logo.height)
        placed = logo.resize((max(1, int(logo.width * scale)),
                              max(1, int(logo.height * scale))), Image.LANCZOS)
        x = (width - placed.width) // 2
        y = int(height * 0.52) - placed.height // 2
        canvas.paste(placed, (x, y), placed)

    def stage_menu_artwork(self, menu_dir):
        """Copy the per-title artwork the disc menu reads at runtime.

        Background, game logo and the WTI bird (unless white-labelled). None of
        this is compiled into menu.exe - the menu picks these files up from its
        own folder, which is what lets one pre-built menu.exe serve every title.
        """
        # Copy the background to the menu folder
        bg_source = self.bg_path_var.get()
        bg_type = "none"
        if bg_source and not os.path.exists(bg_source):
            # Loud, because the alternative is a disc menu with no background
            # and a build log that never mentions it. The usual cause is a
            # saved profile pointing at art that has since been moved.
            self.update_status(f"⚠️ Menu background not found, building without one: {bg_source}")
        if bg_source and os.path.exists(bg_source):
            # GIF, still image, or a refused video
            ext = os.path.splitext(bg_source)[1].lower()
            if ext == '.gif':
                bg_dest = os.path.join(menu_dir, "background.gif")
                bg_type = "gif"
            elif ext in VIDEO_EXTENSIONS:
                # Not staged, on purpose. See VIDEO_EXTENSIONS.
                self.update_status(
                    "⚠️ Video backgrounds are not supported - a video plays only where "
                    "the player's own Windows can decode it, and a disc cannot be fixed "
                    "afterwards. Use an animated GIF (it looks the same everywhere) or "
                    "a still JPG. Building with no background.")
                bg_source = ""
                bg_dest = None
                bg_type = None
            else:
                bg_dest = os.path.join(menu_dir, "background.jpg")
                bg_type = "image"
            try:
                if bg_dest:
                    shutil.copy2(bg_source, bg_dest)
                    self.update_status(f"✅ Copied background {bg_type}")
            except OSError:
                pass

        # Check for game_logo.png in input folder OR from browse selector
        logo_exists = False
        logo_source = None
        
        # First check if user selected a logo via browse
        if self.logo_path_var.get() and os.path.exists(self.logo_path_var.get()):
            logo_source = self.logo_path_var.get()
        elif self.logo_path_var.get():
            self.update_status(f"⚠️ Game logo not found, building without one: {self.logo_path_var.get()}")
        # Otherwise check input folder
        if not logo_source and self.current_game_path:
            potential_logo = os.path.join(self.current_game_path, "game_logo.png")
            if os.path.exists(potential_logo):
                logo_source = potential_logo
        
        if logo_source:
            logo_dest = os.path.join(menu_dir, "game_logo.png")
            try:
                shutil.copy2(logo_source, logo_dest)
                logo_exists = True
                self.update_status("✅ Copied game logo")
            except OSError:
                pass
            # A logo with no alpha lands on the menu as a rectangle of whatever
            # the artist's canvas colour was. Said here, once, in plain terms.
            if image_has_transparency(logo_source) is False:
                self.update_status(
                    "⚠️ The game logo has no see-through background, so it will sit on "
                    "the menu as a solid rectangle. Export it as a PNG with transparency.")

        # Copy bird logo from Rialto root to menu directory (unless white-labeled)
        if not self.remove_wti_branding.get():
            bird_logo_source = asset_path("bird_logo.PNG")
            if os.path.exists(bird_logo_source):
                bird_logo_dest = os.path.join(menu_dir, "bird_logo.PNG")
                try:
                    shutil.copy2(bird_logo_source, bird_logo_dest)
                    self.update_status("✅ Copied bird logo")
                except Exception as e:
                    self.update_status(f"⚠️ Failed to copy bird logo: {e}")
        else:
            # White label: the final cleanup removes menu/ on a successful build,
            # but an interrupted or failed build can leave a stale bird_logo.PNG
            # from an earlier branded run. Delete every branding artifact staged
            # here so the rebuild is genuinely unbranded.
            # Branding is staged per disc (one menu/ folder), so this covers every
            # game on a multi-game disc at once.
            removed_branding = []
            for artifact in ("bird_logo.PNG", "bird_logo.png", "bird_icon.ico"):
                stale = os.path.join(menu_dir, artifact)
                if os.path.exists(stale):
                    try:
                        os.remove(stale)
                        removed_branding.append(artifact)
                    except OSError as e:
                        self.update_status(f"⚠️ Could not remove stale {artifact}: {e}")
            if removed_branding:
                self.update_status(f"🏷️ White label: removed stale branding ({', '.join(removed_branding)})")


# The disc menu, as source. Nothing about any particular game is spliced into
# this string: the title, the game list, branding, mods, bonus and the language
# all arrive at runtime from menu_config.json sitting next to the executable.
# That is what makes one pre-built menu.exe serve every title, so a frozen
# Rialto never has to shell out to PyInstaller on the author's machine.
MENU_TEMPLATE_SOURCE = '''import sys
import os
import json
import shutil
import subprocess
from PyQt5 import QtWidgets, QtGui, QtCore


def menu_dir():
    """The folder holding menu_config.json and the menu's artwork.

    Frozen: beside menu.exe. Source: beside this file. Same folder either way,
    because the build stages menu.exe into the menu/ folder the source launcher
    would have run from.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_menu_config():
    """Read menu_config.json once, at import."""
    try:
        cfg_path = os.path.join(menu_dir(), "menu_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return {}


MENU_CONFIG = load_menu_config()
# The window title and the on-screen title. "Game" is the fallback a config-less
# menu shows, which is also what an author sees if they run menu.exe by hand.
# A line break turned the caption into a two-line mess; a NUL or an escape
# character is worse, because this title is also written into the player's
# shortcuts.vdf, where control characters carry meaning. Every C0 control
# becomes a space, once, here.
_raw_title = str(MENU_CONFIG.get("title") or "Game")
_raw_title = ''.join(c if (c >= ' ' and c != '\\x7f') else ' ' for c in _raw_title)
MENU_TITLE = _raw_title.strip()[:200] or "Game"

# Compatibility mode: a launch argument the author's game already understands,
# offered as a button so the player never has to type one, such as a switch
# to OpenGL for machines where Vulkan is unavailable.
MAX_LAUNCH_ARGS = 16
MAX_LAUNCH_ARG_LEN = 256


def clean_launch_args(raw):
    """The compatibility-mode arguments from menu_config.json, or [].

    menu.exe is signed and generic; menu_config.json is plain JSON sitting
    next to it that anything can rewrite. These arguments go to Popen in list
    form, beside an executable path this menu resolved itself, so they cannot
    change WHICH program runs - only what it is told once it starts.

    Even so, the whole set is refused rather than quietly repaired if any of
    it looks wrong. A control character in a launch argument is not something
    an author typed, and dropping one argument out of a pair like
    ("-mode", "opengl") would silently change what the player asked for.
    """
    if not isinstance(raw, list) or not raw or len(raw) > MAX_LAUNCH_ARGS:
        return []
    cleaned = []
    for item in raw:
        if not isinstance(item, str) or not item or len(item) > MAX_LAUNCH_ARG_LEN:
            return []
        for ch in item:
            if ch < ' ' or ch == '\\x7f':
                return []
        cleaned.append(item)
    return cleaned

# Set the AppUserModelID to ensure proper icon in taskbar
try:
    import ctypes
    myappid = 'DiscMenu.' + MENU_TITLE.replace(" ", "") + '.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

class GameMenu(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # Initialize drag variables
        self.offset = None
        
        # Get the installation directory
        if getattr(sys, 'frozen', False):
            self.game_dir = os.path.dirname(os.path.dirname(sys.executable))
        else:
            self.game_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Set window icon
        icon_path = os.path.join(self.game_dir, "game_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
            # Also set for the application
            QtWidgets.QApplication.instance().setWindowIcon(QtGui.QIcon(icon_path))
        
        # Preview mode: Rialto launches the menu directly so authors can see it
        # before building - PLAY/UNINSTALL are disabled.
        self.preview_mode = os.environ.get("RIALTO_PREVIEW") == "1"

        # Menu configuration (title, multi-game list, branding, mods, bonus).
        # Read once at import by load_menu_config().
        self.menu_config = MENU_CONFIG
        self.menu_title = MENU_TITLE
        self.games = [g for g in self.menu_config.get("games", [])
                      if isinstance(g, dict) and g.get("exe")]

        # Comprehensive language translations
        self.translations = {
            "Arabic": {
                "play": "العب اللعبة", "bonus": "محتوى إضافي", "mods": "مودات", "compat": "وضع التوافق", "uninstall": "إلغاء التثبيت", "exit": "خروج",
                "language": "اللغة:", "error": "خطأ", "warning": "تحذير",
                "game_not_found": "لم يتم العثور على ملف اللعبة القابل للتنفيذ!",
                "bonus_not_found": "لم يتم العثور على المحتوى الإضافي!",
                "mods_not_found": "لم يتم العثور على أداة المودات!",
                "uninstaller_not_found": "لم يتم العثور على برنامج إلغاء التثبيت!",
                "confirm_uninstall": "هل أنت متأكد من أنك تريد إلغاء تثبيت هذه اللعبة؟",
                "install": "تثبيت اللعبة",
                "tip_install": "يشغّل المثبّت الموجود على هذا القرص.",
                "tip_compat": "يشغّل اللعبة بإعدادات مناسبة لكروت الرسوميات القديمة أو غير المدعومة.",
                "tip_bonus": "يفتح المحتوى الإضافي الموجود على هذا القرص.",
                "tip_mods": "يفتح أداة المودات الموجودة على هذا القرص.",
                "tip_steam": "يضيف اللعبة إلى مكتبة Steam لديك لتشغيلها من هناك.",
                "tip_uninstall": "يزيل اللعبة المثبتة. لن يتم المساس بملفات الحفظ الخاصة بك.",
                "yes": "نعم", "no": "لا", "cancel": "إلغاء"
            },
            "Bulgarian": {
                "play": "Играй", "bonus": "Бонус съдържание", "mods": "Модове", "compat": "Режим на съвместимост", "uninstall": "Деинсталирай", "exit": "Изход",
                "language": "Език:", "error": "Грешка", "warning": "Предупреждение",
                "game_not_found": "Изпълнимият файл на играта не е намерен!",
                "bonus_not_found": "Бонус съдържанието не е намерено!",
                "mods_not_found": "Инструментът за модове не е намерен!",
                "uninstaller_not_found": "Деинсталаторът не е намерен!",
                "confirm_uninstall": "Сигурни ли сте, че искате да деинсталирате тази игра?",
                "install": "Инсталирай играта",
                "tip_install": "Стартира инсталатора от този диск.",
                "tip_compat": "Стартира играта с настройки за по-стар или неподдържан графичен хардуер.",
                "tip_bonus": "Отваря допълнителните материали от този диск.",
                "tip_mods": "Отваря инструмента за модове от този диск.",
                "tip_steam": "Добавя играта към вашата Steam библиотека, за да я стартирате оттам.",
                "tip_uninstall": "Премахва инсталираната игра. Запазените игри не се засягат.",
                "yes": "Да", "no": "Не", "cancel": "Отказ"
            },
            "Chinese (Simplified)": {
                "play": "开始游戏", "bonus": "额外内容", "mods": "模组", "compat": "兼容模式", "uninstall": "卸载", "exit": "退出",
                "language": "语言:", "error": "错误", "warning": "警告",
                "game_not_found": "找不到游戏可执行文件！",
                "bonus_not_found": "找不到额外内容！",
                "mods_not_found": "找不到模组工具！",
                "uninstaller_not_found": "找不到卸载程序！",
                "confirm_uninstall": "您确定要卸载此游戏吗？",
                "install": "安装游戏",
                "tip_install": "运行本光盘上的安装程序。",
                "tip_compat": "以适合较旧或不受支持的显卡的设置启动游戏。",
                "tip_bonus": "打开本光盘附带的额外内容。",
                "tip_mods": "打开本光盘附带的模组工具。",
                "tip_steam": "将游戏添加到你的 Steam 库，以便从那里启动。",
                "tip_uninstall": "移除已安装的游戏。你的存档不会被删除。",
                "yes": "是", "no": "否", "cancel": "取消"
            },
            "Chinese (Traditional)": {
                "play": "開始遊戲", "bonus": "額外內容", "mods": "模組", "compat": "相容模式", "uninstall": "移除", "exit": "結束",
                "language": "語言:", "error": "錯誤", "warning": "警告",
                "game_not_found": "找不到遊戲執行檔！",
                "bonus_not_found": "找不到額外內容！",
                "mods_not_found": "找不到模組工具！",
                "uninstaller_not_found": "找不到移除程式！",
                "confirm_uninstall": "您確定要移除此遊戲嗎？",
                "install": "安裝遊戲",
                "tip_install": "執行本光碟上的安裝程式。",
                "tip_compat": "以適合較舊或不支援的顯示卡的設定啟動遊戲。",
                "tip_bonus": "開啟本光碟附帶的額外內容。",
                "tip_mods": "開啟本光碟附帶的模組工具。",
                "tip_steam": "將遊戲加入你的 Steam 收藏庫，以便從那裡啟動。",
                "tip_uninstall": "移除已安裝的遊戲。你的存檔不會被刪除。",
                "yes": "是", "no": "否", "cancel": "取消"
            },
            "Croatian": {
                "play": "Igraj", "bonus": "Bonus sadržaj", "mods": "Modovi", "compat": "Način kompatibilnosti", "uninstall": "Deinstaliraj", "exit": "Izlaz",
                "language": "Jezik:", "error": "Greška", "warning": "Upozorenje",
                "game_not_found": "Izvršna datoteka igre nije pronađena!",
                "bonus_not_found": "Bonus sadržaj nije pronađen!",
                "mods_not_found": "Alat za modove nije pronađen!",
                "uninstaller_not_found": "Deinstalater nije pronađen!",
                "confirm_uninstall": "Jeste li sigurni da želite deinstalirati ovu igru?",
                "install": "Instaliraj igru",
                "tip_install": "Pokreće instalacijski program s ovog diska.",
                "tip_compat": "Pokreće igru s postavkama za stariji ili nepodržani grafički hardver.",
                "tip_bonus": "Otvara dodatni sadržaj s ovog diska.",
                "tip_mods": "Otvara alat za modove s ovog diska.",
                "tip_steam": "Dodaje igru u vašu Steam biblioteku kako biste je pokrenuli odande.",
                "tip_uninstall": "Uklanja instaliranu igru. Vaši spremljeni podaci ostaju netaknuti.",
                "yes": "Da", "no": "Ne", "cancel": "Otkaži"
            },
            "Czech": {
                "play": "Hrát", "bonus": "Bonusový obsah", "mods": "Módy", "compat": "Režim kompatibility", "uninstall": "Odinstalovat", "exit": "Ukončit",
                "language": "Jazyk:", "error": "Chyba", "warning": "Varování",
                "game_not_found": "Spustitelný soubor hry nebyl nalezen!",
                "bonus_not_found": "Bonusový obsah nebyl nalezen!",
                "mods_not_found": "Nástroj pro módy nebyl nalezen!",
                "uninstaller_not_found": "Odinstalátor nebyl nalezen!",
                "confirm_uninstall": "Jste si jisti, že chcete tuto hru odinstalovat?",
                "install": "Nainstalovat hru",
                "tip_install": "Spustí instalátor z tohoto disku.",
                "tip_compat": "Spustí hru s nastavením pro starší nebo nepodporovaný grafický hardware.",
                "tip_bonus": "Otevře bonusový obsah z tohoto disku.",
                "tip_mods": "Otevře nástroj pro módy z tohoto disku.",
                "tip_steam": "Přidá hru do vaší knihovny Steam, abyste ji mohli spustit odtud.",
                "tip_uninstall": "Odstraní nainstalovanou hru. Vaše uložené pozice zůstanou zachovány.",
                "yes": "Ano", "no": "Ne", "cancel": "Zrušit"
            },
            "Danish": {
                "play": "Spil", "bonus": "Bonusindhold", "mods": "Mods", "compat": "Kompatibilitetstilstand", "uninstall": "Afinstaller", "exit": "Afslut",
                "language": "Sprog:", "error": "Fejl", "warning": "Advarsel",
                "game_not_found": "Spil eksekverbar fil ikke fundet!",
                "bonus_not_found": "Bonusindhold ikke fundet!",
                "mods_not_found": "Mod-værktøjet blev ikke fundet!",
                "uninstaller_not_found": "Afinstallationsprogram ikke fundet!",
                "confirm_uninstall": "Er du sikker på, at du vil afinstallere dette spil?",
                "install": "Installer spil",
                "tip_install": "Kører installationsprogrammet på denne disk.",
                "tip_compat": "Starter spillet med indstillinger til ældre eller ikke-understøttet grafikhardware.",
                "tip_bonus": "Åbner det ekstra materiale på denne disk.",
                "tip_mods": "Åbner modværktøjet på denne disk.",
                "tip_steam": "Føjer spillet til dit Steam-bibliotek, så du kan starte det derfra.",
                "tip_uninstall": "Fjerner det installerede spil. Dine gemte spil røres ikke.",
                "yes": "Ja", "no": "Nej", "cancel": "Annuller"
            },
            "Dutch": {
                "play": "Spelen", "bonus": "Bonus Inhoud", "mods": "Mods", "compat": "Compatibiliteitsmodus", "uninstall": "Verwijderen", "exit": "Afsluiten",
                "language": "Taal:", "error": "Fout", "warning": "Waarschuwing",
                "game_not_found": "Game uitvoerbaar bestand niet gevonden!",
                "bonus_not_found": "Bonus inhoud niet gevonden!",
                "mods_not_found": "Mod-tool niet gevonden!",
                "uninstaller_not_found": "Verwijderprogramma niet gevonden!",
                "confirm_uninstall": "Weet je zeker dat je dit spel wilt verwijderen?",
                "install": "Spel installeren",
                "tip_install": "Start het installatieprogramma op deze schijf.",
                "tip_compat": "Start het spel met instellingen voor oudere of niet-ondersteunde grafische hardware.",
                "tip_bonus": "Opent het extra materiaal op deze schijf.",
                "tip_mods": "Opent de modtool op deze schijf.",
                "tip_steam": "Voegt het spel toe aan je Steam-bibliotheek zodat je het daar kunt starten.",
                "tip_uninstall": "Verwijdert het geïnstalleerde spel. Je opgeslagen spellen blijven behouden.",
                "yes": "Ja", "no": "Nee", "cancel": "Annuleren"
            },
            "English": {
                "play": "Play Game", "bonus": "Bonus Content", "mods": "Mods", "compat": "Compatibility Mode", "uninstall": "Uninstall", "exit": "Exit",
                "language": "Language:", "error": "Error", "warning": "Warning",
                "game_not_found": "Game executable not found!",
                "bonus_not_found": "Bonus content not found!",
                "mods_not_found": "Mod launcher not found!",
                "uninstaller_not_found": "Uninstaller not found!",
                "confirm_uninstall": "Are you sure you want to uninstall this game?",
                "install": "Install Game",
                "tip_install": "Runs the installer on this disc.",
                "tip_compat": "Starts the game with settings for older or unsupported graphics hardware.",
                "tip_bonus": "Opens the extra material that came on this disc.",
                "tip_mods": "Opens the mod tool that came on this disc.",
                "tip_steam": "Adds the game to your Steam library so you can start it from there.",
                "tip_uninstall": "Removes the installed game. Your saved games are not touched.",
                "yes": "Yes", "no": "No", "cancel": "Cancel"
            },
            "Finnish": {
                "play": "Pelaa", "bonus": "Bonussisältö", "mods": "Modit", "compat": "Yhteensopivuustila", "uninstall": "Poista asennus", "exit": "Poistu",
                "language": "Kieli:", "error": "Virhe", "warning": "Varoitus",
                "game_not_found": "Pelin suoritettava tiedosto ei löytynyt!",
                "bonus_not_found": "Bonussisältöä ei löytynyt!",
                "mods_not_found": "Modityökalua ei löytynyt!",
                "uninstaller_not_found": "Asennuksen poisto-ohjelmaa ei löytynyt!",
                "confirm_uninstall": "Oletko varma, että haluat poistaa tämän pelin asennuksen?",
                "install": "Asenna peli",
                "tip_install": "Käynnistää tällä levyllä olevan asennusohjelman.",
                "tip_compat": "Käynnistää pelin asetuksilla vanhemmalle tai tukemattomalle näytönohjaimelle.",
                "tip_bonus": "Avaa tällä levyllä olevan lisämateriaalin.",
                "tip_mods": "Avaa tällä levyllä olevan modityökalun.",
                "tip_steam": "Lisää pelin Steam-kirjastoosi, jotta voit käynnistää sen sieltä.",
                "tip_uninstall": "Poistaa asennetun pelin. Tallennuksiisi ei kosketa.",
                "yes": "Kyllä", "no": "Ei", "cancel": "Peruuta"
            },
            "French": {
                "play": "Jouer", "bonus": "Contenu Bonus", "mods": "Mods", "compat": "Mode de compatibilité", "uninstall": "Désinstaller", "exit": "Quitter",
                "language": "Langue:", "error": "Erreur", "warning": "Avertissement",
                "game_not_found": "Exécutable du jeu introuvable!",
                "bonus_not_found": "Contenu bonus introuvable!",
                "mods_not_found": "Outil de mods introuvable !",
                "uninstaller_not_found": "Désinstallateur introuvable!",
                "confirm_uninstall": "Êtes-vous sûr de vouloir désinstaller ce jeu?",
                "install": "Installer le jeu",
                "tip_install": "Lance l'installateur présent sur ce disque.",
                "tip_compat": "Lance le jeu avec des réglages pour les cartes graphiques anciennes ou non prises en charge.",
                "tip_bonus": "Ouvre le contenu supplémentaire présent sur ce disque.",
                "tip_mods": "Ouvre l'outil de mods présent sur ce disque.",
                "tip_steam": "Ajoute le jeu à votre bibliothèque Steam pour le lancer depuis celle-ci.",
                "tip_uninstall": "Supprime le jeu installé. Vos sauvegardes ne sont pas touchées.",
                "yes": "Oui", "no": "Non", "cancel": "Annuler"
            },
            "German": {
                "play": "Spielen", "bonus": "Bonusinhalte", "mods": "Mods", "compat": "Kompatibilitätsmodus", "uninstall": "Deinstallieren", "exit": "Beenden",
                "language": "Sprache:", "error": "Fehler", "warning": "Warnung",
                "game_not_found": "Spiel-Datei nicht gefunden!",
                "bonus_not_found": "Bonusinhalte nicht gefunden!",
                "mods_not_found": "Mod-Tool nicht gefunden!",
                "uninstaller_not_found": "Deinstallationsprogramm nicht gefunden!",
                "confirm_uninstall": "Sind Sie sicher, dass Sie dieses Spiel deinstallieren möchten?",
                "install": "Spiel installieren",
                "tip_install": "Startet das Installationsprogramm auf dieser Disc.",
                "tip_compat": "Startet das Spiel mit Einstellungen für ältere oder nicht unterstützte Grafikhardware.",
                "tip_bonus": "Öffnet das Bonusmaterial auf dieser Disc.",
                "tip_mods": "Öffnet das Mod-Werkzeug auf dieser Disc.",
                "tip_steam": "Fügt das Spiel deiner Steam-Bibliothek hinzu, damit du es von dort starten kannst.",
                "tip_uninstall": "Entfernt das installierte Spiel. Deine Spielstände bleiben erhalten.",
                "yes": "Ja", "no": "Nein", "cancel": "Abbrechen"
            },
            "Greek": {
                "play": "Παίξε", "bonus": "Bonus Περιεχόμενο", "mods": "Mods", "compat": "Λειτουργία συμβατότητας", "uninstall": "Απεγκατάσταση", "exit": "Έξοδος",
                "language": "Γλώσσα:", "error": "Σφάλμα", "warning": "Προειδοποίηση",
                "game_not_found": "Το εκτελέσιμο αρχείο του παιχνιδιού δεν βρέθηκε!",
                "bonus_not_found": "Το bonus περιεχόμενο δεν βρέθηκε!",
                "mods_not_found": "Το εργαλείο mods δεν βρέθηκε!",
                "uninstaller_not_found": "Το πρόγραμμα απεγκατάστασης δεν βρέθηκε!",
                "confirm_uninstall": "Είστε σίγουροι ότι θέλετε να απεγκαταστήσετε αυτό το παιχνίδι;",
                "install": "Εγκατάσταση παιχνιδιού",
                "tip_install": "Εκτελεί το πρόγραμμα εγκατάστασης αυτού του δίσκου.",
                "tip_compat": "Ξεκινά το παιχνίδι με ρυθμίσεις για παλαιότερες ή μη υποστηριζόμενες κάρτες γραφικών.",
                "tip_bonus": "Ανοίγει το πρόσθετο υλικό αυτού του δίσκου.",
                "tip_mods": "Ανοίγει το εργαλείο mods αυτού του δίσκου.",
                "tip_steam": "Προσθέτει το παιχνίδι στη βιβλιοθήκη Steam σας για να το ξεκινάτε από εκεί.",
                "tip_uninstall": "Αφαιρεί το εγκατεστημένο παιχνίδι. Τα αποθηκευμένα σας παραμένουν.",
                "yes": "Ναι", "no": "Όχι", "cancel": "Ακύρωση"
            },
            "Hebrew": {
                "play": "שחק", "bonus": "תוכן בונוס", "mods": "מודים", "compat": "מצב תאימות", "uninstall": "הסר התקנה", "exit": "יציאה",
                "language": "שפה:", "error": "שגיאה", "warning": "אזהרה",
                "game_not_found": "קובץ המשחק לא נמצא!",
                "bonus_not_found": "תוכן הבונוס לא נמצא!",
                "mods_not_found": "כלי המודים לא נמצא!",
                "uninstaller_not_found": "תוכנת ההסרה לא נמצאה!",
                "confirm_uninstall": "האם אתה בטוח שברצונך להסיר את המשחק?",
                "install": "התקן את המשחק",
                "tip_install": "מריץ את תוכנית ההתקנה שבתקליטור הזה.",
                "tip_compat": "מפעיל את המשחק עם הגדרות לחומרה גרפית ישנה או שאינה נתמכת.",
                "tip_bonus": "פותח את התוכן הנוסף שבתקליטור הזה.",
                "tip_mods": "פותח את כלי המודים שבתקליטור הזה.",
                "tip_steam": "מוסיף את המשחק לספריית Steam שלך כדי להפעיל אותו משם.",
                "tip_uninstall": "מסיר את המשחק המותקן. קבצי השמירה שלך לא נפגעים.",
                "yes": "כן", "no": "לא", "cancel": "בטל"
            },
            "Hindi": {
                "play": "खेल खेलें", "bonus": "बोनस सामग्री", "mods": "मॉड्स", "compat": "संगतता मोड", "uninstall": "अनइंस्टॉल", "exit": "बाहर निकलें",
                "language": "भाषा:", "error": "त्रुटि", "warning": "चेतावनी",
                "game_not_found": "गेम एक्जीक्यूटेबल नहीं मिला!",
                "bonus_not_found": "बोनस सामग्री नहीं मिली!",
                "mods_not_found": "मॉड लॉन्चर नहीं मिला!",
                "uninstaller_not_found": "अनइंस्टॉलर नहीं मिला!",
                "confirm_uninstall": "क्या आप वाकई इस गेम को अनइंस्टॉल करना चाहते हैं?",
                "install": "गेम इंस्टॉल करें",
                "tip_install": "इस डिस्क पर मौजूद इंस्टॉलर चलाता है।",
                "tip_compat": "पुराने या असमर्थित ग्राफ़िक्स हार्डवेयर के लिए सेटिंग्स के साथ गेम शुरू करता है।",
                "tip_bonus": "इस डिस्क पर मौजूद अतिरिक्त सामग्री खोलता है।",
                "tip_mods": "इस डिस्क पर मौजूद मॉड टूल खोलता है।",
                "tip_steam": "गेम को आपकी Steam लाइब्रेरी में जोड़ता है ताकि आप उसे वहाँ से शुरू कर सकें।",
                "tip_uninstall": "इंस्टॉल किए गए गेम को हटाता है। आपकी सेव फ़ाइलों को छुआ नहीं जाता।",
                "yes": "हाँ", "no": "नहीं", "cancel": "रद्द करें"
            },
            "Hungarian": {
                "play": "Játék", "bonus": "Bónusz tartalom", "mods": "Modok", "compat": "Kompatibilitási mód", "uninstall": "Eltávolítás", "exit": "Kilépés",
                "language": "Nyelv:", "error": "Hiba", "warning": "Figyelmeztetés",
                "game_not_found": "A játék futtatható fájlja nem található!",
                "bonus_not_found": "A bónusz tartalom nem található!",
                "mods_not_found": "A mod eszköz nem található!",
                "uninstaller_not_found": "Az eltávolító nem található!",
                "confirm_uninstall": "Biztos benne, hogy el szeretné távolítani ezt a játékot?",
                "install": "Játék telepítése",
                "tip_install": "Elindítja a lemezen található telepítőt.",
                "tip_compat": "Elindítja a játékot régebbi vagy nem támogatott videokártyához való beállításokkal.",
                "tip_bonus": "Megnyitja a lemezen található bónusz tartalmat.",
                "tip_mods": "Megnyitja a lemezen található mod eszközt.",
                "tip_steam": "Hozzáadja a játékot a Steam könyvtáradhoz, hogy onnan indíthasd.",
                "tip_uninstall": "Eltávolítja a telepített játékot. A mentéseid érintetlenek maradnak.",
                "yes": "Igen", "no": "Nem", "cancel": "Mégse"
            },
            "Indonesian": {
                "play": "Main Game", "bonus": "Konten Bonus", "mods": "Mod", "compat": "Mode Kompatibilitas", "uninstall": "Hapus Instalan", "exit": "Keluar",
                "language": "Bahasa:", "error": "Kesalahan", "warning": "Peringatan",
                "game_not_found": "File game tidak ditemukan!",
                "bonus_not_found": "Konten bonus tidak ditemukan!",
                "mods_not_found": "Peluncur mod tidak ditemukan!",
                "uninstaller_not_found": "Uninstaller tidak ditemukan!",
                "confirm_uninstall": "Apakah Anda yakin ingin menghapus game ini?",
                "install": "Pasang Game",
                "tip_install": "Menjalankan pemasang pada disk ini.",
                "tip_compat": "Menjalankan game dengan pengaturan untuk perangkat grafis lama atau tidak didukung.",
                "tip_bonus": "Membuka konten tambahan pada disk ini.",
                "tip_mods": "Membuka alat mod pada disk ini.",
                "tip_steam": "Menambahkan game ke pustaka Steam Anda agar bisa dijalankan dari sana.",
                "tip_uninstall": "Menghapus game yang terpasang. File simpanan Anda tidak disentuh.",
                "yes": "Ya", "no": "Tidak", "cancel": "Batal"
            },
            "Italian": {
                "play": "Gioca", "bonus": "Contenuti Bonus", "mods": "Mod", "compat": "Modalità compatibilità", "uninstall": "Disinstalla", "exit": "Esci",
                "language": "Lingua:", "error": "Errore", "warning": "Avvertimento",
                "game_not_found": "File eseguibile del gioco non trovato!",
                "bonus_not_found": "Contenuti bonus non trovati!",
                "mods_not_found": "Strumento mod non trovato!",
                "uninstaller_not_found": "Programma di disinstallazione non trovato!",
                "confirm_uninstall": "Sei sicuro di voler disinstallare questo gioco?",
                "install": "Installa il gioco",
                "tip_install": "Avvia il programma di installazione su questo disco.",
                "tip_compat": "Avvia il gioco con impostazioni per schede grafiche datate o non supportate.",
                "tip_bonus": "Apre il materiale extra presente su questo disco.",
                "tip_mods": "Apre lo strumento per le mod presente su questo disco.",
                "tip_steam": "Aggiunge il gioco alla tua libreria Steam per avviarlo da lì.",
                "tip_uninstall": "Rimuove il gioco installato. I tuoi salvataggi non vengono toccati.",
                "yes": "Sì", "no": "No", "cancel": "Annulla"
            },
            "Japanese": {
                "play": "ゲームを開始", "bonus": "ボーナスコンテンツ", "mods": "MOD", "compat": "互換モード", "uninstall": "アンインストール", "exit": "終了",
                "language": "言語:", "error": "エラー", "warning": "警告",
                "game_not_found": "ゲームファイルが見つかりません！",
                "bonus_not_found": "ボーナスコンテンツが見つかりません！",
                "mods_not_found": "MODツールが見つかりません！",
                "uninstaller_not_found": "アンインストーラーが見つかりません！",
                "confirm_uninstall": "このゲームをアンインストールしてもよろしいですか？",
                "install": "ゲームをインストール",
                "tip_install": "このディスクのインストーラーを実行します。",
                "tip_compat": "古いまたは非対応のグラフィックス環境向けの設定でゲームを起動します。",
                "tip_bonus": "このディスクに収録された特典コンテンツを開きます。",
                "tip_mods": "このディスクに収録されたMODツールを開きます。",
                "tip_steam": "ゲームをSteamライブラリに追加し、そこから起動できるようにします。",
                "tip_uninstall": "インストールされたゲームを削除します。セーブデータはそのまま残ります。",
                "yes": "はい", "no": "いいえ", "cancel": "キャンセル"
            },
            "Korean": {
                "play": "게임 시작", "bonus": "보너스 콘텐츠", "mods": "모드", "compat": "호환 모드", "uninstall": "제거", "exit": "종료",
                "language": "언어:", "error": "오류", "warning": "경고",
                "game_not_found": "게임 실행 파일을 찾을 수 없습니다!",
                "bonus_not_found": "보너스 콘텐츠를 찾을 수 없습니다!",
                "mods_not_found": "모드 실행기를 찾을 수 없습니다!",
                "uninstaller_not_found": "제거 프로그램을 찾을 수 없습니다!",
                "confirm_uninstall": "이 게임을 제거하시겠습니까?",
                "install": "게임 설치",
                "tip_install": "이 디스크의 설치 프로그램을 실행합니다.",
                "tip_compat": "구형 또는 지원되지 않는 그래픽 하드웨어용 설정으로 게임을 시작합니다.",
                "tip_bonus": "이 디스크에 담긴 보너스 콘텐츠를 엽니다.",
                "tip_mods": "이 디스크에 담긴 모드 도구를 엽니다.",
                "tip_steam": "게임을 Steam 라이브러리에 추가하여 거기서 실행할 수 있게 합니다.",
                "tip_uninstall": "설치된 게임을 제거합니다. 저장 파일은 그대로 유지됩니다.",
                "yes": "예", "no": "아니요", "cancel": "취소"
            },
            "Norwegian": {
                "play": "Spill", "bonus": "Bonusinnhold", "mods": "Mods", "compat": "Kompatibilitetsmodus", "uninstall": "Avinstaller", "exit": "Avslutt",
                "language": "Språk:", "error": "Feil", "warning": "Advarsel",
                "game_not_found": "Spillkjørbar fil ikke funnet!",
                "bonus_not_found": "Bonusinnhold ikke funnet!",
                "mods_not_found": "Mod-verktøyet ble ikke funnet!",
                "uninstaller_not_found": "Avinstallerer ikke funnet!",
                "confirm_uninstall": "Er du sikker på at du vil avinstallere dette spillet?",
                "install": "Installer spill",
                "tip_install": "Kjører installasjonsprogrammet på denne platen.",
                "tip_compat": "Starter spillet med innstillinger for eldre eller ikke-støttet grafikkmaskinvare.",
                "tip_bonus": "Åpner bonusmaterialet på denne platen.",
                "tip_mods": "Åpner modverktøyet på denne platen.",
                "tip_steam": "Legger spillet til i Steam-biblioteket ditt så du kan starte det derfra.",
                "tip_uninstall": "Fjerner det installerte spillet. Lagringsfilene dine røres ikke.",
                "yes": "Ja", "no": "Nei", "cancel": "Avbryt"
            },
            "Polish": {
                "play": "Graj", "bonus": "Zawartość Bonusowa", "mods": "Mody", "compat": "Tryb zgodności", "uninstall": "Odinstaluj", "exit": "Wyjście",
                "language": "Język:", "error": "Błąd", "warning": "Ostrzeżenie",
                "game_not_found": "Plik wykonywalny gry nie został znaleziony!",
                "bonus_not_found": "Zawartość bonusowa nie została znaleziona!",
                "mods_not_found": "Nie znaleziono narzędzia do modów!",
                "uninstaller_not_found": "Program dezinstalacyjny nie został znaleziony!",
                "confirm_uninstall": "Czy na pewno chcesz odinstalować tę grę?",
                "install": "Zainstaluj grę",
                "tip_install": "Uruchamia instalator z tej płyty.",
                "tip_compat": "Uruchamia grę z ustawieniami dla starszych lub nieobsługiwanych kart graficznych.",
                "tip_bonus": "Otwiera dodatkowe materiały z tej płyty.",
                "tip_mods": "Otwiera narzędzie do modów z tej płyty.",
                "tip_steam": "Dodaje grę do twojej biblioteki Steam, byś mógł uruchamiać ją stamtąd.",
                "tip_uninstall": "Usuwa zainstalowaną grę. Twoje zapisy pozostają nienaruszone.",
                "yes": "Tak", "no": "Nie", "cancel": "Anuluj"
            },
            "Portuguese": {
                "play": "Jogar", "bonus": "Conteúdo Bônus", "mods": "Mods", "compat": "Modo de compatibilidade", "uninstall": "Desinstalar", "exit": "Sair",
                "language": "Idioma:", "error": "Erro", "warning": "Aviso",
                "game_not_found": "Executável do jogo não encontrado!",
                "bonus_not_found": "Conteúdo bônus não encontrado!",
                "mods_not_found": "Ferramenta de mods não encontrada!",
                "uninstaller_not_found": "Desinstalador não encontrado!",
                "confirm_uninstall": "Tem certeza de que deseja desinstalar este jogo?",
                "install": "Instalar jogo",
                "tip_install": "Executa o instalador deste disco.",
                "tip_compat": "Inicia o jogo com definições para placas gráficas antigas ou não suportadas.",
                "tip_bonus": "Abre o material extra que vem neste disco.",
                "tip_mods": "Abre a ferramenta de mods que vem neste disco.",
                "tip_steam": "Adiciona o jogo à sua biblioteca Steam para o iniciar a partir daí.",
                "tip_uninstall": "Remove o jogo instalado. Os seus jogos guardados não são afetados.",
                "yes": "Sim", "no": "Não", "cancel": "Cancelar"
            },
            "Portuguese (Brazil)": {
                "play": "Jogar", "bonus": "Conteúdo Bônus", "mods": "Mods", "compat": "Modo de compatibilidade", "uninstall": "Desinstalar", "exit": "Sair",
                "language": "Idioma:", "error": "Erro", "warning": "Aviso",
                "game_not_found": "Executável do jogo não encontrado!",
                "bonus_not_found": "Conteúdo bônus não encontrado!",
                "mods_not_found": "Ferramenta de mods não encontrada!",
                "uninstaller_not_found": "Desinstalador não encontrado!",
                "confirm_uninstall": "Tem certeza de que deseja desinstalar este jogo?",
                "install": "Instalar jogo",
                "tip_install": "Executa o instalador deste disco.",
                "tip_compat": "Inicia o jogo com configurações para placas de vídeo antigas ou não suportadas.",
                "tip_bonus": "Abre o material extra que veio neste disco.",
                "tip_mods": "Abre a ferramenta de mods que veio neste disco.",
                "tip_steam": "Adiciona o jogo à sua biblioteca Steam para iniciá-lo por lá.",
                "tip_uninstall": "Remove o jogo instalado. Seus jogos salvos não são afetados.",
                "yes": "Sim", "no": "Não", "cancel": "Cancelar"
            },
            "Romanian": {
                "play": "Joacă", "bonus": "Conținut Bonus", "mods": "Moduri", "compat": "Mod de compatibilitate", "uninstall": "Dezinstalează", "exit": "Ieșire",
                "language": "Limba:", "error": "Eroare", "warning": "Avertisment",
                "game_not_found": "Fișierul executabil al jocului nu a fost găsit!",
                "bonus_not_found": "Conținutul bonus nu a fost găsit!",
                "mods_not_found": "Instrumentul pentru moduri nu a fost găsit!",
                "uninstaller_not_found": "Dezinstalatorul nu a fost găsit!",
                "confirm_uninstall": "Ești sigur că vrei să dezinstalezi acest joc?",
                "install": "Instalează jocul",
                "tip_install": "Rulează programul de instalare de pe acest disc.",
                "tip_compat": "Pornește jocul cu setări pentru plăci grafice mai vechi sau neacceptate.",
                "tip_bonus": "Deschide materialul suplimentar de pe acest disc.",
                "tip_mods": "Deschide instrumentul de moduri de pe acest disc.",
                "tip_steam": "Adaugă jocul în biblioteca ta Steam ca să îl poți porni de acolo.",
                "tip_uninstall": "Elimină jocul instalat. Salvările tale nu sunt atinse.",
                "yes": "Da", "no": "Nu", "cancel": "Anulează"
            },
            "Russian": {
                "play": "Играть", "bonus": "Бонусный контент", "mods": "Моды", "compat": "Режим совместимости", "uninstall": "Удалить", "exit": "Выход",
                "language": "Язык:", "error": "Ошибка", "warning": "Предупреждение",
                "game_not_found": "Исполняемый файл игры не найден!",
                "bonus_not_found": "Бонусный контент не найден!",
                "mods_not_found": "Менеджер модов не найден!",
                "uninstaller_not_found": "Программа удаления не найдена!",
                "confirm_uninstall": "Вы уверены, что хотите удалить эту игру?",
                "install": "Установить игру",
                "tip_install": "Запускает установщик с этого диска.",
                "tip_compat": "Запускает игру с настройками для старых или неподдерживаемых видеокарт.",
                "tip_bonus": "Открывает дополнительные материалы с этого диска.",
                "tip_mods": "Открывает инструмент для модов с этого диска.",
                "tip_steam": "Добавляет игру в вашу библиотеку Steam, чтобы запускать её оттуда.",
                "tip_uninstall": "Удаляет установленную игру. Ваши сохранения не затрагиваются.",
                "yes": "Да", "no": "Нет", "cancel": "Отмена"
            },
            "Serbian": {
                "play": "Igraj", "bonus": "Bonus sadržaj", "mods": "Modovi", "compat": "Režim kompatibilnosti", "uninstall": "Deinstaliraj", "exit": "Izlaz",
                "language": "Jezik:", "error": "Greška", "warning": "Upozorenje",
                "game_not_found": "Izvršna datoteka igre nije pronađena!",
                "bonus_not_found": "Bonus sadržaj nije pronađen!",
                "mods_not_found": "Alat za modove nije pronađen!",
                "uninstaller_not_found": "Deinstalater nije pronađen!",
                "confirm_uninstall": "Da li ste sigurni da želite da deinstalirate ovu igru?",
                "install": "Instaliraj igru",
                "tip_install": "Pokreće instalacioni program sa ovog diska.",
                "tip_compat": "Pokreće igru sa podešavanjima za stariji ili nepodržani grafički hardver.",
                "tip_bonus": "Otvara dodatni sadržaj sa ovog diska.",
                "tip_mods": "Otvara alat za modove sa ovog diska.",
                "tip_steam": "Dodaje igru u vašu Steam biblioteku da biste je pokretali odatle.",
                "tip_uninstall": "Uklanja instaliranu igru. Vaši snimci igre ostaju netaknuti.",
                "yes": "Da", "no": "Ne", "cancel": "Otkaži"
            },
            "Slovak": {
                "play": "Hrať", "bonus": "Bonusový obsah", "mods": "Módy", "compat": "Režim kompatibility", "uninstall": "Odinštalovať", "exit": "Ukončiť",
                "language": "Jazyk:", "error": "Chyba", "warning": "Varovanie",
                "game_not_found": "Spustiteľný súbor hry nebol nájdený!",
                "bonus_not_found": "Bonusový obsah nebol nájdený!",
                "mods_not_found": "Nástroj pre módy sa nenašiel!",
                "uninstaller_not_found": "Odinštalátor nebol nájdený!",
                "confirm_uninstall": "Ste si istí, že chcete odinštalovať túto hru?",
                "install": "Nainštalovať hru",
                "tip_install": "Spustí inštalátor z tohto disku.",
                "tip_compat": "Spustí hru s nastaveniami pre staršie alebo nepodporované grafické karty.",
                "tip_bonus": "Otvorí bonusový obsah z tohto disku.",
                "tip_mods": "Otvorí nástroj na módy z tohto disku.",
                "tip_steam": "Pridá hru do vašej knižnice Steam, aby ste ju mohli spustiť odtiaľ.",
                "tip_uninstall": "Odstráni nainštalovanú hru. Vaše uložené pozície zostanú zachované.",
                "yes": "Áno", "no": "Nie", "cancel": "Zrušiť"
            },
            "Spanish": {
                "play": "Jugar", "bonus": "Contenido Extra", "mods": "Mods", "compat": "Modo de compatibilidad", "uninstall": "Desinstalar", "exit": "Salir",
                "language": "Idioma:", "error": "Error", "warning": "Advertencia",
                "game_not_found": "¡Ejecutable del juego no encontrado!",
                "bonus_not_found": "¡Contenido extra no encontrado!",
                "mods_not_found": "¡No se encontró el gestor de mods!",
                "uninstaller_not_found": "¡Desinstalador no encontrado!",
                "confirm_uninstall": "¿Estás seguro de que quieres desinstalar este juego?",
                "install": "Instalar juego",
                "tip_install": "Ejecuta el instalador de este disco.",
                "tip_compat": "Inicia el juego con ajustes para tarjetas gráficas antiguas o no compatibles.",
                "tip_bonus": "Abre el material extra incluido en este disco.",
                "tip_mods": "Abre la herramienta de mods incluida en este disco.",
                "tip_steam": "Añade el juego a tu biblioteca de Steam para iniciarlo desde ahí.",
                "tip_uninstall": "Elimina el juego instalado. Tus partidas guardadas no se tocan.",
                "yes": "Sí", "no": "No", "cancel": "Cancelar"
            },
            "Swedish": {
                "play": "Spela", "bonus": "Bonusinnehåll", "mods": "Mods", "compat": "Kompatibilitetsläge", "uninstall": "Avinstallera", "exit": "Avsluta",
                "language": "Språk:", "error": "Fel", "warning": "Varning",
                "game_not_found": "Spelkörbar fil hittades inte!",
                "bonus_not_found": "Bonusinnehåll hittades inte!",
                "mods_not_found": "Mod-verktyget hittades inte!",
                "uninstaller_not_found": "Avinstallerare hittades inte!",
                "confirm_uninstall": "Är du säker på att du vill avinstallera detta spel?",
                "install": "Installera spel",
                "tip_install": "Kör installationsprogrammet på den här skivan.",
                "tip_compat": "Startar spelet med inställningar för äldre eller ostödd grafikhårdvara.",
                "tip_bonus": "Öppnar bonusmaterialet på den här skivan.",
                "tip_mods": "Öppnar modverktyget på den här skivan.",
                "tip_steam": "Lägger till spelet i ditt Steam-bibliotek så att du kan starta det därifrån.",
                "tip_uninstall": "Tar bort det installerade spelet. Dina sparfiler rörs inte.",
                "yes": "Ja", "no": "Nej", "cancel": "Avbryt"
            },
            "Thai": {
                "play": "เล่นเกม", "bonus": "เนื้อหาโบนัส", "mods": "ม็อด", "compat": "โหมดความเข้ากันได้", "uninstall": "ถอนการติดตั้ง", "exit": "ออก",
                "language": "ภาษา:", "error": "ข้อผิดพลาด", "warning": "คำเตือน",
                "game_not_found": "ไม่พบไฟล์เกมที่สามารถเรียกใช้ได้!",
                "bonus_not_found": "ไม่พบเนื้อหาโบนัส!",
                "mods_not_found": "ไม่พบตัวจัดการม็อด!",
                "uninstaller_not_found": "ไม่พบโปรแกรมถอนการติดตั้ง!",
                "confirm_uninstall": "คุณแน่ใจหรือว่าต้องการถอนการติดตั้งเกมนี้?",
                "install": "ติดตั้งเกม",
                "tip_install": "เรียกใช้ตัวติดตั้งบนแผ่นนี้",
                "tip_compat": "เริ่มเกมด้วยการตั้งค่าสำหรับการ์ดจอรุ่นเก่าหรือที่ไม่รองรับ",
                "tip_bonus": "เปิดเนื้อหาพิเศษที่มาพร้อมแผ่นนี้",
                "tip_mods": "เปิดเครื่องมือม็อดที่มาพร้อมแผ่นนี้",
                "tip_steam": "เพิ่มเกมลงในคลัง Steam ของคุณเพื่อเปิดเล่นจากที่นั่น",
                "tip_uninstall": "ลบเกมที่ติดตั้งไว้ ไฟล์บันทึกของคุณจะไม่ถูกแตะต้อง",
                "yes": "ใช่", "no": "ไม่", "cancel": "ยกเลิก"
            },
            "Turkish": {
                "play": "Oyunu Oyna", "bonus": "Bonus İçerik", "mods": "Modlar", "compat": "Uyumluluk Modu", "uninstall": "Kaldır", "exit": "Çıkış",
                "language": "Dil:", "error": "Hata", "warning": "Uyarı",
                "game_not_found": "Oyun yürütülebilir dosyası bulunamadı!",
                "bonus_not_found": "Bonus içerik bulunamadı!",
                "mods_not_found": "Mod başlatıcı bulunamadı!",
                "uninstaller_not_found": "Kaldırıcı bulunamadı!",
                "confirm_uninstall": "Bu oyunu kaldırmak istediğinizden emin misiniz?",
                "install": "Oyunu Kur",
                "tip_install": "Bu diskteki kurulum programını çalıştırır.",
                "tip_compat": "Oyunu eski veya desteklenmeyen ekran kartları için ayarlarla başlatır.",
                "tip_bonus": "Bu diskteki ek içeriği açar.",
                "tip_mods": "Bu diskteki mod aracını açar.",
                "tip_steam": "Oyunu Steam kitaplığınıza ekler, böylece oradan başlatabilirsiniz.",
                "tip_uninstall": "Kurulu oyunu kaldırır. Kayıtlarınıza dokunulmaz.",
                "yes": "Evet", "no": "Hayır", "cancel": "İptal"
            },
            "Ukrainian": {
                "play": "Грати", "bonus": "Бонусний контент", "mods": "Моди", "compat": "Режим сумісності", "uninstall": "Видалити", "exit": "Вихід",
                "language": "Мова:", "error": "Помилка", "warning": "Попередження",
                "game_not_found": "Виконуваний файл гри не знайдено!",
                "bonus_not_found": "Бонусний контент не знайдено!",
                "mods_not_found": "Менеджер модів не знайдено!",
                "uninstaller_not_found": "Програму видалення не знайдено!",
                "confirm_uninstall": "Ви впевнені, що хочете видалити цю гру?",
                "install": "Встановити гру",
                "tip_install": "Запускає інсталятор із цього диска.",
                "tip_compat": "Запускає гру з налаштуваннями для старих або непідтримуваних відеокарт.",
                "tip_bonus": "Відкриває додаткові матеріали з цього диска.",
                "tip_mods": "Відкриває інструмент для модів з цього диска.",
                "tip_steam": "Додає гру до вашої бібліотеки Steam, щоб запускати її звідти.",
                "tip_uninstall": "Видаляє встановлену гру. Ваші збереження не зачіпаються.",
                "yes": "Так", "no": "Ні", "cancel": "Скасувати"
            },
            "Vietnamese": {
                "play": "Chơi Game", "bonus": "Nội dung Bonus", "mods": "Mod", "compat": "Chế độ tương thích", "uninstall": "Gỡ cài đặt", "exit": "Thoát",
                "language": "Ngôn ngữ:", "error": "Lỗi", "warning": "Cảnh báo",
                "game_not_found": "Không tìm thấy file thực thi game!",
                "bonus_not_found": "Không tìm thấy nội dung bonus!",
                "mods_not_found": "Không tìm thấy trình quản lý mod!",
                "uninstaller_not_found": "Không tìm thấy chương trình gỡ cài đặt!",
                "confirm_uninstall": "Bạn có chắc chắn muốn gỡ cài đặt game này?",
                "install": "Cài đặt trò chơi",
                "tip_install": "Chạy trình cài đặt trên đĩa này.",
                "tip_compat": "Khởi chạy trò chơi với thiết lập dành cho card đồ họa cũ hoặc không được hỗ trợ.",
                "tip_bonus": "Mở nội dung bổ sung có trên đĩa này.",
                "tip_mods": "Mở công cụ mod có trên đĩa này.",
                "tip_steam": "Thêm trò chơi vào thư viện Steam của bạn để khởi chạy từ đó.",
                "tip_uninstall": "Gỡ trò chơi đã cài đặt. Các tệp lưu của bạn không bị đụng đến.",
                "yes": "Có", "no": "Không", "cancel": "Hủy"
            }
        }
        
        # The menu language this disc was built with. `menu_config.json`
        # has carried a `language` key since the generic menu.exe landed
        # and nothing ever read it, so the box opened in English whatever
        # the key said.
        #
        # Rialto 1.5 writes "English" there unconditionally, so every disc
        # it has ever built behaves exactly as before. Other tools that write
        # this config may name the developer's own language, and a developer
        # who picked Japanese must not be promised a Japanese menu and then
        # get an English one on a disc that cannot be patched.
        #
        # Falls back to English for an absent, unknown or misspelled name:
        # a menu in a language nobody chose is better than one that will
        # not open. The combo below starts on the same value, so the
        # player can still change it.
        _configured_lang = str(MENU_CONFIG.get("language") or "").strip()
        self.current_lang = (
            _configured_lang if _configured_lang in self.translations else "English"
        )
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle(self.menu_title)
        self.setStyleSheet(self.TOOLTIP_STYLE)

        # 4K scaling support
        app = QtWidgets.QApplication.instance()
        screen = app.primaryScreen()
        screen_dpi = screen.logicalDotsPerInch()
        base_dpi = 96
        self.scale_factor = max(1.0, screen_dpi / base_dpi)
        
        # Scale window size for 4K displays
        base_width, base_height = 1280, 720
        scaled_width = int(base_width * self.scale_factor)
        scaled_height = int(base_height * self.scale_factor)
        
        self.setFixedSize(scaled_width, scaled_height)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        
        # Create main layout
        self.main_layout = QtWidgets.QStackedLayout()
        self.setLayout(self.main_layout)
        
        # Background widget
        self.bg_widget = QtWidgets.QWidget()
        self.main_layout.addWidget(self.bg_widget)
        
        # Set dark background color as default
        self.bg_widget.setStyleSheet("background-color: #1a1a1a;")
        
        # An animated GIF, or a still image. Deliberately NOT video.
        #
        # A background.mp4 plays only where the player's own Windows can decode
        # it: QMediaPlayer hands the file to Media Foundation, and on a machine
        # without the right codec it answers InvalidMedia *after* play() has
        # already returned - an opaque black rectangle across the whole menu,
        # on a disc that can never be patched. It can happen with an ordinary
        # H.264 file. A GIF is decoded by Qt itself and
        # needs nothing from the operating system, so it looks the same on
        # every machine, forever. That is the trade this menu makes.
        gif_path = os.path.join(menu_dir(), "background.gif")

        background_loaded = False

        if os.path.exists(gif_path):
            try:
                self.movie_label = QtWidgets.QLabel(self.bg_widget)
                self.movie_label.setGeometry(0, 0, scaled_width, scaled_height)
                self.movie_label.setScaledContents(True)

                self.movie = QtGui.QMovie(gif_path)
                self.movie.setScaledSize(QtCore.QSize(scaled_width, scaled_height))
                self.movie_label.setMovie(self.movie)
                self.movie.start()
                background_loaded = True
            except Exception:
                background_loaded = False

        if not background_loaded:
            # Still image. menu_dir() rather than __file__, which points into
            # the unpack folder when frozen and never at the disc.
            bg_path = os.path.join(menu_dir(), "background.jpg")

            if os.path.exists(bg_path):
                self.background = QtWidgets.QLabel(self.bg_widget)
                pixmap = QtGui.QPixmap(bg_path).scaled(scaled_width, scaled_height, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
                self.background.setPixmap(pixmap)
                self.background.setGeometry(0, 0, scaled_width, scaled_height)
        
        # Add dark overlay for better text contrast (more subtle)
        overlay = QtWidgets.QWidget(self.bg_widget)
        overlay.setGeometry(0, 0, scaled_width, scaled_height)
        overlay.setStyleSheet("background-color: rgba(0, 0, 0, 30);")
        
        # Main container for UI elements
        ui_container = QtWidgets.QWidget(self.bg_widget)
        ui_container.setGeometry(0, 0, scaled_width, scaled_height)
        ui_container.setStyleSheet("background-color: transparent;")
        
        main_layout = QtWidgets.QHBoxLayout(ui_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left side - Menu buttons (neutral color scheme)
        left_panel = QtWidgets.QWidget()
        left_panel.setFixedWidth(int(480 * self.scale_factor))
        left_panel.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(15, 15, 15, 220),
                    stop: 0.6 rgba(20, 20, 20, 200),
                    stop: 0.8 rgba(20, 20, 20, 140),
                    stop: 1 rgba(20, 20, 20, 0));
                border: none;
                margin: 0px;
                padding: 0px;
            }
        """)
        
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(int(40 * self.scale_factor), int(50 * self.scale_factor), int(50 * self.scale_factor), int(50 * self.scale_factor))
        left_layout.setSpacing(0)
        
        # Game title or logo
        logo_path = None
        
        # Look for game logo in current directory first (most up-to-date)
        potential_paths = []
        
        if getattr(sys, 'frozen', False):
            # Running as compiled exe - check exe directory first
            exe_dir = os.path.dirname(sys.executable)
            potential_paths = [
                os.path.join(exe_dir, "game_logo.png"),  # Same dir as executable
                os.path.join(os.path.dirname(exe_dir), "game_logo.png"),  # Parent dir
            ]
        else:
            # Running as script - check script directory
            script_dir = os.path.dirname(__file__)
            potential_paths = [
                os.path.join(script_dir, "game_logo.png"),
            ]
        
        # Find the first existing logo file
        for path in potential_paths:
            if os.path.exists(path):
                logo_path = path
                break
        
        # The game logo
        if logo_path and os.path.exists(logo_path):
            try:
                logo_label = QtWidgets.QLabel()
                logo_pixmap = QtGui.QPixmap(logo_path)
                
                # Check if pixmap loaded successfully
                if not logo_pixmap.isNull():
                    # Check if logo is square (or nearly square)
                    logo_size = logo_pixmap.size()
                    width_ratio = logo_size.width() / logo_size.height() if logo_size.height() > 0 else 1.0
                    is_square = 0.8 <= width_ratio <= 1.2  # Allow some tolerance for "square"
                    
                    # Scale logo to fit properly within available space
                    max_width = int(350 * self.scale_factor)  # Base size
                    max_height = int(120 * self.scale_factor)  # Base size
                    
                    # If square, increase size by 2x
                    if is_square:
                        max_width *= 2
                        max_height *= 2
                    
                    scaled_logo = logo_pixmap.scaled(max_width, max_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    logo_label.setPixmap(scaled_logo)
                    logo_label.setStyleSheet("background: transparent;")
                    halo = self._lift_dark_logo(logo_label, scaled_logo)

                    # The label used to be handed to the layout with no size of
                    # its own, so the layout was free to squash it and cut the
                    # bottom off the logo - which is exactly what it did. Claim
                    # the pixmap's real size, plus room for the halo to spread
                    # into, or the halo gets clipped the same way.
                    logo_label.setContentsMargins(0, halo, 0, halo)
                    logo_label.setMinimumSize(scaled_logo.width() + halo * 2,
                                              scaled_logo.height() + halo * 2)
                    logo_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                             QtWidgets.QSizePolicy.Fixed)
                    logo_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                    left_layout.addWidget(logo_label)
                else:
                    raise Exception("Failed to load pixmap")
            except Exception:
                pass
                # Fallback to text
                title_label = QtWidgets.QLabel(self.menu_title.upper())
                title_label.setStyleSheet("""
                    color: white;
                    font-size: """ + str(int(36 * self.scale_factor)) + """px;
                    font-weight: bold;
                    letter-spacing: """ + str(int(3 * self.scale_factor)) + """px;
                    margin-bottom: """ + str(int(20 * self.scale_factor)) + """px;
                    background: transparent;
                """)
                title_label.setWordWrap(True)
                left_layout.addWidget(title_label)
        else:
            # No logo found, use text
            title_label = QtWidgets.QLabel(self.menu_title.upper())
            title_label.setStyleSheet("""
                color: white;
                font-size: """ + str(int(36 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(3 * self.scale_factor)) + """px;
                margin-bottom: """ + str(int(20 * self.scale_factor)) + """px;
                background: transparent;
            """)
            title_label.setWordWrap(True)
            left_layout.addWidget(title_label)
        
        # Add some spacing
        left_layout.addSpacing(int(40 * self.scale_factor))
        
        # Menu buttons - Neutral white/gray color scheme
        button_style_template = """
            QPushButton {{
                background-color: transparent;
                color: {color};
                border: none;
                border-left: {border_width}px solid {border_color};
                text-align: left;
                padding: """ + str(int(15 * self.scale_factor)) + """px 0px """ + str(int(15 * self.scale_factor)) + """px """ + str(int(20 * self.scale_factor)) + """px;
                font-size: """ + str(int(22 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(2 * self.scale_factor)) + """px;
                margin: """ + str(int(5 * self.scale_factor)) + """px 0px;
            }}
            QPushButton:hover {{
                color: white;
                border-left: """ + str(int(4 * self.scale_factor)) + """px solid #ffffff;
                background-color: rgba(255, 255, 255, 10);
                padding-left: """ + str(int(30 * self.scale_factor)) + """px;
            }}
            QPushButton:pressed {{
                color: #cccccc;
                padding-left: """ + str(int(35 * self.scale_factor)) + """px;
            }}
        """
        
        # Create menu buttons with neutral colors. On an install-first disc the
        # game lives inside setup.exe, so the top button installs rather than
        # promising a launch that cannot happen.
        self.installer_path = self.disc_installer()
        trans = self.translations[self.current_lang]
        self.play_btn = QtWidgets.QPushButton(
            trans["install"].upper() if self.installer_path else "PLAY GAME")
        self.play_btn.clicked.connect(
            self.run_disc_installer if self.installer_path else self.launch_game)
        if self.installer_path:
            self.play_btn.setToolTip(trans["tip_install"])
        self.play_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(button_style_template.format(
            color="#ffffff", border_width="3", border_color="#ffffff"
        ))
        
        # Compatibility mode: a quieter line tucked under PLAY, not a second
        # heading beside it. It is the same act with one argument added, so it
        # reads as a way to play rather than a button competing for the eye -
        # smaller, dimmer, indented, and close enough to PLAY to belong to it.
        # Only appears when the author configured arguments that survive
        # checking; a game with no such mode never shows it.
        compat_style = """
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: """ + str(int(2 * self.scale_factor)) + """px 0px """ + str(int(6 * self.scale_factor)) + """px """ + str(int(34 * self.scale_factor)) + """px;
                font-size: """ + str(int(14 * self.scale_factor)) + """px;
                font-weight: normal;
                letter-spacing: """ + str(int(1 * self.scale_factor)) + """px;
                margin: 0px 0px """ + str(int(10 * self.scale_factor)) + """px 0px;
            }
            QPushButton:hover {
                color: #ffffff;
                padding-left: """ + str(int(40 * self.scale_factor)) + """px;
            }
            QPushButton:pressed {
                color: #cccccc;
                padding-left: """ + str(int(44 * self.scale_factor)) + """px;
            }
        """
        self.compat_btn = None
        if self.compatibility_args() and not self.installer_path:
            self.compat_btn = QtWidgets.QPushButton(self.compatibility_label())
            self.compat_btn.clicked.connect(self.launch_compatibility_mode)
            self.compat_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.compat_btn.setToolTip(self.compatibility_hint())
            self.compat_btn.setStyleSheet(compat_style)

        # Only show bonus button if bonus folder exists
        bonus_exists = False
        bonus_paths = [
            os.path.join(self.game_dir, "bonus"),
            os.path.join(self.game_dir, "BONUS"),
            os.path.join(self.game_dir, "Bonus")
        ]
        for bonus_path in bonus_paths:
            if os.path.exists(bonus_path) and os.path.isdir(bonus_path):
                bonus_exists = True
                break
        
        if bonus_exists:
            self.bonus_btn = QtWidgets.QPushButton("BONUS CONTENT")
            self.bonus_btn.clicked.connect(self.open_bonus)
            self.bonus_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.bonus_btn.setToolTip(self.translations[self.current_lang]["tip_bonus"])
            self.bonus_btn.setStyleSheet(button_style_template.format(
                color="#dddddd", border_width="2", border_color="transparent"
            ))

        # MODS: shown when a mod tool is actually there to run. It used to be
        # shown when a folder literally called "mods" existed, so a disc whose
        # author kept the tool in mod-maker/ never got the button - and the
        # button, when it did appear, could still find nothing.
        mods_exists = bool(self.menu_config.get("mod_launcher")) and \\
            self._resolve_mod_exe() is not None

        if mods_exists:
            self.mods_btn = QtWidgets.QPushButton(self.translations[self.current_lang]["mods"])
            self.mods_btn.clicked.connect(self.launch_mods)
            self.mods_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.mods_btn.setToolTip(self.translations[self.current_lang]["tip_mods"])
            self.mods_btn.setStyleSheet(compat_style)

        # ADD TO STEAM: only offered once the game is actually installed
        self.steam_btn = None
        if self.menu_config.get("steam_button") and os.path.exists(os.path.join(self.game_dir, "unins000.exe")):
            self.steam_btn = QtWidgets.QPushButton("Add to Steam")
            self.steam_btn.clicked.connect(self.add_to_steam)
            self.steam_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.steam_btn.setToolTip(self.translations[self.current_lang]["tip_steam"])
            self.steam_btn.setStyleSheet(compat_style)

        self.uninstall_btn = QtWidgets.QPushButton("UNINSTALL")
        self.uninstall_btn.clicked.connect(self.uninstall_game)
        self.uninstall_btn.setCursor(QtCore.Qt.PointingHandCursor)
        # PLAY and EXIT get no tooltip: a tooltip that restates the button is
        # noise. UNINSTALL gets one because "your saves are safe" is the thing
        # a player actually wants to know before clicking it.
        self.uninstall_btn.setToolTip(self.translations[self.current_lang]["tip_uninstall"])
        self.uninstall_btn.setStyleSheet(button_style_template.format(
            color="#cccccc", border_width="3", border_color="transparent"
        ))
        
        self.exit_btn = QtWidgets.QPushButton("EXIT")
        self.exit_btn.clicked.connect(self.close)
        self.exit_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.exit_btn.setStyleSheet(button_style_template.format(
            color="#cccccc", border_width="3", border_color="transparent"
        ))
        
        # Add buttons to layout conditionally
        # PLAY, then the quiet ways to start or extend it, then the
        # headings for everything else. Three shouted buttons rather than
        # six is the whole point.
        buttons_to_add = [self.play_btn]
        if self.compat_btn is not None:
            buttons_to_add.append(self.compat_btn)
        if mods_exists:
            buttons_to_add.append(self.mods_btn)
        if self.steam_btn is not None:
            buttons_to_add.append(self.steam_btn)
        if bonus_exists:
            buttons_to_add.append(self.bonus_btn)
        buttons_to_add.extend([self.uninstall_btn, self.exit_btn])
        
        for btn in buttons_to_add:
            left_layout.addWidget(btn)
        
        left_layout.addStretch()
        
        # Language selector at bottom
        lang_container = QtWidgets.QWidget()
        lang_container.setStyleSheet("background: transparent;")
        lang_layout = QtWidgets.QHBoxLayout(lang_container)
        lang_layout.setContentsMargins(int(20 * self.scale_factor), int(10 * self.scale_factor), 0, int(30 * self.scale_factor))
        
        self.lang_label = QtWidgets.QLabel("Menu Language:")
        self.lang_label.setStyleSheet("""
            color: #888888;
            font-size: """ + str(int(11 * self.scale_factor)) + """px;
            font-weight: bold;
            letter-spacing: """ + str(int(2 * self.scale_factor)) + """px;
            background: transparent;
        """)
        
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems(sorted(list(self.translations.keys())))
        self.lang_combo.setCurrentText(self.current_lang)
        self.lang_combo.currentTextChanged.connect(self.change_language)
        self.lang_combo.setFixedWidth(int(180 * self.scale_factor))
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(40, 40, 40, 180);
                color: #ffffff;
                border: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 20);
                border-radius: 0px;
                padding: """ + str(int(8 * self.scale_factor)) + """px """ + str(int(15 * self.scale_factor)) + """px;
                font-size: """ + str(int(12 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(1 * self.scale_factor)) + """px;
            }
            QComboBox::drop-down {
                border: none;
                width: """ + str(int(30 * self.scale_factor)) + """px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: """ + str(int(4 * self.scale_factor)) + """px solid transparent;
                border-right: """ + str(int(4 * self.scale_factor)) + """px solid transparent;
                border-top: """ + str(int(5 * self.scale_factor)) + """px solid #ffffff;
                margin-right: """ + str(int(10 * self.scale_factor)) + """px;
            }
            QComboBox:hover {
                background-color: rgba(60, 60, 60, 200);
                border: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 40);
            }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 30, 30, 240);
                color: #ffffff;
                selection-background-color: rgba(255, 255, 255, 30);
                selection-color: white;
                border: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 40);
                padding: """ + str(int(5 * self.scale_factor)) + """px;
            }
            QComboBox QAbstractItemView::item {
                padding: """ + str(int(8 * self.scale_factor)) + """px;
                border-bottom: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 10);
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: rgba(60, 60, 60, 200);
            }
        """)
        
        lang_layout.addWidget(self.lang_label)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        
        # Disable tab focus for language selector to prevent keyboard navigation
        self.lang_combo.setFocusPolicy(QtCore.Qt.NoFocus)
        
        left_layout.addWidget(lang_container)
        
        main_layout.addWidget(left_panel)
        main_layout.addStretch()
        
        # Add close button in top-right
        close_btn = QtWidgets.QPushButton("×", ui_container)
        close_btn.setGeometry(int(1225 * self.scale_factor), int(15 * self.scale_factor), int(40 * self.scale_factor), int(40 * self.scale_factor))
        close_btn.clicked.connect(self.close)
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666666;
                border: """ + str(int(2 * self.scale_factor)) + """px solid #666666;
                border-radius: """ + str(int(20 * self.scale_factor)) + """px;
                font-size: """ + str(int(28 * self.scale_factor)) + """px;
                font-weight: bold;
                text-align: center;
                padding-bottom: """ + str(int(4 * self.scale_factor)) + """px;
            }
            QPushButton:hover {
                color: white;
                border-color: white;
                background-color: rgba(255, 255, 255, 20);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 40);
            }
        """)
        
        # Add company logo in bottom-right
        company_logo_path = None
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            potential_paths = [
                os.path.join(exe_dir, "company_logo.png"),
                os.path.join(os.path.dirname(exe_dir), "company_logo.png"),
            ]
            for path in potential_paths:
                if os.path.exists(path):
                    company_logo_path = path
                    break
        else:
            company_logo_path = os.path.join(os.path.dirname(__file__), "company_logo.png")
            if not os.path.exists(company_logo_path):
                company_logo_path = None
        
        # Company logo and bird logo, bottom right
        logo_spacing = int(25 * self.scale_factor)  # Space between logos
        right_margin = int(25 * self.scale_factor)
        bottom_margin = int(25 * self.scale_factor)
        
        # Scale logo sizes by 1.25x
        max_logo_width = int(187 * self.scale_factor)
        max_logo_height = int(94 * self.scale_factor)
        
        # Load bird logo first (rightmost position)
        # Look for bird logo in multiple locations
        bird_logo_path = None
        # White-labelled disc: never show the bird, even if a stale copy was
        # left in this folder by an earlier build.
        if self.menu_config.get("remove_wti_branding"):
            bird_logo_path = None
        elif getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            potential_bird_paths = [
                os.path.join(exe_dir, "bird_logo.PNG"),
                os.path.join(os.path.dirname(exe_dir), "bird_logo.PNG"),
            ]
            for path in potential_bird_paths:
                if os.path.exists(path):
                    bird_logo_path = path
                    break
        else:
            bird_logo_path = os.path.join(os.path.dirname(__file__), "bird_logo.PNG")
            if not os.path.exists(bird_logo_path):
                bird_logo_path = None
        
        bird_logo_width = 0
        
        if bird_logo_path and os.path.exists(bird_logo_path):
            try:
                bird_logo_label = QtWidgets.QLabel(ui_container)
                bird_logo_pixmap = QtGui.QPixmap(bird_logo_path)
                if not bird_logo_pixmap.isNull():
                    scaled_bird_logo = bird_logo_pixmap.scaled(max_logo_width, max_logo_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    bird_logo_label.setPixmap(scaled_bird_logo)
                    bird_logo_label.setStyleSheet("background: transparent;")
                    bird_logo_width = scaled_bird_logo.width()
                    
                    # Position bird logo at rightmost position
                    bird_x = scaled_width - bird_logo_width - right_margin
                    bird_y = scaled_height - max_logo_height - bottom_margin
                    bird_logo_label.setGeometry(bird_x, bird_y, bird_logo_width, max_logo_height)
            except Exception:
                pass
        
        # Load company logo (to the left of bird logo)
        if company_logo_path and os.path.exists(company_logo_path):
            try:
                company_logo_label = QtWidgets.QLabel(ui_container)
                company_logo_pixmap = QtGui.QPixmap(company_logo_path)
                if not company_logo_pixmap.isNull():
                    scaled_company_logo = company_logo_pixmap.scaled(max_logo_width, max_logo_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    company_logo_label.setPixmap(scaled_company_logo)
                    company_logo_label.setStyleSheet("background: transparent;")
                    company_logo_width = scaled_company_logo.width()
                    
                    # Position company logo to the left of bird logo
                    if bird_logo_width > 0:
                        # Bird logo exists, position company logo to its left
                        company_x = scaled_width - bird_logo_width - logo_spacing - company_logo_width - right_margin
                    else:
                        # No bird logo, position company logo at original position
                        company_x = scaled_width - company_logo_width - right_margin
                    
                    company_y = scaled_height - max_logo_height - bottom_margin
                    company_logo_label.setGeometry(company_x, company_y, company_logo_width, max_logo_height)
            except Exception:
                pass
        
        # Add copyright text from Rialto configuration
        try:
            # Copyright text comes from the config (purely user-driven)
            copyright_text = self.menu_config.get("copyright_text", "")

            # Show copyright only if explicitly configured (no defaults)
            if copyright_text:
                copyright_label = QtWidgets.QLabel(copyright_text, ui_container)
                copyright_label.setStyleSheet("""
                    color: #666666;
                    font-size: """ + str(int(10 * self.scale_factor)) + """px;
                    background: transparent;
                    letter-spacing: """ + str(int(1 * self.scale_factor)) + """px;
                """)
                copyright_label.setWordWrap(True)
                copyright_label.setAlignment(QtCore.Qt.AlignLeft)
                # Position at bottom-left UNDER language selector (aligned with menu buttons)
                copyright_label.setGeometry(int(60 * self.scale_factor), int(650 * self.scale_factor), int(320 * self.scale_factor), int(40 * self.scale_factor))
        except Exception:
            pass
            
        # Initialize controller support
        self.init_controller_support()
    
    def change_language(self, lang):
        self.current_lang = lang
        trans = self.translations[lang]
        
        # Update UI text - keep label text as "Menu Language:" 
        self.play_btn.setText(
            trans["install"].upper() if getattr(self, "installer_path", "")
            else trans["play"].upper())
        if getattr(self, "installer_path", ""):
            self.play_btn.setToolTip(trans["tip_install"])
        # compatibility_label() and compatibility_hint() re-read the author's
        # overrides, so a disc that named or described the mode itself keeps
        # that wording in every language.
        if getattr(self, 'compat_btn', None) is not None:
            self.compat_btn.setText(self.compatibility_label())
            self.compat_btn.setToolTip(self.compatibility_hint())
        if hasattr(self, 'bonus_btn'):
            self.bonus_btn.setText(trans["bonus"].upper())
            self.bonus_btn.setToolTip(trans["tip_bonus"])
        if hasattr(self, 'mods_btn'):
            self.mods_btn.setText(trans["mods"])
            self.mods_btn.setToolTip(trans["tip_mods"])
        if getattr(self, 'steam_btn', None) is not None:
            self.steam_btn.setToolTip(trans["tip_steam"])
        self.uninstall_btn.setText(trans["uninstall"].upper())
        self.uninstall_btn.setToolTip(trans["tip_uninstall"])
        self.exit_btn.setText(trans["exit"].upper())
    
    # --- ADD TO STEAM (adds installed game to the Steam library) ---

    def _steam_root(self):
        """Steam's install folder, or "".

        HKCU first, which is where a normal per-user install records it, then
        HKLM for a machine-wide one, then the two default paths. Any of the
        three can be the only one present on a given PC.
        """
        try:
            import winreg
        except ImportError:
            return ""
        for hive, key_path in ((winreg.HKEY_CURRENT_USER, r"Software\\Valve\\Steam"),
                               (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\WOW6432Node\\Valve\\Steam"),
                               (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Valve\\Steam")):
            for value_name in ("SteamPath", "InstallPath"):
                try:
                    key = winreg.OpenKey(hive, key_path)
                    try:
                        found, _type = winreg.QueryValueEx(key, value_name)
                    finally:
                        winreg.CloseKey(key)
                    if found and os.path.isdir(found):
                        return os.path.normpath(found)
                except OSError:
                    continue
        for guess in (r"C:\\Program Files (x86)\\Steam", r"C:\\Program Files\\Steam"):
            if os.path.isdir(guess):
                return guess
        return ""

    def _steam_is_running(self):
        """True if Steam is up right now.

        Steam holds the shortcut list in memory and writes it back out when it
        exits, so anything added underneath a running Steam is thrown away when
        the player next closes it. Worth saying out loud rather than letting
        them wonder why the game vanished.
        """
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\\Valve\\Steam\\ActiveProcess")
            try:
                pid, _type = winreg.QueryValueEx(key, "pid")
            finally:
                winreg.CloseKey(key)
            return bool(pid)
        except Exception:
            return False

    def _steam_shortcuts_paths(self):
        """shortcuts.vdf for every Steam profile on this PC.

        Includes profiles whose file does not exist yet: a player who has never
        added a non-Steam game has the config folder but no shortcuts.vdf, and
        that is exactly the case where this button is most useful.
        """
        steam_path = self._steam_root()
        if not steam_path:
            return []
        userdata = os.path.join(steam_path, "userdata")
        if not os.path.isdir(userdata):
            return []
        paths = []
        try:
            entries = sorted(os.listdir(userdata))
        except OSError:
            return []
        for entry in entries:
            # Account IDs are numeric; "0" is Steam's anonymous placeholder.
            if not entry.isdigit() or entry == "0":
                continue
            config_dir = os.path.join(userdata, entry, "config")
            if os.path.isdir(config_dir):
                paths.append(os.path.join(config_dir, "shortcuts.vdf"))
        return paths

    def _count_vdf_entries(self, data):
        # Walk the binary VDF just enough to count the top-level shortcuts.
        # Types: 0x00 nested map, 0x01 string, 0x02 int32, 0x08 end of map.
        pos = data.index(b'\\x00shortcuts\\x00') + len(b'\\x00shortcuts\\x00')
        count = 0
        depth = 0
        while pos < len(data):
            kind = data[pos]
            pos += 1
            if kind == 8:
                if depth == 0:
                    return count
                depth -= 1
                continue
            end = data.index(b'\\x00', pos)
            pos = end + 1
            if kind == 0:
                if depth == 0:
                    count += 1
                depth += 1
            elif kind == 1:
                pos = data.index(b'\\x00', pos) + 1
            elif kind == 2:
                pos += 4
            else:
                raise ValueError("unknown vdf field type %r" % kind)
        raise ValueError("unterminated vdf")

    def _vdf_existing_exes(self, data):
        """Every Exe value already in this shortcuts.vdf, normalised for comparison.

        Steam writes the path wrapped in quotes; the comparison strips those and
        lowercases, so clicking ADD TO STEAM twice cannot leave two copies of
        the same game sitting in somebody's library.
        """
        found = set()
        marker = b'\\x01Exe\\x00'
        pos = 0
        while True:
            at = data.find(marker, pos)
            if at == -1:
                return found
            start = at + len(marker)
            end = data.find(b'\\x00', start)
            if end == -1:
                return found
            value = data[start:end].decode('utf-8', 'replace').strip().strip('"')
            if value:
                try:
                    found.add(os.path.normcase(os.path.normpath(value)))
                except ValueError:
                    found.add(value.lower())
            pos = end + 1

    def _steam_appid(self, name, exe):
        """The id Steam files this shortcut under.

        Must be computed exactly the way _vdf_shortcut_entry writes it, because
        the library art is named after this number. One definition, called from
        both places, so the two cannot drift apart and quietly stop the art
        from showing up.
        """
        import zlib
        return (zlib.crc32((exe + name).encode('utf-8')) | 0x80000000) & 0xFFFFFFFF

    def _install_steam_art(self, grid_dir, appid):
        """Drop this disc's library art into Steam's grid folder.

        Rialto composed the pictures at build time and put them in menu/steam/,
        because the disc menu ships without Pillow and cannot make them itself.
        All that happens here is a copy under the names Steam looks for:
        <appid>p.png is the tall library capsule, <appid>.png the grid tile,
        <appid>_hero.png the banner, <appid>_logo.png the transparent logo
        Steam lays over the banner.

        Entirely cosmetic, and every step of it is allowed to fail: without it
        Steam shows a grey box with the exe name under it, which is what every
        non-Steam shortcut looks like anyway.
        """
        source_dir = os.path.join(menu_dir(), "steam")
        if not os.path.isdir(source_dir):
            return False
        pairs = (("capsule.png", "%dp.png"), ("wide.png", "%d.png"),
                 ("hero.png", "%d_hero.png"), ("logo.png", "%d_logo.png"))
        copied = False
        try:
            os.makedirs(grid_dir, exist_ok=True)
        except OSError:
            return False
        for filename, pattern in pairs:
            source = os.path.join(source_dir, filename)
            try:
                if not os.path.isfile(source) or os.path.getsize(source) == 0:
                    continue
                shutil.copy2(source, os.path.join(grid_dir, pattern % appid))
                copied = True
            except (OSError, ValueError):
                continue
        return copied

    def _vdf_shortcut_entry(self, index, name, exe, start_dir, icon):
        import struct

        def string_field(key, value):
            # Every value in this format is NUL-terminated, so a NUL inside one
            # ends the field early and Steam reads what follows as further
            # fields - LaunchOptions among them, which it passes to the process
            # it starts. The title comes from menu_config.json, and JSON can
            # encode \\u0000, so the value gets cleaned rather than trusted: a
            # crafted title would otherwise leave a command in the player's
            # Steam library that outlives the disc being ejected.
            text = ''.join(c for c in str(value) if c >= ' ' and c != '\\x7f')
            return b'\\x01' + key + b'\\x00' + text.encode('utf-8', 'replace') + b'\\x00'

        def int_field(key, value):
            return b'\\x02' + key + b'\\x00' + struct.pack('<I', value)

        # Nothing legitimate is anywhere near this long, and shortcuts.vdf is
        # the player's entire non-Steam library.
        name = str(name)[:200]
        appid = self._steam_appid(name, exe)
        entry = b'\\x00' + str(index).encode('ascii') + b'\\x00'
        entry += int_field(b'appid', appid)
        entry += string_field(b'AppName', name)
        entry += string_field(b'Exe', '"%s"' % exe)
        entry += string_field(b'StartDir', '"%s"' % start_dir)
        entry += string_field(b'icon', icon)
        entry += string_field(b'ShortcutPath', '')
        entry += string_field(b'LaunchOptions', '')
        entry += int_field(b'IsHidden', 0)
        entry += int_field(b'AllowDesktopConfig', 1)
        entry += int_field(b'AllowOverlay', 1)
        entry += int_field(b'OpenVR', 0)
        entry += int_field(b'Devkit', 0)
        entry += string_field(b'DevkitGameID', '')
        entry += int_field(b'DevkitOverrideAppID', 0)
        entry += int_field(b'LastPlayTime', 0)
        entry += b'\\x00tags\\x00\\x08'
        entry += b'\\x08'
        return entry

    def _steam_game_list(self):
        """The games to offer Steam: the same ones PLAY would start.

        Falls through to find_game_exe rather than repeating a shorter version
        of its scan, so a game whose binary is three folders down ends up in
        Steam pointing at the thing that actually runs, not at whatever .exe
        happened to sort first in the install root.
        """
        games = []
        if self.games:
            for game in self.games:
                exe_path = self._configured_exe(game["exe"])
                if exe_path:
                    label = game.get("name") or os.path.splitext(os.path.basename(exe_path))[0]
                    games.append((label, exe_path))
            return games

        resolved, _searched = self.find_game_exe()
        if resolved and os.path.isfile(resolved):
            title = self.menu_title or os.path.splitext(os.path.basename(resolved))[0]
            games.append((title, os.path.normpath(resolved)))
        return games

    def _write_vdf_atomically(self, vdf_path, payload):
        """Replace shortcuts.vdf without ever leaving it half-written.

        Writing straight into the real file means a full disk, a crash or an
        antivirus interruption part-way through destroys the player's entire
        list of non-Steam games. The new list goes to a temp file beside it,
        gets flushed to the platter, and only then replaces the original, which
        on Windows is atomic.
        """
        temp_path = vdf_path + ".rialto-new"
        try:
            with open(temp_path, 'wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, vdf_path)
            return True
        except OSError:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            return False

    def add_to_steam(self):
        if self.preview_mode:
            self.show_preview_notice()
            return
        games = self._steam_game_list()
        if not games:
            self._menu_message(
                "Nothing to add",
                "No game was found to put in your Steam library.",
                "Install the game from the disc first, then try again.")
            return
        shortcut_files = self._steam_shortcuts_paths()
        if not shortcut_files:
            self._menu_message(
                "Steam not found",
                "No Steam profile was found on this PC.",
                "Install Steam and sign in once, then try again. Steam only creates "
                "the folder this needs after the first sign-in.")
            return

        # Nothing is written while Steam is up. Steam holds this list in memory
        # and writes its own copy back out when it exits, so an entry added
        # underneath it is discarded the moment the player quits Steam - the
        # game appears to have been added, and then simply is not there. Saying
        # so before touching the file is the only version of this that does not
        # waste the player's time. Closing the window is not exiting: Steam
        # keeps running in the notification area.
        if self._steam_is_running():
            self._menu_message(
                "Exit Steam first",
                "Steam is running, so nothing has been added yet.",
                "Steam would undo it: it keeps its list of non-Steam games in "
                "memory and writes that copy back out when it closes.\\n\\n"
                "Exit Steam completely - right-click the Steam icon in the "
                "notification area, by the clock, and choose Exit. Closing the "
                "window is not enough. Then press ADD TO STEAM again.")
            return

        icon = os.path.join(self.game_dir, "game_icon.ico")
        icon = icon if os.path.exists(icon) else ""

        added_names = []
        already_there = []
        reached_any = False
        blocked = []

        for vdf_path in shortcut_files:
            try:
                existing = set()
                next_index = 0
                body = b'\\x00shortcuts\\x00'

                if os.path.exists(vdf_path) and os.path.getsize(vdf_path) > 0:
                    with open(vdf_path, 'rb') as f:
                        data = f.read()
                    if not data.startswith(b'\\x00shortcuts\\x00') or not data.endswith(b'\\x08\\x08'):
                        # Not a shape this code understands. Leaving somebody's
                        # library alone is the only safe move.
                        blocked.append("unreadable list")
                        continue
                    try:
                        next_index = self._count_vdf_entries(data)
                    except (ValueError, IndexError):
                        blocked.append("unreadable list")
                        continue
                    existing = self._vdf_existing_exes(data)
                    body = data[:-2]
                    try:
                        with open(vdf_path + '.rialto-backup', 'wb') as f:
                            f.write(data)
                    except OSError:
                        pass  # a backup is a nicety, not a reason to stop

                reached_any = True

                # Skip anything already in this profile's library, so a second
                # click is a no-op rather than a duplicate.
                pending = []
                for name, exe_path in games:
                    key = os.path.normcase(os.path.normpath(exe_path))
                    if key in existing:
                        if name not in already_there:
                            already_there.append(name)
                    else:
                        pending.append((name, exe_path))

                if not pending:
                    continue

                for offset, (name, exe_path) in enumerate(pending):
                    body += self._vdf_shortcut_entry(next_index + offset, name, exe_path,
                                                     os.path.dirname(exe_path), icon)

                if not self._write_vdf_atomically(vdf_path, body + b'\\x08\\x08'):
                    blocked.append("could not be written")
                    continue

                # Library art, so the game does not sit in Steam as a grey box
                # with a filename under it. Never mentioned in the popup: the
                # player opens Steam and sees it, which is worth more than
                # being told about it beforehand.
                grid_dir = os.path.join(os.path.dirname(vdf_path), "grid")
                for name, exe_path in pending:
                    self._install_steam_art(grid_dir, self._steam_appid(name, exe_path))

                for name, _exe in pending:
                    if name not in added_names:
                        added_names.append(name)
            except Exception:
                blocked.append("could not be written")
                continue

        if added_names:
            # Steam cannot be running here - the guard above returned already -
            # so there is no "restart Steam" case left to describe.
            detail = "It will be there the next time you start Steam."
            self._menu_message(
                "Added to Steam",
                "%s is in your Steam library now, under non-Steam games."
                % ", ".join(added_names),
                detail)
        elif already_there:
            self._menu_message(
                "Already in Steam",
                "%s is already in your Steam library." % ", ".join(already_there),
                "Nothing was changed. Remove it from Steam first if you want to add it again.")
        elif blocked:
            self._menu_message(
                "Could not add to Steam",
                "Steam's list of non-Steam games could not be updated.",
                "Close Steam completely and try again. Nothing was changed, and the "
                "previous list is untouched.")
        elif reached_any:
            self._menu_message(
                "Nothing to add",
                "No game was found to put in your Steam library.",
                "Install the game from the disc first, then try again.")
        else:
            self._menu_message(
                "Could not add to Steam",
                "Steam's list of non-Steam games could not be read.",
                "Close Steam completely and try again.")

    # Every popup the menu shows goes through these three. They were being
    # called from fourteen places and defined in none: PLAY with no exe, BONUS
    # or MODS not found, UNINSTALL, the preview notice and every ADD TO STEAM
    # outcome all ended in AttributeError, and PyQt5 turns an unhandled
    # exception in a slot into an abort - so the menu did not show a message,
    # it vanished. _menu_message was lost in an edit; _menu_confirm and
    # _dark_frame were called for from the start and never written.
    # Tooltips explain the buttons whose names cannot explain themselves.
    # Styled here because the stock Windows tooltip is a pale yellow slab, and
    # on a dark full-screen menu that reads as something gone wrong. Set on
    # the window, so every button below it inherits the look.
    TOOLTIP_STYLE = """
        QToolTip {
            background-color: #1a1a1a;
            color: #dddddd;
            border: 1px solid rgba(255, 255, 255, 60);
            padding: 6px 8px;
            font-size: 13px;
        }
    """

    MESSAGE_STYLE = """
        QMessageBox { background-color: #1a1a1a; }
        QMessageBox QLabel { color: #ffffff; background: transparent; font-size: 13px; }
        QMessageBox QPushButton {
            background-color: rgba(40, 40, 40, 200);
            color: #ffffff;
            border: 2px solid rgba(255, 255, 255, 40);
            padding: 8px 22px;
            font-size: 13px;
            font-weight: bold;
            letter-spacing: 1px;
            min-width: 84px;
        }
        QMessageBox QPushButton:hover {
            border-color: #ffffff;
            background-color: rgba(60, 60, 60, 220);
        }
    """

    def _dark_frame(self, window):
        """Ask Windows for a dark title bar on a dialog.

        These dialogs are near black and the caption above them is whatever the
        system theme says, which on most machines is a bright white bar sitting
        on top of a dark box. DwmSetWindowAttribute is the only thing that
        colours it, and the attribute number changed partway through Windows 10,
        so both are tried. Purely cosmetic - every step is allowed to fail, and
        the dialog simply keeps the ordinary caption.
        """
        try:
            import ctypes
            handle = int(window.winId())
            enabled = ctypes.c_int(1)
            for attribute in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except Exception:
            pass

    def _message_box(self, icon, title, body, detail):
        """A dark message box carrying the disc's own icon."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(body)
        if detail:
            box.setInformativeText(detail)
        icon_path = os.path.join(self.game_dir, "game_icon.ico")
        if os.path.exists(icon_path):
            box.setWindowIcon(QtGui.QIcon(icon_path))
        box.setStyleSheet(self.MESSAGE_STYLE)
        self._dark_frame(box)
        return box

    def _menu_message(self, title, body, detail=""):
        """Say what happened, and underneath it what to do about it."""
        self._message_box(QtWidgets.QMessageBox.Information, title, body, detail).exec_()

    def _menu_confirm(self, title, body, detail=""):
        """Ask a yes/no question in the player's own language. True means yes.

        No is the default and the escape key, because the only thing that asks
        is UNINSTALL.
        """
        trans = self.translations[self.current_lang]
        box = self._message_box(QtWidgets.QMessageBox.Question, title, body, detail)
        yes_button = box.addButton(trans["yes"], QtWidgets.QMessageBox.YesRole)
        no_button = box.addButton(trans["no"], QtWidgets.QMessageBox.NoRole)
        box.setDefaultButton(no_button)
        box.setEscapeButton(no_button)
        box.exec_()
        return box.clickedButton() is yes_button

    def show_preview_notice(self):
        self._menu_message(
            "Preview",
            "This button works for real on the finished disc.",
            "Nothing is installed or launched while you are previewing the menu.")

    def launch_configured_exe(self, rel_exe, args=None):
        # Launch a specific configured game executable (multi-game discs).
        # _configured_exe, not a bare join: see its docstring for why a path
        # out of menu_config.json cannot be handed straight to Popen.
        exe_path = self._configured_exe(rel_exe)
        if exe_path:
            subprocess.Popen([exe_path] + (args or []), cwd=os.path.dirname(exe_path))
            QtWidgets.QApplication.instance().quit()
        else:
            trans = self.translations[self.current_lang]
            self._menu_message(trans["error"], trans["game_not_found"],
                               "Looked for: %s" % rel_exe)

    def show_game_chooser(self, args=None):
        # Multi-game disc: let the player pick which game to play. `args` rides
        # along so a compatibility launch still asks which game first.
        args = args or []
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Choose Your Game")
        dialog.setMinimumWidth(int(420 * self.scale_factor))
        icon_path = os.path.join(self.game_dir, "game_icon.ico")
        if os.path.exists(icon_path):
            dialog.setWindowIcon(QtGui.QIcon(icon_path))
        self._dark_frame(dialog)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a1a1a; }
            QLabel { color: #ffffff; background: transparent; }
            QPushButton {
                background-color: rgba(40, 40, 40, 200);
                color: #ffffff;
                border: 2px solid rgba(255, 255, 255, 40);
                padding: 14px 20px;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 2px;
                text-align: left;
            }
            QPushButton:hover { border-color: #ffffff; background-color: rgba(60, 60, 60, 220); }
        """)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QtWidgets.QLabel("CHOOSE YOUR GAME")
        title.setStyleSheet("font-size: 13px; font-weight: bold; letter-spacing: 4px; color: #aaaaaa;")
        layout.addWidget(title)
        for game in self.games:
            label = game.get("name") or os.path.splitext(os.path.basename(game["exe"]))[0]
            btn = QtWidgets.QPushButton("  " + label.upper())
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            def make_handler(exe):
                def handler():
                    dialog.accept()
                    if self.preview_mode:
                        self.show_preview_notice()
                    else:
                        self.launch_configured_exe(exe, args)
                return handler
            btn.clicked.connect(make_handler(game["exe"]))
            layout.addWidget(btn)
        dialog.exec_()

    # Names that are never the game: installer plumbing, crash handlers,
    # redistributables and browser-engine subprocesses.
    HELPER_EXES = frozenset([
        'setup.exe', 'unins000.exe', 'unins001.exe', 'unins002.exe', 'menu.exe',
        'unitycrashhandler64.exe', 'unitycrashhandler32.exe',
        'createdump.exe', 'crashpad_handler.exe', 'crashreportclient.exe',
        'ueprereqsetup_x64.exe', 'ue4prereqsetup_x64.exe', 'ue5prereqsetup_x64.exe',
        'vcredist_x64.exe', 'vcredist_x86.exe', 'vc_redist.x64.exe',
        'vc_redist.x86.exe', 'dxwebsetup.exe', 'dotnet.exe', 'dxsetup.exe',
        'oalinst.exe', 'python.exe', 'pythonw.exe',
    ])

    def _is_helper_exe(self, filename):
        low = filename.lower()
        if not low.endswith('.exe'):
            return True
        if low in self.HELPER_EXES:
            return True
        if 'browsersubprocess' in low or low.startswith(('cefsharp', 'unitycrashhandler',
                                                         'vcredist', 'vc_redist', 'unins')):
            return True
        return False

    def _inside_game_dir(self, path):
        """True only if `path` really lives inside the install folder.

        realpath first, so a junction or a symlink planted in the install
        folder cannot point out of it and still pass.
        """
        try:
            base = os.path.realpath(self.game_dir)
            target = os.path.realpath(path)
            return os.path.commonpath([base, target]) == base
        except (ValueError, OSError):
            # ValueError is commonpath saying "different drives", which is
            # already an answer: not inside the install folder.
            return False

    def _is_reparse_point(self, path):
        """True if `path` is a junction, symlink, or other reparse point.

        os.walk follows directory junctions on Windows even with followlinks
        False, because they are not os.path.islink. A planted junction in the
        install folder would otherwise let the scan pick an exe outside it.
        """
        if os.path.islink(path):
            return True
        try:
            return bool(os.lstat(path).st_file_attributes & 0x400)
        except (AttributeError, OSError):
            return False

    def _configured_exe(self, rel_exe):
        """Resolve an exe path that came out of menu_config.json, or None.

        menu_config.json is plain JSON sitting next to menu.exe, and menu.exe
        is code-signed. Anything in that file is therefore something the
        player's disc or the player's disk handed us, not something we wrote,
        and joining it onto the install folder does not keep it there:

          - "C:/Windows/System32/calc.exe" - os.path.join throws the base away
            the moment the second half is absolute
          - "//host/share/evil.exe" - same, for UNC
          - "../../../Windows/System32/calc.exe" - normpath resolves the ..
            segments straight back out of the folder

        Each of those ends with a signed, trusted binary starting a program
        somebody else chose. So the resolved path has to be checked back
        against the install folder, and held to the same "not installer
        plumbing" bar the folder scan already applies - the blocklist used to
        cover the scan passes only, which left the configured path, the one
        that is actually attacker-reachable, as the way around it.

        Nothing here is a build-time restriction: Rialto writes these paths
        with detect_primary_game_exe / discover_game_exes, which are relative,
        inside the staged folder, and already skip helper names.
        """
        rel_exe = str(rel_exe or "").strip()
        if not rel_exe:
            return None
        candidate = os.path.normpath(os.path.join(self.game_dir, rel_exe))
        if not self._inside_game_dir(candidate):
            return None
        if self._is_helper_exe(os.path.basename(candidate)):
            return None
        if not os.path.isfile(candidate):
            return None
        return candidate

    def find_game_exe(self):
        """Work out which .exe PLAY should start, and say where it looked.

        Returns (path or None, list of folders searched).

        Four passes, cheapest first:
          1. game_exe from menu_config.json - written at build time by the
             machine that could actually see the whole game folder. This is the
             one that matters: guessing at runtime is what produced the
             "Game executable not found!" report that nobody could reproduce.
          2. game.exe at the install root, the conventional entry point.
          3. Any non-helper .exe at the install root.
          4. A bounded walk three folders deep, which is where engine launchers
             live - an Unreal game's real binary sits at
             <Project>/Binaries/Win64/<Project>-Win64-Shipping.exe. The biggest
             candidate wins, because engine binaries dwarf their helpers.

        The walk skips menu/, bonus/, mods/, runtime/ and redist folders: those
        hold executables that are emphatically not the game.
        """
        searched = []

        configured = self._configured_exe(self.menu_config.get("game_exe"))
        if configured:
            return configured, searched

        searched.append(self.game_dir)
        try:
            entries = sorted(os.listdir(self.game_dir))
        except OSError:
            entries = []

        for name in entries:
            if name.lower() == 'game.exe':
                path = os.path.join(self.game_dir, name)
                if os.path.isfile(path) and not self._is_reparse_point(path):
                    return path, searched

        # Several exes at the root is ordinary - a launcher, the game, an
        # editor. The title this disc was built for names the right one; size
        # decides if it does not. Taking whichever sorted first picked the
        # launcher out of a folder simply because L comes before M.
        rooted = []
        for name in entries:
            if self._is_helper_exe(name):
                continue
            path = os.path.join(self.game_dir, name)
            if os.path.isfile(path) and not self._is_reparse_point(path):
                rooted.append((name, path))
        if rooted:
            wanted = ''.join(c for c in MENU_TITLE.lower() if c.isalnum())
            if wanted:
                for name, path in rooted:
                    stem = os.path.splitext(name)[0].lower()
                    if ''.join(c for c in stem if c.isalnum()) == wanted:
                        return path, searched
            if len(rooted) == 1:
                return rooted[0][1], searched

            def rooted_size(item):
                try:
                    return os.path.getsize(item[1])
                except OSError:
                    return 0
            return max(rooted, key=rooted_size)[1], searched

        skip_dirs = {'menu', 'bonus', 'mods', 'runtime', 'redist', 'redistributables',
                     '_commonredist', 'directx', 'dotnet', '$recycle.bin',
                     'system volume information', 'mac', 'linux'}
        # The mod tool is not the game, and its folder is not always called
        # "mods". Kept in mod-maker/, say, its "Mod Maker.exe" can be the
        # biggest candidate the walk finds, and PLAY would
        # start the mod tool. Whatever folder the config points into is out.
        mod_rel = str(self.menu_config.get("mod_exe") or "").replace("\\\\", "/")
        if "/" in mod_rel:
            skip_dirs.add(mod_rel.split("/")[0].strip().lower())
        best = None
        best_size = -1
        for dirpath, dirnames, filenames in os.walk(self.game_dir):
            rel = os.path.relpath(dirpath, self.game_dir)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth >= 3:
                dirnames[:] = []
            kept = []
            try:
                scan = {entry.name: entry for entry in os.scandir(dirpath)}
            except OSError:
                scan = {}
            for d in dirnames:
                if d.lower() in skip_dirs:
                    continue
                entry = scan.get(d)
                if entry is not None:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        st = entry.stat(follow_symlinks=False)
                        if getattr(st, "st_file_attributes", 0) & 0x400:
                            continue
                    except OSError:
                        continue
                    if os.path.islink(entry.path):
                        continue
                elif self._is_reparse_point(os.path.join(dirpath, d)):
                    continue
                kept.append(d)
            dirnames[:] = kept
            if depth > 0:
                searched.append(dirpath)
            for name in filenames:
                if self._is_helper_exe(name):
                    continue
                path = os.path.join(dirpath, name)
                if self._is_reparse_point(path):
                    continue
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size > best_size:
                    best, best_size = path, size

        if best and not self._inside_game_dir(best):
            best = None
        return best, searched

    def _report_missing_game(self, searched):
        """Say what went wrong and where Rialto looked."""
        trans = self.translations[self.current_lang]
        shown = searched[:6]
        detail = "\\n".join("    " + folder for folder in shown)
        if len(searched) > len(shown):
            detail += "\\n    ... and %d more" % (len(searched) - len(shown))
        self._menu_message(
            trans["error"], trans["game_not_found"],
            "Looked in:\\n%s\\n\\nTry Play once more first: a freshly installed folder is "
            "sometimes still being scanned. If it keeps failing, the game folder "
            "may not have finished copying." % detail)

    def _lift_dark_logo(self, label, pixmap):
        """Put a soft light halo behind a logo that is too dark to read here.

        Most game logos are drawn for a store page, on white. A dark logo on a
        transparent background reads well on a pale page and
        vanishes on this panel, which is nearly black. Nothing is wrong with
        the file, so nothing about the file can fix it.

        Measured rather than assumed: the mean brightness of the pixels that
        are actually opaque decides it. A bright logo is left completely alone.

        Returns the padding the caller must reserve around the label, so the
        halo has somewhere to spread instead of being clipped off.
        """
        try:
            image = pixmap.toImage()
            width, height = image.width(), image.height()
            if width < 2 or height < 2:
                return 0
            step = max(1, min(width, height) // 48)
            total, counted = 0, 0
            for y in range(0, height, step):
                for x in range(0, width, step):
                    colour = image.pixelColor(x, y)
                    if colour.alpha() < 128:
                        continue
                    total += (0.2126 * colour.red() + 0.7152 * colour.green()
                              + 0.0722 * colour.blue())
                    counted += 1
            if not counted:
                return 0
            if (total / counted) >= 90:
                return 0

            radius = int(28 * self.scale_factor)
            glow = QtWidgets.QGraphicsDropShadowEffect(label)
            glow.setBlurRadius(radius)
            glow.setOffset(0, 0)
            glow.setColor(QtGui.QColor(255, 255, 255, 190))
            label.setGraphicsEffect(glow)
            return radius // 2
        except Exception:
            # Cosmetic only. A logo with no halo beats a menu that will not open.
            return 0

    def disc_installer(self):
        """setup.exe beside this menu when the game is not here to play, else "".

        An install-first disc keeps the whole game inside setup.exe, so the
        menu sitting on the disc has nothing to launch. It used to offer PLAY
        anyway, and the player got "Game executable not found" - on a disc that
        was working exactly as intended. Offer the installer instead.

        Never guessed at: the game has to be genuinely absent AND a real
        setup.exe has to be sitting at the disc root, inside the menu's own
        folder tree.
        """
        if self.preview_mode:
            return ""
        if self.games:
            # A multi-game disc still installs first if none of its games are
            # actually here - otherwise the chooser opens onto entries that
            # every one of them fails to launch.
            if any(self._configured_exe(g.get("exe")) for g in self.games):
                return ""
        else:
            if self._configured_exe(self.menu_config.get("game_exe")):
                return ""
            found, _searched = self.find_game_exe()
            if found:
                return ""
        setup = os.path.join(self.game_dir, "setup.exe")
        if os.path.isfile(setup) and self._inside_game_dir(setup):
            return setup
        return ""

    def run_disc_installer(self):
        setup = self.disc_installer()
        if not setup:
            # The disc changed under us between building the button and
            # pressing it. Fall back to the normal not-found reporting.
            self.launch_game()
            return
        subprocess.Popen([setup], cwd=os.path.dirname(setup))
        QtWidgets.QApplication.instance().quit()

    def compatibility_args(self):
        """The compatibility-mode arguments, re-read and re-checked each time.

        Deliberately not cached at startup: the config is validated at the
        moment it is used, not once at load, so a file swapped underneath a
        running menu gets the same scrutiny as one read at boot.
        """
        if not self.menu_config.get("compat_mode"):
            return []
        return clean_launch_args(self.menu_config.get("compat_args"))

    def compatibility_label(self):
        """What the compatibility button says. Always the same words.

        Deliberately not author-settable. This is a property of the launcher,
        not of the game: a name like "Legacy Graphics" reads as something the
        game offers rather than a way to start it, and a player who learns
        what this button means on one disc should recognise it on the next.
        Whatever is particular to this game goes in the tooltip instead.

        Not upper-cased, unlike every other button: this one is a quieter
        line under PLAY rather than a heading competing with it.
        """
        return self.translations[self.current_lang]["compat"]

    def compatibility_hint(self):
        """The tooltip explaining what this mode actually does.

        "Compatibility Mode" means nothing on its own, and the generic
        wording can only describe the usual case. The author knows what
        their mode really changes, so their sentence wins when they wrote
        one - same trust boundary as every other config value.
        """
        raw = str(self.menu_config.get("compat_hint") or "")
        raw = ''.join(c if (c >= ' ' and c != '\\x7f') else ' ' for c in raw).strip()
        if raw:
            return raw[:200]
        return self.translations[self.current_lang]["tip_compat"]

    def launch_compatibility_mode(self):
        self.launch_game(args=self.compatibility_args())

    def launch_game(self, args=None):
        args = args or []
        if self.preview_mode:
            if self.games and len(self.games) > 1:
                self.show_game_chooser(args)
            else:
                self.show_preview_notice()
            return

        # Multi-game discs: use the configured game list
        if self.games:
            if len(self.games) == 1:
                self.launch_configured_exe(self.games[0]["exe"], args)
            else:
                self.show_game_chooser(args)
            return

        game_exe, searched = self.find_game_exe()

        if game_exe and os.path.isfile(game_exe):
            subprocess.Popen([game_exe] + args, cwd=os.path.dirname(game_exe))
            QtWidgets.QApplication.instance().quit()
            return

        # One retry after a beat. A first launch straight after installing can
        # fail once and never again, which is
        # what a filter driver still working through a freshly written folder
        # looks like from up here.
        if not getattr(self, "_play_retried", False):
            self._play_retried = True
            QtCore.QTimer.singleShot(1200, lambda: self.launch_game(args))
            return

        self._report_missing_game(searched)
    
    def open_bonus(self):
        bonus_dir = os.path.join(self.game_dir, "bonus")
        if os.path.exists(bonus_dir):
            os.startfile(bonus_dir)
        else:
            trans = self.translations[self.current_lang]
            self._menu_message(trans["warning"], trans["bonus_not_found"],
                               "This disc was built without a bonus folder.")

    def _resolve_mods_dir(self):
        # The mods folder sits at the install root, shared by every game on the disc
        for name in ("mods", "MODS", "Mods"):
            candidate = os.path.join(self.game_dir, name)
            if os.path.isdir(candidate):
                return candidate
        return None

    def _resolve_mod_exe(self):
        # Prefer the exe Rialto detected at build time, then scan the folder
        configured = self._configured_exe(self.menu_config.get("mod_exe"))
        if configured:
            return configured

        mods_dir = self._resolve_mods_dir()
        if not mods_dir:
            return None

        try:
            entries = sorted(os.listdir(mods_dir))
        except OSError:
            return None

        for name in entries:
            candidate = os.path.join(mods_dir, name)
            if name.lower().endswith(".exe") and os.path.isfile(candidate):
                return candidate

        for name in entries:
            sub = os.path.join(mods_dir, name)
            if not os.path.isdir(sub):
                continue
            try:
                for child in sorted(os.listdir(sub)):
                    candidate = os.path.join(sub, child)
                    if child.lower().endswith(".exe") and os.path.isfile(candidate):
                        return candidate
            except OSError:
                continue
        return None

    def launch_mods(self):
        if self.preview_mode:
            self.show_preview_notice()
            return

        mod_exe = self._resolve_mod_exe()
        if mod_exe:
            subprocess.Popen([mod_exe], cwd=os.path.dirname(mod_exe))
            QtWidgets.QApplication.instance().quit()
        else:
            trans = self.translations[self.current_lang]
            self._menu_message(trans["warning"], trans["mods_not_found"],
                               "No mod tool was found in the mods folder on this disc.")

    def uninstall_game(self):
        if self.preview_mode:
            self.show_preview_notice()
            return
        uninstaller = os.path.join(self.game_dir, "unins000.exe")
        if os.path.exists(uninstaller):
            trans = self.translations[self.current_lang]
            if self._menu_confirm(trans["warning"], trans["confirm_uninstall"],
                                  "The game files are removed. Your saves are not touched."):
                subprocess.Popen([uninstaller])
                QtWidgets.QApplication.instance().quit()
        else:
            trans = self.translations[self.current_lang]
            self._menu_message(
                trans["warning"], trans["uninstaller_not_found"],
                "Uninstall the game from Windows Settings, Apps instead.")
    
    def init_controller_support(self):
        """Initialize gamepad/controller support"""
        # Initialize gamepad support
        self.current_button_index = 0
        self.controller_states = {}
        self.gamepad_timer = QtCore.QTimer()
        self.gamepad_timer.timeout.connect(self.check_gamepad_input)
        
        # Try to initialize pygame for gamepad support
        try:
            import pygame
            pygame.init()
            pygame.joystick.init()
            
            controller_count = pygame.joystick.get_count()
            
            self.pygame_available = True
            self.joysticks = []
            
            # Initialize all connected joysticks/controllers
            for i in range(controller_count):
                try:
                    joystick = pygame.joystick.Joystick(i)
                    joystick.init()
                    self.joysticks.append(joystick)
                    self.controller_states[i] = {
                        'last_hat': (0, 0),
                        'last_axis': 0,
                        'last_buttons': [False] * joystick.get_numbuttons(),
                        'nav_cooldown': 0
                    }
                except Exception:
                    pass
            
            if self.joysticks:
                self.gamepad_timer.start(16)  # ~60fps polling

        except ImportError:
            self.pygame_available = False
        except Exception:
            self.pygame_available = False
    
    def check_gamepad_input(self):
        """Check for gamepad/controller input"""
        if not self.pygame_available or not self.joysticks:
            return
            
        try:
            import pygame
            pygame.event.pump()
            
            # Get list of buttons for navigation
            buttons = [self.play_btn]
            if hasattr(self, 'bonus_btn'):
                buttons.append(self.bonus_btn)
            if hasattr(self, 'mods_btn'):
                buttons.append(self.mods_btn)
            if getattr(self, 'steam_btn', None) is not None:
                buttons.append(self.steam_btn)
            buttons.extend([self.uninstall_btn, self.exit_btn])
            
            for i, joystick in enumerate(self.joysticks):
                if i not in self.controller_states:
                    continue
                    
                state = self.controller_states[i]
                
                # Reduce cooldown
                if state['nav_cooldown'] > 0:
                    state['nav_cooldown'] -= 1
                    continue
                
                # D-pad navigation (hat 0)
                if joystick.get_numhats() > 0:
                    hat = joystick.get_hat(0)
                    if hat != state['last_hat']:
                        if hat[1] == 1:  # D-pad up
                            self.navigate_up(buttons)
                            state['nav_cooldown'] = 10  # Cooldown frames
                        elif hat[1] == -1:  # D-pad down
                            self.navigate_down(buttons)
                            state['nav_cooldown'] = 10
                        state['last_hat'] = hat
                
                # Left analog stick (Y-axis for up/down)
                if joystick.get_numaxes() >= 2:
                    y_axis = joystick.get_axis(1)
                    current_direction = 0
                    
                    if y_axis < -0.5:  # Up
                        current_direction = -1
                    elif y_axis > 0.5:  # Down
                        current_direction = 1
                    
                    if current_direction != state['last_axis'] and current_direction != 0:
                        if current_direction == -1:
                            self.navigate_up(buttons)
                        elif current_direction == 1:
                            self.navigate_down(buttons)
                        state['nav_cooldown'] = 15  # Longer cooldown for analog
                    
                    state['last_axis'] = current_direction
                
                # Button presses
                for btn_idx in range(min(joystick.get_numbuttons(), len(state['last_buttons']))):
                    current_pressed = joystick.get_button(btn_idx)
                    was_pressed = state['last_buttons'][btn_idx]
                    
                    # Button just pressed (rising edge)
                    if current_pressed and not was_pressed:
                        if btn_idx == 0:  # A/X button - activate
                            if 0 <= self.current_button_index < len(buttons):
                                buttons[self.current_button_index].click()
                        elif btn_idx == 1:  # B/Circle button - exit
                            self.close()
                    
                    state['last_buttons'][btn_idx] = current_pressed
                        
        except Exception:
            pass

    def navigate_up(self, buttons):
        """Navigate up in menu"""
        if self.current_button_index > 0:
            self.current_button_index -= 1
        else:
            self.current_button_index = len(buttons) - 1  # Wrap to last
        buttons[self.current_button_index].setFocus()
    
    def navigate_down(self, buttons):
        """Navigate down in menu"""
        if self.current_button_index < len(buttons) - 1:
            self.current_button_index += 1
        else:
            self.current_button_index = 0  # Wrap to first
        buttons[self.current_button_index].setFocus()

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        # Get list of buttons for navigation
        buttons = [self.play_btn]
        if hasattr(self, 'bonus_btn'):
            buttons.append(self.bonus_btn)
        if hasattr(self, 'mods_btn'):
            buttons.append(self.mods_btn)
        if getattr(self, 'steam_btn', None) is not None:
            buttons.append(self.steam_btn)
        buttons.extend([self.uninstall_btn, self.exit_btn])

        # Find currently focused button and update index
        current_index = -1
        for i, btn in enumerate(buttons):
            if btn.hasFocus():
                current_index = i
                self.current_button_index = i
                break
        
        # Handle navigation
        if event.key() == QtCore.Qt.Key_Up:
            self.navigate_up(buttons)
        elif event.key() == QtCore.Qt.Key_Down:
            self.navigate_down(buttons)
        elif event.key() in [QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space]:
            if current_index >= 0:
                buttons[current_index].click()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging"""
        if event.button() == QtCore.Qt.LeftButton:
            self.offset = event.pos()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging"""
        if self.offset is not None and event.buttons() == QtCore.Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release for window dragging"""
        self.offset = None

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = GameMenu()
    window.show()
    sys.exit(app.exec_())
'''


def write_menu_source(menu_dir, filename="menu_launcher.pyw"):
    """Write the disc menu source out as a file.

    Two callers: `build_menu_exe.py`, which freezes it once into the generic
    menu.exe that ships with Rialto, and the legacy per-title compile path that
    a source checkout falls back to when no pre-built menu.exe is around.
    Returns the path written, or None.
    """
    path = os.path.join(menu_dir, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(MENU_TEMPLATE_SOURCE)
        return path
    except OSError:
        return None


# Formats the disc menu deliberately will NOT show. QMediaPlayer hands a
# video to Windows Media Foundation, so it plays only where the player's
# own machine has the codec - and answers InvalidMedia after play() has
# already returned, painting an opaque black rectangle over the menu. On a
# disc that can never be patched that is not a risk worth taking, so these
# are refused at staging and an animated GIF is offered instead. GIFs are
# decoded by Qt itself and look the same on every machine.
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.webm', '.mkv', '.m4v', '.wmv')


def image_has_transparency(path):
    """True / False / None for "does this image have real transparency?".

    A logo with no alpha arrives on screen as a rectangle of whatever the
    artist's canvas colour was. That is easy to miss on a store page,
    so it is worth saying out loud at build time rather than discovering on
    the finished copy.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            if im.mode in ('RGBA', 'LA'):
                alpha = im.getchannel('A')
                low, _high = alpha.getextrema()
                return low < 255
            if im.mode == 'P':
                return 'transparency' in im.info
            return False
    except Exception:
        return None


def prebuilt_menu_exe():
    """Locate the pre-built, title-agnostic menu.exe, or None.

    Checked in order: beside Rialto (where a release ships it), a prebuilt/
    subfolder, inside a frozen Rialto's own bundle if it was built with the
    menu embedded, and finally dist/ so a source checkout finds the exe it just
    built without anyone having to move it.
    """
    candidates = [
        os.path.join(APP_ROOT, "menu.exe"),
        os.path.join(APP_ROOT, "prebuilt", "menu.exe"),
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "prebuilt", "menu.exe"))
    candidates.append(os.path.join(APP_ROOT, "dist", "menu.exe"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None



if __name__ == '__main__':
    ensure_structure()
    root = tk.Tk()
    app = RialtoApp(root)
    root.mainloop()