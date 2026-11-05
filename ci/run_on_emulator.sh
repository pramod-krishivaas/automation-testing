#!/usr/bin/env bash
# Runs INSIDE the android-emulator-runner action: the emulator is booted and adb
# is on PATH. Verifies the device, installs the APK, starts Appium, hands over to
# ci/run_suites.py, and always collects logs and stops Appium on the way out.
#
# Never `set -e`: a failing step here has to be classified (spec §12) rather than
# killing the shell before logs are collected.
set -uo pipefail

APK_PATH="${APK_PATH:?APK_PATH is required}"
APP_PACKAGE="${APP_PACKAGE:-}"
APPIUM_PORT="${APPIUM_PORT:-4723}"
OUT_DIR="${OUT_DIR:-ci-out}"
mkdir -p "$OUT_DIR"

APPIUM_PID=""
LOGCAT_PID=""

record() {  # record <category> <message>
  echo "$1" > "$OUT_DIR/failure-category"
  echo "::error::$2"
}

collect_and_stop() {
  echo "── Collecting logs ─────────────────────────────────────────────"
  if [ -n "$LOGCAT_PID" ] && kill -0 "$LOGCAT_PID" 2>/dev/null; then
    kill "$LOGCAT_PID" 2>/dev/null
    wait "$LOGCAT_PID" 2>/dev/null
  else
    adb logcat -d > "$OUT_DIR/logcat.txt" 2>/dev/null
  fi
  echo "logcat → $OUT_DIR/logcat.txt"
  annotate_crashes
  if [ -n "$APPIUM_PID" ] && kill -0 "$APPIUM_PID" 2>/dev/null; then
    kill "$APPIUM_PID" 2>/dev/null
    wait "$APPIUM_PID" 2>/dev/null
    echo "Appium stopped."
  fi
}
# Crash lines surface as a warning on the run page, readable without downloading
# the logs. Patterns are app crashes, native crashes, ANRs and the app process
# dying; `D AndroidRuntime: >>>>>> START` lines from adb shell commands are not
# matched because only error/fatal levels are.
annotate_crashes() {
  [ -s "$OUT_DIR/logcat.txt" ] || return 0
  local pkg="${APP_PACKAGE:-__no_package__}"
  local lines
  lines=$(grep -m 12 -E " E AndroidRuntime| F libc |Fatal signal|am_crash|ANR in| E ReactNativeJS|Process ${pkg} .*has died" "$OUT_DIR/logcat.txt")
  [ -n "$lines" ] || return 0
  # Workflow-command encoding: % and newlines must be escaped.
  echo "::warning title=Crash signals in logcat::$(printf '%s\n' "$lines" \
    | awk '{ gsub(/\r/, ""); gsub(/%/, "%25"); printf "%s%s", (NR > 1 ? "%0A" : ""), substr($0, 1, 300) }')"
  # A crash that is about the emulator image rather than the app or the tests.
  if grep -q "org/apache/http" "$OUT_DIR/logcat.txt" && grep -q "mapsdynamite" "$OUT_DIR/logcat.txt"; then
    echo "::error title=Google Maps crashed the app::This image's Play services uses the legacy Maps"\
"renderer, which needs org.apache.http - not available to apps targeting API 28+ unless they declare"\
"it. Run with a newer android_api_level (34+), or have the app add"\
" <uses-library android:name=%22org.apache.http.legacy%22 android:required=%22false%22/>."
  fi
}

# Cleanup runs however this script exits, including a failure below (spec §27).
trap collect_and_stop EXIT

echo "── Verifying the device ────────────────────────────────────────"
adb wait-for-device
adb devices -l
online=$(adb devices | awk 'NR>1 && $2=="device"' | wc -l)
if [ "$online" -ne 1 ]; then
  record INFRASTRUCTURE_FAILURE "Expected exactly one booted emulator, found $online."
  exit 2
fi
echo "Boot completed: $(adb shell getprop sys.boot_completed | tr -d '\r')"
echo "Android       : $(adb shell getprop ro.build.version.release | tr -d '\r')"

