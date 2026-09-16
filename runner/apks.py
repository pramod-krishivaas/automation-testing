"""APK storage on this machine: Google Drive downloads, listing, and reading an
APK's name, version and icon.

APKs live outside the repo in a machine-wide data dir, so a fresh clone doesn't
lose them: %PROGRAMDATA%\\TestAutomationPlatform\\apks on Windows (shared across
user accounts), ~/.test-automation-platform/apks elsewhere. PLATFORM_DATA_DIR
moves the whole data dir (the knob CI should set); APK_STORAGE_DIR moves just
the APKs.
"""

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

import gdown
from androguard.core.apk import APK
from dotenv import load_dotenv

load_dotenv()


def _default_data_root() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    if os.name == "nt" and program_data:
        return Path(program_data) / "TestAutomationPlatform"
    return Path.home() / ".test-automation-platform"


DATA_ROOT = Path(os.getenv("PLATFORM_DATA_DIR") or _default_data_root()).expanduser().resolve()
APK_STORAGE_DIR = Path(os.getenv("APK_STORAGE_DIR") or DATA_ROOT / "apks").expanduser().resolve()

# Drive file ids in share links (…/file/d/<id>/view?usp=sharing) and in
# open?id= / uc?id= links.
_DRIVE_FILE_ID = re.compile(r"(?:/file/d/|/d/|[?&]id=)([A-Za-z0-9_-]{10,})")


def list_apks() -> list[str]:
    APK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.name for p in APK_STORAGE_DIR.iterdir() if p.suffix.lower() in (".apk", ".apks"))


def resolve_apk(name: str) -> Path:
    """Resolve a requested APK filename inside the storage dir.

    The name comes from the UI, so it is reduced to a bare filename first; a `../`
    in it would otherwise reach anywhere on this machine.
    """
    safe = os.path.basename(str(name or "").strip())
    if not safe or safe in (".", ".."):
        raise ValueError(f"Invalid APK name: {name!r}")
    return APK_STORAGE_DIR / safe


def _developer_from_package(package_name: str) -> str:
    # APKs carry no clean developer field; infer one from the package prefix.
    parts = [p for p in package_name.split(".") if p and p not in {"com", "in", "org", "net", "io"}]
    return parts[0].replace("_", " ").title() if parts else "Unknown Developer"


def describe_apk(apk_path: str) -> tuple[dict, Optional[bytes]]:
    """Name/package/version metadata and the raw icon bytes, from one parse of the APK."""
    try:
        app = APK(apk_path)
    except Exception as exc:
        print(f"Failed to read APK info: {exc}")
        return {}, None

    package_name = app.get_package() or ""
    version_name = app.get_androidversion_name()
    version_code = app.get_androidversion_code()
    info = {
        "app_name": app.get_app_name() or "Unknown App",
        "package_name": package_name,
        "app_version": version_name or str(version_code or "Unknown Version"),
        "developer_name": os.getenv("APP_DEVELOPER_NAME", "").strip() or _developer_from_package(package_name),
        "version_name": version_name,
        "version_code": version_code,
    }

    icon = None
    try:
        icon_name = app.get_app_icon()
        icon = app.get_file(icon_name) if icon_name else None
    except Exception as exc:
        print(f"Failed to extract icon: {exc}")
    return info, icon or None


class _ProgressCapture:
    """Stands in for stderr so gdown's tqdm progress lines reach a callback."""

    def __init__(self, callback: Callable[[str], None]):
        self.callback = callback

    def write(self, message: str) -> None:
        if message and message.strip():
            self.callback(message)

    def flush(self) -> None:
        pass


def download_apk(gdrive_url: str, progress_callback: Optional[Callable[[str], None]] = None) -> str:
    """Download an APK from Google Drive into the storage dir, keeping its original
    filename, and return its absolute path."""
    match = _DRIVE_FILE_ID.search(gdrive_url or "")
    if not match:
        raise Exception(
            "That isn't a Google Drive file link. In Drive, use the file's Share link "
            "(https://drive.google.com/file/d/<id>/view)."
        )
    APK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"⬇️ Starting download from GDrive: {gdrive_url}")

    original_stderr = sys.stderr
    tmp_path = None
    try:
        if progress_callback:
            sys.stderr = _ProgressCapture(progress_callback)

        # Pass the file id, not the link: gdown only understands share links from
        # 6.x on, and older versions name the file after the URL ("view?usp=
        # sharing…"), which Windows rejects. An output ending in a separator is a
        # directory, so the file keeps its name from Drive.
        tmp_path = gdown.download(id=match.group(1), output=str(APK_STORAGE_DIR) + os.sep, quiet=False)

        if not tmp_path or not os.path.exists(tmp_path):
            raise Exception("Download failed - gdown returned no path.")
        if os.path.getsize(tmp_path) < 1000:
            raise Exception("Download failed - File is too small (likely an HTML error page).")

        final_path = APK_STORAGE_DIR / os.path.basename(tmp_path)
        if os.path.abspath(tmp_path) != str(final_path):
            shutil.move(tmp_path, final_path)
        print(f"✅ APK Ready at: {final_path}")
        return str(final_path)

    except Exception as e:
        msg = str(e)
        print(f"❌ Error downloading APK: {msg}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        # Translate gdown's verbose errors into a concise, actionable message.
        low = msg.lower()
        if "public link" in low or "permission" in low or "anyone with the link" in low:
            raise Exception(
                "Google Drive file is not publicly accessible. In Drive open the file → "
                "Share → General access → set to 'Anyone with the link', then try again. "
                "(Or pick a file under 'Select Existing APK'.)"
            )
        if "too small" in low or "html error page" in low:
            raise Exception(
                "The downloaded file isn't a valid APK (got an HTML page). Make sure the "
                "Drive link points directly to the APK and is shared with 'Anyone with the link'."
            )
        raise Exception(f"APK download failed: {msg.splitlines()[0][:200]}")

    finally:
        sys.stderr = original_stderr
