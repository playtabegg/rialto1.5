"""
MSIX export for Rialto.

Packages a game folder as a modern Windows .msix installer using MakeAppx
from the Windows SDK. MSIX gives players a double-click install with a real
Start Menu entry and one-click uninstall from Windows Settings.

Important: Windows only installs SIGNED .msix packages. If Azure Artifact
Signing is configured in Rialto, the package is signed automatically and the
manifest publisher must match the certificate subject exactly. Unsigned
packages are still produced so you can sign them yourself later.
"""
import os
import re
import shutil
import subprocess
import tempfile
import xml.sax.saxutils

XML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="{identity}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>{display_name}</DisplayName>
    <PublisherDisplayName>{publisher_display}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
  <Applications>
    <Application Id="Game" Executable="{executable}" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{display_name}" Description="{description}"
                          BackgroundColor="transparent"
                          Square150x150Logo="Assets\\Square150x150Logo.png"
                          Square44x44Logo="Assets\\Square44x44Logo.png" />
    </Application>
  </Applications>
</Package>
"""


def find_makeappx():
    """Locate MakeAppx.exe from the Windows SDK (same home as signtool)."""
    found = shutil.which("makeappx.exe")
    if found:
        return found
    kit_roots = [
        r"C:\Program Files (x86)\Windows Kits\10\bin",
        r"C:\Program Files\Windows Kits\10\bin",
    ]
    for root in kit_roots:
        if not os.path.isdir(root):
            continue
        for version in sorted(os.listdir(root), reverse=True):
            candidate = os.path.join(root, version, "x64", "makeappx.exe")
            if os.path.exists(candidate):
                return candidate
    return None


def _xml(value):
    """Escape a value for AppxManifest.xml.

    Every field below is dropped into the manifest by str.format, and most of
    them land inside a double-quoted attribute. The escaping used to be done
    by hand and differed per field - the publisher escaped the quote, the
    display name and the description did not, and the version and the
    executable path escaped nothing - so a title with a quote in it could close
    the attribute and add its own. One function, applied to all of them, and it
    covers element text too (DisplayName appears in both places).
    """
    return xml.sax.saxutils.escape(str(value), {'"': "&quot;", "'": "&apos;"})


def safe_version(version):
    """MSIX wants a four-part numeric version and rejects anything else."""
    parts = re.findall(r"\d+", str(version or ""))[:4]
    parts = [p[:5] for p in parts] or ["1"]
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts)


def safe_identity(title):
    """Identity Name allows letters, digits, dots and dashes (3 to 50 chars)."""
    cleaned = re.sub(r"[^A-Za-z0-9.\-]", "", title) or "Game"
    return ("Rialto." + cleaned)[:50]


def _make_square_png(source_image, size, dest_path):
    from PIL import Image
    if source_image:
        img = source_image.copy()
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    else:
        canvas = Image.new("RGBA", (size, size), (34, 34, 34, 255))
    canvas.save(dest_path, "PNG")


def build_msix(game_dir, title, publisher_dn, publisher_display, version,
               executable_rel, art_path, out_msix, status=print):
    """
    Package game_dir as an .msix. Returns (success, message).

    executable_rel: the game's exe, relative to game_dir.
    art_path: png or ico used to generate the tile art (optional).
    publisher_dn: e.g. 'CN=Jane Smith' - must exactly match the signing
                  certificate subject for the package to install when signed.
    """
    makeappx = find_makeappx()
    if not makeappx:
        return False, ("MakeAppx.exe not found. Install the Windows SDK "
                       "(it also provides signtool): "
                       "https://developer.microsoft.com/windows/downloads/windows-sdk/")

    exe_abs = os.path.join(game_dir, executable_rel)
    if not os.path.exists(exe_abs):
        return False, f"Game exe not found: {executable_rel}"

    staging = tempfile.mkdtemp(prefix="rialto_msix_")
    try:
        status("Copying game files into the package layout...")
        package_root = os.path.join(staging, "layout")
        shutil.copytree(game_dir, package_root)

        assets_dir = os.path.join(package_root, "Assets")
        os.makedirs(assets_dir, exist_ok=True)
        source_image = None
        if art_path and os.path.exists(art_path):
            try:
                from PIL import Image
                source_image = Image.open(art_path).convert("RGBA")
            except Exception:
                source_image = None
        _make_square_png(source_image, 150, os.path.join(assets_dir, "Square150x150Logo.png"))
        _make_square_png(source_image, 44, os.path.join(assets_dir, "Square44x44Logo.png"))
        _make_square_png(source_image, 50, os.path.join(assets_dir, "StoreLogo.png"))

        manifest = XML_TEMPLATE.format(
            identity=_xml(safe_identity(title)),
            publisher=_xml(publisher_dn),
            version=safe_version(version),
            display_name=_xml(title),
            publisher_display=_xml(publisher_display or title),
            description=_xml(f"{title} - installed from disc, packaged with Rialto"),
            executable=_xml(executable_rel.replace("/", "\\")),
        )
        with open(os.path.join(package_root, "AppxManifest.xml"), "w", encoding="utf-8") as f:
            f.write(manifest)

        status("Packing with MakeAppx (this can take a minute on big games)...")
        if os.path.exists(out_msix):
            os.remove(out_msix)
        result = subprocess.run(
            [makeappx, "pack", "/o", "/d", package_root, "/p", out_msix],
            capture_output=True, text=True, timeout=1800,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if result.returncode != 0 or not os.path.exists(out_msix):
            output = (result.stdout or "") + (result.stderr or "")
            tail = output.strip().splitlines()[-1] if output.strip() else "unknown error"
            return False, f"MakeAppx failed: {tail}"
        return True, f"Created {os.path.basename(out_msix)}"
    except subprocess.TimeoutExpired:
        return False, "MakeAppx timed out after 30 minutes"
    except Exception as e:
        return False, f"MSIX packaging error: {e}"
    finally:
        shutil.rmtree(staging, ignore_errors=True)
