"""Crop Health screen of the regular farmer app.

Opens a farm, then checks the screen the way a user would see it: the crop-health
layer (pixels from green to black over the farm) is on the map, the legend and
dates are shown, the date slider updates it, and the stress types (Caution,
Warning, Stressed, Severely Stressed) are detected with their percentages, on
the first date (walking back with the date minus icon) where stress pixels
appear on the farm.
Everything is attached to the Allure report with screenshots, including the
verdict "shown / not shown".

Screenshots are taken from the driver while the test runs and stay in memory:
they are analysed as arrays and attached to Allure as PNG bytes, so no image
file or path is involved.
"""
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import allure
import numpy as np
import pytest
from appium.webdriver.common.appiumby import AppiumBy

from tests.utils.wait_utils import smart_click, wait_until_displayed
from utils.opencv_crop_health import (
    STRESS_LABELS, STRESS_TYPES, analyze_crop_health, analyze_stress, annotate_crop_health,
    annotate_stress_markers, decode_png, encode_png, validate_date_slider_changed,
)

sys.dont_write_bytecode = True

# The layer is drawn from tiles fetched when the screen opens, so it can arrive
# after the basemap: wait for it before calling it missing.
LAYER_TIMEOUT_S = 30
LAYER_POLL_S = 2.0

# Where the map and legend sit, as shares of the screen, when they cannot be
# anchored on the screen's own elements. Measured on a crop-health screenshot.
DEFAULT_MAP = (0.026, 0.175, 0.948, 0.549)        # x, y, width, height
DEFAULT_LEGEND = (0.035, 0.788, 0.930, 0.027)

_LABELS = ("crop_health_title", "last_update_date", "last_clear_image",
           "legend_no_issue", "legend_may_be_issue", "selected_date")

# Walking the date slider back until stress pixels appear on the farm.
MAX_DATE_CLICKS = 400          # a safety stop: the app's whole history is far fewer
DATE_CHANGE_WAIT_S = 6         # how long one click may take to show a new date
DATE_STALLS_ALLOWED = 3        # clicks in a row that change nothing: the slider's end
# After a date change the map redraws (tiles, layer, stress markers). A date is
# judged on a screenshot taken once two in a row are the same, or after this long.
SETTLE_TIMEOUT_S = 8
SETTLE_POLL_S = 0.5

# Stress percentages: the app's displayed figure vs what the markers on the map
# measure. The measurement is an estimate (a marker is an outlined cell), so it
# only has to agree within this many percentage points, calibrated on one
# screenshot where it was within 0.3.
STRESS_PCT_TOLERANCE = 0.75
# Two types whose displayed shares differ by at least this factor must rank the
# same way on the map.
STRESS_RANK_RATIO = 1.5


# ===========================================================================
# Locators
# ===========================================================================

def _read_locators(filename):
    """The flat key -> locator table of a locator file (xpath beats the others)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "locators", filename)
    print(f"Loading locators from: {path}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    backslash = chr(92)   # tolerate "\u" sequences that are not valid JSON escapes
    raw = re.sub(re.escape(backslash) + "u(?![0-9a-fA-F]{4})", lambda m: backslash * 2 + "u", raw)
    data = json.loads(raw)
    table = {}
    for source in ("element_ids", "accessibility_ids", "xpath_locators"):
        table.update(data.get(source, {}))
    return table, path


def load_locators_once(self, request):
    farm_locators, farm_path = _read_locators("fr_fa_updates.json")
    screen_locators, screen_path = _read_locators("regular_farmer_crophealth.json")

    def resolve(table, path, key):
        value = table.get(key)
        if not value:
            raise KeyError(f"Locator '{key}' not found in {path}")
        return value

    # The farm card on the farm list: the same locator the farmer-updates flow uses.
    request.cls.farm_card_xpath = resolve(farm_locators, farm_path, "regular_fr_farm_card")
    for key in _LABELS + ("navigation_icon", "date_minus", "date_plus"):
        setattr(request.cls, f"{key}_xpath", resolve(screen_locators, screen_path, key))


# ===========================================================================
# Reading the screen
# ===========================================================================

def _smallest_displayed(driver, xpath):
    """The most specific on-screen element matching `xpath`: a container whose
    content-desc repeats its children's text also matches, and is much larger."""
    try:
        found = [el for el in driver.find_elements(AppiumBy.XPATH, xpath) if el.is_displayed()]
    except Exception:
        return None
    found = [el for el in found if el.rect["width"] > 0 and el.rect["height"] > 0]
    return min(found, key=lambda el: el.rect["width"] * el.rect["height"]) if found else None


