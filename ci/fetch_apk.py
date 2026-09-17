"""Download the APK from Google Drive and prove it is a real APK.

Reuses runner/apks.py — the same Drive-link parsing, download and androguard
metadata read the local runner uses — so CI and laptop runs behave identically.

    python ci/fetch_apk.py --metadata ci-out/metadata.json --dir apk

Failures here are ENVIRONMENT failures (spec §12): the input was unusable, so
no emulator time is spent.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import zipfile
from pathlib import Path

from common import (
    ENVIRONMENT_FAILURE,
    EXIT_CONFIG,
    REPO_ROOT,
    fail,
    log,
    read_json,
    redact_url,
    run_cli,
    set_output,
    slugify,
    write_json,
)

# The runner package holds the Drive/APK helpers this reuses.
sys.path.insert(0, str(REPO_ROOT))

MIN_APK_BYTES = 1_000_000  # anything smaller is an error page, not a build


def _predictable_name(metadata: dict, downloaded: Path) -> str:
    """<app>-<version>-<build>.apk, so the artifact is self-describing (spec §4.8)."""
    # Keep the dots in the version: krishivaas-2.5.1-125.apk, not krishivaas-2-5-1-125.apk.
    version = "".join(ch if ch.isalnum() or ch == "." else "-"
                      for ch in str(metadata.get("app_version") or "")).strip("-.")
    parts = [slugify(metadata.get("app_name"), "app"), version]
    if metadata.get("build_id"):
        parts.append(slugify(metadata["build_id"], ""))
    name = "-".join(p for p in parts if p)
    return f"{name}{downloaded.suffix or '.apk'}" if name else downloaded.name


def validate(path: Path) -> dict:
    """Confirm the file is an APK and describe it, or fail with the reason."""
    size = path.stat().st_size if path.is_file() else 0
    if not size:
        fail(f"Downloaded APK is empty: {path.name}", EXIT_CONFIG, ENVIRONMENT_FAILURE)
    if size < MIN_APK_BYTES:
        fail(f"Downloaded file is only {size} bytes — that is an error page, not an APK.",
             EXIT_CONFIG, ENVIRONMENT_FAILURE)
    # An APK is a zip holding AndroidManifest.xml; check before androguard so a
    # corrupt download gives a clear message instead of a parser traceback.
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        fail(f"{path.name} is not a valid APK (not a zip archive).", EXIT_CONFIG, ENVIRONMENT_FAILURE)
    if "AndroidManifest.xml" not in names:
        fail(f"{path.name} has no AndroidManifest.xml — not an Android APK.",
             EXIT_CONFIG, ENVIRONMENT_FAILURE)

    from runner.apks import describe_apk

    info, _icon = describe_apk(str(path))
    if not info.get("package_name"):
        fail(f"Could not read a package name from {path.name}; the APK looks corrupt.",
             EXIT_CONFIG, ENVIRONMENT_FAILURE)

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)

    return {
        "file_name": path.name,
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 2),
        "sha256": digest.hexdigest(),
        "package_name": info.get("package_name", ""),
        "app_name": info.get("app_name", ""),
        "version_name": info.get("version_name") or info.get("app_version") or "",
        "version_code": str(info.get("version_code") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default="ci-out/metadata.json")
    parser.add_argument("--dir", default="apk", help="where the APK is placed for the artifact")
    args = parser.parse_args()

    metadata = read_json(args.metadata)
    target_dir = Path(args.dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # runner/apks.py downloads into APK_STORAGE_DIR; point that at the workspace
    # so the file lands where the artifact upload expects it.
    os.environ["APK_STORAGE_DIR"] = str(target_dir)
    from runner.apks import download_apk

    log(f"Downloading APK from {redact_url(metadata['apk_url'])}")
    try:
        downloaded = Path(download_apk(metadata["apk_url"]))
    except Exception as exc:
        fail(f"Google Drive download failed: {exc}", EXIT_CONFIG, ENVIRONMENT_FAILURE)

    final = downloaded.with_name(_predictable_name(metadata, downloaded))
    if final != downloaded:
        downloaded.replace(final)

    info = validate(final)
    info["path"] = str(final)
    write_json(target_dir / "apk-info.json", info)

    log(f"APK ready       : {info['file_name']} ({info['size_mb']} MB)")
    log(f"Package         : {info['package_name']} {info['version_name']} ({info['version_code']})")
    log(f"SHA-256         : {info['sha256']}")

    set_output(apk_path=str(final), apk_name=info["file_name"],
               package_name=info["package_name"], apk_size_mb=str(info["size_mb"]))
    return 0


if __name__ == "__main__":
    run_cli(main)
