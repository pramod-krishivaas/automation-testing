# Draw on map: the farm boundary flow

How the suites draw a farm boundary on the app's **Draw on map** screen, why each
part is there, and what to do when it fails. Code:

```
tests/utils/location_utils.py                                  device location, the checks, the taps
tests/pages/regular_client/regular_client_onboarding_page.py   the flow's steps
tests/test_suites/end_to_end/regular_client/test_onboarding_pytest.py   the flow
tests/locators/state_client.json  -> draw_boundary_screen      the screen's locators
```

## The six steps

1. **Set a known mock location** so the map opens on this run's own ground.
2. **Wait for the map** to finish drawing.
3. **Check the ground is free** with OpenCV: existing boundaries are drawn in one
   green, so the area the new boundary will occupy must show none of it.
4. **Work out the 4 corners** from where the map actually is on screen.
5. **Tap the 4 corners and close the polygon** (the first corner twice), after a
   3-second pause for the map to hold still at its new location. If the area is
   unchanged afterwards, nothing was drawn, so the taps are repeated with the
   other press length before the step gives up.
6. **If the ground is taken, search a place by name** and try steps 2, 3 and 5 there.

## The screen

"Draw on map" is a **native Google Map** (react-native-maps), not a web view. Above
it a header shows the location the app is using (`Lat: 17.4401  Lon: 78.3992  Acc: 17`).
Over the map sit a search box, three round buttons on the right (polygon, delete,
current location), a compass (bottom right) and the Google logo (bottom left).

Facts the flow relies on, measured on a 720x1600 phone:

| What | Detail |
| --- | --- |
| Existing boundaries | Drawn in one green, RGB (23, 163, 74). Satellite imagery never matches it: trees are far darker, fields yellower. |
| Overlapping is rejected | The app refuses a boundary crossing an existing farm ("The boundary crosses an existing farm boundary. Please choose a different location."). |
| The map's bounds | The map fills the card from x 33 to 687, y 315 to 1419. **x 690 is the card's white border, not the map**: taps there do nothing. |
| Where it opens | On the location the app has, so the device's GPS decides which ground you draw on. |
| How a tap counts | Google Maps counts a tap only once no second tap follows within ~300 ms; a quicker tap cancels the one before it, and two quick taps near each other are a double-tap zoom. |
| The search box | Google Places autocomplete. It takes place **names**, not coordinates, and a result row is labelled like "Medak, Telangana, India". |

## The flow

In `test_onboarding_pytest.py`:

```python
set_run_location(driver, self, test_flow_steps)   # step 1, before the map opens
...                                               # add farmer, add farm, add crop
draw_boundary_buton_on_modal(...)                 # "Draw boundary" on the modal
...
draw_boundary_on_map(driver, self, test_flow_steps)   # steps 2-6
save_boundary_button(...)
# finally:
reset_device_location(driver)                     # stop mocking the GPS
```

`set_run_location` runs **at the start of the test**, not next to the drawing: the
map opens on whatever location the app already has, so the GPS has to be moved
before the screen appears. It never fails the test; if mocking doesn't work, the
ground will look taken and step 6 takes over.

### A different spot for every run

Overlapping boundaries are rejected and test farms are never deleted, so two runs
must not draw on the same ground.

- The ground around `TEST_AREA_CENTER` is divided into cells `TEST_AREA_CELL_M`
  apart (1 km), numbered in a spiral outward from the centre; `TEST_AREA_RINGS`
  = 10 gives 441 cells, about 20 x 20 km.
- A run takes the cell for the **current minute** (`run_minute`, counted from
  2026-01-01 UTC). Runs a minute or more apart get different cells, on any laptop
  or in CI, with no shared counter.
- Two runs drawing in the same minute get the same cell. The check in step 3
  catches that only if the first has already saved.

## Configuration

In `regular_client_onboarding_page.py`:

| Name | Meaning |
| --- | --- |
| `TEST_AREA_CENTER` | Centre of the area used for test farms. **Set this to an area agreed for testing**, away from real farms; the default is a placeholder near Chevella, Telangana. |
| `TEST_AREA_CELL_M` | Distance between cells (1000 m). Must exceed the boundary's real size at the map's zoom. |
| `TEST_AREA_RINGS` | Rings around the centre; 10 gives 441 cells. |
| `FALLBACK_PLACES` | Place names for step 6. Each holds one boundary, so a longer list means more fallback capacity. |

In `location_utils.py`:

