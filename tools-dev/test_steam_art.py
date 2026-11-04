"""The developer's own Steam art (1.5.2): Disc Extras' rows under Add to Steam, the checks, the disc, the menu.

Ticking "Show an Add to Steam button after install" shows one row for each
picture Steam has for a game, under the name Steamworks gives it: Library
Capsule, Library Header, Library Hero, Library Logo and Shortcut Icon. Each is
optional; an empty row is made by Rialto from the menu background and Game
Logo as before (the icon stays the Game Icon).

Every size and format Steam takes for a piece is taken as the developer gave
it. Only the file itself is refused: not there, a folder, empty, not a
picture, over 64 MB, past 40 million pixels. A refused or odd file never
stops a build.

  1. the pieces, their names, Steam's sizes and files, and the hero at Steam's size
  2. the checks on Browse and at build: Steam's current, half-size, older and
     niche sizes all taken as they are, every format Steam reads, an animated
     PNG or WebP kept, another shape said with its size beside Steam's, a logo
     with no transparency and a non-square icon taken and said, an .ico made
     again from its own pictures;
     and the refusals about the file, with hostile names and files
  3. staging into menu/steam/: the developer's pieces in place of the composed
     ones, at their own size and extension, frames and timing kept, the rest
     composed, a refused or unwritable piece composed and said, a stale folder
  4. kept: the profile's "SteamArt" written, read back, reset, carried by the
     startup profile and the last session, and moved with the game folder
  5. Disc Extras: the rows sit under the tick box and show only while it is
     ticked, each with a Browse and a tooltip; the Help Guide has a row each
  6. the disc meter counts each piece as the build writes it, on the meter's
     worker thread, once per file, and a piece the build composes at its
     allowance, only when there is something to compose it from
  7. the disc menu: ADD TO STEAM copies each piece under the names Steam reads,
     with the extension it was staged under, an old disc's fixed names, the
     icon into the grid folder with the shortcut's icon field naming that copy,
     the logo's place file, and a disc with no art as before

The real methods are pulled out of Rialto.pyw by AST and run on stub hosts
against temp folders: no window is opened, no Steam is needed.

Usage: python test_steam_art.py [path-to-Rialto.pyw]
"""
import ast
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
SRC = open(RIALTO, encoding="utf-8").read()
TREE = ast.parse(SRC)
failures = []


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def class_members(class_name, names, source=SRC, tree=TREE):
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name)
    found = {}
    for item in cls.body:
        if isinstance(item, ast.FunctionDef) and item.name in names:
            found[item.name] = item
        elif isinstance(item, ast.Assign) and getattr(item.targets[0], "id", "") in names:
            found[item.targets[0].id] = item
    missing = set(names) - set(found)
    if missing:
        raise SystemExit("could not extract %s" % sorted(missing))
    out = []
    for name in names:
        node = found[name]
        text = textwrap.dedent(ast.get_source_segment(source, node))
        for deco in getattr(node, "decorator_list", []):
            text = "@" + ast.get_source_segment(source, deco) + "\n" + text
        out.append(text)
    return "\n\n".join(out)


def module_function(name):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SRC, node)


def method_source(name):
    return class_members("RialtoApp", [name])


ART = ["STEAM_ART", "STEAM_ART_PIECES", "STEAM_ART_MAX_BYTES", "STEAM_ART_MAX_PIXELS", "STEAM_ART_MAX_FRAMES",
       "STEAM_ART_MAX_FRAME_PIXELS", "STEAM_ICO_MAX_ENTRIES", "STEAM_ICO_MAX_SIDE", "STEAM_ICO_MAX_PIXELS",
       "STEAM_ART_FORMATS", "STEAM_VIDEO_BACKGROUNDS", "steam_art_paths", "set_steam_art", "read_steam_piece",
       "_steam_turn", "_steam_frame", "_write_steam_piece", "_write_apng", "_ico_pictures", "_ico_as_given",
       "steam_art_sources", "_steam_game_logo", "_background_still", "_plate", "stage_steam_art", "_fill_crop",
       "_overlay_logo"]


def load_builder(names=ART):
    ns = {"os": os, "shutil": shutil, "subprocess": subprocess, "tempfile": tempfile, "threading": threading,
          "Image": Image}
    exec(SRC[SRC.index("_CONTROL_CHARS = "):].split("\n", 1)[0], ns)
    exec(module_function("sanitize_text"), ns)
    exec("class Builder:\n" + textwrap.indent(class_members("RialtoApp", names), "    "), ns)

    class Host(ns["Builder"]):
        def __init__(self):
            self.log = []
            self.current_game_path = ""
            self.bg_path_var, self.logo_path_var = Var(""), Var("")
            for _key, attr, *_rest in self.STEAM_ART_PIECES:
                setattr(self, attr, Var(""))

        def update_status(self, message):
            self.log.append(message)
    return Host


def picture(path, size, mode="RGB", color=(200, 40, 40), fmt=None, alpha_hole=False):
    image = Image.new(mode, size, color if mode != "RGBA" else color + (255,))
    if alpha_hole:
        image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(path, fmt or ("JPEG" if path.lower().endswith((".jpg", ".jpeg")) else None))
    return path


def animation(path, size, fmt, timing=(40, 80, 120, 160)):
    """An animated PNG or WebP whose frames differ in color and in how long each shows."""
    frames = [Image.new("RGBA", size, (60 * i, 200 - 40 * i, 30, 255)) for i in range(len(timing))]
    frames[0].save(path, fmt, save_all=True, append_images=frames[1:], duration=list(timing), loop=0)
    return path


