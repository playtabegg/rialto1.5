"""The disc image tools, driven for real with stand-in tools (1.5.1, bugs review findings 1 to 3).

create_iso, _build_single_iso, create_spanned_isos, _write_one_image,
write_pressing_files, queue_row_result and build_all are lifted out of
Rialto.pyw and run on temp folders. Only the tool itself is a stand-in: each
named tool succeeds, fails, cannot start, stops at 30 minutes, or sees Rialto
closed while it writes, leaving a half-written image behind as a real one would.

  1. One disc: the first tool fails and the next one runs; every tool fails
     and an unpressed disc gets the ZIP while a pressed one stops; a tool that
     cannot start hands over too; a timeout removes the half-written image and
     stops the build with no next tool; a close removes it and stops.
  2. A set of discs: the same hand-over for any failure, oscdimg's copy is the
     counting copy, a timeout stops the set, a close removes the half-written
     disc and stops.
  3. The whole build (build_all with every other step a stand-in): a pressed
     disc whose tool times out gets no Chksum.md5, no master sheet and no
     "Build complete"; a good one gets them for its own image. The files to
     place on the PC, staged beside the build folder, are gone when it ends,
     made or not. With no internet the Visual C++ download, through the real
     rialto.update.fetch, logs one plain line and the build finishes.
  4. write_pressing_files and the Build Queue's summary list only the images the
     build made, never a stray or half-written *.iso in the folder.
"""
import ast
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
failures = []

METHODS = ("create_iso", "_build_single_iso", "create_spanned_isos", "_write_one_image", "_remove_partial_iso",
           "_iso_fallback_unless_pressed", "write_pressing_files", "queue_row_result", "build_all",
           "_collect_disc_fileset", "_fileset_size", "_fileset_disc_bytes", "_fileset_needs_udf", "image_growth",
           "download_essential_runtimes")
MODULE = ("__version__", "_CONTROL_CHARS", "_ISS_META", "_ISS_PATH_META", "_WINDOWS_RESERVED", "MKISOFS_IMAGE_PART", "MKISOFS_PATH_LIST", "mkisofs_graft", "mkisofs_label",
          "mkisofs_path_list", "mkisofs_command", "mkisofs_reads_utf8", "tool_words", "iss_value", "sanitize_text",
          "PLACED_FILES_DIR", "PRESSED_DISC_TYPES", "SECTOR_BYTES", "DVD9_LAYER0_SECTORS", "DVD9_LAYER_LIMIT",
          "DVD5_SECTORS", "dvd9_layers", "iso_facts", "file_md5", "checksum_text", "master_sheet_text",
          "oversized_disc_warnings", "placed_files_root")
MKISOFS, OSCDIMG, CARRIED = r"C:\Path\mkisofs.exe", r"C:\ADK\oscdimg.exe", r"C:\MEI\helpers\cdrtools\mkisofs.exe"


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


def load():
    src = open(RIALTO, encoding="utf-8").read()
    tree = ast.parse(src)
    ns = {"os": os, "re": re, "shutil": shutil, "subprocess": subprocess, "glob": glob, "time": time,
          "traceback": traceback, "zipfile": zipfile}
    for node in tree.body:
        name = getattr(node, "name", None) or (getattr(node.targets[0], "id", "") if isinstance(node, ast.Assign) else "")
        if name in MODULE:
            exec(ast.get_source_segment(src, node), ns)
    missing = [n for n in MODULE if n not in ns]
    if missing:
        raise SystemExit("could not extract " + ", ".join(missing))
    app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RialtoApp")
    found = {i.name: textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body
             if isinstance(i, ast.FunctionDef) and i.name in METHODS}
    consts = [textwrap.dedent(ast.get_source_segment(src, i)) for i in app.body if isinstance(i, ast.Assign)
              and getattr(i.targets[0], "id", "") in ("SPAN_MARGIN",)]
    missing = [n for n in METHODS if n not in found]
    if missing:
        raise SystemExit("could not extract " + ", ".join(missing))
    exec("class Real:\n" + textwrap.indent("\n".join(consts) + "\n\n" + "\n\n".join(found.values()), "    "), ns)
    return ns


NS = load()
NS["safe"] = lambda p: os.path.normpath(os.path.abspath(p))
TOOLS = []                      # what disc_image_tools hands back
NS["disc_image_tools"] = lambda pressed: [t for t in TOOLS if not (pressed and t[0] == "oscdimg")]


