# tests/conftest.py
"""
Step capture — four-layer strategy (most reliable first):

  1. Query server GET /jira/steps/{test_name}  (exact key)
     Falls back to GET /jira/steps/default if test_name returns empty.
  2. Local in-process step buffer (_StepCapturingPlugin reads capstdout live)
  3. Live logcat scrape from device at failure time
  4. report.sections["Captured stdout call"] / capstdout
  (empty list if all fail)

─── STEP CAPTURE FIX ──────────────────────────────────────────────────────────
  Root cause:  _extract_steps_from_text only matched [FOUND] and [CLICK].
               Tests that use [STEP], [ACTION], [TAP], ✅ markers got 0 steps.
  Fix:  Expanded _STEP_PATTERNS to cover all common markers.

─── PYCACHE FIX ────────────────────────────────────────────────────────────────
  Root cause:  Python caches compiled .py → __pycache__/*.pyc.
               Stale .pyc loaded on next run → old Appium config → timeout.
  Fix (3 layers):
    1. sys.dont_write_bytecode = True   — set FIRST, before any import
    2. PYTHONDONTWRITEBYTECODE env var  — covers subprocesses
    3. _clean_pycache() in pytest_configure — wipes existing stale files
       before collection/import starts.

─── JIRA DATES FIX ────────────────────────────────────────────────────────────
  Root cause:  Dates and sprint captured locally but not sent to JIRA API.
  Fix:  Include start_date, end_date, sprint in payload to backend.
────────────────────────────────────────────────────────────────────────────────
"""

# ── MUST be the very first executable lines ───────────────────────────────────
import sys
sys.dont_write_bytecode = True          # Prevent Python writing NEW .pyc files
import sys, os
import logging

import os
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"   # Propagate to child processes

# ── Standard imports ──────────────────────────────────────────────────────────
import re
import json
import time
import shutil
import datetime
import requests as http_requests
from pathlib import Path
from typing import List, Optional

import socket as _socket
import pytest
import allure
from appium import webdriver
from appium.options.android import UiAutomator2Options

RUN_ID_CACHE = None
print("conftest loaded")
_THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from runner.discovery import normalize_match_key

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

_ticket_id:      str  = ""
_issue_counter:  int  = 0
_session_issues: list = []
_developer_name: str  = ""
_test_start_time: datetime.datetime = None  # Track test start time globally
_db_run_id:      int  = None  # DB TestRun id for this session (result storage)

# Per-test local step buffer — populated by _StepCapturingPlugin
_local_step_buffer: dict = {}   # { test_name: [step, ...] }
current_test_name: str  = ""


# ════════════════════════════════════════════════════════════════════════════
#  STEP EXTRACTION — expanded pattern set
#
#  FIX: Added [STEP], [ACTION], [TAP], [PRESSED], [TAPPED], ✅ markers so
#  that any test-side logging convention is captured, not just [FOUND].
# ════════════════════════════════════════════════════════════════════════════

# Each tuple: (compiled pattern, group index that holds the step label)
_STEP_PATTERNS: List[tuple] = [
    # [FOUND] name='Foo'  or  [FOUND] name="Foo"
    (re.compile(r"\[FOUND\]\s+name='([^']+)'",   re.IGNORECASE), 1),
    (re.compile(r'\[FOUND\]\s+name="([^"]+)"',   re.IGNORECASE), 1),
    # [CLICK] label  /  [TAP] label  /  [PRESSED] label  /  [TAPPED] label
    (re.compile(r'\[(?:CLICK|TAP|PRESSED|TAPPED)\]\s+(.+)', re.IGNORECASE), 1),
    # [STEP] Step description
    (re.compile(r'\[STEP\]\s+(.+)',   re.IGNORECASE), 1),
    # [ACTION] did something
    (re.compile(r'\[ACTION\]\s+(.+)', re.IGNORECASE), 1),
    # ✅ Step name  (emitted by helper wrappers)
    (re.compile(r'✅\s+(?:Step\s+)?[–—-]?\s*(.+)', re.IGNORECASE), 1),
]


