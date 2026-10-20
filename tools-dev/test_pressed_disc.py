"""A pressed disc (1.5.1, B5) and the compression choice (1.5.1, B7).

Pressed: CD, DVD and DVD DL make the same image as an unpressed build, by
mkisofs only, plus Chksum.md5 and a master sheet for the plant; DVD DL gets its
layer break worked out. Every other Target Media is refused before anything is
copied, each with its own sentence (pressed Blu-ray waits on the plants). A
pressed build never falls back to the ZIP: a ZIP is not a master.

Compression: Balanced is 1.5.0's lzma2/fast, and what a profile without the key
gets; Smallest disc is lzma2/max; Fastest install stores.

A disc image is faked from its descriptors (the bytes mkisofs writes where a
volume label and UDF live), so no ISO tool is needed; Chksum.md5 is checked
against Windows' own certutil.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_installer_script as tis  # noqa: E402

failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def fake_image(path, label, udf, sectors):
    """A file shaped like a disc image: the primary volume descriptor at sector
    16 with the label, and UDF's NSR02 recognition sector when asked."""
    data = bytearray(sectors * 2048)
    pvd = 16 * 2048
    data[pvd] = 1
    data[pvd + 1:pvd + 6] = b"CD001"
    data[pvd + 40:pvd + 72] = label.encode("ascii").ljust(32)
    if udf:
        data[18 * 2048 + 1:18 * 2048 + 6] = b"NSR02"
    with open(path, "wb") as f:
        f.write(bytes(data))