def fake_image(path, label="GAME", sectors=24):
    """Shaped like a disc image: a primary volume descriptor with the label at sector 16."""
    data = bytearray(sectors * 2048)
    data[16 * 2048] = 1
    data[16 * 2048 + 1:16 * 2048 + 6] = b"CD001"
    data[16 * 2048 + 40:16 * 2048 + 72] = label.encode("ascii", "replace")[:32].ljust(32)
    with open(path, "wb") as fh:
        fh.write(bytes(data))


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Host(NS["Real"]):
    """The window's side, as stand-ins; the tools behave as `behave` says, per tool path, per call."""

    def __init__(self, behave, pressed=False, capacity=None):
        self.behave = {k: list(v) if isinstance(v, (list, tuple)) else [v] for k, v in behave.items()}
        self.pressed, self.capacity = pressed, capacity
        self.log, self.calls, self.copies, self.zip_made = [], [], [], False
        self.target_media_var = Var("DVD 4.7 GB")
        self.mod_launcher_var = Var(False)
        self._abandon_build = False

    def update_status(self, message):
        self.log.append(message)

    def pressed_disc_on(self):
        return self.pressed

    def get_target_media_capacity(self):
        return self.capacity

    def report_disc_media_fit(self, size):
        pass

    def refresh_windows_icon_cache(self):
        pass

    def build_ticker(self, step, total=0):
        return lambda more=0: None

    def counting_copy(self, step, total):
        self.copies.append(step)

        def copy(src, dst, *, follow_symlinks=True):
            return shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
        return copy

    def create_python_iso_fallback(self, output_path, iso_path, iso_files, meta):
        self.zip_made = True

    def run_watched_call(self, step, work, watch=None):
        return work(self.update_status)

    def run_tool_watched(self, command, cwd, timeout, step, on_line=None, watch=None):
        tool = command[0]
        steps = self.behave.get(tool, ["ok"])
        what = steps.pop(0) if len(steps) > 1 else steps[0]
        self.calls.append((tool, what, list(command)))
        if what == "cannot start":
            raise OSError(2, "The system cannot find the file specified")  # as Popen raises it
        target = os.path.join(cwd, command[command.index("-o") + 1]) if "-o" in command else command[-1]
        if what == "ok":
            fake_image(target)
            if watch:
                self.watched = watch()
            return subprocess.CompletedProcess(command, 0, "", "")
        with open(target, "wb") as fh:  # half-written, as a real tool leaves it
            fh.write(b"\0" * 4096)
        if what == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        if what == "close":
            self._abandon_build = True
            raise RuntimeError("Rialto was closed during the build")
        return subprocess.CompletedProcess(command, 2, "", "mkisofs: something went wrong")


def stage(folder, bins=()):
    """A build folder just before the disc image: setup, autorun, README, the menu, and setup-N.bin parts."""
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(os.path.join(folder, "menu"))
    for name, size in [("setup.exe", 2048), ("autorun.inf", 20), ("README.txt", 20), ("menu/menu.exe", 4096)] + \
            [(b, 3 * 1024 * 1024) for b in bins]:
        with open(os.path.join(folder, *name.split("/")), "wb") as fh:
            fh.write(b"x" * size)
    return folder


def isos(folder):
    return sorted(f for f in os.listdir(folder) if f.lower().endswith(".iso"))


def leftovers(folder):
    return [f for f in os.listdir(folder) if f in (NS["MKISOFS_IMAGE_PART"], NS["MKISOFS_PATH_LIST"])
            or f.startswith("temp_")]