def _read_text(driver, xpath):
    el = _smallest_displayed(driver, xpath)
    if el is None:
        return None
    return (el.text or el.get_attribute("content-desc") or "").strip() or None


def _screen_layout(driver, obj, shot_w, shot_h):
    """(map_roi, legend_roi, source), each (x, y, w, h) in screenshot pixels.

    The map sits between the card header and the icon row drawn over its bottom
    edge, the legend is the bar of labels under it. They are anchored on those
    elements; if one can't be found, measured proportions are used instead.
    """
    size = driver.get_window_size()
    sx, sy = shot_w / size["width"], shot_h / size["height"]

    def default(box):
        fx, fy, fw, fh = box
        return (int(fx * shot_w), int(fy * shot_h), int(fw * shot_w), int(fh * shot_h))

    map_roi, legend_roi = default(DEFAULT_MAP), default(DEFAULT_LEGEND)
    anchors = []

    header = _smallest_displayed(driver, obj.last_update_date_xpath)
    icons = _smallest_displayed(driver, obj.navigation_icon_xpath)
    if header is not None and icons is not None:
        top = int((header.rect["y"] + header.rect["height"]) * sy) + int(0.008 * shot_h)
        bottom = int(icons.rect["y"] * sy) - int(0.004 * shot_h)
        if bottom - top >= 0.2 * shot_h:
            x, _, w, _ = default(DEFAULT_MAP)
            map_roi = (x, top, w, bottom - top)
            anchors.append("map")

    legend = _smallest_displayed(driver, obj.legend_no_issue_xpath)
    if legend is not None and legend.rect["height"] * sy <= 0.05 * shot_h:
        pad = max(1, int(0.1 * legend.rect["height"] * sy))
        x, _, w, _ = default(DEFAULT_LEGEND)
        legend_roi = (x, int(legend.rect["y"] * sy) + pad, w, max(4, int(legend.rect["height"] * sy) - 2 * pad))
        anchors.append("legend")

    return map_roi, legend_roi, ("anchored on screen elements: " + ", ".join(anchors)) if anchors \
        else "default proportions (screen elements not found)"


def _capture(driver, obj):
    """Take a screenshot from the driver, right now. Returns
    (png_bytes, image, map_roi, legend_roi, layout); nothing is written to disk."""
    try:
        png = driver.get_screenshot_as_png()
        img = decode_png(png)
    except Exception as e:
        pytest.fail(f"Could not take a screenshot of the crop health screen: {e}")
    map_roi, legend_roi, layout = _screen_layout(driver, obj, img.shape[1], img.shape[0])
    return png, img, map_roi, legend_roi, layout


def _wait_for_layer(driver, obj, timeout=None, poll=None):
    """Take screenshots and analyse each until the layer is on the map, or until
    `timeout` (default LAYER_TIMEOUT_S). Returns (png_bytes, image, result, layout,
    attempts) for the last screenshot."""
    timeout = LAYER_TIMEOUT_S if timeout is None else timeout
    poll = LAYER_POLL_S if poll is None else poll
    deadline = time.time() + timeout
    attempt = 0
    while True:
        attempt += 1
        png, img, map_roi, legend_roi, layout = _capture(driver, obj)
        result = analyze_crop_health(img, map_roi, legend_roi)
        if result["shown"] or time.time() >= deadline:
            return png, img, result, layout, attempt
        time.sleep(poll)


