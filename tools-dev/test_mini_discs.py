"""The 8 cm minis beside Target Media (1.5.1, minis).

Two new Target Media choices, promised to a developer planning a demo disc: a
Mini CD 210 MB (8 cm) and a Mini DVD 1.4 GB (8 cm). This checks, against the
real code pulled out of Rialto.pyw:

  1. the capacities, from the 8 cm discs' own sector counts;
  2. the reserve and the slice size, against what real Rialto discs carried
     beside their installer slices;
  3. a set of several mini CDs, packed by the real create_spanned_isos, and
     the disc meter's count agreeing with it disc for disc;
  4. the disc meter, the over-limit line and the Fits-on and Presses-as lines;
  5. a pressed mini: the refusal, the master sheet's disc type, no layer break;
  6. a 1.5.0 profile: every existing media builds the installer script it
     built before, and its meter reads as it did;
  7. the dropdown, its tooltips and the Help Guide.

No disc, Inno Setup or Tk window is needed: installer slices are one-byte files
whose sizes an os shim reports, as in test_disc_overflow_warning.py.
"""
import ast
import os
import re
import shutil
import sys
import tempfile
import textwrap
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_disc_overflow_warning as dow  # noqa: E402
import test_installer_script as tis  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MINI_CD, MINI_DVD = "Mini CD 210 MB (8 cm)", "Mini DVD 1.4 GB (8 cm)"
MB = 1_000_000

