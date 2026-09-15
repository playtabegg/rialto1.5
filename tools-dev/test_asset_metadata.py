"""The images Rialto ships carry picture data and nothing else.

assets/bird_logo.PNG once held a 51 KB Content Credentials (C2PA) block. The
logo is bundled into Rialto.exe and copied onto every branded disc, so any PNG
in assets/ may carry only the chunks that describe the picture itself.
"""
import os
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "assets")
PICTURE_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP",
                  b"pHYs", b"sBIT", b"bKGD"}


def chunk_kinds(path):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("%s is not a PNG" % path)
    kinds, i = [], 8
    while i < len(data):
        size = struct.unpack(">I", data[i:i + 4])[0]
        kinds.append(data[i + 4:i + 8])
        i += 12 + size
    return kinds


def main():
    pngs = [name for name in sorted(os.listdir(ASSETS)) if name.lower().endswith(".png")]
    if not pngs:
        print("  [FAIL] no PNG found in assets/")
        sys.exit(1)
    failed = False
    for name in pngs:
        extra = sorted({kind.decode("latin-1") for kind in chunk_kinds(os.path.join(ASSETS, name))} -
                       {kind.decode("latin-1") for kind in PICTURE_CHUNKS})
        good = not extra
        failed = failed or not good
        print("  [%s] assets/%s carries only picture chunks%s" % ("OK  " if good else "FAIL", name,
                                                                  "" if good else " (also: %s)" % ", ".join(extra)))
    if failed:
        sys.exit(1)
    print("shipped images are plain.")


if __name__ == "__main__":
    main()