def _measurements(result, layout, attempts):
    return {
        "crop_health_shown": result["shown"],
        "reason": result["reason"],
        "coverage_pct_of_map": result["coverage_pct"],
        "minimum_coverage_pct": result["min_coverage_pct"],
        "distribution_pct_of_layer": result["bands"],
        "dominant_band": result["dominant"],
        "legend": result["legend"],
        "map_area_xywh": result["roi"],
        "legend_area_xywh": result["legend_roi"],
        "areas_found_by": layout,
        "screenshots_taken": attempts,
    }


# ===========================================================================
# Steps
# ===========================================================================

def farm_card(driver, obj, test_flow_steps):
    with allure.step("1. Open the farm's crop health screen"):
        # Already there (a previous test left the app on this screen): nothing to open.
        if wait_until_displayed(driver, obj.legend_no_issue_xpath, timeout=3) is not None:
            test_flow_steps.append({"step": "Crop health screen already open", "status": "Success"})
            return
        if not smart_click(driver, "Farm card", obj.farm_card_xpath, "Farm card"):
            pytest.fail("Could not find or click the 'Farm card' button.")
        test_flow_steps.append({"step": "Click Farm card", "status": "Success"})


def crop_health_screen_loaded(driver, obj, test_flow_steps):
    with allure.step("1. Wait for the crop health screen"):
        for key, label in (("crop_health_title", "Crop Health"), ("legend_no_issue", "No issue")):
            if wait_until_displayed(driver, getattr(obj, f"{key}_xpath"), timeout=30) is None:
                pytest.fail(f"The crop health screen did not open: '{label}' is not on screen.")
        test_flow_steps.append({"step": "Crop health screen loaded", "status": "Success"})


def crop_health_layer_shown(driver, obj, test_flow_steps):
    """The check this module exists for: is the crop-health layer on the map?
    The Allure report gets the screenshot, the detected layer marked on it and the
    measurements, under a step titled SHOWN or NOT SHOWN."""
    with allure.step("2. Check the crop health layer is shown on the map"):
        png, img, result, layout, attempts = _wait_for_layer(driver, obj)
        evidence = encode_png(annotate_crop_health(img, result))
        obj.crop_health_result = result

        verdict = "SHOWN" if result["shown"] else "NOT SHOWN"
        title = f"Crop health layer: {verdict} ({result['coverage_pct']}% of the map)"
        with allure.step(title):
            allure.attach(png, name="Crop health screen", attachment_type=allure.attachment_type.PNG)
            allure.attach(evidence, name=f"Detected layer - {verdict}",
                          attachment_type=allure.attachment_type.PNG)
            allure.attach(json.dumps(_measurements(result, layout, attempts), indent=2, default=str),
                          name="Crop health measurements", attachment_type=allure.attachment_type.JSON)
            if not result["shown"]:
                pytest.fail(f"Crop health is NOT shown: {result['reason']} "
                            f"(waited {LAYER_TIMEOUT_S}s, {attempts} screenshots; see the attached screenshot).")
        test_flow_steps.append({"step": "Crop health layer shown", "status": "Success",
                                "coverage_pct": result["coverage_pct"], "dominant": result["dominant"]})


def crop_health_legend_and_dates(driver, obj, test_flow_steps):
    with allure.step("3. Check the legend and dates are shown"):
        texts = {key: _read_text(driver, getattr(obj, f"{key}_xpath")) for key in _LABELS}
        legend = (getattr(obj, "crop_health_result", None) or {}).get("legend")
        report = {"labels": texts, "legend_bar": legend}
        allure.attach(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                      name="Legend and dates", attachment_type=allure.attachment_type.JSON)

        missing = [key for key, value in texts.items() if value is None]
        if missing:
            pytest.fail(f"Not shown on the crop health screen: {', '.join(missing)}.")
        if legend is not None and not legend.get("ok"):
            pytest.fail(f"The legend bar does not read as bright green fading to darker: {legend.get('reason')}")
        for key in ("last_update_date", "last_clear_image", "selected_date"):
            if not re.search(r"\d{2}-\d{2}-\d{4}", texts[key]):
                pytest.fail(f"'{key}' has no dd-mm-yyyy date: {texts[key]!r}")
        test_flow_steps.append({"step": "Legend and dates shown", "status": "Success", "labels": texts})


