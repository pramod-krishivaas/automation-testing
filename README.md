# automation-testing

The Appium/pytest automation suite (test cases, page objects, locators, flow
definitions, the UI screenshot parser) plus the **test runner**, which connects
this machine to the platform. This is the only repo the office laptop needs.
The backend and frontend are reached by their URLs.

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing-backend`](../automation-testing-backend) and
[`automation-testing-frontend`](../automation-testing-frontend).

## Layout

```
runner/        connects to the backend and runs its commands (python -m runner)
  agent.py       outbound WebSocket, reconnects
  handlers.py    the commands: device, Appium, APKs, runs, reports, discovery
  apks.py        APK storage and Drive downloads
  device.py      adb / Java / tool environment
  discovery.py   reading test sources
tests/         pytest suites, page objects, locators, conftest, test_runner
test-flows/    JSON flow definitions
ui-parser/     screenshot validator
```

## How the pieces talk

```
frontend ──HTTPS──► backend ◄──WebSocket (opened by the laptop)── runner (this repo)
                       ▲                                           │ pytest · Appium · adb · APKs
                       └──── logs, module status, results (HTTPS) ─┘
```

Everything goes over URLs; no repo imports another's code. The runner dials out
to `BACKEND_URL`, so the laptop needs no public address, open port or tunnel.
Only internet access. The backend sends commands down that connection. The
suite reports logs and results to `BACKEND_URL`, and asks it for the things it
owns, such as test-type tags and the Jira assignee name.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

The only setting is `BACKEND_URL`: the deployed backend's URL (e.g.
`https://automation-testing-backend.onrender.com`), or `http://localhost:8000`
locally.

## Running the runner

From this repo's root:

```bash
python -m runner
```

It prints `Connected to …` and the UI's **Test runner** card shows this
machine's name. Leave it running. It reconnects by itself after network drops
and backend restarts or redeploys, and runs one test run at a time.

If it keeps printing `Backend refused the connection (HTTP 404)`, the deployed
backend doesn't have `/runner/ws` yet. Redeploy it.

## APK storage

APKs live outside the repo in a machine-wide data directory,
`%PROGRAMDATA%\TestAutomationPlatform\apks` by default, so a fresh clone doesn't
lose them. Override with `PLATFORM_DATA_DIR` (the knob CI should set) or
`APK_STORAGE_DIR`. The runner serves the APK list and inlines icons into its
replies, so nothing has to reach this disk directly.

## Running pytest directly

```bash
python -m pytest --alluredir=allure-results
```

Note: `tests/web_automation/` needs Playwright, which is not in
`requirements.txt` — that collection error predates the repo split. Install
`playwright` or pass `--ignore=tests/web_automation`.
