"""The disc meter counts each thing as the build places it (1.5.2; his word, 4 November 2026).

His question: the meter counted Mac and Linux builds twice (they go on the disc
once) and a mod folder beside the game once (it goes on twice). Should it count
them as the build actually places them? His answer: "Count as the build does".
Reviewers found the Menu Background the same way: three times on Fastest
install, and a copy short when it was picked from inside the game folder.
The developer's Steam library art (1.5.2) goes in menu/steam/ as the build
writes it, not as it was given, and rides in the installer's menu/ as well.

For each case the real refresh_disc_meter runs (its worker thread run in place)
and so the real disc_weights, and the real build steps run on the same folders
in build_all's order: copy_game_files_to_output, stage_mod_launcher,
build_bonus_gallery, stage_menu_artwork, stage_steam_art while Add to Steam is
ticked, the installer's Source: "*" sweep (read
from generate_enhanced_installer_script, as test_bonus_staging.py reads it),
stage_universal_builds after it, then the disc root _collect_disc_fileset names.
What lands is the installer's files and the disc root's files, added up. Each
case is weighed against the same disc without the thing, so the menu.exe,
runtime and logo allowances drop out and what is left is the thing itself:
the meter's difference must be the build's.

The Mac and Linux builds hold random bytes, which gzip cannot shrink, so the
archive the build writes is as heavy as one can be and the meter must still
not be under it. No window, Inno Setup or disc is needed.
"""
import ast
import gzip
import os
import random
import shutil
import sys
import tempfile
import textwrap
import threading
import types

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
sys.path.insert(0, HERE)
import progress_stub  # noqa: E402
import store_title_stub  # noqa: E402
import test_bonus_staging as tbs  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

failures = []
KB = 1024


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


class InPlaceThread:
    """threading.Thread for refresh_disc_meter's worker: runs it at start(), so the weights are there after."""
    def __init__(self, target, daemon=False):
        self.target = target

    def start(self):
        self.target()


SRC = open(RIALTO, encoding="utf-8").read()
MODULE = tbs.extract_module_funcs(SRC, [
    "_CONTROL_CHARS", "sanitize_text", "VIDEO_EXTENSIONS", "image_has_transparency", "asset_path",
    "menu_music_check", "menu_font_check", "MENU_MUSIC_MAX_BYTES", "MENU_MUSIC_LARGE_BYTES", "format_megabytes",
    "format_length", "font_facts", "menu_font_family_ok", "font_license_beside", "MENU_DEFAULT_FONT_FACTS"])

METER = ["refresh_disc_meter", "disc_weights", "unix_build_bytes", "unix_archive_stem", "folder_is_already_packaged",
         "menu_staging_bytes", "menu_inside_bytes", "menu_music_source", "menu_font_choice", "menu_theme_path",
         "resolved_mod_dir", "default_mod_dir", "resolved_bonus_dir", "default_bonus_dir",
         "RUNTIME_ALLOWANCE", "RUNTIME_STORED", "DISC1_FILES_ALLOWANCE", "UNIX_ARCHIVE_SUFFIXES",
         "UNIX_NOTES_ALLOWANCE", "STEAM_ART_ALLOWANCE", "steam_art_bytes", "_steam_still_possible", "_steam_weighed",
         "steam_piece_bytes", "steam_logo_bytes"]
BUILD = ["copy_game_files_to_output", "stage_mod_launcher", "build_bonus_gallery", "stage_menu_artwork",
         "_collect_disc_fileset", "_fileset_disc_bytes", "staged_mod_dir_name", "stage_universal_builds",
         "package_unix_build", "write_unix_launcher", "write_unix_instructions", "unix_readme_steps",
         "_unix_launch_target", "_is_unix_executable", "unix_launcher_script", "folder_bytes",
         "UNIX_EXEC_SUFFIXES", "UNIX_LAUNCH_PRIORITY",
         "STEAM_ART", "STEAM_ART_PIECES", "STEAM_ART_MAX_BYTES", "STEAM_ART_MAX_PIXELS", "STEAM_ART_MAX_FRAMES",
         "STEAM_ART_MAX_FRAME_PIXELS", "STEAM_ICO_MAX_ENTRIES", "STEAM_ICO_MAX_SIDE", "STEAM_ICO_MAX_PIXELS",
         "STEAM_ART_FORMATS", "STEAM_VIDEO_BACKGROUNDS", "steam_art_paths", "read_steam_piece", "_steam_turn",
         "_steam_frame", "_write_steam_piece", "_write_apng", "_ico_pictures", "_ico_as_given", "steam_art_sources",
         "_steam_game_logo", "_background_still", "_plate", "stage_steam_art", "_fill_crop", "_overlay_logo"]


