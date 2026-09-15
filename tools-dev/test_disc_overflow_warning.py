"""Prove a spanned set warns - and keeps building - when a disc overflows.

Disc 1 of a spanned set is seeded with the whole base fileset (menu, setup
stub, bonus/, mods/) and only the setup-*.bin parts are packed by size, so a
fat bonus folder silently pushes disc 1 past the chosen Target Media. This
checks the warning that now calls that out, in two layers:

  1. `oversized_disc_warnings` (module level in Rialto.pyw) as a pure unit:
     byte totals in, status lines out, boundaries included.
  2. The real `create_spanned_isos` driven end to end on a temp output folder.
     No gigabytes are written: the tree holds one-byte files and an `os` shim
     reports synthetic sizes for them, so the genuine `_collect_disc_fileset`,
     `_fileset_size` and `_fileset_needs_udf` run over a real directory while
     the packer sees a 6 GB bonus folder and 2 GB installer slices.

MEDIA_TYPES and MEDIA_RESERVE are read out of Rialto.pyw rather than copied,
so retuning the disc budget retunes this test with it.

Usage: python test_disc_overflow_warning.py [path-to-Rialto.pyw]
"""
import ast
import os
import shutil
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")

GB = 1_000_000_000
MB = 1_000_000

# The status lines carry an emoji; a cp1252 console would choke on the echo.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------
def extract_methods(src, class_name, names):
    tree = ast.parse(src)
    out, seen = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names:
                    out.append(textwrap.dedent(ast.get_source_segment(src, item)))
                    seen.add(item.name)
    missing = set(names) - seen
    if missing:
        raise SystemExit(f"could not extract {class_name}.{sorted(missing)}")
    return "\n\n".join(out)


def extract_function(src, name):
    """Source of a module-level def."""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit(f"could not extract module-level {name}()")


def extract_class_constant(src, class_name, const):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == const:
                            # literal_eval won't do arithmetic, and
                            # MEDIA_RESERVE is written as 96 * 1024 * 1024.
                            expr = ast.Expression(body=item.value)
                            ast.fix_missing_locations(expr)
                            return eval(compile(expr, "<const>", "eval"), {})
    raise SystemExit(f"could not read {class_name}.{const}")


def method_source(src, class_name, name):
    return extract_methods(src, class_name, [name])


class Flag:
    """Stands in for a tk.StringVar / tk.BooleanVar."""
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


# --------------------------------------------------------------------------
# size shim: real directory tree, synthetic file sizes
# --------------------------------------------------------------------------
class ShimPath:
    def __init__(self, sizes):
        self._sizes = sizes

    def getsize(self, path):
        key = os.path.normcase(os.path.abspath(path))
        if key in self._sizes:
            return self._sizes[key]
        return os.path.getsize(path)

    def __getattr__(self, name):
        return getattr(os.path, name)


class ShimOs:
    """`os` with a pinch of salt: only getsize lies, everything else is real."""
    def __init__(self, sizes):
        self.path = ShimPath(sizes)

    def __getattr__(self, name):
        return getattr(os, name)


def build_host(src, sizes, **attrs):
    attrs.setdefault("mod_folder_var", Flag(""))
    attrs.setdefault("current_game_path", "")
    methods = extract_methods(src, "RialtoApp", [
        "_collect_disc_fileset",
        "default_mod_dir", "resolved_mod_dir", "staged_mod_dir_name",
        "_fileset_size",
        "_fileset_needs_udf",
        "create_spanned_isos",
    ])
    ns = {
        "os": ShimOs(sizes),
        "sys": sys,
        "shutil": shutil,
        "oversized_disc_warnings": load_pure(src),
    }
    exec(f"class Host:\n{textwrap.indent(methods, '    ')}", ns)
    host = ns["Host"]()
    host.log = []
    host.built = []
    host.update_status = host.log.append
    host.refresh_windows_icon_cache = lambda: None

    def fake_build_single_iso(output_path, iso_path, items, disc_label, needs_udf):
        # Stand-in for mkisofs/oscdimg: record the disc and leave a small file
        # behind, because create_spanned_isos stats the ISO it just made.
        host.built.append((os.path.basename(iso_path), list(items), needs_udf))
        with open(iso_path, "wb") as f:
            f.write(b"ISO")
        return True

    host._build_single_iso = fake_build_single_iso
    for k, v in attrs.items():
        setattr(host, k, v)
    return host


