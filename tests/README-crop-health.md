# Crop health detection: report

What the suites check on the regular farmer app's **Crop Health** screen, how each
check works, what the Allure report shows, and what is and isn't proven.

```
tests/utils/opencv_crop_health.py                                   image analysis (no driver)
tests/pages/regular_farmer/regular_farmer_crophealth_page.py        the screen's steps
tests/test_suites/end_to_end/regular_farmer/test_crophealth_pytest.py   the tests
tests/locators/regular_farmer_crophealth.json                       the screen's locators
```

## 1. Summary

| | |
| --- | --- |
| **Screen** | Crop Health for one farm: a satellite map with a crop-health layer (pixels from bright green to black), a "No issue" to "May be issue" legend, a date slider, and a stress legend card (Caution, Warning, Stressed, Severely Stressed with percentages). |
| **Test** | `E2E_RF_003`: the layer is shown, then the date minus icon is clicked until stress pixels appear on the farm, and the stress types and their percentages are checked. |
| **Approach** | Screenshots are taken from the driver while the test runs, kept in memory, analysed with OpenCV, and attached to Allure as PNG bytes. No image file or path is involved. |
| **No API access needed** | Everything is read from the screen: pixels and the accessibility tree. |
| **Status** | Verified offline on your two screenshots and a fake device. **Not yet run on a real device or in CI.** |

## 2. The test

`E2E_RF_003` (in `test_crophealth_pytest.py`) runs these steps in order:

| Step | Function | What it checks |
| --- | --- | --- |
| 1 | `farm_card`, `crop_health_screen_loaded` | Opens the farm (does nothing if the screen is already open) and waits for "Crop Health" and "No issue". |
| 2 | `crop_health_layer_shown` | The **layer is on the map**: verdict SHOWN / NOT SHOWN with screenshot. |
| 4 | `date_slider_until_stress` | Clicks the **date minus icon until stress pixels appear on the farm** (section 6). |
| 5 | `crop_health_stress_types` | Detects the **four stress types** and compares their displayed percentages with the markers on the map (section 5). |

`crop_health_legend_and_dates` and `date_slider_changes_layer` are still in the page
module, but the test doesn't call them at present.

**Confirm `E2E_RF_003` against your test catalogue**: the runner matches tests by ID.

## 3. How the layer is detected

The map draws the vegetation index as a layer of **pure green (R and B close to
0) whose brightness is the value**: bright green = "No issue", black = "May be
issue". A regular grid of holes lets the satellite basemap show through.

> The layer is **not** the palette of the legend bar under the map (a yellower
> green). So pixels are classified by green brightness, not by matching legend colours.

`analyze_crop_health(image, roi, legend_roi)`:

1. **Heat mask** (`heat_mask`): a pixel is layer when it is green-dominant (G leads
   both R and B by at least 25, and R, B stay under 45% of G) **or** near-black (every
   channel at most 14). Satellite fields (more red) and the dark grey share and
   fullscreen buttons (all channels equal, about 35) are not.
2. **Region**: the holes in the grid are closed, and the largest connected region is
   taken as the layer.
3. **Verdict**: `shown` when that region covers at least **3%** of the map area.
4. **Distribution**: the green channel of the layer's pixels is split into four bands
   of the index (see below).
5. **Legend bar**: sampled from the screen (median over the bar's rows, since the
   labels sit on it); it must be a bright green on the left and at least 60 darker in
   green on the right.

### Bands of the index

| Band key | Index (green channel / 255) | Meaning on the legend |
| --- | --- | --- |
| `healthy` | 0.60 and above | "No issue" end |
| `moderate` | 0.35 to 0.60 | |
| `stressed` | 0.15 to 0.35 | |
| `severe` | below 0.15 | black, "May be issue" |

> These are **brightness bands of the layer**. They are not the app's stress types
> (Caution, Warning, Stressed, Severely Stressed), which are the coloured markers in
> section 5. The key names `stressed` and `severe` are inherited from the old module
> so `validate_date_slider_changed` keeps working.

### Measured on your screenshot (12-07-2026)

