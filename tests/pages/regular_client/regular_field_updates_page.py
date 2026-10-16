import time
import allure
import pytest
import io
import json
import os
import re
import sys

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from tests.utils.wait_utils import open_date_picker, smart_click, scroll_and_click_text, wait_until_displayed
from utils.ui_actions import set_input_value

sys.dont_write_bytecode = True

def load_locators_once(self, request):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    locators_path = os.path.join(project_root, "locators", "fr_fa_updates.json")
    print(f"Loading locators from: {locators_path}")
    with open(locators_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    raw = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", raw)
    locators = json.loads(raw)

    # ── locator-type sources (flat: key -> locator) ─────────────────────────
    # Priority when resolving a single value per key: xpath_locators (most
    # complete) > accessibility_ids > element_ids.
    accessibility_ids = locators.get("accessibility_ids", {})
    element_ids = locators.get("element_ids", {})
    xpath_locators = locators.get("xpath_locators", {})

    def resolve(key: str):
        """Return the first available locator for `key`, or raise if missing."""
        value = (
            xpath_locators.get(key)
            or accessibility_ids.get(key)
            or element_ids.get(key)
        )
        if not value:
            raise KeyError(f"Locator '{key}' not found in {locators_path}")
        return value

    request.cls.farm_card_xpath = resolve("regular_fa_farm_card")
    request.cls.farmer_list_tab_xpath = resolve("farmer_list_tab")
    request.cls.farmer_xpath = resolve("farmer")
    request.cls.navigation_icon_xpath = resolve("navigation_icon")
    request.cls.image_capture_icon_xpath = resolve("image_capture_icon")
    request.cls.video_capture_icon_xpath = resolve("video_capture_icon")
    request.cls.stop_video_capture_icon_xpath = resolve("stop_video_capture_icon")
    request.cls.audio_capture_icon_xpath = resolve("audio_capture_icon")
    request.cls.image_comment_inp_xpath = resolve("image_comment_inp")
    request.cls.cancel_image_comment_btn_xpath = resolve("cancel_image_comment_btn")
    request.cls.continue_btn_xpath = resolve("continue_btn")
    request.cls.save_btn_xpath = resolve("save_btn")


# ===========================================================================
# TestFieldUpdates class — kept for backward compatibility
# ===========================================================================

@allure.epic("Field Updates Flow")
@allure.feature("Updates")
class TestFieldUpdates:
    @pytest.fixture(scope="class", autouse=True)
    def _load_locators_once(request):
        """Delegates to the shared standalone loader."""
        load_locators_once(request.cls, request)

def farm_card(driver, obj, test_flow_steps):
    with allure.step("1. Click farm card"):
        if not smart_click(
            driver, "Farm card", obj.farm_card_xpath, "Farm card"
        ):
            pytest.fail("Could not find or click the 'Farm card' button.")
        test_flow_steps.append({"step": "Click Farm card", "status": "Success"})

def navigation_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click navigation icon"):
        if not smart_click(
            driver, "Navigation icon", obj.navigation_icon_xpath, "Navigation icon"
        ):
            pytest.fail("Could not find or click the 'Navigation icon' button.")
        test_flow_steps.append({"step": "Click Navigation icon", "status": "Success"})

def image_capture_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click image capture icon"):
        if not smart_click(
            driver, "Image capture icon", obj.image_capture_icon_xpath, "Image capture icon"
        ):
            pytest.fail("Could not find or click the 'Image capture icon' button.")
        test_flow_steps.append({"step": "Click Image capture icon", "status": "Success"})

def video_capture_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click video capture icon"):
        if not smart_click(
            driver, "Video capture icon", obj.video_capture_icon_xpath, "Video capture icon"
        ):
            pytest.fail("Could not find or click the 'Video capture icon' button.")
        test_flow_steps.append({"step": "Click Video capture icon", "status": "Success"})

def stop_video_capture_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click stop video capture icon"):
        if not smart_click(
            driver, "Stop video capture icon", obj.stop_video_capture_icon_xpath, "Stop video capture icon"
        ):
            pytest.fail("Could not find or click the 'Stop video capture icon' button.")
        test_flow_steps.append({"step": "Click Stop video capture icon", "status": "Success"})

def audio_capture_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click audio capture icon"):
        if not smart_click(
            driver, "Audio capture icon", obj.audio_capture_icon_xpath, "Audio capture icon"
        ):
            pytest.fail("Could not find or click the 'Audio capture icon' button.")
        test_flow_steps.append({"step": "Click Audio capture icon", "status": "Success"})

def image_comment_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter Image Comment"):
        if not set_input_value(
            driver, obj.image_comment_inp_xpath, "test comment", element_name="Image Comment input"
        ):
            pytest.fail("Could not find or interact with the 'Image Comment' input field.")
        test_flow_steps.append({"step": "Enter Image Comment", "status": "Success"})

def cancel_image_comment_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click cancel image comment button"):
        if not smart_click(
            driver, "Cancel image comment button", obj.cancel_image_comment_btn_xpath, "Cancel image comment button"
        ):
            pytest.fail("Could not find or click the 'Cancel image comment button' button.")
        test_flow_steps.append({"step": "Click Cancel image comment button", "status": "Success"})

def continue_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click continue button"):
        if not smart_click(
            driver, "Continue button", obj.continue_btn_xpath, "Continue button"
        ):
            pytest.fail("Could not find or click the 'Continue button' button.")
        test_flow_steps.append({"step": "Click Continue button", "status": "Success"})

def save_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click save button"):
        if not smart_click(
            driver, "Save button", obj.save_btn_xpath, "Save button"
        ):
            pytest.fail("Could not find or click the 'Save button' button.")
        test_flow_steps.append({"step": "Click Save button", "status": "Success"})

def farmer_list_tab(driver, obj, test_flow_steps):
    with allure.step("1. Click farmer list tab"):
        if not smart_click(
            driver, "Farmer list tab", obj.farmer_list_tab_xpath, "Farmer list tab"
        ):
            pytest.fail("Could not find or click the 'Farmer list tab' button.")
        test_flow_steps.append({"step": "Click Farmer list tab", "status": "Success"})

def farmer(driver, obj, test_flow_steps):
    with allure.step("1. Click farmer"):
        if not smart_click(
            driver, "Farmer", obj.farmer_xpath, "Farmer"
        ):
            pytest.fail("Could not find or click the 'Farmer' button.")
        test_flow_steps.append({"step": "Click Farmer", "status": "Success"})
