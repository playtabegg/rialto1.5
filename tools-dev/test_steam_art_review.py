"""The 1.5.2 review of the developer's Steam art: each finding, kept fixed.

  1. an animated PNG kept with a palette is written with every frame, its own
     colors and timing, not as one black frame
  2. a common animated Library Hero keeps its frames: 150 frames at 1920 x 620,
     250 at 3840 x 1240; the limit is 1,000 frames, and 250 at 3840 x 1240
  3. the disc meter: a measure a later refresh has overtaken leaves the meter
     alone, and two measures of one file write it once
  4. the meter counts only what the build writes: nothing when there is
     nothing to compose from, no Library Logo without a Game Logo, and the Game
     Logo as the build saves it again
  5. a JPG turned by its EXIF Orientation stands upright, and a picture in
     another color space is made sRGB
  6. an .ico whose table names one block many times is refused, quickly,
     however many entries it has, and the build goes on
  7. an .ico goes on the disc made again from the pictures in it: an entry
     holding a picture far past its size is refused, and bytes riding inside a
     block are left out
  8. an animation of more frames than Rialto keeps goes as its first frame,
     however small its canvas
  9. no color profile from the developer's file reaches menu/steam/
 10. an .ico's pictures are measured before any of them is decoded
 11. the log gives a picture's size beside Steam's, and nothing about how
     Steam shows it
 12. the Help Guide says what happens to a file Rialto cannot read or write
 13. the tooltips and the Help Guide give the frame limit the code keeps
 14. an animated GIF is said to go as its first frame
 15. the comment above STEAM_ART_FORMATS says what the code does with a WebP

The real methods are pulled out of Rialto.pyw by AST, as test_steam_art.py
does, and run against temp folders. No window is opened.

Usage: python test_steam_art_review.py [path-to-Rialto.pyw]
"""
import io
import os
import shutil
import struct
import sys
import tempfile
import textwrap
import threading
import time
import warnings
import zlib

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_steam_art as tsa  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

SRC, RIALTO = tsa.SRC, tsa.RIALTO
failures = []
MB = 1024 * 1024


