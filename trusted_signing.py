"""
Azure Artifact Signing integration for Rialto.

The service was called Azure Trusted Signing until Microsoft renamed it to
Azure Artifact Signing in January 2026, when it went generally available. Same
service, same endpoints, same $9.99/month Basic tier; the portal resources are
now "Artifact Signing account" and the roles are "Artifact Signing Identity
Verifier" and "Artifact Signing Certificate Profile Signer". This module keeps
its old filename so existing signing_config.json files and imports keep working.

BYOK model: every Rialto user signs with their OWN Azure account.
One-time setup (see the signing guide):
  1. Create an Artifact Signing account + certificate profile (~$9.99/mo).
  2. Install the Azure CLI and run `az login` once.
  3. Enter endpoint / account / profile in Rialto's "Configure Signing" dialog.
After that, builds sign automatically - no upload/download, no per-build clicks.

The actual signing is standard Authenticode via signtool.exe with Microsoft's
dlib. That ships in the Microsoft.ArtifactSigning.Client NuGet package (formerly
Microsoft.Trusted.Signing.Client); Rialto downloads and caches it on first use,
falling back to the old package name for anyone behind a mirror that has not
picked up the rename.

Two things get signed per build, both with the author's own account: the
installer (setup.exe) and this build's own copy of the disc menu
(menu/menu.exe). See sign_staged_menu below for why the menu is signed per
build rather than once, upstream.
"""
import os
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile


def _base_dir():
    """Where the signing config and the cached dlib live.

    Frozen: beside Rialto.exe. Inside a bundle __file__ points into the
    sys._MEIPASS temp folder, which the bootloader deletes on exit - the saved
    signing details would vanish between runs and the ~20 MB dlib would be
    re-downloaded every single build.

    Source: the folder holding this module, unchanged.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "signing_config.json")
DLIB_CACHE_DIR = os.path.join(BASE_DIR, "tools", "TrustedSigning")
# New package first, old one as a fallback: the rename is recent enough that
# some corporate NuGet mirrors still only carry Microsoft.Trusted.Signing.Client.
NUGET_PACKAGE_URLS = (
    "https://www.nuget.org/api/v2/package/Microsoft.ArtifactSigning.Client",
    "https://www.nuget.org/api/v2/package/Microsoft.Trusted.Signing.Client",
)
NUGET_PACKAGE_URL = NUGET_PACKAGE_URLS[0]  # kept for anything importing the old name
# http, and it has to be: signtool rejects the https form of this outright with
# "Invalid Timestamp URL" and the build finishes unsigned. Switching it to https
# looked like a free privacy win - over http anyone on the path sees the hash
# and timing of every binary you build - but signtool's /tr client will not take
# it, so the choice is http or no signature. It costs nothing in integrity: an
# RFC-3161 reply is itself signed, so it cannot be forged over plain http
# either. Do not "fix" this to https again.
TIMESTAMP_URL = "http://timestamp.acs.microsoft.com"

# Every Artifact Signing endpoint is https and lives under this domain. Checked
# rather than assumed, because save_config used to write down whatever string
# it was handed - and the endpoint is where the token exchange goes.
ENDPOINT_DOMAIN_SUFFIX = ".codesigning.azure.net"


class SigningClientError(Exception):
    """The Microsoft signing add-on could not be obtained or could not be trusted."""

# Every region Artifact Signing runs in. The endpoint has to match the region
# the account and certificate profile were created in - a mismatch is the usual
# cause of a 403 at signing time, hours after everything looked correct.
ENDPOINTS = {
    "Brazil South": "https://brs.codesigning.azure.net",
    "Central US": "https://cus.codesigning.azure.net",
    "East US": "https://eus.codesigning.azure.net",
    "Japan East": "https://jpe.codesigning.azure.net",
    "Korea Central": "https://krc.codesigning.azure.net",
    "North Central US": "https://ncus.codesigning.azure.net",
    "North Europe": "https://neu.codesigning.azure.net",
    "Poland Central": "https://plc.codesigning.azure.net",
    "South Central US": "https://scus.codesigning.azure.net",
    "Switzerland North": "https://swn.codesigning.azure.net",
    "West Central US": "https://wcus.codesigning.azure.net",
    "West Europe": "https://weu.codesigning.azure.net",
    "West US": "https://wus.codesigning.azure.net",
    "West US 2": "https://wus2.codesigning.azure.net",
    "West US 3": "https://wus3.codesigning.azure.net",
}


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def endpoint_is_valid(endpoint):
    """True if `endpoint` is an https URL under the Artifact Signing domain.

    The endpoint is not cosmetic: it is the host the dlib exchanges the Azure
    login for a signing token with. Anything that can write signing_config.json
    could point that at its own server, and nothing during a build would look
    unusual. Checked by domain rather than against the ENDPOINTS table, so a
    region Microsoft adds after this release still works.
    """
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint:
        return False
    try:
        parts = urllib.parse.urlsplit(endpoint)
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    host = (parts.hostname or "").lower()
    return host.endswith(ENDPOINT_DOMAIN_SUFFIX) and len(host) > len(ENDPOINT_DOMAIN_SUFFIX)


def save_config(endpoint, account_name, certificate_profile):
    if not endpoint_is_valid(endpoint):
        raise ValueError(
            "That is not an Artifact Signing endpoint. Pick your region from the "
            "dropdown, or enter an https address ending in .codesigning.azure.net.")
    config = load_config()
    config.update({
        # Unchanged on purpose: renaming the value would invalidate every
        # signing_config.json already sitting next to a copy of Rialto.
        "provider": "azure_trusted_signing",
        "endpoint": endpoint.strip().rstrip("/"),
        "account_name": account_name.strip(),
        "certificate_profile": certificate_profile.strip(),
    })
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config


def is_configured():
    config = load_config()
    return bool(config.get("endpoint") and config.get("account_name")
                and config.get("certificate_profile"))


def find_signtool():
    """Locate a signtool.exe new enough to support /dlib (Windows 10 SDK+)."""
    found = shutil.which("signtool.exe")
    if found:
        return found
    kit_roots = [
        r"C:\Program Files (x86)\Windows Kits\10\bin",
        r"C:\Program Files\Windows Kits\10\bin",
    ]
    candidates = []
    for root in kit_roots:
        if not os.path.isdir(root):
            continue
        for version in sorted(os.listdir(root), reverse=True):
            candidate = os.path.join(root, version, "x64", "signtool.exe")
            if os.path.exists(candidate):
                candidates.append(candidate)
    # Prefer versioned SDK folders (sorted newest first); fall back to bin\x64
    for root in kit_roots:
        candidate = os.path.join(root, "x64", "signtool.exe")
        if os.path.exists(candidate):
            candidates.append(candidate)
    return candidates[0] if candidates else None


def find_dlib():
    if not os.path.isdir(DLIB_CACHE_DIR):
        return None
    for dirpath, _dirnames, filenames in os.walk(DLIB_CACHE_DIR):
        for name in filenames:
            if name.lower() == "azure.codesigning.dlib.dll" and "x64" in dirpath.lower():
                return os.path.join(dirpath, name)
    return None


def _resilient(status):
    """Wrap a status callback so console encodings that can't print emoji never break signing."""
    def _safe(message):
        try:
            status(message)
        except UnicodeEncodeError:
            try:
                status(message.encode("ascii", "ignore").decode().strip())
            except Exception:
                pass
    return _safe


