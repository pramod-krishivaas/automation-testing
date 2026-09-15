"""Connects this laptop to the platform backend and runs its commands.

Start it from the automation-testing repo root:

    python -m runner

or once per laptop, `runner\\install-autostart.ps1` makes Windows start it at
every login. It dials OUT to BACKEND_URL over a WebSocket, so the laptop needs
no public address, open port or tunnel, only internet access. It reconnects by
itself after network drops and backend restarts or redeploys.

The laptop shows up in the UI under RUNNER_NAME (default: its hostname). Several
laptops can be connected at once; the UI picks which one runs a test.
"""

import asyncio
import json
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import IO, Optional

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

import tests.test_runner as suite
from runner import handlers
from runner.errors import RunnerError

BACKEND_URL = suite.BACKEND_URL.rstrip("/")
if BACKEND_URL.startswith("https://"):
    WS_URL = "wss://" + BACKEND_URL[len("https://"):] + "/runner/ws"
else:
    WS_URL = "ws://" + BACKEND_URL.removeprefix("http://") + "/runner/ws"

RUNNER_NAME = os.getenv("RUNNER_NAME") or socket.gethostname()
STATE_DIR = Path.home() / ".test-automation-platform"
HEARTBEAT_SECONDS = 3


def _redirect_output_to_log() -> None:
    # Set by the auto-start task, which runs the runner without a console.
    path = os.getenv("RUNNER_LOG_FILE")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(path, "a", encoding="utf-8", buffering=1)


def _claim_single_instance() -> Optional[IO]:
    """Hold a per-name lock for the life of the process.

    Two runners under one name (say, one started by hand next to the auto-start
    task) would keep replacing each other's connection.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / f"runner-{re.sub(r'[^A-Za-z0-9_.-]', '_', RUNNER_NAME)}.lock", "a+")
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


async def serve() -> None:
    async with connect(WS_URL, additional_headers={"X-Runner-Name": RUNNER_NAME},
                       max_size=None, ping_interval=20, ping_timeout=20) as ws:
        print(f"Connected to {BACKEND_URL} as '{RUNNER_NAME}'. Waiting for commands.", flush=True)
        loop = asyncio.get_running_loop()
        send_lock = asyncio.Lock()

        async def send(message: dict) -> None:
            async with send_lock:
                await ws.send(json.dumps(message))

        def sink(name: str, payload: dict) -> None:
            # Called from run threads: hand the send to the event loop and wait, so a
            # failed send raises and handlers.emit keeps the event for next time.
            asyncio.run_coroutine_threadsafe(
                send({"type": "event", "name": name, "payload": payload}), loop
            ).result(timeout=15)

        async def heartbeat() -> None:
            while True:
                snapshot = await asyncio.to_thread(handlers.status_snapshot)
                await send({"type": "status", "status": snapshot})
                await asyncio.sleep(HEARTBEAT_SECONDS)

        async def execute(message: dict) -> None:
            reply = {"type": "reply", "id": message.get("id")}
            try:
                result = await asyncio.to_thread(
                    handlers.dispatch, message.get("action", ""), message.get("payload") or {}
                )
                reply.update(ok=True, result=result)
            except RunnerError as exc:
                reply.update(ok=False, status=exc.status, detail=exc.detail)
            except Exception as exc:
                reply.update(ok=False, status=500, detail=f"{type(exc).__name__}: {exc}")
            await send(reply)

        handlers.set_event_sink(sink)
        # Events from runs that ended while this laptop was disconnected.
        for name, payload in handlers.take_outbox():
            await asyncio.to_thread(handlers.emit, name, payload)

        tasks = {asyncio.create_task(heartbeat())}
        try:
            async for raw in ws:
                message = json.loads(raw)
                if message.get("type") == "command":
                    task = asyncio.create_task(execute(message))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
        finally:
            handlers.set_event_sink(None)
            for task in tasks:
                task.cancel()


def main() -> None:
    _redirect_output_to_log()
    lock = _claim_single_instance()
    if lock is None:
        # Exit 0 so the auto-start task doesn't treat this as a crash and retry.
        print(f"A runner named '{RUNNER_NAME}' is already running on this laptop; not starting another.",
              flush=True)
        return

    print(f"Test runner '{RUNNER_NAME}' for {BACKEND_URL}", flush=True)
    backoff = 1
    while True:
        try:
            asyncio.run(serve())
            backoff = 1
            print("Disconnected; reconnecting.", flush=True)
        except InvalidStatus as exc:
            # 404 here usually means the deployed backend predates /runner/ws.
            print(f"Backend refused the connection (HTTP {exc.response.status_code}) at {WS_URL}. "
                  f"Check BACKEND_URL and that the backend is up to date. Retrying in {backoff}s.",
                  flush=True)
        except (OSError, ConnectionClosed, TimeoutError) as exc:
            print(f"Can't reach {WS_URL} ({type(exc).__name__}); retrying in {backoff}s.", flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 30)
