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
import shutil
import sys
import tempfile
import types
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
HELPERS = ("_registry_string", "_inno_setup_folders", "_inno_setup_major", "find_inno_compiler",
           "inno_setup_7_only", "find_iso_tools")
WOW_UNINSTALL = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Inno Setup 6_is1"
USER_UNINSTALL = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Inno Setup 6_is1"
KITS = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows Kits\\Installed Roots"

failures = []


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
    return "\n\n".join(wanted[name] for name in HELPERS)


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

    def run(self, code, call):
        env = {"ProgramFiles(x86)": self.pf86, "ProgramFiles": self.pf, "LOCALAPPDATA": self.local,
               "PROCESSOR_ARCHITECTURE": self.arch}
        fake_shutil = types.SimpleNamespace(which=lambda name: self.on_path.get(name))
        ns = {"os": os, "shutil": fake_shutil}
        exec(code, ns)
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {"winreg": FakeWinreg(self.registry)}):
            os.environ.pop("PROCESSOR_ARCHITEW6432", None)
            return ns[call]()

    def close(self):
        shutil.rmtree(self.base, ignore_errors=True)


def oscdimg_under(root, arch):
    return os.path.join(root, "Assessment and Deployment Kit", "Deployment Tools", arch, "Oscdimg", "oscdimg.exe")


def main():
    with open(RIALTO, encoding="utf-8") as fh:
        src = fh.read()
    code = helpers(src)

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
        ok("only Inno Setup 7: no ISCC for Rialto", w.run(code, "find_inno_compiler") is None)
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
        ok("Inno Setup 7 put on PATH by hand is refused", w.run(code, "find_inno_compiler") is None)
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

    rialto = next(node for node in ast.parse(src).body if isinstance(node, ast.ClassDef)
                  and any(isinstance(item, ast.FunctionDef) and item.name == "compile_installer_with_iscc" for item in node.body))
    methods = {item.name: ast.get_source_segment(src, item) for item in rialto.body if isinstance(item, ast.FunctionDef)}
    iso_method = next(name for name, body in methods.items() if "Build the ISO with mkisofs or oscdimg" in body)
    for name in ("compile_installer_with_iscc", "_build_single_iso", iso_method):
        body = methods[name]
        ok("%s no longer asks PATH alone" % name,
           'which("ISCC.exe")' not in body and 'which("oscdimg")' not in body and 'which("mkisofs")' not in body)
    ok("the installer step uses find_inno_compiler", "find_inno_compiler()" in methods["compile_installer_with_iscc"])
    ok("the installer step names Inno Setup 7", "inno_setup_7_only()" in methods["compile_installer_with_iscc"])
    ok("both ISO steps use find_iso_tools",
       "find_iso_tools()" in methods["_build_single_iso"] and "find_iso_tools()" in methods[iso_method])

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        sys.exit(1)
    print("Inno Setup 6 and oscdimg are found where their installers put them.")


if __name__ == "__main__":
    main()
