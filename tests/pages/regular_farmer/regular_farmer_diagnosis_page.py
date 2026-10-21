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
    locators_path = os.path.join(project_root, "locators", "diagnosis_updates.json")
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
    
    request.cls.diagnosis_icon_xpath = resolve("diagnosis_icon")
    request.cls.farm_card_xpath = resolve("regular_fr_farm_card")
    request.cls.navigation_icon_xpath = resolve("navigation_icon")
    request.cls.select_crop_name_xpath = resolve("select_crop_name")
    request.cls.ok_btn_xpath = resolve("ok")
    request.cls.confirm_btn_xpath = resolve("confirm_btn")
    request.cls.camera_icon_xpath = resolve("camera_icon")
    request.cls.camera_icon2_xpath = resolve("camera_icon2")
    request.cls.image_capture_icon_xpath = resolve("image_capture_icon")
    request.cls.video_capture_icon_xpath = resolve("video_capture_icon")
    request.cls.stop_video_capture_icon_xpath = resolve("stop_video_capture_icon")
    request.cls.audio_capture_icon_xpath = resolve("audio_capture_icon")
    request.cls.audio_stop_icon_xpath = resolve("audio_stop_icon")
    request.cls.image_comment_inp_xpath = resolve("image_comment_inp")
    request.cls.cancel_image_comment_btn_xpath = resolve("cancel_image_comment_btn")
    request.cls.image_save_btn_xpath = resolve("image_save_btn")
    request.cls.general_comment_inp_xpath = resolve("general_comment_inp")
    request.cls.general_remark_audio_capture_icon_xpath = resolve("general_remark_audio_capture_icon")
    request.cls.general_remark_audio_stop_icon_xpath = resolve("general_remark_audio_stop_icon")
    request.cls.back_btn_xpath = resolve("back_btn")
    request.cls.submit_btn_xpath = resolve("submit_btn")


# ===========================================================================
# TestDiagnosisUpdates class — kept for backward compatibility
# ===========================================================================

@allure.epic("Farmer Updates Flow")
@allure.feature("Updates")
class TestDiagnosisUpdates:
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

def diagnosis_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click diagnosis icon   "):
        if not smart_click(
            driver, "Diagnosis icon", obj.diagnosis_icon_xpath, "Diagnosis icon"
        ):
            pytest.fail("Could not find or click the 'Diagnosis icon' button.")
        test_flow_steps.append({"step": "Click Diagnosis icon", "status": "Success"})

def select_crop_name(driver, obj, test_flow_steps):
    with allure.step("1. Select crop name"):
        if not smart_click(
            driver, "Select crop name", obj.select_crop_name_xpath, "Select crop name"
        ):
            pytest.fail("Could not find or click the 'Select crop name' button.")
        test_flow_steps.append({"step": "Select crop name", "status": "Success"})

def ok_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click OK button"):
        if not smart_click(
            driver, "OK button", obj.ok_btn_xpath, "OK button"
        ):
            pytest.fail("Could not find or click the 'OK button' button.")
        test_flow_steps.append({"step": "Click OK button", "status": "Success"})

def confirm_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click Confirm button"):
        if not smart_click(
            driver, "Confirm button", obj.confirm_btn_xpath, "Confirm button"
        ):
            pytest.fail("Could not find or click the 'Confirm button' button.")
        test_flow_steps.append({"step": "Click Confirm button", "status": "Success"})

def camera_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click Camera icon"):
        if not smart_click(
            driver, "Camera icon", obj.camera_icon_xpath, "Camera icon"
        ):
            pytest.fail("Could not find or click the 'Camera icon' button.")
        test_flow_steps.append({"step": "Click Camera icon", "status": "Success"})

def camera_icon2(driver, obj, test_flow_steps):
    with allure.step("1. Click Camera icon"):
        if not smart_click(
            driver, "Camera icon", obj.camera_icon2_xpath, "Camera icon"
        ):
            pytest.fail("Could not find or click the 'Camera icon' button.")
        test_flow_steps.append({"step": "Click Camera icon", "status": "Success"})

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

def audio_stop_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click audio stop icon"):
        if not smart_click(
            driver, "Audio stop icon", obj.audio_stop_icon_xpath, "Audio stop icon"
        ):
            pytest.fail("Could not find or click the 'Audio stop icon' button.")
        test_flow_steps.append({"step": "Click Audio stop icon", "status": "Success"})

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

def image_save_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click image save button"):
        if not smart_click(
            driver, "Image save button", obj.image_save_btn_xpath, "Image save button"
        ):
            pytest.fail("Could not find or click the 'Image save button' button.")
        test_flow_steps.append({"step": "Click Image save button", "status": "Success"})

def general_comment_input(driver, obj, test_flow_steps):
    with allure.step("1. Enter General Comment"):
        if not set_input_value(
            driver, obj.general_comment_inp_xpath, "general remark test comment", element_name="General Comment input"
        ):
            pytest.fail("Could not find or interact with the 'General Comment' input field.")
        test_flow_steps.append({"step": "Enter General Comment", "status": "Success"})

def general_remark_audio_capture_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click general remark audio capture icon"):
        if not smart_click(
            driver, "General remark audio capture icon", obj.general_remark_audio_capture_icon_xpath, "General remark audio capture icon"
        ):
            pytest.fail("Could not find or click the 'General remark audio capture icon' button.")
        test_flow_steps.append({"step": "Click General remark audio capture icon", "status": "Success"})

def general_remark_audio_stop_icon(driver, obj, test_flow_steps):
    with allure.step("1. Click general remark audio stop icon"):
        if not smart_click(
            driver, "General remark audio stop icon", obj.general_remark_audio_stop_icon_xpath, "General remark audio stop icon"
        ):
            pytest.fail("Could not find or click the 'General remark audio stop icon' button.")
        test_flow_steps.append({"step": "Click General remark audio stop icon", "status": "Success"})

def back_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click back button"):
        if not smart_click(
            driver, "Back button", obj.back_btn_xpath, "Back button"
        ):
            pytest.fail("Could not find or click the 'Back button' button.")
        test_flow_steps.append({"step": "Click Back button", "status": "Success"})

def submit_btn(driver, obj, test_flow_steps):
    with allure.step("1. Click submit button"):
        if not smart_click(
            driver, "Submit button", obj.submit_btn_xpath, "Submit button"
        ):
            pytest.fail("Could not find or click the 'Submit button' button.")
        test_flow_steps.append({"step": "Click Submit button", "status": "Success"})
