"""Give each test run's farm boundary its own ground on the "Draw on map" screen.

Primary: move the device's GPS (Appium mock location) to this run's cell in a test
area, so the map opens there. Fallback, when the app doesn't take the mocked
location: search the map for a place by name (the search box doesn't accept
coordinates). Either way the spot is checked on screen before drawing: existing
boundaries are drawn in the app's green, and a spot showing any is skipped.
"""
import math
import re
import sys
import time
from datetime import datetime, timezone

import cv2
import numpy as np
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import WebDriverException

from utils.ui_actions import set_input_value
from utils.wait_utils import _xpath_literal, wait_until_displayed

sys.dont_write_bytecode = True

SLOT_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
METRES_PER_DEG_LAT = 111320.0
# The map screen's header: "Lat: 17.4401", "Lon: 78.3992" (the location the app sees).
APP_LAT_XPATH = '//*[starts-with(@text, "Lat:")]'
APP_LON_XPATH = '//*[starts-with(@text, "Lon:")]'
# Existing boundaries: RGB (23, 163, 74) = OpenCV HSV (71, 219, 163); the range
# includes the paler anti-aliased edges of the lines. Trees are far darker and
# fields yellower, so satellite imagery doesn't match.
BOUNDARY_HSV_LOW = (63, 110, 80)
BOUNDARY_HSV_HIGH = (82, 255, 255)
BOUNDARY_PX_ALLOWED = 25  # stray pixels; one line across the spot is hundreds


# ── test-area cells ──────────────────────────────────────────────────────────
def _spiral_cell(n):
    """(column, row) of cell `n` in a square spiral around (0, 0): cell 0 is the
    centre, cells 1-8 ring 1, cells 9-24 ring 2, and so on."""
    if n == 0:
        return 0, 0
    ring = (math.isqrt(n) + 1) // 2
    edge, step = divmod(n - (2 * ring - 1) ** 2, 2 * ring)
    if edge == 0:
        return ring, -ring + 1 + step       # east side, going north
    if edge == 1:
        return ring - 1 - step, ring        # north side, going west
    if edge == 2:
        return -ring, ring - 1 - step       # west side, going south
    return -ring + 1 + step, -ring          # south side, going east


