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
from tests.utils.wait_utils import smart_click, scroll_up_and_tap_by_text
from utils.ui_actions import android_back_func, smart_send_keys, generate_mobile_number

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

    # ── login screen ─────────────────────────────────────────────────────────
    request.cls.allow_picture_button_xpath = resolve("login_screen", "allow_picture_button")
    request.cls.allow_location_button_xpath = resolve("login_screen", "allow_location_button")
    request.cls.allow_audio_button_xpath = resolve("login_screen", "allow_audio_button")
    request.cls.next_button_language_login_xpath = resolve("login_screen", "next_button_language_login")
    request.cls.allow_notifications_button_xpath = resolve("login_screen", "allow_notifications_button")
    request.cls.phone_number_input_xpath = resolve("login_screen", "phone_number_input")
    request.cls.next_button_login_xpath = resolve("login_screen", "next_button_login")
    request.cls.verify_button_login_xpath = resolve("login_screen", "verify_button_login")
    request.cls.change_mobile_number_xpath = resolve("login_screen", "change_mobile_number")
    request.cls.resend_otp_button_xpath = resolve("login_screen", "resend_otp_button")

    # ── dashboard screen ─────────────────────────────────────────────────────
    request.cls.add_button_dashboard_xpath = resolve("dashboard_screen", "add_button_dashboard")
    request.cls.add_new_farmer_option_xpath = resolve("dashboard_screen", "add_new_farmer_option")
    request.cls.farm_village_dropdown_button_xpath = resolve("dashboard_screen", "farm_village_dropdown_button")
    request.cls.farm_village_item_xpath = resolve("dashboard_screen", "farm_village_item")
    request.cls.download_boundary_button_xpath = resolve("dashboard_screen", "download_boundary_button")
    request.cls.search_by_bunds_results_xpath = resolve("dashboard_screen", "search_by_bunds_results")
    request.cls.only_add_farmer_button_xpath = resolve("dashboard_screen", "only_add_farmer_button")
    request.cls.submit_button_farm_villages_xpath = resolve("dashboard_screen", "submit_button_farm_villages")
    request.cls.search_by_bunds_lat_long_option_xpath = resolve("dashboard_screen", "search_by_bunds_lat_long_option")
    request.cls.search_by_bunds_lat_long_input_xpath = resolve("dashboard_screen", "search_by_bunds_lat_long_input")
    request.cls.select_bund_xpath = resolve("dashboard_screen", "select_bund")
    request.cls.confirm_bunds_selection_button_xpath = resolve("dashboard_screen", "confirm_bunds_selection_button")
    request.cls.select_survey_button_xpath = resolve("dashboard_screen", "select_survey_button")
    request.cls.search_by_survey_number_option_xpath = resolve("dashboard_screen", "search_by_survey_number_option")

    # ── add farmer screen ────────────────────────────────────────────────────
    request.cls.add_farmer_name_xpath = resolve("add_farmer_screen", "add_farmer_name")
    request.cls.add_farmer_phone_xpath = resolve("add_farmer_screen", "add_farmer_phone")
    request.cls.business_unit_dropdown_xpath = resolve("add_farmer_screen", "business_unit_dropdown")
    request.cls.search_business_unit_xpath = resolve("add_farmer_screen", "search_business_unit")
    request.cls.field_agent_dropdown_xpath = resolve("add_farmer_screen", "field_agent_dropdown")
    request.cls.submit_button_add_farmer_xpath = resolve("add_farmer_screen", "submit_button_add_farmer")
    request.cls.cancel_button_add_farmer_xpath = resolve("add_farmer_screen", "cancel_button_add_farmer")

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
        time.sleep(3)
        if not smart_click(
            driver, "Add button", obj.add_button_dashboard_xpath, "Add"
        ):
            pytest.fail("Could not find or click the 'Add' button.")
        test_flow_steps.append({"step": "Click Add button", "status": "Success"})

def add_farmer_button(driver, obj, test_flow_steps):
    with allure.step("1. Click Add Farmer button"):
        time.sleep(3)
        if not smart_click(
            driver, "Add Farmer button", obj.add_new_farmer_option_xpath, "Add Farmer"
        ):
            pytest.fail("Could not find or click the 'Add Farmer' button.")
        test_flow_steps.append({"step": "Click Add Farmer button", "status": "Success"})

def add_farmer_name_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter Farmer Name"):
        time.sleep(3)
        if not smart_send_keys(
            driver, obj.add_farmer_name_xpath, "John Doe", element_name="Farmer Name input"
        ):
            pytest.fail("Could not find or interact with the 'Farmer Name' input field.")
        test_flow_steps.append({"step": "Enter Farmer Name", "status": "Success"})