def signed_by_microsoft(path):
    """True / False / None: does `path` carry a Microsoft Authenticode signature?

    None means "could not tell" - no signtool - which callers must not read as
    a yes. A timestamped signature stays valid after its certificate expires,
    and signtool already accounts for that, so this asks signtool rather than
    reading the certificate itself.
    """
    signtool = find_signtool()
    if not signtool or not os.path.isfile(path):
        return None
    try:
        result = subprocess.run([signtool, "verify", "/pa", "/v", path],
                                capture_output=True, text=True, timeout=120,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return None
    if result.returncode != 0:
        return False
    output = ((result.stdout or "") + (result.stderr or "")).lower()
    return "microsoft corporation" in output


def safe_extract_all(zipf, dest, status=None):
    """Extract a zip, refusing members that would land outside `dest`.

    Python 3.9-3.12's ZipFile.extractall trusts member paths, so a `..`
    component or an absolute name writes outside the destination (zip-slip).
    Each member is resolved with os.path.realpath and must stay under
    realpath(dest); absolute paths and `..` members are skipped with a warning.
    """
    log = status or print
    dest_real = os.path.realpath(dest)
    dest_prefix = dest_real if dest_real.endswith(os.sep) else dest_real + os.sep
    os.makedirs(dest_real, exist_ok=True)
    for info in zipf.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or name.startswith("\\") or (
                len(name) >= 2 and name[1] == ":"):
            log("⚠️ Skipping unsafe zip member (absolute path): %s" % info.filename)
            continue
        parts = [p for p in name.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            log("⚠️ Skipping unsafe zip member (.. path): %s" % info.filename)
            continue
        target = os.path.realpath(os.path.join(dest_real, *parts) if parts else dest_real)
        if target != dest_real and not target.startswith(dest_prefix):
            log("⚠️ Skipping unsafe zip member (escapes destination): %s" % info.filename)
            continue
        zipf.extract(info, dest_real)


def verify_dlib(dlib, status=print):
    """Raise unless `dlib` is a genuine Microsoft binary.

    signtool loads this DLL into its own process, and that process is holding
    an Azure login authorised to sign with the author's certificate profile.
    Whatever runs in there can sign anything it likes, under the author's name.

    That makes the download worth being careful about. It comes from nuget.org
    at whatever version is current, and TLS was the only thing standing behind
    it: a TLS-terminating proxy, a compromised package owner, or anyone who can
    write into the cache folder - which is gitignored, so nothing about it
    shows up in a diff - could substitute the file. Rialto is portable, so that
    folder is often in Downloads or on a shared drive.

    So the file is checked for a Microsoft signature before it is ever handed
    to signtool, and this fails closed. Not signing a build is recoverable;
    signing one with somebody else's code in the loop is not.
    """
    status = _resilient(status)
    trusted = signed_by_microsoft(dlib)
    if trusted is True:
        return dlib
    if trusted is None:
        raise SigningClientError(
            "Could not check the Microsoft signing add-on because signtool.exe was "
            "not found. Install the Windows SDK and try again.")
    raise SigningClientError(
        "The Microsoft signing add-on at %s does not carry a valid Microsoft "
        "signature, so it will not be used. Delete that folder and let Rialto "
        "download it again." % os.path.dirname(dlib))


def ensure_dlib(status=print):
    """Return path to a verified Azure.CodeSigning.Dlib.dll, downloading it on first use."""
    status = _resilient(status)
    dlib = find_dlib()
    if dlib:
        # Verified every time, not only after downloading: the cached copy is
        # what actually gets loaded, and ensure_dlib returns early on it.
        return verify_dlib(dlib, status)
    status("⬇️ Downloading the Microsoft Artifact Signing client (one-time, ~20 MB)...")
    os.makedirs(DLIB_CACHE_DIR, exist_ok=True)
    package_path = os.path.join(DLIB_CACHE_DIR, "client.nupkg")

    # One pinned downloader for everything Rialto fetches and then runs:
    # https only, nuget.org and its CDN only, a size cap, no partial file.
    from update.fetch import FetchProblem, fetch_to_file
    last_error = None
    for url in NUGET_PACKAGE_URLS:
        try:
            fetch_to_file(url, package_path,
                          hosts={"www.nuget.org", "api.nuget.org", "globalcdn.nuget.org"},
                          cap=64 * 1024 * 1024)
            break
        except FetchProblem as e:
            last_error = e
    else:
        raise last_error

    with zipfile.ZipFile(package_path) as archive:
        safe_extract_all(archive, DLIB_CACHE_DIR, status=status)
    try:
        os.remove(package_path)
    except Exception:
        pass
    dlib = find_dlib()
    if not dlib:
        return None
    try:
        verify_dlib(dlib, status)
    except SigningClientError:
        # Do not leave a package that failed the check sitting in the cache:
        # find_dlib would hand it straight back on the next build.
        shutil.rmtree(DLIB_CACHE_DIR, ignore_errors=True)
        raise
    status("✅ Artifact Signing client ready")
    return dlib


def _masked_account(upn):
    """Show enough of the signed-in account to recognise it, not enough to reuse.

    This lands in the Check My Setup dialog, which is exactly the thing people
    screenshot into a Discord thread when signing will not work - and the plain
    UPN is the author's real email address.
    """
    upn = (upn or "").strip()
    if "@" not in upn:
        return upn
    local, _, domain = upn.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def check_environment(pending=None):
    """
    Check everything signing needs, without signing anything.
    Returns a list of (label, ok, hint) tuples for the Check My Setup dialog.

    `pending` is what is typed into the dialog right now, as
    {"endpoint", "account_name", "certificate_profile"}. Without it this reads
    the saved file only, which is why pressing Check My Setup before Save used
    to report the details missing while they were plainly on screen.
    """
    results = []

    config = load_config()
    live = dict(config)
    unsaved = False
    if pending:
        typed = {k: (pending.get(k) or "").strip() for k in
                 ("endpoint", "account_name", "certificate_profile")}
        typed["endpoint"] = typed["endpoint"].rstrip("/")
        if all(typed.values()):
            unsaved = any(typed[k] != (config.get(k) or "").strip().rstrip("/")
                          if k == "endpoint" else typed[k] != (config.get(k) or "").strip()
                          for k in typed)
            live.update(typed)

    have_details = bool(live.get("endpoint") and live.get("account_name")
                        and live.get("certificate_profile"))
    if have_details:
        detail = f"Account '{live['account_name']}', profile '{live['certificate_profile']}'"
        if unsaved:
            detail += " - checked from what is on screen; click Save to keep it"
        results.append(("Signing details", True, detail))
    else:
        results.append(("Signing details", False,
                        "Fill in the region, account name and certificate profile, then Save"))

    signtool = find_signtool()
    results.append(("signtool (Windows SDK)", bool(signtool),
                    signtool or "Install the Windows SDK: https://aka.ms/windowssdk"))

    dlib = find_dlib()
    if not dlib:
        results.append(("Microsoft signing add-on", True,
                        "Not downloaded yet - happens automatically on your first signed build"))
    else:
        # signtool loads this into a process holding your signing credential,
        # so "it is present" is not the interesting question - see verify_dlib.
        trusted = signed_by_microsoft(dlib)
        if trusted is True:
            results.append(("Microsoft signing add-on", True, f"{dlib} (Microsoft-signed)"))
        elif trusted is None:
            results.append(("Microsoft signing add-on", False,
                            f"{dlib} - cannot be checked without signtool.exe"))
        else:
            results.append(("Microsoft signing add-on", False,
                            f"{dlib} is not Microsoft-signed and will not be used. "
                            f"Delete {DLIB_CACHE_DIR} and Rialto will fetch it again."))

    # Region and endpoint have to agree, or signing fails with a 403 long after
    # everything else looked correct. Catch it here instead.
    endpoint = (live.get("endpoint") or "").strip().rstrip("/")
    if endpoint:
        region = next((name for name, url in ENDPOINTS.items() if url == endpoint), None)
        if region:
            detail, ok = f"{endpoint} ({region})", True
        elif endpoint_is_valid(endpoint):
            # A region added after this release, rather than something wrong.
            detail, ok = f"{endpoint} - a region this version does not list yet", True
        else:
            detail, ok = (f"{endpoint} is not an Artifact Signing endpoint - pick your "
                          "region from the dropdown to fill it in"), False
        results.append(("Endpoint looks like a real region", ok, detail))

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    az = shutil.which("az") or shutil.which("az.cmd")
    if not az:
        results.append(("Azure CLI installed", False, "Install from https://aka.ms/azure-cli then run: az login"))
        results.append(("Signed in to Azure", False, "Install the Azure CLI first"))
    else:
        results.append(("Azure CLI installed", True, az))
        try:
            login = subprocess.run([az, "account", "show", "--query", "user.name", "-o", "tsv"],
                                   capture_output=True, text=True, timeout=30, creationflags=flags)
            if login.returncode == 0 and login.stdout.strip():
                results.append(("Signed in to Azure", True, _masked_account(login.stdout.strip())))
            else:
                results.append(("Signed in to Azure", False, "Run: az login (one time only)"))
        except Exception:
            results.append(("Signed in to Azure", False, "Run: az login (one time only)"))

    # Microsoft's dlib moved to .NET 8 with the Artifact Signing rename.
    dotnet = shutil.which("dotnet")
    dotnet_hint = "Install the .NET 8 runtime: https://dotnet.microsoft.com/download/dotnet/8.0"
    if not dotnet:
        results.append((".NET 8 runtime", False, dotnet_hint))
    else:
        try:
            runtimes = subprocess.run([dotnet, "--list-runtimes"], capture_output=True,
                                      text=True, timeout=30, creationflags=flags)
            versions = [line.split()[1] for line in (runtimes.stdout or "").splitlines()
                        if line.startswith("Microsoft.NETCore.App") and len(line.split()) > 1]
            majors = []
            for version in versions:
                try:
                    majors.append(int(version.split(".")[0]))
                except ValueError:
                    pass
            modern = any(major >= 8 for major in majors)
            if modern:
                detail = ", ".join(sorted({str(m) for m in majors if m >= 8}))
                results.append((".NET 8 runtime", True, f"found .NET {detail}"))
            else:
                found = f"only found .NET {max(majors)}. " if majors else ""
                results.append((".NET 8 runtime", False, found + dotnet_hint))
        except Exception:
            results.append((".NET 8 runtime", False, dotnet_hint))

    return results


def _is_link(path):
    """True if `path` is a junction or a symlink rather than a real entry.

    os.path.islink does not answer this on Windows: it reports False for a
    directory junction, which is the link authors actually make, because
    mklink /J needs no elevation and /D does. os.path.isjunction arrived in
    Python 3.12, so older Pythons read the reparse-point flag directly.
    """
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        return isjunction(path)
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400)  # REPARSE_POINT
    except (AttributeError, OSError):
        return False


def sign_staged_menu(menu_dir, status=print):
    """Sign THIS build's copy of menu.exe, the one staged into menu/.

    Rialto is open source and the generic menu.exe is the same file on every
    disc anyone builds with it, so the copy handed out publicly carries no
    signature: a signature there would put one studio's name on strangers'
    discs. Instead each author signs their own staged copy with their own
    Azure Artifact Signing account, and their disc says who actually made it.

    Only ever the staged copy. The shared source binary (dist/menu.exe or the
    one beside Rialto.exe) is never touched - staging copies it first, and the
    guard below refuses anything living outside menu_dir.

    Returns (signed, message). Never raises: an unsigned staged menu.exe is a
    perfectly good disc, and is what every author gets until they set signing
    up.
    """
    status = _resilient(status)
    menu_dir = os.path.abspath(menu_dir)
    staged = os.path.join(menu_dir, "menu.exe")
    if not os.path.isfile(staged):
        return False, "No staged menu.exe to sign (the batch menu fallback needs no signature)"
    # Belt and braces: never let a link turn "sign the staged copy" into "sign
    # the shared binary every other disc is built from". Three ways to be that
    # same file, and realpath only sees the first.
    if os.path.dirname(os.path.realpath(staged)) != os.path.realpath(menu_dir):
        return False, "Refusing to sign menu.exe: it is not a real file inside this build's menu folder"
    if _is_link(menu_dir):
        # A menu/ folder that is itself a junction defeats the check above:
        # both sides resolve to the same real place, so they compare equal
        # while pointing at the shared binary. A real build always makes this
        # folder with makedirs, so a link here is never something we staged.
        return False, "Refusing to sign menu.exe: this build's menu folder is a link, not a real folder"
    try:
        if os.stat(staged).st_nlink > 1:
            # A hard link IS the other file - same bytes on disk, one inode -
            # and realpath cannot tell, because there is nothing to resolve.
            return False, "Refusing to sign menu.exe: the staged copy is a hard link to another file"
    except OSError:
        pass
    if not is_configured():
        return False, ("Disc menu left unsigned - signing is not set up yet. "
                       "That is the normal do-it-yourself path and the disc works fine. "
                       "Configure Signing to put your own name on it (see SIGNING.md).")
    return sign_file(staged, status)


def sign_file(file_path, status=print):
    """
    Sign a file with Azure Artifact Signing. Returns (success, message).
    Never raises - callers rely on a clean fallback path.
    """
    status = _resilient(status)
    config = load_config()
    if not is_configured():
        return False, "Artifact Signing not configured (use Configure Signing)"
    if not endpoint_is_valid(config.get("endpoint", "")):
        return False, (
            "That is not an Artifact Signing endpoint. Pick your region from the "
            "dropdown, or enter an https address ending in .codesigning.azure.net.")
    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"

    signtool = find_signtool()
    if not signtool:
        return False, ("signtool.exe not found - install the Windows SDK "
                       "(https://developer.microsoft.com/windows/downloads/windows-sdk/)")

    try:
        dlib = ensure_dlib(status)
    except SigningClientError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Could not download the Artifact Signing client: {e}"
    if not dlib:
        return False, "Artifact Signing dlib not found after download"

    metadata = {
        "Endpoint": config["endpoint"],
        "CodeSigningAccountName": config["account_name"],
        "CertificateProfileName": config["certificate_profile"],
    }
    metadata_path = None
    try:
        fd, metadata_path = tempfile.mkstemp(suffix=".json", prefix="rialto_ts_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        cmd = [
            signtool, "sign",
            "/v",
            "/fd", "SHA256",
            "/tr", TIMESTAMP_URL,
            "/td", "SHA256",
            "/dlib", dlib,
            "/dmdf", metadata_path,
            file_path,
        ]
        status(f"🔐 Signing {os.path.basename(file_path)} via Azure Artifact Signing...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0:
            # Read the signature back rather than believing the exit code.
            # "Signed" is a claim that goes into the build log, onto the disc
            # and, in the end, to the buyer - and signtool has more than one
            # way to exit 0 without leaving a signature Windows will accept,
            # a timestamp server that quietly failed being the usual one.
            try:
                import ssl_signing
                verified = ssl_signing.is_signed(file_path)
            except Exception:
                verified = None
            if verified is False:
                return False, ("signtool reported success, but %s carries no signature "
                               "Windows accepts - treat this build as unsigned"
                               % os.path.basename(file_path))
            if verified is None:
                return True, "Signed with Azure Artifact Signing (signature could not be read back)"
            return True, "Signed successfully with Azure Artifact Signing"

        output = (result.stdout or "") + (result.stderr or "")
        hint = ""
        lowered = output.lower()
        if "azure cli" in lowered or "credential" in lowered or "authentication" in lowered:
            hint = " (are you logged in? run: az login)"
        elif "dotnet" in lowered or ".net" in lowered:
            hint = " (the .NET 8 runtime is required: https://dotnet.microsoft.com/download/dotnet/8.0)"
        tail = output.strip().splitlines()[-1] if output.strip() else "unknown error"
        return False, f"signtool failed: {tail}{hint}"
    except subprocess.TimeoutExpired:
        return False, "Signing timed out after 5 minutes"
    except Exception as e:
        return False, f"Signing error: {e}"
    finally:
        if metadata_path and os.path.exists(metadata_path):
            try:
                os.remove(metadata_path)
            except Exception:
                pass