def run_minute(when=None):
    """Minutes since 2026-01-01 UTC: the same on every laptop and CI runner."""
    return int(((when or datetime.now(timezone.utc)) - SLOT_EPOCH).total_seconds() // 60)


def cells_for_run(rings, when=None):
    """Cell numbers to try, in order, for a run starting now.

    Starts at the cell for the current minute, so runs on different laptops or in
    CI a minute or more apart start in different cells without sharing any state;
    the following cells are the next choices when a spot turns out to be taken.
    """
    total = (2 * rings + 1) ** 2
    minute = run_minute(when)
    return [(minute + i) % total for i in range(total)]


def cell_location(center, cell, cell_m):
    """(latitude, longitude) of `cell`'s centre, `cell_m` metres apart around `center`."""
    col, row = _spiral_cell(cell)
    lat0, lng0 = center
    metres_per_deg_lng = METRES_PER_DEG_LAT * math.cos(math.radians(lat0))
    return round(lat0 + row * cell_m / METRES_PER_DEG_LAT, 6), round(lng0 + col * cell_m / metres_per_deg_lng, 6)


# ── device location (Appium mock GPS) ────────────────────────────────────────
def set_device_location(driver, lat, lng):
    """Mock the device's GPS at (lat, lng). True if Appium accepted it.

    Emulators take it via `geo fix`; real phones via the Appium Settings app,
    which UiAutomator2 allows as the mock location app at session start (some
    phones, e.g. MIUI, need Developer options > Select mock location app >
    Appium Settings once). Whether the app picked it up is checked separately.
    """
    try:
        driver.execute_script("mobile: setGeolocation", {"latitude": lat, "longitude": lng, "altitude": 500})
    except WebDriverException:
        try:
            driver.set_location(lat, lng, 500)
        except WebDriverException as e:
            print(f"[location] could not mock the GPS: {e.msg if hasattr(e, 'msg') else e}")
            return False
    try:
        # Push the new fix through Google Play Services so apps see it straight away.
        driver.execute_script("mobile: refreshGpsCache", {"timeoutMs": 10000})
    except WebDriverException:
        pass
    print(f"[location] device GPS set to {lat}, {lng}")
    return True


def reset_device_location(driver):
    """Stop mocking the GPS (real phones go back to their real location)."""
    try:
        driver.execute_script("mobile: resetGeolocation")
        print("[location] device GPS back to the real location")
    except WebDriverException:
        pass  # not supported on emulators; CI's emulator is thrown away after the run


def app_location(driver):
    """(lat, lng) shown in the map screen's header, or None if it isn't readable."""
    values = []
    for xpath in (APP_LAT_XPATH, APP_LON_XPATH):
        try:
            texts = [el.text for el in driver.find_elements(AppiumBy.XPATH, xpath) if el.is_displayed()]
        except WebDriverException:
            return None
        number = re.search(r"-?\d+(?:\.\d+)?", texts[0]) if texts else None
        if not number:
            return None
        values.append(float(number.group()))
    return tuple(values)


def wait_for_app_location(driver, lat, lng, timeout=20, tolerance_deg=0.0005):
    """Wait until the app shows (lat, lng) (the header rounds to 4 decimals).
    Returns True (matches), False (shows somewhere else) or None (header not readable)."""
    deadline = time.time() + timeout
    seen = None
    while True:
        seen = app_location(driver)
        if seen and abs(seen[0] - lat) <= tolerance_deg and abs(seen[1] - lng) <= tolerance_deg:
            return True
        if time.time() >= deadline:
            if seen is None:
                return None
            print(f"[location] the app shows {seen}, not the mocked {lat}, {lng}")
            return False
        time.sleep(1)


# ── is the spot free? ────────────────────────────────────────────────────────
def _screenshot(driver):
    return cv2.imdecode(np.frombuffer(driver.get_screenshot_as_png(), np.uint8), cv2.IMREAD_COLOR)


def _crop(image, box, margin=0):
    x1, y1, x2, y2 = box
    h, w = image.shape[:2]
    return image[max(y1 - margin, 0):min(y2 + margin, h), max(x1 - margin, 0):min(x2 + margin, w)]


def wait_for_map_to_settle(driver, box, timeout=20, min_wait=2.0, poll=1.0):
    """Wait until the map around `box` stops changing (tiles and boundaries drawn)."""
    time.sleep(min_wait)
    deadline = time.time() + timeout
    previous = _crop(_screenshot(driver), box)
    while time.time() < deadline:
        time.sleep(poll)
        current = _crop(_screenshot(driver), box)
        if current.shape == previous.shape and \
                float(np.abs(current.astype(np.int16) - previous.astype(np.int16)).mean()) < 1.0:
            return True
        previous = current
    return False


def boundary_pixels(driver, box, margin=24):
    """Pixels of existing (green) boundaries in `box` plus `margin` on screen."""
    hsv = cv2.cvtColor(_crop(_screenshot(driver), box, margin), cv2.COLOR_BGR2HSV)
    return int(np.count_nonzero(cv2.inRange(hsv, BOUNDARY_HSV_LOW, BOUNDARY_HSV_HIGH)))


# ── where the boundary goes on screen ────────────────────────────────────────
MAP_XPATH = '//*[@content-desc="Google Map"]'
# Where the map sits when its view can't be found: measured on the 720x1600 phone
# (map x 33-687, y 315-1419), as fractions of the screen.
MAP_SCREEN_FRACTIONS = (33 / 720, 315 / 1600, 688 / 720, 1419 / 1600)
# The boundary: a rectangle around the map's centre (the device location), as
# fractions of the map; clear of the search bar (top), the side buttons (top
# right), the compass (bottom right) and the Google logo (bottom left).
BOUNDARY_FRACTIONS = (0.27, 0.32, 0.73, 0.68)


def map_bounds(driver):
    """(left, top, right, bottom) of the map on screen."""
    size = driver.get_window_size()
    element = wait_until_displayed(driver, MAP_XPATH, timeout=3)
    if element is not None:
        r = element.rect
        if r["width"] > 0.5 * size["width"] and r["height"] > 0.3 * size["height"]:
            return int(r["x"]), int(r["y"]), int(r["x"] + r["width"]), int(r["y"] + r["height"])
    left, top, right, bottom = MAP_SCREEN_FRACTIONS
    return (int(left * size["width"]), int(top * size["height"]),
            int(right * size["width"]), int(bottom * size["height"]))


def boundary_corners(driver):
    """The boundary's 4 corners on screen (clockwise from top left), inside the map."""
    left, top, right, bottom = map_bounds(driver)
    w, h = right - left, bottom - top
    x1, y1, x2, y2 = BOUNDARY_FRACTIONS
    xa, xb = int(left + x1 * w), int(left + x2 * w)
    ya, yb = int(top + y1 * h), int(top + y2 * h)
    return [(xa, ya), (xb, ya), (xb, yb), (xa, yb)]


# ── drawing the corners ──────────────────────────────────────────────────────
# Google Maps only counts a tap once no second tap follows within ~300 ms (two
# quick taps are a double-tap zoom); a quicker next tap cancels the pending one.
TAP_GAP_S = 1.0


def _tap(driver, x, y):
    try:
        driver.execute_script("mobile: clickGesture", {"x": int(x), "y": int(y)})
    except WebDriverException:
        driver.tap([(int(x), int(y))], 100)


def _changed_near(before, after, x, y, radius=30):
    """Did the screen change around (x, y)? (a new vertex marker drawn there)"""
    box = (int(x) - radius, int(y) - radius, int(x) + radius, int(y) + radius)
    a, b = _crop(before, box), _crop(after, box)
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    return float((diff > 40).mean()) > 0.03


def tap_boundary_corners(driver, corners, closing_taps=2, attempts=2, confirm_timeout=2.0):
    """Tap each corner until it shows on the map, then tap the first corner
    `closing_taps` times to close the polygon. Returns the taps each corner took.

    Taps are at least TAP_GAP_S apart so none cancels another. After each tap the
    screen around the corner is watched for the new vertex; if none appears within
    `confirm_timeout`s the corner is tapped again (long after the first tap, so
    it can't turn into a double-tap). Raises AssertionError if a corner never shows.
    """
    tries = []
    for i, (x, y) in enumerate(corners, 1):
        for attempt in range(1, attempts + 1):
            before = _screenshot(driver)
            tapped_at = time.time()
            _tap(driver, x, y)
            shown = False
            while not shown and time.time() - tapped_at < confirm_timeout:
                time.sleep(0.4)
                shown = _changed_near(before, _screenshot(driver), x, y)
            time.sleep(max(0.0, TAP_GAP_S - (time.time() - tapped_at)))
            if shown:
                tries.append(attempt)
                break
            print(f"[boundary] corner {i} at ({x}, {y}) didn't show on the map; tapping it again")
        else:
            raise AssertionError(f"Corner {i} at ({x}, {y}) never showed on the map after {attempts} taps.")
    for _ in range(closing_taps):
        _tap(driver, *corners[0])
        time.sleep(TAP_GAP_S)
    print(f"[boundary] {len(corners)} corners drawn (taps per corner: {tries}), polygon closed")
    return tries


# ── fallback: search a place by name ─────────────────────────────────────────
def search_place(driver, search_input_xpath, place, timeout=15):
    """Search the map for `place` and pick its result. True if a result was tapped."""
    literal, with_comma = _xpath_literal(place), _xpath_literal(place + ",")
    result_xpath = f"//*[@content-desc={literal} or starts-with(@content-desc, {with_comma})]"
    if not set_input_value(driver, search_input_xpath, place, element_name="Search Location"):
        return False
    result = wait_until_displayed(driver, result_xpath, timeout=timeout)
    if result is None:
        # The results list may only open while the box has focus: focus it and retype.
        field = wait_until_displayed(driver, search_input_xpath, timeout=2)
        if field is not None:
            field.click()
            set_input_value(driver, search_input_xpath, place, element_name="Search Location")
            result = wait_until_displayed(driver, result_xpath, timeout=timeout)
    if result is None:
        print(f"[location] no search result for {place!r}")
        return False
    result.click()
    try:
        if driver.is_keyboard_shown():
            driver.hide_keyboard()
    except WebDriverException:
        pass
    print(f"[location] map moved to the search result for {place!r}")
    return True