def add_farmer_phone_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter Farmer Phone"):
        time.sleep(3)
        if not smart_send_keys(
            driver, obj.add_farmer_phone_xpath, generate_mobile_number(), element_name="Farmer Phone input"
        ):
            pytest.fail("Could not find or interact with the 'Farmer Phone' input field.")
        test_flow_steps.append({"step": "Enter Farmer Phone", "status": "Success"})

def submit_button_add_farmer(driver, obj, test_flow_steps):
    with allure.step("1. Click Submit button on Add Farmer screen"):
        time.sleep(3)
        if not smart_click(
            driver, "Submit button on Add Farmer screen", obj.submit_button_add_farmer_xpath, "Submit"
        ):
            pytest.fail("Could not find or click the 'Submit' button on the 'Add Farmer' screen.")
        test_flow_steps.append({"step": "Click Submit button on Add Farmer screen", "status": "Success"})

def farm_village_dropdown(driver, obj, test_flow_steps):
    with allure.step("1. Click Farm village dropdown"):
        time.sleep(3)
        if not smart_click(
            driver, "Farm village dropdown", obj.farm_village_dropdown_button_xpath, "Farm village"
        ):
            pytest.fail("Could not find or click the 'Farm village dropdown' button.")
        test_flow_steps.append({"step": "Click Farm village dropdown", "status": "Success"})

def farm_village_item(driver, obj, test_flow_steps):
    with allure.step("1. Click Farm village item"):
        time.sleep(3)
        if not smart_click(
            driver, "Farm village item", obj.farm_village_item_xpath, "Farm village item"
        ):
            pytest.fail("Could not find or click the 'Farm village item' button.")
        test_flow_steps.append({"step": "Click Farm village item", "status": "Success"})

def download_boundary_button(driver, obj, test_flow_steps):
    with allure.step("1. Click Download Boundary button"):
        time.sleep(3)
        if not smart_click(
            driver, "Download Boundary button", obj.download_boundary_button_xpath, "Download Boundary"
        ):
            pytest.fail("Could not find or click the 'Download Boundary' button.")
        test_flow_steps.append({"step": "Click Download Boundary button", "status": "Success"})

def submit_village(driver, obj, test_flow_steps):
    with allure.step("1. Click Submit village"):
        time.sleep(3)
        if not smart_click(
            driver, "Submit village", obj.submit_button_farm_villages_xpath, "Submit village"
        ):
            pytest.fail("Could not find or click the 'Submit village' button.")
        test_flow_steps.append({"step": "Click Submit village", "status": "Success"})

# ===========================================================================
# Add Farm Actions
# ===========================================================================

def search_by_bunds_lat_long_option(driver, obj, test_flow_steps):
    with allure.step("1. Click Search by bunds/Latitude/Longitude option"):
        time.sleep(3)
        if not smart_click(
            driver, "Search by bunds/Latitude/Longitude option", obj.search_by_bunds_lat_long_option_xpath, "Search by bunds/Latitude/Longitude"
        ):
            pytest.fail("Could not find or click the 'Search by bunds/Latitude/Longitude' option.")
        test_flow_steps.append({"step": "Click Search by bunds/Latitude/Longitude option", "status": "Success"})

def click_search_by_bunds_lat_long_input(driver, obj, test_flow_steps):
    with allure.step("1. Click Search by bunds/Latitude/Longitude input"):
        time.sleep(3)
        if not smart_click(
            driver, "Search by bunds/Latitude/Longitude input", obj.search_by_bunds_lat_long_input_xpath, "Search by bunds/Latitude/Longitude"
        ):
            pytest.fail("Could not find or click the 'Search by bunds/Latitude/Longitude' input.")
        test_flow_steps.append({"step": "Click Search by bunds/Latitude/Longitude input", "status": "Success"})

def enter_search_by_bunds_lat_long_value(driver, obj, test_flow_steps, value="580"):
    with allure.step(f"1. Enter '{value}' in Search by bunds/Latitude/Longitude field"):
        time.sleep(3)
        # smart_click can't type (it only clicks / OCR-taps), so grab the real element
        # and send keys into it.
        try:
            field = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, obj.search_by_bunds_lat_long_option_xpath)
                )
            )
        except Exception:
            pytest.fail("Could not find the 'Search by bunds/Latitude/Longitude' input field to type into.")

        try:
            field.click()   # focus the field before typing
        except Exception:
            pass
        try:
            field.clear()   # drop any pre-filled value so we don't append to it
        except Exception:
            pass

        field.send_keys(str(value))
        test_flow_steps.append(
            {"step": f"Enter '{value}' in Search by bunds/Latitude/Longitude field", "status": "Success"}
        )