def ok(label, cond, detail=""):
    print("  [%s] %s%s" % ("OK  " if cond else "FAIL", label, (" -> " + ascii(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(label)


def trying(label, run):
    """Run one part; a part that raises is a failure, said, and the rest still run."""
    start = time.time()
    try:
        run()
        print("  (%s: %.1f s)" % (label, time.time() - start))
    except Exception as e:
        ok(label + " (raised)", False, "%s: %s" % (type(e).__name__, e))


def present(*names):
    """The names of these that RialtoApp has, so a part runs on an older Rialto.pyw and says what is missing."""
    cls = next(n for n in tsa.ast.walk(tsa.TREE) if isinstance(n, tsa.ast.ClassDef) and n.name == "RialtoApp")
    have = {item.name for item in cls.body if isinstance(item, tsa.ast.FunctionDef)}
    have |= {getattr(item.targets[0], "id", "") for item in cls.body if isinstance(item, tsa.ast.Assign)}
    return [name for name in names if name in have]


METER = present("STEAM_ART_ALLOWANCE", "steam_art_bytes", "steam_piece_bytes", "_steam_weighed",
                "steam_logo_bytes", "_steam_still_possible")


def builder(extra=()):
    names = list(dict.fromkeys(present(*tsa.ART) + present("STEAM_ART_MAX_FRAMES", "STEAM_ICO_MAX_ENTRIES", "STEAM_ICO_MAX_SIDE",
                                                 "STEAM_ICO_MAX_PIXELS", "_ico_pictures", "_write_apng",
                                                 "_steam_frame", "_steam_turn", "_steam_game_logo") + list(extra)))
    return tsa.load_builder(names)


def frames_of(path):
    """(format, [(duration, center color), ...], info keys of frame 0) for a staged file."""
    with Image.open(path) as im:
        keys = sorted(im.info)
        out = []
        for index in range(getattr(im, "n_frames", 1)):
            im.seek(index)
            im.load()
            out.append((im.info.get("duration"), im.convert("RGB").getpixel((im.size[0] // 2, im.size[1] // 2))))
        return im.format, out, keys


def palette_apng(path, size, colors, timing):
    palette = [v for color in colors for v in color]
    frames = []
    for index in range(len(colors)):
        frame = Image.new("P", size, index)
        frame.putpalette(palette + [0] * (768 - len(palette)))
        frames.append(frame)
    frames[0].save(path, "PNG", save_all=True, append_images=frames[1:], duration=list(timing), loop=0)
    return path


def blinking(path, size, count, fmt):
    """An animation of `count` frames that alternate between two colors, so no two in a row are alike."""
    frames = [Image.new("RGB", size, (200, 30, 30) if i % 2 else (30, 30, 200)) for i in range(count)]
    frames[0].save(path, fmt, save_all=True, append_images=frames[1:], duration=33, loop=0)
    return path


def cheap_apng(path, size, count):
    """An animated PNG of `count` frames at `size` that is quick to make: a whole first frame, then one pixel each.

    Written here, not with Pillow's writer or Rialto's, so that a hero of hundreds of 3840 x 1240 frames
    takes no time to make; Rialto reads its frame count from its acTL as it would any other's.
    """
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    def idat(image):
        data, at, out = png_bytes(image), 8, []
        while at < len(data):
            length, kind = struct.unpack_from(">I4s", data, at)
            if kind in (b"IHDR", b"IDAT"):
                out.append((kind, data[at + 8:at + 8 + length]))
            at += 12 + length
        return out
    first = idat(Image.new("RGBA", size, (30, 30, 200, 255)))
    dot = [body for kind, body in idat(Image.new("RGBA", (1, 1), (200, 30, 30, 255))) if kind == b"IDAT"]
    out = [b"\x89PNG\r\n\x1a\n", chunk(b"IHDR", dict(first)[b"IHDR"]), chunk(b"acTL", struct.pack(">II", count, 0))]
    out.append(chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, size[0], size[1], 0, 0, 33, 1000, 0, 0)))
    out += [chunk(b"IDAT", body) for kind, body in first if kind == b"IDAT"]
    sequence = 1
    for _index in range(1, count):
        out.append(chunk(b"fcTL", struct.pack(">IIIIIHHBB", sequence, 1, 1, 0, 0, 33, 1000, 0, 0)))
        sequence += 1
        for body in dot:
            out.append(chunk(b"fdAT", struct.pack(">I", sequence) + body))
            sequence += 1
    out.append(chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(b"".join(out))
    return path


def swapped_profile():
    """An ICC display profile whose red and blue primaries are sRGB's blue and red: its red is sRGB's blue."""
    def s15(v):
        return struct.pack(">i", int(round(v * 65536)))

    def xyz(x, y, z):
        return b"XYZ " + b"\0" * 4 + s15(x) + s15(y) + s15(z)
    curve = b"curv" + b"\0" * 4 + struct.pack(">IH", 1, 0x0233) + b"\0\0"
    text = b"swapped primaries\0"
    desc = b"desc" + b"\0" * 4 + struct.pack(">I", len(text)) + text + b"\0" * 8 + b"\0\0\0" + b"\0" * 67
    tags = [(b"desc", desc), (b"wtpt", xyz(0.9642, 1.0, 0.8249)),
            (b"rXYZ", xyz(0.1431, 0.0606, 0.7141)), (b"gXYZ", xyz(0.3851, 0.7169, 0.0971)),
            (b"bXYZ", xyz(0.4361, 0.2225, 0.0139)), (b"rTRC", curve), (b"gTRC", curve), (b"bTRC", curve),
            (b"cprt", b"text" + b"\0" * 4 + b"none\0\0\0\0")]
    at = 128 + 4 + 12 * len(tags)
    table, body = b"", b""
    for sig, data in tags:
        while len(data) % 4:
            data += b"\0"
        table += sig + struct.pack(">II", at + len(body), len(data))
        body += data
    size = at + len(body)
    header = (struct.pack(">I", size) + b"\0" * 4 + struct.pack(">I", 0x02100000) + b"mntr" + b"RGB " + b"XYZ "
              + b"\0" * 12 + b"acsp" + b"\0" * 24 + struct.pack(">I", 0) + s15(0.9642) + s15(1.0) + s15(0.8249)
              + b"\0" * 48)
    return header + struct.pack(">I", len(tags)) + table + body


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def ico_of(blocks, declared=None):
    """An .ico of these blocks, each its own table entry, declared at 0 x 0 (256) unless said."""
    head = struct.pack("<HHH", 0, 1, len(blocks))
    table, body = b"", b""
    place = 6 + 16 * len(blocks)
    for index, block in enumerate(blocks):
        w, h = (declared or {}).get(index, (0, 0))
        table += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(block), place + len(body))
        body += block
    return head + table + body


def main():
    Host = builder()
    work = tempfile.mkdtemp(prefix="rialto_steam_review_")
    d = os.path.join(work, "art")
    os.makedirs(d)
    bg = tsa.picture(os.path.join(d, "background.jpg"), (1280, 720), color=(30, 90, 160))
    try:
        # ---------------------------------------------------------------- 1
        print("1. an animated PNG kept with a palette")

        def part1():
            colors = [(20, 200, 30), (200, 20, 30), (30, 30, 200), (220, 220, 20)]
            source = palette_apng(os.path.join(d, "palette.png"), (600, 900), colors, (40, 80, 120, 160))
            h = Host()
            h.bg_path_var.set(bg)
            h.steam_capsule_var.set(source)
            got = h.read_steam_piece("Capsule", source)
            ok("read: taken as capsule.png with its four frames", got[1:3] == ("capsule.png", "")
               and getattr(got[0], "n_frames", 1) == 4, got[1:])
            got[0].close()
            menu = tempfile.mkdtemp(dir=work)
            h.stage_steam_art(menu)
            fmt, frames, _keys = frames_of(os.path.join(menu, "steam", "capsule.png"))
            ok("staged with every frame, each with its own timing",
               fmt == "PNG" and [t for t, _c in frames] == [40, 80, 120, 160], frames)
            ok("and its own colors, not black", [c for _t, c in frames] == colors, frames)
            ok("said as the developer's", any("yours: Library Capsule" in m for m in h.log), h.log)
        trying("1", part1)
        print()

        # ---------------------------------------------------------------- 2 and 8
        print("2. a common animated Library Hero keeps its frames; 8. more than Rialto keeps goes as its first frame")

        def part2():
            h = Host()
            limit = getattr(h, "STEAM_ART_MAX_FRAMES", None)
            ok("the limit: 1,000 frames, and as many pixels as 1,000 frames at 1920 x 620, which is 250 at 3840 x 1240",
               limit == 1000 and h.STEAM_ART_MAX_FRAME_PIXELS == 1000 * 1920 * 620 == 250 * 3840 * 1240,
               (limit, h.STEAM_ART_MAX_FRAME_PIXELS))
            for fmt, size, count in (("WEBP", (1920, 620), 150), ("PNG", (1920, 620), 150),
                                     ("PNG", (3840, 1240), 250)):
                path = os.path.join(d, "hero-%d-%d.%s" % (size[0], count, fmt.lower()))
                if size == (3840, 1240):
                    cheap_apng(path, size, count)
                else:
                    blinking(path, size, count, fmt)
                got = h.read_steam_piece("Hero", path)
                ok("an animated %s Library Hero at %d x %d with %d frames keeps them all" % (fmt, size[0], size[1], count),
                   got[2] == "" and getattr(got[0], "n_frames", 1) == count and "first frame" not in got[3], got[1:])
                got[0].close()
            path = cheap_apng(os.path.join(d, "hero-over.png"), (3840, 1240), 251)
            got = h.read_steam_piece("Hero", path)
            ok("251 frames at 3840 x 1240 go as the first frame, and said",
               got[2] == "" and getattr(got[0], "n_frames", 1) == 1
               and "has 251 frames at 3840 x 1240, more than Rialto keeps, so Steam gets its first frame." in got[3],
               got[1:])
            got[0].close()
            tiny = cheap_apng(os.path.join(d, "tiny.png"), (2, 2), 1001)
            start = time.time()
            got = h.read_steam_piece("Capsule", tiny)
            ok("8. a 2 x 2 animated PNG of 1,001 frames goes as its first frame, and said",
               got[2] == "" and getattr(got[0], "n_frames", 1) == 1 and "has 1001 frames" in got[3], got[1:])
            ok("and is not read frame by frame to find that out", time.time() - start < 2, time.time() - start)
            got[0].close()
        trying("2", part2)

        def part2b():
            # Written as it is staged: 150 frames of 1920 x 620, one frame in memory at a time.
            h = Host()
            source = os.path.join(d, "hero-1920-150.webp")
            got = h.read_steam_piece("Hero", source)
            target = os.path.join(work, "hero-150.png")
            h._write_steam_piece(got[0], target)
            got[0].close()
            fmt, frames, _keys = frames_of(target)
            ok("and staged with all 150 frames", fmt == "WEBP" and len(frames) == 150, (fmt, len(frames)))
            source = os.path.join(d, "hero-1920-150.png")
            got = h.read_steam_piece("Hero", source)
            target = os.path.join(work, "hero-150-apng.png")
            h._write_steam_piece(got[0], target)
            got[0].close()
            fmt, frames, _keys = frames_of(target)
            ok("an animated PNG Library Hero too, its colors kept", fmt == "PNG" and len(frames) == 150
               and frames[0][1] == (30, 30, 200) and frames[1][1] == (200, 30, 30), (fmt, len(frames), frames[:2]))
        trying("2b", part2b)
        print()

        # ---------------------------------------------------------------- 3
        print("3. the disc meter: a stale measure, and one file weighed once")

        def part3():
            meter_src = tsa.class_members("RialtoApp", ["refresh_disc_meter"])
            ns = {"os": os, "threading": threading, "tk": type("tk", (), {"TclError": RuntimeError})}
            exec("class Meter:\n" + textwrap.indent(meter_src, "    "), ns)
            game = tempfile.mkdtemp(dir=work)
            release = threading.Event()
            drawn = []

            class Var(tsa.Var):
                pass

            class App(ns["Meter"]):
                def __init__(self):
                    self.disc_bar = object()
                    self.current_game_path = game
                    for name in ("logo_path_var", "company_logo_var", "ico_path_var", "disc_icon_var",
                                 "bonus_folder_var", "mac_build_var", "linux_build_var", "bg_path_var"):
                        setattr(self, name, Var(""))
                    self.mod_launcher_var, self.steam_button_var = Var(False), Var(True)
                    self.compression_var = Var("Balanced")
                    self.root = type("root", (), {"after": staticmethod(lambda _ms, then: then())})()
                    self._fill_bytes = self._disc1_bytes = 0

                def resolved_bonus_dir(self): return ""
                def resolved_mod_dir(self): return ""
                def unix_archive_stem(self): return "Probe"
                def menu_staging_bytes(self): return 0
                def menu_inside_bytes(self): return 0
                def steam_art_paths(self): return {"Hero": "hero.webp"}
                def steam_art_sources(self): return ("", "")

                def steam_art_bytes(self, *_args):
                    release.wait(10)  # the developer's hero, being written out
                    return 50 * MB

                def disc_weights(self, _path, _extras, _dup, menu_extra, *_rest):
                    return menu_extra, 0

                def draw_disc_meter(self):
                    drawn.append(self._fill_bytes)

            app = App()
            app.refresh_disc_meter()               # A: the hero is picked, and its weighing starts
            app.steam_button_var.set(False)
            app.refresh_disc_meter()               # B: Add to Steam unticked, weighed at once
            ok("the later measure is drawn at once", app._fill_bytes == 0 and drawn == [0], (app._fill_bytes, drawn))
            release.set()
            for _ in range(100):
                if threading.active_count() == 1:
                    break
                time.sleep(0.05)
            ok("and the earlier one, finishing last, leaves the meter as the later one drew it",
               app._fill_bytes == 0 and drawn == [0], (app._fill_bytes, drawn))
        trying("3a", part3)

        def part3b():
            class Slow(builder(METER)):
                reads = 0

                def read_steam_piece(self, key, path):
                    self.reads += 1
                    time.sleep(0.4)  # a long animation, being read
                    return super().read_steam_piece(key, path)
            m = Slow()
            path = tsa.picture(os.path.join(d, "meter-capsule.png"), (600, 900))
            weights = []
            workers = [threading.Thread(target=lambda: weights.append(m.steam_piece_bytes("Capsule", path)))
                       for _ in range(3)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
            ok("three refreshes while one file is weighed: it is read and written once", m.reads == 1, m.reads)
            ok("and each gets its weight", len(weights) == 3 and len(set(weights)) == 1 and weights[0], weights)
        trying("3b", part3b)
        print()

        # ---------------------------------------------------------------- 4
        print("4. the meter counts only what the build writes")

        def part4():
            Meter = builder(METER)
            allowance = Meter.STEAM_ART_ALLOWANCE

            def both(m, background="", logo=""):
                m.bg_path_var.set(background)
                m.logo_path_var.set(logo)
                counted = m.steam_art_bytes(m.steam_art_paths(), background, logo)
                menu = m.last_menu = tempfile.mkdtemp(dir=work)
                m.stage_steam_art(menu)
                folder = os.path.join(menu, "steam")
                written = sum(os.path.getsize(os.path.join(folder, n)) for n in os.listdir(folder)) \
                    if os.path.isdir(folder) else 0
                return counted, written, sorted(os.listdir(folder)) if os.path.isdir(folder) else []

            counted, written, names = both(Meter())
            ok("nothing given, no background, no Game Logo: nothing written and nothing counted",
               written == 0 and counted == 0, (counted, written, names))
            video = os.path.join(d, "background.mp4")
            with open(video, "wb") as fh:
                fh.write(b"\0" * 1000)
            path_was = os.environ.get("PATH", "")
            os.environ["PATH"] = ""
            try:
                counted, written, names = both(Meter(), video)
            finally:
                os.environ["PATH"] = path_was
            ok("a video background with no ffmpeg to take a still from: nothing counted", counted == 0 and written == 0,
               (counted, written, names))
            counted, written, names = both(Meter(), bg)
            ok("a background and no Game Logo: the three composed pieces, and no Library Logo",
               names == ["capsule.png", "hero.png", "wide.png"]
               and counted == allowance["Capsule"] + allowance["Header"] + allowance["Hero"], (counted, names))
            heavy = os.path.join(d, "heavy-logo.png")
            Image.frombytes("RGBA", (1100, 900), os.urandom(1100 * 900 * 4)).save(heavy)
            m = Meter()
            counted, written, names = both(m, bg, heavy)
            composed = allowance["Capsule"] + allowance["Header"] + allowance["Hero"]
            logo_png = os.path.getsize(os.path.join(m.last_menu, "steam", "logo.png")) if "logo.png" in names else 0
            ok("a %.1f MB Game Logo: counted at what logo.png weighs, not 1 MB" % (os.path.getsize(heavy) / MB),
               logo_png > 3 * MB and counted - composed == logo_png, (counted - composed, logo_png, names))
        trying("4", part4)
        print()

        # ---------------------------------------------------------------- 5 and 9
        print("5. upright and sRGB; 9. no color profile from the file reaches menu/steam/")

        def part5():
            h = Host()
            turned = os.path.join(d, "turned.jpg")
            exif = Image.Exif()
            exif[0x0112] = 6
            Image.new("RGB", (900, 600), (200, 40, 40)).save(turned, "JPEG", exif=exif.tobytes())
            got = h.read_steam_piece("Capsule", turned)
            ok("a 900 x 600 JPG with EXIF Orientation 6 reads as the 600 x 900 capsule a viewer shows",
               got[0] is not None and got[0].size == (600, 900) and got[3] == "", (getattr(got[0], "size", None), got[1:]))
            h.steam_capsule_var.set(turned)
            h.bg_path_var.set(bg)
            menu = tempfile.mkdtemp(dir=work)
            h.stage_steam_art(menu)
            with Image.open(os.path.join(menu, "steam", "capsule.jpg")) as im:
                ok("and goes on the disc standing up", im.size == (600, 900), im.size)

            profile = swapped_profile()
            cases = []
            still = os.path.join(d, "p3.png")
            Image.new("RGB", (600, 900), (255, 0, 0)).save(still, "PNG", icc_profile=profile)
            cases.append(("Capsule", still, "capsule.png", "a still PNG"))
            webp = os.path.join(d, "p3.webp")
            Image.new("RGB", (920, 430), (255, 0, 0)).save(webp, "WEBP", icc_profile=profile, lossless=True)
            cases.append(("Header", webp, "wide.png", "a still WebP"))
            moving = os.path.join(d, "p3-moving.png")
            frames = [Image.new("RGB", (384, 124), (255, 0, 0)), Image.new("RGB", (384, 124), (0, 255, 0))]
            frames[0].save(moving, "PNG", save_all=True, append_images=frames[1:], duration=50, loop=0,
                           icc_profile=profile)
            cases.append(("Hero", moving, "hero.png", "an animated PNG"))
            moving_webp = os.path.join(d, "p3-moving.webp")
            frames[0].save(moving_webp, "WEBP", save_all=True, append_images=frames[1:], duration=50, loop=0,
                           icc_profile=profile, lossless=True)
            cases.append(("Logo", moving_webp, "logo.png", "an animated WebP"))
            h = Host()
            h.bg_path_var.set(bg)
            for key, path, _name, _said in cases:
                getattr(h, next(a for k, a, *_r in h.STEAM_ART_PIECES if k == key)).set(path)
            menu = tempfile.mkdtemp(dir=work)
            h.stage_steam_art(menu)
            for key, path, name, said in cases:
                _fmt, staged, keys = frames_of(os.path.join(menu, "steam", name))
                red = staged[0][1]
                ok("%s in another color space is made sRGB: its red is sRGB's blue" % said,
                   red[2] > 200 and red[0] < 60, red)
                ok("9. and %s's color profile is left out" % said, "icc_profile" not in keys, keys)
        trying("5", part5)
        print()

        # ---------------------------------------------------------------- 6, 7 and 10
        print("6. 7. 10. an .ico, measured before it is decoded and made again")

        def part6():
            h = Host()
            block = png_bytes(Image.new("RGBA", (256, 256), (10, 120, 200, 255))) + b"\0" * MB
            many = os.path.join(d, "many.ico")
            with open(many, "wb") as fh:
                head = struct.pack("<HHH", 0, 1, 200)
                entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(block), 6 + 16 * 200)
                fh.write(head + entry * 200 + block)
            start = time.time()
            made = h._ico_as_given(many)
            ok("200 entries naming one 1 MB block: refused, not made 200 MB",
               made is None, len(made or b""))
            got = h.read_steam_piece("Icon", many)
            ok("and the Shortcut Icon is refused for it, quickly", got[0] is None and "not an .ico" in got[2]
               and time.time() - start < 5, (got[1:], time.time() - start))
            most = os.path.join(d, "most.ico")
            with open(most, "wb") as fh:
                small = png_bytes(Image.new("RGBA", (16, 16), (10, 120, 200, 255)))
                fh.write(struct.pack("<HHH", 0, 1, 65535)
                         + struct.pack("<BBBBHHII", 16, 16, 0, 0, 1, 32, len(small), 6 + 16 * 65535) * 65535 + small)
            start = time.time()
            h.steam_icon_var.set(most)
            h.bg_path_var.set(bg)
            menu = tempfile.mkdtemp(dir=work)
            h.stage_steam_art(menu)
            ok("65,535 entries: the build goes on, the shortcut keeps the Game Icon, quickly",
               not os.path.exists(os.path.join(menu, "steam", "icon.ico"))
               and any("keeps the Game Icon" in m for m in h.log) and time.time() - start < 10,
               (h.log, time.time() - start))
        trying("6", part6)

        def part7():
            h = Host()
            first = png_bytes(Image.new("RGBA", (256, 256), (10, 120, 200, 255)))
            bomb = io.BytesIO()
            Image.new("1", (9500, 9500)).save(bomb, "PNG")
            hidden = os.path.join(d, "hidden.ico")
            with open(hidden, "wb") as fh:
                fh.write(ico_of([first, bomb.getvalue()], {1: (16, 16)}))
            alone = os.path.join(d, "alone.ico")
            with open(alone, "wb") as fh:
                fh.write(ico_of([bomb.getvalue()]))  # its one entry said to be 256 x 256
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                got = h.read_steam_piece("Icon", hidden)
                hero = h.read_steam_piece("Hero", hidden)
                single = h.read_steam_piece("Icon", alone)
            ok("7. an entry said to be 16 x 16 that holds 9500 x 9500 is refused", got[0] is None and got[2] != ""
               and h._ico_as_given(hidden) is None, got[1:])
            ok("10. and nothing in it is decoded first, for the Shortcut Icon or the Library Hero, nor in an .ico "
               "of that one picture said to be 256 x 256",
               hero[0] is None and single[0] is None and not any(issubclass(w.category, Image.DecompressionBombWarning) for w in caught)
               and not any("expected size" in str(w.message) for w in caught), [str(w.message)[:60] for w in caught])

            marker = b"RIDING ALONG IN THE BLOCK " * 400
            stuffed = os.path.join(d, "riding.ico")
            small = png_bytes(Image.new("RGBA", (32, 32), (200, 20, 20, 255)))
            with open(stuffed, "wb") as fh:
                fh.write(ico_of([first + marker, small], {1: (32, 32)}))
            made = h._ico_as_given(stuffed)
            ok("bytes after a picture's end, inside its own block, are left out",
               made is not None and b"RIDING ALONG" not in made, len(made or b""))
            with Image.open(io.BytesIO(made or b"")) as icon:
                sizes = sorted(icon.info.get("sizes", ()))
                icon.size = (32, 32)
                icon.load()
                small_color = icon.convert("RGBA").getpixel((16, 16))
            ok("and every size in it is kept, pixel for pixel", sizes == [(32, 32), (256, 256)]
               and small_color == (200, 20, 20, 255), (sizes, small_color))
            bmp = io.BytesIO()
            Image.new("RGBA", (48, 48), (20, 160, 40, 255)).save(bmp, "ICO", sizes=[(48, 48)], bitmap_format="bmp")
            dib = os.path.join(d, "dib.ico")
            with open(dib, "wb") as fh:
                fh.write(bmp.getvalue())
            made = h._ico_as_given(dib)
            with Image.open(io.BytesIO(made or b"")) as icon:
                ok("a bitmap .ico is made again too", icon.size == (48, 48)
                   and icon.convert("RGBA").getpixel((24, 24)) == (20, 160, 40, 255), icon.size)
        trying("7", part7)
        print()

        # ---------------------------------------------------------------- 11 to 15
        print("11. to 15. the words")

        def part11():
            h = Host()
            got = h.read_steam_piece("Capsule", tsa.picture(os.path.join(d, "wide-capsule.png"), (920, 430)))
            ok("11. the log gives the picture's size beside Steam's, and nothing more",
               got[3] == "wide-capsule.png is 920 x 430; Steam's Library Capsule is 600 x 900.", got[3])
            reader = tsa.method_source("read_steam_piece")
            ok("and nothing in the reader says how Steam fills or crops a piece", "crops its" not in reader
               and "Steam fills" not in reader and "how Steam shows it" not in reader)
            guide = open(os.path.join(os.path.dirname(RIALTO), "docs", "rialto-guide.html"), encoding="utf-8").read()
            steam_guide = guide[guide.index("<h3>Steam</h3>"):guide.index("<h3>Mac and Linux</h3>")]
            lead = steam_guide.split("<table>")[0]
            flat = " ".join(lead.split())
            ok("nor does the Help Guide", "cropping its sides" not in flat and "how Steam shows it" not in flat, flat)
            ok("12. the Help Guide says a file Rialto cannot read or write is said in the log and that picture made",
               "is made by Rialto instead" not in flat and "cannot read or write" in flat
               and "the shortcut keeps your Game Icon" in flat, flat)
            ok("13. the Help Guide gives the frame limit", "1,000 frames" in flat and "250 at 3840 x 1240" in flat
               and "first frame" in flat, flat)
            extras = tsa.method_source("configure_disc_extras")
            steam_part = extras[extras.index("# --- Steam ---"):]
            tips = tsa.ast.literal_eval(steam_part[steam_part.index("steam_tips = ") + len("steam_tips = "):
                                                   steam_part.index("\n\n", steam_part.index("steam_tips = "))].strip())
            ok("13. the tooltips give it too: 1,000 frames, and the Library Hero's 250 at 3840 x 1240",
               all("keeps up to 1,000 of its frames" in tips[k] for k in ("Capsule", "Header", "Hero", "Logo"))
               and "250 at 3840 x 1240" in tips["Hero"] and "keeps its frames" not in " ".join(tips.values()),
               [t[:80] for t in tips.values()])
            gif = os.path.join(d, "moving-review.gif")
            Image.new("RGB", (60, 90), (200, 0, 0)).save(gif, save_all=True, duration=50,
                                                         append_images=[Image.new("RGB", (60, 90), (0, 0, 200))])
            got = h.read_steam_piece("Capsule", gif)
            ok("14. an animated GIF is said to go as its first frame",
               got[0] is not None and "moving-review.gif is an animated GIF, so Steam gets its first frame." in got[3],
               got[3])
            still_gif = tsa.picture(os.path.join(d, "still.gif"), (60, 90), mode="P", color=3, fmt="GIF")
            got = h.read_steam_piece("Capsule", still_gif)
            ok("and a still one is not", "animated" not in got[3], got[3])
            comment = SRC[SRC.index("    STEAM_ART_MAX_FRAME_PIXELS = "):SRC.index("    STEAM_ART_FORMATS = ")]
            ok("15. the comment says an animated WebP goes as a WebP, and a still one as a PNG",
               "an animated WebP inside a file named .png" in " ".join(comment.replace("#", " ").split())
               and "A still WebP" in comment, comment)
        trying("11", part11)
        print()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("FAILED: %d check(s)" % len(failures))
        return 1
    print("All Steam art review checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