def class_body(names):
    """RialtoApp's own methods and class constants, by name."""
    out, got = [], set()
    for node in ast.parse(SRC).body:
        if isinstance(node, ast.ClassDef) and node.name == "RialtoApp":
            for item in node.body:
                name = item.name if isinstance(item, ast.FunctionDef) else \
                    getattr(item.targets[0], "id", "") if isinstance(item, ast.Assign) else ""
                if name in names:
                    text = textwrap.dedent(ast.get_source_segment(SRC, item))
                    for decorator in getattr(item, "decorator_list", []):
                        text = "@" + ast.get_source_segment(SRC, decorator) + "\n" + text
                    out.append(text)
                    got.add(name)
    missing = set(names) - got
    if missing:
        raise SystemExit("could not extract RialtoApp.%s" % sorted(missing))
    return "\n\n".join(out)


def make_app():
    """A stand-in RialtoApp with the real meter and build methods and the profile's fields."""
    ns = {"os": os, "sys": sys, "shutil": shutil, "re": __import__("re"), "json": __import__("json"),
          "wave": __import__("wave"), "tempfile": tempfile, "subprocess": __import__("subprocess"), "Image": Image,
          "prebuilt_menu_exe": lambda: None,
          "threading": types.SimpleNamespace(Thread=InPlaceThread, Lock=threading.Lock),
          "tk": types.SimpleNamespace(TclError=RuntimeError)}
    ns.update(progress_stub.namespace())
    # unix_archive_stem names the Mac and Linux packages through player_title (the store's format stays off).
    ns.update(store_title_stub.namespace(SRC))
    exec(MODULE, ns)
    body = class_body(sorted(set(METER + BUILD))) + "\n\n" + progress_stub.methods(SRC)
    exec("class Host:\n" + textwrap.indent(body, "    "), ns)
    app = ns["Host"]()
    app.update_status = lambda line: None
    app.disc_bar = object()
    app.root = types.SimpleNamespace(after=lambda _ms, _then: None)
    app.draw_disc_meter = lambda: None
    app.entries = {"Title": Var("Meter Probe")}
    for name in ("bg_path_var", "logo_path_var", "company_logo_var", "ico_path_var", "disc_icon_var",
                 "mac_build_var", "linux_build_var", "bonus_folder_var", "mod_folder_var", "menu_music_var"):
        setattr(app, name, Var(""))
    app.mod_launcher_var = Var(False)
    app.steam_button_var = Var(False)
    for _key, attr, *_rest in app.STEAM_ART_PIECES:
        setattr(app, attr, Var(""))
    app.remove_wti_branding = Var(True)
    app.compression_var = Var("Balanced")
    app.menu_theme = {}
    return app


EXCLUDES = tbs.parse_excludes(tbs.inno_files_line(SRC))