# ════════════════════════════════════════════════════════════════════════════
#  PYCACHE CLEANUP
# ════════════════════════════════════════════════════════════════════════════
def _clean_pycache(root: str = ".") -> None:
    """
    Recursively delete every __pycache__ dir and *.pyc / *.pyo file under root.
    Called from pytest_configure — runs BEFORE any module is imported for tests.
    """
    removed_dirs = removed_files = 0
    for p in Path(root).rglob("__pycache__"):
        try:
            shutil.rmtree(p)
            removed_dirs += 1
        except Exception as exc:
            print(f"[PYCACHE] Could not remove {p}: {exc}")
    for ext in ("*.pyc", "*.pyo"):
        for p in Path(root).rglob(ext):
            try:
                p.unlink()
                removed_files += 1
            except Exception as exc:
                print(f"[PYCACHE] Could not remove {p}: {exc}")
    print(
        f"[PYCACHE] Cleaned {removed_dirs} __pycache__ dir(s) "
        f"and {removed_files} bytecode file(s) before session start."
    )


# ════════════════════════════════════════════════════════════════════════════
#  LOCAL BUFFER PLUGIN — captures steps live from pytest stdout
# ════════════════════════════════════════════════════════════════════════════
class _StepCapturingPlugin:
    """
    Registered as a pytest plugin in pytest_configure.
    After each test call phase it reads capstdout and feeds any
    recognised step lines into _local_step_buffer[test_name].
    """

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        test_name = report.nodeid.split("::")[-1]
        cap = getattr(report, "capstdout", "") or ""
        if not cap:
            return
        steps = _extract_steps_from_text(cap)
        if not steps:
            return
        existing = _local_step_buffer.get(test_name, [])
        for s in steps:
            if s not in existing:
                existing.append(s)
        _local_step_buffer[test_name] = existing
        print(f"[LOCAL_BUFFER] Stored {len(existing)} step(s) for {test_name}")


# ════════════════════════════════════════════════════════════════════════════
#  STEP EXTRACTION HELPERS
# ════════════════════════════════════════════════════════════════════════════
def _extract_steps_from_text(text: str) -> list:
    """
    Parse step markers from any text blob using all patterns in _STEP_PATTERNS.
    Deduplicates consecutive identical steps.
    """
    if not text:
        return []
    raw = []
    for line in text.splitlines():
        line = line.strip()
        for pattern, group in _STEP_PATTERNS:
            m = pattern.search(line)
            if m:
                step = m.group(group).strip()
                if step:
                    raw.append(step)
                break  # first matching pattern wins per line
    # dedup consecutive
    deduped = []
    for step in raw:
        if not deduped or step != deduped[-1]:
            deduped.append(step)
    return deduped


def _query_steps_endpoint(key: str) -> list:
    """GET /jira/steps/{key} → list, or [] on any error."""
    try:
        resp = http_requests.get(
            f"{BACKEND_URL}/jira/steps/{key}", timeout=4
        )
        if resp.status_code == 200:
            return resp.json().get("steps", [])
    except Exception as e:
        print(f"[WARN] Could not fetch steps from server (key={key}): {e}")
    return []


def _get_steps_from_server(test_name: str) -> list:
    """
    Layer 1: server query.
    Order: exact key → default bucket → retry both after 1s.
    """
    if not test_name:
        return []

    steps = _query_steps_endpoint(test_name)
    if steps:
        print(f"[STEPS] Server exact → {len(steps)} step(s) for {test_name}")
        return steps

    steps = _query_steps_endpoint("default")
    if steps:
        print(f"[STEPS] Server default → {len(steps)} step(s) for {test_name}")
        return steps

    time.sleep(1)

    steps = _query_steps_endpoint(test_name)
    if steps:
        print(f"[STEPS] Server exact (retry) → {len(steps)} step(s) for {test_name}")
        return steps

    steps = _query_steps_endpoint("default")
    if steps:
        print(f"[STEPS] Server default (retry) → {len(steps)} step(s) for {test_name}")
        return steps

    return []


def _get_steps_from_local_buffer(test_name: str) -> list:
    """Layer 2: in-process buffer populated by _StepCapturingPlugin."""
    steps = _local_step_buffer.get(test_name, [])
    if steps:
        print(f"[STEPS] Local buffer → {len(steps)} step(s) for {test_name}")
    return steps


