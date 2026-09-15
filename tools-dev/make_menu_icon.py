"""Regenerate assets/menu_icon.ico, the disc menu's neutral icon.

One pre-built menu.exe ships on every disc, white-labelled ones included, so its
icon has to carry no bird and no game art. Run this only if the icon needs to
change; the .ico itself is committed.

Usage: python tools-dev/make_menu_icon.py
"""
import os

from PIL import Image, ImageDraw

SIZES = [256, 128, 64, 48, 32, 16]
BASE = 1024  # draw big, downsample
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build():
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded dark plate, matching the menu's own #1a1a1a backdrop
    pad = BASE * 0.06
    box = [pad, pad, BASE - pad, BASE - pad]
    radius = int(BASE * 0.20)
    d.rounded_rectangle(box, radius=radius, fill=(26, 26, 26, 255))
    # Thin light rim, echoing the menu's hairline button styling
    d.rounded_rectangle(box, radius=radius, outline=(221, 221, 221, 255),
                        width=int(BASE * 0.022))

    # Play triangle, optically centred (nudged right of true centre)
    cx, cy = BASE * 0.53, BASE * 0.5
    h = BASE * 0.40
    w = h * 0.88
    d.polygon([(cx - w / 2, cy - h / 2), (cx - w / 2, cy + h / 2), (cx + w / 2, cy)],
              fill=(255, 255, 255, 255))

    out = os.path.join(REPO, "assets", "menu_icon.ico")
    img.save(out, format="ICO", sizes=[(s, s) for s in SIZES])
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({os.path.getsize(path)} bytes)")
