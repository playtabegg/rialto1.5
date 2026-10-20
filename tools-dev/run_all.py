"""Run every dev harness in tools-dev and report one verdict.

None of them need the GUI, PyQt5, PyInstaller or a disc: they pull the real
methods out of Rialto.pyw and exercise them against temp folders.

Usage: python tools-dev/run_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

HARNESSES = [
    ("validate_menu_template.py", "disc menu source, translations, mods button"),
    ("test_generic_menu.py", "one generic menu.exe, title driven by menu_config.json"),
    ("test_frozen_paths.py", "frozen-aware paths and the release spec"),
    ("test_deps_marker.py", "first-run and upgrade dependency install"),
    ("test_version_agreement.py", "one __version__, read by both specs"),
    ("test_update_check.py", "Help > Check for a New Rialto trusts only a signed feed"),
    ("test_bonus_staging.py", "where bonus/ and mods/ end up, build and preview"),
    ("test_disc_overflow_warning.py", "multi-disc sets that overflow the target media"),
    ("test_mod_resolution.py", "mod exe resolution, build side and menu side"),
    ("test_staged_menu_signing.py", "BYOK signing of this build's own menu.exe copy"),
    ("test_steam_shortcuts.py", "ADD TO STEAM against a corrupt, locked or full disk"),
    ("test_installer_script.py", "the .iss ISCC compiles and Rialto then signs"),
    ("test_metadata_sanitization.py", "profile/batch control-char and metachar sanitization"),
    ("test_runtime_authenticity.py", "vcredist Authenticode check before packaging"),
    ("test_signing_endpoint.py", "sign_file re-validates the Artifact Signing endpoint"),
    ("test_package_release.py", "clean release packager, no working-tree secrets"),
    ("test_safe_extract.py", "zip-slip refused on dlib/innoextract extracts"),
    ("test_landmines.py", "IsWin64/DRM gone; find_game_exe skips junctions"),
    ("test_compatibility_mode.py", "compatibility-mode launch argument, build side and menu side"),
    ("test_field_layouts.py", "mod-maker/, a nested exe and a moved input root, handled loudly"),
    ("test_disc_assets.py", "disc size estimate, background video fallback, logo transparency"),
    ("test_engine_layouts.py", "Unity/Unreal/Godot/RPG Maker/Ren'Py/Electron... all start the right exe"),
    ("test_hostile_inputs.py", "hostile titles and degenerate game folders, from a stranger's PC"),
    ("test_copy_failure_stops_build.py", "a game copy that fails halfway stops the build"),
    ("test_non_western_titles.py", "titles outside Western European letters build without a crash"),
    ("test_asset_metadata.py", "shipped images carry no embedded provenance tags"),
    ("test_tool_discovery.py", "Inno Setup and oscdimg found without PATH; the carried tools fill the gap"),
    ("test_carried_tools.py", "the Inno Setup and mkisofs Rialto carries: pins, order, a real disc with its folders"),
    ("test_image_tool_chain.py", "the disc image tools driven with stand-ins: hand over, stop, clean up, only made images"),
    ("test_preview_and_docs.py", "Preview staging and the guide copy never write through a junction or link"),
    ("test_profile_moves.py", "a moved profile's art follows the game folder; missing art is said truly"),
    ("test_review_fixes.py", "the 1.5.1 security and bugs reviews' findings stay fixed"),
    ("test_build_queue.py", "the Build Queue: rows, refusals, stop, summary, the form put back"),
    ("test_build_watch.py", "a build you can watch: every long step watched, closing asks and stops cleanly"),
    ("test_pressed_disc.py", "a pressed disc: the master sheet, Chksum.md5, the DVD-9 break; compression"),
    ("test_placed_files.py", "files the installer places for the player: saves, configs, a mod's first-run files"),
    ("test_many_games.py", "many games on one disc: a game per folder, the Choose Your Game page, stars, the games under Play Games"),
    ("test_windows7_shortcuts.py", "Windows 7 and 8: the shortcuts start the game itself"),
    ("test_main_window_fits.py", "the main window keeps Step 4 and the log in view on a short screen"),
    ("test_disc_extras_fits.py", "Disc Extras fits the screen: two columns, sized to what they hold"),
    ("test_build_gates.py", "the game folder can live anywhere; no installer stops the build"),
    ("test_ui_review.py", "the interface review: one name for each thing, tooltips that teach, the guide, spelling"),
    ("test_fits_every_screen.py", "every window Rialto opens fits the work area, at four screen sizes"),
    ("test_play_games_menu.py", "the disc menu off screen: every game under Play Games, stars, languages, a controller"),
    ("test_no_console_windows.py", "every console program Rialto starts is started hidden: no black window"),
    ("test_update_offer.py", "Check for a New Rialto hands the browser the download: the zip, or the Setup when installed"),
    ("test_mini_discs.py", "the 8 cm Mini CD and Mini DVD: capacities, reserve, a set of minis, pressed, 1.5.0 unchanged"),
    ("test_media_list.py", "the Target Media list opens wide enough to read every choice"),
]


def main():
    # The menu is translated into 34 languages and the harnesses print those
    # strings back. A Windows console is cp1252, so a Thai or Hebrew button
    # label in a failure dump used to kill the runner while it was busy
    # reporting the failure. Children get UTF-8; our own console degrades to
    # replacement characters rather than an exception.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass
    child_env = dict(os.environ, PYTHONIOENCODING="utf-8")

    results = []
    for script, blurb in HARNESSES:
        proc = subprocess.run([sys.executable, os.path.join(HERE, script)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=child_env)
        good = proc.returncode == 0
        results.append((script, good, proc))
        print(f"[{'PASS' if good else 'FAIL'}] {script:<32} {blurb}")
        if not good:
            print((proc.stdout or "")[-3000:])
            print((proc.stderr or "")[-2000:])

    failed = [s for s, good, _ in results if not good]
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} harnesses FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(results)} harnesses passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
