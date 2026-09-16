# Android automation CI/CD

Slack posts a Drive APK link → GitHub Actions runs the existing pytest/Appium
suites on an emulator → the Allure report lands on GitHub Pages under a unique
RUN_ID → Slack gets the result → the APK artifact is deleted.

```
Slack ──► repository_dispatch ──► prepare ──► android-test ──► publish-report ──► notify ──► cleanup
                                    │             │                  │              │          │
                              RUN_ID + APK   emulator, Appium,   Allure → Pages   result     APK
                              artifact       variants × suites   under RUN_ID     message    deleted
```

The workflow is `.github/workflows/android-automation.yml`. It orchestrates;
it does not test. Everything about *how* a test drives the app stays in
`tests/` (conftest fixtures, page objects, locators, crash detection, Allure
metadata). The pipeline only decides what runs, on what device, with what APK,
and where the results go.

## One-time setup

1. **GitHub Pages** — Settings → Pages → Source: **GitHub Actions**. Without
   this, `deploy-pages` fails on the first run. The `gh-pages` branch is created
   automatically by the first successful publish and is the durable store of
   past reports.
2. **Secrets** (Settings → Secrets and variables → Actions → *Secrets*):

   | Secret | Needed for | Notes |
   |---|---|---|
   | `SLACK_WEBHOOK_URL` | Slack messages | Simplest option. Or use the bot token below. |
   | `SLACK_BOT_TOKEN` | Slack messages | `chat:write`. Used with a channel id; takes priority over the webhook. |
   | `LOGIN_PHONE` | login | Overrides `tests/test_data/accounts.json` for the run. Optional. |
   | `LOGIN_MPIN` | login | Optional. |

   `GITHUB_TOKEN` is provided automatically and is what deletes the APK artifact.

3. **Variables** (same page → *Variables*):

   | Variable | Default | Purpose |
   |---|---|---|
   | `SLACK_CHANNEL_ID` | — | Channel for results when using `SLACK_BOT_TOKEN`. |
   | `REPORT_RETENTION_RUNS` | `30` (from `pipeline.yml`) | How many reports stay on Pages. |
   | `BACKEND_URL` | — | Optional. Set it and run results also reach the platform backend; leave it unset and the suite's backend calls fail silently, as designed. |

## Triggering from Slack

Have your Slack app (or the platform backend) call GitHub's dispatch API:

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/dispatches \
  -H "Authorization: Bearer $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  -d '{
        "event_type": "android-automation",
        "client_payload": {
          "apk_url": "https://drive.google.com/file/d/<id>/view?usp=sharing",
          "developer": "john",
          "developer_slack_id": "U07ABCDEF",
          "app_name": "Krishivaas",
          "app_version": "2.5.1",
          "build_id": "125",
          "environment": "staging",
          "slack_channel_id": "C0123456789"
        }
      }'
```

Only `apk_url` is required. Alternatively pass the raw message as
`{"text": "<the Slack message>"}` and the fields are parsed out of it:

```
Android Build Ready

Developer: <@U07ABCDEF|john>
App: Krishivaas
Version: 2.5.1
Build: 125
Environment: staging

APK:
https://drive.google.com/file/d/<id>/view?usp=sharing
```

The same inputs are available as **Run workflow** fields in the Actions tab.

Optional per-run overrides: `app_variants` (e.g. `state_client,regular_client`),
`suite_selection` (e.g. `Smoke,Regression`), `emulator_device`,
`android_api_level`.

## Configuring what runs

`ci/pipeline.yml` — not the YAML workflow — holds the application knowledge:

- **`app_variants`**: which `--target-role` values run, in `priority` order.
- **`suites`**: which type folders run within each variant, in `priority` order.
  Type labels must match `tests/test_type_config.py`.
- **`execution.failure_strategy`**: `continue` (default — a failing suite does
  not stop the rest, so the report is complete) or `stop_on_first_failure`.
- **`emulator`**, **`reports.retention_runs`**.

A variant's tests for a type live in `tests/test_suites/<type_folder>/<variant>/`.
Combinations with no test files are **skipped, not failed**.

**Currently only End-to-End is enabled**; Smoke, Sanity and Regression are set
to `enabled: false`. That gives 4 combinations (one per variant), of which 2
have tests today: `end_to_end/state_client` and `end_to_end/regular_client`. A
trigger's `suite_selection` can narrow the enabled types but cannot run a
disabled one — set `enabled: true` to add a type back.

Each combination is one pytest session:

```
pytest tests/test_cases/common_test_cases/test_login_pytest.py \
       tests/test_suites/end_to_end/state_client \
       --apk <apk> --target-role state_client --test-type End-to-End \
       --alluredir allure-results