def select_bund(driver, obj, test_flow_steps):
    with allure.step("1. Select bund from search results"):
        time.sleep(3)
        if not smart_click(
            driver, "Select bund from search results", obj.select_bund_xpath, "Select bund from search results"
        ):
            pytest.fail("Could not find or click the 'Select bund from search results' option.")
        test_flow_steps.append({"step": "Select bund from search results", "status": "Success"})

def confirm_bunds_selection_button(driver, obj, test_flow_steps):
    with allure.step("1. Confirm bunds selection"):
        time.sleep(3)
        if not smart_click(
            driver, "Confirm bunds selection", obj.confirm_bunds_selection_button_xpath, "Confirm bunds selection"
        ):
            pytest.fail("Could not find or click the 'Confirm bunds selection' button.")
        test_flow_steps.append({"step": "Confirm bunds selection", "status": "Success"})

# ===========================================================================
# Add Crop Actions
# ===========================================================================

def crop_name_dropdown(driver, obj, test_flow_steps):
    with allure.step("4. Click Crop Name dropdown"):
        time.sleep(10)
        if not smart_click(
            driver, "Crop name dropdown", obj.crop_name_dropdown_xpath, "Select Crop Name"
        ):
            pytest.fail("Could not find or click the 'Crop name dropdown' field.")
        test_flow_steps.append({"step": "Click crop name dropdown", "status": "Success"})


def crop_name_item(driver, obj, test_flow_steps):
    with allure.step("5. Select crop from dropdown (OCR)"):
        time.sleep(2)
        if not smart_click(
            driver,
            "select crop from dropdown (OCR)",
            obj.crop_name_item_xpath,
            "Arecanut",
            screenshot_path="screenshots/crop_dropdown.png",
            force_ocr=True,
            ocr_attempts=3,
        ):
            pytest.fail("Could not select the crop name via OCR.")
        test_flow_steps.append({"step": "Click Crop Name item", "status": "Success"})


def plantation_date(driver, obj, test_flow_steps):
    with allure.step("6. Click Plantation Date input"):
        time.sleep(2)
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
        time.sleep(2)
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


def intercrop_name(driver, obj, test_flow_steps):
    with allure.step("6. Click Inter-Crop Name input field"):
        time.sleep(10)
        if not smart_click(
            driver, "Inter-Crop Name input", obj.intercrop_name_xpath, "Inter-Crop Name"
        ):
            pytest.fail("Could not find or click the 'Inter Crop Name' input field.")
        test_flow_steps.append(
            {"step": "Click Inter Crop Name input", "status": "Success"}
        )


def intercrop_dropdown(driver, obj, test_flow_steps):

    with allure.step("7. Select intercrop from dropdown"):
        time.sleep(3)
        # Scroll until crop becomes visible and tap dynamically
        if not scroll_up_and_tap_by_text(driver, text_to_find="Beetroot", max_swipes=5):
            pytest.fail("Could not find/select intercrop name after scrolling.")
            test_flow_steps.append(
                {"step": "Select Intercrop Name item", "status": "Success"}
            )


def sowing_date_input(driver, obj, test_flow_steps):
    with allure.step("8. Click Sowing Date input"):
        time.sleep(2)
        if not smart_click(
            driver,
            "Sowing date input",
            obj.sowing_date_input_xpath,
            "Sowing date input",
        ):
            pytest.fail("Could not find or click the 'Sowing date input' field.")
        test_flow_steps.append({"step": "Click sowing date input", "status": "Success"})


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
        time.sleep(2)
        if not smart_click(driver, "Skip crop addition", obj.skip_button_xpath, "Skip"):
            pytest.fail("Could not find or click the 'Skip' button.")
        test_flow_steps.append(
            {"step": "Click Skip button to skip crop addition", "status": "Success"}
        )


def cancel_button(driver, obj, test_flow_steps):
    with allure.step("12. Click Cancel to cancel crop addition/editing"):
        time.sleep(2)
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


def android_back(driver, obj, test_flow_steps):
    # ── Step 10: Android back ──────────────────────────────────────────
    with allure.step("Android back"):
        time.sleep(10)
        if not android_back_func(driver):
            pytest.fail("Failed Android back")

        test_flow_steps.append({"step": "Android back", "status": "Success"})


def three_dots_menu(driver, obj, test_flow_steps):
    with allure.step("14. Click Three Dots menu on farm card"):
        time.sleep(5)
        if not smart_click(
            driver, "Three dots menu", obj.three_dots_xpath, "Three dots menu"
        ):
            pytest.fail("Could not find or click the 'Three dots' menu.")
        test_flow_steps.append({"step": "Click three dots menu", "status": "Success"})


