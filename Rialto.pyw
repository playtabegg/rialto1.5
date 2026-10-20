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
import tkinter.font as tkfont
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
            messagebox.showinfo("Rialto", "Setup canceled. Run 'pip install -r requirements.txt' manually, then start Rialto again.")
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
__version__ = "1.5.1"

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
    """ISCC.exe from Inno Setup 6, else from Inno Setup 7, or None.

    PATH first, as before, unless that ISCC.exe sits in the folder of an Inno
    Setup version Rialto has not been tested with; then wherever the Inno
    Setup 6 installer put itself, in either install mode, then Inno Setup 7's.
    7 since 1.5.1 (B4): Rialto's own scripts (one disc and a spanned set, all
    21 languages) compiled with 7.1.0 raise the same three warnings as with 6,
    and installed and uninstalled the same, byte for byte. 6 still comes first.
    """
    found = shutil.which("ISCC.exe")
    if found and _inno_setup_major(found) in (None, 6):
        return found
    for major in (6, 7):
        for folder in _inno_setup_folders(major):
            candidate = os.path.join(folder, "ISCC.exe")
            if os.path.isfile(candidate):
                return candidate
    if found and _inno_setup_major(found) == 7:
        return found
    return None


def inno_setup_7_only():
    """True when Inno Setup 7 is installed and Inno Setup 6 is not.

    Since 1.5.1 Rialto builds with 7 in that case (find_inno_compiler); the
    build says so, so an author knows which compiler made their installer.
    """
    found = find_inno_compiler()
    if found and _inno_setup_major(found) in (None, 6):
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


# The tools Rialto carries (1.5.1): Inno Setup 6.5.4 and cdrtools 3.02a10's mkisofs, inside Rialto.exe, so
# nobody has to install anything. A tool already on the PC always comes first and builds exactly as 1.5.0 did;
# a carried one only fills the gap. tools-dev/fetch_helpers.py puts them in helpers/ and pins each file.
CARRIED_INNO_VERSION = "6.5.4"


# What each carried tool needs beside it to run at all (security and bugs reviews, 1.5.1). ISCC will not
# start without its DLLs and their .issig files, and fails on a script whose language file is missing;
# mkisofs prints nothing without cygwin1.dll. A helpers folder is used only when it holds the whole set.
CARRIED_SETS = {
    "inno": ("ISCC.exe", "ISCmplr.dll", "ISPP.dll", "ISPPBuiltins.iss", "Setup.e32", "SetupLdr.e32", "islzma.dll",
             "Default.isl", "ISCmplr.dll.issig", "ISPP.dll.issig", "Setup.e32.issig", "SetupLdr.e32.issig",
             "islzma.dll.issig") + tuple("Languages/%s.isl" % language for language in (
                 "BrazilianPortuguese", "Catalan", "Czech", "Danish", "Dutch", "Finnish", "French", "German",
                 "Hebrew", "Italian", "Japanese", "Norwegian", "Polish", "Portuguese", "Russian", "Slovak",
                 "Slovenian", "Spanish", "Turkish", "Ukrainian")),
    "cdrtools": ("mkisofs.exe", "cygwin1.dll"),
}


def helper_path(*parts):
    """A file Rialto carries, or None. The first part names the tool's folder: "inno" or "cdrtools".

    A frozen Rialto runs only the copies inside its own EXE (sys._MEIPASS, which lasts while Rialto runs),
    never a helpers folder put beside Rialto.exe: nothing checks such a folder, and a zip unpacked into
    Rialto's folder could bring one. A source run uses the checkout's helpers\\, which
    tools-dev/fetch_helpers.py fills and checks. Either way a folder counts only when it holds the tool's
    whole set (CARRIED_SETS), so a part of one never stands in for the real thing. A source checkout that
    never ran fetch_helpers.py has none, and runs on installed tools as before.
    """
    pieces = [p for part in parts for p in re.split(r"[\\/]+", part) if p]
    if not pieces:
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    bases = [meipass] if (getattr(sys, "frozen", False) or meipass) else [APP_ROOT]
    for base in bases:
        if not base:
            continue
        folder = os.path.join(base, "helpers", pieces[0])
        whole = all(os.path.isfile(os.path.join(folder, *name.split("/")))
                    for name in CARRIED_SETS.get(pieces[0], ()))
        candidate = os.path.join(folder, *pieces[1:])
        if whole and len(pieces) > 1 and os.path.isfile(candidate):
            return candidate
    return None


def carried_inno_compiler():
    """The ISCC.exe Rialto carries, with everything it needs beside it, or None."""
    return helper_path("inno", "ISCC.exe")


def carried_mkisofs():
    """The mkisofs.exe Rialto carries, or None. It needs cygwin1.dll beside it: without it, it prints nothing."""
    found = helper_path("cdrtools", "mkisofs.exe")
    if found and os.path.isfile(os.path.join(os.path.dirname(found), "cygwin1.dll")):
        return found
    return None


def installer_compiler():
    """(ISCC.exe, carried): Inno Setup on this PC first (find_inno_compiler), then the one Rialto carries."""
    found = find_inno_compiler()
    if found:
        return found, False
    carried = carried_inno_compiler()
    return (carried, True) if carried else (None, False)


def disc_image_tools(pressed):
    """Every tool that can write the disc image, in the order Rialto tries them: [(kind, path, carried)].

    mkisofs on PATH, then oscdimg (PATH or the Windows ADK), then the mkisofs Rialto carries. A pressed
    disc takes mkisofs only: oscdimg is licensed for Microsoft-authorized content, as it prints itself.
    Empty when there is none, and then only an unpressed build falls back to a ZIP.
    """
    mkisofs, oscdimg = find_iso_tools()
    tools = []
    if mkisofs:
        tools.append(("mkisofs", mkisofs, False))
    if oscdimg and not pressed:
        tools.append(("oscdimg", oscdimg, False))
    carried = carried_mkisofs()
    if carried and not (mkisofs and os.path.normcase(os.path.abspath(mkisofs)) ==
                        os.path.normcase(os.path.abspath(carried))):
        tools.append(("mkisofs", carried, True))
    return tools


def tool_words(kind, path, carried):
    """How the log names a tool: "the mkisofs that comes with Rialto", "your oscdimg (C:\\...)"."""
    if carried:
        if kind == "iscc":
            return "the Inno Setup %s that comes with Rialto" % CARRIED_INNO_VERSION
        return "the %s that comes with Rialto" % kind
    if kind == "iscc":
        return "your Inno Setup (%s)" % path
    return "your %s (%s)" % (kind, path)


def missing_tool_refusals(pressed, image_needed=True):
    """What the preflight says when a tool cannot be found, installed or carried: a sentence each, or []."""
    refusals = []
    if not installer_compiler()[0]:
        refusals.append("No installer compiler: Inno Setup is not on this PC and this copy of Rialto does not "
                        "carry one. Download the full Rialto.exe again, or install Inno Setup 6 from "
                        + INNO_SETUP_DOWNLOAD + ".")
    if image_needed and not disc_image_tools(pressed):
        if pressed:
            refusals.append("Pressed disc: a plant's master is made with mkisofs (from cdrtools), and there is "
                            "none on this PC or in this copy of Rialto. Download the full Rialto.exe again, "
                            "put mkisofs on your PATH, or untick Pressed.")
        else:
            refusals.append("No disc image tool: there is no mkisofs or oscdimg on this PC and this copy of "
                            "Rialto does not carry one. Download the full Rialto.exe again, or install the "
                            "Windows ADK with Deployment Tools ticked.")
    return refusals


def mkisofs_reads_utf8(mkisofs):
    """True for a Cygwin or MSYS build (cygwin1.dll or msys-2.0.dll beside it): it reads file names as UTF-8."""
    folder = os.path.dirname(os.path.abspath(mkisofs))
    return any(os.path.isfile(os.path.join(folder, dll)) for dll in ("cygwin1.dll", "msys-2.0.dll"))


def mkisofs_graft(item, is_folder):
    """One item of the disc root as a graft point: "menu/=menu" for a folder, "setup.exe=setup.exe" for a file.

    Without graft points mkisofs puts a folder's contents at the disc root. "\\" and "=" are escaped as the
    graft syntax asks, and a name that starts with "-" is written "/-name=./-name" so it is not an option.
    """
    escaped = item.replace("\\", "\\\\").replace("=", "\\=")
    on_disc, local = escaped, escaped
    if item.startswith("-"):
        on_disc, local = "/" + escaped, "./" + escaped
    return "%s%s=%s" % (on_disc, "/" if is_folder else "", local)


# A Cygwin or MSYS mkisofs reads its own command line again once it starts: it drops single quotes,
# expands {a,b}, * and [x], and reads a word that starts with @ as a file of words (security review,
# 1.5.1). So no name from a game folder goes on that line. The graft points go in a file in the build
# folder (-path-list), the image is written to a plain name there and renamed once it is finished, and the
# label is made safe by mkisofs_label.
MKISOFS_IMAGE_PART = "rialto-image.part"
MKISOFS_PATH_LIST = "rialto-graft-points.txt"


def mkisofs_label(disc_label):
    """The disc label as mkisofs gets it: no quote, brace, star, ? or square bracket for Cygwin to act on.

    A tilde too: Cygwin reads a label of "~" as the builder's home folder and would write their Windows
    user name onto every copy of the disc.
    """
    cleaned = "".join("" if c in "'\"" else "_" if c in "{}*?[]\\~" else c for c in str(disc_label))
    return cleaned.lstrip("-@ ").rstrip() or "GAME"


def mkisofs_path_list(items, folders):
    """The file -path-list reads: each item of the disc root as a graft point, one a line."""
    return "".join(mkisofs_graft(item, item in folders) + "\n" for item in items)


def mkisofs_command(mkisofs, disc_label, needs_udf, utf8_names=True):
    """The one mkisofs command line, for one disc and for each disc of a set (1.5.1).

    ISO 9660 with Joliet (names up to 103 characters, -joliet-long, as oscdimg keeps them) and Rock Ridge
    (-r: readable by everyone on a Mac or Linux PC, not only by the Windows account that built it), each
    item grafted where it belongs, and UDF for a file over 4 GiB. A Cygwin build reads names as UTF-8, so it
    is told so, or "Café" and Japanese names come out garbled. Run with the build folder as the working
    folder: the graft points are read from MKISOFS_PATH_LIST there (mkisofs_path_list writes it) and the
    image goes to MKISOFS_IMAGE_PART there, so the command line holds no name from the game folder.
    """
    command = [mkisofs, "-o", MKISOFS_IMAGE_PART]
    if utf8_names:
        command += ["-input-charset", "UTF-8"]
    command += ["-J", "-r", "-joliet-long", "-graft-points", "-V", mkisofs_label(disc_label)]
    if needs_udf:
        command += ["-udf", "-iso-level", "3"]
    return command + ["-path-list", MKISOFS_PATH_LIST]


def same_file_bytes(first, second):
    """True when two files hold the same bytes."""
    try:
        if os.path.getsize(first) != os.path.getsize(second):
            return False
        with open(first, "rb") as a, open(second, "rb") as b:
            while True:
                block = a.read(1 << 20)
                if block != b.read(1 << 20):
                    return False
                if not block:
                    return True
    except OSError:
        return False


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
    # Proved at every start: a read-only folder that already holds config.json (a 1.5.0 folder copied
    # into Program Files) raised nothing here, and settings and builds then failed later, silently.
    with tempfile.TemporaryFile(dir=APP_ROOT):
        pass
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)


_QUIET_ALT_HOOKS = []  # every window procedure quiet_alt_tap made, kept for the life of the program


def quiet_alt_tap(window, when=None):
    """A bare Alt (or F10) on this window never puts it into Windows' menu mode (1.5.1, launch day).

    Alt pressed and let go on its own sends the window SC_KEYMENU, and Windows then runs a modal menu
    loop that waits for the next key or click. A build keeps the window answering from inside its own
    loop (keep_window_alive), so it waited too: one stray Alt tap on the Build Queue stopped a build
    until the next click. Here a bare Alt or F10 does nothing while `when()` is true (always, if no
    `when` is given). Alt+Space still opens the window menu and Alt+letter still reaches a menu.

    Hooked when the window is mapped, on the frame Windows draws around it (Tk can make a new frame,
    so each one is hooked once). The hooks are never released: a window being destroyed still calls
    its procedure, and freed code there would crash Rialto.
    """
    if sys.platform != "win32":
        return

    def hook(_event=None):
        try:
            import ctypes
            from ctypes import wintypes
            frame = int(window.wm_frame(), 16)
            if any(h[0] == frame and h[1] is window for h in _QUIET_ALT_HOOKS):
                return
            user32 = ctypes.windll.user32
            lresult = ctypes.c_ssize_t
            procedure = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.CallWindowProcW.restype = lresult
            user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                               wintypes.WPARAM, wintypes.LPARAM]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            previous = [None]

            def answer(hwnd, message, wparam, lparam):
                # WM_SYSCOMMAND (0x0112) with SC_KEYMENU (0xF100) and no key: Alt or F10 alone.
                if message == 0x0112 and (wparam & 0xFFF0) == 0xF100 and lparam == 0:
                    try:
                        if when is None or when():
                            return 0
                    except Exception:
                        pass
                return user32.CallWindowProcW(previous[0], hwnd, message, wparam, lparam)

            callback = procedure(answer)
            previous[0] = user32.SetWindowLongPtrW(frame, -4, ctypes.cast(callback, ctypes.c_void_p))  # GWLP_WNDPROC
            if previous[0]:
                _QUIET_ALT_HOOKS.append((frame, window, callback, previous))
        except Exception:
            pass  # a window that keeps Windows' own Alt behavior is no worse than before

    try:
        window.bind("<Map>", hook, add="+")
        if window.winfo_ismapped():
            hook()
    except Exception:
        pass


class ToolTip:
    # RialtoApp.tooltip_place once Rialto has started: where a tooltip goes by the one rule every window Rialto
    # opens goes through (1.5.1, B13.4). None before that, and then a tooltip opens where it always did.
    place = None

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
        # Below and right of the pointer. `above` is the line its bottom edge goes on when there is no room below.
        if event:
            x = event.x_root + 15
            y = event.y_root + 10
            above = event.y_root - 10
        else:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
            above = self.widget.winfo_rooty()
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tip_bg = self.bg or "#2d2d2d"
        tip_fg = self.fg or "#e0e0e0"
        label = tk.Label(tw, text=self.text, justify='left',
                         background=tip_bg, foreground=tip_fg,
                         relief='solid', borderwidth=1,
                         font=("Segoe UI", 10),
                         wraplength=320)
        label.pack(ipadx=4, ipady=2)
        # A tooltip is a window too (1.5.1, B13.4): from the export bar's last row it opened under the taskbar,
        # now that the main window ends at the work area's edge. Its size is the label's and the padding the
        # label is packed with, which Tk knows before the window is laid out, so it is placed before it shows.
        if ToolTip.place is not None:
            try:
                x, y = ToolTip.place(self.widget, label.winfo_reqwidth() + 8, label.winfo_reqheight() + 4,
                                     x, y, above)
            except Exception:
                pass  # where it always opened is better than no tooltip
        tw.wm_geometry(f"+{x}+{y}")

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
    elif name == "queue":
        # Build Queue: three rows, each a disc and a bar, one after another
        for y in (0.20, 0.50, 0.80):
            circle(0.18, y, 0.11)
            box(0.38, y - 0.075, 0.92, y + 0.075, radius=0.03)
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


# Windows 7 and 8 (1.5.1, B8). The disc menu is frozen with Python 3.12, which
# needs Windows 8.1 (version 6.3): on anything older menu.exe stops at launch,
# missing api-ms-win-core-path-l1-1-0.dll. Setup itself still allows Windows 7
# (MinVersion=6.1), so the installer's shortcuts split by version: 8.1 and later
# open the menu as before, Windows 7 and 8 start the game itself. A player there
# loses the menu, not the game.
MENU_MIN_WINDOWS = "6.3"


def iss_relative_exe(rel):
    """A game exe from menu_config.json as a path under {app}, or "".

    Refused rather than stripped: a path with a character taken out points the
    shortcut at a file that is not there. Only a plain relative path to an .exe
    passes, with no drive, no leading separator and no dot-only component, and
    none of the characters Inno would read as syntax.
    """
    rel = str(rel or "").replace("/", "\\").strip()
    if (not rel or not rel.lower().endswith(".exe") or _ISS_META.search(rel)
            or ":" in rel or rel.startswith("\\")):
        return ""
    if any(part.strip(". ") == "" for part in rel.split("\\")):
        return ""
    return rel


def iss_parameters(args):
    """Launch arguments as an Inno Parameters value, or "" if any cannot be written.

    An argument holding a space is quoted for the game, and Inno wants a quote
    inside a quoted value written twice. The whole set is refused if one
    argument carries a character Inno would read as syntax, the same rule the
    menu applies to the set (dropping one of "-mode opengl" changes the mode).
    """
    out = []
    for arg in args if isinstance(args, list) else []:
        if not isinstance(arg, str) or not arg or _ISS_META.search(arg):
            return ""
        out.append('""%s""' % arg if any(c.isspace() for c in arg) else arg)
    return " ".join(out)


def windows7_shortcut_lines(path_name, config, has_icon):
    """[Icons] and [Run] lines that start the game itself on Windows 7 and 8.

    `config` is the menu_config.json this build staged, so the shortcut starts
    the exe the menu would have started: the configured list on a disc of
    several games (one shortcut each), else game_exe. Each game starts in its
    own folder, as the menu starts it, and compatibility mode gets one more
    Start Menu shortcut carrying its arguments.

    Returns (icons, runs). Both empty means no game could be named safely, and
    the caller keeps the menu shortcuts on every Windows, as 1.5.0 did.
    """
    config = config if isinstance(config, dict) else {}
    only = "; OnlyBelowVersion: %s" % MENU_MIN_WINDOWS
    icon = '; IconFilename: "{app}\\game_icon.ico"' if has_icon else ""
    games = [g for g in config.get("games") or [] if isinstance(g, dict)]
    if len(games) > 1:
        chosen = [(g.get("name"), iss_relative_exe(g.get("exe"))) for g in games]
    else:
        chosen = [(path_name, iss_relative_exe(games[0].get("exe") if games else config.get("game_exe")))]
    chosen = [(name, exe) for name, exe in chosen if exe]
    params = iss_parameters(config.get("compat_args")) if config.get("compat_mode") else ""
    # A Start Menu shortcut for each game on every Windows (1.5.1, B9), when the
    # author asked for it on a disc of several. Beside the menu's shortcut on
    # 8.1 and later, so no game takes the disc's own name there.
    everywhere = bool(config.get("start_menu_per_game")) and len(chosen) > 1

    icons, runs = [], []
    taken = {str(path_name).lower()} if everywhere else set()
    for name, exe in chosen:
        label = iss_value(name, os.path.splitext(os.path.basename(exe))[0], for_path=True)
        base, n = label, 2
        while label.lower() in taken:
            label, n = "%s (%d)" % (base, n), n + 1
        taken.add(label.lower())
        folder = exe.rsplit("\\", 1)[0] if "\\" in exe else ""
        target = 'Filename: "{app}\\%s"; WorkingDir: "{app}%s"' % (exe, "\\" + folder if folder else "")
        icons.append('Name: "{group}\\%s"; %s%s%s' % (label, target, icon, "" if everywhere else only))
        icons.append('Name: "{userdesktop}\\%s"; %s%s; Tasks: desktopicon%s' % (label, target, icon, only))
        if params:
            icons.append('Name: "{group}\\%s (Compatibility Mode)"; %s; Parameters: "%s"%s%s'
                         % (label, target, params, icon, only))
        # One game: the finish page's Launch box starts it. Several: no Launch
        # box on these Windows, rather than one tick box per game.
        if len(chosen) == 1:
            runs.append('%s; Description: "{cm:LaunchProgram}"; Flags: nowait postinstall skipifsilent%s'
                        % (target, only))
    return icons, runs


# Files the installer places for the player (1.5.1, B10): a mod's first-run
# config, a pre-seeded save. Copying files only: running an author's script at
# install time is a different question of trust, and nothing asked for it.
# The places are the ones Inno resolves on any PC, for the user who installs
# (Setup runs per-user unless the player chooses otherwise).
PLACED_FILE_PLACES = (
    ("Documents", "{userdocs}"),
    ("Saved Games", "{usersavedgames}"),
    ("AppData Roaming", "{userappdata}"),
    ("AppData Local", "{localappdata}"),
    ("AppData LocalLow", "{%USERPROFILE}\\AppData\\LocalLow"),
    ("The install folder", "{app}"),
)
# Where a build stages them: beside the build folder, not in it. Everything in
# the build folder is installed into {app}, and Inno's createallsubdirs makes
# even an excluded folder there, empty, on the player's PC.
PLACED_FILES_DIR = ".rialto-placed"


# What a placed file may be, and where it may go (1.5.1 security review). A
# profile is shared between authors and its rows land under a signed
# installer, so: a source only from inside the game folder (never a share, so a
# profile cannot bring its own content), and outside the install folder data
# only, never in a folder Windows or Office starts things from.
PLACED_REFUSED_EXTENSIONS = frozenset(
    ".exe .dll .sys .drv .ocx .com .scr .pif .cpl .msi .msp .msc .bat .cmd .ps1 .psm1 .psd1 "
    ".vbs .vbe .js .jse .wsf .wsh .hta .lnk .url .reg .inf .jar .py .pyw .chm .gadget "
    ".application .appref-ms .library-ms .settingcontent-ms .xll .xla .xlam .dotm .wll "
    ".scf .search-ms .website .diagcab .docm .xlsm .pptm .appx .appxbundle .msix .msixbundle "
    ".vhd .vhdx .iso .img".split())
PLACED_REFUSED_FOLDERS = frozenset(
    ["startup", "start menu", "programs", "windowsapps", "windowspowershell", "powershell",
     "xlstart", "templates", "sendto", "recent", "protocol handler"])


def placed_row_problem(row, game_folder):
    """Why a Files to Place row cannot be built, as a phrase, or "" when it can."""
    source = str((row or {}).get("source") or "")
    if source.startswith(("\\\\", "//")):
        return "it is on a network share"
    if not os.path.isabs(source):
        return "it is not a full path"
    if not game_folder:
        return "there is no game folder"
    real, base = os.path.realpath(source), os.path.realpath(game_folder)
    try:
        inside = os.path.commonpath([real, base]) == base and real != base
    except ValueError:
        inside = False
    if not inside:
        return "it is outside your game folder"
    place = (row or {}).get("place")
    if place not in dict(PLACED_FILE_PLACES):
        return "its place is not one Rialto knows"
    if place != "The install folder":
        parts = [p.lower() for p in placed_subfolder((row or {}).get("subfolder")).split("\\") if p]
        if (parts and parts[0] == "microsoft") or any(p in PLACED_REFUSED_FOLDERS for p in parts):
            return "its sub-folder is one Windows starts programs from"
        if os.path.isfile(source) and placed_file_refused(source):
            return "a program, script or shortcut can only go in the install folder"
    return ""


def placed_file_refused(name):
    """True for a file that runs or opens something: never placed outside the install folder."""
    return os.path.splitext(str(name))[1].lower() in PLACED_REFUSED_EXTENSIONS


def placed_files_root(output_path):
    return os.path.join(os.path.dirname(os.path.abspath(output_path)), PLACED_FILES_DIR)


def placed_subfolder(text):
    """A typed sub-folder (MyStudio\\MyGame) made safe for DestDir: each part as a
    folder name, so ".." and drive letters fall away rather than climb out."""
    parts = re.split(r"[\\/]+", str(text or ""))
    return "\\".join(p for p in (iss_value(part, "", for_path=True) for part in parts) if p)[:200]


def placed_files_lines(staged):
    """[Files] lines for the rows a build staged under ..\\.rialto-placed\\<n>\\.

    `staged` is the manifest the staging step wrote: per row its number, the
    file's name (empty for a folder), the place, the sub-folder and the two
    choices. Never replacing a file already there is the default, so a
    returning player's saves survive a reinstall, and the files outlive an
    uninstall unless the author asked otherwise. A row with a place Rialto does
    not know, or a name Inno would read as syntax, is left out.
    """
    places = dict(PLACED_FILE_PLACES)
    lines = []
    for row in staged if isinstance(staged, list) else []:
        if not isinstance(row, dict) or row.get("place") not in places:
            continue
        try:
            number = int(row.get("n"))
        except (TypeError, ValueError):
            continue
        name = str(row.get("name") or "")
        if name and (_ISS_META.search(name) or name != os.path.basename(name) or name.strip(". ") == ""):
            continue
        sub = placed_subfolder(row.get("subfolder"))
        if row["place"] != "The install folder":
            parts = [p.lower() for p in sub.split("\\") if p]
            if ((parts and parts[0] == "microsoft") or any(p in PLACED_REFUSED_FOLDERS for p in parts)
                    or (name and placed_file_refused(name))):
                continue
        dest = places[row["place"]] + ("\\" + sub if sub else "")
        flags = ["ignoreversion"]
        if not name:
            flags += ["recursesubdirs", "createallsubdirs"]
        if row.get("keep", True):
            flags.append("onlyifdoesntexist")
        if not row.get("remove", False):
            flags.append("uninsneveruninstall")
        flags.append("skipifsourcedoesntexist")
        lines.append('Source: "..\\%s\\%d\\%s"; DestDir: "%s"; Flags: %s'
                     % (PLACED_FILES_DIR, number, name or "*", dest, " ".join(flags)))
    return lines


# How hard the installer squeezes the game (1.5.1, B7). Balanced is 1.5.0's
# installer exactly, and what a profile without the key gets. Solid
# compression stays off in every choice: Setup would have to unpack
# everything before a file to reach it, and a multi-disc install that hits an
# error would ask for Disc 1 again.
COMPRESSION_CHOICES = (
    ("Balanced", "lzma2/fast"),
    ("Smallest disc", "lzma2/max"),
    ("Fastest install", "none"),
)


def compression_setting(choice):
    return dict(COMPRESSION_CHOICES).get(choice, "lzma2/fast")


# Pressed discs (1.5.1, B5): a disc a factory presses rather than one the
# author burns. Every copy of a build is the same image and nothing on a
# Rialto disc checks the media, so a pressed copy behaves like a burned one;
# what changes is what goes to the plant. CD and DVD only for now: pressed
# Blu-ray waits on two plants confirming a data BD-ROM without AACS, and on the
# first UDF 2.50 image a machine has read.
#
# The 8 cm minis (1.5.1, minis) press as an 8 cm CD-ROM and an 8 cm DVD-5. The
# DVD Forum's own name for the 8 cm single-layer disc is DVD-1, so the sheet
# says both. Neither has a second layer, so no layer break applies.
PRESSED_DISC_TYPES = {"Mini CD 210 MB (8 cm)": "CD-ROM, 8 cm", "CD 700 MB": "CD-ROM",
                      "Mini DVD 1.4 GB (8 cm)": "DVD-5, 8 cm (DVD-1)", "DVD 4.7 GB": "DVD-5",
                      "DVD DL 8.5 GB": "DVD-9"}
# The two 8 cm Target Media choices, by the names MEDIA_TYPES gives them.
MINI_DISC_MEDIA = ("Mini CD 210 MB (8 cm)", "Mini DVD 1.4 GB (8 cm)")
# A 24-minute 8 cm CD: 24 x 60 x 75 sectors, the 80-minute CD's density on the
# smaller disc. A pressed 8 cm CD-ROM is held to the same.
MINI_CD_SECTORS = 108_000
# An 8 cm single-layer DVD, a little under the 712,891 sectors of the smaller
# blank (DVD-R 2.0; DVD+R 1.2 gives 714,544). Sources beside MEDIA_TYPES.
MINI_DVD5_SECTORS = 712_800
SECTOR_BYTES = 2048
# Layer 0 of a DVD-9: a multiple of 16 inside the 2,085,000 sectors Sonopress
# gives a layer. Layer 1 takes the rest, so it is never the bigger of the two.
DVD9_LAYER0_SECTORS = 2_084_992
DVD9_LAYER_LIMIT = 2_085_000
# A single-layer DVD, a little under its 2,295,104 sectors.
DVD5_SECTORS = 2_295_000


def pressed_refusal(media):
    """Why a pressed disc cannot be this Target Media, or "" when it can."""
    media = str(media or "")
    if media in PRESSED_DISC_TYPES:
        return ""
    if media.startswith("Auto"):
        return "a plant presses a named size. Pick CD, DVD or DVD DL under Target Media."
    if media.startswith("M-DISC") or "128 GB" in media:
        return "%s only exists as a blank disc to burn, so there is nothing to press." % media
    if media in ("Blu-ray 25 GB", "Blu-ray DL 50 GB"):
        return ("pressed Blu-ray is not ready yet. It waits on plants confirming they press a data "
                "Blu-ray without copy protection. Build it unpressed for now, or pick a DVD.")
    if "XL" in media:
        return "no plant has confirmed pressing a %s as a data disc yet." % media
    return "pick CD, DVD or DVD DL under Target Media."


def dvd9_layers(sectors):
    """(Layer 0, Layer 1) sectors for a DVD-9 image, or None if it cannot be one."""
    sectors = int(sectors)
    if sectors <= 0 or sectors > 2 * DVD9_LAYER0_SECTORS:
        return None
    layer0 = min(sectors, DVD9_LAYER0_SECTORS)
    return layer0, sectors - layer0


def iso_facts(path):
    """(volume label, has UDF) read from a disc image's own descriptors."""
    label, udf = "", False
    try:
        with open(path, "rb") as f:
            f.seek(16 * SECTOR_BYTES)
            head = f.read(24 * SECTOR_BYTES)
    except OSError:
        return label, udf
    if head[1:6] == b"CD001":
        label = head[40:72].decode("ascii", "replace").strip()
    udf = any(head[i + 1:i + 5] in (b"NSR0",) for i in range(0, len(head), SECTOR_BYTES))
    return label, udf


def file_md5(path, chunk=8 * 1024 * 1024, progress=None):
    """The file's MD5. `progress`, if given, is called with each block's size."""
    import hashlib
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            digest.update(block)
            if progress:
                progress(len(block))
    return digest.hexdigest()


def checksum_text(discs):
    """Chksum.md5: one "hash *filename" line per image, the form Sonopress names."""
    return "".join("%s *%s\n" % (disc["md5"], disc["file"]) for disc in discs)


def master_sheet_text(title, developer, version, built_on, discs, signed):
    """The plain-text sheet that goes to the plant with the images."""
    lines = ["%s: master sheet" % title, "",
             "For the pressing plant. Made with Rialto %s on %s." % (version, built_on), "",
             "Title:       %s" % title,
             "Developer:   %s" % developer,
             "Discs:       %d" % len(discs), ""]
    for number, disc in enumerate(discs, start=1):
        sectors = disc["bytes"] // SECTOR_BYTES
        lines += ["Disc %d of %d" % (number, len(discs)),
                  "  File:          %s" % disc["file"],
                  "  Bytes:         {:,}".format(disc["bytes"]),
                  "  Sectors:       {:,} of 2,048 bytes".format(sectors),
                  "  MD5:           %s" % disc["md5"],
                  "  Volume label:  %s" % (disc["label"] or "(none)"),
                  "  Disc type:     %s" % disc["type"],
                  "  File system:   %s" % ("ISO 9660 level 3, Joliet, Rock Ridge and UDF" if disc["udf"]
                                           else "ISO 9660, Joliet and Rock Ridge")]
        if disc["type"] == "DVD-9":
            layers = dvd9_layers(sectors)
            if layers:
                lines.append("  Layer break:   Layer 0 {:,} sectors, Layer 1 {:,} sectors "
                             "(Layer 0 ends with sector {:,})".format(layers[0], layers[1], layers[0] - 1))
            if sectors <= DVD5_SECTORS:
                lines.append("  Note:          this image fits on one layer. A DVD-5 presses cheaper.")
        if disc["bytes"] % SECTOR_BYTES:
            lines.append("  Warning:       not a whole number of sectors. Rebuild before sending.")
        lines.append("")
    lines += ["setup.exe signed:  %s" % signed.get("setup.exe", "not checked"),
              "menu.exe signed:   %s" % signed.get("menu.exe", "not checked"), "",
              "A data disc: a PC game installer, no video. No copy protection is requested.",
              "The checksums are also in Chksum.md5, beside the images.", ""]
    return "\n".join(lines)


def progress_text(step, fraction=None, seconds=0.0, detail=""):
    """The build's live line (1.5.1, B6): the step, how far, and the time so far.

    "Compressing the installer: 812 of 3,140 files, 41%, 6 min 12 s". A step
    that cannot say how far still counts its seconds, so the line never stands
    still.
    """
    minutes, secs = divmod(int(max(seconds, 0)), 60)
    clock = "%d min %d s" % (minutes, secs) if minutes else "%d s" % secs
    parts = [detail] if detail else []
    if fraction is not None:
        parts.append("%d%%" % int(max(0.0, min(fraction, 1.0)) * 100))
    parts.append(clock)
    return "%s: %s" % (step, ", ".join(parts))


def iscc_compressing_path(line):
    """The file an ISCC "   Compressing: <path>" line names, or None.

    Taken from what ISCC 6.5.4 printed compiling a real Rialto script: one such
    line per file, after "Compressing Setup program executable" (no colon).
    """
    text = str(line or "").strip()
    if not text.startswith("Compressing: "):
        return None
    # A file with version info ends "   (3.12.10150.1013)", seen from ISCC 6.
    return re.sub(r"\s+\([\d.]+\)$", "", text[len("Compressing: "):]).strip() or None


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


def spanned_disc_count(base, payload, capacity, reserve, margin):
    """How many discs a build makes, worked out the way the build makes them (1.5.1, minis).

    base is what rides on Disc 1 beside the installer (the menu, setup.exe, the
    art); payload is what goes into the installer. One disc when both fit the
    media less margin, as create_iso decides. Otherwise Inno cuts the payload
    into slices of the media less reserve (get_disk_slice_size), and they are
    packed in order as create_spanned_isos packs them, Disc 1 starting with the
    base. Pure, so the disc meter and the harness use the same sum.
    """
    base, payload = max(int(base), 0), max(int(payload), 0)
    fit = capacity - margin
    if base + payload <= fit:
        return 1
    slice_size = max(262_144, min(capacity - reserve, 2_100_000_000))
    parts = [slice_size] * (payload // slice_size)
    if payload % slice_size:
        parts.append(payload % slice_size)
    discs, held = 1, base
    for part in parts:
        # Every disc holds something when the next part comes: Disc 1 its base,
        # a later disc the part that opened it. So a part never opens two.
        if held + part > fit:
            discs, held = discs + 1, 0
        held += part
    return discs


_MONITOR_CALLS = None  # (user32, MONITORINFO): made by monitor_calls the first time it is asked, and kept


def monitor_calls():
    """Windows' calls for asking about a monitor, declared once: (user32, MONITORINFO).

    ctypes keeps every structure class, and every pointer type made from one,
    for the life of the process. Declared inside work_area_of_monitor they were
    made again, and kept, each time a window opened. Raises if Windows cannot
    be asked; work_area_of_monitor answers None for that.
    """
    global _MONITOR_CALLS
    if _MONITOR_CALLS is None:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        # Its own handle on user32, so declaring these calls changes nothing for the rest of Rialto.
        user32 = ctypes.WinDLL("user32")
        user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
        user32.MonitorFromRect.restype = wintypes.HMONITOR
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        _MONITOR_CALLS = (user32, MONITORINFO)
    return _MONITOR_CALLS


def work_area_of_monitor(box=None):
    """One monitor's work area, the screen less the taskbar, as (left, top, width, height). None if Windows will not say.

    `box` is a window's place as (left, top, width, height): the monitor
    holding most of it is meant, or the nearest. With no box it is the monitor
    the pointer is on, for a window that has no place yet.
    Asked of Windows itself (1.5.1, B13.1), because Tk knows only the whole of
    the main screen: not the taskbar, not a second monitor, not a corner that
    is not 0, 0. Never raises: the caller falls back to Tk's measure of the
    screen, less an allowance for a taskbar it cannot see (available_space).
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32, MONITORINFO = monitor_calls()

        if box is not None:
            left, top, width, height = (int(n) for n in box)
            rect = wintypes.RECT(left, top, left + width, top + height)
            monitor = user32.MonitorFromRect(ctypes.byref(rect), 2)  # MONITOR_DEFAULTTONEAREST
        else:
            point = wintypes.POINT(0, 0)
            user32.GetCursorPos(ctypes.byref(point))
            monitor = user32.MonitorFromPoint(point, 1)  # MONITOR_DEFAULTTOPRIMARY
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
        else:
            work = wintypes.RECT()  # the main monitor's, when the one meant cannot be asked
            if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0):  # SPI_GETWORKAREA
                return None
        width, height = work.right - work.left, work.bottom - work.top
        if width <= 0 or height <= 0:
            return None
        return work.left, work.top, width, height
    except Exception:
        return None


# GUI class begins
class RialtoApp:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.root.title(f"{APP_NAME} {__version__} - Disc Builder")
        
        # Set favicon for main window
        try:
            icon_path = asset_path("bird_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass
        



        self.root.overrideredirect(True)  # Hide native title bar

        # Fit the window to the screen (1.5.1, B13.1): 700 wide and as tall as the work area of the monitor
        # Rialto opens on allows, up to 1200, centred in that work area. No floor: at 900 lines the window
        # was taller than a 1080p laptop's screen at 125 percent, and Windows chose where it went.
        self.window_height = self.place_window(self.root, 700, 1200)[1]
        ToolTip.place = self.tooltip_place  # tooltips are windows too, and take their place from the same rule
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
        # 1.5.1 (B9): an entry may also carry "icon" (a picture inside the game
        # folder) and "blurb" (one line for the Play page).
        self.game_executables = []
        # A Start Menu shortcut for each game as well as the menu's (B9). Off.
        self.game_shortcuts = False
        # Files the installer places on the player's PC (B10): rows of
        # {"source", "place", "subfolder", "keep", "remove"}.
        self.placed_files = []

        # Disc target and extras (Rialto 1.5)
        self.target_media_var = tk.StringVar(value="Auto (single disc)")
        # Beside Target Media (1.5.1): how hard the installer squeezes (B7),
        # and a disc a plant will press (B5).
        self.compression_var = tk.StringVar(value="Balanced")
        self.pressed_disc_var = tk.BooleanVar(value=False)
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
        self.say_missing_tools()
        self.load_last_session()
        self.load_config()
        self.load_last_used_profile()
        self.root.after_idle(self.fit_main_window)







    # A harness's pretended monitor (1.5.1, B13.5), as {"screen": (left, top, width, height), "work_area": (...)}.
    # None on every real run, and then Windows is asked for the real work area.
    PRETEND_MONITOR = None

    def available_space(self, window=None):
        """The space a window may be given, as (left, top, width, height): the one place the sizing code asks.

        It is the work area, the screen less the taskbar, of the monitor
        `window` is on. The main window is on one by the time it is sized
        (setting its icon shows it, where Windows chose), so Rialto opens on
        the monitor Windows picked for it and in the place Rialto picks. A
        window with no place yet is measured on the monitor the pointer is on.
        The corner is not always 0, 0 (a taskbar along the top or the left, a
        monitor left of the main one). If Windows will not say, it is the
        main screen as Tk measures it less 80 lines of height: Tk cannot see
        the taskbar, and 80 lines is the allowance 1.5.0 made for it on every
        screen. The whole screen would let a window run under the taskbar.
        tools-dev/test_fits_every_screen.py sets PRETEND_MONITOR to answer for
        a screen this PC does not have.
        """
        pretend = self.PRETEND_MONITOR
        if pretend is not None:
            return tuple(pretend["work_area"])
        window = window or self.root
        box = None
        try:
            if window.winfo_width() > 1 and window.winfo_height() > 1:
                box = (window.winfo_rootx(), window.winfo_rooty(), window.winfo_width(), window.winfo_height())
        except tk.TclError:
            pass
        return work_area_of_monitor(box) or (0, 0, window.winfo_screenwidth(), window.winfo_screenheight() - 80)

    def window_frame(self):
        """What Windows adds round a titled window, in lines: (title bar, border seen, border unseen).

        A dialog's size in Tk is what it holds. Windows puts the title bar above
        that and a border round it, and since Windows 10 all but one line of the
        border is there to be taken hold of, not seen. The unseen part may hang
        over the edge of the work area; the title bar and the line that shows
        may not.
        """
        try:
            import ctypes
            metric = ctypes.windll.user32.GetSystemMetrics
            border = metric(33) + metric(92)  # SM_CYSIZEFRAME + SM_CXPADDEDBORDER
            title = metric(4) + border        # SM_CYCAPTION, and the border above it
            if border <= 0 or title <= border:
                raise OSError("Windows gave no frame metrics")
            seen = 1 if sys.getwindowsversion().major >= 10 else border
            return title, seen, border - seen
        except Exception:
            return 31, 1, 7  # Windows 10 and 11 at 100 percent

    def fit_in_work_area(self, width, height, space, frame=(0, 0, 0), x=None, y=None, over=None):
        """The one rule for every window Rialto opens (1.5.1, B13): never larger than the work area, and wholly inside it.

        `width` and `height` are what the window holds. `space` is the work
        area from available_space. `frame` is what Windows adds round a titled
        window, from window_frame; a window with no title bar has none. With
        `over`, the box of another window, it goes in the middle of that box a
        third of the way down; with no `x` and `y` either, in the middle of the
        work area. Returns (width, height, x, y) for Tk's geometry. Arithmetic
        only: no window is touched.
        """
        left, top, area_w, area_h = (int(n) for n in space)
        title, seen, unseen = frame
        width = max(1, min(int(width), area_w - 2 * seen))
        height = max(1, min(int(height), area_h - title - seen))
        outer_w, outer_h = width + 2 * seen, height + title + seen
        if over is not None:
            over_x, over_y, over_w, over_h = over
            x = over_x + (over_w - width) // 2
            y = over_y + (over_h - height) // 3  # a third down reads better than dead centre
        if x is None:
            x = left + (area_w - outer_w) // 2 - unseen
        if y is None:
            y = top + (area_h - outer_h) // 2
        # Tk places a titled window by the corner of its unseen border.
        x = max(left - unseen, min(int(x), left + area_w - outer_w - unseen))
        y = max(top, min(int(y), top + area_h - outer_h))
        return width, height, x, y

    def place_window(self, window, width, height, x=None, y=None, over=None, near=None):
        """Give `window` its size and its place by the one rule (fit_in_work_area). Returns what it was given.

        `near` is the window whose monitor is meant; with none it is Rialto's
        own. Every window Rialto opens comes through here: the main window,
        each dialog (centre_on), its message box and the Restore popup. A
        tooltip keeps the size of its words and takes its place from the same
        rule, through tooltip_place.
        """
        frame = (0, 0, 0) if window.wm_overrideredirect() else self.window_frame()
        width, height, x, y = self.fit_in_work_area(
            width, height, self.available_space(near), frame, x, y, over)
        window.geometry(f"{width}x{height}+{x}+{y}")
        return width, height, x, y

    def tooltip_place(self, widget, width, height, x, y, above):
        """Where a tooltip goes, by the one rule: (x, y), wholly inside the work area of the monitor its widget is on.

        `x`, `y` is where it opens when there is room: below and right of the
        pointer, as it always did. Where that would cross the bottom of the
        work area it opens above the pointer instead, its bottom edge on the
        line `above`. Brought up by the rule alone it would open under the
        pointer, take the pointer from its widget and close itself, over and
        over. The rule then keeps it off the other three edges.
        """
        space = self.available_space(widget.winfo_toplevel())
        if y + height > space[1] + space[3]:
            y = above - height
        return self.fit_in_work_area(width, height, space, x=x, y=y)[2:]

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
        """Put `window` in the middle of `parent`, inside the work area of the monitor the parent is on.

        Two things went wrong before. Geometry was read before Tk had laid the
        parent out, so winfo_x/winfo_width answered 1 and 200 and the popup
        landed in the top-left corner of the monitor rather than over Rialto.
        And nothing clamped the result, so a Rialto window near the edge of a
        screen could put its own dialog half off it. Since 1.5.1 (B13.4) the
        size and the place both go through the one rule in place_window: no
        dialog is larger than the work area, and none hangs under the taskbar.
        Returns the (width, height) the window was given.
        """
        parent = parent or self.active_parent()
        try:
            parent.update_idletasks()
            over = (parent.winfo_rootx(), parent.winfo_rooty(), parent.winfo_width(), parent.winfo_height())
            if over[2] <= 1 or over[3] <= 1:  # not laid out yet: the middle of the work area
                over = self.available_space(parent)
            return self.place_window(window, width, height, over=over, near=parent)[:2]
        except tk.TclError:
            window.geometry(f"{int(width)}x{int(height)}")
            return int(width), int(height)

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

    # Disc Extras' two columns (1.5.1, B11): wide enough for both at 1366 by 768, the smallest screen it is tested on.
    DISC_EXTRAS_WIDTH = 1180

    def dialog_height_for(self, requested, work_area_height, title_bar=32):
        """How tall a dialog may be: what it holds (200 at least), never more than the work area less its title bar.

        `title_bar` is every line Windows adds above and below what the dialog
        holds: 32 on Windows 10 and 11 at 100 percent. Before 1.5.1 (B13.4) the
        limit was the whole screen less 80, which let a dialog run under the
        taskbar on a short screen.
        """
        return max(1, min(max(200, int(requested)), int(work_area_height) - int(title_bar)))

    def fold_tutorial(self, folded):
        """Fold the three-steps card to its title line, or open it again."""
        if folded:
            self.tutorial_more.pack_forget()
            self.tutorial_toggle.configure(text="Show")
        else:
            self.tutorial_more.pack(fill="x")
            self.tutorial_toggle.configure(text="Hide")

    def fit_main_window(self):
        """Keep Step 4 and the log in view on every screen (1.5.1).

        The window is 700 wide and as tall as the work area allows, up to 1200,
        never resized. At 1080p 1.5.0's page asked for more than its window
        held, so the Disc Icon row and the whole log sat under the build bar.
        The three-steps card starts folded to its title on every screen, with
        Show beside it to open it again (his word, 19 Oct 2026: the fold short
        screens had, everywhere; create_widgets). Where the folded page is
        still more than the window holds (1005 lines, and a 1080p laptop at
        125 percent has 816), the same page is laid out in fewer lines:
        tighten_to_fit.
        """
        try:
            self.root.update_idletasks()
            short = self.root.winfo_reqheight() > getattr(self, "window_height", 10 ** 6)
        except tk.TclError:
            return
        if short:
            self.tighten_to_fit()

    # The tighter page (1.5.1, B13.2, a candidate): how far each level draws the page in, for a window that cannot
    # hold the folded page. "gap" is the space under each part of the page; "row" the space above and below each
    # row inside a step; "log" the lines of log the page asks for (the log still takes whatever is to spare);
    # "bar" the export bar's own spaces (above its first row, above the build row, above the tick boxes, under
    # them); "button" what the build row's buttons add above and below their words. The page as it always was:
    # gap 8, row 4 (6 in Step 1), log 4, bar 8, 10, 8 and 12, button 6. No text is made smaller at any level.
    PAGE_LEVELS = (
        {"gap": 4, "row": 2, "log": 4, "bar": (6, 8, 6, 8), "button": 6},  # 1: and Step 2's fields two to a row
        {"gap": 4, "row": 1, "log": 3, "bar": (6, 8, 6, 8), "button": 6},  # 2: and Step 4's logos and icons paired
        {"gap": 2, "row": 1, "log": 2, "bar": (4, 6, 4, 5), "button": 3},  # 3: drawn in as far as it still reads
    )
    page_level = 0  # how far this page was drawn in as Rialto opened: 0 is the page as it always was

    def tighten_to_fit(self):
        """Lay the page out in fewer lines, a level at a time, until the window holds it (1.5.1, B13.2).

        The window stays tall and 700 wide, nothing scrolls and nothing is
        taken off the page: the same widgets, read through the same variables,
        in the same order of steps. Chosen once, as Rialto opens, by laying a
        level out and asking Tk what the page then asks for, not from a list of
        screens. Measured at 96 DPI, card folded: the page as it always was
        asks 1005 lines; level 1 asks 810 (a 1080p laptop at 125 percent has
        816), level 2 asks 703 (1366 x 768 has 720) and level 3 asks 655
        (1080p at 150 percent has 672). A window that holds the folded page is
        never touched, so a tall screen and 1080p at 100 percent are as they
        were. Under 655 lines the page is cut as it always was, the log first,
        and one line in the log says so.
        """
        try:
            for level in range(1, len(self.PAGE_LEVELS) + 1):
                self.root.update_idletasks()
                if self.root.winfo_reqheight() <= self.window_height:
                    return
                self.tighten_page(level)
                self.page_level = level
            self.root.update_idletasks()
            asks = self.root.winfo_reqheight()
        except Exception as e:
            # Every widget is still Rialto's own and still read as before; only where it sits may be half done.
            self.update_status("⚠️ Rialto's page could not be laid out tighter for this screen (%s)." % e)
            return
        if asks > self.window_height:
            self.update_status("⚠️ Rialto's page does not fit this screen: it is %d pixels tall with room for %d, "
                               "so the log and then the last rows of Step 4 are cut off. If Windows' display "
                               "Scale is above 100%%, lowering it makes room (Settings > System > Display)."
                               % (asks, self.window_height))

    def tighten_page(self, level):
        """Draw the page in to `level` (1, 2 or 3) from the level before it: only where the widgets sit changes."""
        tight = self.PAGE_LEVELS[level - 1]
        gap = tight["gap"]
        self.page_frame.pack_configure(pady=(gap, 0))
        for part in (self.tutorial_box, self.quick_row, self.step_frame, self.meta_frame, self.disc_frame,
                     self.art_frame):
            part.pack_configure(pady=(0, gap))
        self.status_text.configure(height=tight["log"])
        self.status_text.pack_configure(pady=(2, gap))
        if level == 1:
            self.pair_metadata_rows()
        elif level == 2:
            self.pair_artwork_rows()
        for step in (self.step_frame, self.meta_frame, self.disc_frame, self.art_frame):
            for row in step.winfo_children():  # every child of a step is one of its rows
                tighten = row.grid_configure if row.winfo_manager() == "grid" else row.pack_configure
                tighten(pady=tight["row"])
        above, build, ticks, under = tight["bar"]
        self.export_inner.pack_configure(pady=(above, under))
        self.export_action_row.pack_configure(pady=(build, 0))
        self.export_check_row.pack_configure(pady=(ticks, 0))
        for button in self.export_action_row.pack_slaves():
            button.pack_configure(ipady=tight["button"])

    def align_row_labels(self, rows):
        """Make the labels of these rows as wide as the widest of them needs, so their boxes start on one line.

        Each row is a label, then its box. On the full page every label is 20
        characters wide, the room one field to a row had. Returns that width.
        """
        labels = [row.pack_slaves()[0] for row in rows]
        for label in labels:
            label.configure(width=0)  # as wide as its own words
        widest = max(label.winfo_reqwidth() for label in labels)
        for label in labels:
            label.pack_configure(padx=(0, 4 + widest - label.winfo_reqwidth()))
        return widest

    def pair_metadata_rows(self):
        """Step 2 in two columns: what a person types on the left, what fills itself in from it on the right.

        Game Title, Developer and Publisher down the left; Start Menu Name,
        Copyright Text and Disc Name down the right, each beside the field it
        fills in from. Six rows become three. Tab still goes through them in
        the order they always had. The left column is as wide as its longest
        hint needs ("Who made it: you, your studio, or your team"), and the
        right has the rest.
        """
        fields = self.meta_frame.pack_slaves()
        for field in fields:
            field.pack_forget()
        for index, field in enumerate(fields):
            field.grid(row=index % 3, column=index // 3, sticky="ew", padx=4)
        typed, filled = fields[:3], fields[3:]
        label_width = self.align_row_labels(typed)
        self.align_row_labels(filled)
        # A hint is a label inside its box, 7 across from the box's edge, whether or not it is showing now.
        boxes = [field.pack_slaves()[1] for field in typed]
        hints = [hint.winfo_reqwidth() for box in boxes for hint in box.winfo_children()]
        box_width = max([box.winfo_reqwidth() for box in boxes] + [7 + width + 3 for width in hints])
        # The column: the field's own 4 either side, its label and the 4 after it, the box's 4 either side, the box.
        self.meta_frame.grid_columnconfigure(0, minsize=8 + label_width + 4 + 8 + box_width)
        self.meta_frame.grid_columnconfigure(1, weight=1)

    def pair_artwork_rows(self):
        """Step 4 in three rows: Menu Background across the top, the two logos side by side, then the two icons.

        Five rows become three, read left to right in the order they always
        had. A box beside another is narrow for a whole path, so it keeps the
        end of its path in view (show_path_end).
        """
        background, game_logo, company_logo, game_icon, disc_icon = fields = self.art_frame.pack_slaves()
        for field in fields:
            field.pack_forget()
        background.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4)
        for index, field in enumerate(fields[1:]):
            field.grid(row=1 + index // 2, column=index % 2, sticky="ew", padx=4)
        self.align_row_labels([background, game_logo, game_icon])
        self.align_row_labels([company_logo, disc_icon])
        paths = (self.logo_path_var, self.company_logo_var, self.ico_path_var, self.disc_icon_var)
        for field, path in zip(fields[1:], paths):
            box = field.pack_slaves()[1]
            box.configure(width=8)  # asks for little and is given what the row has, so Browse keeps its whole width
            self.show_path_end(box, path)
        # Both columns share what is to spare, so the four boxes are one width.
        self.art_frame.grid_columnconfigure(0, weight=1)
        self.art_frame.grid_columnconfigure(1, weight=1)

    def show_path_end(self, box, path):
        """Keep the end of a path in view in a narrow box: the file's name is what tells one path from another.

        When the path is set (Browse, a profile, Restore page) and when the box
        is left. Not while it is being typed in.
        """
        def show_end(*_args):
            try:
                box.xview_moveto(1.0)
            except tk.TclError:
                pass  # the window is closing

        def path_set(*_args):
            try:
                if box.focus_get() is not box:
                    box.after_idle(show_end)
            except (tk.TclError, KeyError, RuntimeError):
                pass  # the window is closing, or Tk cannot say who has the focus: the path is set all the same

        path.trace_add("write", path_set)
        box.bind("<FocusOut>", show_end, add="+")
        box.after_idle(show_end)

    def fit_dialog_to_screen(self, dialog, width, height=None):
        """Size a built dialog to what it holds, within the work area, and let the author resize it.

        `height` is for a dialog that wants more than its widgets ask for: one
        that scrolls inside (Configure Code Signing) or is laid out with room
        to spare (Check My Setup). It gets that when the work area has it, and
        never less than what it holds if that fits.

        Where the work area is smaller than what the dialog holds, the dialog
        is cut: nothing in Rialto scrolls to make up for it (the owner's
        ruling). That is said in the log, one line each time it happens.
        """
        try:
            dialog.update_idletasks()
            # Over the window it was opened from. Asking who has the focus here could answer "this dialog".
            parent = dialog.master if isinstance(dialog.master, (tk.Tk, tk.Toplevel)) else self.root
            title, seen, _unseen = self.window_frame()
            holds_w, holds_h = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
            height = self.dialog_height_for(max(holds_h, int(height or 0)),
                                            self.available_space(parent)[3], title + seen)
            given_w, given_h = self.centre_on(dialog, width, height, parent)
            # Told that a window may be resized, Tk makes the window's frame again, even when it already could
            # be, and Windows draws a new frame's title bar light: the dark one themed_dialog asked for was gone
            # from every fitted dialog. So Tk is told only when it has to be, and the dark title bar is asked
            # for again, last, whatever was done to the frame.
            if tuple(dialog.resizable()) != (1, 1):
                dialog.resizable(True, True)
            self.darken_title_bar(dialog)
            # Given less than it holds because the work area had no more. A dialog narrower than its widgets ask
            # because Rialto chose that width is not the screen's doing, and is not said.
            short = []
            if given_h < holds_h:
                short.append("%d pixels tall with room for %d" % (holds_h, given_h))
            if given_w < min(holds_w, int(width)):
                short.append("%d pixels wide with room for %d" % (holds_w, given_w))
            if short:
                self.update_status("⚠️ %s does not fit this screen: it is %s, so part of it is cut off. "
                                   "If Windows' display Scale is above 100%%, lowering it makes room "
                                   "(Settings > System > Display)."
                                   % (getattr(dialog, "shown_name", "") or dialog.title(), " and ".join(short)))
        except tk.TclError:
            pass

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
        dialog.shown_name = title  # for the log, should the screen be too small for it (fit_dialog_to_screen)
        dialog.configure(bg=theme["bg"])
        self.centre_on(dialog, width, height, parent)
        dialog.transient(parent)
        dialog.grab_set()
        quiet_alt_tap(dialog)  # no menu bar here: a bare Alt would only freeze a build

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
        if getattr(self, "_close_when_stopped", False):
            return False if kind == "yesno" else None  # Rialto is closing: no more questions
        if getattr(self, "_batch", None) is not None:
            return self.batch_answer(title, message, kind)
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
        quiet_alt_tap(popup)

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
        """Every way of closing Rialto comes here: the title bar's X, File > Exit, Alt+F4."""
        if getattr(self, "_building", False) or getattr(self, "_queue_running", False):
            # The window answers during a build now (1.5.1, B6), so it can be
            # closed during one. Ask, and stop the running tool if the answer is yes.
            batch, self._batch = getattr(self, "_batch", None), None  # a real question, even mid-queue
            asked = self.show_centered_popup(
                    "A build is running",
                    "Rialto is still making your disc. Stop the build and close Rialto?\n\n"
                    "What it has made so far stays in the output folder, unfinished.",
                    kind="yesno")
            self._batch = batch
            if not asked:
                return
            self._abandon_build = True
            self._close_when_stopped = True
            tool = getattr(self, "_running_tool", None)
            if tool is not None and tool.poll() is None:
                tool.kill()
            # The build is still on the stack below this click. The window goes
            # now; the build stops at its next check, and close_if_asked closes
            # Rialto once it has unwound, so nothing writes to a destroyed window.
            for window in [self.root] + [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]:
                try:
                    window.withdraw()
                except tk.TclError:
                    pass
            return
        self.close_now()

    def close_now(self):
        """Save the session and close the window."""
        self.save_last_session()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def close_if_asked(self):
        """Close Rialto once a build the person chose to stop has unwound."""
        if not getattr(self, "_close_when_stopped", False):
            return
        if getattr(self, "_building", False) or getattr(self, "_queue_running", False):
            return
        self._close_when_stopped = False
        self.close_now()




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
                    self.game_shortcuts = bool(profile_data.get("GameShortcuts", False))
                    self.placed_files = [r for r in profile_data.get("PlacedFiles", []) or [] if isinstance(r, dict)]
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


        self.title_label = tk.Label(self.title_bar, text=f"Rialto {__version__}", bg=self.dark_theme["bg"], fg=self.dark_theme["fg"], font=("Segoe UI", 10, "bold"))
        self.title_label.pack(side="left", padx=10)

        # Close Button
        self.close_btn = tk.Button(
            self.title_bar, text="X",
            bg=self.dark_theme["bg"],
            fg=self.dark_theme["fg"],
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            command=self.on_exit
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
            ("Files to Place on the PC…", self.configure_placed_files),
            ("Build Queue…", self.configure_build_queue),
            None,
            ("Configure Signing…", self.configure_signing),
        ])
        add_menu("Tools", [
            ("Import GOG…", self.import_gog_installer),
            ("Export .msix…", self.export_msix),
        ])
        add_menu("View", [
            ("Dark / Light", self.toggle_theme),
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
        self.page_frame = frame

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

        def tutorial_line(icon_name, text, bold=False, pad=(0, 1), parent=None):
            # TutorialRow, not Tutorial: the card carries the groove border and
            # a row that inherited it drew a light bar under every icon.
            row = ttk.Frame(parent or self.tutorial_box, style="TutorialRow.TFrame")
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
            return row

        title_row = tutorial_line("disc", "Three steps to a disc.", bold=True, pad=(8, 2))
        # Everything under the title starts folded on every screen (his word, 19 Oct 2026; it used to fold
        # only on a short one), so the page opens on Step 1. Show opens it.
        self.tutorial_more = ttk.Frame(self.tutorial_box, style="TutorialRow.TFrame")
        self.tutorial_more._rialto_style = "TutorialRow.TFrame"
        more = self.tutorial_more
        tutorial_line(None, "1.  Put your game in its own folder, then browse to it below.", parent=more)
        tutorial_line(None, "2.  Fill in the name and art. Hover any field for what it wants.", parent=more)
        tutorial_line(None, "3.  Preview the menu, then build. Your ISO lands in the output folder.", parent=more)
        tutorial_line("image", "Background: an animated GIF or a still JPG, at 1280x720.",
                      pad=(8, 1), parent=more)
        tutorial_line("tile", "Icons: .ico files at 256x256. icoconvert.com turns a PNG into one.", parent=more)
        tutorial_line("gift", "Disc Extras: bonus content, mods, Steam, a compatibility mode, files for "
                              "the player's PC, Mac and Linux.", pad=(0, 8), parent=more)
        self.tutorial_toggle = ttk.Label(title_row, text="Show", style="Tutorial.TLabel", cursor="hand2",
                                         font=("Segoe UI", 9, "underline"))
        self.tutorial_toggle._rialto_style = "Tutorial.TLabel"
        self.tutorial_toggle.pack(side="right")
        ToolTip(self.tutorial_toggle, "Shows or hides the three steps, the art sizes and what Disc Extras "
                                      "holds.")
        # Open (packed) folds, folded opens.
        self.tutorial_toggle.bind("<Button-1>", lambda _e: self.fold_tutorial(
            bool(self.tutorial_more.winfo_manager())))

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
        # Build Queue beside Browse (his word, 19 Oct 2026): a queue is the other way to start, and it
        # was only in the Disc menu. The Disc menu keeps it too.
        or_label = ttk.Label(step_row, text="or", style="Path.TLabel")
        or_label._rialto_style = "Path.TLabel"
        or_label.pack(side="left", padx=(8, 0))
        self.queue_btn = self.icon_button(
            step_row, "queue", "Build Queue", self.configure_build_queue, size=18, side="left", padx=(8, 0))
        ToolTip(self.queue_btn, "Build several discs in one run: add saved profiles, each with the game "
                                "folder it builds. No folder is needed here.")

        self.game_path_var = tk.StringVar(value="No folder chosen yet")
        # What the row shows: with Build Queue beside Browse there is less room, so a long path is shown
        # from its end, since the game's own folder name is what tells one path from another.
        self.game_path_shown = tk.StringVar(value=self.game_path_var.get())
        self.game_path_label = ttk.Label(step_row, textvariable=self.game_path_shown,
                                         style="Path.TLabel")
        self.game_path_label._rialto_style = "Path.TLabel"
        self.game_path_label.pack(side="left", padx=(10, 4), fill="x", expand=True)

        def show_game_path(*_args):
            text = self.game_path_var.get()
            try:
                room = self.game_path_label.winfo_width() - 4
                font = tkfont.Font(root=self.root, font=ttk.Style().lookup("Path.TLabel", "font")
                                   or "TkDefaultFont")
            except tk.TclError:
                return  # the window is closing
            if room > 40 and font.measure(text) > room:
                while len(text) > 1 and font.measure("\u2026" + text) > room:
                    text = text[1:]
                text = "\u2026" + text
            if self.game_path_shown.get() != text:
                self.game_path_shown.set(text)

        self.game_path_var.trace_add("write", show_game_path)
        self.game_path_label.bind("<Configure>", show_game_path, add="+")

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
                ToolTip(entry, "The name players see in the Windows Start Menu. Fills in from Game Title until you type your own.")

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
        self.game_exes_summary_var = tk.StringVar(value="One game, found by Rialto")
        exe_summary = ttk.Entry(exe_row, textvariable=self.game_exes_summary_var, state="readonly")
        exe_summary.pack(side="left", fill="x", expand=True)
        # "Add Games", not "Configure" (his word, 19 Oct 2026: Configure was walked past).
        exe_btn = ttk.Button(exe_row, text="Add Games\u2026", command=self.configure_game_exes, style="Rounded.TButton")
        exe_btn.pack(side="left", padx=(6, 4), pady=2)
        exe_tip = ("One game? Leave this alone: Rialto finds it by itself. More than one? Click Add Games, then "
                   "double-click each game, or let Find a game in each folder do it. Players then pick a game "
                   "from Play Games on the disc menu.")
        ToolTip(exe_summary, exe_tip)
        ToolTip(exe_btn, exe_tip)

        # target media + disc extras
        media_row = ttk.Frame(self.disc_frame)
        media_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(media_row, text="Target Media:", width=20).pack(side="left", padx=(0, 4), pady=2)
        # As tall as the list, so every disc shows when it opens and none is
        # scrolled to (1.5.1, minis: fifteen choices, past Tk's ten).
        media_combo = ttk.Combobox(media_row, textvariable=self.target_media_var, state="readonly",
                                   values=[name for name, _cap in self.MEDIA_TYPES],
                                   height=len(self.MEDIA_TYPES), style="Media.TCombobox",
                                   postcommand=lambda: self.widen_media_list(media_combo))
        media_combo.pack(side="left", fill="x", expand=True)
        media_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_disc_meter())
        # On the Target Media row, not a row of their own: at 1080p another row
        # would push the log back under the build bar.
        compression_label = ttk.Label(media_row, text="Compression:")
        compression_label.pack(side="left", padx=(6, 4))
        compression_combo = ttk.Combobox(media_row, textvariable=self.compression_var, state="readonly",
                                         width=12, values=[label for label, _setting in COMPRESSION_CHOICES])
        compression_combo.pack(side="left")
        # Fastest install stores the game as it is, so the meter weighs it again.
        compression_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_disc_meter())
        compression_tip = ("How hard the installer squeezes your game. Balanced suits most games. Smallest "
                           "disc squeezes hardest, so the build takes longer. Fastest install stores the game "
                           "as it is, so setup only copies it, and the disc is bigger, which can mean "
                           "more discs.")
        ToolTip(compression_label, compression_tip)
        ToolTip(compression_combo, compression_tip)
        pressed_check = self.themed_check(media_row, "Pressed", self.pressed_disc_var, side="left", padx=(8, 0))
        ToolTip(pressed_check, "Tick this when a pressing plant will make your discs. Rialto adds the "
                               "checksum file and a master sheet to send with them, and works out the layer "
                               "break for a dual-layer DVD. Pressing works with CD and DVD, full size or 8 cm, and DVD DL.")
        extras_btn = ttk.Button(media_row, text="Disc Extras", command=self.configure_disc_extras, style="Rounded.TButton")
        extras_btn.pack(side="left", padx=(6, 4), pady=2)
        ToolTip(media_combo, "Pick the disc you plan to burn. If your game is too big for one disc, Rialto builds a numbered multi-disc set automatically. Auto means one disc, any size. Mini means the small 8 cm disc, which needs a tray drive.")
        ToolTip(extras_btn, "Bonus content, a mod tool, an Add to Steam button, a compatibility mode, files for the "
                            "player's PC, and Mac or Linux builds on the same disc. All optional.")

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
        ico_tip = "The icon for your installer and desktop shortcut: the small image players see in the Start Menu and taskbar. Needs to be a 256x256 .ico file. You can convert a PNG at icoconvert.com."
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
                     "folder and artwork before compression, so with Balanced or Smallest disc the "
                     "finished ISO is often smaller, and with Fastest install about the same. "
                     "Change Target Media to see it against a different disc. During a build "
                     "this line says what Rialto is doing and how far it has got.")
        ToolTip(self.disc_meter, meter_tip)
        ToolTip(self.disc_fill_label, meter_tip)

        # --- Row 2: build and preview ---
        action_row = surface(tk.Frame(inner, bg=theme["header_bg"]))
        action_row.pack(fill="x", pady=(10, 0))
        self.export_action_row = action_row

        build_btn = self.icon_button(action_row, "play", "BUILD GAME INSTALLER",
                                     self.run_build_process, style="Build.TButton", size=15)
        build_btn.pack(side="left", ipady=6, fill="x", expand=True)
        self.build_btn = build_btn
        ToolTip(build_btn, "Makes the whole disc: installer, disc menu, artwork and the final ISO, "
                           "in one pass. The log above says what it is doing at each step, and the line "
                           "above this button says how far it has got and for how long.")

        # Disc Extras sits here as well as beside Target Media. It is where
        # bonus content, mods, Steam and the Mac and Linux builds live, and up
        # in the form on its own it is easy to walk straight past.
        extras_btn = self.icon_button(action_row, "gift", "Disc Extras",
                                      self.configure_disc_extras, size=15)
        extras_btn.pack(side="left", padx=(8, 0), ipady=6)
        ToolTip(extras_btn, "Bonus content, a mod tool, the Add to Steam button, a compatibility mode, "
                            "files for the player's PC, and Mac or Linux builds on the same disc. All optional.")

        preview_btn = self.icon_button(action_row, "eye", "Preview Disc Menu",
                                       self.preview_disc_menu, size=15)
        preview_btn.pack(side="left", padx=(8, 0), ipady=6)
        ToolTip(preview_btn, "Opens your disc menu exactly as players will see it, in a few seconds. "
                             "Nothing is built or burned. Starting a game and Uninstall are switched "
                             "off, so you can click around freely. On a disc of several games, Play "
                             "Games opens the Choose Your Game page.")

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
        self.game_shortcuts = False
        self.placed_files = []
        self.refresh_game_exes_summary()
        self.target_media_var.set("Auto (single disc)")
        self.compression_var.set("Balanced")
        self.pressed_disc_var.set(False)
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
    # What they really weigh when the installer stores them as they are (Fastest install): the two
    # Visual C++ redistributables, about 39 MB, and the DLLs copied beside the game (1.5.1, end-to-end runs).
    RUNTIME_STORED = 42 * 1024 * 1024
    # What rides on Disc 1 beside the menu and the folders: setup.exe's loader (2.6 MB measured),
    # autorun.inf, README.txt, the two .bat files and the MULTI-DISC README.
    DISC1_FILES_ALLOWANCE = 3 * 1024 * 1024

    def widen_media_list(self, combo):
        """Open the Target Media list as wide as its longest name (bugs review, 1.5.1).

        The box shares its row with Compression, so "Blu-ray XL 128 GB (BD-R quad layer)" is cut in it, and a
        ttk list opens only as wide as its box. Just before the list opens, its style's postoffset widens it
        to the longest name in the list's own font, kept on the screen. The closed box may still cut the
        longest names; the line under the log names the whole choice.
        """
        try:
            popdown = combo.tk.eval("ttk::combobox::PopdownWindow %s" % combo)
            font = tkfont.Font(root=combo, font=combo.tk.call(popdown + ".f.l", "cget", "-font"))
            longest = max(font.measure(str(name)) for name in combo.cget("values"))
            # The list's own border and padding, its frame's border, and a little air.
            need = longest + font.measure("0") * 2 + 12
            extra = max(need - combo.winfo_width(), 0)
            left, _top, width, _height = self.available_space()
            right = combo.winfo_rootx() + combo.winfo_width() + extra
            shift = max(min(left + width - right, 0), left - combo.winfo_rootx())
            ttk.Style(combo).configure("Media.TCombobox", postoffset=(shift, 0, extra, 0))
        except (tk.TclError, ValueError):
            pass

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
        icons = [self.ico_path_var.get().strip(), self.disc_icon_var.get().strip()]
        stored = getattr(self, "compression_var", None) is not None and \
            self.compression_var.get() == "Fastest install"

        def measure():
            self._fill_bytes, self._disc1_bytes = self.disc_weights(path, extras, duplicated, menu_extra,
                                                                    icons, stored)
            try:
                self.root.after(0, self.draw_disc_meter)
            except (RuntimeError, tk.TclError):
                pass  # window closed while the walk was still running

        threading.Thread(target=measure, daemon=True).start()

    def disc_weights(self, path, extras, duplicated, menu_extra, icons=(), stored=False):
        """(what the disc holds, what of it rides on Disc 1 beside the installer's slices), in bytes.

        Never touches the window, so it runs on the meter's worker thread. `duplicated` are the folders that
        go on the disc root and inside the installer (mods, bonus, Mac, Linux); `menu_extra` is
        menu_staging_bytes(); `icons` the game and disc icons; `stored` is Fastest install.

        Disc 1 is weighed as create_spanned_isos fills it (bugs review, 1.5.1): the menu folder, the disc-root
        copies of the duplicated folders, setup.exe, autorun.inf, the READMEs and the icons, each file in
        whole sectors as a disc holds it. Only the setup-N.bin slices are packed onto the other discs.

        A Fastest install build stores everything as it is, so the total there also counts the menu a
        second time (it is on the disc root and inside the installer), the runtimes at their real weight,
        and Disc 1's own files (end-to-end runs, 1.5.1). The total for the other compressions is as before.
        """
        def folder_size(folder):
            total = 0
            for root_dir, _dirs, files in os.walk(folder):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root_dir, name))
                    except OSError:
                        pass
            return total

        def on_disc(size):
            return (-(-size // 2048) + 1) * 2048  # whole sectors, and one for its record

        def folder_on_disc(folder):
            total = 0
            for root_dir, _dirs, files in os.walk(folder):
                total += 2048
                for name in files:
                    try:
                        total += on_disc(os.path.getsize(os.path.join(root_dir, name)))
                    except OSError:
                        pass
            return total

        def inside_game(extra):
            # A folder beside the game whose name starts the same ("Demo Linux" beside "Demo") is not in it.
            try:
                return os.path.commonpath([os.path.abspath(extra), os.path.abspath(path)]) == os.path.abspath(path)
            except ValueError:
                return False

        total = folder_size(path)
        for extra in extras:
            # Art already inside the game folder is counted once, not twice
            if not extra or inside_game(extra):
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
        disc1 = max(menu_extra - self.RUNTIME_ALLOWANCE, 0) + self.DISC1_FILES_ALLOWANCE
        for folder in duplicated:
            if folder and os.path.isdir(folder):
                total += folder_size(folder)
                disc1 += folder_on_disc(folder)

        # The icons on the disc root: the ones picked, and every .ico at the game folder's root, which the
        # build copies beside setup.exe.
        icon_bytes = 0
        named = {os.path.normcase(os.path.abspath(i)) for i in icons if i and os.path.isfile(i)}
        try:
            named |= {os.path.normcase(os.path.join(path, n)) for n in os.listdir(path) if n.lower().endswith(".ico")}
        except OSError:
            pass
        for icon in named:
            try:
                icon_bytes += on_disc(os.path.getsize(icon))
            except OSError:
                pass
        disc1 += icon_bytes

        fill = total + menu_extra
        if stored:
            fill += (max(menu_extra - self.RUNTIME_ALLOWANCE, 0) + self.RUNTIME_STORED - self.RUNTIME_ALLOWANCE
                     + self.DISC1_FILES_ALLOWANCE + icon_bytes)
        return fill, disc1

    def draw_disc_meter(self):
        """Paint the little disc and the bar beside it from self._fill_bytes."""
        if not hasattr(self, "disc_bar"):
            return
        theme = self.dark_theme if self.theme_mode.get() == "dark" else self.light_theme
        total = self._fill_bytes
        capacity = self.get_target_media_capacity()
        usable = (capacity - self.MEDIA_RESERVE) if capacity else 0
        # A mini disc (1.5.1, minis) is weighed as the build will weigh it. The
        # total already holds the menu, so it is set against the disc less the
        # filesystem margin, the same line create_iso draws between one disc
        # and a set; and a set is counted as create_spanned_isos packs it. The
        # reserve is 2% of a DVD but nearly half a mini CD, so the larger
        # discs' sum, which takes it off as well, would call a demo two minis
        # when it is one.
        mini = self.target_media_var.get() in MINI_DISC_MEDIA
        if mini and capacity:
            usable = capacity - self.SPAN_MARGIN

        progress = getattr(self, "_build_line", None)
        if progress is not None:
            # A build is running (1.5.1, B6): this row is its live line.
            text, fraction = progress[0], progress[1] or 0.0
            color = theme["meter_fill"]
        elif not total:
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
            if mini and usable < 1e9:
                text = "%d MB of %d MB usable on %s - %d%%" % (
                    total // 1_000_000, usable // 1_000_000, label, percent)
            if fraction > 1.0:
                discs = int(total // usable) + 1
                if mini:
                    base = min(getattr(self, "_disc1_bytes", 0), total)
                    discs = spanned_disc_count(base, total - base, capacity,
                                               self.MEDIA_RESERVE, self.SPAN_MARGIN)
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
        profile_data = self.current_profile_data()

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

    def current_profile_data(self):
        """Everything on the form, as a profile: Save Profile's, and the Build Queue's snapshot (B1)."""
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
        profile_data["GameShortcuts"] = bool(self.game_shortcuts)
        profile_data["PlacedFiles"] = self.placed_files
        profile_data["TargetMedia"] = self.target_media_var.get()
        profile_data["Compression"] = self.compression_var.get()
        profile_data["PressedDisc"] = bool(self.pressed_disc_var.get())
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
        return profile_data

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
            self.apply_profile_file(file_path)

    def apply_profile_file(self, file_path, remember=True):
        """Put one profile file on the form: Load Profile's work, and each Build Queue row's (B1).

        True when it loaded. `remember` False leaves last_profile.json alone, so
        a queue does not change which profile Rialto opens with next time.
        """
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
                self.game_shortcuts = bool(profile_data.get("GameShortcuts", False))
                self.placed_files = [r for r in profile_data.get("PlacedFiles", []) or [] if isinstance(r, dict)]
                self.refresh_game_exes_summary()
                self.target_media_var.set(profile_data.get("TargetMedia", "Auto (single disc)"))
                compression = profile_data.get("Compression", "Balanced")
                self.compression_var.set(compression if compression in dict(COMPRESSION_CHOICES) else "Balanced")
                self.pressed_disc_var.set(bool(profile_data.get("PressedDisc", False)))
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
                # What happens next, said truly for each (1.5.1, end-to-end runs): the build will not
                # start without a menu background and a game icon; the rest it builds without.
                needed = [label for label, _p in stale if label in ("Menu Background", "Game Icon")]
                optional = [label for label, _p in stale if label not in needed]
                if needed:
                    self.update_status("   Pick %s again under Step 4: the build cannot start without %s."
                                       % (" and ".join(needed), "them" if len(needed) > 1 else "it"))
                if optional:
                    self.update_status("   Pick %s again, or the disc is built without %s."
                                       % (", ".join(optional), "them" if len(optional) > 1 else "it"))
                
                # Save as last used profile
                if remember:
                    profile_name = Path(file_path).name
                    with open(LAST_PROFILE_FILE, "w", encoding="utf-8") as f:
                        json.dump({"last_profile": profile_name}, f)
                return True
            except Exception as e:
                self.update_status(f"❌ Failed to load profile: {e}")
        return False






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
    #
    # The minis (1.5.1, minis) are the 8 cm discs, each listed just before its
    # full-size kin so the list still runs small to large within a family.
    # Mini CD: a 24-minute 8 cm CD-R, 108,000 sectors of 2,048 bytes, sold as
    # 210 MB; the older 21-minute disc (185 MB) is not offered, as 24 is what
    # blanks are sold as now (Wikipedia, "Mini CD": 21 min 185 MB, 24 min
    # 210 MB). Mini DVD: an 8 cm single-layer DVD, sold as 1.4 GB. DVD-R 2.0
    # gives it 712,891 sectors and DVD+R 1.2 gives 714,544 (the DVD-R and
    # DVD+R specifications' tables, as OSTA's DVD FAQ quotes them, reproduced
    # at fvue.nl "How many bytes can be stored on a DVD?"), and the DVD Forum's
    # DVD-1 (8 cm single-layer DVD-ROM, ECMA-267) is 1.46 GB. The smaller,
    # DVD-R's, is used, written as its specification rounds it, 1,460,000,000
    # bytes, as DVD 4.7 GB is written 4,700,000,000: a burn never fails.
    MEDIA_TYPES = [
        ("Auto (single disc)", None),
        ("Mini CD 210 MB (8 cm)", 221_184_000),
        ("CD 700 MB", 737_280_000),
        ("Mini DVD 1.4 GB (8 cm)", 1_460_000_000),
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
    #
    # The minis keep the same 96 MiB (1.5.1, minis), on measurement. Four real
    # Rialto discs carried 71.2 to 78.8 MB beside the installer slices: menu.exe
    # 37.4 MB, a GIF background of up to 31.6 MB, the runtimes and Steam art
    # beside the menu about 6.5 MB, setup.exe 2.2 to 2.6 MB, two icons, and
    # under 0.1 MB of filesystem. Without a GIF it is about 48 MB. The first
    # slice shares Disc 1 only when that rides in the reserve less SPAN_MARGIN,
    # 80 MiB (83.9 MB): the heaviest, 75.2 MiB, fits with 4.8 MiB to spare. A
    # smaller reserve on a mini would put a disc's menu on a disc of its own.
    MEDIA_RESERVE = 96 * 1024 * 1024
    # What a disc of a spanned set may really hold: the media less a little for
    # the filesystem itself (1.5.1). MEDIA_RESERVE is already taken off every
    # installer slice (get_disk_slice_size), and it is that room which carries
    # the menu and setup.exe on Disc 1. Packing the discs against the media less
    # the reserve again counted it twice: Disc 1 went out with only the menu on
    # it, and a 1.2 GB game took four CDs where two hold it.
    SPAN_MARGIN = 16 * 1024 * 1024

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
            self.game_exes_summary_var.set("One game, found by Rialto")
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
            entry = {"name": name, "exe": exe}
            # The Play page's picture and line (1.5.1, B9), only when set, so a
            # 1.5.0 profile writes the menu_config.json it always wrote.
            icon = str(game.get("icon") or "").strip().replace("\\", "/")
            if (icon and self.current_game_path and not os.path.isabs(icon)
                    and ".." not in icon.split("/")
                    and os.path.isfile(os.path.join(self.current_game_path, icon))):
                entry["icon"] = icon
            blurb = sanitize_text(game.get("blurb") or "").strip()[:140]
            if blurb:
                entry["blurb"] = blurb
            valid.append(entry)
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

    GAME_PICTURES = ("icon.ico", "icon.png", "cover.png", "cover.jpg")

    def games_in_subfolders(self, base):
        """One game per sub-folder (1.5.1, B9): a demo disc is a folder of game folders.

        Each sub-folder's exe is found the way a single-game disc's is, its
        label is the folder's name, and an icon or cover image beside it is its
        picture on the Play page. Folders that never hold a game (menu, bonus,
        mods, redistributables) and folders with no exe are passed over.
        """
        games = []
        try:
            names = sorted(os.listdir(base), key=str.casefold)
        except OSError:
            return games
        for name in names:
            folder = os.path.join(base, name)
            if (name.startswith(".") or name.lower() in self.NON_GAME_DIRS
                    or not os.path.isdir(folder) or os.path.islink(folder)):
                continue
            exe = self.detect_primary_game_exe(folder)
            if not exe:
                continue
            entry = {"name": name, "exe": name + "/" + exe}
            for picture in self.GAME_PICTURES:
                if os.path.isfile(os.path.join(folder, picture)):
                    entry["icon"] = name + "/" + picture
                    break
            games.append(entry)
        return games

    def configure_game_exes(self):
        """Dialog to pick which games the disc menu offers (a disc of several games).

        1.5.1 (B9): a demo disc is usually a folder of game folders, so one
        click finds the game in each, with its folder's name and picture. Rows
        can be reordered, given a line for the Play page, or pointed at another
        exe by hand. Its own window, so the main window never grows.
        """
        if not self.current_game_path:
            self.show_centered_popup("Select Game Folder", "Browse for your game folder first, then add the games.")
            return

        discovered = self.discover_game_exes()
        configured = {str(g.get("exe", "")).replace("\\", "/"): g
                      for g in self.game_executables if isinstance(g, dict)}
        all_exes = [e for e in dict.fromkeys(list(configured) + discovered) if e]

        theme = self.current_theme()
        dialog, body = self.themed_dialog(
            "Games on Disc",
            "One disc, as many games as you like",
            width=820, height=600)

        # Packed first, against the bottom, so a long list of executables cannot
        # push Save off the window.
        button_row = tk.Frame(body, bg=theme["bg"])
        button_row.pack(side="bottom", fill="x", padx=12, pady=(4, 12))

        tk.Label(body, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w",
                 text=("One game? Leave every row unticked. Rialto finds it by itself.\n"
                       "Two or more? Double-click each game to tick it. Players pick one from Play Games.\n"
                       "Each game in its own folder? Click Find a game in each folder."),
                 font=("Segoe UI", 10)).pack(fill="x", padx=12, pady=(10, 6))

        self.style_treeview(theme)
        columns = ("include", "name", "exe", "about")
        tree = ttk.Treeview(body, columns=columns, show="headings", height=10,
                            style="Rialto.Treeview")
        tree.heading("include", text="In Menu")
        tree.heading("name", text="Name")
        tree.heading("exe", text="Program (.exe)")
        tree.heading("about", text="One line about it")
        tree.column("include", width=70, anchor="center")
        tree.column("name", width=170)
        tree.column("exe", width=260)
        tree.column("about", width=250)
        tree.pack(fill="both", expand=True, padx=12, pady=4)

        row_state, row_icon = {}, {}

        def add_row(exe, name, about="", icon="", included=False):
            item = tree.insert("", "end", values=("✔" if included else "", name, exe, about))
            row_state[item] = included
            row_icon[item] = icon
            return item

        for exe in all_exes:
            game = configured.get(exe) or {}
            add_row(exe, game.get("name") or os.path.splitext(os.path.basename(exe))[0],
                    game.get("blurb", ""), game.get("icon", ""), exe in configured)

        def set_included(item, included):
            row_state[item] = included
            values = list(tree.item(item, "values"))
            values[0] = "✔" if included else ""
            tree.item(item, values=values)

        def toggle(event=None):
            item = tree.focus()
            if item:
                set_included(item, not row_state[item])

        tree.bind("<Double-1>", toggle)
        tree.bind("<space>", toggle)
        ToolTip(tree, "Double-click a game, or select it and press Space, to tick or untick it. A ticked game "
                      "is on the disc menu. Every file in your game folder goes on the disc either way.")

        # The selected row's label and its line on the Play page
        edit_row = tk.Frame(body, bg=theme["bg"])
        edit_row.pack(fill="x", padx=12, pady=4)
        tk.Label(edit_row, text="Name:", bg=theme["bg"], fg=theme["fg"]).pack(side="left")
        rename_var = tk.StringVar()
        rename_entry = ttk.Entry(edit_row, textvariable=rename_var, width=22)
        rename_entry.pack(side="left", padx=6)
        ToolTip(rename_entry, "The selected game's name on the disc menu and the Choose Your Game page. "
                              "Click Apply to keep it.")
        tk.Label(edit_row, text="One line:", bg=theme["bg"], fg=theme["fg"]).pack(side="left")
        about_var = tk.StringVar()
        about_entry = ttk.Entry(edit_row, textvariable=about_var)
        about_entry.pack(side="left", fill="x", expand=True, padx=6)
        ToolTip(about_entry, "One line under the game's name on the Choose Your Game page, such as its genre "
                             "or how long a demo lasts. Up to 140 characters. Click Apply to keep it.")

        def load_selected(event=None):
            item = tree.focus()
            if item:
                _included, name, _exe, about = tree.item(item, "values")
                rename_var.set(name)
                about_var.set(about)

        def apply_text():
            item = tree.focus()
            if not item:
                return
            values = list(tree.item(item, "values"))
            if sanitize_text(rename_var.get()).strip():
                values[1] = sanitize_text(rename_var.get()).strip()[:80]
            values[3] = sanitize_text(about_var.get()).strip()[:140]
            tree.item(item, values=values)

        tree.bind("<<TreeviewSelect>>", load_selected)
        apply_button = ttk.Button(edit_row, text="Apply", command=apply_text, style="Rounded.TButton")
        apply_button.pack(side="left")
        ToolTip(apply_button, "Keeps the Name and One line typed here for the selected game.")

        # Folders, order, and an exe picked by hand
        tools_row = tk.Frame(body, bg=theme["bg"])
        tools_row.pack(fill="x", padx=12, pady=4)

        def find_per_folder():
            found = self.games_in_subfolders(self.current_game_path)
            if not found:
                self.show_centered_popup(
                    "No game folders found",
                    "Rialto found no folder with a game in it. Put each game in a folder of its own "
                    "inside your game folder, then try again.")
                return
            by_exe = {tree.item(i, "values")[2]: i for i in tree.get_children()}
            for position, game in enumerate(found):
                item = by_exe.get(game["exe"])
                if item is None:
                    item = add_row(game["exe"], game["name"], icon=game.get("icon", ""))
                else:
                    # A row the scan listed under its exe's name takes the
                    # folder's; one already on the disc keeps the author's label.
                    if not row_state.get(item):
                        values = list(tree.item(item, "values"))
                        values[1] = game["name"]
                        tree.item(item, values=values)
                    if not row_icon.get(item):
                        row_icon[item] = game.get("icon", "")
                set_included(item, True)
                tree.move(item, "", position)
            self.update_status(f"🎮 Games on Disc: found a game in {len(found)} folders")

        def move(step):
            item = tree.focus()
            if item:
                tree.move(item, "", max(0, tree.index(item) + step))
                tree.see(item)

        def pick_exe():
            item = tree.focus()
            if not item:
                self.show_centered_popup("Pick a row first", "Select the game whose exe you want to change, then pick its exe.")
                return
            base = os.path.realpath(self.current_game_path)
            chosen = filedialog.askopenfilename(parent=dialog, title="Pick the game's exe",
                                                initialdir=base, filetypes=[("Programs", "*.exe")])
            if not chosen:
                return
            chosen = os.path.realpath(chosen)
            try:
                inside = os.path.commonpath([base, chosen]) == base and chosen != base
            except ValueError:
                inside = False
            if not inside:
                self.show_centered_popup(
                    "Outside the game folder",
                    "The exe has to be inside your game folder, because that folder is what goes on the disc.")
                return
            values = list(tree.item(item, "values"))
            values[2] = os.path.relpath(chosen, base).replace("\\", "/")
            tree.item(item, values=values)
            set_included(item, True)

        for text, command, tip in (
                ("Find a game in each folder", find_per_folder,
                 "For a demo disc: each folder inside your game folder holding a game becomes a row, "
                 "named after the folder, with an icon.ico, icon.png, cover.png or cover.jpg in it as its picture."),
                ("Move Up", lambda: move(-1), "The Choose Your Game page lists games in this order. "
                                              "The main menu lists them A to Z."),
                ("Move Down", lambda: move(1), "The Choose Your Game page lists games in this order. "
                                               "The main menu lists them A to Z."),
                ("Pick the exe…", pick_exe, "Start the selected game with a different exe from inside your game folder.")):
            button = ttk.Button(tools_row, text=text, command=command, style="Rounded.TButton")
            button.pack(side="left", padx=(0, 6))
            ToolTip(button, tip)

        shortcuts_var = tk.BooleanVar(value=bool(self.game_shortcuts))
        shortcuts_check = self.themed_check(
            body, "A Start Menu shortcut for each game", shortcuts_var,
            surface="dialog", anchor="w", padx=12, pady=(2, 0))
        ToolTip(shortcuts_check, "Besides the shortcut to the disc menu, one per game, so players can start "
                                 "a game straight from the Start Menu. Only for two or more games.")

        def save_and_close():
            apply_text()
            games = []
            for item in tree.get_children():
                if row_state.get(item):
                    _include, name, exe, about = tree.item(item, "values")
                    game = {"name": name, "exe": exe}
                    if row_icon.get(item):
                        game["icon"] = row_icon[item]
                    if about:
                        game["blurb"] = about
                    games.append(game)
            self.game_executables = games
            self.game_shortcuts = bool(shortcuts_var.get())
            self.refresh_game_exes_summary()
            if games:
                self.update_status(f"🎮 Games on Disc: {len(games)} on the menu")
            else:
                self.update_status("🎮 Games on Disc: one game, found by Rialto")
            dialog.destroy()

        def clear_and_close():
            self.game_executables = []
            self.refresh_game_exes_summary()
            self.update_status("🎮 Games on Disc: one game, found by Rialto")
            dialog.destroy()

        ttk.Button(button_row, text="Save", command=save_and_close, style="Primary.TButton").pack(side="right", padx=4)
        auto_button = ttk.Button(button_row, text="Let Rialto Find It", command=clear_and_close, style="Rounded.TButton")
        auto_button.pack(side="right", padx=4)
        ToolTip(auto_button, "Unticks every game and closes, so Rialto finds the one game by itself, "
                             "as on a normal single-game disc.")
        ttk.Button(button_row, text="Cancel", command=dialog.destroy, style="Rounded.TButton").pack(side="right", padx=4)
        self.fit_dialog_to_screen(dialog, 820)

    def stage_placed_files(self, output_path):
        """Copy each file or folder to place on the PC into ..\\.rialto-placed\\<n>\\.

        Written fresh every build, with a manifest the installer script reads,
        so an earlier build's files never ride along. A source that is gone
        stops nothing: it is reported and left out.
        """
        staging = placed_files_root(output_path)
        shutil.rmtree(staging, ignore_errors=True)
        rows = [r for r in getattr(self, "placed_files", []) if isinstance(r, dict)]
        manifest = []
        game = getattr(self, "current_game_path", "") or ""
        base = os.path.realpath(game) if game else ""
        for number, row in enumerate(rows, start=1):
            source = str(row.get("source") or "")
            target = os.path.join(staging, str(number))
            problem = placed_row_problem(row, game)
            if problem:
                self.update_status(f"⚠️ Files to place: {source} left out, because {problem}")
                continue
            outside_app = row.get("place") != "The install folder"

            def skip(folder, names, outside_app=outside_app):
                # Inside a folder: no link or junction is followed out of the game
                # folder, and outside {app} no program, script or shortcut goes.
                skipped = []
                for entry in names:
                    full = os.path.join(folder, entry)
                    real = os.path.realpath(full)
                    try:
                        escapes = os.path.commonpath([real, base]) != base
                    except ValueError:
                        escapes = True
                    if (os.path.islink(full) or escapes
                            or (outside_app and os.path.isfile(full) and placed_file_refused(entry))):
                        skipped.append(entry)
                        self.update_status(f"⚠️ Files to place: {full} left out")
                return skipped
            try:
                if os.path.isdir(source):
                    shutil.copytree(source, target, ignore=skip)
                    name = ""
                elif os.path.isfile(source):
                    os.makedirs(target, exist_ok=True)
                    name = os.path.basename(source)
                    shutil.copy2(source, os.path.join(target, name))
                else:
                    self.update_status(f"⚠️ Files to place: not found, left out: {source}")
                    continue
            except OSError as e:
                self.update_status(f"⚠️ Files to place: could not copy {source}: {e}")
                continue
            manifest.append({"n": number, "name": name, "place": row.get("place"),
                             "subfolder": row.get("subfolder", ""),
                             "keep": bool(row.get("keep", True)), "remove": bool(row.get("remove", False))})
            self.update_status(f"📁 Will place on the player's PC: {source} to {row.get('place')}"
                               + (f"\\{placed_subfolder(row.get('subfolder'))}" if row.get("subfolder") else ""))
        # Always written, empty or not, so a manifest an earlier build left
        # behind is never read again.
        os.makedirs(staging, exist_ok=True)
        with open(os.path.join(staging, "placed.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        if manifest:
            self.update_status(f"✅ Staged {len(manifest)} item(s) to place on the player's PC")
        return manifest

    def configure_placed_files(self):
        """Files to Place on the PC (1.5.1, B10): its own window, opened from Disc Extras and the Disc menu.

        For a game that needs files it would make on its first run, like a
        mod's config or a pre-seeded save: rows of "this file or folder" to
        "this place on the player's PC". Copying only, no commands.
        """
        theme = self.current_theme()
        dialog, body = self.themed_dialog(
            "Files to Place on the PC",
            "Saves, settings or a mod's first-run files, copied where the game looks for them",
            width=800, height=560)
        button_row = tk.Frame(body, bg=theme["bg"])
        button_row.pack(side="bottom", fill="x", padx=12, pady=(4, 12))

        tk.Label(body, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w", font=("Segoe UI", 10),
                 text=("Add a file or a folder, then pick where the installer copies it on the player's PC.\n"
                       "A file already there stays as it is unless you untick Keep existing, so saves are safe.\n"
                       "Placed files stay after an uninstall unless you tick Remove on uninstall.")
                 ).pack(fill="x", padx=12, pady=(10, 6))

        self.style_treeview(theme)
        tree = ttk.Treeview(body, columns=("source", "dest", "keep", "remove"), show="headings",
                            height=8, style="Rialto.Treeview")
        for column, text, width in (("source", "From your PC", 270), ("dest", "To the player's PC", 250),
                                    ("keep", "Keep existing", 90), ("remove", "Remove on uninstall", 130)):
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="center" if column in ("keep", "remove") else "w")
        tree.pack(fill="both", expand=True, padx=12, pady=4)
        ToolTip(tree, "Each row is a file or folder from your game and where the installer copies it. "
                      "Select a row to change it below, then click Apply.")

        rows = {}

        def shown(row):
            dest = row["place"] + ("\\" + row["subfolder"] if row.get("subfolder") else "")
            return (row["source"], dest, "✔" if row.get("keep", True) else "", "✔" if row.get("remove") else "")

        def add(row):
            item = tree.insert("", "end", values=shown(row))
            rows[item] = row
            return item

        for row in self.placed_files:
            if isinstance(row, dict) and row.get("source"):
                add({"source": row["source"], "place": row.get("place", "Documents"),
                     "subfolder": row.get("subfolder", ""), "keep": bool(row.get("keep", True)),
                     "remove": bool(row.get("remove", False))})

        edit = tk.Frame(body, bg=theme["bg"])
        edit.pack(fill="x", padx=12, pady=4)
        tk.Label(edit, text="Place:", bg=theme["bg"], fg=theme["fg"]).pack(side="left")
        place_var = tk.StringVar(value="Documents")
        place_box = ttk.Combobox(edit, textvariable=place_var, state="readonly", width=18,
                                 values=[label for label, _const in PLACED_FILE_PLACES])
        place_box.pack(side="left", padx=6)
        ToolTip(place_box, "Where on the player's PC the installer copies the selected file or folder. "
                           "Click Apply to keep it.")
        tk.Label(edit, text="Sub-folder:", bg=theme["bg"], fg=theme["fg"]).pack(side="left")
        sub_var = tk.StringVar()
        sub_entry = ttk.Entry(edit, textvariable=sub_var, width=24)
        sub_entry.pack(side="left", padx=6)
        ToolTip(sub_entry, "Typed as the game expects it, such as MyStudio\\MyGame or My Games\\Rocket Pals. "
                           "Created on the player's PC if it is not there.")
        keep_var = tk.BooleanVar(value=True)
        remove_var = tk.BooleanVar(value=False)
        keep_check = self.themed_check(edit, "Keep existing", keep_var, surface="dialog", side="left", padx=(6, 0))
        ToolTip(keep_check, "Never replace a file that is already on the player's PC, such as a save.")
        remove_check = self.themed_check(edit, "Remove on uninstall", remove_var, surface="dialog", side="left", padx=(6, 0))
        ToolTip(remove_check, "Delete these files when the game is uninstalled. Leave it off for saves.")

        def selected():
            item = tree.focus()
            return item if item in rows else None

        def load(event=None):
            item = selected()
            if item:
                row = rows[item]
                place_var.set(row["place"])
                sub_var.set(row.get("subfolder", ""))
                keep_var.set(row.get("keep", True))
                remove_var.set(row.get("remove", False))

        def apply():
            item = selected()
            if not item:
                return
            row = rows[item]
            row.update(place=place_var.get(), subfolder=placed_subfolder(sub_var.get()),
                       keep=bool(keep_var.get()), remove=bool(remove_var.get()))
            sub_var.set(row["subfolder"])
            tree.item(item, values=shown(row))

        tree.bind("<<TreeviewSelect>>", load)
        apply_button = ttk.Button(edit, text="Apply", command=apply, style="Rounded.TButton")
        apply_button.pack(side="left", padx=6)
        ToolTip(apply_button, "Keeps the Place, Sub-folder and tick boxes set here for the selected row.")

        tools = tk.Frame(body, bg=theme["bg"])
        tools.pack(fill="x", padx=12, pady=4)

        def add_path(path):
            if not path:
                return
            row = {"source": os.path.normpath(path), "place": place_var.get(),
                   "subfolder": placed_subfolder(sub_var.get()), "keep": bool(keep_var.get()),
                   "remove": bool(remove_var.get())}
            problem = placed_row_problem(row, self.current_game_path or "")
            if problem:
                self.show_centered_popup(
                    "This cannot be placed",
                    f"{row['source']} cannot be placed, because {problem}.\n\nPut the files in a folder "
                    "inside your game folder, and keep programs, scripts and shortcuts for the install folder.")
                return
            item = add(row)
            tree.focus(item)
            tree.selection_set(item)

        def remove_row():
            item = selected()
            if item:
                tree.delete(item)
                rows.pop(item, None)

        for text, command, tip in (
                ("Add a File…", lambda: add_path(filedialog.askopenfilename(
                    parent=dialog, title="Pick a file to place on the PC", initialdir=self.current_game_path or INPUT_DIR)),
                 "Pick one file from inside your game folder. It is added with the Place and tick boxes set above."),
                ("Add a Folder…", lambda: add_path(filedialog.askdirectory(
                    parent=dialog, title="Pick a folder to place on the PC", initialdir=self.current_game_path or INPUT_DIR)),
                 "Pick a folder from inside your game folder. Everything in it is placed, with the Place and "
                 "tick boxes set above."),
                ("Remove from List", remove_row,
                 "Takes the selected row off this list. Nothing is deleted from your PC.")):
            button = ttk.Button(tools, text=text, command=command, style="Rounded.TButton")
            button.pack(side="left", padx=(0, 6))
            ToolTip(button, tip)
        tk.Label(tools, bg=theme["bg"], fg=theme["disabled_fg"], font=("Segoe UI", 9),
                 text="From inside your game folder. A folder goes with everything in it.").pack(side="left", padx=6)

        def save_and_close():
            apply()
            self.placed_files = [dict(rows[item]) for item in tree.get_children() if item in rows]
            self.update_status(f"📁 Files to place on the PC: {len(self.placed_files)}")
            dialog.destroy()

        ttk.Button(button_row, text="Save", command=save_and_close, style="Primary.TButton").pack(side="right", padx=4)
        ttk.Button(button_row, text="Cancel", command=dialog.destroy, style="Rounded.TButton").pack(side="right", padx=4)
        self.fit_dialog_to_screen(dialog, 800)
        # Disc Extras opens this over itself and takes its grab back when it closes.
        return dialog

    # === Rialto 1.5.1: the Build Queue (B1) ===

    def batch_answer(self, title, message, kind):
        """A popup during a Build Queue run: logged, and answered as the queue was set (B1).

        The whole popup goes in the log, its lines joined (1.5.1, end-to-end runs): a pressed disc's
        "Sign Final Build is off" warning sits after the first line, and was lost.
        """
        first = " ".join(line.strip() for line in message.splitlines() if line.strip())
        if kind == "yesno":
            answer = title == "Something is missing" and bool(self._batch.get("skip_missing", True))
            self.update_status(f"📋 {title}: {first} ({'yes' if answer else 'no'}, as the queue was set)")
            return answer
        self.update_status(f"📋 {title}: {first}")
        return True

    def queue_row_result(self, name, installers_only=False):
        """What a finished row made, for the summary: each image and its size, or where the installer is."""
        output = os.path.join(OUTPUT_DIR, name)
        if installers_only:
            return "installer and disc files in output\\%s" % name
        # The images the build made (create_iso's images_made), never a half-written one lying in the folder.
        made = getattr(self, "images_made", None)
        images = sorted(p for p in made if os.path.isfile(p)) if made is not None \
            else sorted(glob.glob(os.path.join(output, "*.iso")))
        if not images:
            return "no disc image was made"
        return ", ".join("%s (%.2f GB)" % (os.path.basename(i), os.path.getsize(i) / 1e9) for i in images)

    def run_build_queue(self, rows, installers_only=False, skip_missing=True, on_row=None, should_stop=None):
        """Build every ticked row, one after another (1.5.1, B1).

        The real build, not a copy of it: each row's game folder is set and its
        profile put on the form the way Load Profile does it, then the normal
        build runs. Its popups become log lines, answered as the queue was set;
        the signing pause is never offered. A failed row is marked with its
        reason and the queue moves on. The author's own form comes back after.
        Returns [(row, True / False / None for not started, detail)].
        """
        results = []
        snapshot = self.current_profile_data()
        snapshot_game = self.current_game_path
        snapshot_auto_copyright = getattr(self, "_auto_copyright", None)
        self._batch = {"installers_only": installers_only, "skip_missing": skip_missing, "lines": []}
        self._queue_running = True
        taken = {}

        def record(row, ok, detail):
            results.append((row, ok, detail))
            if on_row:
                on_row(row, ok, detail)

        try:
            # The tools (1.5.1, B12.2), asked once for the run, not once a row: with no installer compiler,
            # or no disc image tool when the queue makes discs, no row can build. Said once, then each row.
            missing = missing_tool_refusals(False, not installers_only)
            if missing:
                for line in missing:
                    self.update_status("❌ Build Queue: " + line)
                reason = "not built: " + "; ".join(line.split(":")[0].lower() for line in missing) + " (see the log)"
                for row in rows:
                    if row.get("run", True):
                        record(row, False, reason)
                return results
            for number, row in enumerate(rows, start=1):
                if not row.get("run", True):
                    continue
                if should_stop and should_stop():
                    record(row, None, "not started: the queue was stopped")
                    continue
                folder = str(row.get("folder") or "")
                name = os.path.basename(os.path.normpath(folder)) if folder else ""
                if any(str(v).startswith(("\\\\", "//")) for v in (row.get("profile") or "", folder)):
                    # A shared queue naming a network share would hand the
                    # author's Windows sign-in to that server (security review).
                    record(row, False, "a row on a network share is not built; copy it to this PC")
                    continue
                if not os.path.isfile(str(row.get("profile") or "")):
                    record(row, False, "the profile file is not there any more")
                    continue
                if not os.path.isdir(folder):
                    record(row, False, "the game folder is not there any more")
                    continue
                if name.lower() in taken:
                    record(row, False, "its game folder has the same name as row %d's, and both would build "
                                       "into output\\%s" % (taken[name.lower()], name))
                    continue
                taken[name.lower()] = number
                if on_row:
                    on_row(row, "building", "")
                self._batch["lines"] = []
                self.update_status(f"📋 Build Queue, row {number}: {os.path.basename(row['profile'])} with {folder}")
                self.current_game_path = folder
                if hasattr(self, "game_path_var"):
                    self.game_path_var.set(folder)
                built = self.apply_profile_file(row["profile"], remember=False) and self.run_build_process()
                if built:
                    record(row, True, self.queue_row_result(name, installers_only))
                else:
                    reasons = [line for line in self._batch["lines"] if line.startswith(("❌", "📋 Preflight Check Failed"))]
                    record(row, False, reasons[-1].lstrip("❌📋 ").strip() if reasons else "the build stopped")
                self.keep_window_alive()
        finally:
            self._batch = None
            self._queue_running = False
            self.restore_form(snapshot, snapshot_game)
            if snapshot_auto_copyright:
                self._auto_copyright = True
                try:
                    self._regenerate_copyright()
                except (tk.TclError, AttributeError):
                    pass
            self.close_if_asked()  # after the author's own form is back, so the session saves it
        return results

    def restore_form(self, profile_data, game_path):
        """Put the author's own form back after a queue (B1)."""
        try:
            handle, path = tempfile.mkstemp(suffix=".json", prefix="rialto_form_")
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                json.dump(profile_data, f)
            self.current_game_path = game_path
            if hasattr(self, "game_path_var"):
                self.game_path_var.set(game_path or "")
            self.apply_profile_file(path, remember=False)
            os.remove(path)
        except (OSError, tk.TclError):
            pass

    def queue_summary(self, results):
        """The end-of-queue summary: one line per row."""
        made = sum(1 for _row, ok, _detail in results if ok)
        lines = ["Build Queue: %d of %d made." % (made, len(results))]
        for row, ok, detail in results:
            title = row.get("title") or os.path.basename(str(row.get("profile") or ""))
            lines.append("%s %s: %s" % ({True: "✅", False: "❌", None: "⏭️"}[ok], title, detail))
        return lines

    def configure_build_queue(self):
        """The Build Queue (1.5.1, B1): many games, many discs, one run. Its own window, opened from Step 1 (beside Browse) and the Disc menu."""
        theme = self.current_theme()
        dialog, body = self.themed_dialog(
            "Build Queue", "Queue up your games and get every disc in one run", width=860, height=560)
        button_row = tk.Frame(body, bg=theme["bg"])
        button_row.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        tk.Label(body, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w", font=("Segoe UI", 10),
                 text=("Add a saved profile and the game folder it builds. Rialto builds each ticked row in turn, "
                       "exactly as\nBUILD GAME INSTALLER would, and tells you at the end what it made. Double-click a "
                       "row to tick or untick it.")).pack(fill="x", padx=12, pady=(10, 6))

        self.style_treeview(theme)
        tree = ttk.Treeview(body, columns=("run", "title", "folder", "media", "status"), show="headings",
                            height=9, style="Rialto.Treeview")
        # Target Media wide enough for "Mini DVD 1.4 GB (8 cm)" (1.5.1, minis),
        # taken from the folder, which is cut short whatever its width.
        for column, text, width in (("run", "Build?", 60), ("title", "Game", 160), ("folder", "Game folder", 220),
                                    ("media", "Target Media", 160), ("status", "Status", 220)):
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="center" if column == "run" else "w")
        tree.pack(fill="both", expand=True, padx=12, pady=4)
        ToolTip(tree, "Each row is one disc: a saved profile and the game folder it builds. Double-click a row, "
                      "or select it and press Space, to tick or untick it.")
        rows = {}

        def describe(profile):
            if str(profile).startswith(("\\\\", "//")):
                return os.path.basename(str(profile)), "?"  # never opened: a network share
            try:
                with open(profile, encoding="utf-8") as f:
                    data = sanitize_profile_data(json.load(f))
                return str(data.get("Title") or os.path.basename(profile)), str(data.get("TargetMedia") or "Auto (single disc)")
            except (OSError, ValueError):
                return os.path.basename(profile), "?"

        def shown(row):
            return ("✔" if row.get("run", True) else "", row["title"], row["folder"], row["media"], row.get("status", "Waiting"))

        def add(row):
            row.setdefault("run", True)
            row["title"], row["media"] = describe(row["profile"])
            item = tree.insert("", "end", values=shown(row))
            rows[item] = row
            return item

        def refresh(item):
            if tree.winfo_exists():
                tree.item(item, values=shown(rows[item]))

        def selected():
            item = tree.focus()
            return item if item in rows else None

        def add_profile():
            profile = filedialog.askopenfilename(parent=dialog, title="Pick a saved profile",
                                                 initialdir=TEMPLATES_DIR, filetypes=[("Rialto profiles", "*.json")])
            if not profile:
                return
            folder = filedialog.askdirectory(parent=dialog, title="Pick the game folder this profile builds",
                                             initialdir=INPUT_DIR)
            if folder:
                add({"profile": os.path.normpath(profile), "folder": os.path.normpath(folder)})

        def change_folder():
            item = selected()
            if item:
                folder = filedialog.askdirectory(parent=dialog, title="Pick the game folder this profile builds",
                                                 initialdir=rows[item]["folder"] or INPUT_DIR)
                if folder:
                    rows[item]["folder"] = os.path.normpath(folder)
                    refresh(item)

        def toggle(event=None):
            item = selected()
            if item:
                rows[item]["run"] = not rows[item].get("run", True)
                refresh(item)

        def remove():
            item = selected()
            if item:
                tree.delete(item)
                rows.pop(item, None)

        def move(step):
            item = selected()
            if item:
                tree.move(item, "", max(0, tree.index(item) + step))

        tree.bind("<Double-1>", toggle)
        tree.bind("<space>", toggle)

        tools = tk.Frame(body, bg=theme["bg"])
        tools.pack(fill="x", padx=12, pady=4)
        editing = []
        for text, command, tip in (
                ("Add a Profile…", add_profile,
                 "Pick a saved profile, then the game folder it builds. Each pair is one row, one disc."),
                ("Change Game Folder…", change_folder, "Point the selected row at a different game folder."),
                ("Remove", remove, "Takes the selected row out of the queue. The profile file stays where it is."),
                ("Move Up", lambda: move(-1), "The queue builds from the top down."),
                ("Move Down", lambda: move(1), "The queue builds from the top down.")):
            button = ttk.Button(tools, text=text, command=command, style="Rounded.TButton")
            button.pack(side="left", padx=(0, 6))
            ToolTip(button, tip)
            editing.append(button)

        options = tk.Frame(body, bg=theme["bg"])
        options.pack(fill="x", padx=12, pady=(2, 0))
        installers_only = tk.BooleanVar(value=False)
        skip_missing = tk.BooleanVar(value=True)
        only_check = self.themed_check(options, "Installers only, no disc images", installers_only,
                                       surface="dialog", side="left", padx=(0, 18))
        ToolTip(only_check, "Stops each build once setup.exe is made, leaving the disc's files in the output "
                            "folder. Quicker when you only need the installers.")
        skip_check = self.themed_check(options, "If an extra folder is missing, build without it", skip_missing,
                                       surface="dialog", side="left")
        ToolTip(skip_check, "Unticked, a row whose bonus, mod or Mac and Linux folder cannot be found fails "
                            "instead, and the queue moves on. Signing follows Sign Final Build: with signing "
                            "set up every disc signs itself, and the build never pauses to sign by hand.")

        def queue_rows():
            return [rows[item] for item in tree.get_children() if item in rows]

        def save_queue():
            path = filedialog.asksaveasfilename(parent=dialog, title="Save this queue", initialdir=TEMPLATES_DIR,
                                                initialfile="queue_.json", defaultextension=".json",
                                                filetypes=[("Build queues", "queue_*.json"), ("JSON", "*.json")])
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"rows": [{k: r[k] for k in ("profile", "folder", "run")} for r in queue_rows()],
                               "installers_only": installers_only.get(), "skip_missing": skip_missing.get()},
                              f, indent=2)
                self.update_status(f"✅ Queue saved: {os.path.basename(path)}")

        def load_queue():
            path = filedialog.askopenfilename(parent=dialog, title="Load a queue", initialdir=TEMPLATES_DIR,
                                              filetypes=[("Build queues", "queue_*.json"), ("JSON", "*.json")])
            if not path:
                return
            try:
                with open(path, encoding="utf-8") as f:
                    data = sanitize_profile_data(json.load(f))
            except (OSError, ValueError) as e:
                self.update_status(f"❌ Could not read that queue: {e}")
                return
            for item in list(rows):
                tree.delete(item)
                rows.pop(item)
            for row in data.get("rows", []) if isinstance(data, dict) else []:
                if isinstance(row, dict) and row.get("profile") and row.get("folder"):
                    add({"profile": str(row["profile"]), "folder": str(row["folder"]), "run": bool(row.get("run", True))})
            installers_only.set(bool(data.get("installers_only", False)))
            skip_missing.set(bool(data.get("skip_missing", True)))

        stop = {"asked": False}

        def on_row(row, ok, detail):
            row["status"] = {"building": "Building…", True: "Done: " + detail, False: "Failed: " + detail,
                             None: "Not started"}[ok]
            for item, candidate in rows.items():
                if candidate is row:
                    refresh(item)

        def build_all_rows():
            chosen = queue_rows()
            if not any(r.get("run", True) for r in chosen):
                self.update_status("📋 Build Queue: tick at least one row")
                return
            stop["asked"] = False
            stop["running"] = True
            for widget in editing + [build_button, save_button, load_button, close_button]:
                widget.configure(state="disabled")
            stop_button.configure(state="normal")
            for item in rows:
                rows[item]["status"] = "Waiting" if rows[item].get("run", True) else "Skipped"
                refresh(item)
            try:
                results = self.run_build_queue(chosen, installers_only.get(), skip_missing.get(),
                                               on_row=on_row, should_stop=lambda: stop["asked"])
            except RuntimeError:
                stop["running"] = False
                return  # Rialto was closed during the queue
            stop["running"] = False
            summary = self.queue_summary(results)
            for line in summary:
                self.update_status(line)
            self.play_completion_jingle()
            try:
                for widget in editing + [build_button, save_button, load_button, close_button]:
                    widget.configure(state="normal")
                stop_button.configure(state="disabled")
                self.show_centered_popup("Build Queue", "\n".join(summary))
            except tk.TclError:
                pass

        def ask_stop():
            stop["asked"] = True
            stop_button.configure(state="disabled")
            self.update_status("📋 Build Queue: stopping after this one")

        def close_window():
            # The window's own X while a queue runs would leave the queue with
            # nothing to report to: it stops after the disc in progress instead.
            if stop.get("running"):
                if not stop["asked"]:
                    ask_stop()
                return
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_window)
        close_button = ttk.Button(button_row, text="Close", command=dialog.destroy, style="Rounded.TButton")
        close_button.pack(side="right", padx=4)
        build_button = ttk.Button(button_row, text="Build All", command=build_all_rows, style="Primary.TButton")
        build_button.pack(side="right", padx=4)
        stop_button = ttk.Button(button_row, text="Stop After This One", command=ask_stop,
                                 style="Rounded.TButton", state="disabled")
        stop_button.pack(side="right", padx=4)
        save_button = ttk.Button(button_row, text="Save Queue…", command=save_queue, style="Rounded.TButton")
        save_button.pack(side="left", padx=4)
        load_button = ttk.Button(button_row, text="Load Queue…", command=load_queue, style="Rounded.TButton")
        load_button.pack(side="left", padx=4)
        ToolTip(build_button, "Builds every ticked row, one after another, and lists what each one made at the end.")
        ToolTip(stop_button, "Finishes the disc being built now and leaves the rest of the queue unbuilt.")
        ToolTip(save_button, "Saves this list of rows to a file, to build the same set again later.")
        ToolTip(load_button, "Adds the rows of a queue you saved earlier.")
        self.fit_dialog_to_screen(dialog, 860)

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
        """Everything a disc can carry beyond the game: bonus, mods, Steam, files for the PC, Mac, Linux."""
        theme = self.current_theme()
        # Two columns, sized to what they hold (1.5.1, B11): one column of five sections ran off the bottom of a
        # 1080-line screen, and the lowest controls could not be reached. Never taller than the work area less
        # its title bar (B13.4), and no scrolling. On a 720-line screen that leaves 640 lines and it asked for
        # 652, so 16 came out of the padding: 6 round Done, 4 round the lead line, 2 above each section's rule.
        dialog, body = self.themed_dialog(
            "Disc Extras",
            "Everything the disc can carry besides the game itself",
            width=self.DISC_EXTRAS_WIDTH, height=600)

        # Packed first, against the bottom, so Done keeps its space no matter
        # how tall the sections below turn out to be.
        button_row = tk.Frame(body, bg=theme["bg"])
        button_row.pack(side="bottom", fill="x", padx=14, pady=(8, 10))
        ttk.Button(button_row, text="Done", command=dialog.destroy,
                   style="Primary.TButton").pack(side="right")

        # Files to Place on the PC (his word, 19 Oct 2026: it was only in the Disc menu, and GitHub #3's feature
        # could not be found). On the Done row, which costs no height: this window is already as tall as a
        # 672-line screen allows. Its own window still.
        placed_btn = ttk.Button(button_row, text="Files to Place on the PC\u2026", style="Rounded.TButton",
                                command=lambda: open_placed_files())
        placed_btn.pack(side="left")
        ToolTip(placed_btn, "Saves, settings or a mod's first-run files from your game folder, and where "
                            "the installer copies each one on the player's PC, such as Documents or Saved "
                            "Games. Copying only: nothing runs.")
        placed_note = tk.Label(button_row, bg=theme["bg"], fg=theme["disabled_fg"], anchor="w",
                               font=("Segoe UI", 9))
        placed_note.pack(side="left", padx=8)

        def refresh_placed_note():
            count = len(getattr(self, "placed_files", None) or [])
            placed_note.configure(text="No files for the player's PC yet." if not count else
                                  "1 file or folder for the player's PC." if count == 1 else
                                  "%d files or folders for the player's PC." % count)

        refresh_placed_note()

        def open_placed_files():
            child = self.configure_placed_files()
            if child is None:
                return

            def back(event):
                # Each window takes the grab when it opens and nothing hands it back, so Disc Extras
                # takes it again here, with the count brought up to date.
                if event.widget is child:
                    try:
                        refresh_placed_note()
                        dialog.grab_set()
                    except tk.TclError:
                        pass  # Disc Extras was closed first

            child.bind("<Destroy>", back, add="+")

        tk.Label(body, bg=theme["bg"], fg=theme["fg"], justify="left", anchor="w",
                 font=("Segoe UI", 10), wraplength=620,
                 text=("All of this is optional. Leave it alone and your disc still builds "
                       "exactly as it would have.")).pack(fill="x", padx=14, pady=(10, 4))

        columns = tk.Frame(body, bg=theme["bg"])
        columns.pack(fill="both", expand=True)
        left = tk.Frame(columns, bg=theme["bg"])
        left.pack(side="left", fill="both", expand=True, anchor="n")
        tk.Frame(columns, bg=theme["button_bg"], width=1).pack(side="left", fill="y", pady=10)
        right = tk.Frame(columns, bg=theme["bg"])
        right.pack(side="left", fill="both", expand=True, anchor="n")
        col = left  # Bonus, Mods and Steam on the left; Compatibility, Mac and Linux on the right (balanced for 1366 x 768)

        def section(title):
            tk.Frame(col, bg=theme["button_bg"], height=1).pack(fill="x", padx=14, pady=(8, 0))
            tk.Label(col, text=title, bg=theme["bg"], fg=theme["fg"], anchor="w",
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
        tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=520,
                 text=("Soundtracks, art, wallpapers, the design doc, anything at all. It gets a "
                       "BONUS button on the disc menu that opens the folder.")
                 ).pack(fill="x", padx=14, pady=(0, 4))

        bonus_row = path_row(col, "Bonus folder:", self.bonus_folder_var,
                             "The folder whose contents become the disc's bonus material. "
                             "Leave it empty and Rialto uses a bonus folder inside your game "
                             "folder if there is one.",
                             pick_dir(self.bonus_folder_var, "Pick your bonus content folder"))

        bonus_note = tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                              anchor="w", font=("Segoe UI", 9), wraplength=520)
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

        bonus_buttons = tk.Frame(col, bg=theme["bg"])
        bonus_buttons.pack(fill="x", padx=14, pady=(6, 0))
        create_btn = self.icon_button(bonus_buttons, "gift", "Create Bonus Folder",
                                      create_bonus_folder, side="left")
        ToolTip(create_btn, "Makes a bonus folder inside your game folder and opens it in Explorer. "
                            "Drop anything in there; whatever is inside ends up on the disc.")
        refresh_bonus_note()

        # --- Mods ---
        section("Mods")
        mods_check = self.themed_check(
            col, "Add a MODS button to the disc menu", self.mod_launcher_var,
            command=self.save_signing_settings, anchor="w", padx=14, pady=2)
        ToolTip(mods_check, "Puts your mods folder on the disc and adds a MODS button to the menu "
                            "that runs the tool inside it. Works from the disc and after installing.")
        tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=520,
                 text=("Point at the folder holding your mod manager or loader. Rialto finds the "
                       ".exe inside it on its own. Leave it empty and a folder called mods inside "
                       "your game folder is used.")
                 ).pack(fill="x", padx=14, pady=(0, 2))

        mods_row = path_row(col, "Mod folder:", self.mod_folder_var,
                            "The folder your mod tool lives in. It does not have to be called "
                            "mods. A folder already inside your game folder is used where it is, "
                            "not copied twice.",
                            pick_dir(self.mod_folder_var, "Pick the folder holding your mod tool"))

        mods_note = tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                             anchor="w", font=("Segoe UI", 9), wraplength=520)
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

        mods_buttons = tk.Frame(col, bg=theme["bg"])
        mods_buttons.pack(fill="x", padx=14, pady=(4, 0))
        mods_btn = self.icon_button(mods_buttons, "mods", "Create Mods Folder",
                                    open_mods_folder, side="left")
        ToolTip(mods_btn, "Makes a mods folder inside your game folder and opens it in Explorer.")

        # --- Compatibility mode ---
        col = right
        section("Compatibility mode")
        compat_check = self.themed_check(
            col, "Add a compatibility button to the disc menu", self.compat_mode_var,
            anchor="w", padx=14, pady=2)
        ToolTip(compat_check, "Puts a second play button on the menu that starts your game with a "
                              "launch argument already set, so a player on older hardware does not "
                              "have to type one.")
        tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=520,
                 text=("For a game that can fall back to older graphics (OpenGL instead of Vulkan, "
                       "windowed instead of fullscreen), if it already reads a launch argument.")
                 ).pack(fill="x", padx=14, pady=(0, 2))

        compat_row = tk.Frame(col, bg=theme["bg"])
        compat_row.pack(fill="x", padx=14, pady=3)
        tk.Label(compat_row, text="Launch argument:", bg=theme["bg"], fg=theme["fg"],
                 width=16, anchor="w").pack(side="left")
        compat_entry = ttk.Entry(compat_row, textvariable=self.compat_args_var)
        compat_entry.pack(side="left", fill="x", expand=True)
        ToolTip(compat_entry, "Exactly what you would type after the .exe, such as -opengl. Spaces "
                              "separate two arguments; put quotes around one that contains a space.")

        hint_row = tk.Frame(col, bg=theme["bg"])
        hint_row.pack(fill="x", padx=14, pady=3)
        tk.Label(hint_row, text="What it does:", bg=theme["bg"], fg=theme["fg"],
                 width=16, anchor="w").pack(side="left")
        hint_entry = ttk.Entry(hint_row, textvariable=self.compat_hint_var)
        hint_entry.pack(side="left", fill="x", expand=True)
        ToolTip(hint_entry, "One sentence, shown when a player hovers over the button. "
                            "Say what changes, in plain words: \"Runs the game on OpenGL "
                            "instead of Vulkan, for older graphics cards.\" Leave it empty "
                            "and the menu explains it in general terms, in the player's language.")

        compat_note = tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                               anchor="w", font=("Segoe UI", 9), wraplength=520)
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
        col = left
        section("Steam")
        steam_check = self.themed_check(
            col, "Show an Add to Steam button after install", self.steam_button_var,
            anchor="w", padx=14, pady=2)
        ToolTip(steam_check, "After an install from your disc, the menu offers one click to add the "
                             "game to the player's Steam library as a non-Steam game. Steam needs to be "
                             "closed first, and the menu shows how.")
        tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=520,
                 text=("Nothing is uploaded or sold through Steam. The button only adds a shortcut to "
                       "the player's own Steam library.")
                 ).pack(fill="x", padx=14, pady=(0, 2))

        # --- Mac and Linux ---
        # The explainer sits above the boxes here, not below them, because the
        # thing worth knowing is what Rialto does to a build folder - and an
        # author who reads that first stops hunting for a .dmg they do not need
        # to make.
        col = right
        section("Mac and Linux on the same disc (only if you built them)")
        tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left", anchor="w",
                 font=("Segoe UI", 9), wraplength=520,
                 text=("Point at a plain build folder, the one you would have zipped up yourself, "
                       "and Rialto packs it so the game comes off the disc ready to run. No "
                       "Terminal, nothing to type. The disc's README spells out the real steps for "
                       "all three: run setup.exe, or open the Mac or Linux folder and what to do once "
                       "you are in it, so nobody has to open a second file to find out which buttons "
                       "to press.")
                 ).pack(fill="x", padx=14, pady=(0, 4))

        unix_notes = {}
        for unix_var, unix_label, unix_tip in (
                (self.mac_build_var, "Mac",
                 "Your game's Mac build. A plain folder is fine: Rialto packs it into an "
                 "archive that carries Mac file permissions, so the app opens with a "
                 "double-click. Already made a .dmg or a .zip? Point at the folder holding "
                 "it and Rialto ships it exactly as it is."),
                (self.linux_build_var, "Linux",
                 "Your game's Linux build. A plain folder is fine: Rialto packs it into an "
                 "archive that carries the executable bit, so the game runs straight out of "
                 "it with no chmod and no Terminal. Already made an .AppImage or a .tar.gz? "
                 "Point at the folder holding it and Rialto ships it exactly as it is.")):
            path_row(col, "%s build:" % unix_label, unix_var, unix_tip,
                     pick_dir(unix_var, "Pick your %s build folder" % unix_label))
            unix_note = tk.Label(col, bg=theme["bg"], fg=theme["disabled_fg"], justify="left",
                                 anchor="w", font=("Segoe UI", 9), wraplength=520)
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
                                        "run, with no Terminal for your %s players."
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

        self.fit_dialog_to_screen(dialog, self.DISC_EXTRAS_WIDTH)

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

        total, _count = self.tree_size(source, skip_ext=())
        tick = self.build_ticker(f"Packaging the {label} build", total)

        def add_filter(info):
            tick(info.size if info.isfile() else 0)
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
                    self.watched_copytree(path, dest, f"Copying the {label} build")
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
                        self.watched_copytree(path, dest, f"Copying the {label} build", dirs_exist_ok=True)
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
                if getattr(self, "_abandon_build", False):
                    raise
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

    def _fileset_disc_bytes(self, output_path, items):
        """What items take on a disc: whole sectors per file, plus one each for its record."""
        total = 0

        def add(path):
            nonlocal total
            try:
                size = os.path.getsize(path)
            except OSError:
                return
            total += (-(-size // 2048) + 1) * 2048
        for item in items:
            path = os.path.join(output_path, item)
            if os.path.isdir(path):
                for dirpath, _dirs, files in os.walk(path):
                    total += 2048
                    for f in files:
                        add(os.path.join(dirpath, f))
            else:
                add(path)
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
            copy = self.counting_copy("Copying to the USB drive", self._fileset_size(output_path, files))
            for item in files:
                src = os.path.join(output_path, item)
                target = os.path.join(dest, item)
                if os.path.isdir(src):
                    if os.path.exists(target):
                        shutil.rmtree(target)
                    shutil.copytree(src, target, copy_function=copy)
                else:
                    copy(src, target)
            hint_path = os.path.join(dest, "START HERE - double click setup.txt")
            with open(hint_path, "w", encoding="utf-8") as f:
                f.write(
                    f"Thanks for grabbing {meta.get('Title', 'this game')}!\n\n"
                    "USB sticks don't start by themselves like discs do.\n"
                    "Just double-click setup.exe and you're on your way.\n"
                )
            self.update_status(f"✅ USB export done: {len(files)} items copied to {dest}")
        except Exception as e:
            if getattr(self, "_abandon_build", False):
                raise
            self.update_status(f"❌ USB export failed: {e}")

    def _remove_partial_iso(self, iso_path):
        """Delete a disc image a failed tool left half-written, so nobody burns it.

        mkisofs writes to MKISOFS_IMAGE_PART beside it until the image is finished, so that goes too.
        """
        name = os.path.basename(iso_path)
        for path in (iso_path, os.path.join(os.path.dirname(iso_path), MKISOFS_IMAGE_PART)):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.update_status(f"🧹 Removed the unfinished {name}")
            except OSError:
                self.update_status(f"⚠️ {name} is unfinished; delete it before burning")

    def image_growth(self, iso_path, payload):
        """How far a disc image is, from its size on disk against what goes in it (B6)."""
        try:
            written = os.path.getsize(iso_path)
        except OSError:
            return None
        return (min(written / payload, 0.99), "%.1f of %.1f GB" % (written / 1e9, payload / 1e9)) if payload else None

    def _write_one_image(self, kind, tool_path, output_path, iso_path, items, disc_label, needs_udf,
                         temp_name, step, copy=None):
        """Write one disc image with one tool: (True, "") when it is made, else (False, why) (1.5.1).

        mkisofs reads the build folder where it is, through the graft points in MKISOFS_PATH_LIST, and
        writes MKISOFS_IMAGE_PART, renamed to iso_path once it is finished; oscdimg gets a copy of just these
        items in temp_name, as before. A timeout, or a tool that cannot start, is raised to the caller, which
        decides; a half-written image is the caller's to remove (_remove_partial_iso).
        """
        temp_folder = os.path.join(output_path, temp_name)
        path_list = os.path.join(output_path, MKISOFS_PATH_LIST)
        written = iso_path
        try:
            if kind == "oscdimg":
                if os.path.exists(temp_folder):
                    shutil.rmtree(temp_folder)
                os.makedirs(temp_folder)
                for item in items:
                    src = os.path.join(output_path, item)
                    dst = os.path.join(temp_folder, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, copy_function=copy or shutil.copy2)
                    elif os.path.exists(src):
                        (copy or shutil.copy2)(src, dst)
                tool = [tool_path, "-m", "-u2" if needs_udf else "-j1", f"-l{disc_label}", temp_folder, iso_path]
            else:
                folders = {item for item in items if os.path.isdir(os.path.join(output_path, item))}
                utf8 = mkisofs_reads_utf8(tool_path)
                written = os.path.join(output_path, MKISOFS_IMAGE_PART)
                if os.path.exists(written):
                    os.remove(written)
                # UTF-8 for a Cygwin or MSYS build, which is told so; any other reads the Windows code page,
                # as it read its command line before.
                with open(path_list, "w", encoding="utf-8" if utf8 else "mbcs", errors="replace",
                          newline="\n") as fh:
                    fh.write(mkisofs_path_list(items, folders))
                tool = mkisofs_command(tool_path, disc_label, needs_udf, utf8)
            payload = self._fileset_size(output_path, items)
            result = self.run_tool_watched(tool, output_path, 1800, step,
                                           watch=lambda: self.image_growth(written, payload))
            if result.returncode != 0 or not os.path.exists(written):
                error_tail = (result.stderr or result.stdout or "").strip().splitlines()
                if result.returncode == 0:
                    return False, "the tool ran but no image was written"
                return False, error_tail[-1] if error_tail else "exit code %s" % result.returncode
            if written != iso_path:
                # A scanner can hold the finished image for a moment; a few tries before the image is
                # called failed and thrown away.
                for attempt in range(10):
                    try:
                        os.replace(written, iso_path)
                        break
                    except OSError:
                        if attempt == 9:
                            raise
                        time.sleep(0.5)
            return True, ""
        finally:
            if os.path.exists(temp_folder):
                try:
                    shutil.rmtree(temp_folder)
                except OSError:
                    pass
            if os.path.exists(path_list):
                try:
                    os.remove(path_list)
                except OSError:
                    pass

    def _build_single_iso(self, output_path, iso_path, items, disc_label, needs_udf):
        """Build one ISO from a list of items. Used by multi-disc sets.

        Each tool in disc_image_tools' order until one writes it (1.5.1); mkisofs only for a plant, as in
        create_iso. create_spanned_isos keeps the tools already named in the log, so a set names its tool once.
        A tool that fails, for any reason, hands over to the next one, as in create_iso, and its half-written
        image is removed first. A timeout stops the build (a RuntimeError) with no next tool, and closing
        Rialto removes the half-written image and stops it too.
        """
        said = getattr(self, "_image_tools_said", None)
        tools = disc_image_tools(self.pressed_disc_on())
        if not tools:
            self.update_status("❌ Multi-disc sets need a disc image tool: mkisofs or oscdimg")
            return False
        for attempt, (kind, tool_path, carried) in enumerate(tools):
            words = tool_words(kind, tool_path, carried)
            if attempt:
                self.update_status("🔄 Trying the next disc image tool: " + words)
            elif said is None or words not in said:
                self.update_status("✅ Writing the disc images with " + words)
            if said is not None:
                said.add(words)
            copy = None
            if kind == "oscdimg":
                # Counted, so the window answers and the live line moves while each disc's items are copied.
                copy = self.counting_copy("Preparing " + os.path.basename(iso_path),
                                          self._fileset_size(output_path, items))
            try:
                made, why = self._write_one_image(kind, tool_path, output_path, iso_path, items, disc_label,
                                                  needs_udf, "temp_span_build", "Writing " + os.path.basename(iso_path),
                                                  copy)
            except subprocess.TimeoutExpired:
                self.update_status("❌ Disc image stopped after 30 minutes without finishing")
                self._remove_partial_iso(iso_path)
                raise RuntimeError(f"{os.path.basename(iso_path)} was not finished after 30 minutes. Check free "
                                   "disk space and that no scanner is holding the build folder, then build again")
            except Exception as e:
                self._remove_partial_iso(iso_path)
                if getattr(self, "_abandon_build", False):
                    raise  # Rialto was closed: no next tool after the window has gone
                made, why = False, str(e)
            if made:
                return True
            self.update_status(f"❌ Disc image failed: {why}")
            self._remove_partial_iso(iso_path)
        return False

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

        fit = capacity - self.SPAN_MARGIN
        # Weighed as a disc holds it: each file rounded up to whole 2,048-byte
        # sectors, and a sector more for its directory record, so a base of
        # thousands of small files cannot push Disc 1 past the media.
        base_size = self._fileset_disc_bytes(output_path, base_items)
        if base_size > fit:
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
            if current and current_size + size > fit:
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
            disc_sizes, fit, self.target_media_var.get()
        )
        for line in self.disc_overflow_warnings:
            self.update_status(line)

        self.update_status(f"📀 This build needs {len(discs)} discs. Creating the set...")
        needs_udf = self._fileset_needs_udf(output_path, all_items)
        made = 0
        self._image_tools_said = set()
        self.images_made = []
        for number, items in enumerate(discs, start=1):
            iso_path = os.path.join(output_path, f"{game_name} Disc {number}.iso")
            label = f"{disc_label[:13]} D{number}"
            self.update_status(f"🔄 Creating Disc {number} of {len(discs)}...")
            if self._build_single_iso(output_path, iso_path, items, label, needs_udf):
                self.images_made.append(iso_path)
                size_mb = os.path.getsize(iso_path) / (1024 * 1024)
                self.update_status(f"✅ Disc {number}: {os.path.basename(iso_path)} ({size_mb:.0f} MB)")
                made += 1
        if made == len(discs):
            self.update_status(f"✅ Multi-disc set complete: {made} ISOs ready to burn")
            self.refresh_windows_icon_cache()
        else:
            self.update_status(f"⚠️ Only {made} of {len(discs)} discs were created")
            if self.pressed_disc_on():
                raise RuntimeError(f"only {made} of {len(discs)} discs were made, and a plant needs the whole set")

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
            from rialto.update.fetch import FetchProblem, fetch_to_file
            try:
                fetch_to_file(INNOEXTRACT_URL, zip_path, hosts={"constexpr.org"},
                              cap=16 * 1024 * 1024, sha256=INNOEXTRACT_SHA256)
            except FetchProblem as problem:
                self.update_status(
                    "❌ innoextract: " + str(problem) + " Install it yourself from "
                    "https://constexpr.org/innoextract/ if you need GOG import.")
                return None
            with zipfile.ZipFile(zip_path) as archive:
                from rialto.trusted_signing import safe_extract_all
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
            # Paths chosen against the old game folder follow it, as Browse does.
            self.rebase_stale_paths()
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
        from rialto import msix_export
        from rialto import trusted_signing

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
        self.centre_on(dialog, 600, 330, self.root)  # over Rialto, inside the work area (it had no place before)
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
            several = self.stage_preview_games(menu_dir, temp_root)

            # Window icon lives two levels up from the launcher (the install root)
            if self.ico_path_var.get() and os.path.exists(self.ico_path_var.get()):
                try:
                    # stage_preview_games may have hard-linked a game's own game_icon.ico here: copying
                    # over the link would write into the author's file, so the link goes first.
                    icon_dest = os.path.join(temp_root, "game_icon.ico")
                    if os.path.lexists(icon_dest):
                        os.remove(icon_dest)
                    shutil.copy2(self.ico_path_var.get(), icon_dest)
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
            if several:
                self.update_status("✅ Preview launched. Click PLAY GAMES to see the Choose Your Game page; "
                                   "starting a game and UNINSTALL are switched off in a preview")
            else:
                self.update_status("✅ Preview launched - PLAY/UNINSTALL are disabled in preview mode")
        except Exception as e:
            self.update_status(f"❌ Preview failed: {e}")

    # A game's exe is copied into a preview only up to this size when it cannot
    # be hard-linked (another drive); past it the game shows no picture there.
    PREVIEW_EXE_COPY_LIMIT = 64 * 1024 * 1024
    # The disc menu's own rules for a game's picture (game_picture in MENU_TEMPLATE_SOURCE): one of these
    # types and at most 8 MB, else it shows the exe's icon instead.
    MENU_PICTURE_TYPES = (".ico", ".png", ".jpg", ".jpeg", ".bmp")
    MENU_PICTURE_LIMIT = 8 * 1024 * 1024

    def stage_preview_games(self, menu_dir, temp_root):
        """Put what the Choose Your Game page shows into a preview of a disc of several games.

        The menu takes each game's picture from inside its own install folder,
        which in a preview is temp_root: the author's image, else the icon of
        the game's exe. It refuses a path that leads out through a junction, so
        each picture, or else each exe, is staged as a real file: a hard link
        where the drive allows one, else a copy. A picture the menu would refuse
        (not a picture type, or over 8 MB) stages the exe instead, whose icon the
        menu then shows. A disc of one game stages nothing, as before. Returns
        True when the disc has several games.

        Nothing is ever written outside temp_root (security review, 1.5.1): the
        bonus and mods folders in a preview are junctions to the author's own
        folders, so a path through one of them is refused, never written into.
        Two games sharing one picture or exe stage it once.
        """
        try:
            with open(os.path.join(menu_dir, "menu_config.json"), encoding="utf-8") as f:
                games = [g for g in json.load(f).get("games") or [] if isinstance(g, dict)]
        except (OSError, ValueError, AttributeError):
            return False
        if len(games) < 2 or not self.current_game_path:
            return False
        source_root = os.path.realpath(self.current_game_path)
        preview_root = os.path.realpath(temp_root)

        def inside_game(rel):
            """(parts, real source path) for a file inside the game folder, else None."""
            parts = [p for p in rel.split("/") if p]
            if not parts or ".." in parts or os.path.isabs(rel) or parts[0].lower() == "menu":
                return None
            source = os.path.realpath(os.path.join(source_root, *parts))
            try:
                if os.path.commonpath([source_root, source]) != source_root or not os.path.isfile(source):
                    return None
            except ValueError:
                return None
            return parts, source

        no_picture, linked_out, staged = [], [], set()
        for game in games:
            icon = inside_game(str(game.get("icon") or "").replace("\\", "/").strip())
            if icon:
                try:
                    usable = (icon[0][-1].lower().endswith(self.MENU_PICTURE_TYPES)
                              and os.path.getsize(icon[1]) <= self.MENU_PICTURE_LIMIT)
                except OSError:
                    usable = False
                if not usable:
                    icon = None  # the menu falls back to the exe's icon, so the exe is what it needs
            pick = icon or inside_game(str(game.get("exe") or "").replace("\\", "/").strip())
            if not pick:
                continue
            parts, source = pick
            label = str(game.get("name") or parts[-1])
            dest = os.path.join(temp_root, *parts)
            key = os.path.normcase(os.path.normpath(dest))
            if key in staged:
                continue  # another game's picture or exe, already staged
            try:
                if os.path.commonpath([preview_root, os.path.realpath(dest)]) != preview_root:
                    linked_out.append(label)
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    os.link(source, dest)
                except OSError:
                    if icon or os.path.getsize(source) <= self.PREVIEW_EXE_COPY_LIMIT:
                        shutil.copy2(source, dest)
                    else:
                        no_picture.append(label)
                        continue
                staged.add(key)
            except (OSError, ValueError):
                no_picture.append(label)
        if no_picture:
            self.update_status("ℹ️ The preview shows no picture for %s: the exe is large and on another "
                               "drive. The finished disc shows it." % ", ".join(no_picture))
        if linked_out:
            self.update_status("ℹ️ The preview shows no picture for %s: it is in the bonus or mods folder, "
                               "which a preview only links to. The finished disc shows it." % ", ".join(linked_out))
        return True

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

            # Named for the version, like the Setup's own shortcuts: "Rialto 1.5.1".
            name = "%s %s.lnk" % (APP_NAME, __version__)

            script_lines = [
                "$ws = New-Object -ComObject WScript.Shell",
                "$desktop = [Environment]::GetFolderPath('Desktop')",
                "$new = Join-Path $desktop %s" % ps_quote(name),
                # This menu item used to name the shortcut plain "Rialto" (his word, 19 Oct 2026: the desktop
                # said Rialto, not Rialto 1.5.1). One of those pointing at this same Rialto takes the new name.
                "$old = Join-Path $desktop 'Rialto.lnk'",
                # From source the target is pythonw.exe, so the script it starts has to match too.
                ("if ((Test-Path -LiteralPath $old) -and -not (Test-Path -LiteralPath $new) -and "
                 "($ws.CreateShortcut($old).TargetPath -eq %s) -and "
                 "($ws.CreateShortcut($old).Arguments -eq %s)) { Rename-Item -LiteralPath $old -NewName %s }"
                 % (ps_quote(target), ps_quote(arguments), ps_quote(name))),
                "$s = $ws.CreateShortcut($new)",
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
                self.update_status("✅ %s %s is on your desktop" % (APP_NAME, __version__))
                self.show_centered_popup(
                    "Shortcut Created",
                    "%s %s is on your desktop. Double-click the bird to open it." % (APP_NAME, __version__))
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
        "switch to the organization path.\n"
        "5. Creating a Public Trust certificate profile once validation passes.\n"
        "6. Giving my own user the \"Artifact Signing Certificate Profile "
        "Signer\" role, and explaining why signing fails without it.\n"
        "7. Installing the Azure CLI and running az login.\n"
        "8. Finding the three values I have to type into my build tool: the "
        "region endpoint URL, the account name, and the certificate profile "
        "name. Tell me exactly where in the portal each one is.\n\n"
        "At the end, print those three values back to me as a labeled list so "
        "I can copy them across. If a step fails, help me diagnose it before we "
        "move on."
    )

    def configure_signing(self):
        """Dialog for the user's own Azure Artifact Signing account details."""
        from rialto import trusted_signing

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

        # 740 lines where the work area has them, less where it has not (1.5.1, B13.4): the page scrolls
        # inside as it always did, and Save, Check My Setup and Cancel stay above the taskbar.
        self.fit_dialog_to_screen(dialog, 640, height=740)

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
        # Room to breathe where the work area has it. On a short screen it is as tall as the work area allows,
        # which is less than this and still more than the rows hold: seven rows of long answers ask for 626
        # lines, and a 720-line screen leaves 640 under its taskbar and the title bar (B13.4).
        roomy = min(760, 300 + rows * 62)

        dialog, body = self.themed_dialog(
            "Check My Setup",
            "Everything signing needs, one line at a time",
            width=660, height=roomy)

        close_row = tk.Frame(body, bg=theme["bg"])
        close_row.pack(side="bottom", fill="x", padx=16, pady=(4, 10))
        ttk.Button(close_row, text="Close", command=dialog.destroy,
                   style="Primary.TButton").pack(side="right")

        # The verdict goes at the top, because it is the answer to the question
        # that was actually asked.
        verdict = tk.Frame(body, bg=theme["accent"] if all_ok else theme["header_bg"])
        verdict.pack(fill="x", padx=16, pady=(10, 6))
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
            row.pack(fill="x", padx=16, pady=2)

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

        # Never taller than the work area, and never shorter than what the rows hold when that fits: a found
        # tool is answered with its whole path, and long answers wrap.
        self.fit_dialog_to_screen(dialog, 660, height=roomy)
        self.root.wait_window(dialog)

    # === Documentation ===

    def doc_path(self, filename):
        """Locate a shipped doc: the one this Rialto carries, else a copy beside it.

        A frozen Rialto shows the guide inside its own bundle, so an update
        unzipped over an older folder never shows the older guide that folder
        kept. The bundle lives in a temp folder the PyInstaller bootloader
        deletes on exit, so the page is copied out to APP_ROOT/docs, over any
        older copy, before the browser is pointed at it - otherwise the page
        would vanish from under the browser the moment Rialto closed. A source
        run reads the repo's docs/ (APP_ROOT/docs, then APP_ROOT).
        """
        meipass = getattr(sys, "_MEIPASS", None)
        for bundled in ([os.path.join(meipass, "docs", filename),
                         os.path.join(meipass, filename)] if meipass else []):
            if os.path.isfile(bundled):
                target = os.path.join(APP_ROOT, "docs", filename)
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    # Never through a link put at docs\<file> (security review, 1.5.1): the page goes to
                    # a temporary file beside it and replaces the name itself, never what a link points
                    # at. A copy that is already the same is left as it is.
                    linked = os.path.islink(target) or getattr(os.path, "isjunction", lambda _p: False)(target)
                    if not linked and os.path.isfile(target) and same_file_bytes(bundled, target):
                        return target
                    handle, temp = tempfile.mkstemp(prefix=".rialto-", suffix=".tmp", dir=os.path.dirname(target))
                    try:
                        with os.fdopen(handle, "wb") as out, open(bundled, "rb") as page:
                            shutil.copyfileobj(page, out)
                        os.replace(temp, target)
                    except OSError:
                        if os.path.exists(temp):
                            os.remove(temp)
                        raise
                    return target
                except OSError:
                    return bundled  # read-only install: temp copy is better than nothing

        local = [
            os.path.join(APP_ROOT, "docs", filename),
            os.path.join(APP_ROOT, filename),
        ]
        for candidate in local:
            if os.path.isfile(candidate):
                return candidate
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
                f"You have Rialto {__version__}.\n\n"
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
                from rialto.update.check import check_for_update
                outcome = check_for_update(__version__)
            except Exception:
                pass
            finally:
                self.root.after(0, lambda: self._on_new_rialto_checked(outcome))

        threading.Thread(target=work, name="rialto-update-check", daemon=True).start()

    def _on_new_rialto_checked(self, outcome):
        self._update_check_running = False
        self.update_status("ℹ️ " + outcome.sentence)
        if outcome.release is None and getattr(outcome, "look_yourself", False):
            from rialto.update.keys import RELEASE_PAGE
            # The server answered but publishes no feed yet (1.5.1): Rialto cannot tell, so it offers the
            # releases page, where the person can look for themselves.
            if self.show_centered_popup(
                    "Check for a New Rialto",
                    f"You have Rialto {__version__}.\n\n" + outcome.sentence + "\n\n"
                    "Open the releases page in your web browser to look for yourself?",
                    kind="yesno"):
                import webbrowser
                webbrowser.open(RELEASE_PAGE)
            return
        if outcome.release is None:
            self.show_centered_popup("Check for a New Rialto", f"You have Rialto {__version__}.\n\n" + outcome.sentence)
            return
        from rialto.update.feed import browser_url
        from rialto.update.keys import RELEASE_PAGE
        # The download itself, in one click (1.5.1): the address comes out of the signed feed, and
        # only a github.com or updates.wetheindies.com one is handed to the browser. It used to
        # send the person to the release page for "Rialto.exe and menu.exe", which the page no
        # longer offers: it offers one file.
        download = browser_url(outcome.release.url)
        # An installed Rialto (its Setup left the uninstaller here) updates with the new version's Setup,
        # Rialto-X.Y.Z-Setup.exe, which sits beside the zip in the same release and keeps settings and
        # profiles as they are. The version is the signed feed's, checked as X.Y.Z when it was read.
        if download.lower().endswith(".zip") and os.path.isfile(os.path.join(APP_ROOT, "unins000.dat")):
            download = download.rsplit("/", 1)[0] + "/Rialto-%s-Setup.exe" % outcome.release.version
        name = download.rsplit("/", 1)[-1]
        installed = os.path.isfile(os.path.join(APP_ROOT, "unins000.dat"))
        if download and name.lower().endswith(".zip"):
            ask = ("Download it now? Your web browser saves " + name + ". Unzip the whole folder "
                   "somewhere new and open Rialto.exe from it.")
        elif download and name.lower().endswith(".exe") and installed:
            ask = ("Download it now? Your web browser saves " + name + ". Close Rialto and run it "
                   "to update: your settings and profiles stay as they are.")
        elif download and name.lower().endswith(".exe"):
            ask = ("Download it now? Your web browser saves " + name + ". Run it to install the new "
                   "Rialto for you; this copy and its settings stay where they are.")
        else:
            download = ""
            ask = "Open the release page in your web browser? The download is there."
        if self.show_centered_popup("Check for a New Rialto", outcome.sentence + "\n\n" + ask, kind="yesno"):
            import webbrowser
            webbrowser.open(download or browser_url(outcome.release.notes_url) or RELEASE_PAGE)

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
        """Every build step, from copying the game to the finished ISO. True when it finished."""
        if not self.current_game_path:
            self.update_status("❌ Error: Game path not selected.")
            return False

        game_name = os.path.basename(os.path.normpath(self.current_game_path))
        output_path = safe(os.path.abspath(os.path.join(OUTPUT_DIR, game_name)))
        # The build folder is output\<the game folder's name>. A game folder
        # with no name (a drive root, E:\) would make it output\ itself, and
        # the clean-up at the end, which keeps only disc images, would then
        # delete every other game's build folder (1.5.1).
        game_real = os.path.realpath(self.current_game_path)
        try:
            inside_output = os.path.commonpath([game_real, os.path.realpath(OUTPUT_DIR)]) == os.path.realpath(OUTPUT_DIR)
        except ValueError:
            inside_output = False
        if inside_output:
            # Step 0 empties the build folder: a game kept in output\ would be
            # deleted before it was copied (correctness review, 1.5.1).
            self.update_status("❌ Build failed: your game folder is inside Rialto's output folder, which each "
                               "build empties. Move the game somewhere else, such as input\\, and build again.")
            return False
        if not game_name or game_name == PLACED_FILES_DIR or os.path.dirname(output_path) != safe(OUTPUT_DIR):
            self.update_status("❌ Build failed: put the game in a folder of its own. Rialto names the build "
                               "after that folder, and a drive root has no name.")
            return False
        os.makedirs(output_path, exist_ok=True)

        # Cleared per build so a warning from an earlier one never haunts this
        # summary; create_spanned_isos refills it if a disc comes out oversized.
        self.disc_overflow_warnings = []
        self.images_made = []

        try:
            # 0. Start from an empty build folder (1.5.1). Only the last disc
            # image used to be cleared, so a build that stopped halfway left
            # its staged files behind and the next build copied over them: a
            # file deleted from the game since still rode into the installer.
            # A link inside is removed, never followed.
            if os.listdir(output_path):
                self.update_status(f"🧹 Clearing the last build of {game_name} to start fresh: "
                                   f"output\\{game_name} is emptied, disc images too")
            for stale in os.listdir(output_path):
                path = os.path.join(output_path, stale)
                try:
                    if os.path.islink(path) or getattr(os.path, "isjunction", lambda _p: False)(path):
                        os.unlink(path) if os.path.isfile(path) else os.rmdir(path)
                    elif os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except OSError as e:
                    self.update_status(f"⚠️ Could not clear {stale} from the last build: {e}")

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

            # 3.7. Files the installer places on the player's PC (1.5.1, B10)
            self.stage_placed_files(output_path)

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

            # A Build Queue set to installers only stops here (1.5.1, B1): the
            # disc's files, setup.exe among them, stay in the output folder.
            if (getattr(self, "_batch", None) or {}).get("installers_only"):
                self.log_build_event(meta, output_path, success=True)
                self.update_status(f"✅ Installers only: setup.exe and the disc's files are in {output_path}")
                return True

            # 10. Create ISO
            self.update_status("Creating ISO image...")
            self.create_iso(output_path, meta)

            # 10.1. A pressed disc: the checksum file and the master sheet (1.5.1, B5),
            # for the images this build made and no others
            if self.pressed_disc_on():
                self.write_pressing_files(output_path, meta, self.images_made)

            # 10.5. USB export (optional) - must run before cleanup deletes the disc files
            if self.usb_export_var.get() and getattr(self, "_batch", None) is not None:
                self.update_status("📋 Also export for USB is skipped in a Build Queue: it asks for a folder")
            elif self.usb_export_var.get():
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
            if getattr(self, "_batch", None) is None:
                self.play_completion_jingle()  # a Build Queue plays it once, at the end
            done_message = f"Build complete for {game_name}"
            if overflow:
                # The popup stays short, so it points at the log
                # rather than trying to hold the full per-disc breakdown.
                done_message += "\n\n⚠️ At least one disc is larger than your target media - see the status log."
            self.show_centered_popup("Done", done_message)
            return True

        except RuntimeError as e:
            # A stop Rialto chose, with its reason: one line, no traceback.
            self.update_status(f"❌ Build failed: {e}")
            self.update_status(f"   What was made so far is in {output_path}. The next build starts afresh.")
            return False
        except Exception as e:
            self.update_status(f"❌ Build failed: {e}")
            self.update_status(f"Traceback: {traceback.format_exc()}")
            self.update_status(f"   What was made so far is in {output_path}. The next build starts afresh.")
            return False
        finally:
            # The files to place on the PC were staged beside the build folder for ISCC alone, which has
            # compiled them into setup.exe or stopped (1.5.1, end-to-end runs). Made or not, they go now.
            shutil.rmtree(placed_files_root(output_path), ignore_errors=True)








    def say_missing_tools(self):
        """At start (1.5.1, B12.2): one log line when a tool Rialto needs cannot be found, installed or carried."""
        try:
            missing = missing_tool_refusals(False)
        except Exception:
            return
        if missing:
            self.update_status("⚠️ " + " ".join(missing))

    def run_preflight_check(self):
        issues = []

        # The game folder is the one Browse picked. It can live anywhere;
        # this used to insist on input\\<title without spaces>.
        game_path = getattr(self, "current_game_path", "") or ""
        background_path = self.bg_path_var.get().strip()
        icon_path = self.ico_path_var.get().strip()

        if not os.path.isdir(game_path):
            issues.append("Choose your game folder first (Browse for your game folder).")
        elif not os.path.basename(os.path.normpath(game_path)):
            issues.append("Put the game in a folder of its own: Rialto names the build after that "
                          "folder, and a drive root has no name.")
        else:
            try:
                in_output = os.path.commonpath([os.path.realpath(game_path), os.path.realpath(OUTPUT_DIR)]) \
                    == os.path.realpath(OUTPUT_DIR)
            except ValueError:
                in_output = False
            if in_output:
                issues.append("Your game folder is inside Rialto's output folder, which each build empties. "
                              "Move the game somewhere else, such as input\\.")

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

        # Files to Place on the PC (1.5.1, B10, security review): every row from
        # inside the game folder, and only data outside the install folder.
        for row in getattr(self, "placed_files", []) or []:
            if isinstance(row, dict):
                problem = placed_row_problem(row, game_path)
                if problem:
                    issues.append(f"Files to Place on the PC: {row.get('source') or '(no file)'} cannot be "
                                  f"placed, because {problem}. Fix the row in Files to Place on the PC, at the bottom of Disc Extras.")

        # The tools (1.5.1, B12.2): no installer compiler, or no disc image tool for this disc, installed
        # or carried, is said here, before anything is copied, not found out after the installer compiles.
        # A Build Queue set to installers only makes no image, so it needs no image tool.
        issues.extend(missing_tool_refusals(self.pressed_disc_on(),
                                            not (getattr(self, "_batch", None) or {}).get("installers_only")))

        # A pressed disc (1.5.1, B5): refused here, before anything is copied.
        note = ""
        if self.pressed_disc_on():
            refusal = pressed_refusal(self.target_media_var.get())
            if refusal:
                issues.append("Pressed disc: " + refusal)
            if not self.sign_final_build.get():
                note = ("\n\nSign Final Build is off. Once the plant has the image, the disc cannot be "
                        "re-signed.")

        if issues:
            self.show_centered_popup("Preflight Check Failed", "\n".join(issues))
            return False
        else:
            self.show_centered_popup("Preflight Check Passed", "All required files and metadata are present." + note)
            return True

    def pressed_disc_on(self):
        var = getattr(self, "pressed_disc_var", None)
        try:
            return bool(var is not None and var.get())
        except tk.TclError:
            return False

    def write_pressing_files(self, output_path, meta, made):
        """Chksum.md5 and the master sheet, beside the finished images (1.5.1, B5).

        Only the images in `made`, the ones this build finished (create_iso's images_made), never every
        *.iso in the folder: a half-written or left-over image must not reach a plant's sheet.
        """
        def disc_order(name):
            digits = re.findall(r"(\d+)", name)
            return (int(digits[-1]) if digits else 0, name.lower())

        images = sorted((os.path.basename(p) for p in (made or [])
                         if os.path.dirname(os.path.abspath(p)) == os.path.abspath(output_path)
                         and os.path.isfile(p)), key=disc_order)
        if not images:
            raise RuntimeError("No disc image to send to the plant")
        disc_type = PRESSED_DISC_TYPES.get(self.target_media_var.get(), "")
        discs = []
        for name in images:
            path = os.path.join(output_path, name)
            self.update_status(f"🔐 Checksumming {name} for the plant...")
            label, udf = iso_facts(path)
            tick = self.build_ticker(f"Checksumming {name}", os.path.getsize(path))
            discs.append({"file": name, "bytes": os.path.getsize(path), "md5": file_md5(path, progress=tick),
                          "label": label, "udf": udf, "type": disc_type})
        signed = {}
        try:
            from rialto import trusted_signing
            for name, path in (("setup.exe", os.path.join(output_path, "setup.exe")),
                               ("menu.exe", os.path.join(output_path, "menu", "menu.exe"))):
                answer = trusted_signing.has_valid_signature(path)
                signed[name] = {True: "yes (a signature Windows trusts)", False: "no"}.get(answer, "not checked")
        except ImportError:
            pass
        title = meta.get("Title") or meta.get("GameName") or "Game"
        with open(os.path.join(output_path, "Chksum.md5"), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(checksum_text(discs))
        sheet_name = iss_value(title, "Game", for_path=True) + " master sheet.txt"
        with open(os.path.join(output_path, sheet_name), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(master_sheet_text(title, meta.get("Developer", ""), __version__,
                                      time.strftime("%d %B %Y").lstrip("0"), discs, signed))
        self.update_status(f"📄 Wrote Chksum.md5 and {sheet_name} for the plant")
        for disc in discs:
            sectors = disc["bytes"] // SECTOR_BYTES
            if disc_type == "DVD-9" and sectors <= DVD5_SECTORS:
                self.update_status(f"ℹ️ {disc['file']} fits on one layer: a DVD-5 presses cheaper")








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
        config = {
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
        # A Start Menu shortcut for each game (1.5.1, B9): read by the installer
        # script, not the menu. Absent unless asked for on a disc of several.
        if getattr(self, "game_shortcuts", False) and len(config["games"]) > 1:
            config["start_menu_per_game"] = True
        return config

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
        """Say whether setup.exe carries a signature.

        It used to write a SECURITY_INFO.txt as well, which the clean-up then
        deleted: it never reached a player, and the log said "Added security
        documentation" about it. Gone in 1.5.1; the signature check stays.
        """
        setup_path = os.path.join(output_path, "setup.exe")

        if os.path.exists(setup_path):
            try:

                # Read the signature back rather than assuming. This line used
                # to say "Installer is unsigned" unconditionally, which meant a
                # build that had just signed setup.exe successfully finished by
                # telling the author it had not.
                try:
                    from rialto import ssl_signing
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
        
        # ISCC.exe from Inno Setup 6: PATH, then either install mode's folder, then 7's, then the one
        # Rialto carries (1.5.1). The log says which.
        iscc, carried = installer_compiler()
        problem = None
        unsigned_in_queue = False

        if iscc:
            try:
                command = [iscc, iss_path]
                if carried:
                    self.update_status("ℹ️ Building the installer with " + tool_words("iscc", iscc, True))
                elif _inno_setup_major(iscc) == 7:
                    self.update_status("ℹ️ Building the installer with Inno Setup 7 (Inno Setup 6 is not installed)")
                else:
                    self.update_status("ℹ️ Building the installer with " + tool_words("iscc", iscc, False))
                # An hour: a Blu-ray-sized game can take well over five minutes to
                # compress, and a timeout now stops the build.
                # Watched (1.5.1, B6): ISCC names each file as it starts on it
                # (seen streaming through the pipe, one line per file), so a
                # file's bytes count once ISCC has moved on to the next.
                total, files = self.tree_size(output_path)
                reached = {"bytes": 0, "files": 0, "current": 0}

                def on_line(line):
                    path = iscc_compressing_path(line)
                    if not path:
                        return None
                    reached["bytes"] += reached["current"]
                    reached["files"] += 1
                    try:
                        reached["current"] = os.path.getsize(path)
                    except OSError:
                        reached["current"] = 0
                    return (min(reached["bytes"] / total, 0.99) if total else None,
                            "{:,} of {:,} files".format(min(reached["files"], files), files))

                result = self.run_tool_watched(command, output_path, 3600, "Compressing the installer",
                                               on_line=on_line)
                
                if result.returncode == 0:
                    setup_path = os.path.join(output_path, "setup.exe")
                    if os.path.exists(setup_path):
                        self.update_status(f"Installer compiled: {os.path.basename(setup_path)}")
                        
                        # Sign setup.exe if requested (must happen here, before ISO packaging)
                        if self.sign_final_build.get():
                            signed = False
                            try:
                                from rialto import trusted_signing
                                if trusted_signing.is_configured():
                                    ok, message = self.run_watched_call(
                                        "Signing setup.exe", lambda log: trusted_signing.sign_file(setup_path, log))
                                    self.update_status(("✅ " if ok else "⚠️ ") + message)
                                    signed = ok
                                else:
                                    self.update_status("ℹ️ Automatic signing not set up yet (see the Configure Signing button)")
                            except Exception as e:
                                if getattr(self, "_abandon_build", False):
                                    raise
                                self.update_status(f"⚠️ Signing error: {e}")

                            if signed:
                                try:
                                    from rialto import ssl_signing
                                    self.update_status(f"🔍 Verification: {ssl_signing.verify_signature(setup_path)}")
                                except Exception:
                                    pass
                            else:
                                # Classic manual pause: sign with any service, then continue
                                self.update_status("🔐 Ready for manual code signing...")
                                self.update_status(f"📁 Files to sign are in: {output_path}")

                                import tkinter.messagebox as msgbox
                                # Never offered in a Build Queue (B1): nobody is there to sign by hand.
                                result = False if getattr(self, "_batch", None) is not None else msgbox.askokcancel(
                                    "Code Signing Pause",
                                    f"Automatic signing was skipped or failed.\n\n"
                                    f"Files location: {output_path}\n\n"
                                    f"Steps:\n"
                                    f"1. Sign setup.exe with your signing provider\n"
                                    f"2. Replace the original setup.exe in the build folder\n"
                                    f"3. Click OK to continue with ISO packaging\n\n"
                                    f"Click Cancel to skip signing and continue."
                                )

                                if getattr(self, "_batch", None) is not None:
                                    # Nobody is there to sign by hand: a queue must
                                    # not call an unsigned disc Done (security review).
                                    unsigned_in_queue = True
                                elif result:
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
        else:
            problem = "Inno Setup was not found"
            self.update_status("⚠️ ISCC.exe not found. Cannot create setup.exe. Download Inno Setup 6 or 7: "
                               + INNO_SETUP_DOWNLOAD)

        if problem:
            raise RuntimeError(f"No installer was made ({problem}), so the build was stopped.")
        if unsigned_in_queue:
            raise RuntimeError("Sign Final Build is on and signing did not work, so this disc would have "
                               "gone out unsigned. Fix signing under Configure Signing, then build it again")




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
            from rialto import trusted_signing
            if trusted_signing.find_signtool() is None:
                # Fetching it would be wasted: with nothing here to check Microsoft's signature, the
                # file was downloaded and then discarded on every build (1.5.1, launch day).
                self.update_status("ℹ️ No Visual C++ redistributable added: Rialto adds Microsoft's file only "
                                   "when signtool.exe (from the Windows SDK) can check its signature. Players "
                                   "are pointed at Microsoft's own download.")
            else:
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
        from rialto import trusted_signing
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
        # With no internet both downloads fail the same way: said once, plainly, and the build goes on
        # without them, as 1.5.0's did (1.5.1, end-to-end runs).
        unreachable = []

        for filename, url in downloads.items():
            dest_path = os.path.join(output_path, filename)
            try:
                self.update_status(f"⬇️ Downloading {filename}...")
                
                from rialto.update.fetch import FetchProblem, fetch_to_file

                def fetched_so_far():
                    # fetch_to_file writes to a .download- file beside the
                    # destination, then renames it: its size is the count.
                    sizes = [os.path.getsize(p) for p in glob.glob(os.path.join(output_path, ".download-*"))
                             if os.path.isfile(p)]
                    return (None, "%.1f MB" % (max(sizes) / 1e6)) if sizes else None

                try:
                    self.run_watched_call(
                        f"Downloading {filename}",
                        lambda _log: fetch_to_file(url, dest_path,
                                                   hosts={"aka.ms", "download.visualstudio.microsoft.com",
                                                          "download.microsoft.com"},
                                                   cap=64 * 1024 * 1024),
                        watch=fetched_so_far)
                except FetchProblem as problem:
                    unreachable.append((filename, str(problem)))
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
                if getattr(self, "_abandon_build", False):
                    raise
                self.update_status(f"❌ Download error for {filename}: {e}")

        if len(unreachable) == len(downloads):
            self.update_status("⚠️ The Visual C++ redistributables could not be downloaded, so the disc goes "
                               "without them. Players who need them are pointed at the official Microsoft "
                               "download. (%s)" % unreachable[0][1].strip())
        else:
            for filename, problem in unreachable:
                self.update_status(f"❌ Download failed: {filename}. {problem}")




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
        choice = self.compression_var.get() if hasattr(self, "compression_var") else "Balanced"
        iss_script += f"Compression={compression_setting(choice)}\n"
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
        # 6.1sp1: Inno's own default and its recommendation, and the floor
        # Windows 7 needs to verify a signature at all (B8).
        iss_script += "MinVersion=6.1sp1\n"
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
        # Files placed on the player's PC (1.5.1, B10), from the manifest the
        # staging step wrote beside them.
        try:
            with open(os.path.join(placed_files_root(output_path), "placed.json"), encoding="utf-8") as f:
                placed = placed_files_lines(json.load(f))
        except (OSError, ValueError):
            placed = []
        if placed:
            iss_script += "\n; Files placed for the player: never over one already there unless asked,\n"
            iss_script += "; and kept by the uninstaller unless asked.\n"
            iss_script += "".join(line + "\n" for line in placed)
        iss_script += '\n; Runtime redistributables (only files that passed Authenticode checks)\n'
        for redist in ("vcredist_x86.exe", "vcredist_x64.exe"):
            if os.path.isfile(os.path.join(output_path, redist)):
                iss_script += (
                    f'Source: "{redist}"; DestDir: "{{app}}\\runtime"; '
                    f'Flags: ignoreversion\n')
        
        # The menu needs Windows 8.1; on Windows 7 and 8 the shortcuts start the
        # game itself (1.5.1, B8). They read the menu_config.json staged a step
        # earlier, so they start the exe the menu would have.
        try:
            with open(os.path.join(output_path, "menu", "menu_config.json"), encoding="utf-8") as f:
                staged_config = json.load(f)
        except (OSError, ValueError):
            staged_config = {}
        win7_icons, win7_runs = windows7_shortcut_lines(path_name, staged_config, bool(copied_icon_path))
        menu_only = f"; MinVersion: {MENU_MIN_WINDOWS}" if win7_icons else ""
        if not win7_icons:
            self.update_status("⚠️ No game exe found for Windows 7 and 8: there the shortcuts open the menu, which needs Windows 8.1")

        iss_script += "\n[Icons]\n"
        iss_script += f'Name: "{{group}}\\{path_name}"; Filename: "{{app}}\\menu\\menu.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\game_icon.ico"{menu_only}\n'
        iss_script += f'Name: "{{userdesktop}}\\{path_name}"; Filename: "{{app}}\\menu\\menu.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\game_icon.ico"; Tasks: desktopicon{menu_only}\n'
        for line in win7_icons:
            iss_script += line + "\n"
        
        iss_script += "\n[Tasks]\n"
        iss_script += 'Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"\n'
        
        iss_script += "\n[Run]\n"
        iss_script += f'Filename: "{{app}}\\menu\\menu.exe"; Description: "{{cm:LaunchProgram}}"; Flags: nowait postinstall skipifsilent{menu_only}\n'
        for line in win7_runs:
            iss_script += line + "\n"
        
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
            from rialto import trusted_signing
            signed, message = self.run_watched_call(
                "Signing menu.exe", lambda log: trusted_signing.sign_staged_menu(menu_dir, log))
        except Exception as e:
            if getattr(self, "_abandon_build", False):
                raise
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
            result = self.run_tool_watched(build_cmd, menu_dir, 300, "Compiling the disc menu")
            
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
            if getattr(self, "_abandon_build", False):
                raise
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

    # The art a profile stores as absolute file paths (1.5.1, end-to-end runs): a 1.5.0 profile keeps
    # them under the game folder it was saved beside, so moving that folder left every one stale.
    REBASEABLE_FILES = (
        ("bg_path_var", "Menu Background"),
        ("logo_path_var", "Game Logo"),
        ("company_logo_var", "Company Logo"),
        ("ico_path_var", "Game Icon"),
        ("disc_icon_var", "Disc Icon"),
    )

    def rebase_file_under_game(self, stored):
        """A stored art file that has gone missing, found again in the game folder in use now.

        The same place relative to the game folder first, the longest tail of the stored path that is
        there (C:/old/input/Game/art/logo.png finds <game>/art/logo.png), then a file of the same name
        directly in the game folder. Never outside the game folder, and "" when nothing matches.
        """
        if not stored or not self.current_game_path or os.path.isfile(stored):
            return ""
        game = os.path.realpath(self.current_game_path)
        parts = [p for p in stored.replace("\\", "/").split("/") if p not in ("", ".", "..")]
        # A drive ("C:") or a share's name never joins under the game folder.
        if parts and (parts[0].endswith(":") or stored.replace("\\", "/").startswith("//")):
            parts = parts[1:]
        for start in range(len(parts)):
            candidate = os.path.join(game, *parts[start:])
            try:
                inside = os.path.commonpath([game, os.path.realpath(candidate)]) == game
            except ValueError:
                inside = False
            if inside and os.path.isfile(candidate):
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
        for attr, label in self.REBASEABLE_FILES:
            var = getattr(self, attr, None)
            if var is None:
                continue
            found = self.rebase_file_under_game(var.get().strip())
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
        """Check what the build needs, then build, with the window answering throughout (B6)."""
        if getattr(self, "_building", False):
            return False
        self._building = True
        self._abandon_build = False
        self.hold_page(True)
        try:
            return self._run_build_process()
        finally:
            self._building = False
            self._build_line = None
            self._running_tool = None
            try:
                self.hold_page(False)
                self.refresh_disc_meter()
            except tk.TclError:
                pass
            self.close_if_asked()

    def hold_page(self, hold):
        """While a build runs, the page and the menus take no clicks (1.5.1, B6).

        The title bar still moves and minimises the window, and the log still
        scrolls: Tk's own busy hold sits over everything else, so nothing the
        build reads can change under it.
        """
        page = getattr(self, "page_frame", None)
        held = [getattr(self, "menu_bar", None), getattr(self, "export_action_row", None),
                getattr(self, "export_check_row", None)]
        if page is not None:
            held += [w for w in page.winfo_children() if w is not getattr(self, "status_text", None)]
        for widget in held:
            if widget is None:
                continue
            try:
                widget.tk.call("tk", "busy", "hold" if hold else "forget", widget._w)
            except tk.TclError:
                pass
        if hold:
            try:
                self.status_text.focus_set()
            except (tk.TclError, AttributeError):
                pass
        # tk busy stops the pointer only. A tag at the front of every held
        # widget's bindings swallows keys too, so Tab and Space cannot press
        # Load Profile mid-build (security review).
        try:
            self.root.bind_class("RialtoBuilding", "<Key>", lambda _e: "break")
        except (tk.TclError, AttributeError):
            return

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        for top in held:
            if top is None:
                continue
            try:
                for widget in walk(top):
                    tags = tuple(t for t in widget.bindtags() if t != "RialtoBuilding")
                    widget.bindtags((("RialtoBuilding",) + tags) if hold else tags)
            except tk.TclError:
                pass

    def keep_window_alive(self):
        """Let the window answer Windows between pieces of build work (B6)."""
        try:
            self.root.update()
        except (tk.TclError, AttributeError):
            pass
        if getattr(self, "_abandon_build", False):
            raise RuntimeError("Rialto was closed during the build")

    def show_progress(self, step, fraction=None, seconds=0.0, detail=""):
        """Move the live line under the log (B6)."""
        self._build_line = (progress_text(step, fraction, seconds, detail), fraction)
        try:
            self.draw_disc_meter()
        except (tk.TclError, AttributeError):
            pass

    def tree_size(self, path, skip_ext=(".iso",)):
        """(bytes, files) under `path`, leaving out finished disc images."""
        total, count = 0, 0
        for dirpath, _dirs, files in os.walk(path):
            for name in files:
                if name.lower().endswith(skip_ext):
                    continue
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                    count += 1
                except OSError:
                    pass
        return total, count

    def run_tool_watched(self, command, cwd, timeout, step, on_line=None, watch=None):
        """Run a tool with the window answering and the live line moving (1.5.1, B6).

        Popen with its output read on two small threads into a queue; this loop,
        on the window's own thread, drains the queue into `on_line` (which may
        hand back (fraction, detail)), asks `watch` the same, moves the line and
        lets the window answer. Hands back what subprocess.run would, and raises
        subprocess.TimeoutExpired as it does, so each caller keeps its checks.
        The build itself stays on this thread: Tkinter is not thread-safe.
        """
        import queue
        import threading
        proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, text=True, errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._running_tool = proc
        lines, out, err = queue.Queue(), [], []

        def pump(stream, sink):
            for line in stream:
                sink.append(line)
                lines.put(line)

        readers = [threading.Thread(target=pump, args=(proc.stdout, out), daemon=True),
                   threading.Thread(target=pump, args=(proc.stderr, err), daemon=True)]
        for reader in readers:
            reader.start()
        started, fraction, detail = time.monotonic(), None, ""

        def drain():
            nonlocal fraction, detail
            while True:
                try:
                    line = lines.get_nowait()
                except queue.Empty:
                    return
                if on_line:
                    got = on_line(line.rstrip("\r\n"))
                    if got:
                        fraction, detail = got

        try:
            while True:
                drain()
                if watch:
                    got = watch()
                    if got:
                        fraction, detail = got
                self.show_progress(step, fraction, time.monotonic() - started, detail)
                if proc.poll() is not None:
                    break
                if time.monotonic() - started > timeout:
                    proc.kill()
                    proc.wait()
                    raise subprocess.TimeoutExpired(command, timeout, output="".join(out), stderr="".join(err))
                self.keep_window_alive()
                time.sleep(0.05)
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        for reader in readers:
            reader.join(timeout=5)
        drain()
        self._running_tool = None
        return subprocess.CompletedProcess(command, proc.returncode, "".join(out), "".join(err))

    def build_ticker(self, step, total=0):
        """A tick to call as slow work goes by: it moves the live line and lets the window answer (B6).

        Call it with the bytes just done, or with nothing where there is no
        count, and the line shows the time so far. It redraws five times a
        second at most.
        """
        state = {"done": 0, "started": time.monotonic(), "shown": 0.0}

        def tick(more=0):
            state["done"] += more
            now = time.monotonic()
            if now - state["shown"] > 0.2:
                state["shown"] = now
                done = state["done"]
                if total >= 1e8:
                    detail = "%.1f of %.1f GB" % (done / 1e9, total / 1e9)
                elif not total and done >= 1e6:
                    detail = "%.0f MB" % (done / 1e6)
                else:
                    detail = ""
                self.show_progress(step, done / total if total else None, now - state["started"], detail)
                self.keep_window_alive()
        return tick

    def counting_copy(self, step, total):
        """A copy function for shutil that moves the live line and lets the window answer (B6)."""
        tick = self.build_ticker(step, total)

        def copy(src, dst, *, follow_symlinks=True):
            result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
            try:
                tick(os.path.getsize(src))
            except OSError:
                tick()
            return result
        return copy

    def watched_copytree(self, src, dst, step, **options):
        """shutil.copytree with the live line counting the bytes (B6)."""
        total, _count = self.tree_size(src, skip_ext=())
        return shutil.copytree(src, dst, copy_function=self.counting_copy(step, total), **options)

    def run_watched_call(self, step, work, watch=None):
        """Run slow Python work (a download, a signature) with the window answering (B6).

        `work(log)` runs on a small thread and never touches the window: `log`
        queues its lines, and this loop, on the window's own thread, writes
        them to the log, moves the live line (the time so far, or what `watch`
        hands back as (fraction, detail)) and lets the window answer. Hands back
        what `work` returned, and raises what it raised.
        """
        import queue
        import threading
        lines, outcome = queue.Queue(), {}

        def run():
            try:
                outcome["value"] = work(lines.put)
            except BaseException as error:  # raised again on the window's thread
                outcome["error"] = error

        def drain():
            while True:
                try:
                    self.update_status(lines.get_nowait())
                except queue.Empty:
                    return

        worker = threading.Thread(target=run, daemon=True)
        started, fraction, detail = time.monotonic(), None, ""
        worker.start()
        while worker.is_alive():
            drain()
            if watch:
                got = watch()
                if got:
                    fraction, detail = got
            self.show_progress(step, fraction, time.monotonic() - started, detail)
            self.keep_window_alive()
            worker.join(0.05)
        drain()
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")

    def _run_build_process(self):
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
                self.update_status("⛔ Build canceled - fix the folders in Disc Extras")
                return False

        if not self.run_preflight_check():
            return False
        return self.build_all()

    def refresh_windows_icon_cache(self):
        """Refresh Windows icon cache to show updated disc icons"""
        try:
            if sys.platform == "win32":
                # Force Windows to refresh the icon cache. ie4uinit.exe is a windowed program, run
                # straight from System32: through "cmd /c" it opened a black console window at the
                # end of every build (1.5.1, launch day).
                ie4uinit = os.path.join(os.environ.get("SystemRoot") or "C:\\Windows", "System32", "ie4uinit.exe")
                if not os.path.isfile(ie4uinit):
                    return
                self.update_status("🔄 Refreshing Windows icon cache...")
                subprocess.run([ie4uinit, "-show"], capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.update_status("✅ Icon cache refreshed")
        except Exception as e:
            # Silently fail - this is just a nice-to-have
            pass

    def clean_output_folder_final(self, output_path, keep_mode="iso"):
        """Final cleanup - remove everything except ISO file"""
        
        # Files to KEEP (everything else gets deleted)
        keep_files = []
        
        # Add ISO files to keep, and for a pressed disc what goes to the plant
        for item in os.listdir(output_path):
            if item.lower().endswith(".iso") or item == "Chksum.md5" or item.endswith(" master sheet.txt"):
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
            self.centre_on(drive_dialog, 300, 150, self.root)
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
            self.watched_copytree(bonus_source, bonus_output, "Copying the bonus folder")
            self.update_status("✅ Bonus content copied")
        except Exception as e:
            if getattr(self, "_abandon_build", False):
                raise
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
            self.watched_copytree(mods_source, mods_output, "Copying the mod folder")
            self.update_status(f"✅ Mod folder copied: {staged_name}")
        except Exception as e:
            if getattr(self, "_abandon_build", False):
                raise
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
            total, _count = self.tree_size(source_dir, skip_ext=())
            copy = self.counting_copy("Copying the game", total)
            
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
                    copy(source_path, dest_path)
                    copied_files += 1
                    self.update_status(f"📁 Copied: {item} (game logo)")
                elif os.path.isfile(source_path):
                    copy(source_path, dest_path)
                    copied_files += 1
                    self.update_status(f"📁 Copied: {item}")
                elif os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True, copy_function=copy)
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
        # The 8 cm minis (1.5.1, minis) are named only when one is the Target
        # Media: then the line confirms it, and every other small game's line
        # stays as short as it was.
        mini = self.target_media_var.get() in MINI_DISC_MEDIA
        if self.pressed_disc_on():
            sectors = size_bytes // SECTOR_BYTES
            pressed = [name for name, limit in (("8 cm CD-ROM", MINI_CD_SECTORS if mini else 0),
                                                 ("CD-ROM", 360_000),
                                                 ("8 cm DVD-5", MINI_DVD5_SECTORS if mini else 0),
                                                 ("DVD-5", DVD5_SECTORS),
                                                 ("DVD-9", 2 * DVD9_LAYER0_SECTORS)) if sectors <= limit]
            self.update_status(f"💿 Presses as: {', '.join(pressed)}" if pressed
                               else "⚠️ The image is bigger than a DVD-9 can press")
            return
        media_types = [
            ("Mini CD-R (210 MB, 8 cm)", 221_184_000 if mini else 0),
            ("CD-R (700 MB)", 700 * 1024 * 1024),
            ("Mini DVD-R (1.4 GB, 8 cm)", 1_460_000_000 if mini else 0),
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
        """Build the ISO with mkisofs or oscdimg, or fall back to a ZIP.

        self.images_made lists every disc image this build finished (one, or each disc of a set), and only
        those: the master sheet, Chksum.md5 and the Build Queue's summary are made from it, never from
        whatever *.iso lies in the folder. A tool that stops at 30 minutes stops the build.
        """
        game_name = meta["GameName"]
        iso_path = os.path.join(output_path, f"{game_name}.iso")
        self.images_made = []

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
            # The same limit the set's discs are packed to: a payload that fits
            # one disc is one disc, never a one-disc "set".
            if total_size > capacity - self.SPAN_MARGIN:
                # In MB under a gigabyte, so a mini's "0.3 GB" never sits beside "210 MB".
                weight = (f"{total_size / 1e9:.1f} GB" if total_size >= 1e9
                          else f"{total_size // 1_000_000} MB")
                self.update_status(f"📀 Build is {weight}, over the {self.target_media_var.get()} limit")
                self.create_spanned_isos(output_path, meta, disc_label, capacity)
                return

        # Files over 4 GB need the UDF disc format (standard on Blu-ray players)
        needs_udf = self._fileset_needs_udf(output_path, iso_files)
        if needs_udf:
            self.update_status("💿 Large files detected: using the UDF disc format")
        
        # Which tool writes the image (1.5.1): mkisofs on PATH, then oscdimg (PATH or the Windows ADK), then
        # the mkisofs Rialto carries; each in turn until one works, and the ZIP only when none does. A
        # plant's master is made with mkisofs only: oscdimg is licensed for producing Microsoft-authorized
        # content, as it prints itself (disc_image_tools leaves it out of a pressed disc's list).
        tools = disc_image_tools(self.pressed_disc_on())
        if not tools:
            self.update_status("⚠️ No ISO tool found. Install the Windows ADK with Deployment Tools ticked (oscdimg), or put mkisofs on your PATH")
            # Fallback to Python ZIP method (but still create .iso extension)
            self._iso_fallback_unless_pressed(output_path, iso_path, iso_files, meta)
            return

        for attempt, (kind, tool_path, carried) in enumerate(tools):
            words = tool_words(kind, tool_path, carried)
            if attempt:
                self.update_status("🔄 Trying the next disc image tool: " + words)
            else:
                self.update_status("✅ Writing the disc image with " + words)
            copy = None
            if kind == "oscdimg":
                copy = self.counting_copy("Preparing the disc image", self._fileset_size(output_path, iso_files))
            try:
                # Thirty minutes, not two. Two minutes does not image a DVD on
                # any real machine: a 4 GB payload on a spinning disk takes
                # longer than that before it has finished reading, so the
                # timeout fired on ordinary discs rather than on stuck ones.
                # A genuinely stuck tool is still stopped after half an hour.
                # Watched (1.5.1, B6): the image grows on disk as the tool writes
                # it, which gives a percentage for mkisofs and oscdimg alike.
                made, why = self._write_one_image(kind, tool_path, output_path, iso_path, iso_files, disc_label,
                                                  needs_udf, "temp_iso_build", "Writing the disc image", copy)
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
                # Nor does it return as if all were well (bugs review, 1.5.1): the
                # half-written image used to stay, and a pressed disc then got a
                # checksum and a master sheet for it, with "Build complete". The
                # partial is removed and the build stops, pressed or not.
                self.update_status("❌ ISO creation timed out after 30 minutes")
                self._remove_partial_iso(iso_path)
                raise RuntimeError("the disc image was not finished after 30 minutes, so no image was made. "
                                   "Check free disk space and that no scanner is holding the build folder, "
                                   "then build again")
            except Exception as e:
                if getattr(self, "_abandon_build", False):
                    self._remove_partial_iso(iso_path)
                    raise  # Rialto was closed: no fallback after the window has gone
                made, why = False, str(e)

            if made:
                self.images_made = [iso_path]
                iso_size = os.path.getsize(iso_path) / (1024 * 1024)  # MB
                self.update_status(f"✅ ISO created successfully: {iso_size:.1f} MB")
                self.report_disc_media_fit(os.path.getsize(iso_path))
                self.refresh_windows_icon_cache()
                if self.pressed_disc_on():
                    self.update_status("📀 Ready for the plant: send the image with Chksum.md5 and the master sheet")
                else:
                    self.update_status("📀 Ready to burn: Use disc burning software to burn this ISO")
                return
            self.update_status(f"❌ ISO creation failed with {words}: {why}")
            self._remove_partial_iso(iso_path)

        self.update_status("🔄 Trying Python fallback method...")
        self._iso_fallback_unless_pressed(output_path, iso_path, iso_files, meta)

    def _iso_fallback_unless_pressed(self, output_path, iso_path, iso_files, meta):
        """The ZIP fallback, except for a pressed disc: a ZIP is not a master, so that build stops."""
        if self.pressed_disc_on():
            self._remove_partial_iso(iso_path)
            raise RuntimeError("the disc image for the plant could not be made with mkisofs, see above")
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
        
        batch = getattr(self, "_batch", None)
        if batch is not None:
            batch["lines"].append(message)
        try:
            self.status_text.configure(state="normal")
        except tk.TclError:
            return  # the window was closed during a build
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
        # Near the top left corner of the monitor Rialto is on, which is not always the main one's 100, 100.
        left, top, _width, _height = self.available_space(self.root)
        self.place_window(restore_popup, 200, 60, left + 100, top + 100, near=self.root)
        restore_popup.attributes("-topmost", True)
        restore_popup.configure(bg=self.dark_theme["bg"])

        tk.Label(restore_popup, text="Click to restore Rialto",
                 bg=self.dark_theme["bg"],
                 fg=self.dark_theme["fg"]).pack(pady=5)

        tk.Button(restore_popup, text="Restore",
                  bg=self.dark_theme["button_bg"],
                  fg=self.dark_theme["button_fg"],
                  command=lambda: self._restore_window(restore_popup)).pack(pady=5)

        # As tall as what it holds: at 60 lines the Restore button was cut off half way down.
        restore_popup.update_idletasks()
        self.place_window(restore_popup, 200, max(60, restore_popup.winfo_reqheight()),
                          left + 100, top + 100, near=self.root)

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
import ctypes
import time
import unicodedata
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

# The player's own choices (1.5.1, B9): which games they starred to the top of
# both lists, how the Play page is sorted, and the menu language they picked.
# Kept on this PC under the disc's title, never on the disc, and read back with
# suspicion, because anything on the PC can rewrite the file.
#
# Every game is listed under PLAY GAMES, so a star no longer competes for one of
# three places on the main menu: a player can star as many as they like. The cap
# only bounds what a rewritten file can make the menu hold.
MAX_STARS = 200


def player_prefs_path(title):
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    key = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:80] or "Game"
    return os.path.join(base, "Rialto Disc Menu", key, "player.json")


def read_player_prefs(title):
    try:
        path = player_prefs_path(title)
        if os.path.getsize(path) > 64 * 1024:
            return {"stars": [], "sort": "disc", "lang": ""}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            raw = data.get("stars")
            stars = []
            for x in (raw[-MAX_STARS:] if isinstance(raw, list) else []):
                if isinstance(x, str) and len(x) < 400 and x not in stars:
                    stars.append(x)
            # Only a name the menu has a translation for is ever used; see GameMenu.
            lang = data.get("lang")
            return {"stars": stars,
                    "sort": "az" if data.get("sort") == "az" else "disc",
                    "lang": lang if isinstance(lang, str) and len(lang) < 40 else ""}
    except Exception:
        # Anything at all: a file nested deep enough raises RecursionError, and a
        # menu that will not start on this PC is worse than one that forgot.
        pass
    return {"stars": [], "sort": "disc", "lang": ""}


def write_player_prefs(title, prefs):
    path = player_prefs_path(title)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass

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

# Controller support (1.5.1): XInput, which every Xbox-style pad speaks and Windows has carried
# since Windows 8 (xinput1_4.dll), read through ctypes. Nothing new rides on the disc and the
# player installs nothing. A PlayStation or Switch pad works through Steam Input or its own
# XInput mode. Loaded from System32 by its full path, never from the disc or the install folder.
PAD_UP, PAD_DOWN, PAD_LEFT, PAD_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
PAD_START = 0x0010
PAD_A, PAD_B, PAD_Y = 0x1000, 0x2000, 0x8000
PAD_STICK = 12000  # past a third of its travel, the left stick counts as the D-pad...
PAD_STICK_OFF = 8000  # ...and stays pressed until it is back under a quarter, so a resting thumb never
                      # flickers across one mark and steps the menu on every crossing
PAD_STEER = PAD_UP | PAD_DOWN | PAD_LEFT | PAD_RIGHT


class XInputGamepad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class XInputState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint), ("Gamepad", XInputGamepad)]


def load_xinput():
    """XInputGetState from Windows' own XInput, or None when this Windows has none."""
    system = ""
    try:
        found = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetSystemDirectoryW(found, 260):
            system = found.value
    except Exception:
        pass
    if not system and os.environ.get("SystemRoot"):
        system = os.path.join(os.environ["SystemRoot"], "System32")
    if not system:
        return None
    for name in ("xinput1_4.dll", "xinput9_1_0.dll", "xinput1_3.dll"):
        path = os.path.join(system, name)
        if not os.path.isfile(path):
            continue
        try:
            get_state = ctypes.WinDLL(path).XInputGetState
        except (OSError, AttributeError):
            continue
        get_state.argtypes = [ctypes.c_uint, ctypes.POINTER(XInputState)]
        get_state.restype = ctypes.c_uint
        return get_state
    return None


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
        self.player_prefs = read_player_prefs(MENU_TITLE)

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
                "choose_game": "اختر لعبتك", "sort_disc": "بترتيب القرص", "sort_az": "أبجديًا",
                "tip_star": "ضع نجمة على لعبة لتظهر في أعلى القائمة الرئيسية.",
                "play_games": "العب الألعاب", "steam": "أضف إلى Steam",
                "ok": "موافق",
                "steam_none_title": "لا شيء لإضافته",
                "steam_none": "لم يتم العثور على أي لعبة لإضافتها إلى مكتبة Steam لديك.",
                "steam_none_detail": "ثبّت اللعبة من القرص أولاً، ثم حاول مرة أخرى.",
                "steam_missing_title": "لم يتم العثور على Steam",
                "steam_missing": "لم يتم العثور على أي ملف تعريف Steam على هذا الكمبيوتر.",
                "steam_missing_detail": "ثبّت Steam وسجّل الدخول مرة واحدة، ثم حاول مرة أخرى. لا ينشئ Steam المجلد المطلوب إلا بعد أول تسجيل دخول.",
                "steam_running_title": "أغلق Steam أولاً",
                "steam_running": "Steam قيد التشغيل، لذلك لم تتم إضافة أي شيء بعد.",
                "steam_running_why": "سيتراجع Steam عن الإضافة: فهو يحتفظ بقائمة الألعاب غير التابعة لـ Steam في الذاكرة ويعيد كتابة تلك النسخة عند إغلاقه.",
                "steam_running_detail": "أغلق Steam تمامًا: انقر بزر الماوس الأيمن على أيقونة Steam في منطقة الإعلامات بجوار الساعة، واختر خروج. إغلاق النافذة لا يكفي. ثم اضغط «أضف إلى Steam» مرة أخرى.",
                "steam_added_title": "تمت الإضافة إلى Steam",
                "steam_added": "تمت إضافة %s إلى مكتبة Steam لديك، ضمن الألعاب غير التابعة لـ Steam.",
                "steam_added_detail": "ستجدها هناك في المرة القادمة التي تشغّل فيها Steam.",
                "steam_already_title": "موجودة في Steam بالفعل",
                "steam_already": "سبق أن أُضيفت %s إلى مكتبة Steam لديك.",
                "steam_already_detail": "لم يتم تغيير أي شيء. احذفها من Steam أولاً إذا أردت إضافتها مرة أخرى.",
                "steam_failed_title": "تعذّرت الإضافة إلى Steam",
                "steam_blocked": "تعذّر تحديث قائمة Steam للألعاب غير التابعة لـ Steam.",
                "steam_blocked_detail": "أغلق Steam تمامًا وحاول مرة أخرى. لم يتم تغيير أي شيء، والقائمة السابقة كما هي.",
                "steam_unread": "تعذّرت قراءة قائمة Steam للألعاب غير التابعة لـ Steam.",
                "steam_unread_detail": "أغلق Steam تمامًا وحاول مرة أخرى.",
                "uninstaller_detail": "ألغِ تثبيت اللعبة بدلاً من ذلك من Windows: الإعدادات، ثم التطبيقات.",
                "bonus_detail": "تم إنشاء هذا القرص بدون مجلد للمحتوى الإضافي.",
                "mods_detail": "لم يتم العثور على أداة مودات في مجلد المودات على هذا القرص.",
                "looked_for": "تم البحث عن: %s",
                "looked_in": "تم البحث في:",
                "and_more": "... و%d أخرى",
                "play_again": "جرّب الضغط على «العب اللعبة» مرة أخرى أولاً: قد يكون المجلد المثبّت حديثًا لا يزال قيد الفحص. إذا استمر الفشل، فربما لم يكتمل نسخ مجلد اللعبة.",
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
                "choose_game": "Изберете игра", "sort_disc": "Както на диска", "sort_az": "От А до Я",
                "tip_star": "Отбележете игра със звезда, за да се появи най-горе в главното меню.",
                "play_games": "Играй", "steam": "Добави в Steam",
                "ok": "OK",
                "steam_none_title": "Няма какво да се добави",
                "steam_none": "Не е намерена игра, която да бъде добавена към вашата Steam библиотека.",
                "steam_none_detail": "Първо инсталирайте играта от диска, след това опитайте отново.",
                "steam_missing_title": "Steam не е намерен",
                "steam_missing": "На този компютър не е намерен профил в Steam.",
                "steam_missing_detail": "Инсталирайте Steam и влезте поне веднъж, след това опитайте отново. Steam създава нужната папка едва след първото влизане.",
                "steam_running_title": "Първо излезте от Steam",
                "steam_running": "Steam работи, затова все още нищо не е добавено.",
                "steam_running_why": "Steam би отменил промяната: той пази списъка си с игри извън Steam в паметта и записва това копие обратно при затваряне.",
                "steam_running_detail": "Излезте напълно от Steam: щракнете с десния бутон върху иконата на Steam в областта за уведомяване до часовника и изберете Изход. Затварянето на прозореца не е достатъчно. След това натиснете „Добави в Steam“ отново.",
                "steam_added_title": "Добавено в Steam",
                "steam_added": "%s вече е във вашата Steam библиотека, сред игрите извън Steam.",
                "steam_added_detail": "Ще се появи там следващия път, когато стартирате Steam.",
                "steam_already_title": "Вече е в Steam",
                "steam_already": "%s вече е във вашата Steam библиотека.",
                "steam_already_detail": "Нищо не е променено. Ако искате да добавите играта отново, първо я премахнете от Steam.",
                "steam_failed_title": "Неуспешно добавяне в Steam",
                "steam_blocked": "Списъкът на Steam с игри извън Steam не можа да бъде обновен.",
                "steam_blocked_detail": "Затворете Steam напълно и опитайте отново. Нищо не е променено и предишният списък е непокътнат.",
                "steam_unread": "Списъкът на Steam с игри извън Steam не можа да бъде прочетен.",
                "steam_unread_detail": "Затворете Steam напълно и опитайте отново.",
                "uninstaller_detail": "Вместо това деинсталирайте играта от Настройки на Windows, Приложения.",
                "bonus_detail": "Този диск е създаден без папка с бонус съдържание.",
                "mods_detail": "В папката с модове на този диск не е намерен инструмент за модове.",
                "looked_for": "Търсено: %s",
                "looked_in": "Търсено в:",
                "and_more": "... и още %d",
                "play_again": "Първо опитайте „Играй“ още веднъж: току-що инсталирана папка понякога все още се сканира. Ако продължава да не става, копирането на папката на играта може да не е завършило.",
                "yes": "Да", "no": "Не", "cancel": "Отказ"
            },
            "Chinese (Simplified)": {
                "play": "开始游戏", "bonus": "额外内容", "mods": "模组", "compat": "兼容模式", "uninstall": "卸载", "exit": "退出",
                "language": "语言:", "error": "错误", "warning": "警告",
                "game_not_found": "找不到游戏可执行文件！",
                "bonus_not_found": "找不到额外内容！",
                "mods_not_found": "找不到模组工具！",
                "uninstaller_not_found": "找不到卸载程序！",
                "confirm_uninstall": "你确定要卸载此游戏吗？",
                "install": "安装游戏",
                "tip_install": "运行本光盘上的安装程序。",
                "tip_compat": "以适合较旧或不受支持的显卡的设置启动游戏。",
                "tip_bonus": "打开本光盘附带的额外内容。",
                "tip_mods": "打开本光盘附带的模组工具。",
                "tip_steam": "将游戏添加到你的 Steam 库，以便从那里启动。",
                "tip_uninstall": "移除已安装的游戏。你的存档不会被删除。",
                "choose_game": "选择你的游戏", "sort_disc": "按光盘顺序", "sort_az": "按名称",
                "tip_star": "为游戏加上星标，它就会排在主菜单的最上方。",
                "play_games": "开始游戏", "steam": "添加到 Steam",
                "ok": "确定",
                "steam_none_title": "没有可添加的游戏",
                "steam_none": "没有找到可以添加到你的 Steam 库的游戏。",
                "steam_none_detail": "请先从光盘安装游戏，然后再试一次。",
                "steam_missing_title": "找不到 Steam",
                "steam_missing": "这台电脑上没有找到 Steam 用户资料。",
                "steam_missing_detail": "请安装 Steam 并登录一次，然后再试一次。Steam 只有在首次登录后才会创建所需的文件夹。",
                "steam_running_title": "请先退出 Steam",
                "steam_running": "Steam 正在运行，所以还没有添加任何内容。",
                "steam_running_why": "Steam 会撤销这项更改：它把非 Steam 游戏列表保存在内存中，并在关闭时把这份副本写回去。",
                "steam_running_detail": "请完全退出 Steam：在时钟旁的通知区域右键单击 Steam 图标，然后选择退出。只关闭窗口是不够的。之后再按一次添加到 Steam 按钮。",
                "steam_added_title": "已添加到 Steam",
                "steam_added": "%s 现已添加到你的 Steam 库中，位于非 Steam 游戏下。",
                "steam_added_detail": "下次启动 Steam 时就会看到它。",
                "steam_already_title": "已在 Steam 中",
                "steam_already": "%s 已在你的 Steam 库中。",
                "steam_already_detail": "未做任何更改。如果想重新添加，请先从 Steam 中移除它。",
                "steam_failed_title": "无法添加到 Steam",
                "steam_blocked": "无法更新 Steam 的非 Steam 游戏列表。",
                "steam_blocked_detail": "请完全关闭 Steam 后再试一次。未做任何更改，原有列表保持不变。",
                "steam_unread": "无法读取 Steam 的非 Steam 游戏列表。",
                "steam_unread_detail": "请完全关闭 Steam 后再试一次。",
                "uninstaller_detail": "请改为在 Windows 设置 > 应用 中卸载此游戏。",
                "bonus_detail": "这张光盘制作时没有附带额外内容文件夹。",
                "mods_detail": "在本光盘的模组文件夹中找不到模组工具。",
                "looked_for": "查找的文件：%s",
                "looked_in": "查找位置：",
                "and_more": "……还有 %d 个",
                "play_again": "请先再按一次开始游戏：刚安装好的文件夹有时仍在被扫描。如果仍然失败，可能是游戏文件夹还没有复制完成。",
                "yes": "是", "no": "否", "cancel": "取消"
            },
            "Chinese (Traditional)": {
                "play": "開始遊戲", "bonus": "額外內容", "mods": "模組", "compat": "相容模式", "uninstall": "移除", "exit": "結束",
                "language": "語言:", "error": "錯誤", "warning": "警告",
                "game_not_found": "找不到遊戲執行檔！",
                "bonus_not_found": "找不到額外內容！",
                "mods_not_found": "找不到模組工具！",
                "uninstaller_not_found": "找不到移除程式！",
                "confirm_uninstall": "你確定要移除此遊戲嗎？",
                "install": "安裝遊戲",
                "tip_install": "執行本光碟上的安裝程式。",
                "tip_compat": "以適合較舊或不支援的顯示卡的設定啟動遊戲。",
                "tip_bonus": "開啟本光碟附帶的額外內容。",
                "tip_mods": "開啟本光碟附帶的模組工具。",
                "tip_steam": "將遊戲加入你的 Steam 收藏庫，以便從那裡啟動。",
                "tip_uninstall": "移除已安裝的遊戲。你的存檔不會被刪除。",
                "choose_game": "選擇你的遊戲", "sort_disc": "按光碟順序", "sort_az": "按名稱",
                "tip_star": "為遊戲加上星號，它就會排在主選單的最上方。",
                "play_games": "開始遊戲", "steam": "加入 Steam",
                "ok": "確定",
                "steam_none_title": "沒有可加入的遊戲",
                "steam_none": "找不到可以加入你的 Steam 收藏庫的遊戲。",
                "steam_none_detail": "請先從光碟安裝遊戲，然後再試一次。",
                "steam_missing_title": "找不到 Steam",
                "steam_missing": "這台電腦上找不到 Steam 使用者資料。",
                "steam_missing_detail": "請安裝 Steam 並登入一次，然後再試一次。Steam 只有在第一次登入後才會建立所需的資料夾。",
                "steam_running_title": "請先結束 Steam",
                "steam_running": "Steam 正在執行，所以尚未加入任何項目。",
                "steam_running_why": "Steam 會復原這項變更：它會把非 Steam 遊戲清單保存在記憶體中，並在關閉時把這份副本寫回去。",
                "steam_running_detail": "請完全結束 Steam：在時鐘旁的通知區域中以滑鼠右鍵按一下 Steam 圖示，然後選擇「結束」。只關閉視窗是不夠的。接著再按一次「加入 Steam」。",
                "steam_added_title": "已加入 Steam",
                "steam_added": "%s 現已加入你的 Steam 收藏庫，位於非 Steam 遊戲之下。",
                "steam_added_detail": "下次啟動 Steam 時就會看到它。",
                "steam_already_title": "已在 Steam 中",
                "steam_already": "%s 已在你的 Steam 收藏庫中。",
                "steam_already_detail": "未做任何變更。若想重新加入，請先從 Steam 移除它。",
                "steam_failed_title": "無法加入 Steam",
                "steam_blocked": "無法更新 Steam 的非 Steam 遊戲清單。",
                "steam_blocked_detail": "請完全關閉 Steam 後再試一次。未做任何變更，原本的清單維持不變。",
                "steam_unread": "無法讀取 Steam 的非 Steam 遊戲清單。",
                "steam_unread_detail": "請完全關閉 Steam 後再試一次。",
                "uninstaller_detail": "請改從 Windows「設定」中的「應用程式」移除此遊戲。",
                "bonus_detail": "這張光碟製作時沒有附帶額外內容資料夾。",
                "mods_detail": "在本光碟的模組資料夾中找不到模組工具。",
                "looked_for": "尋找的檔案：%s",
                "looked_in": "尋找位置：",
                "and_more": "……還有 %d 個",
                "play_again": "請先再按一次「開始遊戲」：剛安裝好的資料夾有時仍在掃描中。如果還是失敗，可能是遊戲資料夾尚未複製完成。",
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
                "choose_game": "Odaberite igru", "sort_disc": "Kao na disku", "sort_az": "Od A do Ž",
                "tip_star": "Označite igru zvjezdicom i bit će na vrhu glavnog izbornika.",
                "play_games": "Igraj", "steam": "Dodaj u Steam",
                "ok": "U redu",
                "steam_none_title": "Nema se što dodati",
                "steam_none": "Nije pronađena nijedna igra za dodavanje u vašu Steam biblioteku.",
                "steam_none_detail": "Najprije instalirajte igru s diska, a zatim pokušajte ponovno.",
                "steam_missing_title": "Steam nije pronađen",
                "steam_missing": "Na ovom računalu nije pronađen nijedan Steam profil.",
                "steam_missing_detail": "Instalirajte Steam i jednom se prijavite, a zatim pokušajte ponovno. Steam tek nakon prve prijave stvara mapu koja je za ovo potrebna.",
                "steam_running_title": "Najprije izađite iz Steama",
                "steam_running": "Steam je pokrenut, pa još ništa nije dodano.",
                "steam_running_why": "Steam bi to poništio: svoj popis igara izvan Steama drži u memoriji i pri zatvaranju zapisuje tu kopiju natrag.",
                "steam_running_detail": "Potpuno izađite iz Steama: desnom tipkom miša kliknite ikonu Steama u području obavijesti pokraj sata i odaberite Exit. Zatvaranje prozora nije dovoljno. Zatim ponovno pritisnite „Dodaj u Steam”.",
                "steam_added_title": "Dodano u Steam",
                "steam_added": "%s sada se nalazi u vašoj Steam biblioteci, među igrama izvan Steama.",
                "steam_added_detail": "Bit će ondje sljedeći put kad pokrenete Steam.",
                "steam_already_title": "Već je u Steamu",
                "steam_already": "%s već se nalazi u vašoj Steam biblioteci.",
                "steam_already_detail": "Ništa nije promijenjeno. Ako je želite ponovno dodati, najprije je uklonite iz Steama.",
                "steam_failed_title": "Dodavanje u Steam nije uspjelo",
                "steam_blocked": "Steamov popis igara izvan Steama nije moguće ažurirati.",
                "steam_blocked_detail": "Potpuno zatvorite Steam i pokušajte ponovno. Ništa nije promijenjeno, a prethodni popis ostao je netaknut.",
                "steam_unread": "Steamov popis igara izvan Steama nije moguće pročitati.",
                "steam_unread_detail": "Potpuno zatvorite Steam i pokušajte ponovno.",
                "uninstaller_detail": "Umjesto toga deinstalirajte igru u sustavu Windows: Postavke, Aplikacije.",
                "bonus_detail": "Ovaj je disk izrađen bez mape s bonus sadržajem.",
                "mods_detail": "U mapi s modovima na ovom disku nije pronađen alat za modove.",
                "looked_for": "Traženo: %s",
                "looked_in": "Traženo u:",
                "and_more": "... i još %d",
                "play_again": "Najprije još jednom pokušajte „Igraj”: tek instalirana mapa ponekad se još skenira. Ako i dalje ne uspijeva, kopiranje mape igre možda nije dovršeno.",
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
                "choose_game": "Vyberte hru", "sort_disc": "Jako na disku", "sort_az": "Od A do Z",
                "tip_star": "Označte hru hvězdičkou a bude nahoře v hlavní nabídce.",
                "play_games": "Hrát", "steam": "Přidat do Steamu",
                "ok": "OK",
                "steam_none_title": "Není co přidat",
                "steam_none": "Nebyla nalezena žádná hra, kterou by bylo možné přidat do vaší knihovny Steam.",
                "steam_none_detail": "Nejprve nainstalujte hru z disku a pak to zkuste znovu.",
                "steam_missing_title": "Steam nebyl nalezen",
                "steam_missing": "V tomto počítači nebyl nalezen žádný profil Steam.",
                "steam_missing_detail": "Nainstalujte Steam, jednou se přihlaste a pak to zkuste znovu. Steam vytvoří potřebnou složku až po prvním přihlášení.",
                "steam_running_title": "Nejprve ukončete Steam",
                "steam_running": "Steam je spuštěný, proto zatím nebylo nic přidáno.",
                "steam_running_why": "Steam by změnu vrátil: seznam her mimo Steam drží v paměti a při zavření tuto kopii znovu zapíše.",
                "steam_running_detail": "Steam úplně ukončete: klikněte pravým tlačítkem na ikonu Steamu v oznamovací oblasti vedle hodin a zvolte Ukončit. Zavřít okno nestačí. Potom znovu stiskněte „Přidat do Steamu“.",
                "steam_added_title": "Přidáno do Steamu",
                "steam_added": "%s je nyní ve vaší knihovně Steam mezi hrami mimo Steam.",
                "steam_added_detail": "Objeví se tam při příštím spuštění Steamu.",
                "steam_already_title": "Už je ve Steamu",
                "steam_already": "%s už je ve vaší knihovně Steam.",
                "steam_already_detail": "Nic nebylo změněno. Pokud ji chcete přidat znovu, nejprve ji ze Steamu odeberte.",
                "steam_failed_title": "Přidání do Steamu se nezdařilo",
                "steam_blocked": "Seznam her mimo Steam se ve Steamu nepodařilo aktualizovat.",
                "steam_blocked_detail": "Steam úplně zavřete a zkuste to znovu. Nic nebylo změněno a předchozí seznam zůstal beze změny.",
                "steam_unread": "Seznam her mimo Steam se ve Steamu nepodařilo přečíst.",
                "steam_unread_detail": "Steam úplně zavřete a zkuste to znovu.",
                "uninstaller_detail": "Hru místo toho odinstalujte v systému Windows v Nastavení, v části Aplikace.",
                "bonus_detail": "Tento disk byl vytvořen bez složky s bonusovým obsahem.",
                "mods_detail": "Ve složce s módy na tomto disku nebyl nalezen žádný nástroj pro módy.",
                "looked_for": "Hledáno: %s",
                "looked_in": "Hledáno v:",
                "and_more": "... a dalších %d",
                "play_again": "Nejprve zkuste ještě jednou „Hrát“: čerstvě nainstalovaná složka se někdy ještě prověřuje. Pokud to stále selhává, kopírování složky hry možná nebylo dokončeno.",
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
                "choose_game": "Vælg dit spil", "sort_disc": "Som på disken", "sort_az": "A til Å",
                "tip_star": "Giv et spil en stjerne, så kommer det øverst i hovedmenuen.",
                "play_games": "Spil", "steam": "Føj til Steam",
                "ok": "OK",
                "steam_none_title": "Intet at tilføje",
                "steam_none": "Der blev ikke fundet noget spil at føje til dit Steam-bibliotek.",
                "steam_none_detail": "Installer spillet fra disken først, og prøv så igen.",
                "steam_missing_title": "Steam blev ikke fundet",
                "steam_missing": "Der blev ikke fundet nogen Steam-profil på denne pc.",
                "steam_missing_detail": "Installer Steam, og log ind én gang, og prøv så igen. Steam opretter først den mappe, der skal bruges, efter det første login.",
                "steam_running_title": "Afslut Steam først",
                "steam_running": "Steam kører, så der er ikke tilføjet noget endnu.",
                "steam_running_why": "Steam ville fortryde det: Steam holder sin liste over ikke-Steam-spil i hukommelsen og skriver den kopi tilbage, når programmet lukkes.",
                "steam_running_detail": "Afslut Steam helt: Højreklik på Steam-ikonet i meddelelsesområdet ved uret, og vælg Afslut. Det er ikke nok at lukke vinduet. Tryk derefter på »Føj til Steam« igen.",
                "steam_added_title": "Føjet til Steam",
                "steam_added": "%s er nu i dit Steam-bibliotek under ikke-Steam-spil.",
                "steam_added_detail": "Det ligger der, næste gang du starter Steam.",
                "steam_already_title": "Allerede i Steam",
                "steam_already": "%s er allerede i dit Steam-bibliotek.",
                "steam_already_detail": "Intet blev ændret. Fjern det fra Steam først, hvis du vil tilføje det igen.",
                "steam_failed_title": "Kunne ikke føje til Steam",
                "steam_blocked": "Steams liste over ikke-Steam-spil kunne ikke opdateres.",
                "steam_blocked_detail": "Luk Steam helt, og prøv igen. Intet blev ændret, og den tidligere liste er urørt.",
                "steam_unread": "Steams liste over ikke-Steam-spil kunne ikke læses.",
                "steam_unread_detail": "Luk Steam helt, og prøv igen.",
                "uninstaller_detail": "Afinstaller i stedet spillet under Indstillinger, Apps i Windows.",
                "bonus_detail": "Denne disk blev lavet uden en bonusmappe.",
                "mods_detail": "Der blev ikke fundet noget mod-værktøj i mods-mappen på denne disk.",
                "looked_for": "Ledte efter: %s",
                "looked_in": "Ledte i:",
                "and_more": "... og %d mere",
                "play_again": "Prøv »Spil« én gang til først: En nyinstalleret mappe bliver nogle gange stadig scannet. Hvis det bliver ved med at mislykkes, er spilmappen måske ikke færdig med at blive kopieret.",
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
                "choose_game": "Kies je spel", "sort_disc": "Zoals op de schijf", "sort_az": "A tot Z",
                "tip_star": "Geef een spel een ster en het komt bovenaan in het hoofdmenu.",
                "play_games": "Spelen", "steam": "Toevoegen aan Steam",
                "ok": "OK",
                "steam_none_title": "Niets om toe te voegen",
                "steam_none": "Er is geen spel gevonden om aan je Steam-bibliotheek toe te voegen.",
                "steam_none_detail": "Installeer eerst het spel vanaf de schijf en probeer het daarna opnieuw.",
                "steam_missing_title": "Steam niet gevonden",
                "steam_missing": "Er is geen Steam-profiel gevonden op deze pc.",
                "steam_missing_detail": "Installeer Steam, meld je één keer aan en probeer het daarna opnieuw. Steam maakt de benodigde map pas aan na de eerste aanmelding.",
                "steam_running_title": "Sluit Steam eerst af",
                "steam_running": "Steam is actief, dus er is nog niets toegevoegd.",
                "steam_running_why": "Steam zou het ongedaan maken: Steam houdt de lijst met niet-Steam-spellen in het geheugen en schrijft die kopie terug bij het afsluiten.",
                "steam_running_detail": "Sluit Steam helemaal af: klik met de rechtermuisknop op het Steam-pictogram in het meldingsgebied bij de klok en kies Afsluiten. Het venster sluiten is niet genoeg. Druk daarna opnieuw op ‘Toevoegen aan Steam’.",
                "steam_added_title": "Toegevoegd aan Steam",
                "steam_added": "%s staat nu in je Steam-bibliotheek, bij de niet-Steam-spellen.",
                "steam_added_detail": "Je ziet het daar de volgende keer dat je Steam start.",
                "steam_already_title": "Staat al in Steam",
                "steam_already": "%s staat al in je Steam-bibliotheek.",
                "steam_already_detail": "Er is niets gewijzigd. Verwijder het eerst uit Steam als je het opnieuw wilt toevoegen.",
                "steam_failed_title": "Toevoegen aan Steam mislukt",
                "steam_blocked": "De lijst met niet-Steam-spellen van Steam kon niet worden bijgewerkt.",
                "steam_blocked_detail": "Sluit Steam helemaal af en probeer het opnieuw. Er is niets gewijzigd en de vorige lijst is onaangeroerd.",
                "steam_unread": "De lijst met niet-Steam-spellen van Steam kon niet worden gelezen.",
                "steam_unread_detail": "Sluit Steam helemaal af en probeer het opnieuw.",
                "uninstaller_detail": "Verwijder het spel in plaats daarvan via Instellingen, Apps in Windows.",
                "bonus_detail": "Deze schijf is gemaakt zonder bonusmap.",
                "mods_detail": "Er is geen modtool gevonden in de modsmap op deze schijf.",
                "looked_for": "Gezocht naar: %s",
                "looked_in": "Gezocht in:",
                "and_more": "... en nog %d",
                "play_again": "Probeer eerst nog een keer ‘Spelen’: een net geïnstalleerde map wordt soms nog gescand. Blijft het mislukken, dan is de spelmap misschien nog niet helemaal gekopieerd.",
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
                "choose_game": "Choose your game", "sort_disc": "As on the disc", "sort_az": "A to Z",
                "tip_star": "Star a game to put it at the top of the main menu.",
                "play_games": "Play Games", "steam": "Add to Steam",
                "ok": "OK",
                "steam_none_title": "Nothing to add",
                "steam_none": "No game was found to put in your Steam library.",
                "steam_none_detail": "Install the game from the disc first, then try again.",
                "steam_missing_title": "Steam not found",
                "steam_missing": "No Steam profile was found on this PC.",
                "steam_missing_detail": "Install Steam and sign in once, then try again. Steam only creates the folder this needs after the first sign-in.",
                "steam_running_title": "Exit Steam first",
                "steam_running": "Steam is running, so nothing has been added yet.",
                "steam_running_why": "Steam would undo it: it keeps its list of non-Steam games in memory and writes that copy back out when it closes.",
                "steam_running_detail": "Exit Steam completely: right-click the Steam icon in the notification area, by the clock, and choose Exit. Closing the window is not enough. Then press Add to Steam again.",
                "steam_added_title": "Added to Steam",
                "steam_added": "%s is in your Steam library now, under non-Steam games.",
                "steam_added_detail": "It will be there the next time you start Steam.",
                "steam_already_title": "Already in Steam",
                "steam_already": "%s is already in your Steam library.",
                "steam_already_detail": "Nothing was changed. Remove it from Steam first if you want to add it again.",
                "steam_failed_title": "Could not add to Steam",
                "steam_blocked": "Steam's list of non-Steam games could not be updated.",
                "steam_blocked_detail": "Close Steam completely and try again. Nothing was changed, and the previous list is untouched.",
                "steam_unread": "Steam's list of non-Steam games could not be read.",
                "steam_unread_detail": "Close Steam completely and try again.",
                "uninstaller_detail": "Uninstall the game from Windows Settings, Apps instead.",
                "bonus_detail": "This disc was built without a bonus folder.",
                "mods_detail": "No mod tool was found in the mods folder on this disc.",
                "looked_for": "Looked for: %s",
                "looked_in": "Looked in:",
                "and_more": "... and %d more",
                "play_again": "Try Play once more first: a freshly installed folder is sometimes still being scanned. If it keeps failing, the game folder may not have finished copying.",
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
                "choose_game": "Valitse peli", "sort_disc": "Kuten levyllä", "sort_az": "A-Ö",
                "tip_star": "Merkitse peli tähdellä, niin se näkyy päävalikon ylimpänä.",
                "play_games": "Pelaa", "steam": "Lisää Steamiin",
                "ok": "OK",
                "steam_none_title": "Ei lisättävää",
                "steam_none": "Steam-kirjastoosi lisättävää peliä ei löytynyt.",
                "steam_none_detail": "Asenna peli ensin levyltä ja yritä sitten uudelleen.",
                "steam_missing_title": "Steamia ei löytynyt",
                "steam_missing": "Tältä tietokoneelta ei löytynyt Steam-profiilia.",
                "steam_missing_detail": "Asenna Steam ja kirjaudu sisään kerran, ja yritä sitten uudelleen. Steam luo tarvittavan kansion vasta ensimmäisen kirjautumisen jälkeen.",
                "steam_running_title": "Sulje Steam ensin",
                "steam_running": "Steam on käynnissä, joten mitään ei ole vielä lisätty.",
                "steam_running_why": "Steam kumoaisi muutoksen: se pitää luetteloa muista kuin Steam-peleistä muistissa ja kirjoittaa sen kopion takaisin sulkeutuessaan.",
                "steam_running_detail": "Sulje Steam kokonaan: napsauta hiiren kakkospainikkeella Steam-kuvaketta ilmaisinalueella kellon vieressä ja valitse Poistu. Ikkunan sulkeminen ei riitä. Paina sitten uudelleen ”Lisää Steamiin”.",
                "steam_added_title": "Lisätty Steamiin",
                "steam_added": "%s on nyt Steam-kirjastossasi muiden kuin Steam-pelien joukossa.",
                "steam_added_detail": "Se näkyy siellä, kun käynnistät Steamin seuraavan kerran.",
                "steam_already_title": "Jo Steamissa",
                "steam_already": "%s on jo Steam-kirjastossasi.",
                "steam_already_detail": "Mitään ei muutettu. Poista se ensin Steamista, jos haluat lisätä sen uudelleen.",
                "steam_failed_title": "Steamiin lisääminen epäonnistui",
                "steam_blocked": "Steamin luetteloa muista kuin Steam-peleistä ei voitu päivittää.",
                "steam_blocked_detail": "Sulje Steam kokonaan ja yritä uudelleen. Mitään ei muutettu, ja aiempi luettelo on ennallaan.",
                "steam_unread": "Steamin luetteloa muista kuin Steam-peleistä ei voitu lukea.",
                "steam_unread_detail": "Sulje Steam kokonaan ja yritä uudelleen.",
                "uninstaller_detail": "Poista pelin asennus sen sijaan Windowsin kohdasta Asetukset, Sovellukset.",
                "bonus_detail": "Tämä levy on tehty ilman bonuskansiota.",
                "mods_detail": "Tämän levyn mods-kansiosta ei löytynyt modityökalua.",
                "looked_for": "Etsittiin: %s",
                "looked_in": "Etsittiin kohteesta:",
                "and_more": "... ja %d muuta",
                "play_again": "Kokeile ensin vielä kerran ”Pelaa”: juuri asennettua kansiota tarkistetaan joskus vielä. Jos se ei vieläkään onnistu, pelikansion kopiointi on ehkä kesken.",
                "yes": "Kyllä", "no": "Ei", "cancel": "Peruuta"
            },
            "French": {
                "play": "Jouer", "bonus": "Contenu Bonus", "mods": "Mods", "compat": "Mode de compatibilité", "uninstall": "Désinstaller", "exit": "Quitter",
                "language": "Langue :", "error": "Erreur", "warning": "Avertissement",
                "game_not_found": "Exécutable du jeu introuvable !",
                "bonus_not_found": "Contenu bonus introuvable !",
                "mods_not_found": "Outil de mods introuvable !",
                "uninstaller_not_found": "Désinstallateur introuvable !",
                "confirm_uninstall": "Êtes-vous sûr de vouloir désinstaller ce jeu ?",
                "install": "Installer le jeu",
                "tip_install": "Lance l'installateur présent sur ce disque.",
                "tip_compat": "Lance le jeu avec des réglages pour les cartes graphiques anciennes ou non prises en charge.",
                "tip_bonus": "Ouvre le contenu supplémentaire présent sur ce disque.",
                "tip_mods": "Ouvre l'outil de mods présent sur ce disque.",
                "tip_steam": "Ajoute le jeu à votre bibliothèque Steam pour le lancer depuis celle-ci.",
                "tip_uninstall": "Supprime le jeu installé. Vos sauvegardes ne sont pas touchées.",
                "choose_game": "Choisissez votre jeu", "sort_disc": "Comme sur le disque", "sort_az": "De A à Z",
                "tip_star": "Ajoutez une étoile à un jeu pour le placer en haut du menu principal.",
                "play_games": "Jouer", "steam": "Ajouter à Steam",
                "ok": "OK",
                "steam_none_title": "Rien à ajouter",
                "steam_none": "Aucun jeu n'a été trouvé à ajouter à votre bibliothèque Steam.",
                "steam_none_detail": "Installez d'abord le jeu depuis le disque, puis réessayez.",
                "steam_missing_title": "Steam introuvable",
                "steam_missing": "Aucun profil Steam n'a été trouvé sur ce PC.",
                "steam_missing_detail": "Installez Steam et connectez-vous une fois, puis réessayez. Steam ne crée le dossier nécessaire qu'après la première connexion.",
                "steam_running_title": "Quittez d'abord Steam",
                "steam_running": "Steam est en cours d'exécution, rien n'a donc encore été ajouté.",
                "steam_running_why": "Steam annulerait l'ajout : il garde sa liste de jeux non-Steam en mémoire et réécrit cette copie à sa fermeture.",
                "steam_running_detail": "Quittez complètement Steam : faites un clic droit sur l'icône Steam dans la zone de notification, près de l'horloge, puis choisissez Quitter. Fermer la fenêtre ne suffit pas. Appuyez ensuite de nouveau sur « Ajouter à Steam ».",
                "steam_added_title": "Ajouté à Steam",
                "steam_added": "%s est maintenant dans votre bibliothèque Steam, parmi les jeux non-Steam.",
                "steam_added_detail": "Il y apparaîtra au prochain démarrage de Steam.",
                "steam_already_title": "Déjà dans Steam",
                "steam_already": "%s est déjà dans votre bibliothèque Steam.",
                "steam_already_detail": "Rien n'a été modifié. Retirez-le d'abord de Steam si vous voulez l'ajouter à nouveau.",
                "steam_failed_title": "Impossible d'ajouter à Steam",
                "steam_blocked": "La liste des jeux non-Steam de Steam n'a pas pu être mise à jour.",
                "steam_blocked_detail": "Fermez complètement Steam et réessayez. Rien n'a été modifié et la liste précédente est intacte.",
                "steam_unread": "La liste des jeux non-Steam de Steam n'a pas pu être lue.",
                "steam_unread_detail": "Fermez complètement Steam et réessayez.",
                "uninstaller_detail": "Désinstallez plutôt le jeu depuis Paramètres, Applications dans Windows.",
                "bonus_detail": "Ce disque a été créé sans dossier de bonus.",
                "mods_detail": "Aucun outil de mods n'a été trouvé dans le dossier mods de ce disque.",
                "looked_for": "Recherché : %s",
                "looked_in": "Emplacement recherché :",
                "and_more": "... et %d de plus",
                "play_again": "Essayez d'abord « Jouer » une nouvelle fois : un dossier tout juste installé est parfois encore en cours d'analyse. Si l'échec persiste, la copie du dossier du jeu n'est peut-être pas terminée.",
                "yes": "Oui", "no": "Non", "cancel": "Annuler"
            },
            "German": {
                "play": "Spielen", "bonus": "Bonusinhalte", "mods": "Mods", "compat": "Kompatibilitätsmodus", "uninstall": "Deinstallieren", "exit": "Beenden",
                "language": "Sprache:", "error": "Fehler", "warning": "Warnung",
                "game_not_found": "Spiel-Datei nicht gefunden!",
                "bonus_not_found": "Bonusinhalte nicht gefunden!",
                "mods_not_found": "Mod-Tool nicht gefunden!",
                "uninstaller_not_found": "Deinstallationsprogramm nicht gefunden!",
                "confirm_uninstall": "Bist du sicher, dass du dieses Spiel deinstallieren möchtest?",
                "install": "Spiel installieren",
                "tip_install": "Startet das Installationsprogramm auf dieser Disc.",
                "tip_compat": "Startet das Spiel mit Einstellungen für ältere oder nicht unterstützte Grafikhardware.",
                "tip_bonus": "Öffnet das Bonusmaterial auf dieser Disc.",
                "tip_mods": "Öffnet das Mod-Werkzeug auf dieser Disc.",
                "tip_steam": "Fügt das Spiel deiner Steam-Bibliothek hinzu, damit du es von dort starten kannst.",
                "tip_uninstall": "Entfernt das installierte Spiel. Deine Spielstände bleiben erhalten.",
                "choose_game": "Wähle dein Spiel", "sort_disc": "Wie auf der Disc", "sort_az": "A bis Z",
                "tip_star": "Markiere ein Spiel mit einem Stern, dann steht es oben im Hauptmenü.",
                "play_games": "Spielen", "steam": "Zu Steam hinzufügen",
                "ok": "OK",
                "steam_none_title": "Nichts hinzuzufügen",
                "steam_none": "Es wurde kein Spiel gefunden, das deiner Steam-Bibliothek hinzugefügt werden kann.",
                "steam_none_detail": "Installiere zuerst das Spiel von der Disc und versuche es dann erneut.",
                "steam_missing_title": "Steam nicht gefunden",
                "steam_missing": "Auf diesem PC wurde kein Steam-Profil gefunden.",
                "steam_missing_detail": "Installiere Steam, melde dich einmal an und versuche es dann erneut. Steam legt den benötigten Ordner erst nach der ersten Anmeldung an.",
                "steam_running_title": "Beende zuerst Steam",
                "steam_running": "Steam läuft, deshalb wurde noch nichts hinzugefügt.",
                "steam_running_why": "Steam würde die Änderung rückgängig machen: Steam hält seine Liste der Nicht-Steam-Spiele im Arbeitsspeicher und schreibt diese Kopie beim Beenden zurück.",
                "steam_running_detail": "Beende Steam vollständig: Klicke mit der rechten Maustaste auf das Steam-Symbol im Infobereich neben der Uhr und wähle Beenden. Das Fenster zu schließen reicht nicht. Drücke danach erneut auf „Zu Steam hinzufügen“.",
                "steam_added_title": "Zu Steam hinzugefügt",
                "steam_added": "%s ist jetzt in deiner Steam-Bibliothek, unter den Nicht-Steam-Spielen.",
                "steam_added_detail": "Beim nächsten Start von Steam ist es dort zu finden.",
                "steam_already_title": "Bereits in Steam",
                "steam_already": "%s ist bereits in deiner Steam-Bibliothek.",
                "steam_already_detail": "Es wurde nichts geändert. Entferne es zuerst aus Steam, wenn du es erneut hinzufügen möchtest.",
                "steam_failed_title": "Hinzufügen zu Steam fehlgeschlagen",
                "steam_blocked": "Die Liste der Nicht-Steam-Spiele in Steam konnte nicht aktualisiert werden.",
                "steam_blocked_detail": "Schließe Steam vollständig und versuche es erneut. Es wurde nichts geändert, die bisherige Liste ist unverändert.",
                "steam_unread": "Die Liste der Nicht-Steam-Spiele in Steam konnte nicht gelesen werden.",
                "steam_unread_detail": "Schließe Steam vollständig und versuche es erneut.",
                "uninstaller_detail": "Deinstalliere das Spiel stattdessen in Windows unter Einstellungen, Apps.",
                "bonus_detail": "Diese Disc wurde ohne Bonusordner erstellt.",
                "mods_detail": "Im Mods-Ordner dieser Disc wurde kein Mod-Werkzeug gefunden.",
                "looked_for": "Gesucht nach: %s",
                "looked_in": "Gesucht in:",
                "and_more": "... und %d weitere",
                "play_again": "Versuche es zuerst noch einmal mit „Spielen“: Ein frisch installierter Ordner wird manchmal noch geprüft. Wenn es weiterhin fehlschlägt, wurde der Spielordner vielleicht nicht vollständig kopiert.",
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
                "choose_game": "Επιλέξτε παιχνίδι", "sort_disc": "Όπως στον δίσκο", "sort_az": "Α έως Ω",
                "tip_star": "Βάλτε αστέρι σε ένα παιχνίδι για να εμφανιστεί στην κορυφή του κύριου μενού.",
                "play_games": "Παίξε", "steam": "Προσθήκη στο Steam",
                "ok": "OK",
                "steam_none_title": "Τίποτα για προσθήκη",
                "steam_none": "Δεν βρέθηκε παιχνίδι για προσθήκη στη βιβλιοθήκη Steam σας.",
                "steam_none_detail": "Εγκαταστήστε πρώτα το παιχνίδι από τον δίσκο και δοκιμάστε ξανά.",
                "steam_missing_title": "Το Steam δεν βρέθηκε",
                "steam_missing": "Δεν βρέθηκε προφίλ Steam σε αυτόν τον υπολογιστή.",
                "steam_missing_detail": "Εγκαταστήστε το Steam και συνδεθείτε μία φορά, και μετά δοκιμάστε ξανά. Το Steam δημιουργεί τον φάκελο που χρειάζεται μόνο μετά την πρώτη σύνδεση.",
                "steam_running_title": "Τερματίστε πρώτα το Steam",
                "steam_running": "Το Steam εκτελείται, οπότε δεν έχει προστεθεί τίποτα ακόμα.",
                "steam_running_why": "Το Steam θα αναιρούσε την αλλαγή: κρατά τη λίστα με τα παιχνίδια εκτός Steam στη μνήμη και γράφει ξανά αυτό το αντίγραφο όταν κλείνει.",
                "steam_running_detail": "Τερματίστε πλήρως το Steam: κάντε δεξί κλικ στο εικονίδιο του Steam στην περιοχή ειδοποιήσεων, δίπλα στο ρολόι, και επιλέξτε Έξοδος. Το κλείσιμο του παραθύρου δεν αρκεί. Μετά πατήστε ξανά «Προσθήκη στο Steam».",
                "steam_added_title": "Προστέθηκε στο Steam",
                "steam_added": "%s βρίσκεται πλέον στη βιβλιοθήκη Steam σας, στα παιχνίδια εκτός Steam.",
                "steam_added_detail": "Θα εμφανίζεται εκεί την επόμενη φορά που θα ανοίξετε το Steam.",
                "steam_already_title": "Ήδη στο Steam",
                "steam_already": "%s βρίσκεται ήδη στη βιβλιοθήκη Steam σας.",
                "steam_already_detail": "Δεν άλλαξε τίποτα. Αφαιρέστε το πρώτα από το Steam αν θέλετε να το προσθέσετε ξανά.",
                "steam_failed_title": "Δεν ήταν δυνατή η προσθήκη στο Steam",
                "steam_blocked": "Δεν ήταν δυνατή η ενημέρωση της λίστας του Steam με τα παιχνίδια εκτός Steam.",
                "steam_blocked_detail": "Κλείστε εντελώς το Steam και δοκιμάστε ξανά. Δεν άλλαξε τίποτα και η προηγούμενη λίστα έμεινε ανέπαφη.",
                "steam_unread": "Δεν ήταν δυνατή η ανάγνωση της λίστας του Steam με τα παιχνίδια εκτός Steam.",
                "steam_unread_detail": "Κλείστε εντελώς το Steam και δοκιμάστε ξανά.",
                "uninstaller_detail": "Απεγκαταστήστε το παιχνίδι από τις Ρυθμίσεις των Windows, στις Εφαρμογές.",
                "bonus_detail": "Αυτός ο δίσκος δημιουργήθηκε χωρίς φάκελο bonus.",
                "mods_detail": "Δεν βρέθηκε εργαλείο mods στον φάκελο mods αυτού του δίσκου.",
                "looked_for": "Αναζητήθηκε: %s",
                "looked_in": "Αναζήτηση σε:",
                "and_more": "... και %d ακόμη",
                "play_again": "Δοκιμάστε πρώτα ξανά το «Παίξε»: ένας φάκελος που μόλις εγκαταστάθηκε μερικές φορές ελέγχεται ακόμα. Αν συνεχίσει να αποτυγχάνει, ίσως δεν έχει ολοκληρωθεί η αντιγραφή του φακέλου του παιχνιδιού.",
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
                "choose_game": "בחר את המשחק שלך", "sort_disc": "כמו בדיסק", "sort_az": "לפי שם",
                "tip_star": "סמן משחק בכוכב כדי שיופיע בראש התפריט הראשי.",
                "play_games": "שחק", "steam": "הוסף ל-Steam",
                "ok": "אישור",
                "steam_none_title": "אין מה להוסיף",
                "steam_none": "לא נמצא משחק להוספה לספריית Steam שלך.",
                "steam_none_detail": "התקן קודם את המשחק מהתקליטור, ואז נסה שוב.",
                "steam_missing_title": "Steam לא נמצא",
                "steam_missing": "לא נמצא פרופיל Steam במחשב הזה.",
                "steam_missing_detail": "התקן את Steam והתחבר פעם אחת, ואז נסה שוב. Steam יוצר את התיקייה הדרושה רק אחרי ההתחברות הראשונה.",
                "steam_running_title": "צא קודם מ-Steam",
                "steam_running": "Steam פועל, ולכן עדיין לא נוסף דבר.",
                "steam_running_why": "Steam היה מבטל את ההוספה: הוא שומר בזיכרון את רשימת המשחקים שאינם מ-Steam וכותב את העותק הזה בחזרה כשהוא נסגר.",
                "steam_running_detail": "צא מ-Steam לגמרי: לחץ לחיצה ימנית על סמל Steam באזור ההודעות, ליד השעון, ובחר Exit. סגירת החלון אינה מספיקה. לאחר מכן לחץ שוב על הוסף ל-Steam.",
                "steam_added_title": "נוסף ל-Steam",
                "steam_added": "%s בספריית Steam שלך עכשיו, תחת משחקים שאינם מ-Steam.",
                "steam_added_detail": "זה יופיע שם בפעם הבאה שתפעיל את Steam.",
                "steam_already_title": "כבר נמצא ב-Steam",
                "steam_already": "%s כבר בספריית Steam שלך.",
                "steam_already_detail": "לא שונה דבר. הסר אותו קודם מ-Steam אם ברצונך להוסיף אותו שוב.",
                "steam_failed_title": "לא ניתן להוסיף ל-Steam",
                "steam_blocked": "לא ניתן היה לעדכן את רשימת המשחקים שאינם מ-Steam ב-Steam.",
                "steam_blocked_detail": "סגור את Steam לגמרי ונסה שוב. לא שונה דבר, והרשימה הקודמת לא נפגעה.",
                "steam_unread": "לא ניתן היה לקרוא את רשימת המשחקים שאינם מ-Steam ב-Steam.",
                "steam_unread_detail": "סגור את Steam לגמרי ונסה שוב.",
                "uninstaller_detail": "במקום זאת, הסר את המשחק דרך הגדרות, אפליקציות ב-Windows.",
                "bonus_detail": "התקליטור הזה נבנה ללא תיקיית בונוס.",
                "mods_detail": "לא נמצא כלי מודים בתיקיית המודים שבתקליטור הזה.",
                "looked_for": "חיפוש אחר: %s",
                "looked_in": "חיפוש ב:",
                "and_more": "... ועוד %d",
                "play_again": "נסה קודם ללחוץ על שחק פעם נוספת: תיקייה שהותקנה זה עתה נסרקת לפעמים עדיין. אם זה ממשיך להיכשל, ייתכן שהעתקת תיקיית המשחק לא הסתיימה.",
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
                "choose_game": "अपना गेम चुनें", "sort_disc": "डिस्क के क्रम में", "sort_az": "नाम के क्रम में",
                "tip_star": "किसी गेम पर स्टार लगाएँ ताकि वह मुख्य मेनू में सबसे ऊपर दिखे।",
                "play_games": "गेम खेलें", "steam": "Steam में जोड़ें",
                "ok": "ठीक है",
                "steam_none_title": "जोड़ने के लिए कुछ नहीं",
                "steam_none": "आपकी Steam लाइब्रेरी में जोड़ने के लिए कोई गेम नहीं मिला।",
                "steam_none_detail": "पहले डिस्क से गेम इंस्टॉल करें, फिर दोबारा कोशिश करें।",
                "steam_missing_title": "Steam नहीं मिला",
                "steam_missing": "इस PC पर कोई Steam प्रोफ़ाइल नहीं मिली।",
                "steam_missing_detail": "Steam इंस्टॉल करें और एक बार साइन इन करें, फिर दोबारा कोशिश करें। Steam इसके लिए ज़रूरी फ़ोल्डर पहली बार साइन इन करने के बाद ही बनाता है।",
                "steam_running_title": "पहले Steam से बाहर निकलें",
                "steam_running": "Steam चल रहा है, इसलिए अभी तक कुछ नहीं जोड़ा गया है।",
                "steam_running_why": "Steam इसे पलट देगा: वह गैर-Steam गेम्स की अपनी सूची मेमोरी में रखता है और बंद होते समय वही कॉपी वापस लिख देता है।",
                "steam_running_detail": "Steam से पूरी तरह बाहर निकलें: घड़ी के पास सूचना क्षेत्र में Steam आइकन पर राइट-क्लिक करें और Exit चुनें। सिर्फ़ विंडो बंद करना काफ़ी नहीं है। फिर ‘Steam में जोड़ें’ दोबारा दबाएँ।",
                "steam_added_title": "Steam में जोड़ा गया",
                "steam_added": "%s अब आपकी Steam लाइब्रेरी में, गैर-Steam गेम्स के अंतर्गत है।",
                "steam_added_detail": "अगली बार Steam शुरू करने पर यह वहाँ दिखेगा।",
                "steam_already_title": "पहले से Steam में है",
                "steam_already": "%s पहले से आपकी Steam लाइब्रेरी में है।",
                "steam_already_detail": "कुछ भी नहीं बदला गया। अगर आप इसे फिर से जोड़ना चाहते हैं, तो पहले इसे Steam से हटाएँ।",
                "steam_failed_title": "Steam में नहीं जोड़ा जा सका",
                "steam_blocked": "Steam की गैर-Steam गेम्स की सूची अपडेट नहीं की जा सकी।",
                "steam_blocked_detail": "Steam को पूरी तरह बंद करें और दोबारा कोशिश करें। कुछ भी नहीं बदला गया, और पिछली सूची जस की तस है।",
                "steam_unread": "Steam की गैर-Steam गेम्स की सूची पढ़ी नहीं जा सकी।",
                "steam_unread_detail": "Steam को पूरी तरह बंद करें और दोबारा कोशिश करें।",
                "uninstaller_detail": "इसके बजाय Windows की सेटिंग्स में ऐप्स से गेम अनइंस्टॉल करें।",
                "bonus_detail": "यह डिस्क बोनस फ़ोल्डर के बिना बनाई गई थी।",
                "mods_detail": "इस डिस्क के mods फ़ोल्डर में कोई मॉड टूल नहीं मिला।",
                "looked_for": "खोजा गया: %s",
                "looked_in": "यहाँ खोजा गया:",
                "and_more": "... और %d",
                "play_again": "पहले एक बार और ‘खेल खेलें’ आज़माएँ: नया इंस्टॉल हुआ फ़ोल्डर कभी-कभी अभी भी स्कैन हो रहा होता है। अगर यह बार-बार विफल हो, तो हो सकता है कि गेम फ़ोल्डर की कॉपी पूरी न हुई हो।",
                "yes": "हाँ", "no": "नहीं", "cancel": "रद्द करें"
            },
            "Hungarian": {
                "play": "Játék", "bonus": "Bónusz tartalom", "mods": "Modok", "compat": "Kompatibilitási mód", "uninstall": "Eltávolítás", "exit": "Kilépés",
                "language": "Nyelv:", "error": "Hiba", "warning": "Figyelmeztetés",
                "game_not_found": "A játék futtatható fájlja nem található!",
                "bonus_not_found": "A bónusz tartalom nem található!",
                "mods_not_found": "A mod eszköz nem található!",
                "uninstaller_not_found": "Az eltávolító nem található!",
                "confirm_uninstall": "Biztosan el szeretnéd távolítani ezt a játékot?",
                "install": "Játék telepítése",
                "tip_install": "Elindítja a lemezen található telepítőt.",
                "tip_compat": "Elindítja a játékot régebbi vagy nem támogatott videokártyához való beállításokkal.",
                "tip_bonus": "Megnyitja a lemezen található bónusz tartalmat.",
                "tip_mods": "Megnyitja a lemezen található mod eszközt.",
                "tip_steam": "Hozzáadja a játékot a Steam könyvtáradhoz, hogy onnan indíthasd.",
                "tip_uninstall": "Eltávolítja a telepített játékot. A mentéseid érintetlenek maradnak.",
                "choose_game": "Válaszd ki a játékot", "sort_disc": "Ahogy a lemezen", "sort_az": "A-tól Z-ig",
                "tip_star": "Jelölj meg egy játékot csillaggal, és a főmenü tetejére kerül.",
                "play_games": "Játék", "steam": "Hozzáadás a Steamhez",
                "ok": "OK",
                "steam_none_title": "Nincs mit hozzáadni",
                "steam_none": "Nem található játék, amelyet hozzá lehetne adni a Steam könyvtáradhoz.",
                "steam_none_detail": "Előbb telepítsd a játékot a lemezről, aztán próbáld újra.",
                "steam_missing_title": "A Steam nem található",
                "steam_missing": "Ezen a gépen nem található Steam-profil.",
                "steam_missing_detail": "Telepítsd a Steamet, és jelentkezz be egyszer, aztán próbáld újra. A Steam csak az első bejelentkezés után hozza létre a szükséges mappát.",
                "steam_running_title": "Előbb lépj ki a Steamből",
                "steam_running": "A Steam fut, ezért még semmi sem lett hozzáadva.",
                "steam_running_why": "A Steam visszacsinálná: a nem Steames játékok listáját a memóriában tartja, és bezáráskor ezt a példányt írja vissza.",
                "steam_running_detail": "Lépj ki teljesen a Steamből: kattints jobb gombbal a Steam ikonjára az értesítési területen, az óra mellett, és válaszd a Kilépés lehetőséget. Az ablak bezárása nem elég. Ezután nyomd meg újra a Hozzáadás a Steamhez gombot.",
                "steam_added_title": "Hozzáadva a Steamhez",
                "steam_added": "%s mostantól a Steam könyvtáradban van, a nem Steames játékok között.",
                "steam_added_detail": "A Steam következő indításakor ott lesz.",
                "steam_already_title": "Már a Steamben van",
                "steam_already": "%s már a Steam könyvtáradban van.",
                "steam_already_detail": "Semmi sem változott. Ha újra hozzá szeretnéd adni, előbb távolítsd el a Steamből.",
                "steam_failed_title": "Nem sikerült hozzáadni a Steamhez",
                "steam_blocked": "A Steam nem Steames játékokat tartalmazó listáját nem sikerült frissíteni.",
                "steam_blocked_detail": "Zárd be teljesen a Steamet, és próbáld újra. Semmi sem változott, az előző lista érintetlen.",
                "steam_unread": "A Steam nem Steames játékokat tartalmazó listáját nem sikerült beolvasni.",
                "steam_unread_detail": "Zárd be teljesen a Steamet, és próbáld újra.",
                "uninstaller_detail": "Ehelyett a Windows Gépház, Alkalmazások részében távolítsd el a játékot.",
                "bonus_detail": "Ez a lemez bónuszmappa nélkül készült.",
                "mods_detail": "A lemez mods mappájában nem található mod eszköz.",
                "looked_for": "Keresés: %s",
                "looked_in": "Keresés helye:",
                "and_more": "... és még %d",
                "play_again": "Előbb próbáld meg még egyszer a Játék gombot: egy frissen telepített mappát néha még ellenőriz a rendszer. Ha továbbra sem sikerül, lehet, hogy a játék mappájának másolása nem fejeződött be.",
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
                "choose_game": "Pilih game Anda", "sort_disc": "Sesuai urutan disk", "sort_az": "A sampai Z",
                "tip_star": "Beri bintang pada game agar muncul paling atas di menu utama.",
                "play_games": "Main Game", "steam": "Tambahkan ke Steam",
                "ok": "OK",
                "steam_none_title": "Tidak ada yang ditambahkan",
                "steam_none": "Tidak ditemukan game untuk dimasukkan ke pustaka Steam Anda.",
                "steam_none_detail": "Pasang game dari disk terlebih dahulu, lalu coba lagi.",
                "steam_missing_title": "Steam tidak ditemukan",
                "steam_missing": "Tidak ditemukan profil Steam di PC ini.",
                "steam_missing_detail": "Pasang Steam dan masuk sekali, lalu coba lagi. Steam baru membuat folder yang dibutuhkan setelah masuk pertama kali.",
                "steam_running_title": "Keluar dari Steam dulu",
                "steam_running": "Steam sedang berjalan, jadi belum ada yang ditambahkan.",
                "steam_running_why": "Steam akan membatalkannya: Steam menyimpan daftar game non-Steam di memori dan menulis ulang salinan itu saat ditutup.",
                "steam_running_detail": "Keluar dari Steam sepenuhnya: klik kanan ikon Steam di area pemberitahuan, di dekat jam, lalu pilih Keluar. Menutup jendela saja tidak cukup. Lalu tekan Tambahkan ke Steam lagi.",
                "steam_added_title": "Ditambahkan ke Steam",
                "steam_added": "%s sekarang ada di pustaka Steam Anda, di bagian game non-Steam.",
                "steam_added_detail": "Game akan muncul di sana saat Anda menjalankan Steam berikutnya.",
                "steam_already_title": "Sudah ada di Steam",
                "steam_already": "%s sudah ada di pustaka Steam Anda.",
                "steam_already_detail": "Tidak ada yang diubah. Hapus dulu dari Steam jika Anda ingin menambahkannya lagi.",
                "steam_failed_title": "Tidak dapat menambahkan ke Steam",
                "steam_blocked": "Daftar game non-Steam milik Steam tidak dapat diperbarui.",
                "steam_blocked_detail": "Tutup Steam sepenuhnya, lalu coba lagi. Tidak ada yang diubah, dan daftar sebelumnya tetap utuh.",
                "steam_unread": "Daftar game non-Steam milik Steam tidak dapat dibaca.",
                "steam_unread_detail": "Tutup Steam sepenuhnya, lalu coba lagi.",
                "uninstaller_detail": "Sebagai gantinya, hapus instalan game dari Pengaturan, Aplikasi di Windows.",
                "bonus_detail": "Disk ini dibuat tanpa folder bonus.",
                "mods_detail": "Tidak ditemukan alat mod di folder mods pada disk ini.",
                "looked_for": "Mencari: %s",
                "looked_in": "Mencari di:",
                "and_more": "... dan %d lainnya",
                "play_again": "Coba Main Game sekali lagi dulu: folder yang baru dipasang terkadang masih dipindai. Jika terus gagal, mungkin folder game belum selesai disalin.",
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
                "choose_game": "Scegli il tuo gioco", "sort_disc": "Come sul disco", "sort_az": "Dalla A alla Z",
                "tip_star": "Aggiungi una stella a un gioco per metterlo in cima al menu principale.",
                "play_games": "Gioca", "steam": "Aggiungi a Steam",
                "ok": "OK",
                "steam_none_title": "Niente da aggiungere",
                "steam_none": "Non è stato trovato nessun gioco da aggiungere alla tua libreria Steam.",
                "steam_none_detail": "Installa prima il gioco dal disco, poi riprova.",
                "steam_missing_title": "Steam non trovato",
                "steam_missing": "Su questo PC non è stato trovato nessun profilo Steam.",
                "steam_missing_detail": "Installa Steam ed effettua l'accesso una volta, poi riprova. Steam crea la cartella necessaria solo dopo il primo accesso.",
                "steam_running_title": "Prima esci da Steam",
                "steam_running": "Steam è in esecuzione, quindi non è stato ancora aggiunto nulla.",
                "steam_running_why": "Steam annullerebbe la modifica: tiene in memoria il suo elenco di giochi non Steam e lo riscrive alla chiusura.",
                "steam_running_detail": "Esci completamente da Steam: fai clic con il pulsante destro sull'icona di Steam nell'area di notifica, vicino all'orologio, e scegli Esci. Chiudere la finestra non basta. Poi premi di nuovo «Aggiungi a Steam».",
                "steam_added_title": "Aggiunto a Steam",
                "steam_added": "%s è ora nella tua libreria Steam, tra i giochi non Steam.",
                "steam_added_detail": "Lo troverai lì al prossimo avvio di Steam.",
                "steam_already_title": "Già in Steam",
                "steam_already": "%s è già nella tua libreria Steam.",
                "steam_already_detail": "Non è stato modificato nulla. Se vuoi aggiungerlo di nuovo, rimuovilo prima da Steam.",
                "steam_failed_title": "Impossibile aggiungere a Steam",
                "steam_blocked": "Non è stato possibile aggiornare l'elenco dei giochi non Steam di Steam.",
                "steam_blocked_detail": "Chiudi completamente Steam e riprova. Non è stato modificato nulla e l'elenco precedente è intatto.",
                "steam_unread": "Non è stato possibile leggere l'elenco dei giochi non Steam di Steam.",
                "steam_unread_detail": "Chiudi completamente Steam e riprova.",
                "uninstaller_detail": "Disinstalla invece il gioco da Impostazioni, App di Windows.",
                "bonus_detail": "Questo disco è stato creato senza una cartella bonus.",
                "mods_detail": "Nella cartella mods di questo disco non è stato trovato nessuno strumento per le mod.",
                "looked_for": "Cercato: %s",
                "looked_in": "Cercato in:",
                "and_more": "... e altre %d",
                "play_again": "Prova prima ancora una volta «Gioca»: una cartella appena installata a volte è ancora in fase di scansione. Se continua a non funzionare, la copia della cartella del gioco potrebbe non essere stata completata.",
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
                "choose_game": "ゲームを選択", "sort_disc": "ディスクの順", "sort_az": "名前順",
                "tip_star": "星を付けたゲームはメインメニューの一番上に表示されます。",
                "play_games": "ゲームを開始", "steam": "Steamに追加",
                "ok": "OK",
                "steam_none_title": "追加するものがありません",
                "steam_none": "Steamライブラリに追加できるゲームが見つかりませんでした。",
                "steam_none_detail": "先にディスクからゲームをインストールしてから、もう一度お試しください。",
                "steam_missing_title": "Steamが見つかりません",
                "steam_missing": "このPCにSteamのプロフィールが見つかりませんでした。",
                "steam_missing_detail": "Steamをインストールして一度サインインしてから、もう一度お試しください。必要なフォルダーは、最初のサインイン後にSteamが作成します。",
                "steam_running_title": "先にSteamを終了してください",
                "steam_running": "Steamが起動中のため、まだ何も追加されていません。",
                "steam_running_why": "このままではSteamが変更を元に戻してしまいます。Steamは非Steamゲームの一覧をメモリに保持し、終了時にその内容を書き戻すためです。",
                "steam_running_detail": "Steamを完全に終了してください。時計の横にある通知領域のSteamアイコンを右クリックし、「終了」を選びます。ウィンドウを閉じるだけでは不十分です。その後、もう一度「Steamに追加」を押してください。",
                "steam_added_title": "Steamに追加しました",
                "steam_added": "%s をSteamライブラリの非Steamゲームに追加しました。",
                "steam_added_detail": "次回Steamを起動したときに表示されます。",
                "steam_already_title": "すでにSteamにあります",
                "steam_already": "%s はすでにSteamライブラリにあります。",
                "steam_already_detail": "何も変更していません。もう一度追加する場合は、先にSteamから削除してください。",
                "steam_failed_title": "Steamに追加できませんでした",
                "steam_blocked": "Steamの非Steamゲーム一覧を更新できませんでした。",
                "steam_blocked_detail": "Steamを完全に終了してから、もう一度お試しください。何も変更しておらず、以前の一覧はそのままです。",
                "steam_unread": "Steamの非Steamゲーム一覧を読み込めませんでした。",
                "steam_unread_detail": "Steamを完全に終了してから、もう一度お試しください。",
                "uninstaller_detail": "代わりにWindowsの「設定」の「アプリ」からゲームをアンインストールしてください。",
                "bonus_detail": "このディスクはボーナスフォルダーなしで作成されています。",
                "mods_detail": "このディスクのmodsフォルダーにMODツールが見つかりませんでした。",
                "looked_for": "検索対象: %s",
                "looked_in": "検索場所:",
                "and_more": "…ほか %d 件",
                "play_again": "まずもう一度「ゲームを開始」をお試しください。インストールしたばかりのフォルダーは、まだスキャン中のことがあります。それでも失敗する場合は、ゲームフォルダーのコピーが完了していない可能性があります。",
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
                "choose_game": "게임 선택", "sort_disc": "디스크 순서", "sort_az": "이름순",
                "tip_star": "게임에 별표를 하면 메인 메뉴 맨 위에 표시됩니다.",
                "play_games": "게임 시작", "steam": "Steam에 추가",
                "ok": "확인",
                "steam_none_title": "추가할 항목 없음",
                "steam_none": "Steam 라이브러리에 추가할 게임을 찾지 못했습니다.",
                "steam_none_detail": "먼저 디스크에서 게임을 설치한 다음 다시 시도하세요.",
                "steam_missing_title": "Steam을 찾을 수 없음",
                "steam_missing": "이 PC에서 Steam 프로필을 찾지 못했습니다.",
                "steam_missing_detail": "Steam을 설치하고 한 번 로그인한 다음 다시 시도하세요. Steam은 처음 로그인한 후에야 필요한 폴더를 만듭니다.",
                "steam_running_title": "먼저 Steam을 종료하세요",
                "steam_running": "Steam이 실행 중이어서 아직 아무것도 추가하지 않았습니다.",
                "steam_running_why": "그대로 두면 Steam이 변경 내용을 되돌립니다. Steam은 비 Steam 게임 목록을 메모리에 보관하다가 종료할 때 그 사본을 다시 저장합니다.",
                "steam_running_detail": "Steam을 완전히 종료하세요. 시계 옆 알림 영역에서 Steam 아이콘을 마우스 오른쪽 버튼으로 클릭하고 ‘종료’를 선택합니다. 창을 닫는 것만으로는 부족합니다. 그런 다음 ‘Steam에 추가’를 다시 누르세요.",
                "steam_added_title": "Steam에 추가됨",
                "steam_added": "%s 게임이 이제 Steam 라이브러리의 비 Steam 게임 항목에 있습니다.",
                "steam_added_detail": "다음에 Steam을 시작하면 표시됩니다.",
                "steam_already_title": "이미 Steam에 있음",
                "steam_already": "%s 게임은 이미 Steam 라이브러리에 있습니다.",
                "steam_already_detail": "아무것도 변경하지 않았습니다. 다시 추가하려면 먼저 Steam에서 제거하세요.",
                "steam_failed_title": "Steam에 추가할 수 없음",
                "steam_blocked": "Steam의 비 Steam 게임 목록을 업데이트할 수 없습니다.",
                "steam_blocked_detail": "Steam을 완전히 종료한 다음 다시 시도하세요. 아무것도 변경하지 않았으며 이전 목록은 그대로입니다.",
                "steam_unread": "Steam의 비 Steam 게임 목록을 읽을 수 없습니다.",
                "steam_unread_detail": "Steam을 완전히 종료한 다음 다시 시도하세요.",
                "uninstaller_detail": "대신 Windows 설정의 앱에서 게임을 제거하세요.",
                "bonus_detail": "이 디스크는 보너스 폴더 없이 만들어졌습니다.",
                "mods_detail": "이 디스크의 mods 폴더에서 모드 도구를 찾지 못했습니다.",
                "looked_for": "찾으려던 항목: %s",
                "looked_in": "검색한 위치:",
                "and_more": "... 외 %d개",
                "play_again": "먼저 ‘게임 시작’을 한 번 더 눌러 보세요. 방금 설치한 폴더는 아직 검사 중일 때가 있습니다. 계속 실패하면 게임 폴더 복사가 끝나지 않았을 수 있습니다.",
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
                "choose_game": "Velg spillet ditt", "sort_disc": "Som på platen", "sort_az": "A til Å",
                "tip_star": "Gi et spill en stjerne, så kommer det øverst på hovedmenyen.",
                "play_games": "Spill", "steam": "Legg til i Steam",
                "ok": "OK",
                "steam_none_title": "Ingenting å legge til",
                "steam_none": "Fant ikke noe spill å legge til i Steam-biblioteket ditt.",
                "steam_none_detail": "Installer spillet fra platen først, og prøv deretter på nytt.",
                "steam_missing_title": "Fant ikke Steam",
                "steam_missing": "Fant ingen Steam-profil på denne PC-en.",
                "steam_missing_detail": "Installer Steam og logg på én gang, og prøv deretter på nytt. Steam oppretter mappen som trengs først etter den første påloggingen.",
                "steam_running_title": "Avslutt Steam først",
                "steam_running": "Steam kjører, så ingenting er lagt til ennå.",
                "steam_running_why": "Steam ville angret det: Steam holder listen over ikke-Steam-spill i minnet og skriver den kopien tilbake når programmet lukkes.",
                "steam_running_detail": "Avslutt Steam helt: Høyreklikk på Steam-ikonet i varslingsområdet ved klokken, og velg Avslutt. Det er ikke nok å lukke vinduet. Trykk deretter på «Legg til i Steam» igjen.",
                "steam_added_title": "Lagt til i Steam",
                "steam_added": "%s ligger nå i Steam-biblioteket ditt, under ikke-Steam-spill.",
                "steam_added_detail": "Det vil være der neste gang du starter Steam.",
                "steam_already_title": "Allerede i Steam",
                "steam_already": "%s ligger allerede i Steam-biblioteket ditt.",
                "steam_already_detail": "Ingenting ble endret. Fjern det fra Steam først hvis du vil legge det til på nytt.",
                "steam_failed_title": "Kunne ikke legge til i Steam",
                "steam_blocked": "Steams liste over ikke-Steam-spill kunne ikke oppdateres.",
                "steam_blocked_detail": "Lukk Steam helt, og prøv på nytt. Ingenting ble endret, og den forrige listen er urørt.",
                "steam_unread": "Steams liste over ikke-Steam-spill kunne ikke leses.",
                "steam_unread_detail": "Lukk Steam helt, og prøv på nytt.",
                "uninstaller_detail": "Avinstaller heller spillet fra Innstillinger, Apper i Windows.",
                "bonus_detail": "Denne platen ble laget uten bonusmappe.",
                "mods_detail": "Fant ikke noe mod-verktøy i mods-mappen på denne platen.",
                "looked_for": "Så etter: %s",
                "looked_in": "Så i:",
                "and_more": "... og %d til",
                "play_again": "Prøv «Spill» én gang til først: En nyinstallert mappe blir noen ganger fortsatt skannet. Hvis det fortsetter å mislykkes, er kanskje ikke spillmappen ferdig kopiert.",
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
                "choose_game": "Wybierz grę", "sort_disc": "Jak na płycie", "sort_az": "Od A do Z",
                "tip_star": "Oznacz grę gwiazdką, a pojawi się na górze menu głównego.",
                "play_games": "Graj", "steam": "Dodaj do Steama",
                "ok": "OK",
                "steam_none_title": "Nie ma czego dodać",
                "steam_none": "Nie znaleziono gry, którą można dodać do twojej biblioteki Steam.",
                "steam_none_detail": "Najpierw zainstaluj grę z płyty, a potem spróbuj ponownie.",
                "steam_missing_title": "Nie znaleziono Steam",
                "steam_missing": "Na tym komputerze nie znaleziono profilu Steam.",
                "steam_missing_detail": "Zainstaluj Steam i zaloguj się raz, a potem spróbuj ponownie. Steam tworzy potrzebny folder dopiero po pierwszym zalogowaniu.",
                "steam_running_title": "Najpierw zamknij Steam",
                "steam_running": "Steam jest uruchomiony, więc jeszcze nic nie zostało dodane.",
                "steam_running_why": "Steam cofnąłby tę zmianę: trzyma listę gier spoza Steam w pamięci i przy zamykaniu zapisuje z powrotem tę kopię.",
                "steam_running_detail": "Całkowicie zamknij Steam: kliknij prawym przyciskiem myszy ikonę Steam w obszarze powiadomień obok zegara i wybierz Wyjdź. Zamknięcie okna nie wystarczy. Potem ponownie naciśnij „Dodaj do Steama”.",
                "steam_added_title": "Dodano do Steam",
                "steam_added": "%s jest teraz w twojej bibliotece Steam, wśród gier spoza Steam.",
                "steam_added_detail": "Pojawi się tam przy następnym uruchomieniu Steam.",
                "steam_already_title": "Już jest w Steam",
                "steam_already": "%s jest już w twojej bibliotece Steam.",
                "steam_already_detail": "Nic nie zostało zmienione. Jeśli chcesz dodać grę ponownie, najpierw usuń ją ze Steam.",
                "steam_failed_title": "Nie udało się dodać do Steam",
                "steam_blocked": "Nie udało się zaktualizować listy gier spoza Steam w Steam.",
                "steam_blocked_detail": "Całkowicie zamknij Steam i spróbuj ponownie. Nic nie zostało zmienione, a poprzednia lista jest nienaruszona.",
                "steam_unread": "Nie udało się odczytać listy gier spoza Steam w Steam.",
                "steam_unread_detail": "Całkowicie zamknij Steam i spróbuj ponownie.",
                "uninstaller_detail": "Zamiast tego odinstaluj grę w systemie Windows: Ustawienia, Aplikacje.",
                "bonus_detail": "Ta płyta została utworzona bez folderu z bonusami.",
                "mods_detail": "W folderze mods na tej płycie nie znaleziono narzędzia do modów.",
                "looked_for": "Szukano: %s",
                "looked_in": "Szukano w:",
                "and_more": "... i %d więcej",
                "play_again": "Najpierw spróbuj jeszcze raz „Graj”: świeżo zainstalowany folder jest czasem jeszcze skanowany. Jeśli nadal się nie udaje, kopiowanie folderu gry mogło się nie zakończyć.",
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
                "choose_game": "Escolha o seu jogo", "sort_disc": "Como no disco", "sort_az": "De A a Z",
                "tip_star": "Marque um jogo com uma estrela para o pôr no topo do menu principal.",
                "play_games": "Jogar", "steam": "Adicionar ao Steam",
                "ok": "OK",
                "steam_none_title": "Nada para adicionar",
                "steam_none": "Não foi encontrado nenhum jogo para adicionar à sua biblioteca Steam.",
                "steam_none_detail": "Instale primeiro o jogo a partir do disco e, depois, tente novamente.",
                "steam_missing_title": "Steam não encontrado",
                "steam_missing": "Não foi encontrado nenhum perfil Steam neste PC.",
                "steam_missing_detail": "Instale o Steam e inicie sessão uma vez e, depois, tente novamente. O Steam só cria a pasta necessária depois do primeiro início de sessão.",
                "steam_running_title": "Saia primeiro do Steam",
                "steam_running": "O Steam está em execução, por isso ainda não foi adicionado nada.",
                "steam_running_why": "O Steam iria anular a alteração: mantém a lista de jogos não Steam na memória e volta a gravar essa cópia quando é fechado.",
                "steam_running_detail": "Saia completamente do Steam: clique com o botão direito no ícone do Steam na área de notificação, junto ao relógio, e escolha Sair. Fechar a janela não chega. Depois, prima novamente «Adicionar ao Steam».",
                "steam_added_title": "Adicionado ao Steam",
                "steam_added": "%s está agora na sua biblioteca Steam, nos jogos não Steam.",
                "steam_added_detail": "Estará lá da próxima vez que iniciar o Steam.",
                "steam_already_title": "Já está no Steam",
                "steam_already": "%s já está na sua biblioteca Steam.",
                "steam_already_detail": "Não foi alterado nada. Remova-o primeiro do Steam se quiser adicioná-lo novamente.",
                "steam_failed_title": "Não foi possível adicionar ao Steam",
                "steam_blocked": "Não foi possível atualizar a lista de jogos não Steam do Steam.",
                "steam_blocked_detail": "Feche completamente o Steam e tente novamente. Não foi alterado nada e a lista anterior está intacta.",
                "steam_unread": "Não foi possível ler a lista de jogos não Steam do Steam.",
                "steam_unread_detail": "Feche completamente o Steam e tente novamente.",
                "uninstaller_detail": "Em vez disso, desinstale o jogo em Definições, Aplicações do Windows.",
                "bonus_detail": "Este disco foi criado sem uma pasta de bónus.",
                "mods_detail": "Não foi encontrada nenhuma ferramenta de mods na pasta mods deste disco.",
                "looked_for": "Procurado: %s",
                "looked_in": "Procurado em:",
                "and_more": "... e mais %d",
                "play_again": "Experimente primeiro «Jogar» mais uma vez: uma pasta acabada de instalar por vezes ainda está a ser analisada. Se continuar a falhar, a cópia da pasta do jogo pode não ter terminado.",
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
                "choose_game": "Escolha seu jogo", "sort_disc": "Como no disco", "sort_az": "De A a Z",
                "tip_star": "Marque um jogo com uma estrela para colocá-lo no topo do menu principal.",
                "play_games": "Jogar", "steam": "Adicionar ao Steam",
                "ok": "OK",
                "steam_none_title": "Nada para adicionar",
                "steam_none": "Nenhum jogo foi encontrado para adicionar à sua biblioteca Steam.",
                "steam_none_detail": "Primeiro instale o jogo pelo disco e depois tente de novo.",
                "steam_missing_title": "Steam não encontrada",
                "steam_missing": "Nenhum perfil da Steam foi encontrado neste PC.",
                "steam_missing_detail": "Instale a Steam e faça login uma vez, depois tente de novo. A Steam só cria a pasta necessária depois do primeiro login.",
                "steam_running_title": "Saia da Steam primeiro",
                "steam_running": "A Steam está aberta, então nada foi adicionado ainda.",
                "steam_running_why": "A Steam desfaria a alteração: ela mantém a lista de jogos não Steam na memória e grava essa cópia de volta ao ser fechada.",
                "steam_running_detail": "Saia completamente da Steam: clique com o botão direito no ícone da Steam na área de notificação, ao lado do relógio, e escolha Sair. Fechar a janela não basta. Depois, clique de novo no botão Adicionar ao Steam.",
                "steam_added_title": "Adicionado à Steam",
                "steam_added": "%s agora está na sua biblioteca Steam, em jogos não Steam.",
                "steam_added_detail": "Ele vai aparecer lá na próxima vez que você abrir a Steam.",
                "steam_already_title": "Já está na Steam",
                "steam_already": "%s já está na sua biblioteca Steam.",
                "steam_already_detail": "Nada foi alterado. Remova o jogo da Steam primeiro se quiser adicioná-lo de novo.",
                "steam_failed_title": "Não foi possível adicionar à Steam",
                "steam_blocked": "Não foi possível atualizar a lista de jogos não Steam da Steam.",
                "steam_blocked_detail": "Feche a Steam completamente e tente de novo. Nada foi alterado, e a lista anterior continua intacta.",
                "steam_unread": "Não foi possível ler a lista de jogos não Steam da Steam.",
                "steam_unread_detail": "Feche a Steam completamente e tente de novo.",
                "uninstaller_detail": "Em vez disso, desinstale o jogo em Configurações, Aplicativos do Windows.",
                "bonus_detail": "Este disco foi criado sem uma pasta de bônus.",
                "mods_detail": "Nenhuma ferramenta de mods foi encontrada na pasta mods deste disco.",
                "looked_for": "Procurado: %s",
                "looked_in": "Procurado em:",
                "and_more": "... e mais %d",
                "play_again": "Tente clicar em Jogar mais uma vez primeiro: uma pasta recém-instalada às vezes ainda está sendo verificada. Se continuar falhando, talvez a cópia da pasta do jogo não tenha terminado.",
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
                "choose_game": "Alege-ți jocul", "sort_disc": "Ca pe disc", "sort_az": "De la A la Z",
                "tip_star": "Marchează un joc cu o stea ca să apară în partea de sus a meniului principal.",
                "play_games": "Joacă", "steam": "Adaugă în Steam",
                "ok": "OK",
                "steam_none_title": "Nimic de adăugat",
                "steam_none": "Nu a fost găsit niciun joc de adăugat în biblioteca ta Steam.",
                "steam_none_detail": "Instalează mai întâi jocul de pe disc, apoi încearcă din nou.",
                "steam_missing_title": "Steam nu a fost găsit",
                "steam_missing": "Nu a fost găsit niciun profil Steam pe acest PC.",
                "steam_missing_detail": "Instalează Steam și conectează-te o dată, apoi încearcă din nou. Steam creează folderul necesar abia după prima conectare.",
                "steam_running_title": "Mai întâi ieși din Steam",
                "steam_running": "Steam rulează, așa că încă nu s-a adăugat nimic.",
                "steam_running_why": "Steam ar anula modificarea: păstrează lista de jocuri non-Steam în memorie și scrie înapoi acea copie când se închide.",
                "steam_running_detail": "Ieși complet din Steam: fă clic dreapta pe pictograma Steam din zona de notificare, lângă ceas, și alege Ieșire. Închiderea ferestrei nu este suficientă. Apoi apasă din nou „Adaugă în Steam”.",
                "steam_added_title": "Adăugat în Steam",
                "steam_added": "%s se află acum în biblioteca ta Steam, la jocurile non-Steam.",
                "steam_added_detail": "Va fi acolo data viitoare când pornești Steam.",
                "steam_already_title": "Deja în Steam",
                "steam_already": "%s se află deja în biblioteca ta Steam.",
                "steam_already_detail": "Nu s-a modificat nimic. Elimină-l mai întâi din Steam dacă vrei să-l adaugi din nou.",
                "steam_failed_title": "Nu s-a putut adăuga în Steam",
                "steam_blocked": "Lista de jocuri non-Steam din Steam nu a putut fi actualizată.",
                "steam_blocked_detail": "Închide complet Steam și încearcă din nou. Nu s-a modificat nimic, iar lista anterioară a rămas neatinsă.",
                "steam_unread": "Lista de jocuri non-Steam din Steam nu a putut fi citită.",
                "steam_unread_detail": "Închide complet Steam și încearcă din nou.",
                "uninstaller_detail": "Dezinstalează în schimb jocul din Setări, Aplicații în Windows.",
                "bonus_detail": "Acest disc a fost creat fără un folder bonus.",
                "mods_detail": "Nu a fost găsit niciun instrument pentru moduri în folderul mods de pe acest disc.",
                "looked_for": "S-a căutat: %s",
                "looked_in": "S-a căutat în:",
                "and_more": "... și încă %d",
                "play_again": "Încearcă mai întâi încă o dată „Joacă”: un folder abia instalat este uneori încă scanat. Dacă eșuează în continuare, este posibil ca folderul jocului să nu se fi copiat complet.",
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
                "choose_game": "Выберите игру", "sort_disc": "Как на диске", "sort_az": "От А до Я",
                "tip_star": "Отметьте игру звёздочкой, и она окажется вверху главного меню.",
                "play_games": "Играть", "steam": "Добавить в Steam",
                "ok": "ОК",
                "steam_none_title": "Нечего добавить",
                "steam_none": "Не найдено ни одной игры для добавления в вашу библиотеку Steam.",
                "steam_none_detail": "Сначала установите игру с диска, затем повторите попытку.",
                "steam_missing_title": "Steam не найден",
                "steam_missing": "На этом компьютере не найден профиль Steam.",
                "steam_missing_detail": "Установите Steam и войдите в аккаунт хотя бы один раз, затем повторите попытку. Steam создаёт нужную папку только после первого входа.",
                "steam_running_title": "Сначала закройте Steam",
                "steam_running": "Steam запущен, поэтому пока ничего не добавлено.",
                "steam_running_why": "Steam отменил бы изменения: он хранит список сторонних игр в памяти и при закрытии записывает эту копию обратно.",
                "steam_running_detail": "Полностью закройте Steam: щёлкните правой кнопкой мыши по значку Steam в области уведомлений рядом с часами и выберите Выход. Закрыть окно недостаточно. Затем снова нажмите «Добавить в Steam».",
                "steam_added_title": "Добавлено в Steam",
                "steam_added": "%s теперь в вашей библиотеке Steam, среди сторонних игр.",
                "steam_added_detail": "Игра появится там при следующем запуске Steam.",
                "steam_already_title": "Уже в Steam",
                "steam_already": "%s уже есть в вашей библиотеке Steam.",
                "steam_already_detail": "Ничего не изменено. Если хотите добавить игру заново, сначала удалите её из Steam.",
                "steam_failed_title": "Не удалось добавить в Steam",
                "steam_blocked": "Не удалось обновить список сторонних игр в Steam.",
                "steam_blocked_detail": "Полностью закройте Steam и повторите попытку. Ничего не изменено, прежний список не тронут.",
                "steam_unread": "Не удалось прочитать список сторонних игр в Steam.",
                "steam_unread_detail": "Полностью закройте Steam и повторите попытку.",
                "uninstaller_detail": "Вместо этого удалите игру через Параметры Windows, раздел Приложения.",
                "bonus_detail": "Этот диск создан без папки с бонусами.",
                "mods_detail": "В папке mods на этом диске не найден инструмент для модов.",
                "looked_for": "Искали: %s",
                "looked_in": "Где искали:",
                "and_more": "... и ещё %d",
                "play_again": "Сначала попробуйте нажать «Играть» ещё раз: только что установленная папка иногда ещё проверяется. Если ошибка повторяется, возможно, папка игры скопировалась не полностью.",
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
                "choose_game": "Izaberite igru", "sort_disc": "Kao na disku", "sort_az": "Od A do Ž",
                "tip_star": "Označite igru zvezdicom i biće na vrhu glavnog menija.",
                "play_games": "Igraj", "steam": "Dodaj u Steam",
                "ok": "U redu",
                "steam_none_title": "Nema šta da se doda",
                "steam_none": "Nije pronađena nijedna igra koja bi se dodala u vašu Steam biblioteku.",
                "steam_none_detail": "Prvo instalirajte igru sa diska, a zatim pokušajte ponovo.",
                "steam_missing_title": "Steam nije pronađen",
                "steam_missing": "Na ovom računaru nije pronađen nijedan Steam profil.",
                "steam_missing_detail": "Instalirajte Steam i prijavite se jednom, a zatim pokušajte ponovo. Steam tek posle prve prijave pravi fasciklu koja je za ovo potrebna.",
                "steam_running_title": "Prvo izađite iz Steama",
                "steam_running": "Steam je pokrenut, pa još ništa nije dodato.",
                "steam_running_why": "Steam bi to poništio: svoju listu igara van Steama drži u memoriji i pri zatvaranju upisuje tu kopiju nazad.",
                "steam_running_detail": "Potpuno izađite iz Steama: kliknite desnim tasterom miša na ikonu Steama u oblasti za obaveštenja pored sata i izaberite Exit. Zatvaranje prozora nije dovoljno. Zatim ponovo pritisnite „Dodaj u Steam”.",
                "steam_added_title": "Dodato u Steam",
                "steam_added": "%s se sada nalazi u vašoj Steam biblioteci, među igrama van Steama.",
                "steam_added_detail": "Biće tamo sledeći put kada pokrenete Steam.",
                "steam_already_title": "Već je u Steamu",
                "steam_already": "%s se već nalazi u vašoj Steam biblioteci.",
                "steam_already_detail": "Ništa nije promenjeno. Ako želite da je ponovo dodate, prvo je uklonite iz Steama.",
                "steam_failed_title": "Dodavanje u Steam nije uspelo",
                "steam_blocked": "Steam lista igara van Steama nije mogla da se ažurira.",
                "steam_blocked_detail": "Potpuno zatvorite Steam i pokušajte ponovo. Ništa nije promenjeno, a prethodna lista je ostala netaknuta.",
                "steam_unread": "Steam lista igara van Steama nije mogla da se pročita.",
                "steam_unread_detail": "Potpuno zatvorite Steam i pokušajte ponovo.",
                "uninstaller_detail": "Umesto toga deinstalirajte igru u sistemu Windows: Podešavanja, Aplikacije.",
                "bonus_detail": "Ovaj disk je napravljen bez fascikle sa bonus sadržajem.",
                "mods_detail": "U fascikli mods na ovom disku nije pronađen alat za modove.",
                "looked_for": "Traženo: %s",
                "looked_in": "Traženo u:",
                "and_more": "... i još %d",
                "play_again": "Prvo još jednom pokušajte „Igraj”: tek instalirana fascikla se ponekad još skenira. Ako i dalje ne uspeva, kopiranje fascikle igre možda nije završeno.",
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
                "choose_game": "Vyberte hru", "sort_disc": "Ako na disku", "sort_az": "Od A po Z",
                "tip_star": "Označte hru hviezdičkou a zobrazí sa navrchu hlavnej ponuky.",
                "play_games": "Hrať", "steam": "Pridať do Steamu",
                "ok": "OK",
                "steam_none_title": "Nie je čo pridať",
                "steam_none": "Nenašla sa žiadna hra, ktorú by bolo možné pridať do vašej knižnice Steam.",
                "steam_none_detail": "Najprv nainštalujte hru z disku a potom to skúste znova.",
                "steam_missing_title": "Steam sa nenašiel",
                "steam_missing": "V tomto počítači sa nenašiel žiadny profil Steam.",
                "steam_missing_detail": "Nainštalujte Steam, raz sa prihláste a potom to skúste znova. Steam vytvorí potrebný priečinok až po prvom prihlásení.",
                "steam_running_title": "Najprv ukončite Steam",
                "steam_running": "Steam je spustený, preto zatiaľ nebolo nič pridané.",
                "steam_running_why": "Steam by zmenu vrátil: zoznam hier mimo Steamu drží v pamäti a pri zatvorení túto kópiu znova zapíše.",
                "steam_running_detail": "Steam úplne ukončite: kliknite pravým tlačidlom na ikonu Steamu v oblasti oznámení vedľa hodín a vyberte Exit. Zatvoriť okno nestačí. Potom znova stlačte „Pridať do Steamu“.",
                "steam_added_title": "Pridané do Steamu",
                "steam_added": "%s je teraz vo vašej knižnici Steam medzi hrami mimo Steamu.",
                "steam_added_detail": "Objaví sa tam pri ďalšom spustení Steamu.",
                "steam_already_title": "Už je v Steame",
                "steam_already": "%s už je vo vašej knižnici Steam.",
                "steam_already_detail": "Nič sa nezmenilo. Ak ju chcete pridať znova, najprv ju zo Steamu odstráňte.",
                "steam_failed_title": "Pridanie do Steamu zlyhalo",
                "steam_blocked": "Zoznam hier mimo Steamu sa v Steame nepodarilo aktualizovať.",
                "steam_blocked_detail": "Steam úplne zatvorte a skúste to znova. Nič sa nezmenilo a predchádzajúci zoznam zostal nedotknutý.",
                "steam_unread": "Zoznam hier mimo Steamu sa v Steame nepodarilo prečítať.",
                "steam_unread_detail": "Steam úplne zatvorte a skúste to znova.",
                "uninstaller_detail": "Hru namiesto toho odinštalujte vo Windowse v časti Nastavenia, Aplikácie.",
                "bonus_detail": "Tento disk bol vytvorený bez priečinka s bonusovým obsahom.",
                "mods_detail": "V priečinku mods na tomto disku sa nenašiel žiadny nástroj na módy.",
                "looked_for": "Hľadané: %s",
                "looked_in": "Hľadané v:",
                "and_more": "... a ďalších %d",
                "play_again": "Najprv skúste ešte raz „Hrať“: čerstvo nainštalovaný priečinok sa niekedy ešte kontroluje. Ak to stále zlyháva, kopírovanie priečinka hry možno nebolo dokončené.",
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
                "choose_game": "Elige tu juego", "sort_disc": "Como en el disco", "sort_az": "De la A a la Z",
                "tip_star": "Marca un juego con una estrella para ponerlo arriba en el menú principal.",
                "play_games": "Jugar", "steam": "Añadir a Steam",
                "ok": "Aceptar",
                "steam_none_title": "Nada que añadir",
                "steam_none": "No se encontró ningún juego para añadir a tu biblioteca de Steam.",
                "steam_none_detail": "Primero instala el juego desde el disco y luego vuelve a intentarlo.",
                "steam_missing_title": "No se encontró Steam",
                "steam_missing": "No se encontró ningún perfil de Steam en este PC.",
                "steam_missing_detail": "Instala Steam e inicia sesión una vez, y luego vuelve a intentarlo. Steam solo crea la carpeta necesaria después del primer inicio de sesión.",
                "steam_running_title": "Primero sal de Steam",
                "steam_running": "Steam está abierto, así que todavía no se ha añadido nada.",
                "steam_running_why": "Steam desharía el cambio: guarda en memoria su lista de juegos ajenos a Steam y vuelve a escribir esa copia al cerrarse.",
                "steam_running_detail": "Sal de Steam por completo: haz clic derecho en el icono de Steam en el área de notificación, junto al reloj, y elige Salir. Cerrar la ventana no basta. Después, pulsa otra vez «Añadir a Steam».",
                "steam_added_title": "Añadido a Steam",
                "steam_added": "%s se ha añadido a tu biblioteca de Steam, en los juegos ajenos a Steam.",
                "steam_added_detail": "Lo verás allí la próxima vez que inicies Steam.",
                "steam_already_title": "Ya está en Steam",
                "steam_already": "%s ya está en tu biblioteca de Steam.",
                "steam_already_detail": "No se ha cambiado nada. Si quieres volver a añadirlo, quítalo primero de Steam.",
                "steam_failed_title": "No se pudo añadir a Steam",
                "steam_blocked": "No se pudo actualizar la lista de juegos ajenos a Steam de Steam.",
                "steam_blocked_detail": "Cierra Steam por completo y vuelve a intentarlo. No se ha cambiado nada y la lista anterior sigue intacta.",
                "steam_unread": "No se pudo leer la lista de juegos ajenos a Steam de Steam.",
                "steam_unread_detail": "Cierra Steam por completo y vuelve a intentarlo.",
                "uninstaller_detail": "En su lugar, desinstala el juego desde Configuración, Aplicaciones de Windows.",
                "bonus_detail": "Este disco se creó sin carpeta de contenido extra.",
                "mods_detail": "No se encontró ninguna herramienta de mods en la carpeta mods de este disco.",
                "looked_for": "Se buscó: %s",
                "looked_in": "Se buscó en:",
                "and_more": "... y %d más",
                "play_again": "Prueba primero «Jugar» una vez más: a veces una carpeta recién instalada todavía se está analizando. Si sigue fallando, puede que la carpeta del juego no haya terminado de copiarse.",
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
                "choose_game": "Välj ditt spel", "sort_disc": "Som på skivan", "sort_az": "A till Ö",
                "tip_star": "Stjärnmärk ett spel så hamnar det överst i huvudmenyn.",
                "play_games": "Spela", "steam": "Lägg till i Steam",
                "ok": "OK",
                "steam_none_title": "Inget att lägga till",
                "steam_none": "Inget spel hittades att lägga till i ditt Steam-bibliotek.",
                "steam_none_detail": "Installera spelet från skivan först och försök sedan igen.",
                "steam_missing_title": "Steam hittades inte",
                "steam_missing": "Ingen Steam-profil hittades på den här datorn.",
                "steam_missing_detail": "Installera Steam och logga in en gång, och försök sedan igen. Steam skapar mappen som behövs först efter den första inloggningen.",
                "steam_running_title": "Avsluta Steam först",
                "steam_running": "Steam körs, så inget har lagts till än.",
                "steam_running_why": "Steam skulle ångra det: Steam håller sin lista över icke-Steam-spel i minnet och skriver tillbaka den kopian när programmet stängs.",
                "steam_running_detail": "Avsluta Steam helt: högerklicka på Steam-ikonen i meddelandefältet vid klockan och välj Avsluta. Det räcker inte att stänga fönstret. Tryck sedan på ”Lägg till i Steam” igen.",
                "steam_added_title": "Tillagt i Steam",
                "steam_added": "%s finns nu i ditt Steam-bibliotek, under icke-Steam-spel.",
                "steam_added_detail": "Det finns där nästa gång du startar Steam.",
                "steam_already_title": "Redan i Steam",
                "steam_already": "%s finns redan i ditt Steam-bibliotek.",
                "steam_already_detail": "Inget ändrades. Ta bort det från Steam först om du vill lägga till det igen.",
                "steam_failed_title": "Kunde inte lägga till i Steam",
                "steam_blocked": "Steams lista över icke-Steam-spel kunde inte uppdateras.",
                "steam_blocked_detail": "Stäng Steam helt och försök igen. Inget ändrades, och den tidigare listan är orörd.",
                "steam_unread": "Steams lista över icke-Steam-spel kunde inte läsas.",
                "steam_unread_detail": "Stäng Steam helt och försök igen.",
                "uninstaller_detail": "Avinstallera i stället spelet under Inställningar, Appar i Windows.",
                "bonus_detail": "Den här skivan skapades utan bonusmapp.",
                "mods_detail": "Inget modverktyg hittades i mods-mappen på den här skivan.",
                "looked_for": "Letade efter: %s",
                "looked_in": "Letade i:",
                "and_more": "... och %d till",
                "play_again": "Prova ”Spela” en gång till först: en nyinstallerad mapp skannas ibland fortfarande. Om det fortsätter att misslyckas kanske spelmappen inte har kopierats klart.",
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
                "choose_game": "เลือกเกมของคุณ", "sort_disc": "ตามลำดับในดิสก์", "sort_az": "เรียงตามชื่อ",
                "tip_star": "ติดดาวให้เกมเพื่อให้แสดงอยู่บนสุดของเมนูหลัก",
                "play_games": "เล่นเกม", "steam": "เพิ่มลงใน Steam",
                "ok": "ตกลง",
                "steam_none_title": "ไม่มีอะไรให้เพิ่ม",
                "steam_none": "ไม่พบเกมที่จะเพิ่มลงในคลัง Steam ของคุณ",
                "steam_none_detail": "ติดตั้งเกมจากแผ่นก่อน แล้วลองอีกครั้ง",
                "steam_missing_title": "ไม่พบ Steam",
                "steam_missing": "ไม่พบโปรไฟล์ Steam บนพีซีเครื่องนี้",
                "steam_missing_detail": "ติดตั้ง Steam และลงชื่อเข้าใช้หนึ่งครั้ง แล้วลองอีกครั้ง Steam จะสร้างโฟลเดอร์ที่จำเป็นหลังจากลงชื่อเข้าใช้ครั้งแรกเท่านั้น",
                "steam_running_title": "ออกจาก Steam ก่อน",
                "steam_running": "Steam กำลังทำงานอยู่ จึงยังไม่ได้เพิ่มอะไรเลย",
                "steam_running_why": "Steam จะยกเลิกการเปลี่ยนแปลงนี้ เพราะ Steam เก็บรายการเกมที่ไม่ใช่ของ Steam ไว้ในหน่วยความจำ และเขียนสำเนานั้นกลับเมื่อปิดโปรแกรม",
                "steam_running_detail": "ออกจาก Steam ให้หมด: คลิกขวาที่ไอคอน Steam ในพื้นที่แจ้งเตือนข้างนาฬิกา แล้วเลือก ออก การปิดหน้าต่างอย่างเดียวไม่พอ จากนั้นกด เพิ่มลงใน Steam อีกครั้ง",
                "steam_added_title": "เพิ่มลงใน Steam แล้ว",
                "steam_added": "%s อยู่ในคลัง Steam ของคุณแล้ว ในหมวดเกมที่ไม่ใช่ของ Steam",
                "steam_added_detail": "เกมจะปรากฏที่นั่นเมื่อคุณเปิด Steam ครั้งถัดไป",
                "steam_already_title": "มีอยู่ใน Steam แล้ว",
                "steam_already": "%s อยู่ในคลัง Steam ของคุณอยู่แล้ว",
                "steam_already_detail": "ไม่มีการเปลี่ยนแปลงใด ๆ หากต้องการเพิ่มอีกครั้ง ให้ลบออกจาก Steam ก่อน",
                "steam_failed_title": "ไม่สามารถเพิ่มลงใน Steam",
                "steam_blocked": "ไม่สามารถอัปเดตรายการเกมที่ไม่ใช่ของ Steam ใน Steam ได้",
                "steam_blocked_detail": "ปิด Steam ให้หมดแล้วลองอีกครั้ง ไม่มีการเปลี่ยนแปลงใด ๆ และรายการเดิมยังอยู่ครบ",
                "steam_unread": "ไม่สามารถอ่านรายการเกมที่ไม่ใช่ของ Steam ใน Steam ได้",
                "steam_unread_detail": "ปิด Steam ให้หมดแล้วลองอีกครั้ง",
                "uninstaller_detail": "ให้ถอนการติดตั้งเกมจาก การตั้งค่า > แอป ของ Windows แทน",
                "bonus_detail": "แผ่นนี้สร้างขึ้นโดยไม่มีโฟลเดอร์โบนัส",
                "mods_detail": "ไม่พบเครื่องมือม็อดในโฟลเดอร์ mods บนแผ่นนี้",
                "looked_for": "สิ่งที่ค้นหา: %s",
                "looked_in": "ตำแหน่งที่ค้นหา:",
                "and_more": "... และอีก %d รายการ",
                "play_again": "ลองกด เล่นเกม อีกครั้งก่อน เพราะโฟลเดอร์ที่เพิ่งติดตั้งบางครั้งยังถูกสแกนอยู่ หากยังล้มเหลวอยู่ อาจเป็นเพราะการคัดลอกโฟลเดอร์เกมยังไม่เสร็จ",
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
                "choose_game": "Oyununuzu seçin", "sort_disc": "Diskteki sırayla", "sort_az": "A'dan Z'ye",
                "tip_star": "Ana menünün en üstünde görünmesi için bir oyunu yıldızla işaretleyin.",
                "play_games": "Oyun Oyna", "steam": "Steam'e Ekle",
                "ok": "Tamam",
                "steam_none_title": "Eklenecek bir şey yok",
                "steam_none": "Steam kitaplığınıza eklenecek bir oyun bulunamadı.",
                "steam_none_detail": "Önce oyunu diskten kurun, sonra tekrar deneyin.",
                "steam_missing_title": "Steam bulunamadı",
                "steam_missing": "Bu bilgisayarda Steam profili bulunamadı.",
                "steam_missing_detail": "Steam'i kurun ve bir kez oturum açın, sonra tekrar deneyin. Steam gereken klasörü ancak ilk oturum açıştan sonra oluşturur.",
                "steam_running_title": "Önce Steam'den çıkın",
                "steam_running": "Steam çalışıyor, bu yüzden henüz hiçbir şey eklenmedi.",
                "steam_running_why": "Steam bunu geri alır: Steam dışı oyunlar listesini bellekte tutar ve kapanırken bu kopyayı geri yazar.",
                "steam_running_detail": "Steam'den tamamen çıkın: saatin yanındaki bildirim alanında Steam simgesine sağ tıklayın ve Çıkış'ı seçin. Pencereyi kapatmak yeterli değildir. Ardından Steam'e Ekle düğmesine yeniden basın.",
                "steam_added_title": "Steam'e Eklendi",
                "steam_added": "%s artık Steam kitaplığınızda, Steam dışı oyunlar altında.",
                "steam_added_detail": "Steam'i bir sonraki başlatışınızda orada olacak.",
                "steam_already_title": "Zaten Steam'de",
                "steam_already": "%s zaten Steam kitaplığınızda.",
                "steam_already_detail": "Hiçbir şey değiştirilmedi. Yeniden eklemek istiyorsanız önce Steam'den kaldırın.",
                "steam_failed_title": "Steam'e Eklenemedi",
                "steam_blocked": "Steam'in Steam dışı oyunlar listesi güncellenemedi.",
                "steam_blocked_detail": "Steam'i tamamen kapatıp tekrar deneyin. Hiçbir şey değiştirilmedi ve önceki liste olduğu gibi duruyor.",
                "steam_unread": "Steam'in Steam dışı oyunlar listesi okunamadı.",
                "steam_unread_detail": "Steam'i tamamen kapatıp tekrar deneyin.",
                "uninstaller_detail": "Bunun yerine oyunu Windows Ayarlar, Uygulamalar bölümünden kaldırın.",
                "bonus_detail": "Bu disk bonus klasörü olmadan oluşturulmuş.",
                "mods_detail": "Bu diskteki mods klasöründe mod aracı bulunamadı.",
                "looked_for": "Aranan: %s",
                "looked_in": "Aranan konum:",
                "and_more": "... ve %d tane daha",
                "play_again": "Önce Oyunu Oyna'yı bir kez daha deneyin: yeni kurulmuş bir klasör bazen hâlâ taranıyor olabilir. Hata sürerse oyun klasörünün kopyalanması tamamlanmamış olabilir.",
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
                "choose_game": "Виберіть гру", "sort_disc": "Як на диску", "sort_az": "Від А до Я",
                "tip_star": "Позначте гру зірочкою, і вона з'явиться вгорі головного меню.",
                "play_games": "Грати", "steam": "Додати до Steam",
                "ok": "OK",
                "steam_none_title": "Нічого додати",
                "steam_none": "Не знайдено жодної гри для додавання до вашої бібліотеки Steam.",
                "steam_none_detail": "Спочатку встановіть гру з диска, а потім спробуйте ще раз.",
                "steam_missing_title": "Steam не знайдено",
                "steam_missing": "На цьому комп'ютері не знайдено профілю Steam.",
                "steam_missing_detail": "Встановіть Steam і увійдіть хоча б один раз, а потім спробуйте ще раз. Steam створює потрібну теку лише після першого входу.",
                "steam_running_title": "Спочатку закрийте Steam",
                "steam_running": "Steam запущено, тому поки що нічого не додано.",
                "steam_running_why": "Steam скасував би зміни: він зберігає список сторонніх ігор у пам'яті й під час закриття записує цю копію назад.",
                "steam_running_detail": "Повністю закрийте Steam: клацніть правою кнопкою миші значок Steam в області сповіщень біля годинника й виберіть Вихід. Закрити вікно недостатньо. Потім знову натисніть «Додати до Steam».",
                "steam_added_title": "Додано до Steam",
                "steam_added": "%s тепер у вашій бібліотеці Steam, серед сторонніх ігор.",
                "steam_added_detail": "Гра з'явиться там під час наступного запуску Steam.",
                "steam_already_title": "Уже в Steam",
                "steam_already": "%s уже є у вашій бібліотеці Steam.",
                "steam_already_detail": "Нічого не змінено. Якщо хочете додати гру знову, спочатку видаліть її зі Steam.",
                "steam_failed_title": "Не вдалося додати до Steam",
                "steam_blocked": "Не вдалося оновити список сторонніх ігор у Steam.",
                "steam_blocked_detail": "Повністю закрийте Steam і спробуйте ще раз. Нічого не змінено, попередній список не зачеплено.",
                "steam_unread": "Не вдалося прочитати список сторонніх ігор у Steam.",
                "steam_unread_detail": "Повністю закрийте Steam і спробуйте ще раз.",
                "uninstaller_detail": "Натомість видаліть гру в Windows через Параметри, Програми.",
                "bonus_detail": "Цей диск створено без теки з бонусами.",
                "mods_detail": "У теці mods на цьому диску не знайдено інструмента для модів.",
                "looked_for": "Шукали: %s",
                "looked_in": "Де шукали:",
                "and_more": "... і ще %d",
                "play_again": "Спочатку спробуйте ще раз натиснути «Грати»: щойно встановлену теку іноді ще перевіряють. Якщо помилка повторюється, можливо, теку гри скопійовано не повністю.",
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
                "choose_game": "Chọn trò chơi của bạn", "sort_disc": "Theo thứ tự trên đĩa", "sort_az": "Từ A đến Z",
                "tip_star": "Gắn sao cho trò chơi để nó hiện ở đầu menu chính.",
                "play_games": "Chơi Game", "steam": "Thêm vào Steam",
                "ok": "OK",
                "steam_none_title": "Không có gì để thêm",
                "steam_none": "Không tìm thấy trò chơi nào để thêm vào thư viện Steam của bạn.",
                "steam_none_detail": "Hãy cài đặt trò chơi từ đĩa trước, rồi thử lại.",
                "steam_missing_title": "Không tìm thấy Steam",
                "steam_missing": "Không tìm thấy hồ sơ Steam nào trên máy tính này.",
                "steam_missing_detail": "Hãy cài đặt Steam và đăng nhập một lần, rồi thử lại. Steam chỉ tạo thư mục cần thiết sau lần đăng nhập đầu tiên.",
                "steam_running_title": "Hãy thoát Steam trước",
                "steam_running": "Steam đang chạy, nên chưa có gì được thêm.",
                "steam_running_why": "Steam sẽ hoàn tác thay đổi: Steam giữ danh sách trò chơi không thuộc Steam trong bộ nhớ và ghi lại bản sao đó khi đóng.",
                "steam_running_detail": "Hãy thoát hẳn Steam: nhấp chuột phải vào biểu tượng Steam trong vùng thông báo, cạnh đồng hồ, rồi chọn Thoát. Chỉ đóng cửa sổ là chưa đủ. Sau đó nhấn lại Thêm vào Steam.",
                "steam_added_title": "Đã thêm vào Steam",
                "steam_added": "%s hiện đã có trong thư viện Steam của bạn, trong mục trò chơi không thuộc Steam.",
                "steam_added_detail": "Trò chơi sẽ xuất hiện ở đó vào lần tới bạn khởi động Steam.",
                "steam_already_title": "Đã có trong Steam",
                "steam_already": "%s đã có sẵn trong thư viện Steam của bạn.",
                "steam_already_detail": "Không có gì thay đổi. Hãy gỡ trò chơi khỏi Steam trước nếu bạn muốn thêm lại.",
                "steam_failed_title": "Không thể thêm vào Steam",
                "steam_blocked": "Không thể cập nhật danh sách trò chơi không thuộc Steam của Steam.",
                "steam_blocked_detail": "Hãy đóng hẳn Steam rồi thử lại. Không có gì thay đổi và danh sách trước đó vẫn nguyên vẹn.",
                "steam_unread": "Không thể đọc danh sách trò chơi không thuộc Steam của Steam.",
                "steam_unread_detail": "Hãy đóng hẳn Steam rồi thử lại.",
                "uninstaller_detail": "Thay vào đó, hãy gỡ cài đặt trò chơi trong Cài đặt, Ứng dụng của Windows.",
                "bonus_detail": "Đĩa này được tạo mà không có thư mục bonus.",
                "mods_detail": "Không tìm thấy công cụ mod nào trong thư mục mods trên đĩa này.",
                "looked_for": "Đã tìm: %s",
                "looked_in": "Đã tìm trong:",
                "and_more": "... và %d mục khác",
                "play_again": "Hãy thử nhấn Chơi Game thêm một lần trước: thư mục vừa cài đặt đôi khi vẫn đang được quét. Nếu vẫn tiếp tục lỗi, có thể thư mục trò chơi chưa sao chép xong.",
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
        # The language this player picked last time, on this PC, wins over the
        # disc's own (1.5.1): a player should not have to pick it every time.
        if self.player_prefs.get("lang") in self.translations:
            self.current_lang = self.player_prefs["lang"]
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
        
        title_label = None  # a text title is fitted to the column once it is built: _fit_title
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
                    if is_square and len(self.games) < 2:
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
                title_label.setTextFormat(QtCore.Qt.PlainText)
                title_label.setStyleSheet("""
                    color: white;
                    font-size: """ + str(int(36 * self.scale_factor)) + """px;
                    font-weight: bold;
                    letter-spacing: """ + str(int(3 * self.scale_factor)) + """px;
                    margin-bottom: """ + str(int(20 * self.scale_factor)) + """px;
                    background: transparent;
                """)
                title_label.setWordWrap(True)
                self._keep_title_whole(title_label)
                left_layout.addWidget(title_label)
        else:
            # No logo found, use text
            title_label = QtWidgets.QLabel(self.menu_title.upper())
            title_label.setTextFormat(QtCore.Qt.PlainText)
            title_label.setStyleSheet("""
                color: white;
                font-size: """ + str(int(36 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(3 * self.scale_factor)) + """px;
                margin-bottom: """ + str(int(20 * self.scale_factor)) + """px;
                background: transparent;
            """)
            title_label.setWordWrap(True)
            self._keep_title_whole(title_label)
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
            QPushButton:hover, QPushButton:focus {{
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
        # promising a launch that cannot happen. Every label starts in the menu's
        # language: they used to start in English, so a disc set to another
        # language (or a player's remembered one) opened half translated.
        self.installer_path = self.disc_installer()
        trans = self.translations[self.current_lang]
        self.play_btn = QtWidgets.QPushButton(self.play_label(trans))
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
            QPushButton:hover, QPushButton:focus {
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

        # Every game under PLAY GAMES (1.5.1, B9): quiet lines like compatibility
        # mode, one per game, starred ones first, each starting its game. Only on
        # a disc of several games that is already installed. A long list scrolls
        # inside its own box, so UNINSTALL and EXIT never leave the window.
        self.quick_style = compat_style
        self.quick_btns = []
        self.quick_box = QtWidgets.QWidget()
        self.quick_box.setStyleSheet("background: transparent;")
        self.quick_layout = QtWidgets.QVBoxLayout(self.quick_box)
        self.quick_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_layout.setSpacing(0)
        self.quick_scroll = QtWidgets.QScrollArea()
        self.quick_scroll.setWidget(self.quick_box)
        self.quick_scroll.setWidgetResizable(True)
        self.quick_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.quick_scroll.setFocusPolicy(QtCore.Qt.NoFocus)
        self.quick_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.quick_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.quick_scroll.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        self.quick_scroll.setStyleSheet("""
            QWidget { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: """ + str(int(6 * self.scale_factor)) + """px; margin: 0px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 60); min-height: """ + str(int(24 * self.scale_factor)) + """px; }
            QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 120); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

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
            self.bonus_btn = QtWidgets.QPushButton(self.shout(trans["bonus"]))
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
            self.steam_btn = QtWidgets.QPushButton(trans["steam"])
            self.steam_btn.clicked.connect(self.add_to_steam)
            self.steam_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.steam_btn.setToolTip(self.translations[self.current_lang]["tip_steam"])
            self.steam_btn.setStyleSheet(compat_style)

        self.uninstall_btn = QtWidgets.QPushButton(self.shout(trans["uninstall"]))
        self.uninstall_btn.clicked.connect(self.uninstall_game)
        self.uninstall_btn.setCursor(QtCore.Qt.PointingHandCursor)
        # PLAY and EXIT get no tooltip: a tooltip that restates the button is
        # noise. UNINSTALL gets one because "your saves are safe" is the thing
        # a player actually wants to know before clicking it.
        self.uninstall_btn.setToolTip(self.translations[self.current_lang]["tip_uninstall"])
        self.uninstall_btn.setStyleSheet(button_style_template.format(
            color="#cccccc", border_width="3", border_color="transparent"
        ))
        
        self.exit_btn = QtWidgets.QPushButton(self.shout(trans["exit"]))
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
        buttons_to_add.append(self.quick_scroll)
        if mods_exists:
            buttons_to_add.append(self.mods_btn)
        if self.steam_btn is not None:
            buttons_to_add.append(self.steam_btn)
        if bonus_exists:
            buttons_to_add.append(self.bonus_btn)
        buttons_to_add.extend([self.uninstall_btn, self.exit_btn])
        
        for btn in buttons_to_add:
            left_layout.addWidget(btn)
        self.refresh_quick_starts()  # after quick_scroll has its place, never as a window of its own
        for btn in self.nav_buttons():
            btn.installEventFilter(self)  # Up and Down follow the screen; see eventFilter
        
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
        if title_label is not None:
            self._fit_title(title_label, left_layout, scaled_height)
        
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
                # Plain text: menu_config.json can be rewritten, and markup in a
                # label can make the signed menu fetch a file (security review).
                copyright_label.setTextFormat(QtCore.Qt.PlainText)
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
    
    def _keep_title_whole(self, label):
        """A text title claims the height of every line it wraps to.

        The games under PLAY GAMES take room in the column, and the layout took
        it from the title, which lost its last line: a cut that reads as another
        name. Measured after the style sheet is applied, or the font is wrong.
        """
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        label.ensurePolished()
        label.setMinimumHeight(label.heightForWidth(int(390 * self.scale_factor)))

    def _fit_title(self, label, layout, room):
        """Fit a text title to the column, which never grows: the window has one size.

        Claiming every line was not enough on its own. With Mods, Add to Steam and
        Bonus as well, a title of three or four lines and the buttons were taller
        than the column, and the layout put PLAY GAMES on top of the title's last
        line. The type steps down instead, to 22 px at most, measured with the
        layout's own minimum; past that the title is cut, never overlapped.
        """
        size = int(36 * self.scale_factor)
        floor = int(22 * self.scale_factor)
        step = max(1, int(2 * self.scale_factor))

        def over():
            layout.invalidate()
            return layout.minimumSize().height() - room

        while over() > 0 and size - step >= floor:
            old = "font-size: %dpx" % size
            size -= step
            label.setStyleSheet(label.styleSheet().replace(old, "font-size: %dpx" % size))
            self._keep_title_whole(label)
        excess = over()
        if excess > 0:
            label.setMinimumHeight(max(0, label.minimumHeight() - excess))

    def shout(self, text):
        """A label in capitals, as the menu's language writes them: a Turkish i
        keeps its dot (SEÇİN, never SEÇIN), and Greek capitals drop their accents."""
        if self.current_lang == "Turkish":
            text = text.replace("i", "İ")
        text = text.upper()
        if self.current_lang == "Greek":
            text = unicodedata.normalize("NFC", "".join(
                c for c in unicodedata.normalize("NFD", text) if c != chr(0x301)))
        return text

    def play_label(self, trans):
        """The top button's words: Install on an install-first disc, Play Games
        on a disc of several games (it opens the Choose Your Game page), else
        Play Game."""
        if getattr(self, "installer_path", ""):
            return self.shout(trans["install"])
        if len(self.games) > 1:
            return self.shout(trans["play_games"])
        return self.shout(trans["play"])

    def change_language(self, lang):
        self.current_lang = lang
        trans = self.translations[lang]
        # Remembered on this PC, so the menu opens in it next time.
        self.player_prefs["lang"] = lang
        self.keep_player_prefs()

        # Update UI text - keep label text as "Menu Language:", so a player who
        # picked a language they cannot read can still find the way back.
        self.play_btn.setText(self.play_label(trans))
        if getattr(self, "installer_path", ""):
            self.play_btn.setToolTip(trans["tip_install"])
        # compatibility_label() and compatibility_hint() re-read the author's
        # overrides, so a disc that named or described the mode itself keeps
        # that wording in every language.
        if getattr(self, 'compat_btn', None) is not None:
            self.compat_btn.setText(self.compatibility_label())
            self.compat_btn.setToolTip(self.compatibility_hint())
        if hasattr(self, 'bonus_btn'):
            self.bonus_btn.setText(self.shout(trans["bonus"]))
            self.bonus_btn.setToolTip(trans["tip_bonus"])
        if hasattr(self, 'mods_btn'):
            self.mods_btn.setText(trans["mods"])
            self.mods_btn.setToolTip(trans["tip_mods"])
        if getattr(self, 'steam_btn', None) is not None:
            self.steam_btn.setText(trans["steam"])
            self.steam_btn.setToolTip(trans["tip_steam"])
        self.uninstall_btn.setText(self.shout(trans["uninstall"]))
        self.uninstall_btn.setToolTip(trans["tip_uninstall"])
        self.exit_btn.setText(self.shout(trans["exit"]))
    
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
        trans = self.translations[self.current_lang]
        games = self._steam_game_list()
        if not games:
            self._menu_message(trans["steam_none_title"], trans["steam_none"], trans["steam_none_detail"])
            return
        shortcut_files = self._steam_shortcuts_paths()
        if not shortcut_files:
            self._menu_message(trans["steam_missing_title"], trans["steam_missing"], trans["steam_missing_detail"])
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
                trans["steam_running_title"], trans["steam_running"],
                trans["steam_running_why"] + "\\n\\n" + trans["steam_running_detail"])
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
            self._menu_message(trans["steam_added_title"], trans["steam_added"] % ", ".join(added_names),
                               trans["steam_added_detail"])
        elif already_there:
            self._menu_message(trans["steam_already_title"], trans["steam_already"] % ", ".join(already_there),
                               trans["steam_already_detail"])
        elif blocked:
            self._menu_message(trans["steam_failed_title"], trans["steam_blocked"], trans["steam_blocked_detail"])
        elif reached_any:
            self._menu_message(trans["steam_none_title"], trans["steam_none"], trans["steam_none_detail"])
        else:
            self._menu_message(trans["steam_failed_title"], trans["steam_unread"], trans["steam_unread_detail"])

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
        box.setTextFormat(QtCore.Qt.PlainText)  # "Looked for:" quotes the config
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
        """Say what happened, and underneath it what to do about it. The OK
        button is the menu's own: Qt's stock one says OK in every language."""
        box = self._message_box(QtWidgets.QMessageBox.Information, title, body, detail)
        box.addButton(self.translations[self.current_lang]["ok"], QtWidgets.QMessageBox.AcceptRole)
        box.exec_()

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
            self._menu_message(trans["error"], trans["game_not_found"], trans["looked_for"] % rel_exe)

    def nav_buttons(self):
        """The menu's buttons top to bottom, as the screen shows them.

        For the arrow keys and a controller. Two hand-kept lists used to do
        this, and both had drifted from the screen: Compatibility Mode was in
        neither, and Bonus came before Mods.
        """
        order = [self.play_btn, getattr(self, "compat_btn", None)]
        order += list(getattr(self, "quick_btns", []))
        order += [getattr(self, "mods_btn", None), getattr(self, "steam_btn", None),
                  getattr(self, "bonus_btn", None), self.uninstall_btn, self.exit_btn]
        return [b for b in order if b is not None]

    def game_label(self, game):
        """A game's name as the author gave it, else its exe's name."""
        raw = str(game.get("name") or os.path.splitext(os.path.basename(str(game.get("exe") or "")))[0])
        return "".join(c if c >= " " else " " for c in raw).strip()[:80] or "Game"

    def game_blurb(self, game):
        """The author's one line about a game, for the Play page."""
        raw = str(game.get("blurb") or "")
        return "".join(c if c >= " " else " " for c in raw).strip()[:140]

    def game_picture(self, game):
        """The game's picture on the Play page.

        The author's image when it is a picture inside the install folder
        (menu_config.json can be rewritten, so the path is held to the same
        containment as an exe), else the exe's own icon.
        """
        rel = str(game.get("icon") or "").strip()
        if rel and not os.path.isabs(rel) and rel.lower().endswith((".ico", ".png", ".jpg", ".jpeg", ".bmp")):
            path = os.path.normpath(os.path.join(self.game_dir, rel))
            try:
                fits = os.path.isfile(path) and os.path.getsize(path) <= 8 * 1024 * 1024
            except OSError:
                fits = False
            if fits and self._inside_game_dir(path):
                pixmap = QtGui.QPixmap(path)
                if not pixmap.isNull():
                    return QtGui.QIcon(pixmap)
        exe = self._configured_exe(game.get("exe"))
        if exe:
            return QtWidgets.QFileIconProvider().icon(QtCore.QFileInfo(exe))
        return QtGui.QIcon()

    def keep_player_prefs(self):
        # A preview runs on the author's own PC: what they click there is not a
        # player's choice, so it lasts only as long as the preview.
        if not self.preview_mode:
            write_player_prefs(MENU_TITLE, self.player_prefs)

    def listed_games(self):
        """Every game, for the lines under PLAY GAMES: the starred ones first,
        then the rest, each group A to Z."""
        if len(self.games) < 2 or getattr(self, "installer_path", ""):
            return []
        stars = self.player_prefs.get("stars", [])
        return sorted(self.games, key=lambda g: (g["exe"] not in stars, self.game_label(g).casefold()))

    def start_one_game(self, exe, args=None):
        if self.preview_mode:
            self.show_preview_notice()
        else:
            self.launch_configured_exe(exe, args)

    def refresh_quick_starts(self):
        """Rebuild the lines under PLAY GAMES: every game, starred ones first."""
        layout = getattr(self, "quick_layout", None)
        if layout is None:
            return
        for btn in self.quick_btns:
            layout.removeWidget(btn)
            btn.deleteLater()
        self.quick_btns = []
        stars = self.player_prefs.get("stars", [])
        # The line's room inside the menu column, less the indent it slides to
        # on hover: a longer name ends in an ellipsis and shows whole as a tooltip.
        # The star follows the name, so every name starts at the same place.
        room = int(330 * self.scale_factor)
        for game in self.listed_games():
            name = self.game_label(game)
            mark = "  ★" if game["exe"] in stars else ""
            btn = QtWidgets.QPushButton()
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet(self.quick_style)
            btn.ensurePolished()
            metrics = btn.fontMetrics()
            shown = metrics.elidedText(name, QtCore.Qt.ElideRight, room - metrics.horizontalAdvance(mark))
            btn.setText(shown + mark)
            if shown != name:
                btn.setToolTip(name)
            btn.clicked.connect(lambda _checked=False, exe=game["exe"]: self.start_one_game(exe))
            btn.installEventFilter(self)
            layout.addWidget(btn)
            # A line added to a menu already on screen is shown by Qt a moment
            # later, and a hidden line measures as nothing: starring a game on the
            # page squeezed the whole list to 1 px until the menu was started again.
            btn.show()
            self.quick_btns.append(btn)
        # As tall as its lines where the column has room, and never shorter than
        # two of them; past that the box scrolls. Summed from the lines themselves.
        tall = sum(b.sizeHint().height() for b in self.quick_btns)
        line = self.quick_btns[0].sizeHint().height() if self.quick_btns else 0
        self.quick_scroll.setMaximumHeight(max(tall, 1))
        self.quick_scroll.setMinimumHeight(min(tall, line * 2))
        self.quick_scroll.setVisible(bool(self.quick_btns))
        order = self.nav_buttons()
        for first, second in zip(order, order[1:]):
            QtWidgets.QWidget.setTabOrder(first, second)

    def show_in_list(self, btn):
        """Scroll a game's line into view when the keyboard or a controller reaches it."""
        if btn in getattr(self, "quick_btns", []):
            self.quick_scroll.ensureWidgetVisible(btn)

    def show_game_chooser(self, args=None):
        # A disc of several games (1.5.1, B9): the Play page. Each game with its
        # picture, its name and the author's line about it, and a star that lifts
        # it to the top here and under PLAY GAMES. As on the disc or A to Z, the
        # player's choice, kept on this PC with the stars. `args` rides along so a
        # compatibility launch still asks which game first.
        args = args or []
        trans = self.translations[self.current_lang]
        scale = self.scale_factor
        dialog = QtWidgets.QDialog(self)
        # No "?" in the title bar: Qt 5 gives every dialog Windows' context-help
        # button, and nothing on this page answers it, so a click did nothing.
        dialog.setWindowFlags(dialog.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog.setWindowTitle(trans["choose_game"])
        # Sized to the screen it opens on, not a fixed 560 (1.5.1, end-to-end runs): each game's name and
        # line wrap inside its row, so every picture, name, line and star shows at any width.
        handle = self.windowHandle()
        screen = ((handle.screen() if handle is not None else None)
                  or QtWidgets.QApplication.instance().primaryScreen()).availableGeometry()
        widest = max(int(screen.width() * 0.9), 320)
        dialog.setMinimumWidth(min(int(560 * scale), widest))
        icon_path = os.path.join(self.game_dir, "game_icon.ico")
        if os.path.exists(icon_path):
            dialog.setWindowIcon(QtGui.QIcon(icon_path))
        self._dark_frame(dialog)
        dialog.setStyleSheet("""
            QDialog { background-color: #1a1a1a; }
            QLabel { color: #ffffff; background: transparent; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
            QPushButton {
                background-color: rgba(40, 40, 40, 200);
                color: #ffffff;
                border: 2px solid rgba(255, 255, 255, 40);
                padding: 12px 18px;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 1px;
                text-align: left;
            }
            QPushButton:hover { border-color: #ffffff; background-color: rgba(60, 60, 60, 220); }
            QFrame#gameRow { background-color: rgba(40, 40, 40, 200); border: 2px solid rgba(255, 255, 255, 40); }
            QFrame#gameRow:hover, QFrame#gameRow:focus {
                border-color: #ffffff; background-color: rgba(60, 60, 60, 220);
            }
            QLabel#gameName { font-size: 15px; font-weight: bold; letter-spacing: 1px; }
            QLabel#gameLine { font-size: 13px; color: #cccccc; }
            QPushButton#star { font-size: 20px; padding: 8px 14px; text-align: center; color: #888888; }
            QPushButton#star[starred="true"] { color: #ffd54a; }
            QPushButton#star:focus { border-color: #ffffff; }
            QPushButton#sort {
                font-size: 11px; padding: 6px 10px; text-align: center;
                color: #888888; border: 1px solid rgba(255, 255, 255, 20);
            }
            QPushButton#sort:checked { color: #ffffff; border-color: rgba(255, 255, 255, 120); }
        """)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(self.shout(trans["choose_game"]))
        title.setStyleSheet("font-size: 13px; font-weight: bold; letter-spacing: 4px; color: #aaaaaa;")
        head.addWidget(title)
        head.addStretch()
        sort_buttons = {}
        for key in ("disc", "az"):
            btn = QtWidgets.QPushButton(trans["sort_" + key])
            btn.setObjectName("sort")
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: set_sort(k))
            sort_buttons[key] = btn
            head.addWidget(btn)
        layout.addLayout(head)

        rows = QtWidgets.QWidget()
        rows_layout = QtWidgets.QVBoxLayout(rows)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(8)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setFocusPolicy(QtCore.Qt.NoFocus)  # no stop of its own between the rows and the sort buttons
        scroll.setWidget(rows)
        layout.addWidget(scroll)

        hint = QtWidgets.QLabel(trans["tip_star"])
        hint.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(hint)

        def ordered():
            games = list(self.games)
            if self.player_prefs.get("sort") == "az":
                games.sort(key=lambda g: self.game_label(g).casefold())
            # Starred games first, each group in the order chosen above.
            stars = self.player_prefs.get("stars", [])
            return sorted(games, key=lambda g: g["exe"] not in stars)

        def make_play(exe):
            def play():
                dialog.accept()
                self.start_one_game(exe, args)
            return play

        class GameRow(QtWidgets.QFrame):
            """One game: its picture, its name and the author's line, each wrapped to the row's width.
            Pressed like a button: a click, Enter or Space."""

            def __init__(self, on_press):
                super().__init__()
                self.on_press = on_press
                self.exe = None  # the game it starts, and its star: set by fill()
                self.star = None
                self.setObjectName("gameRow")
                self.setFocusPolicy(QtCore.Qt.StrongFocus)
                self.setCursor(QtCore.Qt.PointingHandCursor)
                self.setAttribute(QtCore.Qt.WA_Hover, True)

            def mouseReleaseEvent(self, event):
                if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.pos()):
                    self.on_press()
                else:
                    super().mouseReleaseEvent(event)

            def keyPressEvent(self, event):
                if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space):
                    self.on_press()
                elif event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
                    self.step(event.key() == QtCore.Qt.Key_Down)
                elif event.key() == QtCore.Qt.Key_Right and getattr(self, "star", None) is not None:
                    self.star.setFocus(QtCore.Qt.TabFocusReason)
                else:
                    super().keyPressEvent(event)

            def step(self, down):
                """Row to row, for the arrow keys and a pad. The star between two rows is for a
                click, Tab or Right: stepping onto it made the next Enter star the game."""
                ring = list(row_order)
                i = ring.index(self) + (1 if down else -1) if self in ring else 0
                if 0 <= i < len(ring):
                    ring[i].setFocus(QtCore.Qt.TabFocusReason if down else QtCore.Qt.BacktabFocusReason)
                    scroll.ensureWidgetVisible(ring[i])

        def breakable(text):
            # A long name with no space (Sky_Quest_Remastered) cannot wrap, and one such row would push
            # every star off the page: a zero-width space after an underscore, a dot or a slash, and in
            # any run of 16 letters, gives the line somewhere to break. Nothing visible changes.
            out, run = [], 0
            for ch in text:
                out.append(ch)
                if ch.isspace() or ch == "-":
                    run = 0
                    continue
                run += 1
                if ch in "_./" or run >= 16:
                    out.append(chr(0x200B))
                    run = 0
            return "".join(out)

        def words(text, name):
            label = QtWidgets.QLabel(breakable(text))
            label.setObjectName(name)
            label.setTextFormat(QtCore.Qt.PlainText)
            label.setWordWrap(True)
            label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            return label

        def fit_list():
            # Every game in view up to two thirds of the screen; past that, the
            # list scrolls rather than the page running off the bottom. Measured
            # at the width the rows have, with their words wrapped.
            width = scroll.viewport().width() if dialog.isVisible() else dialog.width() - 48
            tall = rows.heightForWidth(width) if rows.hasHeightForWidth() else -1
            scroll.setMinimumHeight(min(tall if tall > 0 else rows.sizeHint().height(), int(screen.height() * 0.66)))

        row_order = []  # the rows as the page shows them
        placed = {}  # a game's exe: its row and its star

        def fill():
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            del row_order[:]
            placed.clear()
            stars = self.player_prefs.get("stars", [])
            for game in ordered():
                row = QtWidgets.QWidget()
                line = QtWidgets.QHBoxLayout(row)
                line.setContentsMargins(0, 0, 0, 0)
                blurb = self.game_blurb(game)
                play = GameRow(make_play(game["exe"]))
                inside = QtWidgets.QHBoxLayout(play)
                inside.setContentsMargins(16, 10, 16, 10)
                inside.setSpacing(14)
                side = int(40 * scale)
                picture = QtWidgets.QLabel()
                picture.setFixedSize(side, side)
                picture.setPixmap(self.game_picture(game).pixmap(side, side))
                picture.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
                inside.addWidget(picture, 0, QtCore.Qt.AlignTop)
                text = QtWidgets.QVBoxLayout()
                text.setSpacing(3)
                text.addWidget(words(self.game_label(game).upper(), "gameName"))
                if blurb:
                    text.addWidget(words(blurb, "gameLine"))
                inside.addLayout(text, 1)
                starred = game["exe"] in stars
                star = QtWidgets.QPushButton("★" if starred else "☆")
                star.setObjectName("star")
                star.setProperty("starred", "true" if starred else "false")
                star.setCursor(QtCore.Qt.PointingHandCursor)
                star.clicked.connect(lambda _checked=False, exe=game["exe"]: toggle_star(exe))
                play.exe = star.exe = game["exe"]
                play.star = star
                star.row = play
                row_order.append(play)
                placed[game["exe"]] = (play, star)
                line.addWidget(play, 1)
                line.addWidget(star)
                rows_layout.addWidget(row)
            rows_layout.addStretch()
            for key, btn in sort_buttons.items():
                btn.setChecked(self.player_prefs.get("sort", "disc") == key)
            fit_list()

        def set_sort(key):
            self.player_prefs["sort"] = key
            self.keep_player_prefs()
            fill()

        def toggle_star(exe):
            focus = dialog.focusWidget()
            kept = getattr(focus, "exe", None) == exe and focus.objectName() in ("star", "gameRow")
            on_star = kept and focus.objectName() == "star"
            stars = [x for x in self.player_prefs.get("stars", []) if x != exe]
            if exe not in self.player_prefs.get("stars", []):
                stars.append(exe)
            # Any number: a star lifts a game to the top of both lists.
            self.player_prefs["stars"] = stars[-MAX_STARS:]
            self.keep_player_prefs()
            fill()
            self.refresh_quick_starts()
            # The keyboard or the pad keeps its place: on the same game, which may have moved.
            if kept and exe in placed:
                target = placed[exe][1] if on_star else placed[exe][0]
                target.setFocus()
                scroll.ensureWidgetVisible(target)

        # Opened wide enough for a long line on one or two rows, never wider than the screen it is on.
        dialog.resize(min(max(int(820 * scale), dialog.minimumWidth()), widest), dialog.height())
        fill()
        tall = dialog.layout().totalHeightForWidth(dialog.width()) if dialog.layout().hasHeightForWidth() else -1
        dialog.resize(dialog.width(), min(tall if tall > 0 else dialog.sizeHint().height(), int(screen.height() * 0.9)))
        if row_order:
            row_order[0].setFocus()  # the first game, ready for Enter or a pad's A
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
            detail += "\\n    " + trans["and_more"] % (len(searched) - len(shown))
        self._menu_message(
            trans["error"], trans["game_not_found"],
            trans["looked_in"] + "\\n" + detail + "\\n\\n" + trans["play_again"])

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
            # A tooltip reads markup by itself, so angle brackets from the
            # rewritable config are shown, never obeyed (1.5.1 security re-read).
            return raw[:200].replace("<", "‹").replace(">", "›")
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
            self._menu_message(trans["warning"], trans["bonus_not_found"], trans["bonus_detail"])

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
            self._menu_message(trans["warning"], trans["mods_not_found"], trans["mods_detail"])

    def uninstall_game(self):
        if self.preview_mode:
            self.show_preview_notice()
            return
        uninstaller = os.path.join(self.game_dir, "unins000.exe")
        if os.path.exists(uninstaller):
            trans = self.translations[self.current_lang]
            if self._menu_confirm(trans["warning"], trans["confirm_uninstall"], trans["tip_uninstall"]):
                subprocess.Popen([uninstaller])
                QtWidgets.QApplication.instance().quit()
        else:
            trans = self.translations[self.current_lang]
            self._menu_message(trans["warning"], trans["uninstaller_not_found"], trans["uninstaller_detail"])
    
    def init_controller_support(self):
        """A pad drives the menu as the keyboard does: see check_gamepad_input."""
        self.current_button_index = 0
        self.pad_held = 0
        self.pad_slots = []
        self.pad_scan_due = 0.0
        self.pad_repeat = None
        self.xinput = load_xinput()
        self.gamepad_timer = QtCore.QTimer(self)
        self.gamepad_timer.timeout.connect(self.check_gamepad_input)
        if self.xinput is not None:
            # A button already down as the menu opens (A, from a front end that started it) is not a
            # press: it started a game, or setup.exe, nobody chose.
            self.pad_held = self.read_pads()
            self.gamepad_timer.start(25)

    def read_pads(self):
        """The buttons held on every connected pad, as one set of XInput bits, the left stick
        counting as the D-pad. An empty slot is asked again only every two seconds: asking a
        slot with no pad in it is slow."""
        now = time.monotonic()
        if now >= self.pad_scan_due:
            slots, self.pad_scan_due = range(4), now + 2.0
        else:
            slots = list(self.pad_slots)
        state = XInputState()
        held, connected = 0, []
        for slot in slots:
            try:
                if self.xinput(slot, ctypes.byref(state)) != 0:
                    continue
            except Exception:
                continue
            connected.append(slot)
            pad = state.Gamepad
            held |= pad.wButtons
            for value, sign, bit in ((pad.sThumbLY, 1, PAD_UP), (pad.sThumbLY, -1, PAD_DOWN),
                                     (pad.sThumbLX, -1, PAD_LEFT), (pad.sThumbLX, 1, PAD_RIGHT)):
                mark = PAD_STICK_OFF if self.pad_held & bit else PAD_STICK
                if value * sign > mark:
                    held |= bit
        self.pad_slots = connected
        return held

    def check_gamepad_input(self):
        """Read the pads every 25 ms and act on what was just pressed.

        Every press is acted on a moment later, outside this timer. A press that opens the
        Choose Your Game page or a message box starts that window's own loop, and a timer
        still inside its own call never fires again: the pad went dead on the page. Only
        while the player is looking at this menu: never behind a game or another window.
        """
        if self.xinput is None:
            return
        held = self.read_pads()
        pressed = held & ~self.pad_held
        self.pad_held = held
        if QtWidgets.QApplication.activeWindow() is None:
            self.pad_repeat = None
            return
        now = time.monotonic()
        steer = held & PAD_STEER
        if pressed & PAD_STEER:
            self.pad_repeat = (steer, now + 0.4)
            self.pad_later(pressed & PAD_STEER)
        elif steer and self.pad_repeat and self.pad_repeat[0] == steer and now >= self.pad_repeat[1]:
            # Held, it repeats after a short wait, as a held arrow key does.
            self.pad_repeat = (steer, now + 0.12)
            self.pad_later(steer)
        elif not steer:
            self.pad_repeat = None
        for bit in (PAD_A, PAD_START, PAD_B, PAD_Y):
            if pressed & bit:
                self.pad_later(bit)

    def pad_later(self, bits):
        """Act on one press after this poll returns; one direction at a time, Up first."""
        for bit in (PAD_UP, PAD_DOWN, PAD_LEFT, PAD_RIGHT, PAD_A, PAD_START, PAD_B, PAD_Y):
            if bits & bit:
                QtCore.QTimer.singleShot(0, lambda bit=bit: self.pad_act(bit))
                return

    def pad_act(self, bit):
        """One press: on a window the menu opened, there; else on the menu's own buttons,
        where the pad and the keyboard share one place, the focused button."""
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None:
            self.pad_act_in_dialog(modal, bit)
            return
        buttons = self.nav_buttons()
        if not buttons:
            return
        focus = QtWidgets.QApplication.focusWidget()
        if focus in buttons:
            self.current_button_index = buttons.index(focus)
        else:
            # Nothing of the menu's has focus yet: the first press only shows where the pad is.
            if not 0 <= self.current_button_index < len(buttons):
                self.current_button_index = 0
            buttons[self.current_button_index].setFocus()
            self.show_in_list(buttons[self.current_button_index])
            return
        if bit == PAD_UP:
            self.navigate_up(buttons)
        elif bit == PAD_DOWN:
            self.navigate_down(buttons)
        elif bit in (PAD_A, PAD_START):
            buttons[self.current_button_index].click()

    def pad_act_in_dialog(self, dialog, bit):
        """The pad on the Choose Your Game page or a message box. Up and Down move (row to
        row on the page), Left and Right move between a row and its star or between Yes and
        No, A presses, Y stars the game in focus, B closes the window as Escape would."""
        focus = dialog.focusWidget()
        if bit == PAD_B:
            escape = dialog.escapeButton() if isinstance(dialog, QtWidgets.QMessageBox) else None
            if escape is not None:
                escape.click()
            else:
                dialog.reject()
        elif bit in (PAD_UP, PAD_DOWN) and hasattr(focus, "step"):
            focus.step(bit == PAD_DOWN)
        elif hasattr(focus, "step") and bit in (PAD_LEFT, PAD_RIGHT):
            if bit == PAD_RIGHT and focus.star is not None:
                focus.star.setFocus()  # a row's star, as Right does on the keyboard
        elif getattr(focus, "row", None) is not None and bit & PAD_STEER:
            # On a star: Left goes back to its row, Up and Down move on from it.
            if bit == PAD_LEFT:
                focus.row.setFocus()
            elif bit in (PAD_UP, PAD_DOWN):
                focus.row.step(bit == PAD_DOWN)
        elif bit & PAD_STEER:
            dialog.focusNextPrevChild(bit in (PAD_DOWN, PAD_RIGHT))
        elif bit in (PAD_A, PAD_START):
            if hasattr(focus, "on_press"):
                focus.on_press()
            elif isinstance(focus, QtWidgets.QAbstractButton):
                focus.click()
        elif bit == PAD_Y and getattr(focus, "star", None) is not None:
            focus.star.click()
        elif bit == PAD_Y and getattr(focus, "row", None) is not None:
            focus.click()  # Y on the star itself

    def navigate_up(self, buttons):
        """Navigate up in menu"""
        if self.current_button_index > 0:
            self.current_button_index -= 1
        else:
            self.current_button_index = len(buttons) - 1  # Wrap to last
        buttons[self.current_button_index].setFocus()
        self.show_in_list(buttons[self.current_button_index])
    
    def navigate_down(self, buttons):
        """Navigate down in menu"""
        if self.current_button_index < len(buttons) - 1:
            self.current_button_index += 1
        else:
            self.current_button_index = 0  # Wrap to first
        buttons[self.current_button_index].setFocus()
        self.show_in_list(buttons[self.current_button_index])

    def eventFilter(self, obj, event):
        """Up and Down pressed on one of the menu's buttons move through the menu.

        A button left to itself takes the arrow keys and moves along Qt's tab
        chain, which is the order the buttons were made in, not the screen's: the
        games under PLAY GAMES are made last, so Down from PLAY GAMES jumped to
        UNINSTALL, and keyPressEvent below (the screen's order, shared with a
        controller) only ever ran when no button had focus.
        """
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
                self.keyPressEvent(event)
                return True
            if event.key() in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right):
                return True  # a column of buttons has no left or right
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        buttons = self.nav_buttons()

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
    # No context-help "?" on any dialog this menu opens (Qt 5 adds one to each).
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_DisableWindowContextHelpButton)
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
    try:
        ensure_structure()
    except OSError:
        # A folder Rialto cannot write to, such as a zip unpacked into Program Files: one plain message
        # instead of a crash at the first line (1.5.1, launch day).
        import tkinter.messagebox
        _root = tk.Tk()
        _root.withdraw()
        tkinter.messagebox.showerror(
            "Rialto",
            "Rialto can't write to the folder it is in:\n%s\n\nRialto keeps its settings, profiles and "
            "discs beside itself, so it needs a folder you can write to. Install it with "
            "Rialto-%s-Setup.exe, or unzip it into a folder of your own, not Program Files." % (APP_ROOT, __version__))
        _root.destroy()
        sys.exit(1)
    # The name Rialto's Setup watches (its AppMutex), so an update asks for Rialto to be closed before
    # it starts. Left to Windows' Restart Manager, the window closed but the one-file EXE's first process
    # stayed running and held Rialto.exe, and the update could not replace it (1.5.1, launch day). Released
    # by Windows when Rialto exits; kept in a module global until then.
    try:
        import ctypes
        _SETUP_WATCHES = ctypes.windll.kernel32.CreateMutexW(None, False, "RialtoDiscMaker15")
    except Exception:
        _SETUP_WATCHES = None
    root = tk.Tk()
    app = RialtoApp(root)
    quiet_alt_tap(root, when=lambda: getattr(app, "_building", False))  # its menus stay a keypress away otherwise
    root.mainloop()