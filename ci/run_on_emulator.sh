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

record() {  # record <category> <message>
  echo "$1" > "$OUT_DIR/failure-category"
  echo "::error::$2"
}

collect_and_stop() {
  echo "── Collecting logs ─────────────────────────────────────────────"
  adb logcat -d > "$OUT_DIR/logcat.txt" 2>/dev/null && echo "logcat → $OUT_DIR/logcat.txt"
  if [ -n "$APPIUM_PID" ] && kill -0 "$APPIUM_PID" 2>/dev/null; then
    kill "$APPIUM_PID" 2>/dev/null
    wait "$APPIUM_PID" 2>/dev/null
    echo "Appium stopped."
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

echo "── Installing the APK ──────────────────────────────────────────"
if ! adb install -r "$APK_PATH" > "$OUT_DIR/install.log" 2>&1; then
  cat "$OUT_DIR/install.log"
  adb logcat -d | tail -n 200 > "$OUT_DIR/install-logcat.txt"
  record ENVIRONMENT_FAILURE "APK installation failed — see install.log."
  exit 2
fi
cat "$OUT_DIR/install.log"

if [ -n "$APP_PACKAGE" ]; then
  if adb shell pm list packages | tr -d '\r' | grep -qx "package:$APP_PACKAGE"; then
    echo "Package installed: $APP_PACKAGE"
  else
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
