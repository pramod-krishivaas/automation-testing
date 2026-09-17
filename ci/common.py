"""Shared helpers for the CI orchestration scripts.

These scripts are the orchestration layer only: they decide WHAT runs and record
WHAT happened. Everything about HOW a test drives the app stays in the pytest
framework (tests/, pages/, locators/, conftest.py).
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_DIR = REPO_ROOT / "ci"
DEFAULT_CONFIG = CI_DIR / "pipeline.yml"

# Exit codes the workflow maps to a status (spec §26).
EXIT_OK = 0
EXIT_TEST_FAILURE = 1
EXIT_INFRASTRUCTURE = 2
EXIT_CONFIG = 3

# Failure categories reported to Slack (spec §12).
TEST_FAILURE = "TEST_FAILURE"
INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"


class CiError(Exception):
    """Fatal error carrying the exit code the workflow should surface."""

    def __init__(self, message: str, code: int = EXIT_CONFIG, category: str = ENVIRONMENT_FAILURE):
        super().__init__(message)
        self.code = code
        self.category = category


def log(message: str) -> None:
    # flush: GitHub Actions interleaves stdout with step output.
    print(message, flush=True)


def fail(message: str, code: int = EXIT_CONFIG, category: str = ENVIRONMENT_FAILURE) -> None:
    raise CiError(message, code, category)


def run_cli(main) -> None:
    """Run a script's main(), turning any failure into an ::error:: line + exit code.

    Unexpected crashes get an annotation too: annotations can be read without
    access to the run's logs, so the reason is visible on the run page.
    """
    try:
        sys.exit(main() or EXIT_OK)
    except CiError as exc:
        log(f"::error::{exc}")
        sys.exit(exc.code)
    except Exception as exc:  # a bug or missing dependency in the orchestration itself
        traceback.print_exc()
        log(f"::error::Unexpected {type(exc).__name__}: {exc}")
        sys.exit(EXIT_INFRASTRUCTURE)


# ── Config ──────────────────────────────────────────────────────────────────

def load_config(path: Optional[Path] = None) -> dict:
    path = Path(path or os.getenv("CI_PIPELINE_CONFIG") or DEFAULT_CONFIG)
    if not path.is_file():
        fail(f"Pipeline config not found: {path}")
    try:
        import yaml
    except ImportError:
        fail("PyYAML is required to read the pipeline config (pip install -r requirements.txt).")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def enabled_sorted(entries: list[dict], key: str) -> list[dict]:
    """Entries that are enabled, ordered by priority then name."""
    live = [e for e in (entries or []) if e.get("enabled", True)]
    return sorted(live, key=lambda e: (e.get("priority", 999), str(e.get(key, ""))))


# ── Run identity ────────────────────────────────────────────────────────────

def make_run_id(run_number: Optional[str] = None, now: Optional[datetime] = None) -> str:
    """RUN-<UTC date>-<GitHub run number>, e.g. RUN-20260916-001.

    The run number makes it unique without needing any stored counter, and it
    stays sortable and readable in Slack, artifact names and report URLs.
    """
    now = now or datetime.now(timezone.utc)
    try:
        sequence = int(run_number)
    except (TypeError, ValueError):
        # Manual/local invocation: fall back to the time of day.
        return f"RUN-{now:%Y%m%d}-{now:%H%M%S}"
    return f"RUN-{now:%Y%m%d}-{sequence:03d}"


def slugify(value: str, default: str = "app") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or default


# ── JSON files passed between jobs ──────────────────────────────────────────

def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        if default is None:
            fail(f"Could not read required file: {path}")
        return default


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ── GitHub Actions plumbing ─────────────────────────────────────────────────

def set_output(**values: Any) -> None:
    """Expose values to later steps/jobs via $GITHUB_OUTPUT."""
    target = os.getenv("GITHUB_OUTPUT")
    if not target:
        for key, value in values.items():
            log(f"[output] {key}={value}")
        return
    with open(target, "a", encoding="utf-8") as fh:
        for key, value in values.items():
            fh.write(f"{key}={value}\n")


def add_summary(markdown: str) -> None:
    """Append to the job summary shown on the workflow run page."""
    target = os.getenv("GITHUB_STEP_SUMMARY")
    if not target:
        log(markdown)
        return
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(markdown.rstrip() + "\n")


def redact_url(url: str) -> str:
    """A URL safe to print: keeps the host and path, drops query/fragment.

    Drive share links can carry tokens in the query string, and CI logs are
    readable by anyone with repo access (spec §4, §24).
    """
    if not url:
        return ""
    return re.sub(r"[?#].*$", "?…", str(url))
