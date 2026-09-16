"""Run the pytest suites for each app_variant, in priority order.

This is the orchestration layer described in spec §10/§11: it decides which
variant × suite combinations exist and invokes the EXISTING framework for each
one. It does not know how to drive the app — conftest.py, the page objects and
the locators do that.

Each combination runs as its own pytest session:

    pytest <login_entry> tests/test_suites/<type>/<variant>/ \
           --apk <apk> --target-role <variant> --test-type <type> ...

The login entry runs first so the shared login lands and switches to that
variant, and a fresh session means the driver fixture's fullReset reinstalls the
app — so no state leaks from the previous variant.

    python ci/run_suites.py --apk apk/app.apk --metadata ci-out/metadata.json
    python ci/run_suites.py --dry-run          # print the plan, run nothing
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import (
    EXIT_INFRASTRUCTURE,
    EXIT_OK,
    EXIT_TEST_FAILURE,
    INFRASTRUCTURE_FAILURE,
    REPO_ROOT,
    TEST_FAILURE,
    add_summary,
    enabled_sorted,
    fail,
    load_config,
    log,
    read_json,
    run_cli,
    set_output,
    write_json,
)

sys.path.insert(0, str(REPO_ROOT / "tests"))

# pytest's documented exit codes; anything else means pytest itself broke.
PYTEST_OK, PYTEST_TESTS_FAILED, PYTEST_INTERRUPTED = 0, 1, 2
PYTEST_INTERNAL_ERROR, PYTEST_USAGE_ERROR, PYTEST_NO_TESTS = 3, 4, 5

TAIL_LINES = 40  # kept per suite for the failure summary


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def build_plan(config: dict, metadata: dict) -> list[dict]:
    """Every variant × suite combination that has tests to run."""
    from test_type_config import folder_for_type, normalize_type_label

    variant_filter = {v.lower() for v in _split_csv(metadata.get("app_variants"))}
    suite_filter = {normalize_type_label(s) for s in _split_csv(metadata.get("suite_selection"))}
    suite_filter.discard(None)

    plan: list[dict] = []
    for variant in enabled_sorted(config.get("app_variants"), "name"):
        name = str(variant.get("name", "")).strip()
        if not name or (variant_filter and name.lower() not in variant_filter):
            continue
        for suite in enabled_sorted(config.get("suites"), "type"):
            label = normalize_type_label(suite.get("type"))
            if not label or (suite_filter and label not in suite_filter):
                continue
            folder = folder_for_type(label)
            if not folder:
                continue
            suite_dir = Path(folder) / name
            tests = sorted(suite_dir.glob("test_*.py")) if suite_dir.is_dir() else []
            plan.append({
                "variant": name,
                "suite": label,
                "path": str(suite_dir.relative_to(REPO_ROOT)) if suite_dir.is_relative_to(REPO_ROOT) else str(suite_dir),
                "test_files": len(tests),
                # Empty variant × type folders are normal: not every app has every
                # suite type yet. Skipping beats failing the run.
                "runnable": bool(tests),
            })
    return plan


def _result_files(results_dir: Path) -> set[str]:
    return {p.name for p in results_dir.glob("*-result.json")} if results_dir.is_dir() else set()


def _count(results_dir: Path, names: set[str]) -> dict:
    """Tally Allure result files: pytest writes one *-result.json per test."""
    counts = {"total": 0, "passed": 0, "failed": 0, "broken": 0, "skipped": 0}
    for name in names:
        try:
            with open(results_dir / name, encoding="utf-8") as fh:
                status = (json.load(fh).get("status") or "unknown").lower()
        except (OSError, ValueError):
            continue
        counts["total"] += 1
        if status in counts:
            counts[status] += 1
    return counts


def _clear_app_state(package: str) -> None:
    """Belt-and-braces state reset between variants (the driver's fullReset also
    reinstalls, but this also clears anything the installer left behind)."""
    if not package or not shutil.which("adb"):
        return
    try:
        subprocess.run(["adb", "shell", "pm", "clear", package],
                       capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"::warning::Could not clear {package} between variants: {exc}")


def run_one(entry: dict, args, metadata: dict, config: dict, results_dir: Path) -> dict:
    """Run one variant × suite pytest session and classify the outcome."""
    execution = config.get("execution") or {}
    command = [
        sys.executable, "-m", "pytest",
        execution.get("login_entry", "tests/test_cases/common_test_cases/test_login_pytest.py"),
        entry["path"],
        "--apk", str(Path(args.apk).resolve()),
        "--target-role", entry["variant"],
        "--test-type", entry["suite"],
        "--app-name", metadata.get("app_name", ""),
        "--app-version", metadata.get("app_version", ""),
        "--developer-name", metadata.get("developer", ""),
        "-p", "allure_pytest",
        "--alluredir", str(results_dir),
    ]
    # Credentials come from the environment (a secret in CI), never the command
    # line, so they cannot land in a log or a process listing.
    if os.getenv("LOGIN_PHONE"):
        command += ["--login-phone", os.environ["LOGIN_PHONE"]]
    if os.getenv("LOGIN_MPIN"):
        command += ["--login-mpin", os.environ["LOGIN_MPIN"]]
    command += [str(extra) for extra in (execution.get("pytest_extra_args") or [])]

    environment = {**os.environ, "PLATFORM_RUN_ID": metadata.get("run_id", ""),
                   "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}

    log(f"\n{'=' * 78}\n▶ {entry['variant']} · {entry['suite']}  ({entry['test_files']} file(s))\n{'=' * 78}")
    before = _result_files(results_dir)
    started = time.time()

    tail: list[str] = []
    process = subprocess.Popen(command, cwd=REPO_ROOT, env=environment, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               bufsize=1, errors="replace")
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        tail.append(line.rstrip())
        del tail[:-TAIL_LINES]
    code = process.wait()
    duration = round(time.time() - started, 1)
    counts = _count(results_dir, _result_files(results_dir) - before)

    if code == PYTEST_OK:
        status, category = "passed", None
    elif code == PYTEST_TESTS_FAILED:
        status, category = "failed", TEST_FAILURE
    elif code == PYTEST_NO_TESTS:
        status, category = "skipped", None
    else:
        # Interrupted / internal error / usage error: the framework or the
        # environment broke, not the app under test.
        status, category = "error", INFRASTRUCTURE_FAILURE

    log(f"◀ {entry['variant']} · {entry['suite']} → {status} "
        f"(exit {code}, {duration}s, {counts['passed']}P/{counts['failed'] + counts['broken']}F/{counts['skipped']}S)")

    return {**entry, "status": status, "category": category, "exit_code": code,
            "duration_seconds": duration, "tests": counts,
            "tail": tail if status in ("failed", "error") else []}


def summarize(results: list[dict], plan: list[dict], metadata: dict, started: float) -> dict:
    totals = {"total": 0, "passed": 0, "failed": 0, "broken": 0, "skipped": 0}
    for result in results:
        for key, value in result["tests"].items():
            totals[key] += value

    failed_tests = totals["failed"] + totals["broken"]
    infrastructure = any(r["category"] == INFRASTRUCTURE_FAILURE for r in results)
    executed = [r for r in results if r["status"] != "skipped"]

    if infrastructure:
        status, category = "INFRASTRUCTURE_FAILURE", INFRASTRUCTURE_FAILURE
    elif failed_tests or any(r["status"] == "failed" for r in results):
        status, category = "FAILED", TEST_FAILURE
    elif not executed or totals["total"] == 0:
        # Nothing ran: an empty matrix is a configuration problem, not a pass.
        status, category = "NO_TESTS", None
    else:
        status, category = "PASSED", None

    return {
        "run_id": metadata.get("run_id", ""),
        "app_name": metadata.get("app_name", ""),
        "app_version": metadata.get("app_version", ""),
        "status": status,
        "failure_category": category,
        "totals": {
            "total": totals["total"],
            "passed": totals["passed"],
            # Allure counts "broken" separately; for Slack it reads as a failure.
            "failed": failed_tests,
            "skipped": totals["skipped"],
        },
        "duration_seconds": round(time.time() - started, 1),
        "variants_executed": sorted({r["variant"] for r in executed}),
        "suites": results,
        "planned": plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", help="APK under test (required unless --dry-run)")
    parser.add_argument("--metadata", default="ci-out/metadata.json")
    parser.add_argument("--results", default="allure-results")
    parser.add_argument("--summary", default="ci-out/summary.json")
    parser.add_argument("--config", default=None)
    parser.add_argument("--package", default=os.getenv("APP_PACKAGE", ""),
                        help="app package id, cleared between variants")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = parser.parse_args()

    config = load_config(args.config)
    metadata = read_json(args.metadata, {} if args.dry_run else None) or {}
    plan = build_plan(config, metadata)

    runnable = [entry for entry in plan if entry["runnable"]]
    log(f"Planned {len(plan)} variant × suite combination(s); {len(runnable)} with tests:")
    for entry in plan:
        mark = "run " if entry["runnable"] else "skip"
        log(f"  [{mark}] {entry['variant']:<16} {entry['suite']:<12} {entry['path']} "
            f"({entry['test_files']} file(s))")

    if args.dry_run:
        write_json(args.summary, {"planned": plan})
        return EXIT_OK
    if not args.apk:
        fail("--apk is required (pass the APK downloaded in the prepare job).")
    if not runnable:
        fail("No variant × suite combination has any test files. Check ci/pipeline.yml "
             "against tests/test_suites/<type>/<variant>/.")

    results_dir = Path(args.results).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    strategy = (config.get("execution") or {}).get("failure_strategy", "continue")

    results: list[dict] = []
    for index, entry in enumerate(runnable):
        if index:
            _clear_app_state(args.package)
        result = run_one(entry, args, metadata, config, results_dir)
        results.append(result)
        if strategy == "stop_on_first_failure" and result["status"] in ("failed", "error"):
            log(f"::warning::failure_strategy=stop_on_first_failure — skipping the "
                f"remaining {len(runnable) - index - 1} combination(s).")
            break

    summary = summarize(results, plan, metadata, started)
    write_json(args.summary, summary)

    rows = "\n".join(
        f"| {r['variant']} | {r['suite']} | {r['status']} | {r['tests']['passed']} | "
        f"{r['tests']['failed'] + r['tests']['broken']} | {r['tests']['skipped']} | {r['duration_seconds']}s |"
        for r in results
    )
    add_summary(
        f"### Android automation · {summary['run_id']} — **{summary['status']}**\n\n"
        f"| Variant | Suite | Result | Passed | Failed | Skipped | Duration |\n"
        f"|---|---|---|---|---|---|---|\n{rows}\n"
    )
    set_output(status=summary["status"], failure_category=summary["failure_category"] or "",
               passed=summary["totals"]["passed"], failed=summary["totals"]["failed"],
               skipped=summary["totals"]["skipped"], total=summary["totals"]["total"])

    log(f"\nOverall: {summary['status']} — {summary['totals']['passed']} passed, "
        f"{summary['totals']['failed']} failed, {summary['totals']['skipped']} skipped "
        f"in {summary['duration_seconds']}s")

    if summary["failure_category"] == INFRASTRUCTURE_FAILURE:
        return EXIT_INFRASTRUCTURE
    return EXIT_TEST_FAILURE if summary["status"] in ("FAILED", "NO_TESTS") else EXIT_OK


if __name__ == "__main__":
    run_cli(main)