def main():
    work = tempfile.mkdtemp(prefix="rialto_toolchain_")
    meta = {"GameName": "Sky Quest", "Title": "Sky Quest", "Developer": "Your Studio"}
    try:
        out = os.path.join(work, "Sky Quest")
        print("1. one disc")
        TOOLS[:] = [("mkisofs", MKISOFS, False), ("oscdimg", OSCDIMG, False), ("mkisofs", CARRIED, True)]
        h = Host({MKISOFS: "fail"})
        h.create_iso(stage(out), meta)
        ok("the first tool fails, the next one runs and makes the image",
           [c[:2] for c in h.calls] == [(MKISOFS, "fail"), (OSCDIMG, "ok")] and isos(out) == ["Sky Quest.iso"], h.calls)
        ok("its half-written image was removed before the next tool ran",
           any("Removed the unfinished Sky Quest.iso" in l for l in h.log), h.log)
        ok("oscdimg's copy is the counting one", h.copies == ["Preparing the disc image"], h.copies)
        ok("images_made names that image alone", h.images_made == [os.path.join(out, "Sky Quest.iso")], h.images_made)
        ok("no ZIP, no temp folder, no path list, no unfinished image left", not h.zip_made and leftovers(out) == [],
           leftovers(out))

        h = Host({MKISOFS: "ok"})
        h.create_iso(stage(out), meta)
        made_cmd = h.calls[0][2]
        ok("mkisofs writes to the plain name, renamed when finished",
           made_cmd[made_cmd.index("-o") + 1] == NS["MKISOFS_IMAGE_PART"] and isos(out) == ["Sky Quest.iso"]
           and leftovers(out) == [], (made_cmd, os.listdir(out)))
        ok("the live line watched the image as mkisofs wrote it", getattr(h, "watched", None) is not None)

        h = Host({MKISOFS: "cannot start", OSCDIMG: "fail"})
        h.create_iso(stage(out), meta)
        ok("a tool that cannot start hands over, as does a failing one, to the carried mkisofs",
           [c[:2] for c in h.calls] == [(MKISOFS, "cannot start"), (OSCDIMG, "fail"), (CARRIED, "ok")]
           and isos(out) == ["Sky Quest.iso"], h.calls)

        h = Host({MKISOFS: "fail", OSCDIMG: "fail", CARRIED: "fail"})
        h.create_iso(stage(out), meta)
        ok("every tool fails, unpressed: each one tried, then the ZIP, and no image",
           len(h.calls) == 3 and h.zip_made and isos(out) == [] and h.images_made == [], h.calls)

        h = Host({MKISOFS: "fail", CARRIED: "fail"}, pressed=True)
        try:
            h.create_iso(stage(out), meta)
            raised = None
        except RuntimeError as e:
            raised = str(e)
        ok("every tool fails, pressed: never oscdimg, never the ZIP, the build stops with a reason",
           [c[0] for c in h.calls] == [MKISOFS, CARRIED] and not h.zip_made and raised and "mkisofs" in raised
           and isos(out) == [], (h.calls, raised))

        for pressed in (False, True):
            h = Host({MKISOFS: "timeout"}, pressed=pressed)
            try:
                h.create_iso(stage(out), meta)
                raised = None
            except RuntimeError as e:
                raised = str(e)
            ok("a timeout (%s): no next tool, no ZIP, the half-written image removed, the build stops"
               % ("pressed" if pressed else "unpressed"),
               len(h.calls) == 1 and not h.zip_made and raised and "30 minutes" in raised and isos(out) == []
               and leftovers(out) == [] and h.images_made == [], (h.calls, raised, os.listdir(out)))

        h = Host({MKISOFS: "close"})
        try:
            h.create_iso(stage(out), meta)
            raised = None
        except RuntimeError as e:
            raised = str(e)
        ok("closed mid-image: the half-written image removed, no next tool, no ZIP, stopped",
           len(h.calls) == 1 and raised == "Rialto was closed during the build" and not h.zip_made
           and isos(out) == [] and leftovers(out) == [], (h.calls, raised, os.listdir(out)))
        print()

        print("2. a set of discs")
        bins = ["setup-1.bin", "setup-2.bin", "setup-3.bin"]
        cap = 4 * 1024 * 1024 + NS["Real"].SPAN_MARGIN  # one part a disc

        def run_set(behave, pressed=False):
            h = Host(behave, pressed=pressed, capacity=cap)
            try:
                h.create_iso(stage(out, bins), meta)
                return h, None
            except RuntimeError as e:
                return h, str(e)

        TOOLS[:] = [("mkisofs", MKISOFS, False), ("oscdimg", OSCDIMG, False), ("mkisofs", CARRIED, True)]
        h, raised = run_set({MKISOFS: ["cannot start", "fail", "ok"]})
        ok("three discs; any failure hands over to the next tool, as for one disc",
           raised is None and isos(out) == ["Sky Quest Disc 1.iso", "Sky Quest Disc 2.iso", "Sky Quest Disc 3.iso"]
           and [c[:2] for c in h.calls] == [(MKISOFS, "cannot start"), (OSCDIMG, "ok"), (MKISOFS, "fail"),
                                            (OSCDIMG, "ok"), (MKISOFS, "ok")], (raised, h.calls, isos(out)))
        ok("oscdimg's copy of each disc is the counting one, so the window answers",
           h.copies == ["Preparing Sky Quest Disc 1.iso", "Preparing Sky Quest Disc 2.iso"], h.copies)
        ok("images_made names the three discs", [os.path.basename(p) for p in h.images_made]
           == ["Sky Quest Disc 1.iso", "Sky Quest Disc 2.iso", "Sky Quest Disc 3.iso"], h.images_made)
        ok("nothing half-written left", leftovers(out) == [], os.listdir(out))

        h, raised = run_set({MKISOFS: "fail", OSCDIMG: "fail", CARRIED: "fail"}, pressed=True)
        ok("pressed, every tool fails: oscdimg never tried, no disc made, the build stops",
           OSCDIMG not in [c[0] for c in h.calls] and raised and "whole set" in raised and isos(out) == [], (raised, h.calls))

        h, raised = run_set({MKISOFS: ["ok", "timeout"]})
        ok("a timeout on Disc 2: no next tool, its half-written image removed, the set stops",
           raised and "30 minutes" in raised and [c[:2] for c in h.calls] == [(MKISOFS, "ok"), (MKISOFS, "timeout")]
           and isos(out) == ["Sky Quest Disc 1.iso"] and leftovers(out) == [], (raised, h.calls, os.listdir(out)))

        h, raised = run_set({MKISOFS: ["ok", "close"]})
        ok("closed while Disc 2 is written: its half-written image removed, no next tool, stopped",
           raised == "Rialto was closed during the build" and len(h.calls) == 2
           and isos(out) == ["Sky Quest Disc 1.iso"] and leftovers(out) == [], (raised, h.calls, os.listdir(out)))
        TOOLS[:] = [("oscdimg", OSCDIMG, False)]
        h, raised = run_set({OSCDIMG: ["ok", "close"]})
        ok("the same with oscdimg, which writes the real name directly",
           raised == "Rialto was closed during the build" and isos(out) == ["Sky Quest Disc 1.iso"]
           and leftovers(out) == [], (raised, os.listdir(out)))
        print()

        print("3. the whole build, on a PC with no internet")
        TOOLS[:] = [("mkisofs", MKISOFS, False), ("mkisofs", CARRIED, True)]
        # The Visual C++ redistributables are fetched through the real rialto.update.fetch, with every address
        # failing as it does with no internet (bugs E8): the build must log one plain line and go on.
        sys.path.insert(0, REPO)
        import rialto.update.fetch  # noqa: F401
        sys.path.remove(REPO)
        import urllib.error
        import urllib.request

        def offline(request, timeout=None):
            raise urllib.error.URLError(OSError(11001, "getaddrinfo failed"))
        real_urlopen = urllib.request.urlopen
        urllib.request.urlopen = offline
        output_dir = os.path.join(work, "output")
        game = os.path.join(work, "input", "Sky Quest")
        os.makedirs(game, exist_ok=True)
        NS["OUTPUT_DIR"] = output_dir

        class Build(Host):
            """Every step of build_all that is not the disc image is a stand-in that does nothing."""

            def __init__(self, behave, pressed):
                super().__init__(behave, pressed=pressed)
                self.current_game_path = game
                self.entries = {"Title": Var("Sky Quest"), "Developer": Var("Your Studio")}
                self._batch = None
                self.popups = []

            def __getattr__(self, name):
                if name.endswith("_var"):
                    return Var("")
                return lambda *a, **k: None

            def stage_universal_builds(self, output_path):  # the last step before the image
                stage(output_path)

            def copy_runtime_dependencies(self, output_path):  # with no local copy, Rialto fetches them
                self.download_essential_runtimes(output_path)

            def stage_placed_files(self, output_path):  # as the real step stages them, for ISCC
                staging = NS["placed_files_root"](output_path)
                os.makedirs(os.path.join(staging, "1"), exist_ok=True)
                with open(os.path.join(staging, "placed.json"), "w", encoding="utf-8") as fh:
                    fh.write("[]")

            def show_centered_popup(self, title, message):
                self.popups.append(title)

        b = Build({MKISOFS: "timeout"}, pressed=True)
        finished = b.build_all()
        built = os.path.join(output_dir, "Sky Quest")
        ok("pressed, the tool times out: the build fails with the reason",
           finished is False and any(l.startswith("❌ Build failed: the disc image was not finished after 30 minutes")
                                     for l in b.log), b.log[-4:])
        ok("no Chksum.md5, no master sheet, no image, no Build complete, no Done",
           not os.path.exists(os.path.join(built, "Chksum.md5")) and not glob.glob(os.path.join(built, "* master sheet.txt"))
           and isos(built) == [] and "✅ Build complete!" not in b.log and "Done" not in b.popups, os.listdir(built))
        ok("and no next tool after the timeout", [c[:2] for c in b.calls] == [(MKISOFS, "timeout")], b.calls)
        ok("the files to place, staged beside the build folder for ISCC, are gone after a failed build",
           not os.path.exists(os.path.join(output_dir, ".rialto-placed")), os.listdir(output_dir))

        b = Build({MKISOFS: "timeout"}, pressed=False)
        ok("unpressed, the tool times out: the build stops too, not called made",
           b.build_all() is False and "✅ Build complete!" not in b.log and isos(built) == [], b.log[-3:])

        b = Build({MKISOFS: "fail"}, pressed=True)
        finished = b.build_all()
        sums = open(os.path.join(built, "Chksum.md5"), encoding="utf-8").read() if os.path.exists(
            os.path.join(built, "Chksum.md5")) else ""
        ok("pressed, the first mkisofs fails and the carried one makes it: the sheet and checksum, then Build complete",
           finished is True and sums.strip().endswith("*Sky Quest.iso") and len(sums.strip().splitlines()) == 1
           and glob.glob(os.path.join(built, "* master sheet.txt")) and "✅ Build complete!" in b.log, (sums, b.log[-4:]))
        ok("and after a finished one", not os.path.exists(os.path.join(output_dir, ".rialto-placed")),
           os.listdir(output_dir))
        said = [l for l in b.log if "Visual C++" in l or "Download failed" in l or "Download error" in l]
        ok("with no internet: one plain line about the redistributables, and the build finishes",
           finished is True and len(said) == 1 and "official Microsoft download" in said[0]
           and "could not be downloaded" in said[0], said)
        urllib.request.urlopen = real_urlopen
        print()

        print("4. only the images this build made")
        folder = stage(os.path.join(work, "only"))
        fake_image(os.path.join(folder, "Sky Quest.iso"), "SKY")
        fake_image(os.path.join(folder, "Old Game Disc 7.iso"), "OLD")    # left over, not this build's
        with open(os.path.join(folder, "Half Disc 2.iso"), "wb") as fh:   # half-written
            fh.write(b"\0" * 4096)
        h = Host({}, pressed=True)
        h.write_pressing_files(folder, meta, [os.path.join(folder, "Sky Quest.iso")])
        sums = open(os.path.join(folder, "Chksum.md5"), encoding="utf-8").read()
        sheet = open(glob.glob(os.path.join(folder, "* master sheet.txt"))[0], encoding="utf-8").read()
        ok("Chksum.md5 lists the made image alone", sums.strip().splitlines()[-1].endswith("*Sky Quest.iso")
           and len(sums.strip().splitlines()) == 1, sums)
        ok("so does the master sheet", "Sky Quest.iso" in sheet and "Old Game" not in sheet and "Half Disc" not in sheet)
        try:
            h.write_pressing_files(folder, meta, [])
            raised = False
        except RuntimeError:
            raised = True
        ok("nothing made: no sheet at all, whatever *.iso lies there", raised)
        NS["OUTPUT_DIR"] = work
        h.images_made = [os.path.join(folder, "Sky Quest.iso")]
        ok("the Build Queue's summary names the made image alone",
           h.queue_row_result("only") == "Sky Quest.iso (0.00 GB)", h.queue_row_result("only"))
        h.images_made = []
        ok("and says none was made when none was", h.queue_row_result("only") == "no disc image was made")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nThe disc image tools hand over, stop and clean up as they should, and a plant gets only made images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
