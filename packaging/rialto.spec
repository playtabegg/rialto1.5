# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Rialto 1.5.

Build with:  pyinstaller packaging/rialto.spec      (from the repo root)
Then sign dist/Rialto.exe the same way builds are signed (rialto/trusted_signing.py).

This file lives in packaging/; every path below is taken from ROOT, the folder
above it, where Rialto.pyw is.

Three things Rialto needs from a frozen build:
  * docs/rialto-guide.html inside the bundle, because Help, Help Guide opens it
    (see RialtoApp.doc_path - it checks beside the exe first, then _MEIPASS,
    and copies a bundled page out to APP_ROOT/docs before handing it to the
    browser, because _MEIPASS is deleted when Rialto exits and the browser
    would be left pointing at nothing).
  * docs/signing-guide.html inside the bundle, for the same reason: the
    Configure Signing dialog's Read the Guide button opens it, and a frozen
    Rialto has no checkout to fall back on.
  * requirements.txt inside the bundle. A frozen build never installs anything
    - its dependencies are already inside the bundle and sys.executable there
    is Rialto.exe, not a python that could run pip, so the bootstrap at the top
    of Rialto.pyw skips itself entirely. The file rides along so the bundle
    still says what it was built against.
  * helpers/inno and helpers/cdrtools (1.5.1): the Inno Setup 6.5.4 and
    mkisofs Rialto carries, so nobody has to install them, with licenses/
    beside them. tools-dev/fetch_helpers.py puts them in helpers/; this spec
    refuses to build unless every file matches its pin in helpers/MANIFEST.json
    and nothing unpinned is there. Rialto runs them from the bundle (see
    helper_path in Rialto.pyw), never from a helpers folder beside the exe.
Rialto's own working files (config.json, input/, output/, signing_config.json,
the cached signing dlib) deliberately do NOT live in the bundle - they are
anchored next to the exe by app_root() in Rialto.pyw and _base_dir() in
rialto/trusted_signing.py, so they survive the temp folder being cleaned up.
"""

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

import os
import re as _re

# This spec sits in packaging/. Everything it builds from is one folder up.
ROOT = os.path.dirname(SPECPATH)


def _src(relative):
    """A path in the checkout, from its repo-relative name ("assets/bird_icon.ico")."""
    return os.path.join(ROOT, *relative.split("/"))


# The version lives in Rialto.pyw (`__version__`); this reads that line so a
# release cannot ship with the file properties and the About text apart.
# tools-dev/test_version_agreement.py pins the three together.
with open(_src("Rialto.pyw"), encoding="utf-8") as _pyw:
    _match = _re.search(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"', _pyw.read(), _re.M)
if not _match:
    raise SystemExit("Rialto.pyw has no __version__ = \"X.Y.Z\" line")
VERSION = (int(_match.group(1)), int(_match.group(2)), int(_match.group(3)), 0)
VERSION_STR = "%d.%d.%d.%d" % VERSION

# The carried tools (1.5.1): refuse to build a Rialto.exe without them, or with
# any file that is not exactly the pinned one. The check is fetch_helpers.problems.
import sys as _sys
_sys.path.insert(0, _src("tools-dev"))
from fetch_helpers import problems as _helper_problems
_HELPER_PROBLEMS = _helper_problems(_src("helpers"))
if _HELPER_PROBLEMS:
    raise SystemExit("Rialto.exe carries Inno Setup and mkisofs, and helpers/ is not ready:\n  "
                     + "\n  ".join(_HELPER_PROBLEMS)
                     + "\nRun: python tools-dev/fetch_helpers.py")

# A real VS_VERSION_INFO resource. The old spec passed `version_info={...}` to
# EXE, which is not a parameter PyInstaller knows - it was silently dropped and
# the exe shipped with no version resource at all. Signed releases need one:
# it is what Windows shows in the file properties and what SmartScreen and AV
# reputation systems key on alongside the signature.
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
                    # The legal entity, spelled exactly as the signing
                    # certificate spells it (CN="We The Indies, LLC"), so the
                    # Details tab and the Digital Signatures tab agree.
                    # LegalCopyright below stays in the brand's voice, matching
                    # LICENSE.
                    StringStruct("CompanyName", "We The Indies, LLC"),
                    StringStruct("FileDescription", "Rialto %d.%d.%d Disc Maker" % VERSION[:3]),
                    StringStruct("FileVersion", VERSION_STR),
                    StringStruct("InternalName", "Rialto"),
                    StringStruct("LegalCopyright",
                                 "Copyright (c) 2025-2026 We the Indies. MIT License."),
                    StringStruct("OriginalFilename", "Rialto.exe"),
                    StringStruct("ProductName", "Rialto"),
                    StringStruct("ProductVersion", VERSION_STR),
                ],
            ),
        ]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    [_src('Rialto.pyw')],
    # ROOT is where the rialto package is (rialto/trusted_signing.py, rialto/update/...).
    pathex=[ROOT],
    binaries=[],
    datas=[
        (_src('assets/bird_icon.ico'), 'assets'),
        (_src('assets/bird_logo.PNG'), 'assets'),
        (_src('assets/success.wav'), 'assets'),
        # Read at runtime by the first-run pip bootstrap
        (_src('requirements.txt'), '.'),
        # Opened by Help, Help Guide
        (_src('docs/rialto-guide.html'), 'docs'),
        # Opened by Read the Guide in the Configure Signing dialog
        (_src('docs/signing-guide.html'), 'docs'),
        # Not opened by anything in the app; rides along so a downloaded
        # Rialto.exe still carries the text GitHub readers see.
        (_src('README.md'), '.'),
        (_src('SIGNING.md'), '.'),
        # The tools Rialto carries (1.5.1), checked against their pins above,
        # and the license texts that go with them.
        (_src('helpers/inno'), 'helpers/inno'),
        (_src('helpers/cdrtools'), 'helpers/cdrtools'),
        (_src('licenses'), 'licenses'),
        # templates/ is NOT bundled: it is a user folder Rialto creates next to
        # the exe for saved profiles, so a read-only copy in the temp bundle
        # would only shadow it.
    ],
    # Rialto.pyw imports these inside the functions that use them, which
    # PyInstaller follows on its own; they are named here as well so a module
    # of Rialto's can never go missing from the EXE unnoticed.
    hiddenimports=[
        'rialto',
        'rialto.msix_export',
        'rialto.ssl_signing',
        'rialto.trusted_signing',
        'rialto.update',
        'rialto.update._ed25519',
        'rialto.update._semver',
        'rialto.update.check',
        'rialto.update.feed',
        'rialto.update.fetch',
        'rialto.update.keys',
        'rialto.update.minisig',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    # PyInstaller 6 removed `cipher`, `win_no_prefer_redirects` and
    # `win_private_assemblies`. It still accepts them, but raises the moment any
    # of them is truthy - so the old spec only survived because all three were
    # falsy. They are gone from here rather than left as a trap.
    noarchive=False,
)

# Likewise `a.zipped_data` / `a.zipfiles`: zipped eggs went away in PyInstaller
# 6, and both attributes are now permanently empty lists.
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Rialto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX stays off. It corrupts Qt binaries, and a packed exe is a strong
    # false-positive signal for antivirus heuristics - which defeats the point
    # of paying for a signature.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_src('assets/bird_icon.ico'),
    version=version_resource,
)
