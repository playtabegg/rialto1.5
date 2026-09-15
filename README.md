# Rialto 1.5

Turn your finished Windows game into a real disc: an autorun menu with your art, a proper installer, a disc icon and a ready-to-write ISO. Drop it in a drive and it feels like the games you grew up with.

Free and open source, built by [We the Indies](https://wetheindies.com).

**[Download Rialto 1.5](https://github.com/playtabegg/rialto1.5/releases/latest)** · [Signing guide](SIGNING.md) · The manual opens from **Help Guide** inside Rialto

## Easier from the very first minute

- Double-click `Rialto.exe` and everything works. No Python, and nothing to install for Rialto itself.
- Choose **File > Put Rialto on the Desktop** and launch Rialto like any normal app.
- Your game's exe keeps its own name. No renaming to game.exe, ever.
- The disc's name in Windows comes from Disc Name. Keep it to 16 characters and every PC shows all of it.
- And way more, [see below](#whats-new-in-15).

## What you need

- Windows 10 or 11
- **[Inno Setup 6](https://jrsoftware.org/isdl.php)**, free, builds the installer. Pick version **6**, not 7.
- **An ISO tool:** `oscdimg` from the free [Windows ADK](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install) (tick only **Deployment Tools**), or `mkisofs` on your PATH

**Rialto can't install these two for you, and it needs both to build a disc.** Once they are installed, Rialto finds them by itself. The download's `IMPORTANT - Before You Build.txt` walks through every click.

## Three steps to a disc

1. Put your game in a folder of its own (the `input` folder is a good home), then open Rialto and Browse to it.
2. Fill in your game's name and art. Hover over anything for help.
3. Preview Disc Menu, then Build Game Installer. Your ISO lands in `output`. Write it to disc with any disc-writing tool and hand somebody your game.

Want to see a menu first? The download has a sample: click **Load Profile** and open `templates\Sample Game.json`, Browse to `input\SampleGame`, then click **Preview Disc Menu**.

## Two ways to get Rialto

- **The download.** Get `Rialto-1.5-Disc-Maker.zip` from the [latest release](https://github.com/playtabegg/rialto1.5/releases/latest), unzip the whole folder and run `Rialto.exe`. Keep `menu.exe` beside it: it is the disc menu Rialto puts on every disc. `Rialto.exe` is signed by We The Indies, LLC; `menu.exe` is unsigned on purpose, and [SIGNING.md](SIGNING.md) says why.
- **From source.** `git clone` this repository and double-click `Rialto.pyw`. You need Python 3.9 to 3.12; Rialto installs its own packages on first run. Without a pre-built `menu.exe`, each build compiles its menu, which adds a minute or two.

## What's new in 1.5

- **More than one game on a disc**, with a Choose Your Game screen in the menu
- **Preview Disc Menu**: your real menu, before you build anything
- **USB export** for players without a disc drive, with a Start Here file
- **Multi-disc sets**: pick your Target Media, and a game too big for one disc splits across as many discs as it needs
- **Blu-ray ready**: files over 4 GB switch to UDF, and the capacity check says which discs your build fits
- **Windows, Mac and Linux on one disc**, set under Disc Extras
- **An Add to Steam button** puts the installed game in the player's Steam library. Steam has to be closed first, and the menu tells them so
- **Import from GOG** offline installers
- **.msix export**, with a Start Menu entry and a clean uninstall
- **A Mods button** that runs your game's mod tool, from the disc and after installing
- **A Compatibility Mode button** for a second way to start, such as an OpenGL mode
- **Bring-your-own code signing** through Azure Artifact Signing, about $10 a month: set it up once, tick Sign Final Build, and every build signs itself with your name ([signing guide](SIGNING.md))

<details>
<summary><strong>Troubleshooting and running from source</strong></summary>

**The build stops with "ISCC.exe not found".** Install Inno Setup 6, then build again.

**The build stops and says it found Inno Setup 7.** Rialto 1.5 builds with Inno Setup 6. Install 6 as well; the two sit side by side.

**Rialto wrote a ZIP and says no disc was made.** It couldn't find `oscdimg` or `mkisofs`, or the one it found failed; the lines above it in the log say which. Install the Windows ADK with Deployment Tools ticked.

**Preview Disc Menu can't find `menu.exe`.** Unzip the whole folder again and keep the files together.

**The download needs no Python.** `Rialto.exe` carries its own Python and packages, and never touches the Python on your PC.

**Running from source** needs 64-bit Python 3.9 to 3.12 from [python.org](https://www.python.org/downloads/), installed with "Add python.exe to PATH" ticked. If the Microsoft Store opens when Python should run, you only have Windows' placeholder: install the real one. On first run Rialto asks once, then runs `pip install -r requirements.txt` into the Python that started it. There is no venv; make and activate your own if you want one. Delete the hidden `.deps_installed` file to force a reinstall. If nothing happens when you double-click `Rialto.pyw`, run `debug_rialto.bat` to see the error.

**Disclaimer.** Rialto is offered as-is, with no warranty (see [LICENSE](LICENSE)). It keeps its settings, downloads and builds in its own folder, uses Windows' temp folder while it works, and writes elsewhere only when you ask: a desktop shortcut, a USB export, or a bonus or mods folder in your game folder. It never uploads your game; code signing sends Microsoft a fingerprint of each file, never the file itself. Keep your own backup of your game, and check the ISO before you send a disc to a duplicator. Bug reports are welcome on the [issue tracker](https://github.com/playtabegg/rialto1.5/issues).

</details>

## Contributors

<table>
  <tr>
    <td align="center" width="130"><a href="https://github.com/playtabegg"><img src="https://github.com/playtabegg.png?size=128" width="64" height="64" alt="Chandler"><br><b>Chandler</b></a><br><sub>We the Indies</sub></td>
    <td align="center" width="130"><a href="https://github.com/claude"><img src="https://github.com/claude.png?size=128" width="64" height="64" alt="Claude"><br><b>Claude</b></a><br><sub>Anthropic</sub></td>
  </tr>
</table>

Contributions are welcome: fork, branch and open a pull request. If you change `Rialto.pyw`, run `python tools-dev/run_all.py` first; the harnesses catch most breakages in a few seconds.

## Credits and license

Built with love by Chandler at [We the Indies](https://x.com/WetheIndies). Keep physical media alive. Keep creating.

MIT License, see [LICENSE](LICENSE). The sound Rialto plays when a build finishes, `assets/success.wav`, is a jingle by Hicham Chahidi (MusicScreen.org) and is not covered by the MIT License.

Rialto Disc Maker was made over 1.5 years utilizing AI coding.