| | |
| --- | --- |
| Layer coverage of the map | 27.3% |
| Bands | healthy 60.1% · moderate 24.1% · stressed 9.6% · severe 6.2% |
| Legend bar | left (113, 243, 30) → right (9, 64, 31), read as OK |

## 4. Where the map and legend are found

The map is the area between the card header ("Last Update Date") and the icon row
(Navigation, Diary, Weather) drawn over its bottom edge; the legend is the bar of
"No issue" / "May be issue" labels under it. They are **anchored on those screen
elements** (taking the smallest matching element, since a container whose
content-desc repeats its children's text also matches). If an element isn't found,
proportions measured on a screenshot are used instead. Which one was used is
recorded in the Allure measurements as `areas_found_by`.

The layer is drawn from tiles fetched when the screen opens, so it can arrive after
the basemap: the test **keeps taking screenshots every 2 s for up to 30 s** before
calling it missing.

## 5. Stress types

The app marks the parts of the farm that need attention with small outlined cells in
four flat colours, and a card under the date slider names each colour and gives its
share:

| Type | Marker colour (RGB) | Example shown |
| --- | --- | --- |
| Caution | yellow (255, 255, 1) | 0.30% |
| Warning | orange (255, 165, 1) | 0.75% |
| Stressed | magenta (255, 65, 255) | 1.56% |
| Severely Stressed | red (255, 1, 1) | 0.15% |

The test gets the figure two independent ways and compares them.

**What the app displays** (`parse_stress_legend`): every text and content-desc on the
screen is read from the page source, in document order, and parsed. It copes with a
label followed by its value, a label and value in one string, and all labels before
all values.

**What the map shows** (`analyze_stress`): each colour is found on and just around the
layer, specks under 8 px are ignored, and the markers' **filled area as a % of the
layer's area** is the estimate.

On your screenshot (11-03-2026):

| Type | Displayed | Measured on the map | Difference |
| --- | --- | --- | --- |
| Caution | 0.30% | 0.43% | +0.13 |
| Warning | 0.75% | 0.85% | +0.10 |
| Stressed | 1.56% | 1.27% | -0.29 |
| Severely Stressed | 0.15% | 0.19% | +0.04 |

Same rank order on both. The test **fails** when:

- **all four types are displayed as 0% while stress pixels are on the map**;
- a type has no displayed percentage;
- a type shown above 0% has no markers of its colour on the map;
- a type shown as 0% has markers on the map;
- displayed and measured differ by more than **0.75 percentage points**;
- two types whose displayed shares differ by 1.5x or more rank the opposite way on the map.

The measurement corroborates the displayed number; it does not replace it. A marker
is an outlined cell, so the estimate is approximate.

## 6. Date slider: walking back until stress appears

`date_slider_until_stress` does **not** use a fixed date. It looks at the map on the
current date and, while no stress pixels are on the farm, clicks the date minus icon
once and looks again.

- **Stress pixels** are Caution, Warning, Stressed or Severely Stressed markers found by
  `analyze_stress` on the crop-health layer. A date where the layer isn't shown has none.
- **Each date is judged on a settled screenshot**: after the date changes the map
  redraws, so screenshots are taken every 0.5 s until two in a row are the same (up to
  8 s). Without this a frame caught mid-redraw can miss the markers and the walk goes
  one day too far.
- **Stops** on the first date with stress pixels; with **0 clicks** if the starting date
  already has them.
- **Fails** if the date stops changing for 3 clicks (the slider's end) or after 400
  clicks, saying how many dates were checked and from which date back to which.
- **Speed**: two or more screenshots per date, so a walk of about 120 dates takes a few
  minutes on a device. Progress is printed every 10 clicks.

## 7. What the Allure report shows

| Step | Attachments |
| --- | --- |
| `2. Check the crop health layer is shown on the map` → **`Crop health layer: SHOWN (28.4% of the map)`** or **`NOT SHOWN`** (failed) | `Crop health screen`, `Detected layer - SHOWN/NOT SHOWN` (layer tinted magenta, map area outlined, verdict banner), `Crop health measurements` (coverage, bands, legend, areas, how they were found, screenshots taken) |
| `3. Check the legend and dates are shown` | `Legend and dates` (each label's text, legend bar reading) |
| `4. Click the date minus icon until stress pixels appear on the farm` → **`Stress pixels on 11-03-2026 after 123 clicks: Caution (2 regions), ...`** | `Crop health screen`, `Stress markers detected on the map`, `Dates checked for stress pixels` (every date checked: layer shown, coverage, regions per type). On failure: `Last screen checked` and the same list. |
| `5. Detect the stress types and their percentages` → **`Stress on <date>: Caution 0.3% \| Warning 0.75% \| ...`** | `Crop health screen`, `Stress markers detected on the map` (every marker boxed, count per type), `Stress types and percentages` (displayed, detected, regions, measured, difference, problems) |

The evidence image for the layer is tinted magenta; the stress evidence image is
**not** tinted, because magenta is also the "Stressed" marker colour.

When a test fails, `conftest.py` also attaches its usual "Failure Screenshot".

## 8. Locators

`regular_farmer_crophealth.json` (the farm card is reused from `fr_fa_updates.json`):

| Key | Locator |
| --- | --- |
| `date_minus` | `//android.view.ViewGroup[@resource-id="date-slider-control-previous-date-button"]` |
| `date_plus` | `//android.view.ViewGroup[@resource-id="date-slider-control-next-date-button"]` |
| `crop_health_title`, `last_update_date`, `last_clear_image`, `legend_no_issue`, `legend_may_be_issue`, `selected_date` | `contains(@text, ...) or contains(@content-desc, ...)` on the visible text |
| `navigation_icon` | `//android.view.ViewGroup[@content-desc="Navigation"]` |

The text locators were written from what the screenshots show. If one isn't found
the failing step names it.

## 9. Configuration

In `regular_farmer_crophealth_page.py`:

| Name | Value | Meaning |
| --- | --- | --- |
| `LAYER_TIMEOUT_S` / `LAYER_POLL_S` | 30 / 2.0 | How long to wait for the layer to arrive. |
| `MAX_DATE_CLICKS` | 400 | Safety stop for the date walk. |
| `SETTLE_TIMEOUT_S` / `SETTLE_POLL_S` | 8 / 0.5 | How long a date may take to finish redrawing, and how often to look. |
| `DATE_CHANGE_WAIT_S` / `DATE_STALLS_ALLOWED` | 6 / 3 | Per click, and clicks in a row that may change nothing. |
| `STRESS_PCT_TOLERANCE` | 0.75 | Allowed gap between displayed and measured, in percentage points. |
| `STRESS_RANK_RATIO` | 1.5 | Displayed shares at least this far apart must rank the same on the map. |
| `DEFAULT_MAP`, `DEFAULT_LEGEND` | proportions | Used only if the screen elements can't be found. |

In `opencv_crop_health.py`:

| Name | Value | Meaning |
| --- | --- | --- |
| `MIN_LAYER_COVERAGE_PCT` | 3.0 | Layer must cover this much of the map to be "shown". |
| `HEAT_GREEN_LEAD`, `HEAT_SIDE_RATIO`, `HEAT_NEAR_BLACK_MAX` | 25, 0.45, 14 | What counts as a layer pixel. |
| `STRESS_MARKER_RGB` | see section 5 | Measured on the legend dots. |
| `STRESS_MAX_COLOUR_DISTANCE`, `STRESS_MIN_PART_PX` | 60, 8 | Colour match and minimum marker size. |
| `SSIM_CHANGE_THRESHOLD` | 0.95 | Below this the map counts as changed. |

## 10. When it fails

| Message | Means | Do |
| --- | --- | --- |
| `Crop health is NOT shown: no crop-health layer: its largest region covers 0.0% of the map` | No layer after 30 s. | Open the attached screenshot: map still loading, no data for the date, or the app left the screen. |
| `The crop health screen did not open: 'Crop Health' / 'No issue' is not on screen` | The farm card didn't lead to the screen. | Check the farm card locator in `fr_fa_updates.json` and the app's state. |
| `Not shown on the crop health screen: <keys>` | A label or date text is missing. | Check that locator in `regular_farmer_crophealth.json`. |
| `The legend bar does not read as bright green fading to darker` | The legend bar looks wrong. | Open the attachment: its left and right colours are recorded. |
| `No stress pixels on the farm on any of the N date(s) from <a> back to <b>: ... the slider is at its end` | The whole history was walked without a stress marker on the farm. | Open `Dates checked for stress pixels`. If the app shows stress you can see but the test doesn't, the marker colours need re-measuring (`STRESS_MARKER_RGB`). |
| `The date minus icon is not on screen` | The `date_minus` locator didn't match. | Check it in `regular_farmer_crophealth.json`. |
| `Stress types do not match the screen: ...` | Displayed and detected stress disagree. | Open `Stress types and percentages` and the marker image. |
| `... are all displayed as 0% although stress pixels are on the map` | The card says no stress but the map shows markers. | A defect in the app's figures: the attached marker image shows where. |
| `...: no percentage is displayed` | The stress card isn't on this date. | Open the screenshot: the card may not have loaded. |

## 11. What was fixed in the existing module

`opencv_crop_health.py` existed but nothing used it, and it could not run:

| Problem | Fix |
| --- | --- |
| It imported `scikit-image`, which isn't in `requirements.txt`, so the module failed on import. | SSIM is computed with OpenCV. |
| "Stress" buckets looked for yellow, red and magenta hues, which never appear on a green-to-black scale. | Classified by green brightness. |
| The black end of the scale (V below 40) counted as nothing. | Near-black is part of the layer. |
| It passed on any 5% of green-ish pixels, so farmland imagery passed with no layer drawn. | The layer's largest connected region must cover 3% of the map. |
| Every function required an image file path. | Every function takes the driver's screenshot (an array) or a path. |

The leaf and soil moisture validators in the same file are **untouched**, and still
carry their placeholder reference pixels (`FILL IN`).

## 12. What was verified, and what wasn't

**Verified offline**

- **Image analysis (16 checks)** on your first screenshot and negatives built from it: the layer detected as the farm polygon; buttons ignored; layer missing, wrong palette, a launcher screen and bare farmland not shown; an all-black layer still shown; darker data moving the bands; SSIM.
- **The test under pytest** against a fake device that serves your screenshots and answers the locators. The date walks back one day per click and stress exists only from 11-03-2026, which the test isn't told:
  - finds 11-03-2026 by itself after 123 clicks and passes;
  - stops with 0 clicks when the starting date already has stress;
  - fails when no date has stress before the slider's end (73 dates checked);
  - **fails when all four are displayed as 0% with markers on the map**;
  - fails on a wrong displayed percentage;
  - handles a frame caught mid-redraw: with settling switched off the same case stops a day late (10-03-2026), with it on it stops on 11-03-2026.
- **Earlier variants** (layer missing, labels missing, app gone, legend in three layouts, no legend, rank mismatch) were run before the walk changed; the steps they cover are unchanged.
- **No file written**: the fake device raises if a screenshot file is requested.

**Not verified**

- **A real device or CI run.** Accessibility-tree text and locators are inferred from screenshots.
- **The accuracy of the vegetation values.** The tests prove the layer is drawn and its colours are in range, not that the values are right for the field. That needs reference data.
- **The stress measurement on other farms, zoom levels and resolutions.** The 0.75-point tolerance and the marker colours come from one 342 px wide screenshot. Run it once and inspect the `Stress types and percentages` attachment before relying on the tolerance.
- **The relationships between dates** ("Last Update Date", "Last Clear Image", selected date). They are read and format-checked only; the rules should be confirmed with the product team.

## 13. Known limits

- **A marker "region" is a connected piece of outline**, not an exact marker count.
- **The walk stops on the first date with stress markers.** If the app shows stress you can see but the colours differ from `STRESS_MARKER_RGB`, it walks past it: re-measure the colours on a device screenshot.
- **The date walk is slow by design**: one click, one date read and a settled screenshot per day.
- **A large existing layer region elsewhere on the map**, such as a second farm in view, would be counted if it is the largest connected region.
