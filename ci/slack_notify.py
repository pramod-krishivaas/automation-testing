"""Send the Slack start / result / failure message for a run.

    python ci/slack_notify.py --event started   --metadata ci-out/metadata.json
    python ci/slack_notify.py --event completed --metadata … --summary … --report-url …
    python ci/slack_notify.py --event failed    --metadata … --category INFRASTRUCTURE_FAILURE \
        --reason "Android emulator failed to boot"

Posts via SLACK_BOT_TOKEN + a channel, or SLACK_WEBHOOK_URL. A notification
problem is reported but never fails the workflow — the run's real result is the
test outcome, and cleanup still has to happen (spec §27).
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

from common import log, read_json, run_cli

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"


def _duration(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def _who(metadata: dict) -> str:
    """A real Slack mention when we have the user id, else the plain name."""
    slack_id = metadata.get("developer_slack_id")
    return f"<@{slack_id}>" if slack_id else f"@{metadata.get('developer', 'unknown')}"


def _app_lines(metadata: dict) -> list[str]:
    lines = [
        f"*Developer:* {_who(metadata)}",
        f"*App:* {metadata.get('app_name', '—')}",
        f"*Version:* {metadata.get('app_version', '—')}",
    ]
    if metadata.get("build_id"):
        lines.append(f"*Build:* {metadata['build_id']}")
    lines.append(f"*Environment:* {metadata.get('environment', '—')}")
    lines.append(f"*RUN_ID:* `{metadata.get('run_id', '—')}`")
    return lines


def build_message(event: str, metadata: dict, summary: dict, report_url: str,
                  category: str, reason: str) -> tuple[str, list[dict]]:
    if event == "started":
        headline = "🚀 Android Automation Started"
        body = _app_lines(metadata) + ["", "*APK:* Received", "*Automation:* Started"]
    elif event == "failed":
        headline = "⚠️ Android Automation Failed"
        body = _app_lines(metadata) + [
            "", f"*Reason:* {reason or 'The workflow failed before tests could report a result.'}",
            f"*Status:* `{category or 'INFRASTRUCTURE_FAILURE'}`",
        ]
    else:
        totals = summary.get("totals") or {}
        status = summary.get("status", "UNKNOWN")
        headline = f"{'✅' if status == 'PASSED' else '❌'} Android Automation Completed"
        variants = summary.get("variants_executed") or []
        body = _app_lines(metadata)
        if variants:
            body += ["", "*Variants:*"] + [f"• {name}" for name in variants]
        body += [
            "",
            f"*Tests:* Total {totals.get('total', 0)} · "
            f"Passed {totals.get('passed', 0)} · "
            f"Failed {totals.get('failed', 0)} · "
            f"Skipped {totals.get('skipped', 0)}",
            f"*Duration:* {_duration(summary.get('duration_seconds', 0))}",
            f"*Status:* `{status}`",
        ]
        if summary.get("failure_category"):
            body.append(f"*Failure type:* `{summary['failure_category']}`")

    if report_url:
        body += ["", f"*Allure Report:* {report_url}"]
    if metadata.get("workflow_url"):
        body.append(f"*Workflow:* {metadata['workflow_url']}")

    text = f"{headline}\n" + "\n".join(body)
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": headline, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(body)}},
    ]
    return text, blocks


def _post(url: str, payload: dict, headers: dict) -> tuple[bool, str]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return False, str(exc)
    # A webhook answers "ok"; the Web API answers JSON with an "ok" field.
    if body.strip() == "ok":
        return True, body
    try:
        parsed = json.loads(body)
    except ValueError:
        return False, body[:200]
    return bool(parsed.get("ok")), parsed.get("error", body[:200])


def send(text: str, blocks: list[dict], channel: str) -> bool:
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()

    if token and channel:
        ok, detail = _post(SLACK_POST_URL, {"channel": channel, "text": text, "blocks": blocks},
                           {"Authorization": f"Bearer {token}"})
    elif webhook:
        ok, detail = _post(webhook, {"text": text, "blocks": blocks}, {})
    else:
        log("::warning::No SLACK_BOT_TOKEN+channel or SLACK_WEBHOOK_URL set — skipping Slack.")
        log(text)
        return False

    if not ok:
        # Never echo the token or webhook; `detail` is Slack's error code.
        log(f"::warning::Slack notification failed: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=("started", "completed", "failed"), required=True)
    parser.add_argument("--metadata", default="ci-out/metadata.json")
    parser.add_argument("--summary", default="")
    parser.add_argument("--report-url", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    args = parser.parse_args()

    metadata = read_json(args.metadata, {}) or {}
    summary = read_json(args.summary, {}) if args.summary else {}
    text, blocks = build_message(args.event, metadata, summary, args.report_url,
                                 args.category, args.reason)

    if args.dry_run:
        log(text)
        return 0

    channel = metadata.get("slack_channel_id") or os.getenv("SLACK_CHANNEL_ID", "")
    send(text, blocks, channel)
    return 0  # notification problems never fail the pipeline


if __name__ == "__main__":
    run_cli(main)