def date_slider_changes_layer(driver, obj, test_flow_steps):
    """Tap the date minus control and check the screen moved to another date: the
    selected date changes, or at least the map re-renders."""
    with allure.step("4. Move the date slider and check the layer updates"):
        before_png, before_img, before, layout, _ = _wait_for_layer(driver, obj)
        date_before = _read_text(driver, obj.selected_date_xpath)

        if not smart_click(driver, "Date minus", obj.date_minus_xpath):
            pytest.fail("Could not find or click the date slider's minus control "
                        "(locator 'date_minus' in regular_farmer_crophealth.json).")
        time.sleep(2)
        after_png, after_img, after, _, _ = _wait_for_layer(driver, obj, timeout=15)
        date_after = _read_text(driver, obj.selected_date_xpath)

        comparison = validate_date_slider_changed(before_img, after_img, before["roi"])
        date_changed = bool(date_before and date_after and date_before != date_after)
        evidence = encode_png(annotate_crop_health(after_img, after))
        verdict = ("date and map changed" if date_changed and comparison["map_changed"] else
                   "date changed" if date_changed else
                   "map changed" if comparison["map_changed"] else "NO CHANGE")
        with allure.step(f"Date slider: {verdict}; layer {'SHOWN' if after['shown'] else 'NOT SHOWN'} on the new date"):
            allure.attach(before_png, name="Before", attachment_type=allure.attachment_type.PNG)
            allure.attach(after_png, name="After", attachment_type=allure.attachment_type.PNG)
            allure.attach(evidence, name="Detected layer after", attachment_type=allure.attachment_type.PNG)
            allure.attach(json.dumps({
                "selected_date_before": date_before, "selected_date_after": date_after,
                "date_changed": date_changed, "map_comparison": comparison,
                "layer_shown_before": before["shown"], "layer_shown_after": after["shown"],
                "distribution_before": before["bands"], "distribution_after": after["bands"],
            }, indent=2, default=str), name="Date slider comparison",
                attachment_type=allure.attachment_type.JSON)
            if not date_changed and not comparison["map_changed"]:
                pytest.fail(f"The date slider did not change anything: the selected date stayed "
                            f"{date_before!r} and the map is unchanged (SSIM {comparison['ssim_score']}).")
        test_flow_steps.append({"step": "Date slider updated the screen", "status": "Success",
                                "date_before": date_before, "date_after": date_after})


# ===========================================================================
# Date slider: go to a given date
# ===========================================================================

def _parse_date(text):
    """The dd-mm-yyyy date in a text such as '16-06-2026 | Day -34', or None."""
    m = re.search(r"\d{2}-\d{2}-\d{4}", text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%d-%m-%Y").date()
    except ValueError:
        return None


def _selected_date(driver, obj):
    return _parse_date(_read_text(driver, obj.selected_date_xpath))


def _wait_for_date_change(driver, obj, previous, timeout=None):
    """The date on screen once it differs from `previous`, or None if it doesn't."""
    deadline = time.time() + (DATE_CHANGE_WAIT_S if timeout is None else timeout)
    while True:
        now = _selected_date(driver, obj)
        if now is not None and now != previous:
            return now
        if time.time() >= deadline:
            return None
        time.sleep(0.15)


def _map_unchanged(before, after, roi):
    """True when the map area looks the same in two screenshots."""
    x, y, w, h = roi
    a, b = before[y:y + h, x:x + w], after[y:y + h, x:x + w]
    return a.shape == b.shape and float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) < 1.0


