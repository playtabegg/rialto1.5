# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the generic disc menu, menu.exe.

Build with:  pyinstaller menu.spec      ->  dist/menu.exe

This is the one menu executable every disc gets. It is title-agnostic: the
title, the button set, the game list, the language, the branding flag and the
mods/bonus settings all arrive at runtime from the menu_config.json that Rialto
stages beside it. Nothing here is per-game, so it is built once, signed once,
and copied onto discs like any other file - which is what lets a frozen Rialto
build a disc on a machine with no Python and no PyInstaller on it.

The source is not a file in the repo. It is MENU_TEMPLATE_SOURCE inside
Rialto.pyw, extracted here at build time, so the exe and the source Rialto falls
back to compiling cannot drift apart.

Two deliberate omissions, both because one exe serves white-labelled discs too:
  * the icon is a neutral play glyph, not the WTI bird
  * the version resource names no company and carries no copyright line
The per-title icon is unaffected - Windows shortcuts and the menu's own window
icon both point at the game's game_icon.ico, exactly as before.
"""

import os
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

sys.path.insert(0, os.path.join(SPECPATH, "tools-dev"))
from menu_source import write_menu_source  # noqa: E402

# Extract the disc menu out of Rialto.pyw. Single source of truth.
MENU_SCRIPT = write_menu_source(
    os.path.join(SPECPATH, "build", "menu_src"),
    rialto_path=os.path.join(SPECPATH, "Rialto.pyw"),
)

import re as _re

# The version lives in Rialto.pyw (`__version__`); this reads that line so a
# release cannot ship with the file properties and the About text apart.
# tools-dev/test_version_agreement.py pins the three together.
with open(os.path.join(SPECPATH, "Rialto.pyw"), encoding="utf-8") as _src:
    _match = _re.search(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"', _src.read(), _re.M)
if not _match:
    raise SystemExit("Rialto.pyw has no __version__ = \"X.Y.Z\" line")
VERSION = (int(_match.group(1)), int(_match.group(2)), int(_match.group(3)), 0)
VERSION_STR = "%d.%d.%d.%d" % VERSION

version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=VERSION,
        prodvers=VERSION,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,       # VOS_NT_WINDOWS32
        fileType=0x1,     # VFT_APP
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                "040904B0",  # US English, Unicode
                [
                    # No CompanyName and no LegalCopyright on purpose: this file
                    # ships unchanged on white-labelled discs.
                    StringStruct("FileDescription", "Disc Menu"),
                    StringStruct("FileVersion", VERSION_STR),
                    StringStruct("InternalName", "menu"),
                    StringStruct("OriginalFilename", "menu.exe"),
                    StringStruct("ProductName", "Disc Menu"),
                    StringStruct("ProductVersion", VERSION_STR),
                ],
            ),
        ]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    [MENU_SCRIPT],
    pathex=[],
    binaries=[],
    # Nothing bundled. Every file the menu reads - menu_config.json, the
    # background, game_logo.png, company_logo.png, bird_logo.PNG - is staged
    # next to the exe per title and found there at runtime.
    datas=[],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The menu never touches these; excluding them keeps the disc payload down.
    # QtMultimedia is excluded on purpose. Video backgrounds were dropped:
    # they play only where the player's own Windows can decode them, and a
    # finished disc cannot be patched when it turns out theirs cannot. GIF
    # backgrounds are decoded by Qt itself. Dropping it also takes several
    # MB off the copy of menu.exe that every single disc carries.
    excludes=['tkinter', 'PIL', 'numpy', 'PyQt5.QtWebEngineWidgets',
              'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='menu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX stays off for the same reasons as Rialto.exe: it corrupts Qt binaries,
    # and a packed exe is a strong false-positive signal for antivirus.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, 'assets', 'menu_icon.ico'),
    version=version_resource,
)
