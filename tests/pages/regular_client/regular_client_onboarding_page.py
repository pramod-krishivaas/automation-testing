import time
import allure
import pytest
import json
import os
import re
import sys

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from tests.utils.wait_utils import open_date_picker, smart_click, scroll_and_click_text, wait_until_displayed
from utils.ui_actions import android_back_func, generate_mobile_number, set_input_value
from utils.location_utils import (
    BOUNDARY_PX_ALLOWED, app_is_foreground, boundary_corners, boundary_pixels, cell_location, cells_for_run, drag_map,
    map_has_rendered,
    emptiest_side, run_minute, search_place, set_device_location, tap_boundary_corners,
    wait_for_app_location, wait_for_map_to_settle,
)

sys.dont_write_bytecode = True


def load_locators_once(self, request):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    locators_path = os.path.join(project_root, "locators", "state_client.json")
    print(f"Loading locators from: {locators_path}")
    with open(locators_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    raw = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", raw)
    xpaths = json.loads(raw)

    # ── locator-type sources ────────────────────────────────────────────────
    # Priority when resolving a single value per key: xpath_locators (most
    # complete) > accessibility_ids > element_ids.
    accessibility_ids = xpaths.get("accessibility_ids", {})
    element_ids = xpaths.get("element_ids", {})
    xpath_locators = xpaths.get("xpath_locators", {})

    def resolve(screen: str, key: str):
        """Return the first available locator for `key` on `screen`."""
        return (
            xpath_locators.get(screen, {}).get(key)
            or accessibility_ids.get(screen, {}).get(key)
            or element_ids.get(screen, {}).get(key)
        )

    # ── dashboard screen ─────────────────────────────────────────────────────
    request.cls.add_button_dashboard_xpath = resolve("dashboard_screen", "add_button_dashboard")
    request.cls.add_new_farmer_option_xpath = resolve("dashboard_screen", "add_new_farmer_option")
    request.cls.only_add_farmer_button_xpath = resolve("dashboard_screen", "only_add_farmer_button")

    # ── add farmer screen ────────────────────────────────────────────────────
    request.cls.add_farmer_name_xpath = resolve("add_farmer_screen", "add_farmer_name")
    request.cls.add_farmer_phone_xpath = resolve("add_farmer_screen", "add_farmer_phone")
    request.cls.business_unit_dropdown_xpath = resolve("add_farmer_screen", "business_unit_dropdown")
    request.cls.search_business_unit_xpath = resolve("add_farmer_screen", "search_business_unit")
    request.cls.field_agent_dropdown_xpath = resolve("add_farmer_screen", "field_agent_dropdown")
    request.cls.field_agent_dropdown_item_xpath = resolve("add_farmer_screen", "field_agent_dropdown_item")
    request.cls.submit_button_add_farmer_xpath = resolve("add_farmer_screen", "submit_button_add_farmer")
    request.cls.cancel_button_add_farmer_xpath = resolve("add_farmer_screen", "cancel_button_add_farmer")

    # ── add farm screen ──────────────────────────────────────────────────────
    request.cls.submit_button_add_farm_xpath = resolve("add_farmer_screen", "submit_button_add_farm")
    request.cls.cancel_button_add_farm_xpath = resolve("add_farmer_screen", "cancel_button_add_farm")

    # ── add crop screen ──────────────────────────────────────────────────────
    request.cls.crop_name_dropdown_xpath = resolve("add_crop_screen", "crop_name_dropdown")
    request.cls.crop_name_item_xpath = resolve("add_crop_screen", "crop_name")
    request.cls.short_duration_button_xpath = resolve("add_crop_screen", "short_duration_button")
    request.cls.long_duration_button_xpath = resolve("add_crop_screen", "long_duration_button")
    request.cls.medium_duration_button_xpath = resolve("add_crop_screen", "medium_duration_button")
    request.cls.direct_sowing_button_xpath = resolve("add_crop_screen", "direct_sowing_button")
    request.cls.transplanted_button_xpath = resolve("add_crop_screen", "transplanted_button")
    request.cls.submit_crop_button_xpath = resolve("add_crop_screen", "submit_crop_button")
    request.cls.sowing_date_xpath = resolve("add_crop_screen", "sowing_date")
    request.cls.calendar_ok_button_xpath = resolve("add_crop_screen", "calendar_ok_button")
    request.cls.transplanted_date_xpath = resolve("add_crop_screen", "transplanted_date")
    request.cls.plantation_date_xpath = resolve("add_crop_screen", "plantation_date")
    request.cls.inter_crop_name_dropdown_xpath = resolve("add_crop_screen", "inter_crop_name_dropdown")
    request.cls.inter_crop_name_item_xpath = resolve("add_crop_screen", "inter_crop_name")
    request.cls.inter_crop_short_duration_button_xpath = resolve("add_crop_screen", "inter_crop_short_duration_button")
    request.cls.inter_crop_sowing_date_xpath = resolve("add_crop_screen", "inter_crop_sowing_date")
    request.cls.inter_crop_name_search_input_xpath = resolve("add_crop_screen", "inter_crop_search_input")

    # ─────── draw boundary screen ─────────────────────────────────────────────────────────────────────
    request.cls.save_boundary_button_xpath = resolve("draw_boundary_screen", "save_boundary_button")
    request.cls.draw_boundary_button_xpath = resolve("draw_boundary_screen", "draw_boundary_button")
    request.cls.search_input_xpath = resolve("draw_boundary_screen", "search-input")
    request.cls.search_result_xpath = resolve("draw_boundary_screen", "search-result")
    # Optional: the map's "current location" button, to recentre on a new mocked
    # location while the map is open. Without it only the run's first cell is used.
    request.cls.current_location_button_xpath = resolve("draw_boundary_screen", "current_location_button")

# ===========================================================================
# TestOnboarding class — kept for backward compatibility
# ===========================================================================
@allure.epic("Onboarding Flow")
@allure.feature("Authentication")
class TestOnboarding:
    @pytest.fixture(scope="class", autouse=True)
    def _load_locators_once(request):
        """Delegates to the shared standalone loader."""
        load_locators_once(request.cls, request)


# ===========================================================================
# Page-action helpers
# ===========================================================================

# ===========================================================================
# Add Farmer Actions
# ===========================================================================

def add_button(driver, obj, test_flow_steps):
    with allure.step("1. Click Add button"):
        if not smart_click(
            driver, "Add button", obj.add_button_dashboard_xpath, "Add"
        ):
            pytest.fail("Could not find or click the 'Add' button.")
        test_flow_steps.append({"step": "Click Add button", "status": "Success"})

def add_farmer_button(driver, obj, test_flow_steps):
    with allure.step("1. Click Add Farmer button"):
        if not smart_click(
            driver, "Add Farmer button", obj.add_new_farmer_option_xpath, "Add Farmer"
        ):
            pytest.fail("Could not find or click the 'Add Farmer' button.")
        test_flow_steps.append({"step": "Click Add Farmer button", "status": "Success"})

def add_farmer_name_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter Farmer Name"):
        if not set_input_value(
            driver, obj.add_farmer_name_xpath, "John Doe", element_name="Farmer Name input"
        ):
            pytest.fail("Could not find or interact with the 'Farmer Name' input field.")
        test_flow_steps.append({"step": "Enter Farmer Name", "status": "Success"})

def add_farmer_phone_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter Farmer Phone"):
        if not set_input_value(
            driver, obj.add_farmer_phone_xpath, generate_mobile_number(), element_name="Farmer Phone input"
        ):
            pytest.fail("Could not find or interact with the 'Farmer Phone' input field.")
        test_flow_steps.append({"step": "Enter Farmer Phone", "status": "Success"})

def field_agent_dropdown(driver, obj, test_flow_steps):
    with allure.step("1. Click Field Agent dropdown"):
        if not smart_click(
            driver, "Field Agent dropdown", obj.field_agent_dropdown_xpath, "Field Agent"
        ):
            pytest.fail("Could not find or click the 'Field Agent' dropdown.")
        test_flow_steps.append({"step": "Click Field Agent dropdown", "status": "Success"})

def field_agent_dropdown_item(driver, obj, test_flow_steps):
    with allure.step("1. Select Field Agent"):
        if not smart_click(
            driver, "Field Agent dropdown item", obj.field_agent_dropdown_item_xpath, "Pramod FA"
        ):
            pytest.fail("Could not find or click the 'Pramod FA' option in the 'Field Agent' dropdown.")
        test_flow_steps.append({"step": "Select Field Agent", "status": "Success"})

def submit_button_add_farmer(driver, obj, test_flow_steps):
    with allure.step("1. Click Submit button on Add Farmer screen"):
        if not smart_click(
            driver, "Submit button on Add Farmer screen", obj.submit_button_add_farmer_xpath, "Submit"
        ):
            pytest.fail("Could not find or click the 'Submit' button on the 'Add Farmer' screen.")
        test_flow_steps.append({"step": "Click Submit button on Add Farmer screen", "status": "Success"})

# ===========================================================================
# Add Farm Actions
# ===========================================================================
def submit_button_add_farm(driver, obj, test_flow_steps):
    with allure.step("1. Click Submit button on Add Farm screen"):
        if not smart_click(
            driver, "Submit button on Add Farm screen", obj.submit_button_add_farmer_xpath, "Submit"
        ):
            pytest.fail("Could not find or click the 'Submit' button on the 'Add Farm' screen.")
        test_flow_steps.append({"step": "Click Submit button on Add Farm screen", "status": "Success"})

# ===========================================================================
# Add Crop Actions
# ===========================================================================

def crop_name_dropdown(driver, obj, test_flow_steps):
    with allure.step("4. Click Crop Name dropdown"):
        if not smart_click(
            driver, "Crop name dropdown", obj.crop_name_dropdown_xpath, "Select Crop Name"
        ):
            pytest.fail("Could not find or click the 'Crop name dropdown' field.")
        test_flow_steps.append({"step": "Click crop name dropdown", "status": "Success"})

def inter_crop_name_dropdown(driver, obj, test_flow_steps):
    with allure.step("4. Click Inter-Crop Name dropdown"):
        if not smart_click(
            driver, "Inter-Crop name dropdown", obj.inter_crop_name_dropdown_xpath, "Select Inter-Crop Name"
        ):
            pytest.fail("Could not find or click the 'Inter-Crop name dropdown' field.")
        test_flow_steps.append({"step": "Click inter-crop name dropdown", "status": "Success"})

def crop_name_item(driver, obj, test_flow_steps):
    with allure.step("5. Select crop from dropdown"):
        # Scrolls the open list until the crop is found: element tree first, then OCR.
        if not scroll_and_click_text(driver, "crop dropdown", "Arecanut", xpath=obj.crop_name_item_xpath):
            pytest.fail("Could not find 'Arecanut' in the crop list.")
        test_flow_steps.append({"step": "Click Crop Name item", "status": "Success"})

def inter_crop_name_item(driver, obj, test_flow_steps):
    with allure.step("5. Select inter-crop from dropdown"):
        # Scrolls the open list until the crop is found: element tree first, then OCR.
        if not scroll_and_click_text(driver, "inter-crop dropdown", "Bengal Gram", xpath=obj.inter_crop_name_item_xpath):
            pytest.fail("Could not find 'Bengal Gram' in the inter-crop list.")
        test_flow_steps.append({"step": "Click Inter-Crop Name item", "status": "Success"})

def inter_crop_name_search_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter Inter-Crop Name"):
        if not set_input_value(
            driver, obj.inter_crop_name_search_input_xpath, "Bengal Gram", element_name="Inter-Crop Name input"
        ):
            pytest.fail("Could not find or interact with the 'Inter-Crop Name' input field.")
        test_flow_steps.append({"step": "Enter Inter-Crop Name", "status": "Success"})

def plantation_date(driver, obj, test_flow_steps):
    with allure.step("6. Click Plantation Date input"):
        if not smart_click(
            driver,
            "Plantation date input",
            obj.plantation_date_xpath,
            "Plantation date input",
        ):
            pytest.fail("Could not find or click the 'Plantation date input' field.")
        test_flow_steps.append(
            {"step": "Click plantation date input", "status": "Success"}
        )


def transplanted_date(driver, obj, test_flow_steps):
    with allure.step("7. Click Transplanted Date input"):
        if not smart_click(
            driver,
            "Transplanted date input",
            obj.transplanted_date_input_xpath,
            "Transplanted date input",
        ):
            pytest.fail("Could not find or click the 'Transplanted date input' field.")
        test_flow_steps.append(
            {"step": "Click transplanted date input", "status": "Success"}
        )

def sowing_date_input(driver, obj, test_flow_steps):
    with allure.step("8. Click Sowing Date input"):
        if not smart_click(
            driver,
            "Sowing date input",
            obj.sowing_date_input_xpath,
            "Sowing date input",
        ):
            pytest.fail("Could not find or click the 'Sowing date input' field.")
        test_flow_steps.append({"step": "Click sowing date input", "status": "Success"})

def inter_crop_sowing_date_input(driver, obj, test_flow_steps):
    with allure.step("8. Click Inter-Crop Sowing Date input"):
        # Found by its on-screen label at every scroll position, and tapped until the
        # date picker opens (calendar_ok_button then picks the date).
        if not open_date_picker(
            driver,
            "Inter-Crop Sowing date input",
            "Inter-Crop Sowing Date",
            xpath=obj.inter_crop_sowing_date_xpath,
            picker_xpath=obj.calendar_ok_button_xpath,
        ):
            pytest.fail("Could not find or open the 'Inter-Crop Sowing Date' field.")
        test_flow_steps.append({"step": "Click inter-crop sowing date input", "status": "Success"})

def inter_crop_short_duration_button(driver, obj, test_flow_steps):
    with allure.step("8. Click Inter-Crop Short Duration button"):
        if not smart_click(
            driver,
            "Inter-Crop Short Duration button",
            obj.inter_crop_short_duration_button_xpath,
            "Inter-Crop Short Duration button",
        ):
            pytest.fail("Could not find or click the 'Inter-Crop Short Duration button' field.")
        test_flow_steps.append({"step": "Click inter-crop short duration button", "status": "Success"})

def calendar_ok_button(driver, obj, test_flow_steps):
    with allure.step("9. Click OK on calendar"):
        if not smart_click(driver, "OK button on calendar", obj.calendar_ok_button_xpath, "OK"):
            pytest.fail("Could not find or click the 'OK' button.")
        test_flow_steps.append(
            {"step": "Click OK button on calendar", "status": "Success"}
        )


def submit_crop_button(driver, obj, test_flow_steps):
    with allure.step("10. Click Submit Crop button"):
        if not smart_click(
            driver, "Submit crop", obj.submit_crop_button_xpath, "Submit"
        ):
            pytest.fail("Could not find or click the 'Submit crop' button.")
        test_flow_steps.append({"step": "Click Submit crop", "status": "Success"})


def update_crop(driver, obj, test_flow_steps):
    with allure.step("11. Click Update Crop button"):
        if not smart_click(
            driver, "Update crop", obj.update_crop_button_xpath, "Update"
        ):
            pytest.fail("Could not find or click the 'Update crop' button.")
        test_flow_steps.append({"step": "Click Update crop", "status": "Success"})


def skip_crop(driver, obj, test_flow_steps):
    with allure.step("11. Click Skip to skip crop addition"):
        if not smart_click(driver, "Skip crop addition", obj.skip_button_xpath, "Skip"):
            pytest.fail("Could not find or click the 'Skip' button.")
        test_flow_steps.append(
            {"step": "Click Skip button to skip crop addition", "status": "Success"}
        )


def cancel_button(driver, obj, test_flow_steps):
    with allure.step("12. Click Cancel to cancel crop addition/editing"):
        if not smart_click(
            driver, "Cancel crop addition/editing", obj.cancel_button_xpath, "Cancel"
        ):
            pytest.fail("Could not find or click the 'Cancel' button.")
        test_flow_steps.append(
            {
                "step": "Click Cancel button to cancel crop addition/editing",
                "status": "Success",
            }
        )

# ============================================
#              boundary Actions
# ============================================

# Where boundaries are drawn. Each run mocks the device GPS to its own cell of a
# test area: cells 1 km apart in a spiral around TEST_AREA_CENTER (10 rings = 441
# cells). Use an area agreed for test farms, away from real ones.
TEST_AREA_CENTER = (17.3100, 78.1400)   # farmland near Chevella, Telangana
TEST_AREA_CELL_M = 1000
TEST_AREA_RINGS = 10
# Fallback when the app doesn't take the mocked GPS: places to search for by name
# (the search box doesn't accept coordinates). Each run starts at a different one.
FALLBACK_PLACES = [
    "Medak", "Siddipet", "Sangareddy", "Kamareddy", "Vikarabad", "Jangaon",
    "Nalgonda", "Suryapet", "Mahabubnagar", "Nizamabad", "Karimnagar", "Khammam",
]


def set_run_location(driver, obj, test_flow_steps):
    """Mock the device GPS at this run's test-area cell, before the map opens there."""
    with allure.step("0. Set this run's device location (mock GPS)"):
        obj.location_cells = cells_for_run(TEST_AREA_RINGS)
        lat, lng = cell_location(TEST_AREA_CENTER, obj.location_cells[0], TEST_AREA_CELL_M)
        obj.mock_location_set = set_device_location(driver, lat, lng)
        # Not fatal: the boundary step falls back to searching a place by name.
        test_flow_steps.append({"step": f"Set device location to {lat}, {lng}",
                                "status": "Success" if obj.mock_location_set else "Skipped"})


def _free_spot_for_boundary(driver, obj, box, tries=3, max_places=5):
    """Put the map on ground with no existing boundary around `box` (screen area of
    the new boundary); returns how, or None.

    First this run's mock-GPS cell. If that spot is taken, the map is moved and
    checked again, up to `tries` in total: to the next cell when the map's
    current-location button is known, otherwise by dragging the map towards the
    side showing the fewest boundaries. After that, places are searched by name.
    """
    locate = getattr(obj, "current_location_button_xpath", None)
    cells = getattr(obj, "location_cells", None) or cells_for_run(TEST_AREA_RINGS)
    for i in range(tries):
        cell, where = cells[i % len(cells)], None
        if i == 0 or locate:
            lat, lng = cell_location(TEST_AREA_CENTER, cell, TEST_AREA_CELL_M)
            if (i > 0 or not getattr(obj, "mock_location_set", False)) and not set_device_location(driver, lat, lng):
                break
            seen = wait_for_app_location(driver, lat, lng)
            if seen is False:
                break  # the app ignores the mocked GPS: search by place name instead
            if locate:
                smart_click(driver, "current location button", locate, timeout=5)
            where = {"method": "mock GPS", "cell": cell, "latitude": lat, "longitude": lng,
                     "app_showed_location": seen is True}
        else:
            # No way to recentre on another cell, so move across the ground the map
            # is already showing, towards where it shows the fewest boundaries.
            side = emptiest_side(driver)
            if not drag_map(driver, side):
                break
            where = {"method": "dragged the map", "towards": side, "from_cell": cells[0]}
        wait_for_map_to_settle(driver, box, min_wait=3)
        found = boundary_pixels(driver, box)
        if found <= BOUNDARY_PX_ALLOWED:
            return where
        print(f"[location] try {i + 1}/{tries}: this spot already has a boundary ({found} px)")

    start = run_minute() % len(FALLBACK_PLACES)
    for place in (FALLBACK_PLACES[start:] + FALLBACK_PLACES[:start])[:max_places]:
        if not search_place(driver, obj.search_input_xpath, place):
            continue
        wait_for_map_to_settle(driver, box, min_wait=3)
        found = boundary_pixels(driver, box)
        if found <= BOUNDARY_PX_ALLOWED:
            return {"method": "place search", "place": place}
        print(f"[location] {place} already has a boundary there ({found} px); trying the next place")
    return None


def draw_boundary_buton_on_modal(driver, obj, test_flow_steps):
    with allure.step("14. Click draw on map button on modal"):
        if not smart_click(
            driver, "draw on map button", obj.draw_boundary_button_xpath, "Draw boundary"
        ):
            pytest.fail("Could not find or click the 'Draw boundary' button.")
        test_flow_steps.append({"step": "Click Draw boundary", "status": "Success"})

def search_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter location in search input"):
        if not set_input_value(
            driver, obj.search_input_xpath, "Medak", element_name="Search input"
        ):
            pytest.fail("Could not find or interact with the 'Search input' field.")
        test_flow_steps.append({"step": "Enter location", "status": "Success"})

def search_result(driver, obj, test_flow_steps):
    with allure.step("14. Click search result"):
        if not smart_click(
            driver, "search result", obj.search_result_xpath, "Search result"
        ):
            pytest.fail("Could not find or click the 'Search result' button.")
        test_flow_steps.append({"step": "Click Search result", "status": "Success"})

def save_boundary_button(driver, obj, test_flow_steps):
    with allure.step("14. Click save boundary button"):
        if not smart_click(
            driver, "save boundary button", obj.save_boundary_button_xpath, "Save boundary"
        ):
            pytest.fail("Could not find or click the 'Save boundary' button.")
        test_flow_steps.append({"step": "Click Save boundary", "status": "Success"})


def draw_boundary_on_map(driver, obj, test_flow_steps):
    with allure.step("36. Draw boundary polygon on map"):
        # Corners worked out from where the map is on screen (fixed points like
        # x=690 fell on the card's border just right of the map, x 33-687).
        corners = boundary_corners(driver)
        xs, ys = [x for x, _ in corners], [y for _, y in corners]
        box = (min(xs), min(ys), max(xs), max(ys))
        # The app has to be on screen with the map drawn: otherwise a crashed app or
        # a map that never loaded looks like free ground and every tap goes nowhere.
        if not app_is_foreground(driver):
            pytest.fail("The app is not on screen any more: it stopped before the boundary could be "
                        "drawn (see the 'Crash Logs' attachment).")
        wait_for_map_to_settle(driver, box, min_wait=3)
        if not map_has_rendered(driver, box):
            pytest.fail("The map is blank where the boundary goes, so there is nothing to draw on: "
                        "the map did not load on this device.")
        # Then makes sure no existing boundary (green) is where this one goes: this
        # run's mock-GPS cell, else a place by name.
        spot = _free_spot_for_boundary(driver, obj, box)
        if spot is None:
            pytest.fail("No free spot for the boundary: the mocked location and the fallback "
                        "places all show existing boundaries (or couldn't be reached).")
        allure.attach(json.dumps(spot, indent=2), name="Boundary location",
                      attachment_type=allure.attachment_type.JSON)
        # 4 corners, each confirmed on screen; then the first point twice to close.
        try:
            tap_boundary_corners(driver, corners, closing_taps=2)
        except AssertionError as e:
            pytest.fail(f"Could not draw all 4 boundary corners: {e}")
        test_flow_steps.append({"step": f"Draw Boundary on Map ({spot['method']})", "status": "Success"})

def save_approve_boundary(driver, obj, test_flow_steps):
    with allure.step("14. Click Save boundary"):
        if not smart_click(
            driver, "Save and approve boundary", obj.save_approve_button_xpath, "Save boundary"
        ):
            pytest.fail("Could not find or click the 'Save boundary' button.")
        test_flow_steps.append({"step": "Click Save boundary", "status": "Success"})

def android_back(driver, obj, test_flow_steps):
    with allure.step("Android back"):
        time.sleep(10)
        if not android_back_func(driver):
            pytest.fail("Failed Android back")
        test_flow_steps.append({"step": "Android back", "status": "Success"})


def three_dots_menu(driver, obj, test_flow_steps):
    with allure.step("14. Click Three Dots menu on farm card"):
        if not smart_click(
            driver, "Three dots menu", obj.three_dots_xpath, "Three dots menu"
        ):
            pytest.fail("Could not find or click the 'Three dots' menu.")
        test_flow_steps.append({"step": "Click three dots menu", "status": "Success"})

def hamburger_menu(driver, obj, test_flow_steps):
    with allure.step("16. Click Hamburger menu"):
        if not smart_click(driver, "Hamburger menu", obj.hamburger_menu_xpath):
            print("hamburger_menu_xpath =", obj.hamburger_menu_xpath)
            pytest.fail("Could not find or click the 'Hamburger' menu.")
        test_flow_steps.append({"step": "Click Hamburger menu", "status": "Success"})


def pending_farms_tab(driver, obj, test_flow_steps):
    with allure.step("17. Navigate to Pending Farms tab"):
        if not smart_click(
            driver, "Pending Farms tab", obj.pending_farms_tab_xpath, "Pending Farms"
        ):
            pytest.fail("Could not find or click the 'Pending Farms' tab.")
        test_flow_steps.append({"step": "Click Pending Farms tab", "status": "Success"})


def type_dropdown(driver, obj, test_flow_steps):
    with allure.step("18. Click Type dropdown in Pending Farms"):
        if not smart_click(
            driver, "Type dropdown", obj.type_dropdown_xpath, "Type dropdown"
        ):
            pytest.fail("Could not find or click the 'Type' dropdown in Pending Farms.")
        test_flow_steps.append(
            {"step": "Click Type dropdown in Pending Farms", "status": "Success"}
        )


def active_dropdown(driver, obj, test_flow_steps):
    with allure.step("19. Click Active dropdown in Pending Farms"):
        if not smart_click(
            driver, "Active dropdown", obj.active_dropdown_xpath, "Active"
        ):
            pytest.fail(
                "Could not find or click the 'Active' dropdown in Pending Farms."
            )
        test_flow_steps.append(
            {"step": "Click Active dropdown in Pending Farms", "status": "Success"}
        )


def historical_option(driver, obj, test_flow_steps):
    with allure.step("20. Select Historical option in Active dropdown"):
        if not smart_click(
            driver, "Historical option", obj.historical_xpath, "Historical"
        ):
            pytest.fail(
                "Could not find or click the 'Historical' option in Active dropdown."
            )
        test_flow_steps.append(
            {"step": "Click Historical option in Active dropdown", "status": "Success"}
        )


def cross_button(driver, obj, test_flow_steps):
    with allure.step("21. Click Cross button to clear filters in Pending Farms"):
        if not smart_click(
            driver, "Cross button to clear filters", obj.cross_button_xpath, "Cross"
        ):
            pytest.fail("Could not find or click the 'Cross' button to clear filters.")
        test_flow_steps.append(
            {
                "step": "Click Cross button to clear filters in Pending Farms",
                "status": "Success",
            }
        )


def all_dropdown(driver, obj, test_flow_steps):
    with allure.step("22. Click All dropdown in Pending Farms"):
        if not smart_click(driver, "All dropdown", obj.all_dropdown_xpath, "All"):
            pytest.fail("Could not find or click the 'All' dropdown in Pending Farms.")
        test_flow_steps.append(
            {"step": "Click All dropdown in Pending Farms", "status": "Success"}
        )


def only_farms_option(driver, obj, test_flow_steps):
    with allure.step("23. Select Only Farms option in All dropdown"):
        if not smart_click(
            driver, "Only Farms option", obj.only_farms_xpath, "Only Farms"
        ):
            pytest.fail(
                "Could not find or click the 'Only Farms' option in All dropdown."
            )
        test_flow_steps.append(
            {"step": "Click Only Farms option in All dropdown", "status": "Success"}
        )

def all_tab(driver, obj, test_flow_steps):
    with allure.step("24. Click All tab in Pending Farms"):
        if not smart_click(driver, "All tab", obj.all_tab_xpath, "All"):
            pytest.fail("Could not find or click the 'All' tab in Pending Farms.")
        test_flow_steps.append(
            {"step": "Click All tab in Pending Farms", "status": "Success"}
        )

def farm_card_three_dots(driver, obj, test_flow_steps):
    with allure.step("25. Click Three Dots menu on farm card in Pending Farms"):
        if not smart_click(
            driver,
            "Three dots menu on farm card",
            obj.farm_card_three_dots_xpath,
            "Three dots on farm card",
        ):
            pytest.fail("Could not find or click the 'Three dots' menu on a farm card.")
        test_flow_steps.append(
            {
                "step": "Click three dots menu on farm card in Pending Farms",
                "status": "Success",
            }
        )

def pending_farms_three_dots_menu(driver, obj, test_flow_steps):
    with allure.step("25. Click Three Dots menu on farm card in Pending Farms"):
        if not smart_click(
            driver,
            "Three dots menu on farm card",
            obj.three_dots_pending_farms_xpath,
            "Three dots on farm card",
        ):
            pytest.fail("Could not find or click the 'Three dots' menu on a farm card.")
        test_flow_steps.append(
            {
                "step": "Click three dots menu on farm card in Pending Farms",
                "status": "Success",
            }
        )

def farms_with_no_crops_option(driver, obj, test_flow_steps):
    with allure.step("26. Select Farms With No Crops option in Type dropdown"):
        if not smart_click(
            driver,
            "Farms with no crops option",
            obj.farms_with_no_crops_xpath,
            "Farms with no crops",
        ):
            pytest.fail("Could not find or click the 'Farms with no crops' option.")
        test_flow_steps.append(
            {
                "step": "Click Farms with no crops option in Type dropdown",
                "status": "Success",
            }
        )

def farms_with_no_boundary_option(driver, obj, test_flow_steps):
    with allure.step("27. Select Farms With No Boundary option in Type dropdown"):
        if not smart_click(
            driver,
            "Farms with no boundary option",
            obj.farms_with_no_boundary_xpath,
            "Farms with no boundary",
        ):
            pytest.fail("Could not find or click the 'Farms with no boundary' option.")
        test_flow_steps.append(
            {
                "step": "Click Farms with no boundary option in Type dropdown",
                "status": "Success",
            }
        )

# ===========================================================================
# Three Dots Menu Actions
# ===========================================================================
def overview_option(driver, obj, test_flow_steps):
    with allure.step("28. Click Overview option in Three Dots menu"):
        if not smart_click(driver, "Overview option", obj.Overview_xpath, "Overview"):
            pytest.fail(
                "Could not find or click the 'Overview' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Overview option in three dots menu", "status": "Success"}
        )