# Play services comes with the system image and can't be updated here. Before
# 22.x its Google Maps renderer needs org.apache.http, which apps targeting API
# 28+ only get if they declare it — otherwise the app dies when a map opens.
GMS_VERSION=$(adb shell dumpsys package com.google.android.gms 2>/dev/null \
  | sed -n 's/.*versionName=\([0-9][0-9.]*\).*/\1/p' | head -1 | tr -d '\r')
echo "Play services : ${GMS_VERSION:-unknown}"
case "${GMS_VERSION%%.*}" in
  ''|*[!0-9]*) ;;
  *) if [ "${GMS_VERSION%%.*}" -lt 22 ]; then
       echo "::warning title=Old Play services on this emulator image::Play services ${GMS_VERSION}"\
"uses the legacy Google Maps renderer, which crashes apps that don't declare org.apache.http.legacy."\
"Suites that open a map need a newer android_api_level (34+)."
     fi ;;
esac

# Keep the screen from rotating: a configuration change recreates the activity,
# which some React Native screens don't survive.
adb shell settings put system accelerometer_rotation 0 >/dev/null 2>&1
adb shell settings put system user_rotation 0 >/dev/null 2>&1
# Same reason: never destroy an activity as soon as it goes to the background
# (e.g. behind a permission dialog).
adb shell settings put global always_finish_activities 0 >/dev/null 2>&1

# Stream logcat for the whole run: by the end, the device's small ring buffers
# have usually overwritten the lines from when the app first launched.
adb logcat -c 2>/dev/null
adb logcat -b main -b system -b crash -b events -v threadtime > "$OUT_DIR/logcat.txt" 2>/dev/null &
LOGCAT_PID=$!

echo "── Installing the APK ──────────────────────────────────────────"
if ! adb install -r "$APK_PATH" > "$OUT_DIR/install.log" 2>&1; then
  cat "$OUT_DIR/install.log"
  adb logcat -d | tail -n 200 > "$OUT_DIR/install-logcat.txt"
  record ENVIRONMENT_FAILURE "APK installation failed — see install.log."
  exit 2
fi
cat "$OUT_DIR/install.log"

if [ -n "$APP_PACKAGE" ]; then
  # Capture, then compare. Piping into `grep -q` under pipefail reports a miss
  # when grep exits early and the writers get SIGPIPE (141), even on a match.
  installed=$(adb shell pm path "$APP_PACKAGE" 2>/dev/null | tr -d '\r')
  if [[ "$installed" == package:* ]]; then
    echo "Package installed: $APP_PACKAGE (${installed#package:})"
  else
    echo "Third-party packages on the device:"
    adb shell pm list packages -3 | tr -d '\r'
    record ENVIRONMENT_FAILURE "$APP_PACKAGE is not present after install."
    exit 2
  fi
fi

echo "── Starting Appium ─────────────────────────────────────────────"
appium --address 127.0.0.1 --port "$APPIUM_PORT" \
       --log "$OUT_DIR/appium.log" --log-timestamp --local-timezone \
       --session-override &
APPIUM_PID=$!

ready=""
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${APPIUM_PORT}/status" > /dev/null; then ready=1; break; fi
  if ! kill -0 "$APPIUM_PID" 2>/dev/null; then break; fi
  sleep 1
done
if [ -z "$ready" ]; then
  tail -n 50 "$OUT_DIR/appium.log" 2>/dev/null
  record INFRASTRUCTURE_FAILURE "Appium did not become healthy on port $APPIUM_PORT."
  exit 2
fi
echo "Appium is healthy on port $APPIUM_PORT (pid $APPIUM_PID)."

echo "── Running the suites ──────────────────────────────────────────"
python ci/run_suites.py \
  --apk "$APK_PATH" \
  --package "$APP_PACKAGE" \
  --metadata "$OUT_DIR/metadata.json" \
  --summary "$OUT_DIR/summary.json" \
  --results allure-results
rc=$?

echo "$rc" > "$OUT_DIR/exit-code"
echo "run_suites.py exited with $rc"
exit "$rc"