def _get_steps_from_logcat(driver_obj) -> list:
    """
    Layer 3: scrape device logcat for step markers at failure time.
    """
    if not driver_obj:
        return []
    try:
        logs   = driver_obj.get_log("logcat")
        joined = "\n".join(entry.get("message", "") for entry in logs)
        steps  = _extract_steps_from_text(joined)
        if steps:
            print(f"[STEPS] Logcat → {len(steps)} step(s)")
        return steps
    except Exception as e:
        print(f"[STEPS] Logcat scrape failed: {e}")
        return []


def _get_steps_from_sections(report) -> list:
    """Layer 4: pytest captured stdout sections."""
    for header, content in getattr(report, "sections", []):
        if "stdout" in header.lower() and content:
            steps = _extract_steps_from_text(content)
            if steps:
                print(f"[STEPS] report.sections → {len(steps)} step(s)")
                return steps
    cap = getattr(report, "capstdout", "") or ""
    if cap:
        steps = _extract_steps_from_text(cap)
        if steps:
            print(f"[STEPS] report.capstdout → {len(steps)} step(s)")
            return steps
    return []


def _get_steps(item, report, test_name: str) -> list:
    """
    Full pipeline — tries all layers in order, returns first non-empty result.
    """
    steps = _get_steps_from_server(test_name)
    if steps:
        return steps

    steps = _get_steps_from_local_buffer(test_name)
    if steps:
        return steps

    driver_obj = item.funcargs.get("driver")
    steps = _get_steps_from_logcat(driver_obj)
    if steps:
        return steps

    steps = _get_steps_from_sections(report)
    if steps:
        return steps

    print(f"[WARN] No steps captured for {test_name}")
    return []


# ════════════════════════════════════════════════════════════════════════════
#  GENERAL HELPERS
# ════════════════════════════════════════════════════════════════════════════
def _make_ticket_id() -> str:
    return "RUN-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _make_issue_id() -> str:
    global _issue_counter
    _issue_counter += 1
    return f"ISS-{_issue_counter:03d}"


def _fetch_developer_name_from_jira() -> str:
    """The configured Jira assignee's display name, resolved by the backend, which holds the Jira credentials."""
    try:
        resp = http_requests.get(f"{BACKEND_URL}/test/jira/assignee-name", timeout=8)
        if resp.ok:
            name = (resp.json() or {}).get("name", "")
            if name:
                print(f"[JIRA] Developer name resolved: {name}")
                return name
    except Exception as e:
        print(f"[WARN] Could not fetch Jira user displayName: {e}")
    return ""


# ════════════════════════════════════════════════════════════════════════════
#  PYTEST HOOKS
# ════════════════════════════════════════════════════════════════════════════
def pytest_configure(config):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True          # overrides any existing handlers
    )
    """
    Earliest pytest hook — before collection, before any test module is imported.
    1. Wipe stale pycache
    2. Register the live step-buffer plugin
    """
    _clean_pycache(_PROJECT_ROOT)
    print("[PYCACHE] sys.dont_write_bytecode =", sys.dont_write_bytecode)
    print("[PYCACHE] PYTHONDONTWRITEBYTECODE  =",
          os.environ.get("PYTHONDONTWRITEBYTECODE", "NOT SET"))
    config.pluginmanager.register(_StepCapturingPlugin(), "step_buffer_plugin")


def pytest_addoption(parser):
    parser.addoption("--apk",            action="store", default=None)
    parser.addoption("--app-name",       action="store", default="Unknown App")
    parser.addoption("--app-version",    action="store", default="Unknown Version")
    parser.addoption("--developer-name", action="store", default="")
    # Target automation role chosen in the UI: regular_farmer | regular_client |
    # state_farmer | state_client. Used by the shared login/switch flow to detect
    # the landed app and switch to the intended one.
    parser.addoption("--target-role",    action="store", default=None)
    # Mobile number + MPIN provided in the UI to log in with (overrides accounts.json).
    parser.addoption("--login-phone",    action="store", default=None)
    parser.addoption("--login-mpin",     action="store", default=None)
    # Requested test types (comma-separated): Smoke,Regression,End-to-End,Sanity.
    # Consumed by pytest_collection_modifyitems (folder-precedence + DB test_types).
    parser.addoption("--test-type",      action="store", default=None)


