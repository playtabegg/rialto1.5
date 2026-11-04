"""His last answers for 1.5.2 (4 Nov 2026), held against the real code.

1. Hide the menu's title and logo: its tooltip and its Help Guide row say the
   game's title and Game Logo are hidden, the Company Logo stays in its corner,
   and an empty Company Logo shows none; the disc menu draws the Company Logo
   whatever the tick.
2. Restore page leaves alone the settings config.json keeps for this PC: Sign
   Final Build, No time limit, Remove WTI Branding and the MODS tick. It writes
   no config.json, and its question says so.
3. (test_steam_later_disc.py: ADD TO STEAM from a later disc.)
4. The disc meter, counting more than one disc on Balanced or Smallest disc,
   adds ", fewer once compressed"; not on Fastest install, not for one disc.
5. No word Rialto shows, nor the Help Guide, says squeeze: compress.

Usage: python test_final_behaviours.py [path-to-Rialto.pyw]
"""
import ast
import os
import re
import sys
import textwrap

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_mini_discs as tmd  # noqa: E402

RIALTO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "Rialto.pyw")
SRC = open(RIALTO, encoding="utf-8").read()
TREE = ast.parse(SRC)
GUIDE = open(os.path.join(REPO, "docs", "rialto-guide.html"), encoding="utf-8").read()
failures = []


def says(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" -> " + ascii(detail)) if detail and not condition else ""))
    if not condition:
        failures.append(label)


def method(name, cls="RialtoApp"):
    for node in TREE.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return textwrap.dedent(ast.get_source_segment(SRC, item))
    raise SystemExit("%s.%s not found" % (cls, name))


