"""
Signature verification for Rialto's finished artifacts.

Named for SSL.com, which is how Rialto used to sign. It does not sign anything
any more - signing lives in trusted_signing.py - it only reads back whether the
signature that was just applied actually took, and says so in one line.

The signtool it uses is the one trusted_signing found, not a guess: this module
used to hardcode `Windows Kits\\10\\bin\\x64\\signtool.exe`, a path that does
not exist on a normal SDK install (the real one is under a versioned folder like
10.0.22621.0\\x64). So verification reported "SignTool not available" on every
machine, immediately after a signature that had in fact succeeded.
"""
import os
import subprocess


def _signtool():
    try:
        import trusted_signing
        found = trusted_signing.find_signtool()
        if found:
            return found
    except Exception:
        pass
    # Last resort, for anyone importing this module on its own
    import shutil
    return shutil.which("signtool.exe")


def verify_signature(file_path):
    """
    Verify the digital signature on a file.

    Args:
        file_path (str): Path to file to verify

    Returns:
        str: a one-line result, safe to print straight into the build log
    """
    signtool_path = _signtool()

    if not signtool_path:
        return "no signtool found, so the signature could not be read back (install the Windows SDK)"

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    try:
        cmd = [signtool_path, "verify", "/pa", "/all", "/v", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = (result.stdout or "") + (result.stderr or "")

        if result.returncode == 0:
            if "timestamp" in output.lower():
                return "signature verified, and timestamped"
            return "signature verified"

        lowered = output.lower()
        if "no signature" in lowered or "is not signed" in lowered:
            return "not digitally signed"
        tail = [line.strip() for line in output.splitlines() if line.strip()]
        return f"signature verification failed: {tail[-1] if tail else 'unknown error'}"

    except subprocess.TimeoutExpired:
        return "signature verification timed out"
    except Exception as e:
        return f"verification error: {e}"


def is_signed(file_path):
    """True if `file_path` carries a signature Windows would accept."""
    signtool_path = _signtool()
    if not signtool_path or not os.path.exists(file_path):
        return None  # unknown, which is not the same as unsigned
    try:
        result = subprocess.run([signtool_path, "verify", "/pa", file_path],
                                capture_output=True, text=True, timeout=60,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode == 0
    except Exception:
        return None