def pytest_collection_modifyitems(config, items):
    """
    Filter collected tests by the requested test type(s) (--test-type), with a
    FOLDER-FIRST precedence so the two type mechanisms never conflict:

      • A test whose file lives under tests/test_suites/<type>/ is kept iff that
        folder's type is in the requested set. The DB is NOT consulted for it — the
        folder location is the sole authority (tests/test_type_config.py).
      • Every OTHER test falls back to the DB test_types tag: its function name is
        matched to a testcase_key (prefix-normalised via discovery.normalize_match_key)
        and kept iff its catalogued test_types intersect the requested set.

    No --test-type → no filtering at all (full collection; backward compatible). If
    the backend is unreachable the tag check fails OPEN (keeps the test) so a
    transient outage never silently drops shared/common tests.
    """
    raw = config.getoption("--test-type", None)
    if not raw:
        return  # backward compatible: no type filter requested → collect everything
    requested = {p.strip() for p in str(raw).split(",") if p.strip()}
    if not requested:
        return

    try:
        from tests.test_type_config import type_folder_for_path
    except ImportError:                       # when tests/ (not repo root) is the entry
        from test_type_config import type_folder_for_path

    # DB testcase_key -> {test_types} map, built LAZILY and once — and only if we
    # actually reach a non-folder test, so a folders-only run never asks the backend.
    _db = {"loaded": False, "by_key": {}}

    def _db_types_by_key():
        if _db["loaded"]:
            return _db["by_key"]
        _db["loaded"] = True
        try:
            resp = http_requests.get(f"{BACKEND_URL}/api/test-cases/type-tags", timeout=10)
            resp.raise_for_status()
            for key, types in resp.json()["items"].items():
                _db["by_key"][normalize_match_key(key)] = set(types or [])
        except Exception as e:
            print(f"[test-type] Type tags unavailable from the backend ({e}); shared/common tests won't be type-filtered.")
        return _db["by_key"]

    kept, deselected = [], []
    for item in items:
        file_path = str(getattr(item, "path", None) or getattr(item, "fspath", ""))
        folder_label = type_folder_for_path(file_path)

        if folder_label is not None:
            # Folder location is authoritative — keep iff its type was requested. Skip DB.
            (kept if folder_label in requested else deselected).append(item)
            continue

        # Not under a test_suites/<type>/ folder → decide by the DB test_types tag.
        by_key = _db_types_by_key()
        if not by_key:
            kept.append(item)   # DB unavailable → fail open (never silently drop)
            continue
        func_name = getattr(item, "originalname", None) or item.name.split("[")[0]
        tags = by_key.get(normalize_match_key(func_name), set())
        (kept if (tags & requested) else deselected).append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
        print(f"[test-type] {sorted(requested)} -> kept {len(kept)}, deselected {len(deselected)}.")


def pytest_sessionstart(session):
    global _ticket_id, _issue_counter, _developer_name, _db_run_id
    _ticket_id     = _make_ticket_id()
    _issue_counter = 0
    print(f"\n[TICKET] Session ticket_id: {_ticket_id}")
    _developer_name = _fetch_developer_name_from_jira()
    if _developer_name:
        print(f"[TICKET] Developer: {_developer_name}")

    # Open a DB TestRun so per-test results can be stored against catalogued cases.
    try:
        app_type = session.config.getoption("--target-role", None)
        app_name = _cfg_from_config(session.config, "--app-name", "")
        resp = http_requests.post(
            f"{BACKEND_URL}/api/test-runs/start",
            json={
                "app_type": app_type,
                "run_name": (f"Automation {app_name}".strip() or None),
                "environment": "device",
                "triggered_by": _developer_name or "automation",
            },
            timeout=5,
        )
        if resp.status_code in (200, 201):
            _db_run_id = resp.json().get("run_id")
            print(f"[RESULT] DB test run started: run_id={_db_run_id} (app_type={app_type})")
        else:
            print(f"[RESULT] Could not start DB run ({resp.status_code}); results won't be stored.")
    except Exception as e:
        print(f"[RESULT] Could not start DB run: {e}")


def _cfg_from_config(config, option: str, fallback: str) -> str:
    try:
        return config.getoption(option) or fallback
    except Exception:
        return fallback