def edit_farm(driver, obj, test_flow_steps):
    with allure.step("29. Click Edit Farm in Three Dots menu"):
        if not smart_click(
            driver, "Edit farm (three dots menu)", obj.edit_farm_xpath, "Edit Farm"
        ):
            pytest.fail(
                "Could not find or click the 'Edit Farm' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Edit farm in three dots menu", "status": "Success"}
        )

def delete_farm(driver, obj, test_flow_steps):
    with allure.step("30. Click Delete Farm in Three Dots menu"):
        if not smart_click(
            driver,
            "Delete farm (three dots menu)",
            obj.delete_farm_xpath,
            "Delete Farm",
        ):
            pytest.fail(
                "Could not find or click the 'Delete Farm' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Delete farm in three dots menu", "status": "Success"}
        )

def add_crop(driver, obj, test_flow_steps):
    with allure.step("31. Click Add Crop in Three Dots menu"):
        if not smart_click(
            driver, "Add crop (three dots menu)", obj.add_crop_xpath, "Add Crop"
        ):
            pytest.fail(
                "Could not find or click the 'Add Crop' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Add crop in three dots menu", "status": "Success"}
        )

def edit_crop(driver, obj, test_flow_steps):
    with allure.step("32. Click Edit Crop in Three Dots menu"):
        if not smart_click(
            driver, "Edit crop (three dots menu)", obj.edit_crop_xpath, "Edit Crop"
        ):
            pytest.fail(
                "Could not find or click the 'Edit Crop' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Edit crop in three dots menu", "status": "Success"}
        )

