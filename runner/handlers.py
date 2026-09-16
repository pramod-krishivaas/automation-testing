"""The commands the backend can send to this runner.

Each takes keyword arguments from the command's payload and returns something
JSON-serialisable. RunnerError carries a status the backend passes through to
the UI (bad input, busy, not found). They run on worker threads, so blocking
work is fine here.
"""

import base64
import glob
import inspect
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import tests.test_runner as suite
from runner import apks, discovery
from runner.device import ADB_PATH, ALLURE_CMD, APPIUM_PORT, JAVA_HOME, build_tool_env, pick_free_port
from runner.errors import RunnerError

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = REPO_ROOT / "tests"

_run_lock = threading.Lock()
_active_run: Optional[str] = None
_appium_proc: Optional[subprocess.Popen] = None

# Events for the backend, e.g. run-finished. The agent installs a sink while it
# is connected; anything emitted while disconnected waits here for the next one.
_event_sink: Optional[Callable[[str, dict], None]] = None
_outbox: list[tuple[str, dict]] = []
_events_lock = threading.Lock()


def set_event_sink(sink: Optional[Callable[[str, dict], None]]) -> None:
    global _event_sink
    with _events_lock:
        _event_sink = sink


def take_outbox() -> list[tuple[str, dict]]:
    with _events_lock:
        pending = list(_outbox)
        _outbox.clear()
    return pending


def emit(name: str, payload: dict) -> None:
    with _events_lock:
        sink = _event_sink
    if sink is not None:
        try:
            sink(name, payload)
            return
        except Exception as exc:
            print(f"[runner] Could not send '{name}' yet ({exc}); it will go on reconnect.")
    with _events_lock:
        _outbox.append((name, payload))


# ── Status ──────────────────────────────────────────────────────────────────

def _device() -> Optional[str]:
    """Model of the first attached, authorised phone (e.g. 'M2006C3MII'), or None."""
    try:
        out = subprocess.run([ADB_PATH, "devices", "-l"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), parts[0])
    return None


def _device_connected() -> bool:
    return _device() is not None


def _appium_running() -> bool:
    return _appium_proc is not None and _appium_proc.poll() is None


def status_snapshot() -> dict:
    """Pushed to the backend every few seconds, so its status polls need no round trip."""
    device = _device()
    return {
        "device_connected": device is not None,
        "device": device,
        "appium": "running" if _appium_running() else "stopped",
        "active_run": _active_run,
    }


def device_status() -> dict:
    return {"connected": _device_connected()}


# ── Appium ──────────────────────────────────────────────────────────────────

def _appium_port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", APPIUM_PORT)) == 0


def appium_status() -> dict:
    return {"status": "running", "port": APPIUM_PORT} if _appium_running() else {"status": "stopped"}


def appium_start(wait: float = 0) -> dict:
    """Start Appium. With wait=N, block up to N seconds (max 60) until it accepts connections."""
    global _appium_proc
    if _appium_running():
        return {"status": "running", "message": "Appium is already running via the runner."}
    if _appium_port_in_use():
        return {"status": "running", "message": f"Appium already active on port {APPIUM_PORT}"}
    # shell=True so Windows resolves the appium.cmd shim; the env guarantees
    # JAVA_HOME / ANDROID_HOME for UiAutomator2's APK signature checks.
    _appium_proc = subprocess.Popen(
        ["appium", "-p", str(APPIUM_PORT)],
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=build_tool_env(),
    )
    deadline = time.monotonic() + min(max(float(wait), 0), 60)
    while time.monotonic() < deadline and not _appium_port_in_use():
        time.sleep(1)

    message = f"Appium started on port {APPIUM_PORT}"
    if wait and not _appium_port_in_use():
        message += " (not accepting connections yet)"
    if not JAVA_HOME:
        message += " (no JDK found — set JAVA_HOME; APK signature checks may fail)"
    return {"status": "started", "message": message, "java_home": JAVA_HOME}


