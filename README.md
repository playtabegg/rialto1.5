# Rialto - Game Disc Builder

**Create professional game disc ISOs for indie games.** Rialto automates the entire pipeline: game files in, ready-to-burn ISO out — complete with installer, menus, bonus content, and soundtrack CDs.

Built by [We the Indies](https://wetheindies.com). Free and open-source.

---

## Features

- **One-click ISO creation** — Select your game folder, fill in metadata, hit Build
- **Professional installers** — Inno Setup with 21+ language support, Start Menu entries, uninstaller
- **Custom game menus** — PyQt5-powered launcher with background images/videos, logo, language selection, and bonus content viewer thru file explorer
- **Dark/Light themes** — Modern UI with custom title bar
- **Profile system** — Save and reuse build configurations
- **Optional code signing** — SSL.com integration for signed installers

## Prerequisites

- **Windows 10/11**
- **Python 3.9+** (bundled in `python39/` or install separately)
- **Inno Setup 6** — [Download](https://jrsoftware.org/isdl.php) (required for installer creation)
- **mkisofs** or **oscdimg** — For ISO creation (recommended, has basic Python fallback)

## Quick Start

1. Clone this repository
2. Double-click `launch_rialto.bat` (sets up venv and launches automatically)
3. Select your game folder under `input/`
4. Fill in game metadata (title, developer, etc.)
5. Click **Build Installer + ISO**
6. Find your ISO in `output/`

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
```

### Building

1. Launch Rialto
2. Browse to your game folder
3. Enter metadata: Title, Developer, Publisher text
4. Optionally set background, logo, and icons
5. Click **Build Installer + ISO**

### Code Signing (Optional)

Rialto supports optional code signing via [SSL.com eSigner](https://www.ssl.com/esigner/). During the build flow, Rialto will pause and prompt you to sign your installer manually through the eSigner web interface.

## Project Structure

```
rialto_v1/
  Rialto.pyw              # Main application
  launch_rialto.bat        # Setup + launch script
  debug_rialto.bat         # Launch with console output
  requirements.txt         # Python dependencies
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