def frames_of(path):
    """(format, [(duration, center color), ...]) for every frame of a staged file."""
    with Image.open(path) as im:
        out = []
        for index in range(getattr(im, "n_frames", 1)):
            im.seek(index)
            im.load()
            out.append((im.info.get("duration"), im.convert("RGB").getpixel((im.size[0] // 2, im.size[1] // 2))))
        return im.format, out


def ico_bytes(sizes):
    buffer = io.BytesIO()
    Image.new("RGBA", (256, 256), (10, 120, 200, 255)).save(buffer, "ICO", sizes=sizes)
    return buffer.getvalue()


# Every size the research found Steam (or the tools that set Steam art) takes, by piece:
# Steamworks' current size, its half-size, the older sizes, and the niche ones SteamGridDB serves.
SIZES = {
    "Capsule": [(600, 900), (300, 450), (342, 482), (660, 930), (512, 512), (1024, 1024)],
    "Header": [(920, 430), (460, 215), (292, 136), (512, 512), (1024, 1024)],
    "Hero": [(3840, 1240), (1920, 620), (860, 380), (1600, 650)],
    "Logo": [(1280, 720), (640, 360), (1280, 300), (400, 720), (960, 540)],
    "Icon": [(s, s) for s in (8, 10, 14, 16, 20, 24, 28, 32, 35, 40, 48, 54, 56, 57, 60, 64, 72, 76, 80, 90, 96, 100,
                              114, 120, 128, 144, 150, 152, 160, 180, 184, 192, 194, 256, 310, 512, 600, 768, 1024)],
}


def main():
    Host = load_builder()
    host = Host()
    work = tempfile.mkdtemp(prefix="rialto_steam_art_")
    try:
        # ---------------------------------------------------------------- 1
        print("1. the pieces, under Steam's own names, at Steam's own sizes")
        pieces = {key: (attr, name, stem, w, h) for key, attr, name, stem, w, h in host.STEAM_ART_PIECES}
        ok("five pieces, in the order the rows show them",
           [p[0] for p in host.STEAM_ART_PIECES] == ["Capsule", "Header", "Hero", "Logo", "Icon"])
        ok("named as Steamworks names them",
           [p[2] for p in host.STEAM_ART_PIECES] == ["Library Capsule", "Library Header", "Library Hero",
                                                     "Library Logo", "Shortcut Icon"])
        ok("Library Capsule, Steam's 600 x 900, as capsule", pieces["Capsule"][2:] == ("capsule", 600, 900))
        ok("Library Header, Steam's 920 x 430, as wide", pieces["Header"][2:] == ("wide", 920, 430))
        ok("Library Hero, Steam's 3840 x 1240, as hero", pieces["Hero"][2:] == ("hero", 3840, 1240))
        ok("Library Logo, Steam's 1280 x 720 box, as logo", pieces["Logo"][2:] == ("logo", 1280, 720))
        ok("Shortcut Icon, Steam's 256 x 256, as icon", pieces["Icon"][2:] == ("icon", 256, 256))
        composed = {f: (w, h) for f, w, h, _s, _l in host.STEAM_ART}
        ok("the composer makes the hero at Steam's 3840 x 1240, not the half-size 1920 x 620",
           composed.get("hero.png") == (3840, 1240), composed)
        ok("and the capsule and header as before",
           composed.get("capsule.png") == (600, 900) and composed.get("wide.png") == (920, 430))
        ok("each composed file is a piece's own stem",
           all(os.path.splitext(f)[0] in {p[3] for p in host.STEAM_ART_PIECES} for f in composed))
        print()

        # ---------------------------------------------------------------- 2
        print("2. the checks, on Browse and at build")
        d = os.path.join(work, "art")
        os.makedirs(d)
        read = host.read_steam_piece

        # 2a. every size Steam takes, taken as it is, in each format Steam reads
        refused, resized, misnamed = [], [], []
        for key, sizes in SIZES.items():
            stem = pieces[key][2]
            for size in sizes:
                kinds = [("png", "PNG", ".png"), ("jpg", "JPEG", ".jpg"), ("webp", "WEBP", ".png")]
                if key == "Logo":
                    kinds = [("png", "PNG", ".png"), ("webp", "WEBP", ".png"), ("jpg", "JPEG", ".png")]
                if key == "Icon":
                    kinds = [("png", "PNG", ".png"), ("webp", "WEBP", ".png")]
                for ext, fmt, staged_as in kinds:
                    path = os.path.join(d, "%s-%dx%d.%s" % (key, size[0], size[1], ext))
                    picture(path, size, mode="RGB" if fmt == "JPEG" else "RGBA", fmt=fmt,
                            alpha_hole=fmt != "JPEG" and key == "Logo")
                    got = read(key, path)
                    if got[0] is None or got[2]:
                        refused.append((key, size, fmt, got[2]))
                    elif got[0].size != size:
                        resized.append((key, size, fmt, got[0].size))
                    elif got[1] != stem + staged_as:
                        misnamed.append((key, size, fmt, got[1]))
        ok("every size in the research, for every piece and format, is taken: none refused", not refused, refused[:4])
        ok("and taken at the size it was given: none scaled", not resized, resized[:4])
        ok("a PNG or WebP goes as <piece>.png, a JPG as <piece>.jpg (a JPG logo as logo.png)", not misnamed,
           misnamed[:4])
        for key, size in (("Icon", (32, 32)), ("Icon", (256, 256)), ("Icon", (16, 16))):
            path = os.path.join(d, "legacy-%d.ico" % size[0])
            Image.new("RGBA", size, (10, 120, 200, 255)).save(path, sizes=[size])
            got = read(key, path)
            ok("a %d x %d .ico is taken as icon.ico" % size, got[0] is not None and got[1:3] == ("icon.ico", ""), got[1:])

        got = read("Capsule", picture(os.path.join(d, "capsule.png"), (600, 900)))
        ok("Steam's own 600 x 900 is taken with nothing to say", got[0] is not None and got[1:] == ("capsule.png", "", ""),
           got[1:])
        got = read("Capsule", picture(os.path.join(d, "near.png"), (602, 900)))
        ok("within 1 percent of the shape counts as the shape", got[0] is not None and got[3] == "", got[3])
        got = read("Capsule", picture(os.path.join(d, "big.jpg"), (1200, 1800)))
        ok("a 1200 x 1800 JPG is taken as it is, as capsule.jpg",
           got[0] is not None and got[0].size == (1200, 1800) and got[1:] == ("capsule.jpg", "", ""), got[1:])
        got = read("Capsule", picture(os.path.join(d, "tiny.png"), (100, 150)))
        ok("a small one is taken too: nothing is refused as too soft", got[0] is not None and got[0].size == (100, 150)
           and got[2] == "", got[2])

        # 2b. another shape: taken, and the note gives its size beside Steam's, and nothing about how Steam shows it
        for key, size in (("Capsule", (1920, 1080)), ("Capsule", (300, 900)), ("Header", (512, 512)),
                          ("Hero", (1600, 650)), ("Hero", (3840, 2160)), ("Header", (2000, 430))):
            name = pieces[key][1]
            want = "%d x %d" % pieces[key][3:]
            shown = "%s-shape-%dx%d.png" % (key, size[0], size[1])
            got = read(key, picture(os.path.join(d, shown), size))
            ok("the %s at %d x %d is taken, and the note gives its size beside Steam's %s" % (name, size[0], size[1],
                                                                                           want),
               got[0] is not None and got[0].size == size and got[2] == ""
               and got[3] == "%s is %d x %d; Steam's %s is %s." % (shown, size[0], size[1], name, want), got[1:])

        # 2c. the logo and the icon
        got = read("Logo", picture(os.path.join(d, "logo-solid.png"), (1280, 400), mode="RGBA"))
        ok("a logo with no transparent pixel is taken, and the note says so",
           got[0] is not None and got[2] == "" and "has no transparent background, so Steam draws it over the "
           "Library Hero with its background." in got[3], got[1:])
        got = read("Logo", picture(os.path.join(d, "logo.png"), (640, 400), mode="RGBA", alpha_hole=True))
        ok("a transparent logo at 640 x 400 is taken as it is, transparency kept, nothing to say",
           got[0] is not None and got[0].size == (640, 400) and got[0].mode == "RGBA" and got[1:] == ("logo.png", "", ""),
           got[1:])
        got = read("Logo", picture(os.path.join(d, "logo.jpg"), (1280, 720)))
        ok("a JPG logo is taken, as logo.png, said as having no transparency and written as a PNG",
           got[0] is not None and got[1] == "logo.png" and "no transparent background" in got[3]
           and "Rialto writes it as a PNG, which Steam reads." in got[3], got[1:])
        got = read("Icon", picture(os.path.join(d, "icon-wide.png"), (512, 256), mode="RGBA"))
        ok("an icon that is not square is taken, and the note says Steam's is",
           got[0] is not None and got[0].size == (512, 256) and got[1] == "icon.png" and got[2] == ""
           and "is 512 x 256, not a square." in got[3], got[1:])
        got = read("Icon", picture(os.path.join(d, "icon.jpg"), (256, 256)))
        ok("a JPG icon is taken, as icon.png", got[0] is not None and got[1] == "icon.png"
           and "Rialto writes it as a PNG" in got[3], got[1:])

        # 2d. formats Steam does not read in its grid folder are written out as a PNG
        for ext, fmt, mode in (("gif", "GIF", "P"), ("bmp", "BMP", "RGB"), ("tif", "TIFF", "RGB"), ("tga", "TGA", "RGB")):
            path = picture(os.path.join(d, "capsule.%s" % ext), (600, 900), mode=mode,
                           color=3 if mode == "P" else (200, 40, 40), fmt=fmt)
            got = read("Capsule", path)
            ok("a %s is taken and written as capsule.png" % fmt, got[0] is not None and got[1] == "capsule.png"
               and got[3] == "Rialto writes it as a PNG, which Steam reads.", got[1:])
        got = read("Capsule", picture(os.path.join(d, "disguised.png"), (600, 900), fmt="WEBP"))
        ok("a WebP named .png is judged by what it is: a still WebP, written as a real PNG",
           got[0] is not None and got[1] == "capsule.png" and "writes it as a PNG" in got[3], got[1:])

        # 2e. animated pictures keep their frames
        for key, fmt in (("Capsule", "PNG"), ("Header", "WEBP"), ("Hero", "PNG"), ("Logo", "WEBP")):
            size = (60, 90) if key == "Capsule" else (92, 43) if key == "Header" else (384, 124) if key == "Hero" \
                else (128, 72)
            path = animation(os.path.join(d, "moving-%s.%s" % (key, fmt.lower())), size, fmt)
            got = read(key, path)
            ok("an animated %s %s is taken with its four frames, as %s.png" % (fmt, pieces[key][1], pieces[key][2]),
               got[0] is not None and getattr(got[0], "n_frames", 1) == 4 and got[1] == pieces[key][2] + ".png"
               and got[2] == "" and "writes it as a PNG" not in got[3], (got[1:], getattr(got[0], "n_frames", 1)))
        gif = os.path.join(d, "moving.gif")
        Image.new("P", (60, 90), 1).save(gif, save_all=True, append_images=[Image.new("P", (60, 90), 2)], duration=50)
        got = read("Capsule", gif)
        ok("an animated GIF goes as its first frame, written as a PNG", got[0] is not None
           and getattr(got[0], "n_frames", 1) == 1 and got[1] == "capsule.png", got[1:])
        got = read("Icon", animation(os.path.join(d, "moving-icon.png"), (64, 64), "PNG"))
        ok("an animated icon goes as its first frame", got[0] is not None and getattr(got[0], "n_frames", 1) == 1
           and got[1] == "icon.png")
        budget = Host()
        budget.STEAM_ART_MAX_FRAME_PIXELS = 3 * 60 * 90
        got = budget.read_steam_piece("Capsule", os.path.join(d, "moving-Capsule.png"))
        ok("frames past the budget: taken as the first frame, and said",
           got[0] is not None and getattr(got[0], "n_frames", 1) == 1 and got[2] == ""
           and "has 4 frames at 60 x 90, more than Rialto keeps, so Steam gets its first frame." in got[3], got[1:])

        # 2f. the .ico, as given
        ico = os.path.join(d, "game.ico")
        plain_ico = ico_bytes([(256, 256), (48, 48), (16, 16)])
        with open(ico, "wb") as fh:
            fh.write(plain_ico)
        got = read("Icon", ico)
        ok("an .ico goes as icon.ico", got[0] is not None and got[1:] == ("icon.ico", "", ""), got[1:])
        made_ico = host._ico_as_given(ico)

        def ico_pixels(data):
            """{size: the picture's RGBA bytes} for every size in an .ico."""
            out = {}
            with Image.open(io.BytesIO(data)) as icon:
                for size in sorted(icon.info["sizes"]):
                    icon.size = size
                    icon.load()
                    out[size] = icon.convert("RGBA").tobytes()
            return out
        ok("made again with every size in it, pixel for pixel", made_ico is not None
           and ico_pixels(made_ico) == ico_pixels(plain_ico) and len(ico_pixels(made_ico)) == 3)
        stuffed = os.path.join(d, "stuffed.ico")
        with open(stuffed, "wb") as fh:
            fh.write(plain_ico + b"PK\x03\x04 a zip riding on the end" * 50)
        got = read("Icon", stuffed)
        cleaned = host._ico_as_given(stuffed)
        ok("an .ico with data after its pictures is taken, and the data is left out",
           got[0] is not None and cleaned == made_ico, len(cleaned or b""))
        count = struct.unpack_from("<H", plain_ico, 4)[0]
        first_at = struct.unpack_from("<I", plain_ico, 6 + 12)[0]
        gap = bytearray(plain_ico[:6 + 16 * count]) + b"JUNK" * 8 + plain_ico[6 + 16 * count:]
        for index in range(count):
            at = struct.unpack_from("<I", gap, 6 + 16 * index + 12)[0]
            struct.pack_into("<I", gap, 6 + 16 * index + 12, at + 32)
        gapped = os.path.join(d, "gapped.ico")
        with open(gapped, "wb") as fh:
            fh.write(bytes(gap))
        ok("and data between the table and the pictures too", host._ico_as_given(gapped) == made_ico
           and first_at == 6 + 16 * count)
        broken = bytearray(plain_ico)
        struct.pack_into("<I", broken, 6 + 12, len(plain_ico) + 10)  # first picture said to lie past the end
        bad = os.path.join(d, "broken.ico")
        with open(bad, "wb") as fh:
            fh.write(bytes(broken))
        got = read("Icon", bad)
        ok("an .ico whose table points past its end is refused", got[0] is None and got[2] != "", got[2])
        ok("and _ico_as_given says None for it", host._ico_as_given(bad) is None)

        # 2g. the refusals about the file, which stay
        fake = os.path.join(d, "notapicture.png")
        with open(fake, "wb") as fh:
            fh.write(b"MZ this is a program, not a picture")
        got = read("Capsule", fake)
        ok("a file named .png that is not a picture is refused", got[0] is None and "not a picture" in got[2], got[2])
        ppm = picture(os.path.join(d, "capsule.ppm"), (600, 900), fmt="PPM")
        got = read("Capsule", ppm)
        ok("a picture in a format Steam has no use for is refused, and the formats are said",
           got[0] is None and "is a PPM file" in got[2] and "a PNG, a JPG or a WebP" in got[2], got[2])
        empty = os.path.join(d, "empty.png")
        open(empty, "wb").close()
        ok("an empty file is refused", "empty" in read("Capsule", empty)[2])
        ok("a file that is not there is refused", "cannot find" in read("Capsule", os.path.join(d, "gone.png"))[2])
        ok("a folder is not a file", "cannot find" in read("Capsule", d)[2])
        heavy = os.path.join(d, "heavy.png")
        with open(heavy, "wb") as fh:
            fh.truncate(64 * 1024 * 1024 + 1)
        ok("a file over 64 MB is refused before it is opened", "too large" in read("Hero", heavy)[2])
        os.remove(heavy)
        huge = os.path.join(d, "huge.png")
        Image.new("1", (8000, 6000)).save(huge)
        got = read("Hero", huge)
        ok("a picture past 40 million pixels is refused before it is decoded",
           got[0] is None and "is 8000 x 6000, too large" in got[2], got[2])
        # Windows will not hold a control character in a name; a format sign and a direction mark it will.
        hostile = picture(os.path.join(d, "%s %d \u202ecap.png"), (300, 300))
        got = read("Capsule", hostile)
        ok("a hostile name is said as it is, never read as a format",
           got[0] is not None and got[3].startswith("%s %d \u202ecap.png is 300 x 300"), got[3])
        ok("a control character from a profile's path is said without it",
           "\x01" not in read("Capsule", os.path.join(d, "gone\x01.png"))[2])
        reader = method_source("read_steam_piece")
        ok("nothing in the reader refuses for size, shape, softness or transparency",
           not re.search(r"under half|would look soft|does not crop|needs one|is a square:", reader))
        print()

        # ---------------------------------------------------------------- 3
        print("3. staged on the disc in menu/steam/")
        bg = picture(os.path.join(d, "background.jpg"), (1920, 1080), color=(30, 90, 160))
        game_logo = picture(os.path.join(d, "game_logo.png"), (800, 300), mode="RGBA", color=(250, 250, 250),
                            alpha_hole=True)

        def staged(host_, menu=None):
            menu = menu or tempfile.mkdtemp(dir=work)
            host_.stage_steam_art(menu)
            folder = os.path.join(menu, "steam")
            if not os.path.isdir(folder):
                return {}, host_.log, folder
            sizes = {}
            for name in os.listdir(folder):
                with Image.open(os.path.join(folder, name)) as im:
                    sizes[name] = (im.format, im.size, im.convert("RGB").getpixel((im.size[0] // 2, im.size[1] // 2)))
            return sizes, host_.log, folder

        h = Host()
        h.bg_path_var.set(bg)
        h.logo_path_var.set(game_logo)
        got, log, _f = staged(h)
        ok("nothing given: the four pieces composed as before",
           sorted(got) == ["capsule.png", "hero.png", "logo.png", "wide.png"], sorted(got))
        ok("at Steam's sizes", got.get("capsule.png", (0, 0))[1] == (600, 900) and got.get("wide.png", (0, 0))[1]
           == (920, 430) and got.get("hero.png", (0, 0))[1] == (3840, 1240) and got.get("logo.png", (0, 0))[1]
           == (800, 300), got)
        ok("all PNG", all(v[0] == "PNG" for v in got.values()))
        ok("and said", any(m.startswith("✅ Steam library art, made by Rialto: Library Capsule, Library Header, "
                                       "Library Hero, Library Logo") for m in log), log)

        h = Host()
        h.bg_path_var.set(bg)
        h.logo_path_var.set(game_logo)
        h.steam_capsule_var.set(picture(os.path.join(d, "mine.jpg"), (1200, 1800), color=(0, 200, 0)))
        h.steam_hero_var.set(picture(os.path.join(d, "mine-hero.png"), (1920, 620), color=(200, 0, 200)))
        h.steam_header_var.set(picture(os.path.join(d, "mine-header.png"), (460, 215), color=(0, 0, 220)))
        h.steam_icon_var.set(stuffed)
        got, log, folder = staged(h)
        ok("the developer's JPG Library Capsule goes as capsule.jpg, a JPG at its own 1200 x 1800",
           got.get("capsule.jpg", ("",))[0] == "JPEG" and got["capsule.jpg"][1] == (1200, 1800)
           and got["capsule.jpg"][2][1] > 150 and got["capsule.jpg"][2][0] < 50, got.get("capsule.jpg"))
        ok("and no composed capsule.png beside it", "capsule.png" not in got, sorted(got))
        ok("the half-size Library Hero goes at its own 1920 x 620",
           got.get("hero.png", (0, (0, 0), (0,)))[1:] == ((1920, 620), (200, 0, 200)), got.get("hero.png"))
        ok("the older 460 x 215 Library Header goes at its own size",
           got.get("wide.png", (0, (0, 0)))[1] == (460, 215), got.get("wide.png"))
        ok("the rest composed: the Library Logo from the Game Logo", got.get("logo.png", (0, (0, 0)))[1] == (800, 300))
        with open(os.path.join(folder, "icon.ico"), "rb") as fh:
            ok("the Shortcut Icon staged as icon.ico, its pictures made again and the riding data left out",
               fh.read() == made_ico)
        ok("said: whose is whose", any("yours: Library Capsule, Library Header, Library Hero, Shortcut Icon" in m
                                       and "made by Rialto: Library Logo" in m for m in log), log)
        ok("nothing said about scaling", not any("scales" in m for m in log), log)

        h = Host()
        h.bg_path_var.set(bg)
        h.steam_capsule_var.set(os.path.join(d, "moving-Capsule.png"))
        h.steam_header_var.set(os.path.join(d, "moving-Header.webp"))
        h.steam_logo_var.set(os.path.join(d, "moving-Logo.webp"))
        got, log, folder = staged(h)
        fmt, frames = frames_of(os.path.join(folder, "capsule.png"))
        ok("an animated PNG capsule is staged with every frame, each with its own timing",
           fmt == "PNG" and [t for t, _c in frames] == [40, 80, 120, 160]
           and len({c for _t, c in frames}) == 4, frames)
        fmt, frames = frames_of(os.path.join(folder, "wide.png"))
        ok("an animated WebP header is staged as a WebP under wide.png, every frame kept",
           fmt == "WEBP" and len(frames) == 4, (fmt, frames))
        fmt, frames = frames_of(os.path.join(folder, "logo.png"))
        ok("an animated WebP logo too", fmt == "WEBP" and len(frames) == 4, (fmt, frames))
        ok("and the composed art is made with the logo's first frame (no Game Logo)",
           got.get("hero.png", ("", (0, 0)))[1] == (3840, 1240) and any("made by Rialto: Library Hero" in m for m in log),
           log)

        h = Host()
        h.bg_path_var.set(bg)
        h.steam_header_var.set(picture(os.path.join(d, "header-square.png"), (900, 900)))
        h.steam_icon_var.set(picture(os.path.join(d, "icon-odd.png"), (300, 200), mode="RGBA"))
        h.steam_hero_var.set(fake)
        got, log, _f = staged(h)
        ok("a square Library Header is taken at 900 x 900", got.get("wide.png", (0, (0, 0)))[1] == (900, 900))
        ok("and the log gives its size beside Steam's, the build going on",
           "ℹ️ Library Header: header-square.png is 900 x 900; Steam's Library Header is 920 x 430." in log, log)
        ok("a non-square icon is staged too", got.get("icon.png", ("", (0, 0)))[1] == (300, 200), sorted(got))
        ok("a refused piece is composed instead", got.get("hero.png", ("", (0, 0)))[1] == (3840, 1240))
        ok("and the log says why, and what happens",
           any("notapicture.png is not a picture Rialto can read" in m and "Rialto makes the Library Hero instead." in m
               for m in log), log)

        broken_anim = os.path.join(d, "broken-anim.png")
        with open(os.path.join(d, "moving-Hero.png"), "rb") as fh:
            whole = fh.read()
        with open(broken_anim, "wb") as fh:
            fh.write(whole[:len(whole) * 3 // 5])
        h = Host()
        h.bg_path_var.set(bg)
        h.steam_hero_var.set(broken_anim)
        h.steam_capsule_var.set(os.path.join(d, "capsule.png"))
        first = read("Hero", broken_anim)
        got, log, folder = staged(h)
        ok("an animation that breaks partway passes the first look", first[0] is not None, first[1:])
        ok("but cannot be written: the log says so and the Library Hero is composed instead",
           got.get("hero.png", ("", (0, 0)))[1] == (3840, 1240) and any(
               "Rialto could not write broken-anim.png for the Library Hero. Rialto makes the Library Hero instead."
               in m for m in log), log)
        ok("and the rest of the art still goes on the disc", got.get("capsule.png", ("", (0, 0)))[1] == (600, 900)
           and "wide.png" in got and any(m.startswith("✅ Steam library art, yours: Library Capsule;") for m in log), log)

        menu = tempfile.mkdtemp(dir=work)
        os.makedirs(os.path.join(menu, "steam"))
        for stale in ("capsule.png", "hero.jpg", "icon.png"):
            picture(os.path.join(menu, "steam", stale), (10, 10))
        h = Host()
        h.bg_path_var.set(bg)
        h.steam_capsule_var.set(os.path.join(d, "big.jpg"))
        h.steam_icon_var.set(ico)
        got, log, _f = staged(h, menu)
        ok("a folder left by an earlier build: only this build's files are there",
           sorted(got) == ["capsule.jpg", "hero.png", "icon.ico", "wide.png"], sorted(got))

        h = Host()
        h.steam_capsule_var.set(os.path.join(d, "capsule.png"))
        h.steam_logo_var.set(os.path.join(d, "logo.png"))
        got, log, _f = staged(h)
        ok("no background or Game Logo: the developer's pieces still go on the disc, and the Library Logo "
           "is laid on the composed ones", sorted(got) == ["capsule.png", "hero.png", "logo.png", "wide.png"]
           and got["logo.png"][1] == (640, 400), sorted(got))

        h = Host()
        h.steam_hero_var.set(fake)
        got, log, _f = staged(h)
        ok("only a refused piece and no Step 4 art: no steam folder, the log says why, nothing else",
           got == {} and len(log) == 1 and "Rialto makes the Library Hero instead." in log[0], log)

        h = Host()
        got, log, _f = staged(h)
        ok("nothing given and no Step 4 art: no steam folder, as before", got == {} and not log, log)
        print()

        # ---------------------------------------------------------------- 4
        print("4. kept: the profile, the startup profile, the session, Restore Defaults, a moved game folder")
        h = Host()
        h.steam_capsule_var.set("C:/art/capsule.png")
        h.steam_icon_var.set("C:/art/icon.ico")
        paths = h.steam_art_paths()
        ok("written as SteamArt {Capsule, Header, Hero, Logo, Icon}",
           paths == {"Capsule": "C:/art/capsule.png", "Header": "", "Hero": "", "Logo": "", "Icon": "C:/art/icon.ico"},
           paths)
        back = Host()
        back.set_steam_art(json.loads(json.dumps(paths)))
        ok("and read back the same", back.steam_art_paths() == paths)
        back.set_steam_art({"Capsule": ["not", "a", "path"], "Hero": 7, "Logo": {"x": 1},
                            "Header": "C:/a\x00b\nc.png", "Other": "C:/x.png"})
        ok("a hostile SteamArt: only strings, control characters out, unknown keys dropped",
           back.steam_art_paths() == {"Capsule": "", "Header": "C:/abc.png", "Hero": "", "Logo": "", "Icon": ""},
           back.steam_art_paths())
        for stored in (None, "C:/x.png", ["C:/x.png"], 5):
            back.set_steam_art(stored)
            ok("SteamArt as %r: every row empty" % (stored,), set(back.steam_art_paths().values()) == {""})
        back.set_steam_art({})
        ok("Restore Defaults' empty SteamArt clears every row", set(back.steam_art_paths().values()) == {""})

        save_src = method_source("current_profile_data")
        ok("Save Profile and the Build Queue's snapshot write it",
           'profile_data["SteamArt"] = self.steam_art_paths()' in save_src)
        # Load Profile and the start put a profile on the form through one list (readiness, 4 Nov).
        ok("Load Profile reads it", 'self.set_steam_art(profile_data.get("SteamArt"))' in method_source("put_profile_on_form")
           and "self.put_profile_on_form(profile_data)" in method_source("apply_profile_file"))
        ok("the startup profile carries it, beside the Step 4 art",
           "self.put_profile_on_form(profile_data, at_start=True)" in method_source("load_last_used_profile"))
        ok("the last session too", 'session_data["SteamArt"] = self.steam_art_paths()' in method_source("save_last_session")
           and 'self.set_steam_art(value)' in method_source("load_last_session"))
        ok("Restore Defaults empties it", "self.set_steam_art({})" in method_source("restore_page"))
        ok("a moved game folder brings it along", all(
            '("%s", "%s")' % (attr, name) in SRC for _k, attr, name, *_r in host.STEAM_ART_PIECES))
        print()

        # ---------------------------------------------------------------- 5
        print("5. Disc Extras: the rows under the tick box, the tooltips, the Help Guide")
        extras = method_source("configure_disc_extras")
        steam_part = extras[extras.index("# --- Steam ---"):]
        ok("Steam has its own column", 'col, wrap = steam_col, 330' in extras and 'section("Steam")' in steam_part)
        ok("one row for each piece, named as Steam names it, each with a Browse",
           'path_row(steam_rows, "%s:" % name, var, steam_tips[key], pick_steam_piece(key, var, name),' in steam_part)
        row_maker = extras[extras.index("def path_row("):extras.index("def pick_dir(")]
        ok("every Browse in Disc Extras has a tooltip, a folder's by default",
           "ToolTip(browse, browse_tip)" in row_maker
           and 'browse_tip="Pick the folder from your files."' in row_maker, row_maker)
        kinds_at = steam_part.index("steam_kinds = ") + len("steam_kinds = ")
        kinds = ast.literal_eval(steam_part[kinds_at:steam_part.index("\n", kinds_at)].strip())
        ok("each Steam piece's Browse says what to pick, in the kinds its file picker offers",
           '"Pick the %s, %s, from your files." % (name, steam_kinds.get(key, "a PNG, a JPG or a WebP"))' in steam_part
           and kinds == {"Logo": "a PNG or a WebP", "Icon": "an .ico or a .png"}
           and '"Logo": [("PNG or WebP", "*.png;*.webp")]' in steam_part
           and '"Icon": [("Icon or PNG", "*.ico;*.png")]' in steam_part
           and '[("PNG, JPG or WebP", "*.png;*.jpg;*.jpeg;*.webp")]' in steam_part
           and '[("All Files", "*.*")]' in steam_part, kinds)
        browse_words = ["Pick the %s, %s, from your files." % (name, kinds.get(key, "a PNG, a JPG or a WebP"))
                        for key, _attr, name, *_r in host.STEAM_ART_PIECES]
        ok("as plain words: the Library Hero's reads 'Pick the Library Hero, a PNG, a JPG or a WebP, from your files.'",
           "Pick the Library Hero, a PNG, a JPG or a WebP, from your files." in browse_words
           and "Pick the Shortcut Icon, an .ico or a .png, from your files." in browse_words, browse_words)
        ok("the rows show only while the box is ticked",
           "steam_check.configure(command=lambda: (show_steam_rows(), self.refresh_disc_meter()))" in steam_part
           and "steam_rows.pack_forget()" in steam_part)
        ok("the window is sized with the rows showing, so ticking later needs no more room",
           steam_part.index("holds = dialog.winfo_reqheight()") < steam_part.index("show_steam_rows()\n        self.fit")
           and "self.fit_dialog_to_screen(dialog, self.DISC_EXTRAS_WIDTH, holds)" in steam_part)
        ok("Browse opens Windows' file picker and checks the file before it is kept",
           "filedialog.askopenfilename(" in steam_part and steam_part.index("self.read_steam_piece(key, path)")
           < steam_part.index("var.set(path)") and 'self.show_centered_popup("Steam cannot use this %s" % name, problem)'
           in steam_part)
        tips = ast.literal_eval(steam_part[steam_part.index("steam_tips = ") + len("steam_tips = "):
                                           steam_part.index("\n\n", steam_part.index("steam_tips = "))].strip())
        ok("a tooltip for each piece", sorted(tips) == sorted(pieces))
        for key, best, others in (("Capsule", "600 x 900", ["300 x 450"]), ("Header", "920 x 430", ["460 x 215"]),
                                  ("Hero", "3840 x 1240", ["1920 x 620"]),
                                  ("Logo", "1280 wide or 720 tall", ["1280 x 720", "640 x 360"]),
                                  ("Icon", "256 x 256 or 512 x 512", ["32 x 32"])):
            tip = tips[key]
            ok("the %s's tooltip gives Steam's size first, then the others taken too" % pieces[key][1],
               ("Steam's size is " + best) in tip and all(tip.index(best) < tip.index(o) for o in others)
               and "other size" in tip and "taken as they are" in tip, tip)
        ok("the formats", all(f in tips[k] for k, f in (("Capsule", "A PNG, a JPG or a WebP"),
                                                           ("Header", "A PNG, a JPG or a WebP"),
                                                           ("Hero", "A PNG, a JPG or a WebP"),
                                                           ("Logo", "a PNG with a transparent background"),
                                                           ("Logo", "A WebP works too"),
                                                           ("Icon", "an .ico or a .png"))))
        ok("an animated PNG or WebP keeps up to 1,000 of its frames, said for the four grid pieces",
           all("an animated PNG or WebP keeps up to 1,000 of its frames" in tips[k] and "Steam gets its first frame"
               in tips[k] for k in ("Capsule", "Header", "Hero", "Logo"))
           and "250 at 3840 x 1240" in tips["Hero"] and "animated" not in tips["Icon"])
        ok("where Steam shows it", all(w in tips[k] for k, w in (
            ("Capsule", "Steam library"), ("Header", "Recent Games"), ("Hero", "game's page"),
            ("Logo", "over the Library Hero"), ("Icon", "Steam library's list"))))
        ok("the capsule's tooltip says card art", "card art" in tips["Capsule"])
        ok("and what an empty row does", all("Leave it empty" in t for t in tips.values()))
        words = " ".join(tips.values())
        ok("nothing in them says scaled or refused", not re.search(r"scaled|refused|is scaled|cropped by Rialto", words))
        ok("plain: no em dash, no British spelling, no We The Indies",
           "\u2014" not in words and not re.search(r"colour|centre|behaviour", words) and "Indies" not in words)

        guide = open(os.path.join(os.path.dirname(RIALTO), "docs", "rialto-guide.html"), encoding="utf-8").read()
        for _key, _attr, name, *_r in host.STEAM_ART_PIECES:
            ok("the Help Guide has a row for the %s" % name, "<tr><td>%s</td>" % name in guide)
        steam_guide = guide[guide.index("<h3>Steam</h3>"):guide.index("<h3>Mac and Linux</h3>")]
        ok("and its Steam part gives each piece's sizes as the tooltips do", all(s in steam_guide for s in (
            "600 x 900", "300 x 450", "920 x 430", "460 x 215", "3840 x 1240", "1920 x 620", "640 x 360", "32 x 32")))
        ok("and says nothing is refused for its size or shape any more",
           "refused" not in steam_guide.split("<table>")[0].replace("A file Rialto cannot read", "")
           and "goes on" in steam_guide, steam_guide[:600])
        print()

        # ---------------------------------------------------------------- 6
        print("6. the disc meter counts each piece as it is staged")
        meter = method_source("refresh_disc_meter")
        ok("only when Add to Steam is ticked", "self.steam_art_paths() if self.steam_button_var.get() else None"
           in meter)
        ok("weighed on the worker thread, with what Rialto composes from, in menu/ on the disc root and in the "
           "installer's copy", "steam_bytes = self.steam_art_bytes(steam, *steam_sources)" in meter.split(
               "def measure():")[1] and "steam_sources = self.steam_art_sources()" in meter
           and "menu_extra + steam_bytes" in meter and "menu_inside + steam_bytes" in meter)
        ok("and not a second time in menu_staging_bytes", "self.steam_art_bytes(" not in
           method_source("menu_staging_bytes"))
        ok("picking a Game Logo weighs again, since the Steam art Rialto makes comes from it",
           "self.refresh_disc_meter()" in method_source("browse_logo"))

        class Meter(load_builder(ART + ["STEAM_ART_ALLOWANCE", "steam_art_bytes", "_steam_still_possible",
                                    "_steam_weighed", "steam_piece_bytes", "steam_logo_bytes"])):
            reads = 0

            def read_steam_piece(self, key, path):
                self.reads += 1
                return super().read_steam_piece(key, path)

        m = Meter()
        ok("nothing given, with a background: the composed pieces' allowance, and no Shortcut Icon",
           m.steam_art_bytes(m.steam_art_paths(), bg) == sum(m.STEAM_ART_ALLOWANCE.values())
           and sorted(m.STEAM_ART_ALLOWANCE) == ["Capsule", "Header", "Hero"])
        ok("and nothing at all with nothing to compose from", m.steam_art_bytes(m.steam_art_paths()) == 0)

        # Each piece in a form the build writes again: a JPG at a low quality (written at 95), a still WebP
        # (written as a PNG), an animated PNG and an animated WebP (frame by frame), an .ico with data riding
        # after its pictures (left out). Noise, so no two encoders land on the same size by chance.
        import random
        rng = random.Random(20261104)

        def noisy(size):
            return Image.frombytes("RGB", size, rng.randbytes(size[0] * size[1] * 3))
        meter_art = os.path.join(work, "meter-art")
        os.makedirs(meter_art)
        given = {"Capsule": os.path.join(meter_art, "capsule.jpg"), "Header": os.path.join(meter_art, "header.webp"),
                 "Hero": os.path.join(meter_art, "hero.png"), "Logo": os.path.join(meter_art, "logo.webp"),
                 "Icon": os.path.join(meter_art, "icon.ico")}
        noisy((600, 900)).save(given["Capsule"], "JPEG", quality=30)
        noisy((460, 215)).save(given["Header"], "WEBP", quality=60)
        hero = [noisy((480, 155)) for _ in range(3)]
        hero[0].save(given["Hero"], "PNG", save_all=True, append_images=hero[1:], duration=[50, 90, 130], loop=0)
        logo = [noisy((320, 180)).convert("RGBA") for _ in range(3)]
        logo[0].save(given["Logo"], "WEBP", save_all=True, append_images=logo[1:], duration=[60, 60, 200], loop=0)
        with open(given["Icon"], "wb") as fh:
            fh.write(ico_bytes([(32, 32), (256, 256)]) + b"riding along" * 500)
        for key, path in given.items():
            getattr(m, next(a for k, a, *_r in m.STEAM_ART_PIECES if k == key)).set(path)
        counted = m.steam_art_bytes(m.steam_art_paths())
        menu = tempfile.mkdtemp(dir=work)
        m.stage_steam_art(menu)
        folder = os.path.join(menu, "steam")
        written = {name: os.path.getsize(os.path.join(folder, name)) for name in os.listdir(folder)}
        ok("every piece given: the five files the build writes", sorted(written) == [
            "capsule.jpg", "hero.png", "icon.ico", "logo.png", "wide.png"], sorted(written))
        ok("the meter counts what they weigh, %s bytes" % "{:,}".format(sum(written.values())),
           counted == sum(written.values()), (counted, written))
        sources = sum(os.path.getsize(p) for p in given.values())
        ok("which is not what the files given weigh (%s bytes)" % "{:,}".format(sources), counted != sources)
        for key, name in (("Capsule", "capsule.jpg"), ("Header", "wide.png"), ("Icon", "icon.ico")):
            ok("the %s as the build writes it, not as given" % key,
               m.steam_piece_bytes(key, given[key]) == written[name] != os.path.getsize(given[key]),
               (m.steam_piece_bytes(key, given[key]), written[name], os.path.getsize(given[key])))

        reads = m.reads
        m.steam_art_bytes(m.steam_art_paths())
        ok("drawn again, no file is read again", m.reads == reads, (m.reads, reads))
        noisy((300, 450)).save(given["Capsule"], "JPEG", quality=90)
        later = os.stat(given["Capsule"]).st_mtime_ns + 10 ** 9
        os.utime(given["Capsule"], ns=(later, later))
        m.steam_art_bytes(m.steam_art_paths())
        ok("a file changed is weighed again", m.reads == reads + 1, (m.reads, reads))

        big = os.path.join(meter_art, "big-hero.png")
        with open(big, "wb") as fh:
            fh.write(b"\0" * (30 * 1024 * 1024))
        m.steam_hero_var.set(big)
        m.steam_icon_var.set(os.path.join(meter_art, "not-there.ico"))
        ok("a piece the build cannot take counts as the one it makes: the Hero at its allowance, no icon",
           m.steam_piece_bytes("Hero", big) is None and m.steam_art_bytes(m.steam_art_paths())
           == m.steam_piece_bytes("Capsule", given["Capsule"]) + written["wide.png"] + written["logo.png"]
           + m.STEAM_ART_ALLOWANCE["Hero"])
        print()

        # ---------------------------------------------------------------- 7
        print("7. the disc menu's ADD TO STEAM")
        menu_steam(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll Steam art checks passed.")
    return 0


def menu_steam(work):
    sys.path.insert(0, HERE)
    import test_steam_shortcuts as shortcuts  # the stub disc menu with the real Steam methods on it

    def disc(art):
        tmp = tempfile.mkdtemp(dir=work)
        game_dir, exe = shortcuts.make_disc(tmp, with_art=False)
        open(os.path.join(game_dir, "game_icon.ico"), "wb").write(b"\0\0\1\0")
        steam = os.path.join(game_dir, "menu", "steam")
        os.makedirs(steam, exist_ok=True)
        for name in art:
            open(os.path.join(steam, name), "wb").write(("art " + name).encode())
        vdf = os.path.join(tmp, "Steam", "userdata", "123456789", "config", "shortcuts.vdf")
        os.makedirs(os.path.dirname(vdf), exist_ok=True)
        menu = shortcuts.make_menu(tmp, game_dir, [vdf], resolved_exe=exe)
        return menu, game_dir, exe, vdf

    def icon_field(vdf):
        data = open(vdf, "rb").read()
        at = data.index(b"\x01icon\x00") + len(b"\x01icon\x00")
        return data[at:data.index(b"\x00", at)].decode("utf-8")

    def copied(grid, target, source):
        path = os.path.join(grid, target)
        return os.path.isfile(path) and open(path, "rb").read() == ("art " + source).encode()

    # A disc pressed before 1.5.2's any-size art: every piece under its fixed .png name.
    menu, game_dir, exe, vdf = disc(["capsule.png", "wide.png", "hero.png", "logo.png", "icon.png"])
    menu.add_to_steam()
    grid = os.path.join(os.path.dirname(vdf), "grid")
    appid = menu._steam_appid("Mock Game", exe)
    ok("added", menu.said[-1][0] == "Added to Steam", menu.said)
    for source, target in (("capsule.png", "%dp.png"), ("wide.png", "%d.png"), ("hero.png", "%d_hero.png"),
                           ("logo.png", "%d_logo.png"), ("icon.png", "%d_icon.png")):
        ok("an old disc's %s copied to grid/%s" % (source, target % appid), copied(grid, target % appid, source))
    ok("the shortcut's icon field names the copy in the grid folder, not the disc",
       os.path.normcase(icon_field(vdf)) == os.path.normcase(os.path.join(grid, "%d_icon.png" % appid)), icon_field(vdf))
    place = os.path.join(grid, "%d.json" % appid)
    ok("the logo brings the place file Steam needs to show it, bottom left",
       os.path.isfile(place) and json.load(open(place))["logoPosition"]["pinnedPosition"] == "BottomLeft")
    data = open(vdf, "rb").read()
    at = data.index(b"\x02appid\x00") + len(b"\x02appid\x00")
    ok("the appid in shortcuts.vdf is the number the art is named after, stored as Steam's signed int32 is",
       struct.unpack("<I", data[at:at + 4])[0] == appid and struct.unpack("<i", data[at:at + 4])[0] == appid - 2 ** 32)

    # A disc with JPGs: each copied under Steam's name with .jpg, and this shortcut's old .png copy taken away.
    menu, game_dir, exe, vdf = disc(["capsule.jpg", "wide.jpg", "hero.jpg", "logo.png"])
    grid = os.path.join(os.path.dirname(vdf), "grid")
    appid = menu._steam_appid("Mock Game", exe)
    os.makedirs(grid, exist_ok=True)
    for left in ("%dp.png", "%d_hero.jpeg", "%d.png"):
        open(os.path.join(grid, left % appid), "wb").write(b"an earlier ADD TO STEAM")
    open(os.path.join(grid, "999p.png"), "wb").write(b"another game's capsule")
    menu.add_to_steam()
    for source, target in (("capsule.jpg", "%dp.jpg"), ("wide.jpg", "%d.jpg"), ("hero.jpg", "%d_hero.jpg"),
                           ("logo.png", "%d_logo.png")):
        ok("%s copied to grid/%s" % (source, target % appid), copied(grid, target % appid, source))
    ok("this shortcut's earlier .png and .jpeg copies are gone, so only the disc's own art is there",
       not any(os.path.exists(os.path.join(grid, left % appid)) for left in ("%dp.png", "%d_hero.jpeg", "%d.png")))
    ok("another game's art in the grid folder is left alone", os.path.isfile(os.path.join(grid, "999p.png")))

    # A crafted folder with both: the .png is taken, once.
    menu, game_dir, exe, vdf = disc(["capsule.png", "capsule.jpg"])
    menu.add_to_steam()
    grid = os.path.join(os.path.dirname(vdf), "grid")
    appid = menu._steam_appid("Mock Game", exe)
    ok("a disc carrying both a capsule.png and a capsule.jpg: the .png goes, and only it",
       copied(grid, "%dp.png" % appid, "capsule.png") and not os.path.exists(os.path.join(grid, "%dp.jpg" % appid)))

    menu, game_dir, exe, vdf = disc(["capsule.png", "icon.ico"])
    grid = os.path.join(os.path.dirname(vdf), "grid")
    os.makedirs(grid, exist_ok=True)
    appid = menu._steam_appid("Mock Game", exe)
    menu.add_to_steam()
    ok("an .ico goes as <appid>_icon.ico", os.path.isfile(os.path.join(grid, "%d_icon.ico" % appid)))
    ok("and the field names it", icon_field(vdf).endswith("%d_icon.ico" % appid), icon_field(vdf))
    ok("no logo on the disc: no place file", not os.path.exists(os.path.join(grid, "%d.json" % appid)))

    menu, game_dir, exe, vdf = disc(["capsule.png", "wide.png", "hero.png", "logo.png"])
    grid = os.path.join(os.path.dirname(vdf), "grid")
    appid = menu._steam_appid("Mock Game", exe)
    os.makedirs(grid, exist_ok=True)
    with open(os.path.join(grid, "%d.json" % appid), "w") as fh:
        fh.write('{"nVersion":1,"logoPosition":{"pinnedPosition":"CenterCenter"}}')
    menu.add_to_steam()
    ok("a disc with no Shortcut Icon: the field keeps the installed game_icon.ico, as before",
       os.path.normcase(icon_field(vdf)) == os.path.normcase(os.path.join(game_dir, "game_icon.ico")), icon_field(vdf))
    ok("a place the player already set is left alone",
       "CenterCenter" in open(os.path.join(grid, "%d.json" % appid)).read())

    menu, game_dir, exe, vdf = disc(["capsule.jpg"])
    open(os.path.join(game_dir, "menu", "steam", "capsule.jpg"), "wb").close()
    menu.add_to_steam()
    grid = os.path.join(os.path.dirname(vdf), "grid")
    ok("an empty staged file is not copied, and the shortcut is still added",
       menu.said[-1][0] == "Added to Steam" and not os.path.exists(os.path.join(grid, "%dp.jpg"
                                                                                % menu._steam_appid("Mock Game", exe))))

    menu, game_dir, exe, vdf = disc([])
    shutil.rmtree(os.path.join(game_dir, "menu", "steam"))
    menu.add_to_steam()
    grid = os.path.join(os.path.dirname(vdf), "grid")
    ok("a disc with no Steam art at all: added, nothing in the grid folder, the Game Icon in the field",
       menu.said[-1][0] == "Added to Steam" and not os.path.exists(grid)
       and icon_field(vdf).endswith("game_icon.ico"), (menu.said, icon_field(vdf)))

    menu, game_dir, exe, vdf = disc(["icon.png"])
    grid = os.path.join(os.path.dirname(vdf), "grid")
    appid = menu._steam_appid("Mock Game", exe)
    menu._write_vdf_atomically = lambda path, payload: False
    menu.add_to_steam()
    ok("the list cannot be written: the icon copied for it is taken back",
       not os.path.exists(os.path.join(grid, "%d_icon.png" % appid)) and menu.said[-1][0] == "Could not add to Steam")

    menu_src = shortcuts.menu_source(SRC)
    install = class_members("GameMenu", ["_install_steam_icon"], menu_src, ast.parse(menu_src))
    art = class_members("GameMenu", ["_install_steam_art"], menu_src, ast.parse(menu_src))
    ok("the menu reads no new menu_config key for the art: only the files Rialto staged",
       "menu_config" not in install and "menu_config" not in art)
    ok("and copies only under names it makes itself from the appid, never a name from the disc",
       "os.listdir" not in art and "glob" not in art)


if __name__ == "__main__":
    raise SystemExit(main())