def appium_stop() -> dict:
    global _appium_proc
    if _appium_proc is None:
        return {"status": "not_running"}
    if os.name == "nt":
        # /T takes down the node child that the cmd shim spawned.
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(_appium_proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        _appium_proc.kill()
    _appium_proc = None
    return {"status": "stopped"}


# ── APKs ────────────────────────────────────────────────────────────────────

def list_apks() -> dict:
    return {"apks": apks.list_apks()}


def _stored_apk(name: str) -> Path:
    try:
        path = apks.resolve_apk(name)
    except ValueError as exc:
        raise RunnerError(400, str(exc))
    if not path.is_file():
        raise RunnerError(404, f"APK not found on the runner: {path.name}")
    return path


def prepare_apk(apk_name: Optional[str] = None, url: Optional[str] = None,
                run_id: Optional[str] = None) -> dict:
    """Make sure the APK is on this machine (downloading it if given a URL) and describe it."""
    if bool(apk_name) == bool(url):
        raise RunnerError(400, "Send exactly one of apk_name or url")

    if url:
        suite.send_log("Starting APK download...", "INFO", run_id=run_id)

        def progress(message: str) -> None:
            clean = message.replace("\r", "").strip()
            if clean:
                suite.send_log(clean, "PROGRESS", run_id=run_id)

        try:
            path = Path(apks.download_apk(url, progress))
        except Exception as exc:
            raise RunnerError(400, f"Download failed: {exc}")
    else:
        path = _stored_apk(apk_name)

    info, icon = apks.describe_apk(str(path))
    return {
        "apk_name": path.name,
        "info": info,
        # Inlined, so a UI served from anywhere can show it without reaching this disk.
        "icon": "data:image/png;base64," + base64.b64encode(icon).decode("ascii") if icon else None,
    }


# ── Runs ────────────────────────────────────────────────────────────────────

def _is_suite_file(rel_path: str) -> bool:
    """Only files inside tests/ may be handed to pytest."""
    if not rel_path:
        return False
    candidate = (REPO_ROOT / rel_path).resolve()
    return candidate.suffix == ".py" and candidate.is_file() and candidate.is_relative_to(SUITE_DIR)


def _count_results() -> tuple[int, int]:
    """Tally the run from allure-results: pytest writes one *-result.json per test."""
    passed = failed = 0
    for result_file in glob.glob(str(REPO_ROOT / suite.RESULTS_DIR / "*-result.json")):
        try:
            with open(result_file, encoding="utf-8") as fh:
                status = (json.load(fh).get("status") or "").upper()
        except (OSError, ValueError):
            continue
        if status == "PASSED":
            passed += 1
        elif status in ("FAILED", "BROKEN"):
            failed += 1
    return passed, failed


def _execute_run(run_id: str, apk_path: str, tests: list[dict], options: dict) -> None:
    global _active_run
    passed = failed = 0
    error = None
    try:
        suite.run_tests_and_get_suggestions(apk_path, tests_to_run=tests, run_id=run_id, **options)
        passed, failed = _count_results()
    except Exception as exc:
        error = str(exc)
        suite.send_log(f"Run failed on the runner: {exc}", "FAILED")
    finally:
        with _run_lock:
            _active_run = None
    emit("run-finished", {"run_id": run_id, "passed": passed, "failed": failed,
                           "stopped": bool(suite.STOP_FLAG), "error": error})


def start_run(
    run_id: str,
    apk_name: str,
    tests_to_run: Optional[list] = None,
    app_type: Optional[str] = None,
    app_name: Optional[str] = None,
    app_version: Optional[str] = None,
    developer_name: Optional[str] = None,
    login_phone: Optional[str] = None,
    login_mpin: Optional[str] = None,
    test_types: Optional[list] = None,
) -> dict:
    """Start a run in the background; its end is reported as a run-finished event."""
    global _active_run
    apk_path = _stored_apk(apk_name)

    requested = [t for t in (tests_to_run or []) if isinstance(t, dict)]
    valid = [t for t in requested if _is_suite_file(t.get("path", ""))]
    skipped = [t.get("path", "") for t in requested if t not in valid]
    if not valid and not test_types:
        raise RunnerError(400, f"None of the requested test scripts exist in the suite on the runner: {skipped}")

    with _run_lock:
        if _active_run:
            raise RunnerError(409, f"A run is already in progress ({_active_run})")
        _active_run = run_id

    options = {"app_type": app_type, "app_name": app_name, "app_version": app_version,
               "developer_name": developer_name, "login_phone": login_phone,
               "login_mpin": login_mpin, "test_types": test_types}
    threading.Thread(target=_execute_run, args=(run_id, str(apk_path), valid, options),
                     name=f"run-{run_id[:8]}", daemon=True).start()
    return {"status": "started", "run_id": run_id, "skipped": skipped}


def stop_run() -> dict:
    return {"stopped": suite.stop_current_tests()}


# ── Reports ─────────────────────────────────────────────────────────────────

def generate_report() -> dict:
    threading.Thread(target=suite.generate_report, daemon=True).start()
    return {"status": "ok", "message": "Report generation started"}


def allure_start() -> dict:
    port = pick_free_port()
    subprocess.Popen(
        [ALLURE_CMD, "open", "-h", "127.0.0.1", "-p", str(port), suite.REPORT_DIR],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        shell=True, env=build_tool_env(),  # allure is a JVM tool and needs java
    )
    return {"url": f"http://127.0.0.1:{port}"}


# ── Test-source discovery ───────────────────────────────────────────────────

def discover_tests(path: str) -> list[dict]:
    return discovery.discover_automation_tests(path)


def discover_type_folder(type: str) -> list[dict]:
    return discovery.discover_type_folder(type)


ACTIONS: dict[str, Callable[..., object]] = {
    "device_status": device_status,
    "appium_status": appium_status,
    "appium_start": appium_start,
    "appium_stop": appium_stop,
    "list_apks": list_apks,
    "prepare_apk": prepare_apk,
    "start_run": start_run,
    "stop_run": stop_run,
    "generate_report": generate_report,
    "allure_start": allure_start,
    "discover_tests": discover_tests,
    "discover_type_folder": discover_type_folder,
}


def dispatch(action: str, payload: dict):
    handler = ACTIONS.get(action)
    if handler is None:
        raise RunnerError(400, f"Unknown command: {action}")
    try:
        inspect.signature(handler).bind(**payload)
    except TypeError as exc:
        raise RunnerError(400, f"Bad arguments for '{action}': {exc}")
    return handler(**payload)
