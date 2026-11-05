"""Draw a farm boundary on the app's "Draw on map" screen.

The flow, in order:
  1. set a known mock location, so the map opens on this run's own ground,
  2. wait for the map to finish drawing,
  3. check with OpenCV that no existing boundary (drawn in the app's green) is
     where this one goes,
  4. work out the 4 corners relative to the map on screen,
  5. tap the 4 corners and close the polygon,
  6. if the ground is taken, search the map for a place by name and try again
     (the search box takes names, not coordinates).
"""
import math
import sys
import time
from datetime import datetime, timezone

import cv2
import numpy as np
from selenium.common.exceptions import WebDriverException

from utils.ui_actions import set_input_value
from utils.wait_utils import _xpath_literal, wait_for_first_displayed, wait_until_displayed

sys.dont_write_bytecode = True

SLOT_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
METRES_PER_DEG_LAT = 111320.0
# Existing boundaries: RGB (23, 163, 74) = OpenCV HSV (71, 219, 163); the range
# includes the paler anti-aliased edges of the lines. Trees are far darker and
# fields yellower, so satellite imagery doesn't match.
BOUNDARY_HSV_LOW = (63, 110, 80)
BOUNDARY_HSV_HIGH = (82, 255, 255)
BOUNDARY_PX_ALLOWED = 25  # stray pixels; one line across the spot is hundreds


# ── 1. a known mock location, one cell per run ───────────────────────────────
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
    CI a minute or more apart start in different cells without sharing any state.
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


def set_device_location(driver, lat, lng):
    """Mock the device's GPS at (lat, lng). True if Appium accepted it.

    Emulators take it via `geo fix`; real phones via the Appium Settings app,
    which UiAutomator2 allows as the mock location app at session start (some
    phones, e.g. MIUI, need Developer options > Select mock location app >
    Appium Settings once).
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
        # Push the new fix through Google Play services so apps see it straight away.
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


# ── 2 and 3. wait for the map, then look for existing boundaries ─────────────
def _screenshot(driver):
    return cv2.imdecode(np.frombuffer(driver.get_screenshot_as_png(), np.uint8), cv2.IMREAD_COLOR)


def _crop(image, box, margin=0):
    x1, y1, x2, y2 = box
    h, w = image.shape[:2]
    return image[max(y1 - margin, 0):min(y2 + margin, h), max(x1 - margin, 0):min(x2 + margin, w)]


def wait_for_map_to_settle(driver, box, timeout=20, min_wait=3.0, poll=1.0):
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


def area_snapshot(driver, box):
    """The boundary's area on screen, to compare against later."""
    return _crop(_screenshot(driver), box)


def area_changed(before, after, threshold=0.01):
    """Did the area change? (whatever colour the app draws a new boundary in)"""
    if before.shape != after.shape:
        return True
    diff = np.abs(after.astype(np.int16) - before.astype(np.int16)).max(axis=2)
    return float((diff > 40).mean()) > threshold


# ── 4. the 4 corners, relative to the map on screen ──────────────────────────
MAP_XPATH = '//*[@content-desc="Google Map"]'
# Where the map sits when its view can't be found: measured on the 720x1600 phone
# (map x 33-687, y 315-1419), as fractions of the screen.
MAP_SCREEN_FRACTIONS = (33 / 720, 315 / 1600, 688 / 720, 1419 / 1600)
# The boundary: a rectangle around the map's centre (the device location), as
# fractions of the map, well clear of the search bar, the side buttons, the
# compass and the Google logo. This is the same size as the box drawn by hand on
# the 720x1600 phone (about 60x80 px); widen it for a larger farm.
BOUNDARY_FRACTIONS = (0.454, 0.464, 0.546, 0.536)


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


# ── 5. tap the corners and close the polygon ─────────────────────────────────
# Google Maps counts a tap only once no other tap follows within ~300 ms (two
# quick taps near each other are a double-tap zoom), so the taps are spaced out.
TAP_GAP_S = 1.0
# How long each press lasts. Only a short press is a tap (onMapClick), which is
# what adds a vertex; from about half a second the map sees a long press, another
# gesture. If a run draws nothing, the flow tries RETRY_PRESS_MS instead.
PRESS_MS = 1000
RETRY_PRESS_MS = 100
# The map keeps moving for a moment after it centres on the mocked location, and
# taps while it moves are ignored.
MAP_MOVE_WAIT_S = 3.0


def tap_boundary_corners(driver, corners, closing_taps=2, press_ms=PRESS_MS, gap_s=TAP_GAP_S,
                         wait_before_s=MAP_MOVE_WAIT_S):
    """Let the map settle on its location, then tap each corner and close the polygon
    by tapping the first corner `closing_taps` times."""
    time.sleep(wait_before_s)
    for x, y in list(corners) + [corners[0]] * closing_taps:
        driver.tap([(int(x), int(y))], press_ms)
        time.sleep(gap_s)
    print(f"[boundary] tapped {len(corners)} corners at {corners} and closed the polygon")


# ── 6. fallback: search the map for a place by name ──────────────────────────
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"


def _result_locators(place, result_xpath=None):
    """Locators for a search result for `place`, most specific first. The search box
    holds the same text, so EditTexts are excluded."""
    exact, lowered = _xpath_literal(place), _xpath_literal(place.lower())

    def any_case(attr):
        return f"contains(translate(@{attr}, '{_UPPER}', '{_LOWER}'), {lowered})"

    return [x for x in (result_xpath,
                        f"//*[@content-desc={exact} or @text={exact}]",
                        f"//*[not(self::android.widget.EditText)][{any_case('content-desc')} or {any_case('text')}]") if x]


def search_place(driver, search_input_xpath, place, result_xpath=None, timeout=10):
    """Search the map for `place` and open the first result. True if one was tapped.

    The box is focused and the name typed, so its own change events fire and the
    results list opens; a result is anything (other than the box) showing that name.
    If nothing appears, the keyboard's search action is sent before giving up.
    """
    field = wait_until_displayed(driver, search_input_xpath, timeout=5)
    if field is None:
        print("[location] the map's search box is not on screen")
        return False
    field.click()  # focus: the results list only opens for the focused box
    try:
        field.clear()
        field.send_keys(place)  # typed, so the app sees each change
    except WebDriverException:
        if not set_input_value(driver, search_input_xpath, place, element_name="Search Location"):
            return False
    locators = _result_locators(place, result_xpath)
    name, result = wait_for_first_displayed(driver, locators, timeout=timeout)
    if result is None:
        try:  # some screens only search when the keyboard's search key is pressed
            driver.execute_script("mobile: performEditorAction", {"action": "search"})
        except WebDriverException:
            pass
        name, result = wait_for_first_displayed(driver, locators, timeout=timeout)
    if result is None:
        print(f"[location] no search result for {place!r} (tried {len(locators)} locators)")
        return False
    result.click()
    try:
        if driver.is_keyboard_shown():
            driver.hide_keyboard()
    except WebDriverException:
        pass
    print(f"[location] map moved to the search result for {place!r} (locator {name})")
    return True
