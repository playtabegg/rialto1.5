"""Background video, logo transparency, and what the disc really weighs.

Three things a build used to get wrong, all of them the build being
quietly optimistic:

  1. The fill meter weighed the source game folder and stopped. It could
     read far under the finished disc, because bonus, the mod
     folder and the Mac/Linux builds ride on the disc root AND inside the
     installer, and the menu folder (a 38 MB menu.exe plus the background)
     was not counted at all. An author is told a DVD-sized disc fits on a CD.
  2. The menu set video_loaded = True the moment it called play(). QMediaPlayer
     loads asynchronously, so a video Windows cannot decode reported success
     and painted an opaque black rectangle over the whole menu, with the
     error handler wired to `lambda: None`.
  3. A logo with no alpha channel arrives as a solid rectangle, and the
     build gave no warning.

Source-extracted and exec'd on stub objects: no tkinter, no PyQt5.
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_source import extract_menu_source  # noqa: E402

failures = []


def check(label, got, want):
    good = got == want
    print(f"  [{'OK  ' if good else 'FAIL'}] {label}: {got!r}")
    if not good:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def ok(label, cond):
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def module_bits(src, names):
    tree = ast.parse(src)
    out, got = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
            got.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out.append(ast.get_source_segment(src, node))
                    got.add(t.id)
    missing = set(names) - got
    if missing:
        raise SystemExit(f"could not extract {sorted(missing)}")
    return "\n\n".join(out)


def methods(src, class_name, names):
    tree = ast.parse(src)
    out, got = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.name)
                elif isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    got.add(item.targets[0].id)
    missing = set(names) - got
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


def host(method_src, globals_=None, **attrs):
    ns = {"os": os, "sys": sys, "shutil": shutil, "subprocess": __import__("subprocess")}
    ns.update(globals_ or {})
    exec(f"class Host:\n{textwrap.indent(method_src, '    ')}", ns)
    obj = ns["Host"]()
    obj.update_status = lambda msg: None
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


class Flag:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


def fill(path, megabytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\0" * (megabytes * 1024 * 1024))


def main():
    src = open(RIALTO, encoding="utf-8").read()
    menu_src = extract_menu_source(RIALTO)
    base = tempfile.mkdtemp(prefix="rialto_assets_")
    MB = 1024 * 1024
    try:
        # --------------------------------------------------------------
        print("1. the meter weighs the disc, not the source folder")
        game = os.path.join(base, "game")
        fill(os.path.join(game, "game", "MyGame.exe"), 20)
        fill(os.path.join(game, "bonus", "art.png"), 10)
        fill(os.path.join(game, "mod-maker", "Maker.exe"), 15)
        prebuilt = os.path.join(base, "menu.exe")
        fill(prebuilt, 38)
        background = os.path.join(base, "background.mp4")
        fill(background, 19)

        meter_src = methods(src, "RialtoApp", ["menu_staging_bytes", "RUNTIME_ALLOWANCE"])
        h = host(meter_src, {"prebuilt_menu_exe": lambda: prebuilt},
                 bg_path_var=Flag(background))
        staged = h.menu_staging_bytes()
        # 38 MB menu.exe + 19 MB background + 26 MB runtimes + 4 MB art/dlls
        check("the menu folder is counted, in MB", round(staged / MB), 87)

        h2 = host(meter_src, {"prebuilt_menu_exe": lambda: None}, bg_path_var=Flag(""))
        ok("a missing prebuilt menu still reserves room", h2.menu_staging_bytes() >= 60 * MB)

        # The whole point: these land on the media twice.
        ok("the source tree alone is far lighter than the disc",
           (20 + 10 + 15) * MB < (20 + 10 + 15) * MB + staged)

        # --------------------------------------------------------------
        print("2. a logo with no transparency is called out")
        alpha_src = module_bits(src, ["image_has_transparency"])
        ns = {}
        exec(alpha_src, {"os": os, "sys": sys}, ns)
        has_alpha = ns["image_has_transparency"]
        try:
            from PIL import Image
        except ImportError:
            print("  [SKIP] Pillow not importable here")
        else:
            rgba = os.path.join(base, "clear.png")
            Image.new("RGBA", (8, 8), (255, 0, 0, 0)).save(rgba)
            check("a real transparent PNG passes", has_alpha(rgba), True)

            opaque = os.path.join(base, "opaque.png")
            Image.new("RGB", (8, 8), (12, 12, 12)).save(opaque)
            check("a flat RGB PNG is reported", has_alpha(opaque), False)

            # A common export: palette mode, no transparency.
            palette = os.path.join(base, "palette.png")
            Image.new("RGB", (8, 8), (60, 40, 20)).convert("P").save(palette)
            check("a palette PNG with no transparency is reported",
                  has_alpha(palette), False)

            solid_rgba = os.path.join(base, "solid_rgba.png")
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(solid_rgba)
            check("RGBA that is fully opaque still counts as no transparency",
                  has_alpha(solid_rgba), False)

        check("a missing file is unknown, not a failure",
              has_alpha(os.path.join(base, "nope.png")), None)

        # --------------------------------------------------------------
        print("3. video backgrounds are refused, not risked")
        ns2 = {}
        exec(module_bits(src, ["VIDEO_EXTENSIONS"]), {"os": os, "sys": sys}, ns2)
        exts = ns2["VIDEO_EXTENSIONS"]
        for e in (".mp4", ".avi", ".mov", ".webm", ".mkv", ".m4v", ".wmv"):
            ok("%s is refused" % e, e in exts)
        ok("gif is not refused", ".gif" not in exts)
        ok("jpg is not refused", ".jpg" not in exts)

        ok("staging refuses a video instead of copying it",
           "Video backgrounds are not supported" in src)
        ok("and names the GIF as the thing that works",
           "animated GIF" in src)
        ok("the file picker no longer offers video",
           '"*.mp4;*.avi;*.mov;*.webm"' not in src)
        ok("typing a video path is caught too",
           "if ext in VIDEO_EXTENSIONS:" in src)
        # The probe existed only to warn about a feature that is now gone.
        ok("the playability probe is gone with it",
           "video_background_playable" not in src and "--probe-video" not in src)

        print("4. the menu carries no video machinery at all")
        # Not merely unused - gone, so PyInstaller stops bundling QtMultimedia
        # and every disc's copy of menu.exe gets smaller.
        code_only = [l for l in menu_src.splitlines() if not l.strip().startswith("#")]
        code_only = chr(10).join(code_only)
        for banned in ("QMediaPlayer", "QMediaContent", "QVideoWidget",
                       "QtMultimedia", "self.media_player", "self.video_widget"):
            ok("no %s in the menu source" % banned, banned not in code_only)
        ok("the spec excludes QtMultimedia",
           "'PyQt5.QtMultimedia'" in open(os.path.join(REPO, "menu.spec"),
                                          encoding="utf-8").read())
        ok("the GIF path survives", "QtGui.QMovie(gif_path)" in menu_src)
        ok("and the still-image path survives", 'background.jpg' in menu_src)
        ok("both are found beside the exe, not in the unpack folder",
           'os.path.join(menu_dir(), "background.gif")' in menu_src
           and 'os.path.join(menu_dir(), "background.jpg")' in menu_src)

        print("5. the Unix build is packaged so nobody has to type anything")
        # A disc cannot carry an executable bit, but a tar archive carries the
        # mode of every file inside it. That is what turns "open a terminal and
        # chmod this" into "extract, then double-click".
        pack_src = methods(src, "RialtoApp",
                           ["package_unix_build", "_is_unix_executable",
                            "_unix_launch_target", "unix_launcher_script",
                            "write_unix_launcher",
                            "folder_is_already_packaged", "folder_bytes",
                            "UNIX_EXEC_SUFFIXES", "UNIX_ARCHIVE_SUFFIXES",
                            "UNIX_LAUNCH_PRIORITY"])
        ELF = b"\x7fELF"
        PAD = b"\x00" * 512
        rawdir = os.path.join(base, "LinuxRaw")
        os.makedirs(rawdir, exist_ok=True)
        # An ELF whose name gives nothing away - only the magic identifies it.
        open(os.path.join(rawdir, "runme"), "wb").write(ELF + PAD)
        open(os.path.join(rawdir, "Game.x86_64"), "wb").write(PAD)
        open(os.path.join(rawdir, "data.pck"), "wb").write(PAD)
        open(os.path.join(rawdir, "lib.so"), "wb").write(ELF + PAD)

        p = host(pack_src, {"sanitize_text": lambda v: str(v or "")},
                 entries={"Title": Flag("MyGame")})
        out = os.path.join(base, "LinuxOut")
        os.makedirs(out, exist_ok=True)
        target = p._unix_launch_target(rawdir)
        check("the launcher picked is the one a player would double-click",
              target, "Game.x86_64")
        name = p.package_unix_build(rawdir, out, "Linux", launcher=target)
        check("the archive is named after the game", name, "MyGame-Linux.tar.gz")

        import tarfile
        with tarfile.open(os.path.join(out, name)) as t:
            members = [m for m in t.getmembers() if m.isfile()]
        modes = {m.name.split("/")[-1]: m.mode for m in members}
        ok("an .x86_64 comes out runnable", bool(modes["Game.x86_64"] & 0o111))
        ok("an ELF with no telltale name does too", bool(modes["runme"] & 0o111))
        # .so is ELF too, but a shared library is loaded, never executed.
        ok("a shared library is runnable as well (it is ELF)", bool(modes["lib.so"] & 0o111))
        ok("game data stays plain", not modes["data.pck"] & 0o111)
        # The old instructions pointed at a start.sh nobody ever wrote.
        ok("the start.sh the notes promise is really in there",
           "MyGame-Linux/start.sh" in [m.name for m in members])
        ok("and it comes out runnable", bool(modes["start.sh"] & 0o111))
        with tarfile.open(os.path.join(out, name)) as t:
            script = t.extractfile("MyGame-Linux/start.sh").read().decode()
        ok("it runs the game rather than guessing", 'GAME="Game.x86_64"' in script)
        ok("from wherever the player put the folder", 'cd "$(dirname "$0")"' in script)
        ok("ownership is not the packer's own account",
           all(m.uid == 0 and m.uname == "" for m in members))

        packed = os.path.getsize(os.path.join(out, name))
        ok("packing shrinks it", packed < p.folder_bytes(rawdir))

        # An author who already shipped archives gets left alone.
        prepacked = os.path.join(base, "AlreadyPacked")
        os.makedirs(prepacked, exist_ok=True)
        open(os.path.join(prepacked, "Game.AppImage"), "wb").write(b"x")
        ok("a folder of archives is recognised", p.folder_is_already_packaged(prepacked))
        ok("a raw tree is not", not p.folder_is_already_packaged(rawdir))

        print("6. and the player is told what to do with it")
        unix_src = methods(src, "RialtoApp", ["write_unix_instructions"])
        u = host(unix_src, entries={"Title": Flag("MyGame")})
        u.write_unix_instructions(out, "Linux", archive=name, launcher=target)
        notes = open(os.path.join(out, "START HERE.txt"), encoding="utf-8").read()
        ok("the archive route names the archive", name in notes)
        ok("and promises no chmod", "nothing to chmod" in notes)
        ok("with a terminal fallback if the file manager balks",
           "bash start.sh" in notes)

        # And the other way round: no start.sh written, so none promised.
        u.write_unix_instructions(out, "Linux", archive=name)
        bare = open(os.path.join(out, "START HERE.txt"), encoding="utf-8").read()
        ok("a start.sh that was never written is never mentioned",
           "start.sh" not in bare)

        # No archive: the old chmod route, still correct.
        fallback = os.path.join(base, "LinuxFallback")
        os.makedirs(fallback, exist_ok=True)
        open(os.path.join(fallback, "MyGame.x86_64"), "wb").write(ELF)
        u.write_unix_instructions(fallback, "Linux", archive="")
        raw_notes = open(os.path.join(fallback, "START HERE.txt"), encoding="utf-8").read()
        ok("without an archive it explains chmod", "chmod +x" in raw_notes)
        ok("and says why the disc itself will not do", "read-only" in raw_notes)

        mac = os.path.join(base, "Mac")
        os.makedirs(mac, exist_ok=True)
        u.write_unix_instructions(mac, "Mac", archive="MyGame-Mac.tar.gz")
        mac_notes = open(os.path.join(mac, "START HERE.txt"), encoding="utf-8").read()
        ok("Mac gets its own notes", "Applications" in mac_notes)
        ok("including the Gatekeeper warning players will hit",
           "unidentified developer" in mac_notes)
        # The Mac notes used to be one line while Linux got a walkthrough;
        # both platforms get the same care.
        ok("Mac is walked through it, not just pointed at it",
           mac_notes.count("  3.") == 1 and "Copy" in mac_notes)
        ok("and is told why the disc alone will not do",
           "off this disc" in mac_notes)
        ok("no start.sh is invented for Mac", "start.sh" not in mac_notes)

        print("7. and the disc's own README tells each player what to press")
        readme_src = methods(src, "RialtoApp", ["stage_universal_builds"])
        steps = host(methods(src, "RialtoApp", ["unix_readme_steps"]))

        packed_mac = steps.unix_readme_steps("Mac", "MyGame-Mac.tar.gz")
        packed_lin = steps.unix_readme_steps("Linux", "MyGame-Linux.tar.gz")
        appimage = steps.unix_readme_steps("Linux", "MyGame.AppImage")
        loose_mac = steps.unix_readme_steps("Mac", "")
        loose_lin = steps.unix_readme_steps("Linux", "")

        # The whole point: the steps are here, not in a file this one points at.
        for name, block in (("Mac", packed_mac), ("Linux", packed_lin),
                            ("Linux .AppImage", appimage),
                            ("loose Mac", loose_mac), ("loose Linux", loose_lin)):
            ok("%s is told what to do, not told to go and read" % name,
               "START HERE" not in " ".join(block))
        ok("the Mac archive is named in the step", "MyGame-Mac.tar.gz" in packed_mac[0])
        ok("the Linux archive is named in the step", "MyGame-Linux.tar.gz" in packed_lin[0])
        ok("an .AppImage gets the step an .AppImage needs",
           "allow running as a program" in " ".join(appimage))
        ok("and a tarball does not", "allow running" not in " ".join(packed_lin))
        ok("a loose Linux build falls back to start.sh",
           "bash start.sh" in " ".join(loose_lin))

        for name, block in (("Mac", packed_mac), ("Linux", packed_lin),
                            ("Linux .AppImage", appimage),
                            ("loose Mac", loose_mac), ("loose Linux", loose_lin)):
            ok("%s stays inside a plain-text width" % name,
               max(len(line) for line in block) <= 72)
            ok("%s lines up under the WINDOWS column" % name,
               all(line.startswith(" " * 13) for line in block[1:]))

        check("Mac gets as many steps as Linux", len(packed_mac), len(packed_lin))
        ok("Windows is sent to setup.exe in the same breath",
           "WINDOWS: run 'setup.exe'" in readme_src)
        ok("and the Gatekeeper wall is warned about where a Mac player will hit it",
           "unidentified developer" in readme_src)

        # The signpost swaps out text that lives in another method. If someone
        # rewords the Windows steps, this is how we find out.
        def literal(fn_name, want):
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.FunctionDef) and node.name == fn_name:
                    for piece in ast.walk(node):
                        if want == "template" and isinstance(piece, ast.JoinedStr):
                            return "".join(v.value for v in piece.values
                                           if isinstance(v, ast.Constant))
                        if (want == "marker" and isinstance(piece, ast.Assign)
                                and getattr(piece.targets[0], "id", "") == "windows_only"):
                            return "\n".join(e.value for e in piece.value.args[0].elts)
            return ""

        ok("the steps still replace what generate_readme writes",
           literal("stage_universal_builds", "marker") in literal("generate_readme", "template"))

        ok("Read Me First no longer promises what is not there",
           "follow what's inside" not in src)

    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    if failures:
        print("FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("all disc-asset checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
