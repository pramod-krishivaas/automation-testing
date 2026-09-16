"""Add this run's Allure report to the GitHub Pages site.

The site is a directory of past runs (checked out from the gh-pages branch), so
publishing must ADD to it rather than replace it (spec §17):

    <site>/index.html          run history, newest first
    <site>/runs.json           the data behind index.html
    <site>/RUN-20260916-001/   one Allure report per run
    <site>/RUN-20260916-002/

Allure history (spec §18): before generating, the `history` folder of the most
recent previous run OF THE SAME APP is copied into the results directory. That
is what gives Allure its trend graphs, and scoping it by app keeps one app's
trends out of another's.

    python ci/publish_report.py --site reports-site --results allure-results \
        --metadata ci-out/metadata.json --summary ci-out/summary.json
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import (
    EXIT_INFRASTRUCTURE,
    INFRASTRUCTURE_FAILURE,
    fail,
    load_config,
    log,
    read_json,
    run_cli,
    set_output,
    write_json,
)

RUN_DIR_PREFIX = "RUN-"


def copy_history(site: Path, results: Path, app_slug: str, runs: list[dict]) -> str | None:
    """Seed Allure's history from the previous run of the same app."""
    for run in runs:  # runs.json is newest first
        if run.get("app_slug") != app_slug:
            continue
        history = site / run.get("run_id", "") / "history"
        if history.is_dir():
            shutil.copytree(history, results / "history", dirs_exist_ok=True)
            log(f"Allure history carried over from {run['run_id']}")
            return run["run_id"]
    log("No previous report for this app — this run starts a fresh history.")
    return None


def generate(results: Path, destination: Path) -> None:
    if not shutil.which("allure"):
        fail("The `allure` CLI is not installed on this runner.",
             EXIT_INFRASTRUCTURE, INFRASTRUCTURE_FAILURE)
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["allure", "generate", str(results), "-o", str(destination), "--clean"],
        text=True, capture_output=True,
    )
    if completed.returncode != 0:
        fail(f"allure generate failed: {completed.stderr.strip() or completed.stdout.strip()}",
             EXIT_INFRASTRUCTURE, INFRASTRUCTURE_FAILURE)
    if not (destination / "index.html").is_file():
        fail(f"allure generate produced no index.html in {destination}",
             EXIT_INFRASTRUCTURE, INFRASTRUCTURE_FAILURE)


def prune(site: Path, runs: list[dict], keep: int) -> list[dict]:
    """Keep the newest `keep` runs; delete the rest from disk and from runs.json."""
    kept, dropped = runs[:keep], runs[keep:]
    for run in dropped:
        directory = site / str(run.get("run_id", ""))
        if directory.is_dir() and directory.name.startswith(RUN_DIR_PREFIX):
            shutil.rmtree(directory, ignore_errors=True)
            log(f"Retention: removed {directory.name}")

    # Also sweep report directories that runs.json no longer knows about, so a
    # failed publish can't leave an orphan behind forever.
    known = {str(run.get("run_id")) for run in kept}
    for directory in site.iterdir():
        if directory.is_dir() and directory.name.startswith(RUN_DIR_PREFIX) and directory.name not in known:
            shutil.rmtree(directory, ignore_errors=True)
            log(f"Retention: removed orphaned {directory.name}")
    return kept


