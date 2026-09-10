import time
import allure
import pytest
import json
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from appium.webdriver.common.appiumby import AppiumBy

from utils.wait_utils import smart_click

from tests.pages.state_client.state_client_onboarding_page import (
    load_locators_once, add_button, add_farmer_button, farm_village_dropdown,
    farm_village_item, download_boundary_button, submit_village, search_by_bunds_lat_long_option, click_search_by_bunds_lat_long_input,
    enter_search_by_bunds_lat_long_value, select_bund, confirm_bunds_selection_button, crop_name_dropdown, crop_name_item, plantation_date,
    calendar_ok_button, submit_crop_button, add_farmer_name_input, add_farmer_phone_input, submit_button_add_farmer
)


@allure.epic("Onboarding Flow")
@allure.feature("Authentication")
class TestOnboarding:

    @pytest.fixture(scope="class", autouse=True)
    def setup(self, request):
        load_locators_once(self, request)

    @allure.story("Successful Onboarding")
    @allure.title("Dashboard → Add Farmer → Add Farm → Add Crop")
    def test_add_new_farmer_farm_crop_flow(self, driver):
            test_flow_steps = []
            try:
                # After the login run lands on the dashboard, a loader overlays the
                # screen briefly. Wait it out so the Add button is actually tappable
                # (without this the tap can land on the loader and the test fails).
                time.sleep(6)
                add_button(driver, self, test_flow_steps)
                add_farmer_button(driver, self, test_flow_steps)
                farm_village_dropdown(driver, self, test_flow_steps)
                farm_village_item(driver, self, test_flow_steps)
                download_boundary_button(driver, self, test_flow_steps)
                time.sleep(15)
                submit_village(driver, self, test_flow_steps)
                # search_by_bunds_lat_long_option(driver, self, test_flow_steps)
                enter_search_by_bunds_lat_long_value(driver, self, test_flow_steps, "580")
                click_search_by_bunds_lat_long_input(driver, self, test_flow_steps)
                select_bund(driver, self, test_flow_steps)
                confirm_bunds_selection_button(driver, self, test_flow_steps)
                time.sleep(4)
                add_farmer_name_input(driver, self, test_flow_steps)
                add_farmer_phone_input(driver, self, test_flow_steps)
                submit_button_add_farmer(driver, self, test_flow_steps)
                crop_name_dropdown(driver, self, test_flow_steps)
                crop_name_item(driver, self, test_flow_steps)
                plantation_date(driver, self, test_flow_steps)
                calendar_ok_button(driver, self, test_flow_steps)
                submit_crop_button(driver, self, test_flow_steps)
    
            finally:
                os.makedirs("test-flows", exist_ok=True)
                with open("test-flows/onboarding_flow_success.json", "w") as f:
                    json.dump(test_flow_steps, f, indent=4)