def _record_result_to_db(item, report) -> None:
    """Best-effort: store one test's outcome against its catalogued TestCase."""
    if not _db_run_id:
        return
    try:
        failure_reason = _extract_error_only(report.longrepr) if report.failed else None
        payload = {
            "test_name": item.name,
            "status": report.outcome,          # passed / failed / skipped
            "execution_time": round(float(getattr(report, "duration", 0.0) or 0.0), 2),
            "failure_reason": failure_reason,
        }
        drv = item.funcargs.get("driver")
        if drv is not None:
            caps = getattr(drv, "capabilities", {}) or {}
            payload["device_name"] = caps.get("deviceName") or caps.get("udid")
            payload["os_version"] = str(caps.get("platformVersion") or "") or None
        http_requests.post(
            f"{BACKEND_URL}/api/test-runs/{_db_run_id}/result", json=payload, timeout=4
        )
    except Exception as e:
        print(f"[RESULT] Could not record result for {item.name}: {e}")


def pytest_runtest_setup(item):
    """
    Signal the server which test is starting so it buckets steps
    under the correct key (not 'default').
    Also pre-initialise the local buffer slot for this test.
    """
    global current_test_name, _test_start_time
    current_test_name = item.name
    _test_start_time = datetime.datetime.now()
    _local_step_buffer.setdefault(item.name, [])

    try:
        http_requests.post(
            f"{BACKEND_URL}/test/log-step",
            json={"message": f"[TEST_START:{item.name}]", "status": "INFO"},
            timeout=2,
        )
    except Exception:
        pass


# ── Appium readiness guard ────────────────────────────────────────────────────
def _wait_for_appium(host: str = "127.0.0.1", port: int = 4723,
                     timeout: int = 30, poll_interval: int = 2) -> None:
    """
    Poll Appium's TCP port before handing control to webdriver.Remote.

    Without this guard, webdriver.Remote raises a cryptic MaxRetryError /
    WinError 10061 when Appium hasn't finished starting yet (or was never
    started at all).

    Raises pytest.fail with a human-readable message so the developer knows
    exactly what to do instead of digging through urllib3 tracebacks.
    """
    deadline = time.monotonic() + timeout
    print(f"[Appium] Waiting for server at {host}:{port} (up to {timeout}s)…")
    while time.monotonic() < deadline:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex((host, port)) == 0:
                print(f"[Appium] ✅ Server is ready at {host}:{port}")
                return
        time.sleep(poll_interval)
    pytest.fail(
        f"\n\n[Appium] ❌ Server is NOT reachable at {host}:{port} after {timeout}s.\n"
        f"  → Start Appium first:  appium -p {port}\n"
        f"  → Or use the 'Start Server' button in the UI before running tests.\n"
    )


# ── Target-role fixture ───────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def target_role(request):
    """
    The automation role the UI asked us to test (regular_farmer | regular_client
    | state_farmer | state_client), passed via --target-role. Because the unified
    app redirects to a home screen by priority (state_client > state_farmer >
    regular_farmer > regular_client), the shared login lands on whichever role the
    number resolves to first; the switch step uses this value to reach the intended
    app. Returns None when not supplied (tests should then skip the switch step).
    """
    return request.config.getoption("--target-role")


@pytest.fixture(scope="session")
def login_phone(request):
    """Mobile number provided in the UI to log in with, or None (→ accounts.json)."""
    val = request.config.getoption("--login-phone")
    return val.strip() if val and val.strip() else None


@pytest.fixture(scope="session")
def login_mpin(request):
    """MPIN provided in the UI for the login number, or None (→ accounts.json)."""
    val = request.config.getoption("--login-mpin")
    return val.strip() if val and val.strip() else None


# ── Driver fixture ────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def driver(request):
    apk_path = request.config.getoption("--apk")
    if not apk_path:
        pytest.fail("No APK path provided!")
    if not os.path.exists(apk_path):
        pytest.fail(f"APK file not found at: {apk_path}")

    # Verify Appium is actually reachable before attempting a WebDriver session.
    # This converts the opaque MaxRetryError / WinError 10061 into a clear
    # pytest failure message telling the developer exactly what to do.
    _wait_for_appium()

    print(f"Initializing Appium with APK: {apk_path}")
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name   = "AndroidDevice"
    options.app           = apk_path

    options.set_capability("appium:noReset", False)
    options.set_capability("appium:fullReset", True)

    options.set_capability("appium:ignoreHiddenApiPolicyError", False)
    options.set_capability("appium:uiautomator2ServerLaunchTimeout", 60000)
    options.set_capability("appium:adbExecTimeout", 50000)
    options.set_capability("appium:newCommandTimeout", 300)
    options.set_capability("appium:autoGrantPermissions", False)

    drv = webdriver.Remote("http://127.0.0.1:4723", options=options)
    try:
        drv.get_log("logcat")
    except Exception:
        pass
    yield drv
    drv.quit()


