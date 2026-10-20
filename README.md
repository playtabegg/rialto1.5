# Rialto 1.5.1

Turn your finished Windows game into a real disc: an autorun menu with your art, a proper installer, a disc icon and a ready-to-write ISO. Drop it in a drive and it feels like the games you grew up with.

Free and open source, built by [We the Indies](https://wetheindies.com).

**[Download Rialto 1.5.1](https://github.com/playtabegg/rialto1.5/releases/latest)** · [Signing guide](SIGNING.md) · The manual opens from **Help Guide** inside Rialto

## Easier from the very first minute

- Run `Rialto-1.5.1-Setup.exe` and Rialto opens, ready to build. No administrator prompt, no Python, nothing else to install.
- Choose **File > Put Rialto on the Desktop** and launch Rialto like any normal app.
- Your game's exe keeps its own name. No renaming to game.exe, ever.
- Windows shows your disc by the Disc Name you type, in full up to 16 characters.
- And way more, [see below](#whats-new-in-151).

## What you need

- Windows 10 or 11
- Nothing else to install. `Rialto.exe` carries Inno Setup 6.5.4, which builds the installer, and mkisofs, which writes the disc image.
- In a future update, Rialto will add support for [Installway](https://github.com/Tooltip-Focus/Installway) and custom installer integration.
- Mac and Linux support is coming in a future update too: Rialto itself, and a disc menu and installer for Mac and Linux players.

If you already have [Inno Setup](https://jrsoftware.org/isdl.php) 6 or 7, `oscdimg` from the [Windows ADK](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install), or `mkisofs` on your PATH, Rialto uses yours. The log says which tool built the installer and which wrote the disc image.

Inno Setup is free. Its makers ask businesses and freelancers who earn more than USD 5,000 a year to [buy a license](https://jrsoftware.org/isorder.php). That is why Rialto's log may show Inno Setup's "Non-commercial use only" line. The installers you make carry no such line. The licenses of the tools Rialto carries, and where their source is, are in [licenses/THIRD-PARTY.txt](licenses/THIRD-PARTY.txt).

## Three steps to a disc

1. Put your game in a folder of its own (the `input` folder is a good home), then open Rialto and Browse to it.
2. Fill in your game's name and art. Hover over anything for help.
3. Preview Disc Menu, then Build Game Installer. Your ISO lands in `output`. Write it to disc with any disc-writing tool and hand somebody your game.

Want to see a menu first? The download has a sample: click **Load Profile** and open `templates\Sample Game.json`, Browse to `input\SampleGame`, then click **Preview Disc Menu**.

## Three ways to get Rialto

- **The installer.** Run `Rialto-1.5.1-Setup.exe` from the [latest release](https://github.com/playtabegg/rialto1.5/releases/latest). Rialto goes in your own user folder, with a Start Menu shortcut and a desktop shortcut, and opens at the end. A newer Setup later updates Rialto and keeps your settings and profiles.
- **The portable folder.** Get `Rialto-1.5.1-Disc-Maker.zip` from the same release, unzip the whole folder somewhere you can write to (not Program Files) and run `Rialto.exe`. Keep `menu.exe` beside it: it is the disc menu Rialto puts on every disc. `Rialto.exe` is signed by We The Indies, LLC; `menu.exe` is unsigned on purpose, and [SIGNING.md](SIGNING.md) says why.
- **From source.** `git clone` this repository and double-click `Rialto.pyw`. You need Python 3.9 to 3.12; Rialto installs its own packages on first run. Without a pre-built `menu.exe`, each build compiles its menu, which adds a minute or two.

## What's new in 1.5.1

- **An installer**: `Rialto-1.5.1-Setup.exe` installs Rialto in one step, and **Help > Check for a New Rialto** downloads the next one for you
- **Play Games**: on a disc of several games, the main menu lists every game, and a star puts favorites at the top
- **Controllers** in the disc menu: any Xbox-style pad, or a pad switched to its Xbox mode
- **The disc menu, fully translated**: all 34 languages now cover every label and popup, and the menu remembers the player's choice
- **Files to Place on the PC**: saves, settings or a mod's first-run files, copied to Documents, Saved Games, AppData or the install folder ([#3](https://github.com/playtabegg/rialto1.5/issues/3))
- **Pressed discs**: a master sheet and checksum file for the plant, and the layer break for a dual-layer DVD
- **Mini CD and Mini DVD** in Target Media
- **Compression you can pick**, a **Build Queue** for many discs in one run, and a window that fits laptops with Windows scaling turned up
- Every fix is in the [release notes](https://github.com/playtabegg/rialto1.5/releases/tag/v1.5.1)

## What's new in 1.5

- **More than one game on a disc**, with the Choose Your Game page in the menu
- **Preview Disc Menu**: your real menu, before you build anything
- **USB export** for players without a disc drive, with a Start Here file
- **Multi-disc sets**: pick your Target Media, and a game too big for one disc splits across as many discs as it needs
- **Blu-ray ready**: files over 4 GB switch to UDF, and the capacity check says which discs your build fits
- **Windows, Mac and Linux on one disc**, set under Disc Extras
- **An Add to Steam button** puts the installed game in the player's Steam library. Steam needs to be closed first, and the menu shows how
- **Import from GOG** offline installers
- **.msix export**, with a Start Menu entry and a clean uninstall
- **A Mods button** that runs your game's mod tool, from the disc and after installing
- **A Compatibility Mode button** for a second way to start, such as an OpenGL mode
- **Bring-your-own code signing** through Azure Artifact Signing, about $10 a month: set it up once, tick Sign Final Build, and every build signs itself with your name ([signing guide](SIGNING.md))

<details>
<summary><strong>Troubleshooting and running from source</strong></summary>

**The pre-build check says there is no installer compiler or no disc image tool.** This copy of `Rialto.exe` is missing the tools it carries. Download Rialto again and keep the whole folder. You can also install Inno Setup 6, or the Windows ADK with Deployment Tools ticked.

**Rialto wrote a ZIP and says no disc was made.** Every disc image tool it tried failed. The lines above it in the log name each tool and what went wrong. Check free disk space and that no scanner is holding the build folder, then build again.

**The log says "Non-commercial use only".** That line comes from Inno Setup. Its makers ask businesses that earn more than USD 5,000 a year to buy a license. Your installer carries no such line.

**From source, the log says a tool is missing.** Run `python tools-dev/fetch_helpers.py` once. It copies the carried tools into `helpers\` from an installed Inno Setup 6.5.4 and `C:\cdrtools`, and checks each file. Or install Inno Setup and an ISO tool.

**Preview Disc Menu can't find `menu.exe`.** Unzip the whole folder again and keep the files together.

**The download needs no Python.** `Rialto.exe` carries its own Python and packages, and never touches the Python on your PC.

**Running from source** needs 64-bit Python 3.9 to 3.12 from [python.org](https://www.python.org/downloads/), installed with "Add python.exe to PATH" ticked. If the Microsoft Store opens when Python should run, you only have Windows' placeholder: install the real one. On first run Rialto asks once, then runs `pip install -r requirements.txt` into the Python that started it. There is no venv; make and activate your own if you want one. Delete the hidden `.deps_installed` file to force a reinstall. If nothing happens when you double-click `Rialto.pyw`, run `scripts\debug_rialto.bat` to see the error.

**What is where in the repository.** `Rialto.pyw` is the app. `rialto\` holds the modules it imports: signing, the MSIX export and the update check. `packaging\` holds the specs that build `Rialto.exe` and `menu.exe` with PyInstaller (`pyinstaller packaging\rialto.spec`, run from this top folder). `scripts\` holds two launchers, and `tools-dev\` the harnesses. `helpers\MANIFEST.json` pins the tools Rialto carries, and `licenses\` holds their license texts.

**Disclaimer.** Rialto is offered as-is, with no warranty (see [LICENSE](LICENSE)). It keeps its settings, downloads and builds in its own folder, uses Windows' temp folder while it works, and writes elsewhere only when you ask: a desktop shortcut, a USB export, or a bonus or mods folder in your game folder. It never uploads your game; code signing sends Microsoft a fingerprint of each file, never the file itself. Keep your own backup of your game, and check the ISO before you send a disc to a duplicator. Bug reports are welcome on the [issue tracker](https://github.com/playtabegg/rialto1.5/issues).

</details>

## Contributing

Contributions are welcome: fork, branch and open a pull request. If you change `Rialto.pyw`, run `python tools-dev/run_all.py` first; the harnesses catch most breakages in a few seconds.

## Credits and license

Built with love by Chandler at [We the Indies](https://x.com/WetheIndies). Keep physical media alive. Keep creating.

MIT License, see [LICENSE](LICENSE). The sound Rialto plays when a build finishes, `assets/success.wav`, is a jingle by Hicham Chahidi (MusicScreen.org) and is not covered by the MIT License.

Rialto Disc Maker was made over 1.5 years utilizing AI coding.