def _settled_capture(driver, obj):
    """A screenshot taken once the map has stopped changing after a date change
    (the last one if it is still changing after SETTLE_TIMEOUT_S). Returns
    (png_bytes, image, map_roi, legend_roi, layout)."""
    deadline = time.time() + SETTLE_TIMEOUT_S
    shot = _capture(driver, obj)
    while time.time() < deadline:
        time.sleep(SETTLE_POLL_S)
        latest = _capture(driver, obj)
        if _map_unchanged(shot[1], latest[1], latest[2]):
            return latest
        shot = latest
    return shot


def _stress_on_screen(driver, obj):
    """Look at the map now: (png_bytes, image, layer_result, stress_result, regions),
    where regions is the number of marker regions found per stress type. Stress is
    only looked for when the crop-health layer is on the map."""
    png, img, map_roi, legend_roi, _ = _settled_capture(driver, obj)
    layer = analyze_crop_health(img, map_roi, legend_roi)
    stress = analyze_stress(img, map_roi) if layer["shown"] else None
    regions = {n: (stress["types"][n]["parts"] if stress else 0) for n in STRESS_TYPES}
    return png, img, layer, stress, regions


def _walk_entry(day, layer, regions):
    return {"date": f"{day:%d-%m-%Y}" if day else None, "layer_shown": layer["shown"],
            "layer_coverage_pct": layer["coverage_pct"],
            "stress_regions": {STRESS_LABELS[n]: k for n, k in regions.items()}}


def _fail_walk(message, png, walk, began):
    """Attach what was checked, then fail the step."""
    allure.attach(png, name="Last screen checked", attachment_type=allure.attachment_type.PNG)
    allure.attach(json.dumps({"dates_checked": walk, "seconds": round(time.time() - began, 1)},
                             indent=2), name="Dates checked for stress pixels",
                  attachment_type=allure.attachment_type.JSON)
    pytest.fail(message)


def date_slider_until_stress(driver, obj, test_flow_steps):
    """Click the date slider's minus icon, one date at a time, until stress pixels
    (Caution, Warning, Stressed or Severely Stressed markers) appear on the farm.

    Each date is judged on a screenshot taken once the map has finished drawing.
    Stops on the current date if it already has stress pixels. Fails if the
    slider reaches its end, or MAX_DATE_CLICKS, without any.
    """
    with allure.step("4. Click the date minus icon until stress pixels appear on the farm"):
        current = start = _selected_date(driver, obj)
        if current is None:
            pytest.fail("Could not read the selected date on the crop health screen.")

        began = time.time()
        png, img, layer, stress, regions = _stress_on_screen(driver, obj)
        walk = [_walk_entry(current, layer, regions)]
        clicks, stalls, control = 0, 0, None
        while not any(regions.values()):
            if clicks >= MAX_DATE_CLICKS:
                _fail_walk(f"No stress pixels appeared on the farm after {clicks} clicks on the date "
                           f"minus icon ({start:%d-%m-%Y} back to {current:%d-%m-%Y}).", png, walk, began)
            if control is None:
                control = _smallest_displayed(driver, obj.date_minus_xpath)
            if control is None:
                _fail_walk(f"The date minus icon is not on screen at {current:%d-%m-%Y} (locator "
                           "'date_minus' in regular_farmer_crophealth.json).", png, walk, began)
            try:
                control.click()
            except Exception:                      # the screen re-rendered: look the icon up again
                control = _smallest_displayed(driver, obj.date_minus_xpath)
                if control is None:
                    _fail_walk(f"The date minus icon disappeared at {current:%d-%m-%Y}.", png, walk, began)
                control.click()
            clicks += 1

            new = _wait_for_date_change(driver, obj, current)
            if new is None:
                stalls += 1
                if stalls >= DATE_STALLS_ALLOWED:
                    _fail_walk(f"No stress pixels on the farm on any of the {len(walk)} date(s) from "
                               f"{start:%d-%m-%Y} back to {current:%d-%m-%Y}: the date stayed "
                               f"{current:%d-%m-%Y} after {stalls} clicks, so the slider is at its end.",
                               png, walk, began)
                continue
            stalls = 0
            current = new
            png, img, layer, stress, regions = _stress_on_screen(driver, obj)
            walk.append(_walk_entry(current, layer, regions))
            if clicks % 10 == 0:
                print(f"[crop health] {clicks} clicks, now {current:%d-%m-%Y}, no stress pixels yet")

        found = ", ".join(f"{STRESS_LABELS[n]} ({k} region{'s' if k != 1 else ''})"
                          for n, k in regions.items() if k)
        title = (f"Stress pixels on {current:%d-%m-%Y} after {clicks} click{'s' if clicks != 1 else ''}"
                 f": {found}")
        with allure.step(title):
            allure.attach(png, name="Crop health screen", attachment_type=allure.attachment_type.PNG)
            allure.attach(encode_png(annotate_stress_markers(img, stress)),
                          name="Stress markers detected on the map",
                          attachment_type=allure.attachment_type.PNG)
            allure.attach(json.dumps({"from": f"{start:%d-%m-%Y}", "stopped_at": f"{current:%d-%m-%Y}",
                                      "clicks": clicks, "seconds": round(time.time() - began, 1),
                                      "dates_checked": walk}, indent=2),
                          name="Dates checked for stress pixels",
                          attachment_type=allure.attachment_type.JSON)
        obj.stress_date = current
        test_flow_steps.append({"step": "Date slider moved until stress pixels appeared", "status": "Success",
                                "from": f"{start:%d-%m-%Y}", "date": f"{current:%d-%m-%Y}",
                                "clicks": clicks, "stress_regions": walk[-1]["stress_regions"]})


