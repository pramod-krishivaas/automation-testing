"""
Shared login page object for the UNIFIED app.

Every role (regular_farmer / regular_client / state_farmer / state_client) goes
through the exact same login screen — one phone number + MPIN/OTP — so this lives
in `pages/common/` and is reused by every role's test suite. Post-login, the app
redirects to a home screen by PRIORITY (state_client > state_farmer >
regular_farmer > regular_client); reaching the *intended* role is handled by
`pages/common/switch_page.py`.
"""
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
from utils.wait_utils import smart_click

sys.dont_write_bytecode = True


def load_locators_once(self, request):
    """
    Load the unified locator file ONCE per test class and bind:
      • login_screen  → request.cls.<name>_xpath   (flat attributes, as before)
      • switch_control → request.cls.switch_toggle_button_xpath + request.cls.switch_targets
      • home_markers   → request.cls.home_markers   (role -> xpath dict)
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    locators_path = os.path.join(project_root, "locators", "unified_app.json")
    with open(locators_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    # Guard against lone `\u` sequences that aren't valid JSON unicode escapes.
    raw = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', raw)
    xpaths = json.loads(raw)

    # ── Login screen ────────────────────────────────────────────────
    login = xpaths.get("login_screen", {})
    request.cls.language_next_xpath           = login.get("next_button_language_login")
    request.cls.allow_picture_button_xpath    = login.get("allow_picture_button")
    request.cls.allow_location_button_xpath   = login.get("allow_location_button")
    request.cls.allow_audio_button_xpath      = login.get("allow_audio_button")
    request.cls.allow_notifications_button_xpath = login.get("allow_notifications_button")
    request.cls.phone_number_input_xpath      = login.get("phone_number_input")
    request.cls.next_button_login_xpath       = login.get("next_button_login")
    request.cls.verify_button_login_xpath     = login.get("verify_button_login")
    request.cls.change_mobile_number_xpath    = login.get("change_mobile_number")
    request.cls.resend_otp_button_xpath       = login.get("resend_otp_button")
    request.cls.mpin_input_xpath              = login.get("mpin_input")
    request.cls.reset_mpin_button_xpath       = login.get("reset_mpin_button")
    request.cls.mpin_input_0_xpath            = login.get("mpin_input_0")
    request.cls.mpin_input_1_xpath            = login.get("mpin_input_1")
    request.cls.mpin_input_2_xpath            = login.get("mpin_input_2")
    request.cls.mpin_input_3_xpath            = login.get("mpin_input_3")

    # ── Switch control ──────────────────────────────────────────────
    switch = xpaths.get("switch_control", {})
    request.cls.switch_toggle_button_xpath = switch.get("switch_toggle_button")
    request.cls.switch_targets = {
        "regular_farmer": switch.get("target_regular_farmer"),
        "regular_client": switch.get("target_regular_client"),
        "state_farmer":   switch.get("target_state_farmer"),
        "state_client":   switch.get("target_state_client"),
    }

    # ── Home markers (landed-app detection) ─────────────────────────
    markers = xpaths.get("home_markers", {})
    request.cls.home_markers = {
        "regular_farmer": markers.get("regular_farmer"),
        "regular_client": markers.get("regular_client"),
        "state_farmer":   markers.get("state_farmer"),
        "state_client":   markers.get("state_client"),
    }


# ════════════════════════════════════════════════════════════════════
#  LOGIN FLOW STEPS  (shared by all roles)
# ════════════════════════════════════════════════════════════════════
def language_next(driver, obj, test_flow_steps):
    with allure.step("Next button on language selection screen"):
        if not smart_click(driver, "Next Button (Language)", obj.language_next_xpath, "Next"):
            pytest.fail("Could not find or click the 'Next' button on language selection.")
        test_flow_steps.append({"step": "Click Next on language selection", "status": "Success"})


def picture_permissions(driver, obj, test_flow_steps):
    with allure.step("Allow picture permission"):
        if not smart_click(driver, "Allow picture", obj.allow_picture_button_xpath, "While using the app"):
            pytest.fail("Could not find or click the 'Allow picture' permission button.")
        test_flow_steps.append({"step": "Allow picture permission", "status": "Success"})


def login_permissions_location(driver, obj, test_flow_steps):
    with allure.step("Allow location permission"):
        if not smart_click(driver, "Allow location", obj.allow_location_button_xpath, "While using"):
            pytest.fail("Could not find or click the 'Allow location' permission button.")
        test_flow_steps.append({"step": "Allow location permission", "status": "Success"})


def login_permissions_audio(driver, obj, test_flow_steps):
    with allure.step("Allow audio permission"):
        if not smart_click(driver, "Allow audio", obj.allow_audio_button_xpath, "While using the app"):
            pytest.fail("Could not find or click the 'Allow audio' permission button.")
        test_flow_steps.append({"step": "Allow audio permission", "status": "Success"})


def login_permissions_notifications(driver, obj, test_flow_steps):
    with allure.step("Allow notifications permission"):
        if not smart_click(driver, "Allow notifications", obj.allow_notifications_button_xpath, "Allow"):
            pytest.fail("Could not find or click the 'Allow notifications' permission button.")
        test_flow_steps.append({"step": "Allow notifications permission", "status": "Success"})


def login_enter_phone(driver, obj, test_flow_steps, phone_number):
    with allure.step(f"Enter phone number {phone_number}"):
        phone_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.XPATH, obj.phone_number_input_xpath))
        )
        phone_input.clear()
        phone_input.send_keys(str(phone_number))
        test_flow_steps.append({"step": "Enter phone number", "status": "Success", "value": str(phone_number)})


def login_submit_phone(driver, obj, test_flow_steps):
    with allure.step("Tap Next after phone number"):
        if not smart_click(driver, "Next (login)", obj.next_button_login_xpath, "Next"):
            pytest.fail("Could not find or click the 'Next' button after entering phone number.")
        test_flow_steps.append({"step": "Click Next after phone number", "status": "Success"})


def login_enter_mpin_digits(driver, obj, test_flow_steps, mpin="1234"):
    """Enter MPIN into the 4 individual digit boxes (otp_input_0..3)."""
    with allure.step(f"Enter MPIN digits"):
        mpin_xpaths = [
            obj.mpin_input_0_xpath,
            obj.mpin_input_1_xpath,
            obj.mpin_input_2_xpath,
            obj.mpin_input_3_xpath,
        ]
        digits = list(str(mpin))
        if len(digits) != len(mpin_xpaths):
            pytest.fail(f"MPIN '{mpin}' does not have {len(mpin_xpaths)} digits.")
        for digit, xpath in zip(digits, mpin_xpaths):
            box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((AppiumBy.XPATH, xpath))
            )
            box.clear()
            box.send_keys(digit)
        test_flow_steps.append({"step": "Enter MPIN digits", "status": "Success"})


def login_submit_mpin(driver, obj, test_flow_steps):
    with allure.step("Submit / Verify MPIN"):
        if not smart_click(driver, "Verify MPIN", obj.verify_button_login_xpath, "Verify"):
            pytest.fail("Could not find or click the 'Verify mPIN' button.")
        test_flow_steps.append({"step": "Submit MPIN", "status": "Success"})


def do_login(driver, obj, test_flow_steps, phone_number, mpin="1234", handle_permissions=True):
    """
    Full shared login flow: (optional permissions) → language → phone → MPIN.
    Lands on whichever role's home the number resolves to by priority.
    Individual permission steps are best-effort so tests still run when the OS
    dialogs don't appear (e.g. permissions already granted on a warm install).
    """
    if handle_permissions:
        for step in (
            picture_permissions,
            login_permissions_location,
            login_permissions_audio,
            # login_permissions_notifications,
        ):
            try:
                step(driver, obj, test_flow_steps)
            except Exception as e:
                print(f"[login] Permission step {step.__name__} skipped: {e}")

    try:
        language_next(driver, obj, test_flow_steps)
    except Exception as e:
        print(f"[login] Language screen skipped: {e}")

    login_enter_phone(driver, obj, test_flow_steps, phone_number)
    login_submit_phone(driver, obj, test_flow_steps)
    # login_enter_mpin_digits(driver, obj, test_flow_steps, mpin)
    login_submit_mpin(driver, obj, test_flow_steps)
