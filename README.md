# automation-testing

The Appium/pytest automation suite: test cases, page objects, locators, flow
definitions and the UI screenshot parser. Runs on the office laptop against a
connected Android device.

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing-backend`](../automation-testing-backend) and
[`automation-testing-frontend`](../automation-testing-frontend).

## Layout

```
tests/                 pytest suites, page objects, locators, conftest, test_runner
tests/repo_paths.py    locates the sibling backend repo
test-flows/            JSON flow definitions
ui-parser/             screenshot validator invoked by the backend
allure-results/        raw results written by pytest
allure-report/         generated HTML (gitignored)
docker-compose.yml     MySQL + InfluxDB + Grafana
```

## Requires the backend repo

The suite imports backend modules — Jira attachment, the `test_management` DB
session and models, and the Java/Android env builder used for Appium and Allure.
It expects `automation-testing-backend` as a **sibling folder**:

```
Projects/
├── automation-testing/
└── automation-testing-backend/
```

If your checkouts are not side by side, set `BACKEND_REPO_PATH` (see
`.env.example`).

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

`requirements.txt` covers both repos: the backend imports this package to run
tests, and this package imports the backend, so they share one environment on
the laptop.

## Running

Tests are normally launched from the platform UI, which calls the backend, which
calls `tests/test_runner.py`. To run pytest directly:

```bash
python -m pytest --alluredir=allure-results
```

Note: `tests/web_automation/` needs Playwright, which is not in
`requirements.txt` — that collection error predates the repo split. Install
`playwright` or pass `--ignore=tests/web_automation`.
