"""Rialto finds Inno Setup 6 and oscdimg where their installers put them.

Rialto used to look for ISCC.exe on PATH and in one folder, the one Install
for all users picks, and for oscdimg only on PATH, which the Windows ADK never
edits. So a stranger who installed both the normal way still got
"ISCC.exe not found" or a ZIP instead of an ISO. Now find_inno_compiler and
find_iso_tools also read the folders the installers record in the registry
and their default folders, and inno_setup_7_only names the case where only
Inno Setup 7 is installed.

Source-extracted and exec'd with a fake registry, a fake PATH and temp folders:
no tkinter, no PyQt5, nothing read from this PC.
"""
import ast
import os
import re
import shutil
import sys
import tempfile
import types
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
HELPERS = ("_registry_string", "_inno_setup_folders", "_inno_setup_major", "find_inno_compiler",
           "inno_setup_7_only", "find_iso_tools", "helper_path", "carried_inno_compiler", "carried_mkisofs",
           "installer_compiler", "disc_image_tools", "tool_words", "missing_tool_refusals")
WOW_UNINSTALL = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Inno Setup 6_is1"
USER_UNINSTALL = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Inno Setup 6_is1"
KITS = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows Kits\\Installed Roots"

failures = []
SETS = {}


def ok(label, cond, detail=""):
    shown = (" -> " + ascii(detail)) if (detail and not cond) else ""
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, shown))
    if not cond:
        failures.append(label)


class FakeKey:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg(types.ModuleType):
    HKEY_LOCAL_MACHINE = "HKLM"
    HKEY_CURRENT_USER = "HKCU"

    def __init__(self, keys):
        super().__init__("winreg")
        self.keys = {(hive, path.lower()): values for (hive, path), values in keys.items()}

    def OpenKey(self, hive, subkey):
        if (hive, subkey.lower()) not in self.keys:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return FakeKey(self.keys[(hive, subkey.lower())])

    def QueryValueEx(self, key, value):
        if value not in key.values:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        return key.values[value], 1


def helpers(src):
    tree = ast.parse(src)
    wanted = {node.name: ast.get_source_segment(src, node) for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name in HELPERS}
    missing = [name for name in HELPERS if name not in wanted]
    if missing:
        raise SystemExit("could not extract " + ", ".join(missing))
    sets = next(ast.get_source_segment(src, node) for node in tree.body if isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "CARRIED_SETS")
    return sets + "\n\n" + "\n\n".join(wanted[name] for name in HELPERS)


def carried_sets(src):
    tree = ast.parse(src)
    node = next(node for node in tree.body if isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "CARRIED_SETS")
    ns = {}
    exec(ast.get_source_segment(src, node), ns)
    return ns["CARRIED_SETS"]


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"MZ")
    return path


class World:
    """A pretend PC: Program Files folders, a registry and a PATH, all in a temp folder."""

    def __init__(self, arch="AMD64"):
        self.base = tempfile.mkdtemp(prefix="rialto_tools_")
        self.pf86 = os.path.join(self.base, "Program Files (x86)")
        self.pf = os.path.join(self.base, "Program Files")
        self.local = os.path.join(self.base, "AppData", "Local")
        self.arch = arch
        self.registry = {}
        self.on_path = {}
        # Where Rialto runs from, and the one-file EXE's temp folder (None: a source run)
        self.app_root = os.path.join(self.base, "Rialto")
        self.meipass = None

    def carry(self, root, mkisofs=True, cygwin=True, inno=True, inno_rest=True):
        """The tools Rialto carries, in root/helpers, each with its whole set (CARRIED_SETS) unless told
        otherwise. Returns (ISCC.exe, mkisofs.exe)."""
        iscc = touch(os.path.join(root, "helpers", "inno", "ISCC.exe")) if inno else None
        if inno and inno_rest:
            for name in SETS["inno"]:
                touch(os.path.join(root, "helpers", "inno", *name.split("/")))
        mk = touch(os.path.join(root, "helpers", "cdrtools", "mkisofs.exe")) if mkisofs else None
        if cygwin:
            touch(os.path.join(root, "helpers", "cdrtools", "cygwin1.dll"))
        return iscc, mk

    def run(self, code, call, *args):
        env = {"ProgramFiles(x86)": self.pf86, "ProgramFiles": self.pf, "LOCALAPPDATA": self.local,
               "PROCESSOR_ARCHITECTURE": self.arch}
        fake_shutil = types.SimpleNamespace(which=lambda name: self.on_path.get(name))
        fake_sys = types.SimpleNamespace(**({"_MEIPASS": self.meipass} if self.meipass else {}))
        ns = {"os": os, "re": re, "shutil": fake_shutil, "sys": fake_sys, "APP_ROOT": self.app_root,
              "CARRIED_INNO_VERSION": "6.5.4", "INNO_SETUP_DOWNLOAD": "https://jrsoftware.org/isdl.php"}
        exec(code, ns)
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {"winreg": FakeWinreg(self.registry)}):
            os.environ.pop("PROCESSOR_ARCHITEW6432", None)
            return ns[call](*args)

    def close(self):
        shutil.rmtree(self.base, ignore_errors=True)


