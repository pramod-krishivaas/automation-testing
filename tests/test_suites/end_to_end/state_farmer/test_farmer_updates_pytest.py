import time
import allure
import pytest
import json
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy

from utils.location_utils import reset_device_location
from tests.pages.regular_farmer.regular_farmer_updates_page import (
   farm_card, navigation_icon, image_capture_icon, video_capture_icon, audio_capture_icon, image_comment_input, cancel_image_comment_btn, continue_btn, save_btn, load_locators_once,
   stop_video_capture_icon
)

@allure.epic("Farmer Updates Flow")
@allure.feature("Updates")
class TestFarmerUpdates:

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, request):
        load_locators_once(self, request)

    @allure.story("Successful Farmer Updates Flow")
    @allure.title("E2E_SF_005 -- Provide media and verify in Farmer Updates")
    def test_E2E_SF_005(self, driver):
            test_flow_steps = []
            try:
                farm_card(driver, self, test_flow_steps)
                navigation_icon(driver, self, test_flow_steps)
                image_capture_icon(driver, self, test_flow_steps)
                image_comment_input(driver, self, test_flow_steps)
                continue_btn(driver, self, test_flow_steps)
                audio_capture_icon(driver, self, test_flow_steps)
                time.sleep(3) # Wait for audio recording to complete
                audio_capture_icon(driver, self, test_flow_steps)
                video_capture_icon(driver, self, test_flow_steps)
                stop_video_capture_icon(driver, self, test_flow_steps)
                save_btn(driver, self, test_flow_steps)

            finally:
                reset_device_location(driver)
                os.makedirs("test-flows", exist_ok=True)
                with open("test-flows/farmer_updates_flow_success.json", "w") as f:
                    json.dump(test_flow_steps, f, indent=4)


