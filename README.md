# automation-testing

The Appium/pytest automation suite (test cases, page objects, locators, flow
definitions, the UI screenshot parser) plus the **test runner**, which connects
a laptop and its phone to the platform. This is the only repo a test laptop
needs. The backend and frontend are reached by their URLs.

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing-backend`](../automation-testing-backend) and
[`automation-testing-frontend`](../automation-testing-frontend).

## Layout

```
runner/                   connects this laptop to the backend and runs its commands
  agent.py                  outbound WebSocket, reconnects, one runner per name
  handlers.py               the commands: device, Appium, APKs, runs, reports, discovery
  install-autostart.ps1     start the runner at every Windows login
  apks.py / device.py / discovery.py
tests/                    pytest suites, page objects, locators, conftest, test_runner
test-flows/               JSON flow definitions
ui-parser/                screenshot validator
```

## How the pieces talk

```
                        ┌──WebSocket (opened by laptop A)── runner A + phone
frontend ──HTTPS──► backend
                        └──WebSocket (opened by laptop B)── runner B + phone
```

Every laptop running the runner dials out to `BACKEND_URL`, so laptops need no
public address, open port or tunnel, only internet access. The UI lists the
connected laptops, and you pick which one a run goes to. Several laptops can
run at the same time. Each run's live logs and status are tagged with its run
id, so every screen shows only its own run.

Everything goes over URLs; no repo imports another's code.

## Setting up a laptop

Once per laptop:

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
```

Create `.env` in this folder with the backend's URL:

```
BACKEND_URL=https://automation-testing-backend.onrender.com
```

The laptop appears in the UI under its Windows computer name. To show a
friendlier name, add `RUNNER_NAME=...` to `.env`; names must be unique across
laptops.

Then make the runner start by itself at every login:

```bash
powershell -ExecutionPolicy Bypass -File runner\install-autostart.ps1
```

This registers a per-user scheduled task named "Automation Test Runner" (no
admin rights needed). It starts the runner now, in a hidden window, and at
every login after that, and restarts it if it crashes. Its output goes to
`%USERPROFILE%\.test-automation-platform\runner.log`. To remove it:

```bash
powershell -ExecutionPolicy Bypass -File runner\install-autostart.ps1 -Uninstall
```

To run it by hand instead, run `python -m runner` from this folder. Only one
runner per name can run on a laptop: a second copy says so and exits.

If the log keeps showing `Backend refused the connection (HTTP 404)`, the
deployed backend doesn't have `/runner/ws` yet. Redeploy it.

## APK storage

APKs live outside the repo in a machine-wide data directory,
`%PROGRAMDATA%\TestAutomationPlatform\apks` by default, so a fresh clone doesn't
lose them. Each laptop has its own. Override with `PLATFORM_DATA_DIR` (the knob
CI should set) or `APK_STORAGE_DIR`. The runner serves the APK list and inlines
icons into its replies, so nothing has to reach this disk directly.

## Running pytest directly

```bash
python -m pytest --alluredir=allure-results
```

Note: `tests/web_automation/` needs Playwright, which is not in
`requirements.txt` — that collection error predates the repo split. Install
`playwright` or pass `--ignore=tests/web_automation`.