# What 1.5.0 offered, in its order, and what each disc's installer slice was
# (the media less 96 MiB, inside Inno's 2,100,000,000-byte ceiling). Pinned
# here so a change to any of them fails this run.
MEDIA_150 = [
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
SLICE_150 = {"CD 700 MB": 636_616_704, "DVD 4.7 GB": 2_100_000_000}

# The heaviest Disc 1 measured beside its slices, from a real Rialto ISO
# (10 September 2026): 78,834,457 bytes in all.
MEASURED_BASE = {
    "setup.exe": 2_615_232,
    "autorun.inf": 133,
    "README.txt": 281,
    "game_icon.ico": 370_070,
    "disc_icon.ico": 370_070,
    "menu.bat": 2_238,
    "start_menu.bat": 837,
    "menu/menu.exe": 37_410_096,
    "menu/background.gif": 31_552_930,
    "menu/steam/hero.png": 2_075_331,
    "menu/steam/capsule.png": 905_070,
    "menu/steam/wide.png": 800_910,
    "menu/steam/logo.png": 199_262,
    "menu/company_logo.png": 433_768,
    "menu/game_logo.png": 190_063,
    "menu/runtime_dlls.bin": 1_908_166,  # msvcp140, concrt140, vccorlib140, the rest of the menu folder
}

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Canvas:
    """Just enough of a tk.Canvas for draw_disc_meter."""
    def __getattr__(self, name):
        return lambda *a, **k: 200 if name == "winfo_width" else None


def module_names(src, tree, names):
    ns = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in names:
            exec(ast.get_source_segment(src, node), ns)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            exec(ast.get_source_segment(src, node), ns)
    missing = set(names) - set(ns)
    if missing:
        raise SystemExit("could not read %s from Rialto.pyw" % sorted(missing))
    return ns


def media_host(src, ns, method_names, media, **attrs):
    """A stand-in RialtoApp carrying the real media constants and methods."""
    body = [textwrap.dedent(dow.method_source(src, "RialtoApp", n)) for n in method_names]
    ns = dict(ns)
    exec("class Host:\n" + textwrap.indent("\n\n".join(body), "    "), ns)
    host = ns["Host"]()
    for const in ("MEDIA_TYPES", "MEDIA_RESERVE", "SPAN_MARGIN", "RUNTIME_ALLOWANCE"):
        setattr(host, const, dow.extract_class_constant(src, "RialtoApp", const))
    host.target_media_var = Var(media)
    host.log = []
    host.update_status = host.log.append
    for k, v in attrs.items():
        setattr(host, k, v)
    return host


def capacity(media_types, name):
    return dict(media_types)[name]


def spanned_set(base_dir, src, media_types, media, payload):
    """A finished output folder: the measured Disc 1 base, and the payload cut
    into slices the size the real get_disk_slice_size gives this media."""
    host = media_host(src, {}, ["get_target_media_capacity", "get_disk_slice_size"], media)
    slice_size = host.get_disk_slice_size()
    out = os.path.join(base_dir, "output", "Demo")
    os.makedirs(out, exist_ok=True)
    sizes = {}

    def touch(rel, size):
        path = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        sizes[os.path.normcase(os.path.abspath(path))] = size

    for rel, size in MEASURED_BASE.items():
        touch(rel, size)
    parts = [slice_size] * (payload // slice_size) + ([payload % slice_size] if payload % slice_size else [])
    for number, size in enumerate(parts, start=1):
        touch("setup-%d.bin" % number, size)
    span = dow.build_host(src, sizes,
                          SPAN_MARGIN=dow.extract_class_constant(src, "RialtoApp", "SPAN_MARGIN"),
                          mod_launcher_var=dow.Flag(False), target_media_var=dow.Flag(media))
    items = span._collect_disc_fileset(out)
    base_items = [i for i in items if not (i.startswith("setup-") and i.endswith(".bin"))]
    span.create_spanned_isos(out, {"GameName": "Demo", "Title": "Demo"}, "DEMO", capacity(media_types, media))
    # Disc 1's base as the packer weighs it, with the MULTI-DISC README it wrote.
    base = span._fileset_disc_bytes(out, base_items) + os.path.getsize(os.path.join(out, "MULTI-DISC README.txt"))
    disc_bytes = []
    for _name, disc_items, _udf in span.built:
        disc_bytes.append(span._fileset_size(out, disc_items))
    return span, base, slice_size, parts, disc_bytes


def meter_against_build(src, media_types, reserve, margin, count, work):
    """The meter's own Disc 1 (disc_weights, the path refresh_disc_meter runs) against the build's packing,
    for a game with a 100 MB Linux build on a Mini CD (bugs review, 1.5.1). The build puts the Linux build
    on Disc 1's root beside the menu, so the meter must weigh it there, not count it into the slices."""
    cd = capacity(media_types, MINI_CD)
    sizes = {}

    def touch(path, size):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        sizes[os.path.normcase(os.path.abspath(path))] = size
        return path

    game = os.path.join(work, "Demo")
    touch(os.path.join(game, "Demo.exe"), 85 * MB)
    linux = os.path.join(work, "Demo Linux")
    touch(os.path.join(linux, "Demo.x86_64"), 100 * MB)
    art = os.path.join(work, "art")
    background = touch(os.path.join(art, "background.gif"), 5 * MB)
    game_icon = touch(os.path.join(art, "game_icon.ico"), 370_070)
    disc_icon = touch(os.path.join(art, "disc_icon.ico"), 370_070)
    menu_exe = touch(os.path.join(work, "dist", "menu.exe"), 37_410_096)
    shim = dow.ShimOs(sizes)
    host = media_host(src, {"os": shim, "prebuilt_menu_exe": lambda: menu_exe},
                      ["menu_staging_bytes", "disc_weights"], MINI_CD, bg_path_var=Var(background))
    for const in ("RUNTIME_STORED", "DISC1_FILES_ALLOWANCE"):
        setattr(host, const, dow.extract_class_constant(src, "RialtoApp", const))
    menu_extra = host.menu_staging_bytes()
    extras = [background, "", "", game_icon, disc_icon, "", linux, ""]
    total, disc1 = host.disc_weights(game, extras, ["", linux], menu_extra, [game_icon, disc_icon])

    # The build folder the same game makes, packed by the real create_spanned_isos.
    out = os.path.join(work, "output", "Demo")
    for rel, size in (("setup.exe", 2_615_232), ("autorun.inf", 133), ("README.txt", 281), ("menu.bat", 2_238),
                      ("start_menu.bat", 837), ("game_icon.ico", 370_070), ("disc_icon.ico", 370_070),
                      ("menu/menu.exe", 37_410_096), ("menu/background.gif", 5 * MB),
                      ("menu/steam_art_and_dlls.bin", 4 * 1024 * 1024), ("Linux/Demo.x86_64", 100 * MB)):
        touch(os.path.join(out, *rel.split("/")), size)
    payload = total - disc1  # what the meter puts in the slices; the build is given the same
    slicer = media_host(src, {}, ["get_target_media_capacity", "get_disk_slice_size"], MINI_CD)
    slice_size = slicer.get_disk_slice_size()
    parts = [slice_size] * (payload // slice_size) + ([payload % slice_size] if payload % slice_size else [])
    for number, size in enumerate(parts, start=1):
        touch(os.path.join(out, "setup-%d.bin" % number), size)
    span = dow.build_host(src, sizes, SPAN_MARGIN=margin, mod_launcher_var=dow.Flag(False),
                          target_media_var=dow.Flag(MINI_CD))
    items = span._collect_disc_fileset(out)
    base_items = [i for i in items if not (i.startswith("setup-") and i.endswith(".bin"))]
    span.create_spanned_isos(out, {"GameName": "Demo", "Title": "Demo"}, "DEMO", cd)
    base = span._fileset_disc_bytes(out, base_items) + os.path.getsize(os.path.join(out, "MULTI-DISC README.txt"))
    says("a 100 MB Linux build on a Mini CD: the build puts it on Disc 1, beside the menu",
         "Linux" in span.built[0][1] and "menu" in span.built[0][1], span.built[0][1])
    says("the meter's Disc 1 (%.1f MB) is the build's (%.1f MB), within 2 MB and never under it"
         % (disc1 / MB, base / MB), base <= disc1 <= base + 2 * MB, (disc1, base))
    says("the meter's count is the build's, %d mini CDs" % len(span.built),
         count(min(disc1, total), total - min(disc1, total), cd, reserve, margin) == len(span.built),
         (count(min(disc1, total), total - min(disc1, total), cd, reserve, margin), len(span.built)))
    old_disc1 = menu_extra - host.RUNTIME_ALLOWANCE
    says("weighed as before (the menu alone on Disc 1), the meter would have said a disc fewer",
         count(old_disc1, total - old_disc1, cd, reserve, margin) == len(span.built) - 1,
         count(old_disc1, total - old_disc1, cd, reserve, margin))

    # Fastest install stores everything as it is: the menu is on the disc and inside the installer, and the
    # runtimes weigh what they weigh. Every other compression reads as it did.
    stored, _d1 = host.disc_weights(game, extras, ["", linux], menu_extra, [game_icon, disc_icon], True)
    says("Fastest install: the menu counted again, the runtimes at their weight, Disc 1's own files",
         stored - total == (menu_extra - host.RUNTIME_ALLOWANCE) + host.RUNTIME_STORED - host.RUNTIME_ALLOWANCE
         + host.DISC1_FILES_ALLOWANCE + 2 * ((-(-370_070 // 2048) + 1) * 2048), stored - total)
    says("the other compressions' total is 1.5.1's before this fix: game, art, the folders twice, the menu",
         total == 85 * MB + 5 * MB + 2 * 370_070 + 100 * MB + 100 * MB + menu_extra, total)


def main():
    src = open(dow.RIALTO, encoding="utf-8").read()
    flat = src.replace("\r\n", "\n")
    tree = ast.parse(src)
    media_types = dow.extract_class_constant(src, "RialtoApp", "MEDIA_TYPES")
    reserve = dow.extract_class_constant(src, "RialtoApp", "MEDIA_RESERVE")
    margin = dow.extract_class_constant(src, "RialtoApp", "SPAN_MARGIN")
    mod = module_names(src, tree, (
        "PRESSED_DISC_TYPES", "MINI_DISC_MEDIA", "MINI_CD_SECTORS", "MINI_DVD5_SECTORS", "SECTOR_BYTES",
        "DVD9_LAYER0_SECTORS", "DVD9_LAYER_LIMIT", "DVD5_SECTORS", "pressed_refusal", "dvd9_layers",
        "master_sheet_text", "spanned_disc_count"))
    count = mod["spanned_disc_count"]

    print("1. the capacities")
    cd, dvd = capacity(media_types, MINI_CD), capacity(media_types, MINI_DVD)
    says("Mini CD: a 24-minute 8 cm CD, 108,000 sectors of 2,048 bytes", cd == 108_000 * 2048 == 221_184_000, cd)
    says("Mini DVD: inside DVD-R 2.0's 712,891 sectors, the smaller 8 cm blank",
         dvd <= 712_891 * 2048 and dvd <= 714_544 * 2048 and dvd == 1_460_000_000, dvd)
    says("the same sectors back the pressed limits",
         mod["MINI_CD_SECTORS"] == 108_000 and mod["MINI_DVD5_SECTORS"] * 2048 <= dvd)
    says("each source is cited where the numbers are",
         "712,891" in flat and "714,544" in flat and "Mini CD" in flat and "ECMA-267" in flat)
    print()

    print("2. the reserve and the slice size")
    measured = sum(MEASURED_BASE.values())
    says("the minis keep the 96 MiB reserve, and no media's reserve changed", reserve == 96 * 1024 * 1024)
    says("the heaviest Disc 1 measured (%.1f MB) rides in the reserve less the filesystem margin" % (measured / MB),
         measured + 64 * 2048 <= reserve - margin, measured)
    for name, want in ((MINI_CD, cd - reserve), (MINI_DVD, dvd - reserve)):
        host = media_host(src, {}, ["get_target_media_capacity", "get_disk_slice_size"], name)
        says("%s: slices of %s bytes, the media less the reserve" % (name, "{:,}".format(want)),
             host.get_disk_slice_size() == want, host.get_disk_slice_size())
        says("%s: a slice and the measured Disc 1 fit the disc less the margin" % name,
             want + measured <= capacity(media_types, name) - margin)
    print()

    print("3. a set of mini CDs, packed as the build packs them")
    work = tempfile.mkdtemp(prefix="rialto_minis_")
    try:
        fit = cd - margin
        for payload in (300 * MB, 400 * MB, 600 * MB, 1_000 * MB):
            span, base, slice_size, parts, discs = spanned_set(os.path.join(work, str(payload)), src,
                                                                media_types, MINI_CD, payload)
            label = "%d MB in %d slices" % (payload // MB, len(parts))
            says("%s: %d mini CDs, every one inside %s bytes" % (label, len(discs), "{:,}".format(fit)),
                 discs and all(size <= fit for size in discs), discs)
            says("%s: the first slice rides on Disc 1 with the menu" % label,
                 "setup-1.bin" in span.built[0][1] and "menu" in span.built[0][1])
            says("%s: every slice is on a disc, in order" % label,
                 [i for d in span.built for i in d[1] if i.endswith(".bin")]
                 == ["setup-%d.bin" % n for n in range(1, len(parts) + 1)])
            says("%s: no disc overflows, so no warning" % label, span.disc_overflow_warnings == [])
            says("%s: the meter's count is the build's, %d" % (label, len(discs)),
                 count(base, payload, cd, reserve, margin) == len(discs), count(base, payload, cd, reserve, margin))
        span, base, _s, _p, discs = spanned_set(os.path.join(work, "dvd"), src, media_types, MINI_DVD, 3_000 * MB)
        says("a set of mini DVDs packs the same way (%d discs)" % len(discs),
             all(size <= dvd - margin for size in discs) and count(base, 3_000 * MB, dvd, reserve, margin) == len(discs),
             discs)
        says("one disc when the base and the payload fit, as create_iso decides",
             count(50 * MB, cd - margin - 50 * MB, cd, reserve, margin) == 1
             and count(50 * MB, cd - margin - 50 * MB + 1, cd, reserve, margin) == 2)
        says("create_iso draws that line where the meter does",
             "if total_size > capacity - self.SPAN_MARGIN:" in flat and "fit = capacity - self.SPAN_MARGIN" in flat)
        meter_against_build(src, media_types, reserve, margin, count, os.path.join(work, "linux"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()

    print("4. the disc meter and the lines the build writes")
    theme = {k: k for k in ("meter_fill", "meter_warn", "meter_over", "meter_track", "header_bg", "button_bg")}
    meter_ns = {"MINI_DISC_MEDIA": mod["MINI_DISC_MEDIA"], "spanned_disc_count": count}

    def meter(media, total, disc1=48 * MB):
        host = media_host(src, meter_ns, ["get_target_media_capacity", "draw_disc_meter"], media,
                          disc_bar=Canvas(), disc_meter=Canvas(), theme_mode=Var("dark"), dark_theme=theme,
                          light_theme=theme, disc_fill_var=Var(""), _fill_bytes=total, _disc1_bytes=disc1)
        host.draw_disc_meter()
        return host.disc_fill_var.get()

    line = meter(MINI_CD, 150 * MB)
    says("a 150 MB demo on a Mini CD: one disc, in MB", line == "150 MB of 204 MB usable on %s - 73%%" % MINI_CD, line)
    line = meter(MINI_CD, 400 * MB, disc1=50 * MB)
    want = count(50 * MB, 350 * MB, cd, reserve, margin)
    says("400 MB on Mini CDs: the build's count, %d" % want, line.endswith(" - about %d discs" % want), line)
    line = meter(MINI_DVD, 1_200 * MB)
    says("1.2 GB on a Mini DVD", line == "1.20 GB of 1.44 GB usable on %s - 83%%" % MINI_DVD, line)
    says("the meter keeps Disc 1's weight beside the total, from disc_weights",
         "self._fill_bytes, self._disc1_bytes = self.disc_weights(" in flat)
    says("the over-limit line in MB under a gigabyte",
         'else f"{total_size // 1_000_000} MB")' in flat and "Build is {weight}, over the" in flat)

    fit_ns = dict(mod)

    def report(media, size, pressed=False):
        host = media_host(src, fit_ns, ["report_disc_media_fit"], media)
        host.pressed_disc_on = lambda: pressed
        host.report_disc_media_fit(size)
        return host.log

    says("Fits on, for a Mini CD: the mini named first",
         report(MINI_CD, 150 * MB)[0] == "💿 Fits on: Mini CD-R (210 MB, 8 cm), CD-R (700 MB), Mini DVD-R (1.4 GB, 8 cm), "
                                          "DVD-R (4.7 GB), DVD-R DL (8.5 GB), Blu-ray BD-R (25 GB), Blu-ray BD-R DL (50 GB)",
         report(MINI_CD, 150 * MB))
    says("Fits on, for a Mini DVD: the CDs it is too big for are left out",
         report(MINI_DVD, 1_300 * MB)[0].startswith("💿 Fits on: Mini DVD-R (1.4 GB, 8 cm), DVD-R (4.7 GB)"),
         report(MINI_DVD, 1_300 * MB))
    says("Fits on, for a CD 700 MB: a small game's line as it was, no mini",
         report("CD 700 MB", 150 * MB) == ["💿 Fits on: CD-R (700 MB), DVD-R (4.7 GB), DVD-R DL (8.5 GB), "
                                            "Blu-ray BD-R (25 GB), Blu-ray BD-R DL (50 GB)"],
         report("CD 700 MB", 150 * MB))
    says("Presses as, for a pressed Mini CD",
         report(MINI_CD, 150 * MB, True) == ["💿 Presses as: 8 cm CD-ROM, CD-ROM, 8 cm DVD-5, DVD-5, DVD-9"],
         report(MINI_CD, 150 * MB, True))
    says("Presses as, for a pressed CD 700 MB: as it was",
         report("CD 700 MB", 150 * MB, True) == ["💿 Presses as: CD-ROM, DVD-5, DVD-9"], report("CD 700 MB", 150 * MB, True))
    says("every disc the build makes for a mini presses as that mini",
         (cd - margin) // 2048 <= mod["MINI_CD_SECTORS"] and (dvd - margin) // 2048 <= mod["MINI_DVD5_SECTORS"])
    print()

    print("5. a pressed mini")
    says("both minis can be pressed", mod["pressed_refusal"](MINI_CD) == "" and mod["pressed_refusal"](MINI_DVD) == "")
    says("the sheet names an 8 cm CD-ROM and an 8 cm DVD-5",
         mod["PRESSED_DISC_TYPES"][MINI_CD] == "CD-ROM, 8 cm"
         and mod["PRESSED_DISC_TYPES"][MINI_DVD] == "DVD-5, 8 cm (DVD-1)")
    says("the full-size entries are as they were",
         {k: v for k, v in mod["PRESSED_DISC_TYPES"].items() if k not in (MINI_CD, MINI_DVD)}
         == {"CD 700 MB": "CD-ROM", "DVD 4.7 GB": "DVD-5", "DVD DL 8.5 GB": "DVD-9"})
    for name, sectors in ((MINI_CD, 100_000), (MINI_DVD, 700_000)):
        disc = {"file": "Demo.iso", "bytes": sectors * 2048, "md5": "0" * 32, "label": "DEMO", "udf": False,
                "type": mod["PRESSED_DISC_TYPES"][name]}
        sheet = mod["master_sheet_text"]("Demo", "Your Studio", "1.5.1", "19 October 2026", [disc], {})
        says("%s: the sheet's disc type, and no layer break" % name,
             "  Disc type:     %s\n" % disc["type"] in sheet and "Layer break" not in sheet
             and "presses cheaper" not in sheet and "—" not in sheet, sheet)
    says("the build looks the disc type up by the Target Media",
         'disc_type = PRESSED_DISC_TYPES.get(self.target_media_var.get(), "")' in flat)
    print()

    print("6. a 1.5.0 profile builds what it built before")
    says("1.5.0's media are all here, in their order, at their capacities",
         [m for m in media_types if m[0] not in (MINI_CD, MINI_DVD)] == MEDIA_150)
    host, _ns = tis.build_host(src)
    slicer = media_host(src, {}, ["get_target_media_capacity", "get_disk_slice_size"], "Auto (single disc)")
    host.get_disk_slice_size = types.MethodType(type(slicer).get_disk_slice_size, slicer)
    host.compression_var = Var("Balanced")

    def script_for(media):
        slicer.target_media_var = Var(media)
        script, out = tis.generate(host, {"Title": "Sky Quest", "Developer": "Your Studio"})
        shutil.rmtree(out, ignore_errors=True)
        return script.replace(out, "<out>")
    auto = script_for("Auto (single disc)")
    says("Auto writes no slice size", "DiskSliceSize=" not in auto)
    for name, cap in MEDIA_150[1:]:
        want = min(cap - 96 * 1024 * 1024, 2_100_000_000)
        script = script_for(name)
        changed = [line for line in script.splitlines() if line not in auto.splitlines()]
        if name in SLICE_150:
            says("%s: DiskSliceSize=%d, as 1.5.0 wrote it" % (name, SLICE_150[name]), want == SLICE_150[name])
        says("%s: only DiskSliceSize=%d differs from Auto" % (name, want),
             changed == ["DiskSliceSize=%d" % want] and script.replace("DiskSliceSize=%d\n" % want, "") == auto,
             changed)
    line = meter("CD 700 MB", 500 * MB)
    says("the meter on a CD 700 MB reads as 1.5.0's did", line == "0.50 GB of 0.64 GB usable on CD 700 MB - 79%", line)
    line = meter("DVD 4.7 GB", 10_000 * MB)
    says("and a set on DVD counts as 1.5.0's did", line.endswith(" - about %d discs" % (int(10e9 // (4.7e9 - reserve)) + 1)), line)
    print()

    print("7. the dropdown, its tooltips and the Help Guide")
    names = [name for name, _cap in media_types]
    says("the dropdown lists both minis, each before its full-size kin",
         names[1:5] == [MINI_CD, "CD 700 MB", MINI_DVD, "DVD 4.7 GB"], names[:6])
    says("the dropdown is filled from MEDIA_TYPES and shows every choice unscrolled",
         "values=[name for name, _cap in self.MEDIA_TYPES],\n"
         "                                   height=len(self.MEDIA_TYPES), style=\"Media.TCombobox\"," in flat)
    says("MINI_DISC_MEDIA names exactly the minis", tuple(mod["MINI_DISC_MEDIA"]) == (MINI_CD, MINI_DVD))
    tips = re.findall(r'ToolTip\(media_combo, "([^"]+)"\)', flat) + re.findall(r'ToolTip\(pressed_check, ([^)]+)\)', flat)
    says("the Target Media tooltip teaches what a Mini is", any("8 cm" in t and "tray drive" in t for t in tips), tips)
    says("the Pressed tooltip says the minis press", any("full size or 8 cm" in t for t in tips), tips)
    says("the Build Queue's Target Media column fits a mini's name", '("media", "Target Media", 160)' in flat)
    guide = open(os.path.join(REPO, "docs", "rialto-guide.html"), encoding="utf-8").read()
    says("the Help Guide's media table has both minis",
         "<td>%s</td><td>0.22 GB</td>" % MINI_CD in guide and "<td>%s</td><td>1.46 GB</td>" % MINI_DVD in guide)
    says("and its pressed section names them", "full size or 8 cm" in guide and "8 cm DVD-5" in guide)
    says("no em dash in what the minis added", "—" not in guide)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        for label in failures:
            print("  - " + label)
        return 1
    print("\nAll mini disc checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