# ===========================================================================
# Stress types: Caution, Warning, Stressed, Severely Stressed
# ===========================================================================

_STRESS_WORDS = re.compile(r"severely\s+stressed|caution|warning|stressed", re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def parse_stress_legend(strings):
    """{type: percentage} read from the texts on the screen, in document order.

    Handles a label followed by its value ("Caution", "0.30%"), a label and value
    in one string ("Caution 0.30%"), and all labels listed before all values.
    """
    blob = " | ".join(strings)
    labels = [(m.start(), m.end(), re.sub(r"\s+", "_", m.group(0).lower()))
              for m in _STRESS_WORDS.finditer(blob)]
    values = [(m.start(), float(m.group(1).replace(",", "."))) for m in _PERCENT.finditer(blob)]

    found = {}
    for i, (_, end, key) in enumerate(labels):
        following = labels[i + 1][0] if i + 1 < len(labels) else len(blob)
        between = [v for pos, v in values if end <= pos < following]
        if between and key not in found:
            found[key] = between[0]
    if len(found) < len(set(key for _, _, key in labels)) and len(labels) == len(values):
        found = {key: v for (_, _, key), (_, v) in zip(labels, values)}
    return found


def _page_strings(driver):
    """Every text and content-desc on the screen, in document order."""
    root = ET.fromstring(driver.page_source.encode("utf-8"))
    out = []
    for node in root.iter():
        for attribute in ("text", "content-desc"):
            value = (node.get(attribute) or "").strip()
            if value:
                out.append(value)
    return out


def _read_stress_legend(driver):
    """The percentages the app displays for each stress type ({} if none shown)."""
    return parse_stress_legend(_page_strings(driver))


def crop_health_stress_types(driver, obj, test_flow_steps):
    """Detect the stress types on the map and compare them with the percentages
    the app displays under the date slider."""
    with allure.step("5. Detect the stress types and their percentages"):
        png, img, result, layout, attempts = _wait_for_layer(driver, obj)
        date = _selected_date(driver, obj)
        date_text = f"{date:%d-%m-%Y}" if date else "the selected date"
        if not result["shown"]:
            allure.attach(png, name="Crop health screen", attachment_type=allure.attachment_type.PNG)
            pytest.fail(f"Cannot measure stress on {date_text}: crop health is NOT shown "
                        f"({result['reason']}).")

        displayed = _read_stress_legend(driver)
        stress = analyze_stress(img, result["roi"])

        rows, problems = [], []
        # All four shown as 0% while the map has stress markers: the figures are wrong.
        marked = sum(stress["types"][n]["parts"] for n in STRESS_TYPES)
        all_zero = all(displayed.get(n) == 0 for n in STRESS_TYPES)
        if all_zero and marked:
            on_map = ", ".join(f"{STRESS_LABELS[n]} {stress['types'][n]['parts']}" for n in STRESS_TYPES
                               if stress["types"][n]["parts"])
            problems.append(f"Caution, Warning, Stressed and Severely Stressed are all displayed as 0% "
                            f"although stress pixels are on the map ({marked} marker region(s): {on_map})")
        for name in STRESS_TYPES:
            on_map = stress["types"][name]
            shown = displayed.get(name)
            rows.append({
                "type": STRESS_LABELS[name],
                "displayed_pct": shown,
                "detected_on_map": on_map["detected"],
                "marker_regions": on_map["parts"],
                "measured_pct_of_layer": on_map["area_pct_of_layer"],
                "difference_pct_points": None if shown is None
                else round(on_map["area_pct_of_layer"] - shown, 2),
            })
            if shown is None:
                problems.append(f"{STRESS_LABELS[name]}: no percentage is displayed")
                continue
            if shown > 0 and not on_map["detected"]:
                problems.append(f"{STRESS_LABELS[name]} is displayed as {shown}% but no markers "
                                "of its colour are on the map")
            elif shown == 0 and on_map["detected"] and not all_zero:   # all-zero is reported above
                problems.append(f"{STRESS_LABELS[name]} is displayed as 0% but "
                                f"{on_map['parts']} marker region(s) of its colour are on the map")
            elif abs(on_map["area_pct_of_layer"] - shown) > STRESS_PCT_TOLERANCE:
                problems.append(f"{STRESS_LABELS[name]} is displayed as {shown}% but the markers cover "
                                f"{on_map['area_pct_of_layer']}% of the layer (more than "
                                f"{STRESS_PCT_TOLERANCE} points apart)")
        known = [n for n in STRESS_TYPES if displayed.get(n) is not None]
        for a in known:
            for b in known:
                if displayed[a] >= STRESS_RANK_RATIO * displayed[b] > 0 and \
                        stress["types"][a]["area_px"] < stress["types"][b]["area_px"]:
                    problems.append(f"{STRESS_LABELS[a]} ({displayed[a]}%) should cover more of the map "
                                    f"than {STRESS_LABELS[b]} ({displayed[b]}%), but covers less")

        summary = " | ".join(f"{STRESS_LABELS[n]} {displayed[n]}%" if displayed.get(n) is not None
                             else f"{STRESS_LABELS[n]} not shown" for n in STRESS_TYPES)
        evidence = encode_png(annotate_stress_markers(img, stress))
        with allure.step(f"Stress on {date_text}: {summary}"):
            allure.attach(png, name="Crop health screen", attachment_type=allure.attachment_type.PNG)
            allure.attach(evidence, name="Stress markers detected on the map",
                          attachment_type=allure.attachment_type.PNG)
            allure.attach(json.dumps({"date": date_text, "stress_types": rows,
                                      "layer_area_px": stress["layer_area_px"],
                                      "tolerance_pct_points": STRESS_PCT_TOLERANCE,
                                      "problems": problems}, indent=2, default=str),
                          name="Stress types and percentages",
                          attachment_type=allure.attachment_type.JSON)
            if problems:
                pytest.fail("Stress types do not match the screen: " + "; ".join(problems) + ".")
        test_flow_steps.append({"step": "Stress types detected", "status": "Success", "date": date_text,
                                "displayed_pct": {n: displayed.get(n) for n in STRESS_TYPES}})