# ── Metadata helpers ──────────────────────────────────────────────────────────
def _cfg(item, option: str, fallback: str) -> str:
    try:
        val = item.config.getoption(option)
        return val if val else fallback
    except Exception:
        return fallback


def _extract_feature(item) -> str:
    for marker in item.iter_markers(name="allure_label"):
        if marker.kwargs.get("label_type") == "feature":
            return str(marker.kwargs.get("value") or (marker.args[0] if marker.args else ""))
    return "Unknown Feature"


def _extract_module(item) -> str:
    name   = item.name.lower()
    nodeid = item.nodeid.lower()
    if "login"       in name or "login"       in nodeid: return "Login"
    if "onboarding"  in name or "onboarding"  in nodeid: return "Onboarding"
    if "addfarm"     in name or "addfarm"     in nodeid: return "Onboarding"
    if "marketplace" in name or "marketplace" in nodeid: return "Marketplace"
    if "cart"        in name or "cart"        in nodeid: return "Cart"
    if item.cls is not None:
        return item.cls.__name__
    return "Unknown Module"


def _extract_error_only(longrepr) -> str:
    if not longrepr:
        return "No error details"
    text = str(longrepr)
    error_lines, seen, unique = [], set(), []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("E "):
            error_lines.append(s[2:].strip())
        elif "pytest.fail" in s or (
            "assert" in s.lower()
            and not s.startswith("#")
            and not s.startswith("import")
        ):
            error_lines.append(s)
    for l in error_lines:
        if l not in seen:
            seen.add(l)
            unique.append(l)
    return "\n".join(unique) if unique else text.split("\n")[-1].strip() or "Test failed"


def _build_description(error_text: str, steps: list) -> str:
    parts = []
    if error_text and error_text.strip() and error_text != "No error details":
        parts.append(error_text.strip())
    if steps:
        parts.append(
            "\nSteps Executed:\n" +
            "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
        )
    return "\n".join(parts) if parts else "Test failed"


# ── Crash detection ───────────────────────────────────────────────────────────
def check_for_crashes(driver):
    try:
        logs = driver.get_log("logcat")
        sigs = [
            "fatal exception", "force removing activity", "androidruntime",
            "beginning of crash", "am_crash", "anr in", "vm aborting",
        ]
        crash_lines, capture = [], False
        for entry in logs:
            msg   = entry.get("message", "")
            lower = msg.lower()
            if not capture:
                if any(s in lower for s in sigs):
                    capture = True
                    crash_lines.append(f"CRASH START: {msg}")
            else:
                if len(crash_lines) < 80:
                    crash_lines.append(msg)
        return "\n".join(crash_lines) if crash_lines else None
    except Exception as e:
        print("Logcat crash detection failed:", e)
        return None


# ── Send payload to backend ───────────────────────────────────────────────────
def _send_payload_to_backend(payload: dict) -> None:
    print("JIRA_PAYLOAD_JSON:" + json.dumps(payload, ensure_ascii=False))
    try:
        resp = http_requests.post(
            f"{BACKEND_URL}/jira/payload",
            json=payload, timeout=5,
        )
        if resp.status_code == 200:
            print(f"[PAYLOAD SENT] #{payload.get('issue_id')} → {payload.get('module')}")
        else:
            print(f"[WARN] Payload POST returned {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[WARN] Could not POST payload to backend: {e}")