def main():
    src = open(tis.RIALTO, encoding="utf-8").read()
    tree = ast.parse(src)
    host, ns = tis.build_host(src)
    names = ("PRESSED_DISC_TYPES", "SECTOR_BYTES", "DVD9_LAYER0_SECTORS", "DVD9_LAYER_LIMIT", "DVD5_SECTORS")
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in names:
            exec(ast.get_source_segment(src, node), ns)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in (
                "pressed_refusal", "dvd9_layers", "iso_facts", "file_md5", "checksum_text", "master_sheet_text"):
            exec(ast.get_source_segment(src, node), ns)
    media = [name for name, _cap in next(ast.literal_eval(i.value) for n in tree.body if isinstance(n, ast.ClassDef)
                                         and n.name == "RialtoApp" for i in n.body if isinstance(i, ast.Assign)
                                         and getattr(i.targets[0], "id", "") == "MEDIA_TYPES")]

    print("1. which Target Media can be pressed")
    allowed = [m for m in media if not ns["pressed_refusal"](m)]
    says("CD, DVD and DVD DL only, the 8 cm minis among them (1.5.1, minis)",
         allowed == ["Mini CD 210 MB (8 cm)", "CD 700 MB", "Mini DVD 1.4 GB (8 cm)", "DVD 4.7 GB", "DVD DL 8.5 GB"],
         allowed)
    reasons = {m: ns["pressed_refusal"](m) for m in media if m not in allowed}
    says("Auto: a plant presses a named size", "named size" in reasons["Auto (single disc)"])
    says("every M-DISC and 128 GB: a blank only", all("blank disc to burn" in reasons[m]
                                                      for m in media if m.startswith("M-DISC") or "128 GB" in m))
    says("Blu-ray: waiting on the plants, with what to do now",
         all("not ready yet" in reasons[m] and "unpressed" in reasons[m] for m in ("Blu-ray 25 GB", "Blu-ray DL 50 GB")))
    says("66 and 100 GB XL: not confirmed by a plant",
         all("no plant has confirmed" in reasons[m] for m in ("Blu-ray XL 66 GB (4K UHD)", "Blu-ray XL 100 GB")))
    says("no refusal carries an em dash", not any("—" in r for r in reasons.values()))
    print()

    print("2. the DVD-9 layer break")
    layers = ns["dvd9_layers"]
    for sectors in (2_400_000, 3_000_000, 4_169_984, 2_084_993):
        l0, l1 = layers(sectors)
        says("{:,} sectors: Layer 0 a multiple of 16, at least Layer 1, neither over 2,085,000".format(sectors),
             l0 % 16 == 0 and l0 >= l1 and max(l0, l1) <= 2_085_000 and l0 + l1 == sectors, (l0, l1))
    says("past two full layers: not a DVD-9", layers(4_169_985) is None)
    says("everything on Layer 0 when it fits there", layers(1_000_000) == (1_000_000, 0))
    print()

    print("3. Chksum.md5 and the master sheet")
    work = tempfile.mkdtemp(prefix="rialto_b5_")
    try:
        disc1, disc2 = os.path.join(work, "Sky Quest Disc 1.iso"), os.path.join(work, "Sky Quest Disc 2.iso")
        fake_image(disc1, "SKYQUEST_1", False, 40)
        fake_image(disc2, "SKYQUEST_2", True, 48)
        says("the label read from the image", ns["iso_facts"](disc1) == ("SKYQUEST_1", False), ns["iso_facts"](disc1))
        says("UDF found where mkisofs puts it", ns["iso_facts"](disc2) == ("SKYQUEST_2", True), ns["iso_facts"](disc2))
        discs = [{"file": os.path.basename(p), "bytes": os.path.getsize(p), "md5": ns["file_md5"](p),
                  "label": ns["iso_facts"](p)[0], "udf": ns["iso_facts"](p)[1], "type": "DVD-9"} for p in (disc1, disc2)]
        try:
            certutil = subprocess.run(["certutil", "-hashfile", disc1, "MD5"], capture_output=True, text=True).stdout
            says("the MD5 is certutil's", discs[0]["md5"] in certutil.replace(" ", "").lower(), certutil)
        except OSError:
            says("certutil is on this PC", False)
        says("one 'hash *file' line per image",
             ns["checksum_text"](discs) == "%s *Sky Quest Disc 1.iso\n%s *Sky Quest Disc 2.iso\n" % (discs[0]["md5"], discs[1]["md5"]))
        sheet = ns["master_sheet_text"]("Sky Quest", "Your Studio", "1.5.1", "3 October 2026", discs,
                                        {"setup.exe": "yes", "menu.exe": "no"})
        says("every disc, numbered", "Disc 1 of 2" in sheet and "Disc 2 of 2" in sheet)
        says("bytes and sectors", "Bytes:         81,920" in sheet and "Sectors:       40 of 2,048 bytes" in sheet)
        says("the file system as built", "ISO 9660, Joliet and Rock Ridge" in sheet
             and "ISO 9660 level 3, Joliet, Rock Ridge and UDF" in sheet)
        says("a DVD-9's break, and the cheaper DVD-5 named when it would do",
             "Layer break:   Layer 0 40 sectors, Layer 1 0 sectors" in sheet and "A DVD-5 presses cheaper" in sheet)
        says("what is signed", "setup.exe signed:  yes" in sheet and "menu.exe signed:   no" in sheet)
        says("a data disc, no copy protection asked for", "No copy protection is requested." in sheet)
        says("no em dash", "—" not in sheet)
        big = dict(discs[0], bytes=3_000_000 * 2048)
        sheet = ns["master_sheet_text"]("T", "D", "1.5.1", "x", [big], {})
        says("a real DVD-9's break", "Layer 0 2,084,992 sectors, Layer 1 915,008 sectors (Layer 0 ends with sector 2,084,991)" in sheet
             and "presses cheaper" not in sheet, sheet)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()

    print("4. the build")
    flat = src.replace("\r\n", "\n")
    # mkisofs only for a plant (1.5.1): disc_image_tools leaves oscdimg out of a pressed disc's list, and
    # takes mkisofs on PATH, then the one Rialto carries. Run with a fake PATH, ADK and helpers folder.
    pick_src = "\n\n".join(ast.get_source_segment(src, n) for n in tree.body if (
        isinstance(n, ast.FunctionDef) and n.name in ("helper_path", "carried_mkisofs", "disc_image_tools"))
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "CARRIED_SETS"))
    work = tempfile.mkdtemp(prefix="rialto_pick_")
    try:
        carried = os.path.join(work, "helpers", "cdrtools", "mkisofs.exe")
        os.makedirs(os.path.dirname(carried))
        for name in ("mkisofs.exe", "cygwin1.dll"):
            open(os.path.join(work, "helpers", "cdrtools", name), "wb").close()
        pick = {"os": os, "re": re, "sys": types.SimpleNamespace(), "APP_ROOT": work,
                "find_iso_tools": lambda: (None, r"C:\ADK\oscdimg.exe")}
        exec(pick_src, pick)
        says("mkisofs only: oscdimg set aside for a pressed disc, the carried mkisofs taken",
             pick["disc_image_tools"](True) == [("mkisofs", carried, True)]
             and pick["disc_image_tools"](False)[0] == ("oscdimg", r"C:\ADK\oscdimg.exe", False))
        pick["find_iso_tools"] = lambda: (r"D:\cdrtools\mkisofs.exe", r"C:\ADK\oscdimg.exe")
        says("a pressed disc: mkisofs on PATH first, then the carried one",
             pick["disc_image_tools"](True) == [("mkisofs", r"D:\cdrtools\mkisofs.exe", False), ("mkisofs", carried, True)])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # One disc and a set taking that list, never the ZIP for a pressed disc, the sheet and checksum after
    # the image and only for the images made: driven for real in test_image_tool_chain.py.
    says("refused before anything is copied", "refusal = pressed_refusal(self.target_media_var.get())" in flat
         and "missing_tool_refusals(self.pressed_disc_on()" in flat
         and "if not self.run_preflight_check():\n            return False\n        return self.build_all()" in flat)
    says("the sheet and checksum are kept by the clean-up",
         'item == "Chksum.md5" or item.endswith(" master sheet.txt")' in flat)
    says("saved, loaded and cleared with the profile",
         'profile_data["PressedDisc"] = bool(self.pressed_disc_var.get())' in flat
         and 'self.pressed_disc_var.set(bool(profile_data.get("PressedDisc", False)))' in flat
         and "self.pressed_disc_var.set(False)" in flat)
    print()

    print("5. compression")
    choose = ns["compression_setting"]
    says("Balanced is 1.5.0's", choose("Balanced") == "lzma2/fast")
    says("Smallest disc and Fastest install", choose("Smallest disc") == "lzma2/max" and choose("Fastest install") == "none")
    says("a profile without the key, or with nonsense, builds as 1.5.0", choose(None) == "lzma2/fast" and choose("Ultra") == "lzma2/fast")

    class Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value
    for label, want in (("Balanced", "lzma2/fast"), ("Smallest disc", "lzma2/max"), ("Fastest install", "none")):
        host.compression_var = Var(label)
        script, out = tis.generate(host, {"Title": "T", "Developer": "D"})
        shutil.rmtree(out, ignore_errors=True)
        lines = [l for l in script.splitlines() if l.startswith("Compression=")]
        says("%s writes Compression=%s and nothing else changes" % (label, want),
             lines == ["Compression=" + want] and "SolidCompression=no" in script, lines)
    says("saved, loaded (checked against the choices) and cleared",
         'profile_data["Compression"] = self.compression_var.get()' in flat
         and "compression if compression in dict(COMPRESSION_CHOICES) else \"Balanced\"" in flat
         and 'self.compression_var.set("Balanced")' in flat)

    if failures:
        print("\nFAILED: %d check(s)" % len(failures))
        return 1
    print("\nAll pressed-disc and compression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
