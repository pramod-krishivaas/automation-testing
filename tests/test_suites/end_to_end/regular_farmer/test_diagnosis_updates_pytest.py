import time
import allure
import pytest
import json
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy

from utils.location_utils import reset_device_location
from tests.pages.regular_farmer.regular_farmer_diagnosis_page import (
   farm_card, diagnosis_icon, select_crop_name, ok_btn, confirm_btn, camera_icon, image_capture_icon, video_capture_icon, stop_video_capture_icon, load_locators_once,
   audio_capture_icon, audio_stop_icon, image_comment_input, cancel_image_comment_btn, image_save_btn, general_comment_input, general_remark_audio_capture_icon, general_remark_audio_stop_icon,
   back_btn, submit_btn, camera_icon2
)
from tests.pages.regular_client.regular_client_onboarding_page import (
    set_run_location
)

@allure.epic("Diagnosis Updates Flow")
@allure.feature("Diagnosis Updates")
class TestDiagnosisUpdates:

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, request):
        load_locators_once(self, request)

    @allure.story("Successful Diagnosis Updates Flow")
    @allure.title("E2E_RF_005 -- Provide media and verify in Diagnosis Updates")
    def test_E2E_RF_005(self, driver):
            test_flow_steps = []
            try:
                farm_card(driver, self, test_flow_steps)
                set_run_location(driver, self, test_flow_steps)
                diagnosis_icon(driver, self, test_flow_steps)
                select_crop_name(driver, self, test_flow_steps)
                ok_btn(driver, self, test_flow_steps)
                ok_btn(driver, self, test_flow_steps)
                # ok_btn(driver, self, test_flow_steps)
                confirm_btn(driver, self, test_flow_steps)
                ok_btn(driver, self, test_flow_steps)
                camera_icon(driver, self, test_flow_steps)
                image_capture_icon(driver, self, test_flow_steps)
                image_comment_input(driver, self, test_flow_steps)
                image_save_btn(driver, self, test_flow_steps)
                time.sleep(3) # Wait for image to be saved
                camera_icon2(driver, self, test_flow_steps)
                video_capture_icon(driver, self, test_flow_steps)
                time.sleep(3)
                stop_video_capture_icon(driver, self, test_flow_steps)

                time.sleep(3)
                # audio_capture_icon(driver, self, test_flow_steps)
                # time.sleep(3) # Wait for audio recording to complete
                # audio_stop_icon(driver, self, test_flow_steps)
                # time.sleep(2)
                general_comment_input(driver, self, test_flow_steps)
                # general_remark_audio_capture_icon(driver, self, test_flow_steps)
                time.sleep(3) # Wait for audio recording to complete
                # general_remark_audio_stop_icon(driver, self, test_flow_steps)
                submit_btn(driver, self, test_flow_steps)

            finally:
                reset_device_location(driver)
                os.makedirs("test-flows", exist_ok=True)
                with open("test-flows/diagnosis_updates_flow_success.json", "w") as f:
                    json.dump(test_flow_steps, f, indent=4)