def save_approve_boundary(driver, obj, test_flow_steps):
    with allure.step("15. Click Save boundary"):
        time.sleep(5)

        wait = WebDriverWait(driver, 20)
        try:
            wait.until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, obj.save_approve_button_xpath)
                )
            )
        except Exception:
            pass  # Fall through to smart_click which has its own retry

        if not smart_click(
            driver,
            "Save and approve boundary",
            obj.save_approve_button_xpath,
            "Save boundary",
        ):
            pytest.fail("Could not find or click the 'Save boundary' button.")
        test_flow_steps.append(
            {"step": "Click Save and approve boundary", "status": "Success"}
        )


def hamburger_menu(driver, obj, test_flow_steps):
    with allure.step("16. Click Hamburger menu"):
        time.sleep(5)
        if not smart_click(driver, "Hamburger menu", obj.hamburger_menu_xpath):
            print("hamburger_menu_xpath =", obj.hamburger_menu_xpath)
            pytest.fail("Could not find or click the 'Hamburger' menu.")
        test_flow_steps.append({"step": "Click Hamburger menu", "status": "Success"})


def pending_farms_tab(driver, obj, test_flow_steps):
    with allure.step("17. Navigate to Pending Farms tab"):
        time.sleep(5)
        if not smart_click(
            driver, "Pending Farms tab", obj.pending_farms_tab_xpath, "Pending Farms"
        ):
            pytest.fail("Could not find or click the 'Pending Farms' tab.")
        test_flow_steps.append({"step": "Click Pending Farms tab", "status": "Success"})


def type_dropdown(driver, obj, test_flow_steps):
    with allure.step("18. Click Type dropdown in Pending Farms"):
        time.sleep(2)
        if not smart_click(
            driver, "Type dropdown", obj.type_dropdown_xpath, "Type dropdown"
        ):
            pytest.fail("Could not find or click the 'Type' dropdown in Pending Farms.")
        test_flow_steps.append(
            {"step": "Click Type dropdown in Pending Farms", "status": "Success"}
        )


def active_dropdown(driver, obj, test_flow_steps):
    with allure.step("19. Click Active dropdown in Pending Farms"):
        time.sleep(2)
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
        time.sleep(2)
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
        time.sleep(2)
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
        time.sleep(2)
        if not smart_click(driver, "All dropdown", obj.all_dropdown_xpath, "All"):
            pytest.fail("Could not find or click the 'All' dropdown in Pending Farms.")
        test_flow_steps.append(
            {"step": "Click All dropdown in Pending Farms", "status": "Success"}
        )


def only_farms_option(driver, obj, test_flow_steps):
    with allure.step("23. Select Only Farms option in All dropdown"):
        time.sleep(2)
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
        time.sleep(2)
        if not smart_click(driver, "All tab", obj.all_tab_xpath, "All"):
            pytest.fail("Could not find or click the 'All' tab in Pending Farms.")
        test_flow_steps.append(
            {"step": "Click All tab in Pending Farms", "status": "Success"}
        )


def farm_card_three_dots(driver, obj, test_flow_steps):
    with allure.step("25. Click Three Dots menu on farm card in Pending Farms"):
        time.sleep(5)
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
        time.sleep(10)
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
        time.sleep(2)
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
        time.sleep(2)
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


def overview_option(driver, obj, test_flow_steps):
    with allure.step("28. Click Overview option in Three Dots menu"):
        time.sleep(5)
        if not smart_click(driver, "Overview option", obj.Overview_xpath, "Overview"):
            pytest.fail(
                "Could not find or click the 'Overview' option in the three dots menu."
            )
        test_flow_steps.append(
            {"step": "Click Overview option in three dots menu", "status": "Success"}
        )


def edit_farm(driver, obj, test_flow_steps):
    with allure.step("29. Click Edit Farm in Three Dots menu"):
        time.sleep(5)
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
        time.sleep(5)
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
        time.sleep(5)
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
        time.sleep(5)
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
        time.sleep(5)
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
        time.sleep(5)
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
        time.sleep(5)
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


def draw_boundary_on_map(driver, obj, test_flow_steps):
    with allure.step("36. Draw boundary polygon on map"):
        time.sleep(15)  # Wait for map to fully load
        coordinates = [
            (390, 760),  # Top-left corner
            (690, 760),  # Top-right corner
            (690, 1160),  # Bottom-right corner
            (390, 1160),  # Bottom-left corner
            (390, 760),  # Close the polygon (first point)
            (390, 760),  # Confirm close
        ]
        for coord in coordinates:
            driver.tap([coord], 100)  # 100 ms per tap
        test_flow_steps.append({"step": "Draw Boundary on Map", "status": "Success"})