def oscdimg_under(root, arch):
    return os.path.join(root, "Assessment and Deployment Kit", "Deployment Tools", arch, "Oscdimg", "oscdimg.exe")


def main():
    with open(RIALTO, encoding="utf-8") as fh:
        src = fh.read()
    code = helpers(src)
    SETS.update(carried_sets(src))

    w = World()
    try:
        ok("a bare PC: no ISCC", w.run(code, "find_inno_compiler") is None)
        ok("a bare PC: not the Inno Setup 7 case", w.run(code, "inno_setup_7_only") is False)
        ok("a bare PC: no ISO tools", w.run(code, "find_iso_tools") == (None, None))

        w.on_path["ISCC.exe"] = r"D:\Tools\ISCC.exe"
        ok("ISCC on PATH still wins", w.run(code, "find_inno_compiler") == r"D:\Tools\ISCC.exe")
    finally:
        w.close()

    w = World()
    try:
        iscc = touch(os.path.join(w.pf86, "Inno Setup 6", "ISCC.exe"))
        ok("Install for all users, default folder", w.run(code, "find_inno_compiler") == iscc)
    finally:
        w.close()

    w = World()
    try:
        iscc = touch(os.path.join(w.local, "Programs", "Inno Setup 6", "ISCC.exe"))
        ok("Install for me only, default folder", w.run(code, "find_inno_compiler") == iscc)
    finally:
        w.close()

    w = World()
    try:
        custom = os.path.join(w.base, "Somewhere", "Inno")
        iscc = touch(os.path.join(custom, "ISCC.exe"))
        w.registry[("HKCU", USER_UNINSTALL)] = {"InstallLocation": custom + "\\"}
        ok("Install for me only, a folder of their own, read from the user uninstall key",
           w.run(code, "find_inno_compiler") == os.path.join(custom + "\\", "ISCC.exe"))
    finally:
        w.close()

    w = World()
    try:
        custom = os.path.join(w.base, "Tools", "Inno Setup 6")
        touch(os.path.join(custom, "ISCC.exe"))
        w.registry[("HKLM", WOW_UNINSTALL)] = {"InstallLocation": custom}
        found = w.run(code, "find_inno_compiler")
        ok("Install for all users, a folder of their own, read from the machine uninstall key",
           found == os.path.join(custom, "ISCC.exe"), found)
        w.registry[("HKLM", WOW_UNINSTALL)] = {"InstallLocation": os.path.join(w.base, "Deleted")}
        ok("a stale uninstall entry is skipped, not trusted", w.run(code, "find_inno_compiler") is None)
    finally:
        w.close()

    w = World()
    try:
        touch(os.path.join(w.pf, "Inno Setup 7", "ISCC.exe"))
        seven_only = os.path.join(w.pf, "Inno Setup 7", "ISCC.exe")
        ok("only Inno Setup 7: Rialto uses it (1.5.1)",
           os.path.normpath(w.run(code, "find_inno_compiler") or "") == os.path.normpath(seven_only))
        ok("only Inno Setup 7: named as such", w.run(code, "inno_setup_7_only") is True)
        six = touch(os.path.join(w.pf86, "Inno Setup 6", "ISCC.exe"))
        ok("6 beside 7: Rialto takes 6", w.run(code, "find_inno_compiler") == six)
        ok("6 beside 7: not the Inno Setup 7 case", w.run(code, "inno_setup_7_only") is False)
    finally:
        w.close()

    w = World()
    try:
        seven = touch(os.path.join(w.pf, "Inno Setup 7", "ISCC.exe"))
        w.on_path["ISCC.exe"] = seven
        ok("Inno Setup 7 put on PATH by hand is used when there is no 6", w.run(code, "find_inno_compiler") == seven)
        ok("and named as the Inno Setup 7 case", w.run(code, "inno_setup_7_only") is True)
        six = touch(os.path.join(w.pf86, "Inno Setup 6", "ISCC.exe"))
        ok("7 on PATH, 6 installed: Rialto still takes 6", w.run(code, "find_inno_compiler") == six)
        ok("7 on PATH, 6 installed: not the Inno Setup 7 case", w.run(code, "inno_setup_7_only") is False)
        w.on_path["ISCC.exe"] = os.path.join(w.base, "Tools", "Inno Setup 6", "ISCC.exe")
        ok("an Inno Setup 6 folder on PATH is used", w.run(code, "find_inno_compiler") == w.on_path["ISCC.exe"])
    finally:
        w.close()

    w = World()
    try:
        oscdimg = touch(oscdimg_under(os.path.join(w.pf86, "Windows Kits", "10"), "amd64"))
        ok("ADK in its default folder: oscdimg found without PATH", w.run(code, "find_iso_tools") == (None, oscdimg))
        w.on_path["mkisofs"] = r"D:\cdrtools\mkisofs.exe"
        ok("mkisofs on PATH is still returned beside it", w.run(code, "find_iso_tools") == (r"D:\cdrtools\mkisofs.exe", oscdimg))
        w.on_path["oscdimg"] = r"D:\Other\oscdimg.exe"
        ok("oscdimg on PATH still wins", w.run(code, "find_iso_tools")[1] == r"D:\Other\oscdimg.exe")
    finally:
        w.close()

    w = World()
    try:
        kits = os.path.join(w.base, "Kits") + "\\"
        oscdimg = touch(oscdimg_under(kits, "amd64"))
        w.registry[("HKLM", KITS)] = {"KitsRoot10": kits}
        ok("ADK in a folder of their own, read from KitsRoot10", w.run(code, "find_iso_tools") == (None, oscdimg))
    finally:
        w.close()

    w = World(arch="ARM64")
    try:
        root = os.path.join(w.pf86, "Windows Kits", "10")
        touch(oscdimg_under(root, "amd64"))
        arm = touch(oscdimg_under(root, "arm64"))
        ok("an ARM PC takes the arm64 oscdimg", w.run(code, "find_iso_tools") == (None, arm))
    finally:
        w.close()

    print("the tools Rialto carries (1.5.1): they fill the gap and never replace a tool on the PC")
    w = World()
    try:
        ok("a source checkout without helpers/: nothing carried", w.run(code, "installer_compiler") == (None, False)
           and w.run(code, "disc_image_tools", False) == [] and w.run(code, "disc_image_tools", True) == [])
        refusals = w.run(code, "missing_tool_refusals", False)
        ok("and the preflight names both, one sentence each", len(refusals) == 2
           and refusals[0].startswith("No installer compiler:") and refusals[1].startswith("No disc image tool:"),
           refusals)
        ok("an installers-only queue asks for the compiler alone",
           len(w.run(code, "missing_tool_refusals", False, False)) == 1)
        ok("a pressed disc's sentence names mkisofs and Pressed",
           "untick Pressed" in w.run(code, "missing_tool_refusals", True)[1])
        w.meipass = os.path.join(w.base, "_MEI1234")
        iscc, mk = w.carry(w.meipass)
        ok("the bare EXE: the carried Inno Setup, said as carried", w.run(code, "installer_compiler") == (iscc, True))
        ok("the bare EXE: the carried mkisofs", w.run(code, "disc_image_tools", False) == [("mkisofs", mk, True)])
        ok("the bare EXE, a pressed disc: the carried mkisofs", w.run(code, "disc_image_tools", True) == [("mkisofs", mk, True)])
        ok("the bare EXE: nothing missing", w.run(code, "missing_tool_refusals", True) == [])
        ok("helper_path finds a carried file, any slash", w.run(code, "helper_path", "inno/ISCC.exe") == iscc
           and w.run(code, "helper_path", "inno", "ISCC.exe") == iscc)
        ok("helper_path: None for a file not carried", w.run(code, "helper_path", "inno", "Compil32.exe") is None)
        # The security review (1.5.1): a frozen Rialto never runs a helpers folder put beside Rialto.exe,
        # complete or not. A zip unpacked into Rialto's folder could bring one, and nothing checks it.
        w.carry(w.app_root)
        ok("a frozen Rialto ignores helpers beside Rialto.exe: the bundle's own copies run",
           w.run(code, "installer_compiler") == (iscc, True)
           and w.run(code, "disc_image_tools", False) == [("mkisofs", mk, True)])
        shutil.rmtree(os.path.join(w.app_root, "helpers"))
        os.remove(os.path.join(w.meipass, "helpers", "cdrtools", "cygwin1.dll"))
        ok("a carried mkisofs without cygwin1.dll is not used (it would print nothing)",
           w.run(code, "carried_mkisofs") is None and w.run(code, "disc_image_tools", True) == [])
        touch(os.path.join(w.meipass, "helpers", "cdrtools", "cygwin1.dll"))

        # A source run (no _MEIPASS): the checkout's helpers\, but only a whole set (bugs review, 1.5.1).
        meipass, w.meipass = w.meipass, None
        src_iscc, src_mk = w.carry(w.app_root)
        ok("a source run: the checkout's helpers, when each set is whole",
           w.run(code, "installer_compiler") == (src_iscc, True)
           and w.run(code, "disc_image_tools", False) == [("mkisofs", src_mk, True)])
        os.remove(os.path.join(w.app_root, "helpers", "inno", "islzma.dll.issig"))
        ok("a source run: ISCC without one of its .issig files is not used", w.run(code, "installer_compiler") == (None, False))
        os.remove(os.path.join(w.app_root, "helpers", "inno", "Languages", "Czech.isl"))
        ok("helper_path names no file from a part of a set", w.run(code, "helper_path", "inno", "ISCC.exe") is None)
        os.remove(os.path.join(w.app_root, "helpers", "cdrtools", "cygwin1.dll"))
        ok("a source run: mkisofs without cygwin1.dll is not used", w.run(code, "carried_mkisofs") is None
           and w.run(code, "disc_image_tools", True) == [])
        shutil.rmtree(os.path.join(w.app_root, "helpers"))
        w.meipass = meipass
        ok("the log's words: carried", w.run(code, "tool_words", "iscc", iscc, True) == "the Inno Setup 6.5.4 that comes with Rialto"
           and w.run(code, "tool_words", "mkisofs", mk, True) == "the mkisofs that comes with Rialto")
        ok("the log's words: the PC's own", w.run(code, "tool_words", "oscdimg", r"C:\K\oscdimg.exe", False)
           == r"your oscdimg (C:\K\oscdimg.exe)")

        six = touch(os.path.join(w.pf86, "Inno Setup 6", "ISCC.exe"))
        ok("Inno Setup 6 installed: it comes first, exactly as 1.5.0", w.run(code, "installer_compiler") == (six, False))
        os.remove(six)
        seven = touch(os.path.join(w.pf, "Inno Setup 7", "ISCC.exe"))
        ok("only Inno Setup 7 installed: still before the carried 6.5.4", w.run(code, "installer_compiler") == (seven, False))
        os.remove(seven)
        w.on_path["ISCC.exe"] = r"D:\Tools\ISCC.exe"
        ok("ISCC on PATH: before the carried one", w.run(code, "installer_compiler") == (r"D:\Tools\ISCC.exe", False))
        del w.on_path["ISCC.exe"]

        oscdimg = touch(oscdimg_under(os.path.join(w.pf86, "Windows Kits", "10"), "amd64"))
        ok("the ADK's oscdimg: before the carried mkisofs",
           w.run(code, "disc_image_tools", False) == [("oscdimg", oscdimg, False), ("mkisofs", mk, True)])
        ok("a pressed disc never takes oscdimg: the carried mkisofs alone",
           w.run(code, "disc_image_tools", True) == [("mkisofs", mk, True)])
        w.on_path["mkisofs"] = r"D:\cdrtools\mkisofs.exe"
        ok("mkisofs on PATH, then oscdimg, then the carried mkisofs",
           w.run(code, "disc_image_tools", False) == [("mkisofs", r"D:\cdrtools\mkisofs.exe", False),
                                                      ("oscdimg", oscdimg, False), ("mkisofs", mk, True)])
        ok("a pressed disc: mkisofs on PATH, then the carried one",
           w.run(code, "disc_image_tools", True) == [("mkisofs", r"D:\cdrtools\mkisofs.exe", False), ("mkisofs", mk, True)])
        w.on_path["mkisofs"] = mk
        ok("the carried mkisofs put on PATH is listed once",
           w.run(code, "disc_image_tools", True) == [("mkisofs", mk, False)])
    finally:
        w.close()

    rialto = next(node for node in ast.parse(src).body if isinstance(node, ast.ClassDef)
                  and any(isinstance(item, ast.FunctionDef) and item.name == "compile_installer_with_iscc" for item in node.body))
    methods = {item.name: ast.get_source_segment(src, item) for item in rialto.body if isinstance(item, ast.FunctionDef)}
    iso_method = next(name for name, body in methods.items() if "Build the ISO with mkisofs or oscdimg" in body)
    for name in ("compile_installer_with_iscc", "_build_single_iso", "_write_one_image", iso_method):
        body = methods[name]
        ok("%s no longer asks PATH alone" % name,
           'which("ISCC.exe")' not in body and 'which("oscdimg")' not in body and 'which("mkisofs")' not in body)
    ok("the installer step uses installer_compiler (installed, then carried)",
       "installer_compiler()" in methods["compile_installer_with_iscc"])
    ok("the installer step says when it builds with Inno Setup 7 (1.5.1)",
       "_inno_setup_major(iscc) == 7" in methods["compile_installer_with_iscc"])
    ok("the installer step says when it builds with the carried Inno Setup",
       'tool_words("iscc", iscc, True)' in methods["compile_installer_with_iscc"])
    # Both ISO steps taking disc_image_tools' order and writing through _write_one_image are driven for real,
    # with stand-in tools, in test_image_tool_chain.py.
    ok("oscdimg's command is 1.5.0's",
       '[tool_path, "-m", "-u2" if needs_udf else "-j1", f"-l{disc_label}", temp_folder, iso_path]'
       in methods["_write_one_image"])
    ok("the preflight refuses a missing tool before anything is copied",
       "missing_tool_refusals(self.pressed_disc_on()" in methods["run_preflight_check"])
    ok("a Build Queue asks once for the run", methods["run_build_queue"].count("missing_tool_refusals(") == 1
       and methods["run_build_queue"].index("missing_tool_refusals(") < methods["run_build_queue"].index("for number, row in"))
    ok("at start, one log line when a tool is missing", "self.say_missing_tools()" in src
       and "missing_tool_refusals(False)" in methods["say_missing_tools"])

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        sys.exit(1)
    print("Inno Setup 6 and oscdimg are found where their installers put them.")


if __name__ == "__main__":
    main()