def landed(app, work):
    """What the build puts on the media for this profile: (the installer's bytes + the disc root's, Disc 1's root)."""
    game = app.current_game_path
    out = os.path.join(work, "output", os.path.basename(game))
    shutil.rmtree(os.path.join(work, "output"), ignore_errors=True)
    os.makedirs(out)
    app.copy_game_files_to_output(game, out)                                    # step 2
    app.stage_mod_launcher(game, out)                                           # step 3.5
    app.build_bonus_gallery(game, out, app.resolved_bonus_dir() or None)        # step 3.6
    os.makedirs(os.path.join(out, "menu"))
    app.stage_menu_artwork(os.path.join(out, "menu"))                           # step 4
    if app.steam_button_var.get():
        app.stage_steam_art(os.path.join(out, "menu"))
    with open(os.path.join(out, "installer.iss"), "w", encoding="utf-8") as f:  # step 5
        f.write("; written")
    installer = sum(os.path.getsize(os.path.join(out, *rel.split("/")))         # step 6, ISCC's sweep
                    for rel in tbs.inno_sweep(out, EXCLUDES))
    for name, text in (("setup.exe", "MZ"), ("README.txt", "Run setup.exe.\n"), ("autorun.inf", "[autorun]\n")):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
    app.stage_universal_builds(out)                                             # step 9.5, after ISCC
    items = app._collect_disc_fileset(out)                                      # step 10
    root = 0
    for item in items:
        path = os.path.join(out, item)
        if os.path.isdir(path):
            root += sum(os.path.getsize(os.path.join(d, n)) for d, _s, files in os.walk(path) for n in files)
        else:
            root += os.path.getsize(path)
    return installer + root, app._fileset_disc_bytes(out, items), out


def metered(app, stored):
    app.compression_var.set("Fastest install" if stored else "Balanced")
    app.refresh_disc_meter()
    return app._fill_bytes, app._disc1_bytes