| Name | Meaning |
| --- | --- |
| `BOUNDARY_FRACTIONS` | The boundary rectangle as fractions of the map (0.454, 0.464, 0.546, 0.536): a small box centred on the map, about 60x80 px on the phone. Widen it for a larger farm. |
| `BOUNDARY_HSV_LOW` / `_HIGH` | The green of existing boundaries. Re-measure if the app's colour changes. |
| `BOUNDARY_PX_ALLOWED` | Green pixels tolerated in the target area before it counts as taken (25). One line across it is hundreds. |
| `MAP_SCREEN_FRACTIONS` | Where the map sits when its view can't be found, as fractions of the screen. |
| `MAP_XPATH` | The map view, `content-desc="Google Map"`. |
| `MAP_MOVE_WAIT_S` | Pause before the first tap (3.0 s), while the map settles on the location. |
| `TAP_GAP_S` | Seconds between taps (1.0). Taps closer than ~300 ms cancel each other. |
| `PRESS_MS` / `RETRY_PRESS_MS` | How long each press lasts (1000 ms), and what is tried when nothing gets drawn (100 ms). Only a short press is a tap, which is what adds a vertex; from about half a second the map sees a long press instead. If the retry is what works on your device, make it the default. |

Locators, under `draw_boundary_screen` in `tests/locators/state_client.json` (the
file the regular_client page loads):

```
draw_boundary_button        the modal's "Draw on map"
save_boundary_button        "Save Boundary"
search-input                //android.widget.EditText[@resource-id="location-search-input"]
search-result               a result row (currently written for one place name)
```

## Requirements

- **Mock location on a real phone.** UiAutomator2 allows the Appium Settings app
  as the mock location app at session start. Some phones (MIUI) need it once by
  hand: Developer options > Select mock location app > Appium Settings.
- **OpenCV** (`opencv-python`, already in `requirements.txt`) for step 3.
- **Play services recent enough for the current Google Maps renderer.** The older,
  legacy renderer needs `org.apache.http` and **crashes any app that doesn't
  declare it**. The API 30 emulator image ships Play services 20.18.17 and does
  crash the app as the map opens; a real phone with current Play services is fine.
  In CI, run with `android_api_level` 34 or newer (`ci/run_on_emulator.sh` prints
  the image's Play services version after boot and warns below 22, which is where
  the new renderer became usual). The permanent fix belongs in the app:
  `<uses-library android:name="org.apache.http.legacy" android:required="false" />`
  inside `<application>`.

## What the log says

```
[location] device GPS set to 17.372882, 78.205865
[location] cell 341 (17.238135, 78.055317) already has a boundary (543 px)
[location] map moved to the search result for 'Medak' (locator 2)
[boundary] tapped 4 corners at [(330, 827), (390, 827), (390, 906), (330, 906)] and closed the polygon
[boundary] nothing was drawn with a 1000 ms press; trying again with 100 ms
```

The chosen spot is also attached to the Allure report as "Boundary location".

## When it fails

| Message | Means | Do |
| --- | --- | --- |
| `No free spot for the boundary` | This run's cell and the fallback places all showed existing boundaries. | Widen the test area (`TEST_AREA_RINGS`), add `FALLBACK_PLACES`, or clean up old test farms. |
| `no search result for 'X'` | Places autocomplete returned nothing for that name, or the results list didn't open. | Check the name exists in autocomplete and that `search-input` still matches. |
| The app's overlap message after saving | The ground was used by a boundary that wasn't visible on screen. | Re-run: the next minute gives another cell. |
| `The taps drew nothing on the map` | Neither press length changed the area: the app isn't taking the taps. | Check the "Crash Logs" and "Failure Screenshot" attachments (on an emulator this is usually the Maps renderer crash above), that the points are on the map, and that drawing mode is on. |
| The boundary has too few corners after saving | One tap of the four didn't register. | Look at the "Failure Screenshot"; raise `TAP_GAP_S` if the map is slow to react. |
| `could not mock the GPS` | Appium couldn't set the location. | On a real phone, set Appium Settings as the mock location app (see Requirements). |

## Known limits

- **Only "did anything get drawn" is checked, not each corner.** If one tap of the
  four is dropped, the step still passes and the wrong shape is saved; if none of
  them land, the step fails.
- **A boundary whose outline is off screen isn't seen.** Step 3 only looks at the
  visible map, so a large existing farm surrounding the view goes unnoticed. The
  app's own overlap check still applies when saving.
- **Runs in the same minute share a cell** (see above).
- **Each fallback place holds one boundary.** After that the flow moves to the next
  name, so the list length is the fallback's capacity.
- **Cleaning up test farms is the real fix.** Overlaps accumulate because farms
  created by tests are never removed; if they were, every run could reuse one spot.
- **state_client has its own `draw_boundary_on_map`** and does not use any of this.
