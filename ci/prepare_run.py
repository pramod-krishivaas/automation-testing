"""Turn the trigger into a RUN_ID and a metadata file the whole pipeline uses.

Accepts either structured fields (repository_dispatch client_payload, or
workflow_dispatch inputs) or the raw Slack message text, and writes
ci-out/metadata.json. Every later job reads that file, so the developer,
app, version and RUN_ID stay attached to the run from trigger to Slack result.

    python ci/prepare_run.py --payload "$PAYLOAD_JSON" --out ci-out/metadata.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

from common import (
    make_run_id,
    read_json,
    redact_url,
    run_cli,
    set_output,
    slugify,
    write_json,
    fail,
    log,
)

# "Developer: @john" style lines in a Slack message.
_FIELD_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z _-]{2,30})\s*:\s*(.+?)\s*$", re.MULTILINE)
# Slack renders a user mention as <@U123ABC> or <@U123ABC|john>.
_SLACK_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|([^>]+))?>")
# Slack wraps links as <https://…|label>; take the URL part.
_DRIVE_URL = re.compile(r"<?(https?://(?:drive|docs)\.google\.com/[^\s|>]+)")

_FIELD_ALIASES = {
    "developer": "developer",
    "dev": "developer",
    "app": "app_name",
    "application": "app_name",
    "app_name": "app_name",
    "version": "app_version",
    "app_version": "app_version",
    "build": "build_id",
    "build_id": "build_id",
    "environment": "environment",
    "env": "environment",
    "apk": "apk_url",
    "apk_url": "apk_url",
}

_PASSTHROUGH = (
    "developer", "developer_slack_id", "app_name", "app_version", "build_id",
    "environment", "apk_url", "slack_channel_id", "app_variants", "suite_selection",
    "emulator_device", "android_api_level",
)


def parse_slack_text(text: str) -> dict:
    """Pull the known fields out of a Slack message body."""
    found: dict[str, str] = {}
    for raw_key, raw_value in _FIELD_LINE.findall(text or ""):
        key = _FIELD_ALIASES.get(raw_key.strip().lower().replace(" ", "_"))
        if key and raw_value.strip():
            found[key] = raw_value.strip()

    mention = _SLACK_MENTION.search(text or "")
    if mention:
        found["developer_slack_id"] = mention.group(1)
        found.setdefault("developer", mention.group(2) or mention.group(1))

    # The APK line often puts the link on the next line, so search the whole body.
    url = _DRIVE_URL.search(text or "")
    if url:
        found["apk_url"] = url.group(1)
    elif found.get("apk_url"):
        link = _DRIVE_URL.search(found["apk_url"])
        found["apk_url"] = link.group(1) if link else found["apk_url"]
    return found


def collect(payload: dict) -> dict:
    """Structured payload fields win; anything missing is parsed from the text."""
    data = {key: str(payload[key]).strip() for key in _PASSTHROUGH
            if payload.get(key) not in (None, "")}
    text = payload.get("text") or payload.get("message") or ""
    if text:
        for key, value in parse_slack_text(text).items():
            data.setdefault(key, value)

    developer = data.get("developer", "")
    mention = _SLACK_MENTION.search(developer)
    if mention:  # "Developer: <@U123|john>"
        data["developer_slack_id"] = data.get("developer_slack_id") or mention.group(1)
        data["developer"] = mention.group(2) or mention.group(1)
    data["developer"] = data.get("developer", "").lstrip("@") or "unknown"
    return data


def build_metadata(payload: dict) -> dict:
    data = collect(payload)
    if not data.get("apk_url"):
        fail("No Google Drive APK URL in the trigger. Send `apk_url`, or a Slack "
             "message containing the Drive link.")

    run_id = (payload.get("run_id") or os.getenv("RUN_ID")
              or make_run_id(os.getenv("GITHUB_RUN_NUMBER")))
    app_name = data.get("app_name") or "App"
    server, repo = os.getenv("GITHUB_SERVER_URL", ""), os.getenv("GITHUB_REPOSITORY", "")
    run_number = os.getenv("GITHUB_RUN_ID", "")

    return {
        "run_id": run_id,
        "developer": data["developer"],
        "developer_slack_id": data.get("developer_slack_id", ""),
        "app_name": app_name,
        "app_slug": slugify(app_name),
        "app_version": data.get("app_version") or "unknown",
        "build_id": data.get("build_id") or "",
        "environment": data.get("environment") or "staging",
        "apk_url": data["apk_url"],
        "slack_channel_id": data.get("slack_channel_id", ""),
        # Optional per-run overrides of ci/pipeline.yml.
        "app_variants": data.get("app_variants", ""),
        "suite_selection": data.get("suite_selection", ""),
        "emulator_device": data.get("emulator_device", ""),
        "android_api_level": data.get("android_api_level", ""),
        "triggered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workflow_url": f"{server}/{repo}/actions/runs/{run_number}" if run_number else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", default=os.getenv("TRIGGER_PAYLOAD", "{}"),
                        help="JSON object: client_payload, workflow inputs, or {'text': '<slack message>'}")
    parser.add_argument("--out", default="ci-out/metadata.json")
    args = parser.parse_args()

    try:
        payload = json.loads(args.payload or "{}")
    except ValueError as exc:
        fail(f"Trigger payload is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        fail("Trigger payload must be a JSON object.")

    metadata = build_metadata(payload)
    write_json(args.out, metadata)

    log(f"RUN_ID          : {metadata['run_id']}")
    log(f"Developer       : {metadata['developer']} {metadata['developer_slack_id']}")
    log(f"App             : {metadata['app_name']} {metadata['app_version']} "
        f"(build {metadata['build_id'] or 'n/a'}, {metadata['environment']})")
    log(f"APK             : {redact_url(metadata['apk_url'])}")

    set_output(
        run_id=metadata["run_id"],
        app_name=metadata["app_name"],
        app_version=metadata["app_version"],
        apk_artifact=f"android-apk-{metadata['run_id']}",
        metadata_artifact=f"run-metadata-{metadata['run_id']}",
    )
    return 0


if __name__ == "__main__":
    run_cli(main)
