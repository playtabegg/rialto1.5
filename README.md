# Rialto - Game Disc Builder

**Create professional game disc ISOs for indie games.** Rialto automates the entire pipeline: game files in, ready-to-burn ISO out, complete with installer, menus, and bonus content.

Built by [We the Indies](https://wetheindies.com). Free and open-source.

---

## Features

- **One-click ISO creation**: select your game folder, fill in metadata, hit Build
- **Professional installers**: Inno Setup with 21+ language support, Start Menu entries, uninstaller
- **Custom game menus**: PyQt5-powered launcher with background images/videos, logo, language selection, and bonus content
- **Dark/Light themes**: modern UI with custom title bar
- **Profile system**: save and reuse build configurations
- **Optional code signing**: pause-and-sign flow works with any signing service for signed installers

## Prerequisites

- **Windows 10/11**
- **Python 3.9+ (64-bit)** from [python.org](https://www.python.org/downloads/), installed with **"Add python.exe to PATH"** ticked. 3.9 - 3.12 is the tested range. See [Troubleshooting](#troubleshooting--python-note) before you start.
- **Inno Setup 6**: [Download](https://jrsoftware.org/isdl.php) (required for installer creation)
- **mkisofs** or **oscdimg**: for ISO creation (recommended, has basic Python fallback)

## Quick Start

1. Install Python 3.9+ with **"Add python.exe to PATH"** ticked
2. Clone this repository
3. Double-click `launch_rialto.bat` (creates `venv/`, installs dependencies, then launches Rialto)
4. Select your game folder under `input/`
5. Fill in game metadata (title, developer, etc.)
6. Click **Build Installer + ISO**
7. Find your ISO in `output/`

## Usage

### Preparing Your Game

Place your game files in a folder under `input/`:
```
input/
  MyGame/
    MyGame.exe
    game_icon.ico       (optional)
    disc_icon.ico       (optional)
    background.png      (optional - menu background)
    game_logo.png       (optional - menu logo)
    bonus/              (optional - bonus content folder, opened via file explorer)
```

### Building

1. Launch Rialto
2. Browse to your game folder
3. Enter metadata: Title, Developer, Publisher text
4. Optionally set background, logo, and icons
5. Click **Build Installer + ISO**

### Code Signing (Optional)

Rialto supports optional code signing via [SSL.com eSigner](https://www.ssl.com/esigner/). During the build flow, Rialto will pause and prompt you to sign your installer manually through the eSigner web interface.

## Troubleshooting / Python note

**Rialto needs Python 3.9 or newer (64-bit), installed from [python.org](https://www.python.org/downloads/) with "Add python.exe to PATH" ticked on the first page of the installer.** 3.9 - 3.12 is the range Rialto is developed and tested against; newer releases generally work but are not tested, so if a dependency refuses to install, drop back to 3.12. If you already installed Python without the PATH option, re-run the installer, choose *Modify*, and enable it.

**What `launch_rialto.bat` does on first run:** it looks for Python on your PATH, creates a virtual environment in a `venv/` folder next to the script, installs everything in `requirements.txt` into it, drops a `venv\rialto_deps_ok.txt` marker, and starts Rialto. Later runs see the marker and skip straight to launching, so only the first run is slow. To force a clean reinstall, delete the `venv/` folder and run the script again. `debug_rialto.bat` does exactly the same thing but runs Rialto with a console window attached so you can read any error.

**If the window closes instantly or nothing happens:** run `debug_rialto.bat` instead and read the message. Both scripts now pause on every error rather than vanishing.

**Disclaimer:** Rialto is a free hobby project, offered as-is with no warranty (see [LICENSE](LICENSE)). It is developed and tested on Windows 10/11 with Python 3.9 - 3.12; other setups may not work. It writes only inside its own folder and the `input/`/`output/` folders, and it never uploads your game anywhere. Always keep your own backup of your game files, and check the ISO it produces before you send a disc to a duplicator. Bug reports are very welcome on the [issue tracker](https://github.com/playtabegg/rialto1/issues).

## Project Structure

```
rialto_v1/
  Rialto.pyw              # Main application
  launch_rialto.bat        # Setup + launch script (creates venv/ on first run)
  debug_rialto.bat         # Same, but launches with console output
  requirements.txt         # Python dependencies
  venv/                    # Created on first launch, not in the repo
  config.json              # App configuration
  rialto.spec              # PyInstaller build spec
  assets/
    bird_icon.ico          # App icon
    bird_logo.PNG          # Brand logo
    success.wav            # Build complete sound
  templates/               # Build profile templates
  input/                   # Game folders go here
  output/                  # Built ISOs appear here
```

## License

MIT License. See [LICENSE](LICENSE).

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Credits

Built with love by Chandler at [We the Indies](https://x.com/WetheIndies).

Keep physical media alive. Keep creating.

Originally built over three months using GPT-4. Polished and packaged for the masses by Claude Code and Opus 4.6.
