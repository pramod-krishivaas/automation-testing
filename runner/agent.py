"""Connects this machine to the platform backend and runs its commands.

Start it from the automation-testing repo root:

    python -m runner

It dials OUT to BACKEND_URL over a WebSocket, so the laptop needs no public
address, open port or tunnel, only internet access. It reconnects by itself
after network drops and backend restarts or redeploys.
"""

import asyncio
import json
import socket
import time

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

HEARTBEAT_SECONDS = 3


async def serve() -> None:
    async with connect(WS_URL, additional_headers={"X-Runner-Name": socket.gethostname()},
                       max_size=None, ping_interval=20, ping_timeout=20) as ws:
        print(f"Connected to {BACKEND_URL}. Waiting for commands.", flush=True)
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
        # Events from runs that ended while this machine was disconnected.
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
    print(f"Test runner for {BACKEND_URL}", flush=True)
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