def noise(path, size, head=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(head + random.randbytes(size - len(head)))
    return path


def folder_weight(folder):
    return sum(os.path.getsize(os.path.join(d, n)) for d, _s, files in os.walk(folder) for n in files)


def entries(*folders):
    """Files and folders under `folders`: the tar headers the meter counts one by one."""
    return sum(1 + len(files) for folder in folders for _d, _s, files in os.walk(folder))


def tar_agrees(app, out, label, folder, launcher):
    """The tar inside the build's .tar.gz against the meter's count of it, header for header."""
    archive = next(n for n in os.listdir(os.path.join(out, label)) if n.endswith(".tar.gz"))
    with open(os.path.join(out, label, archive), "rb") as f:
        tar = len(gzip.decompress(f.read()))
    root = archive[:-len(".tar.gz")]
    weight, _sectors = app.unix_build_bytes(folder, root)
    packed = weight - app.UNIX_NOTES_ALLOWANCE

    def bound(size):
        return size + (size >> 12) + (size >> 14) + (size >> 25) + 7 + 18 + len(root.encode("utf-8")) + 5
    if launcher:
        says("%s: the meter's tar is the build's, %s bytes, header for header" % (label, "{:,}".format(tar)),
             packed == bound(tar), (packed, bound(tar)))
    else:
        # The meter always allows for a start.sh, which the build writes only into a Linux archive with a
        # launcher: a record more at most.
        says("%s: the meter's tar is the build's, %s bytes, or a record more for the start.sh it allows for"
             % (label, "{:,}".format(tar)), packed in (bound(tar), bound(tar + 20 * 512)), (packed, bound(tar)))


def compare(label, app, work, turn_on, turn_off, exact=True, note="", archived=(), in_menu=0, menu_folders=0):
    """The meter's difference for the thing against the build's, on Balanced and on Fastest install.

    `exact` False is a Mac or Linux build: the meter counts its .tar.gz at the most it can weigh, so it is
    never under the build and over it by what gzip squeezes out of the tar's headers, a KB or so for each
    file and folder in `archived`, and for each archive its last record and the notes beside it. `in_menu` is how many
    files the thing puts in menu/, in `menu_folders` folders of their own, which Disc 1 weighs by their bytes, their
    sectors being in Disc 1's allowance.
    """
    slack = 16 * KB * max(len(archived), 1) + KB * entries(*archived)
    turn_off(app)
    base_land, base_root, _out = landed(app, work)
    base = {stored: metered(app, stored) for stored in (False, True)}
    turn_on(app)
    land, root, out = landed(app, work)
    build = land - base_land
    for stored in (False, True):
        fill, disc1 = metered(app, stored)
        meter = fill - base[stored][0]
        on_root = disc1 - base[stored][1]
        how = "Fastest install" if stored else "Balanced"
        if exact:
            says("%s, %s: the meter adds %s bytes, what the build places%s"
                 % (label, how, "{:,}".format(meter), note), meter == build, (meter, build))
        else:
            says("%s, %s: the meter adds %s bytes, the build %s: never under, within %s KB"
                 % (label, how, "{:,}".format(meter), "{:,}".format(build), "{:,}".format((build // 1000 + slack) // KB)),
                 build <= meter <= build + build // 1000 + slack, (meter, build))
        placed = root - base_root
        if in_menu:
            says("%s, %s: Disc 1's root, the file's bytes in menu/" % (label, how),
                 placed - 2048 * (2 * in_menu + menu_folders) < on_root <= placed, (on_root, placed))
        elif exact:
            says("%s, %s: Disc 1's root as the build fills it" % (label, how), on_root == placed, (on_root, placed))
        else:
            says("%s, %s: Disc 1's root never under the build's" % (label, how),
                 placed <= on_root <= placed + placed // 1000 + slack + 8 * KB, (on_root, placed))
    turn_off(app)
    return build, out


def main():
    random.seed(20261104)
    work = tempfile.mkdtemp(prefix="rialto_meter_places_")
    try:
        game = os.path.join(work, "input", "Probe")
        noise(os.path.join(game, "Probe.exe"), 300 * KB)
        noise(os.path.join(game, "data", "level.pak"), 200 * KB)
        app = make_app()
        app.current_game_path = game

        print("1. Mac and Linux builds: once, on the disc root, as stage_universal_builds packs them")
        beside_mac = os.path.join(work, "input", "Probe Mac")
        noise(os.path.join(beside_mac, "Probe.app", "Contents", "MacOS", "Probe"), 400 * KB)
        noise(os.path.join(beside_mac, "Probe.app", "Contents", "Resources", "data.pak"), 250 * KB)
        inside_linux = os.path.join(game, "builds", "linux64")
        noise(os.path.join(inside_linux, "Probe.x86_64"), 350 * KB, b"\x7fELF")
        noise(os.path.join(inside_linux, "Probe_Data", "level.pak"), 150 * KB)
        # A name past tar's 100 bytes and one outside ASCII: tarfile gives each its own long header.
        noise(os.path.join(inside_linux, "Probe_Data", "StreamingAssets", "a_long_folder_name_for_the_audio_banks",
                           "music_and_ambience_bank_for_the_first_world.bank"), 40 * KB)
        noise(os.path.join(inside_linux, "Probe_Data", "Niveau_été.pak"), 20 * KB)
        beside_linux = os.path.join(work, "input", "Probe Linux packed")
        noise(os.path.join(beside_linux, "Probe.AppImage"), 500 * KB, b"\x7fELF")
        inside_mac = os.path.join(game, "mac")
        noise(os.path.join(inside_mac, "Probe.dmg"), 300 * KB)
        noise(os.path.join(inside_mac, "Probe-mac.zip"), 100 * KB)

        def var(name, value):
            return lambda a: getattr(a, name).set(value)

        build, out = compare("a raw Mac build beside the game", app, work,
                             var("mac_build_var", beside_mac), var("mac_build_var", ""), exact=False,
                             archived=[beside_mac])
        says("the build packed it once, as a .tar.gz in Mac/", sorted(os.listdir(os.path.join(out, "Mac")))
             == ["Meter Probe-Mac.tar.gz", "START HERE.txt"], os.listdir(os.path.join(out, "Mac")))
        tar_agrees(app, out, "Mac", beside_mac, launcher=False)
        says("1.5.1 counted it twice, the source tree (%s bytes): now about once"
             % "{:,}".format(2 * folder_weight(beside_mac)), build < 1.1 * folder_weight(beside_mac),
             (build, folder_weight(beside_mac)))
        build, out = compare("a raw Linux build inside the game folder", app, work,
                             var("linux_build_var", inside_linux), var("linux_build_var", ""), exact=False,
                             archived=[inside_linux])
        tar_agrees(app, out, "Linux", inside_linux, launcher=True)
        says("the installer has it with the game folder either way; the disc root adds the archive once",
             build < 1.1 * folder_weight(inside_linux), (build, folder_weight(inside_linux)))
        compare("a packed Linux build (an AppImage) beside the game", app, work,
                var("linux_build_var", beside_linux), var("linux_build_var", ""), exact=False)
        build, _out = compare("a packed Mac build (a .dmg and a .zip) in the game folder's own mac/", app, work,
                              var("mac_build_var", inside_mac), var("mac_build_var", ""), exact=False)
        says("the disc root carried the game's mac/ already, with or without the Mac build: only its notes are new",
             build < 4 * KB, build)
        own = os.path.join(game, "Linux")

        def own_linux(a):
            noise(os.path.join(own, "libsteam_api.so"), 80 * KB, b"ELF")

        def no_own_linux(a):
            shutil.rmtree(own, ignore_errors=True)

        build, _out = compare("a Linux folder of the game's own, no Linux build named", app, work, own_linux,
                              no_own_linux, note=", in the installer and on the disc root")
        says("twice: the disc root takes every folder named Linux", build == 2 * 80 * KB, build)

        def both(a):
            a.mac_build_var.set(beside_mac)
            a.linux_build_var.set(inside_linux)

        def neither(a):
            a.mac_build_var.set("")
            a.linux_build_var.set("")

        compare("a Mac build and a Linux build on one disc", app, work, both, neither, exact=False,
                archived=[beside_mac, inside_linux])
        print()

        print("2. a mod folder: in the installer and on the disc root, unless the game folder already holds it")
        beside_mods = os.path.join(work, "input", "ModKit")
        noise(os.path.join(beside_mods, "ModKit.exe"), 120 * KB)
        noise(os.path.join(beside_mods, "templates", "item.json"), 30 * KB)
        root_mods = os.path.join(game, "mods")
        noise(os.path.join(root_mods, "Maker.exe"), 90 * KB)
        nested_mods = os.path.join(game, "tools", "Workshop")
        noise(os.path.join(nested_mods, "Workshop.exe"), 70 * KB)

        def mods(folder):
            def on(a):
                a.mod_launcher_var.set(True)
                a.mod_folder_var.set(folder)
            return on

        def no_mods(a):
            a.mod_launcher_var.set(False)
            a.mod_folder_var.set("")

        build, _out = compare("a mod folder beside the game", app, work, mods(beside_mods), no_mods,
                              note=", twice (1.5.1 counted it once)")
        says("twice: the installer's copy and the disc root's", build == 2 * folder_weight(beside_mods),
             (build, folder_weight(beside_mods)))
        build, _out = compare("mods/ at the game folder's root", app, work, mods(""), no_mods,
                              note=", once more than the game's own copy, as today")
        says("once more: the game folder brings it into the installer", build == folder_weight(root_mods),
             (build, folder_weight(root_mods)))
        build, _out = compare("a mod folder deeper in the game folder (tools/Workshop)", app, work,
                              mods(nested_mods), no_mods, note=", twice more than the game's own copy")
        says("twice more: copied into the output as Workshop/, the game's tools/Workshop stays",
             build == 2 * folder_weight(nested_mods), (build, folder_weight(nested_mods)))
        other_mods = os.path.join(work, "elsewhere", "mods")
        noise(os.path.join(other_mods, "Other.exe"), 60 * KB)
        build, _out = compare("a mods folder picked from elsewhere while the game has its own mods/", app, work,
                              mods(other_mods), no_mods)
        says("the picked folder twice, and the game's own mods/ no longer in the installer",
             build == 2 * folder_weight(other_mods) - folder_weight(root_mods), build)
        print()

        print("3. the Menu Background: in menu/, on the disc root and inside the installer")
        art = os.path.join(work, "art", "background.gif")
        noise(art, 180 * KB, b"GIF89a")
        in_game = os.path.join(game, "art", "title.jpg")
        noise(in_game, 140 * KB, b"\xff\xd8\xff")
        video = os.path.join(work, "art", "intro.mp4")
        noise(video, 90 * KB)
        build, _out = compare("a background beside the game", app, work, var("bg_path_var", art),
                              var("bg_path_var", ""), note=", twice (1.5.1 counted three times on Fastest install)",
                              in_menu=True)
        says("twice", build == 2 * os.path.getsize(art), build)
        build, _out = compare("a background picked from inside the game folder", app, work,
                              var("bg_path_var", in_game), var("bg_path_var", ""),
                              note=", twice more than the game's own copy (1.5.1: once more)", in_menu=True)
        says("twice more", build == 2 * os.path.getsize(in_game), build)
        build, _out = compare("a video background, which the build refuses", app, work, var("bg_path_var", video),
                              var("bg_path_var", ""), note=", nothing")
        says("nothing", build == 0, build)
        print()

        print("4. everything at once, as one profile")

        def everything(a):
            both(a)
            mods(beside_mods)(a)
            a.bg_path_var.set(in_game)

        def nothing(a):
            neither(a)
            no_mods(a)
            a.bg_path_var.set("")

        compare("Mac, Linux, a mod folder and the background together", app, work, everything, nothing, exact=False,
                archived=[beside_mac, inside_linux])
        flat = SRC.replace("\r\n", "\n")
        says("refresh_disc_meter hands disc_weights the builds and the mod folder, and no background as an extra",
             "menu_inside + steam_bytes, builds, mod)" in flat
             and "(self.logo_path_var, self.company_logo_var," in flat)
        says("package_unix_build names its archive as the meter does",
             "stem = self.unix_archive_stem()" in class_body(["package_unix_build"]))
        print()

        print("5. the developer's Steam library art: in menu/steam/ as the build writes it, on the disc root and"
              " inside the installer")
        steam_art = os.path.join(work, "input", "Steam art")
        os.makedirs(steam_art)

        def noisy(size, mode="RGB"):
            return Image.frombytes("RGB", size, random.randbytes(size[0] * size[1] * 3)).convert(mode)
        given = {"Capsule": os.path.join(steam_art, "capsule.jpg"), "Header": os.path.join(steam_art, "header.webp"),
                 "Hero": os.path.join(steam_art, "hero.png"), "Logo": os.path.join(steam_art, "logo.webp"),
                 "Icon": os.path.join(steam_art, "icon.png")}
        # A JPG written again at quality 95, a still WebP written as a PNG, an animated PNG and an animated
        # WebP written frame by frame, a PNG icon written again.
        noisy((300, 450)).save(given["Capsule"], "JPEG", quality=40)
        noisy((460, 215)).save(given["Header"], "WEBP", quality=60)
        hero = [noisy((480, 155)) for _ in range(3)]
        hero[0].save(given["Hero"], "PNG", save_all=True, append_images=hero[1:], duration=[50, 90, 130], loop=0)
        logo = [noisy((320, 180), "RGBA") for _ in range(2)]
        logo[0].save(given["Logo"], "WEBP", save_all=True, append_images=logo[1:], duration=[80, 160], loop=0)
        noisy((256, 256), "RGBA").save(given["Icon"], "PNG")

        def steam_on(a):
            a.steam_button_var.set(True)
            for key, attr, *_rest in a.STEAM_ART_PIECES:
                getattr(a, attr).set(given[key])

        def steam_off(a):
            a.steam_button_var.set(False)
            for _key, attr, *_rest in a.STEAM_ART_PIECES:
                getattr(a, attr).set("")

        build, out = compare("Add to Steam with every piece the developer's own", app, work, steam_on, steam_off,
                             note=", twice", in_menu=5, menu_folders=1)
        folder = os.path.join(out, "menu", "steam")
        says("the build wrote the five pieces", sorted(os.listdir(folder)) == [
            "capsule.jpg", "hero.png", "icon.png", "logo.png", "wide.png"], os.listdir(folder))
        says("twice what menu/steam/ weighs, not what the files given weigh",
             build == 2 * folder_weight(folder) != 2 * sum(os.path.getsize(p) for p in given.values()),
             (build, folder_weight(folder)))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()
    if failures:
        print("%d check(s) failed:" % len(failures))
        for label in failures:
            print("  - " + label)
        return 1
    print("All disc meter placement checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