```

The login entry runs first so the shared login lands and switches to that
variant. Because each combination is a new session, the driver fixture's
`fullReset` reinstalls the app — no state carries over between variants. The
package is also `pm clear`ed between variants as a second line of defence.

## RUN_ID

`RUN-<UTC date>-<workflow run number>`, e.g. `RUN-20260916-001`. One identifier
ties together the APK artifact (`android-apk-RUN-…`), the Allure results, the
Pages directory, the report URL and the Slack messages. It is generated once in
`prepare` and passed to every later job.

## Reports on GitHub Pages

```
<pages root>/
├── index.html          run history, newest first
├── runs.json           the data behind index.html
├── RUN-20260916-002/   one Allure report per run
└── RUN-20260916-003/
```

Publishing **adds** to the site: the `gh-pages` branch is checked out, this
run's report is added, old runs beyond `REPORT_RETENTION_RUNS` are deleted, the
index is rebuilt, and the whole directory is deployed. Previous reports stay
reachable at their own URLs.

**Allure history/trends**: before generating, `ci/publish_report.py` copies the
`history/` folder from the most recent previous run **of the same app**
(matched on `app_slug` in `runs.json`) into the new results directory. That is
what produces Allure's trend graphs, and scoping by app keeps one app's trends
out of another's.

## APK lifecycle

The APK is only ever a transfer mechanism between jobs: downloaded from Drive in
`prepare`, uploaded as `android-apk-<RUN_ID>` (1-day retention as a backstop),
downloaded by the test job, and **deleted by the `cleanup` job**, which runs
`if: always()` — after test failures, emulator failures, Appium failures and
publish failures alike. The Allure report is not touched by cleanup; it has the
opposite lifecycle.

## Failure categories and exit codes

| Category | Meaning | Examples |
|---|---|---|
| `TEST_FAILURE` | The app misbehaved | assertion failed, element not found, crash detected |
| `INFRASTRUCTURE_FAILURE` | The harness broke | emulator never booted, Appium unhealthy, pytest internal error |
| `ENVIRONMENT_FAILURE` | The inputs were unusable | Drive link not shared, file is not an APK, install rejected |

`ci/run_suites.py` exit codes: `0` passed · `1` test failure · `2`
infrastructure · `3` configuration/input. The Slack result always names the
RUN_ID and, when a report exists, its exact URL.

## Running the pieces locally

No emulator needed for any of these:

```bash
python ci/prepare_run.py --payload '{"text":"APK: https://drive.google.com/file/d/ID/view"}' --out ci-out/metadata.json
python ci/run_suites.py --dry-run            # print the variant × suite plan
python ci/slack_notify.py --event started --metadata ci-out/metadata.json --dry-run
python ci/publish_report.py --site /tmp/site --metadata ci-out/metadata.json \
       --summary ci-out/summary.json --skip-generate
```

## Notes

- `.github/workflows/browserstack.yml` is the earlier BrowserStack attempt. It
  calls `scripts/*.py`, which do not exist in this repo, so it cannot run
  today. Delete it once this pipeline is live.
- `tests/test_data/accounts.json` holds login numbers and MPINs in the repo.
  Prefer the `LOGIN_PHONE` / `LOGIN_MPIN` secrets, and consider removing the
  committed credentials.
- The framework's backend calls (Jira name, test-type tags, run results) are all
  optional: with no `BACKEND_URL` they fail fast and the run continues.