def load_pure(src):
    ns = {}
    exec(extract_function(src, "oversized_disc_warnings"), ns)
    return ns["oversized_disc_warnings"]


# --------------------------------------------------------------------------
# fixture
# --------------------------------------------------------------------------
def make_output_tree(base, bonus_bytes, bin_bytes, mods_bytes=30 * MB):
    """A finished output folder just before create_iso, with faked sizes."""
    out = os.path.join(base, "output", "MockGame")
    os.makedirs(out, exist_ok=True)
    sizes = {}

    def touch(rel, size):
        p = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        sizes[os.path.normcase(os.path.abspath(p))] = size

    touch("setup.exe", 2 * MB)
    touch("autorun.inf", 1024)
    touch("README.txt", 4096)
    touch("game_icon.ico", 200 * 1024)
    touch("menu/menu.exe", 40 * MB)
    if bonus_bytes:
        # Lopsided on purpose: one fat making-of video and a small artbook, so
        # a big bonus folder also trips the >4 GiB single-file UDF rule.
        touch("bonus/artbook.pdf", bonus_bytes // 8)
        touch("bonus/making_of.mkv", bonus_bytes - bonus_bytes // 8)
    if mods_bytes:
        touch("mods/ModLauncher.exe", mods_bytes)
    for i, size in enumerate(bin_bytes, start=1):
        touch(f"setup-{i}.bin", size)
    return out, sizes


def capacity_of(media_types, label):
    for name, cap in media_types:
        if name == label:
            return cap
    raise SystemExit(f"no such media type: {label}")


def run_span(base, src, media_types, reserve, media_label,
             bonus_bytes, bin_bytes):
    out, sizes = make_output_tree(base, bonus_bytes, bin_bytes)
    host = build_host(src, sizes,
                      MEDIA_RESERVE=reserve,
                      mod_launcher_var=Flag(True),
                      target_media_var=Flag(media_label))
    host.create_spanned_isos(out, {"GameName": "MockGame", "Title": "Mock Game"},
                             "MOCKGAME", capacity_of(media_types, media_label))
    return host


def warn_lines(host):
    return [line for line in host.log if line.startswith("⚠️ Disc ")]


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------
def main():
    src = open(RIALTO, encoding="utf-8").read()
    media_types = extract_class_constant(src, "RialtoApp", "MEDIA_TYPES")
    reserve = extract_class_constant(src, "RialtoApp", "MEDIA_RESERVE")
    warn = load_pure(src)

    dvd = capacity_of(media_types, "DVD 4.7 GB")
    dvd_budget = dvd - reserve
    print(f"Media constants read from Rialto.pyw: DVD {dvd} bytes, "
          f"reserve {reserve} bytes, budget {dvd_budget} bytes "
          f"({dvd_budget / 1e9:.2f} GB)\n")

    # --- 1. the pure check ------------------------------------------------
    print("Unit - oversized_disc_warnings()")
    check("everything fits -> silence", warn([1 * GB, 2 * GB], dvd_budget, "DVD 4.7 GB"), [])
    check("exactly on budget -> silence", warn([dvd_budget], dvd_budget, "DVD 4.7 GB"), [])
    check("one byte over -> two lines",
          len(warn([dvd_budget + 1], dvd_budget, "DVD 4.7 GB")), 2)
    check("empty set -> silence", warn([], dvd_budget, "DVD 4.7 GB"), [])

    six = warn([6 * GB + 130 * MB, 2 * GB], dvd_budget, "DVD 4.7 GB")
    print(f"    line 1: {six[0]}")
    print(f"    line 2: {six[1]}")
    check("6 GB bonus disc is named with its real size", "Disc 1 is 6.13 GB" in six[0], True)
    check("the media budget is quoted too", f"{dvd_budget / 1e9:.2f} GB" in six[0], True)
    check("the chosen media is named", "DVD 4.7 GB" in six[0], True)
    check("says the build continues", "The build will continue" in six[1], True)
    check("offers both ways out",
          "larger Target Media" in six[1] and "trimming the bonus folder" in six[1], True)
    check("the fitting disc 2 is not mentioned", any("Disc 2" in l for l in six), False)

    many = warn([6 * GB, 1 * GB, 9 * GB], dvd_budget, "DVD 4.7 GB")
    numbered = [l for l in many if l.startswith("⚠️ Disc ")]
    check("every oversized disc is listed, by number",
          [l.split()[2] for l in numbered], ["1", "3"])
    print()

    # --- 2. the real spanned build ----------------------------------------
    base = tempfile.mkdtemp(prefix="rialto_span_")
    try:
        # A: the motivating case - 6 GB of bonus content against a DVD
        host = run_span(os.path.join(base, "A"), src, media_types, reserve,
                        "DVD 4.7 GB", bonus_bytes=6 * GB,
                        bin_bytes=[2 * GB, 2 * GB, 2 * GB])
        print("Scenario A - 6 GB bonus folder, Target Media = DVD 4.7 GB")
        for line in host.log:
            print(f"    {line}")
        lines = warn_lines(host)
        check("disc 1 overflow is warned about", len(lines), 1)
        check("the warning is about disc 1", "Disc 1 is 6.07 GB" in (lines[0] if lines else ""), True)
        check("warning is kept for the build summary",
              (getattr(host, "disc_overflow_warnings", None) or [None])[0],
              (lines or [None])[0])
        # The oversized base flushes disc 1 on its own, then the three slices
        # pack two-to-a-disc: 3 ISOs, none of them skipped.
        check("the set was still built (warn, don't refuse)", len(host.built), 3)
        check("disc 1 carries bonus and mods",
              [i for i in host.built[0][1] if i in ("bonus", "mods")], ["bonus", "mods"])
        check("no bin was left behind",
              sorted(i for d in host.built for i in d[1] if i.endswith(".bin")),
              ["setup-1.bin", "setup-2.bin", "setup-3.bin"])
        check("the set reports itself complete",
              any("Multi-disc set complete" in l for l in host.log), True)
        check("a bonus file over 4 GiB forces UDF", host.built[0][2], True)
        print()

        # B: same build, bonus trimmed to something that fits
        host = run_span(os.path.join(base, "B"), src, media_types, reserve,
                        "DVD 4.7 GB", bonus_bytes=200 * MB,
                        bin_bytes=[2 * GB, 2 * GB, 2 * GB])
        print("Scenario B - 200 MB bonus folder, Target Media = DVD 4.7 GB")
        for line in host.log:
            print(f"    {line}")
        check("no disc overflows, so no warning", warn_lines(host), [])
        check("nothing is stashed for the summary",
              getattr(host, "disc_overflow_warnings", "unset"), [])
        check("the set is built either way", len(host.built) > 1, True)
        print()

        # C: the same 6 GB bonus is fine on bigger media
        host = run_span(os.path.join(base, "C"), src, media_types, reserve,
                        "Blu-ray 25 GB", bonus_bytes=6 * GB,
                        bin_bytes=[2 * GB, 2 * GB, 2 * GB, 2 * GB, 2 * GB, 2 * GB,
                                   2 * GB, 2 * GB, 2 * GB, 2 * GB, 2 * GB, 2 * GB,
                                   2 * GB])
        print("Scenario C - the same 6 GB bonus folder, Target Media = Blu-ray 25 GB")
        check("bigger media, no warning", warn_lines(host), [])
        check("still spans more than one disc", len(host.built) > 1, True)
        print()

        # D: a single installer slice bigger than the disc (built for other
        # media, then burned to a CD) - the other way a disc overflows.
        host = run_span(os.path.join(base, "D"), src, media_types, reserve,
                        "CD 700 MB", bonus_bytes=0,
                        bin_bytes=[2 * GB, 100 * MB])
        print("Scenario D - a 2 GB installer slice against a CD")
        for line in warn_lines(host):
            print(f"    {line}")
        check("an oversized slice is warned about too", len(warn_lines(host)) >= 1, True)
        check("the set is still built", len(host.built) >= 1, True)
        print()
    finally:
        shutil.rmtree(base, ignore_errors=True)

    # --- 3. the completion path is wired up -------------------------------
    print("Wiring - build_all")
    build_all = method_source(src, "RialtoApp", "build_all")
    check("the list is cleared at the start of every build",
          "self.disc_overflow_warnings = []" in build_all, True)
    check("the warning is repeated at build completion",
          "disc_overflow_warnings" in build_all.split("Build complete!")[1], True)
    check("the done popup mentions it",
          "target media" in build_all.split("Build complete!")[1], True)
    span = method_source(src, "RialtoApp", "create_spanned_isos")
    check("create_spanned_isos no longer bails out when the base is too big",
          "don't fit the chosen disc" in span, False)
    print()

    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print("  - " + f)
        return 1
    print("All disc-overflow warning assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