def write_index(site: Path, runs: list[dict], title: str) -> None:
    def cell(value) -> str:
        return html.escape(str(value if value not in (None, "") else "—"))

    rows = "\n".join(
        "        <tr>"
        f'<td><a href="{cell(run.get("run_id"))}/index.html">{cell(run.get("run_id"))}</a></td>'
        f'<td>{cell(run.get("app_name"))}</td>'
        f'<td>{cell(run.get("app_version"))}</td>'
        f'<td>{cell(run.get("build_id"))}</td>'
        f'<td class="s {html.escape(str(run.get("status", "")).lower())}">{cell(run.get("status"))}</td>'
        f'<td>{cell(run.get("passed"))}</td>'
        f'<td>{cell(run.get("failed"))}</td>'
        f'<td>{cell(run.get("skipped"))}</td>'
        f'<td>{cell(run.get("developer"))}</td>'
        f'<td>{cell(run.get("finished_at", "")[:16].replace("T", " "))}</td>'
        "</tr>"
        for run in runs
    )
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 14px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; padding: 32px 16px; }}
  main {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  p.sub {{ margin: 0 0 24px; opacity: .65; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid rgba(128,128,128,.28); white-space: nowrap; }}
  th {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; opacity: .7; }}
  td.s {{ font-weight: 700; }}
  td.s.passed {{ color: #059669; }}
  td.s.failed, td.s.infrastructure_failure, td.s.environment_failure, td.s.no_tests {{ color: #DC2626; }}
  a {{ color: #2563EB; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .empty {{ opacity: .6; padding: 24px 0; }}
</style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <p class="sub">{len(runs)} run(s) retained. Newest first.</p>
  {'<table><thead><tr><th>Run ID</th><th>App</th><th>Version</th><th>Build</th><th>Status</th>'
   '<th>Passed</th><th>Failed</th><th>Skipped</th><th>Developer</th><th>Finished (UTC)</th></tr></thead>'
   f'<tbody>{rows}</tbody></table>' if runs else '<p class="empty">No reports yet.</p>'}
</main>
</body>
</html>
""", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="reports-site", help="checked-out Pages site")
    parser.add_argument("--results", default="allure-results")
    parser.add_argument("--metadata", default="ci-out/metadata.json")
    parser.add_argument("--summary", default="ci-out/summary.json")
    parser.add_argument("--base-url", default="", help="GitHub Pages base URL")
    parser.add_argument("--retention", type=int, default=0, help="override pipeline.yml")
    parser.add_argument("--config", default=None)
    parser.add_argument("--skip-generate", action="store_true",
                        help="assemble the site without calling allure (for tests)")
    args = parser.parse_args()

    config = load_config(args.config)
    reports = config.get("reports") or {}
    retention = args.retention or int(reports.get("retention_runs", 30))

    metadata = read_json(args.metadata)
    summary = read_json(args.summary, {})
    run_id = metadata["run_id"]
    site = Path(args.site).resolve()
    site.mkdir(parents=True, exist_ok=True)
    results = Path(args.results).resolve()

    runs = read_json(site / "runs.json", [])
    if not isinstance(runs, list):
        runs = []

    if args.skip_generate:
        destination = site / run_id
        (destination / "history").mkdir(parents=True, exist_ok=True)
        (destination / "index.html").write_text(f"<!doctype html><title>{run_id}</title>\n", encoding="utf-8")
    else:
        if not results.is_dir() or not any(results.iterdir()):
            fail(f"No Allure results to publish at {results}", EXIT_INFRASTRUCTURE, INFRASTRUCTURE_FAILURE)
        copy_history(site, results, metadata.get("app_slug", ""), runs)
        generate(results, site / run_id)

    totals = (summary.get("totals") or {})
    runs = [run for run in runs if run.get("run_id") != run_id]  # re-publish overwrites
    runs.insert(0, {
        "run_id": run_id,
        "app_name": metadata.get("app_name", ""),
        "app_slug": metadata.get("app_slug", ""),
        "app_version": metadata.get("app_version", ""),
        "build_id": metadata.get("build_id", ""),
        "environment": metadata.get("environment", ""),
        "developer": metadata.get("developer", ""),
        "status": summary.get("status", "UNKNOWN"),
        "failure_category": summary.get("failure_category") or "",
        "passed": totals.get("passed", 0),
        "failed": totals.get("failed", 0),
        "skipped": totals.get("skipped", 0),
        "duration_seconds": summary.get("duration_seconds", 0),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workflow_url": metadata.get("workflow_url", ""),
    })

    runs = prune(site, runs, retention)
    write_json(site / "runs.json", runs)
    write_index(site, runs, str(reports.get("site_title", "Android Automation Reports")))
    # Pages serves the artifact as-is; without this, Jekyll drops Allure's
    # _-prefixed asset folders and the report renders blank.
    (site / ".nojekyll").touch()

    report_url = f"{args.base_url.rstrip('/')}/{run_id}/" if args.base_url else f"./{run_id}/"
    log(f"Published {run_id} → {report_url}  ({len(runs)} run(s) retained)")
    set_output(report_url=report_url, retained_runs=str(len(runs)))
    return 0


if __name__ == "__main__":
    run_cli(main)