def delete_crop(driver, obj, test_flow_steps):
    with allure.step("33. Click Delete Crop in Three Dots menu"):
        if not smart_click(
            driver,
            "Delete crop (three dots menu)",
            obj.delete_crop_xpath,
            "Delete Crop",
        ):
            pytest.fail(
                "Could not find or click the 'Delete Crop' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Delete crop in three dots menu", "status": "Success"}
        )

def add_boundary_from_three_dots(driver, obj, test_flow_steps):
    with allure.step("34. Click Add Boundary in Three Dots menu"):
        if not smart_click(
            driver, "Add Boundary option", obj.add_boundary_xpath, "Add Boundary"
        ):
            pytest.fail(
                "Could not find or click the 'Add Boundary' option in the three dots menu."
            )
        test_flow_steps.append(
            {
                "step": "Click Add Boundary option in three dots menu",
                "status": "Success",
            }
        )

def edit_boundary_from_three_dots(driver, obj, test_flow_steps):
    with allure.step("35. Click Edit Boundary in Three Dots menu"):
        if not smart_click(
            driver, "Edit Boundary option", obj.edit_boundary_xpath, "Edit Boundary"
        ):
            pytest.fail(
                "Could not find or click the 'Edit Boundary' option in the three dots menu."
            )
        test_flow_steps.append(
            {
                "step": "Click Edit Boundary option in three dots menu",
                "status": "Success",
            }
        )