def joined_strings(code):
    """Every string in this code, adjacent literals joined as Python joins them."""
    return [n.value for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def guide_row(name):
    match = re.search(r"<tr><td>%s</td><td>(.*?)</td></tr>" % re.escape(name), GUIDE, re.S)
    return match.group(1) if match else ""


def hide_title():
    print("1. Hide the menu's title and logo keeps the Company Logo in its corner")
    tips = [s for s in joined_strings(method("create_widgets")) if s.startswith("Tick this when your background")]
    tip = tips[0] if tips else ""
    says("the tooltip says the game title and Game Logo are hidden", "no game title or Game Logo on top" in tip, tip)
    says("that the Company Logo stays in its corner", "The Company Logo stays in its corner." in tip, tip)
    says("and that an empty Company Logo shows none", "Leave Company Logo empty to show none." in tip, tip)
    row = guide_row("Hide the menu's title and logo")
    says("the Help Guide row says the same", "no game title or Game Logo on top" in row
         and "The Company Logo stays in its corner" in row and "leave Company Logo empty to show none" in row, row)
    template = next(ast.literal_eval(n.value) for n in TREE.body if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", "") == "MENU_TEMPLATE_SOURCE")
    block = template[template.index("# Add company logo in bottom-right"):template.index("# Add copyright text")]
    says("the disc menu draws the Company Logo whatever the tick", "company_logo.png" in block
         and "own_art" not in block and "background_has_title" not in block)
    print()


def restore_page():
    print("2. Restore page leaves the settings kept on this PC as they are")
    asked = []
    ns = {"tk": None}
    exec(method("restore_page"), ns)
    host = type("Host", (), {})()
    host.show_centered_popup = lambda title, text, kind="": asked.append(text) or True
    wrote = []
    host.save_signing_settings = lambda: wrote.append(True)
    for name in ("sign_final_build", "remove_wti_branding", "mod_launcher_var"):
        setattr(host, name, tmd.Var(True))
    host.no_time_limit = tmd.Var(False)
    for name in ("game_path_var", "publisher_text_var", "disc_name_var", "bg_path_var", "menu_music_var",
                 "logo_path_var", "company_logo_var", "ico_path_var", "disc_icon_var", "mac_build_var",
                 "linux_build_var", "bonus_folder_var", "target_media_var", "compression_var", "pressed_disc_var",
                 "bg_has_title_var", "usb_export_var", "mod_folder_var", "steam_button_var", "compat_mode_var",
                 "compat_args_var", "compat_hint_var"):
        setattr(host, name, tmd.Var("x"))
    host.entries = {}
    host.refresh_game_exes_summary = host.refresh_disc_meter = lambda: None
    host.set_steam_art = lambda pieces: None
    host.update_status = lambda line: None
    ns["restore_page"](host)
    says("Sign Final Build stays ticked", host.sign_final_build.get() is True)
    says("No time limit stays unticked", host.no_time_limit.get() is False)
    says("Remove WTI Branding stays ticked", host.remove_wti_branding.get() is True)
    says("the MODS tick stays", host.mod_launcher_var.get() is True)
    says("and config.json is not written", not wrote)
    says("the page itself is cleared", host.bg_path_var.get() == "" and host.compression_var.get() == "Balanced")
    text = asked[0] if asked else ""
    says("its question names the settings that stay", all(w in text for w in (
        "Sign Final Build", "No time limit", "Remove WTI Branding", "MODS button", "stay as they are")), text)
    says("and still says profiles and builds are not touched",
         "Saved profiles, your signing setup and anything already built are not touched" in text, text)
    tips = [s for s in joined_strings(method("build_export_bar")) if s.startswith("Clears every field on the page")]
    says("the button's tooltip says the same, with no exclamation", bool(tips) and "stay as they are" in tips[0]
         and "!" not in tips[0], tips)
    # A start puts the last profile on the form, and Load Profile sets Remove
    # WTI Branding and the MODS tick from a profile: neither "as a fresh Rialto
    # starts" nor "since Rialto keeps them on this PC" is true (review, 4 Nov).
    says("and claims no more than that", bool(tips) and tips[0] == (
        "Clears every field on the page. Sign Final Build, No time limit, Remove WTI Branding and the MODS "
        "button in Disc Extras stay as they are. Save your work first."), tips)
    print()


def meter():
    print("4. the disc meter: fewer once compressed")
    ns = tmd.module_names(SRC, TREE, ["MINI_DISC_MEDIA", "spanned_disc_count"])
    theme = {k: k for k in ("meter_fill", "meter_warn", "meter_over", "meter_track", "header_bg", "button_bg")}

    def line(media, total, choice):
        host = tmd.media_host(SRC, ns, ["get_target_media_capacity", "draw_disc_meter"], media,
                              disc_bar=tmd.Canvas(), disc_meter=tmd.Canvas(), theme_mode=tmd.Var("dark"),
                              dark_theme=theme, light_theme=theme, disc_fill_var=tmd.Var(""),
                              _fill_bytes=total, _disc1_bytes=60_000_000, compression_var=tmd.Var(choice))
        host.draw_disc_meter()
        return host.disc_fill_var.get()

    for choice in ("Balanced", "Smallest disc"):
        got = line("CD 700 MB", 1_980_000_000, choice)
        says("%s, three CDs: about 3 discs, fewer once compressed" % choice,
             got.endswith(" - about 3 discs, fewer once compressed"), got)
    got = line("CD 700 MB", 1_980_000_000, "Fastest install")
    says("Fastest install: about 3 discs, and no more", got.endswith(" - about 3 discs"), got)
    got = line("CD 700 MB", 500_000_000, "Balanced")
    says("one disc: no count and no such words", "discs" not in got and "compressed" not in got, got)
    print()


def compress_words():
    print("5. compress, never squeeze, in every word Rialto shows and in the Help Guide")
    words = [n.value for n in ast.walk(TREE) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    hits = [w[:80] for w in words if "squeez" in w.lower()]
    says("no string in Rialto.pyw says squeeze, the disc menu's included", not hits, hits)
    says("nor the Help Guide", "squeez" not in GUIDE.lower(), re.findall(r".{40}squeez.{20}", GUIDE, re.I))
    tip = [s for s in joined_strings(method("create_widgets")) if s.startswith("How much the installer")]
    says("the Compression tooltip: compresses, meaning unchanged", tip == [
        "How much the installer compresses your game. Balanced suits most games. Smallest disc compresses "
        "it the most, so the build takes longer. Fastest install stores the game as it is, so setup only copies "
        "it, and the disc is bigger, which can mean more discs."], tip)
    says("the guide's Compression part too", "sets how much the installer compresses\n  your game" in GUIDE
         and "<b>Smallest disc</b> compresses it the most" in GUIDE)
    says("and its Menu Music row", "The menu's copy is kept as it is. The installer compresses its copy on "
         "Balanced and Smallest disc" in guide_row("Menu Music"), guide_row("Menu Music"))
    print()


def main():
    print("1.5.2: his last answers, 4 Nov 2026\n")
    hide_title()
    restore_page()
    meter()
    compress_words()
    if failures:
        print("FAILED (%d):" % len(failures))
        for label in failures:
            print("  - " + label)
        return 1
    print("All final-behaviour checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