# ── Failure hook ──────────────────────────────────────────────────────────────
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report  = outcome.get_result()

    # Store every test's outcome (pass or fail) against its catalogued test case.
    if report.when == "call":
        _record_result_to_db(item, report)

    if report.when != "call":
        return

    driver = item.funcargs.get("driver")
    if not driver:
        return

    time.sleep(2)

    # 1. Crash detection
    crash_log = check_for_crashes(driver)
    if crash_log:
        print(f"CRASH DETECTED in {item.nodeid}")
        allure.attach(crash_log, name="Crash Logs",
                      attachment_type=allure.attachment_type.TEXT)
        if report.outcome != "failed":
            report.outcome  = "failed"
            report.longrepr = "Application crash detected in logcat"

    if report.outcome != "failed":
        return

    # 2. Screenshot
    try:
        os.makedirs("screenshots", exist_ok=True)
        screenshot_path = f"screenshots/{item.name}.png"
        driver.save_screenshot(screenshot_path)
        allure.attach.file(screenshot_path, name="Failure Screenshot",
                           attachment_type=allure.attachment_type.PNG)
    except Exception as e:
        print("Screenshot capture failed:", e)

    # 3. Metadata
    app_name    = _cfg(item, "--app-name",    "Unknown App")
    app_version = _cfg(item, "--app-version", "Unknown Version")
    module      = _extract_module(item)
    feature     = _extract_feature(item)
    test_name   = item.name
    issue_id    = _make_issue_id()

    developer_name = (
        _developer_name
        or _cfg(item, "--developer-name", "")
        or "Unknown Developer"
    )

    issue_summary = f"Automation Failure: {test_name}"

    # 4. Step collection (4-layer pipeline — now uses expanded patterns)
    steps_executed = _get_steps(item, report, test_name)

    # 5. Error text
    error_text = _extract_error_only(report.longrepr)

    # ── Capture accurate test execution dates ──────────────────────────────
    global _test_start_time

    test_start = _test_start_time or datetime.datetime.now()
    test_end   = datetime.datetime.now()

    start_date_iso      = test_start.isoformat()
    end_date_iso        = test_end.isoformat()
    start_date_readable = test_start.strftime('%d/%m/%Y, %H:%M')
    end_date_readable   = test_end.strftime('%d/%m/%Y, %H:%M')
    duration_seconds    = (test_end - test_start).total_seconds()
    duration_readable   = f"{int(duration_seconds)} seconds"

    print(f"\n📅 Test Execution Timeline:")
    print(f"   Start:    {start_date_readable} (ISO: {start_date_iso})")
    print(f"   End:      {end_date_readable} (ISO: {end_date_iso})")
    print(f"   Duration: {duration_readable}")
    print(f"   Steps:    {len(steps_executed)}")

    # ── Build payload ──────────────────────────────────────────────────────
    payload = {
        "ticket_id":       _ticket_id,
        "issue_id":        issue_id,
        "app_name":        app_name,
        "app_version":     app_version,
        "module":          module,
        "feature":         feature,
        "issue_summary":   issue_summary,
        "title":           issue_summary,
        "test_name":       test_name,
        "steps_executed":  steps_executed,
        "developer_name":  developer_name,
        "description":     _build_description(error_text, steps_executed),
        "start_date":      start_date_iso,
        "end_date":        end_date_iso,
        "sprint":          "Automation",
        "fix_version":     ["Production"],
        "affects_version": [app_name] if app_name and app_name != "Unknown App" else [],
    }

    allure.attach(
        json.dumps(payload, ensure_ascii=False, indent=2),
        name=f"Automation Payload [#{issue_id}]",
        attachment_type=allure.attachment_type.JSON,
    )

    _send_payload_to_backend(payload)
    _session_issues.append({
        "issue_id":  issue_id,
        "test_name": test_name,
        "module":    module,
        "steps":     len(steps_executed),
    })


# ── Session finish ────────────────────────────────────────────────────────────
def pytest_sessionfinish(session, exitstatus):
    # print(f"\n{'='*50}")
    # print(f"TEST SESSION FINISHED  |  Run ID: {_ticket_id}")
    if _session_issues:
        print(f"Failures ({len(_session_issues)}):")
        for iss in _session_issues:
            print(
                f"  [#{iss['issue_id']}] {iss['module']} — "
                f"{iss['test_name']} ({iss['steps']} steps)"
            )
    # print("Review failures in IssuePanel and click 'Create' to file Jira tickets.")
    # print(f"{'='*50}\n")

    # Finalize the DB test run (status derived from recorded results server-side).
    if _db_run_id:
        try:
            http_requests.post(
                f"{BACKEND_URL}/api/test-runs/{_db_run_id}/finish",
                json={"exit_status": int(exitstatus)},
                timeout=5,
            )
            print(f"[RESULT] DB test run {_db_run_id} finalized.")
        except Exception as e:
            print(f"[RESULT] Could not finalize DB run {_db_run_id}: {e}")


def notReportFailed(report):
    return report.outcome != "failed"
